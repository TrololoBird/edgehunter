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
from strategies.base import PlanInput, Strategy

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
    from levels import atr_of
    base_atr = (atr_of(before) or atr) if len(before) >= 25 else atr     # Wilder's ATR14 of that day (one ATR)
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


HOUR_MS = 3_600_000
DONCHIAN_HOURS = 480            # 20 days (the Turtles' System 1 channel)


def breakout_donchian(h1: Sequence[Sequence[float]]) -> Optional[Dict]:
    """
    The canonical breakout (Donchian / the Turtles' 20-day channel, with Market Profile's acceptance): the previous 1h
    candle CLOSED beyond the high / low of the 20 days before it, and the 1h candle that just closed held beyond it
    too. Volume and taker flow are recorded, not required (the Turtles used neither).
    """
    if len(h1) < DONCHIAN_HOURS + 2:
        return None
    rng, b, a = h1[-DONCHIAN_HOURS - 2:-2], h1[-2], h1[-1]
    hi, lo = max(c[2] for c in rng), min(c[3] for c in rng)
    if b[4] > hi and a[4] > hi and h1[-3][4] <= hi:
        d = 1
    elif b[4] < lo and a[4] < lo and h1[-3][4] >= lo:
        d = -1
    else:
        return None
    avg_volume = sum(c[5] for c in rng) / len(rng)
    flow = 2 * b[6] - b[5] if len(b) > 6 else 0.0
    return {'setup': 'BREAKOUT UP' if d > 0 else 'BREAKOUT DOWN', 'direction': d,
            'setup_note': f"1h closed {'above' if d > 0 else 'below'} the 20-day {'high' if d > 0 else 'low'} "
                          f"{hi if d > 0 else lo:.6g} (Donchian 20) and the next close held; volume "
                          f"{b[5] / avg_volume if avg_volume else 0:.1f}x the 20-day hour, taker flow "
                          f"{'with' if flow * d > 0 else 'against'} it",
            'range_lo': lo, 'range_hi': hi, 'anchor_ts': int(rng[0][0]), 'break_ts': int(b[0]),
            'break_extreme': b[3] if d > 0 else b[2], 'anchor_close': a[4], 'event_ts': int(a[0]) + HOUR_MS}


class BreakoutStrategy(Strategy):
    """
    The Turtles' breakout (strategies/turtle.py, eng-31): entered at once on the touch of the 20-day (System 1) / 55-day
    (System 2) channel, stop 2N, no target - the trade ends on the 10-day / 20-day opposite channel (SignalBook trails
    it, `trail_days`). No volume, flow, OI, spot or confirmation filter: the Turtles used none.
    """
    name = 'breakout'
    anchor_type = 'range'
    setups = {'BREAKOUT UP': 1, 'BREAKOUT DOWN': -1}
    ttl_key = 'breakout_ttl'
    time_exit = 'fixed'                # the method's own exit (eng-47)

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('anchor_ts'), x.sig.get('turtle_system')) if x.sig.get('turtle_n') else None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        from strategies.maniac_strategies import _confirm_plan
        sig, d = x.sig, x.direction
        if not sig.get('turtle_n'):
            return None
        stop = sig['anchor_level'] - d * 2 * sig['turtle_n']
        # review V05: 2N from the ENTRY the levels are computed at (stop_n, geometry.system_levels), not from the
        # channel / the minute's close - entry 106 with the stop fixed at 103 was 3N
        exit = {'stop': ['price', stop], 'stop_n': 2 * sig['turtle_n'], 'stop_src': '2N from the entry (Turtles)',
                'tp': ['trail'],
                'tp_src': f"none: exit on the {sig['trail_days']}-day {'low' if d > 0 else 'high'}", 'atr': x.atr}
        plan = _confirm_plan(x, self.name, '1d', exit, f"Turtle System {sig['turtle_system']} breakout")
        if plan is not None:
            plan['trail_days'] = sig['trail_days']
            plan['no_tp'] = True             # out on the channel: no take-profit orders
            plan['turtle_n'] = sig['turtle_n']
            plan['key'] = (sig['anchor_ts'], sig['turtle_system'], d)
        return plan
