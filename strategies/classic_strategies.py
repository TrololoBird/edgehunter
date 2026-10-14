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
        exit = {'stop': ['ref', 0.0], 'tp': ['level', sig['va_far'], 1.0, None], 'atr': x.atr, 'own_targets': True,
                'stop_src': 'beyond the value area edge', 'tp_src': "value area far edge (Dalton's 80% rule)"}
        # eng-94: the stop beyond the edge price re-entered through (Dalton: back outside value = the rule failed), not
        # beyond the whole excursion outside it - the system stop took the farther of the two (the day's low / high)
        return _confirm_plan(x, self.name, '15m', exit, "back inside yesterday's value area for two 30m periods",
                             stop_ref=sig['anchor_level'], stop_ref_only=True)


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
        # eng-84 (ORB practice, no source): the breakout minute's relative volume >= 1.5 - eng-109: shadow only
        rvol = sig.get('rvol_1m')
        if rvol is not None and rvol < 1.5:
            from signal_book import shadow_veto
            shadow_veto(sig, 'low_rvol')
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
        # eng-84 (ORB practice, no source): longs only above the day's VWAP - eng-109: shadow only
        day0 = (x.minutes[-1][0] // 86_400_000 * 86_400_000) if x.minutes else None
        today = [m for m in (x.minutes or []) if day0 is not None and m[0] >= day0]
        qv = sum(float(m[5]) for m in today if len(m) > 5)
        if qv > 0:
            vwap = sum((m[2] + m[3] + m[4]) / 3 * float(m[5]) for m in today if len(m) > 5) / qv
            if d * (sig['anchor_close'] - vwap) < 0:
                from signal_book import shadow_veto
                shadow_veto(sig, 'against_vwap')
        # eng-109, Crabel: the other stop level is the protective stop; no target - out at the session's close (the
        # eng-84 middle stop and 100% projection were ours)
        exit = {'stop': ['price', sig['anchor_extreme']], 'tp': ['trail'], 'atr': x.atr,
                'stop_src': "the opposite Crabel level (open -+ Stretch)",
                'tp_src': "none: out at the session's close (Crabel)"}
        plan = _confirm_plan(x, self.name, '15m', exit, f"{sig.get('orb_session', 'session')} open +- Stretch (Crabel)")
        if plan and not plan.get('skip'):
            plan['no_tp'] = True
        return plan


class ConnorsStrategy(_System):
    """Connors' RSI(2): out at the SMA5 (the target), stop from the structure (he uses none)."""
    name = 'connors'
    setups = {'RSI2 LONG': 1, 'RSI2 SHORT': -1, 'RSI2X LONG': 1, 'RSI2X SHORT': -1}   # RSI2X: Connors' own entry, shadow
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
