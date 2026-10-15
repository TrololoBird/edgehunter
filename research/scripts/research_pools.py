"""
Which coins suit which method (eng-59, the pool audit), pre-registered before the run.

The two strategies whose live rules replay exactly on the archive's DAILY candles: the Turtles (research_turtle.trades,
R in first-unit risk) and Connors' RSI(2) as traded since eng-58 (5 / 95, out on the first close beyond the SMA5, the
3-ATR catastrophic stop, no day cap; research_connors.trades, net return per trade). The other strategies need the live
lifecycle on 1m data (B9) - not here.

Each trade carries its coin's state on the day BEFORE the entry (no look-ahead):
- vol_rank: the coin's rank by its 30-day mean daily quote volume among ALL archive perpetuals that day (1 = most liquid);
- atr_pct: 20-day ATR / close;
- chop: Dreiss' Choppiness Index (14 days): > 61.8 a range, < 38.2 a trend (his levels);
- er: Kaufman's efficiency ratio over 20 days;
- beta / corr: vs BTC over the 60 days before (daily returns).

Rule (fixed here, before any number is seen): terciles of each attribute are cut on the OLDER half of the window; an
attribute is a pool rule for a strategy only if the best tercile beats the worst by the same sign in BOTH halves and
the newer half's difference has a 90% month-cluster bootstrap interval above 0, with Benjamini-Hochberg q <= 0.10 over
all strategy x attribute tests of the newer half. Everything else stays 'all'.

Run: .venv\\Scripts\\python research_pools.py [--months 48] [--coins 250] [--out research/pools.md]
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import argparse
import os
from datetime import date, timedelta
from typing import Dict, List

import numpy as np

from research_connors import trades as connors_trades
from research_turtle import trades as turtle_trades

ATTRS = ('vol_rank', 'atr_pct', 'chop', 'er', 'beta', 'corr')
DAY_MS = 86_400_000


def features(kl: np.ndarray, btc: Dict[int, float]) -> Dict[int, Dict[str, float]]:
    """Per day index i: the attributes measured on days < i (the state the morning of day i)."""
    ts, h, l, c = kl[:, 0], kl[:, 2], kl[:, 3], kl[:, 4]
    out = {}
    tr = np.maximum(h[1:], c[:-1]) - np.minimum(l[1:], c[:-1])
    ret = np.diff(np.log(c))
    for i in range(61, len(kl)):
        f = {'atr_pct': float(tr[i - 21:i - 1].mean() / c[i - 1])}
        span = h[i - 14:i].max() - l[i - 14:i].min()
        f['chop'] = float(100 * np.log10(tr[i - 15:i - 1].sum() / span) / np.log10(14)) if span > 0 else np.nan
        path = np.abs(np.diff(c[i - 21:i])).sum()
        f['er'] = float(abs(c[i - 1] - c[i - 21]) / path) if path > 0 else np.nan
        b = [btc.get(int(t)) for t in ts[i - 60:i]]
        pairs = [(ret[k - 1], b[j]) for j, k in enumerate(range(i - 60, i)) if b[j] is not None and k >= 1]
        if len(pairs) >= 40:
            x, y = np.array([p[1] for p in pairs]), np.array([p[0] for p in pairs])
            v = x.var()
            f['beta'] = float(np.cov(x, y)[0, 1] / v) if v > 0 else np.nan
            f['corr'] = float(np.corrcoef(x, y)[0, 1]) if v > 0 and y.var() > 0 else np.nan
        out[i] = f
    return out


def boot_diff(a: List[tuple], b: List[tuple], rng, draws: int = 2000):
    """90% interval of mean(a) - mean(b), resampling calendar months of both sides together; p of diff <= 0."""
    months = sorted({m for _, m in a} | {m for _, m in b})
    if len(months) < 6:
        return None
    ga = {m: [v for v, mm in a if mm == m] for m in months}
    gb = {m: [v for v, mm in b if mm == m] for m in months}
    diffs = []
    for _ in range(draws):
        pick = rng.choice(len(months), len(months))
        xa = [v for k in pick for v in ga[months[k]]]
        xb = [v for k in pick for v in gb[months[k]]]
        if xa and xb:
            diffs.append(np.mean(xa) - np.mean(xb))
    if not diffs:
        return None
    lo, hi = np.percentile(diffs, [5, 95])
    return lo, hi, (sum(d <= 0 for d in diffs) + 1) / (len(diffs) + 1)


def main():
    from history import Archive
    from pretrain import _spot_pair
    ap = argparse.ArgumentParser()
    ap.add_argument('--months', type=int, default=48)
    ap.add_argument('--coins', type=int, default=250)
    ap.add_argument('--rate', type=float, default=2e6)
    ap.add_argument('--out', default=os.path.join('research', 'pools.md'))
    args = ap.parse_args()
    arch = Archive(rate_bytes=args.rate)
    today = date.today()
    end = date(today.year, today.month, 1) - timedelta(days=1)
    first = date(end.year, end.month, 1)
    for _ in range(args.months - 1):
        first = (first - timedelta(days=1)).replace(day=1)
    spot = set(arch.list_symbols('spot'))
    coins = [s for s in arch.list_symbols('futures') if s.endswith('USDT') and '_' not in s
             and 'SETTLED' not in s and _spot_pair(s[:-4], spot)]
    data: Dict[str, np.ndarray] = {}
    for k, sym in enumerate(coins):
        try:
            kl = arch.klines_ohlc('futures', sym, '1d', first, end)
        except Exception:
            continue
        if len(kl) >= 120:
            data[sym] = kl
        if k % 50 == 0:
            print(f'loaded {k}/{len(coins)}', flush=True)
    # the 30-day mean volume of every coin on every day -> the cross-sectional rank (all coins, delisted included)
    vol30: Dict[int, Dict[str, float]] = {}
    for sym, kl in data.items():
        qv = np.convolve(kl[:, 5], np.ones(30) / 30, 'valid')
        for j, v in enumerate(qv):
            vol30.setdefault(int(kl[j + 30, 0]) if j + 30 < len(kl) else -1, {})[sym] = float(v)
    rank: Dict[int, Dict[str, int]] = {t: {s: r for r, (s, _) in enumerate(sorted(m.items(), key=lambda kv: -kv[1]), 1)}
                                       for t, m in vol30.items() if t > 0}
    liquid = sorted(data, key=lambda s: -float(data[s][-90:, 5].mean()))[:args.coins]
    btc_kl = data.get('BTCUSDT')
    btc = {}
    if btc_kl is not None:
        btc = {int(t): float(r) for t, r in zip(btc_kl[1:, 0], np.diff(np.log(btc_kl[:, 4])))}
    rows: List[Dict] = []
    for sym in liquid:
        kl = data[sym]
        feats = features(kl, btc)
        idx = {int(t): i for i, t in enumerate(kl[:, 0])}
        d1 = [list(map(float, r)) for r in kl]
        for t in turtle_trades(d1):
            i = idx.get(int(t[0]))
            if i in feats:
                rows.append({'strategy': 'breakout (Turtles)', 'ts': int(t[0]), 'y': t[3], 'sym': sym,
                             'vol_rank': rank.get(int(t[0]), {}).get(sym), **feats[i]})
        ts, o, h, l, c = (kl[:, k] for k in range(5))
        for side in (1, -1):
            for t in connors_trades(o, h, l, c, ts, side, 5, 0, 3.0):
                i = idx.get(t['ts'])
                if i in feats:
                    rows.append({'strategy': f"connors {'long' if side > 0 else 'short'}", 'ts': t['ts'],
                                 'y': t['ret'] * 100, 'sym': sym, 'vol_rank': rank.get(t['ts'], {}).get(sym),
                                 **feats[i]})
    if not rows:
        print('no trades')
        return
    mid = (min(r['ts'] for r in rows) + max(r['ts'] for r in rows)) / 2
    rng = np.random.default_rng(5)
    tests = []
    lines = [f"# Coin attributes vs method ({len(liquid)} coins, {first} .. {end})", '',
             'Rules: the docstring of `research_pools.py` (pre-registered). Turtles in R, Connors in % net per trade.',
             'Terciles cut on the older half; T1 = lowest attribute values.', '',
             '| strategy | attribute | cuts | half | T1 | T2 | T3 | n |', '|---|---|---|---|---:|---:|---:|---:|']
    for strategy in sorted({r['strategy'] for r in rows}):
        srows = [r for r in rows if r['strategy'] == strategy]
        for a in ATTRS:
            vals = [r for r in srows if r.get(a) is not None and not np.isnan(r[a])]
            old = [r for r in vals if r['ts'] < mid]
            new = [r for r in vals if r['ts'] >= mid]
            if len(old) < 60 or len(new) < 60:
                continue
            q1, q2 = np.percentile([r[a] for r in old], [33.3, 66.7])
            tier = lambda r: 0 if r[a] <= q1 else 1 if r[a] <= q2 else 2   # noqa: E731
            means = {}
            for name, part in (('older', old), ('newer', new)):
                g = [[r['y'] for r in part if tier(r) == k] for k in range(3)]
                means[name] = [float(np.mean(x)) if x else np.nan for x in g]
                lines.append(f"| {strategy} | {a} | {q1:.3g} / {q2:.3g} | {name} | " +
                             ' | '.join(f"{m:+.3f}" for m in means[name]) + f" | {len(part)} |")
            best = int(np.nanargmax(means['older']))
            worst = int(np.nanargmin(means['older']))
            if best == worst:
                continue
            same = (means['newer'][best] - means['newer'][worst]) > 0
            month = lambda r: r['ts'] // (30 * DAY_MS)                       # noqa: E731
            res = boot_diff([(r['y'], month(r)) for r in new if tier(r) == best],
                            [(r['y'], month(r)) for r in new if tier(r) == worst], rng)
            if res is not None:
                tests.append((strategy, a, best, worst, same, res))
    m = len(tests)
    ranked = sorted(range(m), key=lambda k: tests[k][5][2])
    qv = [1.0] * m
    prev = 1.0
    for pos in range(m - 1, -1, -1):
        k = ranked[pos]
        prev = min(prev, tests[k][5][2] * m / (pos + 1))
        qv[k] = prev
    lines += ['', '## Verdict (newer half: best older tercile minus worst)', '',
              '| strategy | attribute | best | worst | same sign | 90% interval | q (BH) | pool rule |',
              '|---|---|---|---|---|---|---:|---|']
    for k, (strategy, a, best, worst, same, (lo, hi, _p)) in enumerate(tests):
        ok = same and lo > 0 and qv[k] <= 0.10
        lines.append(f"| {strategy} | {a} | T{best + 1} | T{worst + 1} | {'yes' if same else 'no'} | "
                     f"[{lo:+.3f}..{hi:+.3f}] | {qv[k]:.2f} | {'ADOPT' if ok else '-'} |")
    text = '\n'.join(lines)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(text + '\n')
    print(text)


if __name__ == '__main__':
    main()
