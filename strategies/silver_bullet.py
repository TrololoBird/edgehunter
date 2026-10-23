"""
ICT's Silver Bullet: a one-hour window of the New York day (03:00-04:00, 10:00-11:00, 14:00-15:00 NY time) in which
price raids nearby liquidity, shifts structure and displaces the other way, leaving a fair value gap; the trade is
the retrace into that gap, entered at its consequent encroachment (CE, the gap's 50%), the stop beyond the raid's
extreme, the target the DRAW ON LIQUIDITY of the day (eng-58: the previous day's high / low in the trade's
direction; none ahead of the entry -> no trade). Detected loop-side on the final 1m candles built into 5m bars
(strategies.loopside.LoopDetectors._silver_bullet).

- liquidity (eng-106): the hour BEFORE the window plus the Asia (20:00-00:00 NY) and London (02:00-05:00 NY) session
  highs / lows - the nearest one beyond the window's open is the pool;
- the raid: a 5m bar inside the window trades beyond it;
- the market structure shift (eng-58, ICT): the displacement closes beyond the last 3-candle swing the raid came from;
- the displacement: a 5m bar with a body >= half its range in the other direction that leaves the FIRST FVG after
  the raid (bullish: the first bar's high < the third bar's low) inside the window;
- one setup per coin, window and direction.
"""
from datetime import datetime, timedelta, timezone
from config import CONFIG
from typing import Dict, Optional, Sequence
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
WINDOWS = ((3, 4), (10, 11), (14, 15))
FIVE_MS = 300_000


def window_of(ts_ms: int) -> Optional[int]:
    """The window's start (epoch ms) when `ts_ms` falls inside one, else None."""
    local = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone(NY)
    for start, end in WINDOWS:
        if start <= local.hour < end:
            return int(local.replace(hour=start, minute=0, second=0, microsecond=0).timestamp() * 1000)
    return None


def silver_bullet(bars5: Sequence[Sequence[float]], now_ms: int, pdh: Optional[float] = None,
                  pdl: Optional[float] = None, skip: Sequence[int] = ()) -> Optional[Dict]:
    """bars5: final 5m bars [open_time, o, h, l, c, ...] covering at least the hour before the window.
    skip: directions already fired this window - searched past (audit A02: the first LONG kept coming back and hid a
    later SHORT of the same window)."""
    start = window_of(now_ms)
    if start is None:
        return None
    before = [b for b in bars5 if start - 3_600_000 <= b[0] < start]
    inside = [b for b in bars5 if b[0] >= start and b[0] + FIVE_MS <= now_ms]
    if len(before) < 10 or len(inside) < 3:
        return None
    hour_hi, hour_lo = max(b[2] for b in before), min(b[3] for b in before)
    # eng-106, the sources (LuxAlgo, ChartingLens, TradingView on ICT): the liquidity a Silver Bullet raids is the
    # session highs / lows (Asia 20:00-00:00 NY, London 02:00-05:00 NY) besides the hour before the window - the nearest
    # one beyond the window's open is the pool; was the hour before the window only
    local = datetime.fromtimestamp(start / 1000, tz=timezone.utc).astimezone(NY)
    # eng-138 (audit A08): each boundary is a New York wall-clock time of its own (fixed hours added to midnight were an
    # hour off on the DST change days); 20:00 of the previous day .. 00:00 Asia, 02:00 .. 05:00 London
    day = local.date()

    def ny_ms(d, hour):
        return datetime(d.year, d.month, d.day, hour, tzinfo=NY).timestamp() * 1000
    prev = day - timedelta(days=1)
    sessions = [(ny_ms(prev, 20), ny_ms(day, 0)), (ny_ms(day, 2), ny_ms(day, 5))]
    pools_hi, pools_lo = [(hour_hi, 'the hour before')], [(hour_lo, 'the hour before')]
    for (a, b), tag in zip(sessions, ('Asia', 'London')):
        if b > start:
            continue                                # a session still running at the window's start is no pool yet
        part = [x for x in bars5 if a <= x[0] < b and x[0] + FIVE_MS <= start]
        if len(part) >= 6:
            pools_hi.append((max(x[2] for x in part), tag))
            pools_lo.append((min(x[3] for x in part), tag))
    open_px = inside[0][1]
    above = sorted(p for p in pools_hi if p[0] > open_px)
    below = sorted((p for p in pools_lo if p[0] < open_px), reverse=True)
    for d in (1, -1):
        if d in skip:
            continue
        pool = (below[0] if below else None) if d > 0 else (above[0] if above else None)
        if pool is None:
            continue
        ref_hi = pool[0] if d < 0 else hour_hi
        ref_lo = pool[0] if d > 0 else hour_lo
        raid = next((k for k, b in enumerate(inside) if (b[3] < ref_lo if d > 0 else b[2] > ref_hi)), None)
        if raid is None:
            continue
        # the swing the raid came from: the last 3-bar swing high (long; low short) before the raid
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
            if c[0] - a[0] != 2 * FIVE_MS:
                continue                           # a bar dropped between them (resample's gap policy): no FVG
            span = m[2] - m[3]
            if span <= 0 or (m[4] - m[1]) * d <= 0:     # eng-119: no body share (ours)
                continue
            if (max(m[4], c[4]) <= swing) if d > 0 else (min(m[4], c[4]) >= swing):
                continue                           # no market structure shift yet
            if d > 0 and a[2] < c[3]:
                lo, hi = a[2], c[3]
            elif d < 0 and a[3] > c[2]:
                lo, hi = c[2], a[3]
            else:
                continue
            extreme = min(b[3] for b in inside[:i + 1]) if d > 0 else max(b[2] for b in inside[:i + 1])
            draw = pdh if d > 0 else pdl
            target = draw if draw is not None and d * (draw - (lo + hi) / 2) > 0 else (ref_hi if d > 0 else ref_lo)
            if d * (target - (lo + hi) / 2) <= 0:
                continue
            ce = (lo + hi) / 2
            return {'setup': 'SILVER BULLET LONG' if d > 0 else 'SILVER BULLET SHORT', 'direction': d,
                    'setup_note': f"ICT Silver Bullet {local:%H}:00-{local.hour + 1:02d}:00 NY: took {pool[1]}'s "
                                  f"{'low' if d > 0 else 'high'} {ref_lo if d > 0 else ref_hi:.6g}, displaced, 5m FVG "
                                  f"{lo:.6g}-{hi:.6g} (CE {ce:.6g}) after a structure shift; target {target:.6g}",
                    'anchor_level': ce, 'anchor_extreme': extreme, 'anchor_label': 'Silver Bullet FVG',
                    'anchor_ts': start, 'anchor_close': c[4], 'fvg_lo': lo, 'fvg_hi': hi, 'sb_target': target,
                    'event_ts': int(c[0]) + FIVE_MS}
    return None


from strategies.base import PlanInput, Strategy, base_plan          # noqa: E402
from strategies.geometry import select_targets                      # noqa: E402
from zones import merge                                             # noqa: E402


class SilverBulletStrategy(Strategy):
    """The Silver Bullet playbook of the ICT liquidity strategy: the FVG's CE (first touch, 5m; with
    executor.touch_confirm_close the entry is the close of the touching candle), stop beyond the raid's extreme +
    the measured pierce, TP1 the day's draw on liquidity (PDH / PDL) ahead of the entry, else no trade."""
    name = 'sweep'
    anchor_type = 'level'
    setups = {'SILVER BULLET LONG': 1, 'SILVER BULLET SHORT': -1}
    min_rr = 2.0                     # eng-84: >= 1:2 to the opposite liquidity (Silver Bullet practice)
    ttl_key = 'silver_bullet_ttl'
    time_exit = 'fixed'                # the method's own exit (eng-47)
    uses_minutes = True
    default_tf = '5m'

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('anchor_ts'), x.direction) if x.sig.get('fvg_lo') is not None else None

    def context_veto(self, sig: Dict, direction: int) -> Optional[str]:
        # eng-49, ICT: the Silver Bullet is the liquidity strategy's playbook, traded with the higher-timeframe bias
        # (weekly, else daily, else the coin's 1h trend) as the sweep - it took 12 longs into a falling market
        bias = sig.get('weekly_bias') or sig.get('daily_bias')
        if bias:
            return 'against_bias' if bias == -direction else None
        # eng-150 (plan 4.1): ICT's top-down order has no 1h substitute - no weekly / daily bias, no trade; eng-151
        # (external audit #1): shadow (strategies.shadow_vetoes) - blocking it lost the outcome and against_bias trades
        if CONFIG.strategies.sweep_bias_required and sig.get('coin_trend') == -direction:
            from signal_book import shadow_veto
            # review eng-151: with the bias veto in shadow the 1h trend is still journaled
            shadow_veto(sig, 'against_trend')
        return 'sweep_no_htf_bias' if CONFIG.strategies.sweep_bias_required else \
            ('against_trend' if sig.get('coin_trend') == -direction else None)

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig, d, atr = x.sig, x.direction, x.atr
        if sig.get('fvg_lo') is None or not atr:
            return None
        ce, lo, hi = sig['anchor_level'], sig['fvg_lo'], sig['fvg_hi']
        # ICT: longs from the discount half of the dealing range, shorts from the premium (APT bought at 0.91)
        from strategies.ict import dealing_range, range_position
        pos = range_position(dealing_range(x.h1 or []), ce, d)
        if pos is not None and pos > 0.5:
            from signal_book import shadow_veto
            shadow_veto(sig, 'premium' if d > 0 else 'discount')     # eng-107: not in the sources' rule - shadow
        zone = (lo, ce) if d > 0 else (ce, hi)
        zones = merge(list(x.raw_levels or []), atr, symbol=x.symbol)
        risk = abs(ce - sig['anchor_extreme'])
        # the day's draw as TP1 only on the trade's side (eng-84; its 3R cap removed in eng-110)
        first = (sig['sb_target'], "the day's draw on liquidity (PDH / PDL)") \
            if risk and 0 < d * (sig['sb_target'] - ce) else None      # eng-110: no 3R cap (ours)
        if first is None:
            # the Silver Bullet's target is the day's draw on liquidity; already behind the entry -> no trade (was the
            # map's nearest opposite liquidity, a target no source names)
            return {'skip': "no draw on liquidity ahead"}
        targets, sources = select_targets(zones, ce, d, atr, 'opposite_liquidity', first=first)
        anchor = {'type': 'level', 'tf': '5m', 'level': ce, 'label': 'Silver Bullet FVG (CE)',
                  'extreme': sig['anchor_extreme'], 'ts': sig['anchor_ts']}
        plan = base_plan(x, self.name, anchor, '5m', entry='pullback', trigger='touch', single_touch=True,
                         zone_lo=zone[0], zone_hi=zone[1], zone_src='Silver Bullet FVG, limit at its CE',
                         invalid=sig['anchor_extreme'], fix_invalid=True, missable=True,
                         stop_ref=sig['anchor_extreme'],
                         # system_levels takes TP1 from exit['tp'] (eng-96)
                         exit={'stop': ['ref', 0.0], 'atr': atr, 'stop_src': "beyond the raid's extreme",
                               'tp': ['level', sig['sb_target'], 1.0, None],
                               'tp_src': "the day's draw on liquidity (PDH / PDL)"},
                         intent='opposite_liquidity', targets=targets, target_src=sources, zones=zones,
                         key=(sig['anchor_ts'], d))
        if plan and not plan.get('skip'):
            # audit: ICT (the Silver Bullet lecture, 11:24): a NEW entry only inside the hour; a trade may run past it
            plan['entry_until_ms'] = int(sig['anchor_ts']) + 3_600_000
        return plan
