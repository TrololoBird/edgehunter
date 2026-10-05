"""
ICT's Power of Three / Judas swing (eng-58; innercircletrader.net, theinnercircletraders.com, ictkillzone.com - ICT
publishes it only in videos, so the rule is the common ground of several write-ups): a day unfolds as
accumulation (the Asian range), manipulation (a false move at the London open beyond one side of that range against
the day's bias - the Judas swing, which takes the stops there) and distribution (the true move the other way).

- the Asian range: the high / low of 20:00-00:00 New York time (ICT's Asian range);
- the window: the London kill zone, 02:00-05:00 New York time;
- the Judas swing: a 5m bar inside the window trades beyond the Asian range's side OPPOSITE the trade (below the low
  for a long);
- the market structure shift: a displacement bar (body >= half its range) closes beyond the last 3-bar swing the raid
  came from and leaves the first fair value gap after the raid;
- the trade: a resting limit at the gap's CE, the stop beyond the raid's extreme (+ the measured pierce), targets the
  Asian range's other side, then the day's draw (the previous day's high / low);
- the day's bias is REQUIRED (weekly, else daily): without it there is no Judas swing to read ('no_bias').
Detected loop-side on the final 1m candles built into 5m bars (Scanner._po3), once per coin, day and direction.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Sequence
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
FIVE_MS = 300_000


def london_window(ts_ms: int) -> Optional[tuple]:
    """(window start, window end, Asian range start, Asian range end) in epoch ms when `ts_ms` is in 02:00-05:00 NY."""
    local = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone(NY)
    if not 2 <= local.hour < 5:
        return None
    day = local.replace(hour=0, minute=0, second=0, microsecond=0)
    ms = lambda t: int(t.timestamp() * 1000)               # noqa: E731
    asia_start = (day - timedelta(days=1)).replace(hour=20)
    return ms(day.replace(hour=2)), ms(day.replace(hour=5)), ms(asia_start), ms(day)


def po3(bars5: Sequence[Sequence[float]], now_ms: int, pdh: Optional[float] = None,
        pdl: Optional[float] = None) -> Optional[Dict]:
    """bars5: final 5m bars [open_time, o, h, l, c, ...] from the Asian range's start on."""
    w = london_window(now_ms)
    if w is None:
        return None
    start, _, a0, a1 = w
    asia = [b for b in bars5 if a0 <= b[0] < a1]
    inside = [b for b in bars5 if b[0] >= start and b[0] + FIVE_MS <= now_ms]
    if len(asia) < 24 or len(inside) < 3:
        return None
    a_hi, a_lo = max(b[2] for b in asia), min(b[3] for b in asia)
    for d in (1, -1):
        raid = next((k for k, b in enumerate(inside) if (b[3] < a_lo if d > 0 else b[2] > a_hi)), None)
        if raid is None:
            continue
        lead = [b for b in bars5 if b[0] < inside[raid][0]][-48:]
        swing = None
        for k in range(len(lead) - 2, 0, -1):
            if d > 0 and lead[k][2] > lead[k - 1][2] and lead[k][2] > lead[k + 1][2]:
                swing = lead[k][2]
                break
            if d < 0 and lead[k][3] < lead[k - 1][3] and lead[k][3] < lead[k + 1][3]:
                swing = lead[k][3]
                break
        if swing is None:
            continue
        for i in range(max(raid + 2, 2), len(inside)):
            a, m, c = inside[i - 2], inside[i - 1], inside[i]
            body, span = abs(m[4] - m[1]), m[2] - m[3]
            if span <= 0 or body < 0.5 * span or (m[4] - m[1]) * d <= 0:
                continue
            if (max(m[4], c[4]) <= swing) if d > 0 else (min(m[4], c[4]) >= swing):
                continue
            if d > 0 and a[2] < c[3]:
                lo, hi = a[2], c[3]
            elif d < 0 and a[3] > c[2]:
                lo, hi = c[2], a[3]
            else:
                continue
            ce = (lo + hi) / 2
            extreme = min(b[3] for b in inside[:i + 1]) if d > 0 else max(b[2] for b in inside[:i + 1])
            other = a_hi if d > 0 else a_lo
            if d * (other - ce) <= 0:
                continue
            draw = pdh if d > 0 else pdl
            return {'setup': 'PO3 LONG' if d > 0 else 'PO3 SHORT', 'direction': d,
                    'setup_note': f"ICT Power of Three: London open took the Asian {'low' if d > 0 else 'high'} "
                                  f"{a_lo if d > 0 else a_hi:.6g} (Judas swing), shifted structure, 5m FVG "
                                  f"{lo:.6g}-{hi:.6g} (CE {ce:.6g}); target the Asian {'high' if d > 0 else 'low'} "
                                  f"{other:.6g}" + (f", then {draw:.6g}" if draw is not None else ''),
                    'anchor_level': ce, 'anchor_extreme': extreme, 'anchor_label': 'PO3 FVG (CE)',
                    'anchor_ts': start, 'anchor_close': c[4], 'fvg_lo': lo, 'fvg_hi': hi, 'po3_target': other,
                    'po3_draw': draw, 'event_ts': int(c[0]) + FIVE_MS}
    return None


from strategies.base import PlanInput, Strategy, base_plan          # noqa: E402
from strategies.geometry import select_targets                      # noqa: E402
from zones import merge                                              # noqa: E402


class Po3Strategy(Strategy):
    name = 'po3'
    anchor_type = 'level'
    setups = {'PO3 LONG': 1, 'PO3 SHORT': -1}
    min_rr = 1.0                     # ICT: the target is the Asian range's other side, no fixed ratio
    ttl_key = 'po3_ttl'
    time_exit = 'fixed'
    uses_minutes = True
    default_tf = '5m'

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('anchor_ts'), x.direction) if x.sig.get('fvg_lo') is not None else None

    def context_veto(self, sig: Dict, direction: int) -> Optional[str]:
        bias = sig.get('weekly_bias') or sig.get('daily_bias')
        if not bias:
            return 'no_bias'
        return 'against_bias' if bias == -direction else None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig, d, atr = x.sig, x.direction, x.atr
        if sig.get('fvg_lo') is None or not atr:
            return None
        ce, lo, hi = sig['anchor_level'], sig['fvg_lo'], sig['fvg_hi']
        zone = (lo, ce) if d > 0 else (ce, hi)
        zones = merge(list(x.raw_levels or []), atr, symbol=x.symbol)
        fillers = tuple(f for f in (sig.get('po3_draw'),) if f is not None and d * (f - sig['po3_target']) > 0)
        targets, sources = select_targets(zones, ce, d, atr, 'draw_liquidity', fillers, "the day's draw (PDH / PDL)",
                                          first=(sig['po3_target'], "the Asian range's other side"))
        anchor = {'type': 'level', 'tf': '5m', 'level': ce, 'label': 'PO3 FVG (CE)',
                  'extreme': sig['anchor_extreme'], 'ts': sig['anchor_ts']}
        return base_plan(x, self.name, anchor, '5m', entry='pullback', trigger='touch', single_touch=True,
                         zone_lo=zone[0], zone_hi=zone[1], zone_src='PO3 FVG, limit at its CE',
                         invalid=sig['anchor_extreme'], fix_invalid=True, missable=True,
                         stop_ref=sig['anchor_extreme'],
                         exit={'stop': ['ref', 0.0], 'tp': ['level', sig['po3_target'], 1.0, None], 'atr': atr,
                               'stop_src': "beyond the Judas swing's extreme",
                               'tp_src': "the Asian range's other side"},
                         intent='draw_liquidity', targets=targets, target_src=sources, zones=zones,
                         key=(sig['anchor_ts'], d))
