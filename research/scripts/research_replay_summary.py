"""Concatenate a replay run (replay.py: <run>/**/cards.parquet + entries.parquet) into one summary parquet - cards and
entries with a `stage` column, without the f_* feature columns - the input of research_optimize.py --replay.

    python research_replay_summary.py data/replay/run24m research/replay_summary_24m.parquet
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import glob
import os
import sys

import polars as pl

run, out = sys.argv[1], sys.argv[2]
parts = []
for stage, name in (('card', 'cards.parquet'), ('entry', 'entries.parquet')):
    for path in glob.glob(os.path.join(run, '**', name), recursive=True):
        df = pl.read_parquet(path)
        parts.append(df.select([c for c in df.columns if not c.startswith('f_')]).with_columns(pl.lit(stage).alias('stage')))
summary = pl.concat(parts, how='diagonal_relaxed')
summary.write_parquet(out)
print(f"{summary.height} rows ({summary.filter(pl.col('stage') == 'entry').height} entries) -> {out}")
