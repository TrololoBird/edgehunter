"""
Breakout with initiative (BREAKOUT UP / BREAKOUT DOWN). Most crypto breakouts fail (60-70% by the usual estimates):
a breakout counts only when a candle of the structure timeframe CLOSES beyond the range on volume, the aggressive flow
is on its side, and the next candle closes beyond too (acceptance). This is the "initiative" reading of large
aggressive flow; the same flow absorbed at a level is the absorption strategy, and a stop run that fails is a sweep.

Anchor: the range of the breakout_range_candles 15m candles before the breakout candle. Entry at the acceptance close
(the confirmation) when R:R allows it, else a retest of the edge with a 5m structure shift; stop at the range middle
(>= the stop floor); INVALID back inside past the middle; targets: map beyond the edge, measured moves of the range.
"""
from typing import Dict, Optional, Sequence

from config import CONFIG
from strategies.base import PlanInput, Strategy, base_plan
from strategies.geometry import select_targets
from strategies.level import reached_since
from zones import RawLevel, merge

QUARTER_MS = 900_000


def breakout_at_close(candles_15m: Sequence[Sequence[float]], atr: float,
                      candles_1h: Sequence[Sequence[float]] = ()) -> Optional[Dict]:
    """The previous candle broke out of the range on volume and flow, the one that just closed held beyond it."""
    cfg = CONFIG.strategies
    n = cfg.breakout_range_candles
    if len(candles_15m) < n + 2 or not atr:
        return None
    rng, b, a = candles_15m[-n - 2:-2], candles_15m[-2], candles_15m[-1]
    hi, lo = max(c[2] for c in rng), min(c[3] for c in rng)
    width = hi - lo
    # Tightness against the ATR of the day BEFORE the range: ATR14 contains the range itself, so a quiet range
    # shrank its own yardstick (NR-type contraction is measured against a longer baseline)
    before = candles_15m[max(0, len(candles_15m) - n - 2 - 96):-n - 2]
    base_atr = (sum(max(c[2] - c[3], abs(c[2] - p[4]), abs(c[3] - p[4])) for p, c in zip(before, before[1:]))
                / (len(before) - 1)) if len(before) >= 25 else atr
    if not cfg.breakout_min_width_atr * base_atr <= width <= cfg.breakout_max_width_atr * base_atr:
        return None
    # Volume against the quiet range AND the same hour of the day (volume peaks at the US open: a break then cleared
    # "1.5x the range" by the clock alone)
    avg_volume = sum(c[5] for c in rng) / n
    hour = int(b[0]) // 3_600_000 % 24
    same_hour = sorted(c[5] for c in candles_1h if int(c[0]) // 3_600_000 % 24 == hour and c[0] < b[0])[-7:]
    hour_ref = same_hour[len(same_hour) // 2] / 4 if len(same_hour) >= 3 else 0.0
    reference = max(avg_volume, hour_ref)
    flow = 2 * b[6] - b[5]
    if not reference or b[5] < cfg.breakout_min_rvol * reference:
        return None
    if b[4] > hi and flow > 0 and a[4] > hi:
        direction = 1
    elif b[4] < lo and flow < 0 and a[4] < lo:
        direction = -1
    else:
        return None
    return {'setup': 'BREAKOUT UP' if direction > 0 else 'BREAKOUT DOWN', 'direction': direction,
            'setup_note': f"15m closed {'above' if direction > 0 else 'below'} a {width / atr:.1f} ATR range "
                          f"{lo:.6g}-{hi:.6g} on {b[5] / avg_volume:.1f}x volume with {'buying' if flow > 0 else 'selling'}, "
                          f"the next close held",
            'range_lo': lo, 'range_hi': hi, 'anchor_ts': int(rng[0][0]), 'break_ts': int(b[0]),
            'anchor_close': a[4], 'event_ts': int(a[0]) + QUARTER_MS}


class BreakoutStrategy(Strategy):
    name = 'breakout'
    requires = ('spot',)
    anchor_type = 'range'
    setups = {'BREAKOUT UP': 1, 'BREAKOUT DOWN': -1}
    ttl_key = 'breakout_ttl'

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('break_ts'), x.sig.get('range_hi')) if x.sig.get('range_hi') is not None else None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        cfg = CONFIG.strategies
        sig, d, atr = x.sig, x.direction, x.atr
        if sig.get('range_hi') is None or not atr:
            return None
        lo, hi = sig['range_lo'], sig['range_hi']
        edge, mid = (hi if d > 0 else lo), (lo + hi) / 2
        unit = max(hi - lo, cfg.breakout_min_move_atr * atr)
        measured = [edge + d * m * unit for m in cfg.breakout_measured_moves]
        zones = merge(list(x.raw_levels or []) + [RawLevel(hi, 'range', 'range high', +1),
                                                   RawLevel(lo, 'range', 'range low', -1)], atr)
        reached = x.reached if x.reached is not None else reached_since(x.minutes, sig['event_ts'], sig['anchor_close'], d)
        targets, sources = select_targets(zones, reached, d, atr, 'measured', measured, 'measured move')
        zone = sorted((edge - d * cfg.breakout_zone_atr * atr, edge + d * cfg.breakout_zone_atr * atr))
        # break_ts: the breakout candle - the confirmation's window starts there, not at the range's first candle
        anchor = {'type': 'range', 'tf': '15m', 'lo': lo, 'hi': hi, 'ts': sig['anchor_ts'], 'break_ts': sig.get('break_ts')}
        return base_plan(x, self.name, anchor, '15m', entry='confirm', zone_lo=zone[0], zone_hi=zone[1],
                         zone_src='retest of the range edge',
                         invalid=mid - d * CONFIG.levels.stop_buffer_atr * atr, fix_invalid=True, missable=True,
                         stop_mid=mid, intent='measured', fillers=tuple(measured), fill_label='measured move',
                         targets=targets, target_src=sources, zones=zones, reached=reached,
                         key=(sig['break_ts'], edge))
