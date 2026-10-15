# ruff: noqa: E741  (O / H / L / C are the candle fields)
"""
Do the scenario card's TRIGGERS carry information beyond the geometry of the levels? The card's ladder
(`scenarios.build`
with the higher-timeframe range: daily swings, previous week / month, the 30-day range and its volume profile) is
rebuilt every 8h per coin on the Binance archive's 1h candles, and the next 48 hours are scanned for the four
triggers the cards describe (levels fixed at the rebuild):

- LONG breakout-retest ("пробой и ретест, закрепление"): a 1h close above the reaction zone, then within 24h a candle
  that dips to its top (<= top + 0.2 ATR) and closes above it -> entry at the next open; stop below the first
  support (- 0.25 ATR); targets the resistances above. Skipped if the first resistance is hit before the retest.
- SHORT breakdown-retest: the mirror below the reaction zone (stop above the first resistance).
- SHORT rejection ("отказ / реакция в зоне"): a candle trades into the first resistance and closes back below it with
  an upper wick >= half its range -> entry at the next open; stop above the second resistance (+ 0.25 ATR); targets
  the reaction zone's bottom and the supports.
- LONG rejection (bounce at the first support): the mirror.

Outcome: TP1 before the stop within 7 days (the stop first when both fall in one candle); R net of 0.20% round trip;
the same for TP2. The geometry of each trade gives what a driftless random walk would do: p_geo = risk / (risk +
reward). A trigger carries information only if its hit rate beats p_geo (excess = hit - p_geo, 90% interval by
calendar week). Split by the weekly trend (EMA20 of weekly closes, with / against the trade) and by the place in
the 30-day range; the older and the newer half separately.

Run: python research_level_triggers.py [--months 38] [--limit N] [--step 8]
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import argparse
import multiprocessing as mp
import os
from datetime import datetime, timezone
from typing import Dict, List

import numpy as np

import research_htf as rh
from scenarios import build

G: Dict = {}
SCAN = 48
RETEST = 24
HOLD = 168


def _outcome(H, L, C, e, d, entry, stop, target):
    """(win 1/0, exit price) of target vs stop from the open of hour e over HOLD hours."""
    last = min(len(C), e + HOLD)
    for h in range(e, last):
        if np.isnan(H[h]):
            return None
        hit_s = L[h] <= stop if d > 0 else H[h] >= stop
        hit_t = H[h] >= target if d > 0 else L[h] <= target
        if hit_s:
            return 0, stop
        if hit_t:
            return 1, target
    return (None, C[last - 1]) if last > e else None


def coin_events(j: int) -> List[Dict]:
    O, H, L, C, V = (G[k][:, j] for k in ('O', 'H', 'L', 'C', 'V'))
    t0, step, elig = G['t0'], G['step'], G['elig'][:, j]
    n = len(C)
    out: List[Dict] = []
    seen = set()
    n_days = n // 24
    daily = []
    for d in range(n_days):
        sl = slice(24 * d, 24 * d + 24)
        if np.isnan(C[sl]).any():
            daily.append(None)
        else:
            daily.append([t0 + d * 86_400_000, O[24 * d], np.max(H[sl]), np.min(L[sl]), C[24 * d + 23],
                          float(np.sum(V[sl]))])
    start = 24 * 200
    for t in range(start, n - SCAN - HOLD, step):
        day = t // 24 - 1
        if day < 0 or not elig[day] or np.isnan(C[t - 720:t]).any():
            continue
        days = [x for x in daily[max(0, t // 24 - 200):t // 24] if x is not None]
        if len(days) < 60:
            continue
        idx = range(t - 720, t)
        c30 = [[t0 + i * rh.HOUR, O[i], H[i], L[i], C[i], V[i]] for i in idx]
        sc = build(c30[-200:], float(C[t - 1]), t0 + t * rh.HOUR, model=False, candles_1d=days, candles_1h_30d=c30)
        if sc is None:
            continue
        atr, react, above, below = sc['atr_1h'], sc['reaction'], sc['above'], sc['below']
        ctx = sc['htf']
        plans = []
        # breakout / breakdown and retest
        for d, edge, far_edge, stop, targets, typ in (
                (1, react['hi'], above[0]['lo'], below[0]['lo'] - 0.25 * atr, [z['lo'] for z in above],
                 'LONG breakout-retest'),
                (-1, react['lo'], below[0]['hi'], above[0]['hi'] + 0.25 * atr, [z['hi'] for z in below],
                 'SHORT breakdown-retest')):
            broke = None
            for h in range(t, t + SCAN):
                if broke is None:
                    if d * (C[h] - edge) > 0:
                        broke = h
                    continue
                if h - broke > RETEST or (H[h] >= far_edge if d > 0 else L[h] <= far_edge):
                    break
                touched = L[h] <= edge + 0.2 * atr if d > 0 else H[h] >= edge - 0.2 * atr
                if touched and d * (C[h] - edge) > 0:
                    plans.append((typ, d, h + 1, stop, targets))
                    break
        # rejection at the first resistance / support
        r0, s0 = above[0], below[0]
        for h in range(t, t + SCAN):
            rng = H[h] - L[h]
            if rng <= 0:
                continue
            if H[h] >= r0['lo'] and C[h] < r0['lo'] and (H[h] - max(O[h], C[h])) >= 0.5 * rng:
                stop = (above[1]['hi'] if len(above) > 1 else r0['hi'] + atr) + 0.25 * atr
                plans.append(('SHORT rejection', -1, h + 1, stop, [react['lo']] + [z['hi'] for z in below]))
                break
        for h in range(t, t + SCAN):
            rng = H[h] - L[h]
            if rng <= 0:
                continue
            if L[h] <= s0['hi'] and C[h] > s0['hi'] and (min(O[h], C[h]) - L[h]) >= 0.5 * rng:
                stop = (below[1]['lo'] if len(below) > 1 else s0['lo'] - atr) - 0.25 * atr
                plans.append(('LONG rejection', 1, h + 1, stop, [react['hi']] + [z['lo'] for z in above]))
                break
        for typ, d, e, stop, targets in plans:
            if (typ, e) in seen or e >= n or np.isnan(O[e]):
                continue
            seen.add((typ, e))
            entry = O[e]
            targets = [x for x in targets if d * (x - entry) > 0]
            risk = d * (entry - stop)
            if risk <= 0 or not targets:
                continue
            row = {'coin': G['coins'][j], 'type': typ, 'dir': d, 'ts': t0 + e * rh.HOUR, 'risk_pct': risk / entry,
                   'trend_w': ctx.get('trend_w', 0.0), 'range_pos': ctx.get('range_pos_30d', 0.5)}
            ok = True
            for k, tgt in ((1, targets[0]), (2, targets[1] if len(targets) > 1 else None)):
                if tgt is None:
                    row[f'win{k}'], row[f'r{k}'], row[f'p_geo{k}'] = None, None, None
                    continue
                res = _outcome(H, L, C, e, d, entry, stop, tgt)
                if res is None:
                    ok = False
                    break
                win, px = res
                reward = d * (tgt - entry)
                row[f'win{k}'] = win
                row[f'r{k}'] = (d * (px - entry) - rh.COST * entry) / risk
                row[f'p_geo{k}'] = risk / (risk + reward)
            if ok:
                out.append(row)
    return out


def _worker(j):
    try:
        return coin_events(j)
    except Exception as e:
        return [{'error': f"{G['coins'][j]}: {type(e).__name__} {e}"}]


def fmt(ms) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime('%Y-%m-%d')


def table(df, keys, title):
    import polars as pl
    lines = [f"### {title}", '',
             '| ' + ' | '.join(keys) + ' | trades | TP1 hit | geometry | excess [90%] | R TP1 net [90%] | TP2 hit | '
             'geometry TP2 | R TP2 net | median stop |',
             '|' + '---|' * len(keys) + '---:|---:|---:|---|---|---:|---:|---:|---:|']
    for key, g in df.group_by(keys, maintain_order=True):
        g1 = g.filter(pl.col('win1').is_not_null())
        if len(g1) < 30:
            continue
        wk = (g1['ts'].to_numpy() // (7 * 86_400_000)).astype(int)
        ex, elo, ehi, _ = rh.week_boot((g1['win1'] - g1['p_geo1']).to_numpy().astype(float), wk)
        wk_all = (g['ts'].to_numpy() // (7 * 86_400_000)).astype(int)
        r, rlo, rhi, _ = rh.week_boot(g['r1'].to_numpy().astype(float), wk_all)
        g2 = g.filter(pl.col('win2').is_not_null())
        key = key if isinstance(key, tuple) else (key,)
        lines.append('| ' + ' | '.join(str(k) for k in key) +
                     f" | {len(g)} | {g1['win1'].mean():.1%} | {g1['p_geo1'].mean():.1%} | "
                     f"{ex * 100:+.1f} pp [{elo * 100:+.1f}..{ehi * 100:+.1f}] | {r:+.3f} [{rlo:+.3f}..{rhi:+.3f}] | "
                     f"{g2['win2'].mean() if len(g2) else float('nan'):.1%} | "
                     f"{g2['p_geo2'].mean() if len(g2) else float('nan'):.1%} | "
                     f"{g['r2'].drop_nulls().mean() if g['r2'].drop_nulls().len() else float('nan'):+.3f} | "
                     f"{g['risk_pct'].median() * 100:.1f}% |")
    return lines + ['']


def main():
    import polars as pl
    parser = argparse.ArgumentParser()
    parser.add_argument('--months', type=int, default=38)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--step', type=int, default=8)
    parser.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument('--out', default=os.path.join('research', 'level_triggers.md'))
    parser.add_argument('--events', default='')
    args = parser.parse_args()
    t0, coins, O, H, L, C, V, _ = rh.load(args.months, args.limit)
    elig, _, _, _ = rh.market_state(C, V, coins)
    G.update(t0=t0, coins=coins, O=O, H=H, L=L, C=C, V=V, elig=elig, step=args.step)
    print(f"{len(coins)} coins, {C.shape[0]} hours", flush=True)
    rows: List[Dict] = []
    with mp.get_context('fork').Pool(args.workers) as pool:
        for k, res in enumerate(pool.imap_unordered(_worker, range(len(coins)), chunksize=2)):
            rows.extend(res)
            if k % 25 == 0:
                print(f"  {k}/{len(coins)} coins, {len(rows)} events", flush=True)
    errors = [r['error'] for r in rows if 'error' in r]
    df = pl.DataFrame([r for r in rows if 'error' not in r], infer_schema_length=None).sort('ts')
    if args.events:
        df.write_parquet(args.events)
    mid = int(df['ts'].min() + (df['ts'].max() - df['ts'].min()) // 2)
    df = df.with_columns(
        pl.when(pl.col('ts') < mid).then(pl.lit('older')).otherwise(pl.lit('newer')).alias('half'),
        pl.when(pl.col('trend_w') * pl.col('dir') > 0).then(pl.lit('with')).otherwise(pl.lit('against'))
        .alias('weekly trend'),
        pl.when(pl.col('range_pos') < 1 / 3).then(pl.lit('lower third'))
        .when(pl.col('range_pos') > 2 / 3).then(pl.lit('upper third')).otherwise(pl.lit('middle')).alias('30d range'))
    lines = [f"# Scenario-card triggers vs the geometry of their levels ({len(coins)} coins, "
             f"{fmt(df['ts'].min())} .. {fmt(df['ts'].max())}, {len(df)} trades)", '',
             "Rules: the docstring of `research_level_triggers.py`. 'geometry' = the hit rate a driftless random "
             "walk gives the same entry / stop / target (risk / (risk + reward)); 'excess' = hit rate minus it (a "
             "trigger with information is > 0); R net of 0.20% round trip. [90%] = bootstrap by calendar week.", '']
    lines += table(df, ['type', 'half'], 'By trigger, older / newer half')
    lines += table(df, ['type', 'weekly trend'], 'By the weekly trend (with / against the trade)')
    lines += table(df, ['type', '30d range'], 'By the place in the 30-day range')
    lines += table(df, ['type', 'weekly trend', '30d range'], 'Weekly trend x place in the range')
    if errors:
        lines += [f"{len(errors)} coins failed, first: {errors[0]}", '']
    text = '\n'.join(lines) + '\n'
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)


if __name__ == '__main__':
    main()
