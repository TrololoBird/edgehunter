"""
Cards of the classic methods in strategies/classic.py: each enters at its signal's close (as its author does), with
its own stop and target where the method defines one; the lifecycle, R:R rule and journal are shared.
"""
from typing import Dict, Optional

from strategies.base import PlanInput
from strategies.maniac_strategies import _System, _confirm_plan


class ValueAreaStrategy(_System):
    """Dalton's 80% rule: target the value area's far edge, stop beyond the edge price re-entered through."""
    name = 'market_profile'        # eng-35: Dalton's 80% rule, with the POC retest (maniac_strategies.AuctionStrategy)
    min_rr = 1.0                     # Dalton: the far edge of the value area is the target, no ratio rule
    setups = {'VA80 LONG': 1, 'VA80 SHORT': -1}
    ttl_key = 'classic_ttl'

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig = x.sig
        if sig.get('va_far') is None:
            return None
        exit = {'stop': ['ref', 0.0], 'tp': ['level', sig['va_far'], 1.0, None], 'atr': x.atr,
                'stop_src': 'beyond the value area edge', 'tp_src': "value area far edge (Dalton's 80% rule)"}
        return _confirm_plan(x, self.name, '15m', exit, "back inside yesterday's value area for two 30m periods",
                             stop_ref=sig['anchor_level'])


class OrbStrategy(_System):
    """Crabel's opening range breakout: stop at the range's other side, the target from the map."""
    name = 'orb'
    setups = {'ORB UP': 1, 'ORB DOWN': -1}
    min_rr = 1.0                     # Crabel: no target / ratio rule (exits by time or the opposite side)
    ttl_key = 'classic_ttl'

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig = x.sig
        if sig.get('orb_hi') is None:
            return None
        other = sig['orb_lo'] if x.direction > 0 else sig['orb_hi']
        exit = {'stop': ['price', other], 'tp': ['map', 1.0], 'atr': x.atr,
                'stop_src': "the opening range's other side (Crabel)"}
        return _confirm_plan(x, self.name, '15m', exit, 'close beyond the US-open 30m range')


class ConnorsStrategy(_System):
    """Connors' RSI(2): out at the SMA5 (the target), stop from the structure (he uses none)."""
    name = 'connors'
    setups = {'RSI2 LONG': 1, 'RSI2 SHORT': -1}
    min_rr = 0.0                     # Connors: no stop, no ratio - out at the SMA5; the R is only measured
    ttl_key = 'connors_ttl'

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig = x.sig
        if sig.get('connors_sma5') is None:
            return None
        exit = {'stop': ['pct', 0.02], 'tp': ['level', sig['connors_sma5'], 0.0, None], 'atr': x.atr,
                'tp_src': 'SMA5 (Connors exit)'}
        return _confirm_plan(x, self.name, '4h', exit, 'daily RSI(2) extreme with the SMA200 trend')


CLASSIC_STRATEGIES = (ValueAreaStrategy(), OrbStrategy(), ConnorsStrategy())
