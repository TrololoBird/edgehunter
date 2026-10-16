"""
Price primitives of the strategies (strategies/): the leg (find_impulse: its end on the last 12h of 15m candles, its
start searched back over 15m and then 1h history until price was last beyond the end, its timeframe by duration 15m /
1h / 4h and checked in that timeframe's ATR), Fibonacci / retracement of a leg, the leg's own levels (fib, anchored
VWAP), resampling 1m candles, the structure-shift trigger on closed lower-timeframe candles, the spring's volume test,
and the journal's replay of an entry on 1m candles (simulate: manual fill, SL first on a tie; r_be = the same trade with
the stop moved to the entry once TP1 traded, exited at TP2).

LTF trigger (market structure shift): after the extreme made inside the zone, a candle closes beyond the highest high
(lowest low for shorts) of the `ltf_break_lookback` candles up to that extreme, while net taker flow of the last
`ltf_flow_candles` candles after the extreme agrees (the selling into a low is what was absorbed there, not a vote
against the shift).
"""
import math
from typing import Dict, List, Optional, Sequence, Tuple

import polars as pl

from config import CONFIG
from zones import RawLevel, vwap

CONTINUATION, REVERSAL = 'continuation', 'reversal'
MINUTE_MS = 60_000


TF_MS = {'1m': 60_000, '5m': 300_000, '15m': 900_000, '1h': 3_600_000, '4h': 14_400_000}
# Entry trigger timeframe (minutes) per leg timeframe, and how much longer the card may wait for the pullback
# Entry trigger timeframe (minutes) per structure timeframe: a 3-6x step (Elder's factor of ~5)
TRIGGER_MINUTES = {'5m': 5, '15m': 5, '1h': 15, '4h': 60, '1d': 240}
TTL_FACTOR = {'15m': 1, '1h': 2, '4h': 4}


def min_leg_atr() -> float:
    """The smallest leg (in ATR) a reversal can be traded from: its first target, the leg's first retracement level
    (levels.reversal_targets[0], 0.382), must pay at least 1 R over the stop floor (levels.min_stop_atr):
    leg >= min_stop_atr / 0.382. A config value > 0 overrides the formula."""
    cfg = CONFIG.levels
    return cfg.impulse_min_atr or cfg.min_stop_atr / cfg.reversal_targets[0]


def min_leg_move() -> float:
    """The smallest leg as a share of price: its 0.382 target must cover cost_guard round-trip costs (fees + the
    slippage of the entry and the stop exit at the reference liquidity). A config value > 0 overrides the formula."""
    cfg = CONFIG.levels
    cost = CONFIG.journal.fee_round_trip + 2 * cfg.slippage_bps / 1e4
    return cfg.impulse_min_move or cfg.cost_guard * cost / cfg.reversal_targets[0]


def atr_of(candles: Sequence[Sequence[float]], period: int = 14) -> Optional[float]:
    """Average true range of [ts, o, h, l, c, ...] candles (simple mean of the last `period` true ranges)."""
    if len(candles) < period + 1:
        return None
    trs = [max(c[2], p[4]) - min(c[3], p[4]) for p, c in zip(candles[-period - 1:-1], candles[-period:])]
    return sum(trs) / period


def resample_htf(candles_1h: Sequence[Sequence[float]], hours: int) -> List[List[float]]:
    """1h candles -> `hours` candles aligned to UTC multiples (the last one may be partial)."""
    size = hours * 3_600_000
    out: List[List[float]] = []
    for c in candles_1h:
        start = int(c[0]) // size * size
        if out and out[-1][0] == start:
            bar = out[-1]
            bar[2], bar[3], bar[4] = max(bar[2], c[2]), min(bar[3], c[3]), c[4]
        else:
            out.append([start, c[1], c[2], c[3], c[4]])
    return out


def _extend_start(leg_direction: int, end: float, start: float, start_ts: int,
                  before: Sequence[Sequence[float]]) -> Tuple[float, int]:
    """
    Walk back over candles [ts, o, h, l, c] older than the leg start (newest first): the move began after the last
    candle that traded beyond the leg's end; its start is the most extreme opposite price after that candle.
    """
    for c in before:
        if (c[2] > end) if leg_direction > 0 else (c[3] < end):
            break
        if leg_direction > 0 and c[3] < start:
            start, start_ts = c[3], int(c[0])
        elif leg_direction < 0 and c[2] > start:
            start, start_ts = c[2], int(c[0])
    return start, start_ts


def _qualifies(size: float, start: float, atr: Optional[float], candles: int) -> bool:
    cfg = CONFIG.levels
    return bool(atr) and size >= min_leg_atr() * atr and size >= min_leg_move() * start \
        and candles >= cfg.impulse_min_candles


def find_impulse(df: Optional[pl.DataFrame], leg_direction: int,
                 htf: Optional[Sequence[Sequence[float]]] = None) -> Optional[Dict]:
    """
    eng-122, the leg from STRUCTURE (no windows of ours): its END is the last confirmed 2/2 swing high (low for a
    down leg) of the 15m frame; its START is the most extreme opposite price between that end and the last candle
    (15m, then the older 1h history) that traded beyond the end - the move began after it. Its timeframe by duration
    (15m up to 12h, 1h up to 2 days, else 4h) and its ATR in that timeframe; it qualifies by the derived minimum leg
    (levels.min_leg_atr / min_leg_move). Returns {'start', 'end', 'size', 'candles', 'atr', 'atr_15m', 'tf',
    'trigger_minutes', 'start_ts', 'end_ts'} or None.
    """
    if df is None or df.height < 20 or 'atr' not in df.columns:
        return None
    rows = df.select(['timestamp', 'open', 'high', 'low', 'close']).rows()
    atr_15m = df['atr'][-1]
    if not atr_15m:
        return None
    n = len(rows)
    hi = [c[2] for c in rows]
    lo = [c[3] for c in rows]
    end_idx = None
    for k in range(n - 3, 1, -1):
        w = range(k - 2, k + 3)
        # strictly beyond the two candles before, not exceeded by the two after (a tie after = the same top)
        if leg_direction > 0 and hi[k] == max(hi[j] for j in w) and hi[k] > max(hi[k - 2:k]):
            end_idx = k
            break
        if leg_direction < 0 and lo[k] == min(lo[j] for j in w) and lo[k] < min(lo[k - 2:k]):
            end_idx = k
            break
    if end_idx is None:
        return None
    end = hi[end_idx] if leg_direction > 0 else lo[end_idx]
    end_ts = int(rows[end_idx][0])
    first_15m = int(rows[0][0])
    older = [list(r) for r in rows[:end_idx]][::-1] + \
        [list(c) for c in (htf or []) if c[0] + 3_600_000 <= first_15m][::-1]
    start, start_ts = None, None
    for c in older:
        if (c[2] > end) if leg_direction > 0 else (c[3] < end):
            break
        if start is None or (c[3] < start if leg_direction > 0 else c[2] > start):
            start, start_ts = (c[3] if leg_direction > 0 else c[2]), int(c[0])
    if start is None:
        return None
    # no candle beyond the end in the history (a new high / low): the origin is the extreme of the whole history
    duration = end_ts - start_ts
    # eng-123, Elder's factor of five: the leg's timeframe is the largest of 15m / 1h / 4h holding >= 5 of its candles
    tf = '4h' if duration >= 5 * TF_MS['4h'] else '1h' if duration >= 5 * TF_MS['1h'] else '15m'
    htf_list = [list(c[:5]) for c in (htf or [])]
    atr = atr_15m if tf == '15m' else atr_of(htf_list if tf == '1h' else resample_htf(htf_list, 4))
    if not atr:
        tf, atr = '15m', atr_15m          # no 1h history loaded yet: the leg measured in the 15m ATR
    size = abs(end - start)
    if not atr or size < min_leg_atr() * atr or size < min_leg_move() * start:
        return None
    return {'start': start, 'end': end, 'size': size, 'candles': duration // TF_MS[tf], 'atr': atr,
            'atr_15m': atr_15m, 'tf': tf, 'trigger_minutes': TRIGGER_MINUTES[tf], 'start_ts': start_ts, 'end_ts': end_ts}


def retracement_of(impulse: Dict[str, float], price: float) -> float:
    """How much of the leg is given back at `price`: 0 = at the leg's end, 1 = back at its start."""
    direction = 1 if impulse['end'] > impulse['start'] else -1
    return direction * (impulse['end'] - price) / impulse['size']


def fib_price(impulse: Dict[str, float], ratio: float) -> float:
    """Retracement level `ratio` of the leg (0 = end, 1 = start); negative ratios lie beyond the end."""
    direction = 1 if impulse['end'] > impulse['start'] else -1
    return impulse['end'] - direction * ratio * impulse['size']


def _leg_levels(df: pl.DataFrame, impulse: Dict[str, float], far_side: Optional[float]) -> List[RawLevel]:
    """Card-specific levels: the leg's Fibonacci levels, a range's far side, VWAP anchored at the leg's start."""
    cfg = CONFIG.levels
    out = [RawLevel(fib_price(impulse, r), 'fib', f"fib {r:g}") for r in (0.382, 0.5, 0.618, 0.786)]
    out += [RawLevel(fib_price(impulse, 1.0 - r), 'fib', f"fib ext {r:g}") for r in cfg.continuation_targets if r > 1.0]
    if far_side:
        out.append(RawLevel(far_side, 'range', 'range edge'))
    rows = df.select(['timestamp', 'open', 'high', 'low', 'close', 'quote_volume']).rows()
    out += vwap(rows, impulse['start_ts'], 'VWAP leg')
    return out


def reached_after(candles: Sequence[Sequence[float]], end_ts: int, end: float, direction: int) -> float:
    """
    Furthest price in the trade's direction (+1: highest) reached after a reversed leg's end, from candles
    [ts, o, h, l, c, ...]: the end candle's close (its high may have printed before its low) and the full range of
    every later candle.
    """
    after = [c for c in candles if c[0] >= end_ts]
    if not after:
        return end
    prices = [after[0][4]] + [c[2] if direction > 0 else c[3] for c in after[1:]]
    return max(prices) if direction > 0 else min(prices)


def resample(candles: Sequence[Sequence[float]], minutes: int, now_ms: Optional[float] = None) -> List[List[float]]:
    """
    1m candles [open_time, open, high, low, close, quote_vol, taker_buy_quote] -> `minutes` candles aligned to
    epoch multiples of `minutes`. Only buckets that have closed by `now_ms` are returned (all of them when None).
    audit C04: a repeated minute counts once (the last copy), and a CLOSED bucket is returned only when its minutes are
    all there (up to 2% missing for bars over an hour) - two minutes 00:00 and 00:04 were a 'closed 5m candle', its
    FVG / MSS / touches built on three minutes that never arrived. Missing minutes are never interpolated.
    """
    seen: Dict[int, Sequence[float]] = {}
    for c in candles:
        seen[int(c[0])] = c                      # a re-delivered minute replaces its copy instead of adding to it
    rows = [seen[t] for t in sorted(seen)]
    if minutes <= 1:
        return [list(c) for c in rows if now_ms is None or c[0] + MINUTE_MS <= now_ms]
    size = minutes * MINUTE_MS
    out: List[List[float]] = []
    count: List[int] = []
    for c in rows:
        start = int(c[0]) // size * size
        if out and out[-1][0] == start:
            bar = out[-1]
            bar[2] = max(bar[2], c[2])
            bar[3] = min(bar[3], c[3])
            bar[4] = c[4]
            bar[5] += c[5]
            bar[6] += c[6]
            count[-1] += 1
        else:
            out.append([start, c[1], c[2], c[3], c[4], c[5], c[6]])
            count.append(1)
    if now_ms is not None:
        need = minutes if minutes <= 60 else int(minutes * 0.98)
        out = [bar for bar, n in zip(out, count) if bar[0] + size <= now_ms and n >= need]
    return out


def ltf_trigger(candles: Sequence[Sequence[float]], direction: int, since_ms: int,
                interval_ms: int = MINUTE_MS) -> Optional[Dict[str, float]]:
    """
    Market structure shift on closed LTF candles [open_time, open, high, low, close, quote_vol, taker_buy_quote].
    Zone candles are those still open at or after `since_ms` (the minute price entered the zone). Returns
    {'entry', 'extreme', 'time', 'extreme_time'} for the first trigger, else None.
    """
    cfg = CONFIG.levels
    # 4 x the lookback before the zone: room for the swing the shift breaks (the zone's own candles decide the extreme)
    usable = list(candles)          # eng-119: the whole history given (the 4 x 5-candle window was ours)
    zone_idx = [i for i, c in enumerate(usable) if c[0] + interval_ms > since_ms]
    if len(zone_idx) < 2:
        return None

    # Extreme against the trade made inside the zone: the swing the stop will sit beyond
    if direction > 0:
        extreme_idx = min(zone_idx, key=lambda i: usable[i][3])
        extreme = usable[extreme_idx][3]
    else:
        extreme_idx = max(zone_idx, key=lambda i: usable[i][2])
        extreme = usable[extreme_idx][2]
    # ICT's market structure shift: the break of the LAST swing (a 2/2 fractal) the move made before the extreme - the
    # lower high a long breaks; without one in the lookback, the high / low of the ltf_break_lookback candles up to it
    level = None
    for j in range(extreme_idx - 2, 1, -1):
        if j + 2 >= len(usable) or j - 2 < 0:
            continue
        w = usable[j - 2:j + 3]
        if direction > 0 and usable[j][2] == max(c[2] for c in w) and sum(c[2] == usable[j][2] for c in w) == 1:
            level = usable[j][2]
            break
        if direction < 0 and usable[j][3] == min(c[3] for c in w) and sum(c[3] == usable[j][3] for c in w) == 1:
            level = usable[j][3]
            break
    if level is None:
        return None                 # eng-119: no swing, no structure shift (the 5-candle fallback was ours)

    for i in range(extreme_idx + 1, len(usable)):
        close = usable[i][4]
        if direction * (close - level) <= 0:
            continue
        # The flow of the shift itself: candles after the extreme (the selling INTO a low is what was absorbed there)
        # eng-119: the taker-flow requirement was ours (ICT's shift is the close beyond the swing) - journaled only
        recent = usable[max(extreme_idx + 1, i - cfg.ltf_flow_candles + 1):i + 1]
        flow = sum(2 * c[6] - c[5] for c in recent)
        return {'entry': close, 'extreme': extreme, 'time': usable[i][0] + interval_ms,
                'extreme_time': usable[extreme_idx][0], 'shift_flow': flow}
    return None


def pullback_volume_ok(minute_candles: Sequence[Sequence[float]], since_ms: int, until_ms: int,
                       reference_minute_usd: float) -> Optional[bool]:
    """
    Wyckoff "test" of a spring: the pullback after the spring trades on lower volume (supply dried up). The average
    1m quote volume in [since_ms, until_ms) must be <= spring_test_volume_ratio x the spring candle's average minute.
    audit C08: None when it cannot be observed (no reference / no pullback minutes) - an unobserved test is not a
    passed one.
    """
    if not reference_minute_usd:
        return None
    window = [c[5] for c in minute_candles if since_ms <= c[0] < until_ms]
    if not window:
        return None
    return sum(window) / len(window) <= CONFIG.levels.spring_test_volume_ratio * reference_minute_usd


def pullback_spread_ok(minute_candles: Sequence[Sequence[float]], since_ms: int, until_ms: int,
                       spring_range: Optional[float], spring_minutes: int = 60) -> Optional[bool]:
    """
    eng-55: Wyckoff's test also NARROWS the spread (StockCharts Wyckoff tutorial; tradingwyckoff: test ranges 40-70%
    smaller than the spring's). The pullback's 15m candles average a range <= spring_test_spread_ratio x the spring
    candle's range scaled to 15m by sqrt(time) - audit: sqrt(spring_minutes / 15), i.e. / 4 for the 4h spring the
    detector runs on (the old / 2 was the 1h case). None when it cannot be observed (audit C08).
    """
    if not spring_range:
        return None
    bars = resample([c for c in minute_candles if since_ms <= c[0] < until_ms], 15, until_ms)
    if not bars:
        return None
    avg = sum(b[2] - b[3] for b in bars) / len(bars)
    return avg <= CONFIG.levels.spring_test_spread_ratio * spring_range / (max(spring_minutes, 15) / 15) ** 0.5


# eng-124: bps of an executor.max_notional_usd market order walked through each coin's REST book (worst side, from the
# mid: half spread included), refreshed with the universe (fetcher._refresh_book_slippage)
BOOK_SLIP: Dict[str, float] = {}


def slippage_bps(volume_24h: Optional[float] = None, symbol: Optional[str] = None) -> float:
    """Slippage of one market order in bps: the base for liquid coins, more for thin ones (CONFIG.levels); with the
    symbol, never below its measured book slippage (eng-124: the volume model priced 84 of 195 coins' books too cheap)."""
    model = _model_slippage_bps(volume_24h)
    measured = BOOK_SLIP.get(symbol) if symbol else None
    return model if measured is None or measured != measured or measured == float('inf') else max(model, measured)


def _model_slippage_bps(volume_24h: Optional[float] = None) -> float:
    cfg = CONFIG.levels
    if not volume_24h or volume_24h <= 0:
        return cfg.slippage_bps
    # eng-71: square-root impact of a slippage_notional_usd order (was 5 x sqrt($500M / V): no order size)
    impact = 1e4 * cfg.slippage_impact_sigma * 0.5 * math.sqrt(cfg.slippage_notional_usd / volume_24h)
    return min(cfg.slippage_max_bps, cfg.slippage_half_spread_bps + impact)


def stop_fill(sl: float, direction: int, candle: List, slip: float) -> float:
    """A stop is a market order: it fills at the stop, or at the open when the candle gapped through it, plus slippage."""
    o = float(candle[1])
    px = o if ((o < sl) if direction > 0 else (o > sl)) else sl
    return px * (1 - direction * slip)


def fill_price(levels: Dict[str, float], direction: int, candles: List[List]) -> Optional[float]:
    """
    Price a human gets: the open of the first 1m candle after the trigger (the journal fetches candles from the
    first full minute after the entry, i.e. ~fill_delay_sec later) plus slippage against the trade.
    """
    if not candles:
        return None
    slip = slippage_bps(levels.get('volume_24h'), levels.get('symbol')) / 1e4
    return float(candles[0][1]) * (1 + direction * slip)


FUNDING_MS = 8 * 3_600_000


def funding_r(funding_8h: Optional[float], direction: int, entry: float, risk: float, t0: float, t1: float,
              interval_h: Optional[float] = None) -> float:
    """
    Funding the position pays over (t0, t1] in R: the rate per settlement x the settlements crossed x entry / risk.
    Longs pay a positive rate. audit C12: the contract's OWN interval (interval_h: 8 / 4 / 1 h, settlements at its
    multiples from 00 UTC) - a 4h contract held 01:00-05:00 settled at 04:00 and paid; the 8h grid counted none. The
    rate is the 8h-normalized one (fetcher), so one settlement of an h-hour contract is rate x h / 8. Still a model:
    one rate for the whole hold, not the actual settled rates (those are the exchange's ledger - executor).
    """
    if not funding_8h or not risk:
        return 0.0
    hours = interval_h if interval_h and interval_h > 0 else 8
    step = hours * 3_600_000
    settlements = int(t1 // step) - int(t0 // step)
    return direction * funding_8h * hours / 8 * max(0, settlements) * entry / risk


def simulate(levels: Dict[str, float], direction: int, candles: List[List], use_fill: bool = True,
             funding_8h: Optional[float] = None) -> Dict:
    """
    Replay 1m candles [open_time, open, high, low, close, ...] after an entry. With use_fill the trade is entered at
    fill_price (manual execution) and R is measured from there; otherwise at levels['entry'] (the trigger close).
    SL and TPs are checked candle by candle; if one candle touches both SL and a TP, SL counts first (conservative); a
    target counts only once price traded target_through_bps THROUGH it (a limit order is not filled by a touch).
    With funding_8h (the rate at the signal) each exit's R is net of the funding settlements it was held through.
    Returns the furthest target reached before the stop and the R result of exiting fully at TP1 / TP2
    (unfinished trades are marked to the last close). A fill already beyond the stop is 'SKIPPED' (not traded).
    """
    sl = levels['sl']
    entry = levels['entry']
    # a system without a profit target journals NULL targets (eng-51): unreachable here, the trade is marked to the end
    targets = [t if t is not None else entry + direction * 1e12 for t in (levels['tp1'], levels['tp2'], levels['tp3'])]
    result = {'filled': 1, 'outcome': 'OPEN', 'r_tp1': None, 'r_tp2': None, 'r_be': None, 'entry_fill': None}
    if use_fill:
        # eng-58: a resting limit (Seiden, ICT CE / OTE) fills AT its price - it was traded at the trigger; only the
        # market entries take the next minute's open + slippage (a human's reaction)
        fill = float(entry) if levels.get('limit_entry') and candles else fill_price(levels, direction, candles)
        if fill is None:
            result['filled'] = 0
            return result
        result['entry_fill'] = fill
        if direction * (fill - sl) <= 0 or direction * (targets[0] - fill) <= 0:
            result.update(filled=0, outcome='SKIPPED')
            return result
        entry = fill
    risk = abs(entry - sl)
    if not candles or not risk:
        result['filled'] = 0
        return result

    through = CONFIG.levels.target_through_bps / 1e4
    slip = slippage_bps(levels.get('volume_24h'), levels.get('symbol')) / 1e4

    def reached(level: float, high: float, low: float) -> bool:
        # a limit target fills once price traded through it (a touch fills only part of the queue)
        return high >= level * (1 + through) if direction > 0 else low <= level * (1 - through)

    best_target = 0
    exits = {1: None, 2: None}
    t_open, t_last = float(candles[0][0]), float(candles[-1][0]) + MINUTE_MS
    exit_t = {1: t_last, 2: t_last}
    be_t = t_last
    # Variant D: once TP1 traded the stop moves to the entry (from the next candle), the rest exits at TP2
    be_result, be_armed = None, False
    for c in candles:
        high, low = float(c[2]), float(c[3])
        stop = entry if be_armed else sl
        if (low <= stop) if direction > 0 else (high >= stop):
            be_result = direction * (stop_fill(stop, direction, c, slip) - entry) / risk
            be_t = float(c[0]) + MINUTE_MS
            break
        if reached(targets[1], high, low):
            be_result = abs(targets[1] - entry) / risk
            be_t = float(c[0]) + MINUTE_MS
            break
        if reached(targets[0], high, low):
            be_armed = True
    if be_result is None:
        be_result = direction * (float(candles[-1][4]) - entry) / risk
        be_result = max(be_result, 0.0) if be_armed and be_result < 0 else be_result
    # A stop is a market order: it fills beyond the stop price by the slippage (targets are limit orders)
    for c in candles:
        high, low = float(c[2]), float(c[3])
        if (low <= sl) if direction > 0 else (high >= sl):
            stop_r = direction * (stop_fill(sl, direction, c, slip) - entry) / risk
            for k in exits:
                if exits[k] is None:
                    exits[k] = stop_r
                    exit_t[k] = float(c[0]) + MINUTE_MS
            result['outcome'] = f"TP{best_target}" if best_target else 'SL'
            break
        for k, level in enumerate(targets, start=1):
            if k > best_target and reached(level, high, low):
                best_target = k
        for k in exits:
            if exits[k] is None and best_target >= k:
                exits[k] = abs(targets[k - 1] - entry) / risk
                exit_t[k] = float(c[0]) + MINUTE_MS
                if k == 1:
                    # minutes from the entry to TP1 (eng-57: the data a measured time stop needs; journal tp1_min)
                    result['tp1_min'] = (exit_t[1] - t_open) / MINUTE_MS
    else:
        result['outcome'] = f"TP{best_target}" if best_target else 'OPEN'

    mark = direction * (float(candles[-1][4]) - entry) / risk
    result['r_tp1'] = (exits[1] if exits[1] is not None else mark) - funding_r(funding_8h, direction, entry, risk, t_open, exit_t[1])
    result['r_tp2'] = (exits[2] if exits[2] is not None else mark) - funding_r(funding_8h, direction, entry, risk, t_open, exit_t[2])
    result['r_be'] = be_result - funding_r(funding_8h, direction, entry, risk, t_open, be_t)
    return result
