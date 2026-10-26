"""
Level map of one coin: where price is likely to stall or where stops / liquidations sit, from several independent
sources, merged into zones weighted by confluence. levels.py builds entry zones, stops and targets from it.

Sources (CONFIG.zones.weights):
- swing_15m / swing_1h: fractal highs and lows (a high with `width` lower highs on each side);
- equal: equal highs / lows (>= 2 swings within equal_tolerance_atr) that were not swept since: stop pools;
- pdhl: previous UTC day's / week's high and low, the current day's high / low and the last completed sessions'
  (Asia / London / New York, the exchanges' local hours in CONFIG.strategies.sweep_sessions) highs / lows: where stops rest;
- book: order-book liquidity that stayed (heatmap bands, depth.py);
- poc / va / hvn: volume profile of 5m candles over ~4 days and of 15m candles over ~24h, each candle's volume spread evenly over its
  range: point of control, value-area edges (CBOT method), high-volume nodes;
- liq_est: ESTIMATED liquidation clusters: every 1h OI increase at price P opened as many longs as shorts (each
  contract has both sides); each side is spread over leverage tiers, the aggressive (taker) side of the candle is
  assumed to use more leverage (its weight shifts towards the high tiers); a position at leverage L is liquidated around
  P * (1 -+ 1/L +- maintenance). OI decreases remove positions proportionally; clusters price already crossed are
  gone. A model (like the public liquidation heatmaps), not data;
- liq_hit: prices where liquidations were actually observed in the last 24h (a pool already swept);
- wall: persistent order-book walls (hot coins only, depth.py);
- liq_hl: REAL liquidation prices of large Hyperliquid accounts (positioning.py), summed per price bucket;
- vwap: VWAP of the current UTC day and VWAP anchored at the measured leg's start;
- fib / range: Fibonacci levels of a leg and a trading range's edges (added by the strategies' plans).

Everything is a hypothesis: the journal stores which sources each target and stop came from, and stats.py measures
how often each kind was reached.
"""
from dataclasses import dataclass, field
import json
import math
import os
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from config import CONFIG

# Data behind the liquidation estimate (written by positioning.py, read here by the maps worker process too):
# models/leverage_mix.json - the notional-weighted leverage of the tracked Hyperliquid accounts' real positions;
# models/maintenance.json  - each contract's lowest-tier maintenance margin and max leverage (Bybit's public risk
# limits; Binance publishes its brackets only to signed requests). Both replace guessed constants (eng-57).
LEVERAGE_MIX_PATH = os.path.join('models', 'leverage_mix.json')
MAINTENANCE_PATH = os.path.join('models', 'maintenance.json')
_FILE_CACHE: Dict[str, Tuple[float, object]] = {}


def _json_file(path: str):
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    hit = _FILE_CACHE.get(path)
    if hit is None or hit[0] != mtime:
        try:
            with open(path, encoding='utf-8') as fh:
                _FILE_CACHE[path] = hit = (mtime, json.load(fh))
        except (OSError, ValueError):
            return None
    return hit[1]


def leverage_mix() -> List[Tuple[float, float]]:
    """(leverage, share of notional) of real positions; the configured guess only until the first measurement."""
    data = _json_file(LEVERAGE_MIX_PATH)
    mix = [(float(l), float(w)) for l, w in (data or {}).get('mix', []) if float(l) >= 1 and float(w) > 0]
    if mix:
        return sorted(mix)
    cfg = CONFIG.zones
    return list(zip(map(float, cfg.liq_leverages), cfg.liq_leverage_weights, strict=True))


def maintenance_of(symbol: Optional[str]) -> Tuple[float, Optional[float]]:
    """(maintenance margin rate, max leverage) of the contract's lowest risk tier; the configured rate without data."""
    data = _json_file(MAINTENANCE_PATH) or {}
    row = data.get((symbol or '').split('/')[0] + 'USDT') if symbol else None
    if row:
        return float(row[0]), (float(row[1]) if row[1] else None)
    return CONFIG.zones.liq_maintenance, None


def equal_tolerance(symbol: Optional[str], price: float, atr: float) -> float:
    """Two swings are 'equal' when they differ by less than the typical pierce of an equal-high / low on this coin
    (p50, pierce.py: the measured overshoot); the ATR share only without the model."""
    from pierce import overshoot
    return overshoot(symbol, 'equal', price, 'p50') or CONFIG.zones.equal_tolerance_atr * atr

HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS

# Kinds that mark resting stops / liquidations: the stop goes beyond them, TP3 prefers them
# Resting orders / stops still there. 'liq_hit' (liquidations that already happened) is a level, not a pool: the
# stops there are gone, so stops are not pushed beyond it and TP3 does not aim for it
POOL_KINDS = ('equal', 'liq_est', 'pdhl', 'range', 'liq_hl', 'round')
# Price-action levels whose edge the market drew with wicks (swings, equal highs / lows, previous day / week and
# sessions, a range's edges, round numbers) or resting size that stayed (book liquidity bands): a stop belongs beyond
# such a zone. VWAP, volume profile, Fibonacci and estimated liquidations have no 'broken here' edge.
# 'book' (order-book liquidity bands) left the stop structures 2026-10-05: resting orders can be pulled (31% of large
# crypto orders could spoof, arXiv 2504.15908) and no study shows depth holding price over hours - a stop is not
# placed on them; they stay map levels (targets / context)
# eng-169e (Osler, NY Fed SR 125 / 150: take-profits cluster AT round numbers, stop-losses just BEYOND them and their
# triggering accelerates the move): a round number stays a level and a TP3 pool, but no stop is pushed beyond it - that
# put our stop inside the band where the others' stops cascade. Estimated liquidations are a model, never a stop pool.
STOP_POOL_KINDS = tuple(k for k in POOL_KINDS if k not in ('liq_est', 'round'))
# eng-169e: 'round' left the structures a stop is anchored beyond (Osler: others' stops cascade just beyond it)
STRUCTURE_KINDS = ('swing_15m', 'swing_1h', 'flip_1h', 'swing_1d', 'swing_1w', 'pmhl', 'year', 'equal', 'pdhl', 'range',
                   'ob_15m', 'ob_1h', 'ob_4h', 'ob_1d', 'ob_1w',
                   'breaker_15m', 'breaker_1h', 'breaker_4h', 'breaker_1d', 'breaker_1w')


@dataclass
class RawLevel:
    price: float
    kind: str
    label: str
    side: int = 0          # +1 a high / resistance-type level, -1 a low / support-type, 0 either
    size: float = 0.0      # USD for liquidation levels
    ts: int = 0            # open time of the candle that made the level (swings), 0 = unknown
    # the candle's body edge on the level's side (a high: max(open, close) of the candle that made it): the zone runs
    # from where price was ACCEPTED (the body) to where it only probed (the wick = `price`); None = a point level
    body: Optional[float] = None
    # audit D09: a swing a later WICK traded through (no close beyond: still an S/R level, but its stops were taken)
    swept: bool = False


@dataclass
class Zone:
    price: float
    lo: float
    hi: float
    kinds: List[str] = field(default_factory=list)
    labels: List[str] = field(default_factory=list)
    strength: float = 0.0
    ts: int = 0            # open time of the candle that made the zone's earliest level (0 = unknown): the chart's box
    # audit D05: the merged levels as (kind, price, lo, hi, swept) - which kind made which edge (a plan of a higher timeframe
    # takes only its own levels' edges, see geometry.htf_zones)
    parts: List[Tuple[str, float, float, float, bool]] = field(default_factory=list)
    origin: int = 0        # id() of the zone this one was trimmed from (geometry.htf_zones), 0 = itself

    @property
    def label(self) -> str:
        return ' · '.join(self.labels[:4])

    def as_dict(self) -> Dict:
        return {'price': self.price, 'lo': self.lo, 'hi': self.hi, 'kinds': self.kinds, 'label': self.label,
                'strength': round(self.strength, 2), 'ts': self.ts}


def _weights() -> Dict[str, float]:
    return {k: float(w) for k, w in CONFIG.zones.weights}


# ---------------------------------------------------------------------------------------------------- sources

def swings(candles: Sequence[Sequence[float]], width: int, kind: str, tf: str) -> List[RawLevel]:
    """
    Fractal swing highs / lows of [ts, o, h, l, c, ...] candles that are still intact: no later candle CLOSED beyond
    them (a broken swing is no longer where stops rest; wicks through it are sweeps and keep it alive).
    """
    out: List[RawLevel] = []
    n = len(candles)
    flip = kind == 'swing_1h'
    pierced: set = set()                # one pierce pool per extreme (one wick through several swings)
    last = candles[-1][4] if n else 0.0
    # Highest / lowest close after each index, to test "broken since" in one pass
    max_after = [float('-inf')] * (n + 1)
    min_after = [float('inf')] * (n + 1)
    hi_after = [float('-inf')] * (n + 1)
    lo_after = [float('inf')] * (n + 1)
    for i in range(n - 1, -1, -1):
        max_after[i] = max(max_after[i + 1], candles[i][4])
        min_after[i] = min(min_after[i + 1], candles[i][4])
        hi_after[i] = max(hi_after[i + 1], candles[i][2])
        lo_after[i] = min(lo_after[i + 1], candles[i][3])
    for i in range(width, n - width):
        h, l = candles[i][2], candles[i][3]
        around = candles[i - width:i] + candles[i + 1:i + 1 + width]
        if all(c[2] < h for c in around):
            if max_after[i + 1] <= h:
                out.append(RawLevel(h, kind, f"{tf} high", +1, ts=int(candles[i][0]),
                                    body=max(candles[i][1], candles[i][4]), swept=hi_after[i + 1] > h))
                if hi_after[i + 1] > h and (hi_after[i + 1], +1) not in pierced:
                    pierced.add((hi_after[i + 1], +1))
                    # eng-150 (plan 4.5): a false pierce's extreme holds the new stops
                    out.append(RawLevel(hi_after[i + 1], kind, f"{tf} high (pierce)", +1, ts=int(candles[i][0])))
            elif flip and last > h:
                # eng-150 (plan 4.5): closed through and still above = the old resistance is support (S/R flip)
                out.append(RawLevel(h, f"flip_{tf}", f"{tf} S/R flip", -1, ts=int(candles[i][0]),
                                    body=max(candles[i][1], candles[i][4])))
        if all(c[3] > l for c in around):
            if min_after[i + 1] >= l:
                out.append(RawLevel(l, kind, f"{tf} low", -1, ts=int(candles[i][0]),
                                    body=min(candles[i][1], candles[i][4]), swept=lo_after[i + 1] < l))
                if lo_after[i + 1] < l and (lo_after[i + 1], -1) not in pierced:
                    pierced.add((lo_after[i + 1], -1))
                    out.append(RawLevel(lo_after[i + 1], kind, f"{tf} low (pierce)", -1, ts=int(candles[i][0])))
            elif flip and last < l:
                out.append(RawLevel(l, f"flip_{tf}", f"{tf} S/R flip", +1, ts=int(candles[i][0]),
                                    body=min(candles[i][1], candles[i][4])))
    return out


def equal_pools(levels: List[RawLevel], candles: Sequence[Sequence[float]], atr: float,
                symbol: Optional[str] = None,
                history: Optional[Sequence[Sequence[float]]] = None) -> List[RawLevel]:
    """Equal highs / lows: >= 2 swings within the tolerance, not traded through since the latest of them.
    `history` (1h candles): the sweep check of pools older than the 15m window (eng-102: a pair of 1h swings from 5 days
    ago, wicked through 3 days ago, read as an untouched EQH - the 15m candles hold ~2 days)."""
    tol = equal_tolerance(symbol, candles[-1][4], atr) if candles else CONFIG.zones.equal_tolerance_atr * atr
    out: List[RawLevel] = []
    for side in (+1, -1):
        same = sorted((l for l in levels if l.side == side), key=lambda l: l.price)
        group: List[RawLevel] = []
        for level in same + [None]:
            if level is not None and group and level.price - group[0].price <= tol:
                group.append(level)
                continue
            if len(group) >= 2:
                edge = max(l.price for l in group) if side > 0 else min(l.price for l in group)
                # Swept when a candle after the latest swing of the group traded beyond the pool (the last 12 candles
                # when the swings carry no time)
                latest = max(l.ts for l in group)
                after = [c for c in candles if c[0] > latest] if latest else candles[-12:]
                if latest and history:
                    start = candles[0][0] if candles else float('inf')
                    after = [c for c in history if latest < c[0] < start] + after
                # any trade beyond the pool's edge took the stops resting there (as structure.liquidity_pools)
                swept = any(c[2] > edge for c in after) if side > 0 else any(c[3] < edge for c in after)
                if not swept:
                    # where the touches were accepted: the body closest to the wicks among them
                    bodies = [l.body for l in group if l.body is not None]
                    body = (max(bodies) if side > 0 else min(bodies)) if bodies else None
                    out.append(RawLevel(edge, 'equal', f"{'EQH' if side > 0 else 'EQL'}×{len(group)}", side,
                                        ts=latest, body=body))
            group = [level] if level is not None else []
    return out


WEEK_MS = 7 * DAY_MS
# 1970-01-01 was a Thursday: ISO weeks (Monday 00:00 UTC) start 4 days after the epoch's week boundary
WEEK_OFFSET_MS = 4 * DAY_MS


def round_levels(price: float, span: float) -> List[float]:
    """
    Round prices within `span` of `price`: multiples of a tenth of the price's order of magnitude (84,000 for BTC,
    3,100 for ETH, 0.23 for a 0.2345 coin). Stop-loss orders cluster just beyond round numbers and take-profits at
    them (Osler, NY Fed Staff Report 150): the stop pools a sweep takes, and levels price reacts to.
    """
    if price <= 0 or span <= 0:
        return []
    step = 10 ** math.floor(math.log10(price)) / 10
    lo, hi = math.ceil((price - span) / step), math.floor((price + span) / step)
    return [round(k * step, 12) for k in range(lo, hi + 1) if k > 0 and abs(k * step - price) > 1e-12]


def session_windows(now_ms: float) -> List[Tuple[str, int, int]]:
    """
    The last COMPLETED occurrence of each session before now: (name, start ms, end ms). Sessions are the exchanges'
    LOCAL hours (Tokyo 09-18, London 08-17, New York 08-17: 00-09 / 08-17 or 07-16 / 13-22 or 12-21 UTC with daylight
    saving - the forex session tables); eng-57, were fixed UTC hours that matched neither season.
    """
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo
    out = []
    now = datetime.fromtimestamp(now_ms / 1000, timezone.utc)
    for name, tz_name, start_h, end_h in CONFIG.strategies.sweep_sessions:
        tz = ZoneInfo(tz_name)
        local_day = now.astimezone(tz).date()
        for back in (0, 1, 2):
            d = local_day - timedelta(days=back)
            start = datetime(d.year, d.month, d.day, start_h, tzinfo=tz)
            end = datetime(d.year, d.month, d.day, end_h, tzinfo=tz)
            if end.timestamp() * 1000 <= now_ms:
                out.append((name, int(start.timestamp() * 1000), int(end.timestamp() * 1000)))
                break
    return out


def htf_swings(candles_1d: Optional[Sequence[Sequence[float]]], candles_1w: Optional[Sequence[Sequence[float]]],
               now_ms: float) -> List[RawLevel]:
    """eng-70 (the owner: "where the 15m / 1h / 4h hold no level, the daily / weekly do"): intact daily (fractal 3) and
    weekly (fractal 2) swing highs / lows, the previous calendar month's high / low and the month's open, the 52-week
    high / low (Murphy / Bulkowski: the prior period's extremes and major swings are where the large S/R sits)."""
    out: List[RawLevel] = []
    d1 = [c for c in (candles_1d or []) if c[0] + DAY_MS <= now_ms]
    w1 = [c for c in (candles_1w or []) if c[0] + WEEK_MS <= now_ms]
    if len(d1) >= 7:
        out += swings(d1[-250:], 3, 'swing_1d', '1d')
    if len(w1) >= 5:
        out += swings(w1[-104:], 2, 'swing_1w', '1w')
    if d1:
        import datetime as _dt
        now = _dt.datetime.fromtimestamp(now_ms / 1000, _dt.timezone.utc)
        m0 = int(_dt.datetime(now.year, now.month, 1, tzinfo=_dt.timezone.utc).timestamp() * 1000)
        pm = _dt.datetime(now.year - (now.month == 1), (now.month - 2) % 12 + 1, 1, tzinfo=_dt.timezone.utc)
        p0 = int(pm.timestamp() * 1000)
        prev = [c for c in d1 if p0 <= c[0] < m0]
        if prev:
            hi, lo = max(prev, key=lambda c: c[2]), min(prev, key=lambda c: c[3])
            out.append(RawLevel(hi[2], 'pmhl', 'PMH', +1, body=max(hi[1], hi[4])))
            out.append(RawLevel(lo[3], 'pmhl', 'PML', -1, body=min(lo[1], lo[4])))
        cur = [c for c in d1 if c[0] >= m0]
        for level in out[-2:] if prev else []:
            mark_swept(level, cur)          # eng-147: traded through this month = no pool / liquidity any more
        if cur:
            out.append(RawLevel(cur[0][1], 'open', 'month open'))
        year = d1[-365:]
        if len(year) >= 200:
            hi, lo = max(year, key=lambda c: c[2]), min(year, key=lambda c: c[3])
            # a contract younger than a year (XAU since 12.2025, CL since 04.2026) has its listing's extremes, not
            # 52-week ones: named honestly (eng-74)
            tag = '52w' if len(d1) >= 365 else f"{len(year)}d"
            out.append(RawLevel(hi[2], 'year', f'{tag} high', +1, body=max(hi[1], hi[4])))
            out.append(RawLevel(lo[3], 'year', f'{tag} low', -1, body=min(lo[1], lo[4])))
    return out


def day_levels(candles_1h: Sequence[Sequence[float]], now_ms: float, with_ts: bool = False,
               candles_1d: Optional[Sequence[Sequence[float]]] = None) -> List:
    """
    Previous UTC day's and week's high / low, the current day's high / low (>= 3 candles) and the last completed
    sessions' highs / lows, from 1h candles. with_ts: also the time each level was complete [(RawLevel, formed ms)].
    """
    today = int(now_ms) // DAY_MS * DAY_MS
    week = (int(now_ms) - WEEK_OFFSET_MS) // WEEK_MS * WEEK_MS + WEEK_OFFSET_MS
    out: List[Tuple[RawLevel, int]] = []

    def span(candles, label_hi, label_lo, formed):
        if candles:
            hi = max(candles, key=lambda c: c[2])
            lo = min(candles, key=lambda c: c[3])
            out.append((RawLevel(hi[2], 'pdhl', label_hi, +1, body=max(hi[1], hi[4])),
                        formed if formed else int(hi[0]) + HOUR_MS))
            out.append((RawLevel(lo[3], 'pdhl', label_lo, -1, body=min(lo[1], lo[4])),
                        formed if formed else int(lo[0]) + HOUR_MS))

    # a period the 1h history does not cover in full takes its extremes from the daily candles (eng-74: 200 1h
    # candles hold ~8 days, the previous week needs up to 14 - ETH's PWL read 2 645 where it was 2 634)
    first = candles_1h[0][0] if len(candles_1h) else None
    for start, end, hi_lb, lo_lb in ((today - DAY_MS, today, 'PDH', 'PDL'), (week - WEEK_MS, week, 'PWH', 'PWL')):
        if first is not None and first <= start:
            span([c for c in candles_1h if start <= c[0] < end], hi_lb, lo_lb, end)
        elif candles_1d:
            days = [c for c in candles_1d if start <= c[0] < end]
            if len(days) * DAY_MS >= end - start:
                # the body of the extreme day, as the 1h path (a wick-to-body zone, not a line)
                top, bot = max(days, key=lambda c: c[2]), min(days, key=lambda c: c[3])
                out.append((RawLevel(top[2], 'pdhl', hi_lb, +1, body=max(top[1], top[4])), end))
                out.append((RawLevel(bot[3], 'pdhl', lo_lb, -1, body=min(bot[1], bot[4])), end))
    cur = [c for c in candles_1h if c[0] >= today]
    if len(cur) >= 3:
        span(cur, 'day high', 'day low', 0)
    for name, start, end in session_windows(now_ms):
        span([c for c in candles_1h if start <= c[0] < end], f"{name} high", f"{name} low", end)
    # eng-147: a previous day / week extreme the price has already traded through since (a wick is enough: its
    # stops are gone) is still drawn, but it is no pool to hide a stop behind and no liquidity to target
    pierces: List[Tuple[RawLevel, int]] = []
    for level, formed in out:
        since = {'PDH': today, 'PDL': today, 'PWH': week, 'PWL': week}.get(level.label)
        if since is not None:
            after = [c for c in candles_1h if c[0] >= since]
            mark_swept(level, after)
            # eng-150 (plan 4.5): a pierce without a 1h close beyond = a false break; its extreme is the new pool
            if level.swept and after:
                closes = [c[4] for c in after]
                # formed when the pierce candle closed (the pool age check of the sweep detector)
                if level.side > 0 and max(closes) <= level.price:
                    top = max(after, key=lambda c: c[2])
                    pierces.append((RawLevel(top[2], 'pdhl', f"{level.label} (pierce)", +1), int(top[0]) + HOUR_MS))
                elif level.side < 0 and min(closes) >= level.price:
                    bot = min(after, key=lambda c: c[3])
                    pierces.append((RawLevel(bot[3], 'pdhl', f"{level.label} (pierce)", -1), int(bot[0]) + HOUR_MS))
    out += pierces
    return out if with_ts else [level for level, _ in out]


def mark_swept(level: 'RawLevel', candles: Sequence[Sequence[float]]) -> None:
    """eng-147: flags `level` swept when any of `candles` wicked beyond it on its side."""
    if level.side > 0 and any(c[2] > level.price for c in candles) or \
            level.side < 0 and any(c[3] < level.price for c in candles):
        level.swept = True


def swept_zone(z: 'Zone', kinds) -> bool:
    """eng-147: every part of `z` of one of `kinds` was swept (a zone with no such parts is not)."""
    own = [p for p in z.parts if p[0] in kinds]
    return bool(own) and all(p[4] for p in own)


def volume_profile(candles: Sequence[Sequence[float]], atr: float, tag: str) -> List[RawLevel]:
    """
    Volume profile of [ts, o, h, l, c, quote_vol, ...] candles, each candle's quote volume spread evenly over its
    range (no tick data), so the candles must be short relative to the window: the 24h profile of 15m candles matched
    one built from 1m candles within one bucket, while 1h candles put a 4-day POC 3% off (the 4-day profile uses 5m).
    - POC: the bucket with the most volume;
    - value area (CBOT method): from the POC, repeatedly add the two buckets above or the two below, whichever pair
      holds more volume, until `value_area` of the volume is inside; VAH / VAL = the area's outer edges;
    - HVN: peaks of the 3-bucket smoothed profile (the highest within +-2 buckets) with >= hvn_ratio x the median;
    - LVN: valleys of it (the lowest within +-2 buckets) at <= lvn_ratio x the lower of the nodes on both sides
      (the highest on each side, each >= the median).
    """
    cfg = CONFIG.zones
    if len(candles) < 10 or not atr:
        return []
    step = atr / cfg.profile_buckets_per_atr
    lo = min(c[3] for c in candles)
    hi = max(c[2] for c in candles)
    n = int((hi - lo) / step) + 1
    if n < 5 or n > 5000:
        return []
    vol = [0.0] * n
    for c in candles:
        a, b = int((c[3] - lo) / step), int((c[2] - lo) / step)
        share = c[5] / (b - a + 1)
        for k in range(a, b + 1):
            vol[k] += share
    total = sum(vol)
    if not total:
        return []
    center = lambda k: lo + (k + 0.5) * step  # noqa: E731
    poc = max(range(n), key=vol.__getitem__)
    out = [RawLevel(center(poc), 'poc', f"POC {tag}")]

    a = b = poc
    inside = vol[poc]
    while inside < cfg.value_area * total and (a > 0 or b < n - 1):
        up = sum(vol[b + 1:b + 3]) if b < n - 1 else -1.0
        down = sum(vol[max(0, a - 2):a]) if a > 0 else -1.0
        if up >= down:
            step_up = min(2, n - 1 - b)
            inside += sum(vol[b + 1:b + 1 + step_up])
            b += step_up
        else:
            step_down = min(2, a)
            inside += sum(vol[a - step_down:a])
            a -= step_down
    out += [RawLevel(lo + (b + 1) * step, 'va', f"VAH {tag}", +1), RawLevel(lo + a * step, 'va', f"VAL {tag}", -1)]

    smooth = [sum(vol[max(0, k - 1):k + 2]) / len(vol[max(0, k - 1):k + 2]) for k in range(n)]
    positive = sorted(v for v in smooth if v > 0)
    median = positive[len(positive) // 2] if positive else 0.0
    nodes = [k for k in range(n)
             if smooth[k] >= cfg.hvn_ratio * median and abs(k - poc) > 2
             and smooth[k] == max(smooth[max(0, k - 2):k + 3])]
    for k in sorted(nodes, key=smooth.__getitem__, reverse=True)[:4]:
        out.append(RawLevel(center(k), 'hvn', f"HVN {tag}"))
    # LVN (Dalton / volume-profile practice): a valley between two volume nodes - price spent little time there, so it
    # passes through it fast and a rejection there returns it to the node it came from; a target / edge, not support
    # running maxima from each side: max(smooth[:k]) per bucket was quadratic (profiles go up to 5000 buckets)
    pre, suf = [0.0] * (n + 1), [0.0] * (n + 1)
    for k in range(n):
        pre[k + 1] = max(pre[k], smooth[k])
    for k in range(n - 1, -1, -1):
        suf[k] = max(suf[k + 1], smooth[k])

    def valley(k: int) -> bool:
        left, right = pre[k], suf[k + 1]
        return smooth[k] == min(smooth[k - 2:k + 3]) and min(left, right) >= median and             smooth[k] <= cfg.lvn_ratio * min(left, right)
    lvns = [k for k in range(2, n - 2) if valley(k)]
    for k in sorted(lvns, key=smooth.__getitem__)[:4]:
        out.append(RawLevel(center(k), 'lvn', f"LVN {tag}"))
    return out


def estimated_liquidations(candles_1h: Sequence[Sequence[float]], oi_1h: Sequence[Tuple[int, float]],
                           atr: float, symbol: Optional[str] = None) -> List[RawLevel]:
    """
    Estimated liquidation clusters from 1h OI changes (see the module docstring). `oi_1h` is OI in COINS (contracts x
    contract size): OI in USD rises with the price alone and read every rally as new positions. Clusters are kept in
    coins; the sizes returned are USD at the last close.
    """
    cfg = CONFIG.zones
    if len(candles_1h) < 10 or len(oi_1h) < 10 or not atr:
        return []
    # openInterestHist timestamps are period END times: OI at the close of the candle opened one hour earlier
    oi_at = {ts - HOUR_MS: v for ts, v in oi_1h}
    # the leverage mix of real positions, without the tiers this contract does not allow; its own maintenance margin
    mmr, max_lev = maintenance_of(symbol)
    mix = [(lev, w) for lev, w in leverage_mix() if max_lev is None or lev <= max_lev] or leverage_mix()[:1]
    levs, weights = [m[0] for m in mix], [m[1] for m in mix]
    step = max(atr / 2, candles_1h[-1][4] * cfg.liq_bucket)
    clusters: Dict[Tuple[int, int], float] = {}   # (bucket, side liquidated: +1 longs, -1 shorts) -> USD
    prev_oi = None
    for c in candles_1h:
        oi = oi_at.get(c[0])
        if oi is None:
            continue
        # Positions whose liquidation price this candle traded through are gone
        for key in [k for k in clusters if (k[1] > 0 and c[3] <= (k[0] + 1) * step) or (k[1] < 0 and c[2] >= k[0] * step)]:
            del clusters[key]
        if prev_oi:
            change = oi - prev_oi
            if change > 0:
                p = (c[2] + c[3] + c[4]) / 3
                buy_share = min(1.0, max(0.0, c[6] / c[5])) if c[5] else 0.5
                tiers = len(levs)
                for side, aggression in ((+1, buy_share), (-1, 1 - buy_share)):
                    # Tilt the leverage mix: an aggressive side (share > 0.5) weighs the high tiers more
                    tilt = [w * (1 + (aggression - 0.5) * (2 * i / (tiers - 1) - 1)) if tiers > 1 else w
                            for i, w in enumerate(weights)]
                    norm = sum(tilt) or 1.0
                    for lev, w in zip(levs, tilt, strict=True):
                        liq = p * (1 - side * (1 / lev - mmr))
                        key = (int(liq / step), side)
                        clusters[key] = clusters.get(key, 0.0) + change * w / norm
            elif change < 0 and prev_oi > 0:
                keep = max(0.0, oi / prev_oi)
                for key in clusters:
                    clusters[key] *= keep
        prev_oi = oi
    if not prev_oi:
        return []
    floor = cfg.liq_min_oi_share * prev_oi
    last_price = candles_1h[-1][4]
    out = []
    ranked = sorted(clusters.items(), key=lambda kv: -kv[1])
    for (bucket, side), coins in [kv for kv in ranked if kv[0][1] > 0][:cfg.liq_max_per_side] + \
            [kv for kv in ranked if kv[0][1] < 0][:cfg.liq_max_per_side]:
        if coins >= floor:
            usd = coins * last_price
            who = 'longs' if side > 0 else 'shorts'
            out.append(RawLevel((bucket + 0.5) * step, 'liq_est', f"liq est {who} {_usd(usd)}", -side, usd))
    return out


BANKRUPTCY_PRICE_VENUES = ('bybit', 'okx')


def observed_liquidations(events: Iterable[Tuple[float, float, float, int]], atr: float, now_ms: float) -> List[RawLevel]:
    """Price buckets where >= liq_observed_min_usd was actually liquidated in the last 24h."""
    if not atr:
        return []
    step = atr / 2
    buckets: Dict[int, float] = {}
    bankr: Dict[int, float] = {}
    for event in events:
        ts, price, usd = event[0], event[1], event[2]
        if now_ms - ts <= DAY_MS and price:
            k = int(price / step)
            buckets[k] = buckets.get(k, 0.0) + usd
            if len(event) > 4 and event[4] in BANKRUPTCY_PRICE_VENUES:
                bankr[k] = bankr.get(k, 0.0) + usd
    # audit E02: Bybit (and OKX) report the BANKRUPTCY price of a liquidated position, not where the order traded: a
    # bucket made mostly of those events is labelled so (the level is where positions went bankrupt, not a fill)
    return [RawLevel((k + 0.5) * step, 'liq_hit', f"liq {_usd(usd)}" + (" (bankruptcy px)" if bankr.get(k, 0.0) > usd / 2 else ""),
                     0, usd)
            for k, usd in buckets.items() if usd >= CONFIG.zones.liq_observed_min_usd]


def vwap(candles: Sequence[Sequence[float]], since_ms: int, label: str) -> List[RawLevel]:
    """VWAP of [ts, o, h, l, c, quote_vol, taker, base_vol] candles opened at or after since_ms: sum(quote) /
    sum(base) - exact (every trade's price x quantity over the quantity; audit S01 / C02: quote-weighted typical
    prices weighted price twice). The base volume is the exchange's own (Binance's kline volume, the 8th field); a
    candle without it (None / NaN / older 7-column rows) falls back to quote / HLC3 - an approximation (one bar of
    trades at 100 and 200 reads 166.67, not 150), kept from the live branch so a coin without base volume keeps its
    VWAP level."""
    num = den = 0.0
    for c in candles:
        if c[0] >= since_ms and c[5]:
            base = c[7] if len(c) > 7 and c[7] is not None and c[7] == c[7] and c[7] > 0 else None
            if base is None:
                typical = (c[2] + c[3] + c[4]) / 3
                base = c[5] / typical if typical > 0 else None
            if base:
                num += c[5]
                den += base
    return [RawLevel(num / den, 'vwap', label)] if den else []


def _usd(v: float) -> str:
    return f"${v / 1e6:.1f}M" if v >= 1e6 else f"${v / 1e3:.0f}k"


# ---------------------------------------------------------------------------------------------------- ICT / SMC

def imbalances(candles: Sequence[Sequence[float]], tf: str, keep: int = 4) -> List[RawLevel]:
    """
    ICT's fair value gaps and order blocks still open on `candles` ([ts, o, h, l, c, ...]):
    - FVG (kind 'fvg'): three candles where the first's high < the third's low (bullish; mirrored bearish): the gap
      between them is the zone; the part price has not traded back through since is kept, a fully filled gap dropped;
    - order block (kind 'ob'): the last opposite candle before a displacement that broke structure - a down-close
      candle whose next three candles close above the last CONFIRMED swing high (ICT's 3-candle swing, confirmed by
      the block's candle: his break of structure is a swing, eng-57; was the highest high of the ten candles before)
      while leaving a bullish FVG (bearish mirrored); the zone runs from its body (open) to its wick (low); mitigated
      (traded back into) = dropped.
    - breaker (kind 'breaker'): an order block that FAILED - price later closed through its far side - flips: a broken
      bullish OB is resistance (ICT's breaker block), mirrored.
    Kinds carry the timeframe ('fvg_4h', 'ob_1d', 'breaker_1h'): a daily order block outweighs a 15m one
    (CONFIG.zones.weights). The `keep` nearest of each kind and side to the last close.
    """
    n = len(candles)
    if n < 15:
        return []
    o = [c[1] for c in candles]
    h = [c[2] for c in candles]
    l = [c[3] for c in candles]
    cl = [c[4] for c in candles]
    out: List[Tuple[float, RawLevel]] = []
    last = cl[-1]
    # audit D06: a candle step from the data itself (the usual spacing); a gap of missing candles inside the three is
    # no imbalance (the third candle's low sits hours after the first's high)
    diffs = sorted(candles[k][0] - candles[k - 1][0] for k in range(1, n))
    step = diffs[len(diffs) // 2]
    for i in range(2, n):
        if step > 0 and candles[i][0] - candles[i - 2][0] != 2 * step:
            continue
        # a gap under a tenth of its displacement candle is noise, not an imbalance (the usual "significant FVG" cut)
        min_gap = 0.1 * (h[i - 1] - l[i - 1])
        if h[i - 2] < l[i] and l[i] - h[i - 2] >= min_gap:
            lo, hi = h[i - 2], l[i]
            low_after = min(l[i + 1:], default=hi)
            if low_after > lo:
                hi = min(hi, low_after)
                out.append((abs(last - hi), RawLevel(hi, f'fvg_{tf}', f"FVG {tf} bull", -1, ts=int(candles[i - 1][0]),
                                                     body=lo)))
        elif l[i - 2] > h[i] and l[i - 2] - h[i] >= min_gap:
            lo, hi = h[i], l[i - 2]
            high_after = max(h[i + 1:], default=lo)
            if high_after < hi:
                lo = max(lo, high_after)
                out.append((abs(last - lo), RawLevel(lo, f'fvg_{tf}', f"FVG {tf} bear", +1, ts=int(candles[i - 1][0]),
                                                     body=hi)))
    # the last confirmed ICT swing high / low at each candle: the 3-candle formation (the middle candle's high above
    # both neighbours'), confirmed once its right neighbour closed
    last_hi, last_lo = [None] * n, [None] * n
    hi_p = lo_p = None
    for j in range(n):
        k = j - 1
        if k >= 1:
            if h[k] > max(h[k - 1], h[k + 1]):
                hi_p = h[k]
            if l[k] < min(l[k - 1], l[k + 1]):
                lo_p = l[k]
        last_hi[j], last_lo[j] = hi_p, lo_p
    for j in range(10, n - 3):
        nxt = range(j + 1, j + 4)
        if cl[j] < o[j]:
            broke = last_hi[j] is not None and any(cl[k] > last_hi[j] for k in nxt)
            gap = any(h[k - 2] < l[k] for k in range(j + 2, j + 4))
            mitigated = min(l[j + 4:], default=h[j]) <= o[j]
            if broke and gap and not mitigated:
                out.append((abs(last - o[j]), RawLevel(l[j], f'ob_{tf}', f"OB {tf} bull", -1, ts=int(candles[j][0]),
                                                       body=o[j])))
            elif broke and gap and any(x < l[j] for x in cl[j + 4:]):
                # closed below the bullish OB's low: a breaker, resistance from below
                out.append((abs(last - o[j]), RawLevel(o[j], f'breaker_{tf}', f"breaker {tf} bear", +1,
                                                       ts=int(candles[j][0]), body=l[j])))
        elif cl[j] > o[j]:
            broke = last_lo[j] is not None and any(cl[k] < last_lo[j] for k in nxt)
            gap = any(l[k - 2] > h[k] for k in range(j + 2, j + 4))
            mitigated = max(h[j + 4:], default=l[j]) >= o[j]
            if broke and gap and not mitigated:
                out.append((abs(last - o[j]), RawLevel(h[j], f'ob_{tf}', f"OB {tf} bear", +1, ts=int(candles[j][0]),
                                                       body=o[j])))
            elif broke and gap and any(x > h[j] for x in cl[j + 4:]):
                out.append((abs(last - o[j]), RawLevel(o[j], f'breaker_{tf}', f"breaker {tf} bull", -1,
                                                       ts=int(candles[j][0]), body=h[j])))
    picked: List[RawLevel] = []
    for kind in (f'fvg_{tf}', f'ob_{tf}', f'breaker_{tf}'):
        for side in (1, -1):
            group = sorted((x for x in out if x[1].kind == kind and x[1].side == side), key=lambda x: x[0])
            picked += [lv for _, lv in group[:keep]]
    return picked


def balanced_ranges(candles: Sequence[Sequence[float]], tf: str, keep: int = 2) -> List[RawLevel]:
    """
    ICT's balanced price range: a bearish FVG and a later bullish one (or the reverse) within 20 candles whose ranges
    overlap - price was delivered both ways through the same area, the overlap is a strong reaction zone. Kept while
    no later close went through it; the side by the later gap (a bullish one: support). Kind 'bpr_<tf>'.
    """
    n = len(candles)
    if n < 10:
        return []
    h = [c[2] for c in candles]
    l = [c[3] for c in candles]
    cl = [c[4] for c in candles]
    gaps = []
    for i in range(2, n):
        if h[i - 2] < l[i]:
            gaps.append((i, 1, h[i - 2], l[i]))
        elif l[i - 2] > h[i]:
            gaps.append((i, -1, h[i], l[i - 2]))
    out: List[Tuple[float, RawLevel]] = []
    last = cl[-1]
    for a in gaps:
        for b in gaps:
            if not (0 < b[0] - a[0] <= 20) or a[1] == b[1]:
                continue
            lo, hi = max(a[2], b[2]), min(a[3], b[3])
            if lo >= hi:
                continue
            side = b[1]
            if any((x < lo) if side > 0 else (x > hi) for x in cl[b[0] + 1:]):
                continue
            edge = hi if side > 0 else lo
            out.append((abs(last - edge), RawLevel(edge, f'bpr_{tf}', f"BPR {tf}", -side,
                                                   ts=int(candles[b[0] - 1][0]), body=lo if side > 0 else hi)))
    out.sort(key=lambda x: x[0])
    return [lv for _, lv in out[:keep]]


def bars_of(candles_1h: Sequence[Sequence[float]], hours: int) -> List[List[float]]:
    """1h candles -> complete `hours` candles aligned to UTC multiples."""
    size = hours * HOUR_MS
    groups: Dict[int, List] = {}
    for c in candles_1h:
        groups.setdefault(int(c[0]) // size * size, []).append(c)
    out = []
    for start in sorted(groups):
        g = sorted(groups[start], key=lambda c: c[0])
        # audit F05: every hour of the bucket exactly once (a count of 4 accepted 00 / 00 / 02 / 03)
        if [int(c[0]) for c in g] == [start + i * HOUR_MS for i in range(hours)]:
            out.append([start, g[0][1], max(c[2] for c in g), min(c[3] for c in g), g[-1][4], sum(c[5] for c in g)])
    return out


def day_poc(candles: Sequence[Sequence[float]], today_ms: int) -> List[Tuple[int, float]]:
    """[(day_ms, POC)] of each completed UTC day the 5m candles fully cover (Dalton's daily profile, volume at price:
    short candles - 1h ones put a POC percents off). The bucket = the candles' mean range x sqrt(3) (~a 15m ATR) /
    profile_buckets_per_atr, as the map's other profiles."""
    if len(candles) < 2:
        return []
    step_ms = candles[1][0] - candles[0][0]
    if step_ms > 5 * 60_000:
        return []
    days: Dict[int, List] = {}
    for c in candles:
        day = int(c[0]) // DAY_MS * DAY_MS
        if day < today_ms:
            days.setdefault(day, []).append(c)
    out = []
    for day, part in sorted(days.items()):
        if len(part) < 0.9 * DAY_MS / step_ms:          # a day the window only partly covers
            continue
        atr = math.sqrt(3) * sum(c[2] - c[3] for c in part) / len(part)
        profile = volume_profile(part, atr, '')
        if profile:
            # (day, POC, VAH, VAL): eng-74 - Dalton reads the PREVIOUS day's value area (the map held only the rolling
            # 24h and 4-day profiles)
            vah = next((l.price for l in profile if l.kind == 'va' and l.side > 0), None)
            val = next((l.price for l in profile if l.kind == 'va' and l.side < 0), None)
            out.append((day, profile[0].price, vah, val))
    return out


def naked_daily_pocs(day_pocs: Sequence[Tuple[int, float]], candles: Sequence[Sequence[float]]) -> List[RawLevel]:
    """The completed days' POCs no candle after that day has traded through (`candles`: 1h, 8 days - a touch needs
    only the range): naked / virgin POCs (Dalton), an untested value reference. Kind 'poc' like the composites."""
    out = []
    for row in day_pocs:
        day, poc = row[0], row[1]
        end = day + DAY_MS
        if not any(c[0] >= end and c[3] <= poc <= c[2] for c in candles):
            out.append(RawLevel(poc, 'poc', f"naked POC {time.strftime('%m-%d', time.gmtime(day / 1000))}", ts=day))
    # the previous completed day's POC / VAH / VAL (Dalton: yesterday's value area is the day's reference - an open
    # outside it, the 80% rule, VAH resistance / VAL support from outside)
    if day_pocs:
        last = max(day_pocs, key=lambda r: r[0])
        out.append(RawLevel(last[1], 'poc', 'POC PD', ts=last[0]))
        if len(last) >= 4 and last[2] is not None and last[3] is not None:
            out.append(RawLevel(last[2], 'va', 'VAH PD', +1, ts=last[0]))
            out.append(RawLevel(last[3], 'va', 'VAL PD', -1, ts=last[0]))
    return out


# ---------------------------------------------------------------------------------------------------- map

def build_raw(candles_15m: Sequence[Sequence[float]], candles_1h: Sequence[Sequence[float]],
              oi_1h: Sequence[Tuple[int, float]], liq_events: Iterable, atr: float, now_ms: float,
              candles_4d: Optional[Sequence[Sequence[float]]] = None,
              candles_1d: Optional[Sequence[Sequence[float]]] = None,
              candles_4h: Optional[Sequence[Sequence[float]]] = None,
              candles_1w: Optional[Sequence[Sequence[float]]] = None, symbol: Optional[str] = None,
              day_pocs: Optional[Sequence[Tuple[int, float]]] = None) -> List[RawLevel]:
    """
    Card-independent levels of one coin (cached by the scanner; rebuilt on a new candle / new 1h history).
    `candles_4d`: 4 days of 5m candles for the 4-day volume profile (1h candles are too coarse for it).
    """
    cfg = CONFIG.zones
    s15 = swings(candles_15m, cfg.swing_width_15m, 'swing_15m', '15m')
    s1h = swings(candles_1h, cfg.swing_width_1h, 'swing_1h', '1h')
    today = int(now_ms) // DAY_MS * DAY_MS
    levels = s15 + s1h
    levels += equal_pools(s15 + s1h, candles_15m, atr, symbol, history=candles_1h)
    levels += htf_swings(candles_1d, candles_1w, now_ms)
    levels += day_levels(candles_1h, now_ms, candles_1d=candles_1d)
    levels += volume_profile(candles_4d or candles_1h, atr, '4d')
    levels += volume_profile(candles_15m, atr, '24h')
    levels += naked_daily_pocs(day_pocs or (), candles_1h)
    levels += estimated_liquidations(candles_1h, oi_1h, atr, symbol)
    levels += observed_liquidations(liq_events, atr, now_ms)
    levels += vwap(candles_15m, today, 'VWAP day')
    # ICT / SMC zones of every timeframe the bot holds: 15m (last day), 1h (8 days), 4h (from the 1h candles) and the
    # daily (60 days): open FVGs, unmitigated order blocks, breakers - weighted by their timeframe
    levels += imbalances(list(candles_15m)[-96:], '15m') + imbalances(list(candles_1h)[-192:], '1h')
    # 4h from its own candles (200 = ~33 days; the 1h map's 8 days gave ~50) - else built from the 1h candles
    levels += imbalances(list(candles_4h)[-120:] if candles_4h else bars_of(candles_1h, 4), '4h')
    levels += balanced_ranges(list(candles_1h)[-192:], '1h')
    if candles_4h:
        levels += balanced_ranges(list(candles_4h)[-120:], '4h')
    if candles_1d:
        levels += imbalances(list(candles_1d)[-60:], '1d')
    if candles_1w:
        levels += imbalances(list(candles_1w)[-52:], '1w')
    # ICT's opening prices: the day's and the week's open (the true day / week open: price above it = the premium of
    # that period)
    if candles_1d:
        # the open of the candle that opened AT 00:00 UTC (as the week's open, eng-74): the first 15m candle held after
        # midnight was taken - after a restart it could be a later one (INJ 2026-10-12: 'day open' 7.8028 for 7.758,
        # beside the ORB's own correct 7.758)
        day_open = int(now_ms) // DAY_MS * DAY_MS
        at = next((c for src in (candles_15m, candles_1h) for c in (src or []) if int(c[0]) == day_open), None)
        if at is not None:
            levels.append(RawLevel(at[1], 'open', 'day open'))
    # the week's open = the open of the candle that opened AT the week's start (eng-74: the first 15m candle held -
    # the 15m history is shorter than a week - was taken: ETH's 'week open' 2 690 where it was 2 725.71)
    week_start = (int(now_ms) - WEEK_OFFSET_MS) // WEEK_MS * WEEK_MS + WEEK_OFFSET_MS
    at = next((c for src in (candles_15m, candles_1h, candles_1d) for c in (src or []) if int(c[0]) == week_start), None)
    if at is not None:
        levels.append(RawLevel(at[1], 'open', 'week open'))
    if candles_15m:
        last = candles_15m[-1][4]
        levels += [RawLevel(p, 'round', f"round {p:g}", +1 if p > last else -1)
                   for p in round_levels(last, cfg.round_span_atr * atr)]
    return levels


def _span(l: RawLevel) -> Tuple[float, float]:
    b = l.body if l.body is not None else l.price
    return min(b, l.price), max(b, l.price)


def merge(levels: Iterable[RawLevel], atr: float, symbol: Optional[str] = None) -> List[Zone]:
    """
    Levels whose body-to-wick spans overlap - or lie closer than the typical pierce of their kind (p50, pierce.py:
    price treats them as one place) - become one zone spanning all of them (classic S/R zones: the region where
    price fought, body to wick; was: points within 0.3 ATR). Without the pierce model the old ATR tolerance applies.
    Strength = sum of source weights over distinct price events (eng-169e: one extreme in several kinds counts once, at
    its largest weight); one kind counted <= 2x.
    """
    from pierce import measured_kind, model, overshoot
    weights = _weights()
    measured = bool(model())
    tol = CONFIG.zones.merge_atr * atr
    zones: List[Zone] = []
    group: List[RawLevel] = []

    def close_group():
        if not group:
            return
        # eng-169e (audit S5): one price extreme seen as several kinds (a 15m swing, the 1h swing, the EQL edge, the day's
        # low - the same tick, the same side) is ONE event: it adds the largest of its weights once, not their sum (one
        # low read 4.0 > min_strength alone). Distinct prices / sides stay separate; a kind still counts <= 2x.
        # per (side, price) event: each kind's own touches (<= 2x its weight), the event keeps its strongest kind only
        events: Dict[Tuple[int, float], Dict[str, float]] = {}
        for l in group:
            w = weights.get(l.kind, 0.5)
            ev = events.setdefault((l.side, round(l.price, 12)), {})
            ev[l.kind] = min(ev.get(l.kind, 0.0) + w, 2 * w)
        per_kind: Dict[str, float] = {}
        for ev in events.values():
            kind = max(ev, key=lambda k: ev[k])
            w = weights.get(kind, 0.5)
            per_kind[kind] = min(per_kind.get(kind, 0.0) + ev[kind], 2 * w)
        for l in group:
            per_kind.setdefault(l.kind, 0.0)          # the zone still lists every kind it holds (labels, roles)
        strength = sum(per_kind.values())
        wsum = sum(weights.get(l.kind, 0.5) for l in group)
        price = sum(l.price * weights.get(l.kind, 0.5) for l in group) / wsum
        ordered = sorted(group, key=lambda l: -weights.get(l.kind, 0.5))
        labels: List[str] = []
        for l in ordered:
            if l.label not in labels:
                labels.append(l.label)
        zones.append(Zone(price, min(_span(l)[0] for l in group), max(_span(l)[1] for l in group),
                          sorted(per_kind, key=lambda k: -per_kind[k]), labels, strength,
                          min((int(l.ts) for l in group if l.ts), default=0),
                          [(l.kind, l.price, *_span(l), l.swept) for l in group]))

    group_hi = float('-inf')
    max_w = CONFIG.zones.max_merge_atr * atr if atr and atr > 0 else float('inf')
    levels = list(levels)
    wide = [l for l in levels if _span(l)[1] - _span(l)[0] > max_w]
    for l in wide:
        # eng-74: a level wider than a zone may be stays its own zone and absorbs nothing
        group = [l]
        close_group()
    group = []
    group_lo = float('inf')
    for l in sorted((l for l in levels if not any(l is w for w in wide)), key=lambda l: _span(l)[0]):
        lo, hi = _span(l)
        if measured:
            gap = overshoot(symbol, measured_kind([l.kind]) or 'swing_15m', l.price, 'p50') or 0.0
        else:
            gap = tol
        # measured from the zone's FIRST level, not its growing edge: chaining A-B-C merged levels far apart into one
        # zone covering half the chart (live eng-27: ETH's PWL + EQL + PDL + estimates 3%+ wide)
        top = max([hi] + [_span(x)[1] for x in group])
        inside = bool(group) and lo <= max(_span(x)[1] for x in group)     # overlaps a level already in the zone
        if group and ((lo - group_hi > gap and not inside) or top - group_lo > max_w):
            close_group()
            group, group_hi = [], float('-inf')
        if not group:
            group_hi, group_lo = hi, lo
        group.append(l)
    close_group()
    zones.sort(key=lambda z: z.lo)
    return zones


def is_pool(zone: Zone) -> bool:
    return any(k in POOL_KINDS for k in zone.kinds)


def is_structural(zone: Zone) -> bool:
    return any(k in STRUCTURE_KINDS for k in zone.kinds)


def targets(zones: List[Zone], entry: float, direction: int, atr: float) -> List[Tuple[float, str]]:
    """
    Up to three targets beyond `entry`: TP1 / TP2 = the first zones strong enough to stall price (min_strength),
    TP3 = the next liquidity pool / liquidation cluster beyond TP2 (else the next strong zone). A target is the zone's
    near edge (price reaches it first). Returns [(price, label)].
    """
    cfg = CONFIG.zones
    ahead = [z for z in zones if direction * (z.price - entry) >= cfg.min_target_atr * atr]
    ahead.sort(key=lambda z: direction * (z.price - entry))
    strong = [z for z in ahead if z.strength >= cfg.min_strength]
    near = lambda z: z.lo if direction > 0 else z.hi  # noqa: E731
    out: List[Tuple[float, str]] = []
    for z in strong:
        if len(out) == 2:
            break
        if not out or direction * (near(z) - out[-1][0]) >= cfg.min_target_atr * atr:
            out.append((near(z), z.label))
    if len(out) == 2:
        # TP3: the next resting-stop / liquidation pool beyond TP2 (such pools attract price even when they are not
        # an obstacle), else the next strong zone
        beyond = [z for z in ahead if direction * (near(z) - out[-1][0]) >= cfg.min_target_atr * atr]
        pools = [z for z in beyond if is_pool(z)]
        strong_beyond = [z for z in beyond if z.strength >= cfg.min_strength]
        pick = pools[0] if pools else (strong_beyond[0] if strong_beyond else None)
        if pick is not None:
            out.append((near(pick), pick.label))
    return out


# eng-84: resting stops also sit beyond swings of 1h and higher (the obvious '1h low'): a stop pushed beyond a
# pool considers them too (targets keep POOL_KINDS)
STOP_SWINGS = ('swing_1h', 'swing_1d', 'swing_1w')


def _pick_pool(zones: List[Zone], direction: int, farthest: bool) -> Zone:
    if farthest:
        return min(zones, key=lambda z: z.lo) if direction > 0 else max(zones, key=lambda z: z.hi)
    return max(zones, key=lambda z: z.lo) if direction > 0 else min(zones, key=lambda z: z.hi)


def liq_only(z: Zone) -> bool:
    """eng-150 (plan 4.6): a zone made of estimated liquidations only - confluence, never a target / anchor."""
    return bool(z.kinds) and all(k == 'liq_est' for k in z.kinds)


def stop_beyond(zones: List[Zone], invalidation: float, entry: float, direction: int, atr: float,
                label: str = 'beyond the swing', symbol: Optional[str] = None,
                farthest: bool = False) -> Tuple[float, str]:
    """
    Stop base: the invalidation price, pushed beyond a stop pool / liquidation cluster that sits just behind it
    (within stop_pool_atr ATR), so a routine sweep of that pool does not take the stop, as long as the risk stays
    within max_stop_atr ATR. Returns (base price before the ATR buffer, label).
    eng-150 (plan 4.3): the NEAREST such pool, never one beyond the next pool (farthest=True = the old rule; eng-152: live
    again for the sweep strategy, plan['stop_farthest']).
    """
    cfg = CONFIG.zones
    from pierce import measured_kind, model, overshoot
    if model():
        # measured: a pool is "just behind" when it lies within the distance price usually pierces a level of that
        # kind (p90) - a routine raid of it would take a stop placed in front of it; no ATR maximum (a stop that
        # does not pay is low_rr, not moved closer)
        near = []
        for z in zones:
            if not any(k in STOP_POOL_KINDS or k in STOP_SWINGS for k in z.kinds):
                continue
            if swept_zone(z, STOP_POOL_KINDS + STOP_SWINGS):
                continue                    # eng-147: its stops were taken already - nothing to hide behind
            edge = z.lo if direction > 0 else z.hi
            reach = overshoot(symbol, measured_kind(z.kinds) or 'equal', invalidation, 'p90')
            if reach is not None and 0 <= direction * (invalidation - edge) <= reach:
                near.append(z)
        if near:
            far = _pick_pool(near, direction, farthest)
            return (far.lo if direction > 0 else far.hi), f"beyond {far.label}"
        return invalidation, label
    # Real resting stops only: an ESTIMATED liquidation cluster is a model, not orders (live eng-6: stops pushed beyond
    # one were the widest, 3.4% median, -0.16R, and 0 of 22 stopped trades reached TP1 afterwards)
    behind = [z for z in zones if any(k in STOP_POOL_KINDS or k in STOP_SWINGS for k in z.kinds)
              and not swept_zone(z, STOP_POOL_KINDS + STOP_SWINGS)
              and 0 <= direction * (invalidation - (z.lo if direction > 0 else z.hi)) <= cfg.stop_pool_atr * atr]
    if behind:
        far = _pick_pool(behind, direction, farthest)
        base = far.lo if direction > 0 else far.hi
        if abs(entry - base) <= cfg.max_stop_atr * atr:
            return base, f"beyond {far.label}"
    return invalidation, label


def support_in(zones: List[Zone], lo: float, hi: float, direction: int) -> Optional[Zone]:
    """Strongest zone inside [lo, hi] (a pullback's support for longs / resistance for shorts)."""
    inside = [z for z in zones if lo <= z.price <= hi and z.strength >= CONFIG.zones.min_strength
              and not liq_only(z)]
    return max(inside, key=lambda z: z.strength) if inside else None
