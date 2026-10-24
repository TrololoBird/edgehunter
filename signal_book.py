"""
Signal lifecycle and anomaly memory for the dashboard.

A directional setup belongs to a strategy (strategies/): the strategy turns it into a PLAN (its anchor - a leg, a
level or a range -, entry style, zone, invalidation, stop reference and targets by intent); this module runs the same
lifecycle for every plan:

    BIAS    the coin's history / level map is still loading (at most plan_wait_sec for 1h-dependent strategies), or
            the plan stopped existing later; a setup without an anchor never becomes a card (vetoed 'no_leg')
    WATCH   waiting for price to reach the plan's zone
    ZONE    price is in the zone: waiting for the structure-shift trigger on the plan's trigger timeframe
    ENTRY   entry / SL / TP set: at the confirmation (plan entry 'confirm') when R:R to TP1 allows it, else on the
            trigger in the zone
    TP1/TP2 targets reached, trade still managed;  final: TP3, SL, CLOSED (time / opposite setup), INVALID, MISSED,
            EXPIRED

Shared rules: INVALID beyond the plan's invalidation (fixed at the card's start when the extreme was known at the
confirmation); MISSED when TP1 (fixed beyond the furthest price reached since the anchor) is reached before an entry;
a continuation whose leg makes a new extreme goes back to waiting and is re-measured; a new card closes the open card
of the opposite direction when its structure timeframe is the same or higher; a card that finished blocks a new one
on the same anchor; every setup carries its market crowd (CONFIG.market) and context (trend, volatility) for the
journal / stats / ML - no limit on the number of cards.

Filters (each journaled with its reason instead of silently dropped, so stats.py can measure it):
- a perp-led continuation (spot disagrees) never becomes a card (journal.veto_reason);
- a strategy's context policy (a sweep against the coin's 1h trend: 'against_trend'), a disabled strategy;
- a spring's entry needs its "test": the pullback trades on lower volume than the spring candle;
- every entry carries its confirmations (strategies/confirm.py: taker flow, spot flow, OI, order flow at the
  extreme); a required one that is negative vetoes it ('no_oi', 'no_orderflow', ...: journaled as a vetoed entry,
  the card keeps waiting for the next trigger).

Statuses follow the futures price at each scan; the journal replays each entry on 1m candles with a manual fill.
Partial phases go to the watchlist; other Tier-0 anomalies are remembered for CONFIG.tier0.display_hold_sec.
"""
import copy
import logging
import time
from strategies.ict import fvg_setup, fvg_trigger, range_position, touch_confirm, touch_trigger
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from strategies.base import CardLevels

from config import CONFIG
from journal import classify, veto_reason
from levels import MINUTE_MS, funding_r, ltf_trigger, pullback_spread_ok, pullback_volume_ok, resample, slippage_bps

# eng-156: the cards' resample of the minute ring ran uncached for every card in its zone on every scan and every
# managed minute (watchdog: levels.resample under _try_entry / _trail stalled the loop 1-2 s a minute). Cached per
# (coin, tf) like fetcher._RESAMPLE_CACHE: the key is the minutes' count, first / last minute, the close bucket and the
# recent minutes' content (a REST-revised or patched minute changes it); callers get copies (no shared bars)
_SB_RESAMPLE: Dict[Tuple[str, int], Tuple[tuple, List]] = {}


def _resample(symbol: str, minutes, tf: int, until_ms) -> List[List[float]]:
    if not minutes:
        return []
    from strategies.ind_panel import content_digest
    tf = int(tf)
    key = (len(minutes), minutes[0][0], minutes[-1][0], int(until_ms // (tf * MINUTE_MS)) if until_ms else None,
           content_digest(minutes[-180:]))
    hit = _SB_RESAMPLE.get((symbol, tf))
    if hit is not None and hit[0] == key:
        bars = hit[1]
    else:
        bars = resample(minutes, tf, until_ms)
        if len(_SB_RESAMPLE) > 1500:
            _SB_RESAMPLE.clear()
        _SB_RESAMPLE[(symbol, tf)] = (key, bars)
    return [list(b) for b in bars]
HOUR_MS, DAY_MS = 3_600_000, 86_400_000
from strategies.maniac import in_session
from strategies.maniac_strategies import MANIAC_STRATEGIES

MANIAC_NAMES = frozenset(s.name for s in MANIAC_STRATEGIES)
from strategies import PlanInput, Strategy, strategy_of
from strategies import bias as htf_bias, confirm, profiles

# eng-84: methods whose exits are their own long-horizon rule (the Turtles' channel, Connors' SMA5, O'Neil's measured
# move): no break-even / partial management
MANAGE_EXEMPT = ('breakout', 'connors', 'cup_handle', 'oi_build')
# break-even + the round trip's costs (taker 0.05% x 2 + slippage ~0.05%): a break-even stop that fills is ~0, not -costs
BE_COST = 0.0015
# eng-84: the regime each method needs (ADX(14) of 4h): trend-following methods / mean-reversion methods
REGIME_TREND = ('continuation', 'pump', 'oi_build')
REGIME_RANGE = ('bollinger', 'market_profile')
from strategies.geometry import entry_levels

logger = logging.getLogger(__name__)

def ict_gated(mode: str, setup: str) -> bool:
    """
    ICT's sweep / continuation models trade inside the London / New York kill zones only (eng-58). The Silver Bullet
    shares the 'sweep' name but has its own windows (03-04, 10-11, 14-15 New York): eng-58 vetoed two of its three.
    """
    return (mode in ('sweep', 'continuation') and not str(setup or '').startswith('SILVER BULLET')
            and bool(CONFIG.strategies.smt_session))


FINAL_STATUSES = {'TP3', 'SL', 'CLOSED', 'INVALID', 'MISSED', 'EXPIRED'}
# A setup that never became a card (no anchor / no room left to a target): removed, not a result
DROPPED = 'DROPPED'
DROP_COOLDOWN_SEC = 1800          # eng-84: a dropped card's setup is not re-created for half an hour
# How long a finished card's anchor blocks a new card on it
FINISHED_LEG_MEMORY_SEC = 24 * 3600
# Structure timeframes by rank: an opposite setup closes a card only from the same or a higher timeframe
TF_RANK = {'1m': 0, '5m': 1, '15m': 2, '1h': 3, '4h': 4, '1d': 5}
# A strategy's structure timeframe when a card has no plan (restored after a restart)
DEFAULT_TF: dict = {}          # (a playbook's own `default_tf` overrides the 15m default)

# confirm_of(symbol, strategy, direction, since_ms, until_ms, extreme_ms) -> {confirmation: True / False / None | str}
ConfirmCheck = Callable[[str, str, int, int, int, Optional[int]], Dict]

# The live candle's items in the scanner's plan key (timestamp, high, low): only leg plans follow the live candle; a
# level / range / cascade plan recomputed on every new tick high cost ~2s of loop time when many cards were open
LIVE_KEY = slice(1, 4)


def _without_live(key: tuple) -> tuple:
    return key[:LIVE_KEY.start] + key[LIVE_KEY.stop:]

# Which anomaly label a coin's row shows when several readings of one event arrive (higher = more significant)
ANOMALY_PRIORITY = {
    'IMPULSE UP': 10, 'IMPULSE DOWN': 10, 'LIQ CASCADE': 9, 'SHORT SQUEEZE': 8, 'LONG FLUSH': 8,
    'WHALES BUY': 7, 'WHALES SELL': 7, 'ALGO BUY': 6, 'ALGO SELL': 6, 'OI SURGE': 5, 'OI FLUSH': 5,
    'ONE-VENUE': 4, 'UNUSUAL': 3, 'IMPULSE UNCONFIRMED': 2, 'ABSORPTION': 1, 'VOLUME SPIKE': 1,
}


def is_directional(kind: str, group_key: str) -> bool:
    return strategy_of(group_key) is not None


def htf_zone_at(zones, price: float) -> bool:
    """A zone of 4h or higher (order block / FVG / BPR / breaker of 4h, daily, weekly; daily swings; HTF range)
    contains the price."""
    import re
    for z in zones:
        if z.lo <= price <= z.hi and any(re.search(r'_(4h|1d|1w)$', k) or k in ('swing_1d', 'htf') for k in z.kinds):
            return True
    return False


def _dur(sec: float) -> str:
    """600 -> '10m', 7200 -> '2h' (reasons are parsed by the dashboard)."""
    return f"{int(sec // 3600)}h" if sec >= 3600 and sec % 3600 == 0 else f"{int(sec // 60)}m"


def _jsonable(v) -> bool:
    if isinstance(v, (int, float, str, bool, type(None))):
        return True
    if isinstance(v, (list, tuple)):
        return all(_jsonable(x) for x in v)
    if isinstance(v, dict):
        return all(isinstance(k, str) and _jsonable(x) for k, x in v.items())
    return False


# eng-104: no_bias is a filter (shadow); audit C08: no_test_data - a required test that could not be observed is not
# a passed one, and not a shadow filter either
_REAL_NO = ('no_data', 'no_leg', 'no_room', 'no_anchor', 'no_test_data')


# setups measured in shadow only (journaled, never traded) by their name: prefix / exact name -> the veto they get.
# One list for _enter and the dashboard (audit N33: the page described setups by a hand-kept table)
# audit (Connors): the book's long (RSI2X LONG) is traded; our eng-84 cross-back entry (RSI2 LONG / SHORT) and the
# mirrored short the book does not state (RSI2X SHORT) are measured in shadow
SHADOW_SETUPS = (('RSI2 ', 'rsi2_crossback_shadow'), ('RSI2X SHORT', 'connors_short_shadow'),
                 ('FLUSH REVERSAL', 'cascade_shadow'), ('SQUEEZE REVERSAL', 'cascade_shadow'),
                 ('OI BUILD ', 'oi_shadow'), ('BB3 ', 'bb3_shadow'))


def shadow_of(group_key: str) -> Optional[str]:
    return next((why for name, why in SHADOW_SETUPS
                 if (group_key.startswith(name) if name.endswith(' ') else group_key == name)), None)


def shadow_veto(sig: Dict, reason: Optional[str]) -> Optional[str]:
    """eng-101: a reason in strategies.shadow_vetoes does not block - it is added to sig['shadow_veto'] and None is
    returned ('no_*' covers the detectors' required confirmations, not the structural no_data / no_leg ...)."""
    if not reason:
        return reason
    names = CONFIG.strategies.shadow_vetoes
    # eng-138: a missing entry CONFIRMATION (confirm.missing: 'no_<confirmation>', a required / journal-promoted one)
    # stays a filter in shadow as before; a setup's own required part (no_spring_test, po3_bias_required, ...) blocks
    conf = '<confirmations>' in names and reason.startswith('no_') and reason[3:] in confirm.required_names()
    if reason in names or conf or ('no_*' in names and reason.startswith('no_') and reason not in _REAL_NO):
        have = set(filter(None, (sig.get('shadow_veto') or '').split(',')))
        sig['shadow_veto'] = ','.join(sorted(have | {reason}))
        return None
    return reason


DEFERRED = object()     # eng-147: SignalBook._enter's 'entry held for the crowd ranking' marker


def crowd_rank(s, levels: Dict, candles_of) -> Tuple[int, float, float]:
    """eng-147 (the owner): the order in which one pass's entries take the crowd_max slots - fewer shadow vetoes, then
    the higher RVOL of the last 15 minutes (vs the 20 quarters before), then min(R:R to TP1, 2.5) (2.0 without a TP1)."""
    n_veto = len([v for v in (s.sig.get('shadow_veto') or '').split(',') if v])
    rvol = 0.0
    try:
        m = list(candles_of(s.symbol))[-315:]
        if len(m) == 315:
            base = sum(c[5] for c in m[:300]) / 20
            rvol = sum(c[5] for c in m[300:]) / base if base > 0 else 0.0
    except (TypeError, IndexError, ValueError):
        pass
    rr = levels.get('rr_tp1')
    score = min(rr, 2.5) if rr is not None and not (s.plan or {}).get('no_tp') else 2.0
    return n_veto, -rvol, -score


# eng-138 (audit R06): (symbol, t0_ms, t1_ms) -> the sum of the funding rates SETTLED in (t0, t1] (as paid, not
# normalized), None when unknown; set by the replay from the archive ledger. Live keeps the entry-rate model (the real
# ledger is the executor's)
FUNDING_PAID: Optional[Callable[[str, float, float], Optional[float]]] = None


def version_no(v: Optional[str]) -> int:
    """'eng-57' -> 57 (0 for anything else): logic versions compare by number, never as strings."""
    try:
        return int(str(v).split('-')[1])
    except (IndexError, ValueError):
        return 0


def _exit_flags(s: 'TrackedSignal') -> Dict:
    """The exit-relevant plan fields of a trade saved without its plan (before eng-55), rebuilt from its signal and
    setup as the strategies set them at the entry."""
    g, sig = s.group_key, s.sig or {}
    plan: Dict = {}
    if g.startswith('BREAKOUT') and sig.get('trail_days'):
        plan.update(trail_days=sig['trail_days'], no_tp=True, turtle_n=sig.get('turtle_n'), tf='1d')
    elif g.startswith('RSI2'):
        plan.update(connors_exit=True, no_tp=True, tf='1d')
    elif g.startswith('ORB') and version_no(s.logic_version) >= 50:
        plan.update(no_tp=True, tf='15m')
    elif g.startswith('BB ') and 55 <= version_no(s.logic_version) < 85:     # eng-85: a real TP1 since
        plan.update(band_exit=True, no_tp=True, tf='15m')
    elif g == 'PUMP START':
        plan.update(add_half=True, tf='15m')
    elif sig.get('ch_tf'):
        plan.update(tf=sig['ch_tf'])          # cup with handle: 1h / 4h (the time exit / TTL scale with it)
    return plan


@dataclass
class TrackedSignal:
    symbol: str
    group_key: str
    direction: int
    mode: str                                   # the strategy's name (kept as 'mode' for saved states)
    created: float
    price_at_signal: float
    sig: Dict
    plan: Optional[Dict] = None
    status: str = 'BIAS'
    last_seen: float = 0.0
    last_price: float = 0.0
    zone_since_ms: Optional[int] = None
    levels: Optional['CardLevels'] = None
    entered_at: Optional[float] = None
    best_target: int = 0
    finished_at: Optional[float] = None
    final_r: Optional[float] = None
    vetoed: Optional[str] = None
    of_confirm: Optional[str] = None
    confirms: dict = field(default_factory=dict)
    vetoed_triggers: int = 0
    variants_done: list = field(default_factory=list)    # eng-149: shadow variants journaled for this card
    limit_variant: bool = False                          # eng-149: a variant that rests a limit (replay fills at it)
    # Veto reasons of the triggers skipped so far, and why / where the card finished
    veto_log: list = field(default_factory=list)
    # Why a far stop did not pay (low_rr): stop / TP1 / the entry's distance from the zone's edge, the last few
    veto_notes: list = field(default_factory=list)
    finish_reason: Optional[str] = None
    finish_price: Optional[float] = None
    # First plan taken (anchor checked, opposite card closed); the fixed target reference and invalidation; whether
    # the entry at the confirmation was tried
    activated: bool = False
    reached: Optional[float] = None
    invalid_price: Optional[float] = None
    confirm_checked: bool = False
    # When the card first had its 15m history and waited for the 1h history / level map
    pending_since: Optional[float] = None
    # Turtle pyramiding: [entry price, time] of every unit (the first = the entry), at most turtle_max_units
    units: list = field(default_factory=list)
    # the signal logic the card was opened by: a card of an older one is closed at the next start (eng-36)
    logic_version: str = ''
    # eng-58: the last final 1m candle the trade was managed on (stops / targets by candle extremes, as the replay);
    # the price the trade really left at (a stop gapped through fills at the candle's open)
    managed_ms: int = 0
    exit_fill: Optional[float] = None
    # eng-58: an ICT setup armed after the sweep (MSS + FVG found): the plan fields overlaid on every re-plan (the
    # resting limit at the gap's CE)
    armed: Optional[dict] = None
    # eng-59: the last trigger time of the replaced rule journaled beside the card ('weak_mss' / 'variant_shift')
    shadow_ms: int = 0
    last_veto: list = field(default_factory=list)   # [reason, entry, sl] of the last journaled veto
    # the order-flow entry in the zone (SignalBook._flow_entry): checked once a minute, journaled once per card
    flow_checked_ms: int = 0
    tp_ms: int = 0                              # audit B03: the end of the last final minute checked for TP1 before an entry
    # audit 2026-10-18 D: when each part of the position left (ms; 'tp1' / 'tp2' / 'p1r'), so funding is charged on what
    # was still held at each settlement, not on the whole position until the last exit
    part_ms: dict = field(default_factory=dict)
    flow_done: bool = False
    # eng-137 (audit A01): the end of the last final 1m candle checked against the invalidation (0 = from the minute
    # after the card's creation); audit A02: how the rest of the entry minute was judged ('' = not yet, 'trades' =
    # the trades after the entry, 'clean' = its 1m range touched no level, 'ambiguous' = touched with no trades to
    # tell whether before or after the entry) and the pessimistic R when that minute's range reached the stop
    inv_ms: int = 0
    entry_min: str = ''
    r_low: Optional[float] = None

    @property
    def finished(self) -> bool:
        return self.finished_at is not None

    @property
    def filled_at(self) -> Optional[float]:
        return self.entered_at

    @property
    def r_now(self) -> Optional[float]:
        """Current result in R (risk units) for an entered signal."""
        if not self.levels or not self.entered_at:
            return None
        # the risk of ONE unit at the entry (a pyramided stop moves; R stays in the first unit's risk)
        risk = self.levels.get('risk0') or abs(self.levels['entry'] - self.levels['sl'])
        if not risk:
            return None
        if self.units:
            # Turtles: every unit is one first-unit risk in size, the result is their sum
            return sum(self.direction * (self.last_price - u[0]) for u in self.units) / risk
        return self.direction * (self.last_price - self.levels['entry']) / risk


@dataclass
class AnomalyEntry:
    symbol: str
    group_key: str
    first_seen: float
    last_seen: float
    sig: Dict
    hits: int = 1
    peak: Dict[str, float] = field(default_factory=dict)


class SignalBook:
    def __init__(self):
        self.signals: Dict[Tuple[str, str], TrackedSignal] = {}
        self.anomalies: Dict[Tuple[str, str], AnomalyEntry] = {}
        self.watchlist: List[Tuple[str, Dict]] = []
        # Directional setups filtered out this scan: (symbol, group_key, reason, sig)
        self.vetoed: List[Tuple[str, str, str, Dict]] = []
        # Outcomes of finished signals this session, and the R of each finished entered signal
        self.session_results: Counter = Counter()
        self.session_r: List[float] = []
        # Status changes of this scan for notifications: (TrackedSignal, event)
        self.events: List[Tuple[TrackedSignal, str]] = []
        # Cards finished this scan (the journal stores each with its reason, then tracks what price did after)
        self.finished_now: List[TrackedSignal] = []
        # symbol -> the coin's level map / 1h candles / structure context; set by the scanner
        self.levels_of: Optional[Callable[[str], Optional[list]]] = None
        self.htf_of: Optional[Callable[[str], Optional[list]]] = None
        self.daily_of: Optional[Callable[[str], Optional[list]]] = None
        self.h4_of: Optional[Callable[[str], Optional[list]]] = None
        # symbol -> {'1h': ATR14, '4h': ..., '1d': ...} of its closed candles (scanner)
        self.tf_atr_of: Optional[Callable[[str], Dict[str, float]]] = None
        self.market_state_of: Optional[Callable[[], Dict]] = None    # eng-145: the live market moves (scanner)
        self.btc_bias_of: Optional[Callable[[], Optional[int]]] = None      # eng-59: BTC's ICT bias (scanner)     # closed daily candles (Turtle exits)
        # the opposite Bollinger band BB(20, 2) of the closed 15m candles (Bollinger W / M exit, eng-55)
        self.band_of: Optional[Callable[[str, int], Optional[float]]] = None
        # eng-137 (audit A02): the trades after an entry (fetcher.track_from / tracked_of / untrack; None in the replay)
        self.track_from: Optional[Callable[[str, int], None]] = None
        self.tracked_of: Optional[Callable[[str, int, int], Optional[Dict]]] = None
        self.untrack: Optional[Callable[[str, int], None]] = None
        self.context_of: Optional[Callable[[str], Optional[object]]] = None
        # symbol -> hashable key of everything a plan depends on (None: always recompute); plans cached per card
        self.plan_key_of: Optional[Callable[[str], Optional[tuple]]] = None
        # symbol -> True once its 1h history and level map are loaded (a plan without them misses 1h / 4h legs)
        self.map_ready_of: Optional[Callable[[str], bool]] = None
        self._plan_cache: Dict[Tuple[str, str], Tuple[tuple, Optional[Dict]]] = {}
        # eng-84: a card dropped as 'not a card' (no anchor, against_tide ...) is not re-created from the same persistent
        # signal on every scan (live ARB BEAR D: SETUP / 'not a card' every 10-30 s for hours, a journal row each time)
        self._dropped: Dict[Tuple[str, str], float] = {}
        self._skip_reason: Dict[Tuple[str, str], str] = {}
        self._born = time.time()                 # _plan_data_ready: the start-up grace
        # (symbol, setup) -> (plan key, gate result): a phase setup repeats on every scan of its candle
        self._gate_cache: Dict[Tuple[str, str], Tuple[tuple, Optional[str]]] = {}
        self._candles_of: Callable[[str], Sequence[Sequence[float]]] = lambda symbol: []
        # (symbol, direction) -> last time the coin produced a directional setup (market-move clusters)
        self._recent_setups: Dict[Tuple[str, int], float] = {}
        # (symbol, direction) -> (anchor key, finished_at) of the last finished card
        self.finished_legs: Dict[Tuple[str, int], Tuple[tuple, float]] = {}
        # eng-58: (symbol, UTC day) -> the direction of the day's first entry (one direction per coin a day)
        self.day_dir: Dict[Tuple[str, int], int] = {}

    # ------------------------------------------------------------------ input

    def update(
        self,
        signals: List[Tuple[str, Dict]],
        frames,
        price_of: Callable[[str], Optional[float]],
        candles_of: Callable[[str], Sequence[Sequence[float]]],
        now: float,
        confirm_of: Optional[ConfirmCheck] = None,
    ) -> Tuple[List[TrackedSignal], List[TrackedSignal]]:
        """
        Feed one scan's signals. `frames.get(symbol)` returns the symbol's 15m futures frame with indicators and
        `candles_of(symbol)` its final 1m futures candles; `confirm_of(...)` reads an entry's confirmations
        (strategies.confirm). Returns (setups created, entries
        triggered this scan); vetoed entries are in the list too, with `.vetoed` set and no status change.
        """
        created: List[TrackedSignal] = []
        self._candles_of = candles_of
        self.watchlist = []
        self.vetoed = []
        self._deferred, self._deferring, self._extra = [], False, []
        self.events = []
        self.finished_now = []
        # cards of an older signal logic (restored from the state): an entered one closes at market, a waiting one
        # expires - their stops / targets / filters are not the current rules (live 2026-10-01: an eng-7 auction card
        # with 0 confirmations and ATR-step targets still traded beside eng-35 cards)
        # An ENTERED one keeps its trade to the end under its own levels (eng-43: closing every trade at each version
        # bump left the demo with almost no finished trades); only a WAITING card of an older logic expires
        keep_from = CONFIG.journal.keep_waiting_from
        for old in [o for o in self.signals.values() if not o.finished and not o.entered_at
                    and o.logic_version != CONFIG.journal.logic_version]:
            # eng-97: versions compare by NUMBER ('eng-100' < 'eng-96' and 'eng-7' > 'eng-55' as strings)
            if keep_from and version_no(old.logic_version) >= version_no(keep_from):
                old.logic_version = CONFIG.journal.logic_version    # eng-87: same card rules, kept
                continue
            reason = f"expired at start: a waiting card of the older signal logic {old.logic_version or '<eng-35'}"
            self._finish(old, 'EXPIRED', now, reason)

        candidates = []
        directional: List[Tuple[int, Dict]] = []
        for symbol, sig in signals:
            kind, group_key, direction = classify(sig)
            key = (symbol, group_key)
            strategy = strategy_of(group_key)
            if strategy is not None:
                self._recent_setups[(symbol, direction)] = now
                directional.append((direction, sig))
                sig.pop('shadow_veto', None)
                sig['card_veto'] = None
                reason = shadow_veto(sig, veto_reason(group_key, sig)) or shadow_veto(sig, strategy.context_veto(sig, direction))
                if reason is None and direction > 0 and sig.get('event_risk'):
                    # eng-53: no longs on a coin Binance tagged for monitoring / is delisting (documented -4..-34%)
                    reason = 'event_risk'
                if reason is None and not strategy.has_data(sig):
                    reason = 'no_data'
                if reason is None and (not strategy.enabled or group_key in CONFIG.strategies.disabled_setups):
                    reason = 'disabled'
                pool_of = getattr(self, 'pool_of', None)
                if reason is None and pool_of is not None and not pool_of(strategy.name, symbol):
                    reason = shadow_veto(sig, 'not_in_pool')
                if reason:
                    sig['card_veto'] = reason
                    self.vetoed.append((symbol, group_key, reason, sig))
                    continue
                # One open card per coin and direction: a setup relabelled on the live candle is the same idea
                same_side = [s for s in self.signals.values()
                             if s.symbol == symbol and s.direction == direction and not s.finished]
                if same_side:
                    for s in same_side:
                        s.last_seen = now
                        if s.group_key == group_key:
                            s.sig = sig
                    continue
                tracked = self.signals.get(key)
                if tracked and now - tracked.finished_at < CONFIG.journal.cooldown_sec:
                    continue
                if now - self._dropped.get(key, -1e18) < DROP_COOLDOWN_SEC:
                    continue
                reason = self._card_gate(symbol, group_key, strategy, direction, frames, sig)
                if reason:
                    sig['card_veto'] = reason
                    self.vetoed.append((symbol, group_key, reason, sig))
                    continue
                price = price_of(symbol)
                if not price:
                    continue
                candidates.append((symbol, group_key, strategy, direction, sig, price))
            elif kind == 'structured':
                self.watchlist.append((symbol, sig))
            else:
                self._remember_anomaly(symbol, group_key, sig, now)

        # Market crowd: how many coins produced a same-direction setup within the window (one market move shows up on
        # many coins at once). A feature for the journal / stats / ML, not a filter: every confirmed setup is a card.
        window = CONFIG.market.cluster_window_sec
        self._recent_setups = {k: t for k, t in self._recent_setups.items() if now - t <= window}
        crowd = {d: len({sym for (sym, dd) in self._recent_setups if dd == d}) for d in (1, -1)}
        for direction, sig in directional:
            sig['market_crowd'] = crowd[direction]
        taken = set()
        for symbol, group_key, strategy, direction, sig, price in candidates:
            # audit A13: one open card per coin and direction holds within one scan too (two setups of the same
            # scan both passed the same_side check above, which only sees cards already open): the first one wins
            if (symbol, direction) in taken:
                sig['card_veto'] = 'same_scan'
                continue
            taken.add((symbol, direction))
            tracked = TrackedSignal(
                symbol=symbol, group_key=group_key, direction=direction, mode=strategy.name,
                created=now, price_at_signal=price, sig=sig, last_seen=now, last_price=price,
                logic_version=CONFIG.journal.logic_version,
            )
            self.signals[(symbol, group_key)] = tracked
            created.append(tracked)

        entries: List[TrackedSignal] = []
        # eng-147 (the owner): the entries that passed every check in this pass are held and entered best first, so
        # crowd_max keeps the best candidates of one candle, not the first ones iterated
        self._deferred, self._deferring, self._extra = [], True, []
        try:
            for tracked in self.signals.values():
                if tracked.finished:
                    continue
                price = price_of(tracked.symbol)
                if not price:
                    continue
                result = self._advance(tracked, price, now, frames, candles_of, confirm_of)
                if result is not None and result is not DEFERRED:
                    entries.append(result)
        finally:
            self._deferring = False
        for pos, (s, lv, t_ms, cf) in enumerate(sorted(self._deferred, key=lambda c: crowd_rank(c[0], c[1], candles_of))):
            s.sig['crowd_pos'] = pos     # eng-148: journaled (Top vs Rest), no slot limit on the demo
            result = self._enter(s, lv, t_ms, None, cf)
            if result is not None:
                entries.append(result)
        self._deferred = []
        entries.extend(self._extra)          # eng-149: shadow variants (vetoed entries, journal only)
        self._extra = []

        # Forget finished signals / stale anomalies once they have been on screen long enough
        keep_for = max(CONFIG.levels.finished_display_sec, CONFIG.journal.cooldown_sec)
        created = [t for t in created if t.status != DROPPED]
        self.signals = {k: s for k, s in self.signals.items()
                        if s.status != DROPPED and (not s.finished or now - s.finished_at < keep_for)}
        self.finished_legs = {k: v for k, v in self.finished_legs.items() if now - v[1] < FINISHED_LEG_MEMORY_SEC}
        self._plan_cache = {k: v for k, v in self._plan_cache.items() if k in self.signals and not self.signals[k].finished}
        if len(self._gate_cache) > 2000:
            self._gate_cache.clear()
        self.anomalies = {k: a for k, a in self.anomalies.items() if now - a.last_seen <= CONFIG.tier0.display_hold_sec}
        return created, entries

    def _remember_anomaly(self, symbol: str, group_key: str, sig: Dict, now: float):
        # One row per coin (one event is often read as several labels at once): the row keeps the most significant
        # label seen while it is held, the numbers follow the latest reading
        akey = (symbol, 'ANOMALY')
        entry = self.anomalies.get(akey)
        if entry is None or now - entry.last_seen > CONFIG.tier0.display_hold_sec:
            entry = AnomalyEntry(symbol, group_key, first_seen=now, last_seen=now, sig=sig)
            self.anomalies[akey] = entry
        else:
            entry.last_seen, entry.sig, entry.hits = now, sig, entry.hits + 1
            if ANOMALY_PRIORITY.get(group_key, 0) >= ANOMALY_PRIORITY.get(entry.group_key, 0):
                entry.group_key = group_key
        for metric in ('rvol_1m', 'price_change_5m', 'oi_change_5m', 'whale_net_5m'):
            value = sig.get(metric, 0.0) or 0.0
            if abs(value) > abs(entry.peak.get(metric, 0.0)):
                entry.peak[metric] = value

    # ------------------------------------------------------------------ plans

    @staticmethod
    def strategy(s: TrackedSignal) -> Optional[Strategy]:
        return strategy_of(s.group_key)

    def _input(self, symbol: str, group_key: str, direction: int, sig: Dict, frames,
               reached: Optional[float]) -> PlanInput:
        return PlanInput(symbol=symbol, direction=direction, setup=group_key, sig=sig, df=frames.get(symbol),
                         minutes=list(self._candles_of(symbol)),
                         raw_levels=(self.levels_of(symbol) if self.levels_of else None) or [],
                         h1=(self.htf_of(symbol) if self.htf_of else None) or [],
                         context=self.context_of(symbol) if self.context_of else None, reached=reached,
                         tf_atr=(self.tf_atr_of(symbol) if self.tf_atr_of else None) or {},
                         h4=(self.h4_of(symbol) if self.h4_of else None) or [],
                         d1=(self.daily_of(symbol) if self.daily_of else None) or [])

    def _card_gate(self, symbol: str, group_key: str, strategy: Strategy, direction: int, frames,
                   sig: Dict) -> Optional[str]:
        """
        Why a setup does not become a card: no anchor to build a plan on ('no_leg'), or a card on this anchor already
        finished ('same_leg': a setup keeps confirming on every candle, the idea was already played). A leg strategy
        without the coin's 1h history is decided by the first plan (1h / 4h legs need it).
        """
        frame = frames.get(symbol)
        if frame is None or frame.height < 20:
            return None
        if strategy.anchor_type == 'leg' and not getattr(strategy, 'own_leg', False) and not (self.htf_of and self.htf_of(symbol)):
            return None
        plan_key = self.plan_key_of(symbol) if self.plan_key_of else None
        cached = self._gate_cache.get((symbol, group_key))
        if plan_key is not None and cached is not None and cached[0] == (plan_key, sig.get('event_ts')):
            key = cached[1]
        else:
            key = strategy.gate_key(self._input(symbol, group_key, direction, sig, frames, None))
            if plan_key is not None:
                self._gate_cache[(symbol, group_key)] = ((plan_key, sig.get('event_ts')), key)
        if key is None:
            return 'no_leg'
        done = self.finished_legs.get((symbol, direction))
        if done and done[0] == key:
            return 'same_leg'
        return None

    PLAN_GRACE_SEC = 600      # after the book is created: the history of every coin loads in the background

    def _plan_data_ready(self, symbol: str, frames, now: float) -> bool:
        """Can a missing plan be trusted: the book has run PLAN_GRACE_SEC and the coin has its 15m frame, its 1h / 4h /
        daily ATRs and final 1m candles (a plan built without them is None for want of data, not of a setup)."""
        if now - self._born < self.PLAN_GRACE_SEC:
            return False
        df = frames.get(symbol) if frames is not None else None
        if df is None or not getattr(df, 'height', 0):
            return False
        if self.tf_atr_of is not None and not self.tf_atr_of(symbol):
            return False
        return bool(self._candles_of(symbol)) if self._candles_of else True

    def _plan(self, s: TrackedSignal, frames) -> Optional[Dict]:
        strategy = self.strategy(s)
        if strategy is None:
            return None
        # A plan only changes with its inputs (15m frame, live candle extremes, level map, walls / HL positions, and
        # the final 1m candles for strategies that follow them): recomputing ~40 plans every scan kept the loop busy
        # The cache is checked BEFORE the plan's inputs are built (copying 1m candles and appending the live candle to
        # the 15m frame for ~40 cards every scan stalled the loop 3s)
        key = self.plan_key_of(s.symbol) if self.plan_key_of else None
        if key is not None:
            if not strategy.follows_live_candle:
                key = _without_live(key)
            candles = self._candles_of(s.symbol) if strategy.uses_minutes else None
            last_minute = candles[-1][0] if candles else None
            key = (key, s.reached, last_minute)
            cached = self._plan_cache.get((s.symbol, s.group_key))
            if cached is not None and cached[0] == key:
                return cached[1]
        plan = strategy.plan(self._input(s.symbol, s.group_key, s.direction, s.sig, frames, s.reached))
        if plan is not None and plan.get('skip'):
            # the strategy says why there is no plan ('no_level'): kept per card, the plan cache holds None
            self._skip_reason[(s.symbol, s.group_key)] = plan['skip']
            plan = None
        if plan is not None and strategy.name not in MANAGE_EXEMPT and not plan.get('trail_days'):
            # eng-84, trade management for every intraday method (the owner's review: W +43%, MAGIC +16%, ZEC at a 4h
            # order block all went back to the stop; the ICT / SMC sources: half at TP1, the rest at break-even): with
            # targets - half at TP1, then the stop to break-even + costs and trailed; without targets (band / session
            # exits) - the stop to break-even + costs once price went +1R
            # (a plan that sets the flag itself, False included, keeps its own choice)
            # eng-85: break-even + costs after +1R for EVERY managed plan, targets or not (the journal of 11-13.10: 19 of
            # 26 AUCTION stops and 18 of 44 Bollinger stops had traded +1R first)
            # eng-111 (the owner: a source or out): no source for break-even after +1R (the evidence leans against it:
            # Quantified Strategies / LuxAlgo MAE-MFE) nor for the EMA20 trail after TP1 (Qullamaggie's is a DAILY
            # 10/20 MA close, secondhand) - both off; the rest of a trade goes to TP2 / TP3. Bollinger keeps its own
            # exit (the live opposite band: band_exit)
            if CONFIG.strategies.be_after_1r:
                plan.setdefault('be_after_r', 1.0)
            if not plan.get('no_tp') and CONFIG.strategies.ema_trail_after_tp1:
                plan.setdefault('trail_after_tp1', True)
        if plan is not None and not CONFIG.strategies.ema_trail_after_tp1 and plan.get('trail_after_tp1') \
                and not plan.get('band_exit'):
            plan['trail_after_tp1'] = False
        if key is not None:
            self._plan_cache[(s.symbol, s.group_key)] = (key, plan)
        return plan

    def _tf(self, s: TrackedSignal) -> str:
        if s.plan:
            return s.plan.get('tf', '15m')
        strategy = self.strategy(s)
        return getattr(strategy, 'default_tf', None) or '15m'

    # ------------------------------------------------------------------ lifecycle

    def _drop(self, s: TrackedSignal, now: float, reason: str):
        """A card that turned out not to be one (no anchor / no room left): removed, shown in Forming as vetoed."""
        s.status, s.finished_at = DROPPED, now
        self._dropped[(s.symbol, s.group_key)] = now
        if len(self._dropped) > 5000:
            self._dropped = {k: t for k, t in self._dropped.items() if now - t < DROP_COOLDOWN_SEC}
        s.sig['card_veto'] = reason
        logger.info(f"Card {s.symbol} {s.group_key}: not a card ({reason})")
        self.vetoed.append((s.symbol, s.group_key, reason, s.sig))

    def _activate(self, s: TrackedSignal, plan: Dict, price: float, now: float):
        """The card's first plan: fix its references and close the open card of the opposite direction."""
        s.activated = True
        s.reached = plan.get('reached')
        if plan.get('fix_invalid'):
            s.invalid_price = plan.get('invalid')
        rank = TF_RANK.get(self._tf(s), 2)
        mine = self.strategy(s)
        for o in self.signals.values():
            if o is s or o.finished or o.symbol != s.symbol or o.direction == s.direction:
                continue
            # crypto_maniac's systems run independently (as in his bots): their signals never close another
            # strategy's card, nor are theirs closed by others - only the same system's opposite signal does
            other = self.strategy(o)
            if mine is not None and other is not None and mine.name != other.name and                     (mine.name in MANIAC_NAMES or other.name in MANIAC_NAMES):
                continue
            # Only a setup of the same or a higher timeframe overrules a card: a 5m event against a 1h idea is noise
            # inside it, the two coexist
            if rank < TF_RANK.get(self._tf(o), 2):
                continue
            if o.entered_at and mine is not None and other is not None and mine.name != other.name and \
                    (getattr(other, 'time_exit', 'bars') != 'bars' or o.best_target):
                # eng-48: a trade with its method's own exit (Turtles, Connors, cup, Seiden, the sessions) is not
                # closed by another method's 15m event (ZEC's RSI(2) by a SWEEP HIGH), and a trade that already took
                # TP1 runs on its levels (1000PEPE's W-bottom at +2.5R closed for an M-top that lost)
                continue
            o.last_price = price
            if o.entered_at:
                self._finish(o, 'CLOSED', now, f"opposite setup {s.group_key} confirmed: closed at market")
            else:
                self._finish(o, 'INVALID', now, f"opposite setup {s.group_key} confirmed")

    def _finish(self, s: TrackedSignal, status: str, now: float, reason: str = ''):
        key = (s.plan or {}).get('key')
        if key is not None:
            self.finished_legs[(s.symbol, s.direction)] = (key, now)
        s.status, s.finished_at = status, now
        if s.entered_at and self.untrack:
            self.untrack(s.symbol, int(s.entered_at * 1000))
        s.finish_reason, s.finish_price = reason or status, (s.exit_fill if s.exit_fill is not None else s.last_price)
        if s.entered_at and (s.plan or {}).get('data_gaps'):
            # audit V04: the result crossed minutes nobody saw - a stop / target inside them can be neither confirmed
            # nor excluded
            s.finish_reason += f" [data gap: {len(s.plan['data_gaps'])} hole(s) in the 1m candles, result uncertain]"
        self.finished_now.append(s)
        label = f"SL after TP{s.best_target}" if status == 'SL' and s.best_target else status
        if status == 'SL' and s.entered_at and s.levels and s.direction * (s.levels['sl'] - s.levels['entry']) > 0:
            label = 'TRAIL'          # eng-132: the trailed stop sits beyond the entry - a stop out in profit, not a loss
        self.session_results[label] += 1
        if s.entered_at and s.r_now is not None:
            s.final_r = self._exit_r(s, status)
            self.session_r.append(s.final_r)
        # audit N14: every terminal outcome of an ENTERED trade notifies once (CLOSED - band / session / time / opposite
        # setup exits - was never sent)
        if status in ('SL', 'TP3') or (status == 'CLOSED' and s.entered_at):
            self.events.append((s, status))

    def _trail(self, s: TrackedSignal, candles_of, hi: Optional[float] = None, lo: Optional[float] = None) -> None:
        """
        Stop management of an open trade, only ever toward the trade (a RESTOP event moves the demo's stop):
        - plan 'sar': Wilder's Parabolic SAR of the plan's bars (BB1 4h);
        - plan 'trail_pct': a % trail behind the best price;
        - plan 'be_after_r': break-even + costs after +R (globally off since eng-111; ORB sets it, eng-154);
        - the partial at +1R: off (partial_share 0 since eng-123);
        - plan 'trail_after_tp1' (half at TP1, then the EMA20 trail): off - _plan resets it while
          strategies.ema_trail_after_tp1 is False (eng-111); only band_exit plans keep it.
        """
        plan, lv, d = s.plan or {}, s.levels, s.direction
        sar = plan.get('sar')
        if sar and candles_of and lv.get('sl'):
            # eng-127, Bollinger's Method I: Wilder's Parabolic SAR of the plan's bars, stepped once per CLOSED bar
            # since the signal; the stop follows it (the SAR's own stop-and-reverse touch is the stop order)
            from strategies.maniac import parabolic_sar_step
            size = int(sar['tf_min']) * MINUTE_MS
            # audit A12: as of the minute being managed (s.managed_ms = its end): a bar that closes later must not
            # move the stop that minute is judged against
            asof = s.managed_ms or None
            minutes = [m for m in candles_of(s.symbol) if asof is None or m[0] + MINUTE_MS <= asof]
            if sar.pop('start_at_sl', False):
                # ORB: the SAR starts at the trade's final stop when that is farther than the plan's (a pool / the
                # min-stop floor) - the first bar must not take the buffer away
                sar['sar'] = min(sar['sar'], lv['sl']) if d > 0 else max(sar['sar'], lv['sl'])
            if minutes:
                done = (int(minutes[-1][0]) + MINUTE_MS) // size * size
                bars = [b for b in _resample(s.symbol, minutes, int(sar['tf_min']), done) if sar['last_ts'] < b[0] and b[0] + size <= done]
                for b in bars:
                    nxt, ep, af, stopped = parabolic_sar_step(sar['sar'], sar['ep'], sar['af'], d, b[2], b[3],
                                                              prev_hi=sar.get('prev_hi'), prev_lo=sar.get('prev_lo'))
                    sar.update(sar=nxt, ep=ep, af=af, last_ts=int(b[0]), prev_hi=float(b[2]), prev_lo=float(b[3]))
                    if stopped:
                        break
                if d * (sar['sar'] - lv['sl']) > 0:
                    lv['sl'] = sar['sar']
                    lv['sl_src'] = f"Parabolic SAR (AF {sar['af']:.2f})"
                    self.events.append((s, 'RESTOP'))
            return
        pct = plan.get('trail_pct')
        if pct and hi is not None and lo is not None and lv.get('sl'):
            # eng-88: a percentage trailing stop behind the best price since the entry (OI build), only toward the
            # trade; moved in steps of >= 0.25% of the price so the demo's stop is not re-placed every minute
            best = hi if d > 0 else lo
            prev = plan.get('trail_best')
            plan['trail_best'] = best if prev is None else (max(prev, best) if d > 0 else min(prev, best))
            new = plan['trail_best'] * (1 - d * pct)
            if d * (new - lv['sl']) > 0.0025 * plan['trail_best']:
                lv['sl'] = new
                lv['sl_src'] = f'trailing {pct:.0%} behind the best price'
                self.events.append((s, 'RESTOP'))
            return
        be_r = plan.get('be_after_r')
        if be_r is None and CONFIG.strategies.be_after_1r:
            be_r = 1.0          # eng-155: cards opened before the flag (restored from the state) get it too
        if hi is not None and lo is not None and lv.get('entry') and lv.get('sl'):
            risk = lv.get('risk0') or abs(lv['entry'] - lv['sl'])
            fav = (hi - lv['entry']) if d > 0 else (lv['entry'] - lo)
            # eng-105 (the owner's rule, independent of break-even since eng-111): the partial at +1R (the demo's tp0)
            if risk and fav >= CONFIG.executor.partial_r * risk and CONFIG.executor.partial_share \
                    and not plan.get('p1r_done') and not s.units and (plan.get('no_tp') or not lv.get('tp1') or
                                                                      d * (lv['tp1'] - lv['entry']) > risk * CONFIG.executor.partial_r):
                plan['p1r_done'] = True
                s.part_ms.setdefault('p1r', int(s.managed_ms or 0))
                self.events.append((s, 'PARTIAL'))     # eng-155: the demo takes the half if its tp0 has not
            if be_r and risk and fav >= be_r * risk:
                # eng-84: the stop to break-even + costs once price traded +be_r R its way (off by default, eng-111)
                be = lv['entry'] * (1 + d * BE_COST)
                if d * (be - lv['sl']) > 0:
                    lv['sl'] = be
                    lv['sl_src'] = f'break-even + costs after +{be_r:g}R'
                    self.events.append((s, 'RESTOP'))
            if not plan.get('trail_after_tp1'):
                return
        if not plan.get('trail_after_tp1') or s.best_target < 1 or not candles_of:
            return
        # eng-84: break-even INCLUDING the round trip's costs (fees + slippage), not the bare entry
        be = lv['entry'] * (1 + d * BE_COST)
        new = max(lv['sl'], be) if d > 0 else min(lv['sl'], be)
        tf = int((s.plan or {}).get('trigger_minutes') or 5)
        # as of the minute being managed (review of 6b771ba: the whole buffer let later bars move an earlier stop)
        asof = s.managed_ms or None
        minutes = [m for m in candles_of(s.symbol) if asof is None or m[0] + MINUTE_MS <= asof]
        bars = _resample(s.symbol, minutes, tf, minutes[-1][0] + MINUTE_MS) if minutes else []
        if len(bars) >= 20:
            alpha, ema = 2 / 21, bars[0][4]
            for b in bars[1:]:
                ema += alpha * (b[4] - ema)
            if d * (bars[-1][4] - ema) > 0:
                new = max(new, ema) if d > 0 else min(new, ema)
        step = 0.1 * (lv.get('risk0') or abs(lv['entry'] - lv['sl']))
        if d * (new - lv['sl']) > step or (d * (new - lv['sl']) > 0 and d * (lv['sl'] - lv['entry']) < 0):
            lv['sl'] = new
            lv['sl_src'] = 'trailing: entry / EMA20 after TP1'
            self.events.append((s, 'RESTOP'))

    def _overlay_exit(self, s: TrackedSignal, c, candles_of) -> Optional[str]:
        """
        Early exits adopted by research_overlays.py (models/exit_overlays.json), checked at each final 1m candle's
        close: noprog_H - H hours in and the trade never traded +0.3R its way; struct - a 15m close at or below -0.5R;
        btc_K - altcoins: BTC moved K% against the trade over the last 15 minutes. Exit at the candle's close.
        """
        overlays = (s.plan or {}).get('exit_overlays')
        lv, d = s.levels, s.direction
        risk = lv.get('risk0') or 0.0
        if not overlays or not risk or not s.entered_at:
            return None
        hi, lo, close, ts = float(c[2]), float(c[3]), float(c[4]), int(c[0])
        fav = (hi - lv['entry']) * d / risk if d > 0 else (lv['entry'] - lo) / risk
        prev = s.plan.get('ov_best')
        s.plan['ov_best'] = fav if prev is None else max(prev, fav)
        held_min = (ts + MINUTE_MS) / 1000 / 60 - s.entered_at / 60
        for ov in overlays:
            kind, _, arg = ov.partition('_')
            if kind == 'noprog' and held_min >= float(arg) * 60 and s.plan['ov_best'] < 0.3:
                return f"early exit: no +0.3R within {arg}h (research_overlays)"
            if kind == 'struct' and (ts + MINUTE_MS) % (15 * MINUTE_MS) == 0 and (close - lv['entry']) * d / risk <= -0.5:
                return "early exit: a 15m close at -0.5R (research_overlays)"
            if kind == 'btc' and not s.symbol.startswith('BTC/') and candles_of:
                btc = [b for b in list(candles_of('BTC/USDT:USDT')) if b[0] <= ts][-16:]
                if len(btc) >= 16 and btc[0][4]:
                    move = btc[-1][4] / btc[0][4] - 1
                    if d * move <= -float(arg) / 100:
                        return f"early exit: BTC {move:+.2%} against the trade in 15 min (research_overlays)"
        return None

    def _profile_manage(self, s: TrackedSignal, hi: float, lo: float) -> None:
        """An optimized profile's stop management on each final 1m candle (research_optimize.simulate): after +1R the
        stop to the entry (`be`) and / or an ATR chandelier `trail` x the 1h ATR behind the best price, only ever
        toward the trade; a RESTOP event moves the demo's stop."""
        pm = (s.plan or {}).get('pm')
        lv, d = s.levels, s.direction
        risk = lv.get('risk0') or 0.0
        if not pm or not risk:
            return
        best = hi if d > 0 else lo
        prev = s.plan.get('pm_best')
        s.plan['pm_best'] = best if prev is None else (max(prev, best) if d > 0 else min(prev, best))
        if d * (s.plan['pm_best'] - lv['entry']) < risk:
            return
        new = lv['sl']
        # eng-85: break-even + costs after +1R always (a profile without 'be' / 'trail' had no management at all)
        be = lv['entry'] * (1 + d * BE_COST)
        new = max(new, be) if d > 0 else min(new, be)
        atr = s.plan.get('pm_atr')
        if pm.get('trail') and atr:
            chand = s.plan['pm_best'] - d * float(pm['trail']) * atr
            new = max(new, chand) if d > 0 else min(new, chand)
        if d * (new - lv['sl']) > 0.05 * risk:
            lv['sl'] = new
            lv['sl_src'] = 'profile: ' + ' + '.join(x for x, on in (('breakeven', True),
                                                                     ('ATR trail', pm.get('trail'))) if on)
            self.events.append((s, 'RESTOP'))

    @staticmethod
    def _funding_r(s: TrackedSignal, risk: float, price: float, t0_ms: float, t1_ms: float) -> float:
        """Funding in R of a whole position at `price` held over (t0, t1]."""
        if t1_ms <= t0_ms:
            return 0.0
        if FUNDING_PAID is not None:
            # eng-138 (audit R06): the settled rates themselves (the archive's fundingRate ledger in the replay), not the
            # entry's rate for the whole hold
            paid = FUNDING_PAID(s.symbol, t0_ms, t1_ms)
            if paid is not None:
                return s.direction * paid * price / risk
        return funding_r(s.sig.get('funding_rate'), s.direction, price, risk, t0_ms, t1_ms, s.sig.get('funding_interval_h'))

    @staticmethod
    def _cost_r(s: TrackedSignal, risk: float, exit_ms: float, parts: Optional[List[Tuple[float, float]]] = None) -> float:
        """eng-58: the round trip's cost in R - fees, the slippage of the entry and of the exit (by the coin's
        liquidity, levels.slippage_bps) and the funding settlements held through - as the journal's replay nets it.
        audit 2026-10-18 D: `parts` = [(share, left at ms)] - each share pays funding only until it left (a third out
        at TP1 pays no later settlement); None = the whole position held to exit_ms."""
        lv = s.levels or {}
        entry = lv.get('entry')
        if not entry or not risk:
            return 0.0
        cost = (CONFIG.journal.fee_round_trip + 2 * slippage_bps(s.sig.get('volume_24h'), s.symbol) / 1e4) * entry / risk
        t0 = (s.entered_at or 0) * 1000
        return cost + sum(share * SignalBook._funding_r(s, risk, entry, t0, min(t1, exit_ms) if t1 else exit_ms)
                          for share, t1 in (parts or [(1.0, exit_ms)]))

    @staticmethod
    def _exit_r(s: TrackedSignal, status: str) -> Optional[float]:
        """
        The card's realized R as it is traded: a third out at each target reached, the rest at the stop (SL) or at the
        last price (closed / expired). r_now marked the WHOLE position at the last price - a TP3 card read +2.62R where
        its thirds made +1.5R (VVV 2026-10-02), an SL after TP1 read -1.08R.
        """
        lv = s.levels or {}
        exit_ms = (s.finished_at or s.last_seen or 0) * 1000
        risk = lv.get('risk0') or (abs(lv['entry'] - lv['sl']) if lv.get('entry') and lv.get('sl') else None)
        # audit N13: the price the trade really left at (a gapped stop's fill, the overlay exit's close) for EVERY part
        # and unit - the scan's last price is a mark, not an exit
        rest = s.exit_fill if s.exit_fill is not None else (lv.get('sl') if status == 'SL' else s.last_price)
        if s.units or not all(isinstance(lv.get(k), (int, float)) for k in ('entry', 'sl', 'tp1', 'tp2', 'tp3')):
            gross = None
            if risk and rest is not None:
                gross = (sum(s.direction * (rest - u[0]) for u in s.units) if s.units else
                         s.direction * (rest - lv['entry'])) / risk
            if gross is not None and (s.plan or {}).get('p1r_done'):
                share = CONFIG.executor.partial_share
                gross = share * CONFIG.executor.partial_r + (1 - share) * gross   # eng-105: the partial at +1R
            if gross is None:
                return None
            if not s.units:
                return gross - SignalBook._cost_r(s, risk, exit_ms, parts=SignalBook._parts_held(s, 0, exit_ms))
            # audit 2026-10-18 D: each unit pays its own round trip and the funding from the time it was added, at its
            # own price (was: every unit charged the first unit's funding from the trade's entry)
            fees = SignalBook._cost_r(s, risk, exit_ms, parts=[(1.0, (s.entered_at or 0) * 1000)])   # costs, no funding
            return gross - sum(fees * u[0] / lv['entry'] + SignalBook._funding_r(s, risk, u[0], u[1] * 1000, exit_ms)
                               for u in s.units)
        if not risk:
            return s.r_now
        reached = 3 if status == 'TP3' else min(int(s.best_target or 0), 3)
        if (s.plan or {}).get('trail_after_tp1'):
            # half at TP1, the other half where the trail / stop / close left it
            parts = ([lv['tp1']] if reached >= 1 else [rest]) + [rest]
            gross = sum(s.direction * (p - lv['entry']) for p in parts) / 2 / risk
        else:
            parts = [lv[f'tp{k}'] for k in range(1, reached + 1)] + [rest] * (3 - reached)
            gross = sum(s.direction * (p - lv['entry']) for p in parts) / 3 / risk
        if (s.plan or {}).get('p1r_done'):
            share = CONFIG.executor.partial_share
            gross = share * CONFIG.executor.partial_r + (1 - share) * gross     # eng-105: the partial at +1R
        return gross - SignalBook._cost_r(s, risk, exit_ms, parts=SignalBook._parts_held(s, reached, exit_ms))

    @staticmethod
    def _parts_held(s: TrackedSignal, reached: int, exit_ms: float) -> List[Tuple[float, float]]:
        """The position's parts as _exit_r books them, each with the time it left (audit 2026-10-18 D)."""
        pm, plan = s.part_ms or {}, s.plan or {}
        if plan.get('trail_after_tp1'):
            parts = [(0.5, pm.get('tp1', exit_ms) if reached >= 1 else exit_ms), (0.5, exit_ms)]
        else:
            parts = [(1 / 3, pm.get(f'tp{k}', exit_ms) if k <= reached and k < 3 else exit_ms) for k in (1, 2, 3)]
        if plan.get('p1r_done'):
            share = CONFIG.executor.partial_share
            parts = [(share, pm.get('p1r', exit_ms))] + [((1 - share) * w, t) for w, t in parts]
        return parts

    def _invalid_reason(self, s: TrackedSignal, price: float, invalid: float) -> str:
        anchor = (s.plan or {}).get('anchor') or {}
        if anchor.get('type') == 'leg' and not s.plan.get('fix_invalid'):
            return "the pullback erased the whole impulse"
        if anchor.get('type') == 'leg':
            return f"price {price:.6g} beyond the reversed leg's end {anchor['end']:.6g} and its stop pool ({invalid:.6g})"
        if anchor.get('type') == 'level':
            return f"price {price:.6g} beyond the extreme {anchor['extreme']:.6g} at {anchor.get('label') or 'the level'} ({invalid:.6g})"
        if anchor.get('type') == 'range':
            # eng-156: a Wyckoff card is invalid past the spring / upthrust extreme, not the range's middle (the text lied)
            return f"price {price:.6g} beyond the {'spring low' if s.direction > 0 else 'upthrust high'} ({invalid:.6g})"
        return f"price {price:.6g} back inside the range past its middle ({invalid:.6g})"

    def _advance(self, s: TrackedSignal, price: float, now: float, frames, candles_of,
                 confirm_of: Optional[ConfirmCheck]) -> Optional[TrackedSignal]:
        """Move one signal along its lifecycle; returns the entry (possibly a vetoed copy) when a trigger fired."""
        cfg = CONFIG.levels
        s.last_price = price
        if s.entered_at:
            self._manage_trade(s, price, now, candles_of)
            return None
        strategy = self.strategy(s)
        if strategy is None:
            self._finish(s, 'EXPIRED', now, "the strategy no longer exists")
            return None
        age = now - s.created
        now_ms = int(now * 1000)
        d = s.direction

        if not s.activated:
            # The first plan needs the coin's 15m history (after a start it loads in the background); a leg strategy
            # also its 1h history and level map (loaded once the card exists)
            frame = frames.get(s.symbol)
            if frame is None or frame.height < 20:
                s.status = 'BIAS'
                if age > cfg.watch_ttl_sec:
                    self._finish(s, 'EXPIRED', now, f"no 15m history for {_dur(cfg.watch_ttl_sec)}")
                return None
            if s.pending_since is None:
                s.pending_since = now
            if strategy.anchor_type == 'leg' and not getattr(strategy, 'own_leg', False) and self.map_ready_of \
                    and not self.map_ready_of(s.symbol) and now - s.pending_since < cfg.plan_wait_sec:
                s.status = 'BIAS'
                return None
            s.plan = self._plan(s, frames)
            if s.plan is None or not s.plan['targets']:
                self._drop(s, now, self._skip_reason.pop((s.symbol, s.group_key), 'no_leg') if s.plan is None else 'no_room')
                return None
            if s.plan.get('missable') and s.plan['entry'] != 'confirm' and d * (price - s.plan['targets'][0]) >= 0:
                # eng-74: a waiting card whose TP1 is already behind the price was born MISSED (ETH FLUSH REVERSAL
                # 2026-10-07 10:08, created after the bounce): not a card
                self._drop(s, now, 'tp1_passed')
                return None
            self._activate(s, s.plan, price, now)
            s.status = 'WATCH'
            if s.plan['entry'] == 'confirm' and not s.confirm_checked:
                s.confirm_checked = True
                entry = self._confirmation_entry(s, price, now_ms, confirm_of)
                if s.plan.get('confirm_only') and (entry is None or entry.vetoed):
                    # the system enters at its signal's close or not at all (no waiting for a retest)
                    why = entry.vetoed if entry is not None else 'no valid levels at the signal close'
                    self._finish(s, 'EXPIRED', now, f"the system's entry at the signal close was skipped ({why})")
                    return entry
                if entry is not None:
                    return entry
        # Until the entry the plan follows the chart (a continuing impulse moves its end, a running cascade its
        # extreme; fixed references stay). A continuation's plan is frozen once price is in its zone.
        elif not (strategy.frozen_in_zone and s.status == 'ZONE'):
            s.plan = self._plan(s, frames)
        if s.armed and s.plan:
            s.plan = {**s.plan, **s.armed['plan']}
        watch_ttl, zone_ttl, _ = strategy.ttls(self._tf(s))
        plan = s.plan
        if plan is None or not plan['targets']:
            s.status = 'BIAS'
            if CONFIG.strategies.structural_lifetimes and not self._plan_data_ready(s.symbol, frames, now):
                # the coin's history is not in yet (after a start: the 15m / 1h / 4h history loads in the background):
                # no plan says nothing about the setup - it waits (every restart expired 14-59 restored cards here),
                # at most its watch TTL (a coin whose data never comes - it left the universe)
                # eng-144: counted from the start-up too (journal 18-21.10: 112 restored SWEEP cards of liquid coins expired
                # here in three bursts, one per restart - their age counted from the setup, before the restart)
                if now - max(s.created, self._born) > watch_ttl:
                    self._finish(s, 'EXPIRED', now, f"no data for a plan within {_dur(watch_ttl)}")
            elif CONFIG.strategies.structural_lifetimes:
                # eng-108: no plan = no setup (was: waiting an invented watch_ttl for the leg to come back)
                # the strategy's own reason (plan['skip']) or the plan's state: 181 sweep cards in a day ended 'no plan'
                # with nothing to tell why
                why = 'no targets' if plan is not None else self._skip_reason.get((s.symbol, s.group_key))
                self._finish(s, 'EXPIRED', now, "the setup stopped qualifying (no plan" + (f": {why})" if why else ")"))
            elif age > watch_ttl:
                self._finish(s, 'EXPIRED', now, f"the leg stopped qualifying and did not return for {_dur(watch_ttl)}")
            return None

        invalid = s.invalid_price if s.invalid_price is not None else plan.get('invalid')
        if invalid is not None and version_no(s.logic_version) >= 137 and candles_of:
            # audit A01: every event since the card's creation, in time order - a wick through a touch invalidation
            # between two scans (or a close beyond it on the system's timeframe) ends the card even when the price is
            # back by the scan; a return never revives it
            hit = self._invalid_since(s, candles_of, invalid, plan.get('invalid_close_min'))
            if hit is not None:
                self._pool2_on_invalid(s, candles_of, now_ms)
                self._finish(s, 'INVALID', now, self._invalid_reason(s, hit, invalid))
                return None
        check = price
        if invalid is not None and plan.get('invalid_close_min'):
            # the system invalidates on a CLOSE beyond (a wick through is allowed): the last final candle of that tf
            check = self._last_close(s.symbol, candles_of, plan['invalid_close_min'])
        if invalid is not None and check is not None and d * (check - invalid) <= 0:
            self._pool2_on_invalid(s, candles_of, now_ms)
            self._finish(s, 'INVALID', now, self._invalid_reason(s, price, invalid))
            return None
        tp1 = plan['targets'][0]
        # eng-108: with structural lifetimes EVERY waiting card ends once TP1 traded before an entry (its structural end;
        # the invented waiting clocks are gone)
        tp_seen = self._tp1_since(s, candles_of, tp1, plan) if version_no(s.logic_version) >= 141 else None
        if (plan.get('missable') or CONFIG.strategies.structural_lifetimes) and (d * (price - tp1) >= 0
                                                                                  or tp_seen is not None):
            reasons = ', '.join(sorted(set(s.veto_log)))
            # two different failures: price never came back to the zone (the zone is too far from where the move
            # turns) vs it did and no trigger fired (the trigger is too strict)
            where = (f"in the zone {plan['zone_lo']:.6g}-{plan['zone_hi']:.6g} since "
                     f"{_dur(now - s.zone_since_ms / 1000)}" if s.status == 'ZONE' and s.zone_since_ms
                     else f"price never came back to the zone {plan['zone_lo']:.6g}-{plan['zone_hi']:.6g}")
            skipped = (f"; {s.vetoed_triggers} trigger(s) vetoed" + (f": {reasons}" if reasons else '')
                       if s.vetoed_triggers else f"; no {plan['trigger_minutes']}m trigger") + f" ({where})"
            self._finish(s, 'MISSED', now, f"TP1 {tp1:.6g} ({plan['target_src'][0]}) reached before an entry" + skipped)
            return None
        if plan.get('reset') is not None and s.status == 'ZONE' and d * (price - plan['reset']) > 0:
            s.status, s.zone_since_ms = 'WATCH', None       # the leg extended without a trigger: re-measure it
            return None
        if plan.get('trigger') == 'fvg' and not s.armed and s.status != 'ZONE' and (s.sig or {}).get('anchor_ts'):
            # eng-113, the order of the sources (sweep -> displacement AWAY with an FVG and a structure shift -> the
            # retrace into that FVG): the FVG is searched from the sweep candle on. It was searched only after price
            # first came BACK into the sweep candle's own range - which a real reversal never does: sweeps 12-14.10
            # had 75 MISSED ('price never came back to the zone'), 0 entries
            s.status, s.zone_since_ms = 'ZONE', int(s.sig['anchor_ts'])
            self.events.append((s, 'ZONE'))
        near_edge = plan['zone_hi'] if d > 0 else plan['zone_lo']
        in_zone = d * (price - near_edge) <= 0
        since_ms = now_ms // 60_000 * 60_000
        if s.status != 'ZONE' and not in_zone and plan.get('trigger') == 'touch' and candles_of:
            # eng-102: a resting limit (the demo's on BingX too) fills on a WICK into the line between two scans: the
            # final 1m candles since the card's plan decide, not only the price at the scan
            start = int((s.pending_since or s.created) * 1000)
            hit = next((c for c in candles_of(s.symbol)
                        if c[0] + MINUTE_MS > start and (c[3] <= near_edge if d > 0 else c[2] >= near_edge)), None)
            if hit is not None:
                in_zone, since_ms = True, int(hit[0])
        if s.status != 'ZONE' and in_zone:
            s.status, s.zone_since_ms = 'ZONE', since_ms
            self.events.append((s, 'ZONE'))
        elif s.status != 'ZONE':
            s.status = 'WATCH'

        end_ms = (s.sig or {}).get('session_end_ms')
        if end_ms and now_ms >= end_ms:
            # eng-95: a session setup (ORB / VA80 / AUCTION) not entered before its session closed is over
            self._finish(s, 'EXPIRED', now, "session_end: the session closed without an entry")
            return None
        if s.status == 'ZONE' and ict_gated(s.mode, s.group_key) and s.zone_since_ms:
            # eng-59, ICT: a setup lives within its kill zone - one that came into its zone inside a kill zone and saw
            # it end without an entry is over (the next session builds its own setup)
            kz = tuple(CONFIG.strategies.smt_session)
            if in_session(int(s.zone_since_ms), kz) and not in_session(now_ms, kz) and \
                    'killzone' not in CONFIG.strategies.shadow_vetoes:
                # eng-107: with 'killzone' in shadow the card lives on (ETH 2026-10-14 expired at 09:00 UTC 45 min
                # after its sweep, then gave the channel's whole move); an entry outside it is journaled shadow_veto
                self._finish(s, 'EXPIRED', now, "session_end: the kill zone ended without an entry")
                return None
        until = plan.get('entry_until_ms')
        if until and now_ms >= until:
            # audit (Silver Bullet): the method's own entry window ended - no NEW entry after it (an entered trade is
            # managed on; structural_lifetimes does not extend the window)
            self._finish(s, 'EXPIRED', now, "entry window ended without an entry")
            return None
        reclaim = self._reclaim_entry(s, price, now_ms)
        if reclaim is not None:
            return reclaim
        if s.status == 'ZONE':
            entry = self._try_entry(s, price, now_ms, candles_of, confirm_of)
            if entry is not None:
                return entry
            # the order-flow entry is journaled only when the method's own trigger did not enter this scan
            flow = self._flow_entry(s, list(candles_of(s.symbol)), now_ms, price, confirm_of)
            if flow is not None:
                return flow
            if not CONFIG.strategies.structural_lifetimes and now_ms - s.zone_since_ms > zone_ttl * 1000:
                self._finish(s, 'EXPIRED', now, f"no valid {plan['trigger_minutes']}m trigger in the zone "
                             f"for {_dur(zone_ttl)}" + (f" ({s.vetoed_triggers} vetoed)" if s.vetoed_triggers else ''))
        elif age > watch_ttl and not CONFIG.strategies.structural_lifetimes:
            self._finish(s, 'EXPIRED', now, f"price did not reach the zone in {_dur(watch_ttl)}")
        return None

    def _try_entry(self, s: TrackedSignal, price: float, now_ms: int, candles_of,
                   confirm_of: Optional[ConfirmCheck]) -> Optional[TrackedSignal]:
        d = s.direction
        minutes = list(candles_of(s.symbol))   # final 1m candles only
        if not minutes:
            return None
        trigger_minutes = s.plan['trigger_minutes']
        interval_ms = trigger_minutes * 60_000
        # A trigger candle is complete once its last minute is final (not by the wall clock: that minute's final
        # kline arrives a moment after the minute ends, and the entry would be a mid-minute price)
        ltf = _resample(s.symbol, minutes, trigger_minutes, minutes[-1][0] + MINUTE_MS)
        kind = s.plan.get('trigger', 'shift')
        shadow = self._shadow_entry(s, ltf, kind, interval_ms, now_ms, price)
        self._limit_variants(s, ltf, interval_ms, now_ms, price)
        self._pool2_variant(s, ltf, interval_ms, now_ms)
        if kind == 'fvg':
            # ICT 2022 (eng-58): the sweep is only the setup; once the displacement broke the swing the raid came from
            # and left a gap, a limit rests at the gap's CE (the plan becomes a touch plan: the demo places it)
            setup = fvg_setup(ltf, d, s.zone_since_ms, interval_ms)
            if setup is not None:
                s.armed = {'plan': {'trigger': 'touch', 'zone_lo': setup['ce'], 'zone_hi': setup['ce'],
                                    'single_touch': True, 'fvg': [setup['gap_lo'], setup['gap_hi']],
                                    'mss': setup['mss']},
                           'since': setup['time']}
                s.plan = {**s.plan, **s.armed['plan']}
                s.zone_since_ms = setup['time']
            return shadow
        elif kind == 'touch':
            touch = touch_confirm if CONFIG.executor.touch_confirm_close else touch_trigger
            trigger = touch(ltf, d, s.zone_since_ms, interval_ms, s.plan['zone_lo'], s.plan['zone_hi'])
        else:
            trigger = ltf_trigger(ltf, d, s.zone_since_ms, interval_ms)
        if not trigger:
            return shadow
        if now_ms - trigger['time'] > interval_ms + 2 * MINUTE_MS:
            # A break that closed long ago (the card was restored after a restart, the feed had a gap): its price is
            # history, not an entry a human could take now. Look for the next one after it.
            s.zone_since_ms = trigger['time']
            return None
        levels = entry_levels(s.plan, trigger['entry'], trigger['extreme'], d)
        if not levels or d * (price - levels['sl']) <= 0:
            return None
        levels['zone_src'] = s.plan.get('zone_src')
        levels['range_pos'] = range_position(s.plan.get('dealing_range'), levels['entry'], d)
        reason = None
        reason = self._overshoot(s, trigger['entry'], levels)
        self._st_stop_variant(s, levels, trigger, now_ms, price)
        # the spring candle's average FUTURES minute (the pullback minutes are futures candles); a card restored from
        # an older state has only the spot figure: no test rather than a test in the wrong units
        spring_minute = s.sig.get('fut_candle_minute_usd')
        if spring_minute is None and not s.sig.get('has_spot'):
            spring_minute = s.sig.get('candle_minute_usd')
        tested = s.group_key in ('BULL B', 'SPRING', 'UTAD', 'FLUSH REVERSAL', 'SQUEEZE REVERSAL')
        vol_ok = pullback_volume_ok(minutes, s.zone_since_ms, trigger['time'], spring_minute or 0.0) if tested else True
        spread_ok = pullback_spread_ok(minutes, s.zone_since_ms, trigger['time'], s.sig.get('spring_range'),
                                       s.sig.get('spring_tf_min') or
                                       {'15m': 15, '1h': 60, '4h': 240, '1d': 1440}.get(s.sig.get('wy_tf') or '1h', 60)) \
            if s.group_key in ('SPRING', 'UTAD') else True
        if vol_ok is False:
            reason = 'no_spring_test'
        elif spread_ok is False:
            reason = 'no_spring_test'                # eng-55: the test's spread did not narrow
        elif vol_ok is None or spread_ok is None:
            reason = 'no_test_data'                  # audit C08: the test was not observable - not passed
        confirms = confirm_of(s.symbol, s.mode, d, s.zone_since_ms, trigger['time'], trigger.get('extreme_time')) \
            if confirm_of else {}
        if confirms is not None and s.plan:
            # ICT / Seiden: an entry whose price sits inside a zone of 4h or higher is the higher-probability one
            confirms['htf_zone'] = htf_zone_at(s.plan.get('zones') or [], levels['entry'])
        if s.mode == 'sweep' and confirms is not None:
            # ICT's own confirmations of a sweep (eng-35): SMT divergence against the correlate, the entry in a kill zone
            if s.sig.get('smt_div') is not None:
                confirms['smt'] = bool(s.sig['smt_div'])
            if CONFIG.strategies.smt_session:
                confirms['killzone'] = in_session(trigger['time'], tuple(CONFIG.strategies.smt_session))
        if reason is None:
            reason = shadow_veto(s.sig, confirm.missing(s.mode, confirms))
        if reason is None and ict_gated(s.mode, s.group_key)                 and not in_session(trigger['time'], tuple(CONFIG.strategies.smt_session)):
            reason = shadow_veto(s.sig, 'killzone')   # eng-58 rule; eng-107: shadow (unproven filter)
        if reason is None:
            reason = shadow_veto(s.sig, self._against_day(s, trigger['time']))   # eng-112: no source - shadow
        if reason is None and s.plan.get('session') and not in_session(trigger['time'], tuple(s.plan['session'])):
            reason = 'off_session'
        if reason is None and CONFIG.levels.veto_low_rr and levels.get('low_rr'):
            reason = 'low_rr'
        if reason:
            # Keep waiting for the next trigger after this one
            s.zone_since_ms = trigger['time']
            if s.plan.get('single_touch'):
                vetoed = self._enter(s, levels, now_ms, reason, confirms)
                self._finish(s, 'EXPIRED', now_ms / 1000, f"the zone's first touch was vetoed ({reason}): no longer fresh")
                return vetoed
        return self._enter(s, levels, now_ms, reason, confirms)

    def _invalid_since(self, s: TrackedSignal, candles_of, invalid: float,
                       close_min: Optional[int]) -> Optional[float]:
        """
        Audit A01: the first final event beyond `invalid` since the last check (s.inv_ms; from the first whole minute
        after the card's creation): a 1m low / high through it (touch rule), or with `close_min` a close beyond it of
        a final `close_min` bar that closed after the card was created. Returns that price, None without one; moves
        s.inv_ms to the end of the last final minute seen. A re-planned (moving) invalidation is checked on the minutes
        since the last check only.
        """
        allm = candles_of(s.symbol)
        if not isinstance(allm, list):
            allm = list(allm or [])
        if not allm:
            return None
        d = s.direction
        start = s.inv_ms or (int(s.created * 1000) // MINUTE_MS + 1) * MINUTE_MS
        done = int(allm[-1][0]) + MINUTE_MS
        s.inv_ms = max(start, done)
        size = int(close_min or 1) * MINUTE_MS
        # the buffer is in time order: only its tail since the last check (+ one bar of the close rule's timeframe)
        k = len(allm)
        while k and allm[k - 1][0] >= start - size:
            k -= 1
        minutes = list(allm[k:])
        if close_min:
            for b in _resample(s.symbol, minutes, int(close_min), done):
                if b[0] + size > start and d * (b[4] - invalid) <= 0:
                    return float(b[4])
            return None
        for c in minutes:
            if c[0] >= start and ((c[3] <= invalid) if d > 0 else (c[2] >= invalid)):
                return float(c[3] if d > 0 else c[2])
        return None

    def _tp1_since(self, s: TrackedSignal, candles_of, tp1: float, plan: Optional[Dict] = None) -> Optional[float]:
        """Audit B03: the first final 1m high / low at TP1 since the last check (s.tp_ms; from the first whole minute after
        the card's creation) - a wick through TP1 between two scans ends the waiting card though the price is back.
        Only the minutes since the last check are read, with the plan of that moment (a moved TP1 is never applied to
        the older candles)."""
        if not candles_of:
            return None
        allm = candles_of(s.symbol)
        if not isinstance(allm, list):
            allm = list(allm or [])
        if not allm:
            return None
        start = s.tp_ms or (int(s.created * 1000) // MINUTE_MS + 1) * MINUTE_MS
        s.tp_ms = max(start, int(allm[-1][0]) + MINUTE_MS)
        k = len(allm)
        while k and allm[k - 1][0] >= start:
            k -= 1
        edge = (plan or {}).get('zone_hi' if s.direction > 0 else 'zone_lo') if (plan or {}).get('trigger') == 'touch' else None
        for c in allm[k:]:
            if edge is not None and not CONFIG.executor.touch_confirm_close and \
                    ((c[3] <= edge) if s.direction > 0 else (c[2] >= edge)):
                # the resting limit filled there; with touch_confirm_close a touch is no entry (it waits for a close
                # back), so a run to TP1 after the touch still ends the card - the batch's later minutes are read
                return None              # the limit's line traded first (or in the same minute): the touch rules decide
            if (c[2] >= tp1) if s.direction > 0 else (c[3] <= tp1):
                return float(c[2] if s.direction > 0 else c[3])
        return None

    @staticmethod
    def _last_close(symbol: str, candles_of, minutes_tf: int) -> Optional[float]:
        """Close of the last FINAL candle of `minutes_tf` minutes (from the final 1m candles), None without data."""
        minutes = list(candles_of(symbol)) if candles_of else []
        if not minutes:
            return None
        bars = _resample(symbol, minutes, minutes_tf, minutes[-1][0] + MINUTE_MS)
        return bars[-1][4] if bars else None

    def _confirmation_entry(self, s: TrackedSignal, price: float, now_ms: int,
                            confirm_of: Optional[ConfirmCheck]) -> Optional[TrackedSignal]:
        """
        Entry at the setup's confirmation (the closed candle that confirmed it), at the current price: taken when R:R
        to TP1 allows it, else the card waits in its zone for a trigger.
        """
        levels = entry_levels(s.plan, price, None, s.direction)
        if not levels or s.direction * (price - levels['sl']) <= 0:
            return None
        levels['zone_src'] = 'setup confirmation'
        levels['range_pos'] = range_position(s.plan.get('dealing_range'), levels['entry'], s.direction)
        anchor = s.plan.get('anchor') or {}
        # the confirming event: a breakout's candle, a reversed leg's end, else the anchor
        since = int(anchor.get('break_ts') or anchor.get('end_ts') or anchor.get('ts') or now_ms - 900_000)
        # a reversal's confirmation follows the reversed leg's end: that is its extreme
        extreme_ms = int(anchor['end_ts']) if anchor.get('end_ts') and s.mode in confirm.REVERSALS else None
        confirms = confirm_of(s.symbol, s.mode, s.direction, since, now_ms, extreme_ms) if confirm_of else {}
        # an entry AT the signal's close (VA80, AUCTION, BB W / M, cup): the method's own rule puts that close past
        # its level by design - journaled, not vetoed (review of eng-147)
        self._overshoot(s, levels['entry'], levels, block=False)
        reason = shadow_veto(s.sig, confirm.missing(s.mode, confirms))
        if reason is None and CONFIG.levels.veto_low_rr and levels.get('low_rr'):
            reason = 'low_rr'
        return self._enter(s, levels, now_ms, reason, confirms)

    OVERSHOOT_EXEMPT = ('orb', 'breakout', 'connors', 'pump')    # stop-order / channel / close entries: no zone edge

    @staticmethod
    def _overshoot(s: TrackedSignal, entry: float, levels: Dict, block: bool = True) -> Optional[str]:
        """
        eng-147 measured how far a trigger close ran past the setup's level (the anchor's level for sweeps, else the
        zone's trade-side edge) in working-tf ATRs. eng-148 (audit: the 0.6 ATR threshold was chosen in sample): the
        ATR overshoot is journaled only; the residual R:R from the trigger price is low_rr's own check (entry_levels
        at the trigger close vs the method's min_rr), so nothing more blocks here.
        Journaled too: cost_r (the round-trip cost in R) and rr_trigger.
        """
        plan, d = s.plan or {}, s.direction
        anchor = plan.get('anchor') or {}
        sl, tp1 = levels.get('sl'), levels.get('tp1')
        if entry is not None and sl is not None and d * (entry - sl) > 0:
            from strategies.geometry import cost_of
            fee = cost_of(entry, (s.sig or {}).get('volume_24h'), s.symbol)
            risk = d * (entry - sl)
            levels['cost_r'] = fee / risk
            if tp1 is not None and not plan.get('no_tp'):
                levels['rr_trigger'] = (d * (tp1 - entry) - fee) / (risk + fee)
        edge = anchor.get('level') if s.mode == 'sweep' and anchor.get('type') == 'level' else None
        if edge is None and plan.get('zone_lo') is not None and plan.get('zone_hi') is not None:
            edge = plan['zone_hi'] if d > 0 else plan['zone_lo']
        work = plan.get('tf_atr') or plan.get('leg_atr') or plan.get('atr')
        if edge is not None and work and entry is not None:
            levels['zone_edge'], levels['trigger_over_atr'] = edge, d * (entry - edge) / work
        # review of eng-148: the residual R:R check IS low_rr (geometry's rrs[0] vs the method's min_rr at the trigger
        # price) - no separate veto; journal only
        return None

    def _enter(self, s: TrackedSignal, levels: Dict, now_ms: int, reason: Optional[str],
               confirms: Dict) -> TrackedSignal:
        """Enter, or journal the entry that would have been taken with the veto reason (the card keeps waiting)."""
        entered_at = now_ms / 1000
        if reason is None:
            from macro_calendar import blackout
            if blackout(now_ms):
                reason = 'macro_event'
        # eng-106 / eng-127: RSI2X (Connors' original entry), BB3 (Bollinger's Method III), the cascade reversals and
        # Pring's OI rule are measured in shadow beside the traded rules (SHADOW_SETUPS)
        if reason is None:
            reason = shadow_of(s.group_key)
        if reason is None and s.mode == 'supply_demand' and (s.plan or {}).get('sd_score', 10) < 8:
            reason = 'sd_score'          # eng-127: Seiden / OTA - below 8 of 10 odds enhancer points no trade
        if reason is None and self.crowded(s.mode, s.direction, entered_at):
            reason = 'crowded'
        if reason is None and self._market_down(s):
            if s.group_key in self.MARKET_DOWN_SHADOW:
                have = set(filter(None, (s.sig.get('shadow_veto') or '').split(',')))
                s.sig['shadow_veto'] = ','.join(sorted(have | {'market_down'}))
            else:
                reason = 'market_down'
        hb = (confirms or {}).get('_bias') or {}
        if reason is None:
            # the top-down bias decides the side before any lower-timeframe setup (strategies/bias.py)
            key = 'bias_daily' if s.mode in htf_bias.DAILY else 'bias'
            reason = shadow_veto(s.sig, htf_bias.gate(s.mode, s.direction, (hb.get('coin') or {}).get(key),
                                                      (hb.get('btc') or {}).get(key), s.symbol.startswith('BTC/')))
        rg_state = (hb.get('coin') or {}).get('rg')
        if rg_state:
            from strategies import regime as rg
            s.sig['regime2'] = rg.label(rg_state)
            if reason is None:
                reason = shadow_veto(s.sig, rg.verdict(rg_state, s.mode, s.direction))
        if reason is None and s.mode not in htf_bias.EXEMPT and s.mode not in htf_bias.DAILY \
                and (hb.get('coin') or {}).get('h4') == -s.direction:
            # eng-84, the owner's review of the live trades: longs bought inside a falling 4h trend (BB W, AUCTION) -
            # an intraday entry also needs the 4h trend not against it (the daily bias alone updates once a day)
            reason = shadow_veto(s.sig, 'h4_against')
        adx4 = (hb.get('coin') or {}).get('adx4')
        if reason is None and adx4 is not None:
            # eng-84, market regime by ADX(14) of 4h (Wilder: > 25 trend, < 25 range): momentum / trend methods only in
            # a trend, mean-reversion / range methods only in a range, Connors' pullback only below 35
            if s.mode in REGIME_TREND and adx4 < 25:
                reason = 'regime_flat'
            elif s.mode in REGIME_RANGE and adx4 >= 25:
                reason = 'regime_trend'
            elif s.mode == 'connors' and adx4 >= 35:
                reason = 'regime_trend'
            reason = shadow_veto(s.sig, reason)
        prof, regime_veto = profiles.select(s.mode, (confirms or {}).get('_regime'))
        if not CONFIG.strategies.optimized_profiles:
            prof, regime_veto = None, None      # eng-128: data-mined profiles off (no source)
        if reason is None and regime_veto:
            reason = shadow_veto(s.sig, regime_veto)
        if reason is None and not prof and CONFIG.strategies.optimized_profiles:
            for f in profiles.overlay_filters(s.mode, 'plan'):
                if f == 'alts_with':
                    mkt, btc = s.sig.get('mkt_4h'), s.sig.get('btc_4h')
                    if mkt is not None and btc is not None and s.direction * (mkt - btc) <= 0:
                        reason = shadow_veto(s.sig, 'alts_vs_btc')
        if reason is None and prof and confirms is not None and not confirms.get('_ind') and prof.get('filters'):
            # no indicator panel (a REST failure / no history): missing data is no veto (the project's rule)
            logger.warning(f"Profile filters of {s.symbol} {s.group_key} skipped: no indicator panel")
        if reason is None and prof and confirms is not None and confirms.get('_ind'):
            # the strategy's optimized profile (research_optimize.py): its filters, measured as the research did
            ind = confirms.get('_ind') or {}
            flags = profiles.masks(ind, s.sig.get('volume_24h'), now_ms, s.direction, confirms.get('_btc_slope'),
                                   None, (ind.get('1h') or {}).get('atr_high'))
            missing_flags = [f for f in prof.get('filters') or [] if not flags.get(f)]
            if missing_flags:
                reason = shadow_veto(s.sig, 'profile')
                s.veto_notes = (s.veto_notes + [f"profile: not {', '.join(missing_flags)}"])[-5:]
        of = confirms.get('orderflow') or None
        if reason:
            key = [reason, levels.get('entry'), levels.get('sl')]
            if key == s.last_veto:
                # the same trigger vetoed again on the next scan (a touch plan sitting at its line, PO3 2026-10-06:
                # 213 rows of one SAND card in 39 min): journaled once, not once per scan
                return None
            s.last_veto = key
            vetoed = copy.copy(s)
            vetoed.levels, vetoed.entered_at, vetoed.vetoed = levels, entered_at, reason
            vetoed.of_confirm, vetoed.confirms = of, dict(confirms)
            s.vetoed_triggers += 1
            if reason == 'low_rr' and levels.get('entry'):
                # A stop that far does not pay: the question is why the signal came here (entry vs the zone's edge)
                e = levels['entry']
                edge = (s.plan or {}).get('zone_lo' if s.direction > 0 else 'zone_hi')
                risk = abs(e - levels['sl'])
                # a method without a profit target (Bollinger's live band, Turtles, Connors, ORB) carries 100 / 200 /
                # 300 R placeholders: printed as a percentage they read as a real 30-100% target
                placeholder = ((s.plan or {}).get('no_tp') or levels.get('tp1') is None
                               or (risk and abs(levels['tp1'] - e) >= 50 * risk))
                tp1_text = (f"no TP1 ({levels.get('tp1_src')})" if placeholder
                            else f"TP1 {abs(levels['tp1'] - e) / e:.2%} ({levels.get('tp1_src')})")
                text = (f"low_rr ({levels.get('rr_reason') or 'R:R'}): stop {risk / e:.2%} ({levels.get('sl_src')}), "
                        f"{tp1_text}"
                        + (f", entry {abs(e - edge) / e:.2%} from the zone edge ({levels.get('zone_src')})"
                           if edge else ''))
                s.veto_notes = (s.veto_notes + [text])[-5:]
            s.veto_log.append(reason)
            return vetoed
        # a system that enters at its signal's close or never (confirm_only: Turtles / Connors / PUMP) is not held
        if getattr(self, '_deferring', False) and not (s.plan or {}).get('confirm_only'):
            self._deferred.append((s, levels, now_ms, confirms))
            return DEFERRED                 # an entry, held: the card's other entry paths stay quiet this pass
        if prof and prof.get('pm'):
            # the profile's position management: stop / targets now, breakeven / trail / time stop in _manage_trade
            profiles.apply_pm(levels, prof['pm'], s.direction)
            s.plan = {**(s.plan or {}), 'pm': dict(prof['pm']), 'profile': prof.get('status', 'candidate'),
                      'pm_atr': confirms.get('_atr_1h'), 'pm_best': None, 'trail_after_tp1': False,
                      'no_tp': str(prof['pm'].get('target')) == 'none' or bool((s.plan or {}).get('no_tp'))}
        # eng-128: no 'range middle (HTF)' override of the methods' own targets (it had no source)
        levels['risk0'] = abs(levels['entry'] - levels['sl'])
        overlays = profiles.exit_overlays(s.mode, 'profile' if prof and prof.get('pm') else 'plan') \
            if CONFIG.strategies.optimized_profiles else []
        if overlays:
            s.plan = {**(s.plan or {}), 'exit_overlays': overlays, 'ov_best': None}
        if (s.plan or {}).get('add_half'):
            # the owner's averaging: one more unit of the same size at half the way to the stop (SignalBook._manage_trade)
            s.units = [[levels['entry'], entered_at]]
        if (s.plan or {}).get('trail_days'):
            # the Turtles' portfolio limit: at most turtle_max_direction_units units in one direction across all coins
            held = sum(len(o.units) for o in self.signals.values()
                       if o is not s and not o.finished and o.units and o.direction == s.direction)
            if held + 1 > CONFIG.strategies.turtle_max_direction_units:
                return self._enter(s, levels, now_ms, 'unit_limit', confirms)
            s.units = [[levels['entry'], entered_at]]
        s.levels, s.entered_at, s.status, s.of_confirm, s.confirms = levels, entered_at, 'ENTRY', of, dict(confirms)
        if version_no(s.logic_version) >= 137:
            # audit A02: the entry minute is managed too - on the trades after the entry, not on its whole 1m range
            s.managed_ms = now_ms // MINUTE_MS * MINUTE_MS
            if self.track_from:
                self.track_from(s.symbol, int(entered_at * 1000))
        else:
            s.managed_ms = (now_ms // MINUTE_MS + 1) * MINUTE_MS
        self.day_dir.setdefault((s.symbol, int(now_ms // 86_400_000)), s.direction)
        self.events.append((s, 'ENTRY'))
        return s

    def _variant(self, s: TrackedSignal, name: str, levels: Dict, now_ms: int, limit: bool = False):
        """eng-149: a shadow variant of the card journaled as a vetoed entry `name` (never traded), once per card."""
        s.variants_done.append(name)
        shadow = copy.copy(s)
        shadow.levels, shadow.entered_at, shadow.vetoed = levels, now_ms / 1000, name
        shadow.of_confirm, shadow.confirms, shadow.limit_variant = None, {}, limit
        self._extra.append(shadow)

    def _limit_variants(self, s: TrackedSignal, ltf, interval_ms: int, now_ms: int, price: float):
        """
        eng-149 (plan eng-148 stage 3.1, audit 13 / 34): once a sweep is armed (MSS + FVG), resting limits at the CE
        ('variant_ce_limit') and at the gap's near edge ('variant_fvg_edge'), filled on the touch at the limit price,
        the plan's own stop / targets - on the same armed cards as the live touch -> close entry, low_rr or not.
        stats.py reads the 50/50 split (edge + CE, one stop) from the pair.
        """
        fvg = s.plan.get('fvg')
        if s.mode != 'sweep' or not fvg or s.plan.get('trigger') != 'touch' or not s.zone_since_ms:
            return
        d = s.direction
        edge = max(fvg) if d > 0 else min(fvg)
        for name, level in (('variant_ce_limit', s.plan['zone_lo']), ('variant_fvg_edge', edge)):
            if name in s.variants_done:
                continue
            trig = touch_trigger(ltf, d, s.zone_since_ms, interval_ms, level, level)
            if not trig:
                continue
            if now_ms - trig['time'] > interval_ms + 2 * MINUTE_MS:
                s.variants_done.append(name)        # a stale touch (restart / gap): not this card's variant
                continue
            # review: the resting limit's stop is known BEFORE the touch (no wick of the touch bar), and the journal
            # window starts at the touch bar's open, so a stop inside that bar counts (conservative: the bar's
            # minutes before the touch count too)
            levels = entry_levels(s.plan, level, None, d)
            if levels and d * (levels['entry'] - levels['sl']) > 0:
                levels['zone_src'] = s.plan.get('zone_src')
                self._variant(s, name, levels, trig['time'] - interval_ms, limit=True)

    def _pool2_on_invalid(self, s: TrackedSignal, candles_of, now_ms: int):
        """review eng-151: the second raid usually runs through the card's invalidation - the variant is read before
        the card ends INVALID, or only the touches that turned within the pad would be journaled (survivorship)."""
        if s.mode != 'sweep' or not s.plan.get('pool2') or 'variant_pool2' in s.variants_done:
            return
        minutes = list(candles_of(s.symbol))
        if not minutes:
            return
        # re-review: the touch on the final 1m candles themselves (a closed trigger candle misses a fast raid inside
        # the forming one), any time since the zone, including the invalidation's minute
        self._pool2_variant(s, minutes, MINUTE_MS, now_ms, stale=False)

    def _pool2_variant(self, s: TrackedSignal, ltf, interval_ms: int, now_ms: int, stale: bool = True):
        """
        eng-151 (external audit #2): when an untaken pool sits within zone_move_pool_atr beyond the sweep's extreme
        (plan['pool2']), a resting limit at that pool's liquidity, filled on the touch - the second raid - with the
        plan's stop rule from the pool and its targets, 'variant_pool2' (never traded), against the live entry.
        """
        p2 = s.plan.get('pool2')
        if s.mode != 'sweep' or not p2 or not s.zone_since_ms or 'variant_pool2' in s.variants_done:
            return
        level = p2['entry']
        trig = touch_trigger(ltf, s.direction, s.zone_since_ms, interval_ms, level, level)
        if not trig:
            return
        if stale and now_ms - trig['time'] > interval_ms + 2 * MINUTE_MS:
            s.variants_done.append('variant_pool2')     # a stale touch (restart / gap)
            return
        levels = entry_levels(dict(s.plan, stop_ref=level), level, None, s.direction)
        if levels and s.direction * (levels['entry'] - levels['sl']) > 0:
            levels['zone_src'] = f"second raid: {p2['label']} (variant)"
            self._variant(s, 'variant_pool2', levels, trig['time'] - interval_ms, limit=True)

    def _st_stop_variant(self, s: TrackedSignal, levels: Dict, trigger: Dict, now_ms: int, price: float):
        """
        eng-149 (plan eng-148 stage 3.6, audit 12): Wyckoff's entry on the secondary test with the stop beyond the
        TEST's extreme (+ 0.25 working ATR, a heuristic pad) instead of beyond the spring / climax - the same entry and
        targets, 'variant_st_stop', only where that stop is tighter than the live one.
        """
        if s.group_key not in ('SPRING', 'UTAD', 'FLUSH REVERSAL', 'SQUEEZE REVERSAL') or \
                'variant_st_stop' in s.variants_done:
            return
        d, atr = s.direction, s.plan.get('tf_atr') or s.plan.get('atr') or 0.0
        sl = trigger['extreme'] - d * 0.25 * atr
        e = levels['entry']
        if d * (e - sl) <= 0 or d * (sl - levels['sl']) <= 0 or d * (price - sl) <= 0:
            return
        lv = dict(levels, sl=sl, sl_src='Wyckoff test extreme + 0.25 ATR (variant)')
        scale = (d * (e - levels['sl'])) / (d * (e - sl))
        if levels.get('cost_r') is not None:
            lv['cost_r'] = levels['cost_r'] * scale            # the same fees over the tighter risk
        if levels.get('tp1') is not None:
            lv['rr_tp1'] = d * (levels['tp1'] - e) / (d * (e - sl))
        lv.pop('rr_trigger', None)
        self._variant(s, 'variant_st_stop', lv, now_ms)

    def _shadow_entry(self, s: TrackedSignal, ltf, kind: str, interval_ms: int, now_ms: int,
                      price: float) -> Optional[TrackedSignal]:
        """
        eng-59: the rule eng-58 replaced, journaled as a vetoed entry of the same card so the journal compares both on
        the same events (vetoes_table): 'weak_mss' = the old sweep trigger (a close beyond the high made after the
        raid, entry at the CE touch) while the new MSS has not armed the card; 'variant_shift' = the old market entry
        on the 5m structure shift beside the resting limit (continuation, an armed sweep). Inside the kill zone only,
        once per trigger.
        """
        if not ict_gated(s.mode, s.group_key):
            return None
        d = s.direction
        if kind == 'fvg':
            trig, reason = fvg_trigger(ltf, d, s.zone_since_ms, interval_ms), 'weak_mss'
        elif kind == 'touch' and (s.armed or s.mode == 'continuation'):
            trig, reason = ltf_trigger(ltf, d, s.zone_since_ms, interval_ms), 'variant_shift'
        else:
            return None
        if not trig or trig['time'] <= s.shadow_ms or now_ms - trig['time'] > interval_ms + 2 * MINUTE_MS:
            return None
        s.shadow_ms = int(trig['time'])
        if not in_session(trig['time'], tuple(CONFIG.strategies.smt_session)):
            return None
        levels = entry_levels(s.plan, trig['entry'], trig['extreme'], d)
        if not levels or d * (price - levels['sl']) <= 0:
            return None
        levels['zone_src'] = s.plan.get('zone_src')
        levels['range_pos'] = range_position(s.plan.get('dealing_range'), levels['entry'], d)
        shadow = copy.copy(s)
        shadow.levels, shadow.entered_at, shadow.vetoed = levels, now_ms / 1000, reason
        shadow.of_confirm, shadow.confirms = None, {}
        return shadow

    def _flow_entry(self, s: TrackedSignal, minutes, now_ms: int, price: float,
                    confirm_of: Optional[ConfirmCheck]) -> Optional[TrackedSignal]:
        """
        The order-flow entry in the zone (2026-10-05, the owner: "we look for the best entry point in the zone"),
        journaled beside the method's own trigger on the same card (vetoed 'flow_entry', never traded) so the journal
        compares the two: once a minute while the card is in its zone, the confirmations since the zone was reached
        - an order-flow reading (absorption, stacked imbalance or a finished auction at the extreme), the taker
        delta since the zone's extreme turned the trade's way, and OI as the method's type expects (rising for
        breaks / continuations, falling for fades; 'n/a' where a method has no OI hypothesis). All three -> an
        entry at the price with the stop beyond the zone's extreme (the plan's own geometry), once per card.
        """
        if s.flow_done or not confirm_of or not s.zone_since_ms or not minutes:
            return None
        minute = int(minutes[-1][0]) + MINUTE_MS            # the end of the last final minute
        if minute <= s.flow_checked_ms or minute - s.zone_since_ms < 3 * MINUTE_MS:
            return None
        s.flow_checked_ms = minute
        d = s.direction
        since = [c for c in minutes if c[0] >= s.zone_since_ms]
        if not since:
            return None
        ext_bar = min(since, key=lambda c: c[3]) if d > 0 else max(since, key=lambda c: c[2])
        extreme = ext_bar[3] if d > 0 else ext_bar[2]
        c = confirm_of(s.symbol, s.mode, d, s.zone_since_ms, minute, int(ext_bar[0]))
        if not c or not confirm.positive(c.get('orderflow')) or c.get('flow') is not True \
                or c.get('oi') not in (True, confirm.NA):
            return None
        levels = entry_levels(s.plan, price, extreme, d)
        if not levels or d * (price - levels['sl']) <= 0:
            return None
        s.flow_done = True
        levels['zone_src'] = s.plan.get('zone_src')
        levels['range_pos'] = range_position(s.plan.get('dealing_range'), levels['entry'], d)
        shadow = copy.copy(s)
        shadow.levels, shadow.entered_at, shadow.vetoed = levels, now_ms / 1000, 'flow_entry'
        shadow.of_confirm, shadow.confirms = c.get('orderflow'), dict(c)
        return shadow

    def _reclaim_entry(self, s: TrackedSignal, price: float, now_ms: int) -> Optional[TrackedSignal]:
        """
        eng-104, the reclaim entry of a liquidity sweep (the owner's comparison with a signal channel 2026-10-14: BTC /
        ETH sweeps of the day high found by the bot at 08:15 UTC were sold there at once, while our card waited for a
        lower-timeframe shift and expired with the kill zone): an entry at the price right after the sweep candle closed
        back inside, the stop beyond the sweep's extreme + the coin's measured pierce (the plan's own stop), the targets
        of the plan. Journaled beside the method's trigger as vetoed 'reclaim_entry' (never traded), once per card,
        only while the price is still within half the way from the swept level to the stop.
        """
        if s.mode != 'sweep' or not s.group_key.startswith('SWEEP') or s.sig.get('_reclaim_done') or not s.plan:
            return None
        level, extreme = s.sig.get('anchor_level'), s.sig.get('anchor_extreme')
        if level is None or extreme is None:
            return None
        s.sig['_reclaim_done'] = True
        d = s.direction
        # inside the sweep's extreme (a price back at / above the swept high is a better short, not a miss) and not
        # run away from the level by more than half the sweep's depth (ETH 2026-10-14: 2522.06 vs the level 2521.89)
        if d * (price - extreme) <= 0 or d * (price - level) > 0.5 * abs(level - extreme) + 1e-12 * price:
            return None
        levels = entry_levels(s.plan, price, extreme, d)
        if not levels or d * (price - levels['sl']) <= 0 or d * (levels['tp1'] - price) <= 0:
            return None
        levels['zone_src'] = 'reclaim of the swept level'
        levels['range_pos'] = range_position(s.plan.get('dealing_range'), levels['entry'], d)
        shadow = copy.copy(s)
        shadow.levels, shadow.entered_at, shadow.vetoed = levels, now_ms / 1000, 'reclaim_entry'
        shadow.of_confirm, shadow.confirms = None, {}
        return shadow

    def _against_day(self, s: TrackedSignal, at_ms: int) -> Optional[str]:
        """
        eng-58: one direction per coin a day (ICT trades the day's bias with every model; a long and a short of two
        strategies on one coin were one coin flip): the first entry of the UTC day sets it, an opposite entry is
        journaled 'against_day'. The Turtles (a multi-week system) are exempt.
        """
        if (s.plan or {}).get('trail_days'):
            return None
        d = self.day_dir.get((s.symbol, int(at_ms // 86_400_000)))
        if d is not None and d != s.direction:
            return 'against_day'
        # eng-59, ICT: altcoins' ICT models trade with BTC's bias (weekly, else daily) - the market's draw
        # eng-100: 'against_btc' removed - BTC's direction now sets the trade's risk (the 7-day momentum regime,
        # executor), not a veto
        return None

    def _entry_minute(self, s: TrackedSignal, c, entry_ms: int, now: float, channel=None, band=None):
        """
        Audit A02: the extremes of the entry minute AFTER the entry. (open, high, low) from the trades since the entry;
        the 1m candle's own when its range touched no stop / target / exit level (nothing to decide); None while the
        minute's trades are still arriving; False when the range touched a level and no complete trade record tells
        whether before or after the entry: 'ambiguous', not judged (no invented fill), the pessimistic stop R kept
        apart in r_low.
        """
        lv, d, entry = s.levels, s.direction, s.levels['entry']
        end = int(c[0]) + MINUTE_MS
        got = self.tracked_of(s.symbol, entry_ms, end) if self.tracked_of else None
        if got is not None and got.get('pending'):
            if now * 1000 - end < 10_000:
                return None
            got = None                       # no trade after the minute within 10 s: the record cannot be closed
        if got is not None:
            if self.untrack:
                self.untrack(s.symbol, entry_ms)
            s.entry_min = 'trades'
            hi = got['hi'] if got['hi'] is not None else entry
            lo = got['lo'] if got['lo'] is not None else entry
            return entry, max(hi, entry), min(lo, entry)
        if self.untrack:
            self.untrack(s.symbol, entry_ms)
        hi, lo = float(c[2]), float(c[3])
        plan = s.plan or {}
        stop_hit = not plan.get('no_stop') and ((lo <= lv['sl']) if d > 0 else (hi >= lv['sl']))
        levels = [] if plan.get('no_tp') else [lv[f'tp{k}'] for k in (1, 2, 3) if lv.get(f'tp{k}') is not None]
        target_hit = any((hi >= t) if d > 0 else (lo <= t) for t in levels)
        # audit EXTRA_2: the Turtles' channel / Bollinger's opposite band are exit levels too - a minute that touched
        # one cannot be called clean without the trades (the low may have printed before the entry)
        exit_hit = (channel is not None and ((lo < channel) if d > 0 else (hi > channel))) or \
                   (band is not None and ((hi >= band) if d > 0 else (lo <= band)))
        if not stop_hit and not target_hit and not exit_hit:
            s.entry_min = 'clean'
            return float(c[1]), hi, lo
        s.entry_min = 'ambiguous'
        if stop_hit:
            risk = lv.get('risk0') or abs(entry - lv['sl'])
            if risk:
                s.r_low = d * (lv['sl'] - entry) / risk - self._cost_r(s, risk, end)
        return False

    GAP_WAIT_MS = 5 * 60_000     # audit V04: how long a hole in the minutes holds the management for the patching

    def _manage_trade(self, s: TrackedSignal, price: float, now: float, candles_of=None):
        lv, d = s.levels, s.direction
        # eng-58: stops and targets on the final 1m candles' extremes since the last check, as the journal's replay
        # does (the scan's last price missed every wick between scans); a target counts once traded
        # target_through_bps through it; a candle touching both counts the stop; a gap through the stop fills at the
        # candle's open
        through = CONFIG.levels.target_through_bps / 1e4
        if not s.managed_ms:
            # a trade restored from a state saved before eng-58: never judge it on candles before its entry
            s.managed_ms = int(((s.entered_at or 0) // 60 + 1) * 60_000)
        candles = [c for c in (list(candles_of(s.symbol)) if candles_of else []) if c[0] >= s.managed_ms]
        if version_no(s.logic_version) >= 141 and candles:
            # audit V04: a hole in the minutes (also right after the last managed minute) is UNKNOWN price action - a
            # bridge knows the two ends, not the hidden high / low. The trade waits at the hole while the minute
            # patching can still fill it; a hole that stays is crossed on the real minutes and the trade is flagged, its
            # result named as resting on missing data
            now_ms, expected = int(now * 1000), int(s.managed_ms)
            for i, c in enumerate(candles):
                if int(c[0]) > expected:
                    if now_ms - int(c[0]) < self.GAP_WAIT_MS:
                        candles = candles[:i]           # judged once the hole is patched (or given up)
                        break
                    gaps = (s.plan or {}).setdefault('data_gaps', []) if s.plan is not None else []
                    if [expected, int(c[0])] not in gaps:
                        gaps.append([expected, int(c[0])])
                        logger.warning(f"{s.symbol} {s.group_key}: minutes {time.strftime('%H:%M', time.gmtime(expected / 1000))}"
                                       f"-{time.strftime('%H:%M', time.gmtime(int(c[0]) / 1000))} UTC missing: the trade "
                                       f"is managed across the hole, its hidden extremes unknown")
                expected = int(c[0]) + MINUTE_MS
        # audit 2026-10-18 P0 (replaces eng-141's B09 bridge candle): a hole is crossed on the real minutes only. A level
        # between the close before the hole and the open after it lies beyond that open, so the next real minute catches
        # it (the stop is checked before targets) and fills at its observed open; the made-up bridge bar opened at the
        # old close and credited the stop price itself (long SL 99, 100 -> hole -> 95 filled at 99, not 95). The fill
        # is still an estimate: the hole is flagged in plan['data_gaps'] and named in the finish reason
        # audit A08: the exit levels that are price conditions (the Turtles' N-day channel, Bollinger's opposite band)
        # are checked on every final 1m candle's extremes like the stop - the scan price missed the wicks between scans.
        # Each minute is judged on the levels known at its OPEN (review of 6b771ba): only the days / 4h bars closed by
        # then, re-read when a day / 4h boundary is crossed, so a later bar never decides an earlier minute
        days = (s.plan or {}).get('trail_days')
        band_on = bool((s.plan or {}).get('band_exit') and self.band_of)
        d1_all = list(self.daily_of(s.symbol) or []) if candles and days and self.daily_of else []
        channel_at = band_at = None
        channel = band = None
        entry_ms = int((s.entered_at or 0) * 1000)
        for c in candles:
            o, hi, lo = float(c[1]), float(c[2]), float(c[3])
            if d1_all and channel_at != int(c[0]) // DAY_MS:
                from strategies.turtle import trail_level
                channel_at = int(c[0]) // DAY_MS
                channel = trail_level([b for b in d1_all if int(b[0]) + DAY_MS <= int(c[0])], days, d)
            if band_on and band_at != int(c[0]) // (4 * HOUR_MS):
                band_at = int(c[0]) // (4 * HOUR_MS)
                band = self.band_of(s.symbol, d, int(c[0]))
            if int(c[0]) <= entry_ms < int(c[0]) + MINUTE_MS:
                # audit A02: the entry minute - its 1m high / low may have traded before the entry
                first = self._entry_minute(s, c, entry_ms, now, channel, band)
                if first is None:
                    break                        # its trades are not all in yet: judged on the next scan
                if first is False:
                    s.managed_ms = int(c[0]) + MINUTE_MS
                    continue                     # not judged (ambiguous): from the next minute on
                o, hi, lo = first
            # audit C07: an exit by time that fell due before this minute opened ends the trade at the due minute's
            # close - a later stop in the catch-up buffer (after an outage) must not pre-empt it
            why_t, due_t = self._time_exit(s, int(c[0]) / 1000)
            if why_t and due_t is not None and s.entered_at and int(c[0]) > entry_ms:
                mark = next((m[4] for m in reversed(list(candles_of(s.symbol))) if m[0] / 1000 + 60 <= due_t), None)
                if mark is not None:
                    s.exit_fill = float(mark)
                    s.last_price = float(mark)
                    why_t += f" (due {time.strftime('%H:%M', time.gmtime(due_t))} UTC, marked at that minute's close)"
                    return self._finish(s, 'CLOSED', due_t, why_t)
            s.managed_ms = int(c[0]) + MINUTE_MS
            stop_hit = not (s.plan or {}).get('no_stop') and ((lo <= lv['sl']) if d > 0 else (hi >= lv['sl']))
            chan_hit = channel is not None and ((lo < channel) if d > 0 else (hi > channel))
            # audit C06: both against the position - the level nearer the open is crossed first (a channel above a
            # long's stop closes it at the channel before the stop is reached)
            if stop_hit and not (chan_hit and d * (channel - lv['sl']) > 0):
                s.exit_fill = min(o, lv['sl']) if d > 0 else max(o, lv['sl'])
                return self._finish(s, 'SL', now, f"stop {lv['sl']:.6g} hit" + (f" after TP{s.best_target}" if s.best_target else ''))
            # Faith: out when the price went BEYOND the N-day low / high (a gap through it fills at the open)
            if chan_hit:
                s.exit_fill = min(o, channel) if d > 0 else max(o, channel)
                return self._finish(s, 'CLOSED', now, f"exit on the {days}-day {'low' if d > 0 else 'high'} "
                                                      f"{channel:.6g} (Turtles)")
            if band is not None and ((hi >= band) if d > 0 else (lo <= band)):
                s.exit_fill = max(o, band) if d > 0 else min(o, band)
                return self._finish(s, 'CLOSED', now, f"the opposite Bollinger band {band:.6g} reached (Bollinger)")
            # audit S10: a plan without targets (no_tp: Turtles, Connors, SAR) never books a TP from its placeholders
            for k in (() if (s.plan or {}).get('no_tp') else (1,) if (s.plan or {}).get('trail_after_tp1') else (3, 2, 1)):
                t = lv[f'tp{k}']
                if k > s.best_target and ((hi >= t * (1 + through)) if d > 0 else (lo <= t * (1 - through))):
                    for j in range(1, k + 1):
                        s.part_ms.setdefault(f'tp{j}', int(c[0]) + MINUTE_MS)
                    s.best_target = k
                    if k < 3:
                        self.events.append((s, f'TP{k}'))
                    break
            if s.best_target == 3:
                return self._finish(s, 'TP3', now, f"TP3 {lv['tp3']:.6g} reached")
            # audit C05: the trail sees the minutes up to THIS candle only - a catch-up pass over several minutes gave
            # the EMA / SAR the later candles of the buffer and moved the stop on data that did not exist yet
            upto = int(c[0])
            self._trail(s, (lambda sym, _t=upto: [m for m in candles_of(sym) if m[0] <= _t]) if candles_of else None,
                        hi, lo)
            self._profile_manage(s, hi, lo)
            why = self._overlay_exit(s, c, candles_of)
            if why:
                s.exit_fill = float(c[4])
                return self._finish(s, 'CLOSED', now, why)
        # Connors (no_stop): 'sl' only sizes R, the trade ends on its own exit rule - the scan price must not stop it
        if not (s.plan or {}).get('no_stop') and d * (price - lv['sl']) <= 0:
            s.exit_fill = price
            return self._finish(s, 'SL', now, f"stop {lv['sl']:.6g} hit" + (f" after TP{s.best_target}" if s.best_target else ''))
        if s.best_target == 3:
            return self._finish(s, 'TP3', now, f"TP3 {lv['tp3']:.6g} reached")
        if s.best_target:
            s.status = f"TP{s.best_target}"
        if (s.plan or {}).get('add_half') and len(s.units) == 1:
            add_at = lv['entry'] - d * 0.5 * (lv.get('risk0') or abs(lv['entry'] - lv['sl']))
            if d * (price - add_at) <= 0:
                s.units.append([add_at, now])
                self.events.append((s, 'ADD'))
        n = (s.plan or {}).get('turtle_n')
        if n and s.units and len(s.units) < CONFIG.strategies.turtle_max_units and \
                d * (price - s.units[-1][0]) >= CONFIG.strategies.turtle_add_n * n:
            held = sum(len(o.units) for o in self.signals.values()
                       if not o.finished and o.units and o.direction == d)
            if held < CONFIG.strategies.turtle_max_direction_units:
                # the Turtles' pyramid: one more unit every 1/2 N in the trade's favour, the stop of ALL units moved
                # to 2N from the newest one. Faith: the 1/2 N interval is measured from the ACTUAL fill of the previous
                # unit (a unit that slipped moves the next one further out) - the unit is booked at the price it was
                # added at, not at the theoretical 1/2 N step
                add_at = price
                s.units.append([add_at, now])
                lv['sl'] = add_at - d * 2 * n
                lv['sl_src'] = f"2N from unit {len(s.units)} (Turtles)"
                self.events.append((s, 'ADD'))
        if (s.plan or {}).get('connors_exit') and self.daily_of:
            d1 = self.daily_of(s.symbol) or []
            # the daily closes since the entry: out on the first one beyond the SMA5 of the last five closes
            if len(d1) >= 5 and d1[-1][0] / 1000 >= s.entered_at - 86400:
                sma5 = sum(c[4] for c in d1[-5:]) / 5
                if d1[-1][0] / 1000 + 86400 > s.entered_at and d * (d1[-1][4] - sma5) > 0:
                    return self._finish(s, 'CLOSED', now, f"daily close {d1[-1][4]:.6g} beyond the SMA5 {sma5:.6g} "
                                                          f"(Connors exit)")
        if (s.plan or {}).get('band_exit') and self.band_of:
            # Bollinger W / M (eng-55): out when price reaches the opposite band as it stands now
            band = self.band_of(s.symbol, d)
            if band is not None and d * (price - band) >= 0:
                s.exit_fill = price
                return self._finish(s, 'CLOSED', now, f"the opposite Bollinger band {band:.6g} reached (Bollinger)")
        days = (s.plan or {}).get('trail_days')
        if days and self.daily_of:
            from strategies.turtle import trail_level
            level = trail_level(self.daily_of(s.symbol) or [], days, d)
            # Faith: exited when the price went BEYOND the N-day low / high (a breakout against the position), not on
            # touching it
            if level is not None and d * (price - level) < 0:
                s.exit_fill = price
                return self._finish(s, 'CLOSED', now, f"exit on the {days}-day {'low' if d > 0 else 'high'} "
                                                      f"{level:.6g} (Turtles)")
        if self._macro_guard(s, price, now):
            return
        why, due = self._time_exit(s, now)
        if why:
            if due is not None and now - due > 2 * 60 and candles_of:
                # the exit fell due while the bot had no data (a feed / internet outage): marked at the close of the
                # minute it was due, not at the price on reconnect hours later
                mark = next((c[4] for c in reversed(list(candles_of(s.symbol))) if c[0] / 1000 + 60 <= due), None)
                if mark is not None:
                    s.last_price = mark
                    why += f" (due {time.strftime('%H:%M', time.gmtime(due))} UTC, marked at that minute's close)"
                    return self._finish(s, 'CLOSED', due, why)
            self._finish(s, 'CLOSED', now, why)

    TF_SEC = {'5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400}

    def _macro_guard(self, s: TrackedSignal, price: float, now: float) -> bool:
        """eng-100: macro_guard_min before a high-impact US release (macro_calendar.upcoming) an intraday trade in profit
        gets its stop at break-even + costs, one flat or in loss is closed at market (True). Multi-day systems keep
        their exits."""
        plan = s.plan or {}
        if plan.get('trail_days') or plan.get('connors_exit') or not s.levels or not price \
                or not CONFIG.levels.macro_guard_min:
            return False
        from macro_calendar import upcoming
        ev = upcoming(now * 1000, CONFIG.levels.macro_guard_min * 60_000)
        if ev is None or plan.get('macro_guarded') == ev[0]:
            return False
        plan['macro_guarded'] = ev[0]
        s.plan = plan
        lv, d = s.levels, s.direction
        be = lv['entry'] * (1 + d * BE_COST)
        name = ev[1]
        if d * (price - be) > 0:
            if d * (be - lv['sl']) > 0:
                lv['sl'], lv['sl_src'] = be, f'break-even + costs before {name}'
                self.events.append((s, 'RESTOP'))
            return False
        self._finish(s, 'CLOSED', now, f"closed at market before {name} (in loss / flat): macro_guard")
        return True

    # the owner's live journal (eng-141..144: 6 of 6 longs stopped; earlier 31 of 36): no long while BTC AND the alt
    # market (the universe's median) both fell over the last 24h (eng-146: 24h only). The Turtles' rules are not changed and
    # Connors buys the dip by design: both exempt. Blocking (not shadow); journaled as vetoed 'market_down'
    MARKET_DOWN_EXEMPT = ('BREAKOUT UP', 'RSI2 LONG', 'RSI2X LONG')    # the Turtles and Connors (not BB1)
    # eng-148 (audit): a reversal long is bought INTO weakness by design - market_down is a shadow veto for these
    # (journaled in shadow_veto), blocking only impulse / breakout / trend longs
    MARKET_DOWN_SHADOW = ('SWEEP LOW', 'SILVER BULLET LONG', 'SPRING', 'FLUSH REVERSAL', 'SD DEMAND', 'VA80 LONG',
                          'AUCTION LONG', 'BB W-BOTTOM')

    def _market_down(self, s: TrackedSignal) -> bool:
        if s.direction <= 0 or s.group_key in self.MARKET_DOWN_EXEMPT or self.market_state_of is None:
            return False
        m = self.market_state_of() or {}
        # eng-146: the 24h moves only - requiring the 4h ones too let every 4h bounce inside a falling day through
        vals = [m.get(k) for k in ('btc_1d', 'mkt_1d')]
        return all(v is not None for v in vals) and all(v < 0 for v in vals)

    def crowded(self, mode: str, direction: int, now: float) -> bool:
        """eng-51: crowd_max open trades in this direction across all strategies (Turtles' correlated-markets limit)."""
        # eng-144: Turtle / Connors cards count and are capped too (Faith: a limit on closely correlated markets;
        # live 11-21.10 Turtle 10 trades -11.6R, 0 winners, entered together; crowded signals -0.22R vs clean +0.01R)
        if CONFIG.strategies.crowd_max <= 0:
            return False                 # eng-148, the owner: no position-count limit on the demo account
        n = sum(1 for o in self.signals.values() if o.entered_at and not o.finished and o.direction == direction)
        return n >= CONFIG.strategies.crowd_max

    def _time_exit(self, s: TrackedSignal, now: float) -> Tuple[Optional[str], Optional[float]]:
        """Why the trade ends by time now (eng-47, Strategy.time_exit) and the time it fell due; (None, None) = it runs."""
        strategy = self.strategy(s)
        held = now - s.entered_at
        pm = (s.plan or {}).get('pm')

        def by(limit: float, text: str):
            return (text, s.entered_at + limit) if held > limit else (None, None)
        if CONFIG.strategies.structural_lifetimes and not (pm and pm.get('hours')) and \
                getattr(strategy, 'time_exit', 'bars') != 'session':
            # eng-108: no invented clock - the trade ends by its stop, targets, break-even / trail and the method's own
            # exit (band, SMA5, session, channel); a measured profile's time stop and a session's close stay
            return None, None
        if pm and pm.get('hours'):
            # an optimized profile's time stop (research_optimize.py), replacing the method's own clock
            limit = float(pm['hours']) * 3600
            return by(limit, f"profile time stop: {_dur(limit)}: closed at market")
        if strategy is None:
            ttl = CONFIG.levels.trade_ttl_sec
            return by(ttl, f"trade open {_dur(ttl)}: closed at market")
        cap = strategy.ttls(self._tf(s))[2]
        mode = getattr(strategy, 'time_exit', 'bars')
        if mode == 'session':
            # eng-93: a card that knows its own session's close (the session ORB) ends there
            end_ms = (s.sig or {}).get('session_end_ms')
            end = end_ms / 1000 if end_ms else strategy.session_end(s.entered_at)
            if end is not None:
                # the session's end IS the method's exit: a shorter cap closed ORB / VA80 days before it (ZEC
                # 2026-10-06: entered 01:03 UTC, the 12h cap fired at 13:03, the session ended 00:00)
                return ("the method's session ended: closed at market", end) if now >= end else (None, None)
            return by(cap, f"trade open {_dur(cap)}: closed at market")
        if mode == 'fixed':
            return by(cap, f"trade open {_dur(cap)}: closed at market")
        cfg = CONFIG.strategies
        tf = self._tf(s)
        limit = max(cfg.time_stop_bars * self.TF_SEC.get(tf, 900), cfg.time_stop_min_sec)
        if not s.best_target:
            return by(limit, f"time stop: no TP1 within {cfg.time_stop_bars} {tf} bars ({_dur(limit)}): closed at market")
        limit *= cfg.time_after_tp1
        return by(limit, f"time stop after TP1: open {_dur(limit)}: closed at market")

    # ------------------------------------------------------------------ views

    def signals_view(self, now: float) -> List[TrackedSignal]:
        """
        Open signals by actionability - in a trade, in the zone, watching (closest to the zone first), direction
        only - followed by signals finished within finished_display_sec.
        """
        def rank(s: TrackedSignal):
            if s.entered_at:
                return (0, -s.entered_at)
            if s.status == 'ZONE':
                return (1, -s.created)
            if s.status == 'WATCH' and s.plan and s.last_price:
                edge = s.plan['zone_hi'] if s.direction > 0 else s.plan['zone_lo']
                return (2, abs(edge / s.last_price - 1))
            return (3, -s.created)

        items = list(self.signals.values())
        open_ = sorted((s for s in items if not s.finished), key=rank)
        done = sorted((s for s in items if s.finished and s.status != DROPPED
                       and now - s.finished_at < CONFIG.levels.finished_display_sec),
                      key=lambda s: -s.finished_at)
        return open_ + done

    def anomalies_view(self) -> List[AnomalyEntry]:
        return sorted(self.anomalies.values(), key=lambda a: -a.last_seen)

    def hot_symbols(self) -> Dict[str, int]:
        """Symbols that deserve order-book data, with a priority (0 = in a trade, 1 = in the zone, 2 = watching)."""
        out: Dict[str, int] = {}
        for s in self.signals.values():
            if s.finished:
                continue
            priority = 0 if s.entered_at else 1 if s.status == 'ZONE' else 2
            out[s.symbol] = min(priority, out.get(s.symbol, 9))
        return out

    def zone_symbols(self) -> Dict[str, float]:
        """
        Symbols waiting for an entry -> their 15m ATR (footprint bucket sizing). From the card's creation, not only
        once in the zone: a footprint started at the zone had seconds of data when the first trigger came.
        """
        return {s.symbol: s.plan['atr'] for s in self.signals.values()
                if not s.finished and not s.entered_at and s.plan and s.plan.get('atr')}

    # ------------------------------------------------------------------ persistence

    def state(self) -> Dict:
        """Open cards and session counters (plans are recomputed from the frames after a restart)."""
        cards = []
        for s in self.signals.values():
            if s.finished:
                continue
            d = asdict(s)
            # a waiting card's plan is recomputed from the frames; an ENTERED trade's is not (the entry froze it), so
            # its exit-relevant fields are kept (eng-55: lost on every restart before - the Turtles' channel exit and
            # pyramid, Connors' SMA5 exit, no_tp ... ran on the stop and the time cap only)
            d['plan'] = {k: v for k, v in s.plan.items() if k != 'zones' and _jsonable(v)} \
                if s.entered_at and s.plan else None
            d['sig'] = {k: v for k, v in s.sig.items() if isinstance(v, (int, float, str, bool, list, type(None)))}
            cards.append(d)
        legs = [[sym, d, list(key), at] for (sym, d), (key, at) in self.finished_legs.items()]
        return {'cards': cards, 'session_results': dict(self.session_results), 'session_r': self.session_r,
                'finished_legs': legs}

    def load_state(self, state: Dict, now: float):
        for d in (state or {}).get('cards', []):
            try:
                s = TrackedSignal(**d)
            except TypeError:
                continue
            strategy = strategy_of(s.group_key)
            if strategy is None:
                continue
            # A card saved by an older logic without its anchor cannot be planned any more
            if not s.entered_at and strategy.anchor_type == 'level' and 'anchor_level' not in s.sig:
                continue
            if not s.entered_at and strategy.anchor_type == 'range' and 'range_hi' not in s.sig:
                continue
            # The strategy's longest lifetimes (a leg strategy's card may have had a 4h leg)
            watch_ttl, _, trade_ttl = strategy.ttls('4h')
            if not s.entered_at and now - s.created > watch_ttl and not CONFIG.strategies.structural_lifetimes:
                continue
            # eng-103: an OPEN trade is always restored - dropped here it vanished without a card row or a result (BAT
            # Turtles 2026-10-13); past its lifetime the next scan closes it through _manage_trade and journals it
            s.mode = strategy.name
            if s.status == 'ZONE' and strategy.frozen_in_zone:
                s.status = 'WATCH'  # the frozen plan was not saved: re-measure
                s.zone_since_ms = None
            # A restored card is not at its confirmation any more: no entry at a price from before the restart
            s.confirm_checked = True
            if s.entered_at and not s.plan:
                s.plan = _exit_flags(s)          # a trade saved before eng-55 kept no plan
            self.signals[(s.symbol, s.group_key)] = s
        for item in (state or {}).get('finished_legs', []):
            if len(item) == 4 and isinstance(item[2], list):
                sym, d, key, at = item
                if now - at < FINISHED_LEG_MEMORY_SEC:
                    self.finished_legs[(sym, d)] = (tuple(key), at)
        self.session_results.update((state or {}).get('session_results', {}))
        self.session_r.extend((state or {}).get('session_r', []))
