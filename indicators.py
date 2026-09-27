import bisect
import math
import polars as pl
from typing import Dict, Optional, Sequence, Tuple
from collections import deque
import time
import ccxt
from config import CONFIG

# Candle size of the stored frames, e.g. 15m -> 900_000
TIMEFRAME_MS = ccxt.Exchange.parse_timeframe(CONFIG.timeframe.rest_timeframe) * 1000

# Raw columns kept on MarketData.spot_df / futures_df. Indicators are derived from these every scan.
RAW_SCHEMA = {
    'timestamp': pl.Int64,
    'open': pl.Float64,
    'high': pl.Float64,
    'low': pl.Float64,
    'close': pl.Float64,
    'volume': pl.Float64,
    'quote_volume': pl.Float64,
    # taker buy quote volume - taker sell quote volume for the candle (per-candle CVD delta)
    'taker_delta': pl.Float64,
    # futures only: open interest (base units) at candle close; null on spot
    'open_interest': pl.Float64,
}


def empty_raw_frame() -> pl.DataFrame:
    return pl.DataFrame(schema=RAW_SCHEMA)


def _safe_div(num: pl.Expr, den: pl.Expr) -> pl.Expr:
    return pl.when(den != 0).then(num / den).otherwise(None)


def _over(expr: pl.Expr) -> pl.Expr:
    """Window expressions run per symbol, so one Polars pass covers every symbol."""
    return expr.over('symbol')


def compute_indicators_batch(frames: Dict[str, pl.DataFrame], funding: Dict[str, Tuple[float, float]]) -> pl.DataFrame:
    """
    Derive every indicator the scorer needs for many symbols at once: the raw frames (RAW_SCHEMA, including the
    live in-progress last row) are stacked with a 'symbol' column and each rolling/shift/cumulative expression runs
    `.over('symbol')`. One query over ~30k rows replaces hundreds of tiny per-symbol queries (~20x faster).
    No global drop_nulls(): new listings with short history keep their rows and nulls are handled per expression.
    `funding` maps symbol -> (funding_rate, predicted_funding), both 8h-normalized.
    """
    parts = [(s, f) for s, f in frames.items() if f is not None and not f.is_empty()]
    if not parts:
        return pl.DataFrame(schema={'symbol': pl.String, **RAW_SCHEMA})

    cfg = CONFIG.metrics
    symbols = [s for s, _ in parts]
    df = pl.concat([f for _, f in parts], how='vertical').with_columns(
        pl.Series('symbol', [s for s, f in parts for _ in range(f.height)], dtype=pl.String)
    )
    fund = pl.DataFrame({
        'symbol': symbols,
        'funding_rate': [funding.get(s, (0.0, 0.0))[0] for s in symbols],
        'predicted_funding': [funding.get(s, (0.0, 0.0))[1] for s in symbols],
    }, schema={'symbol': pl.String, 'funding_rate': pl.Float64, 'predicted_funding': pl.Float64})
    df = df.join(fund, on='symbol', how='left', maintain_order='left')

    close, high, low, quote_vol = pl.col('close'), pl.col('high'), pl.col('low'), pl.col('quote_volume')
    delta = pl.col('taker_delta').fill_null(0.0)
    # Average of the previous candles only, so a spike doesn't dilute its own baseline
    sma_vol = _over(quote_vol.shift(1).rolling_mean(window_size=cfg.rvol_window, min_samples=cfg.rvol_window // 2))
    bb_mid = _over(close.rolling_mean(window_size=20, min_samples=10))
    bb_std = _over(close.rolling_std(window_size=20, min_samples=10))
    prior_low = _over(low.rolling_min(window_size=cfg.spring_lookback, min_samples=cfg.spring_lookback // 2).shift(1))
    prior_range_high = _over(high.rolling_max(window_size=cfg.spring_lookback, min_samples=cfg.spring_lookback // 2).shift(1))
    prior_high = _over(high.rolling_max(window_size=cfg.local_high_window, min_samples=cfg.local_high_window // 2).shift(1))
    open_interest = _over(pl.col('open_interest').forward_fill())
    candle_minutes = TIMEFRAME_MS / 60_000

    def flow(window: int) -> pl.Expr:
        # Net taker flow over the window as a share of its volume: +0.1 = buyers took 55% of the volume
        return _safe_div(_over(delta.rolling_sum(window_size=window, min_samples=1)),
                         _over(quote_vol.rolling_sum(window_size=window, min_samples=1)))

    df = df.with_columns(
        _over(pl.max_horizontal(high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs())
              .rolling_mean(window_size=14, min_samples=7)).alias('atr'),
        sma_vol.alias('sma_vol_50'),
        _safe_div(quote_vol, sma_vol).alias('rvol'),
        (bb_mid - 2 * bb_std).alias('bb_lower'),
        (bb_mid + 2 * bb_std).alias('bb_upper'),
        _safe_div(4 * bb_std, bb_mid).alias('bb_width'),
        _over(close.pct_change(cfg.price_flat_window)).alias('price_change_flat'),
        (_over(high.rolling_max(window_size=cfg.price_flat_window, min_samples=cfg.price_flat_window // 2)) -
         _over(low.rolling_min(window_size=cfg.price_flat_window, min_samples=cfg.price_flat_window // 2))).alias('flat_range'),
        (high >= prior_high).alias('is_local_high'),
        prior_low.alias('prior_low'),
        prior_range_high.alias('prior_range_high'),
        (prior_range_high - prior_low).alias('prior_range'),
        # Net move over the spring lookback before this candle (a range drifts little; a channel is a trend)
        _over(close.shift(1) - close.shift(cfg.spring_lookback)).abs().alias('prior_drift'),
        (low < prior_low).alias('pierced_recent_low'),
        (_safe_div(close - low, high - low) > 0.7).alias('long_lower_wick'),
        # Cumulative CVD over the frame: cvd[t] > cvd[t-1] exactly when candle t had net taker buying
        _over(delta.cum_sum()).alias('cvd'),
        # Candle delta as a share of its volume: -0.2 means taker sells were 60% of the candle
        _safe_div(pl.col('taker_delta'), quote_vol).alias('delta_ratio'),
        flow(cfg.price_flat_window).alias('flow_flat'),
        flow(cfg.cvd_divergence_lookback).alias('flow_divergence'),
        _over(open_interest.pct_change(cfg.oi_change_window)).alias('oi_change_pct'),
        _over(open_interest.pct_change(cfg.price_flat_window)).alias('oi_change_flat'),
        _over(open_interest.pct_change(cfg.oi_short_window)).alias('oi_change_short'),
        # Net taker flow (USD) and its share of volume over the spot-vs-perp window (1h)
        _over(delta.rolling_sum(window_size=cfg.spot_perp_window, min_samples=1)).alias('delta_1h'),
        flow(cfg.spot_perp_window).alias('flow_1h'),
        # Average minute of the candle: the spring "test" compares the pullback's 1m volume with it
        (quote_vol / candle_minutes).alias('candle_minute_usd'),
        # Typical 15m move of price and OI (~24h std): Tier-0 z-scores divide 5m moves by std / sqrt(3)
        _over(close.pct_change().rolling_std(window_size=96, min_samples=24)).alias('ret_std'),
        _over(open_interest.pct_change().rolling_std(window_size=96, min_samples=24)).alias('oi_std'),
    )
    # Squeeze: width within a small tolerance of its lookback minimum (exact float equality with a rolling
    # minimum fails on rounding noise even for a perfectly flat range)
    return df.with_columns(
        (pl.col('bb_width') <= _over(pl.col('bb_width').rolling_min(
            window_size=cfg.bbw_squeeze_lookback, min_samples=cfg.bbw_squeeze_lookback // 2
        )) * cfg.bbw_squeeze_tolerance).alias('is_squeezed'),
    )


def compute_indicators(raw_df: pl.DataFrame, funding_rate: float = 0.0, predicted_funding: float = 0.0) -> pl.DataFrame:
    """Single-symbol convenience wrapper around compute_indicators_batch (keeps a constant 'symbol' column)."""
    if raw_df is None or raw_df.is_empty():
        return raw_df
    return compute_indicators_batch({'_': raw_df}, {'_': (funding_rate, predicted_funding)})


def merge_live_candle(raw_df: pl.DataFrame, row: Optional[dict], finalized_until: int = 0) -> Tuple[pl.DataFrame, bool]:
    """
    Replace (same candle) or append (new candle) a kline row; keeps the last rest_lookback_candles rows.
    Returns (frame, needs_backfill): backfill when a candle is skipped or the previous candle was never
    finalized (e.g. stream reconnect, or a candle closed between the REST download and the first WS update).
    """
    if not row:
        return raw_df, False
    if raw_df is None or raw_df.is_empty():
        return raw_df, True

    last_ts = raw_df['timestamp'][-1]
    ts = row['timestamp']
    if ts < last_ts:
        return raw_df, False

    needs_backfill = False
    if ts == last_ts:
        raw_df = raw_df.slice(0, raw_df.height - 1)
    else:
        needs_backfill = ts > last_ts + TIMEFRAME_MS or last_ts > finalized_until

    new_row = pl.DataFrame({c: [row.get(c)] for c in raw_df.columns}, schema=raw_df.schema)
    # rechunk: repeated vstacks otherwise leave ~100 chunks per frame and slow every later query
    return raw_df.vstack(new_row).tail(CONFIG.timeframe.rest_lookback_candles).rechunk(), needs_backfill


# Tier-0 metrics per symbol (live, from stream data). minute_usd: quote volume of the last 60s (an RVOL spike only
# counts on a minute of real size); *_z: 5m moves in units of the coin's typical 5m move; liq_*: liquidation USD
# over 5m (all venues; Binance's feed is sampled); cluster: +1/-1 algo cluster running; sec_into_quarter: seconds
# since the last :00/:15/:30/:45 (algo bursts); agg_*: all futures venues; top_venue_*: the venue that carried the
# 5m net flow; spot_cvd_5m: spot net taker flow (Binance spot 1m klines + spot venues).
TIER0_COLUMNS = (
    'rvol_1m', 'oi_change_5m', 'price_change_5m', 'whale_net_5m', 'minute_usd',
    'price_z', 'oi_z', 'avg_minute_usd', 'liq_long_5m', 'liq_short_5m', 'cluster', 'sec_into_quarter',
    'agg_cvd_5m', 'agg_oi_change_5m', 'top_venue_share', 'top_venue_net', 'venues_active', 'spot_cvd_5m',
    'futures_cvd_5m',
    # ml.AnomalyModel: IsolationForest score (lower = more unusual), its flag, and whether it is fitted
    'ml_score', 'ml_anomaly', 'ml_ready',
)

QUARTER_SEC = 900


def _base_sample(samples: Sequence[Tuple], since_ms: float):
    """First sample at or after since_ms (samples are time-ordered): bisect instead of a linear scan."""
    idx = bisect.bisect_left(samples, since_ms, key=lambda s: s[0])
    return samples[idx] if idx < len(samples) else None


def calculate_tier0_metrics(
    ticker_samples: deque,
    oi_samples: deque,
    minute_klines: deque,
    now_ms: Optional[float] = None,
    whale_trades: Optional[deque] = None,
    whale_threshold_usd: float = 0.0,
    ret_std: Optional[float] = None,
    oi_std: Optional[float] = None,
    avg_minute_usd: Optional[float] = None,
) -> Dict[str, float]:
    """
    Core Tier-0 raw impulse metrics from in-memory stream data (no REST, no Polars); the order-flow columns are
    filled in by the scanner from FlowStore / WhaleBook.

    rvol_1m: quote volume of the last 60 seconds from the futures 1m kline stream (the current minute plus the
    not-yet-elapsed share of the previous one) divided by the average minute of the last 24h.
    whale_net_5m: net whale flow over the window in units of the symbol's whale size (legacy input: whale_trades
    as (ts_ms, signed usd, ...) records; the scanner overrides it with WhaleBook.net_units).
    price_z / oi_z: the 5m change divided by the coin's typical 5m change (15m std / sqrt(3)); 0 when unknown.
    """
    now_ms = now_ms or time.time() * 1000
    t0 = CONFIG.tier0
    window_ms = t0.window_sec * 1000
    metrics = {c: 0.0 for c in TIER0_COLUMNS}
    metrics['sec_into_quarter'] = float(int(now_ms // 1000) % QUARTER_SEC)
    sqrt3 = math.sqrt(3)

    # Ignore stale streams so a dead socket can't pin a symbol as anomalous
    if ticker_samples and now_ms - ticker_samples[-1][0] < 60_000:
        ts_last, price_last, qv_24h = ticker_samples[-1]

        base = _base_sample(ticker_samples, now_ms - window_ms)
        # The baseline must really be ~5m old (after a stream gap the first sample could be seconds old)
        if base is not None and base[0] <= now_ms - 0.8 * window_ms and base[1] > 0:
            metrics['price_change_5m'] = price_last / base[1] - 1
            if ret_std:
                metrics['price_z'] = metrics['price_change_5m'] / (ret_std / sqrt3)

        avg_minute = avg_minute_usd or qv_24h / 1440
        metrics['avg_minute_usd'] = avg_minute
        if minute_klines and avg_minute > 0:
            cur_open, cur_quote = minute_klines[-1][0], minute_klines[-1][5]
            elapsed = min(max((now_ms - cur_open) / 60_000, 0.0), 1.0)
            prev = minute_klines[-2] if len(minute_klines) >= 2 and minute_klines[-2][0] == cur_open - 60_000 else None
            if now_ms - cur_open < 120_000:
                if prev is not None:
                    last_60s = cur_quote + prev[5] * (1 - elapsed)
                elif elapsed >= 0.5:
                    # Warm-up (no previous minute yet): project the current minute
                    last_60s = cur_quote / elapsed
                else:
                    last_60s = None
                if last_60s is not None:
                    metrics['rvol_1m'] = last_60s / avg_minute
                    metrics['minute_usd'] = last_60s

    if whale_trades and whale_threshold_usd > 0:
        net = sum(t[1] for t in whale_trades if t[0] >= now_ms - window_ms)
        metrics['whale_net_5m'] = net / whale_threshold_usd

    oi_interval_ms = CONFIG.timeframe.oi_update_interval_sec * 1000
    if len(oi_samples) >= 2 and now_ms - oi_samples[-1][0] < 3 * oi_interval_ms:
        ts_oi, oi_last = oi_samples[-1]
        # Baseline: the newest sample at least 0.8 window older than the last one, and not older than 1.6 windows
        # (OI arrives about once a minute, sometimes later: a fixed narrow slot often held no sample)
        idx = bisect.bisect_right(oi_samples, ts_oi - 0.8 * window_ms, key=lambda s: s[0]) - 1
        base = oi_samples[idx] if idx >= 0 else None
        if base is not None and ts_oi - base[0] <= 1.6 * window_ms and base[1] > 0:
            metrics['oi_change_5m'] = oi_last / base[1] - 1
            if oi_std:
                metrics['oi_z'] = metrics['oi_change_5m'] / (oi_std / sqrt3)

    return metrics


def minute_delta(minute_klines: Sequence[Sequence[float]], now_ms: float, window_sec: int = 300) -> float:
    """Net taker flow (USD) of 1m klines [t, o, h, l, c, quote, taker_buy_quote] overlapping the last window."""
    cutoff = now_ms - window_sec * 1000
    return sum(2 * c[6] - c[5] for c in minute_klines if c[0] + 60_000 > cutoff)
