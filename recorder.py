"""
Data recorder: the live-only inputs the Binance public archive does not have, written to Parquet so they can be
tested offline later (as filters for 1h-4h trades, never as tick strategies: a manual entry is seconds late).

- flow:  per second x venue x coin, taker buy / sell USD, long / short liquidation USD, trade count (all six venues;
         the FlowStore ring buffers, so nothing new is streamed). Every Binance / Bybit / OKX liquidation event is
         already kept one by one in the journal's `liquidations` table.
- depth: each 500-level REST book of the hot coins (~40, every 60s): best bid / ask, and USD resting in 0.1% bands
         from the mid out to 5% per side (flat columns bid_00..bid_49 / ask_00..ask_49), plus the live top-20
         metrics (spread, band depth / imbalance, persistent walls).
- deriv: per minute x venue x coin, OI (coins and USD), mark, 8h funding (Bybit / OKX / Bitget / Hyperliquid OI is
         not in any public archive).

Layout: <root>/<kind>/date=YYYY-MM-DD/HHMM.parquet per minute, merged into HH.parquet once the hour is over.

The event loop only copies the finished minute out of the ring buffers (numpy slices, ~1 ms) and hands it to the
bot's worker PROCESS (the level-map pool); building frames and writing Parquet happen there, so disk I/O and
polars never hold the loop's GIL.
"""
import glob
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

N_BANDS = 50            # 0.1% bands out to 5% on each side of the mid
BAND = 0.001


# ------------------------------------------------------------------------------------------------ loop side

def flow_minute(flow_store, minute_start_sec: int) -> Optional[Dict]:
    """
    The non-zero cells of one finished minute of every venue's ring buffer. Seconds after a venue's head
    (`last_sec`) are masked: their slots still hold data from one ring period ago.
    """
    rows = flow_store.rows
    if not rows:
        return None
    symbols = [None] * (max(rows.values()) + 1)
    for s, r in rows.items():
        symbols[r] = s
    secs = np.arange(minute_start_sec, minute_start_sec + 60)
    parts = []
    for v_idx, (venue, vf) in enumerate(flow_store.venues.items()):
        if vf.last_sec == 0 or minute_start_sec <= vf.last_sec - vf.H:
            continue
        valid = secs <= vf.last_sec
        if not valid.any():
            continue
        slots = secs[valid] % vf.H
        n_rows = min(len(symbols), vf.data.shape[2])
        data = vf.data[slots][:, :, :n_rows]                    # (s, 4, rows) copy
        counts = vf.counts[slots][:, :n_rows]
        s_idx, r_idx = np.nonzero((data.sum(axis=1) != 0) | (counts != 0))
        if not len(s_idx):
            continue
        parts.append((venue, secs[valid][s_idx].astype(np.int64), r_idx.astype(np.int32),
                      data[s_idx, :, r_idx].astype(np.float32), counts[s_idx, r_idx].astype(np.int32)))
    return {'symbols': symbols, 'parts': parts} if parts else None


def depth_rows(depth_book, since_ts: float) -> List[Dict]:
    """Every 500-level snapshot newer than since_ts: raw levels (bucketed in the worker) + live top-20 metrics."""
    out = []
    for symbol, book in list(depth_book.books.items()):
        if book.deep_ts <= since_ts or not book.deep_bids or not book.deep_asks:
            continue
        out.append({'symbol': symbol, 'ts': book.deep_ts, 'bids': list(book.deep_bids), 'asks': list(book.deep_asks),
                    'live': depth_book.metrics(symbol)})
    return out


def deriv_rows(venue_derivs: Dict, now_ms: float) -> List[tuple]:
    out = []
    for symbol, states in list(venue_derivs.items()):
        for venue, st in list(states.items()):
            if not st.ts or now_ms - st.ts > 600_000:
                continue
            oi = st.samples[-1][1] if st.samples else None
            out.append((symbol, venue, st.oi_usd or None, oi, st.mark or None, st.funding_8h))
    return out


# ------------------------------------------------------------------------------------------------ worker side

def _path(root: str, kind: str, ts_sec: float, minute: bool = True) -> str:
    t = datetime.fromtimestamp(ts_sec, tz=timezone.utc)
    folder = os.path.join(root, kind, f"date={t:%Y-%m-%d}")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{t:%H%M}.parquet" if minute else f"{t:%H}.parquet")


def _bands(levels, mid: float, side: int) -> List[float]:
    out = [0.0] * N_BANDS
    for p, q in levels:
        k = int(abs(p / mid - 1) / BAND)
        if k < N_BANDS and (p - mid) * side >= 0:
            out[k] += p * q
    return out


def write_minute(root: str, minute_start_sec: int, flow: Optional[Dict], depth: List[Dict], deriv: List[tuple]) -> int:
    """Worker process: one minute of each kind to its own file. Returns the rows written."""
    import polars as pl
    written = 0
    if flow:
        symbols = flow['symbols']
        frames = []
        for venue, ts, r_idx, vals, counts in flow['parts']:
            frames.append(pl.DataFrame({
                'ts': ts * 1000, 'venue': [venue] * len(ts), 'symbol': [symbols[r] for r in r_idx],
                'buy_usd': vals[:, 0], 'sell_usd': vals[:, 1], 'liq_long_usd': vals[:, 2], 'liq_short_usd': vals[:, 3],
                'trades': counts}))
        df = pl.concat(frames).with_columns(pl.col('ts').cast(pl.Datetime('ms', 'UTC')),
                                            pl.col('venue').cast(pl.Categorical), pl.col('symbol').cast(pl.Categorical))
        df.write_parquet(_path(root, 'flow', minute_start_sec), compression='zstd')
        written += df.height
    if depth:
        rows = []
        for d in depth:
            bid0, ask0 = d['bids'][0][0], d['asks'][0][0]
            mid = (bid0 + ask0) / 2
            row = {'ts': int(d['ts'] * 1000), 'symbol': d['symbol'], 'mid': mid, 'best_bid': bid0, 'best_ask': ask0,
                   'spread_bps': (ask0 - bid0) / mid * 1e4,
                   'bid_reach_pct': (1 - d['bids'][-1][0] / mid) * 100, 'ask_reach_pct': (d['asks'][-1][0] / mid - 1) * 100}
            for i, v in enumerate(_bands(d['bids'], mid, -1)):
                row[f'bid_{i:02d}'] = v
            for i, v in enumerate(_bands(d['asks'], mid, 1)):
                row[f'ask_{i:02d}'] = v
            for k, v in (d['live'] or {}).items():
                if k != 'mid':
                    row[f'live_{k}'] = float(v)
            rows.append(row)
        df = pl.DataFrame(rows, infer_schema_length=None).with_columns(
            pl.col('ts').cast(pl.Datetime('ms', 'UTC')), pl.col('symbol').cast(pl.Categorical))
        df.write_parquet(_path(root, 'depth', minute_start_sec), compression='zstd')
        written += df.height
    if deriv:
        df = pl.DataFrame(deriv, schema=[('symbol', pl.Utf8), ('venue', pl.Utf8), ('oi_usd', pl.Float64),
                                         ('oi_coins', pl.Float64), ('mark', pl.Float64), ('funding_8h', pl.Float64)],
                          orient='row').with_columns(
            pl.lit(minute_start_sec * 1000).cast(pl.Datetime('ms', 'UTC')).alias('ts'),
            pl.col('symbol').cast(pl.Categorical), pl.col('venue').cast(pl.Categorical))
        df.write_parquet(_path(root, 'deriv', minute_start_sec), compression='zstd')
        written += df.height
    return written


def compact(root: str, before_sec: float) -> int:
    """Worker process: merge the minute files of every hour that ended before `before_sec` into HH.parquet."""
    import polars as pl
    hours: Dict[str, List[str]] = {}
    for f in glob.glob(os.path.join(root, '*', 'date=*', '[0-9][0-9][0-9][0-9].parquet')):
        folder, name = os.path.split(f)
        day = os.path.basename(folder)[5:]
        start = datetime.strptime(f"{day} {name[:2]}", '%Y-%m-%d %H').replace(tzinfo=timezone.utc).timestamp()
        if start + 3600 <= before_sec:
            hours.setdefault(os.path.join(folder, f"{name[:2]}.parquet"), []).append(f)
    for target, files in hours.items():
        parts = [pl.read_parquet(f) for f in sorted(files)]
        if os.path.exists(target):
            parts.insert(0, pl.read_parquet(target))
        pl.concat(parts, how='diagonal_relaxed').write_parquet(target + '.tmp', compression='zstd')
        os.replace(target + '.tmp', target)
        for f in files:
            os.remove(f)
    return len(hours)


# ------------------------------------------------------------------------------------------------ loop task

def cfg_rec():
    from config import CONFIG
    return CONFIG.recorder


def prune(root: str, keep_days: int) -> None:
    """Delete day folders older than keep_days."""
    import shutil
    cutoff = datetime.now(timezone.utc).date().toordinal() - keep_days
    for folder in glob.glob(os.path.join(root, '*', 'date=*')):
        try:
            day = datetime.strptime(os.path.basename(folder)[5:], '%Y-%m-%d').date()
        except ValueError:
            continue
        if day.toordinal() < cutoff:
            shutil.rmtree(folder, ignore_errors=True)

def _log_failure(future) -> None:
    if not future.cancelled() and future.exception() is not None:
        logger.warning(f"Recorder write failed: {future.exception()!r}")


async def record_loop(fetcher, executor_fn, root: str, running) -> None:
    """
    Once a minute: the minute that ended >= 30s ago (venue lag) goes to the worker; hourly compaction there too.
    `executor_fn()` returns the worker pool (created lazily by the scanner); `running()` stops the loop.
    """
    import asyncio
    loop = asyncio.get_running_loop()
    last_minute = int(time.time() // 60) - 1
    last_depth = time.time()
    last_compact = 0.0
    pending = None
    while running():
        await asyncio.sleep(60 - (time.time() - 30) % 60 + 0.1)
        minute = int((time.time() - 30) // 60) - 1
        if minute <= last_minute:
            continue
        if pending is not None and not pending.done():
            logger.warning("Recorder: the previous write is still running, skipping a minute")
            continue
        try:
            import shutil
            if shutil.disk_usage(root if os.path.exists(root) else '.').free < cfg_rec().min_free_gb * 1e9:
                logger.warning(f"Recorder paused: less than {cfg_rec().min_free_gb:g} GB free on the disk")
                last_minute = minute
                continue
            # Minutes missed while the loop was busy are written too (the ring keeps 15 min for the short venues)
            flows = [(m, flow_minute(fetcher.flow, m * 60)) for m in range(max(last_minute + 1, minute - 10), minute + 1)]
            now = time.time()
            depth = depth_rows(fetcher.depth, last_depth)
            last_depth = now
            deriv = deriv_rows(fetcher.venue_derivs, now * 1000)
            last_minute = minute
            pool = executor_fn()
            for i, (m, flow) in enumerate(flows):
                last = i == len(flows) - 1
                pending = loop.run_in_executor(pool, write_minute, root, m * 60, flow,
                                               depth if last else [], deriv if last else [])
                pending.add_done_callback(_log_failure)
            if now - last_compact > 600:
                last_compact = now
                prune(root, cfg_rec().keep_days)
                loop.run_in_executor(pool, compact, root, now).add_done_callback(_log_failure)
        except Exception as e:
            logger.warning(f"Recorder: {e!r}")
