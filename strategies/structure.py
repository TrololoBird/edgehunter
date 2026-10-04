"""
A coin's market structure for the strategies, rebuilt after every closed 15m candle in the maps worker PROCESS
(pure Python: in threads it held the GIL and stalled the event loop):

- the level map (zones.build_raw on the 15m candles and the coin's 1h history) merged into zones;
- resting-stop pools of the higher timeframes with the time each formed: intact 1h swings, equal highs / lows,
  previous day / week, the day's extremes, the last completed sessions - minus those price traded through since;
- the coin's own 1h trend (close vs EMA and its slope) and its volatility state (last hour's ATR vs ATR14);
- the events of the candle that just closed (a sweep of a pool, a breakout accepted), detected here so the loop
  never scans 300 coins' candles.
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from config import CONFIG
from zones import HOUR_MS, RawLevel, Zone, build_raw, day_levels, equal_pools, equal_tolerance, merge, round_levels

QUARTER_MS = 900_000
Pool = Tuple[float, int, str, int]          # (price, side +1 high / -1 low, label, formed at ms)


@dataclass
class Context:
    atr: float                               # ATR14 of the 15m candles
    recent_atr: float                        # ATR of the last recent_atr_candles 15m candles
    cut_ms: int                              # close time of the last closed 15m candle
    zones: List[Zone]                        # merged level map
    pools: List[Pool]                        # higher-timeframe resting-stop pools (as of the last candle's close)
    trend: int                               # the coin's 1h trend: +1 up, -1 down, 0 none
    tail: List[List[float]] = field(default_factory=list)   # the last 24 closed 15m candles
    events: List[Dict] = field(default_factory=list)       # setups of the candle that just closed
    smt_pair: Optional[str] = None                          # the SMT correlate (corr >= smt_min_correlation), None = none

    @property
    def vol_ratio(self) -> float:
        return self.recent_atr / self.atr if self.atr else 1.0


def true_ranges(candles: Sequence[Sequence[float]]) -> List[float]:
    return [max(c[2], p[4]) - min(c[3], p[4]) for p, c in zip(candles, candles[1:])]


def recent_atr(candles_15m: Sequence[Sequence[float]]) -> float:
    trs = true_ranges(candles_15m)[-CONFIG.strategies.recent_atr_candles:]
    return sum(trs) / len(trs) if trs else 0.0


def coin_trend(candles_1h: Sequence[Sequence[float]]) -> int:
    """+1 when the last close is above a rising EMA, -1 below a falling one, else 0."""
    cfg = CONFIG.strategies
    closes = [c[4] for c in candles_1h]
    if len(closes) < cfg.trend_ema + cfg.trend_slope_bars:
        return 0
    k = 2 / (cfg.trend_ema + 1)
    ema = [closes[0]]
    for c in closes[1:]:
        ema.append(ema[-1] + k * (c - ema[-1]))
    slope = ema[-1] - ema[-1 - cfg.trend_slope_bars]
    if closes[-1] > ema[-1] and slope > 0:
        return 1
    if closes[-1] < ema[-1] and slope < 0:
        return -1
    return 0


def weekly_ref(closes_1w: Sequence[float]) -> Optional[Tuple[float, float]]:
    """
    (EMA(trend_w_ema) of CLOSED weekly closes, std of their weekly log returns over the same number of weeks), or None
    with fewer weeks than the EMA's period (a young listing has no weekly trend yet).
    """
    import math
    n = CONFIG.strategies.trend_w_ema
    closes = [c for c in closes_1w if c > 0]
    if len(closes) < n + 1:
        return None
    k = 2 / (n + 1)
    ema = closes[0]
    for c in closes[1:]:
        ema += k * (c - ema)
    rets = [math.log(b / a) for a, b in zip(closes[-n - 1:-1], closes[-n:])]
    mean = sum(rets) / len(rets)
    std = (sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) ** 0.5
    return (ema, std) if std > 0 else None


def trend_w_of(ref: Optional[Tuple[float, float]], price: Optional[float]) -> Optional[float]:
    """The price's distance from the weekly EMA in weekly standard deviations (+ above, - below)."""
    import math
    if not ref or not price or price <= 0:
        return None
    return math.log(price / ref[0]) / ref[1]


def _swings_with_ts(candles: Sequence[Sequence[float]], width: int, bar_ms: int) -> List[Pool]:
    """Intact fractal swings (no later CLOSE beyond) with the time the fractal completed."""
    n = len(candles)
    out: List[Pool] = []
    if n < 2 * width + 1:
        return out
    max_after = [float('-inf')] * (n + 1)
    min_after = [float('inf')] * (n + 1)
    for i in range(n - 1, -1, -1):
        max_after[i] = max(max_after[i + 1], candles[i][4])
        min_after[i] = min(min_after[i + 1], candles[i][4])
    for i in range(width, n - width):
        h, lo = candles[i][2], candles[i][3]
        around = list(candles[i - width:i]) + list(candles[i + 1:i + 1 + width])
        formed = int(candles[i + width][0]) + bar_ms
        if all(c[2] < h for c in around) and max_after[i + 1] <= h:
            out.append((h, +1, '1h high', formed))
        if all(c[3] > lo for c in around) and min_after[i + 1] >= lo:
            out.append((lo, -1, '1h low', formed))
    return out


def liquidity_pools(h1_before: Sequence[Sequence[float]], c15_hour: Sequence[Sequence[float]], atr: float,
                    now_ms: int, symbol: Optional[str] = None) -> List[Pool]:
    """
    Resting-stop pools as of `now_ms` from closed 1h candles plus the 15m candles of the running hour: intact 1h swings
    of the last sweep_swing_hours, equal highs / lows among them, previous day / week, the day's extremes and the last
    completed sessions; a pool price traded through after it formed is taken and dropped.
    """
    cfg = CONFIG.strategies
    recent_1h = [c for c in h1_before if c[0] >= now_ms - cfg.sweep_swing_hours * HOUR_MS]
    pools = _swings_with_ts(recent_1h, CONFIG.zones.swing_width_1h, HOUR_MS)
    swing_levels = [RawLevel(p, 'swing_1h', lab, side) for p, side, lab, _ in pools]
    formed_of = {(p, side): f for p, side, _, f in pools}
    for level in equal_pools(swing_levels, recent_1h, atr, symbol):
        group = [f for (p, side), f in formed_of.items() if side == level.side and abs(p - level.price) <= equal_tolerance(symbol, level.price, atr)]
        pools.append((level.price, level.side, level.label, max(group) if group else now_ms))
    # The running hour as one partial 1h candle, so the day's extremes include it
    hourly = list(h1_before)
    if c15_hour:
        hourly.append([c15_hour[0][0], c15_hour[0][1], max(c[2] for c in c15_hour), min(c[3] for c in c15_hour),
                       c15_hour[-1][4], 0.0, 0.0])
    for level, formed in day_levels(hourly, now_ms, with_ts=True):
        pools.append((level.price, level.side, level.label, formed))
    # Round numbers: their stops re-gather after price last traded through them (that candle's end = "formed")
    if hourly:
        last = hourly[-1][4]
        for price in round_levels(last, CONFIG.zones.round_span_atr * atr):
            crossed = [c for c in hourly if c[3] <= price <= c[2]]
            formed = int(crossed[-1][0]) + HOUR_MS if crossed else int(hourly[0][0])
            pools.append((price, +1 if price > last else -1, f"round {price:g}", formed))
    # Taken since it formed: any later candle traded beyond it (a wick through is a sweep: the stops are gone)
    history = list(h1_before) + list(c15_hour)
    out = []
    for price, side, label, formed in pools:
        later = [c for c in history if c[0] >= formed]
        if side > 0 and any(c[2] > price for c in later):
            continue
        if side < 0 and any(c[3] < price for c in later):
            continue
        out.append((price, side, label, formed))
    return out


def pools_before(candles_15m: Sequence[Sequence[float]], candles_1h: Sequence[Sequence[float]], atr: float,
                 at_ms: int, symbol: Optional[str] = None) -> List[Pool]:
    """The pools as they stood when the candle opening at `at_ms` started."""
    hour = at_ms // HOUR_MS * HOUR_MS
    h1_before = [c for c in candles_1h if c[0] + HOUR_MS <= hour]
    c15_hour = [c for c in candles_15m if hour <= c[0] < at_ms]
    return liquidity_pools(h1_before, c15_hour, atr, at_ms, symbol)


def merge_candles(older: Sequence[Sequence[float]], newer: Sequence[Sequence[float]], cut_ms: int,
                  bar_ms: int) -> List[List[float]]:
    """A long history (REST, refreshed hourly) with the newer closed candles on top, only bars closed by `cut_ms`."""
    merged = {int(c[0]): list(c) for c in older}
    merged.update({int(c[0]): list(c) for c in newer})
    return [merged[t] for t in sorted(merged) if t + bar_ms <= cut_ms]


def hours_from(candles_15m: Sequence[Sequence[float]], h1: Sequence[Sequence[float]], cut_ms: int) -> List[List[float]]:
    """Closed 1h candles up to `cut_ms`; an hour REST has not published yet is built from its four 15m candles."""
    out = [list(c) for c in h1 if c[0] + HOUR_MS <= cut_ms]
    last = out[-1][0] if out else None
    by_hour: Dict[int, List] = {}
    for c in candles_15m:
        hour = int(c[0]) // HOUR_MS * HOUR_MS
        if (last is None or hour > last) and hour + HOUR_MS <= cut_ms:
            by_hour.setdefault(hour, []).append(c)
    for hour in sorted(by_hour):
        q = sorted(by_hour[hour], key=lambda c: c[0])
        if len(q) == 4:
            out.append([hour, q[0][1], max(c[2] for c in q), min(c[3] for c in q), q[-1][4],
                        sum(c[5] for c in q), sum(c[6] for c in q)])
    return out


def maniac_events(symbol: Optional[str], m15: List[List[float]], h1: List[List[float]],
                  corr: Optional[List[List[float]]], cut: int, h4: Sequence = (), d1: Sequence = ()) -> List[Dict]:
    """crypto_maniac's systems on the candle that just closed (15m), and on the hour when one closed (1h)."""
    from strategies import maniac
    from strategies.auction_engine import auction_signals
    log = logging.getLogger(__name__)
    events: List[Dict] = []

    def run(name, fn, *args):
        try:
            found = fn(*args)
        except Exception as e:                   # one system's slip must not cost the others (logged, not hidden)
            log.warning(f"{name} of {symbol} failed: {type(e).__name__} {e}", exc_info=True)
            return
        # numpy scalars -> Python numbers: the dashboard's orjson (default=str) turned them into strings
        clean = lambda e: {k: (v.item() if hasattr(v, 'item') and not isinstance(v, (list, dict)) else v)
                           for k, v in e.items()}
        if isinstance(found, dict):
            events.append(clean(found))
        elif found:
            events.extend(clean(e) for e in found)

    # Seiden draws supply / demand on 4h or higher and enters on the lower one: zones of 4h candles at the 4h close,
    # the limit touch on 1h (eng-37; eng-34 1h zones, the sample's 15m before). His curve: demand is bought in the
    # lower half of the daily range (20 days), supply sold in the upper half
    if cut % (4 * HOUR_MS) == 0 and len(h4) >= 40:
        found = []
        run_into = lambda: maniac.sd_zone_events(h4, 4 * HOUR_MS, '4h')     # noqa: E731
        try:
            found = run_into()
        except Exception as e:
            logging.getLogger(__name__).warning(f"supply/demand of {symbol} failed: {type(e).__name__} {e}", exc_info=True)
        rows = list(d1)[-20:]
        for e in found:
            if len(rows) >= 10:
                hi, lo = max(r[2] for r in rows), min(r[3] for r in rows)
                mid = (e['zone_lo'] + e['zone_hi']) / 2
                e['curve_pos'] = (mid - lo) / (hi - lo) if hi > lo else None
            events.append({k: (v.item() if hasattr(v, 'item') and not isinstance(v, (list, dict)) else v)
                           for k, v in e.items()})
    run('Bollinger W / M', maniac.bollinger_wm_event, m15)
    if cut % (24 * HOUR_MS) == 0 and len(d1) >= 120:
        # O'Neil's cup with handle on DAILY candles at the UTC day's close (eng-58: his weekly / daily bases of >= 7
        # weeks; the 1h / 4h version of eng-40..57 was another pattern under his name)
        from strategies.cup_handle import cup_handle
        run('cup with handle 1d', cup_handle, list(d1), '1d', 24 * HOUR_MS)
    if cut % HOUR_MS == 0 and len(h1) >= 30:
        # Edwards & Magee: a line's significance grows with its timeframe - lines of 1h candles (was 15m)
        run('trendline', maniac.trendline_event, h1, HOUR_MS, '1h')
        if symbol:
            try:
                signals = auction_signals(symbol, h1, m15)
            except Exception as e:
                log.warning(f"auction of {symbol} failed: {type(e).__name__} {e}", exc_info=True)
                signals = []
            for s in signals:
                s = {k: (v.item() if hasattr(v, 'item') else v) for k, v in s.items()}
                d = s['direction']
                events.append({
                    'setup': 'AUCTION LONG' if d > 0 else 'AUCTION SHORT', 'direction': d,
                    'setup_note': f"1h retest of the POC {s['level']:.6g} (concentration {s['conc']:.1f}, {s['kind']}) "
                                  f"reacted: close {'above' if d > 0 else 'below'} by >= "
                                  f"{CONFIG.strategies.auction_reaction_atr:g} ATR",
                    'anchor_level': s['level'], 'anchor_extreme': s['extreme'], 'anchor_label': f"POC ({s['kind']})",
                    'anchor_ts': int(s['level_ts'] or s['ts']), 'anchor_close': s['entry'],
                    'auction_stop': s['stop'], 'auction_target': s['target'], 'auction_kind': s['kind'],
                    'atr_1h': s['atr'], 'event_ts': int(s['ts']) + HOUR_MS})
    return events


def smt_divergence(corr: Optional[Sequence[Sequence[float]]], formed_ms: Optional[int], sweep_ts: int,
                   direction: int) -> Optional[bool]:
    """
    ICT's SMT divergence at a sweep: the coin took its pool (a new low since the pool formed, for SWEEP LOW) while the
    correlated market's candle of the sweep did NOT go below the correlate's own low of that window. None without a
    correlate or a window.
    """
    if not corr or not formed_ms:
        return None
    window = [c for c in corr if formed_ms <= c[0] < sweep_ts]
    at = [c for c in corr if c[0] == sweep_ts]
    if len(window) < 4 or not at:
        return None
    if direction > 0:
        return at[0][3] > min(c[3] for c in window)
    return at[0][2] < max(c[2] for c in window)


def build_context(candles_15m: Sequence[Sequence[float]], candles_1h: Sequence[Sequence[float]], atr: float,
                  zones: List[Zone], now_ms: float, symbol: Optional[str] = None,
                  m15_long: Sequence[Sequence[float]] = (), h1_long: Sequence[Sequence[float]] = (),
                  corr: Optional[Sequence[Sequence[float]]] = None, h4: Sequence = (),
                  d1: Sequence = ()) -> Optional[Context]:
    if not candles_15m or not atr:
        return None
    cut = int(candles_15m[-1][0]) + QUARTER_MS
    last_open = int(candles_15m[-1][0])
    closed_1h = [c for c in candles_1h if c[0] + HOUR_MS <= cut]
    ctx = Context(atr=atr, recent_atr=recent_atr(candles_15m), cut_ms=cut, zones=zones,
                  pools=pools_before(candles_15m, candles_1h, atr, cut, symbol), trend=coin_trend(closed_1h),
                  tail=[list(c) for c in candles_15m[-24:]])
    # Events of the candle that just closed (only while it is fresh: a rebuild after a restart or a backfill must not
    # fire an old candle again)
    if now_ms - cut <= CONFIG.strategies.close_event_max_age_sec * 1000:
        from strategies.level import sweep_at_close
        pools = pools_before(candles_15m, candles_1h, atr, last_open, symbol)
        sweep = sweep_at_close(candles_15m, pools, atr, ctx.trend, symbol)
        if sweep:
            # ICT's SMT divergence is a confirmation of the sweep (eng-35; was the separate 'smt' system): the
            # correlate (BTC / ETH / SOL, corr >= 0.7) did NOT take its own extreme of the same window
            corr15 = merge_candles(corr, [], cut, QUARTER_MS) if corr else None
            sweep['smt_div'] = smt_divergence(corr15, sweep.get('pool_formed_ms'), int(candles_15m[-1][0]),
                                              sweep['direction'])
            ctx.events.append(sweep)
        m15 = merge_candles(m15_long, candles_15m, cut, QUARTER_MS)
        h1 = hours_from(candles_15m, list(h1_long) or list(candles_1h), cut)
        if cut % HOUR_MS == 0:
            # 1h events at the hour's close: the Turtles' 20-day breakout, Wyckoff's spring / UTAD of a trading range
            from strategies.wyckoff_range import wyckoff_events
            ctx.events.extend(wyckoff_events(h1))     # (the breakout is the Turtles' daily system, loop-side)
        corr15 = merge_candles(corr, [], cut, QUARTER_MS) if corr else None
        ctx.events.extend(maniac_events(symbol, m15, h1, corr15, cut, list(h4 or []), list(d1 or [])))
        # classic published methods (strategies/classic.py): Dalton's 80% rule, Crabel's ORB, Connors' RSI(2)
        try:
            from strategies.classic import classic_events
            ctx.events.extend(classic_events(m15, h1, cut))
        except Exception as e:
            logging.getLogger(__name__).warning(f"classic events of {symbol} failed: {type(e).__name__} {e}",
                                                exc_info=True)
    return ctx


PART_COLUMNS = ['timestamp', 'open', 'high', 'low', 'close', 'quote_volume', 'taker_delta', 'atr']


def part_candles(part) -> Tuple[List[List[float]], Optional[float]]:
    """A symbol's closed 15m frame (Polars) -> candles [ts, o, h, l, c, quote_vol, taker_buy] and its latest ATR."""
    if part is None or part.is_empty():
        return [], None
    rows = part.select(['timestamp', 'open', 'high', 'low', 'close', 'quote_volume', 'taker_delta']).rows()
    candles = [[ts, o, h, l, c, qv or 0.0, ((qv or 0.0) + (td or 0.0)) / 2] for ts, o, h, l, c, qv, td in rows]
    atr = part['atr'][-1] if 'atr' in part.columns else None
    return candles, atr


def pick_correlate(symbol: str, m15, corr: Dict[str, list]) -> Optional[list]:
    """
    SMT needs a CLOSELY correlated pair (ICT: ES / NQ): of BTC and ETH, the one whose 15m returns correlate more with
    the coin's over the last 200 candles (BTC <-> ETH for the two themselves).
    """
    import numpy as np
    if symbol.startswith('BTC/'):
        pick_correlate.last_name = 'ETH'
        return corr.get('ETH')
    if symbol.startswith('ETH/'):
        pick_correlate.last_name = 'BTC'
        return corr.get('BTC')
    # only a pair correlated >= smt_min_correlation (crypto SMT guides: > 0.7), else no SMT for the coin
    best, best_r = None, CONFIG.strategies.smt_min_correlation
    own = {int(c[0]): c[4] for c in list(m15)[-201:]}
    for name in ('BTC', 'ETH', 'SOL'):
        other = corr.get(name)
        if not other or symbol.startswith(name + '/'):     # never the coin itself (SOL vs SOL: r = 1)
            continue
        ref = {int(c[0]): c[4] for c in other[-201:]}
        ts = sorted(set(own) & set(ref))
        if len(ts) < 50:
            continue
        a = np.diff(np.log([own[t] for t in ts]))
        b = np.diff(np.log([ref[t] for t in ts]))
        if a.std() > 0 and b.std() > 0:
            r = float(np.corrcoef(a, b)[0, 1])
            if r > best_r:
                best, best_r = other, r
                pick_correlate.last_name = name
    return best


def build_maps(jobs: List[tuple], corr: Optional[Dict[str, object]] = None) -> Dict[str, tuple]:
    """
    Worker PROCESS: level maps and contexts of many coins. A job is (symbol, the closed 15m frame (PART_COLUMNS),
    1h candles (8 days, every coin), card 1h candles (with OI), 1h OI, liquidation events, now ms, 4-day 5m candles,
    with_context, the long 15m / 1h histories (numpy, crypto_maniac's systems)) -> {symbol: (raw levels, Context or
    None)}. The frame is turned into candles here: ~300 conversions after every close held the event loop ~2s.
    `corr`: the SMT correlates' long 15m histories {'BTC': ..., 'ETH': ...} (BTC for every coin, ETH for BTC).
    """
    out: Dict[str, tuple] = {}
    corr = {k: (v.tolist() if hasattr(v, 'tolist') else list(v)) for k, v in (corr or {}).items()}
    for job in jobs:
        symbol, part, h1, card_1h, oi_1h, liq_events, now_ms, candles_4d, with_context = job[:9]
        m15_long, h1_long = (job[9], job[10]) if len(job) > 10 else ((), ())
        d1 = job[11] if len(job) > 11 else []
        h4 = job[12] if len(job) > 12 else []
        w1 = job[13] if len(job) > 13 else []
        try:
            candles, atr = part_candles(part)
            if not candles or not atr:
                continue
            # Estimated liquidations need the 1h OI history (card coins); swings / day / week / sessions use 8 days
            candles_1h = h1 if len(h1) >= len(card_1h) else card_1h
            profile = candles_4d or candles_1h[-96:]
            raw = build_raw(candles, candles_1h, oi_1h, liq_events, atr, now_ms, candles_4d=profile, candles_1d=d1,
                            candles_4h=h4, candles_1w=w1, symbol=symbol)
            if with_context:
                m15 = m15_long.tolist() if hasattr(m15_long, 'tolist') else list(m15_long)
                # after m15 exists (eng-16 read it one line early: every coin's context failed, no worker events)
                pick_correlate.last_name = None
                correlate = pick_correlate(symbol, m15 or candles, corr)
                h1l = h1_long.tolist() if hasattr(h1_long, 'tolist') else list(h1_long)
                context = build_context(candles, candles_1h, atr, merge(raw, atr, symbol=symbol), now_ms, symbol=symbol,
                                        m15_long=m15, h1_long=h1l, corr=correlate, h4=h4, d1=d1)
                if context is not None:
                    context.smt_pair = pick_correlate.last_name if correlate is not None else None
            else:
                context = None
        except Exception as e:
            # a coin without a map has no levels / pools / events: say so instead of dropping it silently (the worker
            # process has no logging config: WARNING goes to its stderr, the bot's console)
            logging.getLogger(__name__).warning(f"Level map of {symbol} failed: {type(e).__name__} {e}", exc_info=True)
            continue
        out[symbol] = (raw, context)
    return out
