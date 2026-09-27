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
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from config import CONFIG
from zones import HOUR_MS, RawLevel, Zone, build_raw, day_levels, equal_pools, merge, round_levels

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
                    now_ms: int) -> List[Pool]:
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
    for level in equal_pools(swing_levels, recent_1h, atr):
        group = [f for (p, side), f in formed_of.items() if side == level.side and abs(p - level.price) <= CONFIG.zones.equal_tolerance_atr * atr]
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
                 at_ms: int) -> List[Pool]:
    """The pools as they stood when the candle opening at `at_ms` started."""
    hour = at_ms // HOUR_MS * HOUR_MS
    h1_before = [c for c in candles_1h if c[0] + HOUR_MS <= hour]
    c15_hour = [c for c in candles_15m if hour <= c[0] < at_ms]
    return liquidity_pools(h1_before, c15_hour, atr, at_ms)


def build_context(candles_15m: Sequence[Sequence[float]], candles_1h: Sequence[Sequence[float]], atr: float,
                  zones: List[Zone], now_ms: float) -> Optional[Context]:
    if not candles_15m or not atr:
        return None
    cut = int(candles_15m[-1][0]) + QUARTER_MS
    last_open = int(candles_15m[-1][0])
    closed_1h = [c for c in candles_1h if c[0] + HOUR_MS <= cut]
    ctx = Context(atr=atr, recent_atr=recent_atr(candles_15m), cut_ms=cut, zones=zones,
                  pools=pools_before(candles_15m, candles_1h, atr, cut), trend=coin_trend(closed_1h),
                  tail=[list(c) for c in candles_15m[-24:]])
    # Events of the candle that just closed (only while it is fresh: a rebuild after a restart or a backfill must not
    # fire an old candle again)
    if now_ms - cut <= CONFIG.strategies.close_event_max_age_sec * 1000:
        from strategies.breakout import breakout_at_close
        from strategies.level import sweep_at_close
        pools = pools_before(candles_15m, candles_1h, atr, last_open)
        for event in (sweep_at_close(candles_15m, pools, atr, ctx.trend), breakout_at_close(candles_15m, atr, closed_1h)):
            if event:
                ctx.events.append(event)
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


def build_maps(jobs: List[tuple]) -> Dict[str, tuple]:
    """
    Worker PROCESS: level maps and contexts of many coins. A job is (symbol, the closed 15m frame (PART_COLUMNS),
    1h candles (8 days, every coin), card 1h candles (with OI), 1h OI, liquidation events, now ms, 4-day 5m candles,
    with_context) -> {symbol: (raw levels, Context or None)}. The frame is turned into candles here: ~300 conversions
    after every close held the event loop ~2s.
    """
    out: Dict[str, tuple] = {}
    for symbol, part, h1, card_1h, oi_1h, liq_events, now_ms, candles_4d, with_context in jobs:
        try:
            candles, atr = part_candles(part)
            if not candles or not atr:
                continue
            # Estimated liquidations need the 1h OI history (card coins); swings / day / week / sessions use 8 days
            candles_1h = h1 if len(h1) >= len(card_1h) else card_1h
            profile = candles_4d or candles_1h[-96:]
            raw = build_raw(candles, candles_1h, oi_1h, liq_events, atr, now_ms, candles_4d=profile)
            context = build_context(candles, candles_1h, atr, merge(raw, atr), now_ms) if with_context else None
        except Exception:
            continue
        out[symbol] = (raw, context)
    return out
