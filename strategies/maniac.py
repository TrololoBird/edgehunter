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
    # eng-55 Seiden / OTA (secondary sources agree): the leg-out is an "exciting" candle, its body > half its range
    # (the base's "boring" candles have bodies <= half)
    if first[2] - first[3] <= 0 or body <= 0.5 * (first[2] - first[3]):
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


def trendline_event(c15: Sequence[Sequence[float]], period_ms: int = QUARTER_MS, tf: str = '15m') -> Optional[Dict]:
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
                'setup_note': f"{tf} closed twice {'above a falling resistance' if d > 0 else 'below a rising support'} "
                              f"({line['pivot_touches']} pivots, {line['touches']} touches, angle {line['angle']:+.0f})",
                'line_p1': line['p1'], 'line_slope': line['slope'], 'line_ts1': int(window[line['i1']][0]),
                'line_value': value(i), 'atr_line': atr,
                'anchor_level': value(i), 'anchor_extreme': l[i] if d > 0 else h[i],
                'anchor_label': 'trendline', 'anchor_ts': int(window[line['i1']][0]),
                'anchor_close': float(c[i]), 'target_price': line['p1'],
                'event_ts': int(window[-1][0]) + period_ms}
    return None


# ------------------------------------------------------------------------------------------------ Bollinger W / M

def bollinger_wm_event(c15: Sequence[Sequence[float]], period_ms: int = QUARTER_MS, tf: str = '15m') -> Optional[Dict]:
    """
    John Bollinger's reversal method ("Bollinger on Bollinger Bands", 2001, method III; W / M patterns after Arthur
    Merrill): a band tag is NOT a signal by itself. W-bottom: a low that closed BELOW the lower band (%b < 0), a rally,
    a retest low whose close stays INSIDE the band (%b >= 0, the price low may be lower), then the first close above the
    rally's high between them -> long at that close; stop below the retest low; out at the OPPOSITE BAND as it moves
    (Bollinger; eng-51 / 55), A/D must not confirm the retest.
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
    # Accumulation Distribution (Williams / Chaikin): the volume-weighted close location, cumulated
    vol = [float(x[5]) if len(x) > 5 and x[5] is not None else None for x in c15]
    ad: List[Optional[float]] = []
    acc = 0.0
    for k in range(n):
        rng = h[k] - l[k]
        if vol[k] is None:
            ad.append(None)
            continue
        acc += (((c[k] - l[k]) - (h[k] - c[k])) / rng * vol[k]) if rng > 0 else 0.0
        ad.append(acc)
    i = n - 1
    start = n - 30                     # our search window (Bollinger / Merrill set none): journaled as such
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
        # eng-55: method III compares the band tags with a VOLUME indicator (Bollinger: Accumulation Distribution; "tags
        # are not signals"): the retest must not be confirmed by it - AD higher at the W's retest than at its first
        # low (accumulation), lower at the M's retest (distribution)
        if ad[b_] is None or ad[a_] is None or not (ad[b_] > ad[a_] if d > 0 else ad[b_] < ad[a_]):
            continue
        level = h[peak] if d > 0 else l[peak]
        broke_now = c[i] > level if d > 0 else c[i] < level
        broke_before = any((c[k] > level) if d > 0 else (c[k] < level) for k in range(b_ + 1, i))
        if not broke_now or broke_before:
            continue
        stop = l[b_] if d > 0 else h[b_]
        # eng-51: the target is the OPPOSITE BAND (Bollinger: after the bounce crosses the middle band, the other band
        # is the objective; StockCharts / bollingerbandspro). The measured move of eng-40 was ours: it replaced the
        # band because the band's R:R was low - such a W / M is skipped by the R:R check instead
        target = upper[i] if d > 0 else lower[i]
        return {'setup': 'BB W-BOTTOM' if d > 0 else 'BB M-TOP', 'direction': d,
                'setup_note': f"{tf} {'W-bottom' if d > 0 else 'M-top'} on BB(20, 2): first {'low' if d > 0 else 'high'} "
                              f"closed outside the band, the retest held inside (%b {pb[b_]:.2f}), close beyond the "
                              f"middle {'peak' if d > 0 else 'trough'} {level:.6g}, A/D not confirming the retest "
                              f"(Bollinger method III; window {i - a_} candles)",
                'bb_gap': float(i - a_),
                'anchor_level': float(level), 'anchor_extreme': float(stop), 'anchor_label': 'Bollinger W / M',
                'bb_stop': float(stop), 'bb_target': float(target),
                'anchor_ts': int(c15[a_][0]), 'anchor_close': float(c[i]), 'event_ts': int(c15[-1][0]) + period_ms,
                'bb_tf': tf}
    return None


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
