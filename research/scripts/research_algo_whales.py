"""
Do ALGO BUY / SELL and WHALES BUY / SELL anomalies predict the next hours? (pre-registered 2026-10-12, the owner saw
them "move the price"; the raw journal suggested a REVERSAL after 4h.)

Data: the journal's anomaly rows (signals.db, any logic version - the labels' rules did not change) with the coin's
price at the event and the universe snapshots (table `universe`, every USDT perpetual's mark every 5-15 min).
Outcome per event and horizon H (1h, 4h): the coin's return from the event's price to the first snapshot at /
after t+H minus the MEAN return of every
coin over the same window (the universe snapshots nearest to t and t+H) - the market's move taken out - signed by
the label's direction (+ = the price went the label's way).
Placebo: the same coin at the same hour of day on a random other day 1-7 days away (its own excess return, same
sign) - what any moment of that coin does.
Pre-registered reading, per label and horizon: CONTINUATION if mean signed excess > placebo with the 90% interval
of the difference (bootstrap of 4h clusters) above 0 in both halves of the sample; REVERSAL if the interval is below
0 in both halves; otherwise NO EFFECT. Writes research/algo_whales.md.

    python research_algo_whales.py --db signals.db
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import argparse
import bisect
import os
import random
from collections import defaultdict

import numpy as np
import sqlite3

LABELS = ('ALGO BUY', 'ALGO SELL', 'WHALES BUY', 'WHALES SELL')
HOURS = (1, 4)
H_MS = 3_600_000


def load(db):
    c = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    ev = c.execute("select ts_ms, symbol, group_key, price from signals where kind='anomaly' and group_key in "
                   f"({','.join('?' * len(LABELS))}) and price > 0", LABELS).fetchall()
    snaps = defaultdict(dict)                       # ts -> {symbol: price}
    for ts, sym, px in c.execute("select ts_ms, symbol, price from universe where price > 0"):
        snaps[int(ts)][sym] = float(px)
    times = sorted(snaps)
    per_sym = defaultdict(list)                     # symbol -> sorted [(ts, price)]
    for t in times:
        for s, p in snaps[t].items():
            per_sym[s].append((t, p))
    return ev, snaps, times, per_sym


def nearest(times, t, tol=20 * 60_000):
    # the first snapshot AT / AFTER t (a snapshot before an event would hold the event's own move)
    i = bisect.bisect_left(times, t)
    return times[i] if i < len(times) and times[i] - t <= tol else None


def market_ret(snaps, times, t0, t1):
    a, b = nearest(times, t0), nearest(times, t1)
    if a is None or b is None or b <= a:
        return None
    pa, pb = snaps[a], snaps[b]
    common = [s for s in pa if s in pb]
    if len(common) < 50:
        return None
    return float(np.mean([pb[s] / pa[s] - 1 for s in common]))


def coin_ret(per_sym, sym, t0, t1, tol=20 * 60_000, start=None):
    rows = per_sym.get(sym)
    if not rows:
        return None
    ts = [r[0] for r in rows]

    def at(t):
        i = bisect.bisect_left(ts, t)
        return rows[i][1] if i < len(ts) and ts[i] - t <= tol else None
    a, b = (start if start else at(t0)), at(t1)
    return (b / a - 1) if a and b else None


def boot_diff(x, y, cx, cy, n=1000, seed=7):
    """90% interval of mean(x) - mean(y), resampling 4h clusters (events of one 4h block move together)."""
    rng = np.random.default_rng(seed)
    gx, gy = defaultdict(list), defaultdict(list)
    for v, c in zip(x, cx):
        gx[c].append(v)
    for v, c in zip(y, cy):
        gy[c].append(v)
    kx, ky = list(gx), list(gy)
    if len(kx) < 10 or len(ky) < 10:
        return None
    out = []
    for _ in range(n):
        sx = [v for k in rng.choice(kx, len(kx)) for v in gx[k]]
        sy = [v for k in rng.choice(ky, len(ky)) for v in gy[k]]
        out.append(np.mean(sx) - np.mean(sy))
    return float(np.percentile(out, 5)), float(np.percentile(out, 95))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default='signals.db')
    args = ap.parse_args()
    ev, snaps, times, per_sym = load(args.db)
    rnd = random.Random(11)
    res = defaultdict(lambda: {'real': [], 'plac': [], 'cr': [], 'cp': [], 'half': []})
    t_mid = None
    if ev:
        ts_all = sorted(e[0] for e in ev)
        t_mid = ts_all[len(ts_all) // 2]
    for ts, sym, label, px in ev:
        sym = sym.split(':')[0].replace('/', '')          # 'BTC/USDT:USDT' -> the universe table's 'BTCUSDT'
        d = 1 if label.endswith('BUY') else -1
        for h in HOURS:
            r = coin_ret(per_sym, sym, ts, ts + h * H_MS, start=px)    # from the event's own price
            m = market_ret(snaps, times, ts, ts + h * H_MS)
            if r is None or m is None:
                continue
            shift = rnd.choice([-1, 1]) * rnd.randint(1, 7) * 24 * H_MS
            rp = coin_ret(per_sym, sym, ts + shift, ts + shift + h * H_MS)
            mp = market_ret(snaps, times, ts + shift, ts + shift + h * H_MS)
            key = (label, h)
            res[key]['real'].append(d * (r - m))
            res[key]['cr'].append(ts // (4 * H_MS))
            res[key]['half'].append(ts < t_mid)
            if rp is not None and mp is not None:
                res[key]['plac'].append(d * (rp - mp))
                res[key]['cp'].append((ts + shift) // (4 * H_MS))
    lines = ['# ALGO / WHALES anomalies vs the market and a placebo (research_algo_whales.py)', '',
             'Signed excess return = the coin\'s return minus the mean of every coin, + = the label\'s way. Placebo = '
             'the same coin and hour on a random day 1-7 days away. Interval = 90% bootstrap of 4h clusters of the '
             'difference real - placebo. Pre-registered: CONTINUATION / REVERSAL only if the interval excludes 0 in both '
             'halves.', '',
             '| label | h | n | mean real | mean placebo | diff [90%] | older half | newer half | verdict |',
             '|---|---:|---:|---:|---:|---|---|---|---|']
    for (label, h), v in sorted(res.items()):
        real, plac = np.asarray(v['real']), np.asarray(v['plac'])
        if len(real) < 30 or len(plac) < 30:
            continue
        ci = boot_diff(v['real'], v['plac'], v['cr'], v['cp'])
        halves = []
        for flag in (True, False):
            idx = [i for i, f in enumerate(v['half']) if f == flag]
            rr = [v['real'][i] for i in idx]
            cc = [v['cr'][i] for i in idx]
            halves.append(boot_diff(rr, v['plac'], cc, v['cp']) if len(rr) >= 30 else None)
        f = lambda c: '-' if c is None else f"[{c[0] * 100:+.3f}..{c[1] * 100:+.3f}]"   # noqa: E731
        both_pos = all(c is not None and c[0] > 0 for c in halves)
        both_neg = all(c is not None and c[1] < 0 for c in halves)
        verdict = 'CONTINUATION' if both_pos else 'REVERSAL' if both_neg else 'no effect'
        lines.append(f"| {label} | {h}h | {len(real)} | {real.mean() * 100:+.3f}% | {plac.mean() * 100:+.3f}% | "
                     f"{(real.mean() - plac.mean()) * 100:+.3f}% {f(ci)} | {f(halves[0])} | {f(halves[1])} | {verdict} |")
    os.makedirs('research', exist_ok=True)
    open(os.path.join('research', 'algo_whales.md'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
