"""
Pretraining on the public Binance archive (history.py) BEFORE the bot starts; live, the models keep learning.

What is trained (everything the archive has the inputs for):
- the market regime model (ml.RegimeModel): the same market-wide features per closed 15m candle (BTC 1h move and
  volatility, breadth, median funding / 1h OI change / RVOL) over months of history instead of the last days;
- P(edge) (ml.SuccessModel): the journal rows the bot would have written - phase setups (A-F) scored by the same
  indicator / scorer code on 15m candles built from 1m klines (futures + spot, OI from the 5-minute metrics, funding
  from the funding history), liquidity sweeps and breakouts from the same detector (strategies.structure.build_context
  on each closed candle with its 8 days of 1h candles), Tier-0 anomalies / impulses from the same
  calculate_tier0_metrics + rules on every minute that could qualify - each with its context (market / BTC moves, the
  coin's 1h trend, volatility, 24h volume, long-short ratios, regime, market crowd), the journal's cooldown, and the
  label the live journal gives it (the 4h return in the signal's direction beat the median of every coin).

Not in the archive (the models learn them live only): liquidations, order books, the other venues' flows / OI,
Hyperliquid accounts, Coinbase, the IsolationForest verdict (Tier-0 rows here are the rule-based ones). Whale sizes
come from live sweeps (kept across restarts). The IsolationForest itself is not pretrained: it judges "unusual
compared with the last 3 hours", which history cannot tell (its window survives restarts, ml_state.pkl).

Run:  .venv\\Scripts\\python pretrain.py [--months 6] [--min-volume 3e6] [--workers 3] [--rate 1000000]
Downloads are cached (history_cache/); a re-run only computes. The result is pretrained.pkl; the bot loads it at
start (journal P(edge), scanner regimes) and keeps learning on top of it. Run it while the bot is stopped or with a
low --rate: the download shares the link with the live streams.
"""
import errors
import argparse
import logging
import pickle
import statistics
import time
from collections import deque
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import polars as pl

from config import CONFIG

logger = logging.getLogger('pretrain')

MINUTE_MS = 60_000
QUARTER_MS = 900_000
HOUR_MS = 3_600_000
DAY_MINUTES = 1440
H4_MS = 4 * HOUR_MS
# Keys of a signal kept for the journal row (the rest of the scored row is dropped before pickling)
SIG_KEYS = None   # filled lazily: journal.FEATURE_KEYS values + _base_row inputs


# ====================================================================== coins

def _spot_pair(base: str, spot_ids: set) -> Optional[str]:
    """The Binance spot pair of a futures base (1000PEPE -> PEPEUSDT), else None."""
    if f"{base}USDT" in spot_ids:
        return f"{base}USDT"
    from symbols import split_base
    coin = split_base(base)[0]
    return f"{coin}USDT" if coin != base and f"{coin}USDT" in spot_ids else None


def eligible_days(daily: np.ndarray, start: date, end: date, min_volume: float) -> List[int]:
    """
    Days (epoch day numbers) in [start, end] on which the coin would have passed the universe's volume floor and
    listing age, from PAST data only: the average daily quote volume of the 30 days before (over the days it traded,
    at least min_listing_days of them) >= min_volume. Days whose 30 days before hold fewer than 20 known daily candles
    (the running month has no monthly 1d file) keep the last decision.
    """
    if len(daily) == 0:
        return []
    by_day = {int(ts // 86_400_000): qv for ts, _, qv in daily}
    first = min(by_day)
    min_age = CONFIG.exchange.min_listing_days
    out: List[int] = []
    last = False
    d0, d1 = (start - date(1970, 1, 1)).days, (end - date(1970, 1, 1)).days
    for day in range(d0, d1 + 1):
        window = [by_day[k] for k in range(day - 30, day) if k in by_day]
        if len(window) >= 20 or (day - first < 30 and len(window) >= min_age):
            last = day - first >= min_age and sum(window) / len(window) >= min_volume
        if last:
            out.append(day)
    return out


def select_coins(archive, start: date, end: date, min_volume: float) -> List[Tuple[str, str, str, List[int]]]:
    """
    (journal key, futures id, spot id, eligible days) of every USDT perpetual the ARCHIVE has - delisted ones included
    - with a Binance spot pair (the live universe requires one: CONFIG.exchange.require_spot; tokenized stocks and
    pre-IPO contracts have none) that passed the volume floor on at least one day of the window, judged day by day from
    the 30 days before it. Today's exchange list and today's 24h volume picked the coins before: delisted coins were
    missing (survivorship) and a coin that became liquid last week counted for all months (look-ahead).
    Sorted by volume over the window.
    """
    from concurrent.futures import ThreadPoolExecutor
    futures = [s for s in archive.list_symbols('futures')
               if s.endswith('USDT') and '_' not in s and 'SETTLED' not in s]
    spot_ids = set(archive.list_symbols('spot'))
    pairs = [(f, _spot_pair(f[:-4], spot_ids)) for f in futures]
    pairs = [(f, sp) for f, sp in pairs if sp]
    since = start - timedelta(days=35)

    def one(item):
        fut_id, spot_id = item
        daily = archive.klines_1d('futures', fut_id, since, end)
        days = eligible_days(daily, start, end, min_volume)
        window = daily[daily[:, 0] >= (start - date(1970, 1, 1)).days * 86_400_000] if len(daily) else daily
        return fut_id, spot_id, days, float(window[:, 2].sum()) if len(window) else 0.0

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(one, pairs))
    out = [(f"{f[:-4]}/USDT:USDT", f, sp, days, vol) for f, sp, days, vol in results if days]
    out.sort(key=lambda c: -c[4])
    logger.info(f"pretrain: {len(out)} coins with a spot pair passed the ${min_volume / 1e6:g}M floor on some day "
                f"({len(pairs)} with a spot pair, {len(futures)} USDT perpetuals in the archive, delisted included)")
    return [c[:4] for c in out]


# ====================================================================== per coin (worker process)

def _bucket(arr: np.ndarray, ms: int) -> np.ndarray:
    """1m rows [ts, o, h, l, c, v, qv, tbq] -> candles of `ms` (the last, possibly incomplete one dropped). audit C16:
    as live (levels.resample), only a group holding every one of its minutes once is a candle - a 5m bar of two minutes
    is not."""
    if len(arr) == 0:
        return np.empty((0, 8))
    arr = arr[np.r_[True, arr[1:, 0] != arr[:-1, 0]]] if len(arr) > 1 else arr   # a re-delivered minute once
    b = (arr[:, 0] // ms) * ms
    idx = np.flatnonzero(np.r_[True, b[1:] != b[:-1]])
    last = np.r_[idx[1:] - 1, len(arr) - 1]
    out = np.column_stack([b[idx], arr[idx, 1], np.maximum.reduceat(arr[:, 2], idx),
                           np.minimum.reduceat(arr[:, 3], idx), arr[last, 4], np.add.reduceat(arr[:, 5], idx),
                           np.add.reduceat(arr[:, 6], idx), np.add.reduceat(arr[:, 7], idx)])
    full = (last - idx + 1) == ms // 60_000
    return out[:-1][full[:-1]]


def _raw_frame(c: np.ndarray, oi: Optional[Dict[int, float]]) -> pl.DataFrame:
    from indicators import RAW_SCHEMA
    return pl.DataFrame({
        'timestamp': c[:, 0].astype(np.int64), 'open': c[:, 1], 'high': c[:, 2], 'low': c[:, 3], 'close': c[:, 4],
        'volume': c[:, 5], 'quote_volume': c[:, 6], 'taker_delta': 2 * c[:, 7] - c[:, 6],
        'open_interest': [oi.get(int(t)) for t in c[:, 0]] if oi is not None else [None] * len(c),
    }, schema=RAW_SCHEMA)


def closed_minutes(open_ts: np.ndarray, now_ms: float) -> int:
    """How many 1m candles (by open time) have CLOSED by now_ms: an archive minute holds its whole minute, the live
    scanner only the seconds already passed, so a running minute must not be read."""
    return int(np.searchsorted(open_ts, now_ms - MINUTE_MS, side='right'))


def _asof(ts: np.ndarray, values: np.ndarray, at: float) -> Optional[float]:
    i = int(np.searchsorted(ts, at, side='right')) - 1
    return float(values[i]) if i >= 0 else None


def process_coin(job: tuple) -> Optional[Dict]:
    """
    One coin: download, build the live data structures from history, and produce the journal rows the bot would
    have written (without the cross-coin context, added in the main process) plus the market series.
    """
    key, fut_id, spot_id, start_iso, end_iso, rate, days_ok = job
    days_ok = frozenset(days_ok)
    from history import Archive
    from indicators import (calculate_tier0_metrics, compute_indicators_batch, minute_delta, seasonal_factors,
                            seasonal_scale)
    from journal import classify, event_family
    from scorer import PhaseScorer
    from strategies.breakout import breakout_at_close
    from strategies.level import sweep_at_close
    from strategies.structure import coin_trend, pools_before, recent_atr, trend_w_of, weekly_ref

    import os
    paths = _paths(fut_id, start_iso, end_iso, days_ok)
    if all(os.path.exists(v) for v in paths.values()):
        # computed by an earlier (interrupted) run over the same window: resume
        return {'key': key, 'n': pl.scan_parquet(paths['rows']).select(pl.len()).collect().item(), **paths}
    os.makedirs(os.path.dirname(paths['rows']), exist_ok=True)
    start, end = date.fromisoformat(start_iso), date.fromisoformat(end_iso)
    archive = Archive(rate_bytes=rate)
    fut = archive.klines_1m('futures', fut_id, start, end)
    if len(fut) < DAY_MINUTES * 10:
        return None
    spot = archive.klines_1m('spot', spot_id, start, end) if spot_id else np.empty((0, 8))
    met = archive.metrics(fut_id, start, end)
    fund = archive.funding(fut_id, start, end)
    w1 = _weekly_closes(archive, fut_id, start, end)

    # ---------------------------------------------------------------- 15m / 1h candles, indicators, phases
    c15 = _bucket(fut, QUARTER_MS)
    s15 = _bucket(spot, QUARTER_MS) if len(spot) else np.empty((0, 8))
    # OI onto candles as live: a snapshot at a period's END closes the candle before it
    oi15 = {}
    for t, v in zip(met['ts'], met['oi']):
        if int(t) % QUARTER_MS == 0 and v:
            oi15[int((t - 1) // QUARTER_MS * QUARTER_MS)] = float(v)
    fut_df = _raw_frame(c15, oi15)
    fut_all = compute_indicators_batch({key: fut_df}, {key: (0.0, 0.0)})
    spot_all = compute_indicators_batch({key: _raw_frame(s15, None)}, {key: (0.0, 0.0)}) if len(s15) else None
    # Funding at each candle's close from the settlement history (live: the current rate)
    if len(fund):
        closes = fut_all['timestamp'].to_numpy() + QUARTER_MS
        rates = [(_asof(fund[:, 0], fund[:, 1], t) or 0.0) for t in closes]
        fut_all = fut_all.with_columns(pl.Series('funding_rate', rates), pl.Series('predicted_funding', rates))
        if spot_all is not None:
            s_closes = spot_all['timestamp'].to_numpy() + QUARTER_MS
            s_rates = [(_asof(fund[:, 0], fund[:, 1], t) or 0.0) for t in s_closes]
            spot_all = spot_all.with_columns(pl.Series('funding_rate', s_rates), pl.Series('predicted_funding', s_rates))
    scorer = PhaseScorer()
    scored = scorer.calculate_scores(spot_all, fut_all, None, None)
    if scored.is_empty():
        return None
    scored = scored.sort('timestamp')

    # ---------------------------------------------------------------- minute-level inputs of Tier-0
    m_ts = fut[:, 0]
    qv_cum = np.concatenate(([0.0], np.cumsum(fut[:, 6])))
    stream_cols = [0, 1, 2, 3, 4, 6, 7]                                        # stream format [t,o,h,l,c,q,Q]

    def stream_rows(arr: np.ndarray, a: int, b: int) -> List[List[float]]:
        return arr[max(0, a):b][:, stream_cols].tolist()

    s_ts = spot[:, 0] if len(spot) else np.empty(0)
    oi_pts = [(float(t), float(v)) for t, v in zip(met['ts'], met['oi']) if v]
    oi_ts = np.asarray([p[0] for p in oi_pts]) if oi_pts else np.empty(0)
    fut_ind = fut_all.select('timestamp', 'ret_std', 'oi_std', 'atr').to_numpy()
    h1 = _bucket(fut, HOUR_MS)
    h1_list = [[r[0], r[1], r[2], r[3], r[4], r[6], r[7], r[5]] for r in h1]
    h1_close_ts = h1[:, 0] + HOUR_MS if len(h1) else np.empty(0)
    c15_list = [[r[0], r[1], r[2], r[3], r[4], r[6], r[7], r[5]] for r in c15]

    seasons: Dict[int, Optional[Dict]] = {}

    def season_at(now_ms: float) -> Optional[Dict]:
        """The time-of-day profile as the bot would have had it: the 4 weeks of 1h candles before that day."""
        day = int(now_ms) // 86_400_000
        if day not in seasons:
            h = int(np.searchsorted(h1_close_ts, day * 86_400_000, side='right'))
            seasons[day] = seasonal_factors(h1_list[max(0, h - 672):h])
        return seasons[day]

    def tier0_at(now_ms: float) -> Dict[str, float]:
        """calculate_tier0_metrics exactly as the scanner calls it, on the history up to now_ms."""
        # Only minutes CLOSED by now_ms: an archive minute holds its whole minute, while the live scanner sees only
        # the seconds of the running minute that have passed (the full minute after a 15m close leaked up to 55s of
        # future volume and taker flow into rvol_1m / minute_usd / *_cvd_5m)
        j = closed_minutes(m_ts, now_ms)
        minutes = deque(stream_rows(fut, j - 30, j), maxlen=240)
        ticker = deque(((k[0] + 59_999, k[4], 0.0) for k in stream_rows(fut, j - 10, j)), maxlen=400)
        k = int(np.searchsorted(oi_ts, now_ms, side='right')) if len(oi_ts) else 0
        oi = deque(oi_pts[max(0, k - 13):k], maxlen=64)
        n = min(j, DAY_MINUTES)
        avg_minute = (qv_cum[j] - qv_cum[j - n]) / max(1, n) if n else 0.0
        q = int(np.searchsorted(fut_ind[:, 0], now_ms - QUARTER_MS, side='right')) - 1
        ret_std = fut_ind[q, 1] if q >= 0 and fut_ind[q, 1] == fut_ind[q, 1] else None
        oi_std = fut_ind[q, 2] if q >= 0 and fut_ind[q, 2] == fut_ind[q, 2] else None
        season = season_at(now_ms)
        if ret_std:
            ret_std *= seasonal_scale(season, now_ms, 'ret')
        avg_minute *= seasonal_scale(season, now_ms, 'vol')
        m = calculate_tier0_metrics(ticker, oi, minutes, now_ms, ret_std=ret_std, oi_std=oi_std,
                                    avg_minute_usd=avg_minute)
        m['futures_cvd_5m'] = minute_delta(minutes, now_ms)
        if len(s_ts):
            js = closed_minutes(s_ts, now_ms)
            m['spot_cvd_5m'] = minute_delta(stream_rows(spot, js - 6, js), now_ms)
        m['whale_net_5m'] = None        # no historical sweeps: the feature is learned live only
        m['volume_24h'] = qv_cum[j] - qv_cum[max(0, j - DAY_MINUTES)]
        return m

    w1_refs: Dict[int, Optional[tuple]] = {}

    def weekly_at(now_ms: float) -> Optional[tuple]:
        """weekly_ref of the weeks CLOSED before now_ms (as the live bot has it after each weekly close)."""
        i = int(np.searchsorted(w1[:, 0], now_ms, side='right')) if len(w1) else 0     # weeks closed by now
        if i not in w1_refs:
            w1_refs[i] = weekly_ref(w1[:i, 1].tolist()) if i else None
        return w1_refs[i]

    def context_at(now_ms: float) -> Dict:
        """The coin's own context (the market's is added in the main process)."""
        out: Dict = {}
        k = int(np.searchsorted(m_ts, now_ms - MINUTE_MS, side='right')) - 1
        out['trend_w'] = trend_w_of(weekly_at(now_ms), float(fut[k, 4])) if k >= 0 else None
        h = int(np.searchsorted(h1_close_ts, now_ms, side='right'))
        out['coin_trend'] = coin_trend(h1_list[max(0, h - 200):h]) if h else None
        q = int(np.searchsorted(c15[:, 0] + QUARTER_MS, now_ms, side='right'))
        atr = fut_ind[q - 1, 3] if q else None
        if q and atr and atr == atr:
            out['vol_ratio'] = recent_atr(c15_list[max(0, q - 24):q]) / atr
        for name, series in (('top_ratio', 'top_pos'), ('ls_top', 'top_acc'), ('ls_global', 'global')):
            out[name] = _asof(met['ts'], met[series], now_ms) if len(met['ts']) else None
        out['has_spot'] = bool(spot_id)
        return out

    def ret_4h(now_ms: float, price: float) -> Optional[float]:
        k = int(np.searchsorted(m_ts, now_ms + H4_MS - MINUTE_MS, side='right')) - 1
        if k < 0 or m_ts[k] < now_ms + H4_MS - 2 * MINUTE_MS or not price:
            return None
        return float(fut[k, 4]) / price - 1

    candidates: List[tuple] = []     # (ts_ms, kind, group_key, direction, price, sig)

    def emit(now_ms: float, sig: Dict, price: float):
        kind, group_key, direction = classify(sig)
        if direction:
            candidates.append((int(now_ms), kind, group_key, direction, price, _small(sig)))

    # ---------------------------------------------------------------- phases on every closed 15m candle
    # In slices: the whole scored frame as Python dicts (~17k rows x ~150 columns per coin) took ~300 MB per worker
    # and pushed the live bot into swap
    scored_ts = scored['timestamp'].to_numpy()
    for chunk in scored.iter_slices(2000):
        rows_chunk = chunk.to_dicts()
        closes_15 = [r['timestamp'] + QUARTER_MS for r in rows_chunk]
        t0s = [tier0_at(close_ms + 5_000) for close_ms in closes_15]      # the scan a few seconds after the close
        flags = scorer.flag_tier_0_anomaly(pl.DataFrame(
            [{'symbol': key, **{c: v for c, v in t0.items() if isinstance(v, (int, float)) and v is not None}}
             for t0 in t0s], infer_schema_length=None))
        for n, (row, close_ms, t0) in enumerate(zip(rows_chunk, closes_15, t0s)):
            now_ms = close_ms + 5_000
            row.update(t0)
            row['is_tier_0_anomaly'] = bool(flags['is_tier_0_anomaly'][n])
            row['rule_anomaly'] = bool(flags['rule_anomaly'][n])
            row['liq_cascade'] = False
            sig = scorer.signal_from_row(row)
            if sig and sig.get('is_structured'):
                sig.update(context_at(now_ms))
                # the futures price (live: _price_of): for a coin with spot the scored row's close is the SPOT
                # close, 1000x smaller for 1000PEPE-type contracts
                k = int(np.searchsorted(m_ts, now_ms - MINUTE_MS, side='right')) - 1
                emit(now_ms, sig, float(fut[k, 4]))
        del rows_chunk, t0s, flags

    def scored_row(i: int) -> Dict:
        return scored.row(i, named=True) if 0 <= i < len(scored_ts) else {}

    # ---------------------------------------------------------------- sweeps / breakouts at each close
    atr_by_ts = {int(t): a for t, a in zip(fut_ind[:, 0], fut_ind[:, 3])}
    flow_cols = ('spot_delta_1h', 'perp_delta_1h', 'perp_led_long', 'perp_led_short', 'funding_rate')
    flow_by_ts = {int(t): dict(zip(flow_cols, vals)) for t, *vals in
                  scored.select('timestamp', *[c for c in flow_cols if c in scored.columns]).iter_rows()}
    # The events of build_context's close block, by the same functions (sweep_at_close with pools_before at the
    # candle's open, breakout_at_close), without the live map's second pool pass. A sweep needs the candle's volume
    # >= sweep_min_rvol x the average of the 20 before (sweep_at_close's own first test): pools are built only then.
    qv15 = c15[:, 6]
    prev20 = np.convolve(qv15, np.ones(20), 'full')[:len(qv15)]
    prev20 = np.r_[np.nan, prev20[:-1]] / 20
    sweep_possible = ~(prev20 > 0) | (qv15 >= CONFIG.strategies.sweep_min_rvol * prev20)
    for q in range(98, len(c15_list)):
        last_open = int(c15_list[q][0])
        cut = last_open + QUARTER_MS
        atr = atr_by_ts.get(last_open)
        if not atr or atr != atr:
            continue
        window = c15_list[q - 98:q + 1]
        h = int(np.searchsorted(h1_close_ts, cut, side='right'))
        h1_window = h1_list[max(0, h - 200):h]
        events = [breakout_at_close(window, atr, h1_window)]
        if sweep_possible[q]:
            pools = pools_before(window, h1_window, atr, last_open)
            events.append(sweep_at_close(window, pools, atr, coin_trend(h1_window)))
        events = [e for e in events if e]
        if not events:
            continue
        now_ms = cut + 5_000
        base = tier0_at(now_ms)
        for event in events:
            sig = dict(base)
            sig.update(is_setup=True, is_structured=False, is_tier_0_anomaly=False, active_phases=[],
                       long_score=0, short_score=0, alert_type='LONG' if event['direction'] > 0 else 'SHORT')
            sig.update(event)
            sig.update(context_at(now_ms))
            last = flow_by_ts.get(int(c15_list[q][0]), {})
            for k2 in ('spot_delta_1h', 'perp_delta_1h', 'perp_led_long', 'perp_led_short', 'funding_rate'):
                sig[k2] = last.get(k2)
            emit(now_ms, sig, float(c15_list[q][4]))

    # ---------------------------------------------------------------- Tier-0 anomalies on qualifying minutes
    t0cfg = CONFIG.tier0
    closes = fut[:, 4]
    with np.errstate(divide='ignore', invalid='ignore'):
        ch5 = np.abs(closes[5:] / closes[:-5] - 1)
        avg = (qv_cum[DAY_MINUTES:] - qv_cum[:-DAY_MINUTES]) / DAY_MINUTES
    price_idx = np.flatnonzero(ch5 > 0.8 * t0cfg.price_change_5m_threshold) + 5
    rv_idx = np.flatnonzero((fut[DAY_MINUTES - 1:, 6] > 0.8 * t0cfg.rvol_1m_threshold * avg[:len(fut) - DAY_MINUTES + 1])
                            & (fut[DAY_MINUTES - 1:, 6] >= t0cfg.rvol_min_minute_usd)) + DAY_MINUTES - 1
    oi_idx = []
    if len(oi_pts) > 1:
        oi_v = np.asarray([p[1] for p in oi_pts])
        big = np.flatnonzero(np.abs(oi_v[1:] / oi_v[:-1] - 1) > 0.8 * t0cfg.oi_change_5m_threshold) + 1
        oi_idx = [int(np.searchsorted(m_ts, oi_ts[b], side='right')) - 1 for b in big]
    minutes_to_check = sorted(set(price_idx.tolist()) | set(rv_idx.tolist()) | {i for i in oi_idx if i >= 0})
    probe_rows, probe_meta = [], []
    for i in minutes_to_check:
        now_ms = float(m_ts[i]) + MINUTE_MS       # the minute's close: its final kline is what the live loop reads
        m = tier0_at(now_ms)
        probe_rows.append({'symbol': key, **{c: v for c, v in m.items() if isinstance(v, (int, float)) and v is not None}})
        probe_meta.append((now_ms, m, float(closes[i])))
    if probe_rows:
        flagged = scorer.flag_tier_0_anomaly(pl.DataFrame(probe_rows, infer_schema_length=None))
        for n, (now_ms, m, price) in enumerate(probe_meta):
            if not flagged['is_tier_0_anomaly'][n]:
                continue
            q = int(np.searchsorted(scored_ts, now_ms - QUARTER_MS, side='right')) - 1   # the last CLOSED candle
            full = scored_row(q)
            full.update(m)
            full['is_tier_0_anomaly'] = True
            full['rule_anomaly'] = True
            full['liq_cascade'] = False
            sig = scorer.signal_from_row(full)
            if sig:
                sig.update(context_at(now_ms))
                emit(now_ms, sig, price)

    # ---------------------------------------------------------------- the journal's cooldown, labels
    candidates.sort(key=lambda c: c[0])
    last_logged: Dict[str, Tuple[int, int]] = {}
    cooldown = CONFIG.journal.cooldown_sec * 1000
    rows = []
    for ts, kind, group_key, direction, price, sig in candidates:
        family, rank = event_family(group_key)
        last_ts, last_rank = last_logged.get(family, (0, -1))
        if ts - last_ts < cooldown and rank <= last_rank:
            continue
        last_logged[family] = (ts, rank)
        if ts // 86_400_000 not in days_ok:
            continue            # the coin was not in the universe that day (volume floor / listing age, past data)
        r4 = ret_4h(ts, price)
        if r4 is None:
            continue
        rows.append({**sig, 'ts': ts, 'symbol': key, 'kind': kind, 'group_key': group_key, 'direction': direction,
                     'price': price, 'ret_4h': r4})

    # On disk, not returned: ~500k rows of all coins as Python objects in the main process were ~2 GB
    series = fut_all.select('timestamp', 'close', 'ret_std', 'predicted_funding', 'oi_change_short', 'rvol')
    # above the weekly EMA at each candle's close (the market's weekly breadth, like the scanner's breadth_w)
    above = []
    for t, c in zip(series['timestamp'].to_list(), series['close'].to_list()):
        tw = trend_w_of(weekly_at(t + QUARTER_MS), c)
        above.append(None if tw is None else float(tw > 0))
    series = series.with_columns(pl.Series('above_w', above, dtype=pl.Float64))
    series.with_columns(pl.lit(key).alias('symbol')).write_parquet(paths['series'])
    # 5m closes: the label's universe baseline at <= 5 min from any signal (15m put minute rows up to 15 min off)
    c5 = _bucket(fut, 5 * MINUTE_MS)
    pl.DataFrame({'timestamp': c5[:, 0].astype(np.int64), 'close': c5[:, 4], 'symbol': [key] * len(c5)}).write_parquet(
        paths['series5'])
    pl.DataFrame(rows, infer_schema_length=None).write_parquet(paths['rows']) if rows else \
        pl.DataFrame({'ts': []}, schema={'ts': pl.Int64}).write_parquet(paths['rows'])
    return {'key': key, 'n': len(rows), **paths}


def _weekly_closes(archive, fut_id: str, start: date, end: date) -> np.ndarray:
    """
    [close time ms, close] of the futures' COMPLETE weekly candles (Monday 00:00 UTC weeks, like Binance's 1w) from the
    archive's daily candles since ~16 months before the window (weekly_ref needs 21 closed weeks). The archive is
    point-in-time and reachable where the REST API is not.
    """
    daily = archive.klines_1d('futures', fut_id, start - timedelta(days=480), end)
    if len(daily) == 0:
        return np.empty((0, 2))
    week_ms, offset = 7 * 86_400_000, 4 * 86_400_000          # 1970-01-01 was a Thursday
    weeks: Dict[int, Tuple[float, float]] = {}
    for ts, close, _ in daily:
        start_ms = int((ts - offset) // week_ms * week_ms + offset)
        if start_ms not in weeks or ts > weeks[start_ms][0]:
            weeks[start_ms] = (ts, close)
    out = [[w + week_ms, c] for w, (last_ts, c) in sorted(weeks.items())
           if last_ts >= w + week_ms - 86_400_000]          # the week's last day is in: the week closed
    return np.asarray(out, dtype=float).reshape(-1, 2)


def _paths(fut_id: str, start_iso: str, end_iso: str, days: frozenset = frozenset()) -> Dict[str, str]:
    import hashlib
    import os
    # the logic version and the coin's eligible days are part of the name: rows of older signal logic or of another
    # volume floor are never resumed
    tag = hashlib.sha1(','.join(map(str, sorted(days))).encode()).hexdigest()[:8]
    stem = os.path.join(CONFIG.pretrain.cache_dir, 'rows',
                        f"{fut_id}_{start_iso}_{end_iso}_{tag}_{CONFIG.journal.logic_version}")
    return {'rows': stem + '.rows.parquet', 'series': stem + '.series.parquet', 'series5': stem + '.series5.parquet'}


def _sig_keys() -> set:
    """What the journal row, the veto and P(edge) read from a signal (journal._base_row / _features / veto_reason)."""
    from journal import FEATURE_KEYS
    return set(FEATURE_KEYS.values()) | {
        'long_score', 'short_score', 'active_phases', 'is_tier_0_anomaly', 'tier2_active', 'rvol_1m', 'oi_change_5m',
        'price_change_5m', 'delta_ratio', 'funding_rate', 'whale_net_5m', 'agg_ready', 'cluster', 'sec_into_quarter',
        'has_spot', 'perp_led_long', 'perp_led_short', 'spot_cvd_5m', 'futures_cvd_5m', 'futures_cvd', 'agg_cvd_5m',
        'venues_active', 'is_setup', 'is_structured', 'setup_note'}


_SIG_KEYS: Optional[set] = None


def _small(sig: Dict) -> Dict:
    """The fields of a signal the journal row / P(edge) read, not the whole scored frame row."""
    global _SIG_KEYS
    if _SIG_KEYS is None:
        _SIG_KEYS = _sig_keys()
    return {k: v for k, v in sig.items() if k in _SIG_KEYS and (k == 'active_phases' or
                                                               isinstance(v, (int, float, str, bool, type(None))))}


# ====================================================================== market-wide pass (main process)

def _forward_stats(series: pl.DataFrame, step_ms: int, horizon_ms: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    (grid of candle open times, the median and the mean over coins of close[t + horizon] / close[t] - 1 from each
    candle's close). The median labels P(edge) (a balanced 'beat the median coin'); the mean is the Edge baseline:
    coins beat the median by ~0.11% per 4h on average (right-skewed returns), the mean has zero excess by construction.
    """
    closes = series.select('symbol', 'timestamp', 'close').pivot(on='symbol', index='timestamp', values='close')
    ts = closes['timestamp'].to_numpy().astype(np.int64)
    grid = np.arange(ts.min(), ts.max() + step_ms, step_ms, dtype=np.int64)
    C = np.full((len(grid), closes.width - 1), np.nan, dtype=np.float32)
    C[((ts - grid[0]) // step_ms).astype(int)] = closes.drop('timestamp').to_numpy().astype(np.float32)
    k = horizon_ms // step_ms
    fwd = np.full_like(C, np.nan)
    fwd[:-k] = C[k:] / C[:-k] - 1
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        med = np.nanmedian(fwd, axis=1)
        mean = np.nanmean(fwd, axis=1)
    few = np.sum(~np.isnan(fwd), axis=1) < 20
    med[few] = np.nan
    mean[few] = np.nan
    return grid, med, mean


def _market_series(series: pl.DataFrame) -> Dict[str, object]:
    """
    Per 15m candle (open time) on a regular grid: the median 1h / 4h move of every coin to that candle's close, BTC's
    1h move, and the median forward 4h move from that close (the label's universe baseline). Vectorized: a
    Python lookup per journal row over every coin took minutes per 10k rows.
    """
    closes = series.select('symbol', 'timestamp', 'close').pivot(on='symbol', index='timestamp', values='close')
    ts = closes['timestamp'].to_numpy().astype(np.int64)
    grid = np.arange(ts.min(), ts.max() + QUARTER_MS, QUARTER_MS, dtype=np.int64)
    C = np.full((len(grid), closes.width - 1), np.nan)
    C[((ts - grid[0]) // QUARTER_MS).astype(int)] = closes.drop('timestamp').to_numpy().astype(float)
    symbols = closes.drop('timestamp').columns

    def back(k: int) -> np.ndarray:
        out = np.full_like(C, np.nan)
        out[k:] = C[k:] / C[:-k] - 1
        return out

    def median(M: np.ndarray) -> np.ndarray:
        with np.errstate(all='ignore'):
            med = np.nanmedian(M, axis=1)
        med[np.sum(~np.isnan(M), axis=1) < 20] = np.nan
        return med

    fwd = np.full_like(C, np.nan)
    fwd[:-16] = C[16:] / C[:-16] - 1
    btc = C[:, symbols.index('BTC/USDT:USDT')] if 'BTC/USDT:USDT' in symbols else np.full(len(grid), np.nan)
    btc_1h = np.full(len(grid), np.nan)
    btc_1h[4:] = btc[4:] / btc[:-4] - 1
    # the share of coins above their weekly EMA (scanner: breadth_w); series cached by an older run have no above_w
    breadth = np.full(len(grid), np.nan)
    if 'above_w' in series.columns:
        above = series.select('symbol', 'timestamp', 'above_w').pivot(on='symbol', index='timestamp', values='above_w')
        A = np.full((len(grid), above.width - 1), np.nan)
        A[((above['timestamp'].to_numpy().astype(np.int64) - grid[0]) // QUARTER_MS).astype(int)] =             above.drop('timestamp').to_numpy().astype(float)
        n = np.sum(~np.isnan(A), axis=1)
        with np.errstate(all='ignore'):
            breadth = np.where(n >= 20, np.nansum(A, axis=1) / np.maximum(n, 1), np.nan)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return {'grid': grid, 'mkt_1h': median(back(4)), 'mkt_4h': median(back(16)), 'btc_1h': btc_1h,
                'fwd_4h': median(fwd), 'breadth_w': breadth}


def run(months: int, min_volume: float, workers: int, rate: float, limit: Optional[int] = None) -> Dict:
    import glob
    import os
    from journal import SignalJournal, _strategy_of, veto_reason
    from ml import RegimeModel, SuccessModel, label_of

    end = datetime.now(timezone.utc).date() - timedelta(days=1)
    start = end - timedelta(days=30 * months)
    from history import Archive
    coins = select_coins(Archive(rate_bytes=rate), start, end, min_volume)
    if limit:
        coins = coins[:limit]
    logger.info(f"pretrain: {len(coins)} coins, {start} .. {end}, {workers} workers, {rate / 1e6:.1f} MB/s total")
    jobs = [(key, fid, sid, start.isoformat(), end.isoformat(), rate / max(1, workers), days)
            for key, fid, sid, days in coins]
    results: List[Dict] = []
    started = time.time()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(process_coin, job): job[0] for job in jobs}
        for n, fut in enumerate(as_completed(futures), 1):
            key = futures[fut]
            try:
                res = fut.result()
            except Exception as e:
                logger.warning(f"pretrain: {key} failed ({type(e).__name__} {e})")
                continue
            if res:
                results.append(res)
            if n % 10 == 0 or n == len(jobs):
                logger.info(f"pretrain: {n}/{len(jobs)} coins in {time.time() - started:.0f}s "
                            f"({sum(r['n'] for r in results)} rows so far)")

    # ---------------------------------------------------------------- market series, regimes
    series = pl.concat([pl.read_parquet(r['series']) for r in results], how='diagonal_relaxed')
    market = _market_series(series)
    grid = market['grid']
    series5 = pl.concat([pl.read_parquet(r['series5']) for r in results], how='diagonal_relaxed')
    grid5, fwd5, fwd5_mean = _forward_stats(series5, 5 * MINUTE_MS, H4_MS)
    del series5

    def baseline_at(ts_ms: int, values: np.ndarray) -> Optional[float]:
        """The universe's 4h move (median or mean) from the last 5m close at or before the signal."""
        i = (ts_ms // (5 * MINUTE_MS) * 5 * MINUTE_MS - 5 * MINUTE_MS - int(grid5[0])) // (5 * MINUTE_MS)
        if 0 <= i < len(grid5):
            v = values[i]
            return None if v != v else float(v)
        return None

    def at(name: str, t: int) -> Optional[float]:
        i = (t - int(grid[0])) // QUARTER_MS
        if 0 <= i < len(grid):
            v = market[name][i]
            return None if v != v else float(v)
        return None

    regime_model = RegimeModel()
    regime_model.history = RegimeModel.market_features(series)
    del series
    regimes: Dict[int, str] = {}
    if len(regime_model.history) >= CONFIG.ml.regime_min_history:     # a --limit run of a few coins has no market
        regime_model.refit()
        regimes = regime_model.labels_walk_forward()    # known at each candle's time, no look-ahead
    logger.info(f"pretrain: regimes fitted on {len(regime_model.history)} market candles: "
                f"{sorted(set(regimes.values()))}")

    # ---------------------------------------------------------------- journal rows in time order, labels, learning
    rows_df = pl.concat([pl.read_parquet(r['rows']) for r in results if r['n']], how='diagonal_relaxed').sort('ts')
    recent: deque = deque()            # (ts, symbol, direction) of directional setups for the market crowd
    success = SuccessModel()
    edges: Dict[str, List[float]] = {}
    learned = 0
    out_dir = CONFIG.pretrain.dataset_path
    os.makedirs(out_dir, exist_ok=True)
    for old in glob.glob(os.path.join(out_dir, '*.parquet')):
        os.remove(old)
    part: List[Dict] = []
    parts = 0
    # audit N15: a label is learned only once it EXISTS - ret_4h of a row at T is known at T + 4h. predict(T) ->
    # learn(ret_4h(T)) -> predict(T + 1 min) put four future hours into the next prediction (p_before / prequential)
    import heapq
    maturing: List[tuple] = []          # (available_at ms, seq, row, label)
    seq = 0
    for sig in rows_df.iter_rows(named=True):
        ts, key, kind, group_key = sig.pop('ts'), sig.pop('symbol'), sig.pop('kind'), sig.pop('group_key')
        while maturing and maturing[0][0] <= ts:
            _, _, old_row, old_label = heapq.heappop(maturing)
            success.learn(old_row, old_label)
            learned += 1
        direction, price, r4 = sig.pop('direction'), sig.pop('price'), sig.pop('ret_4h')
        last_closed = (ts - 5_000) // QUARTER_MS * QUARTER_MS - QUARTER_MS      # the candle that just closed
        sig['mkt_1h'], sig['mkt_4h'] = at('mkt_1h', last_closed), at('mkt_4h', last_closed)
        sig['btc_1h'] = at('btc_1h', last_closed)
        sig['breadth_w'] = at('breadth_w', last_closed)
        sig['regime'] = regimes.get(last_closed)
        while recent and ts - recent[0][0] > CONFIG.market.cluster_window_sec * 1000:
            recent.popleft()
        if kind in ('setup', 'structured'):
            recent.append((ts, key, direction))
        sig['market_crowd'] = len({s for _, s, d in recent if d == direction})
        row = SignalJournal._base_row(ts, key, kind, group_key, direction, price, sig)
        row['vetoed'] = veto_reason(group_key, sig)
        row['strategy'] = _strategy_of(group_key)
        row['perp_led'] = int(bool(sig.get('perp_led_long') if direction > 0 else sig.get('perp_led_short')))
        row['ret_4h'] = r4
        # the universe baseline: the median move of every coin over the same 4h, from the last 5m close at or before
        # the signal (the 15m grid put a minute row's baseline up to 15 min before it)
        baseline = baseline_at(ts, fwd5)
        baseline_mean = baseline_at(ts, fwd5_mean)
        label = label_of(row, baseline)
        if label is None:
            continue
        part.append({'ts_ms': ts, 'symbol': key, 'kind': kind, 'group_key': group_key, 'direction': direction,
                     'ret_4h': r4, 'baseline_4h': baseline, 'baseline_mean_4h': baseline_mean, 'label': bool(label),
                     'p_before': success.predict(row), **SuccessModel.features(row)})
        heapq.heappush(maturing, (ts + 4 * 3_600_000, seq, row, label))
        seq += 1
        if baseline_mean is not None:
            edges.setdefault(group_key, []).append(direction * (r4 - baseline_mean))
        if len(part) >= 50_000:
            pl.DataFrame(part, infer_schema_length=None).write_parquet(os.path.join(out_dir, f"part-{parts:04d}.parquet"))
            parts, part = parts + 1, []
    if part:
        pl.DataFrame(part, infer_schema_length=None).write_parquet(os.path.join(out_dir, f"part-{parts:04d}.parquet"))
    # the offline fit before the live start: every label of the finished past is learned (no prediction after it)
    while maturing:
        _, _, old_row, old_label = heapq.heappop(maturing)
        success.learn(old_row, old_label)
        learned += 1

    summary = {g: (len(v), statistics.fmean(v)) for g, v in edges.items()}
    state = {
        'created': time.time(), 'start': start.isoformat(), 'end': end.isoformat(), 'coins': len(results),
        'rows': learned, 'logic_version': CONFIG.journal.logic_version,
        'success': success.state(), 'regime_history': regime_model.history, 'summary': summary,
    }
    with open(CONFIG.pretrain.path + '.tmp', 'wb') as fh:
        pickle.dump(state, fh)
    os.replace(CONFIG.pretrain.path + '.tmp', CONFIG.pretrain.path)
    logger.info(f"pretrain: P(edge) learned {learned} rows ({success.drifts} drift resets, accuracy "
                f"{(success.accuracy or 0):.1%}); saved {CONFIG.pretrain.path} in {time.time() - started:.0f}s")
    for g, (n, e) in sorted(summary.items(), key=lambda kv: -kv[1][0]):
        logger.info(f"pretrain:   {g:24} n={n:6}  Edge 4h {e * 100:+.3f}%")
    return state


def main():
    cfg = CONFIG.pretrain
    parser = argparse.ArgumentParser(description='Pretrain the models on the Binance public archive')
    parser.add_argument('--months', type=int, default=cfg.months)
    parser.add_argument('--min-volume', type=float, default=cfg.min_volume_usd)
    parser.add_argument('--workers', type=int, default=cfg.workers)
    parser.add_argument('--rate', type=float, default=cfg.download_bytes_per_sec, help='total download bytes / s')
    parser.add_argument('--limit', type=int, default=None, help='only the N most liquid coins (a quick run)')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-7s | %(message)s', datefmt='%H:%M:%S')
    import os
    # Below-normal CPU priority (the worker processes inherit it): the live bot shares the machine
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if os.name == 'nt' else 10)
    except Exception as e:
        errors.report('pretrain.priority', e, 'runs at normal priority beside the bot')
    lock = cfg.lock_path
    # one run at a time (the bot starts it weekly; a manual run while it is running would double the load)
    if os.path.exists(lock):
        try:
            pid = int(open(lock).read().strip() or 0)
            import psutil
            if pid and psutil.pid_exists(pid) and pid != os.getpid():
                logger.info(f"pretrain: already running (pid {pid}), not started")
                return
        except (ValueError, OSError, ImportError):
            pass
    with open(lock, 'w') as fh:
        fh.write(str(os.getpid()))
    try:
        run(args.months, args.min_volume, args.workers, args.rate, args.limit)
        # never shorter than the configured window: a short test run (--months 1) must not delete the long cache
        prune_cache(max(args.months, cfg.months))
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


def prune_cache(months: int):
    """Delete cached archive files older than the training window (+1 month): the cache would grow forever."""
    import os
    import re
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=30 * (months + 1))).isoformat()
    removed = 0
    for root, _, files in os.walk(CONFIG.pretrain.cache_dir):
        for name in files:
            m = re.search(r'(\d{4}-\d{2}(?:-\d{2})?)\.zip', name)
            if m and (m.group(1) + '-31')[:10] < cutoff:
                os.remove(os.path.join(root, name))
                removed += 1
    # per-coin rows / series of an older logic version are never read again (_paths names the version)
    rows_dir = os.path.join(CONFIG.pretrain.cache_dir, 'rows')
    if os.path.isdir(rows_dir):
        tag = f"_{CONFIG.journal.logic_version}."
        for name in os.listdir(rows_dir):
            if name.endswith('.parquet') and tag not in name:
                os.remove(os.path.join(rows_dir, name))
                removed += 1
    if removed:
        logger.info(f"pretrain: pruned {removed} cached files (older than {cutoff} or of older logic)")


if __name__ == '__main__':
    main()
