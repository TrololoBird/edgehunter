"""
Cards of crypto_maniac's systems (detectors: strategies/maniac.py, classic.py). Each keeps its author's entry
and exit: the entry at the signal's close (confirm_only: skipped, not re-timed, when his rule rejects it) or his own
5m trigger (pinbar retest, inversion FVG), his stop and his target; the lifecycle, journal and stats are ours.
"""
from typing import Dict, List, Optional

import numpy as np

from levels import MINUTE_MS, resample
from strategies.base import PlanInput, Strategy, base_plan
from strategies.geometry import system_levels
from strategies.maniac import find_pivots
from zones import merge


def _anchor(sig: Dict, tf: str) -> Dict:
    return {'type': 'level', 'tf': tf, 'level': sig['anchor_level'], 'label': sig.get('anchor_label', ''),
            'extreme': sig['anchor_extreme'], 'ts': sig['anchor_ts']}


def _finish(x: PlanInput, plan: Dict, entry_est: float, extreme: Optional[float]) -> Optional[Dict]:
    """The card's targets as they stand at the estimated entry (the entry recomputes them at its own price)."""
    levels = system_levels(plan, entry_est, extreme, x.direction)
    if levels is None:
        # no target ahead / no valid stop: journaled as such, not as a missing anchor ('no_leg', eng-50)
        return {'skip': 'no_target'}
    plan['targets'] = [levels['tp1'], levels['tp2'], levels['tp3']]
    plan['target_src'] = [levels['tp1_src'], levels['tp2_src'], levels['tp3_src']]
    # these targets already sit in front of their levels by the pierce: shown on the card, never re-read as levels
    # (exit_target's 'map' re-measured them and pulled them by p50 a second time)
    plan['targets_final'] = True
    return plan


def _confirm_plan(x: PlanInput, name: str, tf: str, exit: Dict, zone_src: str, **fields) -> Optional[Dict]:
    """A system entering at its signal's close: a narrow zone around that close, no waiting."""
    sig, atr = x.sig, x.atr
    if sig.get('anchor_level') is None or not atr:
        return None
    close = sig['anchor_close']
    zones = merge(list(x.raw_levels or []), atr, symbol=x.symbol)
    from pierce import overshoot
    half = overshoot(x.symbol, 'swing_15m', close, 'p50') or 0.25 * atr
    plan = base_plan(x, name, _anchor(sig, tf), tf, entry='confirm', confirm_only=True,
                     zone_lo=close - half, zone_hi=close + half, zone_src=zone_src, missable=False,
                     exit=exit, zones=zones, targets=[], target_src=[], key=(sig['anchor_ts'], name), **fields)
    return _finish(x, plan, close, sig.get('anchor_extreme'))


class _System(Strategy):
    anchor_type = 'level'

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('anchor_ts'), self.name) if x.sig.get('anchor_level') is not None else None


# ------------------------------------------------------------------------------------------------ supply / demand

class SupplyDemandStrategy(_System):
    """
    eng-127, Seiden / OTA's odds enhancers (strategies/maniac.sd_zone_events): a 4h zone, its first return; the entry
    at the close of the candle that touched the zone and closed back (the confirmation entry - Seiden's score 8; the
    bot takes no resting limits), the stop beyond the distal line, the target the opposite liquidity at >= 3:1 (his
    profit margin). The score (max 10) is completed here and the entry vetoed below 8 ('sd_score'):
      strength 0-2, time 0-1    from the detector (the coin's own history);
      freshness 2               the first return only (a second would be 1, a third 0: not traded);
      reward / risk 2           min_rr 3 (his "at least 3:1") - below it there is no trade at all;
      big picture 0-2           1 for the daily trend with the trade (coin_trend of the daily closes), 1 for the
                                zone on the right side of the curve (the lower half of the 20-day range for demand);
      arrival 0-1               1 when no opposite swing (a 2/2 fractal of 1h) formed on the way back to the zone
                                (Seiden: "we don't want new resistance levels before we buy").
    """
    name = 'supply_demand'
    setups = {'SD DEMAND': 1, 'SD SUPPLY': -1}
    min_rr = 3.0
    ttl_key = 'sd_ttl'
    time_exit = 'fixed'
    uses_minutes = True

    @staticmethod
    def arrival(h1, since_ms: int, d: int) -> int:
        bars = [b for b in h1 if b[0] >= since_ms]
        if len(bars) < 5:
            return 0                     # audit C08: an arrival not observable yet earns no point (was 1)
        k = 2 if d > 0 else 3
        vals = [b[k] for b in bars]
        for i in range(2, len(vals) - 2):
            w = vals[i - 2:i + 3]
            if (d > 0 and vals[i] == max(w)) or (d < 0 and vals[i] == min(w)):
                return 0
        return 1

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig, d, atr = x.sig, x.direction, x.atr
        if sig.get('zone_lo') is None or not atr:
            return None
        trend = sig.get('trend_1d')
        curve = sig.get('curve_pos')
        big = (1 if trend == d else 0) + (1 if curve is not None and (curve <= 0.5 if d > 0 else curve >= 0.5) else 0)
        arrival = self.arrival(x.h1 or [], int(sig.get('departure_ts') or sig['anchor_ts']), d)
        score = int(sig.get('sd_strength') or 0) + int(sig.get('sd_time') or 0) + 2 + 2 + big + arrival
        lo, hi = sig['zone_lo'], sig['zone_hi']
        far = lo if d > 0 else hi
        zones = merge(list(x.raw_levels or []), atr, symbol=x.symbol)
        near = hi if d > 0 else lo
        # Seiden's target: the opposing fresh 4h zone's proximal line (maniac.sd_opposing), not the map's liquidity;
        # none -> no profit zone to measure -> no trade
        opposing = [t for t in (sig.get('sd_targets') or []) if d * (t[0] - near) > 0]
        if not opposing:
            return {'skip': 'no opposing supply / demand zone'}
        targets, sources = [t[0] for t in opposing], [t[1] for t in opposing]
        while len(targets) < 3:
            targets.append(targets[-1])
            sources.append(sources[-1])
        plan = base_plan(x, self.name, _anchor(sig, '4h'), '4h', entry='pullback', trigger='touch', single_touch=True,
                         zone_lo=lo, zone_hi=hi,
                         zone_src=f"{sig.get('anchor_label', 'zone')}: odds {score}/10 (strength "
                                  # R:R 2: granted here, ENFORCED by min_rr = 3 to TP1 (the nearest opposing zone,
                                  # geometry.finish_levels, audit C07) - a plan below it is rejected, not scored
                                  f"{sig.get('sd_strength')}, time {sig.get('sd_time')}, fresh 2, R:R 2, big picture "
                                  f"{big}, arrival {arrival})",
                         invalid=far, fix_invalid=True, missable=False, stop_ref=far,
                         # the opposing zones only (own_targets): TP1 the nearest, TP2 the next (the last repeats)
                         exit={'stop': ['ref', 0.0], 'tp': ['level', targets[0], 0.0, None],
                               'tp2': ['level', targets[1], 0.0, None], 'own_targets': True, 'atr': atr,
                               'stop_src': 'beyond the distal line', 'tp_src': 'the opposing 4h supply / demand zone (Seiden)'},
                         intent='opposite_liquidity', targets=targets, target_src=sources, zones=zones,
                         sd_score=score, min_rr_on_tp1=True, key=(sig['anchor_ts'], near))
        return plan


# ------------------------------------------------------------------------------------------------ auction

class AuctionStrategy(_System):
    """eng-127, the failed auction (strategies/classic.failed_auction_event): in at the close of the 30-minute period
    back inside value, the stop beyond the probe's extreme, the target the value area's opposite end, out at the
    session's close. Replaces the ported auction_theory_in_code POC retest (its 0.35 ATR / 1.5 R / 2.5 R numbers)."""
    name = 'market_profile'
    min_rr = 1.0
    setups = {'AUCTION LONG': 1, 'AUCTION SHORT': -1}
    ttl_key = 'classic_ttl'
    time_exit = 'session'

    def session_end(self, entered_at: float) -> Optional[float]:
        return None                  # only the signal's own session close (SignalBook._time_exit) ends it by time

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig = x.sig
        if sig.get('va_far') is None:
            return None
        exit = {'stop': ['ref', 0.0], 'tp': ['level', sig['va_far'], 1.0, None], 'atr': x.atr, 'own_targets': True,
                'stop_src': "beyond the failed probe's extreme", 'tp_src': 'value area opposite end (failed auction)'}
        return _confirm_plan(x, self.name, '15m', exit, 'back inside value after a probe without acceptance',
                             stop_ref=sig['anchor_extreme'], stop_ref_only=True)


# ------------------------------------------------------------------------------------------------ SMT

# ------------------------------------------------------------------------------------------------ trendline

def structural_stop(minutes, direction: int, entry: float, pad: float, tf_min: int = 5) -> Optional[float]:
    """trendline_bot structural_stop: the last confirmed 5m pivot (3 / 3) beyond the entry, else the extreme of the
    last 40 5m bars, + a 0.1 ATR(5m) pad."""
    bars = resample(minutes, tf_min, minutes[-1][0] + MINUTE_MS) if minutes else []
    if len(bars) < 9:
        return None
    h = np.asarray([b[2] for b in bars])
    l = np.asarray([b[3] for b in bars])
    if direction < 0:
        for i in reversed(find_pivots(h, 3, 3, 'high')):
            if h[i] > entry:
                return float(h[i] + pad)
        top = float(h[-40:].max())
        return top + pad if top > entry else None
    for i in reversed(find_pivots(l, 3, 3, 'low')):
        if l[i] < entry:
            return float(l[i] - pad)
    bottom = float(l[-40:].min())
    return bottom - pad if bottom < entry else None


def _pivot_stop(bars, direction: int, entry: float, pad: float) -> Optional[float]:
    """The last confirmed pivot (3 / 3) of `bars` beyond the entry, else the extreme of the last 40 bars, + pad."""
    if len(bars) < 9:
        return None
    h = np.asarray([b[2] for b in bars])
    l = np.asarray([b[3] for b in bars])
    if direction < 0:
        for i in reversed(find_pivots(h, 3, 3, 'high')):
            if h[i] > entry:
                return float(h[i] + pad)
        top = float(h[-40:].max())
        return top + pad if top > entry else None
    for i in reversed(find_pivots(l, 3, 3, 'low')):
        if l[i] < entry:
            return float(l[i] - pad)
    bottom = float(l[-40:].min())
    return bottom - pad if bottom < entry else None


class TrendlineStrategy(_System):
    """Edwards & Magee trendline break on 1h lines: two closes beyond the line, a resting limit at the broken line
    (the retest), the stop beyond the last confirmed 1h pivot, targets the next 1h+ levels of the map."""
    name = 'trendline'
    setups = {'TL EM UP': 1, 'TL EM DOWN': -1}   # eng-127: the ATR-line bot (TRENDLINE UP / DOWN) is deleted
    ttl_key = 'trendline_ttl'
    uses_minutes = True

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig, d = x.sig, x.direction
        if sig.get('target_price') is None or not x.minutes:
            return None
        # eng-79: the stop beyond the last confirmed 1h pivot (the line's own timeframe), 0.1 x ATR(1h) beyond it
        now_ms = x.minutes[-1][0] + MINUTE_MS
        h1 = [b for b in (x.h1 or []) if b[0] + 3_600_000 <= now_ms]
        # eng-116: beyond the pivot by the coin's measured pierce of a 1h swing (pierce.py, p80 as the other structural
        # stops) - the 0.1 x ATR(1h) was ours
        from pierce import overshoot
        pad = overshoot(x.symbol, 'swing_1h', sig['anchor_level']) or 0.0
        line = sig['anchor_level']
        if sig.get('line_slope') is not None and sig.get('line_ts1') is not None:
            # audit: the retest is of the SAME sloped line, extended to now (Murphy: the broken line keeps its
            # slope as it changes role) - not the horizontal price the line had at the break
            bars = (now_ms - int(sig['line_ts1'])) / float(sig.get('line_period_ms') or 3_600_000)
            line = sig['line_p1'] + sig['line_slope'] * bars
        # beyond the line where the retest enters NOW (audit 2026-10-18: measured from the break's level, a rising
        # line's retest could sit beyond the stop)
        stop = _pivot_stop(h1[-120:], d, line, pad)
        if stop is None:
            return None
        # classic trendline break (Edwards & Magee): the targets are the next support / resistance levels (the map), not
        # the line's first anchor (his robot's target, kept in the setup note)
        exit = {'stop': ['price', stop], 'stop_src': '1h structure beyond the line + measured pierce', 'tp': ['map', 1.0],
                'atr': x.atr, 'no_atr_steps': True}
        plan = _confirm_plan(x, self.name, '1h', exit, 'trendline break (2 closes)')
        if plan and not plan.get('skip'):
            # eng-58, practice (Edwards & Magee; break -> retest -> move): the entry is a resting limit at the broken
            # line, retested from the other side, not the second close's price; first touch only
            # eng-84 (breakout-retest write-ups: retest + a confirming candle, not a resting limit; the owner's review):
            # the retest area is the line to half an hour-ATR beyond it on the broken side; the entry is a 15m
            # structure shift with agreeing taker flow there
            # eng-127: the retest area = the line to its measured pierce (the 5 x pad was ours)
            area = sorted((line, line + d * pad)) if pad else (line, line)
            plan.update(entry='pullback', confirm_only=False, trigger='shift', missable=True,
                        zone_lo=area[0], zone_hi=area[1], zone_src='the broken trendline: retest + 15m confirmation')
        return plan


# ------------------------------------------------------------------------------------------------ indicator systems

class BollingerStrategy(_System):
    """Bollinger's W-bottom / M-top (method III): entry at the close beyond the middle peak, the stop beyond the retest,
    the first target the opposite band (then the map)."""
    name = 'bollinger'
    setups = {'BB W-BOTTOM': 1, 'BB M-TOP': -1, 'BB3 BUY': 1, 'BB3 SELL': -1}   # BB3: eng-106 Method III, shadow
    min_rr = 1.0                     # Bollinger: the target is the opposite band, no ratio rule - only paying > risk
    ttl_key = 'bollinger_ttl'

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig = x.sig
        if sig.get('bb_stop') is None:
            return None
        # eng-55: the target is the opposite band AS IT MOVES (a band is the current mean +- 2 sigma: a level frozen at
        # the entry sits 3-4 sigma away once the bands contract) - out at market when price reaches the live band
        # (SignalBook band exit), no take-profit orders. Entered only while the band at the signal pays > the risk.
        close, d = sig['anchor_close'], x.direction
        if d * (sig['bb_target'] - close) <= abs(close - sig['bb_stop']):
            return {'skip': 'low_rr'}
        # 'pad': the retest's low is structure, the stop goes beyond it by the measured pierce / zone buffer and the
        # 1 ATR floor (eng-71: BTC's W stop sat 0.08% under the retest, then the cost guard vetoed it)
        # eng-85: the opposite band AT THE SIGNAL is a real TP1 (half out there, the rest trailed / out on the live band):
        # with no target at all 90 Bollinger entries of 11-13.10 booked 0 take-profits, winners went back to the stop
        exit = {'stop': ['price', sig['bb_stop']], 'stop_src': 'beyond the W / M retest', 'tp': ['trail'], 'pad': True,
                'tp_src': 'the opposite Bollinger band, live (Bollinger)', 'atr': x.atr,
                'tp1_price': sig['bb_target'], 'tp1_src': 'the opposite Bollinger band at the signal (Bollinger)'}
        plan = _confirm_plan(x, self.name, sig.get('bb_tf') or '15m', exit, 'Bollinger W / M confirmed by A/D')
        if plan and not plan.get('skip'):
            plan['band_exit'] = True
            plan['trail_after_tp1'] = True
        return plan


class BollingerSqueezeStrategy(_System):
    """eng-127, Bollinger's Method I (strategies/maniac.bb_method1_event): in at the close of the first band close after
    a Squeeze, out on Wilder's Parabolic SAR of the 4h bars (SignalBook._trail), no target."""
    name = 'breakout'
    setups = {'BB1 UP': 1, 'BB1 DOWN': -1}
    min_rr = 0.0
    ttl_key = 'bollinger_ttl'
    time_exit = 'fixed'

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig = x.sig
        if sig.get('bb_stop') is None:
            return None
        exit = {'stop': ['price', sig['bb_stop']], 'stop_src': 'Parabolic SAR (Wilder 0.02 / 0.20) of the 4h bars',
                'tp': ['trail'], 'tp_src': 'none: out on the Parabolic SAR (Bollinger, Method I)', 'atr': x.atr}
        plan = _confirm_plan(x, self.name, '4h', exit, 'Bollinger Method I: first band close after a Squeeze')
        if plan and not plan.get('skip'):
            plan['no_tp'] = True
            plan['sar'] = {'tf_min': 240, 'sar': sig['bb_stop'], 'ep': sig['sar_ep'], 'af': 0.02,
                           'last_ts': int(sig['event_ts']) - 240 * 60_000,
                           # review V08: the signal bar is the first step's previous bar (two-bar limit)
                           'prev_hi': sig.get('sar_prev_hi'), 'prev_lo': sig.get('sar_prev_lo')}
        return plan


MANIAC_STRATEGIES: List[Strategy] = [SupplyDemandStrategy(), AuctionStrategy(), TrendlineStrategy(),
                                     BollingerStrategy(), BollingerSqueezeStrategy()]
