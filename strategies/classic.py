"""
Classic published methods added as their authors define them (eng-29), detected in the maps worker at candle closes:

- value_area  Dalton's 80% rule (The Profile Reports 1987-91; Dalton "Mind Over Markets"): the day opens outside the
              previous day's value area (70% of its volume around the POC), comes back into it and stays there for two
              consecutive 30-minute periods -> the market tends to traverse the whole value area. Entry at the second
              period's close, target the opposite edge, stop beyond the edge it re-entered through (outside the value
              area is where the idea is wrong). Crypto has no session open: the UTC day is the session.
- orb         Toby Crabel's opening range breakout ("Day Trading with Short Term Price Patterns and Opening Range
              Breakout", 1990): the range of the first 30 minutes of the session; a close beyond it is taken in its
              direction, the stop at the range's other side. For crypto the session is the US equity open (09:30 New
              York, DST-aware): the largest volume shift of the day. Crabel's narrow-range days (NR4 / NR7: yesterday's
              range the smallest of 4 / 7) precede the larger expansions: journaled (`nr7`), not a filter.
- connors     Larry Connors' RSI(2) ("Short Term Trading Strategies That Work", 2008): with the trend (close above the
              200-period SMA) buy when RSI(2) < 10, exit on a close above the 5-period SMA (shorts mirrored: below the
              SMA200, RSI(2) > 90, out below the SMA5). Connors trades daily bars; the bot's 1h candles are the
              closest it holds with 200 periods. He uses no stop: ours is the structure beyond the entry (the journal
              needs an R), the target is the SMA5 at the entry (his exit is a close beyond it). Expected: high hit
              rate, small targets - most entries fail R:R >= 2 and are journaled `low_rr`, the replay measures them.
"""
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo

from config import CONFIG

QUARTER_MS = 900_000
HOUR_MS = 3_600_000
DAY_MS = 86_400_000
NY = ZoneInfo('America/New_York')


# ------------------------------------------------------------------------------------------------ value area

def value_area(candles: Sequence[Sequence[float]], share: float = 0.70, buckets: int = 60):
    """(VAL, POC, VAH) of the candles' volume spread evenly over each candle's range, else None."""
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
        part = (c[5] or 0.0) / (b - a + 1)
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
    va = value_area(prev)
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
    extreme = min(c[3] for c in day) if side > 0 else max(c[2] for c in day)
    return {'setup': 'VA80 LONG' if side > 0 else 'VA80 SHORT', 'direction': side,
            'setup_note': f"opened {'below' if side > 0 else 'above'} yesterday's value area {val:.6g}-{vah:.6g} "
                          f"(POC {poc:.6g}), back inside for two 30m periods: Dalton's 80% rule -> the far edge",
            'anchor_level': edge, 'anchor_extreme': extreme, 'anchor_label': f"value area {'low' if side > 0 else 'high'}",
            'anchor_ts': today, 'anchor_close': last[4], 'va_far': far, 'va_poc': poc,
            'event_ts': int(last[0]) + QUARTER_MS}


# ------------------------------------------------------------------------------------------------ opening range

def _ny_open_ms(cut: int) -> int:
    """09:30 New York of the New York day `cut` falls in (epoch ms)."""
    local = datetime.fromtimestamp(cut / 1000, tz=timezone.utc).astimezone(NY)
    return int(local.replace(hour=9, minute=30, second=0, microsecond=0).timestamp() * 1000)


def narrow_range(h1: Sequence[Sequence[float]], days: int, cut: int) -> Optional[bool]:
    """Crabel's NR-n: yesterday's (UTC) range the smallest of the last n days (None without the history)."""
    today = cut - cut % DAY_MS
    ranges = []
    for k in range(1, days + 1):
        day = [c for c in h1 if today - k * DAY_MS <= c[0] < today - (k - 1) * DAY_MS]
        if len(day) < 20:
            return None
        ranges.append(max(c[2] for c in day) - min(c[3] for c in day))
    return ranges[0] <= min(ranges)


def orb_event(m15: Sequence[Sequence[float]], h1: Sequence[Sequence[float]], cut: int) -> Optional[Dict]:
    """The first 15m close beyond the first 30 minutes' range after the US equity open, within 2.5h of the open."""
    cfg = CONFIG.strategies
    start = _ny_open_ms(cut)
    or_end = start + cfg.orb_minutes * 60_000
    if not or_end < cut <= start + cfg.orb_window_min * 60_000:
        return None
    opening = [c for c in m15 if start <= c[0] < or_end]
    after = [c for c in m15 if or_end <= c[0] < cut]
    if len(opening) < cfg.orb_minutes // 15 or not after:
        return None
    hi, lo = max(c[2] for c in opening), min(c[3] for c in opening)
    last = after[-1]
    earlier = after[:-1]
    if any(c[4] > hi or c[4] < lo for c in earlier):
        return None                                # only the first break of the day
    if last[4] > hi:
        side = 1
    elif last[4] < lo:
        side = -1
    else:
        return None
    nr7 = narrow_range(h1, 7, cut)
    nr4 = narrow_range(h1, 4, cut)
    edge, other = (hi, lo) if side > 0 else (lo, hi)
    return {'setup': 'ORB UP' if side > 0 else 'ORB DOWN', 'direction': side,
            'setup_note': f"15m close {'above' if side > 0 else 'below'} the US-open 30m range {lo:.6g}-{hi:.6g} "
                          f"(Crabel){'; NR7 day' if nr7 else '; NR4 day' if nr4 else ''}",
            'anchor_level': edge, 'anchor_extreme': other, 'anchor_label': 'opening range',
            'anchor_ts': start, 'anchor_close': last[4], 'orb_hi': hi, 'orb_lo': lo,
            'nr7': 1.0 if nr7 else 0.0 if nr7 is not None else None,
            'nr4': 1.0 if nr4 else 0.0 if nr4 is not None else None,
            'event_ts': int(last[0]) + QUARTER_MS}


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


def connors_event(h1: Sequence[Sequence[float]], first: bool = True) -> Optional[Dict]:
    """The hour RSI(2) crossed into the extreme (`first`: not already there an hour earlier: Connors is in until the
    SMA5 exit, a run of oversold hours is one trade)."""
    cfg = CONFIG.strategies
    if len(h1) < 202:
        return None
    if first and connors_event(h1[:-1], first=False) is not None:
        return None
    closes = [c[4] for c in h1]
    sma200 = sum(closes[-200:]) / 200
    sma5 = sum(closes[-5:]) / 5
    r = rsi(closes[-60:], 2)
    if r is None or math.isnan(r):
        return None
    last = h1[-1]
    c = last[4]
    if c > sma200 and r < cfg.connors_rsi_low and c < sma5:
        side = 1
    elif c < sma200 and r > cfg.connors_rsi_high and c > sma5:
        side = -1
    else:
        return None
    extreme = min(x[3] for x in h1[-3:]) if side > 0 else max(x[2] for x in h1[-3:])
    return {'setup': 'RSI2 LONG' if side > 0 else 'RSI2 SHORT', 'direction': side,
            'setup_note': f"1h RSI(2) {r:.0f} {'below 10 above' if side > 0 else 'above 90 below'} the SMA200 "
                          f"{sma200:.6g} (Connors); exit at the SMA5 {sma5:.6g}",
            'anchor_level': c, 'anchor_extreme': extreme, 'anchor_label': 'RSI(2) extreme',
            'anchor_ts': int(last[0]), 'anchor_close': c, 'connors_sma5': sma5, 'rsi2': r,
            'event_ts': int(last[0]) + HOUR_MS}


def classic_events(m15: List[List[float]], h1: List[List[float]], cut: int) -> List[Dict]:
    out = []
    for found in (value_area_event(m15, cut), orb_event(m15, h1, cut)):
        if found:
            out.append(found)
    if cut % HOUR_MS == 0:
        found = connors_event(h1)
        if found:
            out.append(found)
    return out
