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
from strategies.ict import fvg_trigger, range_position, touch_trigger
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from config import CONFIG
from journal import classify, veto_reason
from levels import MINUTE_MS, ltf_trigger, pullback_volume_ok, resample
from strategies.maniac import ifvg_trigger, in_session, pinbar_trigger
from strategies.maniac_strategies import MANIAC_STRATEGIES

MANIAC_NAMES = frozenset(s.name for s in MANIAC_STRATEGIES)
from strategies import PlanInput, Strategy, strategy_of
from strategies import confirm
from strategies.geometry import entry_levels

logger = logging.getLogger(__name__)

FINAL_STATUSES = {'TP3', 'SL', 'CLOSED', 'INVALID', 'MISSED', 'EXPIRED'}
# A setup that never became a card (no anchor / no room left to a target): removed, not a result
DROPPED = 'DROPPED'
# How long a finished card's anchor blocks a new card on it
FINISHED_LEG_MEMORY_SEC = 24 * 3600
# Structure timeframes by rank: an opposite setup closes a card only from the same or a higher timeframe
TF_RANK = {'1m': 0, '5m': 1, '15m': 2, '1h': 3, '4h': 4}
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


def _dur(sec: float) -> str:
    """600 -> '10m', 7200 -> '2h' (reasons are parsed by the dashboard)."""
    return f"{int(sec // 3600)}h" if sec >= 3600 and sec % 3600 == 0 else f"{int(sec // 60)}m"


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
    levels: Optional[Dict[str, float]] = None
    entered_at: Optional[float] = None
    best_target: int = 0
    finished_at: Optional[float] = None
    final_r: Optional[float] = None
    vetoed: Optional[str] = None
    of_confirm: Optional[str] = None
    confirms: dict = field(default_factory=dict)
    vetoed_triggers: int = 0
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
        self.daily_of: Optional[Callable[[str], Optional[list]]] = None     # closed daily candles (Turtle exits)
        self.context_of: Optional[Callable[[str], Optional[object]]] = None
        # symbol -> hashable key of everything a plan depends on (None: always recompute); plans cached per card
        self.plan_key_of: Optional[Callable[[str], Optional[tuple]]] = None
        # symbol -> True once its 1h history and level map are loaded (a plan without them misses 1h / 4h legs)
        self.map_ready_of: Optional[Callable[[str], bool]] = None
        self._plan_cache: Dict[Tuple[str, str], Tuple[tuple, Optional[Dict]]] = {}
        self._skip_reason: Dict[Tuple[str, str], str] = {}
        # (symbol, setup) -> (plan key, gate result): a phase setup repeats on every scan of its candle
        self._gate_cache: Dict[Tuple[str, str], Tuple[tuple, Optional[str]]] = {}
        self._candles_of: Callable[[str], Sequence[Sequence[float]]] = lambda symbol: []
        # (symbol, direction) -> last time the coin produced a directional setup (market-move clusters)
        self._recent_setups: Dict[Tuple[str, int], float] = {}
        # (symbol, direction) -> (anchor key, finished_at) of the last finished card
        self.finished_legs: Dict[Tuple[str, int], Tuple[tuple, float]] = {}

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
        self.events = []
        self.finished_now = []

        candidates = []
        directional: List[Tuple[int, Dict]] = []
        for symbol, sig in signals:
            kind, group_key, direction = classify(sig)
            key = (symbol, group_key)
            strategy = strategy_of(group_key)
            if strategy is not None:
                self._recent_setups[(symbol, direction)] = now
                directional.append((direction, sig))
                reason = veto_reason(group_key, sig) or strategy.context_veto(sig, direction)
                if reason is None and not strategy.has_data(sig):
                    reason = 'no_data'
                if reason is None and (not strategy.enabled or group_key in CONFIG.strategies.disabled_setups):
                    reason = 'disabled'
                pool_of = getattr(self, 'pool_of', None)
                if reason is None and pool_of is not None and not pool_of(strategy.name, symbol):
                    reason = 'not_in_pool'
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
        for symbol, group_key, strategy, direction, sig, price in candidates:
            tracked = TrackedSignal(
                symbol=symbol, group_key=group_key, direction=direction, mode=strategy.name,
                created=now, price_at_signal=price, sig=sig, last_seen=now, last_price=price,
            )
            self.signals[(symbol, group_key)] = tracked
            created.append(tracked)

        entries: List[TrackedSignal] = []
        for tracked in self.signals.values():
            if tracked.finished:
                continue
            price = price_of(tracked.symbol)
            if not price:
                continue
            result = self._advance(tracked, price, now, frames, candles_of, confirm_of)
            if result is not None:
                entries.append(result)

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
                         context=self.context_of(symbol) if self.context_of else None, reached=reached)

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
        s.finish_reason, s.finish_price = reason or status, s.last_price
        self.finished_now.append(s)
        label = f"SL after TP{s.best_target}" if status == 'SL' and s.best_target else status
        self.session_results[label] += 1
        if s.entered_at and s.r_now is not None:
            s.final_r = s.r_now
            self.session_r.append(s.r_now)
        if status in ('SL', 'TP3'):
            self.events.append((s, status))

    def _invalid_reason(self, s: TrackedSignal, price: float, invalid: float) -> str:
        anchor = (s.plan or {}).get('anchor') or {}
        if anchor.get('type') == 'leg' and not s.plan.get('fix_invalid'):
            return "the pullback erased the whole impulse"
        if anchor.get('type') == 'leg':
            return f"price {price:.6g} beyond the reversed leg's end {anchor['end']:.6g} and its stop pool ({invalid:.6g})"
        if anchor.get('type') == 'level':
            return f"price {price:.6g} beyond the extreme {anchor['extreme']:.6g} at {anchor.get('label') or 'the level'} ({invalid:.6g})"
        return f"price {price:.6g} back inside the range past its middle ({invalid:.6g})"

    def _advance(self, s: TrackedSignal, price: float, now: float, frames, candles_of,
                 confirm_of: Optional[ConfirmCheck]) -> Optional[TrackedSignal]:
        """Move one signal along its lifecycle; returns the entry (possibly a vetoed copy) when a trigger fired."""
        cfg = CONFIG.levels
        s.last_price = price
        if s.entered_at:
            self._manage_trade(s, price, now)
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
        watch_ttl, zone_ttl, _ = strategy.ttls(self._tf(s))
        plan = s.plan
        if plan is None or not plan['targets']:
            s.status = 'BIAS'
            if age > watch_ttl:
                self._finish(s, 'EXPIRED', now, f"the leg stopped qualifying and did not return for {_dur(watch_ttl)}")
            return None

        invalid = s.invalid_price if s.invalid_price is not None else plan.get('invalid')
        check = price
        if invalid is not None and plan.get('invalid_close_min'):
            # the system invalidates on a CLOSE beyond (a wick through is allowed): the last final candle of that tf
            check = self._last_close(s.symbol, candles_of, plan['invalid_close_min'])
        if invalid is not None and check is not None and d * (check - invalid) <= 0:
            self._finish(s, 'INVALID', now, self._invalid_reason(s, price, invalid))
            return None
        tp1 = plan['targets'][0]
        if plan.get('missable') and d * (price - tp1) >= 0:
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
        near_edge = plan['zone_hi'] if d > 0 else plan['zone_lo']
        in_zone = d * (price - near_edge) <= 0
        if s.status != 'ZONE' and in_zone:
            s.status, s.zone_since_ms = 'ZONE', now_ms // 60_000 * 60_000
            self.events.append((s, 'ZONE'))
        elif s.status != 'ZONE':
            s.status = 'WATCH'

        if s.status == 'ZONE':
            entry = self._try_entry(s, price, now_ms, candles_of, confirm_of)
            if entry is not None:
                return entry
            if now_ms - s.zone_since_ms > zone_ttl * 1000:
                self._finish(s, 'EXPIRED', now, f"no valid {plan['trigger_minutes']}m trigger in the zone "
                             f"for {_dur(zone_ttl)}" + (f" ({s.vetoed_triggers} vetoed)" if s.vetoed_triggers else ''))
        elif age > watch_ttl:
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
        ltf = resample(minutes, trigger_minutes, minutes[-1][0] + MINUTE_MS)
        kind = s.plan.get('trigger', 'shift')
        if kind == 'pinbar':
            trigger = pinbar_trigger(ltf, d, s.zone_since_ms, interval_ms, s.plan['zone_lo'], s.plan['zone_hi'])
        elif kind == 'fvg':
            trigger = fvg_trigger(ltf, d, s.zone_since_ms, interval_ms)
        elif kind == 'touch':
            trigger = touch_trigger(ltf, d, s.zone_since_ms, interval_ms, s.plan['zone_lo'], s.plan['zone_hi'])
        elif kind == 'ifvg':
            trigger = ifvg_trigger(ltf, d, int(s.plan.get('trigger_from_ms') or s.zone_since_ms), s.zone_since_ms,
                                   interval_ms)
        else:
            trigger = ltf_trigger(ltf, d, s.zone_since_ms, interval_ms)
        if not trigger:
            return None
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
        # the spring candle's average FUTURES minute (the pullback minutes are futures candles); a card restored from
        # an older state has only the spot figure: no test rather than a test in the wrong units
        spring_minute = s.sig.get('fut_candle_minute_usd')
        if spring_minute is None and not s.sig.get('has_spot'):
            spring_minute = s.sig.get('candle_minute_usd')
        if s.group_key in ('BULL B', 'SPRING', 'UTAD', 'FLUSH REVERSAL', 'SQUEEZE REVERSAL') and not pullback_volume_ok(minutes, s.zone_since_ms, trigger['time'],
                                                             spring_minute or 0.0):
            reason = 'no_spring_test'
        confirms = confirm_of(s.symbol, s.mode, d, s.zone_since_ms, trigger['time'], trigger.get('extreme_time')) \
            if confirm_of else {}
        if s.mode == 'sweep' and confirms is not None:
            # ICT's own confirmations of a sweep (eng-35): SMT divergence against the correlate, the entry in a kill zone
            if s.sig.get('smt_div') is not None:
                confirms['smt'] = bool(s.sig['smt_div'])
            if CONFIG.strategies.smt_session:
                confirms['killzone'] = in_session(trigger['time'], tuple(CONFIG.strategies.smt_session))
        if reason is None:
            reason = confirm.missing(s.mode, confirms)
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

    @staticmethod
    def _last_close(symbol: str, candles_of, minutes_tf: int) -> Optional[float]:
        """Close of the last FINAL candle of `minutes_tf` minutes (from the final 1m candles), None without data."""
        minutes = list(candles_of(symbol)) if candles_of else []
        if not minutes:
            return None
        bars = resample(minutes, minutes_tf, minutes[-1][0] + MINUTE_MS)
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
        reason = confirm.missing(s.mode, confirms)
        if reason is None and CONFIG.levels.veto_low_rr and levels.get('low_rr'):
            reason = 'low_rr'
        return self._enter(s, levels, now_ms, reason, confirms)

    def _enter(self, s: TrackedSignal, levels: Dict, now_ms: int, reason: Optional[str],
               confirms: Dict) -> TrackedSignal:
        """Enter, or journal the entry that would have been taken with the veto reason (the card keeps waiting)."""
        entered_at = now_ms / 1000
        if reason is None:
            from macro_calendar import blackout
            if blackout(now_ms):
                reason = 'macro_event'
        of = confirms.get('orderflow') or None
        if reason:
            vetoed = copy.copy(s)
            vetoed.levels, vetoed.entered_at, vetoed.vetoed = levels, entered_at, reason
            vetoed.of_confirm, vetoed.confirms = of, dict(confirms)
            s.vetoed_triggers += 1
            if reason == 'low_rr' and levels.get('entry'):
                # A stop that far does not pay: the question is why the signal came here (entry vs the zone's edge)
                e = levels['entry']
                edge = (s.plan or {}).get('zone_lo' if s.direction > 0 else 'zone_hi')
                text = (f"low_rr: stop {abs(e - levels['sl']) / e:.2%} ({levels.get('sl_src')}), "
                        f"TP1 {abs(levels['tp1'] - e) / e:.2%} ({levels.get('tp1_src')})"
                        + (f", entry {abs(e - edge) / e:.2%} from the zone edge ({levels.get('zone_src')})"
                           if edge else ''))
                s.veto_notes = (s.veto_notes + [text])[-5:]
            s.veto_log.append(reason)
            return vetoed
        levels['risk0'] = abs(levels['entry'] - levels['sl'])
        if (s.plan or {}).get('trail_days'):
            # the Turtles' portfolio limit: at most turtle_max_direction_units units in one direction across all coins
            held = sum(len(o.units) for o in self.signals.values()
                       if o is not s and not o.finished and o.units and o.direction == s.direction)
            if held + 1 > CONFIG.strategies.turtle_max_direction_units:
                return self._enter(s, levels, now_ms, 'unit_limit', confirms)
            s.units = [[levels['entry'], entered_at]]
        s.levels, s.entered_at, s.status, s.of_confirm, s.confirms = levels, entered_at, 'ENTRY', of, dict(confirms)
        self.events.append((s, 'ENTRY'))
        return s

    def _manage_trade(self, s: TrackedSignal, price: float, now: float):
        lv, d = s.levels, s.direction
        if d * (price - lv['sl']) <= 0:
            return self._finish(s, 'SL', now, f"stop {lv['sl']:.6g} hit" + (f" after TP{s.best_target}" if s.best_target else ''))
        for k in (3, 2, 1):
            if k > s.best_target and d * (price - lv[f'tp{k}']) >= 0:
                s.best_target = k
                if k < 3:
                    self.events.append((s, f'TP{k}'))
                break
        if s.best_target == 3:
            return self._finish(s, 'TP3', now, f"TP3 {lv['tp3']:.6g} reached")
        if s.best_target:
            s.status = f"TP{s.best_target}"
        n = (s.plan or {}).get('turtle_n')
        if n and s.units and len(s.units) < CONFIG.strategies.turtle_max_units and \
                d * (price - s.units[-1][0]) >= CONFIG.strategies.turtle_add_n * n:
            held = sum(len(o.units) for o in self.signals.values()
                       if not o.finished and o.units and o.direction == d)
            if held < CONFIG.strategies.turtle_max_direction_units:
                # the Turtles' pyramid: one more unit every 1/2 N in the trade's favour, the stop of ALL units moved
                # to 2N from the newest one
                add_at = s.units[-1][0] + d * CONFIG.strategies.turtle_add_n * n
                s.units.append([add_at, now])
                lv['sl'] = add_at - d * 2 * n
                lv['sl_src'] = f"2N from unit {len(s.units)} (Turtles)"
                self.events.append((s, 'ADD'))
        days = (s.plan or {}).get('trail_days')
        if days and self.daily_of:
            from strategies.turtle import trail_level
            level = trail_level(self.daily_of(s.symbol) or [], days, d)
            if level is not None and d * (price - level) <= 0:
                return self._finish(s, 'CLOSED', now, f"exit on the {days}-day {'low' if d > 0 else 'high'} "
                                                      f"{level:.6g} (Turtles)")
        strategy = self.strategy(s)
        trade_ttl = strategy.ttls(self._tf(s))[2] if strategy else CONFIG.levels.trade_ttl_sec
        if now - s.entered_at > trade_ttl:
            self._finish(s, 'CLOSED', now, f"trade open {_dur(trade_ttl)}: closed at market")

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
            d['plan'] = None
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
            if now - (s.entered_at or s.created) > (trade_ttl if s.entered_at else watch_ttl):
                continue
            s.mode = strategy.name
            if s.status == 'ZONE' and strategy.frozen_in_zone:
                s.status = 'WATCH'  # the frozen plan was not saved: re-measure
                s.zone_since_ms = None
            # A restored card is not at its confirmation any more: no entry at a price from before the restart
            s.confirm_checked = True
            self.signals[(s.symbol, s.group_key)] = s
        for item in (state or {}).get('finished_legs', []):
            if len(item) == 4 and isinstance(item[2], list):
                sym, d, key, at = item
                if now - at < FINISHED_LEG_MEMORY_SEC:
                    self.finished_legs[(sym, d)] = (tuple(key), at)
        self.session_results.update((state or {}).get('session_results', {}))
        self.session_r.extend((state or {}).get('session_r', []))
