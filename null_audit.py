"""
Null-world audit (ML_PLAN.md A3, after "Spurious Predictability in Financial ML", arXiv 2604.15531): the research
pipelines run on data that has NO predictability by construction. A pipeline that still "finds" an edge there is
broken (look-ahead, leakage, a cost or label bug), whatever it reports on the real data.

- `archive`: every 1m candle series (futures, spot, the BTC / ETH correlate) is rebuilt from the coin's real minutes
  with the HOURS shuffled within each week - the same permutation for every symbol and market, so the coins stay
  aligned with each other and the volatility of the week is kept, but structure longer than an hour (trends, levels,
  sweeps of yesterday's high) is random. research_cards / research_classic are replayed in-process on a few coins.
  Expected: gross R ~ 0, net R ~ minus the cost, nothing beats its placebo.
  Daily files (Connors' RSI(2)) get their days permuted inside 28-day blocks the same way.
- `ml`: ml_eval's walk-forward + CPCV on the pretraining rows with the labels shuffled within each week. Expected:
  AUC ~ 0.5, log-loss skill <= 0, PBO ~ 0.5, the top 20% not better than all rows.

    python null_audit.py archive --coins 8 --months 3
    python null_audit.py ml
"""
import argparse
import os
import sys
from datetime import date, timedelta

import numpy as np

HOUR_MS = 3_600_000
WEEK_MS = 7 * 86_400_000
_ROOT = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(_ROOT, 'research', 'null_audit.md')


def shuffle_hours(arr: np.ndarray, seed: int = 20261002) -> np.ndarray:
    """1m klines [ts, o, h, l, c, v, qv, tbq] with whole hours permuted inside each week, prices re-chained."""
    if len(arr) < 2:
        return arr
    ts = arr[:, 0]
    hour = (ts // HOUR_MS).astype(np.int64)
    week = (ts // WEEK_MS).astype(np.int64)
    prev_c = np.r_[arr[0, 1], arr[:-1, 4]]
    gap = arr[:, 1] / prev_c                     # open vs the previous close
    rel = arr[:, 2:5] / arr[:, 1:2]              # high / low / close vs the minute's own open
    order = []
    for w in np.unique(week):
        hours = np.unique(hour[week == w])
        # one permutation per week number: identical for every symbol and market (coins stay aligned)
        perm = np.random.default_rng(seed + int(w)).permutation(len(hours))
        for h in hours[perm]:
            order.append(np.flatnonzero(hour == h))
    idx = np.concatenate(order)
    out = arr.copy()
    g, r = gap[idx], rel[idx]
    g[0] = 1.0
    opens = np.empty(len(idx))
    price = arr[0, 1]
    for i in range(len(idx)):                    # re-chain: open_i = close_{i-1} x gap_i
        price = price * g[i]
        opens[i] = price
        price = price * r[i, 2]
    out[:, 1] = opens
    out[:, 2:5] = opens[:, None] * r
    out[:, 5:] = arr[idx, 5:]                    # volume and taker flow travel with their minute
    return out                                   # timestamps stay in order: the shuffled minutes take them


def shuffle_days(arr: np.ndarray, seed: int = 20261002) -> np.ndarray:
    """Daily klines [ts, o, h, l, c, qv] with the days permuted inside 28-day blocks, prices re-chained."""
    if len(arr) < 2:
        return arr
    block = (arr[:, 0] // (28 * 86_400_000)).astype(np.int64)
    prev_c = np.r_[arr[0, 1], arr[:-1, 4]]
    gap, rel = arr[:, 1] / prev_c, arr[:, 2:5] / arr[:, 1:2]
    idx = np.concatenate([np.flatnonzero(block == b)[np.random.default_rng(seed + int(b)).permutation(
        int((block == b).sum()))] for b in np.unique(block)])
    out = arr.copy()
    price = arr[0, 1]
    for i, j in enumerate(idx):
        price = price * (gap[j] if i else 1.0)
        out[i, 1] = price
        out[i, 2:5] = price * rel[j]
        price = out[i, 4]
    out[:, 5:] = arr[idx, 5:]
    return out


def patch_archive():
    import history
    real = history.Archive.klines_1m
    real_ohlc = history.Archive.klines_ohlc

    def klines_1m(self, market, symbol, start, end):
        return shuffle_hours(real(self, market, symbol, start, end))

    def klines_ohlc(self, market, symbol, interval, start, end):
        arr = real_ohlc(self, market, symbol, interval, start, end)
        return shuffle_days(arr) if interval == '1d' else arr    # RSI(2) / Turtles read daily files directly
    history.Archive.klines_1m = klines_1m
    history.Archive.klines_ohlc = klines_ohlc


def run_archive(args) -> str:
    patch_archive()
    import polars as pl
    from history import Archive
    from pretrain import select_coins
    import research_cards
    import research_classic
    end = date.fromisoformat(args.end)
    start = end - timedelta(days=30 * args.months)
    coins = select_coins(Archive(rate_bytes=4e7), start, end, 3e6)[:args.coins]
    cards, classic = [], []
    for k, f, s, days in coins:
        print(f"null world: {k}", flush=True)
        rows, _ = research_cards.replay_coin((k, f, s, start.isoformat(), end.isoformat(), days, 'all'))
        cards += rows
        classic += research_classic.replay_coin((k, f, s, start.isoformat(), end.isoformat(), days))
    lines = [f"# Null-world audit ({len(coins)} coins, {start} .. {end}, hours shuffled within each week)", '',
             'Expected on a world without structure: gross R ~ 0, net R ~ -cost, no setup above its placebo.', '',
             '## research_cards (card replay)', '', '| Setup | entries | mean R TP1 | placebo | system - placebo [90%] |',
             '|---|---:|---:|---:|---|']
    from validation import block_stats

    def diff_ci(g, r_col, p_col):
        g = g.filter(pl.col(r_col).is_not_null() & pl.col(p_col).is_not_null())
        if g.height < 10:
            return '—'
        d = (g[r_col] - g[p_col]).to_numpy().astype(float)
        mean, lo, hi, _, _ = block_stats(d, g['ts_ms'].to_numpy() // (4 * HOUR_MS))
        return f"{mean:+.3f} [{lo:+.3f}..{hi:+.3f}]"

    if cards:
        df = pl.DataFrame(cards, infer_schema_length=None)
        e = df.filter((pl.col('status') == 'ENTRY') & pl.col('r_tp1').is_not_null())
        for setup in sorted(e['setup'].unique().to_list()):
            g = e.filter(pl.col('setup') == setup)
            pl_mean = g['pl_r_tp1'].mean() if 'pl_r_tp1' in g.columns else None
            lines.append(f"| {setup} | {g.height} | {g['r_tp1'].mean():+.3f} | "
                         f"{'—' if pl_mean is None else f'{pl_mean:+.3f}'} | "
                         f"{diff_ci(g, 'r_tp1', 'pl_r_tp1') if 'pl_r_tp1' in g.columns else '—'} |")
    lines += ['', '## research_classic', '', '| Setup | trades | mean | placebo | system - placebo [90%] |',
              '|---|---:|---:|---:|---|']
    if classic:
        df = pl.DataFrame(classic, infer_schema_length=None)
        for setup in sorted(df['setup'].unique().to_list()):
            g = df.filter(pl.col('setup') == setup)
            lines.append(f"| {setup} | {g.height} | {g['r'].mean():+.3f} | {g['pl_r'].mean():+.3f} | "
                         f"{diff_ci(g, 'r', 'pl_r')} |")
    return '\n'.join(lines) + '\n'


def run_ml(args) -> str:
    import glob
    import io
    import contextlib
    import polars as pl
    import ml_eval
    from config import CONFIG
    path = CONFIG.pretrain.dataset_path
    files = sorted(glob.glob(os.path.join(path, '*.parquet'))) if os.path.isdir(path) else [path]
    df = pl.concat([pl.read_parquet(f) for f in files], how='diagonal_relaxed').sort('ts_ms')
    week = (df['ts_ms'].to_numpy() // WEEK_MS)
    y = df['label'].to_numpy().copy()
    rng = np.random.default_rng(7)
    for w in np.unique(week):                     # labels shuffled within each week: base rate kept, link broken
        m = np.flatnonzero(week == w)
        y[m] = y[rng.permutation(m)]
    df = df.with_columns(pl.Series('label', y))
    X, _ = ml_eval.matrix(df)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ml_eval.cpcv_report(df, X, df['label'].cast(pl.Float64).to_numpy(), ml_eval.uniqueness(df['ts_ms'].to_numpy()),
                            6, 2, args.max_rows)
    return ('# Null-world audit of ml_eval (labels shuffled within each week)\n\nExpected: AUC ~ 0.5, log-loss skill '
            '<= 0, PBO ~ 0.5, top 20% ~ all rows.\n\n```\n' + buf.getvalue() + '```\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=('archive', 'ml'))
    ap.add_argument('--coins', type=int, default=8)
    ap.add_argument('--months', type=int, default=3)
    ap.add_argument('--end', default='2026-09-30')
    ap.add_argument('--max-rows', type=int, default=200_000)
    args = ap.parse_args()
    text = run_archive(args) if args.mode == 'archive' else run_ml(args)
    mode = 'a' if os.path.exists(REPORT_PATH) else 'w'
    with open(REPORT_PATH, mode, encoding='utf-8') as fh:
        fh.write(text + '\n')
    sys.stdout.write(text)


if __name__ == '__main__':
    main()
