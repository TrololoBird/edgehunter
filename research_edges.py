"""
Historical Edge of every setup on the pretraining dataset (pretrain_rows/: every labelled row the bot would have
written over the archive window, with its label and baseline), with the same statistics the live journal uses:

- Edge 4h = the 4h return in the signal's direction minus the universe median over the same window;
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
from typing import Dict, List, Tuple

import numpy as np
import polars as pl

from config import CONFIG

H4 = 4 * 3_600_000
HOUR = 3_600_000
DAY = 86_400_000
BOOT = 2000


def block_stats(values: np.ndarray, blocks: np.ndarray, seed: int = 7) -> Tuple[float, float, float, float, int]:
    """(mean, lo, hi, two-sided p, number of blocks): 90% interval and p of the mean from a block bootstrap."""
    order = np.argsort(blocks, kind='stable')
    v, b = values[order], blocks[order]
    starts = np.flatnonzero(np.r_[True, b[1:] != b[:-1]])
    sums = np.add.reduceat(v, starts)
    counts = np.diff(np.r_[starts, len(v)])
    k = len(sums)
    if k < 5:
        return float(values.mean()) if len(values) else float('nan'), float('nan'), float('nan'), float('nan'), k
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, k, size=(BOOT, k))
    means = sums[idx].sum(axis=1) / counts[idx].sum(axis=1)
    lo, hi = np.quantile(means, [0.05, 0.95])
    below = float((means <= 0).mean())
    p = min(1.0, 2 * min(below, 1 - below) + 1 / BOOT)
    return float(values.mean()), float(lo), float(hi), p, k


def bh(pvalues: List[float]) -> List[float]:
    """Benjamini-Hochberg q-values (NaN stays NaN)."""
    idx = sorted((p, i) for i, p in enumerate(pvalues) if p == p)
    q = [float('nan')] * len(pvalues)
    running, m = 1.0, len(idx)
    for rank in range(m, 0, -1):
        p, i = idx[rank - 1]
        running = min(running, p * m / rank)
        q[i] = running
    return q


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
    ret, base = df['ret_4h'].to_numpy().astype(float), df['baseline_4h'].to_numpy().astype(float)
    ts = df['ts_ms'].to_numpy().astype(np.int64)
    sym = df['symbol'].to_list()
    beta = np.asarray([betas.get((s, int(t // DAY)), np.nan) for s, t in zip(sym, ts)])
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
             f"universe median; [90%] block bootstrap (4h x direction blocks); q = Benjamini-Hochberg over all setups; "
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
