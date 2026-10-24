"""
Strategies: each class of market event has its own anchor, entry, stop and target intent (see the modules). The
registry as it stands (eng-145; one methodology = one strategy name, several playbooks may share it):

    strategy        setups                                   module               entry / exit (summary)
    continuation    IMPULSE UP / DOWN (Tier-0)               leg.py               ICT OTE 0.62-0.79, touch -> close;
                                                                                  targets start + k x leg
    sweep           SWEEP LOW / HIGH                         level.py             raid of an HTF pool, 5m FVG CE
                    SILVER BULLET LONG / SHORT               silver_bullet.py     NY windows, FVG CE, TP1 PDH / PDL
    wyckoff         SPRING / UTAD                            wyckoff_range.py     1h range spring / upthrust + test
                    FLUSH / SQUEEZE REVERSAL                 cascade.py           the climax's secondary test
    breakout        BREAKOUT UP / DOWN                       breakout.py          the Turtles (touch, 2N, channel exit)
                    BB1 UP / DOWN                            maniac_strategies    Bollinger method I (squeeze)
    supply_demand   SD DEMAND / SUPPLY                       maniac_strategies    Seiden 4h zones, 1h touch, R:R 3
    market_profile  VA80 LONG / SHORT                        classic_strategies   Dalton's 80% rule by session
                    AUCTION LONG / SHORT                     maniac_strategies    the failed auction (eng-127)
    trendline       TL EM UP / DOWN, TL TOUCH UP / DOWN      maniac_strategies    Edwards & Magee, retest 'shift' / 3rd touch
    bollinger       BB W-BOTTOM / M-TOP, BB3 BUY / SELL      maniac_strategies    W / M, method III (BB3 shadow)
    orb             ORB UP / DOWN                            classic_strategies   Crabel 5-min range +- Stretch, touch;
                                                                                  out on 15m Parabolic SAR (eng-145)
    connors         RSI2 / RSI2X LONG / SHORT                classic_strategies   daily RSI(2), out at the SMA5
    pump            PUMP / DUMP START, PUMP TOP, DUMP BOUNCE pump.py              the owner's pump playbook
    cup_handle      CUP HANDLE                               cup_handle.py        O'Neil, 1h / 4h
    po3             PO3 LONG / SHORT                         po3.py               ICT power of three, Asian range
    oi_build        OI BUILD LONG / SHORT                    oi_build.py          off (CONFIG.strategies.disabled_setups)

Which setups trade on the demo account: CONFIG.executor.demo_off_setups; journaled-only setups: SHADOW_SETUPS in
signal_book.py. Detection: Tier-0 (impulse), structure.build_context (15m closes, worker process), loopside.py
(1m / daily candles on the loop).
"""
from typing import Dict, Optional, Tuple

from strategies.base import PlanInput, Strategy
from strategies.breakout import BreakoutStrategy
from strategies.cascade import ExhaustionStrategy
from strategies.leg import MomentumStrategy
from strategies.level import SweepStrategy
from strategies.maniac_strategies import MANIAC_STRATEGIES
from strategies.wyckoff_range import WyckoffRangeStrategy
from strategies.classic_strategies import CLASSIC_STRATEGIES
from strategies.silver_bullet import SilverBulletStrategy
from strategies.pump import DumpBounceStrategy, DumpStartStrategy, PumpStartStrategy, PumpTopStrategy
from strategies.cup_handle import CupHandleStrategy
from strategies.oi_build import OiBuildStrategy
from strategies.po3 import Po3Strategy

# eng-35: one methodology = one strategy name; a methodology with several playbooks (Wyckoff's climax test and
# spring, Market Profile's 80% rule and failed auction, the continuation's two impulse detectors) keeps one class per
# playbook under ONE name - the journal, pools, stats and the live verdict judge the methodology
_ALL: Tuple[Strategy, ...] = (
    MomentumStrategy(), SweepStrategy(), SilverBulletStrategy(), ExhaustionStrategy(),
    WyckoffRangeStrategy(),
    BreakoutStrategy(), *MANIAC_STRATEGIES, *CLASSIC_STRATEGIES, PumpStartStrategy(), DumpStartStrategy(), PumpTopStrategy(),
    DumpBounceStrategy(), CupHandleStrategy(), Po3Strategy(), OiBuildStrategy())
STRATEGIES: Dict[str, Strategy] = {}
for _s in _ALL:
    STRATEGIES.setdefault(_s.name, _s)

# Setup name -> (strategy name, direction); setup name -> the playbook's object
SETUPS: Dict[str, Tuple[str, int]] = {setup: (s.name, d) for s in _ALL for setup, d in s.setups.items()}
_OBJ: Dict[str, Strategy] = {setup: s for s in _ALL for setup in s.setups}


def strategy_of(group_key: str) -> Optional[Strategy]:
    return _OBJ.get(group_key)


__all__ = ["PlanInput", "Strategy", "STRATEGIES", "SETUPS", "strategy_of"]


def unknown_names() -> Dict[str, list]:
    """audit-80: strategy names in the mode tables (regime / bias / confirm) that no registered strategy carries - a
    deleted strategy's leftover (the oi_signal outage). deploy/precheck.sh prints them; 'cascade' is a shadow mode."""
    from strategies import bias, confirm, regime
    known = set(STRATEGIES) | {'cascade'}
    tables = {'regime.TREND_MODES': regime.TREND_MODES, 'regime.RANGE_MODES': regime.RANGE_MODES,
              'bias.TREND': bias.TREND, 'bias.WITH_BIAS': bias.WITH_BIAS, 'bias.RANGE': bias.RANGE,
              'bias.EXEMPT': bias.EXEMPT, 'bias.DAILY': bias.DAILY, 'confirm.OI_EXPECT': tuple(confirm.OI_EXPECT)}
    return {k: sorted(set(v) - known) for k, v in tables.items() if set(v) - known}
