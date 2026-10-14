"""
Wyckoff springs and upthrusts after distribution (UTAD) as Wyckoff defines them (Pruden, "The Three Skills of Top
Trading"; Weis, "Trades About to Happen"): events of an established TRADING RANGE that followed a trend's stop, on 1h.

- The range is defined by Wyckoff's phase A EVENTS, not a bar count (eng-55; StockCharts' Wyckoff tutorial, Wyckoff
  Analytics): the selling climax (SC: a wide 1h candle on climactic volume at a new 2-day low after a decline) sets
  the range low, the automatic rally (AR: the high of the rebound after it) the range high, the secondary test (ST:
  back toward the SC on LESS volume, holding above its low) completes phase A. The decline it stopped: the close 48h
  before the SC above the AR's high. Distribution mirrored (BC -> AR -> ST, UTAD). The quantification of "climactic"
  (volume >= 2x and range >= 1.5x the 20 candles before) is ours: Wyckoff describes it, he gives no number.
- SPRING (phase C): the 1h candle that just closed traded below the SC low and closed back inside, its lower wick >=
  half the candle, the pierce <= 30% of the range height, after the ST and with the range unbroken (no close beyond
  either edge since the ST). UTAD mirrored at the AR / BC high.
- The trade (Wyckoff buys the test, not the spring): a pullback toward the spring's area on less volume AND a narrower
  spread (SignalBook: pullback_volume_ok / pullback_spread_ok); the entry on the 15m structure shift there; the stop
  beyond the spring's low; targets: the range's far side, the point-and-figure count of the range (Wyckoff's cause ->
  effect: columns x box x 3 from the spring's low; box = a tenth of the range height, 3-box reversal - our box
  choice), then the map.

Replaces the 15m "BULL B / BEAR C" phase scores (a 5-hour window called a range; C was a CVD divergence at a new
high with no range at all). BULL E, the selling climax, is not bought: Wyckoff reads it as the range's start.
"""
from typing import Dict, List, Optional, Sequence

from strategies.base import PlanInput, Strategy, base_plan
from strategies.geometry import select_targets
from zones import RawLevel, merge

HOUR_MS = 3_600_000
SEARCH = 168          # HOURS: the SC / BC within the last week
TREND_BACK = 48       # HOURS: the climax's new 2-day extreme / the decline it stopped
# eng-97: both are hours, converted to the candles given (eng-84 moved the detector to 4h candles and left them as bar
# counts: a '2-day' low meant 8 days, the 'week' 4 weeks)
MAX_PIERCE = 0.30
CLIMAX_VOL = 2.0      # our quantification of a climax (Wyckoff gives none): volume and spread vs the 20 candles before
CLIMAX_SPREAD = 1.5


def _phase_a(h1: Sequence[Sequence[float]], d: int, period_ms: int = HOUR_MS) -> Optional[Dict]:
    """The latest SC -> AR -> ST (d = +1; BC -> AR -> ST for d = -1) before the last candle, with the range intact."""
    per_hour = HOUR_MS / period_ms
    search, trend_back = max(10, round(SEARCH * per_hour)), max(6, round(TREND_BACK * per_hour))
    n = len(h1)
    hi = [x[2] for x in h1]
    lo = [x[3] for x in h1]
    cl = [x[4] for x in h1]
    vol = [x[5] for x in h1]
    last = n - 1
    for i in range(last - 4, max(trend_back + 20, last - search) - 1, -1):
        prev = range(i - 20, i)
        avg_v = sum(vol[k] for k in prev) / 20
        avg_r = sum(hi[k] - lo[k] for k in prev) / 20
        if not avg_v or not avg_r or vol[i] < CLIMAX_VOL * avg_v or hi[i] - lo[i] < CLIMAX_SPREAD * avg_r:
            continue
        extreme = lo[i] if d > 0 else hi[i]
        window = range(i - trend_back, i)
        if (d > 0 and extreme > min(lo[k] for k in window)) or (d < 0 and extreme < max(hi[k] for k in window)):
            continue                                  # the climax makes a new 2-day extreme
        # the automatic rally (reaction) and the secondary test after it
        for k in range(i + 3, last):
            seg = range(i + 1, k)
            p = max(seg, key=lambda j: hi[j]) if d > 0 else min(seg, key=lambda j: lo[j])
            ar = hi[p] if d > 0 else lo[p]
            height = abs(ar - extreme)
            if p < i + 1 or not height:
                continue
            near = (lo[k] <= extreme + 0.5 * height and lo[k] >= extreme) if d > 0 else \
                   (hi[k] >= extreme - 0.5 * height and hi[k] <= extreme)
            if k <= p or not near or vol[k] >= vol[i]:
                continue
            before = cl[i - trend_back]
            if (d > 0 and before <= ar) or (d < 0 and before >= ar):
                return None                           # no prior trend into the range
            # the range intact from the ST to the candle before the spring: no close beyond either edge
            lo_e, hi_e = (extreme, ar) if d > 0 else (ar, extreme)
            if any(cl[j] < lo_e or cl[j] > hi_e for j in range(k, last)):
                return None
            return {'climax': i, 'ar': p, 'st': k, 'lo': lo_e, 'hi': hi_e}
        return None
    return None


def pnf_count(closes: Sequence[float], box: float, reversal: int = 3) -> int:
    """Columns of a close-only point-and-figure chart (box size `box`, `reversal`-box reversal)."""
    if box <= 0 or len(closes) < 2:
        return 0
    cols, direction, ref = 1, 0, closes[0]
    for c in closes[1:]:
        if direction >= 0 and c >= ref + box:
            ref += box * int((c - ref) / box)
            direction = 1
        elif direction <= 0 and c <= ref - box:
            ref -= box * int((ref - c) / box)
            direction = -1
        elif direction > 0 and c <= ref - reversal * box:
            cols += 1
            ref -= box * int((ref - c) / box)
            direction = -1
        elif direction < 0 and c >= ref + reversal * box:
            cols += 1
            ref += box * int((c - ref) / box)
            direction = 1
    return cols


def weis_waves(closes: Sequence[float], volumes: Sequence[float], reversal: float) -> List[tuple]:
    """Weis waves on closes: a wave runs until price closes `reversal` back from its extreme; (direction, volume)."""
    if len(closes) < 2 or reversal <= 0:
        return []
    waves, d, ext, vol = [], 0, closes[0], volumes[0]
    for c, v in zip(closes[1:], volumes[1:]):
        if d >= 0 and c > ext:
            d, ext = 1, c
        elif d <= 0 and c < ext:
            d, ext = -1, c
        elif d > 0 and c <= ext - reversal or d < 0 and c >= ext + reversal:
            waves.append((d, vol))
            d, ext, vol = -d, c, 0.0
        vol += v
    waves.append((d, vol))
    return waves


def weis_ratio(h1: Sequence[Sequence[float]], start: int, d: int, reversal: float) -> Optional[float]:
    """Weis's effort into the spring (d = +1; the upthrust for -1): the volume of the last wave against the trade
    divided by the mean of the earlier waves against it since the climax. Below 1 = less effort into the test edge
    (supply drying up, Weis "Trades About to Happen"). Journaled (`weis_ratio`), not a filter."""
    waves = weis_waves([x[4] for x in h1[start:]], [x[5] for x in h1[start:]], reversal)
    against = [v for w, v in waves if w == -d]
    if len(against) < 2:
        return None
    prior = sum(against[:-1]) / len(against[:-1])
    return against[-1] / prior if prior else None


def wyckoff_events(h1: Sequence[Sequence[float]], period_ms: int = HOUR_MS, tf: str = '1h') -> List[Dict]:
    """A spring / UTAD on the candle that just closed (h1[-1]) inside a phase-A range, else []. eng-84: run on 4h
    candles (the range of a trading range is read on 4h / daily, the 1h only times the entry - the owner's review of
    the live trades and the Wyckoff write-ups); `period_ms` / `tf` describe the candles given."""
    if len(h1) < max(6, round(TREND_BACK * HOUR_MS / period_ms)) + 30:
        return []
    last = h1[-1]
    o, h, l, c = last[1], last[2], last[3], last[4]
    span = h - l
    if span <= 0:
        return []
    for d in (1, -1):
        rng = _phase_a(h1, d, period_ms)
        if rng is None:
            continue
        lo, hi = rng['lo'], rng['hi']
        height = hi - lo
        # eng-119: the spring as the sources define it - below the SC low, closed back inside (the half-wick and the 30%
        # pierce limits were ours)
        if d > 0 and l < lo and c > lo:
            return [_event('SPRING', 1, lo, hi, l, h1, rng, last, period_ms, tf)]
        if d < 0 and h > hi and c < hi:
            return [_event('UTAD', -1, lo, hi, h, h1, rng, last, period_ms, tf)]
    return []


def _event(setup: str, d: int, lo: float, hi: float, extreme: float, h1, rng: Dict, last, period_ms: int = HOUR_MS,
           tf: str = '1h') -> Dict:
    edge = lo if d > 0 else hi
    height = hi - lo
    box = height / 10
    cols = pnf_count([x[4] for x in h1[rng['climax']:]], box)
    count = extreme + d * cols * box * 3
    hours = (len(h1) - 1 - rng['climax']) * period_ms // HOUR_MS
    return {'setup': setup, 'direction': d,
            'setup_note': f"{tf} {'spring below' if d > 0 else 'upthrust above'} a {hours}h trading range {lo:.6g}-{hi:.6g} "
                          f"({'SC' if d > 0 else 'BC'} -> AR -> ST) after a {'decline' if d > 0 else 'rally'}: closed "
                          f"back inside; P&F count {cols} columns -> {count:.6g}; the entry waits for the test",
            'range_lo': lo, 'range_hi': hi, 'anchor_level': edge, 'anchor_extreme': extreme,
            'anchor_label': f"{'SC low' if d > 0 else 'BC high'} (phase A range)",
            'anchor_ts': int(h1[rng['climax']][0]), 'anchor_close': last[4], 'event_ts': int(last[0]) + period_ms, 'wy_tf': tf,
            'pnf_target': count, 'pnf_cols': float(cols),
            # Weis wave volume into the spring vs the range's earlier waves (reversal = 3 boxes, the P&F convention)
            'weis_ratio': weis_ratio(h1, rng['climax'], d, 3 * box),
            # the spring candle's average FUTURES minute and range: Wyckoff's test trades on less volume and a narrower
            # spread (levels.pullback_volume_ok / pullback_spread_ok)
            'fut_candle_minute_usd': float(last[5]) / (period_ms / 60_000) if len(last) > 5 else None,
            'spring_range': float(last[2] - last[3])}


class WyckoffRangeStrategy(Strategy):
    name = 'wyckoff'               # eng-35: one Wyckoff strategy (phase C here, the climax's test in cascade.py)
    anchor_type = 'range'
    setups = {'SPRING': 1, 'UTAD': -1}

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('anchor_ts'), x.sig.get('anchor_level')) if x.sig.get('range_lo') is not None else None

    def context_veto(self, sig: Dict, direction: int) -> Optional[str]:
        """Wyckoff reads a 1h range inside the larger picture: no spring against a falling daily trend's weekly
        markdown, no UTAD against a rising one (both the daily trend and the weekly bias against the trade)."""
        if sig.get('trend_1d') == -direction and sig.get('weekly_bias') == -direction:
            return 'against_htf'      # eng-110: our trend / bias definitions - shadow (config.shadow_vetoes)
        return None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig, d, atr = x.sig, x.direction, x.atr
        if sig.get('range_lo') is None or not atr:
            return None
        lo, hi, extreme = sig['range_lo'], sig['range_hi'], sig['anchor_extreme']
        edge, far = (lo, hi) if d > 0 else (hi, lo)
        zones = merge(list(x.raw_levels or []) + [RawLevel(hi, 'range', 'range high', +1),
                                                   RawLevel(lo, 'range', 'range low', -1)], atr, symbol=x.symbol)
        fillers = (far,) + ((sig['pnf_target'],) if sig.get('pnf_target') and d * (sig['pnf_target'] - far) > 0 else ())
        # eng-84 (Wyckoff practice): TP1 the middle of the range, then its far side / the P&F count
        # eng-110: Wyckoff's objectives - the range's far side and the P&F count (the eng-84 'range middle' TP1 was ours)
        targets, sources = select_targets(zones, edge, d, atr, 'range', fillers, 'range far side / P&F count')
        # the test: back toward the spring's area (the spring's extreme to a fifth into the range)
        # eng-110: the test comes back to the spring's area - its extreme to the range edge (the 'fifth into the range'
        # was ours)
        zone = sorted((extreme, edge))
        tf = sig.get('wy_tf') or '1h'
        anchor = {'type': 'range', 'tf': tf, 'lo': lo, 'hi': hi, 'ts': sig['anchor_ts']}
        return base_plan(x, self.name, anchor, tf, entry='pullback', zone_lo=zone[0], zone_hi=zone[1],
                         zone_src=f"Wyckoff test of the {'spring' if d > 0 else 'upthrust'}", invalid=extreme,
                         fix_invalid=True, missable=True, stop_ref=extreme, intent='range', fillers=(far,),
                         fill_label='range far side', targets=targets, target_src=sources, zones=zones,
                         key=(sig['anchor_ts'], edge))
