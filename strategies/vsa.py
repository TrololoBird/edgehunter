"""
Volume Spread Analysis (Tom Williams, "Master the Markets"; Wyckoff's effort vs result): every bar read by its volume,
its spread (high - low) and where it closed within the spread, against the bars before it.

For an entry the question is whether the bars since the extreme show the other side giving up:
- long:  NO SUPPLY / TEST (a down bar with a narrow spread on volume below the two bars before: nobody sells),
         STOPPING VOLUME (a down bar on >= 2x the average volume that closes in its upper half: buyers absorbed the
         selling), SPRING-like bars count as tests;
- short: NO DEMAND (an up bar, narrow spread, volume below the two before), UPTHRUST (a new high closing in its lower
         third on volume above the two before), BUYING CLIMAX (an up bar on >= 2x volume closing in its lower half).
Bars against the trade with these signs of the OTHER side (no demand at a long, stopping volume at a short) make the
reading negative. Returns the sign's name (positive), False (an opposing sign or none) - a confirmation `vsa`.
"""
from typing import List, Optional, Sequence

AVG_BARS = 20


def close_location(bar: Sequence[float]) -> float:
    """0 = closed at the low, 1 = at the high (0.5 for a bar without range)."""
    span = bar[2] - bar[3]
    return (bar[4] - bar[3]) / span if span > 0 else 0.5


def signs(bars: List[List[float]], i: int) -> List[str]:
    """VSA signs of bar i (needs AVG_BARS before it). Bars: [ts, o, h, l, c, volume, ...]."""
    if i < max(2, AVG_BARS) or i >= len(bars):
        return []
    b, p1, p2 = bars[i], bars[i - 1], bars[i - 2]
    hist = bars[i - AVG_BARS:i]
    avg_vol = sum(x[5] for x in hist) / AVG_BARS
    avg_spread = sum(x[2] - x[3] for x in hist) / AVG_BARS
    if avg_vol <= 0 or avg_spread <= 0:
        return []
    vol, spread, loc = b[5], b[2] - b[3], close_location(b)
    narrow = spread < 0.7 * avg_spread
    low_vol = vol < p1[5] and vol < p2[5]
    high_vol = vol >= 2 * avg_vol
    up, down = b[4] > p1[4], b[4] < p1[4]
    out = []
    if down and narrow and low_vol:
        out.append('no_supply')
    if up and narrow and low_vol and loc <= 0.6:
        out.append('no_demand')
    if down and high_vol and loc >= 0.5:
        out.append('stopping_volume')
    if up and high_vol and loc <= 0.5:
        out.append('buying_climax')
    if b[2] > max(p1[2], p2[2]) and loc <= 1 / 3 and vol > p1[5] and vol > p2[5]:
        out.append('upthrust')
    if b[3] < min(p1[3], p2[3]) and loc >= 2 / 3 and vol > p1[5] and vol > p2[5]:
        out.append('reverse_upthrust')
    return out


BULL = ('no_supply', 'stopping_volume', 'reverse_upthrust')
BEAR = ('no_demand', 'buying_climax', 'upthrust')


def confirm(bars: List[List[float]], since_ms: int, direction: int) -> Optional[object]:
    """The last VSA sign since `since_ms` (bars opened at / after it): its name when it backs the trade, else False."""
    good, bad = (BULL, BEAR) if direction > 0 else (BEAR, BULL)
    found = None
    for i, b in enumerate(bars):
        if b[0] < since_ms:
            continue
        for s in signs(bars, i):
            if s in good:
                found = s
            elif s in bad:
                found = False
    return found if found else False
