# ruff: noqa: E741  (O / H / L / C are the candle fields)
"""
Should the stop / target be tuned per coin (or per volatility class) instead of one set for all coins, and is ATR a
sensible unit at all? Walk-forward on the archive's 1h candles, with the entries of the scenario-card triggers
(research_level_triggers.py events: coin, hour, direction), so the entry is fixed and only the exit geometry varies.

Geometry grid: the stop at k x ATR14(1h) (k in 1, 1.5, 2, 3, 4) or at a fixed percentage (1, 2, 4, 8%), the target at
m x the stop (m in 1, 1.5, 2, 3); held up to 7 days; R net of 0.20% round trip.

Each month, choose from the PREVIOUS 6 months only (>= 20 trades for a per-coin choice, else the global one):
- 'fixed': the one geometry best over all coins; - 'per coin': the best for that coin;
- 'per volatility class': the best for the coin's ATR%-tercile of that month; - 'random': a random geometry.
Then trade the month with it. The question is whether per-coin / per-class tuning beats one global geometry out of
sample (it overfits when it does not).

Run: python research_adaptive.py [--events lt_events.parquet] [--sample 200000]
"""
import argparse
import multiprocessing as mp
import os
from typing import Dict, List

import numpy as np

import research_htf as rh

G: Dict = {}
HOLD = 168
K_ATR = (1.0, 1.5, 2.0, 3.0, 4.0)
K_PCT = (0.01, 0.02, 0.04, 0.08)
M_TGT = (1.0, 1.5, 2.0, 3.0)
GEOMS = [('atr', k, m) for k in K_ATR for m in M_TGT] + [('pct', k, m) for k in K_PCT for m in M_TGT]


def coin_rows(args) -> List[tuple]:
    j, evs = args
    H, L, C, O = G['H'][:, j], G['L'][:, j], G['C'][:, j], G['O'][:, j]
    out = []
    for e, d in evs:
        if e < 20 or e + 2 >= len(C) or np.isnan(O[e]):
            continue
        tr = np.maximum(H[e - 14:e] - L[e - 14:e], np.maximum(np.abs(H[e - 14:e] - C[e - 15:e - 1]),
                                                             np.abs(L[e - 14:e] - C[e - 15:e - 1])))
        atr = np.nanmean(tr)
        entry = O[e]
        if not atr or np.isnan(atr):
            continue
        seg_h, seg_l = H[e:e + HOLD], L[e:e + HOLD]
        ok = ~np.isnan(seg_h)
        if not ok.all():
            n = int(np.argmin(ok))
            if n == 0:
                continue
            seg_h, seg_l = seg_h[:n], seg_l[:n]
        last = C[e + len(seg_h) - 1]
        fav = (seg_h - entry) if d > 0 else (entry - seg_l)
        adv = (entry - seg_l) if d > 0 else (seg_h - entry)
        rs = []
        for kind, k, m in GEOMS:
            risk = k * atr if kind == 'atr' else k * entry
            tgt = m * risk
            hit_s = np.argmax(adv >= risk) if (adv >= risk).any() else 10 ** 9
            hit_t = np.argmax(fav >= tgt) if (fav >= tgt).any() else 10 ** 9
            if hit_s == 10 ** 9 and hit_t == 10 ** 9:
                gross = d * (last - entry)
            elif hit_s <= hit_t:
                gross = -risk
            else:
                gross = tgt
            rs.append((gross - 0.002 * entry) / risk)
        out.append((G['coins'][j], int(G['t0'] + e * rh.HOUR), atr / entry, rs))
    return out


def main():
    import polars as pl
    parser = argparse.ArgumentParser()
    parser.add_argument('--events', default='/tmp/claude-0/cards/lt_events.parquet')
    parser.add_argument('--sample', type=int, default=200000)
    parser.add_argument('--out', default=os.path.join('research', 'adaptive_params.md'))
    args = parser.parse_args()
    ev = pl.read_parquet(args.events).select(['coin', 'ts', 'dir'])
    if len(ev) > args.sample:
        ev = ev.sample(args.sample, seed=3)
    t0, coins, O, H, L, C, V, _ = rh.load(38, 0)
    G.update(t0=t0, coins=coins, O=O, H=H, L=L, C=C)
    idx = {c: j for j, c in enumerate(coins)}
    jobs: Dict[int, list] = {}
    for c, ts, d in ev.iter_rows():
        if c in idx:
            jobs.setdefault(idx[c], []).append((int((ts - t0) // rh.HOUR), int(d)))
    rows = []
    with mp.get_context('fork').Pool(max(1, (os.cpu_count() or 2) - 1)) as pool:
        for res in pool.imap_unordered(coin_rows, jobs.items(), chunksize=4):
            rows.extend(res)
    coin_arr = np.array([r[0] for r in rows])
    ts_arr = np.array([r[1] for r in rows])
    vol = np.array([r[2] for r in rows])
    R = np.array([r[3] for r in rows])                    # [trade x geometry]
    month = (ts_arr // (30 * 86_400_000)).astype(int)
    months = sorted(set(month))
    rng = np.random.default_rng(7)
    res = {'fixed': [], 'per coin': [], 'per volatility class': [], 'random': [], 'oracle (look-ahead, bound)': []}
    for m in months:
        past = (month >= m - 6) & (month < m)
        cur = month == m
        if past.sum() < 2000 or not cur.any():
            continue
        g_best = int(np.argmax(R[past].mean(axis=0)))
        qs = np.quantile(vol[past], [1 / 3, 2 / 3])
        cls_past = np.digitize(vol[past], qs)
        cls_best = {c: int(np.argmax(R[past][cls_past == c].mean(axis=0))) for c in range(3)}
        cur_idx = np.flatnonzero(cur)
        coin_best = {}
        for c in set(coin_arr[cur_idx]):
            mask = past & (coin_arr == c)
            coin_best[c] = int(np.argmax(R[mask].mean(axis=0))) if mask.sum() >= 20 else g_best
        cls_cur = np.digitize(vol[cur_idx], qs)
        oracle = int(np.argmax(R[cur].mean(axis=0)))
        for i, cl in zip(cur_idx, cls_cur):
            res['fixed'].append(R[i, g_best])
            res['per coin'].append(R[i, coin_best[coin_arr[i]]])
            res['per volatility class'].append(R[i, cls_best[cl]])
            res['random'].append(R[i, rng.integers(len(GEOMS))])
            res['oracle (look-ahead, bound)'].append(R[i, oracle])
    lines = ['# Per-coin / per-volatility tuning of the exit geometry, walk-forward', '',
             f"{len(R)} trades (the scenario-card triggers' entries), {len(GEOMS)} geometries (stop in ATR14(1h) or "
             "in fixed %, target 1-3x the stop). Each month the choice is made on the 6 months before. Rules: the "
             "docstring of `research_adaptive.py`.", '',
             '| choice | trades | mean net R |', '|---|---:|---:|']
    for k, v in res.items():
        lines.append(f"| {k} | {len(v)} | {np.mean(v):+.3f} |")
    lines += ['', '## Every geometry over the whole window (no choice)', '', '| stop | target | mean net R |',
              '|---|---|---:|']
    for gi, (kind, k, m) in enumerate(GEOMS):
        stop = f"{k:g} ATR" if kind == 'atr' else f"{k * 100:g}%"
        lines.append(f"| {stop} | {m:g}x | {R[:, gi].mean():+.3f} |")
    text = '\n'.join(lines) + '\n'
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)


if __name__ == '__main__':
    main()
