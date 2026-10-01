"""
Detectors of crypto_maniac's trading systems (github.com/roman-boop), ported rule for rule onto our candles
[open_time, open, high, low, close, quote_volume, taker_buy_quote]. Each fires on the candle that just closed (the
maps worker runs them after every 15m close; the 1h systems when an hour closed), so an event fires once.

    system (his repo)                    tf        event                                    entry / exit (his)
    supply_demand-v4                     15m / 5m  a demand / supply zone confirmed         5m pinbar retest, stop beyond
                                                                                             the pinbar and the zone
    auction_theory_in_code               1h        POC retest reacted (auction_engine.py)   at the close, naked POC / 2.5R
    lllll (SMT / Quasimodo)              15m / 5m  2-candle sweep of an external pool       5m inversion FVG, opposite
                                                   + SMT vs BTC (ETH for BTC) or QM          pool (>= 2R) else 2.5R
    trendline_bot                        15m       2 closes beyond a sloped line            at the close, first anchor
    thirdeye_strategy_algo               1h        CCI(25) crossing +-98 + Ichimoku, EMA200, at the close, SL 1% TP 5%
                                                   ADX / RSI / NATR / BBW filters
    fibonachi_trading_system             1h        a candle pierces the impulse's 0.5 and    at the close, stop beyond
                                                   closes back                               the impulse, its extreme
    bomberman_bot                        1h        MACD cross + EMA100 side + QML + BBW      at the close, 1.5 ATR / 2R
    bollinger_bands-with-clusters        15m       close beyond BB(40, 1.5) in a CSI         at the close, SL 0.4%,
                                                   cluster of the same side + RSI(96)        out after 3 bars
    oi_trading_robot v7.4                1m/5m OI  OI +5%/1h, price <= half of it, OI 24h    long, ATR stop / targets
                                                   above price 24h, 15m higher lows          (strategies/maniac_oi)

Fixes of his code (the ideas as written, not the slips): Third Eye's realtime filters `(~use_x or cond)` are always
true in Python (~True == -2), so his live bot traded the CCI cross alone - here the filters apply as in his backtest.
"""
import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from config import CONFIG

HOUR_MS = 3_600_000
QUARTER_MS = 900_000


# ------------------------------------------------------------------------------------------------ helpers

def _arr(candles: Sequence[Sequence[float]], k: int) -> np.ndarray:
    return np.asarray([c[k] for c in candles], dtype=float)


def true_range(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
    prev = np.concatenate([[c[0]], c[:-1]])
    return np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))


def wilder(x: np.ndarray, n: int) -> np.ndarray:
    """RMA / Wilder smoothing (pandas ewm(alpha=1/n, adjust=False))."""
    out = np.empty_like(x)
    acc = x[0]
    a = 1.0 / n
    for i, v in enumerate(x):
        acc = v if i == 0 else acc + a * (v - acc)
        out[i] = acc
    return out


def ema(x: np.ndarray, span: int) -> np.ndarray:
    out = np.empty_like(x)
    k = 2.0 / (span + 1)
    acc = x[0]
    for i, v in enumerate(x):
        acc = v if i == 0 else acc + k * (v - acc)
        out[i] = acc
    return out


def rolling_mean(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan)
    if len(x) >= n:
        cs = np.cumsum(np.insert(x, 0, 0.0))
        out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def _windows(x: np.ndarray, n: int):
    from numpy.lib.stride_tricks import sliding_window_view
    return sliding_window_view(x, n) if len(x) >= n else None


def rolling_std(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan)
    w = _windows(x, n)
    if w is not None:
        out[n - 1:] = w.std(axis=1, ddof=1)
    return out


def rolling_max(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan)
    w = _windows(x, n)
    if w is not None:
        out[n - 1:] = w.max(axis=1)
    return out


def rolling_min(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan)
    w = _windows(x, n)
    if w is not None:
        out[n - 1:] = w.min(axis=1)
    return out


def is_bull_pinbar(o: float, h: float, l: float, c: float) -> bool:
    """His rejection candle (supply_demand-v4 is_bullish_pinbar_df): body <= 35% of the range, a bullish close, the
    lower wick >= 55% of the range and >= 2x the upper wick."""
    span = h - l
    if span <= 0 or abs(c - o) > 0.35 * span or c <= o:
        return False
    lower, upper = min(o, c) - l, h - max(o, c)
    return lower >= 0.55 * span and lower >= 2 * upper


def is_bear_pinbar(o: float, h: float, l: float, c: float) -> bool:
    span = h - l
    if span <= 0 or abs(c - o) > 0.35 * span or c >= o:
        return False
    upper, lower = h - max(o, c), min(o, c) - l
    return upper >= 0.55 * span and upper >= 2 * lower


def in_session(ts_ms: int, session: Tuple[str, ...]) -> bool:
    """Inside any of the session's [start, end) windows of the day in its time zone: (tz, start, end[, start, end...])
    (DST handled; windows across midnight too)."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    tz = session[0]
    local = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone(ZoneInfo(tz))
    cur = local.hour * 60 + local.minute
    for start, end in zip(session[1::2], session[2::2]):
        lo = int(start[:2]) * 60 + int(start[3:])
        hi = int(end[:2]) * 60 + int(end[3:])
        if lo == hi or (lo <= cur < hi if lo < hi else (cur >= lo or cur < hi)):
            return True
    return False


# ------------------------------------------------------------------------------------------------ supply / demand

def _sd_departure(c15, i: int, zone: Dict, atr: float, kind: str) -> Optional[Tuple[int, float]]:
    cfg = CONFIG.strategies
    first = c15[i + 1]
    body = abs(first[4] - first[1])
    if body < 0.55 * atr:
        return None
    future = range(i + 1, min(len(c15), i + cfg.sd_lookahead + 1))
    if zone['type'] > 0:
        if first[4] <= first[1] or first[4] <= zone['high'] + 0.15 * atr:
            return None
        dist = {j: c15[j][4] - zone['high'] for j in future}
    else:
        if first[4] >= first[1] or first[4] >= zone['low'] - 0.15 * atr:
            return None
        dist = {j: zone['low'] - c15[j][4] for j in future}
    confirmed = [j for j in future if dist[j] >= cfg.sd_min_move_atr * atr]
    if not confirmed:
        return None
    j = confirmed[0]
    score = min(4.0, dist[j] / atr) + min(1.5, body / atr) + (1.0 if kind in ('order', 'base') else 0.5)
    return j, round(score, 2)


def sd_zone_events(c15: Sequence[Sequence[float]], period_ms: int = QUARTER_MS, tf: str = '15m') -> List[Dict]:
    """
    supply_demand-v4 find_supply_demand_zones, the zones CONFIRMED by the candle that just closed. The source candle is
    the last counter-trend candle (an order block) or a rejection pinbar at a local extreme reached by a >= 0.75 ATR
    approach over 6 bars; the next candle departs with a body >= 0.55 ATR and a close >= 2 ATR beyond the zone comes
    within 4 bars; zone height <= 1.2 ATR; score >= 3.5 (strength of the departure + body + kind). ATR(20) of the
    candles BEFORE the source candle.
    """
    cfg = CONFIG.strategies
    n = len(c15)
    if n < cfg.sd_atr_period + cfg.sd_prior_bars + 3:
        return []
    h, l, c = _arr(c15, 2), _arr(c15, 3), _arr(c15, 4)
    tr = true_range(h, l, c)
    zones = []
    for i in range(max(cfg.sd_atr_period + cfg.sd_prior_bars, n - 1 - cfg.sd_lookahead), n - 1):
        atr = float(tr[i - cfg.sd_atr_period:i].mean())
        if not atr > 0:
            continue
        # Sam Seiden's base: 1-6 "boring" candles (body <= half the candle) right before the departure; demand =
        # lowest wick (distal) to the highest body (proximal), supply mirrored. (The order-block / pinbar source of
        # the ported code was ICT's, not Seiden's.)
        k = i
        while k >= 0 and i - k < 6 and c15[k][2] > c15[k][3] \
                and abs(c15[k][4] - c15[k][1]) <= 0.5 * (c15[k][2] - c15[k][3]):
            k -= 1
        base = c15[k + 1:i + 1]
        if not base:
            continue
        candidates = [(1, 'base'), (-1, 'base')]
        for side, kind in candidates:
            if side > 0:
                low, high = min(x[3] for x in base), max(max(x[1], x[4]) for x in base)
            else:
                low, high = min(min(x[1], x[4]) for x in base), max(x[2] for x in base)
            if high <= low or high - low > cfg.sd_max_zone_atr * atr:
                continue
            zone = {'type': side, 'low': low, 'high': high}
            dep = _sd_departure(c15, i, zone, atr, kind)
            if dep is None or dep[0] != n - 1 or dep[1] < cfg.sd_min_score:
                continue
            zones.append((dep[1], i, side, kind, low, high, atr))
    out = []
    for side in (1, -1):
        picked = sorted((z for z in zones if z[2] == side), reverse=True)
        if not picked:
            continue
        score, i, side, kind, low, high, atr = picked[0]
        out.append({'setup': 'SD DEMAND' if side > 0 else 'SD SUPPLY', 'direction': side,
                    'setup_note': f"{tf} {'demand' if side > 0 else 'supply'} zone {low:.6g}-{high:.6g} "
                                  f"({kind} candle, score {score:.1f}) confirmed by a {'rally' if side > 0 else 'drop'} "
                                  f"of {cfg.sd_min_move_atr:g}+ ATR; entry at the proximal line, first touch only",
                    'zone_lo': low, 'zone_hi': high, 'zone_kind': kind, 'zone_score': score,
                    'anchor_level': high if side > 0 else low, 'anchor_extreme': low if side > 0 else high,
                    'anchor_label': f"{'demand' if side > 0 else 'supply'} zone ({kind})",
                    'anchor_ts': int(c15[i][0]), 'anchor_close': c15[-1][4],
                    'event_ts': int(c15[-1][0]) + period_ms})
    return out


# ------------------------------------------------------------------------------------------------ trendlines

def find_pivots(values: np.ndarray, left: int, right: int, kind: str) -> List[int]:
    out = []
    for i in range(left, len(values) - right):
        w = values[i - left:i + right + 1]
        m = w.min() if kind == 'low' else w.max()
        if values[i] == m and int(np.sum(w == m)) == 1:
            out.append(i)
    return out


def _trendline(h, l, c, atr: float, kind: str) -> Optional[Dict]:
    """trendline_bot _detect_one_side (sloped only): the best line through >= 3 pivots, never closed through."""
    cfg = CONFIG.strategies
    n = len(c)
    if n < cfg.tl_min_span + 2 * cfg.tl_pivot + 2 or atr <= 0:
        return None
    vals = l if kind == 'support' else h
    pivots = find_pivots(vals, cfg.tl_pivot, cfg.tl_pivot, 'low' if kind == 'support' else 'high')
    piv = np.asarray(pivots, dtype=int)
    flat_limit = math.tan(math.radians(cfg.tl_flat_deg)) * atr
    best, best_score = None, ()
    for a in range(len(pivots)):
        for b in range(a + 1, len(pivots)):
            i1, i2 = pivots[a], pivots[b]
            if i2 - i1 < cfg.tl_min_span:
                continue
            p1, p2 = vals[i1], vals[i2]
            slope = (p2 - p1) / (i2 - i1)
            if kind == 'support' and slope < -flat_limit:
                continue
            if kind == 'resistance' and slope > flat_limit:
                continue
            angle = math.degrees(math.atan(slope / atr))
            if abs(angle) > cfg.tl_max_deg or abs(angle) <= cfg.tl_flat_deg:
                continue                                  # his config trades sloped lines only
            idx = np.arange(i1, n)
            line = p1 + slope * (idx - i1)
            if kind == 'support':
                if np.any(c[i1:] < line - cfg.tl_violation_atr * atr):
                    continue
                touch = (l[i1:] - line) <= cfg.tl_touch_atr * atr
                dist_now = c[-1] - line[-1]
            else:
                if np.any(c[i1:] > line + cfg.tl_violation_atr * atr):
                    continue
                touch = (line - h[i1:]) <= cfg.tl_touch_atr * atr
                dist_now = line[-1] - c[-1]
            if dist_now > cfg.tl_max_dist_atr * atr:
                continue
            tidx = np.flatnonzero(touch)
            if tidx.size == 0 or (n - 1) - (i1 + tidx[-1]) > cfg.tl_last_touch_age:
                continue
            touches = 1 + int(np.sum(np.diff(tidx) > max(1, cfg.tl_touch_gap)))
            if touches < cfg.tl_min_touches:
                continue
            span = piv[piv >= i1]
            pivot_touches = int(np.sum(np.abs(vals[span] - (p1 + slope * (span - i1))) <= cfg.tl_pivot_tol_atr * atr))
            if pivot_touches < cfg.tl_min_pivot_touches:
                continue
            score = (pivot_touches, touches, i2 - i1, i2)
            if best is None or score > best_score:
                best, best_score = {'kind': kind, 'i1': i1, 'i2': i2, 'p1': float(p1), 'p2': float(p2),
                                    'slope': float(slope), 'angle': angle, 'touches': touches,
                                    'pivot_touches': pivot_touches}, score
    return best


def trendline_event(c15: Sequence[Sequence[float]]) -> Optional[Dict]:
    """
    trendline_bot: lines are built on the candles BEFORE the two confirming ones; both close beyond the line by
    >= 0.15 ATR, the last with a body >= 0.35 ATR, <= 1.2 ATR beyond it and closing in its outer 40%. A broken
    resistance (falling or flat) -> long, a broken support (rising or flat) -> short. ATR = Wilder(14) of 15m.
    """
    cfg = CONFIG.strategies
    window = c15[-(cfg.tl_lookback + 2):]
    n = len(window)
    if n < cfg.tl_min_span + 10:
        return None
    h, l, c, o = _arr(window, 2), _arr(window, 3), _arr(window, 4), _arr(window, 1)
    atr = float(wilder(true_range(h, l, c), 14)[-3])
    if not atr > 0:
        return None
    buf = cfg.tl_confirm_atr * atr
    for kind in ('resistance', 'support'):
        line = _trendline(h[:-2], l[:-2], c[:-2], atr, kind)
        if line is None:
            continue
        value = lambda j: line['p1'] + line['slope'] * (j - line['i1'])
        d = 1 if kind == 'resistance' else -1
        if not all(d * (c[j] - value(j)) > buf for j in (n - 2, n - 1)):
            continue
        i = n - 1
        if abs(c[i] - o[i]) < cfg.tl_min_body_atr * atr or abs(c[i] - value(i)) > cfg.tl_max_depth_atr * atr:
            continue
        rng = h[i] - l[i]
        pos = ((h[i] - c[i]) if d > 0 else (c[i] - l[i])) / rng if rng > 0 else 0.0
        if pos > cfg.tl_close_pos_max:
            continue
        return {'setup': 'TRENDLINE UP' if d > 0 else 'TRENDLINE DOWN', 'direction': d,
                'setup_note': f"15m closed twice {'above a falling resistance' if d > 0 else 'below a rising support'} "
                              f"({line['pivot_touches']} pivots, {line['touches']} touches, angle {line['angle']:+.0f})",
                'line_p1': line['p1'], 'line_slope': line['slope'], 'line_ts1': int(window[line['i1']][0]),
                'line_value': value(i), 'atr_line': atr,
                'anchor_level': value(i), 'anchor_extreme': l[i] if d > 0 else h[i],
                'anchor_label': 'trendline', 'anchor_ts': int(window[line['i1']][0]),
                'anchor_close': float(c[i]), 'target_price': line['p1'],
                'event_ts': int(window[-1][0]) + QUARTER_MS}
    return None


# ------------------------------------------------------------------------------------------------ SMT / Quasimodo

def _swings(candles, left: int = 2, right: int = 2) -> List[Tuple[int, float, str]]:
    """lllll find_swings: fractal swings alternating H / L (of consecutive same kinds the more extreme stays)."""
    h, l = _arr(candles, 2), _arr(candles, 3)
    raw = []
    for i in range(left, len(candles) - right):
        hw, lw = h[i - left:i + right + 1], l[i - left:i + right + 1]
        if h[i] >= hw.max() and int(np.argmax(hw)) == left:
            raw.append((i, float(h[i]), 'H'))
        if l[i] <= lw.min() and int(np.argmin(lw)) == left:
            raw.append((i, float(l[i]), 'L'))
    raw.sort(key=lambda s: (s[0], s[2]))
    out: List[Tuple[int, float, str]] = []
    for s in raw:
        if out and out[-1][2] == s[2]:
            if (s[1] > out[-1][1]) if s[2] == 'H' else (s[1] < out[-1][1]):
                out[-1] = s
        else:
            out.append(s)
    return out


def _trend(candles, swings, right: int = 2) -> str:
    trend, last_h, last_l, pi = 'range', None, None, 0
    for i, c in enumerate(candles):
        while pi < len(swings) and swings[pi][0] + right <= i:
            if swings[pi][2] == 'H':
                last_h = swings[pi]
            else:
                last_l = swings[pi]
            pi += 1
        if last_h is not None and c[4] > last_h[1]:
            trend = 'up'
        if last_l is not None and c[4] < last_l[1]:
            trend = 'down'
    return trend


def _pools(swings, trend: str):
    highs = [s for s in swings if s[2] == 'H']
    lows = [s for s in swings if s[2] == 'L']
    if not highs or not lows:
        return None, None
    last_low, last_high = lows[-1], highs[-1]
    if trend == 'up':
        after = [x for x in highs if x[0] > last_low[0]]
        return last_low, after[-1] if after else last_high
    if trend == 'down':
        after = [x for x in lows if x[0] > last_high[0]]
        return after[-1] if after else last_low, last_high
    return last_low, last_high


def _qm_levels(candles, swings, lookback: int = 14) -> List[Tuple[int, float, float]]:
    """Quasimodo: H1 -> L1 -> H2 > H1 then a close below L1 (sell, QML = H1); mirrored for buys. (dir, qml, head)."""
    out = []
    seq = swings[-lookback:]
    closes = [c[4] for c in candles]
    for k in range(len(seq) - 2):
        a, b, c3 = seq[k], seq[k + 1], seq[k + 2]
        if a[2] == 'H' and b[2] == 'L' and c3[2] == 'H' and c3[1] > a[1] and any(x < b[1] for x in closes[c3[0] + 1:]):
            out.append((-1, a[1], c3[1]))
        if a[2] == 'L' and b[2] == 'H' and c3[2] == 'L' and c3[1] < a[1] and any(x > b[1] for x in closes[c3[0] + 1:]):
            out.append((1, a[1], c3[1]))
    return out[-6:]


def smt_event(c15: Sequence[Sequence[float]], corr: Optional[Sequence[Sequence[float]]]) -> Optional[Dict]:
    """
    lllll SignalEngine.on_main_bar on 15m: structure (fractal 2/2 swings, trend by break of structure), the two
    external pools, a 2-candle sweep whose REACTION candle just closed (the piercing candle wicks beyond the pool and
    closes back, the reaction candle closes away from it; no earlier close beyond the pool), SMT against the correlate
    (it did NOT take its matching swing) or Quasimodo confluence (the wick inside a QM's QML-head zone substitutes
    SMT); mode require_if_available: rejected only when SMT is proven absent and there is no QM.
    """
    cfg = CONFIG.strategies
    main = c15[-cfg.smt_main_bars:]
    n = len(main)
    if n < 60:
        return None
    swings = _swings(main)
    trend = _trend(main, swings)
    pool_low, pool_high = _pools(swings, trend)
    if pool_low is None or pool_high is None:
        return None
    j = n - 1
    i = n - 2
    o, h, l, c = main[j][1], main[j][2], main[j][3], main[j][4]
    best = None
    for side, pool in ((-1, pool_low), (1, pool_high)):
        level = pool[1]
        if i <= pool[0]:
            continue
        # a close beyond the pool before the pierce: the pool is broken, not swept
        if any((x[4] < level) if side < 0 else (x[4] > level) for x in main[pool[0] + 1:i]):
            continue
        pc = main[i]
        if side < 0 and pc[3] < level <= pc[4] and c > o and c > level:
            best = (1, pool, min(pc[3], l))
        elif side > 0 and pc[2] > level >= pc[4] and c < o and c < level:
            best = (-1, pool, max(pc[2], h))
    if best is None:
        return None
    direction, pool, extreme = best
    if cfg.smt_with_trend_only and trend in ('up', 'down') and direction != (1 if trend == 'up' else -1):
        return None
    # SMT: the correlate's swing of the same kind nearest in time to the pool's formation, within 60 main bars, taken
    # (or not) between it and the reaction candle
    smt = None
    if corr and len(corr) >= 30:
        cswings = [s for s in _swings(corr) if s[2] == ('L' if direction > 0 else 'H')]
        level_ts, pierce_ts, react_ts = main[pool[0]][0], main[i][0], main[j][0]
        cands = [s for s in cswings if corr[s[0]][0] <= pierce_ts]
        if cands:
            ref = min(cands, key=lambda s: abs(corr[s[0]][0] - level_ts))
            if abs(corr[ref[0]][0] - level_ts) <= cfg.smt_ref_window * QUARTER_MS:
                seg = [x for x in corr if corr[ref[0]][0] < x[0] <= react_ts]
                if seg:
                    swept = min(x[3] for x in seg) < ref[1] if direction > 0 else max(x[2] for x in seg) > ref[1]
                    smt = not swept
    qm = any(q[0] == direction and min(q[1], q[2]) <= extreme <= max(q[1], q[2]) for q in _qm_levels(main, swings))
    # SMT is the method: a divergence against a correlated pair (smt True) or the Quasimodo; with no pair
    # (correlation < 0.7, structure.pick_correlate) or no reference swing it passed as a plain 'SWEEP'
    if not smt and not qm:
        return None
    tags = '+'.join(t for t, on in (('SMT', smt), ('QM', qm)) if on) or 'SWEEP'
    opposite = pool_high[1] if direction > 0 else pool_low[1]
    atr = float(np.mean(true_range(_arr(main, 2), _arr(main, 3), _arr(main, 4))[-14:]))
    return {'setup': 'SMT LOW' if direction > 0 else 'SMT HIGH', 'direction': direction,
            'setup_note': f"15m 2-candle sweep of the {'low' if direction > 0 else 'high'} pool {pool[1]:.6g} "
                          f"(trend {trend}, {tags}{'' if smt is not None else ', SMT n/a'}); entry on a 5m inversion FVG",
            'anchor_level': pool[1], 'anchor_extreme': extreme, 'anchor_label': f"external {'low' if direction > 0 else 'high'} ({tags})",
            'anchor_ts': int(main[i][0]), 'anchor_close': c, 'opposite_pool': opposite, 'smt': smt, 'qm': qm,
            'smt_trend': trend, 'atr_main': atr, 'event_ts': int(main[j][0]) + QUARTER_MS}


# ------------------------------------------------------------------------------------------------ Bollinger + CSI

def bollinger_wm_event(c15: Sequence[Sequence[float]]) -> Optional[Dict]:
    """
    John Bollinger's reversal method ("Bollinger on Bollinger Bands", 2001, method III; W / M patterns after Arthur
    Merrill): a band tag is NOT a signal by itself. W-bottom: a low that closed BELOW the lower band (%b < 0), a rally,
    a retest low whose close stays INSIDE the band (%b >= 0, the price low may be lower), then the first close above the
    rally's high between them -> long at that close; stop below the retest low; target the upper band, then the map.
    M-top mirrored. BB(20, 2), within the last 30 15m candles. (Replaces crypto_maniac's CSI system: a close beyond
    BB(40, 1.5) read as a reversal contradicts Bollinger's own rule, and its "candle sentiment index" is his invention.)
    """
    n = len(c15)
    if n < 60:
        return None
    h, l, c = _arr(c15, 2), _arr(c15, 3), _arr(c15, 4)
    ma, sd = rolling_mean(c, 20), rolling_std(c, 20)
    upper, lower = ma + 2 * sd, ma - 2 * sd
    width = upper - lower
    pb = np.where(width > 0, (c - lower) / np.where(width > 0, width, 1), np.nan)
    i = n - 1
    start = n - 30
    for d in (1, -1):
        # first test: closed outside the band
        firsts = [k for k in range(start, i - 3) if (pb[k] < 0 if d > 0 else pb[k] > 1)]
        if not firsts:
            continue
        a_ = firsts[-1]
        mid = range(a_ + 1, i)
        if len(mid) < 3:
            continue
        peak = max(mid, key=lambda k: h[k]) if d > 0 else min(mid, key=lambda k: l[k])
        retest = [k for k in range(peak + 1, i)]
        if not retest:
            continue
        b_ = min(retest, key=lambda k: l[k]) if d > 0 else max(retest, key=lambda k: h[k])
        inside = pb[b_] >= 0 if d > 0 else pb[b_] <= 1
        if not inside:
            continue
        level = h[peak] if d > 0 else l[peak]
        broke_now = c[i] > level if d > 0 else c[i] < level
        broke_before = any((c[k] > level) if d > 0 else (c[k] < level) for k in range(b_ + 1, i))
        if not broke_now or broke_before:
            continue
        stop = l[b_] if d > 0 else h[b_]
        target = upper[i] if d > 0 else lower[i]
        return {'setup': 'BB W-BOTTOM' if d > 0 else 'BB M-TOP', 'direction': d,
                'setup_note': f"15m {'W-bottom' if d > 0 else 'M-top'} on BB(20, 2): first {'low' if d > 0 else 'high'} "
                              f"closed outside the band, the retest held inside (%b {pb[b_]:.2f}), close beyond the "
                              f"middle {'peak' if d > 0 else 'trough'} {level:.6g} (Bollinger)",
                'anchor_level': float(level), 'anchor_extreme': float(stop), 'anchor_label': 'Bollinger W / M',
                'bb_stop': float(stop), 'bb_target': float(target),
                'anchor_ts': int(c15[a_][0]), 'anchor_close': float(c[i]), 'event_ts': int(c15[-1][0]) + QUARTER_MS}
    return None


# ------------------------------------------------------------------------------------------------ 1h systems

def fib05_event(c1h: Sequence[Sequence[float]]) -> Optional[Dict]:
    """
    fibonachi_trading_system (1h): MarketStructureTracker (3-bar fractals; HL / HH extend a bull impulse, a lower low
    is a CHoCH to bear, mirrored) keeps the current impulse; the candle that just closed pierced its 0.5 and closed
    back on the impulse's side -> entry at the close, stop beyond the impulse's start. One entry per impulse.
    """
    n = len(c1h)
    if n < 30:
        return None
    trend = None
    last = {'HH': None, 'HL': None, 'LH': None, 'LL': None}
    imp = None
    for k in range(2, n - 1):                  # swings confirmed by the bar after them (not by the one just closed)
        left, piv, right = c1h[k - 2], c1h[k - 1], c1h[k]
        idx = k - 1
        if piv[3] < left[3] and piv[3] < right[3]:
            p = piv[3]
            if trend in (None, 'bull'):
                if last['HL'] is None or p > last['HL'][1]:
                    last['HL'] = (idx, p)
                    trend = trend or 'bull'
                    if imp and imp['type'] == 'bull':
                        imp.update(low=p, low_i=idx)
                    else:
                        imp = {'type': 'bull', 'low': p, 'low_i': idx, 'high': None, 'high_i': None}
                else:
                    trend = 'bear'
                    last['LL'] = (idx, p)
                    lh = last['LH']
                    imp = {'type': 'bear', 'low': p, 'low_i': idx, 'high': lh[1] if lh else p, 'high_i': lh[0] if lh else idx}
                    last['HL'] = last['HH'] = None
            elif last['LL'] is None or p < last['LL'][1]:
                last['LL'] = (idx, p)
                if imp and imp['type'] == 'bear':
                    imp.update(low=p, low_i=idx)
        if piv[2] > left[2] and piv[2] > right[2]:
            p = piv[2]
            if trend in (None, 'bear'):
                if last['LH'] is None or p < last['LH'][1]:
                    last['LH'] = (idx, p)
                    trend = trend or 'bear'
                    if imp and imp['type'] == 'bear':
                        imp.update(high=p, high_i=idx)
                    else:
                        imp = {'type': 'bear', 'high': p, 'high_i': idx, 'low': None, 'low_i': None}
                else:
                    trend = 'bull'
                    last['HH'] = (idx, p)
                    hl = last['HL']
                    imp = {'type': 'bull', 'high': p, 'high_i': idx, 'low': hl[1] if hl else p, 'low_i': hl[0] if hl else idx}
                    last['LL'] = last['LH'] = None
            elif last['HH'] is None or p > last['HH'][1]:
                last['HH'] = (idx, p)
                if imp and imp['type'] == 'bull':
                    imp.update(high=p, high_i=idx)
    if not imp or imp['low'] is None or imp['high'] is None or imp['high'] <= imp['low']:
        return None
    d = 1 if imp['type'] == 'bull' else -1
    lo, hi = imp['low'], imp['high']
    half = (lo + hi) / 2
    end_i = imp['high_i'] if d > 0 else imp['low_i']
    last_c = c1h[-1]
    # the 0.5 not touched between the impulse's end and this candle (one entry per impulse)
    between = c1h[end_i + 1:-1]
    if any((x[3] <= half) if d > 0 else (x[2] >= half) for x in between):
        return None
    if d > 0 and not (last_c[3] <= half < last_c[4]):
        return None
    if d < 0 and not (last_c[2] >= half > last_c[4]):
        return None
    start, end = (lo, hi) if d > 0 else (hi, lo)
    return {'setup': 'FIB 0.5 LONG' if d > 0 else 'FIB 0.5 SHORT', 'direction': d,
            'setup_note': f"1h pierced the 0.5 {half:.6g} of the {'bull' if d > 0 else 'bear'} impulse "
                          f"{start:.6g} -> {end:.6g} and closed back",
            'anchor_level': half, 'anchor_extreme': start, 'anchor_label': 'impulse 0.5',
            'impulse_start': start, 'impulse_end': end,
            'anchor_ts': int(c1h[imp['low_i'] if d > 0 else imp['high_i']][0]), 'anchor_close': last_c[4],
            'event_ts': int(last_c[0]) + HOUR_MS}


# ------------------------------------------------------------------------------------------------ inversion FVG (5m)

def ifvg_trigger(ltf: Sequence[Sequence[float]], direction: int, pierce_ms: int, scan_from_ms: int,
                 interval_ms: int) -> Optional[Dict]:
    """
    lllll find_first_inversion on the entry timeframe: for a buy the FIRST bearish FVG (high[i] < low[i-2]) formed
    from 40 bars before the pierce on is inverted by a close ABOVE its top (a sell mirrored); FVGs smaller than 0.03
    ATR are noise. Only an inversion closing at or after `scan_from_ms` counts. Entry at that close; the extreme is
    the deepest price since the pierce.
    """
    cfg = CONFIG.strategies
    if len(ltf) < 10:
        return None
    ts = [int(x[0]) for x in ltf]
    start = next((k for k, t in enumerate(ts) if t + interval_ms > pierce_ms), None)
    if start is None:
        return None
    h, l, c = _arr(ltf, 2), _arr(ltf, 3), _arr(ltf, 4)
    atr = float(np.mean(true_range(h, l, c)[-120:]))
    min_size = cfg.smt_ifvg_min_atr * atr
    best = None
    for i in range(max(2, start - cfg.smt_ifvg_search_back), len(ltf)):
        if direction > 0 and h[i] < l[i - 2] and l[i - 2] - h[i] >= min_size:
            top = l[i - 2]
            j = next((k for k in range(i + 1, len(ltf)) if c[k] > top), None)
        elif direction < 0 and l[i] > h[i - 2] and l[i] - h[i - 2] >= min_size:
            bottom = h[i - 2]
            j = next((k for k in range(i + 1, len(ltf)) if c[k] < bottom), None)
        else:
            continue
        if j is not None and ts[j] + interval_ms > scan_from_ms and (best is None or j < best):
            best = j
    if best is None:
        return None
    seg = ltf[start:best + 1]
    extreme = min(x[3] for x in seg) if direction > 0 else max(x[2] for x in seg)
    return {'entry': float(c[best]), 'extreme': float(extreme), 'time': ts[best] + interval_ms,
            'extreme_time': int(min(seg, key=lambda x: x[3])[0] if direction > 0 else max(seg, key=lambda x: x[2])[0])}


def pinbar_trigger(ltf: Sequence[Sequence[float]], direction: int, since_ms: int, interval_ms: int,
                   zone_lo: float, zone_hi: float) -> Optional[Dict]:
    """supply_demand-v4: the first closed entry-timeframe candle since `since_ms` that is a pinbar retesting the zone
    (its wick into the zone, the close inside it or at most 25% of the zone's height beyond the near edge)."""
    width = zone_hi - zone_lo
    for x in ltf:
        if x[0] + interval_ms <= since_ms:
            continue
        o, h, l, c = x[1], x[2], x[3], x[4]
        if direction > 0:
            ok = is_bull_pinbar(o, h, l, c) and l <= zone_hi and h >= zone_lo and zone_lo <= c <= zone_hi + 0.25 * width
        else:
            ok = is_bear_pinbar(o, h, l, c) and h >= zone_lo and l <= zone_hi and zone_lo - 0.25 * width <= c <= zone_hi
        if ok:
            return {'entry': c, 'extreme': l if direction > 0 else h, 'time': int(x[0]) + interval_ms,
                    'extreme_time': int(x[0])}
    return None


# ------------------------------------------------------------------------------------------------ OI accumulation

