"""
D1 of ML_PLAN.md: is the IsolationForest worth its worker process? On the live journal (run where signals.db is):

    .venv\\Scripts\\python research_anomaly.py [--days 30]

Rule anomalies carry the forest's shadow `ml_score` (higher = more unusual). If the forest adds information, the
anomalies it scores highest should be followed by larger moves than the rest of the SAME rule label: the absolute 1h
and 4h return, each divided by the label's median (labels differ in size). Reported per label and pooled: the
Spearman correlation of ml_score with the normalized move, and the top-quintile vs the rest with a block bootstrap
(4h blocks). Pre-registered decision (ML_PLAN.md D2): keep the forest only if the pooled top-quintile / rest ratio
of the 4h move is > 1.1 with the 90% interval above 1 - otherwise remove it (RAM on the laptop).
Writes research/anomaly_d1.md.
"""
import argparse
import os
import sqlite3
import time

import numpy as np
import polars as pl

_ROOT = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(_ROOT, 'research', 'anomaly_d1.md')
DB_PATH = os.path.join(_ROOT, 'signals.db')


def spearman(a, b):
    ra = np.argsort(np.argsort(a))
    rb = np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1]) if len(a) > 2 else float('nan')


def ratio_ci(top, rest, blocks_top, blocks_rest, n=2000, seed=5):
    rng = np.random.default_rng(seed)
    ub = np.unique(np.r_[blocks_top, blocks_rest])
    out = []
    for _ in range(n):
        pick = set(rng.choice(ub, len(ub)))
        mt = np.isin(blocks_top, list(pick))
        mr = np.isin(blocks_rest, list(pick))
        if mt.sum() and mr.sum():
            out.append(top[mt].mean() / rest[mr].mean())
    out = np.sort(out)
    return float(top.mean() / rest.mean()), float(out[int(0.05 * len(out))]), float(out[int(0.95 * len(out))])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=float, default=30)
    args = ap.parse_args()
    since = int((time.time() - args.days * 86400) * 1000)
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    df = pl.read_database("SELECT ts_ms, symbol, group_key, ml_score, ret_1h, ret_4h FROM signals WHERE kind = "
                          "'anomaly' AND ml_score IS NOT NULL AND ret_4h IS NOT NULL AND ts_ms >= ?", con,
                          execute_options={'parameters': [since]})
    con.close()
    lines = [f"# D1 — IsolationForest vs the rule labels ({df.height} rule anomalies with a shadow score, "
             f"last {args.days:g} days)", '',
             '| Label | n | Spearman(score, |1h|) | Spearman(score, |4h|) | top 20% / rest |4h| |', '|---|---:|---:|---:|---:|']
    pooled_t, pooled_r, bt, br = [], [], [], []
    for (label,), g in df.group_by(['group_key']):
        if g.height < 50:
            continue
        s = g['ml_score'].to_numpy()
        m1 = np.abs(g['ret_1h'].fill_null(0).to_numpy())
        m4 = np.abs(g['ret_4h'].to_numpy())
        m1n, m4n = m1 / (np.median(m1) or 1), m4 / (np.median(m4) or 1)
        top = s >= np.quantile(s, 0.8)
        lines.append(f"| {label} | {g.height} | {spearman(s, m1n):+.3f} | {spearman(s, m4n):+.3f} | "
                     f"{m4n[top].mean() / m4n[~top].mean():.2f} |")
        blocks = g['ts_ms'].to_numpy() // (4 * 3_600_000)
        pooled_t.append(m4n[top])
        pooled_r.append(m4n[~top])
        bt.append(blocks[top])
        br.append(blocks[~top])
    if pooled_t:
        r, lo, hi = ratio_ci(np.concatenate(pooled_t), np.concatenate(pooled_r), np.concatenate(bt),
                             np.concatenate(br))
        keep = r > 1.1 and lo > 1.0
        lines += ['', f"Pooled top-20% / rest of the normalized 4h move: {r:.2f} [{lo:.2f}..{hi:.2f}]", '',
                  '## Decision (pre-registered, ML_PLAN.md D2)', '',
                  'KEEP the IsolationForest' if keep else
                  'REMOVE the IsolationForest (CONFIG.ml.anomaly_enabled = False, then delete AnomalyModel and its '
                  'worker): it does not separate the larger moves within a rule label']
    text = '\n'.join(lines) + '\n'
    with open(REPORT_PATH, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)


if __name__ == '__main__':
    main()
