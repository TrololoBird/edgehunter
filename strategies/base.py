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

Lifecycle, stop floor, R:R and the journal are shared (signal_book.py, geometry.py).
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple, TypedDict

import polars as pl

from config import CONFIG
from levels import TRIGGER_MINUTES, TTL_FACTOR  # noqa: F401  (TRIGGER_MINUTES re-exported for the strategies)


class CardLevels(TypedDict, total=False):
    """audit-80: the card's trade geometry (geometry.entry_levels / system_levels -> TrackedSignal.levels), one place
    that names every key the lifecycle, the executor and the page read."""
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
        return all(bool(sig.get('has_spot')) for need in self.requires if need == 'spot')
    follows_live_candle = False                     # the plan depends on the live 15m candle's high / low (a leg)
    # the method's own minimum reward / risk to TP1 (its source's rule); None = CONFIG.levels.min_rr_tp1 (eng-40)
    min_rr: Optional[float] = None
    frozen_in_zone = False                          # a continuation's plan is frozen once price is in its zone
    # How the trade ends by time (eng-47): 'bars' = no TP1 within CONFIG.strategies.time_stop_bars bars of the
    # structure timeframe (the rest runs time_after_tp1 x longer once TP1 traded); 'fixed' = the method's own exit
    # decides (Turtles' channel, Connors' SMA5, O'Neil, Seiden, the Silver Bullet's session) and ttls()[2] only caps;
    # 'session' = out at the end of the method's session (session_end)
    time_exit = 'bars'

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
        # 'pinbar', 'ifvg'), their own exit rules (geometry.system_levels), an entry only at the signal's close
        # (confirm_only: a vetoed confirmation ends the card), entries only in a session (tz, 'HH:MM', 'HH:MM'),
        # the pierce time the inversion FVG is searched from, and INVALID on a CLOSE of this many minutes beyond
        # the invalid price (a wick through is allowed)
        'trigger': 'shift', 'exit': None, 'confirm_only': False, 'session': None, 'trigger_from_ms': None,
        'invalid_close_min': None,
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
