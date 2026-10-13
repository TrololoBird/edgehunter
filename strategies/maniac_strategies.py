"""
Cards of crypto_maniac's systems (detectors: strategies/maniac.py, auction_engine.py). Each keeps its author's entry
and exit: the entry at the signal's close (confirm_only: skipped, not re-timed, when his rule rejects it) or his own
5m trigger (pinbar retest, inversion FVG), his stop and his target; the lifecycle, journal and stats are ours.
"""
from typing import Dict, List, Optional

import numpy as np

from config import CONFIG
from levels import MINUTE_MS, resample
from strategies.base import PlanInput, Strategy, base_plan
from strategies.geometry import select_targets, system_levels
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
    """supply_demand-v4: a fresh 15m zone; a 5m pinbar retesting it is the entry; stop beyond the pinbar and the zone
    (no buffer); the zone is dead on a 15m CLOSE beyond it (his INVALIDATION_METHOD 'close'). He sends no target:
    targets are ours (the opposite liquidity on the map)."""
    name = 'supply_demand'
    setups = {'SD DEMAND': 1, 'SD SUPPLY': -1}
    min_rr = 3.0                     # Seiden (Online Trading Academy): a trade needs >= 3:1 reward / risk to the opposing zone
    ttl_key = 'sd_ttl'
    time_exit = 'fixed'                # the method's own exit (eng-47)
    uses_minutes = True

    def context_veto(self, sig: Dict, direction: int) -> Optional[str]:
        """eng-58, Seiden / OTA's odds enhancer 'big picture': demand only when the daily trend is not down, supply only
        when it is not up."""
        return 'big_picture' if sig.get('trend_1d') == -direction else None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig, d, atr = x.sig, x.direction, x.atr
        if sig.get('zone_lo') is None or not atr:
            return None
        # Seiden's curve: demand only low on the higher-timeframe curve, supply only high (the daily range of 20 days)
        curve = sig.get('curve_pos')
        if curve is not None and (curve > 0.5 if d > 0 else curve < 0.5):
            return {'skip': 'curve'}
        lo, hi = sig['zone_lo'], sig['zone_hi']
        far = lo if d > 0 else hi
        zones = merge(list(x.raw_levels or []), atr, symbol=x.symbol)
        near = hi if d > 0 else lo
        targets, sources = select_targets(zones, near, d, atr, 'opposite_liquidity')
        # Seiden: a resting limit at the proximal line, the stop beyond the distal line, the zone's FIRST touch only
        plan = base_plan(x, self.name, _anchor(sig, '4h'), '4h', entry='pullback', trigger='touch', single_touch=True,
                         zone_lo=lo, zone_hi=hi, zone_src=f"{sig.get('anchor_label', 'zone')} (5m pinbar)",
                         # not missable: the zone is confirmed only once price left it by 2 ATR, so a target
                         # measured from the zone is often behind price already; his zone waits for the return
                         invalid=far, fix_invalid=True, invalid_close_min=240, missable=False, stop_ref=far,
                         exit={'stop': ['ref', 0.0], 'tp': ['map', 0.0], 'atr': atr,
                               'stop_src': 'beyond the pinbar and the zone'},
                         intent='opposite_liquidity', targets=targets, target_src=sources, zones=zones,
                         key=(sig['anchor_ts'], near))
        return plan


# ------------------------------------------------------------------------------------------------ auction

class AuctionStrategy(_System):
    """auction_theory_in_code: a POC retest reacted on 1h; entry at that close, stop beyond the test's extreme + 0.35
    ATR, target the nearest strong untested POC (skipped below 1.5 R), else 2.5 R."""
    name = 'market_profile'        # eng-35: Dalton's POC retest, with the 80% rule (classic_strategies.py)
    min_rr = 1.5                     # the auction system's own rule: the next POC must pay >= 1.5 R
    setups = {'AUCTION LONG': 1, 'AUCTION SHORT': -1}
    ttl_key = 'auction_ttl'

    def plan(self, x: PlanInput) -> Optional[Dict]:
        cfg = CONFIG.strategies
        sig = x.sig
        if sig.get('auction_stop') is None:
            return None
        target, tp_src = sig.get('auction_target'), 'naked strong POC'
        if target is None:
            # the engine's own 1h POCs hold none ahead: the next POC of another profile on the map - a completed
            # day's naked POC (Dalton's virgin POC), the 4-day or the 24h composite (was: no_target)
            atr = sig.get('atr_1h') or x.atr
            ahead = sorted((lv for lv in (x.raw_levels or []) if lv.kind == 'poc'
                            and x.direction * (lv.price - sig['anchor_close']) > 0.1 * atr),
                           key=lambda lv: x.direction * (lv.price - sig['anchor_close']))
            if ahead:
                target, tp_src = ahead[0].price, ahead[0].label
        exit = {'stop': ['price', sig['auction_stop']], 'stop_src': "beyond the POC test + measured pierce",
                # no 'x R' fallback target (eng-41): the next POC, else no trade
                'tp': ['level', target, cfg.auction_min_rr, None],
                'tp_src': tp_src, 'atr': sig.get('atr_1h') or x.atr}
        return _confirm_plan(x, self.name, '1h', exit, f"POC {sig['anchor_level']:.6g} retest reaction ({sig.get('auction_kind')})")


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
    setups = {'TRENDLINE UP': 1, 'TRENDLINE DOWN': -1}
    ttl_key = 'trendline_ttl'
    uses_minutes = True

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig, d = x.sig, x.direction
        if sig.get('target_price') is None or not x.minutes:
            return None
        # eng-79: the stop beyond the last confirmed 1h pivot (the line's own timeframe), 0.1 x ATR(1h) beyond it
        now_ms = x.minutes[-1][0] + MINUTE_MS
        h1 = [b for b in (x.h1 or []) if b[0] + 3_600_000 <= now_ms]
        trs = [max(b[2] - b[3], abs(b[2] - p[4]), abs(b[3] - p[4])) for p, b in zip(h1, h1[1:])][-14:]
        pad = 0.1 * (sum(trs) / len(trs)) if trs else 0.0
        stop = _pivot_stop(h1[-120:], d, sig['anchor_level'], pad)          # beyond the line (the retest entry)
        if stop is None:
            return None
        # classic trendline break (Edwards & Magee): the targets are the next support / resistance levels (the map), not
        # the line's first anchor (his robot's target, kept in the setup note)
        exit = {'stop': ['price', stop], 'stop_src': '1h structure beyond the line', 'tp': ['map', 1.0], 'atr': x.atr}
        plan = _confirm_plan(x, self.name, '1h', exit, 'trendline break (2 closes)')
        if plan and not plan.get('skip'):
            # eng-58, practice (Edwards & Magee; break -> retest -> move): the entry is a resting limit at the broken
            # line, retested from the other side, not the second close's price; first touch only
            line = sig['anchor_level']
            plan.update(entry='pullback', confirm_only=False, trigger='touch', single_touch=True, missable=True,
                        zone_lo=line, zone_hi=line, zone_src='the broken trendline, retest from the other side')
        return plan


# ------------------------------------------------------------------------------------------------ indicator systems

class BollingerStrategy(_System):
    """Bollinger's W-bottom / M-top (method III): entry at the close beyond the middle peak, the stop beyond the retest,
    the first target the opposite band (then the map)."""
    name = 'bollinger'
    setups = {'BB W-BOTTOM': 1, 'BB M-TOP': -1}
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
        exit = {'stop': ['price', sig['bb_stop']], 'stop_src': 'beyond the W / M retest', 'tp': ['trail'], 'pad': True,
                'tp_src': 'the opposite Bollinger band, live (Bollinger)', 'atr': x.atr}
        plan = _confirm_plan(x, self.name, sig.get('bb_tf') or '15m', exit, 'Bollinger W / M confirmed by A/D')
        if plan and not plan.get('skip'):
            plan['band_exit'] = True
            plan['no_tp'] = True
        return plan


MANIAC_STRATEGIES: List[Strategy] = [SupplyDemandStrategy(), AuctionStrategy(), TrendlineStrategy(),
                                     BollingerStrategy()]
