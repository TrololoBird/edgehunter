"""
Report of the archive replay (replay.py, B9), pre-registered: per strategy and setup
- the cards' own net result (final_r, eng-58 lifecycle exits) - mean, 90% interval by 4h clusters, older / newer half;
- the journal-style replay of every entry (r_tp1 net) - passed vs each veto reason (does the veto reject worse?);
- the plan's open questions answered on the same trades: 2.3 trendline (retest limit - the replay holds the live
  rule), 2.4 Bollinger (opposite-band exit = final_r) vs fixed TP1 (r_tp1), 3.1 exits by nature (final_r vs r_tp1 vs
  r_tp2 vs r_be per strategy).
A strategy is "positive on the archive" only if its mean final_r is > 0 in both halves and the 90% interval of all
its cards is above 0 (the live verdict's rule applied to history; it does not replace the live verdict).

Run: .venv\\Scripts\\python research_replay_report.py [--run data/replay/run] [--out research/replay.md]
"""
import argparse
import glob
import os
from typing import List

import numpy as np
import polars as pl


def ci(values: np.ndarray, clusters: np.ndarray, rng, draws: int = 2000):
    u = np.unique(clusters)
    if len(u) < 5:
        return None
    idx = {k: np.flatnonzero(clusters == k) for k in u}
    bs = [values[np.concatenate([idx[k] for k in rng.choice(u, len(u))])].mean() for _ in range(draws)]
    return np.percentile(bs, [5, 95])


def fmt(x):
    return '—' if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:+.3f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', default=os.path.join('data', 'replay', 'run'))
    ap.add_argument('--out', default=os.path.join('research', 'replay.md'))
    args = ap.parse_args()
    cards = pl.concat([pl.read_parquet(f) for f in glob.glob(os.path.join(args.run, '*', 'cards.parquet'))],
                      how='diagonal_relaxed')
    entries = pl.concat([pl.read_parquet(f) for f in glob.glob(os.path.join(args.run, '*', 'entries.parquet'))],
                        how='diagonal_relaxed')
    rng = np.random.default_rng(23)
    lines: List[str] = ['# Archive replay of the live card lifecycle (B9)', '',
                        f"{cards.height} cards, {entries.filter(pl.col('stage') == 'entry').height} entries "
                        f"(passed + vetoed), run `{args.run}`. Rules: the docstring of `research_replay_report.py`.", '']
    traded = cards.filter(pl.col('final_r').is_not_null())
    if traded.height:
        ts = traded['entered_ms'].to_numpy()
        mid = (ts.min() + ts.max()) / 2
        lines += ['## Cards (final_r: the lifecycle exit, net)', '',
                  '| strategy | cards | mean | 90% (4h clusters) | older | newer | win | verdict |',
                  '|---|---:|---:|---|---:|---:|---:|---|']
        for strat in sorted(set(traded['strategy'].to_list())):
            t = traded.filter(pl.col('strategy') == strat)
            r = t['final_r'].to_numpy()
            e = t['entered_ms'].to_numpy()
            cl = (e // (4 * 3_600_000)) * np.sign(t['direction'].to_numpy())
            c = ci(r, cl, rng)
            old, new = r[e < mid], r[e >= mid]
            ok = c is not None and c[0] > 0 and len(old) and len(new) and old.mean() > 0 and new.mean() > 0
            lines.append(f"| {strat} | {len(r)} | {r.mean():+.3f} | "
                         f"{'[' + fmt(c[0]) + '..' + fmt(c[1]) + ']' if c is not None else '—'} | "
                         f"{fmt(old.mean() if len(old) else None)} | {fmt(new.mean() if len(new) else None)} | "
                         f"{(r > 0).mean():.0%} | {'POSITIVE' if ok else '-'} |")
        lines += ['', '## Exits by nature (3.1): the same entered cards, mean net R', '',
                  '| strategy | lifecycle exit (final_r) | all at TP1 (r_tp1) | all at TP2 (r_tp2) | BE after TP1 (r_be) |',
                  '|---|---:|---:|---:|---:|']
        ent = entries.filter((pl.col('stage') == 'entry') & pl.col('vetoed').is_null())
        for strat in sorted(set(traded['strategy'].to_list())):
            t = traded.filter(pl.col('strategy') == strat)
            e = ent.filter(pl.col('strategy') == strat) if 'strategy' in ent.columns else ent.head(0)
            m = lambda col: float(e[col].drop_nulls().mean()) if col in e.columns and e[col].drop_nulls().len() else None  # noqa: E731
            lines.append(f"| {strat} | {fmt(float(t['final_r'].mean()))} | {fmt(m('r_tp1'))} | {fmt(m('r_tp2'))} | "
                         f"{fmt(m('r_be'))} |")
    ent = entries.filter((pl.col('stage') == 'entry') & pl.col('r_tp1').is_not_null()) if 'r_tp1' in entries.columns \
        else entries.head(0)
    if ent.height:
        lines += ['', '## Vetoes: entries rejected vs passed (r_tp1 net, journal replay)', '',
                  '| strategy | veto | n | mean r_tp1 | passed mean | rejected worse? |', '|---|---|---:|---:|---:|---|']
        for strat in sorted(set(ent['strategy'].drop_nulls().to_list())):
            e = ent.filter(pl.col('strategy') == strat)
            passed = e.filter(pl.col('vetoed').is_null())['r_tp1']
            pm = float(passed.mean()) if passed.len() else None
            for veto in sorted(set(e['vetoed'].drop_nulls().to_list())):
                v = e.filter(pl.col('vetoed') == veto)['r_tp1']
                vm = float(v.mean())
                lines.append(f"| {strat} | {veto} | {v.len()} | {vm:+.3f} | {fmt(pm)} | "
                             f"{'yes' if pm is not None and vm < pm else 'no' if pm is not None else '—'} |")
    st = entries.filter(pl.col('stage') == 'setup')
    if st.height:
        lines += ['', '## Setups that never became a card (by reason)', '', '| setup | reason | n |', '|---|---|---:|']
        for row in st.group_by('setup', 'vetoed').len().sort('len', descending=True).head(40).iter_rows():
            lines.append(f"| {row[0]} | {row[1]} | {row[2]} |")
    text = '\n'.join(lines)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(text + '\n')
    print(text)


if __name__ == '__main__':
    main()
