"""
Evaluation of the P(edge) model on the pretraining dataset (pretrain_rows.parquet: every labelled historical row
with its features and the online model's prediction made BEFORE it learned that row).

1. Prequential (test-then-train) quality of the online logistic regression as it ran (river, pretrain.py).
2. Purged walk-forward comparison (time folds; training rows whose 4h label window reaches into the test fold are
   dropped, plus a 4h embargo): base rate vs logistic regression vs LightGBM, rows weighted by their uniqueness
   (1 / the number of labels overlapping their 4h window: signals of one market move are not independent).
3. What it gives the trader: Edge 4h of the rows the model ranks highest vs all rows.

4. --trades (eng-174): P(trade) on the closed trades of the journal - ENTRY-row features, label card_r_low > 0,
   purging and uniqueness on each trade's real [entry, exit] interval, isotonic calibration fitted on earlier
   folds only, R of the top-ranked trades and the Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014) of the best
   threshold and of each strategy against the pool. Run: .venv/bin/python ml_eval.py --trades --db signals.db

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
    # audit N15: the base rate KNOWN before each row - only labels already matured (row ts + 4h <= this row's ts)
    cum = np.r_[0.0, np.cumsum(y)]
    known = np.searchsorted(ts + 4 * 3_600_000, ts, side='right')     # ts sorted, so ts + 4h is too
    base_online = np.where(known > 0, cum[known] / np.maximum(known, 1), 0.5)
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


# ====================================================================== eng-174: P(trade) on the closed trades

def interval_uniqueness(t0: np.ndarray, t1: np.ndarray) -> np.ndarray:
    """AFML average uniqueness over each label's REAL interval [entry, exit]: the mean of 1 / concurrency inside it."""
    n = len(t0)
    out = np.ones(n)
    for i in range(n):
        lo, hi = t0[i], max(t1[i], t0[i] + 1)
        j = (t0 < hi) & (t1 > lo)
        cuts = np.unique(np.clip(np.r_[t0[j], t1[j], lo, hi], lo, hi))
        mids = (cuts[:-1] + cuts[1:]) / 2
        conc = np.array([np.sum((t0[j] <= m) & (t1[j] > m)) for m in mids])
        out[i] = np.sum(np.diff(cuts) / np.maximum(conc, 1)) / (hi - lo)
    return out


def deflated_sharpe(r: np.ndarray, trial_srs: List[float]) -> Tuple[float, float, float]:
    """
    Bailey & Lopez de Prado (2014): P(true Sharpe > 0) of the best of M tried variants, per-trade Sharpe of r, the
    expected maximum SR0 of M null trials from the variance of the trials' Sharpes. Returns (SR, SR0, DSR).
    """
    from scipy.stats import kurtosis, norm, skew
    t = len(r)
    if t < 3 or np.std(r) == 0:
        return float('nan'), float('nan'), float('nan')
    sr = float(np.mean(r) / np.std(r, ddof=1))
    m = max(1, len(trial_srs))
    if m > 1:
        euler = 0.5772156649
        v = float(np.var(trial_srs, ddof=1))
        sr0 = np.sqrt(v) * ((1 - euler) * norm.ppf(1 - 1 / m) + euler * norm.ppf(1 - 1 / (m * np.e)))
    else:
        sr0 = 0.0
    g3, g4 = float(skew(r)), float(kurtosis(r, fisher=False))
    den = 1 - g3 * sr + (g4 - 1) / 4 * sr ** 2
    dsr = float(norm.cdf((sr - sr0) * np.sqrt(t - 1) / np.sqrt(den))) if den > 0 else float('nan')
    return sr, float(sr0), dsr


def load_trades(db: str) -> pl.DataFrame:
    """Closed taken trades: ENTRY row features (frozen at the entry), label, entry time, real exit time."""
    import sqlite3
    from ml import TradeModel, trade_label
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM signals WHERE kind = 'entry' AND vetoed IS NULL AND card_r IS NOT NULL "
                        "ORDER BY ts_ms").fetchall()
    exits = {(s, g, t): e for s, g, t, e in conn.execute(
        "SELECT symbol, 'ENTRY ' || substr(group_key, instr(group_key, ' ') + 1), setup_ts_ms, ts_ms FROM signals "
        "WHERE kind = 'card' AND card_r IS NOT NULL")}
    recs = []
    for r in rows:
        keys = r.keys()
        exit_ms = (r['exit_ts_ms'] if 'exit_ts_ms' in keys else None) or exits.get((r['symbol'], r['group_key'], r['setup_ts_ms']))
        label = trade_label(r)
        if exit_ms is None or label is None:
            continue
        rec = {f'f:{k}': v for k, v in TradeModel.features(r).items()}
        r_low = r['card_r_low'] if 'card_r_low' in keys and r['card_r_low'] is not None else r['card_r']
        rec.update(ts_ms=r['ts_ms'], exit_ms=int(exit_ms), label=float(label), r=float(r_low),
                   strategy=r['strategy'] or r['group_key'],
                   p_before=r['p_trade'] if 'p_trade' in keys else None)
        recs.append(rec)
    return pl.from_dicts(recs, infer_schema_length=None) if recs else pl.DataFrame()


def main_trades(db: str, folds: int):
    import warnings
    warnings.filterwarnings('ignore', category=RuntimeWarning)      # all-NaN feature columns in a fold
    df = load_trades(db)
    if df.height < 60:
        print(f"closed trades: {df.height} - too few for an out-of-sample evaluation")
        return
    df = df.sort('ts_ms')
    y = df['label'].to_numpy()
    t0, t1 = df['ts_ms'].to_numpy(), df['exit_ms'].to_numpy()
    r = df['r'].to_numpy()
    w = interval_uniqueness(t0, t1)
    cols = [c for c in df.columns if c.startswith('f:')]
    X = df.select([pl.col(c).cast(pl.Float64) for c in cols]).to_numpy()
    print(f"closed trades {df.height}, {np.mean(y):.1%} positive (card_r_low > 0), mean R {r.mean():+.3f}, "
          f"life median {np.median(t1 - t0) / 3.6e6:.1f}h max {np.max(t1 - t0) / 3.6e6:.1f}h, "
          f"effective n {w.sum():.0f}")

    if 'p_before' in df.columns and df['p_before'].null_count() < df.height:
        p_on = df['p_before'].cast(pl.Float64).to_numpy()
        ok = ~np.isnan(p_on)
        # the base rate known at each entry: only trades already CLOSED before it
        known = np.array([y[t1 <= t][:].mean() if np.any(t1 <= t) else 0.5 for t in t0])
        bl, bb = _logloss(y[ok], known[ok], w[ok]), _brier(y[ok], known[ok], w[ok])
        print("\n1. online P(trade) as it ran (journaled at the entry)")
        print("   " + report('base rate (running)', y[ok], known[ok], w[ok], bl, bb))
        print("   " + report('river LR (online)', y[ok], p_on[ok], w[ok], bl, bb))

    # walk-forward by entry time; purge: a training trade must have CLOSED before the test fold starts
    edges = np.linspace(t0.min(), t0.max() + 1, folds + 2)[1:]
    names = ('base rate', 'logistic (L2)', 'LightGBM (shallow)')
    oos = {n: np.full(len(y), np.nan) for n in names}
    for k in range(folds):
        lo, hi = edges[k], edges[k + 1]
        train = t1 < lo
        test = (t0 >= lo) & (t0 < hi)
        if train.sum() < 40 or test.sum() < 10:
            continue
        yt, wt = y[train], w[train]
        oos['base rate'][test] = np.average(yt, weights=wt)
        from sklearn.linear_model import LogisticRegression
        mu = np.nan_to_num(np.nanmean(X[train], axis=0))
        sd = np.nanstd(X[train], axis=0)
        sd[~(sd > 0)] = 1.0
        z = lambda a: np.nan_to_num((a - mu) / sd)
        if len(set(yt)) > 1:
            oos['logistic (L2)'][test] = LogisticRegression(C=0.05, max_iter=2000).fit(
                z(X[train]), yt, sample_weight=wt).predict_proba(z(X[test]))[:, 1]
            import lightgbm as lgb
            gbm = lgb.LGBMClassifier(n_estimators=150, learning_rate=0.03, num_leaves=4, min_child_samples=20,
                                     subsample=0.8, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0, verbose=-1)
            oos['LightGBM (shallow)'][test] = gbm.fit(X[train], yt, sample_weight=wt).predict_proba(X[test])[:, 1]
        print(f"   fold {k + 1}: train {train.sum()} (closed before the fold), test {test.sum()}")

    mask = ~np.isnan(oos['base rate'])
    if not mask.any():
        print("no fold had enough closed trades before it")
        return
    print("\n2. purged walk-forward on the real [entry, exit] intervals (out of sample)")
    bl, bb = _logloss(y[mask], oos['base rate'][mask], w[mask]), _brier(y[mask], oos['base rate'][mask], w[mask])
    for n in names:
        m = mask & ~np.isnan(oos[n])
        if m.any():
            print("   " + report(n, y[m], oos[n][m], w[m], bl, bb))
    # isotonic calibration fitted only on the EARLIER folds' out-of-sample predictions, applied to the next fold
    from sklearn.isotonic import IsotonicRegression
    for n in names[1:]:
        cal = np.full(len(y), np.nan)
        for k in range(1, folds):
            lo, hi = edges[k], edges[k + 1]
            past = mask & ~np.isnan(oos[n]) & (t1 < lo)
            now = (t0 >= lo) & (t0 < hi) & ~np.isnan(oos[n])
            if past.sum() >= 30 and now.any():
                iso = IsotonicRegression(out_of_bounds='clip', y_min=0.01, y_max=0.99)
                cal[now] = iso.fit(oos[n][past], y[past], sample_weight=w[past]).predict(oos[n][now])
        m = ~np.isnan(cal)
        if m.sum() >= 20:
            bl2, bb2 = _logloss(y[m], oos['base rate'][m], w[m]), _brier(y[m], oos['base rate'][m], w[m])
            print("   " + report(n + ' raw', y[m], oos[n][m], w[m], bl2, bb2))
            print("   " + report(n + ' isotonic', y[m], cal[m], w[m], bl2, bb2))

    # 3. what it gives in R, and the Deflated Sharpe of the best threshold among the ones tried
    print("\n3. R per trade (card_r_low, after costs) out of sample")
    rr = r[mask]
    print(f"   all trades          mean {rr.mean():+.3f}R  n {mask.sum()}")
    # every threshold of every model is one try (M), nested or not: SR0 comes from all of them
    tries = {}
    for n in names[1:]:
        m = mask & ~np.isnan(oos[n])
        if m.sum() < 20:
            continue
        for q in (0.3, 0.5, 0.7):
            keep = oos[n][m] >= np.quantile(oos[n][m], q)
            tries[(n, f"top {1 - q:.0%}")] = r[m][keep]
            print(f"   {n:20} top {1 - q:.0%}: mean {r[m][keep].mean():+.3f}R  n {keep.sum()}")
    if tries:
        srs = [v.mean() / v.std(ddof=1) for v in tries.values() if len(v) > 2 and v.std() > 0]
        srs.append(rr.mean() / rr.std(ddof=1))
        best = max(tries, key=lambda k: tries[k].mean())
        sr, sr0, dsr = deflated_sharpe(tries[best], srs)
        print(f"   best {best[0]} {best[1]}: per-trade SR {sr:.3f} vs SR0 {sr0:.3f} of {len(srs)} tries -> DSR {dsr:.2f}"
              f"  (> 0.95 = significant; nested thresholds make it optimistic)")

    # 4. strategies: the best one's DSR against all strategies tried (multiple testing across the strategy pool)
    print("\n4. strategies (all closed trades, not only out of sample): Deflated Sharpe vs the whole pool")
    groups = {}
    for s_, v in zip(df['strategy'].to_list(), r):
        groups.setdefault(s_, []).append(v)
    pool = {k: np.array(v) for k, v in groups.items() if len(v) >= 10}
    srs = [v.mean() / v.std(ddof=1) for v in pool.values() if v.std() > 0]
    for k, v in sorted(pool.items(), key=lambda kv: -kv[1].mean()):
        sr, sr0, dsr = deflated_sharpe(v, srs)
        print(f"   {k:28} n {len(v):4}  mean {v.mean():+.3f}R  SR {sr:+.3f}  SR0 {sr0:.3f}  DSR {dsr:.2f}")


if __name__ == '__main__':
    import sys
    if '--trades' in sys.argv:
        ap = argparse.ArgumentParser()
        ap.add_argument('--trades', action='store_true')
        ap.add_argument('--db', default=CONFIG.journal.db_path)
        ap.add_argument('--folds', type=int, default=5)
        a_ = ap.parse_args()
        main_trades(a_.db, a_.folds)
    else:
        main()
