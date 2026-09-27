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
import argparse
import json
import logging
import pickle
import statistics
import time
import urllib.request
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

def select_coins(min_volume: float) -> List[Tuple[str, str, Optional[str]]]:
    """(journal key, futures id, spot id or None) of every trading USDT perpetual above the volume floor."""
    info = json.load(urllib.request.urlopen('https://fapi.binance.com/fapi/v1/exchangeInfo', timeout=60))
    tickers = json.load(urllib.request.urlopen('https://fapi.binance.com/fapi/v1/ticker/24hr', timeout=60))
    spot_info = json.load(urllib.request.urlopen('https://api.binance.com/api/v3/exchangeInfo?permissions=SPOT',
                                                 timeout=60))
    spot_ids = {s['symbol'] for s in spot_info.get('symbols', []) if s.get('status') == 'TRADING'}
    volume = {t['symbol']: float(t.get('quoteVolume') or 0) for t in tickers}
    excluded = set(CONFIG.exchange.excluded_underlying_types)
    out = []
    for s in info.get('symbols', []):
        if (s.get('contractType') != 'PERPETUAL' or s.get('quoteAsset') != 'USDT' or s.get('status') != 'TRADING'
                or s.get('underlyingType') in excluded or volume.get(s['symbol'], 0) < min_volume):
            continue
        base = s['baseAsset']
        key = f"{base}/USDT:USDT"
        spot = f"{base}USDT" if f"{base}USDT" in spot_ids else None
        if spot is None:
            for prefix in ('1000000', '1000', '1M'):
                if base.startswith(prefix) and f"{base[len(prefix):]}USDT" in spot_ids:
                    spot = f"{base[len(prefix):]}USDT"
                    break
        out.append((key, s['symbol'], spot))
    out.sort(key=lambda c: -volume.get(c[1], 0))
    return out


# ====================================================================== per coin (worker process)

def _bucket(arr: np.ndarray, ms: int) -> np.ndarray:
    """1m rows [ts, o, h, l, c, v, qv, tbq] -> candles of `ms` (the last, possibly incomplete one dropped)."""
    if len(arr) == 0:
        return np.empty((0, 8))
    b = (arr[:, 0] // ms) * ms
    idx = np.flatnonzero(np.r_[True, b[1:] != b[:-1]])
    last = np.r_[idx[1:] - 1, len(arr) - 1]
    out = np.column_stack([b[idx], arr[idx, 1], np.maximum.reduceat(arr[:, 2], idx),
                           np.minimum.reduceat(arr[:, 3], idx), arr[last, 4], np.add.reduceat(arr[:, 5], idx),
                           np.add.reduceat(arr[:, 6], idx), np.add.reduceat(arr[:, 7], idx)])
    return out[:-1]


def _raw_frame(c: np.ndarray, oi: Optional[Dict[int, float]]) -> pl.DataFrame:
    from indicators import RAW_SCHEMA
    return pl.DataFrame({
        'timestamp': c[:, 0].astype(np.int64), 'open': c[:, 1], 'high': c[:, 2], 'low': c[:, 3], 'close': c[:, 4],
        'volume': c[:, 5], 'quote_volume': c[:, 6], 'taker_delta': 2 * c[:, 7] - c[:, 6],
        'open_interest': [oi.get(int(t)) for t in c[:, 0]] if oi is not None else [None] * len(c),
    }, schema=RAW_SCHEMA)


def _asof(ts: np.ndarray, values: np.ndarray, at: float) -> Optional[float]:
    i = int(np.searchsorted(ts, at, side='right')) - 1
    return float(values[i]) if i >= 0 else None


def process_coin(job: tuple) -> Optional[Dict]:
    """
    One coin: download, build the live data structures from history, and produce the journal rows the bot would
    have written (without the cross-coin context, added in the main process) plus the market series.
    """
    key, fut_id, spot_id, start_iso, end_iso, rate = job
    from history import Archive
    from indicators import calculate_tier0_metrics, compute_indicators_batch, minute_delta
    from journal import classify, event_family
    from scorer import PhaseScorer
    from strategies.breakout import breakout_at_close
    from strategies.level import sweep_at_close
    from strategies.structure import coin_trend, pools_before, recent_atr

    import os
    paths = _paths(fut_id, start_iso, end_iso)
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
    h1_list = [[r[0], r[1], r[2], r[3], r[4], r[6], r[7]] for r in h1]
    h1_close_ts = h1[:, 0] + HOUR_MS if len(h1) else np.empty(0)
    c15_list = [[r[0], r[1], r[2], r[3], r[4], r[6], r[7]] for r in c15]

    def tier0_at(now_ms: float) -> Dict[str, float]:
        """calculate_tier0_metrics exactly as the scanner calls it, on the history up to now_ms."""
        i = int(np.searchsorted(m_ts, now_ms - MINUTE_MS + 1, side='right'))      # minutes opened <= now - 1m
        j = int(np.searchsorted(m_ts, now_ms, side='right'))
        minutes = deque(stream_rows(fut, j - 30, j), maxlen=240)
        ticker = deque(((k[0] + 59_999, k[4], 0.0) for k in stream_rows(fut, i - 10, i)), maxlen=400)
        k = int(np.searchsorted(oi_ts, now_ms, side='right')) if len(oi_ts) else 0
        oi = deque(oi_pts[max(0, k - 13):k], maxlen=64)
        n = min(j, DAY_MINUTES)
        avg_minute = (qv_cum[j] - qv_cum[j - n]) / max(1, n) if n else 0.0
        q = int(np.searchsorted(fut_ind[:, 0], now_ms - QUARTER_MS, side='right')) - 1
        ret_std = fut_ind[q, 1] if q >= 0 and fut_ind[q, 1] == fut_ind[q, 1] else None
        oi_std = fut_ind[q, 2] if q >= 0 and fut_ind[q, 2] == fut_ind[q, 2] else None
        m = calculate_tier0_metrics(ticker, oi, minutes, now_ms, ret_std=ret_std, oi_std=oi_std,
                                    avg_minute_usd=avg_minute)
        m['futures_cvd_5m'] = minute_delta(minutes, now_ms)
        if len(s_ts):
            js = int(np.searchsorted(s_ts, now_ms, side='right'))
            m['spot_cvd_5m'] = minute_delta(stream_rows(spot, js - 6, js), now_ms)
        m['whale_net_5m'] = None        # no historical sweeps: the feature is learned live only
        m['volume_24h'] = qv_cum[j] - qv_cum[max(0, j - DAY_MINUTES)]
        return m

    def context_at(now_ms: float) -> Dict:
        """The coin's own context (the market's is added in the main process)."""
        out: Dict = {}
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
        now_ms = float(m_ts[i]) + 59_000          # late in the minute, as the 2s Tier-0 loop sees it
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
        r4 = ret_4h(ts, price)
        if r4 is None:
            continue
        rows.append({**sig, 'ts': ts, 'symbol': key, 'kind': kind, 'group_key': group_key, 'direction': direction,
                     'price': price, 'ret_4h': r4})

    # On disk, not returned: ~500k rows of all coins as Python objects in the main process were ~2 GB
    series = fut_all.select('timestamp', 'close', 'ret_std', 'predicted_funding', 'oi_change_short', 'rvol')
    series.with_columns(pl.lit(key).alias('symbol')).write_parquet(paths['series'])
    pl.DataFrame(rows, infer_schema_length=None).write_parquet(paths['rows']) if rows else \
        pl.DataFrame({'ts': []}, schema={'ts': pl.Int64}).write_parquet(paths['rows'])
    return {'key': key, 'n': len(rows), **paths}


def _paths(fut_id: str, start_iso: str, end_iso: str) -> Dict[str, str]:
    import os
    stem = os.path.join(CONFIG.pretrain.cache_dir, 'rows', f"{fut_id}_{start_iso}_{end_iso}")
    return {'rows': stem + '.rows.parquet', 'series': stem + '.series.parquet'}


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
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return {'grid': grid, 'mkt_1h': median(back(4)), 'mkt_4h': median(back(16)), 'btc_1h': btc_1h,
                'fwd_4h': median(fwd)}


def run(months: int, min_volume: float, workers: int, rate: float, limit: Optional[int] = None) -> Dict:
    import glob
    import os
    from journal import SignalJournal, _strategy_of, veto_reason
    from ml import RegimeModel, SuccessModel, label_of

    end = datetime.now(timezone.utc).date() - timedelta(days=1)
    start = end - timedelta(days=30 * months)
    coins = select_coins(min_volume)
    if limit:
        coins = coins[:limit]
    logger.info(f"pretrain: {len(coins)} coins, {start} .. {end}, {workers} workers, {rate / 1e6:.1f} MB/s total")
    jobs = [(key, fid, sid, start.isoformat(), end.isoformat(), rate / max(1, workers)) for key, fid, sid in coins]
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
    series = pl.concat([pl.read_parquet(r['series']) for r in results], how='vertical_relaxed')
    market = _market_series(series)
    grid = market['grid']

    def at(name: str, t: int) -> Optional[float]:
        i = (t - int(grid[0])) // QUARTER_MS
        if 0 <= i < len(grid):
            v = market[name][i]
            return None if v != v else float(v)
        return None

    regime_model = RegimeModel()
    regime_model.history = RegimeModel.market_features(series)
    del series
    regime_model.refit()
    regimes = regime_model.labels_walk_forward()        # known at each candle's time, no look-ahead
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
    for sig in rows_df.iter_rows(named=True):
        ts, key, kind, group_key = sig.pop('ts'), sig.pop('symbol'), sig.pop('kind'), sig.pop('group_key')
        direction, price, r4 = sig.pop('direction'), sig.pop('price'), sig.pop('ret_4h')
        last_closed = (ts - 5_000) // QUARTER_MS * QUARTER_MS - QUARTER_MS      # the candle that just closed
        sig['mkt_1h'], sig['mkt_4h'] = at('mkt_1h', last_closed), at('mkt_4h', last_closed)
        sig['btc_1h'] = at('btc_1h', last_closed)
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
        # the universe baseline: the median move of every coin over the same 4h, from the close the signal saw
        baseline = at('fwd_4h', last_closed)
        label = label_of(row, baseline)
        if label is None:
            continue
        part.append({'ts_ms': ts, 'symbol': key, 'kind': kind, 'group_key': group_key, 'direction': direction,
                     'ret_4h': r4, 'baseline_4h': baseline, 'label': bool(label),
                     'p_before': success.predict(row), **SuccessModel.features(row)})
        success.learn(row, label)
        learned += 1
        edges.setdefault(group_key, []).append(direction * (r4 - baseline))
        if len(part) >= 50_000:
            pl.DataFrame(part, infer_schema_length=None).write_parquet(os.path.join(out_dir, f"part-{parts:04d}.parquet"))
            parts, part = parts + 1, []
    if part:
        pl.DataFrame(part, infer_schema_length=None).write_parquet(os.path.join(out_dir, f"part-{parts:04d}.parquet"))

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
    except Exception:
        pass
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
    if removed:
        logger.info(f"pretrain: pruned {removed} cached files older than {cutoff}")


if __name__ == '__main__':
    main()
