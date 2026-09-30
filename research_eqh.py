# ruff: noqa: E741  (O / H / L / C are the candle fields)
"""
The XAU card of 2026-09-22 worked at "EQH 4374 with 11 touches": price ran into the equal highs and turned. Is a
rejection at equal highs / lows with many touches, in the direction of the daily trend, better than geometry?
Pre-registered (fixed before the run), Binance archive 1h candles, point-in-time universe:

- a level = a 1h swing high (fractal, 2 candles each side) of the last 168h not closed above since; its TOUCHES = the
  1h highs of those 168h within 0.1 ATR14(1h) of it (EQL: mirror with lows);
- the event = a 1h candle trading into [level - 0.25 ATR, level + 0.1 ATR] that closes below the level with an upper
  wick >= half its range (a rejection); SHORT at the next open (EQL: LONG, mirror);
- stops: 'tight' = level + 0.5 ATR (just beyond the pool: the liquidity above equal highs), 'wide' = level + 2 ATR;
  target = 1x and 2x the stop distance; held up to 72h; R net of 0.20% round trip;
- context: the daily trend = the last closed daily close vs its EMA20 (with / against the trade); touches 2-3 / 4-6 /
  7+; each trade against the random-walk hit rate of its geometry; older / newer half.

Run: python research_eqh.py [--months 38] [--end-month YYYY-MM]
"""
import argparse
import multiprocessing as mp
import os
from typing import Dict, List

import numpy as np

import research_htf as rh

G: Dict = {}
HOLD = 72


def coin_trades(j: int) -> List[Dict]:
    O, H, L, C = (G[k][:, j] for k in ('O', 'H', 'L', 'C'))
    t0, elig = G['t0'], G['elig'][:, j]
    n = len(C)
    pc = np.concatenate([[np.nan], C[:-1]])
    tr = np.nanmax(np.vstack([H - L, np.abs(H - pc), np.abs(L - pc)]), axis=0)
    atr = np.full(n, np.nan)
    w = np.lib.stride_tricks.sliding_window_view(tr, 14)
    atr[14:] = w[:-1].mean(axis=1)                     # ATR of the 14 hours BEFORE t
    nd = n // 24
    cd = C[:nd * 24].reshape(nd, 24)[:, -1]
    ema = np.full(nd, np.nan)
    a = 2 / 21
    for i in range(nd):
        if np.isnan(cd[i]):
            continue
        ema[i] = cd[i] if i == 0 or np.isnan(ema[i - 1]) else ema[i - 1] + a * (cd[i] - ema[i - 1])
    out = []
    busy = -1
    for t in range(24 * 60, n - HOLD - 1):
        if t <= busy or np.isnan(atr[t]) or np.isnan(C[t]):
            continue
        day = t // 24 - 1
        if not elig[day] or np.isnan(ema[day]):
            continue
        at = atr[t]
        lo_w = t - 168
        for d in (-1, 1):                               # -1: short at EQH, +1: long at EQL
            seg = H[lo_w:t] if d < 0 else L[lo_w:t]
            if np.isnan(seg).any():
                continue
            # swing extremes (2 each side) of the window, not closed beyond since
            s = seg if d < 0 else -seg                  # lows mirrored: a swing low is a swing high of -low
            cand = [i for i in range(2, len(s) - 2)
                    if s[i] > s[i - 1] and s[i] > s[i - 2] and s[i] >= s[i + 1] and s[i] >= s[i + 2]]
            s = seg
            if not cand:
                continue
            closes_after = C[lo_w:t]
            best = None
            for i in cand:
                lvl = s[i]
                after = closes_after[i + 1:]
                if (d < 0 and (after > lvl).any()) or (d > 0 and (after < lvl).any()):
                    continue
                touches = int((np.abs(s - lvl) <= 0.1 * at).sum())
                if touches >= 2 and (best is None or touches > best[1]):
                    best = (lvl, touches)
            if best is None:
                continue
            lvl, touches = best
            rng = H[t] - L[t]
            if rng <= 0:
                continue
            if d < 0:
                hit = H[t] >= lvl - 0.25 * at and H[t] <= lvl + 0.1 * at and C[t] < lvl and \
                    (H[t] - max(O[t], C[t])) >= 0.5 * rng
            else:
                hit = L[t] <= lvl + 0.25 * at and L[t] >= lvl - 0.1 * at and C[t] > lvl and \
                    (min(O[t], C[t]) - L[t]) >= 0.5 * rng
            if not hit or np.isnan(O[t + 1]):
                continue
            entry = O[t + 1]
            trend_with = (cd[day] < ema[day]) if d < 0 else (cd[day] > ema[day])
            row = {'coin': G['coins'][j], 'ts': t0 + (t + 1) * rh.HOUR, 'dir': d, 'touches': touches,
                   'trend': 'with' if trend_with else 'against', 'major': G['coins'][j] in G['majors']}
            hh, ll = H[t + 1:t + 1 + HOLD], L[t + 1:t + 1 + HOLD]
            last = C[t + HOLD]
            for sname, sk in (('tight', 0.5), ('wide', 2.0)):
                stop = lvl - d * sk * at
                risk = d * (entry - stop)
                if risk <= 0:
                    row[f'{sname}_ok'] = False
                    continue
                row[f'{sname}_ok'] = True
                adv = (hh - entry) if d < 0 else (entry - ll)
                for m in (1, 2):
                    tgt = m * risk
                    fav = (entry - ll) if d < 0 else (hh - entry)
                    i_s = int(np.argmax(adv >= risk)) if (adv >= risk).any() else 10 ** 9
                    i_t = int(np.argmax(fav >= tgt)) if (fav >= tgt).any() else 10 ** 9
                    if i_s == i_t == 10 ** 9:
                        gross, win = d * (last - entry), None
                    elif i_s <= i_t:
                        gross, win = -risk, 0
                    else:
                        gross, win = tgt, 1
                    row[f'{sname}_{m}_r'] = (gross - 0.002 * entry) / risk
                    row[f'{sname}_{m}_win'] = win
                    row[f'{sname}_{m}_geo'] = 1 / (1 + m)
            out.append(row)
            busy = t + 6
            break
    return out


def _worker(j):
    try:
        return coin_trades(j)
    except Exception as e:
        return [{'error': f"{G['coins'][j]}: {type(e).__name__} {e}"}]


def main():
    import polars as pl
    parser = argparse.ArgumentParser()
    parser.add_argument('--months', type=int, default=38)
    parser.add_argument('--end-month', default='')
    parser.add_argument('--out', default=os.path.join('research', 'eqh.md'))
    args = parser.parse_args()
    t0, coins, O, H, L, C, V, _ = rh.load(args.months, 0, args.end_month)
    elig, _, _, _ = rh.market_state(C, V, coins)
    G.update(t0=t0, coins=coins, O=O, H=H, L=L, C=C, elig=elig,
             majors={'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'BNBUSDT'})
    rows: List[Dict] = []
    with mp.get_context('fork').Pool(max(1, (os.cpu_count() or 2) - 1)) as pool:
        for res in pool.imap_unordered(_worker, range(len(coins)), chunksize=2):
            rows.extend(res)
    errors = [r for r in rows if 'error' in r]
    df = pl.DataFrame([r for r in rows if 'error' not in r], infer_schema_length=None).sort('ts')
    mid = int(df['ts'].min() + (df['ts'].max() - df['ts'].min()) // 2)
    df = df.with_columns(
        pl.when(pl.col('ts') < mid).then(pl.lit('older')).otherwise(pl.lit('newer')).alias('half'),
        pl.when(pl.col('dir') < 0).then(pl.lit('short EQH')).otherwise(pl.lit('long EQL')).alias('side'),
        pl.when(pl.col('touches') <= 3).then(pl.lit('2-3')).when(pl.col('touches') <= 6).then(pl.lit('4-6'))
        .otherwise(pl.lit('7+')).alias('touch'))
    fmt = lambda ms: __import__('datetime').datetime.fromtimestamp(ms / 1000, __import__('datetime').timezone.utc).strftime('%Y-%m-%d')  # noqa: E731,E501
    lines = [f"# Rejections at equal highs / lows ({df['coin'].n_unique()} coins, {fmt(df['ts'].min())} .. "
             f"{fmt(df['ts'].max())}, {len(df)} events)", '',
             "Rules: the docstring of `research_eqh.py` (pre-registered). hit = target before stop within 72h; "
             "geometry = the random-walk rate of the same stop / target (1/(1+m)); R net of 0.20%. [90%] by week.", '']
    for stop in ('tight', 'wide'):
        for m in (1, 2):
            key = f'{stop}_{m}'
            lines += [f"## stop {stop}, target {m}x the stop", '',
                      '| side | daily trend | touches | half | trades | hit | geometry | R net [90%] |',
                      '|---|---|---|---|---:|---:|---:|---|']
            d = df.filter(pl.col(f'{stop}_ok'))
            for k, g in d.group_by(['side', 'trend', 'touch', 'half'], maintain_order=True):
                if len(g) < 40:
                    continue
                w = g.filter(pl.col(f'{key}_win').is_not_null())
                wk = (g['ts'].to_numpy() // (7 * 86_400_000)).astype(int)
                rv = g[f'{key}_r'].fill_null(np.nan).to_numpy().astype(float)
                ok = ~np.isnan(rv)                      # a coin delisted / data ending inside the hold: no exit price
                mm, lo, hi, _ = rh.week_boot(rv[ok], wk[ok])
                lines.append(f"| {' | '.join(k)} | {len(g)} | {w[f'{key}_win'].mean():.0%} | {1 / (1 + m):.0%} | "
                             f"{mm:+.3f} [{lo:+.3f}..{hi:+.3f}] |")
            lines.append('')
    if errors:
        lines.append(f"{len(errors)} coins failed, first: {errors[0]['error']}")
    text = '\n'.join(lines) + '\n'
    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)


if __name__ == '__main__':
    main()
