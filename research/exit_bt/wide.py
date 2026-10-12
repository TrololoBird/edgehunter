"""Session ORB on top-5 majors with a WIDE risk: entry on the break of the first M-minute range (as tf.py), but the
stop = k x daily ATR(14) from the entry and a fixed target at T R; out at the session end otherwise. Costs in R shrink
by the wider stop. Pessimistic stop-first inside a bar. Run: python -I wide.py"""
import sys, os, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import bt, sessions, tf


def daily_atr(a):
    days = bt.daily(a)
    H = np.array([d[2] for d in days]); L = np.array([d[3] for d in days]); C = np.array([d[4] for d in days])
    tr = np.concatenate([[H[0] - L[0]], np.maximum(H[1:], C[:-1]) - np.minimum(L[1:], C[:-1])])
    return {int(d[0] // bt.DAY): tr[max(0, n - 14):n].mean() for n, d in enumerate(days) if n >= 14}


def run(data, bar, rng, k_atr, tp, hold_h=None):
    per_h, kb = 60 // bar, rng // bar
    res = {}
    for name, (fn, hours) in sessions.SESS.items():
        if name.startswith('Asia'):
            continue
        rows = []
        for sym, a in data.items():
            ts = a[:, 0]; idx = {int(t): i for i, t in enumerate(ts)}; atr = daily_atr(a)
            for day in range(int(ts[0] // bt.DAY) + 1, int(ts[-1] // bt.DAY)):
                if day not in atr:
                    continue
                d = dt.datetime.fromtimestamp(day * 86400, dt.UTC)
                h, m = fn(d); i = idx.get((day * 86400 + h * 3600 + m * 60) * 1000)
                n = int((hold_h or hours) * per_h)
                if i is None or i + n > len(a):
                    continue
                up, dn = a[i:i + kb, 2].max(), a[i:i + kb, 3].min()
                for b in range(i + kb, i + int(hours * per_h)):
                    hu, hd = a[b, 2] >= up, a[b, 3] <= dn
                    if hu and hd:
                        break
                    if hu or hd:
                        side = 1 if hu else -1
                        lvl = up if side > 0 else dn
                        entry = max(lvl, a[b, 1]) if side > 0 else min(lvl, a[b, 1])
                        stop = entry - side * k_atr * atr[day]
                        if side * ((a[b, 3] if side > 0 else a[b, 2]) - stop) <= 0:
                            R, mfe, xi = -1 - bt.cost(entry, abs(entry - stop)), 0, b
                        else:
                            R, mfe, xi = bt.orb_trade(a, None, b + 1, side, entry, stop, min(len(a), i + n), {'tp': tp})
                        rows.append((ts[b], sym, side, R, mfe, ts[xi], abs(entry - stop) / entry))
                        break
        res[name.split(' (')[0]] = rows
    return res


if __name__ == '__main__':
    data = tf.load('data5')
    out = ["# Session ORB, wide risk (stop k x daily ATR, target T R), top-5 majors, 5m bars; mean R (90% CI)", "",
           "| range | k ATR | target | hold | session | stop % | dev 0.20% | holdout 0.20% | holdout 0.07% | holdout gross | n ho |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for rng in (30, 60):
        for k in (0.5, 1.0):
            for T in (1.0, 2.0, 3.0):
                for hold in (None, 24):
                    cell = {}
                    for cost in (0.0020, 0.0007, 0.0):
                        bt.COST = cost
                        for s, rows in run(data, 5, rng, k, T, hold).items():
                            cell.setdefault(s, {})[cost] = (bt.stats([x for x in rows if x[0] < bt.SPLIT]),
                                                             bt.stats([x for x in rows if x[0] >= bt.SPLIT]),
                                                             np.median([x[6] for x in rows]) * 100)
                    for s, c in cell.items():
                        f = lambda x: f"{x['mean']:+.3f} [{x['lo']:+.2f},{x['hi']:+.2f}]"
                        out.append(f"| {rng}m | {k} | {T}R | {'session' if hold is None else '24h'} | {s} | {c[0.002][2]:.2f} | "
                                   f"{f(c[0.002][0])} | {f(c[0.002][1])} | {f(c[0.0007][1])} | {f(c[0.0][1])} | {c[0.002][1]['n']} |")
                        print(out[-1], flush=True)
    open(os.path.join(tf.HERE, 'report_wide.md'), 'w').write('\n'.join(out) + '\n')
