'Records configured entry-confirmation readings (flow, spot, OI, order-flow and volume/spread\nconditions). The readings are not assumed independent, and their predictive value, source\nfidelity and promotion rules are not established by this docstring.'
from typing import Dict, Optional, Sequence, Set, Tuple

from config import CONFIG

NAMES = ('flow', 'spot', 'oi', 'orderflow', 'vsa')
NA = 'n/a'
OI_EXPECT = {'continuation': 1, 'breakout': 1, 'sweep': -1, 'silver_bullet': -1, 'wyckoff': -1,
             # eng-169e (audit S4): PO3's Judas swing is a raid-and-reverse like the sweep - positions flushed, not added
             'po3': -1,
             # 2026-10-05: every method gets the reading its type implies (journaled; required only when proven):
             # breaks and momentum need new positions behind them, fades of an extreme need them flushed
             'orb': 1, 'pump_start': 1, 'dump_start': 1, 'pump_top': -1, 'dump_bounce': -1,
             'trendline_break': 1, 'trendline_touch': 1, 'cup_handle': 1,
             'bollinger_wm': -1, 'bollinger_method3': -1, 'bollinger_method1': 1,
             'value_area': -1, 'auction': -1, 'supply_demand': -1, 'connors': -1,
             'cascade': -1, 'oi_build': 1}
REVERSALS = ('wyckoff', 'cascade', 'sweep', 'silver_bullet', 'po3')
MINUTE_MS = 60_000
HOUR_MS = 3_600_000

# (strategy, confirmation) required because the journal proved entries without it lose (refreshed hourly)
PROMOTED: Set[Tuple[str, str]] = set()


def positive(value) -> bool:
    'Returns whether a confirmation value is present under the configured missing/NA convention.'
    return value is True or (isinstance(value, str) and value != NA)


def required(strategy: str) -> Tuple[str, ...]:
    'Returns the confirmation names configured for a strategy.'
    cfg = CONFIG.orderflow
    out = [item.split(':', 1)[1] for item in cfg.required_confirmations if item.split(':', 1)[0] in (strategy, '*')]
    if cfg.require_orderflow_confirm:
        out.append('orderflow')
    out += [name for s, name in PROMOTED if s == strategy]
    return tuple(dict.fromkeys(out))


def required_names() -> Set[str]:
    'Returns the union of configured and promoted confirmation names.\nPromotion is a project rule; no statistical proof is claimed.'
    out = {item.split(':', 1)[1] for item in CONFIG.orderflow.required_confirmations}
    out.add('orderflow')
    out.update(name for _, name in PROMOTED)
    return out


# eng-169h (the owner: long or short is decided by where the volume and the liquidity are): a liquidity-raid setup
# trades only when the volume after the raid backs it - the taker delta on the trade's side OR absorption / CVD
# divergence for it. Journal before the rule (303 cards): raids with neither -0.18R / card (21), with delta +0.21R
# (39), delta against but absorbed +0.36R (19). Missing flow data (None) never vetoes.
LIQ_FLOW = ('sweep', 'silver_bullet', 'po3', 'wyckoff', 'cascade')
LIQ_FLOW_SETUPS = ('PUMP TOP',)


def liq_flow_missing(strategy: str, confirms: Dict, setup: str = '') -> bool:
    if strategy not in LIQ_FLOW and not any((setup or '').startswith(x) for x in LIQ_FLOW_SETUPS):
        return False
    return confirms.get('flow') is False and not positive(confirms.get('orderflow'))


def missing(strategy: str, confirms: Dict, setup: str = '') -> Optional[str]:
    'Returns the first missing required confirmation reason under the configured veto convention.'
    # An OI-dependent playbook cannot make a valid entry decision without a
    # fresh OI window.  Missing OI is a data-quality veto, never a neutral
    # reading that can silently pass when the confirmation is not promoted.
    if strategy in OI_EXPECT and confirms.get('oi') is None:
        return 'no_oi_data'
    if confirms and liq_flow_missing(strategy, confirms, setup):
        return 'no_flow_absorb'
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
    'Computes taker buy-minus-sell quote delta for the supplied minute window.'
    return sum(2 * c[6] - c[5] for c in minutes if since_ms <= c[0] < until_ms)


def covered_delta(minutes: Optional[Sequence[Sequence[float]]], since_ms: int, until_ms: int) -> Optional[float]:
    'Returns delta only when the supplied minute window is covered by recent data; otherwise returns\nno reading. Missing data are not recoded as a negative confirmation.'
    window = [c for c in (minutes or ()) if since_ms <= c[0] < until_ms]
    if not window or until_ms - window[-1][0] > 3 * MINUTE_MS:
        return None
    return sum(2 * c[6] - c[5] for c in window)


def oi_change(samples: Sequence[Tuple[float, float]], since_ms: int, until_ms: int) -> Optional[float]:
    'Computes relative OI change between the first and last available samples in the supplied window;\nno directional position inference is claimed.'
    window = [(t, v) for t, v in samples if since_ms <= t <= until_ms and v]
    if len(window) < 2 or window[-1][0] - window[0][0] < 5 * MINUTE_MS \
            or until_ms - window[-1][0] > 3 * MINUTE_MS:
        return None
    return window[-1][1] / window[0][1] - 1


def cvd_divergence(minutes: Sequence[Sequence[float]], extreme_ms: int, direction: int) -> bool:
    """Compare candle taker-buy aggregates around an extreme; this is OHLCV-derived delta, not event-level CVD."""
    'Flags a configured price/CVD divergence condition. It is a descriptive pattern, not proof of\nexhaustion or participant intent.'
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
    'Evaluates the configured confirmation set for one entry.'
    # Flows since the extreme, at most the last hour (a 1h / 4h leg's end can be hours back: its flow would be the
    # whole pullback)
    start = max(extreme_ms if extreme_ms is not None else since_ms, until_ms - HOUR_MS)
    # flow_usd / spot_usd: the multi-venue deltas over the same window when the caller has them (fetcher: every futures
    # venue; Binance spot + Coinbase / Bybit spot), else Binance's 1m candles alone
    flow = flow_usd if flow_usd is not None else covered_delta(minutes, start, until_ms)
    out: Dict = {'flow': None if flow is None else direction * flow > 0}
    if spot_minutes is None and spot_usd is None:
        out['spot'] = NA
    else:
        spot = spot_usd if spot_usd is not None else covered_delta(spot_minutes, start, until_ms)
        out['spot'] = None if spot is None else direction * spot > 0
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
