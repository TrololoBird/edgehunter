"""
Do classic indicator confirmations separate good entries from bad ones? (2026-10-05, the owner's question: "the classic
strategies do not work as published - they need confirmations")

Data: every entry of the cloud's archive replay of the live card lifecycle (research/replay_summary.parquet: 40 coins x
12 months, 2025-09-30 .. 2026-09-30, vetoed entries included - they are replayed too) with its outcome `r_tp1` (R of
the plan, net of costs). Indicators from the archive's monthly 15m and 1h futures klines, read on the last candle that
CLOSED at or before the entry (no look-ahead), oriented to the trade's direction.

PRE-REGISTERED RULE (written before the first run, not changed after it):
- Cells = strategy x timeframe (15m, 1h) x rule (RULES below, each a boolean "the indicator agrees with the trade").
- Discovery = the first half of the replay's time span; validation = the second half, looked at once.
- Discovery: a cell qualifies when both its 'agree' and 'disagree' groups span >= 30 independent 4h clusters (one
  direction's entries in one 4h block are one cluster) and the mean R difference agree - all has a block-bootstrap
  one-sided p-value of "diff <= 0"; cells are kept at a Benjamini-Hochberg false discovery rate of 0.10 over ALL
  tested cells.
- Validation (second half, kept cells only): CONFIRMED when the agree - all difference is > 0 with the 90% block
  bootstrap interval's lower bound > 0. USEFUL when, in addition, the agree group's own mean R is > 0 (a filter that
  only shrinks a loss is CONFIRMED but not USEFUL).
- No combinations of rules are searched (each extra condition multiplies the cells); a rule that is CONFIRMED may be
  combined later only as a new pre-registered test.

Output: research/indicator_confirms.md and research/indicator_confirms.parquet (every cell's numbers).
Downloads go through history.Archive at --rate bytes/s (default 300 KB/s: the live bot shares the link).
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import argparse
import logging
import os
from datetime import date, datetime, timezone

import numpy as np
import polars as pl

from history import Archive

logger = logging.getLogger('indicator_confirms')

HOUR = 3_600_000
BLOCK = 4 * HOUR
TF_MS = {'15m': 15 * 60_000, '1h': HOUR}
BOOT = 2000
SEED = 7


from strategies.ind_panel import indicators, rules  # noqa: E402  (shared with the live journal)


# ---------------------------------------------------------------------- statistics

def block_boot(r: np.ndarray, clusters: np.ndarray, mask: np.ndarray, rng) -> np.ndarray:
    """Bootstrap of mean(r[mask]) - mean(r), resampling whole clusters. Returns BOOT differences."""
    uniq, inv = np.unique(clusters, return_inverse=True)
    n = len(uniq)
    s_all = np.bincount(inv, weights=r, minlength=n)
    c_all = np.bincount(inv, minlength=n).astype(float)
    s_in = np.bincount(inv, weights=r * mask, minlength=n)
    c_in = np.bincount(inv, weights=mask.astype(float), minlength=n)
    idx = rng.integers(0, n, size=(BOOT, n))
    a = s_in[idx].sum(1) / np.maximum(c_in[idx].sum(1), 1e-12)
    b = s_all[idx].sum(1) / np.maximum(c_all[idx].sum(1), 1e-12)
    return a - b


def bh(pvals: np.ndarray, q: float) -> np.ndarray:
    order = np.argsort(pvals)
    m = len(pvals)
    passed = np.zeros(m, bool)
    cutoff = 0
    for rank, i in enumerate(order, 1):
        if pvals[i] <= q * rank / m:
            cutoff = rank
    passed[order[:cutoff]] = True
    return passed


# ---------------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--rate', type=float, default=300_000)
    p.add_argument('--out', default='research/indicator_confirms')
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', datefmt='%H:%M:%S')

    ent = (pl.read_parquet('research/replay_summary.parquet',
                           columns=['symbol', 'strategy', 'direction', 'ts', 'vetoed', 'r_tp1'])
           .filter(pl.col('r_tp1').is_not_null()).sort('ts'))
    t0, t1 = ent['ts'].min(), ent['ts'].max()
    mid = (t0 + t1) // 2
    first = datetime.fromtimestamp(t0 / 1000, timezone.utc).date()
    start = date(first.year - (first.month <= 2), (first.month - 3) % 12 + 1, 1)    # 2 months of warm-up
    end = datetime.fromtimestamp(t1 / 1000, timezone.utc).date()
    arch = Archive(rate_bytes=args.rate)

    frames = []
    for sym in ent['symbol'].unique().sort().to_list():
        code = sym.split(':')[0].replace('/', '')
        part = ent.filter(pl.col('symbol') == sym)
        ts = part['ts'].to_numpy()
        dirs = part['direction'].to_numpy()
        cols = {}
        for tf, ms in TF_MS.items():
            k = arch.klines_ohlc('futures', code, tf, start, end)
            if len(k) < 300:
                logger.info(f"{sym} {tf}: {len(k)} candles, skipped")
                continue
            ind = indicators(k)
            close_ms = k[:, 0] + ms
            # the last candle closed at or before the entry
            pos = np.searchsorted(close_ms, ts, side='right') - 1
            ok = pos >= 250
            for d in (1, -1):
                rs = rules(ind, d)
                for name, arr in rs.items():
                    col = cols.setdefault(f'{tf}:{name}', np.full(len(ts), None, dtype=object))
                    sel = ok & (dirs == d)
                    col[sel] = np.asarray(arr, dtype=bool)[pos[sel]] & ~np.isnan(np.asarray(arr, dtype=float)[pos[sel]])
        if cols:
            frames.append(part.with_columns([pl.Series(n, v.tolist(), dtype=pl.Boolean) for n, v in cols.items()]))
        logger.info(f"{sym}: {len(ts)} entries (archive: {arch.downloaded / 1e6:.0f} MB downloaded, "
                    f"{arch.cached} cached files)")
    data = pl.concat(frames, how='diagonal_relaxed')
    data = data.with_columns(((pl.col('ts') // BLOCK) * 2 + (pl.col('direction') > 0).cast(pl.Int64)).alias('cluster'),
                             (pl.col('ts') > mid).alias('late'))
    rule_cols = [c for c in data.columns if ':' in c]
    rng = np.random.default_rng(SEED)

    rows = []
    for strat in data['strategy'].unique().sort().to_list():
        for half in (False, True):
            sub = data.filter((pl.col('strategy') == strat) & (pl.col('late') == half))
            r = sub['r_tp1'].to_numpy()
            cl = sub['cluster'].to_numpy()
            for col in rule_cols:
                m = sub[col].to_numpy()
                valid = np.array([x is not None for x in m])
                if valid.sum() < 50:
                    continue
                rv, cv, mv = r[valid], cl[valid], np.array([bool(x) for x in m[valid]])
                n_in, n_out = len(np.unique(cv[mv])), len(np.unique(cv[~mv]))
                diff = rv[mv].mean() - rv.mean() if mv.any() else np.nan
                boot = block_boot(rv, cv, mv, rng) if mv.any() and (~mv).any() else np.array([np.nan])
                rows.append(dict(strategy=strat, rule=col, late=half, n=int(valid.sum()), n_agree=int(mv.sum()),
                                 clusters_agree=n_in, clusters_disagree=n_out, mean_all=float(rv.mean()),
                                 mean_agree=float(rv[mv].mean()) if mv.any() else np.nan,
                                 mean_disagree=float(rv[~mv].mean()) if (~mv).any() else np.nan,
                                 diff=float(diff), p=float((np.sum(boot <= 0) + 1) / (len(boot) + 1)),
                                 lo90=float(np.nanpercentile(boot, 5)), hi90=float(np.nanpercentile(boot, 95))))
    res = pl.DataFrame(rows)
    disc = res.filter(~pl.col('late') & (pl.col('clusters_agree') >= 30) & (pl.col('clusters_disagree') >= 30))
    keep = bh(disc['p'].to_numpy(), 0.10) if disc.height else np.array([], bool)
    kept = disc.filter(pl.Series(keep)).select('strategy', 'rule')
    val = res.filter(pl.col('late')).join(kept, on=['strategy', 'rule'], how='inner')
    val = val.with_columns((pl.col('lo90') > 0).alias('confirmed'),
                           ((pl.col('lo90') > 0) & (pl.col('mean_agree') > 0)).alias('useful'))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    res.write_parquet(args.out + '.parquet')

    lines = ['# Indicator confirmations on the archive replay (pre-registered, research_indicator_confirms.py)', '',
             f'Entries: {data.height} of {data["strategy"].n_unique()} strategies; discovery < '
             f'{datetime.fromtimestamp(mid / 1000, timezone.utc):%Y-%m-%d} <= validation. Cells tested in discovery: '
             f'{disc.height}; kept at BH q 0.10: {kept.height}.', '',
             '## Validation of the kept cells', '',
             '| strategy | rule | n agree / all | mean R all | agree | disagree | diff [90%] | verdict |',
             '|---|---|---|---|---|---|---|---|']
    for r in val.sort(['useful', 'confirmed', 'diff'], descending=True).iter_rows(named=True):
        verdict = 'USEFUL' if r['useful'] else 'CONFIRMED' if r['confirmed'] else 'not confirmed'
        lines.append(f"| {r['strategy']} | {r['rule']} | {r['n_agree']} / {r['n']} | {r['mean_all']:+.3f} | "
                     f"{r['mean_agree']:+.3f} | {r['mean_disagree']:+.3f} | {r['diff']:+.3f} "
                     f"[{r['lo90']:+.3f}..{r['hi90']:+.3f}] | {verdict} |")
    if not val.height:
        lines.append('| - | no cell passed discovery | | | | | | |')
    lines += ['', '## Discovery: the 25 largest differences (before the BH correction)', '',
              '| strategy | rule | n agree / all | agree | disagree | diff [90%] | p |', '|---|---|---|---|---|---|---|']
    for r in disc.sort('diff', descending=True).head(25).iter_rows(named=True):
        lines.append(f"| {r['strategy']} | {r['rule']} | {r['n_agree']} / {r['n']} | {r['mean_agree']:+.3f} | "
                     f"{r['mean_disagree']:+.3f} | {r['diff']:+.3f} [{r['lo90']:+.3f}..{r['hi90']:+.3f}] | {r['p']:.4f} |")
    with open(args.out + '.md', 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
