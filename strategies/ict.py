"""
ICT / SMC readings of a plan (hypotheses, measured by the journal - never proven edges; Osler's NY Fed SR150 backs only
the stop clustering beyond round numbers / levels):

- protected swing: the last 15m pivot on the stop side that produced a break of structure (a later close beyond the
  opposite pivot before it). While it holds, the idea holds: the stop goes beyond it, not right behind an obvious
  unswept pool (equal lows, the day's low: the stops a raid takes before the move).
- premium / discount: where the entry sits in the dealing range (the last 48 1h candles' high - low), for the trade's
  direction: 0 = the cheapest end (a long at the range low), 1 = the dearest. ICT buys only in discount (< 0.5).
  Journaled as `range_pos`, split in stats.py; a filter only if the journal proves it.
"""
from typing import Optional, Sequence, Tuple

PIVOT = 3
LOOKBACK = 96          # 15m candles (24h)
RANGE_HOURS = 48


def protected_swing(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
                    direction: int) -> Optional[float]:
    """The price of the protected swing (the most recent one), None without a break of structure in the window."""
    n = len(closes)
    start = max(PIVOT, n - LOOKBACK)
    piv_hi = [i for i in range(start, n - PIVOT)
              if highs[i] == max(highs[i - PIVOT:i + PIVOT + 1])]
    piv_lo = [i for i in range(start, n - PIVOT)
              if lows[i] == min(lows[i - PIVOT:i + PIVOT + 1])]
    own, opp = (piv_lo, piv_hi) if direction > 0 else (piv_hi, piv_lo)
    for i in reversed(own):
        before = [j for j in opp if j < i]
        if not before:
            continue
        level = highs[before[-1]] if direction > 0 else lows[before[-1]]
        broke = any((closes[k] > level) if direction > 0 else (closes[k] < level) for k in range(i + 1, n))
        if broke:
            return lows[i] if direction > 0 else highs[i]
    return None


def dealing_range(h1: Sequence[Sequence[float]]) -> Optional[Tuple[float, float]]:
    rows = list(h1)[-RANGE_HOURS:]
    if len(rows) < 12:
        return None
    lo, hi = min(r[3] for r in rows), max(r[2] for r in rows)
    return (lo, hi) if hi > lo else None


def range_position(rng: Optional[Sequence[float]], price: float, direction: int) -> Optional[float]:
    """0 = the cheapest end of the dealing range for this direction, 1 = the dearest (clipped)."""
    if not rng:
        return None
    lo, hi = rng
    pos = (price - lo) / (hi - lo)
    pos = pos if direction > 0 else 1 - pos
    return max(0.0, min(1.0, pos))


def fvg_trigger(ltf: Sequence[Sequence[float]], direction: int, since_ms: int, interval_ms: int) -> Optional[dict]:
    """
    ICT entry after a liquidity sweep: displacement (a candle with a body >= half its range in the trade's direction)
    that leaves a fair value gap (long: low[i] > high[i-2]) and shifts structure (a close beyond the highest high /
    lowest low since the sweep, before the displacement); the entry is the first later candle that retraces into the
    gap and closes without closing through it. A close through the gap kills it; the next displacement is searched.
    """
    start = next((k for k, x in enumerate(ltf) if x[0] + interval_ms > since_ms), None)
    if start is None or len(ltf) - start < 4:
        return None
    o = [x[1] for x in ltf]
    h = [x[2] for x in ltf]
    l = [x[3] for x in ltf]
    c = [x[4] for x in ltf]
    for i in range(start + 2, len(ltf) - 1):
        j = i - 1                                          # the displacement candle
        body, span = abs(c[j] - o[j]), h[j] - l[j]
        if span <= 0 or body < 0.5 * span or (c[j] - o[j]) * direction <= 0:
            continue
        if direction > 0:
            if not l[i] > h[i - 2]:
                continue
            gap_lo, gap_hi = h[i - 2], l[i]
            swing = max(h[start:j]) if j > start else h[start]
            if max(c[j], c[i]) <= swing:
                continue
        else:
            if not h[i] < l[i - 2]:
                continue
            gap_lo, gap_hi = h[i], l[i - 2]
            swing = min(l[start:j]) if j > start else l[start]
            if min(c[j], c[i]) >= swing:
                continue
        for k in range(i + 1, len(ltf)):
            if (c[k] < gap_lo) if direction > 0 else (c[k] > gap_hi):
                break                                      # closed through the gap: dead
            touched = l[k] <= gap_hi if direction > 0 else h[k] >= gap_lo
            if touched:
                seg = ltf[start:k + 1]
                ext = min(seg, key=lambda x: x[3]) if direction > 0 else max(seg, key=lambda x: x[2])
                return {'entry': c[k], 'extreme': ext[3] if direction > 0 else ext[2],
                        'time': int(ltf[k][0]) + interval_ms, 'extreme_time': int(ext[0])}
    return None


def touch_trigger(ltf: Sequence[Sequence[float]], direction: int, since_ms: int, interval_ms: int,
                  zone_lo: float, zone_hi: float) -> Optional[dict]:
    """
    Sam Seiden's entry: a resting limit at the fresh zone's PROXIMAL line, filled by the first candle that trades into
    it (at the open if it gapped past the line); the extreme is that candle's wick.
    """
    for x in ltf:
        if x[0] + interval_ms <= since_ms:
            continue
        o, hi, lo = x[1], x[2], x[3]
        if direction > 0 and lo <= zone_hi:
            return {'entry': min(o, zone_hi), 'extreme': lo, 'time': int(x[0]) + interval_ms, 'extreme_time': int(x[0])}
        if direction < 0 and hi >= zone_lo:
            return {'entry': max(o, zone_lo), 'extreme': hi, 'time': int(x[0]) + interval_ms, 'extreme_time': int(x[0])}
    return None
