"""Timeframe sensitivity of the session ORB on the top-5 majors: opening-range length (15/30/60/120m) x bar
resolution (5m vs 15m) x costs. Range = the first M minutes after the session open, entry on a break of it, stop = the
other side, out at the session end; stop-first inside a bar (pessimistic). Run: python -I tf.py"""
import sys, os, datetime as dt, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import bt, sessions

MAJ = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']
HERE = os.path.dirname(os.path.abspath(__file__))


def load(folder):
    return {s: np.load(os.path.join(HERE, folder, s + '.npy')) for s in MAJ}


def run(data, bar_min, range_min):
    per_h = 60 // bar_min
    k = range_min // bar_min
    res = {}
    for name, (fn, hours) in sessions.SESS.items():
        rows = []
        for sym, a in data.items():
            ts = a[:, 0]; idx = {int(t): i for i, t in enumerate(ts)}
            for day in range(int(ts[0] // bt.DAY) + 1, int(ts[-1] // bt.DAY)):
                d = dt.datetime.fromtimestamp(day * 86400, dt.UTC)
                h, m = fn(d); i = idx.get((day * 86400 + h * 3600 + m * 60) * 1000)
                n = int(hours * per_h)
                if i is None or i + n > len(a):
                    continue
                up, dn = a[i:i + k, 2].max(), a[i:i + k, 3].min()
                for b in range(i + k, i + n):
                    hu, hd = a[b, 2] >= up, a[b, 3] <= dn
                    if hu and hd:
                        break
                    if hu or hd:
                        side = 1 if hu else -1
                        lvl = up if side > 0 else dn
                        entry = max(lvl, a[b, 1]) if side > 0 else min(lvl, a[b, 1])
                        stop = dn if side > 0 else up
                        if abs(entry - stop) / entry < 0.001:
                            break
                        if side * ((a[b, 3] if side > 0 else a[b, 2]) - stop) <= 0:
                            R, mfe, xi = -1 - bt.cost(entry, abs(entry - stop)), 0, b
                        else:
                            R, mfe, xi = bt.orb_trade(a, None, b + 1, side, entry, stop, i + n, {})
                        rows.append((ts[b], sym, side, R, mfe, ts[xi], abs(entry - stop) / entry))
                        break
        res[name.split(' (')[0]] = rows
    return res


if __name__ == '__main__':
    out = ["# Session ORB timeframe sensitivity, top-5 majors; mean R per trade (90% day-block CI), dev | holdout",
           "", "| bars | range | session | stop % | gross dev | gross holdout | 0.07% holdout | 0.20% holdout | n holdout |",
           "|---|---|---|---|---|---|---|---|---|"]
    for folder, bar in (('data5', 5), ('data', 15)):
        data = load(folder)
        for rng in (15, 30, 60, 120):
            if rng < bar:
                continue
            cells = {}
            for cost in (0.0, 0.0007, 0.0020):
                bt.COST = cost
                for sess, rows in run(data, bar, rng).items():
                    dev = bt.stats([x for x in rows if x[0] < bt.SPLIT]); ho = bt.stats([x for x in rows if x[0] >= bt.SPLIT])
                    c = cells.setdefault(sess, {'stop': np.median([x[6] for x in rows]) * 100, 'n': ho['n']})
                    c[cost] = (dev, ho)
            for sess, c in cells.items():
                f = lambda s: f"{s['mean']:+.3f} [{s['lo']:+.2f},{s['hi']:+.2f}]"
                out.append(f"| {bar}m | {rng}m | {sess} | {c['stop']:.2f} | {f(c[0.0][0])} | {f(c[0.0][1])} | "
                           f"{f(c[0.0007][1])} | {f(c[0.002][1])} | {c['n']} |")
            print('\n'.join(out[-len(cells):]), flush=True)
    open(os.path.join(HERE, 'report_tf.md'), 'w').write('\n'.join(out) + '\n')
