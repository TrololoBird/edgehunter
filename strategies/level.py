"""
Level strategies: the anchor is a price level and the extreme made at it, not a leg (no Fibonacci).

- sweep (SWEEP LOW / SWEEP HIGH): a closed 15m candle pierces a higher-timeframe resting-stop pool (structure.py) -
  at most the pool kind's measured pierce p90 (no minimum with the pierce model) - and closes back beyond it on
  volume. Bias: the weekly bias, else the daily, else the coin's trend (context_veto: 'against_bias' /
  'against_trend'). A raid outside a 1h+ POI ('no_htf_poi') and an entry in premium / discount of the dealing range
  ('premium' / 'discount') are SHADOW vetoes again (eng-148: eng-147 had made them blocking; audit 33: the cut and the
  kept entries lost alike, journaled until a pre-registered test decides).
- the entry (trigger 'fvg', ICT's 2022 model, eng-58): a displacement that breaks the swing the raid came from and
  leaves a gap arms the gap's CE (ict.fvg_setup); with executor.touch_confirm_close the trade opens at the CLOSE of
  the trigger candle that touched the CE and closed back on the trade's side (no resting limit).
- stop beyond the wick (and a pool behind it) + the measured pierce; targets: the draw on liquidity.
"""
import re
import math
from typing import Dict, List, Optional, Sequence

from config import CONFIG
from strategies.base import PlanInput, Strategy, base_plan
from strategies.geometry import select_targets
from strategies.structure import Pool
from zones import merge, stop_beyond

MINUTE_MS = 60_000
QUARTER_MS = 900_000


def reached_since(minutes: Sequence[Sequence[float]], since_ms: int, start: float, direction: int) -> float:
    """Furthest price in the trade's direction from `start` over the final 1m candles since `since_ms`."""
    prices = [start] + [c[2] if direction > 0 else c[3] for c in minutes if c[0] >= since_ms]
    return max(prices) if direction > 0 else min(prices)


def _level_anchor(sig: Dict, tf: str) -> Dict:
    return {'type': 'level', 'tf': tf, 'level': sig['anchor_level'], 'label': sig.get('anchor_label', ''),
            'extreme': sig['anchor_extreme'], 'ts': sig['anchor_ts']}


# ------------------------------------------------------------------------------------------------ sweep

def pool_rank(label: str) -> int:
    """Significance of a pool by its label: previous week > previous day / day > sessions, equal levels, round > 1h swing."""
    if label.startswith('PW'):
        return 5
    if label.startswith(('PD', 'day ')):
        return 4
    if label.startswith(('Asia', 'London', 'New York', 'EQ', 'round')):
        return 3
    return 1


def sweep_tf(label: str) -> str:
    """eng-84: the plan timeframe of a sweep by the swept pool: a 1h swing -> 15m (5m trigger), sessions / equal
    levels / rounds / the day / previous day / week -> 1h (15m trigger)."""
    # eng-153 (external audit #3): the raid is a 15m candle, so its confirmation is at most 15m - a 60m trigger
    # (the day / previous day / week -> 4h plan) left 109 of 113 MISSED cards "no 60m trigger" (TP1 in 15-90 min)
    rank = pool_rank(label or '')
    return '1h' if rank >= 3 else '15m'


def sweep_at_close(candles_15m: Sequence[Sequence[float]], pools: List[Pool], atr: float, trend: int,
                   symbol: Optional[str] = None) -> Optional[Dict]:
    """The candle that just closed took a pool and closed back beyond it on volume -> the sweep event."""
    cfg = CONFIG.strategies
    if len(candles_15m) < 21 or atr is None or not math.isfinite(atr) or atr <= 0:
        return None
    c = candles_15m[-1]
    avg_volume = sum(x[5] for x in candles_15m[-21:-1]) / 20
    if not math.isfinite(avg_volume) or avg_volume <= 0 or not math.isfinite(c[5]) \
            or c[5] < cfg.sweep_min_rvol * avg_volume:
        return None
    lo_depth, hi_depth = cfg.sweep_min_depth_atr * atr, cfg.sweep_max_depth_atr * atr
    best = None
    for price, side, label, formed in pools:
        if c[0] - formed < cfg.sweep_pool_min_age_sec * 1000 or formed > c[0]:
            continue
        if not cfg.sweep_round_pools and (label or '').startswith('round'):
            continue
        if side > 0:
            depth, back = c[2] - price, c[4] < price
        else:
            depth, back = price - c[3], c[4] > price
        # one candle can take several pools: the most significant one names the sweep (a week low taken with a
        # minor 1h swing is a week-low sweep), the shallowest among equals
        # the deepest a sweep may go: the usual pierce of this kind of level on this coin (p90, pierce.py), not
        # 1 ATR - deeper and back is a failed breakout, not a raid of the stops just beyond
        from pierce import kind_of_label, overshoot
        measured = overshoot(symbol, kind_of_label(label), price, 'p90')
        limit = measured if measured is not None else hi_depth
        # any trade beyond the pool takes the stops resting right behind it (ICT); the volume and the close back
        # filter weak pokes - the 0.1 ATR minimum only without the pierce model
        floor = 0.0 if measured is not None else lo_depth
        if back and floor < depth <= limit and (best is None or (pool_rank(label), -depth) > (pool_rank(best[3]), -best[0])):
            best = (depth, price, side, label, formed)
    if best is None:
        return None
    depth, price, side, label, formed = best
    direction = -side
    extreme = c[2] if side > 0 else c[3]
    return {'setup': 'SWEEP LOW' if direction > 0 else 'SWEEP HIGH', 'direction': direction,
            'setup_note': f"15m swept {label} {price:.6g} by {depth / atr:.2f} ATR on {c[5] / avg_volume:.1f}x volume, "
                          f"closed back {'above' if direction > 0 else 'below'}",
            'anchor_level': price, 'anchor_label': label, 'anchor_extreme': extreme, 'anchor_ts': int(c[0]),
            'anchor_close': c[4], 'pool_formed_ms': int(formed), 'event_ts': int(c[0]) + QUARTER_MS,
            # eng-108: the values the removed thresholds read, journaled for a later look at them
            'sweep_rvol': c[5] / avg_volume if avg_volume else None, 'sweep_depth_atr': depth / atr,
            'pool_age_h': (c[0] - formed) / 3_600_000}


class SweepStrategy(Strategy):
    name = 'sweep'
    anchor_type = 'level'
    setups = {'SWEEP LOW': 1, 'SWEEP HIGH': -1}
    ttl_key = 'sweep_ttl'

    def ttls(self, tf: str):
        # eng-84: a sweep of a daily / weekly pool is a 1h / 4h trade - its waiting and its trade last as many times
        # longer as its timeframe (levels.TTL_FACTOR: 15m x1, 1h x2, 4h x4)
        from levels import TTL_FACTOR
        k = TTL_FACTOR.get(tf, 1)
        return tuple(v * k for v in super().ttls(tf))

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('anchor_ts'), x.sig.get('anchor_level')) if x.sig.get('anchor_level') is not None else None

    def context_veto(self, sig: Dict, direction: int) -> Optional[str]:
        # ICT: a sweep is traded in the direction of the higher-timeframe bias (the daily one); with no daily bias the
        # coin's 1h trend decides, as before
        # ICT's top-down order: the weekly bias first, the daily one when the week has none
        # eng-148: shadow again (strategies.shadow_vetoes: against_bias / against_trend)
        bias = sig.get('weekly_bias') or sig.get('daily_bias')
        if bias:
            return 'against_bias' if bias == -direction else None
        # eng-150 (plan 4.1): ICT's top-down order has no 1h substitute - no weekly / daily bias, no trade; eng-151
        # (external audit #1): shadow (strategies.shadow_vetoes) - blocking it lost the outcome and against_bias trades
        if CONFIG.strategies.sweep_bias_required and sig.get('coin_trend') == -direction:
            from signal_book import shadow_veto
            # review eng-151: with the bias veto in shadow the 1h trend is still journaled
            shadow_veto(sig, 'against_trend')
        return 'sweep_no_htf_bias' if CONFIG.strategies.sweep_bias_required else \
            ('against_trend' if sig.get('coin_trend') == -direction else None)

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig, d, atr = x.sig, x.direction, x.atr
        if sig.get('anchor_level') is None or not atr:
            return None
        level, extreme = sig['anchor_level'], sig['anchor_extreme']
        zones = merge(list(x.raw_levels or []), atr, symbol=x.symbol)
        # ICT's three layers: the bias (context_veto), the ZONE - the raid ran into a point of interest of 1h or higher
        # (order block, FVG, BPR, breaker), and the entry (5m FVG). A raid in empty space is no ICT setup.
        poi = [z for z in zones if any(re.match(r'(ob|fvg|bpr|breaker)_(1h|4h|1d|1w)$', k) for k in z.kinds)
               and z.lo <= max(extreme, level) and z.hi >= min(extreme, level)]
        from signal_book import shadow_veto
        if not poi:
            # eng-148: shadow again (eng-107; eng-147 had made it blocking without an out-of-sample test)
            shadow_veto(sig, 'no_htf_poi')
        # premium / discount of the dealing range (1h pivots, ict.dealing_range): longs only in its discount half, shorts only in its premium
        from strategies.ict import dealing_range, range_position
        # eng-150 (plan 4.2): the dealing range of the swept pool's timeframe - a weekly pool in the daily range, a
        # daily / day pool in the 4h one, the rest in the 1h one (closed candles only); still a shadow veto
        rank = pool_rank(sig.get('anchor_label', '') or '')
        range_tf = '1d' if rank >= 5 else '4h' if rank == 4 else '1h'
        rows = {'1d': x.d1, '4h': x.h4}.get(range_tf)
        if not rows:
            range_tf, rows = '1h', x.h1 or []          # no 4h / daily history yet: journaled as the 1h range
        rng = dealing_range(rows)
        pos = range_position(rng, extreme, d)
        if pos is not None and pos > 0.5:
            shadow_veto(sig, 'premium' if d > 0 else 'discount')     # eng-148: shadow again
        sig['range_tf'] = range_tf
        sig['range_pos_tf'] = pos                       # paired with range_pos_1h: both at the raid's extreme
        sig['range_pos_1h'] = range_position(dealing_range(x.h1 or []), extreme, d)
        # eng-150 (plan 4.3): an untaken pool within zone_move_pool_atr of the structure ATR beyond the extreme is
        # journaled (zone_moved) only: the 'fvg' trigger enters at the 5m FVG's CE and never reads the zone, so moving
        # the zone onto that pool would only have widened the stop past the next pool (review eng-150)
        tf = sweep_tf(sig.get('anchor_label', ''))
        tf_atr = (x.tf_atr or {}).get(tf) if tf != '15m' else atr
        moved = None
        if tf_atr:
            from zones import STOP_POOL_KINDS, STOP_SWINGS, swept_zone
            kinds = STOP_POOL_KINDS + STOP_SWINGS
            cand = [z for z in zones if any(k in kinds for k in z.kinds) and not swept_zone(z, kinds)
                    and 0 < d * (extreme - (z.hi if d > 0 else z.lo)) <= CONFIG.strategies.zone_move_pool_atr * tf_atr]
            if cand:
                moved = max(cand, key=lambda z: z.hi) if d > 0 else min(cand, key=lambda z: z.lo)
        sig['zone_moved'] = moved.label if moved else None
        sig['zone_move_atr'] = round(d * (extreme - (moved.hi if d > 0 else moved.lo)) / tf_atr, 3) if moved else None
        # eng-152 (live eng-151: 41 of 44 INVALID sweep cards had the nearest-pool stop, median life 16 min against
        # 135; 26 of them never reached the old one): 4.3 back to shadow - the live stop beyond the farthest pool,
        # the nearest-pool invalidation journaled as sl_near
        base, _ = stop_beyond(zones, extreme, extreme, d, atr, symbol=x.symbol, farthest=True)
        near, _ = stop_beyond(zones, extreme, extreme, d, atr, symbol=x.symbol)
        from pierce import overshoot as _pierce
        from strategies.geometry import capped_pad
        # eng-147: past a further pool only the small pad, else the measured pierce capped in ATR (no double buffer)
        pad, _ = capped_pad(_pierce(x.symbol, 'swing_15m', base), atr, base != extreme)
        invalid = base - d * (pad if pad is not None else CONFIG.levels.stop_buffer_atr * atr)
        sig['sl_old'] = invalid                         # the farthest-pool stop is the live one since eng-152
        npad, _ = capped_pad(_pierce(x.symbol, 'swing_15m', near), atr, near != extreme)
        sig['sl_near'] = near - d * (npad if npad is not None else CONFIG.levels.stop_buffer_atr * atr)
        pool2 = None
        if moved is not None:
            # eng-151 (external audit #2), shadow only: a resting limit at the next pool's liquidity (the second raid),
            # the plan's stop rule from that pool - 'variant_pool2' against the live entry of the same card
            # live check eng-151: the merged zone's far edge (a VAL / OB / round number below the pool) was never
            # touched - the entry is the pool's own untaken price, the first one a second raid meets
            prices = [p[1] for p in moved.parts if p[0] in kinds and not p[4]]
            p2 = (max(prices) if d > 0 else min(prices)) if prices else (moved.hi if d > 0 else moved.lo)
            pool2 = {'entry': p2, 'label': moved.label}
        reached = x.reached if x.reached is not None else reached_since(x.minutes, sig['event_ts'], sig['anchor_close'], d)
        # eng-166: the entry needs a structure shift beyond the swing the raid came from (ict.fvg_setup on the trigger
        # timeframe); a TP1 at or before that swing is reached before any entry can exist (live 15:12-22:00: 29 of 39
        # MISSED cards had TP1 inside the MSS level). The targets are drawn from beyond it - ICT's draw after the shift
        # is the liquidity past the broken structure.
        from levels import TRIGGER_MINUTES, resample
        from strategies.ict import raid_swing
        trig_min = TRIGGER_MINUTES.get(tf, 5)
        mss = None
        if x.minutes:
            ltf = resample(x.minutes, trig_min, x.minutes[-1][0] + 60_000)
            mss = raid_swing(ltf, d, int(sig['anchor_ts']), trig_min * 60_000)
        sig['mss_level'] = mss
        start = reached if mss is None else (max(reached, mss) if d > 0 else min(reached, mss))
        targets, sources = select_targets(zones, start, d, atr, 'draw_liquidity')
        # ICT: the sweep is only the setup, a wick is not yet a reversal: the entry waits for the displacement's FVG
        # (trigger 'fvg') inside the sweep's area
        close = sig.get('anchor_close', level)
        # the sweep candle itself is the area: its wick to its close (or the level, whichever is further); no ATR pad
        edge = max(close, level) if d > 0 else min(close, level)
        zone = sorted((extreme, edge))
        # ICT: after the sweep, displacement with a fair value gap and a structure shift; the entry is the retrace into
        # that gap (5m), not the shift's close
        # eng-84: the structure shift is read on the timeframe that matches the swept pool (the sweep write-ups: 1h
        # levels -> 5m, 4h / session / daily levels -> 15m, daily / weekly levels -> 1h; below 30m most sweeps are
        # false): the plan's timeframe sets the trigger's (levels.TRIGGER_MINUTES 15m -> 5, 1h -> 15, 4h -> 60)
        zone_src = f"sweep of {sig.get('anchor_label', 'the level')} (5m FVG retrace)"
        plan = base_plan(x, self.name, _level_anchor(sig, tf), tf, entry='pullback', trigger='fvg', zone_lo=zone[0],
                         zone_hi=zone[1], zone_src=zone_src,
                         invalid=invalid,
                         fix_invalid=True, missable=True, stop_ref=extreme, intent='draw_liquidity',
                         targets=targets, target_src=sources, zones=zones, reached=reached,
                         key=(sig['anchor_ts'], level))
        if plan is not None:
            plan['dealing_range'] = rng
            plan['range_tf'] = range_tf
            plan['pool2'] = pool2
            plan['stop_farthest'] = True                # eng-152: the entry's stop by the same rule as invalid
        return plan
