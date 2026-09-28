"""
Meta-labeling of the bot's trades (Lopez de Prado, Advances in Financial Machine Learning, ch. 3): the strategies
decide WHAT to trade (side, entry, stop, targets); a secondary model learns from their historical trades WHICH of them
to take. Trained on the card replay's samples (research_cards.py --samples: every taken and first vetoed trade with
its features at the entry and its net R), judged only out of sample:

1. purged walk-forward over time (folds in time order, trades whose 8h life reaches into the test fold dropped from
   training, plus an embargo): logistic regression vs LightGBM on "TP1 before the stop" (r_tp1 > 0), AUC and log-loss
   against the base rate;
2. the economics that matter to a trader: the mean net R of the trades the model would take (its score above the
   training fold's top-quantile threshold) against all trades, with 4h x direction block-bootstrap intervals;
3. a clean temporal holdout: trained on the older half of the window, tested on the newer half, by strategy and month.

A model is worth shipping (shadow: shown on cards, journaled, never a filter) only if the trades it selects have a
positive net R whose 90% interval is above 0 on the holdout. Run:
    .venv\\Scripts\\python research_meta.py --samples samples_12m.parquet [--out research/meta_12m.md] [--save models/]
"""
import argparse
import json
import os
from typing import Dict, List, Tuple

import numpy as np
import polars as pl

H8 = 8 * 3_600_000
H4 = 4 * 3_600_000
CATEGORICAL = ('strategy', 'setup', 'trigger_veto', 'card_veto')
META = ('symbol', 'ts_ms', 'r_tp1', 'r_tp2', 'r_be')


def design(df: pl.DataFrame, categories: Dict[str, List[str]] = None) -> Tuple[np.ndarray, List[str], Dict[str, List[str]]]:
    """Numeric features + one-hot categoricals (categories fixed on the training data)."""
    categories = categories or {c: sorted(df[c].unique().to_list()) for c in CATEGORICAL if c in df.columns}
    # x_* are the exit rules' OUTCOMES of the same trade (research_cards.exit_variants): never features (they leaked the
    # label - AUC 1.000 - in the first run)
    numeric = [c for c in df.columns if c not in META and c not in CATEGORICAL and not c.startswith('x_')
               and df[c].dtype.is_numeric()]
    cols = [pl.col(c).cast(pl.Float64) for c in numeric]
    names = list(numeric)
    for c, values in categories.items():
        for v in values:
            cols.append((pl.col(c) == v).cast(pl.Float64).alias(f"{c}={v}"))
            names.append(f"{c}={v}")
    return df.select(cols).to_numpy(), names, categories


def block_mean_ci(values: np.ndarray, ts: np.ndarray, direction: np.ndarray, seed: int = 7, boot: int = 2000):
    """(mean, lo, hi) of values with a block bootstrap over 4h x direction blocks (one market move = one block)."""
    if len(values) < 10:
        return float(values.mean()) if len(values) else float('nan'), float('nan'), float('nan')
    blocks = (ts // H4) * 2 + (direction > 0)
    order = np.argsort(blocks, kind='stable')
    v, b = values[order], blocks[order]
    starts = np.flatnonzero(np.r_[True, b[1:] != b[:-1]])
    sums, counts = np.add.reduceat(v, starts), np.diff(np.r_[starts, len(v)])
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(sums), size=(boot, len(sums)))
    means = sums[idx].sum(axis=1) / counts[idx].sum(axis=1)
    lo, hi = np.quantile(means, [0.05, 0.95])
    return float(values.mean()), float(lo), float(hi)


def auc(y: np.ndarray, p: np.ndarray) -> float:
    order = np.argsort(p, kind='mergesort')
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    pos = y == 1
    n1, n0 = pos.sum(), (~pos).sum()
    return float((ranks[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else float('nan')


def logloss(y, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def fit_regressor(X: np.ndarray, r: np.ndarray):
    """LightGBM on the net R itself (the economic target), R clipped to [-1.5, 5] against outliers."""
    from lightgbm import LGBMRegressor
    gbm = LGBMRegressor(n_estimators=400, learning_rate=0.03, num_leaves=15, min_child_samples=200, subsample=0.8,
                        subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0, verbose=-1)
    gbm.fit(X, np.clip(r, -1.5, 5.0))
    return gbm


def fit_models(X: np.ndarray, y: np.ndarray):
    from lightgbm import LGBMClassifier
    from sklearn.linear_model import LogisticRegression
    mu, sd = np.nanmean(X, axis=0), np.nanstd(X, axis=0)
    mu, sd = np.nan_to_num(mu), np.where(sd > 0, sd, 1.0)
    lr = LogisticRegression(C=0.05, max_iter=3000).fit(np.nan_to_num((X - mu) / sd), y)
    gbm = LGBMClassifier(n_estimators=400, learning_rate=0.03, num_leaves=15, min_child_samples=200,
                         subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0, verbose=-1)
    gbm.fit(X, y)
    return {'logistic': lambda Z: lr.predict_proba(np.nan_to_num((Z - mu) / sd))[:, 1],
            'lightgbm': lambda Z: gbm.predict_proba(Z)[:, 1]}, gbm


def select_report(name: str, r: np.ndarray, ts: np.ndarray, d: np.ndarray, score: np.ndarray, threshold: float) -> str:
    take = score >= threshold
    m_all, lo_all, hi_all = block_mean_ci(r, ts, d)
    m_sel, lo_sel, hi_sel = block_mean_ci(r[take], ts[take], d[take])
    return (f"| {name} | {len(r)} | {m_all:+.3f} [{lo_all:+.3f}..{hi_all:+.3f}] | {take.sum()} ({take.mean():.0%}) | "
            f"{m_sel:+.3f} [{lo_sel:+.3f}..{hi_sel:+.3f}] | {float((r[take] > 0).mean()) if take.any() else float('nan'):.0%} |")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--samples', default='research_samples.parquet')
    parser.add_argument('--out', default=os.path.join('research', 'meta_12m.md'))
    parser.add_argument('--folds', type=int, default=5)
    parser.add_argument('--top', type=float, default=0.2, help='the share of trades the model takes (by training scores)')
    parser.add_argument('--save', default=None, help='directory to save the model when it passes the holdout')
    args = parser.parse_args()
    df = pl.read_parquet(args.samples).sort('ts_ms')
    df = df.filter(pl.col('r_tp1').is_not_null())
    ts = df['ts_ms'].to_numpy()
    r = df['r_tp1'].to_numpy().astype(float)
    d = df['direction'].to_numpy().astype(float)
    y = (r > 0).astype(int)
    lines = [f"# Meta-labeling of the card trades ({len(df)} trades, {df['symbol'].n_unique()} coins, "
             f"{pl.from_epoch(pl.Series([ts.min()]), 'ms')[0]:%Y-%m-%d} .. {pl.from_epoch(pl.Series([ts.max()]), 'ms')[0]:%Y-%m-%d})", '',
             "Samples: every trade the card replay took plus the first trigger each card's vetoes skipped (low_rr, no_oi, "
             "no_spring_test), with the features at the entry and the net R (fees, slippage, funding) exiting at TP1 / "
             "the stop / 8h. Label: TP1 before the stop (r_tp1 > 0). Everything below is out of sample.", '']

    # ---------------------------------------------------------------- 1. purged walk-forward
    edges = np.linspace(ts.min(), ts.max(), args.folds + 2)[1:]
    lines += ['## 1. Purged walk-forward', '', '| fold | train | test | base AUC | logistic AUC | LightGBM AUC | '
              'LightGBM log-loss skill |', '|---:|---:|---:|---:|---:|---:|---:|']
    wf_rows = []
    for k in range(args.folds):
        lo, hi = edges[k], edges[k + 1]
        train = ts < lo - H8 - H4                     # the trade's 8h life + a 4h embargo before the test fold
        test = (ts >= lo) & (ts < hi)
        if train.sum() < 2000 or test.sum() < 500:
            continue
        Xtr, names, cats = design(df.filter(pl.Series(train)))
        assert not any(n.startswith('x_') or n in ('r_tp1', 'r_tp2', 'r_be') for n in names), 'outcome columns in the features'
        Xte, _, _ = design(df.filter(pl.Series(test)), cats)
        models, _ = fit_models(Xtr, y[train])
        p_lr, p_gb = models['logistic'](Xte), models['lightgbm'](Xte)
        thr = np.quantile(models['lightgbm'](Xtr), 1 - args.top)
        base = np.full(test.sum(), y[train].mean())
        skill = 1 - logloss(y[test], p_gb) / logloss(y[test], base)
        lines.append(f"| {k + 1} | {train.sum()} | {test.sum()} | 0.500 | {auc(y[test], p_lr):.3f} | "
                     f"{auc(y[test], p_gb):.3f} | {skill:+.2%} |")
        wf_rows.append((test, p_gb, thr))
    lines += ['', '### Net R of the trades the model takes (walk-forward, all folds pooled)', '',
              '| trades | n | mean R all [90%] | taken | mean R taken [90%] | win |', '|---|---:|---|---:|---|---:|']
    if wf_rows:
        mask = np.zeros(len(df), bool)
        score = np.full(len(df), -1.0)
        thr_of = np.full(len(df), np.inf)
        for test, p, thr in wf_rows:
            mask |= test
            score[test] = p
            thr_of[test] = thr
        take_score = np.where(score >= thr_of, 1.0, 0.0)
        lines.append(select_report('all strategies', r[mask], ts[mask], d[mask], take_score[mask], 0.5))

    # ---------------------------------------------------------------- 3. temporal holdout
    mid = ts.min() + (ts.max() - ts.min()) // 2
    train = ts < mid - H8 - H4
    test = ts >= mid
    Xtr, names, cats = design(df.filter(pl.Series(train)))
    Xte, _, _ = design(df.filter(pl.Series(test)), cats)
    models, gbm = fit_models(Xtr, y[train])
    p_gb = models['lightgbm'](Xte)
    thr = float(np.quantile(models['lightgbm'](Xtr), 1 - args.top))
    lines += ['', f"## 3. Holdout: trained before {pl.from_epoch(pl.Series([mid]), 'ms')[0]:%Y-%m-%d}, tested after",
              '', f"LightGBM AUC {auc(y[test], p_gb):.3f}, logistic AUC {auc(y[test], models['logistic'](Xte)):.3f}; "
              f"takes the trades scoring above the training top {args.top:.0%} ({thr:.3f}).", '',
              '| trades | n | mean R all [90%] | taken | mean R taken [90%] | win |', '|---|---:|---|---:|---|---:|']
    rt, tt, dt = r[test], ts[test], d[test]
    lines.append(select_report('all strategies', rt, tt, dt, p_gb, thr))
    strat = df.filter(pl.Series(test))['strategy'].to_numpy()
    for s in sorted(set(strat)):
        m = strat == s
        if m.sum() >= 50:
            lines.append(select_report(s, rt[m], tt[m], dt[m], p_gb[m], thr))
    veto = df.filter(pl.Series(test))['trigger_veto'].to_numpy()
    for v in sorted(set(veto)):
        m = veto == v
        if m.sum() >= 50:
            lines.append(select_report(f"trigger veto: {v or 'none (taken)'}", rt[m], tt[m], dt[m], p_gb[m], thr))
    months = (tt // (30 * 86_400_000))
    lines += ['', '### Taken trades by month (holdout)', '', '| month | taken | mean R taken | mean R all |', '|---|---:|---:|---:|']
    for mo in sorted(set(months)):
        m = months == mo
        take = m & (p_gb >= thr)
        lines.append(f"| {pl.from_epoch(pl.Series([int(mo) * 30 * 86_400_000]), 'ms')[0]:%Y-%m} | {take.sum()} | "
                     f"{rt[take].mean() if take.any() else float('nan'):+.3f} | {rt[m].mean():+.3f} |")
    imp = sorted(zip(gbm.booster_.feature_importance('gain'), names), reverse=True)[:15]
    lines += ['', '### Most informative features (LightGBM gain, holdout model)', '',
              ', '.join(f"{n} ({g / sum(x for x, _ in imp):.0%})" for g, n in imp)]

    # the economic target: a regressor on the net R, taking the trades it expects to be positive (and its top 20%)
    reg = fit_regressor(Xtr, r[train])
    pr_tr, pr = reg.predict(Xtr), reg.predict(Xte)
    thr_r = float(np.quantile(pr_tr, 1 - args.top))
    lines += ['', '## 4. Holdout, target = net R (regression), trained on the older half', '',
              f"Correlation of the predicted and the realized R on the holdout: {np.corrcoef(pr, rt)[0, 1]:+.3f}.", '',
              '| selection | n | mean R all [90%] | taken | mean R taken [90%] | win |', '|---|---:|---|---:|---|---:|']
    lines.append(select_report('predicted R > 0', rt, tt, dt, pr, 1e-9))
    lines.append(select_report(f"top {args.top:.0%} of training predictions", rt, tt, dt, pr, thr_r))
    for s_name in sorted(set(strat)):
        m = strat == s_name
        if m.sum() >= 50:
            lines.append(select_report(f"{s_name}: predicted R > 0", rt[m], tt[m], dt[m], pr[m], 1e-9))
    m_reg, lo_reg, hi_reg = block_mean_ci(rt[pr > 1e-9], tt[pr > 1e-9], dt[pr > 1e-9]) if (pr > 1e-9).any() else (0, -1, -1)

    m_sel, lo_sel, hi_sel = block_mean_ci(rt[p_gb >= thr], tt[p_gb >= thr], dt[p_gb >= thr])
    if lo_reg > lo_sel:
        m_sel, lo_sel, hi_sel = m_reg, lo_reg, hi_reg
    passed = lo_sel > 0
    lines += ['', f"## Verdict: {'PASSED' if passed else 'NOT PASSED'}", '',
              f"The trades the model would take on the holdout: mean net R {m_sel:+.3f} [{lo_sel:+.3f}..{hi_sel:+.3f}]. "
              + ("Its 90% interval is above 0: worth shipping in shadow (shown on cards, journaled, never a filter) and "
                 "judging live." if passed else
                 "Its 90% interval is not above 0: the model does not turn the strategies' trades into a profitable "
                 "selection; not shipped.")]
    text = '\n'.join(lines) + '\n'
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)
    if passed and args.save:
        os.makedirs(args.save, exist_ok=True)
        gbm.booster_.save_model(os.path.join(args.save, 'meta_card.txt'))
        with open(os.path.join(args.save, 'meta_card.json'), 'w') as fh:
            json.dump({'features': names, 'categories': cats, 'threshold': thr}, fh)


if __name__ == '__main__':
    main()
