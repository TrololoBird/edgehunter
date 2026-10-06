"""
Task 1.5 of docs/CLOUD_TASKS.md: eng-59 vs eng-72 replay, per strategy (the tables; the Russian summary on top of
research/eng72_vs_eng59.md is written from them).

- full-trade final R (the card's own exit, `final_r`, net) of the entered cards: n, mean, 90% bootstrap interval of
  4h clusters (floor(entered / 4h) x direction, 2000 draws), share of wins; by side and by month;
- vetoes: per strategy x veto reason the vetoed entries' 8h replay r_tp1 next to the passed entries' (the same replay);
- geometry and entries vs placebo come from research_geometry_audit.py / research_entry_edge.py run on each summary
  (research/geometry_audit[_eng72].md, research/entry_edge[_eng72].md), quoted by the report.

    python research_eng72_vs_eng59.py research/replay_summary.parquet research/replay_summary_eng72.parquet > tables.md
"""
import random
import sys

import numpy as np
import polars as pl

H4 = 4 * 3_600_000


def boot(r, cl, n=2000, seed=11):
    groups = {}
    for v, c in zip(r, cl):
        groups.setdefault(c, []).append(v)
    blocks = list(groups.values())
    if len(blocks) < 5:
        return None, None, len(blocks)
    rng = random.Random(seed)
    k = len(blocks)
    means = []
    for _ in range(n):
        vals = [v for _ in range(k) for v in blocks[rng.randrange(k)]]
        means.append(float(np.mean(vals)))
    lo, hi = np.percentile(means, [5, 95])
    return lo, hi, k


def cards(path):
    d = pl.read_parquet(path)
    if 'stage' in d.columns:
        d = d.filter(pl.col('stage').is_null() | (pl.col('stage') == 'card'))
    return d.filter(pl.col('entered_ms').is_not_null() & pl.col('final_r').is_not_null() &
                    pl.col('final_r').is_finite()).with_columns(
        ((pl.col('entered_ms') // H4).cast(pl.Utf8) + '_' + pl.col('direction').cast(pl.Utf8)).alias('cl'),
        pl.from_epoch('entered_ms', time_unit='ms').dt.strftime('%Y-%m').alias('month'))


def summary_rows(c):
    rows = []
    for strat in sorted(c['strategy'].unique().to_list()):
        for side, sub in (('all', c.filter(pl.col('strategy') == strat)),
                          ('long', c.filter((pl.col('strategy') == strat) & (pl.col('direction') > 0))),
                          ('short', c.filter((pl.col('strategy') == strat) & (pl.col('direction') < 0)))):
            if sub.height == 0:
                continue
            lo, hi, k = boot(sub['final_r'].to_list(), sub['cl'].to_list())
            rows.append(dict(strategy=strat, side=side, n=sub.height, clusters=k, mean=sub['final_r'].mean(), lo=lo,
                             hi=hi, win=(sub['final_r'] > 0).mean()))
    return rows


def fmt(x, s='+.3f'):
    return '—' if x is None else format(x, s)


def main():
    old, new = sys.argv[1], sys.argv[2]
    out = []
    data = {'eng-59': cards(old), 'eng-72': cards(new)}
    sums = {k: {(r['strategy'], r['side']): r for r in summary_rows(v)} for k, v in data.items()}
    out += ['## Итоговый R по полной сделке (final_r карточки, нетто), 90% бутстрэп 4h-кластеров', '',
            '| стратегия | сторона | eng-59 n | eng-59 R [90%] | eng-72 n | eng-72 кластеров | eng-72 R [90%] | eng-72 win |',
            '|---|---|---:|---|---:|---:|---|---:|']
    keys = sorted(set(sums['eng-59']) | set(sums['eng-72']), key=lambda k: (k[0], ['all', 'long', 'short'].index(k[1])))
    for key in keys:
        a, b = sums['eng-59'].get(key), sums['eng-72'].get(key)
        ca = f"{fmt(a['mean'])} [{fmt(a['lo'])}..{fmt(a['hi'])}]" if a else '—'
        cb = f"{fmt(b['mean'])} [{fmt(b['lo'])}..{fmt(b['hi'])}]" if b else '—'
        out.append(f"| {key[0]} | {key[1]} | {a['n'] if a else 0} | {ca} | {b['n'] if b else 0} | "
                   f"{b['clusters'] if b else 0} | {cb} | {fmt(b['win'], '.0%') if b else '—'} |")
    out += ['', '## eng-72 по месяцам: средний final_r (n)', '']
    c = data['eng-72']
    months = sorted(c['month'].unique().to_list())
    out.append('| стратегия | ' + ' | '.join(m[2:] for m in months) + ' |')
    out.append('|---|' + '---:|' * len(months))
    for strat in sorted(c['strategy'].unique().to_list()):
        cells = []
        for m in months:
            s = c.filter((pl.col('strategy') == strat) & (pl.col('month') == m))
            cells.append(f"{s['final_r'].mean():+.2f} ({s.height})" if s.height else '')
        out.append(f"| {strat} | " + ' | '.join(cells) + ' |')
    out += ['', '## Вето eng-72: r_tp1 (8h реплей) отклонённых входов против прошедших', '',
            '| стратегия | вето | n | r_tp1 отклонённых | r_tp1 прошедших |', '|---|---|---:|---:|---:|']
    e = pl.read_parquet(new).filter((pl.col('stage') == 'entry') & pl.col('r_tp1').is_not_null() &
                                    pl.col('r_tp1').is_finite())
    passed = e.filter(pl.col('vetoed').is_null()).group_by('strategy').agg(pl.col('r_tp1').mean().alias('p'))
    pmap = dict(passed.iter_rows())
    vt = (e.filter(pl.col('vetoed').is_not_null()).group_by('strategy', 'vetoed')
          .agg(pl.len().alias('n'), pl.col('r_tp1').mean().alias('r')).sort('strategy', 'n', descending=[False, True]))
    for strat, veto, n, r in vt.iter_rows():
        if n >= 20:
            out.append(f"| {strat} | {veto} | {n} | {r:+.3f} | {fmt(pmap.get(strat))} |")
    print('\n'.join(out))


if __name__ == '__main__':
    main()
