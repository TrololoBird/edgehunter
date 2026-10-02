"""
Historical Edge of every setup on the pretraining dataset (pretrain_rows/: every labelled row the bot would have
written over the archive window, with its label and baseline), with the same statistics the live journal uses:

- Edge 4h = the 4h return in the signal's direction minus the universe MEAN over the same window (coins beat the
  median by ~0.11% per 4h on average - right-skewed returns - so the median favoured every long);
- 90% block-bootstrap interval (4h blocks of one direction resampled together: one market move = one cluster);
- Benjamini-Hochberg q-value over every setup (many setups at once make some "significant" by chance);
- Edge beta: the baseline scaled by the coin's beta to the universe (7 days of hourly returns before the signal's
  day, Blume-adjusted), from the per-coin series pretraining caches;
- stability: Edge in the first and the second half of the window (a real edge shows in both);
- the coin's 1h trend vs the signal (with / against / none): the split the live filters use.

Only setups the archive can produce appear (phases, sweeps, breakouts, impulses): absorption, cascades and whale
labels need live data. Run: .venv\\Scripts\\python research_edges.py [--path pretrain_rows] [--out research_edges.md]
"""
import argparse
import glob
import os
import random
from typing import Dict, Tuple

import numpy as np
import polars as pl

from config import CONFIG

H4 = 4 * 3_600_000
HOUR = 3_600_000
DAY = 86_400_000


from validation import BOOT, bh, block_stats  # noqa: E402,F401  (moved to validation.py, re-exported)


def coin_betas(series_glob: str) -> Dict[Tuple[str, int], float]:
    """(symbol, day) -> Blume-adjusted beta of the coin's hourly returns to the universe median over the 7 days before."""
    files = glob.glob(series_glob)
    if not files:
        return {}
    s = pl.concat([pl.read_parquet(f, columns=['symbol', 'timestamp', 'close']) for f in files], how='vertical_relaxed')
    # the 15m candle opening on the hour; series of overlapping windows repeat candles
    s = s.filter(pl.col('timestamp') % HOUR == 0).unique(['symbol', 'timestamp'], keep='first')
    wide = s.pivot(on='symbol', index='timestamp', values='close').sort('timestamp')
    ts = wide['timestamp'].to_numpy()
    symbols = [c for c in wide.columns if c != 'timestamp']
    C = wide.drop('timestamp').to_numpy().astype(float)
    R = np.full_like(C, np.nan)
    R[1:] = C[1:] / C[:-1] - 1
    with np.errstate(all='ignore'):
        mkt = np.nanmedian(R, axis=1)
    out: Dict[Tuple[str, int], float] = {}
    days = np.unique(ts // DAY)
    for day in days:
        lo, hi = np.searchsorted(ts, (day - 7) * DAY), np.searchsorted(ts, day * DAY)
        if hi - lo < 48:
            continue
        m, Rw = mkt[lo:hi], R[lo:hi]
        ok_m = ~np.isnan(m)
        for j, sym in enumerate(symbols):
            ok = ok_m & ~np.isnan(Rw[:, j])
            if ok.sum() < 48:
                continue
            x, y = m[ok], Rw[ok, j]
            var = ((x - x.mean()) ** 2).sum()
            if var > 0:
                beta = ((x - x.mean()) * (y - y.mean())).sum() / var
                out[(sym, int(day))] = 0.67 * beta + 0.33
    return out


def mean_baseline(df: pl.DataFrame, ts: np.ndarray, series5_glob: str) -> np.ndarray:
    """
    The universe's MEAN 4h move from the last 5m close at or before each row: coins beat the median by ~0.11% per 4h
    on average (right-skewed returns), so an Edge against the median favours every long and penalises every short.
    From the dataset when pretraining stored it, else rebuilt from the cached 5m series.
    """
    if 'baseline_mean_4h' in df.columns and df['baseline_mean_4h'].null_count() < df.height:
        return df['baseline_mean_4h'].to_numpy().astype(float)
    from pretrain import _forward_stats
    files = glob.glob(series5_glob)
    s5 = pl.concat([pl.read_parquet(f) for f in files], how='vertical_relaxed').unique(['symbol', 'timestamp'])
    grid, _, mean = _forward_stats(s5, 300_000, H4)
    i = (ts // 300_000 * 300_000 - 300_000 - int(grid[0])) // 300_000
    ok = (i >= 0) & (i < len(grid))
    out = np.full(len(ts), np.nan)
    out[ok] = mean[i[ok]]
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--path', default=CONFIG.pretrain.dataset_path)
    parser.add_argument('--series', default=os.path.join(CONFIG.pretrain.cache_dir, 'rows',
                                                         f"*_{CONFIG.journal.logic_version}.series.parquet"))
    parser.add_argument('--out', default='research_edges.md')
    args = parser.parse_args()
    path = os.path.join(args.path, '*.parquet') if os.path.isdir(args.path) else args.path
    # the parts carry different one-hot columns (setups / regimes seen so far): union them
    df = pl.concat([pl.read_parquet(f) for f in sorted(glob.glob(path))], how='diagonal_relaxed').sort('ts_ms')
    df = df.filter(pl.col('direction') != 0)
    betas = coin_betas(args.series)
    d = df['direction'].to_numpy().astype(float)
    ts = df['ts_ms'].to_numpy().astype(np.int64)
    ret = df['ret_4h'].to_numpy().astype(float)
    base = mean_baseline(df, ts, args.series.replace('.series.parquet', '.series5.parquet'))
    sym = df['symbol'].to_list()
    beta = np.asarray([betas.get((s, int(t // DAY)), np.nan) for s, t in zip(sym, ts)])
    keep = np.isfinite(base)
    d, ts, ret, base, beta = d[keep], ts[keep], ret[keep], base[keep], beta[keep]
    df = df.filter(pl.Series(keep))
    sym = df['symbol'].to_list()
    edge = d * (ret - base)
    edge_b = d * (ret - np.where(np.isnan(beta), 1.0, beta) * base)
    block = (ts // H4) * 2 + (d > 0)
    trend = df['coin_trend_dir'].to_numpy().astype(float) if 'coin_trend_dir' in df.columns else np.full(len(df), np.nan)
    mid = ts.min() + (ts.max() - ts.min()) // 2
    groups = df['group_key'].to_list()
    keys = sorted(set(groups), key=lambda g: -groups.count(g))
    garr = np.asarray(groups)

    rows = []
    for g in keys:
        m = garr == g
        if m.sum() < 30:
            continue
        mean, lo, hi, p, k = block_stats(edge[m], block[m])
        mb, lob, hib, pb, _ = block_stats(edge_b[m], block[m])
        h1 = m & (ts < mid)
        h2 = m & (ts >= mid)
        e1 = float(edge[h1].mean()) if h1.any() else float('nan')
        e2 = float(edge[h2].mean()) if h2.any() else float('nan')
        splits = {}
        for name, cond in (('with', trend > 0), ('against', trend < 0), ('flat', trend == 0)):
            mm = m & cond
            splits[name] = (float(edge[mm].mean()) if mm.sum() >= 30 else float('nan'), int(mm.sum()))
        rows.append(dict(setup=g, n=int(m.sum()), blocks=k, edge=mean, lo=lo, hi=hi, p=p, edge_b=mb, lob=lob, hib=hib,
                         pb=pb, h1=e1, h2=e2, cov=float(np.isfinite(beta[m]).mean()), **{f"t_{n}": v for n, v in splits.items()}))
    qs = bh([r['p'] for r in rows])
    qbs = bh([r['pb'] for r in rows])
    for r, q, qb in zip(rows, qs, qbs):
        r['q'], r['qb'] = q, qb

    pctf = lambda v: '—' if v != v else f"{v * 100:+.3f}%"  # noqa: E731
    lines = [f"# Historical Edge by setup (pretraining rows, logic {CONFIG.journal.logic_version})", '',
             f"Window {pl.from_epoch(pl.Series([ts.min()]), 'ms')[0]:%Y-%m-%d} .. {pl.from_epoch(pl.Series([ts.max()]), 'ms')[0]:%Y-%m-%d}, "
             f"{len(df)} directional rows, {df['symbol'].n_unique()} coins. Edge = 4h return in the signal's direction minus the "
             f"universe MEAN (the median favours every long by ~0.11%); [90%] block bootstrap (4h x direction blocks); q = Benjamini-Hochberg over all setups; "
             f"Edge β = baseline x the coin's Blume-adjusted 7-day beta; halves = Edge in the first / second half of the "
             f"window; trend = the coin's 1h trend vs the signal (N >= 30). No execution costs: a round trip costs "
             f"~{(CONFIG.journal.fee_round_trip + 2 * CONFIG.levels.slippage_bps / 1e4) * 100:.2f}% (fees + slippage).", '',
             '| Setup | N | blocks | Edge 4h [90%] | q | Edge β [90%] | q β | 1st half | 2nd half | with trend | against | no trend |',
             '|---|---:|---:|---|---:|---|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        lines.append(
            f"| {r['setup']} | {r['n']} | {r['blocks']} | {pctf(r['edge'])} [{pctf(r['lo'])}..{pctf(r['hi'])}] | "
            f"{r['q']:.3f} | {pctf(r['edge_b'])} [{pctf(r['lob'])}..{pctf(r['hib'])}] | {r['qb']:.3f} | {pctf(r['h1'])} | "
            f"{pctf(r['h2'])} | {pctf(r['t_with'][0])} ({r['t_with'][1]}) | {pctf(r['t_against'][0])} ({r['t_against'][1]}) | "
            f"{pctf(r['t_flat'][0])} ({r['t_flat'][1]}) |")
    text = '\n'.join(lines) + '\n'
    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)


if __name__ == '__main__':
    random.seed(0)
    main()
