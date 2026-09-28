"""
Pre-registered holdout of the negative-funding short (research/positioning.md): SHORT a coin when its last funding
settlement is <= -0.0317% (a fixed cutoff: the 2025-10..2026-08 bottom decile), hold 72h, one position per coin at a
time; net of 0.20% round trip AND the funding the short pays over the hold (the archive's per-settlement rates).
Reported absolute and vs the universe mean, by half-year; 90% interval by calendar week.

Run: python research_funding.py [--months 24] [--end-month 2025-09]
"""
import argparse
import multiprocessing as mp
import os
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List

import numpy as np

import research_htf as rh

CUTOFF = -0.0003171
HOLD = 72
G: Dict = {}


def coin_trades(j: int) -> List[Dict]:
    from history import Archive
    sym, C, t0, elig = G['coins'][j], G['C'][:, j], G['t0'], G['elig'][:, j]
    archive = Archive(rate_bytes=4e7, cache_dir=os.environ.get('HTF_CACHE') or None)
    f = archive.funding(sym, G['start'], G['end'], raw=True)
    if not len(f):
        return []
    out, busy = [], -1
    n = len(C)
    for ts, rate in f:
        t = int((ts - t0) // rh.HOUR) + 1                # the first full hour after the settlement is known
        if t <= busy or t < 24 or t + HOLD >= n or rate > CUTOFF:
            continue
        day = t // 24 - 1
        if not elig[day] or np.isnan(C[t - 1]) or np.isnan(C[t + HOLD]):
            continue
        entry, exit_ = C[t - 1], C[t + HOLD]
        paid = -f[(f[:, 0] > ts) & (f[:, 0] <= t0 + (t + HOLD) * rh.HOUR), 1].sum()   # a short pays negative funding
        gross = -(exit_ / entry - 1)
        mk = G['mkt']
        mret = mk[t + HOLD] / mk[t - 1] - 1
        out.append({'coin': sym, 'ts': t0 + t * rh.HOUR, 'rate': rate, 'gross': gross,
                    'net': gross - 0.002 - paid, 'rel': gross + mret - 0.002 - paid, 'funding_paid': paid})
        busy = t + HOLD
    return out


def main():
    import polars as pl
    parser = argparse.ArgumentParser()
    parser.add_argument('--months', type=int, default=24)
    parser.add_argument('--end-month', default='2025-09')
    parser.add_argument('--out', default=os.path.join('research', 'funding_holdout.md'))
    args = parser.parse_args()
    t0, coins, O, H, L, C, V, _ = rh.load(args.months, 0, args.end_month)
    elig, _, _, _ = rh.market_state(C, V, coins)
    r1 = np.vstack([np.full(C.shape[1], np.nan), C[1:] / C[:-1] - 1])
    el_h = np.repeat(elig, 24, axis=0)
    el_h = np.vstack([el_h, np.zeros((max(0, C.shape[0] - el_h.shape[0]), C.shape[1]), bool)])[:C.shape[0]]
    mret = np.nanmean(np.where(el_h, r1, np.nan), axis=1)
    y, mth = map(int, args.end_month.split('-'))
    end = date(y + (mth == 12), mth % 12 + 1, 1) - timedelta(days=1)
    start = datetime.fromtimestamp(t0 / 1000, timezone.utc).date()
    G.update(t0=t0, coins=coins, C=C, elig=elig, mkt=np.cumprod(1 + np.nan_to_num(mret)), start=start, end=end)
    rows: List[Dict] = []
    with mp.get_context('fork').Pool(max(1, (os.cpu_count() or 2) - 1)) as pool:
        for res in pool.imap_unordered(coin_trades, range(len(coins)), chunksize=4):
            rows.extend(res)
    df = pl.DataFrame(rows).sort('ts')
    dt = pl.from_epoch(pl.col('ts'), time_unit='ms')
    df = df.with_columns((dt.dt.year().cast(pl.Utf8) + pl.when(dt.dt.month() <= 6).then(pl.lit('-H1'))
                          .otherwise(pl.lit('-H2'))).alias('period'))
    fmt = lambda ms: datetime.fromtimestamp(ms / 1000, timezone.utc).strftime('%Y-%m-%d')  # noqa: E731
    lines = [f"# Negative-funding short, holdout {fmt(df['ts'].min())} .. {fmt(df['ts'].max())} "
             f"({df['coin'].n_unique()} coins, {len(df)} trades)", '',
             "Rule (fixed before the run): short when the last settlement <= -0.0317%, hold 72h, net of 0.20% and the "
             "funding paid. 'vs mean' = plus the universe mean return over the hold (the short's excess).", '',
             '| period | trades | gross | funding paid | net absolute [90%] | net vs universe mean [90%] | win |',
             '|---|---:|---:|---:|---|---|---:|']
    for key, g in [('ALL', df)] + [(k[0], v) for k, v in df.group_by(['period'], maintain_order=True)]:
        wk = (g['ts'].to_numpy() // (7 * 86_400_000)).astype(int)
        a = rh.week_boot(g['net'].to_numpy(), wk)
        r = rh.week_boot(g['rel'].to_numpy(), wk)
        lines.append(f"| {key} | {len(g)} | {g['gross'].mean() * 100:+.2f}% | {g['funding_paid'].mean() * 100:+.2f}% | "
                     f"{a[0] * 100:+.2f}% [{a[1] * 100:+.2f}..{a[2] * 100:+.2f}] | "
                     f"{r[0] * 100:+.2f}% [{r[1] * 100:+.2f}..{r[2] * 100:+.2f}] | {(g['net'] > 0).mean():.0%} |")
    a = rh.week_boot(df['net'].to_numpy(), (df['ts'].to_numpy() // (7 * 86_400_000)).astype(int))
    r = rh.week_boot(df['rel'].to_numpy(), (df['ts'].to_numpy() // (7 * 86_400_000)).astype(int))
    ok = r[1] > 0 and a[0] > 0
    lines += ['', f"**Verdict (pre-registered): {'CONFIRMED' if ok else 'NOT confirmed'}** - net vs mean "
              f"{r[0] * 100:+.2f}% [{r[1] * 100:+.2f}..{r[2] * 100:+.2f}], absolute {a[0] * 100:+.2f}%."]
    text = '\n'.join(lines) + '\n'
    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)


if __name__ == '__main__':
    main()
