"""
Meta-labeling on the B9 archive replay (docs/CLOUD_RESEARCH.md job 8; Lopez de Prado, AFML ch. 3): the strategies
decide WHAT to trade; a secondary model learns from the replayed trades WHICH of them to take.

Data: the replay's entries.parquet (all `data/replay/<run>/**/entries.parquet`), rows with stage == 'entry',
vetoed IS NULL (passed entries) and r_tp1 not null (the journal-style replay, net). Label: r_tp1 > 0.
Features: every `f_*` column (the signal's numeric context), every `c_*` confirmation (True 1 / False 0 / None NaN),
direction, rr_tp1, conf_n. Never the outcomes (r_*, outcome) nor prices.

Method, per strategy with >= 300 passed entries (strategies below that are listed, not judged):
- purged walk-forward by calendar month: the test fold is month m (from the third month with data on); training =
  every row whose trade life (ts + 8h, `CONFIG.levels.trade_ttl_sec`) ends before month m's start minus a 1-day
  embargo; at least 100 training rows with both labels, else the month is skipped;
- models: LightGBM classifier (primary, the verdict's model), logistic regression on standardized features (NaN -> 0;
  reported), the base rate (the training fold's share of r_tp1 > 0; AUC 0.5 by definition, its log-loss reported);
- out-of-sample AUC of each model over all test months;
- "top third": in each test month, the rows whose LightGBM score is >= the 2/3 quantile of the SAME model's scores on
  its training rows (threshold fixed before the test month - no look-ahead); compared with all rows of the test
  months. Halves = the out-of-sample rows split at the median entry time.

PRE-REGISTERED DECISION RULE (fixed before the first run, not to be changed after seeing results):
  the meta-model is USEFUL for a strategy only if the top third's mean net r_tp1 is greater than the mean of all its
  out-of-sample entries in BOTH halves, AND in the NEWER half the 90% bootstrap interval of the top third's mean net
  r_tp1 (resampling whole UTC days, 2000 draws) has its lower bound above 0. Otherwise NOT USEFUL. Strategies with
  < 300 passed entries: INSUFFICIENT. Nothing here changes the bot; a USEFUL verdict would at most justify a shadow
  score on the cards.

Run: .venv/bin/python research_meta_replay.py [--run data/replay/run12m] [--out research/meta_replay.md]
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import argparse
import glob
import os
from typing import List, Optional, Tuple

import numpy as np
import polars as pl

H8 = 8 * 3_600_000
DAY = 86_400_000
MIN_ENTRIES = 300
MIN_TRAIN = 100


def load(run: str) -> pl.DataFrame:
    files = glob.glob(os.path.join(run, '**', 'entries.parquet'), recursive=True)
    df = pl.concat([pl.read_parquet(f) for f in files], how='diagonal_relaxed')
    return df.filter((pl.col('stage') == 'entry') & pl.col('vetoed').is_null() & pl.col('r_tp1').is_not_null()) \
        .sort('ts')


def design(df: pl.DataFrame) -> Tuple[np.ndarray, List[str]]:
    names = [c for c in df.columns if c.startswith('f_') or c.startswith('c_')] + \
        [c for c in ('direction', 'rr_tp1', 'conf_n') if c in df.columns]
    cols = []
    for c in names:
        s = df[c]
        if s.dtype == pl.Boolean:
            s = s.cast(pl.Float64)
        elif s.dtype == pl.Null:
            s = pl.Series(c, [None] * df.height, dtype=pl.Float64)
        cols.append(s.cast(pl.Float64, strict=False).fill_null(np.nan).to_numpy())
    return np.column_stack(cols) if cols else np.zeros((df.height, 0)), names


def auc(y: np.ndarray, p: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else float('nan')


def logloss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def day_ci(r: np.ndarray, ts: np.ndarray, rng, draws: int = 2000) -> Optional[Tuple[float, float]]:
    days = ts // DAY
    u = np.unique(days)
    if len(u) < 5:
        return None
    idx = {d: np.flatnonzero(days == d) for d in u}
    bs = [r[np.concatenate([idx[d] for d in rng.choice(u, len(u))])].mean() for _ in range(draws)]
    lo, hi = np.percentile(bs, [5, 95])
    return float(lo), float(hi)


def walk_forward(df: pl.DataFrame):
    from lightgbm import LGBMClassifier
    from sklearn.linear_model import LogisticRegression
    X, _ = design(df)
    keep = ~np.all(np.isnan(X), axis=0)
    X = X[:, keep]
    y = (df['r_tp1'].to_numpy() > 0).astype(int)
    ts = df['ts'].to_numpy().astype(np.int64)
    month_key = pl.from_epoch(df['ts'].cast(pl.Int64), time_unit='ms').dt.strftime('%Y-%m').to_numpy()
    uniq = sorted(set(month_key))
    out = {k: np.full(len(y), np.nan) for k in ('gbm', 'lr', 'base', 'thr')}
    for m in uniq[2:]:
        test = month_key == m
        start = ts[test].min()
        m_start = int(pl.Series([f"{m}-01"]).str.to_datetime('%Y-%m-%d', time_zone='UTC').dt.epoch('ms')[0])
        start = min(start, m_start)
        train = (ts + H8) < (start - DAY)
        if train.sum() < MIN_TRAIN or len(np.unique(y[train])) < 2:
            continue
        Xtr, ytr, Xte = X[train], y[train], X[test]
        gbm = LGBMClassifier(n_estimators=200, learning_rate=0.03, num_leaves=15, min_child_samples=30,
                             subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=7)
        gbm.fit(Xtr, ytr)
        mu, sd = np.nanmean(Xtr, axis=0), np.nanstd(Xtr, axis=0)
        sd[~(sd > 0)] = 1.0
        mu = np.nan_to_num(mu)
        z = lambda A: np.nan_to_num((A - mu) / sd)  # noqa: E731
        lr = LogisticRegression(C=0.05, max_iter=3000).fit(z(Xtr), ytr)
        out['gbm'][test] = gbm.predict_proba(Xte)[:, 1]
        out['lr'][test] = lr.predict_proba(z(Xte))[:, 1]
        out['base'][test] = ytr.mean()
        out['thr'][test] = np.quantile(gbm.predict_proba(Xtr)[:, 1], 2 / 3)
    return y, ts, out


def judge(strat: str, df: pl.DataFrame, rng) -> Tuple[str, str]:
    y, ts, o = walk_forward(df)
    oos = ~np.isnan(o['gbm'])
    if oos.sum() < 30:
        return 'NO OOS', f"| {strat} | {df.height} | {int(oos.sum())} | — | — | — | — | — | — | — | — | NO OOS |"
    r = df['r_tp1'].to_numpy()[oos]
    t, yy = ts[oos], y[oos]
    top = o['gbm'][oos] >= o['thr'][oos]
    mid = np.median(t)
    old, new = t < mid, t >= mid
    a_g, a_l = auc(yy, o['gbm'][oos]), auc(yy, o['lr'][oos])
    ll_g, ll_b = logloss(yy, o['gbm'][oos]), logloss(yy, o['base'][oos])

    def mean(mask):
        return float(r[mask].mean()) if mask.sum() else float('nan')
    top_old, all_old = mean(old & top), mean(old)
    top_new, all_new = mean(new & top), mean(new)
    c = day_ci(r[new & top], t[new & top], rng) if (new & top).sum() else None
    ok = (top_old > all_old) and (top_new > all_new) and c is not None and c[0] > 0
    verdict = 'USEFUL' if ok else 'NOT USEFUL'
    ci_s = f"[{c[0]:+.3f}..{c[1]:+.3f}]" if c else '—'
    return verdict, (f"| {strat} | {df.height} | {int(oos.sum())} | {a_g:.3f} | {a_l:.3f} | {ll_g:.4f} / {ll_b:.4f} | "
                     f"{all_old:+.3f} / {top_old:+.3f} ({int((old & top).sum())}) | "
                     f"{all_new:+.3f} / {top_new:+.3f} ({int((new & top).sum())}) | {ci_s} | {verdict} |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', default=os.path.join('data', 'replay', 'run12m'))
    ap.add_argument('--out', default=os.path.join('research', 'meta_replay.md'))
    args = ap.parse_args()
    df = load(args.run)
    rng = np.random.default_rng(29)
    rows, verdicts = [], {}
    small = []
    for strat in sorted(set(df['strategy'].drop_nulls().to_list())):
        d = df.filter(pl.col('strategy') == strat)
        if d.height < MIN_ENTRIES:
            small.append(f"{strat} ({d.height})")
            verdicts[strat] = 'INSUFFICIENT'
            continue
        v, line = judge(strat, d, rng)
        verdicts[strat] = v
        rows.append(line)
    useful = [k for k, v in verdicts.items() if v == 'USEFUL']
    summary = (f"**Summary.** {df.height} passed replay entries; strategies judged (>= {MIN_ENTRIES} entries): "
               f"{len(rows)}; USEFUL by the pre-registered rule: {', '.join(useful) if useful else 'none'}. "
               f"Below {MIN_ENTRIES} entries (not judged): {', '.join(small) if small else 'none'}.")
    lines = ['# Meta-labeling on the archive replay (job 8)', '', summary, '',
             f"Run `{args.run}`; rule and method: the docstring of `research_meta_replay.py`. Label r_tp1 > 0; "
             'purged monthly walk-forward (8h trade life + 1-day embargo); net R = r_tp1 (journal replay, net of fees '
             'and slippage).', '',
             '| strategy | passed entries | OOS rows | AUC LightGBM | AUC logistic | log-loss GBM / base | '
             'older: all / top⅓ (n) | newer: all / top⅓ (n) | newer top⅓ 90% (days) | verdict |',
             '|---|---:|---:|---:|---:|---|---|---|---|---|'] + rows
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
