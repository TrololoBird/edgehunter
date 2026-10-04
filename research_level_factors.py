"""
Step 2 of the level rework (eng-59): which approach factors make a LEVEL hold better than a placebo price, on the
dataset of research_level_events.py (data/level_events/*.parquet). Pre-registered here before any result.

Outcome: b1 of the bounce trade (+1 = the 1R target first, -1 = the stop first, 0 = neither within the horizon) -
its mean is the gross expectancy in R of a 1:1 bounce. Edge of a group = mean b1 of REAL levels minus mean b1 of
their PLACEBO prices (same kind / time / rules, shifted beyond the zone): what the level adds beyond the price path.

1. Single factors. For each factor x level family (all; 15m; 1h; 4h; 1d / 1w / previous day / week), terciles are cut
   on the OLDER half's real events (touch / prior_bounces / swept: fixed bins). Effect = edge(T3) - edge(T1).
   A factor survives when the effect has the same sign in both halves AND the newer half's 90% interval (bootstrap of
   UTC days) excludes 0, with Benjamini-Hochberg q <= 0.10 over all factor x family tests of the newer half.
2. Combinations: LightGBM on the real events' factors (+ kind, tf) predicting b1 = +1, walk-forward by month (train on
   all months before); the same model class trained and scored on the placebo events. The model is useful for LEVELS
   only if the top decile of its real predictions beats the top decile of the placebo predictions (mean b1) in both
   halves with the newer half's 90% interval above 0.
Survivors go to signal generation (as journal features first, then as a filter / weight once live proves them).

Run: .venv\\Scripts\\python research_level_factors.py [--out research/level_factors.md]
"""
import argparse
import glob
import os
from typing import List, Optional, Tuple

import numpy as np
import polars as pl

FACTORS = ('age_h', 'width_atr', 'origin_atr', 'origin_vol', 'into_atr', 'speed_atr', 'run_atr', 'vol_ratio', 'delta',
           'range_pos', 'room_atr', 'ema_dev', 'trend_1d', 'trend_4h', 'er_4h', 'vol_regime', 'btc_1h', 'oi_1h')
BINNED = {'touch': [(1, 1), (2, 2), (3, 10_000)], 'prior_bounces': [(0, 0), (1, 1), (2, 10_000)],
          'swept': [(0, 0), (1, 1), (1, 1)]}
DAY_MS = 86_400_000


def family(tf: str, kind: str) -> str:
    if kind in ('pdhl', 'pwhl') or tf in ('1d', '1w'):
        return 'daily+'
    return tf or 'other'


def load(cols: List[str], limit: int = 0) -> pl.DataFrame:
    files = sorted(glob.glob(os.path.join('data', 'level_events', '*.parquet')))
    files = files[:limit] if limit else files
    return pl.concat([pl.read_parquet(f, columns=cols) for f in files], how='vertical_relaxed')


def day_sums(day: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    u, inv = np.unique(day, return_inverse=True)
    return u, np.bincount(inv, weights=y, minlength=len(u)), np.bincount(inv, minlength=len(u)).astype(float)


def boot_effect(groups, rng, draws: int = 1000) -> Optional[Tuple[float, float, float]]:
    """groups: {(tier, real): (day, b1)}; effect = (r3 - p3) - (r1 - p1); bootstrap of the union of days."""
    days = np.unique(np.concatenate([g[0] for g in groups.values()]))
    if len(days) < 30:
        return None
    pos = {d: i for i, d in enumerate(days)}
    sums = {}
    for key, (day, y) in groups.items():
        idx = np.array([pos[d] for d in day])
        sums[key] = (np.bincount(idx, weights=y, minlength=len(days)), np.bincount(idx, minlength=len(days)).astype(float))
    out = []
    for _ in range(draws):
        w = np.bincount(rng.integers(0, len(days), len(days)), minlength=len(days)).astype(float)
        m = {}
        for key, (s, n) in sums.items():
            nn = (n * w).sum()
            m[key] = (s * w).sum() / nn if nn else np.nan
        out.append((m[(2, 1)] - m[(2, 0)]) - (m[(0, 1)] - m[(0, 0)]))
    out = np.array(out)
    out = out[~np.isnan(out)]
    if len(out) < draws // 2:
        return None
    lo, hi = np.percentile(out, [5, 95])
    p = min(1.0, 2 * min((out <= 0).mean(), (out >= 0).mean()) + 1 / len(out))
    return float(lo), float(hi), float(p)


def tiers(x: np.ndarray, name: str, cuts) -> np.ndarray:
    if name in BINNED:
        t = np.full(len(x), -1)
        for k, (lo, hi) in enumerate(BINNED[name]):
            t[(x >= lo) & (x <= hi) & (t < 0)] = k
        if name == 'swept':
            t[t == 1] = 2                                   # 0 = no sweep (T1), 1 = swept (T3)
        return t
    q1, q2 = cuts
    return np.where(np.isnan(x), -1, np.where(x <= q1, 0, np.where(x <= q2, 1, 2)))


def edge(y, real, sel) -> float:
    r, p = y[sel & (real == 1)], y[sel & (real == 0)]
    return float(r.mean() - p.mean()) if len(r) >= 30 and len(p) >= 30 else np.nan


def single_factors(df: pl.DataFrame, mid: float, rng, lines: List[str]):
    tests = []
    fam = np.array([family(t, k) for t, k in zip(df['tf'].to_list(), df['kind'].to_list())])
    y = df['b1'].to_numpy().astype(float)
    real = 1 - df['placebo'].to_numpy()
    ts = df['ts'].to_numpy()
    day = (ts // DAY_MS).astype(np.int64)
    old, new = ts < mid, ts >= mid
    lines += ['## 1. Single factors: edge (real − placebo mean b1) by tercile', '',
              '| family | factor | half | T1 | T2 | T3 | effect T3−T1 |', '|---|---|---|---:|---:|---:|---:|']
    for f in ('all', '15m', '1h', '4h', 'daily+'):
        fsel = np.ones(len(df), bool) if f == 'all' else fam == f
        for name in FACTORS + tuple(BINNED):
            x = df[name].to_numpy().astype(float)
            ref = x[fsel & old & (real == 1) & ~np.isnan(x)]
            if name not in BINNED and len(ref) < 300:
                continue
            cuts = tuple(np.percentile(ref, [33.3, 66.7])) if name not in BINNED else None
            t = tiers(x, name, cuts)
            eff = {}
            for half, hsel in (('older', old), ('newer', new)):
                e = [edge(y, real, fsel & hsel & (t == k)) for k in range(3)]
                eff[half] = e[2] - e[0]
                lines.append(f"| {f} | {name} | {half} | " + ' | '.join(f"{v:+.3f}" for v in e) + f" | {eff[half]:+.3f} |")
            if np.isnan(eff['older']) or np.isnan(eff['newer']):
                continue
            groups = {(k, rl): (day[fsel & new & (t == k) & (real == rl)], y[fsel & new & (t == k) & (real == rl)])
                      for k in (0, 2) for rl in (0, 1)}
            if min(len(g[1]) for g in groups.values()) < 30:
                continue
            res = boot_effect(groups, rng)
            if res is not None:
                tests.append((f, name, eff['older'], eff['newer'], res))
    m = len(tests)
    order = sorted(range(m), key=lambda k: tests[k][4][2])
    q = [1.0] * m
    run = 1.0
    for pos in range(m - 1, -1, -1):
        k = order[pos]
        run = min(run, tests[k][4][2] * m / (pos + 1))
        q[k] = run
    lines += ['', '### Verdict', '', '| family | factor | effect older | effect newer | 90% newer | q | survives |',
              '|---|---|---:|---:|---|---:|---|']
    survivors = []
    for k, (f, name, eo, en, (lo, hi, _)) in enumerate(tests):
        ok = np.sign(eo) == np.sign(en) and (lo > 0 or hi < 0) and q[k] <= 0.10
        if ok:
            survivors.append((f, name, en))
        lines.append(f"| {f} | {name} | {eo:+.3f} | {en:+.3f} | [{lo:+.3f}..{hi:+.3f}] | {q[k]:.2f} | "
                     f"{'YES' if ok else '-'} |")
    lines += ['', f"Survivors: {', '.join(f'{a}/{b} ({c:+.3f})' for a, b, c in survivors) or 'none'}", '']
    return survivors


def gbm(df: pl.DataFrame, mid: float, rng, lines: List[str]):
    import lightgbm as lgb
    feats = list(FACTORS) + list(BINNED)
    kinds = {k: i for i, k in enumerate(sorted(set(df['kind'].to_list())))}
    tfs = {k: i for i, k in enumerate(sorted(set(df['tf'].to_list())))}
    X = np.column_stack([df[f].to_numpy().astype(float) for f in feats] +
                        [np.array([kinds[k] for k in df['kind'].to_list()], float),
                         np.array([tfs[k] for k in df['tf'].to_list()], float)])
    y = df['b1'].to_numpy()
    real = 1 - df['placebo'].to_numpy()
    ts = df['ts'].to_numpy()
    month = (ts // (30 * DAY_MS)).astype(int)
    months = sorted(set(month))
    pred = np.full(len(df), np.nan)
    for m in months[3:]:
        for rl in (0, 1):
            tr = (month < m) & (real == rl)
            te = (month == m) & (real == rl)
            if tr.sum() < 2000 or te.sum() == 0:
                continue
            model = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05, num_leaves=31, min_child_samples=200,
                                       subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)
            model.fit(X[tr], (y[tr] == 1).astype(int))
            pred[te] = model.predict_proba(X[te])[:, 1]
    lines += ['## 2. LightGBM walk-forward (top decile of predictions, mean b1)', '',
              '| half | real top10% | placebo top10% | difference | 90% (days) |', '|---|---:|---:|---:|---|']
    verdict = []
    for half, hsel in (('older', ts < mid), ('newer', ts >= mid)):
        out = {}
        for rl in (1, 0):
            s = hsel & (real == rl) & ~np.isnan(pred)
            if s.sum() < 500:
                continue
            cut = np.percentile(pred[s], 90)
            top = s & (pred >= cut)
            out[rl] = (y[top].astype(float), (ts[top] // DAY_MS).astype(np.int64))
        if len(out) < 2:
            lines.append(f"| {half} | — | — | — | — |")
            continue
        diff = out[1][0].mean() - out[0][0].mean()
        boots = []
        for _ in range(1000):
            mm = []
            for rl in (1, 0):
                u, s_, n_ = day_sums(out[rl][1], out[rl][0])
                w = np.bincount(rng.integers(0, len(u), len(u)), minlength=len(u))
                mm.append((s_ * w).sum() / max(1.0, (n_ * w).sum()))
            boots.append(mm[0] - mm[1])
        lo, hi = np.percentile(boots, [5, 95])
        verdict.append((half, diff, lo))
        lines.append(f"| {half} | {out[1][0].mean():+.3f} | {out[0][0].mean():+.3f} | {diff:+.3f} | [{lo:+.3f}..{hi:+.3f}] |")
    ok = len(verdict) == 2 and all(d > 0 for _, d, _ in verdict) and verdict[1][2] > 0
    lines += ['', f"GBM verdict: {'useful for levels' if ok else 'no level-specific skill'}", '']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join('research', 'level_factors.md'))
    ap.add_argument('--no-gbm', action='store_true')
    ap.add_argument('--limit', type=int, default=0, help='first N coins only (a smoke test)')
    args = ap.parse_args()
    cols = ['ts', 'kind', 'tf', 'placebo', 'b1'] + list(FACTORS) + list(BINNED)
    df = load(cols, args.limit).filter(pl.col('b1').is_not_null())
    ts = df['ts'].to_numpy()
    mid = float((ts.min() + ts.max()) / 2)
    rng = np.random.default_rng(17)
    n_real = int((df['placebo'] == 0).sum())
    lines = ['# Level factors vs placebo (step 2)', '',
             f"{df['ts'].len()} events ({n_real} real, {df['ts'].len() - n_real} placebo); halves split at "
             f"{np.datetime64(int(mid), 'ms')}. Rules: the docstring of `research_level_factors.py` (pre-registered).", '']
    single_factors(df, mid, rng, lines)
    if not args.no_gbm:
        gbm(df, mid, rng, lines)
    text = '\n'.join(lines)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(text + '\n')
    print(text)


if __name__ == '__main__':
    main()
