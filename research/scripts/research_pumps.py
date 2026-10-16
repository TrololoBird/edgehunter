# ruff: noqa: E741  (O / H / L / C are the candle fields)
"""
Small caps are traded differently: they pump for hours, pull back, then often fall back to where the move started
("they go for the liquidity"). This study measures that on the Binance archive's 1h candles, point in time.

Universe: coins of the live universe's rules (spot pair, >= $10M average daily volume over the 30 days before, >= 100
days listed; delisted included) that are NOT among the 30 most traded that day ("small caps"); the 5 majors (BTC,
ETH, SOL, XRP, BNB) are reported separately for comparison.

Event (pre-registered): a PUMP = the close is >= 15% above the lowest low of the last 6 hours and the hours since that low
traded >= 3x the coin's average hourly volume of the 7 days before; the first hour it holds, then nothing for 48h. The pump's
base = that 6h low (where the move started: the liquidity it left behind), its peak = the highest high until the
exhaustion. DUMPS mirror it (-15%).

What happens next (descriptive, 7 days): the share of pumps that return to 50% / 100% of the move (the base) before
making a new high, and the forward return 6h / 24h / 72h minus the universe mean.

Trades (fixed rules, entry at the next 1h open, 0.20% round trip AND a 0.40% small-cap cost for sensitivity):
- FADE: after the pump, the first 1h close below the previous 1h low within 24h -> short; stop above the peak
  (+ 0.25 ATR1h); TP1 = 50% of the pump, TP2 = the base.
- DIP-BUY: after the pump, price retraces to 38.2-61.8% of it within 24h and a 1h close above the previous 1h high
  -> long; stop below the pullback low (- 0.25 ATR1h); TP1 = the peak, TP2 = the 1.618 extension.
Each trade against the random-walk hit rate of the same entry / stop / target (risk / (risk + reward)); older and
newer half separately; 90% intervals by calendar week.

Run: python research_pumps.py [--months 38] [--limit N]
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import argparse
import multiprocessing as mp
import os
from datetime import datetime, timezone
from typing import Dict, List

import numpy as np

import research_htf as rh

G: Dict = {}
MAJORS = ('BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'BNBUSDT')
PUMP = 0.15
WIN = 6
VOL_X = 3.0
COOLDOWN = 48
HOLD = 168


def atr1h(H, L, C, t, n=14):
    tr = np.maximum(H[t - n:t] - L[t - n:t], np.maximum(np.abs(H[t - n:t] - C[t - n - 1:t - 1]),
                                                       np.abs(L[t - n:t] - C[t - n - 1:t - 1])))
    return float(np.nanmean(tr))


def outcome(H, L, C, e, d, stop, target):
    """1 target first, 0 stop first (stop wins ties), None neither in HOLD; and the exit price."""
    last = min(len(C), e + HOLD)
    for h in range(e, last):
        if np.isnan(H[h]):
            return None, C[h - 1] if h > e else None
        if (L[h] <= stop) if d > 0 else (H[h] >= stop):
            return 0, stop
        if (H[h] >= target) if d > 0 else (L[h] <= target):
            return 1, target
    return None, C[last - 1]


def coin_rows(j: int) -> List[Dict]:
    O, H, L, C, V = (G[k][:, j] for k in ('O', 'H', 'L', 'C', 'V'))
    coin = G['coins'][j]
    cls_major = coin in MAJORS
    t0, elig, rank = G['t0'], G['elig'][:, j], G['rank'][:, j]
    n = len(C)
    out = []
    last_event = -10 ** 9
    for t in range(24 * 110, n - HOLD - 30):
        day = t // 24 - 1
        if not elig[day] or (not cls_major and rank[day] <= 30) or t - last_event < COOLDOWN:
            continue
        if np.isnan(C[t]) or np.isnan(L[t - WIN + 1:t + 1]).any():
            continue
        vol7 = np.nanmean(V[t - 168 - WIN:t - WIN + 1])
        for d in (1, -1):
            seg = slice(t - WIN + 1, t + 1)
            k0 = int(np.argmin(L[seg]) if d > 0 else np.argmax(H[seg])) + t - WIN + 1
            base = L[k0] if d > 0 else H[k0]
            move = C[t] / base - 1 if d > 0 else base / C[t] - 1
            # the move's own hours (from the base candle on) traded >= VOL_X x the average hour of the week before
            if move < PUMP or not vol7 or np.nansum(V[k0:t + 1]) < VOL_X * (t + 1 - k0) * vol7:
                continue
            last_event = t
            a = atr1h(H, L, C, t)
            # the peak until exhaustion: the first close beyond the previous candle's extreme against the move
            peak, ex = (H[t], None)
            for h in range(t + 1, min(n - 1, t + 25)):
                peak = max(peak, H[h]) if d > 0 else min(peak, L[h])
                if (C[h] < L[h - 1]) if d > 0 else (C[h] > H[h - 1]):
                    ex = h
                    break
            size = abs(peak - base)
            row = {'coin': coin, 'major': cls_major, 'dir': d, 'ts': t0 + t * rh.HOUR, 'move': move,
                   'kind': 'pump' if d > 0 else 'dump'}
            # descriptive: back to 50% / to the base before a new extreme, 7 days after the event
            half, back = peak - d * 0.5 * size, base
            reached = {'half': None, 'base': None}
            for key, lvl in (('half', half), ('base', back)):
                for h in range(t + 1, min(n, t + HOLD)):
                    beyond = (H[h] > peak) if d > 0 else (L[h] < peak)
                    hit = (L[h] <= lvl) if d > 0 else (H[h] >= lvl)
                    if hit:
                        reached[key] = 1
                        break
                    if beyond:
                        reached[key] = 0
                        break
            row['back_half'], row['back_base'] = reached['half'], reached['base']
            mkt = G['mkt']
            for hz in (6, 24, 72):
                r = C[t + hz] / C[t] - 1 if not np.isnan(C[t + hz]) else np.nan
                row[f'fwd_{hz}h'] = d * (r - (mkt[t + hz] / mkt[t] - 1))
            trades = []
            if ex is not None and ex + 1 < n and not np.isnan(O[ex + 1]):
                e = ex + 1
                entry = O[e]
                stop = peak + d * 0.25 * a
                trades.append(('FADE', -d, e, entry, stop, [peak - d * 0.5 * size, base]))
            # dip-buy: retrace to 38.2-61.8% of the pump within 24h, then a close beyond the previous candle.
            # Audit 2026-10-16 R05: causal - the peak (and with it the zone and the targets) is only known once the
            # exhaustion candle confirmed it, so the search starts AFTER it (was t + 1: a trade entered before the
            # exhaustion took its targets from a peak set after its entry)
            lo_r, hi_r = peak - d * 0.382 * size, peak - d * 0.618 * size
            touched, pull = False, None
            for h in (range(ex + 1, min(n - 1, t + 25)) if ex is not None else ()):
                if not touched:
                    if (L[h] <= lo_r) if d > 0 else (H[h] >= lo_r):
                        touched, pull = True, L[h] if d > 0 else H[h]
                    continue
                pull = min(pull, L[h]) if d > 0 else max(pull, H[h])
                if (pull < hi_r) if d > 0 else (pull > hi_r):
                    break
                if (C[h] > H[h - 1]) if d > 0 else (C[h] < L[h - 1]):
                    e = h + 1
                    if e < n and not np.isnan(O[e]):
                        trades.append(('DIP-BUY', d, e, O[e], pull - d * 0.25 * a, [peak, base + d * 1.618 * size]))
                    break
            row['trades'] = []
            for name, td, e, entry, stop, targets in trades:
                risk = td * (entry - stop)
                if risk <= 0:
                    continue
                tr = {'strategy': name, 'tdir': td, 'risk_pct': risk / entry}
                for k, tgt in enumerate(targets, 1):
                    reward = td * (tgt - entry)
                    if reward <= 0:
                        tr[f'win{k}'] = None
                        continue
                    win, px = outcome(H, L, C, e, td, stop, tgt)
                    if px is None:
                        break
                    gross = td * (px - entry) / risk
                    tr[f'win{k}'] = win
                    tr[f'geo{k}'] = risk / (risk + reward)
                    tr[f'r{k}'] = gross - 0.002 * entry / risk
                    tr[f'r{k}_hi'] = gross - 0.004 * entry / risk
                row['trades'].append(tr)
            out.append(row)
            break
    return out


def _worker(j):
    try:
        return coin_rows(j)
    except Exception as e:
        return [{'error': f"{G['coins'][j]}: {type(e).__name__} {e}"}]


def fmt(ms) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime('%Y-%m-%d')


def main():
    import polars as pl
    parser = argparse.ArgumentParser()
    parser.add_argument('--months', type=int, default=38)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument('--out', default=os.path.join('research', 'pumps.md'))
    parser.add_argument('--end-month', default='', help="YYYY-MM: the window's last month (a holdout period)")
    args = parser.parse_args()
    t0, coins, O, H, L, C, V, _ = rh.load(args.months, args.limit, args.end_month)
    elig, _, _, _ = rh.market_state(C, V, coins)
    n_days = C.shape[0] // 24
    Vd = np.nansum(V[:n_days * 24].reshape(n_days, 24, -1), axis=1)
    avg30 = np.full_like(Vd, np.nan)
    cs = np.cumsum(Vd, axis=0)
    avg30[31:] = (cs[30:-1] - cs[:-31]) / 30
    rank = np.full(Vd.shape, 10 ** 6)
    for d in range(31, n_days):
        v = np.where(elig[d], avg30[d], -1)
        order = np.argsort(-v)
        rank[d, order] = np.arange(1, len(order) + 1)
    # universe mean price path (equal weight of hourly returns of eligible coins) for the market-relative returns
    r1 = np.vstack([np.full(C.shape[1], np.nan), C[1:] / C[:-1] - 1])
    el_h = np.repeat(elig, 24, axis=0)[:C.shape[0]]
    if el_h.shape[0] < C.shape[0]:
        el_h = np.vstack([el_h, np.zeros((C.shape[0] - el_h.shape[0], C.shape[1]), bool)])
    mret = np.nanmean(np.where(el_h, r1, np.nan), axis=1)
    mkt = np.cumprod(1 + np.nan_to_num(mret))
    G.update(t0=t0, coins=coins, O=O, H=H, L=L, C=C, V=V, elig=elig, rank=rank, mkt=mkt)
    rows: List[Dict] = []
    with mp.get_context('fork').Pool(args.workers) as pool:
        for k, res in enumerate(pool.imap_unordered(_worker, range(len(coins)), chunksize=2)):
            rows.extend(res)
            if k % 50 == 0:
                print(f"  {k}/{len(coins)} coins, {len(rows)} events", flush=True)
    errors = [r['error'] for r in rows if 'error' in r]
    rows = [r for r in rows if 'error' not in r]
    ev = pl.DataFrame([{k: v for k, v in r.items() if k != 'trades'} for r in rows]).sort('ts')
    tr = pl.DataFrame([{**t, 'ts': r['ts'], 'major': r['major'], 'kind': r['kind'], 'coin': r['coin'],
                        'size': '15-30%' if r['move'] < 0.30 else '30-60%' if r['move'] < 0.60 else '60%+'}
                       for r in rows for t in r['trades']], infer_schema_length=None).sort('ts')
    mid = int(ev['ts'].min() + (ev['ts'].max() - ev['ts'].min()) // 2)
    half = pl.when(pl.col('ts') < mid).then(pl.lit('older')).otherwise(pl.lit('newer')).alias('half')
    cls = pl.when(pl.col('major')).then(pl.lit('majors')).otherwise(pl.lit('small caps')).alias('class')
    ev = ev.with_columns(half, cls)
    tr = tr.with_columns(half, cls)
    lines = [f"# Pumps / dumps and what follows ({len(coins)} coins, {fmt(ev['ts'].min())} .. {fmt(ev['ts'].max())})",
             '', "Rules: the docstring of `research_pumps.py` (pre-registered). 'fwd' = the return in the move's "
             "direction minus the universe mean (so negative = reversal).", '',
             '## What follows the event', '',
             '| class | kind | half | events | back to 50% before a new extreme | back to the base | fwd 6h | fwd 24h | '
             'fwd 72h |', '|---|---|---|---:|---:|---:|---:|---:|---:|']
    for key, g in ev.group_by(['class', 'kind', 'half'], maintain_order=True):
        lines.append(f"| {' | '.join(key)} | {len(g)} | {g['back_half'].drop_nulls().mean():.0%} | "
                     f"{g['back_base'].drop_nulls().mean():.0%} | {g['fwd_6h'].mean() * 100:+.2f}% | "
                     f"{g['fwd_24h'].fill_nan(None).mean() * 100:+.2f}% | {g['fwd_72h'].fill_nan(None).mean() * 100:+.2f}% |")
    lines += ['', '## Trades', '', '| class | kind | strategy | half | trades | TP1 hit | geometry | R TP1 net '
              '0.20% [90%] | R TP1 at 0.40% | TP2 hit | geometry TP2 | R TP2 net | median stop |',
              '|---|---|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|']
    for key, g in tr.group_by(['class', 'kind', 'strategy', 'half'], maintain_order=True):
        g1 = g.filter(pl.col('win1').is_not_null())
        if len(g) < 20:
            continue
        wk = (g['ts'].to_numpy() // (7 * 86_400_000)).astype(int)
        r1v = g['r1'].fill_null(np.nan).to_numpy().astype(float)
        ok = ~np.isnan(r1v)
        m, lo, hi, _ = rh.week_boot(r1v[ok], wk[ok])
        g2 = g.filter(pl.col('win2').is_not_null()) if 'win2' in g.columns else g.head(0)
        lines.append(f"| {' | '.join(key)} | {len(g)} | {g1['win1'].mean():.0%} | {g1['geo1'].mean():.0%} | "
                     f"{m:+.3f} [{lo:+.3f}..{hi:+.3f}] | {g['r1_hi'].mean():+.3f} | "
                     f"{g2['win2'].mean() if len(g2) else float('nan'):.0%} | "
                     f"{g2['geo2'].mean() if len(g2) else float('nan'):.0%} | "
                     f"{g['r2'].drop_nulls().mean() if 'r2' in g.columns and g['r2'].drop_nulls().len() else float('nan'):+.3f} | "
                     f"{g['risk_pct'].median() * 100:.1f}% |")
    lines += ['', '## Trades by the size of the move (whole window)', '',
              '| class | kind | strategy | size | trades | TP1 hit | geometry | R TP1 net | R TP2 net |',
              '|---|---|---|---|---:|---:|---:|---:|---:|']
    for key, g in tr.group_by(['class', 'kind', 'strategy', 'size'], maintain_order=True):
        if len(g) < 20:
            continue
        g1 = g.filter(pl.col('win1').is_not_null())
        lines.append(f"| {' | '.join(key)} | {len(g)} | {g1['win1'].mean():.0%} | {g1['geo1'].mean():.0%} | "
                     f"{g['r1'].drop_nulls().mean():+.3f} | "
                     f"{g['r2'].drop_nulls().mean() if 'r2' in g.columns and g['r2'].drop_nulls().len() else float('nan'):+.3f} |")
    if errors:
        lines += ['', f"{len(errors)} coins failed, first: {errors[0]}"]
    text = '\n'.join(lines) + '\n'
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)


if __name__ == '__main__':
    main()
