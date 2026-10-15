"""
Pumps (the owner's strategy, eng-39), built from published pieces, not invented thresholds:

- PUMP START (long): momentum ignition - a range expansion out of quiet trading (Crabel's volatility breakout / the
  start of Wyckoff's markup) confirmed by participation: the last 15 minutes rose >= `pump_start_z` x the coin's own
  15m volatility and >= `pump_start_min_pct`, on >= `pump_start_rvol` x the usual volume, with open interest rising
  (new positions, not short covering) and spot taker buying (not a perp-only squeeze), price at a fresh 24h high.
  Entry at market; stop below the low of the ignition (the quiet range the move left) + the measured pierce; targets
  from the map (fillers in the move's own size).
- PUMP TOP (short): the end of a pump - Wyckoff's buying climax / VSA's upthrust after a move of >= `pump_top_min_pct`
  within 4h: a 15m candle at the high with a wick >= half its range on >= 2x the average volume (the climax), then the
  5m structure shift down; open interest falling or the CVD diverging confirms. Stop above the pump's high + the
  measured pierce; targets the pump's 0.382 / 0.5 / 0.618 retracements (the mean of the leg) and the map.
- Averaging 1:1 (the owner's rule): one more unit of the same size at half the way from the entry to the stop; the stop
  stays; R is the sum of both units in the first unit's risk (SignalBook `add_at`).
Archive note (research/pumps_by_size.md): fading pumps of 60%+ was the worst setup (-0.19R); this short waits for the
climax and the shift, it is not a fade of the rise itself. Both are journaled and judged like every strategy.
"""
from typing import Dict, Optional, Sequence

from config import CONFIG
from levels import MINUTE_MS, resample
from strategies.base import PlanInput, Strategy, base_plan
from strategies.geometry import htf_zones, select_targets
from zones import merge

QUARTER_MS = 900_000


def pump_start(minutes: Sequence[Sequence[float]], m: Dict, vol_15m: Optional[float], now_ms: int) -> Optional[Dict]:
    """minutes: final 1m candles (>= 24h preferred); m: the coin's Tier-0 metrics; vol_15m: std of 15m returns."""
    cfg = CONFIG.strategies
    if len(minutes) < 120 or not vol_15m:
        return None
    last = minutes[-1]
    # by time, not by index (eng-74: after a feed gap minutes[-16] is older than 15 minutes - a false '+x% in 15m')
    from strategies.oi_build import _close_at
    base = next((c for c in minutes if c[0] == int(last[0]) - 15 * MINUTE_MS), None)
    if base is None or _close_at(minutes, int(last[0]) - 15 * MINUTE_MS) is None:
        return None
    move = last[4] / base[4] - 1
    if move < max(cfg.pump_start_min_pct, cfg.pump_start_z * vol_15m):
        return None
    if (m.get('rvol_1m') or 0) < cfg.pump_start_rvol:
        return None
    if (m.get('oi_change_5m') or 0) <= 0 or (m.get('spot_cvd_5m') or 0) <= 0:
        return None
    day = [c for c in minutes if c[0] >= now_ms - 86_400_000 - MINUTE_MS and c[0] < minutes[-15][0]]
    if day and last[2] <= max(c[2] for c in day):
        return None                                   # not a fresh 24h high: a recovery inside the range
    quiet = minutes[-60:-15]
    low = min(c[3] for c in minutes[-16:])
    return {'setup': 'PUMP START', 'direction': 1,
            'setup_note': f"+{move:.1%} in 15m ({move / vol_15m:.1f}x the 15m volatility), RVOL {m.get('rvol_1m', 0):.1f}, "
                          f"OI rising, spot buying, a fresh 24h high",
            'anchor_level': max(c[2] for c in quiet) if quiet else base[4], 'anchor_extreme': low,
            'anchor_label': 'ignition', 'anchor_ts': int(base[0]), 'anchor_close': last[4],
            'pump_low': low, 'pump_move': move, 'event_ts': int(last[0]) + MINUTE_MS}


def pump_top(minutes: Sequence[Sequence[float]], m: Dict, now_ms: int) -> Optional[Dict]:
    """The climax 15m candle that just closed after a pump of >= pump_top_min_pct within 4h."""
    cfg = CONFIG.strategies
    bars = resample(minutes, 15, now_ms)
    if len(bars) < 20:
        return None
    last = bars[-1]
    window = bars[-16:]
    low = min(b[3] for b in window)
    hi = max(b[2] for b in window)
    if last[2] < hi or hi / low - 1 < cfg.pump_top_min_pct:
        return None                                   # the climax must be the high of the pump
    span = last[2] - last[3]
    upper = last[2] - max(last[1], last[4])
    avg_vol = sum(b[5] for b in bars[-21:-1]) / 20
    if span <= 0 or upper < 0.5 * span or not avg_vol or last[5] < 2 * avg_vol:
        return None
    oi_falling = (m.get('oi_change_5m') or 0) < 0
    return {'setup': 'PUMP TOP', 'direction': -1,
            'setup_note': f"buying climax after +{hi / low - 1:.0%} in 4h: 15m upper wick {upper / span:.0%} of the "
                          f"candle on {last[5] / avg_vol:.1f}x volume{', OI falling' if oi_falling else ''}; "
                          f"entry on the 5m shift down",
            'anchor_level': hi, 'anchor_extreme': hi, 'anchor_label': 'pump high', 'anchor_ts': int(window[0][0]),
            'anchor_close': last[4], 'pump_low': low, 'pump_high': hi, 'event_ts': int(last[0]) + QUARTER_MS}


MAJORS = ('BTC', 'ETH', 'SOL', 'XRP', 'BNB')


def dump_bounce(h1: Sequence[Sequence[float]], now_ms: int) -> Optional[Dict]:
    """
    eng-55, the rule of research_pumps.py (DIP-BUY mirrored for a dump; the only pump / dump rule positive in every
    period 2021-2026: +0.14R on 156 trades Apr-Sep 2026, 900 perpetuals). On CLOSED 1h candles [ts, o, h, l, c, vol]:
    - DUMP at hour t: close >= dump_min_move below the highest high of the last 6 hours, and the hours since that high
      traded >= dump_vol_x x the average hour of the week before; one dump per 48h.
    - its low: the lowest low until the first close above the previous hour's high (exhaustion), within 24h.
    - the bounce: price retraces to 38.2% of the dump (from the low toward the 6h high) within 24h, not beyond 61.8%,
      then a 1h close below the previous hour's low -> short at market now (the research entered at the next open).
    - stop above the bounce's high + 0.25 ATR(1h); TP1 the dump's low; TP2 the 1.618 extension of the dump.
    Fires only when the trigger is the candle that just closed.
    """
    cfg = CONFIG.strategies
    n = len(h1)
    if n < 190:
        return None
    h = [c[2] for c in h1]
    lo = [c[3] for c in h1]
    cl = [c[4] for c in h1]
    v = [c[5] for c in h1]
    last_event = -10 ** 9
    found = None
    for t in range(max(175, n - 75), n - 1):
        if t - last_event < 48:
            continue
        k0 = max(range(t - 5, t + 1), key=lambda k: h[k])
        base = h[k0]
        if not cl[t] or base / cl[t] - 1 < cfg.dump_min_move:
            continue
        week = v[t - 168 - 5:t - 5 + 1]
        vol7 = sum(week) / len(week) if week else 0.0
        if not vol7 or sum(v[k0:t + 1]) < cfg.dump_vol_x * (t + 1 - k0) * vol7:
            continue
        last_event = t
        if t < n - 26:
            continue                                  # too old to be still bouncing
        trs = [max(h[k], cl[k - 1]) - min(lo[k], cl[k - 1]) for k in range(t - 13, t + 1)]
        atr = sum(trs) / len(trs)
        peak = lo[t]
        for k in range(t + 1, min(n, t + 25)):
            peak = min(peak, lo[k])
            if cl[k] > h[k - 1]:
                break
        size = base - peak
        if size <= 0:
            continue
        lo_r, hi_r = peak + 0.382 * size, peak + 0.618 * size
        touched, pull = False, None
        for k in range(t + 1, min(n, t + 25)):
            if not touched:
                if h[k] >= lo_r:
                    touched, pull = True, h[k]
                continue
            pull = max(pull, h[k])
            if pull > hi_r:
                break
            if cl[k] < lo[k - 1]:
                if k == n - 1:
                    stop = pull + 0.25 * atr
                    found = {'setup': 'DUMP BOUNCE SHORT', 'direction': -1,
                             'setup_note': f"1h dump -{base / cl[t] - 1:.0%} from the 6h high {base:.6g} on "
                                           f"{sum(v[k0:t + 1]) / ((t + 1 - k0) * vol7):.1f}x volume; the bounce reached "
                                           f"{(pull - peak) / size:.0%} of it and closed below the previous low",
                             'anchor_level': cl[k], 'anchor_extreme': stop, 'anchor_label': 'dump bounce',
                             'anchor_ts': int(h1[t][0]), 'anchor_close': cl[k], 'dump_low': peak, 'dump_high': base,
                             'dump_stop': stop, 'dump_ext': base - 1.618 * size,
                             'event_ts': int(h1[k][0]) + 3_600_000}
                break
    return found


class DumpBounceStrategy(Strategy):
    """The short of the first bounce after a dump (eng-55): at market on the trigger close, stop above the bounce,
    TP1 the dump's low, TP2 its 1.618 extension (research_pumps.py)."""
    name = 'pump'
    anchor_type = 'level'
    setups = {'DUMP BOUNCE SHORT': -1}
    min_rr = 0.0                     # the research rule has no ratio filter: TP1 is the dump's low wherever it is
    ttl_key = 'pump_ttl'

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('anchor_ts'), 'dump') if x.sig.get('dump_low') is not None else None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        from strategies.maniac_strategies import _confirm_plan
        sig = x.sig
        if sig.get('dump_low') is None:
            return None
        exit = {'stop': ['price', sig['dump_stop']], 'stop_src': 'above the bounce + 0.25 ATR(1h)',
                'tp': ['level', sig['dump_low'], 0.0, None], 'tp_src': "the dump's low", 'atr': x.atr}
        plan = _confirm_plan(x, self.name, '1h', exit, 'first bounce after a dump, 1h close below the previous low')
        if plan and not plan.get('skip'):
            plan['key'] = (sig['anchor_ts'], 'dump')
        return plan


class PumpStartStrategy(Strategy):
    name = 'pump'
    anchor_type = 'level'
    setups = {'PUMP START': 1}
    # eng-71: the stop spans the ignition and TP1 is its measured move - R:R ~1 by construction, the global 2 vetoed
    # every PUMP START (ORCA / NIGHT 0.5-1.0); the owner's method has no ratio rule (as the other sources: 1)
    min_rr = 1.0
    ttl_key = 'pump_ttl'
    uses_minutes = True
    default_tf = '15m'

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('anchor_ts'), 'start') if x.sig.get('pump_low') is not None else None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig, atr = x.sig, x.atr
        if sig.get('pump_low') is None or not atr:
            return None
        close = sig['anchor_close']
        zones = merge(list(x.raw_levels or []), atr, symbol=x.symbol)
        move = close - sig['pump_low']
        fillers = (close + move, close + 1.618 * move)
        # eng-69: the stop spans the whole ignition, so the targets cannot be the nearest 15m swing / FVG (live eng-60:
        # TP1 at 0.56 of the risk, every entry low_rr) - the measured move and 1h+ zones only
        targets, sources = select_targets(htf_zones(zones, '1h'), close, 1, max(atr, x.tf_atr.get('1h') or 0.0),
                                          'extension', fillers, 'measured move')
        anchor = {'type': 'level', 'tf': '15m', 'level': sig['anchor_level'], 'label': 'pump ignition',
                  'extreme': sig['pump_low'], 'ts': sig['anchor_ts']}
        plan = base_plan(x, self.name, anchor, '15m', entry='confirm', confirm_only=True,
                         zone_lo=close - 0.25 * atr, zone_hi=close + 0.25 * atr, zone_src='momentum ignition',
                         missable=False, stop_ref=sig['pump_low'],
                         exit={'stop': ['ref', 0.0], 'tp': ['map', 0.0], 'atr': atr,
                               'stop_src': 'below the ignition'},
                         intent='extension', fillers=fillers, fill_label='measured move', targets=targets,
                         target_src=sources, zones=zones, key=(sig['anchor_ts'], 'start'))
        plan['target_tf'] = '1h'                     # eng-69: targets from 1h+ zones (see above)
        # eng-91: no averaging into a loser (was add_half: one more unit at half the way to the stop)
        return plan


class PumpTopStrategy(Strategy):
    name = 'pump'
    anchor_type = 'level'
    setups = {'PUMP TOP': -1}
    ttl_key = 'pump_ttl'
    uses_minutes = True
    default_tf = '15m'

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('anchor_ts'), 'top') if x.sig.get('pump_high') is not None else None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig, atr = x.sig, x.atr
        if sig.get('pump_high') is None or not atr:
            return None
        hi, lo = sig['pump_high'], sig['pump_low']
        leg = hi - lo
        retraces = tuple(hi - r * leg for r in (0.382, 0.5, 0.618))
        zones = merge(list(x.raw_levels or []), atr, symbol=x.symbol)
        targets, sources = select_targets(zones, sig['anchor_close'], -1, atr, 'mean', retraces, 'retrace')
        anchor = {'type': 'level', 'tf': '15m', 'level': hi, 'label': 'pump high', 'extreme': hi,
                  'ts': sig['anchor_ts']}
        # the shift down is looked for in the climax's upper part: from the high to its 0.236 retracement
        zone = (hi - 0.236 * leg, hi)
        plan = base_plan(x, self.name, anchor, '15m', entry='pullback', zone_lo=zone[0], zone_hi=zone[1],
                         zone_src='buying climax (5m shift down)', invalid=hi, fix_invalid=False, missable=True,
                         stop_ref=hi, intent='mean', fillers=retraces, fill_label='retrace', targets=targets,
                         target_src=sources, zones=zones, key=(sig['anchor_ts'], 'top'))
        # eng-91: no averaging into a loser (was add_half)
        return plan
