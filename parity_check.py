"""
Train / serve parity (ML_PLAN.md A4): the features the models learn from the ARCHIVE (pretrain.process_coin) must
be the features the bot journals LIVE for the same coin and moment. Run on the machine that holds signals.db:

    .venv\\Scripts\\python parity_check.py --days 5 --coins 20

For the coins with the most live 'setup' / 'structured' rows in the window (ending 2 days ago: the archive's daily
files are published the next day), the archive replay is run over the same days, rows are matched on (symbol,
group_key, ts within `--tolerance-sec`) and every journal feature column (journal.FEATURE_KEYS) is compared: share of
matched rows whose values agree within 5% relative (or 1e-6 absolute), and the median relative error. Columns that
disagree are live-only (other venues, books, liquidations) or a parity bug; the report says which.
Writes research/parity.md.
"""
import argparse
import os
import sqlite3
from datetime import datetime, timedelta, timezone

import numpy as np
import polars as pl

_ROOT = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(_ROOT, 'research', 'parity.md')
DB_PATH = os.path.join(_ROOT, 'signals.db')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=5)
    ap.add_argument('--coins', type=int, default=20)
    ap.add_argument('--tolerance-sec', type=int, default=120)
    args = ap.parse_args()
    from config import CONFIG
    from history import Archive
    from journal import FEATURE_KEYS
    from pretrain import process_coin, select_coins

    end = datetime.now(timezone.utc).date() - timedelta(days=2)
    start = end - timedelta(days=args.days)
    lo = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp() * 1000)
    hi = int(datetime(end.year, end.month, end.day, tzinfo=timezone.utc).timestamp() * 1000) + 86_400_000
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    cols = [r[1] for r in con.execute('PRAGMA table_info(signals)')]
    feat_cols = [c for c in FEATURE_KEYS if c in cols]
    live = pl.read_database(
        f"SELECT ts_ms, symbol, group_key, {', '.join(feat_cols)} FROM signals "
        f"WHERE ts_ms >= ? AND ts_ms < ? AND kind IN ('setup', 'structured')", con,
        execute_options={'parameters': [lo, hi]}, infer_schema_length=None)
    con.close()
    if live.is_empty():
        print('no live rows in the window')
        return
    top = live.group_by('symbol').len().sort('len', descending=True)['symbol'].head(args.coins).to_list()
    coins = {k: (k, f, s, d) for k, f, s, d in select_coins(Archive(rate_bytes=4e6), start, end,
                                                            CONFIG.pretrain.min_volume_usd)}
    arch_rows = []
    for sym in top:
        if sym not in coins:
            continue
        k, f, s, days = coins[sym]
        res = process_coin((k, f, s, start.isoformat(), end.isoformat(), 4e6, days))
        if res and res['n']:
            arch_rows.append(pl.read_parquet(res['rows']))
    if not arch_rows:
        print('no archive rows')
        return
    arch = pl.concat(arch_rows, how='diagonal_relaxed')
    arch = arch.select(['ts', 'symbol', 'group_key'] + [pl.col(FEATURE_KEYS[c]).alias(c) for c in feat_cols
                                                        if FEATURE_KEYS[c] in arch.columns])
    arch = arch.rename({'ts': 'ts_ms'}).with_columns(pl.col('ts_ms').cast(pl.Int64)).sort('ts_ms')
    live = live.filter(pl.col('symbol').is_in(top)).with_columns(pl.col('ts_ms').cast(pl.Int64)).sort('ts_ms')
    joined = live.join_asof(arch, on='ts_ms', by=['symbol', 'group_key'], tolerance=args.tolerance_sec * 1000,
                            strategy='nearest', suffix='_arch')
    matched = joined.filter(pl.col('ts_ms').is_not_null())
    lines = [f"# Train / serve parity ({start} .. {end}, {len(top)} coins)", '',
             f"{live.height} live rows, {arch.height} archive rows; a row matches on symbol + group_key within "
             f"{args.tolerance_sec}s.", '',
             '| Column | matched | agree (5% rel) | median rel. error | verdict |', '|---|---:|---:|---:|---|']
    for c in feat_cols:
        if f"{c}_arch" not in matched.columns:
            lines.append(f"| {c} | 0 | — | — | not in the archive rows (live-only) |")
            continue
        both = matched.select(pl.col(c).cast(pl.Float64, strict=False).alias('a'),
                              pl.col(f"{c}_arch").cast(pl.Float64, strict=False).alias('b')).drop_nulls()
        if both.is_empty():
            lines.append(f"| {c} | 0 | — | — | no overlap |")
            continue
        a, b = both['a'].to_numpy(), both['b'].to_numpy()
        rel = np.abs(a - b) / np.maximum(np.maximum(np.abs(a), np.abs(b)), 1e-12)
        agree = float(np.mean((rel <= 0.05) | (np.abs(a - b) <= 1e-6)))
        verdict = 'ok' if agree >= 0.9 else 'CHECK' if agree >= 0.5 else 'MISMATCH'
        lines.append(f"| {c} | {len(a)} | {agree:.0%} | {np.median(rel):.3f} | {verdict} |")
    text = '\n'.join(lines) + '\n'
    with open(REPORT_PATH, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)


if __name__ == '__main__':
    main()
