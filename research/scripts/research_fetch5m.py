"""Monthly 5m futures klines of the replay's coins (research/replay_summary.parquet) into history_cache via
history.Archive at a capped rate (the live bot shares the link). Input of research_optimize.py."""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import logging
import sys
from datetime import date, datetime, timezone

import polars as pl

from history import Archive

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', datefmt='%H:%M:%S')
rate = float(sys.argv[1]) if len(sys.argv) > 1 else 300_000
ent = pl.read_parquet('research/replay_summary.parquet', columns=['symbol', 'ts'])
t0 = datetime.fromtimestamp(ent['ts'].min() / 1000, timezone.utc).date()
t1 = datetime.fromtimestamp(ent['ts'].max() / 1000, timezone.utc).date()
arch = Archive(rate_bytes=rate)
for sym in ent['symbol'].unique().sort().to_list():
    code = sym.split(':')[0].replace('/', '')
    k = arch.klines_ohlc('futures', code, '5m', date(t0.year, t0.month, 1), t1)
    logging.info(f"{sym}: {len(k)} 5m candles ({arch.downloaded / 1e6:.0f} MB downloaded)")
