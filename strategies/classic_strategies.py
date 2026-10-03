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
    time_exit = 'session'

    def session_end(self, entered_at: float) -> Optional[float]:
        # Dalton: the 80% rule trades the day whose value area price re-entered - out at the UTC day's close
        return (int(entered_at) // 86400 + 1) * 86400

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
    time_exit = 'session'

    def session_end(self, entered_at: float) -> Optional[float]:
        # Crabel: the opening range trade is closed at the session's close - 16:00 New York of the entry day
        import datetime as _dt
        from zoneinfo import ZoneInfo
        ny = _dt.datetime.fromtimestamp(entered_at, ZoneInfo('America/New_York'))
        end = ny.replace(hour=16, minute=0, second=0, microsecond=0)
        if end <= ny:
            end += _dt.timedelta(days=1)
        return end.timestamp()

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig = x.sig
        if sig.get('orb_hi') is None:
            return None
        other = sig['orb_lo'] if x.direction > 0 else sig['orb_hi']
        # Crabel: no profit target - the stop at the range's other side, out at the session's close (eng-47's
        # session exit). A map target killed 38 of 49 ORB plans on 2026-10-03 (a break into price discovery has no
        # level beyond; journaled as 'no_leg') - eng-50
        exit = {'stop': ['price', other], 'tp': ['trail'], 'atr': x.atr,
                'stop_src': "the opening range's other side (Crabel)",
                'tp_src': "none: out at the session's close (Crabel)"}
        plan = _confirm_plan(x, self.name, '15m', exit, 'close beyond the US-open 30m range')
        if plan and not plan.get('skip'):
            plan['no_tp'] = True
        return plan


class ConnorsStrategy(_System):
    """Connors' RSI(2): out at the SMA5 (the target), stop from the structure (he uses none)."""
    name = 'connors'
    setups = {'RSI2 LONG': 1, 'RSI2 SHORT': -1}
    min_rr = 0.0                     # Connors: no stop, no ratio - out at the SMA5; the R is only measured
    ttl_key = 'connors_ttl'
    time_exit = 'fixed'                # the method's own exit (eng-47)

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig = x.sig
        if sig.get('connors_sma5') is None:
            return None
        # Connors: out on the first daily CLOSE above (long) / below (short) the CURRENT 5-day SMA - a moving
        # exit, not the SMA5 of the signal day touched intraday (eng-48); SignalBook checks it on each daily close
        exit = {'stop': ['pct', 0.02], 'tp': ['level', sig['connors_sma5'], 0.0, None], 'atr': x.atr,
                'tp_src': 'SMA5 (Connors exit)', 'connors_exit': True}
        plan = _confirm_plan(x, self.name, '4h', exit, 'daily RSI(2) extreme with the SMA200 trend')
        if plan and not plan.get('skip'):
            plan['connors_exit'] = True
            plan['no_tp'] = True              # out on the SMA5 close: no take-profit orders
        return plan


CLASSIC_STRATEGIES = (ValueAreaStrategy(), OrbStrategy(), ConnorsStrategy())
