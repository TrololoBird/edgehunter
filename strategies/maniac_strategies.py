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
        return None
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
    plan = base_plan(x, name, _anchor(sig, tf), tf, entry='confirm', confirm_only=True,
                     zone_lo=close - 0.25 * atr, zone_hi=close + 0.25 * atr, zone_src=zone_src, missable=False,
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
    ttl_key = 'sd_ttl'
    uses_minutes = True

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig, d, atr = x.sig, x.direction, x.atr
        if sig.get('zone_lo') is None or not atr:
            return None
        lo, hi = sig['zone_lo'], sig['zone_hi']
        far = lo if d > 0 else hi
        zones = merge(list(x.raw_levels or []), atr, symbol=x.symbol)
        near = hi if d > 0 else lo
        targets, sources = select_targets(zones, near, d, atr, 'opposite_liquidity')
        # Seiden: a resting limit at the proximal line, the stop beyond the distal line, the zone's FIRST touch only
        plan = base_plan(x, self.name, _anchor(sig, '1h'), '1h', entry='pullback', trigger='touch', single_touch=True,
                         zone_lo=lo, zone_hi=hi, zone_src=f"{sig.get('anchor_label', 'zone')} (5m pinbar)",
                         # not missable: the zone is confirmed only once price left it by 2 ATR, so a target
                         # measured from the zone is often behind price already; his zone waits for the return
                         invalid=far, fix_invalid=True, invalid_close_min=60, missable=False, stop_ref=far,
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
    setups = {'AUCTION LONG': 1, 'AUCTION SHORT': -1}
    ttl_key = 'auction_ttl'

    def plan(self, x: PlanInput) -> Optional[Dict]:
        cfg = CONFIG.strategies
        sig = x.sig
        if sig.get('auction_stop') is None:
            return None
        exit = {'stop': ['price', sig['auction_stop']], 'stop_src': "beyond the POC test + measured pierce",
                'tp': ['level', sig.get('auction_target'), cfg.auction_min_rr, cfg.auction_fallback_rr],
                'tp_src': 'naked strong POC', 'atr': sig.get('atr_1h') or x.atr}
        return _confirm_plan(x, self.name, '1h', exit, f"POC {sig['anchor_level']:.6g} retest reaction ({sig.get('auction_kind')})")


# ------------------------------------------------------------------------------------------------ SMT

# ------------------------------------------------------------------------------------------------ trendline

def structural_stop(minutes, direction: int, entry: float, pad: float) -> Optional[float]:
    """trendline_bot structural_stop: the last confirmed 5m pivot (3 / 3) beyond the entry, else the extreme of the
    last 40 5m bars, + a 0.1 ATR(5m) pad."""
    bars = resample(minutes, 5, minutes[-1][0] + MINUTE_MS) if minutes else []
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
    """trendline_bot: two 15m closes beyond a sloped line; entry at the close, stop at the 5m structure, target the
    line's first anchor (R:R >= 1 or no trade)."""
    name = 'trendline'
    setups = {'TRENDLINE UP': 1, 'TRENDLINE DOWN': -1}
    ttl_key = 'trendline_ttl'
    uses_minutes = True

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig, d = x.sig, x.direction
        if sig.get('target_price') is None or not x.minutes:
            return None
        bars = resample(x.minutes, 5, x.minutes[-1][0] + MINUTE_MS)
        trs = [max(b[2] - b[3], abs(b[2] - p[4]), abs(b[3] - p[4])) for p, b in zip(bars, bars[1:])][-14:]
        pad = 0.1 * (sum(trs) / len(trs)) if trs else 0.0
        stop = structural_stop(x.minutes, d, sig['anchor_close'], pad)
        if stop is None:
            return None
        # classic trendline break (Edwards & Magee): the targets are the next support / resistance levels (the map), not
        # the line's first anchor (his robot's target, kept in the setup note)
        exit = {'stop': ['price', stop], 'stop_src': '5m structure beyond the entry', 'tp': ['map', 1.0]}
        return _confirm_plan(x, self.name, '15m', exit, 'trendline break (2 closes)')


# ------------------------------------------------------------------------------------------------ indicator systems

class BollingerStrategy(_System):
    """Bollinger's W-bottom / M-top (method III): entry at the close beyond the middle peak, the stop beyond the retest,
    the first target the opposite band (then the map)."""
    name = 'bollinger'
    setups = {'BB W-BOTTOM': 1, 'BB M-TOP': -1}
    ttl_key = 'bollinger_ttl'

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig = x.sig
        if sig.get('bb_stop') is None:
            return None
        exit = {'stop': ['ref', 0.0], 'stop_src': 'beyond the W / M retest',
                'tp': ['level', sig['bb_target'], 1.0, None], 'tp_src': 'the opposite Bollinger band', 'atr': x.atr}
        return _confirm_plan(x, self.name, '15m', exit, 'Bollinger W / M confirmed', stop_ref=sig['bb_stop'])


MANIAC_STRATEGIES: List[Strategy] = [SupplyDemandStrategy(), AuctionStrategy(), TrendlineStrategy(),
                                     BollingerStrategy()]
