"""
Leg strategies: a real leg (levels.find_impulse: its end on the last 12h of 15m candles, its start searched back over
15m and 1h history; its timeframe by duration 15m / 1h / 4h, the entry 3-6x finer).

continuation (IMPULSE UP / DOWN from Tier-0; BULL F / BEAR D removed in eng-127 - Bollinger's Method I is BB1) by
ICT's optimal trade entry:
- the leg must BREAK STRUCTURE (its end beyond the last 3-candle swing in the 48 candles before its start; no swing =
  no trade) with displacement (a fair value gap inside it), both on the leg's own timeframe;
- Elder's tide ~5x the leg's timeframe (15m -> 1h trend, 1h -> 4h, 4h -> daily) not against the trade (plan());
- the zone = the OTE band itself (CONFIG.levels.continuation_zone, 0.62-0.79 of the leg);
- trigger 'touch': with executor.touch_confirm_close the entry is the CLOSE of the trigger candle that touched the
  zone and closed back on the trade's side (no resting limit);
- the stop beyond the leg's start (the 100% level); the card is invalid at continuation_invalid;
- targets the leg's extensions measured from its START: start + k x leg (CONFIG.levels.continuation_targets), then
  the map. No partial / trail after TP1 (off since eng-111): the position exits in thirds at the targets.
"""
from typing import Dict, List, Optional

import numpy as np
import polars as pl

from config import CONFIG
from levels import TF_MS, _leg_levels, fib_price, find_impulse, retracement_of
from strategies.base import CardLevels, TRIGGER_MINUTES, PlanInput, Strategy, base_plan
from zones import liq_only, merge


def _leg_anchor(impulse: Dict) -> Dict:
    return {'type': 'leg', 'tf': impulse['tf'], 'start': impulse['start'], 'end': impulse['end'],
            'start_ts': impulse['start_ts'], 'end_ts': impulse['end_ts']}


def _continuation_targets(zones, ref, direction, atr, extensions):
    """Continuation-owned OTE target ordering: leg extensions, then map levels."""
    gap = CONFIG.zones.min_target_atr * atr
    targets, sources = [], []
    for price in extensions:
        if direction * (price - ref) >= gap and len(targets) < 3:
            targets.append(price); sources.append('leg extension')
    for zone in sorted((z for z in zones if not liq_only(z)),
                       key=lambda z: direction * ((z.lo if direction > 0 else z.hi) - ref)):
        if len(targets) >= 3: break
        price = zone.lo if direction > 0 else zone.hi
        if direction * (price - (targets[-1] if targets else ref)) >= gap:
            targets.append(price); sources.append(zone.label)
    while len(targets) < 3:
        last = targets[-1] if targets else ref
        targets.append(last + direction * gap); sources.append('continuation ATR discovery')
    return targets, sources


def _rows(df: pl.DataFrame) -> List[List[float]]:
    return [list(r) for r in df.select(['timestamp', 'open', 'high', 'low', 'close']).rows()]


def _closed_df(x: PlanInput) -> Optional[pl.DataFrame]:
    """Drop an in-progress 15m row while retaining all rows in replay/closed-frame callers."""
    if x.df is None or x.df.is_empty() or not x.minutes:
        return x.df
    # The final 1m row is closed; a 15m candle is closed only when its open + 15m is no later than it.
    cutoff = int(x.minutes[-1][0]) + 60_000
    return x.df.filter(pl.col('timestamp') + 15 * 60_000 <= cutoff)


def _ema_of_tf(x: PlanInput, tf: str, span: int) -> Optional[float]:
    """The EMA of the leg's own timeframe: 15m from the frame, 1h from the 1h candles, 4h = 4 x span on 1h."""
    if tf == '15m':
        frame = _closed_df(x)
        closes = frame['close'].to_list() if frame is not None and not frame.is_empty() else []
    else:
        closes = [c[4] for c in (x.h1 or [])]
        span = span * 4 if tf == '4h' else span
    if len(closes) < span:
        return None
    from strategies.ind_panel import ema
    value = float(ema(np.asarray(closes, dtype=float), span)[-1])
    return value if np.isfinite(value) else None


def _to_4h(h1: List[List[float]]) -> List[List[float]]:
    """1h candles [ts, o, h, l, c, vol] grouped into the 4h candles they make (UTC 4h boundaries)."""
    out: List[List[float]] = []
    hours: List[List[int]] = []
    for c in h1:
        ts = int(c[0]) // 14_400_000 * 14_400_000
        if out and out[-1][0] == ts:
            b = out[-1]
            b[2], b[3], b[4], b[5] = max(b[2], c[2]), min(b[3], c[3]), c[4], b[5] + c[5]
            hours[-1].append(int(c[0]))
        else:
            out.append([ts, c[1], c[2], c[3], c[4], c[5]])
            hours.append([int(c[0])])
    # only complete 4h candles: each of the four hours exactly once (a gap / a repeat is no 4h candle)
    return [b for b, hs in zip(out, hours) if hs == [b[0] + i * 3_600_000 for i in range(4)]]


def _adjacent(a, b, c, step_ms: Optional[int]) -> bool:
    """Three rows are three consecutive candles of the timeframe (audit 2026-10-18: a hole between rows is missing data,
    not a gap / swing the market made)."""
    return step_ms is None or (int(b[0]) - int(a[0]) == step_ms and int(c[0]) - int(b[0]) == step_ms)


def broke_structure(candles: List[List[float]], start_ts: int, end: float, direction: int,
                    step_ms: Optional[int] = None) -> bool:
    """ICT: the impulse must break structure - its end beyond the last 3-candle swing high (up; low down) formed in the
    48 candles before the leg's start (a swing high below the start does not count for an up leg)."""
    before = [c for c in candles if c[0] < start_ts][-48:]
    for k in range(len(before) - 2, 0, -1):
        a, b, c = before[k - 1], before[k], before[k + 1]
        if not _adjacent(a, b, c, step_ms):
            continue
        if direction > 0 and b[2] > a[2] and b[2] > c[2]:
            return end > b[2]
        if direction < 0 and b[3] < a[3] and b[3] < c[3]:
            return end < b[3]
    # eng-144 (external audit): no swing in reach is no proven break of structure - the ICT rule needs one
    return False


def displacement(candles: List[List[float]], start_ts: int, end_ts: int, direction: int,
                 step_ms: Optional[int] = None) -> bool:
    """
    ICT's displacement: the leg left a fair value gap in its direction - three candles inside the leg where the first's
    high is below the third's low (up; mirrored down): price moved too fast for the other side to trade there.
    """
    leg = [c for c in candles if start_ts <= c[0] <= end_ts]
    for a, b, c in zip(leg, leg[1:], leg[2:]):
        if not _adjacent(a, b, c, step_ms):
            continue
        if (direction > 0 and a[2] < c[3]) or (direction < 0 and a[3] > c[2]):
            return True
    return False


class LegContinuation(Strategy):
    anchor_type = 'leg'
    requires = ('spot',)
    frozen_in_zone = True
    follows_live_candle = True

    def entry_levels(self, plan: Dict, entry: float, extreme: Optional[float], direction: int) -> Optional[CardLevels]:
        """ICT OTE contract: impulse-start invalidation and measured extensions."""
        atr, ref = float(plan.get('leg_atr') or plan.get('atr') or 0), plan.get('stop_ref')
        targets = list(plan.get('targets') or ())[:3]
        if direction not in (-1, 1) or not atr or ref is None or not targets or not entry: return None
        sl = float(ref) - direction * 0.25 * atr; risk = direction * (entry - sl)
        if risk <= 0 or sl <= 0: return None
        targets += [targets[-1]] * (3-len(targets)); rr=[direction*(t-entry)/risk for t in targets]
        plan['contract_source']='continuation_ict_ote'; src=list(plan.get('target_src') or ())+['leg extension']*3
        return {'entry':float(entry),'sl':sl,'tp1':targets[0],'tp2':targets[1],'tp3':targets[2],'rr_tp1':rr[0],'rr_tp2':rr[1],'rr_blend':sum(rr)/3,'low_rr':False,'rr_reason':None,'risk_units':1.0,'risk0':risk,'stop_pierce':None,'sl_src':'beyond impulse start + 0.25 ATR','tp1_src':src[0],'tp2_src':src[1],'tp3_src':src[2],'zone_src':plan.get('zone_src'),'range_pos':None,'limit_entry':None,'volume_24h':plan.get('volume_24h')}

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        impulse = find_impulse(_closed_df(x), x.direction, x.h1)
        return (impulse['end_ts'], impulse['end']) if impulse else None

    def context_veto(self, sig: Dict, direction: int) -> Optional[str]:
        """
        BTC not moving hard against the trade over the last hour (tide_btc_against) - a shadow veto ('btc_against').
        The coin's own tide (Elder, ~5x the leg's timeframe) is checked in plan(), not here.
        """
        btc = sig.get('btc_1h')
        if btc is not None and direction * btc <= -CONFIG.strategies.tide_btc_against:
            return 'btc_against'     # eng-110: BTC is not Elder's tide (his is the coin's longer timeframe) - shadow
        return None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        cfg = CONFIG.levels
        d = x.direction
        closed_df = _closed_df(x)
        impulse = find_impulse(closed_df, d, x.h1)
        atr = x.atr
        if impulse is None or not atr:
            return None
        # Elder's tide on the timeframe ~5x the leg's (his factor of five): a 15m leg needs the 1h trend, a 1h leg the
        # 4h one, a 4h leg the daily one - not against the trade (was the 1h trend for every leg)
        tide = {'15m': 'coin_trend', '1h': 'trend_4h', '4h': 'trend_1d'}.get(impulse['tf'], 'coin_trend')
        if x.sig.get(tide) == -d:
            return {'skip': 'against_tide'}
        if CONFIG.strategies.require_displacement:
            candles = _rows(closed_df) if impulse['tf'] == '15m' else [list(c) for c in (x.h1 or [])]
            if impulse['tf'] == '4h':
                candles = _to_4h(candles)        # audit 2026-10-18: a 4h leg's FVG / BOS on its own candles, not 1h
            step = TF_MS[impulse['tf']]
            if not displacement(candles, impulse['start_ts'], impulse['end_ts'], d, step):
                return {'skip': 'no_displacement'}
            if not broke_structure(candles, impulse['start_ts'], impulse['end'], d, step):
                return {'skip': 'no_bos'}
        zones = merge(list(x.raw_levels or []) + _leg_levels(closed_df, impulse, None), atr, symbol=x.symbol)
        lo_ratio, hi_ratio = cfg.continuation_zone
        fib_lo, fib_hi = sorted((fib_price(impulse, lo_ratio), fib_price(impulse, hi_ratio)))
        # eng-121: the zone is ICT's OTE band itself (a map level inside it / Raschke's EMA20 + ADX were ours / another
        # method mixed in)
        level_lo, level_hi, zone_src, half = fib_lo, fib_hi, f"OTE {lo_ratio:g}-{hi_ratio:g}", 0.0
        stop_ref = stop_ref_src = None
        near, far = (level_hi + half, level_lo - half) if d > 0 else (level_lo - half, level_hi + half)
        lo_ratio = max(0.0, retracement_of(impulse, near))
        hi_ratio = min(1.0, retracement_of(impulse, far))
        # audit: ICT's OTE objectives - the prior high (the impulse's end) and the leg's 1.272 / 1.618 extensions, all
        # measured on the leg A->B from A (fixed by the impulse, the same at the entry)
        leg = impulse['end'] - impulse['start']
        extensions = [impulse['start'] + k * leg for k in cfg.continuation_targets]
        worst_entry = fib_price(impulse, lo_ratio)
        # targets spaced in the ATR of the leg's own timeframe (15m ATR steps put TP1 inside a 1h / 4h leg's noise)
        targets, sources = _continuation_targets(zones, worst_entry, d, impulse['atr'], extensions)
        zone = sorted((fib_price(impulse, lo_ratio), fib_price(impulse, hi_ratio)))
        # eng-117, the sources on ICT's OTE (LuxAlgo, ChartingLens: "stop beyond the swing that anchors the measurement"
        # = the 100% level, the impulse's start): the stop is beyond the leg's start, not the OTE zone's deep edge /
        # a structural zone inside it (ours, tighter)
        stop_ref, stop_ref_src = impulse['start'], "beyond the impulse's start (the 100% level, ICT OTE)"
        tf = impulse['tf']
        return base_plan(x, self.name, _leg_anchor(impulse), tf, trigger_minutes=TRIGGER_MINUTES.get(tf, 5),
                         leg_atr=impulse['atr'], entry='pullback', zone_lo=zone[0], zone_hi=zone[1], zone_src=zone_src,
                         # ICT: the idea is wrong beyond the impulse's start (the 100% level), not at 0.786 inside
                         # the OTE band
                         trigger='touch',
                         invalid=fib_price(impulse, CONFIG.levels.continuation_invalid), reset=impulse['end'],
                         missable=False, retarget=True,
                         stop_ref=stop_ref, stop_ref_src=stop_ref_src,
                         intent='extension', fillers=tuple(extensions), fill_label='ext', targets=targets,
                         target_src=sources, zones=zones, key=(impulse['end_ts'], impulse['end']), impulse=impulse)


class MomentumStrategy(LegContinuation):
    """The impulse detected by Tier-0 (5m move + OI + flow); the same pullback trade (eng-35: one strategy)."""
    name = 'continuation'

    def entry_levels(self, plan: Dict, entry: float, extreme: Optional[float], direction: int) -> Optional[CardLevels]:
        return super().entry_levels(plan, entry, extreme, direction)
    setups = {'IMPULSE UP': 1, 'IMPULSE DOWN': -1}
