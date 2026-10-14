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
    """eng-93: the session opening range breakout (strategies.classic.session_orb) on the majors, gold, silver and
    oil: the first break of the Asia / London / New York session's first 30 minutes, the stop at the range's middle,
    TP1 the range's width projected, out at that session's close (was Crabel's open +- Stretch on the UTC day)."""
    name = 'orb'
    setups = {'ORB UP': 1, 'ORB DOWN': -1}
    min_rr = 0.0                     # Crabel: no target / ratio rule (exits by time or the opposite level)
    ttl_key = 'classic_ttl'
    time_exit = 'session'
    uses_minutes = True              # eng-84: the day's VWAP side

    def context_veto(self, sig: Dict, direction: int) -> Optional[str]:
        # eng-84 (ORB practice): the break needs participation - the breakout minute's relative volume >= 1.5
        rvol = sig.get('rvol_1m')
        if rvol is not None and rvol < 1.5:
            return 'low_rvol'
        return None

    def session_end(self, entered_at: float) -> Optional[float]:
        # eng-93: the card's own session close is in its signal (session_end_ms, SignalBook._time_exit); this is
        # only the fallback of a card restored without it
        return (int(entered_at) // 86400 + 1) * 86400

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig = x.sig
        if sig.get('orb_hi') is None:
            return None
        d = x.direction
        # eng-84 (ORB practice): longs only above the day's VWAP, shorts only below it
        day0 = (x.minutes[-1][0] // 86_400_000 * 86_400_000) if x.minutes else None
        today = [m for m in (x.minutes or []) if day0 is not None and m[0] >= day0]
        qv = sum(float(m[5]) for m in today if len(m) > 5)
        if qv > 0:
            vwap = sum((m[2] + m[3] + m[4]) / 3 * float(m[5]) for m in today if len(m) > 5) / qv
            if d * (sig['anchor_close'] - vwap) < 0:
                return {'skip': 'against_vwap'}
        # eng-84: the stop at the range's middle (the day's open), TP1 a projection of the range's width (100%);
        # the session close stays the time exit, the management (half at TP1, break-even) is the common one
        width = sig['orb_hi'] - sig['orb_lo']
        mid = (sig['orb_hi'] + sig['orb_lo']) / 2
        exit = {'stop': ['price', mid], 'tp': ['level', sig['anchor_level'] + d * width, 0.0, None], 'atr': x.atr,
                'stop_src': "the opening range's middle",
                'tp_src': "100% projection of the opening range"}
        return _confirm_plan(x, self.name, '15m', exit, f"{sig.get('orb_session', 'session')} opening range break")


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
        # eng-55: Connors uses no stop; the perpetual's margin needs one - a catastrophic stop connors_disaster_atr
        # daily ATR away, labelled as OUR deviation (eng-48..54: a 2% stop sat inside one day's noise)
        from config import CONFIG
        datr = sig.get('connors_atr')
        if datr:
            stop = ['price', sig['anchor_close'] - x.direction * CONFIG.strategies.connors_disaster_atr * datr]
        else:
            stop = ['pct', 0.10]
        exit = {'stop': stop, 'tp': ['level', sig['connors_sma5'], 0.0, None], 'atr': x.atr,
                'stop_src': f"catastrophic stop {CONFIG.strategies.connors_disaster_atr:g} daily ATR (our deviation: "
                            f"Connors uses none)",
                'tp_src': 'SMA5 (Connors exit)', 'connors_exit': True}
        plan = _confirm_plan(x, self.name, '1d', exit, 'daily RSI(2) extreme with the SMA200 trend')
        if plan and not plan.get('skip'):
            plan['connors_exit'] = True
            plan['no_tp'] = True              # out on the SMA5 close: no take-profit orders
        return plan


CLASSIC_STRATEGIES = (ValueAreaStrategy(), OrbStrategy(), ConnorsStrategy())
