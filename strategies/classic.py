"""
Classic published methods added as their authors define them (eng-29), detected in the maps worker at candle closes:

- value_area  Dalton's 80% rule (The Profile Reports 1987-91; Dalton "Mind Over Markets"): the day opens outside the
              previous day's value area (70% of its volume around the POC), comes back into it and stays there for two
              consecutive 30-minute periods -> the market tends to traverse the whole value area. Entry at the second
              period's close, target the opposite edge, stop beyond the edge it re-entered through (outside the value
              area is where the idea is wrong). Crypto has no session open: the UTC day is the session. The value
              area is the TPO one (time at price, eng-58), as Dalton's; the 60 price rows are ours.
- orb         Toby Crabel's opening range breakout ("Day Trading with Short Term Price Patterns and Opening Range
              Breakout", 1990) as the book defines it (eng-55; Oxfordstrat, Crabel's pattern definitions): stop
              orders at the day's open +- the Stretch (10-day SMA of min(High - Open, Open - Low)); the first touched
              is the trade, the other level its stop; out at the session's close. Crypto's day opens 00:00 UTC.
              Checked loop-side on every final minute (strategies.loopside.LoopDetectors._orb_touch). NR4 / NR7 (Crabel's contraction days)
              are journaled. (eng-29..54 used a 30-minute range after the US equity open and a 15m close: not his rule.)
- connors     Larry Connors' RSI(2) ("Short Term Trading Strategies That Work", 2008): with the trend (close above the
              200-day SMA) buy when RSI(2) < 5 (eng-58; the original 2-period RSI rule - < 10 is a later variant),
              exit on a close above the 5-day SMA (shorts mirrored: below the
              SMA200, RSI(2) > 90, out below the SMA5), on DAILY candles (fetcher._daily_candles_loop), checked
              loop-side once per coin after each daily close (strategies.loopside.LoopDetectors._connors_daily). He uses no stop: a perpetual
              needs one for the margin, so a catastrophic stop 3 daily ATR away (our deviation, journaled as such).
"""
import math
from typing import Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo

from config import CONFIG

QUARTER_MS = 900_000
HOUR_MS = 3_600_000
DAY_MS = 86_400_000
NY = ZoneInfo('America/New_York')


# ------------------------------------------------------------------------------------------------ value area

def value_area(candles: Sequence[Sequence[float]], share: float = 0.70, buckets: int = 60, tpo: bool = False):
    """(VAL, POC, VAH) of the candles' volume spread evenly over each candle's range, else None. tpo: each candle
    weighs one time unit instead of its volume (Market Profile's TPO value area, Dalton - eng-58)."""
    if not candles:
        return None
    hi, lo = max(c[2] for c in candles), min(c[3] for c in candles)
    if hi <= lo:
        return None
    size = (hi - lo) / buckets
    vol = [0.0] * buckets
    for c in candles:
        a = min(buckets - 1, int((c[3] - lo) / size))
        b = min(buckets - 1, int((c[2] - lo) / size))
        part = (1.0 if tpo else (c[5] or 0.0)) / (b - a + 1)
        for k in range(a, b + 1):
            vol[k] += part
    total = sum(vol)
    if total <= 0:
        return None
    poc = max(range(buckets), key=lambda k: vol[k])
    i = j = poc
    acc = vol[poc]
    while acc < share * total and (i > 0 or j < buckets - 1):
        down = vol[i - 1] if i > 0 else -1.0
        up = vol[j + 1] if j < buckets - 1 else -1.0
        if up >= down:
            j += 1
            acc += vol[j]
        else:
            i -= 1
            acc += vol[i]
    return lo + i * size, lo + (poc + 0.5) * size, lo + (j + 1) * size


def _day_candles(m15: Sequence[Sequence[float]], day_start: int) -> List[Sequence[float]]:
    return [c for c in m15 if day_start <= c[0] < day_start + DAY_MS]


def value_area_event(m15: Sequence[Sequence[float]], cut: int) -> Optional[Dict]:
    """Dalton's 80% rule at the close of a 30-minute period (`cut` = close time of the last 15m candle)."""
    if cut % (2 * QUARTER_MS) or len(m15) < 100:
        return None
    today = cut - cut % DAY_MS
    prev = _day_candles(m15, today - DAY_MS)
    day = [c for c in _day_candles(m15, today) if c[0] < cut]
    if len(prev) < 90 or len(day) < 4:
        return None
    va = value_area(prev, tpo=True)               # Dalton's value area is TPO (time), not volume (eng-58)
    if va is None:
        return None
    val, poc, vah = va
    opened = day[0][1]
    if val <= opened <= vah:
        return None
    side = 1 if opened < val else -1            # opened below: back inside -> long to VAH; above -> short to VAL

    def inside(pair) -> bool:
        return val <= pair[-1][4] <= vah

    periods = [day[k:k + 2] for k in range(0, len(day) - 1, 2)]
    if len(periods) < 2 or not (inside(periods[-1]) and inside(periods[-2])):
        return None
    if len(periods) >= 3 and inside(periods[-3]):
        return None                               # the rule fired at the previous period already
    edge, far = (val, vah) if side > 0 else (vah, val)
    last = day[-1]
    if side * (far - last[4]) < 0.3 * (vah - val):
        return None       # eng-71: the value area is already traversed (XAU / ONDO / XPL: TP1 0.06-0.15% from the entry)
    extreme = min(c[3] for c in day) if side > 0 else max(c[2] for c in day)
    return {'setup': 'VA80 LONG' if side > 0 else 'VA80 SHORT', 'direction': side,
            'setup_note': f"opened {'below' if side > 0 else 'above'} yesterday's value area {val:.6g}-{vah:.6g} "
                          f"(POC {poc:.6g}), back inside for two 30m periods: Dalton's 80% rule -> the far edge",
            'anchor_level': edge, 'anchor_extreme': extreme, 'anchor_label': f"value area {'low' if side > 0 else 'high'}",
            'anchor_ts': today, 'anchor_close': last[4], 'va_far': far, 'va_poc': poc,
            'event_ts': int(last[0]) + QUARTER_MS}


# ------------------------------------------------------------------------------------------------ opening range

def stretch(d1: Sequence[Sequence[float]], days: int = 10) -> Optional[float]:
    """Crabel's Stretch: the SMA of the last `days` closed days' min(High - Open, Open - Low)."""
    if len(d1) < days:
        return None
    return sum(min(c[2] - c[1], c[1] - c[3]) for c in d1[-days:]) / days


def narrow_range(d1: Sequence[Sequence[float]], days: int) -> Optional[bool]:
    """Crabel's NR-n: the last closed day's range the smallest of the last n days (None without the history)."""
    if len(d1) < days:
        return None
    ranges = [c[2] - c[3] for c in d1[-days:]]
    return ranges[-1] <= min(ranges)


def orb_event(d1: Sequence[Sequence[float]], day_open: float, price_hi: float, price_lo: float,
              before_hi: Optional[float], before_lo: Optional[float], now_ms: int) -> Optional[Dict]:
    """
    Crabel's opening range breakout (eng-55, his book's rule): buy stop at Open + Stretch, sell stop at Open - Stretch
    on the day's open; the first level the price touches is the trade (on the touch, like a stop order), the other
    level is its stop. `d1`: closed daily candles; `before_hi` / `before_lo`: today's extremes before this minute (a
    level crossed earlier today is no fresh entry). NR4 / NR7 (Crabel's contraction filter) are journaled.
    """
    s = stretch(d1, CONFIG.strategies.orb_stretch_days)
    if not s or s <= 0 or not day_open:
        return None
    up, down = day_open + s, day_open - s
    if before_hi is not None and before_hi >= up or before_lo is not None and before_lo <= down:
        return None                                # one ORB a day: the first level already traded
    if price_hi >= up:
        side, level, other = 1, up, down
    elif price_lo <= down:
        side, level, other = -1, down, up
    else:
        return None
    nr7, nr4 = narrow_range(d1, 7), narrow_range(d1, 4)
    day_start = now_ms - now_ms % DAY_MS
    return {'setup': 'ORB UP' if side > 0 else 'ORB DOWN', 'direction': side,
            'setup_note': f"price touched the day's open {day_open:.6g} {'+' if side > 0 else '-'} Stretch {s:.6g} "
                          f"(Crabel){'; NR7 day' if nr7 else '; NR4 day' if nr4 else ''}",
            'anchor_level': level, 'anchor_extreme': other, 'anchor_label': 'open +- stretch',
            'anchor_ts': day_start, 'anchor_close': level, 'orb_hi': up, 'orb_lo': down, 'orb_stretch': s,
            'nr7': 1.0 if nr7 else 0.0 if nr7 is not None else None,
            'nr4': 1.0 if nr4 else 0.0 if nr4 is not None else None,
            'event_ts': int(now_ms // 60_000 * 60_000) + 60_000}


# ------------------------------------------------------------------------------------------------ Connors RSI(2)

def rsi(closes: Sequence[float], period: int) -> Optional[float]:
    """Wilder's RSI of the last close."""
    if len(closes) < period + 1:
        return None
    gains = losses = 0.0
    for a, b in zip(closes[:period], closes[1:period + 1]):
        gains += max(0.0, b - a)
        losses += max(0.0, a - b)
    avg_g, avg_l = gains / period, losses / period
    for a, b in zip(closes[period:], closes[period + 1:]):
        avg_g = (avg_g * (period - 1) + max(0.0, b - a)) / period
        avg_l = (avg_l * (period - 1) + max(0.0, a - b)) / period
    if avg_l == 0:
        return 100.0
    return 100 - 100 / (1 + avg_g / avg_l)


def connors_event(d1: Sequence[Sequence[float]], first: bool = True) -> Optional[Dict]:
    """
    Connors on DAILY candles (his system; the 1h version of eng-29's first draft was another system): the day that
    closed with RSI(2) in the extreme (`first`: not already there the day before - he is in until the SMA5 exit, a
    run of oversold days is one trade).
    """
    cfg = CONFIG.strategies
    h1 = d1
    if len(h1) < 202:
        return None
    closes = [c[4] for c in h1]
    sma200 = sum(closes[-200:]) / 200
    sma5 = sum(closes[-5:]) / 5
    r = rsi(closes[-60:], 2)
    if r is None or math.isnan(r):
        return None
    last = h1[-1]
    c = last[4]
    # eng-84, the cross-back filter (practice for crypto's one-way dumps): the day RSI(2) comes BACK out of the
    # extreme after at least one day in it - not the first day into it
    prev = rsi(closes[-61:-1], 2)
    if prev is None or math.isnan(prev):
        return None
    if c > sma200 and prev < cfg.connors_rsi_low <= r and c < sma5:
        side = 1
    elif c < sma200 and prev > cfg.connors_rsi_high >= r and c > sma5:
        side = -1
    else:
        return None
    extreme = min(x[3] for x in h1[-3:]) if side > 0 else max(x[2] for x in h1[-3:])
    trs = [max(x[2], p[4]) - min(x[3], p[4]) for p, x in zip(h1[-21:-1], h1[-20:])]
    atr = sum(trs) / len(trs) if trs else None
    return {'setup': 'RSI2 LONG' if side > 0 else 'RSI2 SHORT', 'direction': side, 'connors_atr': atr,
            'setup_note': f"daily RSI(2) {r:.0f} {'below ' + format(cfg.connors_rsi_low, 'g') + ' above' if side > 0 else 'above ' + format(cfg.connors_rsi_high, 'g') + ' below'} the SMA200 "
                          f"{sma200:.6g} (Connors); exit at the SMA5 {sma5:.6g}",
            'anchor_level': c, 'anchor_extreme': extreme, 'anchor_label': 'RSI(2) extreme',
            'anchor_ts': int(last[0]), 'anchor_close': c, 'connors_sma5': sma5, 'rsi2': r,
            'event_ts': int(last[0]) + DAY_MS}


def classic_events(m15: List[List[float]], h1: List[List[float]], cut: int) -> List[Dict]:
    out = []
    found = value_area_event(m15, cut)
    if found:
        out.append(found)
    return out                     # ORB (on the touch) and Connors' RSI(2) run on daily candles, loop-side (Scanner)
