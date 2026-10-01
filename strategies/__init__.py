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

crypto_maniac's systems (github.com/roman-boop, strategies/maniac.py), each with its author's own entry and exit:
    supply_demand SD DEMAND / SD SUPPLY            zone     15m zone / 5m pinbar     the map
    auction     AUCTION LONG / SHORT                POC      1h / at the close        naked POC, 2.5R
    smt         SMT LOW / SMT HIGH                  pool     15m sweep / 5m iFVG      opposite pool, 2.5R
    trendline   TRENDLINE UP / DOWN                 line     15m 2 closes             the line's first anchor
    thirdeye    THIRD EYE LONG / SHORT              cloud    1h / at the close        5% (SL 1%)
    fib05       FIB 0.5 LONG / SHORT                impulse  1h / at the close        the impulse's end
    bomberman   BOMBERMAN LONG / SHORT              QML      1h / at the close        2R (SL 1.5 ATR)
    bollinger   BB W-BOTTOM / BB M-TOP             W / M    15m / at the close       the opposite band (Bollinger method III)
    oi_accum    OI ACCUMULATION                     OI       1m OI / at once          4% / 6% (SL 2%)

Classic methods (strategies/classic.py), each at its signal's close:
    value_area  VA80 LONG / SHORT                  value area 15m / 30m periods   the far edge (Dalton's 80% rule)
    orb         ORB UP / DOWN                      opening range 15m close        the map (stop: the range's other side)
    connors     RSI2 LONG / SHORT                  1h RSI(2) + SMA200             the SMA5

Phases (trend, wyckoff) are scored by scorer.py on closed 15m candles, the impulse by Tier-0; the other four are
detected by LiveDetector (1m / liquidations, loop-side) and structure.build_context (15m closes, worker process).
"""
from typing import Dict, Optional, Tuple

from strategies.base import PlanInput, Strategy
from strategies.breakout import BreakoutStrategy
from strategies.cascade import ExhaustionStrategy
from strategies.leg import MomentumStrategy, TrendStrategy
from strategies.level import SweepStrategy
from strategies.maniac_strategies import MANIAC_STRATEGIES
from strategies.wyckoff_range import WyckoffRangeStrategy
from strategies.classic_strategies import CLASSIC_STRATEGIES
from strategies.silver_bullet import SilverBulletStrategy
from strategies.pump import PumpStartStrategy, PumpTopStrategy
from strategies.cup_handle import CupHandleStrategy

# eng-35: one methodology = one strategy name; a methodology with several playbooks (Wyckoff's climax test and
# spring, Market Profile's 80% rule and POC retest, the continuation's two impulse detectors) keeps one class per
# playbook under ONE name - the journal, pools, stats and the live verdict judge the methodology
_ALL: Tuple[Strategy, ...] = (
    TrendStrategy(), MomentumStrategy(), SweepStrategy(), SilverBulletStrategy(), ExhaustionStrategy(),
    WyckoffRangeStrategy(),
    BreakoutStrategy(), *MANIAC_STRATEGIES, *CLASSIC_STRATEGIES, PumpStartStrategy(), PumpTopStrategy(),
    CupHandleStrategy())
STRATEGIES: Dict[str, Strategy] = {}
for _s in _ALL:
    STRATEGIES.setdefault(_s.name, _s)

# Setup name -> (strategy name, direction); setup name -> the playbook's object
SETUPS: Dict[str, Tuple[str, int]] = {setup: (s.name, d) for s in _ALL for setup, d in s.setups.items()}
_OBJ: Dict[str, Strategy] = {setup: s for s in _ALL for setup in s.setups}


def strategy_of(group_key: str) -> Optional[Strategy]:
    return _OBJ.get(group_key)


__all__ = ["PlanInput", "Strategy", "STRATEGIES", "SETUPS", "strategy_of"]
