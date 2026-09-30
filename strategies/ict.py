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
