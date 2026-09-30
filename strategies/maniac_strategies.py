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
    zones = merge(list(x.raw_levels or []), atr)
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
        zones = merge(list(x.raw_levels or []), atr)
        near = hi if d > 0 else lo
        targets, sources = select_targets(zones, near, d, atr, 'opposite_liquidity')
        plan = base_plan(x, self.name, _anchor(sig, '15m'), '15m', entry='pullback', trigger='pinbar',
                         zone_lo=lo, zone_hi=hi, zone_src=f"{sig.get('anchor_label', 'zone')} (5m pinbar)",
                         # not missable: the zone is confirmed only once price left it by 2 ATR, so a target
                         # measured from the zone is often behind price already; his zone waits for the return
                         invalid=far, fix_invalid=True, invalid_close_min=15, missable=False, stop_ref=far,
                         exit={'stop': ['ref', 0.0], 'tp': ['map', 0.0], 'atr': atr,
                               'stop_src': 'beyond the pinbar and the zone'},
                         intent='opposite_liquidity', targets=targets, target_src=sources, zones=zones,
                         key=(sig['anchor_ts'], near))
        return plan


# ------------------------------------------------------------------------------------------------ auction

class AuctionStrategy(_System):
    """auction_theory_in_code: a POC retest reacted on 1h; entry at that close, stop beyond the test's extreme + 0.35
    ATR, target the nearest strong untested POC (skipped below 1.5 R), else 2.5 R."""
    name = 'auction'
    setups = {'AUCTION LONG': 1, 'AUCTION SHORT': -1}
    ttl_key = 'auction_ttl'

    def plan(self, x: PlanInput) -> Optional[Dict]:
        cfg = CONFIG.strategies
        sig = x.sig
        if sig.get('auction_stop') is None:
            return None
        exit = {'stop': ['price', sig['auction_stop']], 'stop_src': f"beyond the POC test + {cfg.auction_stop_pad_atr:g} ATR",
                'tp': ['level', sig.get('auction_target'), cfg.auction_min_rr, cfg.auction_fallback_rr],
                'tp_src': 'naked strong POC', 'atr': sig.get('atr_1h') or x.atr}
        return _confirm_plan(x, self.name, '1h', exit, f"POC {sig['anchor_level']:.6g} retest reaction ({sig.get('auction_kind')})")


# ------------------------------------------------------------------------------------------------ SMT

class SmtStrategy(_System):
    """lllll: the 2-candle sweep with SMT / QM on 15m; entry on a 5m inversion FVG within 8 main candles (NY 02-10
    session), stop beyond the sweep's extreme + 0.1 ATR, target the opposite pool (>= 2 R) else 2.5 R; a 15m close
    beyond the swept level cancels it."""
    name = 'smt'
    setups = {'SMT LOW': 1, 'SMT HIGH': -1}
    ttl_key = 'smt_ttl'
    uses_minutes = True

    def plan(self, x: PlanInput) -> Optional[Dict]:
        cfg = CONFIG.strategies
        sig, atr = x.sig, x.atr
        if sig.get('anchor_level') is None or not atr:
            return None
        level, extreme, opposite = sig['anchor_level'], sig['anchor_extreme'], sig['opposite_pool']
        zone = sorted((extreme, opposite))
        exit = {'stop': ['ref', cfg.smt_sl_buffer_atr], 'stop_src': 'beyond the sweep', 'atr': sig.get('atr_main') or atr,
                'tp': ['level', opposite, cfg.smt_min_rr, cfg.smt_fallback_rr], 'tp_src': 'opposite external pool',
                'fallback_when_close': True}
        plan = base_plan(x, self.name, _anchor(sig, '15m'), '15m', entry='pullback', trigger='ifvg',
                         trigger_from_ms=sig['anchor_ts'], zone_lo=zone[0], zone_hi=zone[1],
                         zone_src=f"after the sweep of {sig.get('anchor_label', 'the pool')} (5m iFVG)",
                         invalid=level, fix_invalid=True, invalid_close_min=15, missable=False, stop_ref=extreme,
                         session=tuple(cfg.smt_session) if cfg.smt_session else None, exit=exit,
                         zones=merge(list(x.raw_levels or []), atr), targets=[], target_src=[],
                         key=(sig['anchor_ts'], level))
        return _finish(x, plan, sig['anchor_close'], extreme)


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
        exit = {'stop': ['price', stop], 'stop_src': '5m structure beyond the entry',
                'tp': ['level', sig['target_price'], CONFIG.strategies.tl_min_rr, None], 'tp_src': "the line's first anchor"}
        return _confirm_plan(x, self.name, '15m', exit, 'trendline break (2 closes)')


# ------------------------------------------------------------------------------------------------ indicator systems

class ThirdEyeStrategy(_System):
    """thirdeye_strategy_algo: CCI + Ichimoku + EMA200 + filters on 1h; entry at the close, SL 1%, TP 5% (his live
    breakeven at +2% is journaled as r_be)."""
    name = 'thirdeye'
    setups = {'THIRD EYE LONG': 1, 'THIRD EYE SHORT': -1}
    ttl_key = 'thirdeye_ttl'

    def plan(self, x: PlanInput) -> Optional[Dict]:
        cfg = CONFIG.strategies
        # 'atr' = the 1h ATR: a 1h system's stop floor is measured on its own timeframe
        exit = {'stop': ['pct', cfg.te_sl_pct], 'tp': ['pct', cfg.te_tp_pct], 'atr': x.sig.get('atr_1h') or x.atr}
        return _confirm_plan(x, self.name, '1h', exit, 'CCI cross with Ichimoku / EMA200 filters')


class Fib05Strategy(_System):
    """fibonachi_trading_system: a pierce of the 1h impulse's 0.5 closed back; entry at the close, stop at the impulse's
    start; his trailing stop starts at the impulse's end (TP1 here), then trails half the impulse."""
    name = 'fib05'
    setups = {'FIB 0.5 LONG': 1, 'FIB 0.5 SHORT': -1}
    ttl_key = 'fib05_ttl'

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig = x.sig
        if sig.get('impulse_start') is None:
            return None
        exit = {'stop': ['price', sig['impulse_start']], 'stop_src': "the impulse's start",
                'tp': ['level', sig['impulse_end'], 0.0, None], 'tp_src': "impulse end (his trailing starts)"}
        return _confirm_plan(x, self.name, '1h', exit, 'pierce of the 0.5 closed back')


class BombermanStrategy(_System):
    """bomberman_bot: MACD cross + EMA100 + QML on 1h; entry at the close, stop 1.5 ATR(14), target 2 R."""
    name = 'bomberman'
    setups = {'BOMBERMAN LONG': 1, 'BOMBERMAN SHORT': -1}
    ttl_key = 'bomberman_ttl'

    def plan(self, x: PlanInput) -> Optional[Dict]:
        exit = {'stop': ['atr', 1.5], 'tp': ['rr', 2.0], 'atr': x.sig.get('atr_1h') or x.atr}
        return _confirm_plan(x, self.name, '1h', exit, 'MACD cross after a QML')


class CsiStrategy(_System):
    """bollinger_bands-with-clusters v6: close beyond BB in a CSI cluster; entry at the close, SL 0.4%, out after 3
    15m bars (the card's trade lifetime); a 3 R cap stands in for his missing target."""
    name = 'csi'
    setups = {'CSI LONG': 1, 'CSI SHORT': -1}
    ttl_key = 'csi_ttl'

    def plan(self, x: PlanInput) -> Optional[Dict]:
        exit = {'stop': ['pct', CONFIG.strategies.csi_sl_pct], 'tp': ['rr', 3.0]}
        return _confirm_plan(x, self.name, '15m', exit, 'Bollinger + CSI cluster')


class OiAccumulationStrategy(_System):
    """oi_trading_robot v7.4 (long only): OI building without price; market entry, SL 2%, TP 4% / 6% (his defaults)."""
    name = 'oi_accum'
    setups = {'OI ACCUMULATION': 1}
    ttl_key = 'oi_accum_ttl'

    def plan(self, x: PlanInput) -> Optional[Dict]:
        cfg = CONFIG.strategies
        exit = {'stop': ['pct', cfg.oi_sl_pct], 'tp': ['pct', cfg.oi_tp_pcts[0]], 'tp2': ['pct', cfg.oi_tp_pcts[-1]],
                'atr': x.sig.get('atr_1h') or x.atr}
        return _confirm_plan(x, self.name, '15m', exit, 'OI +5%/1h without price')


MANIAC_STRATEGIES: List[Strategy] = [SupplyDemandStrategy(), AuctionStrategy(), SmtStrategy(), TrendlineStrategy(),
                                     ThirdEyeStrategy(), Fib05Strategy(), BombermanStrategy(), CsiStrategy(),
                                     OiAccumulationStrategy()]
