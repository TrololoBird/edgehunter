"""
Level strategies: the anchor is a price level and the extreme made at it, not a leg (no Fibonacci).

- sweep (SWEEP LOW / SWEEP HIGH): a closed 15m candle pierces a higher-timeframe resting-stop pool (structure.py) by
  sweep_min_depth_atr-sweep_max_depth_atr and closes back beyond it on volume. Entry at the confirmation (R:R allowing),
  else a retest of the level with a 5m structure shift; stop beyond the wick (and a pool behind it); targets: the
  opposite liquidity. A sweep against the coin's 1h trend is vetoed ('against_trend'): with the trend a sweep is a
  shakeout before the move resumes, against it the first counter-trend break usually fails (and live: sweeps of highs
  in a rising market -0.35R a trade, sweeps of lows +0.36R).
- absorption (ABSORB BID / ABSORB ASK): a 1m candle where aggression into a significant level (a higher-timeframe pool,
  a strong map zone, a book liquidity band) traded heavy volume without moving price, after a move into it. Entry on
  a 5m structure shift from the level; stop beyond the absorption extreme; targets: the mean (VWAP / POC / nodes).
"""
from typing import Dict, List, Optional, Sequence

from config import CONFIG
from strategies.base import PlanInput, Strategy, base_plan
from strategies.geometry import select_targets
from strategies.structure import Pool
from zones import RawLevel, merge, stop_beyond

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


def sweep_at_close(candles_15m: Sequence[Sequence[float]], pools: List[Pool], atr: float, trend: int,
                   symbol: Optional[str] = None) -> Optional[Dict]:
    """The candle that just closed took a pool and closed back beyond it on volume -> the sweep event."""
    cfg = CONFIG.strategies
    if len(candles_15m) < 21 or not atr:
        return None
    c = candles_15m[-1]
    avg_volume = sum(x[5] for x in candles_15m[-21:-1]) / 20
    if avg_volume and c[5] < cfg.sweep_min_rvol * avg_volume:
        return None
    lo_depth, hi_depth = cfg.sweep_min_depth_atr * atr, cfg.sweep_max_depth_atr * atr
    best = None
    for price, side, label, formed in pools:
        if c[0] - formed < cfg.sweep_pool_min_age_sec * 1000:
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
            best = (depth, price, side, label)
    if best is None:
        return None
    depth, price, side, label = best
    direction = -side
    extreme = c[2] if side > 0 else c[3]
    return {'setup': 'SWEEP LOW' if direction > 0 else 'SWEEP HIGH', 'direction': direction,
            'setup_note': f"15m swept {label} {price:.6g} by {depth / atr:.2f} ATR on {c[5] / avg_volume:.1f}x volume, "
                          f"closed back {'above' if direction > 0 else 'below'}",
            'anchor_level': price, 'anchor_label': label, 'anchor_extreme': extreme, 'anchor_ts': int(c[0]),
            'anchor_close': c[4], 'event_ts': int(c[0]) + QUARTER_MS}


class SweepStrategy(Strategy):
    name = 'sweep'
    anchor_type = 'level'
    setups = {'SWEEP LOW': 1, 'SWEEP HIGH': -1}
    ttl_key = 'sweep_ttl'

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('anchor_ts'), x.sig.get('anchor_level')) if x.sig.get('anchor_level') is not None else None

    def context_veto(self, sig: Dict, direction: int) -> Optional[str]:
        # ICT: a sweep is traded in the direction of the higher-timeframe bias (the daily one); with no daily bias the
        # coin's 1h trend decides, as before
        bias = sig.get('daily_bias')
        if bias:
            return 'against_bias' if bias == -direction else None
        return 'against_trend' if sig.get('coin_trend') == -direction else None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig, d, atr = x.sig, x.direction, x.atr
        if sig.get('anchor_level') is None or not atr:
            return None
        level, extreme = sig['anchor_level'], sig['anchor_extreme']
        zones = merge(list(x.raw_levels or []), atr, symbol=x.symbol)
        base, _ = stop_beyond(zones, extreme, extreme, d, atr, symbol=x.symbol)
        invalid = base - d * CONFIG.levels.stop_buffer_atr * atr
        reached = x.reached if x.reached is not None else reached_since(x.minutes, sig['event_ts'], sig['anchor_close'], d)
        targets, sources = select_targets(zones, reached, d, atr, 'opposite_liquidity')
        # ICT: the sweep is only the setup, a wick is not yet a reversal. The entry waits for the 5m market structure
        # shift (a break of the last 5m swing with agreeing taker flow) inside the sweep's area: from the wick to the
        # sweep candle's close (+ a buffer), so the shift right after the sweep and a later retrace both qualify
        close = sig.get('anchor_close', level)
        # the sweep candle itself is the area: its wick to its close (or the level, whichever is further); no ATR pad
        edge = max(close, level) if d > 0 else min(close, level)
        zone = sorted((extreme, edge))
        # ICT: after the sweep, displacement with a fair value gap and a structure shift; the entry is the retrace into
        # that gap (5m), not the shift's close
        return base_plan(x, self.name, _level_anchor(sig, '15m'), '15m', entry='pullback', trigger='fvg', zone_lo=zone[0],
                         zone_hi=zone[1], zone_src=f"sweep of {sig.get('anchor_label', 'the level')} (5m FVG retrace)",
                         invalid=invalid,
                         fix_invalid=True, missable=True, stop_ref=extreme, intent='opposite_liquidity',
                         targets=targets, target_src=sources, zones=zones, reached=reached,
                         key=(sig['anchor_ts'], level))


# ------------------------------------------------------------------------------------------------ absorption

def absorption_at(minutes: Sequence[Sequence[float]], c: Sequence[float], levels: List[tuple], atr: float,
                  avg_minute: float) -> Optional[Dict]:
    """
    A closed 1m candle `c`: heavy aggression (delta >= the hour's percentile, volume >= absorption_min_rvol x the
    average minute) with a range <= absorption_max_move_atr, its extreme at a significant level, after a move of
    >= absorption_min_move_atr into it over the last hour. `levels`: [(price, label)].
    """
    cfg = CONFIG.strategies
    of = CONFIG.orderflow
    history = [x for x in minutes if c[0] - 60 * MINUTE_MS <= x[0] < c[0]]
    if len(history) < 20 or not atr or not avg_minute:
        return None
    deltas = sorted(abs(2 * x[6] - x[5]) for x in history)
    threshold = deltas[min(len(deltas) - 1, int(of.absorption_percentile * len(deltas)))]
    delta = 2 * c[6] - c[5]
    if abs(delta) < threshold or c[5] < cfg.absorption_min_rvol * avg_minute or c[2] - c[3] > of.absorption_max_move_atr * atr:
        return None
    direction = -1 if delta > 0 else 1                  # sellers absorbed -> long; buyers absorbed -> short
    extreme = c[3] if direction > 0 else c[2]
    tol = cfg.absorption_level_atr * atr
    near = [(p, lab) for p, lab in levels if abs(p - extreme) <= tol]
    if not near:
        return None
    price, label = min(near, key=lambda pl: abs(pl[0] - extreme))
    start = max(x[2] for x in history) if direction > 0 else min(x[3] for x in history)
    if abs(start - extreme) < cfg.absorption_min_move_atr * atr:
        return None
    side = 'sellers' if direction > 0 else 'buyers'
    return {'setup': 'ABSORB BID' if direction > 0 else 'ABSORB ASK', 'direction': direction,
            'setup_note': f"{side} {abs(delta) / 1e3:,.0f}k absorbed at {label} {price:.6g} "
                          f"(vol {c[5] / avg_minute:.1f}x, range {(c[2] - c[3]) / atr:.2f} ATR)",
            'anchor_level': price, 'anchor_label': label, 'anchor_extreme': extreme, 'anchor_ts': int(c[0]),
            'anchor_close': c[4], 'event_ts': int(c[0]) + MINUTE_MS}


class AbsorptionStrategy(Strategy):
    name = 'absorption'
    anchor_type = 'level'
    setups = {'ABSORB BID': 1, 'ABSORB ASK': -1}
    ttl_key = 'absorption_ttl'

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('anchor_ts'), x.sig.get('anchor_level')) if x.sig.get('anchor_level') is not None else None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig, d, atr = x.sig, x.direction, x.atr
        if sig.get('anchor_level') is None or not atr:
            return None
        level, extreme = sig['anchor_level'], sig['anchor_extreme']
        zones = merge(list(x.raw_levels or []) + [RawLevel(level, 'hvn', sig.get('anchor_label', 'level'))], atr, symbol=x.symbol)
        base, _ = stop_beyond(zones, extreme, extreme, d, atr, symbol=x.symbol)
        invalid = base - d * CONFIG.levels.stop_buffer_atr * atr
        reached = x.reached if x.reached is not None else reached_since(x.minutes, sig['event_ts'], sig['anchor_close'], d)
        targets, sources = select_targets(zones, reached, d, atr, 'mean')
        zone = sorted((extreme, level + d * CONFIG.strategies.absorption_zone_atr * atr))
        return base_plan(x, self.name, _level_anchor(sig, '15m'), '15m', entry='pullback', zone_lo=zone[0],
                         zone_hi=zone[1], zone_src=f"absorbed at {sig.get('anchor_label', 'the level')}", invalid=invalid,
                         fix_invalid=True, missable=True, stop_ref=extreme, intent='mean', targets=targets,
                         target_src=sources, zones=zones, reached=reached, key=(sig['anchor_ts'], level))
