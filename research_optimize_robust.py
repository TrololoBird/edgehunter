"""
Second pass on research/optimize_matrix.npz (research_optimize.py's simulated R of every entry x PM variant and
its filter flags). The first pass picked each strategy's single best configuration over ~750k (filters x PM) and
7 of 9 failed on the validation months (train +0.3..+1.1R -> validation -0.2..-1.0R: selection luck).
Pre-registered here: a configuration qualifies only when it is positive with its lower 90% bound > 0 in EACH of
the two halves of the training period separately (stable, not one lucky stretch), >= 15 4h clusters in each half;
among those the one with the highest min(half 1, half 2) mean is chosen; validated once on the last 4 months.
Also reported: position management alone (no filter) chosen the same way.
"""
import itertools
import numpy as np
from research_optimize import PM, cluster_stats, TRAIN_MONTHS

z = np.load('research/optimize_matrix.npz', allow_pickle=True)
R, M, strat, ts, clus, names = z['R'], z['M'], z['strat'], z['ts'], z['clus'], list(z['mask_names'])
t0 = ts.min()
from datetime import datetime, timezone
first = datetime.fromtimestamp(t0 / 1000, timezone.utc)
split = int(datetime(first.year + (first.month + TRAIN_MONTHS > 12), (first.month + TRAIN_MONTHS - 1) % 12 + 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
mid = t0 + (split - t0) // 2
lines = ['| strategy | mode | profile | half 1 | half 2 | validation: n, mean [lower 90%] | verdict |', '|---|---|---|---|---|---|---|']
picks = {}
for s in sorted(set(strat)):
    sel = strat == s
    h1, h2, val = sel & (ts < mid), sel & (ts >= mid) & (ts < split), sel & (ts >= split)
    for mode in ('pm only', 'filters + pm'):
        combos = [()] if mode == 'pm only' else [()] + [(i,) for i in range(M.shape[1])] + list(itertools.combinations(range(M.shape[1]), 2))
        best = None
        for combo in combos:
            mk = np.ones(len(R), bool)
            for i in combo:
                mk &= M[:, i]
            a, b = h1 & mk, h2 & mk
            if len(np.unique(clus[a])) < 15 or len(np.unique(clus[b])) < 15:
                continue
            ma, mb = R[a].mean(0), R[b].mean(0)
            score = np.minimum(ma, mb)
            for q in np.argsort(-score)[:3]:
                if score[q] <= 0:
                    break
                sa = cluster_stats(R[a][:, q], clus[a]); sb = cluster_stats(R[b][:, q], clus[b])
                if sa[1] > 0 and sb[1] > 0 and (best is None or score[q] > best[0]):
                    best = (score[q], combo, q, sa, sb)
        if best is None:
            lines.append(f'| {s} | {mode} | - | none stable in both halves | | | no |')
            continue
        _, combo, q, sa, sb = best
        mk = np.ones(len(R), bool)
        for i in combo:
            mk &= M[:, i]
        v = val & mk
        mv, lov, _ = cluster_stats(R[v][:, q], clus[v])
        verdict = 'DEMO' if mv > 0 else 'no'
        name = ' & '.join(names[i] for i in combo) or 'all'
        lines.append(f'| {s} | {mode} | {name} / {PM[q]} | {sa[0]:+.3f} [{sa[1]:+.3f}] | {sb[0]:+.3f} [{sb[1]:+.3f}] | {int(v.sum())}, {mv:+.3f} [{lov:+.3f}] | {verdict} |')
        if verdict == 'DEMO':
            picks.setdefault(s, []).append(dict(mode=mode, filters=[names[i] for i in combo], pm=PM[q], val_n=int(v.sum()), val_mean=float(mv), val_lo=float(lov), half1=float(sa[0]), half2=float(sb[0])))
out = '\n'.join(['# Robust second pass (research_optimize_robust.py)', ''] + lines)
open('research/optimize_robust.md', 'w', encoding='utf-8').write(out + '\n')
import json; json.dump(picks, open('research/optimize_robust_picks.json', 'w'), indent=1, default=str)
print(out)
