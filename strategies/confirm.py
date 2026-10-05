"""
Entry confirmations: independent evidence, measured at the entry, that the market backs the trade. The trigger itself
(a structure shift with agreeing taker flow, an accepted breakout, a confirmed phase) is the entry; these are the
readings order-flow traders check before taking it, each recorded for every entry (journal `confirms`):

- flow       futures taker delta since the extreme (at most the last hour) agrees with the trade;
- spot       spot taker delta over the same window agrees: real buying / selling of the coin, not only leverage
             (spot-led moves hold, perp-led ones get squeezed); 'n/a' for a coin without a spot pair;
- oi         open interest over the last hour (OI-weighted across venues when >= 2 report, else Binance): RISING for
             continuations (trend, momentum, breakout: new positions back the move - price and OI together), FALLING
             for sweeps and cascade exhaustion (the stops / liquidations were flushed); 'n/a' for Wyckoff (its phases
             score OI themselves) and absorption (absorbed market orders open positions on both sides);
- orderflow  at the extreme: stacked footprint imbalances, absorption (a heavy 1m delta against the trade that barely
             moved price), a finished auction (the footprint's extreme price traded only by the side that was pushing:
             nobody left to trade there, ATAS / Market Profile) or, for reversals, a CVD divergence (price made a new
             extreme beyond the previous swing, cumulative delta did not: the aggressive side is exhausted); False
             when none of them happened;
- vsa        Volume Spread Analysis on the 5m bars since the extreme (strategies/vsa.py, Tom Williams): no supply /
             stopping volume / reverse upthrust for longs, no demand / buying climax / upthrust for shorts.

Keys starting with '_' are metadata ('_window' = [since, until, extreme] ms, set by fetcher.confirmations), not readings.
Values: True / False, the order-flow kind (a string = present), NA ('n/a') where the reading cannot exist for this
coin / strategy. The inputs (1m candles of futures and spot, OI) are seeded from REST at start-up, so a reading is
never missing after a restart; if one still is (a REST failure), it is None and never vetoes.
Which confirmations an entry needs: CONFIG.orderflow.required_confirmations (by rule: a breakout needs rising OI,
like the D / F phases and directional impulses) plus those PROMOTED by the journal once entries without them show a
negative Edge (journal.refresh_confirm_stats). The rest are recorded and shown until stats.py proves them.
"""
from typing import Dict, Optional, Sequence, Set, Tuple

from config import CONFIG

NAMES = ('flow', 'spot', 'oi', 'orderflow', 'vsa')
NA = 'n/a'
OI_EXPECT = {'continuation': 1, 'breakout': 1, 'sweep': -1, 'wyckoff': -1}
REVERSALS = ('wyckoff', 'sweep')
MINUTE_MS = 60_000
HOUR_MS = 3_600_000

# (strategy, confirmation) required because the journal proved entries without it lose (refreshed hourly)
PROMOTED: Set[Tuple[str, str]] = set()


def positive(value) -> bool:
    """A confirmation that is present (True or an order-flow kind), not 'n/a' / False / None."""
    return value is True or (isinstance(value, str) and value != NA)


def required(strategy: str) -> Tuple[str, ...]:
    """Confirmations an entry of `strategy` needs."""
    cfg = CONFIG.orderflow
    out = [item.split(':', 1)[1] for item in cfg.required_confirmations if item.split(':', 1)[0] in (strategy, '*')]
    if cfg.require_orderflow_confirm:
        out.append('orderflow')
    out += [name for s, name in PROMOTED if s == strategy]
    return tuple(dict.fromkeys(out))


def missing(strategy: str, confirms: Dict) -> Optional[str]:
    """The veto reason of the first required confirmation that is negative ('no_<name>')."""
    for name in required(strategy):
        if confirms.get(name) is False:
            return f'no_{name}'
    # Order-flow practice (Trader Dale, ATAS: enter only once delta / absorption confirm the level): an entry with NOT
    # ONE positive reading is not taken (live eng-6: 0 of 4 confirmations -0.44R on 67 entries; still journaled as a
    # vetoed entry and replayed, so the rule stays measurable)
    if strategy in CONFIG.orderflow.confirm_exempt:
        return None
    readings = {k: v for k, v in confirms.items() if not k.startswith('_')}
    if CONFIG.orderflow.min_confirmations and readings and             sum(1 for v in readings.values() if positive(v)) < CONFIG.orderflow.min_confirmations:
        return 'no_confirmation'
    return None


def delta(minutes: Sequence[Sequence[float]], since_ms: int, until_ms: int) -> float:
    """Taker delta (buy - sell quote) of the 1m candles opened in [since_ms, until_ms); 0 without trades."""
    return sum(2 * c[6] - c[5] for c in minutes if since_ms <= c[0] < until_ms)


def oi_change(samples: Sequence[Tuple[float, float]], since_ms: int, until_ms: int) -> Optional[float]:
    """
    Relative OI change from the first sample at / after since_ms to the last at / before until_ms (a listing younger
    than the window: over its available history, at least 5 minutes). None without two such samples.
    """
    window = [(t, v) for t, v in samples if since_ms <= t <= until_ms and v]
    if len(window) < 2 or window[-1][0] - window[0][0] < 5 * MINUTE_MS:
        return None
    return window[-1][1] / window[0][1] - 1


def cvd_divergence(minutes: Sequence[Sequence[float]], extreme_ms: int, direction: int) -> bool:
    """
    Price made its extreme beyond the previous swing of the lookback while cumulative delta did not (long: a lower
    low on a higher CVD low). The previous swing = the most extreme candle closing at least 5 minutes before the
    extreme's candle. False when there is no such swing (nothing to diverge from).
    """
    lookback = CONFIG.orderflow.divergence_lookback_min * MINUTE_MS
    window = [c for c in minutes if extreme_ms - lookback <= c[0] <= extreme_ms]
    cvd, total = [], 0.0
    for c in window:
        total += 2 * c[6] - c[5]
        cvd.append(total)
    last = len(window) - 1
    prior = [i for i in range(last) if window[i][0] <= extreme_ms - 5 * MINUTE_MS]
    if not prior:
        return False
    if direction > 0:
        p = min(prior, key=lambda i: window[i][3])
        return window[last][3] < window[p][3] and cvd[last] > cvd[p]
    p = max(prior, key=lambda i: window[i][2])
    return window[last][2] > window[p][2] and cvd[last] < cvd[p]


def evaluate(strategy: str, direction: int, minutes: Sequence[Sequence[float]],
             spot_minutes: Optional[Sequence[Sequence[float]]], oi: Optional[float],
             since_ms: int, until_ms: int, extreme_ms: Optional[int], orderflow: Optional[str],
             flow_usd: Optional[float] = None, spot_usd: Optional[float] = None) -> Dict:
    """
    All confirmations of one entry (see the module docstring). `spot_minutes` None = the coin has no spot pair;
    `oi` = the relative OI change over the last hour.
    """
    # Flows since the extreme, at most the last hour (a 1h / 4h leg's end can be hours back: its flow would be the
    # whole pullback)
    start = max(extreme_ms if extreme_ms is not None else since_ms, until_ms - HOUR_MS)
    # flow_usd / spot_usd: the multi-venue deltas over the same window when the caller has them (fetcher: every futures
    # venue; Binance spot + Coinbase / Bybit spot), else Binance's 1m candles alone
    out: Dict = {'flow': direction * (flow_usd if flow_usd is not None else delta(minutes, start, until_ms)) > 0}
    if spot_minutes is None and spot_usd is None:
        out['spot'] = NA
    else:
        out['spot'] = direction * (spot_usd if spot_usd is not None else delta(spot_minutes, start, until_ms)) > 0
    expect = OI_EXPECT.get(strategy)
    out['oi'] = NA if not expect else (None if oi is None else expect * oi > 0)
    # The raw 1h OI change for every strategy (underscore keys are not confirmations): strategies without an OI
    # hypothesis show 'n/a', but the journal keeps the reading so stats can test one
    out['_oi_1h'] = oi
    if orderflow:
        out['orderflow'] = orderflow
    elif strategy in REVERSALS and extreme_ms is not None and cvd_divergence(minutes, extreme_ms, direction):
        out['orderflow'] = 'divergence'
    else:
        out['orderflow'] = False
    from levels import resample
    from strategies import vsa
    # the whole minute buffer (10h): the sign needs vsa.AVG_BARS 5m bars before it - a 3h window left none for an
    # extreme older than 80 minutes (ORB's median 273, VA80's 300: never positive, 2026-10-05)
    bars = resample([c for c in minutes if c[0] < until_ms], 5)
    bars = [b for b in bars if b[0] + 5 * MINUTE_MS <= until_ms]          # closed 5m bars only
    anchor = extreme_ms if extreme_ms is not None else since_ms
    # the VSA sign must be the extreme's own reading (its 5m bar and the three after it): anywhere since the setup it
    # was positive on 13 of 16 entries (no supply is a common bar) and made the confirmation minimum meaningless.
    # An extreme without AVG_BARS bars before it in the buffer: the last four closed bars before the entry
    first = anchor // (5 * MINUTE_MS) * (5 * MINUTE_MS)
    i = next((k for k, b in enumerate(bars) if b[0] >= first), len(bars))
    if i < vsa.AVG_BARS:
        first = bars[-4][0] if len(bars) >= vsa.AVG_BARS + 4 else None
    out['vsa'] = vsa.confirm([b for b in bars if b[0] < first + 4 * 5 * MINUTE_MS], first, direction)         if first is not None else None
    return out
