"""
Do the bot's entry confirmations and the minimum-confirmation rule select better trades? Reads the card rows of
`research_cards.py --confirm record` / `research_maniac.py --confirm record` (every trigger entered, its confirmations
recorded: conf_flow / spot / oi / orderflow / vsa / htf_zone / smt / killzone, conf_n = how many were positive) and
splits each strategy's entries (cards that passed the context vetoes) by them.

PRE-REGISTERED (written before the results, 2026-10-03), the same bar as the Live verdict:
- a split (one confirmation present, or conf_n >= k for k = 1..5) is tested only where both of its halves have >= 30
  entries in the DEVELOPMENT part;
- it SELECTS when, in development, (with - without) has a 90% block-bootstrap interval above 0 with q <= 0.10
  (Benjamini-Hochberg over every split x strategy tested), AND in the HOLDOUT the entries with it have mean net R > 0
  with the interval's lower bound > -0.05 R and still beat the entries without it (difference > 0);
- otherwise the confirmation is information, not a filter. conf_n >= 1 is the bot's current minimum rule
  (CONFIG.orderflow.min_confirmations): it is tested like the others.
What the archive cannot hold (strategies/confirm.py): the footprint kinds of `orderflow` (stacked imbalance,
absorption, finished auction) - here `orderflow` is only the CVD divergence of reversals; multi-venue flows (Binance
alone); liquidations, books. Those stay for the live journal (stats.py).

Run: .venv/bin/python research_confirms.py --rows a.parquet [b.parquet ...] --split 2025-04-01 --out research/x.md
"""
import argparse
import os
from datetime import date, datetime, timezone
from typing import List

import numpy as np
import polars as pl

from research_cards import CONF_NAMES, H4_MS, _block_ci

MIN_HALF = 30


def _blocks(e: pl.DataFrame) -> np.ndarray:
    return (e['ts_ms'].to_numpy() // H4_MS) * 2 + (e['direction'].to_numpy() > 0)


def _stat(e: pl.DataFrame):
    if e.height < 10:
        return (float('nan'),) * 4
    mean, lo, hi, p, _ = _block_ci(e['r_tp1'].to_numpy().astype(float), _blocks(e))
    return mean, lo, hi, p


def _diff(a: pl.DataFrame, b: pl.DataFrame):
    """Mean R of a minus mean R of b with a block-bootstrap interval (blocks resampled jointly)."""
    if a.height < 10 or b.height < 10:
        return (float('nan'),) * 4
    rng = np.random.default_rng(11)
    ra, rb = a['r_tp1'].to_numpy().astype(float), b['r_tp1'].to_numpy().astype(float)
    ba, bb = _blocks(a), _blocks(b)
    keys = np.unique(np.r_[ba, bb])
    ia = {k: np.flatnonzero(ba == k) for k in keys}
    ib = {k: np.flatnonzero(bb == k) for k in keys}
    obs = ra.mean() - rb.mean()
    draws = []
    for _ in range(2000):
        pick = rng.choice(keys, len(keys))
        xa = np.concatenate([ra[ia[k]] for k in pick])
        xb = np.concatenate([rb[ib[k]] for k in pick])
        if len(xa) and len(xb):
            draws.append(xa.mean() - xb.mean())
    draws = np.asarray(draws)
    lo, hi = np.quantile(draws, [0.05, 0.95])
    p = float(min(1.0, 2 * min((draws <= 0).mean(), (draws >= 0).mean())))
    return float(obs), float(lo), float(hi), p


def splits(e: pl.DataFrame):
    """(label, mask with, mask without) of every pre-registered split."""
    for name in CONF_NAMES:
        col = f'conf_{name}'
        if col in e.columns:
            yield name, pl.col(col) == 1.0, pl.col(col) == 0.0
    for k in range(1, 6):
        yield f'conf_n >= {k}', pl.col('conf_n') >= k, pl.col('conf_n') < k


def report(df: pl.DataFrame, split_ms: int, title: str) -> str:
    from research_edges import bh
    f = lambda v, d=3: '—' if v is None or v != v else f"{v:+.{d}f}"  # noqa: E731
    e_all = df.filter((pl.col('status') == 'ENTRY') & pl.col('r_tp1').is_not_null() & (pl.col('vetoed').fill_null('') == '')
                      & pl.col('conf_n').is_not_null())
    dev_all, hold_all = e_all.filter(pl.col('ts_ms') < split_ms), e_all.filter(pl.col('ts_ms') >= split_ms)
    lines = [f"# Entry confirmations on the archive: {title}", '',
             f"{e_all['symbol'].n_unique()} coins, {e_all.height} entries that passed the context vetoes (every trigger "
             f"entered, confirmations recorded). Development before "
             f"{datetime.fromtimestamp(split_ms / 1000, tz=timezone.utc).date()}, holdout after. R = net R at TP1 "
             f"(research_cards). [90%] = block bootstrap over 4h x direction blocks. The rule is in the docstring "
             f"(pre-registered).", '',
             '## Base: every entry, and the share of entries each confirmation is present in', '',
             '| strategy | dev entries | dev R [90%] | holdout entries | holdout R [90%] | ' +
             ' | '.join(CONF_NAMES) + ' | mean conf_n |',
             '|---|---:|---|---:|---|' + '---:|' * (len(CONF_NAMES) + 1)]
    strategies = sorted(e_all['strategy'].unique().to_list())
    for s in strategies + ['ALL']:
        e = e_all if s == 'ALL' else e_all.filter(pl.col('strategy') == s)
        d, h = e.filter(pl.col('ts_ms') < split_ms), e.filter(pl.col('ts_ms') >= split_ms)
        md, ld, hd, _ = _stat(d)
        mh, lh, hh, _ = _stat(h)
        shares = []
        for name in CONF_NAMES:
            col = e[f'conf_{name}'].drop_nulls()
            shares.append('n/a' if not len(col) else f"{col.mean():.0%}")
        lines.append(f"| {s} | {d.height} | {f(md)} [{f(ld)}..{f(hd)}] | {h.height} | {f(mh)} [{f(lh)}..{f(hh)}] | "
                     + ' | '.join(shares) + f" | {e['conf_n'].mean():.2f} |")
    tests = []
    for s in strategies + ['ALL']:
        dv = dev_all if s == 'ALL' else dev_all.filter(pl.col('strategy') == s)
        ho = hold_all if s == 'ALL' else hold_all.filter(pl.col('strategy') == s)
        for label, yes, no in splits(dv):
            a, b = dv.filter(yes), dv.filter(no)
            if a.height < MIN_HALF or b.height < MIN_HALF:
                continue
            dd = _diff(a, b)
            ha, hb = ho.filter(yes), ho.filter(no)
            tests.append((s, label, a, b, dd, ha, hb, _stat(ha), _diff(ha, hb)))
    qs = bh([t[4][3] for t in tests])
    lines += ['', '## Splits (development: with - without; holdout: the entries with it, and with - without)', '',
              '| strategy | split | dev with / without | dev R with | dev R without | dev diff [90%] | q | '
              'holdout with / without | holdout R with [90%] | holdout diff [90%] | verdict |',
              '|---|---|---:|---:|---:|---|---:|---:|---|---|---|']
    passed: List[str] = []
    for (s, label, a, b, (dm, dl, dh, _), ha, hb, (hm, hl, hhi, _), (xm, xl, xh, _)), q in zip(tests, qs):
        ok = dl > 0 and q <= 0.10 and hm == hm and hm > 0 and hl > -0.05 and xm == xm and xm > 0
        if ok:
            passed.append(f"{s}: {label}")
        lines.append(f"| {s} | {label} | {a.height} / {b.height} | {f(a['r_tp1'].mean())} | {f(b['r_tp1'].mean())} | "
                     f"{f(dm)} [{f(dl)}..{f(dh)}] | {'—' if q != q else f'{q:.3f}'} | {ha.height} / {hb.height} | "
                     f"{f(hm)} [{f(hl)}..{f(hhi)}] | {f(xm)} [{f(xl)}..{f(xh)}] | {'SELECTS' if ok else '—'} |")
    lines += ['', '## Verdict', '',
              ('Splits that pass the pre-registered rule: ' + '; '.join(passed)) if passed else
              'No confirmation and no conf_n threshold passes the pre-registered rule on the archive.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rows', nargs='+', required=True)
    parser.add_argument('--split', required=True, help='first day of the holdout (YYYY-MM-DD)')
    parser.add_argument('--title', default='')
    parser.add_argument('--out', default=os.path.join('research', 'confirms.md'))
    args = parser.parse_args()
    frames = [pl.read_parquet(p) for p in args.rows]
    cols = ['symbol', 'ts_ms', 'strategy', 'direction', 'vetoed', 'status', 'r_tp1'] + \
        [f'conf_{n}' for n in CONF_NAMES] + ['conf_n']
    df = pl.concat([fr.select([pl.col(c) if c in fr.columns else pl.lit(None, dtype=pl.Float64).alias(c)
                               for c in cols]).with_columns([pl.col(f'conf_{n}').cast(pl.Float64) for n in CONF_NAMES]
                                                            + [pl.col('conf_n').cast(pl.Float64)])
                    for fr in frames], how='vertical_relaxed')
    d = date.fromisoformat(args.split)
    split_ms = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)
    text = report(df, split_ms, args.title or ', '.join(args.rows))
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)


if __name__ == '__main__':
    main()
