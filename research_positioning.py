# ruff: noqa: E741
"""
Does POSITIONING carry directional information that price / levels do not? (Price-based entries replayed so far hit
their targets as often as a random walk.) Binance archive, 12 months, every coin of the point-in-time universe,
sampled every 8h: funding (the last settlement's rate and its z-score vs the coin's previous 30 days), the
global accounts' long/short ratio and the top traders' position ratio (z vs 30 days), the 3-day OI change and the
3-day price change. Forward return over 24h / 72h minus the universe mean (the same hours).

Pre-registered reading: the extreme deciles (pooled over coins) of each feature, in the classic contrarian direction
(crowded longs -> short, crowded shorts -> long; for OI up with price up -> continuation is the alternative), their
mean forward excess return with a 90% interval by week, the older half and the newer half separately, and the
net result of trading them (0.20% round trip). A feature is informative only if its extreme-decile spread has the
same sign in both halves and the newer half's interval excludes 0.

Run: python research_positioning.py [--months 12]
"""
import argparse
import multiprocessing as mp
import os
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List

import numpy as np

import research_htf as rh

G: Dict = {}


def coin_rows(j: int) -> List[Dict]:
    from history import Archive
    sym = G['coins'][j]
    C, t0, elig = G['C'][:, j], G['t0'], G['elig'][:, j]
    archive = Archive(rate_bytes=4e7, cache_dir=os.environ.get('HTF_CACHE') or None)
    try:
        m = archive.metrics(sym, G['start'], G['end'])
        f = archive.funding(sym, G['start'] - timedelta(days=40), G['end'], raw=True)
    except Exception:
        return []
    if m is None or not len(m.get('ts', [])):
        return []
    n = len(C)
    hour_idx = ((np.asarray(m['ts']) - t0) // rh.HOUR).astype(int)
    series = {}
    for key in ('oi', 'global', 'top_pos'):
        arr = np.full(n, np.nan)
        ok = (hour_idx >= 0) & (hour_idx < n)
        arr[hour_idx[ok]] = np.asarray(m[key])[ok]
        # forward-fill within 3 hours only
        last = np.nan
        age = 99
        for i in range(n):
            if np.isnan(arr[i]):
                age += 1
                if age <= 3:
                    arr[i] = last
            else:
                last, age = arr[i], 0
        series[key] = arr
    fts = f[:, 0] if len(f) else np.empty(0)
    frate = f[:, 1] if len(f) else np.empty(0)
    out = []
    for t in range(24 * 33, n - 73, 8):
        day = t // 24 - 1
        if day < 0 or day >= len(elig) or not elig[day] or np.isnan(C[t]) or np.isnan(C[t + 72]):
            continue
        now_ms = t0 + t * rh.HOUR
        k = np.searchsorted(fts, now_ms, side='right') - 1
        if k < 60:
            continue
        hist = frate[max(0, k - 90):k]                    # ~30 days of 8h settlements before
        fz = (frate[k] - hist.mean()) / hist.std() if hist.std() > 0 else np.nan
        row = {'coin': sym, 'ts': now_ms, 'funding': frate[k], 'funding_z': fz}
        for key in ('global', 'top_pos'):
            s = series[key]
            w = s[t - 720:t]
            w = w[~np.isnan(w)]
            row[f'{key}_z'] = (s[t - 1] - w.mean()) / w.std() if len(w) > 200 and w.std() > 0 and not np.isnan(s[t - 1]) else np.nan
        oi = series['oi']
        row['oi_3d'] = oi[t - 1] / oi[t - 73] - 1 if not np.isnan(oi[t - 1]) and not np.isnan(oi[t - 73]) and oi[t - 73] else np.nan
        row['px_3d'] = C[t - 1] / C[t - 73] - 1 if not np.isnan(C[t - 73]) else np.nan
        mk = G['mkt']
        row['fwd_24h'] = C[t + 24] / C[t] - 1 - (mk[t + 24] / mk[t] - 1)
        row['fwd_72h'] = C[t + 72] / C[t] - 1 - (mk[t + 72] / mk[t] - 1)
        out.append(row)
    return out


def main():
    import polars as pl
    parser = argparse.ArgumentParser()
    parser.add_argument('--months', type=int, default=12)
    parser.add_argument('--out', default=os.path.join('research', 'positioning.md'))
    args = parser.parse_args()
    t0, coins, O, H, L, C, V, _ = rh.load(args.months + 2, 0)
    elig, _, _, _ = rh.market_state(C, V, coins)
    r1 = np.vstack([np.full(C.shape[1], np.nan), C[1:] / C[:-1] - 1])
    el_h = np.repeat(elig, 24, axis=0)
    el_h = np.vstack([el_h, np.zeros((max(0, C.shape[0] - el_h.shape[0]), C.shape[1]), bool)])[:C.shape[0]]
    mret = np.nanmean(np.where(el_h, r1, np.nan), axis=1)
    today = datetime.now(timezone.utc).date()
    end = date(today.year, today.month, 1) - timedelta(days=1)
    G.update(t0=t0, coins=coins, C=C, elig=elig, mkt=np.cumprod(1 + np.nan_to_num(mret)),
             start=end - timedelta(days=30 * args.months), end=end)
    rows: List[Dict] = []
    with mp.get_context('fork').Pool(max(1, (os.cpu_count() or 2) - 1)) as pool:
        for k, res in enumerate(pool.imap_unordered(coin_rows, range(len(coins)), chunksize=4)):
            rows.extend(res)
    df = pl.DataFrame(rows).sort('ts')
    mid = int(df['ts'].min() + (df['ts'].max() - df['ts'].min()) // 2)
    fmt = lambda ms: datetime.fromtimestamp(ms / 1000, timezone.utc).strftime('%Y-%m-%d')  # noqa: E731
    lines = [f"# Positioning as an entry source ({df['coin'].n_unique()} coins, {len(df)} samples, "
             f"{fmt(df['ts'].min())} .. {fmt(df['ts'].max())})", '',
             "Forward return minus the universe mean, by decile of each feature (pooled over coins); the contrarian "
             "trade = long the bottom decile / short the top one (for oi_3d and px_3d both readings are shown). "
             "[90%] by calendar week. Rules: the docstring of `research_positioning.py`.", '']
    for feat in ('funding', 'funding_z', 'global_z', 'top_pos_z', 'oi_3d', 'px_3d'):
        d = df.filter(pl.col(feat).is_not_null() & pl.col(feat).is_not_nan())
        if len(d) < 1000:
            continue
        lo_q, hi_q = d[feat].quantile(0.1), d[feat].quantile(0.9)
        lines += [f"## {feat} (bottom decile < {lo_q:.4g}, top decile > {hi_q:.4g})", '',
                  '| half | horizon | bottom decile | middle 80% | top decile | spread bottom - top [90%] |',
                  '|---|---|---:|---:|---:|---|']
        for half, cond in (('older', pl.col('ts') < mid), ('newer', pl.col('ts') >= mid)):
            h = d.filter(cond)
            for hz in ('fwd_24h', 'fwd_72h'):
                b = h.filter(pl.col(feat) < lo_q)
                t = h.filter(pl.col(feat) > hi_q)
                mmid = h.filter((pl.col(feat) >= lo_q) & (pl.col(feat) <= hi_q))
                # spread per week: mean(bottom) - mean(top)
                wk_b = (b['ts'].to_numpy() // (7 * 86_400_000)).astype(int)
                wk_t = (t['ts'].to_numpy() // (7 * 86_400_000)).astype(int)
                vals = np.concatenate([b[hz].to_numpy(), -t[hz].to_numpy()])
                wks = np.concatenate([wk_b, wk_t])
                m, lo, hi, _ = rh.week_boot(vals, wks)
                lines.append(f"| {half} | {hz[4:]} | {b[hz].mean() * 100:+.2f}% | {mmid[hz].mean() * 100:+.2f}% | "
                             f"{t[hz].mean() * 100:+.2f}% | {m * 100:+.2f}% [{lo * 100:+.2f}..{hi * 100:+.2f}] |")
        lines.append('')
    text = '\n'.join(lines) + '\n'
    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)


if __name__ == '__main__':
    main()
