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
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import polars as pl

from config import CONFIG
from levels import TRIGGER_MINUTES, TTL_FACTOR  # noqa: F401  (TRIGGER_MINUTES re-exported for the strategies)


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

    @property
    def atr(self) -> Optional[float]:
        if self.context is not None and getattr(self.context, 'atr', None):
            return self.context.atr
        if self.df is not None and 'atr' in self.df.columns and self.df.height:
            return self.df['atr'][-1]
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
    frozen_in_zone = False                          # a continuation's plan is frozen once price is in its zone

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
        'strategy': strategy, 'setup': x.setup, 'direction': x.direction, 'anchor': anchor, 'tf': tf,
        'trigger_minutes': TRIGGER_MINUTES.get(tf, 5), 'atr': x.atr, 'recent_atr': x.recent_atr, 'leg_atr': x.atr,
        'entry': 'pullback', 'invalid': None, 'fix_invalid': False, 'reset': None, 'missable': True,
        'stop_ref': None, 'stop_mid': None, 'retarget': False, 'intent': 'extension', 'fillers': (),
        'fill_label': 'fib', 'impulse': None, 'reached': x.reached,
    }
    plan.update(fields)
    return plan


Detector = Callable[..., Optional[Dict]]
