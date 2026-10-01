"""
Wyckoff springs and upthrusts after distribution (UTAD) as Wyckoff defines them (Pruden, "The Three Skills of Top
Trading"; Weis, "Trades About to Happen"): events of an established TRADING RANGE that followed a trend's stop, on 1h.

- The range: the last R 1h candles before the event (R = 168 / 96 / 48 / 24, the longest that qualifies) moved
  sideways: the net move over them <= half their high - low.
- The trend it stopped: the close R + 48 candles back lay beyond the range (above it for accumulation - price came
  down into it; below it for distribution).
- SPRING (phase C of accumulation): the 1h candle that just closed traded below the range low and closed back inside,
  its lower wick >= half the candle, the pierce <= 30% of the range height. UTAD mirrored at the range high.
- The trade (Wyckoff buys the test, not the spring): a pullback toward the spring's area; the entry on the 15m
  structure shift there; the stop beyond the spring's low (+ the protected swing / measured pierce of the geometry);
  the first target the range's far side (the "range" intent), then the map beyond.

Replaces the 15m "BULL B / BEAR C" phase scores (a 5-hour window called a range; C was a CVD divergence at a new
high with no range at all). BULL E, the selling climax, is not bought: Wyckoff reads it as the range's start.
"""
from typing import Dict, List, Optional, Sequence

from strategies.base import PlanInput, Strategy, base_plan
from strategies.geometry import select_targets
from zones import RawLevel, merge

HOUR_MS = 3_600_000
WINDOWS = (168, 96, 48, 24)
TREND_BACK = 48
MAX_PIERCE = 0.30


def wyckoff_events(h1: Sequence[Sequence[float]]) -> List[Dict]:
    """A spring / UTAD on the 1h candle that just closed (h1[-1]), else []."""
    if len(h1) < WINDOWS[-1] + TREND_BACK + 2:
        return []
    last = h1[-1]
    o, h, l, c = last[1], last[2], last[3], last[4]
    span = h - l
    if span <= 0:
        return []
    for r in WINDOWS:
        if len(h1) < r + TREND_BACK + 2:
            continue
        rng = h1[-1 - r:-1]
        hi, lo = max(x[2] for x in rng), min(x[3] for x in rng)
        height = hi - lo
        if height <= 0 or abs(rng[-1][4] - rng[0][1]) > 0.5 * height:
            continue
        before = h1[-1 - r - TREND_BACK][4]
        if l < lo and c > lo and (min(o, c) - l) >= 0.5 * span and (lo - l) <= MAX_PIERCE * height and before > hi:
            return [_event('SPRING', 1, lo, hi, l, rng, last, r)]
        if h > hi and c < hi and (h - max(o, c)) >= 0.5 * span and (h - hi) <= MAX_PIERCE * height and before < lo:
            return [_event('UTAD', -1, lo, hi, h, rng, last, r)]
    return []


def _event(setup: str, d: int, lo: float, hi: float, extreme: float, rng, last, r: int) -> Dict:
    edge = lo if d > 0 else hi
    return {'setup': setup, 'direction': d,
            'setup_note': f"1h {'spring below' if d > 0 else 'upthrust above'} a {r}h trading range {lo:.6g}-{hi:.6g} "
                          f"after a {'decline' if d > 0 else 'rally'}: closed back inside; the entry waits for the test",
            'range_lo': lo, 'range_hi': hi, 'anchor_level': edge, 'anchor_extreme': extreme,
            'anchor_label': f"{r}h range {'low' if d > 0 else 'high'}", 'anchor_ts': int(rng[0][0]),
            'anchor_close': last[4], 'event_ts': int(last[0]) + HOUR_MS,
            # the spring candle's average FUTURES minute: Wyckoff's test must trade on less (levels.pullback_volume_ok)
            'fut_candle_minute_usd': float(last[5]) / 60 if len(last) > 5 else None}


class WyckoffRangeStrategy(Strategy):
    name = 'wyckoff'               # eng-35: one Wyckoff strategy (phase C here, the climax's test in cascade.py)
    anchor_type = 'range'
    setups = {'SPRING': 1, 'UTAD': -1}

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('anchor_ts'), x.sig.get('anchor_level')) if x.sig.get('range_lo') is not None else None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig, d, atr = x.sig, x.direction, x.atr
        if sig.get('range_lo') is None or not atr:
            return None
        lo, hi, extreme = sig['range_lo'], sig['range_hi'], sig['anchor_extreme']
        edge, far = (lo, hi) if d > 0 else (hi, lo)
        zones = merge(list(x.raw_levels or []) + [RawLevel(hi, 'range', 'range high', +1),
                                                   RawLevel(lo, 'range', 'range low', -1)], atr, symbol=x.symbol)
        targets, sources = select_targets(zones, edge, d, atr, 'range', (far,), 'range far side')
        # the test: back toward the spring's area (the spring's extreme to a fifth into the range)
        zone = sorted((extreme, edge + d * 0.2 * (hi - lo)))
        anchor = {'type': 'range', 'tf': '1h', 'lo': lo, 'hi': hi, 'ts': sig['anchor_ts']}
        return base_plan(x, self.name, anchor, '1h', entry='pullback', zone_lo=zone[0], zone_hi=zone[1],
                         zone_src=f"Wyckoff test of the {'spring' if d > 0 else 'upthrust'}", invalid=extreme,
                         fix_invalid=True, missable=True, stop_ref=extreme, intent='range', fillers=(far,),
                         fill_label='range far side', targets=targets, target_src=sources, zones=zones,
                         key=(sig['anchor_ts'], edge))
