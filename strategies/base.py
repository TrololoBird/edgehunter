"""
The strategy interface. A strategy turns a setup (a detected event or a scored phase) into a PLAN, a dict:

    strategy, direction, anchor {type 'leg' | 'level' | 'range', tf, text, ...}
    tf, trigger_minutes          structure timeframe and the entry trigger's (3-6x finer)
    atr, recent_atr, leg_atr     15m ATR14, the last hour's 15m ATR (stop floor), the anchor's own ATR (stop buffer)
    entry                        'confirm' (enter at the confirmation, else wait in the zone) | 'pullback'
    zone_lo, zone_hi, zone_src   where the trigger is looked for once price is there
    invalid                      price beyond which the idea is wrong (None: none before the entry)
    fix_invalid                  the invalid price is fixed when the card starts (an extreme known at the confirmation)
    reset                        continuation: price beyond it = the leg extended -> back to waiting, re-measured
    missable                     MISSED when TP1 is reached before an entry
    stop_ref / stop_mid          the stop goes beyond stop_ref (and the trigger's swing) or sits at stop_mid
    targets, target_src          fixed at the card's start beyond `reached` (retarget: re-measured from the entry)
    intent, fillers, fill_label  target intent and the anchor's own fillers (fib / measured moves)
    zones                        merged level map (stop pools, targets)
    key                          the anchor's identity: a finished card blocks a new one on the same anchor
    impulse                      the leg (leg anchors) for the retracement read of the zone

Lifecycle and journal transport are shared; trade decisions belong to each
playbook contract and are dispatched by the owning Strategy instance.
"""
from dataclasses import dataclass, field
import math
from typing import Callable, Dict, List, Optional, Sequence, Tuple, TypedDict

import polars as pl

from config import CONFIG
from levels import TRIGGER_MINUTES, TTL_FACTOR  # noqa: F401  (TRIGGER_MINUTES re-exported for the strategies)


class CardLevels(TypedDict, total=False):
    """The executable level payload shared by lifecycle, executor and journal."""
    entry: float
    sl: float
    tp1: float
    tp2: float
    tp3: float
    rr_tp1: Optional[float]            # (TP1 - entry - costs) / (risk + costs); None for target-less systems
    rr_tp2: Optional[float]
    rr_blend: Optional[float]          # a third at each target
    low_rr: bool
    rr_reason: Optional[str]           # why the plan fails its R:R / cost / stop-distance rule
    risk_units: float                  # 1 = one risk unit (the Turtles' units > 1)
    risk0: float                       # the entry's risk, kept when the stop moves (R of a trailed trade)
    stop_pierce: Optional[float]
    sl_src: str
    tp1_src: str
    tp2_src: str
    tp3_src: str
    zone_src: str
    range_pos: Optional[float]
    limit_entry: Optional[float]
    volume_24h: Optional[float]
    geometry_source: str


def validate_card_levels(levels: Optional[CardLevels], direction: int) -> bool:
    """Fail-closed validation for executable stop/target geometry.

    Target-less contracts (Turtles, Connors, ORB) are valid when they provide a
    finite entry and stop; contracts that provide targets must keep every target
    on the trade side and in monotone order.  This check is deliberately small
    and side-effect free so all playbooks and the executor share the same rule.
    """
    if not levels or direction not in (-1, 1):
        return False
    try:
        entry = float(levels.get('entry'))
        stop = float(levels.get('sl'))
    except (TypeError, ValueError):
        return False
    if not all(math.isfinite(x) for x in (entry, stop)) or entry <= 0:
        return False
    if direction * (entry - stop) <= 0:
        return False
    targets = [levels.get(f'tp{k}') for k in (1, 2, 3)]
    if all(t is None for t in targets):
        return True
    if any(t is None for t in targets):
        return False
    try:
        values = [float(t) for t in targets]
    except (TypeError, ValueError):
        return False
    if not all(math.isfinite(t) and t > 0 for t in values):
        return False
    if any(direction * (t - entry) <= 0 for t in values):
        return False
    return all(direction * (values[i + 1] - values[i]) >= 0 for i in range(2))


def finalize_card_levels(plan: Dict, levels: Optional[CardLevels], direction: int) -> Optional[CardLevels]:
    """Run every playbook contract through the shared risk/geometry evaluator.

    Playbooks are allowed to choose their structural reference and target intent, but they are not allowed to
    choose a private definition of risk.  The lazy import keeps the strategy module graph acyclic while making
    ``entry_levels_for`` the single decision point for all contracts.
    """
    if not validate_card_levels(levels, direction):
        return None
    assert levels is not None
    try:
        entry = float(levels['entry'])
        stop = float(levels['sl'])
        risk = direction * (entry - stop)
    except (KeyError, TypeError, ValueError):
        return None
    if not math.isfinite(risk) or risk <= 0:
        return None

    from strategies.geometry import cost_of, finish_levels, stop_too_far

    fee = cost_of(entry, plan.get('volume_24h'), plan.get('symbol'))
    if not math.isfinite(fee) or fee < 0:
        return None
    cap = (plan.get('exit') or {}).get('max_loss_pct') or plan.get('max_loss_pct')
    if cap is not None:
        try:
            if not math.isfinite(float(cap)) or float(cap) <= 0 or risk > float(cap) * entry * (1 + 1e-9):
                return None
        except (TypeError, ValueError):
            return None

    targets = [levels.get(f'tp{k}') for k in (1, 2, 3)]
    if all(t is None for t in targets):
        # A targetless contract is valid only when the plan names its exit manager.  Its cost and stop-distance
        # checks are still mandatory; no synthetic 100R targets are used to make it look like a targetful card.
        if not plan.get('allow_no_targets') or not plan.get('exit_manager'):
            return None
        reason = None
        if risk < CONFIG.levels.cost_guard * fee:
            reason = f"risk < {CONFIG.levels.cost_guard:g}x the round-trip costs" if CONFIG.levels.cost_guard != 1 \
                else 'costs exceed the risk'
        reason = reason or stop_too_far(plan, entry, stop)
        out = dict(levels)
        out.update(risk0=risk, rr_tp1=None, rr_tp2=None, rr_blend=None,
                   low_rr=bool(reason), rr_reason=reason, geometry_source='shared_targetless_guard')
        return out

    sources = [str(levels.get(f'tp{k}_src') or 'custom target') for k in (1, 2, 3)]
    try:
        out = finish_levels(plan, entry, stop, [float(t) for t in targets], sources, direction,
                            str(levels.get('sl_src') or 'strategy stop'))
    except (TypeError, ValueError, KeyError):
        return None
    if out is None:
        return None
    # finish_levels owns the decision fields; preserve transport/management metadata supplied by the playbook.
    for key in ('zone_src', 'range_pos', 'limit_entry', 'volume_24h', 'contract_source'):
        if key in levels:
            out[key] = levels[key]
    out['risk0'] = risk
    out['geometry_source'] = 'shared_finish_levels'
    return out


@dataclass
class PlanInput:
    """Everything a plan is computed from."""
    symbol: str
    direction: int
    setup: str
    sig: Dict
    df: Optional[pl.DataFrame]                      # 15m frame with indicators (+ the live candle)
    minutes: Sequence[Sequence[float]]              # final 1m candles
    raw_levels: List                                # the coin's level map (zones.RawLevel)
    h1: Sequence[Sequence[float]]                   # the coin's 1h candles
    context: Optional[object]                       # strategies.structure.Context
    reached: Optional[float]                        # fixed target reference (None: measure now)
    # ATR14 of the coin's CLOSED 1h / 4h / daily candles: a stop is sized by the volatility of the timeframe its
    # structure lives on (a 4h zone's stop floored by the 15m ATR sat inside the 4h noise - 2026-10-05)
    tf_atr: Dict[str, float] = field(default_factory=dict)
    # eng-150 (plan 4.2): the coin's 4h / daily candles (premium / discount on the swept pool's timeframe)
    h4: Sequence[Sequence[float]] = field(default_factory=list)
    d1: Sequence[Sequence[float]] = field(default_factory=list)

    @property
    def atr(self) -> Optional[float]:
        if self.context is not None and getattr(self.context, 'atr', None):
            return self.context.atr
        if self.df is not None and 'atr' in self.df.columns and self.df.height:
            return self.df['atr'][-1]
        if self.df is None and (self.sig or {}).get('atr_15m'):
            return self.sig['atr_15m']          # eng-158: a small cap (smallcap.py) has no 15m frame
        return None

    @property
    def recent_atr(self) -> Optional[float]:
        return getattr(self.context, 'recent_atr', None) if self.context is not None else None


class Strategy:
    name = ''
    anchor_type = ''
    # setup name -> direction
    setups: Dict[str, int] = {}
    # CONFIG.strategies attribute with (watch, zone, trade) seconds; None: levels lifetimes x the leg's TTL factor
    ttl_key: Optional[str] = None
    uses_minutes = False                            # the plan depends on the final 1m candles (cache key)
    # Data the strategy cannot be judged without: 'spot' = a spot market (a continuation must be told apart from a
    # leverage-only move: the perp-led veto and the spot confirmation). A coin without it: vetoed 'no_data'.
    requires: tuple = ()

    def has_data(self, sig: Dict) -> bool:
        for need in self.requires:
            if need == 'spot' and not bool(sig.get('has_spot')):
                return False
            if need == 'flow' and sig.get('flow_quality_ok') != 1:
                return False
            if need == 'oi' and sig.get('oi_quality_ok') != 1:
                return False
        return True
    follows_live_candle = False                     # the plan depends on the live 15m candle's high / low (a leg)
    # the method's own minimum reward / risk to TP1 (its source's rule); None = CONFIG.levels.min_rr_tp1 (eng-40)
    min_rr: Optional[float] = None
    frozen_in_zone = False                          # a continuation's plan is frozen once price is in its zone
    # How the trade ends by time (eng-47): 'bars' = no TP1 within CONFIG.strategies.time_stop_bars bars of the
    # structure timeframe (the rest runs time_after_tp1 x longer once TP1 traded); 'fixed' = the method's own exit
    # decides (Turtles' channel, Connors' SMA5, O'Neil, Seiden, the Silver Bullet's session) and ttls()[2] only caps;
    # 'session' = out at the end of the method's session (session_end)
    time_exit = 'bars'

    @staticmethod
    def contract_id(setup: str) -> str:
        """Stable playbook identifier used to keep directions and variants separate."""
        return str(setup or '').strip().lower().replace(' ', '_')

    def entry_levels(self, plan: Dict, entry: float, extreme: Optional[float], direction: int) -> Optional[CardLevels]:
        """Return this playbook's executable trade contract.

        Every registered playbook must implement this method.  There is no
        An incomplete migration fails closed and is journaled as an
        unexecutable plan.
        """
        raise NotImplementedError(f"{self.__class__.__name__} has no playbook contract")

    def session_end(self, entered_at: float) -> Optional[float]:
        """Epoch seconds the method's session ends for a trade entered at entered_at ('session' methods)."""
        return None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        raise NotImplementedError

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        """The anchor's identity before a card exists (None: no anchor -> not a card, vetoed 'no_leg')."""
        plan = self.plan(x)
        return plan['key'] if plan else None

    def context_veto(self, sig: Dict, direction: int) -> Optional[str]:
        """Why the market context forbids this setup (journaled as the veto), None = allowed."""
        return None

    def ttls(self, tf: str) -> Tuple[int, int, int]:
        if self.ttl_key:
            return tuple(getattr(CONFIG.strategies, self.ttl_key))
        cfg = CONFIG.levels
        factor = TTL_FACTOR.get(tf, 1)
        # the trade lives as long as its structure: a 4h leg's target is days away, an 8h cap closed it on the way
        return cfg.watch_ttl_sec * factor, cfg.zone_ttl_sec * factor, cfg.trade_ttl_sec * factor

    @property
    def enabled(self) -> bool:
        return self.name in CONFIG.strategies.enabled


def base_plan(x: PlanInput, strategy: str, anchor: Dict, tf: str, **fields) -> Dict:
    """The fields every plan has; strategies add / override the rest."""
    plan = {
        'symbol': x.symbol, 'volume_24h': x.sig.get('volume_24h'), 'strategy': strategy, 'setup': x.setup, 'direction': x.direction, 'anchor': anchor, 'tf': tf,
        'trigger_minutes': TRIGGER_MINUTES.get(tf, 5), 'atr': x.atr, 'recent_atr': x.recent_atr, 'leg_atr': x.atr,
        'tf_atr': (x.tf_atr or {}).get(tf),
        'entry': 'pullback', 'invalid': None, 'fix_invalid': False, 'reset': None, 'missable': True,
        'stop_ref': None, 'stop_mid': None, 'retarget': False, 'intent': 'extension', 'fillers': (),
        'fill_label': 'fib', 'impulse': None, 'reached': x.reached,
        # the ported systems (strategies/maniac.py): their own entry trigger ('shift' = our 5m structure shift,
        # 'pinbar', 'ifvg'), their own exit rules, an entry only at the signal's close
        # (confirm_only: a vetoed confirmation ends the card), entries only in a session (tz, 'HH:MM', 'HH:MM'),
        # the pierce time the inversion FVG is searched from, and INVALID on a CLOSE of this many minutes beyond
        # the invalid price (a wick through is allowed)
        'trigger': 'shift', 'exit': None, 'confirm_only': False, 'session': None, 'trigger_from_ms': None,
        'invalid_close_min': None,
        # Confirmation contracts are immutable facts from the closed signal candle; a later scanner quote is only a
        # freshness/slippage check and must never redraw the original geometry.
        'confirmation_entry_price': None, 'confirmation_ts': None,
        'allow_no_targets': False, 'exit_manager': None,
        'contract_id': Strategy.contract_id(x.setup),
    }
    from strategies.ict import dealing_range, protected_swing
    if x.df is not None and not x.df.is_empty():
        plan['protected'] = protected_swing(x.df['high'].to_list(), x.df['low'].to_list(), x.df['close'].to_list(),
                                            x.direction)
    else:
        plan['protected'] = None
    plan['dealing_range'] = dealing_range(x.h1 or [])
    plan.update(fields)
    from strategies import strategy_of
    strategy = strategy_of(x.setup)
    if strategy is not None and getattr(strategy, 'min_rr', None) is not None:
        plan.setdefault('min_rr', strategy.min_rr)
    return plan


Detector = Callable[..., Optional[Dict]]
