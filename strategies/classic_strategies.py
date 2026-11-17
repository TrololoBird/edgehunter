"""
Cards of the classic methods in strategies/classic.py: each enters at its signal's close (as its author does), with
its own stop and target where the method defines one; the lifecycle, R:R rule and journal are shared.
"""
from typing import Dict, Optional

from config import CONFIG
from strategies.base import CardLevels, PlanInput
from strategies.maniac_strategies import _System, _confirm_plan


CONNORS_CATASTROPHE_STOP_ATR = 2.0


class ValueAreaStrategy(_System):
    """Dalton's 80% rule: target the value area's far edge, stop beyond the edge price re-entered through."""
    name = 'value_area'
    min_rr = 1.0                     # Dalton: the far edge of the value area is the target, no ratio rule
    setups = {'VA80 LONG': 1, 'VA80 SHORT': -1}
    ttl_key = 'classic_ttl'
    time_exit = 'session'

    def entry_levels(self, plan: Dict, entry: float, extreme: Optional[float], direction: int) -> Optional[CardLevels]:
        ex, stop, targets = plan.get('exit') or {}, (plan.get('exit') or {}).get('stop') or [], list(plan.get('targets') or ())[:3]
        if len(stop) < 2 or not targets or not entry: return None
        edge = float(stop[1])
        anchor = plan.get('anchor') or {}
        probe = anchor.get('extreme', extreme)
        try:
            probe = float(probe) if probe is not None else None
        except (TypeError, ValueError):
            probe = None
        # The stop belongs beyond the edge that was re-entered, or beyond the
        # probe extreme when the session recorded one.  A volatility pad and
        # the shared stop floor prevent a close exactly at VAL/VAH from
        # creating a zero/tick-sized risk contract.
        ref = probe if probe is not None and direction * (edge - probe) > 0 else edge
        atr = max(float(plan.get('atr') or 0.0), float(plan.get('tf_atr') or 0.0))
        recent = float(plan.get('recent_atr') or 0.0)
        pad = CONFIG.levels.stop_buffer_atr * max(atr, recent)
        sl = ref - direction * pad if pad > 0 else ref
        floor = CONFIG.levels.min_stop_atr * max(atr, recent)
        if floor > 0 and direction * (entry - sl) < floor:
            sl = entry - direction * floor
        risk = direction * (entry - sl)
        if sl <= 0 or risk <= 0: return None
        targets += [targets[-1]] * (3-len(targets)); rr=[direction*(t-entry)/risk for t in targets]
        src=list(plan.get('target_src') or ())+['value area far edge']*3; plan['contract_source']='value_area_dalton'
        stop_src = ex.get('stop_src') or 'value area edge'
        if probe is not None and ref == probe:
            stop_src = f'{stop_src}: probe extreme + {CONFIG.levels.stop_buffer_atr:g} ATR'
        elif pad > 0:
            stop_src = f'{stop_src} + {CONFIG.levels.stop_buffer_atr:g} ATR'
        if floor > 0 and risk == floor:
            stop_src = f'{stop_src}, widened to {CONFIG.levels.min_stop_atr:g} ATR floor'
        return {'entry':float(entry),'sl':sl,'tp1':targets[0],'tp2':targets[1],'tp3':targets[2],'rr_tp1':rr[0],'rr_tp2':rr[1],'rr_blend':sum(rr)/3,'low_rr':False,'rr_reason':None,'risk_units':1.0,'risk0':risk,'stop_pierce':None,'sl_src':stop_src,'tp1_src':src[0],'tp2_src':src[1],'tp3_src':src[2],'zone_src':plan.get('zone_src'),'range_pos':None,'limit_entry':None,'volume_24h':plan.get('volume_24h')}

    def session_end(self, entered_at: float) -> Optional[float]:
        # Legacy fallback only.  New signals carry session_end_ms and
        # SignalBook uses that exact session close before reaching here.
        return (int(entered_at) // 86400 + 1) * 86400

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig = x.sig
        if sig.get('va_far') is None:
            return None
        exit = {'stop': ['price', sig['anchor_level']], 'tp': ['level', sig['va_far'], 1.0, None], 'atr': x.atr, 'own_targets': True,
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

    def entry_levels(self, plan: Dict, entry: float, extreme: Optional[float], direction: int) -> Optional[CardLevels]:
        """Crabel ORB contract: opposite range level is the stop; session close is the exit."""
        stop = (plan.get('exit') or {}).get('stop') or []
        if len(stop) < 2 or stop[0] != 'price' or not entry:
            return None
        sl = float(stop[1])
        risk = direction * (entry - sl)
        if risk <= 0 or sl <= 0:
            return None
        plan['contract_source'] = 'orb_crabel'
        src = (plan.get('exit') or {}).get('stop_src') or 'opposite opening-range level'
        return {'entry': float(entry), 'sl': sl, 'tp1': None, 'tp2': None, 'tp3': None,
                'rr_tp1': None, 'rr_tp2': None, 'rr_blend': None, 'low_rr': False, 'rr_reason': None,
                'risk_units': 1.0, 'risk0': risk, 'stop_pierce': None, 'sl_src': src,
                'tp1_src': 'none: session close', 'tp2_src': 'none: session close',
                'tp3_src': 'none: session close', 'zone_src': plan.get('zone_src') or 'opening range',
                'range_pos': None, 'limit_entry': None, 'volume_24h': plan.get('volume_24h')}

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
        base = sum(float(m[7]) for m in today if len(m) > 7 and m[7])
        if qv > 0:
            if base > 0 and all(len(m) > 7 for m in today):
                vwap = qv / base                  # audit E03: quote / base is the exact VWAP (no price weighting twice)
            else:
                vwap = sum((m[2] + m[3] + m[4]) / 3 * float(m[5]) for m in today if len(m) > 5) / qv
            if d * (sig['anchor_close'] - vwap) < 0:
                from signal_book import shadow_veto
                shadow_veto(sig, 'against_vwap')
        # eng-109, Crabel: the other stop level is the protective stop; no target - out at the session's close (the
        # eng-84 middle stop and 100% projection were ours)
        exit = {'stop': ['price', sig['anchor_extreme']], 'tp': ['trail'], 'atr': x.atr,
                'stop_src': "the opposite Crabel level (opening range -+ Stretch)",
                'tp_src': "none: out at the session's close (Crabel)"}
        plan = _confirm_plan(x, self.name, '15m', exit, f"{sig.get('orb_session', 'session')} opening range +- Stretch (Crabel)")
        if plan and not plan.get('skip'):
            plan['no_tp'] = True
            # eng-154 (the owner, live eng-148: 8 of 10 ORB cards lost, 4 in a row; XAG / XAU traded +0.8..+1.1R and
            # closed -0.2..-0.7R at the session's close): the stop to break-even + costs after +1R, still out at the close
            plan['be_after_r'] = 1.0
            # eng-164, Crabel (Day Trading with Short Term Price Patterns, 1990): "In general stops should be moved to
            # break even within one hour after entry" - after 60 minutes a trade beyond break-even gets it
            plan['be_after_min'] = 60
        return plan


class ConnorsStrategy(_System):
    """Connors' RSI(2): out at the SMA5 with an explicit 2 daily-ATR catastrophe stop."""
    name = 'connors'
    # Connors' published rule implemented here is RSI2X LONG only: close above SMA200 and RSI(2) < 5.
    # Cross-back and mirrored short variants are research alternatives, not this method's executable card.
    setups = {'RSI2X LONG': 1}
    min_rr = 0.0                     # Connors: no fixed TP ratio - out at the SMA5; risk is the declared catastrophe stop
    ttl_key = 'connors_ttl'
    time_exit = 'fixed'                # the method's own exit (eng-47)

    def entry_levels(self, plan: Dict, entry: float, extreme: Optional[float], direction: int) -> Optional[CardLevels]:
        """Connors contract: the SMA5 is the method exit and the 2 daily-ATR stop is real protection."""
        exit = plan.get('exit') or {}
        stop = exit.get('stop') or []
        if len(stop) < 2 or not entry:
            return None
        unit_stop = float(stop[1])
        risk = direction * (entry - unit_stop)
        if risk <= 0 or unit_stop <= 0:
            return None
        plan['contract_source'] = 'connors_rsi2'
        src = exit.get('stop_src') or '2 daily ATR catastrophe stop'
        tp_src = exit.get('tp_src') or 'SMA5 close'
        return {'entry': float(entry), 'sl': unit_stop, 'tp1': None, 'tp2': None, 'tp3': None,
                'rr_tp1': None, 'rr_tp2': None, 'rr_blend': None, 'low_rr': False, 'rr_reason': None,
                'risk_units': 1.0, 'risk0': risk, 'stop_pierce': None, 'sl_src': src,
                'tp1_src': f'none: {tp_src}', 'tp2_src': f'none: {tp_src}', 'tp3_src': f'none: {tp_src}',
                'zone_src': plan.get('zone_src') or 'daily RSI(2)', 'range_pos': None,
                'limit_entry': None, 'volume_24h': plan.get('volume_24h')}

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig = x.sig
        if sig.get('connors_sma5') is None:
            return None
        # Connors: out on the first daily CLOSE above (long) / below (short) the CURRENT 5-day SMA - a moving
        # exit, not the SMA5 of the signal day touched intraday (eng-48); SignalBook checks it on each daily close
        # The source rule exits on SMA5, but a leveraged perpetual needs an explicit disaster stop.  The stop is
        # part of this project's contract and the executor sizes risk from its actual exchange distance.
        datr = sig.get('connors_atr')
        if not datr:
            return None
        stop = ['price', sig['anchor_close'] - x.direction * CONNORS_CATASTROPHE_STOP_ATR * datr]
        exit = {'stop': stop, 'tp': ['level', sig['connors_sma5'], 0.0, None], 'atr': x.atr,
                'stop_src': f'{CONNORS_CATASTROPHE_STOP_ATR:g} daily ATR catastrophe stop (Connors contract)',
                'tp_src': 'SMA5 (Connors exit)', 'connors_exit': True}
        plan = _confirm_plan(x, self.name, '1d', exit, 'daily RSI(2) extreme with the SMA200 trend')
        if plan and not plan.get('skip'):
            plan['connors_exit'] = True
            plan['no_tp'] = True              # out on the SMA5 close: no take-profit orders
            plan['no_stop'] = False           # the catastrophe stop is a real exchange protection order
            plan['catastrophe_stop_atr'] = CONNORS_CATASTROPHE_STOP_ATR
            plan['allow_no_targets'] = True
            plan['exit_manager'] = 'daily SMA5 close'
        return plan


CLASSIC_STRATEGIES = (ValueAreaStrategy(), OrbStrategy(), ConnorsStrategy())
