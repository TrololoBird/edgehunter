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


def dealing_range(h1: Sequence[Sequence[float]], k: int = 3) -> Optional[Tuple[float, float]]:
    """
    ICT's dealing range (eng-51): the leg between the latest significant swing low and swing high (1h pivots with k
    candles on each side), equilibrium at its 50%. Was the 48h high / low window - a time box is not ICT's definition.
    Falls back to the window while the 1h history holds no pivot pair.
    """
    rows = list(h1)
    if len(rows) < 12:
        return None
    highs = [i for i in range(k, len(rows) - k)
             if rows[i][2] == max(r[2] for r in rows[i - k:i + k + 1])]
    lows = [i for i in range(k, len(rows) - k)
            if rows[i][3] == min(r[3] for r in rows[i - k:i + k + 1])]
    if highs and lows:
        hi_i, lo_i = highs[-1], lows[-1]
        # the range is the last leg: the latest pivot and the opposite pivot that started it
        if hi_i > lo_i:
            lo = rows[lo_i][3]
            hi = max(r[2] for r in rows[lo_i:])
        else:
            hi = rows[hi_i][2]
            lo = min(r[3] for r in rows[hi_i:])
        if hi > lo:
            return lo, hi
    window = rows[-RANGE_HOURS:]
    lo, hi = min(r[3] for r in window), max(r[2] for r in window)
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
        span = h[j] - l[j]
        if span <= 0 or (c[j] - o[j]) * direction <= 0:     # eng-119: no body share (ours) - the FVG is the displacement
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
            # ICT's consequent encroachment: the limit rests at the gap's 50% (eng-36; was the first touch of its edge,
            # entered at that candle's close)
            ce = (gap_lo + gap_hi) / 2
            touched = l[k] <= ce if direction > 0 else h[k] >= ce
            if touched:
                seg = ltf[start:k + 1]
                ext = min(seg, key=lambda x: x[3]) if direction > 0 else max(seg, key=lambda x: x[2])
                fill = min(o[k], ce) if direction > 0 else max(o[k], ce)
                return {'entry': fill, 'extreme': ext[3] if direction > 0 else ext[2],
                        'time': int(ltf[k][0]) + interval_ms, 'extreme_time': int(ext[0])}
    return None


def fvg_setup(ltf: Sequence[Sequence[float]], direction: int, since_ms: int, interval_ms: int) -> Optional[dict]:
    """
    ICT's 2022 model after a liquidity sweep at `since_ms` (eng-58): a displacement candle (body >= half its range, in
    the trade's direction) that CLOSES BEYOND THE SWING THE RAID CAME FROM - the last 3-candle swing high (long; low
    for a short) of the bars before the sweep, the market structure shift - and leaves a fair value gap. Returns the
    gap and its consequent encroachment (CE, 50%) for a resting limit; the entry is that limit's fill (touch_trigger),
    not a later candle's close. eng-36..57 took any close above the highest high SINCE the sweep as the shift.
    """
    # review V02: resample drops an incomplete bar, so neighbours in the list can be hours apart - only the run of
    # time-contiguous bars ending at the last one is read (a gap / MSS across a hole is no structure)
    k0 = len(ltf) - 1
    while k0 > 0 and int(ltf[k0][0]) - int(ltf[k0 - 1][0]) == interval_ms:
        k0 -= 1
    ltf = ltf[k0:]
    start = next((k for k, x in enumerate(ltf) if x[0] + interval_ms > since_ms), None)
    if start is None or len(ltf) - start < 3 or start < 3:
        return None
    o = [x[1] for x in ltf]
    h = [x[2] for x in ltf]
    l = [x[3] for x in ltf]
    c = [x[4] for x in ltf]
    # the swing the raid came from: the last 3-candle pivot before the sweep (up to 48 bars back)
    swing = None
    for k in range(start - 2, max(0, start - 48), -1):
        if direction > 0 and h[k] > h[k - 1] and h[k] > h[k + 1]:
            swing = h[k]
            break
        if direction < 0 and l[k] < l[k - 1] and l[k] < l[k + 1]:
            swing = l[k]
            break
    if swing is None:
        return None
    for i in range(start + 2, len(ltf)):
        j = i - 1                                          # the displacement candle
        span = h[j] - l[j]
        if span <= 0 or (c[j] - o[j]) * direction <= 0:     # eng-119: no body share (ours) - the FVG is the displacement
            continue
        if direction > 0:
            if not (l[i] > h[i - 2] and max(c[j], c[i]) > swing):
                continue
            gap_lo, gap_hi = h[i - 2], l[i]
        else:
            if not (h[i] < l[i - 2] and min(c[j], c[i]) < swing):
                continue
            gap_lo, gap_hi = h[i], l[i - 2]
        seg = ltf[start:i + 1]
        ext = min(seg, key=lambda x: x[3]) if direction > 0 else max(seg, key=lambda x: x[2])
        return {'gap_lo': gap_lo, 'gap_hi': gap_hi, 'ce': (gap_lo + gap_hi) / 2, 'mss': swing,
                'extreme': ext[3] if direction > 0 else ext[2], 'time': int(ltf[i][0]) + interval_ms}
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


def touch_confirm(ltf: Sequence[Sequence[float]], direction: int, since_ms: int, interval_ms: int,
                  zone_lo: float, zone_hi: float) -> Optional[dict]:
    """
    eng-105, the owner: the touch confirmed by a CLOSE - the first closed trigger candle (since the zone was reached)
    that traded into the zone and closed back beyond its proximal line on the trade's side (a long: low <= zone_hi and
    close > zone_hi; a 'zone' of one price - a CE - the same with that price). The entry is that close; the extreme
    is the lowest low (highest high) since the zone was reached. A close through the zone's far side is no entry.
    """
    seen = [x for x in ltf if x[0] + interval_ms > since_ms]
    for k, x in enumerate(seen):
        hi, lo, close = x[2], x[3], x[4]
        if direction > 0:
            touched, back = lo <= zone_hi, close > zone_hi
        else:
            touched, back = hi >= zone_lo, close < zone_lo
        if touched and back:
            part = seen[:k + 1]
            extreme = min(c[3] for c in part) if direction > 0 else max(c[2] for c in part)
            return {'entry': close, 'extreme': extreme, 'time': int(x[0]) + interval_ms, 'extreme_time': int(x[0])}
    return None
