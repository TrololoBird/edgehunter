"""
Evaluation of the P(edge) model on the pretraining dataset (pretrain_rows.parquet: every labelled historical row
with its features and the online model's prediction made BEFORE it learned that row).

1. Prequential (test-then-train) quality of the online logistic regression as it ran (river, pretrain.py).
2. Purged walk-forward comparison (time folds; training rows whose 4h label window reaches into the test fold are
   dropped, plus a 4h embargo): base rate vs logistic regression vs LightGBM, rows weighted by their uniqueness
   (1 / the number of labels overlapping their 4h window: signals of one market move are not independent).
3. What it gives the trader: Edge 4h of the rows the model ranks highest vs all rows.

Metrics: log-loss and Brier skill against the base rate (a model that does not beat "always the base rate" has
no information), AUC (ranking), calibration by probability decile. Run: .venv\\Scripts\\python ml_eval.py
"""
import argparse
from typing import Dict, List, Tuple

import numpy as np
import polars as pl

from config import CONFIG

META = ('ts_ms', 'symbol', 'kind', 'group_key', 'direction', 'ret_4h', 'baseline_4h', 'baseline_mean_4h', 'label',
        'p_before')
H4 = 4 * 3_600_000


def _logloss(y: np.ndarray, p: np.ndarray, w: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.sum(w * (y * np.log(p) + (1 - y) * np.log(1 - p))) / np.sum(w))


def _brier(y: np.ndarray, p: np.ndarray, w: np.ndarray) -> float:
    return float(np.sum(w * (p - y) ** 2) / np.sum(w))


def _auc(y: np.ndarray, p: np.ndarray) -> float:
    order = np.argsort(p, kind='mergesort')
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    # average ranks of ties
    _, inv, counts = np.unique(p, return_inverse=True, return_counts=True)
    sums = np.bincount(inv, weights=ranks)
    ranks = (sums / counts)[inv]
    pos = y == 1
    n1, n0 = pos.sum(), (~pos).sum()
    if not n1 or not n0:
        return float('nan')
    return float((ranks[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def uniqueness(ts: np.ndarray) -> np.ndarray:
    """1 / the number of rows whose 4h label window overlaps this row's (all coins: one market move = one event)."""
    order = np.sort(ts)
    lo = np.searchsorted(order, ts - H4, side='left')
    hi = np.searchsorted(order, ts + H4, side='right')
    return 1.0 / np.maximum(1, hi - lo)


def matrix(df: pl.DataFrame) -> Tuple[np.ndarray, List[str]]:
    cols = [c for c in df.columns if c not in META and df[c].dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32, pl.Boolean)]
    X = df.select([pl.col(c).cast(pl.Float64) for c in cols]).to_numpy()
    return X, cols


def report(name: str, y, p, w, base_ll, base_brier) -> str:
    ll, br = _logloss(y, p, w), _brier(y, p, w)
    return (f"{name:22} log-loss {ll:.4f} (skill {1 - ll / base_ll:+.3%})  Brier skill {1 - br / base_brier:+.3%}  "
            f"AUC {_auc(y, p):.3f}")


def main():
    import warnings
    warnings.filterwarnings('ignore', category=RuntimeWarning)      # all-NaN feature columns in a fold
    parser = argparse.ArgumentParser()
    parser.add_argument('--path', default=CONFIG.pretrain.dataset_path)
    parser.add_argument('--folds', type=int, default=5)
    args = parser.parse_args()
    import os
    path = os.path.join(args.path, '*.parquet') if os.path.isdir(args.path) else args.path
    # the parts carry different one-hot columns (setups / regimes seen so far): union them
    import glob
    df = pl.concat([pl.read_parquet(f) for f in sorted(glob.glob(path))], how='diagonal_relaxed').sort('ts_ms')
    y = df['label'].cast(pl.Float64).to_numpy()
    ts = df['ts_ms'].to_numpy()
    w = uniqueness(ts)
    print(f"rows {len(df)}, coins {df['symbol'].n_unique()}, {np.mean(y):.1%} positive, "
          f"effective n (sum of uniqueness) {w.sum():.0f}")

    # ------------------------------------------------------------ 1. prequential online LR
    p_online = df['p_before'].to_numpy()
    ok = ~np.isnan(p_online.astype(float))
    running = np.cumsum(y) / np.arange(1, len(y) + 1)
    base_online = np.r_[0.5, running[:-1]]            # the base rate known before each row
    print("\n1. online logistic regression as it ran (prediction before learning each row)")
    print("   " + report('base rate (running)', y[ok], base_online[ok], w[ok],
                         _logloss(y[ok], base_online[ok], w[ok]), _brier(y[ok], base_online[ok], w[ok])))
    print("   " + report('river LR (online)', y[ok], p_online[ok].astype(float), w[ok],
                         _logloss(y[ok], base_online[ok], w[ok]), _brier(y[ok], base_online[ok], w[ok])))

    # ------------------------------------------------------------ 2. purged walk-forward
    X, cols = matrix(df)
    edges = np.linspace(ts.min(), ts.max(), args.folds + 2)[1:]
    results: Dict[str, List[Tuple[np.ndarray, np.ndarray, np.ndarray]]] = {'base rate': [], 'logistic (L2)': [],
                                                                          'LightGBM (shallow)': []}
    test_rows = []
    for k in range(args.folds):
        lo, hi = edges[k], edges[k + 1]
        train = ts < lo - 2 * H4          # label window + embargo before the test fold
        test = (ts >= lo) & (ts < hi)
        if train.sum() < 500 or test.sum() < 100:
            continue
        yt, wt = y[train], w[train]
        base = np.full(test.sum(), np.average(yt, weights=wt))
        results['base rate'].append((y[test], base, w[test]))
        # logistic: standardize on the training fold, missing -> the training mean (0 after scaling)
        from sklearn.linear_model import LogisticRegression
        mu = np.nanmean(X[train], axis=0)
        sd = np.nanstd(X[train], axis=0)
        sd[~(sd > 0)] = 1.0
        mu = np.nan_to_num(mu)
        Ztr = np.nan_to_num((X[train] - mu) / sd)
        Zte = np.nan_to_num((X[test] - mu) / sd)
        lr = LogisticRegression(C=0.05, max_iter=2000).fit(Ztr, yt, sample_weight=wt)
        results['logistic (L2)'].append((y[test], lr.predict_proba(Zte)[:, 1], w[test]))
        import lightgbm as lgb
        cut = int(train.sum() * 0.85)       # the training fold's last 15% (by time) for early stopping
        idx = np.flatnonzero(train)
        fit_i, val_i = idx[:cut], idx[cut:]
        model = lgb.LGBMClassifier(n_estimators=2000, learning_rate=0.02, num_leaves=7, min_child_samples=200,
                                   subsample=0.8, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0,
                                   verbose=-1)
        model.fit(X[fit_i], y[fit_i], sample_weight=w[fit_i], eval_X=(X[val_i],), eval_y=(y[val_i],),
                  eval_sample_weight=[w[val_i]], callbacks=[lgb.early_stopping(100, verbose=False)])
        results['LightGBM (shallow)'].append((y[test], model.predict_proba(X[test])[:, 1], w[test]))
        test_rows.append((test, model.predict_proba(X[test])[:, 1]))
        print(f"   fold {k + 1}: train {train.sum()} rows, test {test.sum()} rows, LightGBM {model.best_iteration_} trees")

    print("\n2. purged walk-forward (out of sample)")
    joined = {name: tuple(np.concatenate(parts) for parts in zip(*folds)) for name, folds in results.items() if folds}
    if 'base rate' in joined:
        yb, pb, wb = joined['base rate']
        base_ll, base_br = _logloss(yb, pb, wb), _brier(yb, pb, wb)
        for name, (yy, pp, ww) in joined.items():
            print("   " + report(name, yy, pp, ww, base_ll, base_br))
        # calibration of the best model by decile
        name = min((n for n in joined if n != 'base rate'), key=lambda n: _logloss(*joined[n]))
        yy, pp, ww = joined[name]
        print(f"\n   calibration of {name} (predicted -> observed, by decile)")
        qs = np.quantile(pp, np.linspace(0, 1, 11))
        for a, b in zip(qs[:-1], qs[1:]):
            m = (pp >= a) & (pp <= b)
            if m.sum():
                print(f"     {a:.3f}-{b:.3f}: predicted {np.average(pp[m], weights=ww[m]):.3f}  "
                      f"observed {np.average(yy[m], weights=ww[m]):.3f}  n {m.sum()}")

    # ------------------------------------------------------------ 3. what it gives: Edge of the top-ranked rows
    if test_rows:
        mask = np.zeros(len(df), bool)
        score = np.full(len(df), np.nan)
        for test, p in test_rows:
            mask |= test
            score[test] = p
        # Edge against the universe MEAN (coins beat the median by ~0.11% per 4h: that favoured every long)
        base_col = 'baseline_mean_4h' if 'baseline_mean_4h' in df.columns else 'baseline_4h'
        edge = (df['direction'].to_numpy() * (df['ret_4h'].to_numpy() - df[base_col].to_numpy()))[mask]
        s = score[mask]
        ww = w[mask]
        print(f"\n3. Edge 4h (return in the signal's direction minus the {'mean' if base_col == 'baseline_mean_4h' else 'median'} of all coins), out of sample")
        print(f"   all rows          {np.average(edge, weights=ww) * 100:+.3f}%  (n {mask.sum()})")
        for q in (0.5, 0.8, 0.9):
            top = s >= np.quantile(s, q)
            print(f"   top {1 - q:.0%} by P(edge) {np.average(edge[top], weights=ww[top]) * 100:+.3f}%  (n {top.sum()})")
        print("\n   by setup (all rows vs top 20%):")
        groups = df['group_key'].to_numpy()[mask]
        for g in sorted(set(groups)):
            m = groups == g
            if m.sum() < 200:
                continue
            top = m & (s >= np.quantile(s[m], 0.8))
            print(f"   {g:22} {np.average(edge[m], weights=ww[m]) * 100:+.3f}% -> "
                  f"{np.average(edge[top], weights=ww[top]) * 100:+.3f}%  (n {m.sum()})")


if __name__ == '__main__':
    main()
