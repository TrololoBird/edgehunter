"""
Connors' RSI(2) on the crypto daily archive (plan 2.7, eng-55), pre-registered before the run:

Universe: every USDT perpetual of the Binance archive with a spot pair (delisted included), a coin counted from its
200th daily candle. Rule as in "Short Term Trading Strategies That Work" (2008): long when the close is above the
SMA200 and RSI(2) < 10 (variant 5), entry at that close; exit on the first close above the SMA5 (no stop, the book's
rule) - variants: day-10 cap, and our catastrophic 3-ATR stop. Shorts mirrored (below SMA200, RSI(2) > 90 / 95, out
below the SMA5). Cost 0.20% round trip. Funding ignored (a few days held). Results per side, variant and half
(older / newer of the window), the mean return per trade with a 90% interval by calendar month.
Decision rule: a side is kept only if its mean net return is > 0 in BOTH halves (the book's variant, 10 / 90).

Run: python research_connors.py [--months 60]
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import argparse
import os
from datetime import date, timedelta
from typing import Dict, List

import numpy as np

COST = 0.002


def rsi2(c: np.ndarray) -> np.ndarray:
    out = np.full(len(c), np.nan)
    if len(c) < 4:
        return out
    d = np.diff(c)
    g, lo = np.maximum(d, 0), np.maximum(-d, 0)
    ag, al = g[:2].mean(), lo[:2].mean()
    for i in range(2, len(d)):
        ag = (ag + g[i]) / 2
        al = (al + lo[i]) / 2
        out[i + 1] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def trades(o, h, l, c, ts, side: int, low: float, cap: int, stop_atr: float) -> List[Dict]:
    n = len(c)
    out = []
    if n < 210:
        return out
    sma200 = np.convolve(c, np.ones(200) / 200, 'valid')
    sma200 = np.concatenate([np.full(199, np.nan), sma200])
    sma5 = np.concatenate([np.full(4, np.nan), np.convolve(c, np.ones(5) / 5, 'valid')])
    r = rsi2(c)
    tr = np.maximum(h[1:], c[:-1]) - np.minimum(l[1:], c[:-1])
    atr = np.concatenate([[np.nan] * 20, np.convolve(tr, np.ones(20) / 20, 'valid')])
    i = 200
    while i < n - 1:
        ok = (c[i] > sma200[i] and r[i] < low and c[i] < sma5[i]) if side > 0 else \
             (c[i] < sma200[i] and r[i] > 100 - low and c[i] > sma5[i])
        if not ok or np.isnan(r[i]):
            i += 1
            continue
        entry = c[i]
        stop = entry - side * stop_atr * atr[i] if stop_atr and not np.isnan(atr[i]) else None
        exit_px, j = None, i + 1
        while j < n:
            if stop is not None and side * (l[j] if side > 0 else h[j]) <= side * stop:
                exit_px = min(o[j], stop) if side > 0 else max(o[j], stop)
                break
            if side * (c[j] - sma5[j]) > 0:
                exit_px = c[j]
                break
            if cap and j - i >= cap:
                exit_px = c[j]
                break
            j += 1
        if exit_px is None:
            break
        out.append({'ts': int(ts[i]), 'ret': side * (exit_px / entry - 1) - COST, 'days': j - i})
        i = j + 1
    return out


def main():
    from history import Archive
    from pretrain import _spot_pair
    ap = argparse.ArgumentParser()
    ap.add_argument('--months', type=int, default=60)
    ap.add_argument('--out', default=os.path.join('research', 'connors_crypto.md'))
    args = ap.parse_args()
    arch = Archive(rate_bytes=2e7)
    today = date.today()
    end = date(today.year, today.month, 1) - timedelta(days=1)
    first = date(end.year, end.month, 1)
    for _ in range(args.months - 1):
        first = (first - timedelta(days=1)).replace(day=1)
    spot = set(arch.list_symbols('spot'))
    coins = [s for s in arch.list_symbols('futures') if s.endswith('USDT') and '_' not in s and _spot_pair(s[:-4], spot)]
    variants = [('book 10/90, SMA5 exit, no stop', 10, 0, 0.0), ('5/95', 5, 0, 0.0),
                ('10/90 + day-10 cap', 10, 10, 0.0), ('10/90 + 3 ATR stop (ours)', 10, 10, 3.0)]
    res: Dict = {}
    for k, sym in enumerate(coins):
        try:
            kl = arch.klines_ohlc('futures', sym, '1d', first, end)
        except Exception:
            continue
        if len(kl) < 210:
            continue
        ts, o, h, l, c = (kl[:, i] for i in range(5))
        for name, low, cap, st in variants:
            for side in (1, -1):
                res.setdefault((name, side), []).extend(trades(o, h, l, c, ts, side, low, cap, st))
        if k % 50 == 0:
            print(f'{k}/{len(coins)}', flush=True)
    allts = [t['ts'] for v in res.values() for t in v]
    mid = (min(allts) + max(allts)) / 2 if allts else 0
    lines = [f'# Connors RSI(2) on crypto daily ({len(coins)} coins, {first} .. {end})', '',
             'Rules: the docstring of `research_connors.py` (pre-registered). Net of 0.20% round trip.', '',
             '| variant | side | half | trades | mean | 90% (by month) | win | avg days |', '|---|---|---|---:|---:|---|---:|---:|']
    rng = np.random.default_rng(3)
    for (name, side), tl in res.items():
        for half, sel in (('older', [t for t in tl if t['ts'] < mid]), ('newer', [t for t in tl if t['ts'] >= mid]),
                          ('all', tl)):
            if len(sel) < 10:
                continue
            r = np.array([t['ret'] for t in sel])
            mon = np.array([t['ts'] // (30 * 86_400_000) for t in sel])
            u = np.unique(mon)
            idx = {m: np.where(mon == m)[0] for m in u}
            bs = [r[np.concatenate([idx[m] for m in rng.choice(u, len(u))])].mean() for _ in range(2000)]
            lo, hi = np.percentile(bs, [5, 95])
            lines.append(f"| {name} | {'long' if side > 0 else 'short'} | {half} | {len(sel)} | {r.mean():+.2%} | "
                         f"[{lo:+.2%}..{hi:+.2%}] | {(r > 0).mean():.0%} | {np.mean([t['days'] for t in sel]):.1f} |")
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
