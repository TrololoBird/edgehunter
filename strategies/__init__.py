"""
Strategies: each class of market event has its own anchor, entry, stop and target intent (see the modules).

    strategy    setups                              anchor   structure / entry        targets
    trend       BULL F / BEAR D                     leg      15m-1h-4h / 5m-15m-1h    extension
    momentum    IMPULSE UP / DOWN                   leg      15m-1h-4h / 5m-15m-1h    extension
    wyckoff     BULL A / B / E, BEAR C              leg      15m-1h-4h / 5m-15m-1h    range side (A, B), mean (C, E)
    sweep       SWEEP LOW / SWEEP HIGH              level    1h / 4h pools, 15m / 5m  opposite liquidity
    absorption  ABSORB BID / ABSORB ASK             level    1m event at a level / 5m mean
    exhaustion  FLUSH / SQUEEZE REVERSAL            leg      5m cascade / 5m          mean, retracements
    breakout    BREAKOUT UP / BREAKOUT DOWN         range    15m / 15m close or 5m    measured moves

Phases (trend, wyckoff) are scored by scorer.py on closed 15m candles, the impulse by Tier-0; the other four are
detected by LiveDetector (1m / liquidations, loop-side) and structure.build_context (15m closes, worker process).
"""
from typing import Dict, Optional, Tuple

from strategies.base import PlanInput, Strategy
from strategies.breakout import BreakoutStrategy
from strategies.cascade import ExhaustionStrategy
from strategies.leg import MomentumStrategy, TrendStrategy, WyckoffStrategy
from strategies.level import AbsorptionStrategy, SweepStrategy

STRATEGIES: Dict[str, Strategy] = {s.name: s for s in (
    TrendStrategy(), MomentumStrategy(), WyckoffStrategy(), SweepStrategy(), AbsorptionStrategy(),
    ExhaustionStrategy(), BreakoutStrategy())}

# Setup name -> (strategy name, direction)
SETUPS: Dict[str, Tuple[str, int]] = {setup: (s.name, d) for s in STRATEGIES.values() for setup, d in s.setups.items()}


def strategy_of(group_key: str) -> Optional[Strategy]:
    entry = SETUPS.get(group_key)
    return STRATEGIES[entry[0]] if entry else None


__all__ = ["PlanInput", "Strategy", "STRATEGIES", "SETUPS", "strategy_of"]
