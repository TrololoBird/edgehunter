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
        out[n - 1:] = w.std(axis=1, ddof=0)    # audit C10/R06: Bollinger's population sigma
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

def _boring(k) -> bool:
    """OTA / Seiden: a base ("boring") candle - its body at most half its range."""
    return k[2] > k[3] and abs(k[4] - k[1]) <= 0.5 * (k[2] - k[3])


def _exciting(k, side: int) -> bool:
    """A leg-out ("exciting") candle of the side: body more than half its range, closing in the side's direction."""
    return k[2] > k[3] and abs(k[4] - k[1]) > 0.5 * (k[2] - k[3]) and side * (k[4] - k[1]) > 0


def _sd_bases(bars: Sequence[Sequence[float]]) -> List[Dict]:
    """
    Every base of the history and its departure: a run of boring candles followed by a run of exciting candles of
    one side. Demand: distal = the lowest low of the base, proximal = its highest body; supply mirrored. The departure
    ends at the first candle that is not exciting (its close confirms the zone). `speed` = the departure's move beyond
    the proximal line per candle, in ATR(14) (Seiden: "how quickly they leave"); `n_base` = the base's candles.
    """
    n = len(bars)
    if n < 20:
        return []
    h, l, c = _arr(bars, 2), _arr(bars, 3), _arr(bars, 4)
    atr = wilder(true_range(h, l, c), 14)
    out = []
    i = 1
    while i < n - 1:
        if not _boring(bars[i]):
            i += 1
            continue
        j = i
        while j + 1 < n and _boring(bars[j + 1]):
            j += 1
        base = bars[i:j + 1]
        for side in (1, -1):
            k = j + 1
            while k < n and _exciting(bars[k], side):
                k += 1
            if k == j + 1 or k >= n:          # no departure, or it has not ended yet
                continue
            if side > 0:
                lo, hi = min(x[3] for x in base), max(max(x[1], x[4]) for x in base)
                move = max(x[2] for x in bars[j + 1:k]) - hi
            else:
                lo, hi = min(min(x[1], x[4]) for x in base), max(x[2] for x in base)
                move = lo - min(x[3] for x in bars[j + 1:k])
            a = atr[j]
            if not (a > 0) or hi <= lo or move <= 0:
                continue
            out.append({'side': side, 'lo': lo, 'hi': hi, 'base_from': i, 'base_to': j, 'confirm': k,
                        'speed': move / (k - j - 1) / a, 'n_base': j - i + 1, 'atr': float(a)})
        i = j + 1
    return out


def sd_zone_events(bars: Sequence[Sequence[float]], period_ms: int = QUARTER_MS, tf: str = '15m') -> List[Dict]:
    """
    eng-127, Sam Seiden / Online Trading Academy's odds enhancers ("5 years of Sam Seiden supply and demand
    teaching": Strength of the move max 2, Time at level max 1, Freshness max 2, Reward / Risk max 2, Big picture
    max 2, Arrival max 1; 9-10 limit order, 8 confirmation entry, below that no trade). The zones CONFIRMED by the
    candle that just closed; the history-relative scores are fixed here, the rest at the entry
    (SupplyDemandStrategy / SignalBook):
      strength  the departure speed ranked among this coin's departures (Seiden: "the more quickly they move, the
                more out of balance"): upper third 2, middle 1, lower 0;
      time      the base's candles at most the coin's median (Seiden: "few candles ... be very careful about coming up
                with a specific number") 1, else 0.
    Replaces the ported supply_demand-v4 thresholds (0.55 ATR body, 2 ATR within 4 bars, 1.2 ATR height, score 3.5).
    """
    zones = _sd_bases(bars)
    if len(zones) < 10:
        return []
    closes = [x[4] for x in bars]
    speeds = np.array([z['speed'] for z in zones])
    lo3, hi3 = np.quantile(speeds, [1 / 3, 2 / 3])
    med_base = float(np.median([z['n_base'] for z in zones]))
    out = []
    for z in zones:
        if z['confirm'] != len(bars) - 1:
            continue
        side, lo, hi = z['side'], z['lo'], z['hi']
        strength = 2 if z['speed'] >= hi3 else 1 if z['speed'] >= lo3 else 0
        time_pts = 1 if z['n_base'] <= med_base else 0
        if strength + time_pts + 2 + 2 + 2 + 1 < 8:
            continue                  # cannot reach 8 even with the best big picture and arrival: no card
        out.append({'setup': 'SD DEMAND' if side > 0 else 'SD SUPPLY', 'direction': side,
                    'setup_note': f"{tf} {'demand' if side > 0 else 'supply'} zone {lo:.6g}-{hi:.6g}: base of "
                                  f"{z['n_base']} candles, departure {z['speed']:.2f} ATR / candle "
                                  f"(strength {strength}/2, time {time_pts}/1)",
                    'zone_lo': lo, 'zone_hi': hi, 'zone_kind': 'base', 'sd_strength': strength,
                    'sd_time': time_pts, 'zone_score': strength + time_pts,
                    'departure_ts': int(bars[z['confirm'] - 1][0]),
                    'anchor_level': hi if side > 0 else lo, 'anchor_extreme': lo if side > 0 else hi,
                    'anchor_label': f"{'demand' if side > 0 else 'supply'} zone (base)",
                    'anchor_ts': int(bars[z['base_to']][0]), 'anchor_close': bars[-1][4],
                    'sd_targets': sd_opposing(zones, closes, side, hi if side > 0 else lo),
                    'event_ts': int(bars[-1][0]) + period_ms})
    return out


def sd_opposing(zones: List[Dict], closes: Sequence[float], side: int, ref: float, n: int = 3) -> List[List]:
    """
    Seiden's target: the OPPOSING zone - for a demand trade the nearest fresh supply zone above (its proximal line,
    the lowest body of its base), for a supply trade the nearest fresh demand zone below (its proximal line, the highest
    body); "the distance between our supply and target (T1: Demand) represents our potential profit zone" (FXStreet,
    'Lessons from the pros', 2014). Fresh = no close back at its proximal line since it was confirmed. Up to `n`
    [price, label] pairs, nearest first. Was the map's opposite liquidity (old highs / lows, equal levels, sessions),
    which is not his target.
    """
    out = []
    for z in zones:
        if z['side'] != -side:
            continue
        after = closes[z['confirm']:]
        # audit 2026-10-16: Seiden's FRESH zone = price has not come back to it; was "no close beyond its DISTAL line"
        # (unbroken: a zone tested many times passed). The closes only (the zone list carries no highs / lows): a
        # close at or into the proximal line is the return
        if side > 0:
            proximal, broken = z['lo'], any(c >= z['lo'] for c in after)
            beyond = proximal > ref
        else:
            proximal, broken = z['hi'], any(c <= z['hi'] for c in after)
            beyond = proximal < ref
        if beyond and not broken:
            out.append([float(proximal), f"4h {'supply' if side > 0 else 'demand'} zone {z['lo']:.6g}-{z['hi']:.6g}"])
    out.sort(key=lambda t: side * (t[0] - ref))
    return out[:n]


# ------------------------------------------------------------------------------------------------ trendlines

def find_pivots(values: np.ndarray, left: int, right: int, kind: str) -> List[int]:
    out = []
    for i in range(left, len(values) - right):
        w = values[i - left:i + right + 1]
        m = w.min() if kind == 'low' else w.max()
        if values[i] == m and int(np.sum(w == m)) == 1:
            out.append(i)
    return out


def _em_line(h, l, c, kind: str) -> Optional[Dict]:
    """
    eng-122, Edwards & Magee's trendline: drawn through the two LAST reaction points (2/2 swings) - a down trendline
    (resistance) through two falling tops, an up trendline (support) through two rising bottoms - and valid while no
    close went beyond it between them and since (no parameters of a bot).
    """
    n = len(c)
    if kind == 'resistance':
        piv = [k for k in range(2, n - 2) if h[k] == max(h[k - 2:k + 3])]
        if len(piv) < 2:
            return None
        i1, i2 = piv[-2], piv[-1]
        if not h[i2] < h[i1]:
            return None
        p1, slope = h[i1], (h[i2] - h[i1]) / (i2 - i1)
        if any(c[j] > p1 + slope * (j - i1) for j in range(i1 + 1, n)):
            return None
    else:
        piv = [k for k in range(2, n - 2) if l[k] == min(l[k - 2:k + 3])]
        if len(piv) < 2:
            return None
        i1, i2 = piv[-2], piv[-1]
        if not l[i2] > l[i1]:
            return None
        p1, slope = l[i1], (l[i2] - l[i1]) / (i2 - i1)
        if any(c[j] < p1 + slope * (j - i1) for j in range(i1 + 1, n)):
            return None
    return {'p1': float(p1), 'slope': float(slope), 'i1': i1}


def trendline_em_event(c1h: Sequence[Sequence[float]], period_ms: int = 3_600_000, tf: str = '1h',
                       pct: float = 0.03) -> Optional[Dict]:
    """
    eng-107, the trendline break as Edwards & Magee define a DECISIVE penetration ("Technical Analysis of Stock Trends",
    ch. 14-15): a CLOSE beyond the line by about 3% (eng-109: their 3%; Brandt's 1-2% is his own suggestion for
    commodities / forex) and, on the up side, on rising volume (the breaking bar's volume above the 20-bar average).
    Audit 2026-10-16 (Murphy, Technical Analysis of the Financial Markets, ch. 4 pp. 71-72: the 3% filter and the
    two-day time filter are ALTERNATIVES): the 3% close alone decides (was: both 3% AND two closes), and the 3% is of
    the LINE's price at that bar, the level broken (was: of the close - a long passed only from 103.09 for a line at
    100). The same line as the ATR-line bot (deleted in eng-127).
    """
    cfg = CONFIG.strategies
    window = c1h[-(cfg.tl_lookback + 2):]
    n = len(window)
    if n < cfg.tl_min_span + 10:
        return None
    h, l, c = _arr(window, 2), _arr(window, 3), _arr(window, 4)
    v = np.asarray([float(x[5]) if len(x) > 5 and x[5] is not None else 0.0 for x in window])
    atr = float(wilder(true_range(h, l, c), 14)[-3])
    if not atr > 0:
        return None
    for kind in ('resistance', 'support'):
        line = _em_line(h[:-2], l[:-2], c[:-2], kind)
        if line is None:
            continue
        value = lambda j: line['p1'] + line['slope'] * (j - line['i1'])
        d = 1 if kind == 'resistance' else -1
        if not d * (c[n - 1] - value(n - 1)) >= pct * abs(value(n - 1)):
            continue
        if any(d * (c[j] - value(j)) >= pct * abs(value(j)) for j in range(line['i1'] + 1, n - 1)):
            continue                                   # the decisive break happened earlier: the first one only
        avg_v = v[n - 21:n - 1].mean() if n >= 21 else 0.0
        # Edwards & Magee: "activity should always be expected to rise notably on a genuine UP-side breakout" - the
        # volume test is theirs for the up side only
        if d > 0 and (not avg_v or v[n - 1] <= avg_v):
            continue
        i = n - 1
        return {'setup': 'TL EM UP' if d > 0 else 'TL EM DOWN', 'direction': d,
                'setup_note': f"{tf} closed >= {pct:.1%} of the line {'above a falling resistance' if d > 0 else 'below a rising support'}"
                              f" on {(v[n - 1] / avg_v) if avg_v else 0:.1f}x volume (Edwards & Magee, a line through"
                              f" the last two reaction points)",
                'line_p1': line['p1'], 'line_slope': line['slope'], 'line_ts1': int(window[line['i1']][0]),
                'line_period_ms': int(period_ms),
                'line_value': value(i), 'atr_line': atr,
                'anchor_level': value(i), 'anchor_extreme': l[i] if d > 0 else h[i],
                'anchor_label': 'trendline (E&M)', 'anchor_ts': int(window[line['i1']][0]),
                'anchor_close': float(c[i]), 'target_price': line['p1'],
                'event_ts': int(window[-1][0]) + period_ms}
    return None


def parabolic_sar_step(sar: float, ep: float, af: float, d: int, hi: float, lo: float,
                       step: float = 0.02, cap: float = 0.2, prev_hi: Optional[float] = None,
                       prev_lo: Optional[float] = None) -> Tuple[float, float, float, bool]:
    """
    One bar of Wilder's Parabolic SAR (New Concepts in Technical Trading Systems, 1978: AF 0.02, +0.02 per new extreme,
    at most 0.20) for a position of side d: (new sar, ep, af, stopped). The bar is first checked against the current
    SAR (a touch stops the position), then the SAR for the next bar is computed.
    """
    if (d > 0 and lo <= sar) or (d < 0 and hi >= sar):
        return sar, ep, af, True
    if (d > 0 and hi > ep) or (d < 0 and lo < ep):
        ep, af = (hi if d > 0 else lo), min(cap, af + step)
    nxt = sar + af * (ep - sar)
    # Wilder: the SAR never moves into the range of this bar or the previous one (audit 2026-10-16: two bars)
    if d > 0:
        nxt = min(nxt, lo, prev_lo if prev_lo is not None else lo)
    else:
        nxt = max(nxt, hi, prev_hi if prev_hi is not None else hi)
    return nxt, ep, af, False


def bb_method1_event(bars: Sequence[Sequence[float]], period_ms: int = 4 * HOUR_MS, tf: str = '4h') -> Optional[Dict]:
    """
    eng-127, Bollinger's Method I - volatility breakout (Bollinger on Bollinger Bands, ch. 15-16): "await a Squeeze, then
    go with the expansion".
    - BB(20, 2); BandWidth = (upper - lower) / middle; the Squeeze = BandWidth at its lowest of the last 125 bars
      (his "six-month low" is 125 bars of the DAILY chart; applying 125 bars to other timeframes is our assumption,
      measured in research/bb1_windows.md);
    - the signal: the FIRST close outside a band after the last Squeeze bar (no close outside since it), confirmed
      by the volume indicator he pairs with the bands - Bostian's Intraday Intensity % (21) > 0 for a close above
      the upper band, < 0 below the lower;
    - the head fake is handled by the exit he names: Wilder's Parabolic SAR (0.02 / 0.20), its first value the
      extreme against the trade of the 20 bars of the band (the prior range), trailed bar by bar (SignalBook).
    No target (an expansion is ridden until the SAR stops it). Replaces BULL F / BEAR D (phase scores with our delta /
    OI floors and an ICT pullback entry).
    """
    n = len(bars)
    if n < 20 + 125 + 1:
        return None
    h, l, c = _arr(bars, 2), _arr(bars, 3), _arr(bars, 4)
    v = np.asarray([float(b[5]) if len(b) > 5 and b[5] is not None else 0.0 for b in bars])
    ma, sd = rolling_mean(c, 20), rolling_std(c, 20)
    upper, lower = ma + 2 * sd, ma - 2 * sd
    with np.errstate(divide='ignore', invalid='ignore'):
        bw = (upper - lower) / ma
    i = n - 1
    # audit 2026-10-16: the manual's Method I (2021) looks back 5 bars for the Squeeze event (was: any of the last
    # 125 bars, a squeeze months old)
    squeeze = [k for k in range(i - 5, i) if k >= 144 and np.isfinite(bw[k])
               and bw[k] <= np.nanmin(bw[k - 124:k + 1])]
    if not squeeze:
        return None
    k0 = squeeze[-1]
    if any(c[j] > upper[j] or c[j] < lower[j] for j in range(k0 + 1, i)):
        return None
    d = 1 if c[i] > upper[i] else -1 if c[i] < lower[i] else 0
    if not d:
        return None
    rng = h - l
    clv = np.where(rng > 0, (2 * c - h - l) / np.where(rng > 0, rng, 1), 0.0)
    s_v = v[i - 20:i + 1].sum()
    ii = float((clv[i - 20:i + 1] * v[i - 20:i + 1]).sum() / s_v) if s_v > 0 else 0.0
    if d * ii <= 0:
        return None
    sar0 = float(l[i - 19:i + 1].min() if d > 0 else h[i - 19:i + 1].max())
    return {'setup': 'BB1 UP' if d > 0 else 'BB1 DOWN', 'direction': d,
            'setup_note': f"{tf} Bollinger Method I: Squeeze (BandWidth {bw[k0]:.4f}, 125-bar low) then the first close "
                          f"{'above the upper' if d > 0 else 'below the lower'} band {c[i]:.6g}, Intraday Intensity "
                          f"{ii:+.2f}; exit Parabolic SAR from {sar0:.6g}",
            'anchor_level': float(c[i]), 'anchor_extreme': sar0, 'anchor_label': 'Bollinger Method I',
            'bb_stop': sar0, 'bb_ii': ii, 'sar_ep': float(h[i] if d > 0 else l[i]),
            'anchor_ts': int(bars[k0][0]), 'anchor_close': float(c[i]), 'event_ts': int(bars[-1][0]) + period_ms,
            'bb_tf': tf}


def bb_method3_event(bars: Sequence[Sequence[float]], period_ms: int = QUARTER_MS, tf: str = '4h') -> Optional[Dict]:
    """
    eng-106, Bollinger Method III exactly as John Bollinger's Method III manual (bollingerbands.com, 2021) states it:
    "A tag of the lower Bollinger Band while Intraday Intensity is positive will create a buy alert ... a tag of the
    upper Bollinger Band while Intraday Intensity is negative will generate a sell/short alert. These are alerts rather
    than signals ... wait for a strong up bar after a buy alert, or a strong down bar following a short alert".
    - BB(20, 2); Intraday Intensity (Bostian) normalized over 21 bars: sum((2C - H - L) / (H - L) x V) / sum(V);
    - the alert: a bar whose low tagged the lower band (high the upper) with II% > 0 (< 0), within the last 5 bars;
    - the confirmation, on the bar that just closed (the first after the alert): a strong bar in the trade's way -
      body >= half its range, close in the outer third, range >= the median range of the last 20 bars (ours: the
      manual gives no number);
    - stop beyond the extreme since the alert, the first target the opposite band (the manual names neither: ours, as
      the W / M). Journaled in shadow (SignalBook: 'bb3_shadow') beside the W / M.
    """
    n = len(bars)
    if n < 45:
        return None
    o, h, l, c = _arr(bars, 1), _arr(bars, 2), _arr(bars, 3), _arr(bars, 4)
    v = np.asarray([float(b[5]) if len(b) > 5 and b[5] is not None else 0.0 for b in bars])
    ma, sd = rolling_mean(c, 20), rolling_std(c, 20)
    upper, lower = ma + 2 * sd, ma - 2 * sd
    rng = h - l
    clv = np.where(rng > 0, (2 * c - h - l) / np.where(rng > 0, rng, 1), 0.0)
    i = n - 1
    med = float(np.median(rng[i - 20:i]))
    for d in (1, -1):
        alerts = []
        for k in range(i - 5, i):
            s_v = v[k - 20:k + 1].sum()
            ii = (clv[k - 20:k + 1] * v[k - 20:k + 1]).sum() / s_v if s_v > 0 else 0.0
            tag = l[k] <= lower[k] if d > 0 else h[k] >= upper[k]
            if tag and (ii > 0 if d > 0 else ii < 0):
                alerts.append((k, ii))
        if not alerts:
            continue
        k, ii = alerts[-1]

        def strong(j):
            body, r = c[j] - o[j], rng[j]
            return r > 0 and d * body >= 0.5 * r and r >= med and \
                ((c[j] - l[j]) / r >= 2 / 3 if d > 0 else (h[j] - c[j]) / r >= 2 / 3)
        if not strong(i) or any(strong(j) for j in range(k + 1, i)):
            continue
        stop = float(l[k:i + 1].min() if d > 0 else h[k:i + 1].max())
        target = float(upper[i] if d > 0 else lower[i])
        return {'setup': 'BB3 BUY' if d > 0 else 'BB3 SELL', 'direction': d,
                'setup_note': f"{tf} Bollinger Method III: {'lower' if d > 0 else 'upper'} band tag with Intraday "
                              f"Intensity {ii:+.2f} (alert), then a strong {'up' if d > 0 else 'down'} bar closed "
                              f"{c[i]:.6g} (the manual's confirmation)",
                'anchor_level': float(c[i]), 'anchor_extreme': stop, 'anchor_label': 'Bollinger Method III',
                'bb_stop': stop, 'bb_target': target, 'bb_ii': float(ii),
                'anchor_ts': int(bars[k][0]), 'anchor_close': float(c[i]), 'event_ts': int(bars[-1][0]) + period_ms,
                'bb_tf': tf}
    return None


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
    start = 20                         # eng-121: the whole history with bands (the 30-candle window was ours)
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
