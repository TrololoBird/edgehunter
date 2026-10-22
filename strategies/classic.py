"""
Classic published methods added as their authors define them (eng-29), on the session instruments only
(CONFIG.strategies.orb_bases: the majors, gold, silver, oil):

- value_area  Dalton's 80% rule by SESSION (eng-95; Dalton "Mind Over Markets"): the session (Asia / London / New York,
              weekdays) opens outside the previous same session's TPO value area (70% of time at price, eng-58),
              closes two consecutive 30-minute periods back inside it -> entry at the second period's close, target
              the far edge, out at the session's close (session_va_event, VA80). Beside it the failed auction
              (eng-127, failed_auction_event, AUCTION LONG / SHORT). Both run in the maps worker at 15m closes.
- orb         Toby Crabel's opening range breakout ("Playing the Opening Range Breakout", Stocks & Commodities): the
              range of a session's first 5 minutes, stop orders the Stretch (10-day SMA of min(High - Open,
              Open - Low)) beyond its high / low; the first level traded through is the entry (ON THE TOUCH, a stop
              order), the other level the stop; out at the session's close (eng-146; eng-145's 15m
              Parabolic SAR exit reverted). Checked
              loop-side on every final minute (session_orb via strategies.loopside.LoopDetectors).
- connors     Larry Connors' RSI(2) on DAILY candles, with the trend (close above / below the 200-day SMA): RSI2X = his
              original rule (a close with RSI(2) < 5, buy on the close; the mirrored short is shadow), RSI2 = the
              cross-back (eng-84: RSI(2) comes back out of the extreme, the close still beyond the SMA5). Out on the
              first daily close beyond the current SMA5. He uses no stop: the R unit is 1 daily ATR, position at 1x,
              and the executor keeps a catastrophe stop 3 R units away (eng-144, our deviation). Checked loop-side
              after each daily close (strategies.loopside.LoopDetectors._connors_daily).
"""
import math
from typing import Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo

from config import CONFIG

QUARTER_MS = 900_000
HOUR_MS = 3_600_000
DAY_MS = 86_400_000
NY = ZoneInfo('America/New_York')


# ------------------------------------------------------------------------------------------------ value area

def value_area(candles: Sequence[Sequence[float]], share: float = 0.70, buckets: int = 60, tpo: bool = False):
    """(VAL, POC, VAH) of the candles' volume spread evenly over each candle's range, else None. tpo: Market Profile's
    TPO value area (Dalton - eng-58): the candles are merged into 30-minute brackets and every price row a bracket
    visited gets ONE mark (audit C03: a wide candle's single unit was spread thinly over its rows, so a few narrow
    bars at one price made a 70% 'profile' there)."""
    if not candles:
        return None
    if tpo:
        brackets: Dict[int, list] = {}
        for c in candles:
            k = int(c[0]) // (30 * 60_000)
            b = brackets.get(k)
            brackets[k] = [c[0], c[1], c[2], c[3], c[4], 0.0] if b is None else \
                [b[0], b[1], max(b[2], c[2]), min(b[3], c[3]), c[4], 0.0]
        candles = [brackets[k] for k in sorted(brackets)]
    hi, lo = max(c[2] for c in candles), min(c[3] for c in candles)
    if hi <= lo:
        return None
    size = (hi - lo) / buckets
    vol = [0.0] * buckets
    for c in candles:
        a = min(buckets - 1, int((c[3] - lo) / size))
        b = min(buckets - 1, int((c[2] - lo) / size))
        part = 1.0 if tpo else (c[5] or 0.0) / (b - a + 1)
        for k in range(a, b + 1):
            vol[k] += part
    total = sum(vol)
    if total <= 0:
        return None
    # eng-138 (audit A06): among equal maxima the row nearest the profile's middle, then the lower of two equidistant
    # (Sierra Chart's documented rule; was the lowest row)
    top = max(vol)
    mid = (buckets - 1) / 2
    poc = min((k for k in range(buckets) if vol[k] == top), key=lambda k: (abs(k - mid), k))
    i = j = poc
    acc = vol[poc]
    while acc < share * total and (i > 0 or j < buckets - 1):
        down = vol[i - 1] if i > 0 else -1.0
        up = vol[j + 1] if j < buckets - 1 else -1.0
        if up == down and up >= 0:
            # Sierra Chart: two equal neighbouring rows enter the value area together (audit E01)
            j += 1
            i -= 1
            acc += vol[j] + vol[i]
        elif up > down:
            j += 1
            acc += vol[j]
        else:
            i -= 1
            acc += vol[i]
    return lo + i * size, lo + (poc + 0.5) * size, lo + (j + 1) * size


def _day_candles(m15: Sequence[Sequence[float]], day_start: int) -> List[Sequence[float]]:
    return [c for c in m15 if day_start <= c[0] < day_start + DAY_MS]


def _complete_quarters(rows: Sequence[Sequence[float]], start: int, cut: int) -> bool:
    """Exact closed 15m grid; an off-grid session open needs finer source data."""
    return (cut > start and start % QUARTER_MS == 0 and cut % QUARTER_MS == 0
            and [c[0] for c in rows] == list(range(start, cut, QUARTER_MS)))


def value_area_event(m15: Sequence[Sequence[float]], cut: int) -> Optional[Dict]:
    """Dalton's 80% rule at the close of a 30-minute period (`cut` = close time of the last 15m candle)."""
    if cut % (2 * QUARTER_MS) or len(m15) < 100:
        return None
    today = cut - cut % DAY_MS
    prev = _day_candles(m15, today - DAY_MS)
    day = [c for c in _day_candles(m15, today) if c[0] < cut]
    if len(prev) < 90 or len(day) < 4 or not _complete_quarters(day, today, cut):
        return None
    va = value_area(prev, tpo=True)               # Dalton's value area is TPO (time), not volume (eng-58)
    if va is None:
        return None
    val, poc, vah = va
    opened = day[0][1]
    if val <= opened <= vah:
        return None
    side = 1 if opened < val else -1            # opened below: back inside -> long to VAH; above -> short to VAL

    def inside(pair) -> bool:
        return val <= pair[-1][4] <= vah

    periods = [day[k:k + 2] for k in range(0, len(day) - 1, 2)]
    if len(periods) < 2 or not (inside(periods[-1]) and inside(periods[-2])):
        return None
    if len(periods) >= 3 and inside(periods[-3]):
        return None                               # the rule fired at the previous period already
    edge, far = (val, vah) if side > 0 else (vah, val)
    last = day[-1]
    if side * (far - last[4]) < 0.3 * (vah - val):
        return None       # eng-71: the value area is already traversed (XAU / ONDO / XPL: TP1 0.06-0.15% from the entry)
    extreme = min(c[3] for c in day) if side > 0 else max(c[2] for c in day)
    return {'setup': 'VA80 LONG' if side > 0 else 'VA80 SHORT', 'direction': side,
            'setup_note': f"opened {'below' if side > 0 else 'above'} yesterday's value area {val:.6g}-{vah:.6g} "
                          f"(POC {poc:.6g}), back inside for two 30m periods: Dalton's 80% rule -> the far edge",
            'anchor_level': edge, 'anchor_extreme': extreme, 'anchor_label': f"value area {'low' if side > 0 else 'high'}",
            'anchor_ts': today, 'anchor_close': last[4], 'va_far': far, 'va_poc': poc,
            'event_ts': int(last[0]) + QUARTER_MS}


# ------------------------------------------------------------------------------------------------ opening range

def stretch(d1: Sequence[Sequence[float]], days: int = 10) -> Optional[float]:
    """Crabel's Stretch: the SMA of the last `days` closed days' min(High - Open, Open - Low)."""
    if len(d1) < days:
        return None
    return sum(min(c[2] - c[1], c[1] - c[3]) for c in d1[-days:]) / days


def narrow_range(d1: Sequence[Sequence[float]], days: int) -> Optional[bool]:
    """Crabel's NR-n: the last closed day's range the smallest of the last n days (None without the history)."""
    if len(d1) < days:
        return None
    ranges = [c[2] - c[3] for c in d1[-days:]]
    return ranges[-1] <= min(ranges)


# ------------------------------------------------------------------------------------------------ session ORB (eng-93)

# eng-93 (the owner, 2026-10-14: ORB on the majors, gold, silver and oil, split by sessions; the entry rule is
# session_orb's docstring). Local hours (DST by zoneinfo), Monday-Friday. New York per asset class: the US equity open for crypto, COMEX's for metals (08:20 ET),
# NYMEX's for energy (09:00 ET).
ORB_SESSIONS = (('Asia', 'Asia/Tokyo', (9, 0), (15, 0)),
                ('London', 'Europe/London', (8, 0), (16, 30)),
                ('New York', 'America/New_York', (9, 30), (16, 0)))
ORB_NY_BY_CLASS = {'XAU': ((8, 20), (13, 30)), 'XAG': ((8, 20), (13, 30)),
                   'CL': ((9, 0), (14, 30)), 'BZ': ((9, 0), (14, 30))}


def orb_sessions(base: str, now_ms: int) -> List[tuple]:
    """(name, open_ms, close_ms) of the sessions running at now_ms for the coin (weekdays only)."""
    import datetime as dt
    from zoneinfo import ZoneInfo
    out = []
    now = dt.datetime.fromtimestamp(now_ms / 1000, dt.timezone.utc)
    for name, tz, start, end in ORB_SESSIONS:
        if name == 'New York' and base in ORB_NY_BY_CLASS:
            start, end = ORB_NY_BY_CLASS[base]
        local = now.astimezone(ZoneInfo(tz))
        if local.weekday() >= 5:
            continue
        o = local.replace(hour=start[0], minute=start[1], second=0, microsecond=0)
        c = local.replace(hour=end[0], minute=end[1], second=0, microsecond=0)
        if o <= local < c:
            out.append((name, int(o.timestamp() * 1000), int(c.timestamp() * 1000)))
    return out


def _session_times(base: str, name: str, tz: str, start, end):
    if name == 'New York' and base in ORB_NY_BY_CLASS:
        return ORB_NY_BY_CLASS[base]
    return start, end


def previous_session(base: str, name: str, open_ms: int) -> Optional[tuple]:
    """(open_ms, close_ms) of the same session on the previous weekday (local calendar)."""
    import datetime as dt
    for nm, tz, start, end in ORB_SESSIONS:
        if nm != name:
            continue
        start, end = _session_times(base, nm, tz, start, end)
        z = ZoneInfo(tz)
        day = dt.datetime.fromtimestamp(open_ms / 1000, dt.timezone.utc).astimezone(z).date()
        day -= dt.timedelta(days=1)
        while day.weekday() >= 5:
            day -= dt.timedelta(days=1)
        o = dt.datetime(day.year, day.month, day.day, start[0], start[1], tzinfo=z)
        c = dt.datetime(day.year, day.month, day.day, end[0], end[1], tzinfo=z)
        return int(o.timestamp() * 1000), int(c.timestamp() * 1000)
    return None


def session_va_event(base: str, m15: Sequence[Sequence[float]], cut: int) -> Optional[Dict]:
    """
    eng-95, Dalton's 80% rule by session (as on a stock exchange: yesterday's regular session's value area, today's
    open of the same session): the session opened outside the previous same session's TPO value area and closed two
    consecutive 30-minute periods (counted from the session's open) back inside it -> the far edge; out at the close.
    """
    for name, open_ms, close_ms in orb_sessions(base, cut - 1):
        prev = previous_session(base, name, open_ms)
        if prev is None:
            continue
        pc = [c for c in m15 if prev[0] <= c[0] < prev[1]]
        if len(pc) < 0.8 * (prev[1] - prev[0]) / QUARTER_MS:
            continue
        day = [c for c in m15 if open_ms <= c[0] < cut]
        if len(day) < 4 or len(day) % 2 or cut >= close_ms or not _complete_quarters(day, open_ms, cut):
            continue
        va = value_area(pc, tpo=True)
        if va is None:
            continue
        val, poc, vah = va
        opened = day[0][1]
        if val <= opened <= vah:
            continue
        side = 1 if opened < val else -1
        inside = lambda pair: val <= pair[-1][4] <= vah        # noqa: E731
        periods = [day[k:k + 2] for k in range(0, len(day) - 1, 2)]
        if not (inside(periods[-1]) and inside(periods[-2])) or (len(periods) >= 3 and inside(periods[-3])):
            continue
        edge, far = (val, vah) if side > 0 else (vah, val)
        last = day[-1]
        if side * (far - last[4]) <= 0:
            continue                               # eng-110: only 'the far edge is still ahead' (the 0.3 x VA was ours)
        extreme = min(c[3] for c in day) if side > 0 else max(c[2] for c in day)
        return {'setup': 'VA80 LONG' if side > 0 else 'VA80 SHORT', 'direction': side,
                'setup_note': f"{name} session opened {'below' if side > 0 else 'above'} the previous {name} session's "
                              f"value area {val:.6g}-{vah:.6g} (POC {poc:.6g}), back inside for two 30m periods: "
                              f"Dalton's 80% rule -> the far edge, out at the session's close",
                'anchor_level': edge, 'anchor_extreme': extreme,
                'anchor_label': f"{name} value area {'low' if side > 0 else 'high'}",
                'anchor_ts': open_ms, 'anchor_close': last[4], 'va_far': far, 'va_poc': poc,
                'orb_session': name, 'session_end_ms': close_ms, 'event_ts': int(last[0]) + QUARTER_MS}
    return None


def failed_auction_event(base: str, m15: Sequence[Sequence[float]], cut: int) -> Optional[Dict]:
    """
    eng-127, the failed auction (Steidlmayer / Dalton, auction market theory): the session OPENED INSIDE the previous
    same session's TPO value area, probed beyond one edge and did not find acceptance there - acceptance = two
    consecutive 30-minute periods closing beyond (the TPO convention of the 80% rule) - then a 30-minute period closed
    back inside: "price re-enters a previously accepted value range ... the market will auction to the opposite end"
    -> the far edge; the stop beyond the probe's extreme; out at the session's close. (The opening outside value is
    the 80% rule, session_va_event.)
    """
    for name, open_ms, close_ms in orb_sessions(base, cut - 1):
        prev = previous_session(base, name, open_ms)
        if prev is None:
            continue
        pc = [c for c in m15 if prev[0] <= c[0] < prev[1]]
        if len(pc) < 0.8 * (prev[1] - prev[0]) / QUARTER_MS:
            continue
        day = [c for c in m15 if open_ms <= c[0] < cut]
        if len(day) < 2 or len(day) % 2 or cut >= close_ms or not _complete_quarters(day, open_ms, cut):
            continue
        va = value_area(pc, tpo=True)
        if va is None:
            continue
        val, poc, vah = va
        if not val <= day[0][1] <= vah:
            continue
        periods = [(max(x[2] for x in day[k:k + 2]), min(x[3] for x in day[k:k + 2]), day[k + 1][4])
                   for k in range(0, len(day) - 1, 2)]
        hi, lo, close = periods[-1]
        if not val <= close <= vah:
            continue
        for side, edge, far in ((-1, vah, val), (1, val, vah)):
            beyond = [(p[2] > edge) if side < 0 else (p[2] < edge) for p in periods]
            if any(beyond[k] and beyond[k + 1] for k in range(len(beyond) - 1)):
                continue                       # accepted beyond the edge at some point: not a failed auction
            probed = (hi > edge) if side < 0 else (lo < edge)
            if not (probed or (len(beyond) >= 2 and beyond[-2])):
                continue                       # this period is not the return from a probe
            extreme = max(p[0] for p in periods) if side < 0 else min(p[1] for p in periods)
            if side * (far - close) <= 0:
                continue
            return {'setup': 'AUCTION LONG' if side > 0 else 'AUCTION SHORT', 'direction': side,
                    'setup_note': f"{name} session opened inside the previous {name} value area {val:.6g}-{vah:.6g}, "
                                  f"probed {'below' if side > 0 else 'above'} to {extreme:.6g} without acceptance (no two "
                                  f"30m closes beyond) and closed back inside: failed auction -> the far edge {far:.6g}",
                    'anchor_level': edge, 'anchor_extreme': extreme,
                    'anchor_label': f"{name} value area {'low' if side > 0 else 'high'} (failed auction)",
                    'anchor_ts': open_ms, 'anchor_close': close, 'va_far': far, 'va_poc': poc,
                    'orb_session': name, 'session_end_ms': close_ms, 'event_ts': int(day[-1][0]) + QUARTER_MS}
    return None


def session_orb(base: str, minutes: Sequence[Sequence[float]], now_ms: int, price_hi: float, price_lo: float,
                fired: set, symbol: str, d1: Sequence[Sequence[float]] = ()) -> Optional[Dict]:
    """Crabel's ORB on a running session. audit: Crabel, "Playing the Opening Range Breakout" Part 8 (Stocks &
    Commodities, p. 36) - the opening range of the first minutes (30 seconds to 5 minutes; 5 here), a buy stop the
    Stretch (the 10-day SMA of min(High - Open, Open - Low)) above its high and a sell stop the Stretch below its low;
    the first level TRADED through is the entry (a stop order fills on the touch, at the level or a gap's open), the
    other one the stop. Was: the session's open +- Stretch and a 5m CLOSE beyond (eng-105), another reference and
    moment. `minutes`: final 1m candles; the break is read on them (a minute late at most, the level is the price).
    audit E08: the contract is the CLOSED minute - price_hi / price_lo (the live tick) are accepted for the caller's
    signature and deliberately not read: a stop-entry detected on a candle that closed is a minute late, not instant."""
    or_minutes = 5
    for name, open_ms, close_ms in orb_sessions(base, now_ms):
        if (symbol, open_ms) in fired:
            continue
        s = stretch(list(d1), CONFIG.strategies.orb_stretch_days) if d1 else None
        opening = [c for c in minutes if open_ms <= c[0] < open_ms + or_minutes * 60_000]
        if not s or len(opening) < or_minutes or opening[0][0] != open_ms:
            continue                                   # no stretch / the opening range is incomplete: no Crabel ORB
        hi = max(c[2] for c in opening) + s
        lo = min(c[3] for c in opening) - s
        after = [c for c in minutes if c[0] >= open_ms + or_minutes * 60_000 and c[0] < close_ms]
        hit = next(((c, 1 if c[2] >= hi else -1) for c in after if c[2] >= hi or c[3] <= lo), None)
        if hit is None:
            continue
        b, side = hit
        if b[2] >= hi and b[3] <= lo:
            fired.add((symbol, open_ms))           # both stops in one minute: the order is unknown - no trade
            continue
        if b is not minutes[-1]:
            fired.add((symbol, open_ms))           # the first touch was earlier: the first break only
            continue
        level, other = (hi, lo) if side > 0 else (lo, hi)
        fired.add((symbol, open_ms))
        return {'setup': 'ORB UP' if side > 0 else 'ORB DOWN', 'direction': side,
                'setup_note': f"{name} session: traded through the {or_minutes}-minute opening range +- Crabel's Stretch "
                              f"{lo:.6g}-{hi:.6g} "
                              f"{'up' if side > 0 else 'down'}, out at the session's close",
                'anchor_level': level, 'anchor_extreme': other, 'anchor_label': f'{name} opening range',
                'anchor_ts': open_ms, 'anchor_close': level, 'orb_hi': hi, 'orb_lo': lo, 'orb_session': name,
                'session_end_ms': close_ms, 'event_ts': int(b[0]) + 60_000}
    return None


# ------------------------------------------------------------------------------------------------ Connors RSI(2)

def rsi(closes: Sequence[float], period: int) -> Optional[float]:
    """Wilder's RSI of the last close."""
    if len(closes) < period + 1:
        return None
    gains = losses = 0.0
    for a, b in zip(closes[:period], closes[1:period + 1]):
        gains += max(0.0, b - a)
        losses += max(0.0, a - b)
    avg_g, avg_l = gains / period, losses / period
    for a, b in zip(closes[period:], closes[period + 1:]):
        avg_g = (avg_g * (period - 1) + max(0.0, b - a)) / period
        avg_l = (avg_l * (period - 1) + max(0.0, a - b)) / period
    if avg_l == 0:
        return 50.0 if avg_g == 0 else 100.0     # audit E05: a flat series is neutral, as ind_panel
    return 100 - 100 / (1 + avg_g / avg_l)


def connors_event(d1: Sequence[Sequence[float]], first: bool = True) -> Optional[Dict]:
    """
    Connors on DAILY candles (his system; the 1h version of eng-29's first draft was another system): the day that
    closed with RSI(2) in the extreme (`first`: not already there the day before - he is in until the SMA5 exit, a
    run of oversold days is one trade).
    """
    cfg = CONFIG.strategies
    h1 = d1
    if len(h1) < 202:
        return None
    closes = [c[4] for c in h1]
    sma200 = sum(closes[-200:]) / 200
    sma5 = sum(closes[-5:]) / 5
    r = rsi(closes[-60:], 2)
    if r is None or math.isnan(r):
        return None
    last = h1[-1]
    c = last[4]
    # eng-84, the cross-back filter (practice for crypto's one-way dumps): the day RSI(2) comes BACK out of the
    # extreme after at least one day in it - not the first day into it
    prev = rsi(closes[-61:-1], 2)
    if prev is None or math.isnan(prev):
        return None
    if first == 'orig':
        # audit: Connors / Alvarez, Short Term Trading Strategies That Work (2008), ch. 9 p. 62 - above the SMA200, a
        # CLOSE with RSI(2) < 5, buy on the close (RSI2X, traded); no 'first close into the extreme' condition (a run
        # of oversold days is one trade because the card / position stays open). The mirrored short is not in the
        # book's four rules: journaled in shadow (signal_book.SHADOW_SETUPS)
        if c > sma200 and r < cfg.connors_rsi_low:
            side = 1
        elif c < sma200 and r > cfg.connors_rsi_high:
            side = -1
        else:
            return None
    elif c > sma200 and prev < cfg.connors_rsi_low <= r and c < sma5:
        side = 1
    elif c < sma200 and prev > cfg.connors_rsi_high >= r and c > sma5:
        side = -1
    else:
        return None
    extreme = min(x[3] for x in h1[-3:]) if side > 0 else max(x[2] for x in h1[-3:])
    from levels import atr_of
    atr = atr_of(h1[-200:])                                # Wilder's ATR14, the bot's one ATR (was a 20-bar mean)
    tag = 'RSI2X' if first == 'orig' else 'RSI2'
    return {'setup': f'{tag} LONG' if side > 0 else f'{tag} SHORT', 'direction': side, 'connors_atr': atr,
            'setup_note': f"daily RSI(2) {r:.0f} {'below ' + format(cfg.connors_rsi_low, 'g') + ' above' if side > 0 else 'above ' + format(cfg.connors_rsi_high, 'g') + ' below'} the SMA200 "
                          f"{sma200:.6g} (Connors); exit at the SMA5 {sma5:.6g}",
            'anchor_level': c, 'anchor_extreme': extreme, 'anchor_label': 'RSI(2) extreme',
            'anchor_ts': int(last[0]), 'anchor_close': c, 'connors_sma5': sma5, 'rsi2': r,
            'event_ts': int(last[0]) + DAY_MS}


def classic_events(m15: List[List[float]], h1: List[List[float]], cut: int, symbol: Optional[str] = None) -> List[Dict]:
    out = []
    # eng-95: Dalton's 80% rule by session, on the session instruments only (was the UTC day on every coin)
    base = (symbol or '').split('/')[0]
    for fn in (session_va_event, failed_auction_event):     # eng-127: the failed auction beside the 80% rule
        found = fn(base, m15, cut) if base in CONFIG.strategies.orb_bases else None
        if found:
            out.append(found)
    return out                     # ORB (on the touch) and Connors' RSI(2) run on daily candles, loop-side (Scanner)
