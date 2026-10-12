"""Session-anchored ORB: range = first 30m (2 bars) after a session open, entry on a break of that range (buy stop at
range high / sell stop at range low), stop = the opposite side, exit at the session end. Also Crabel's Stretch from
the session open (open +- 10-session SMA of min(H-O, O-L)). DST: London 07:00 UTC in Apr-Oct else 08:00; NY 13:30 /
14:30 (approx: US DST mid-Mar..early-Nov). Run: python -I sessions.py"""
import sys, os, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import bt

def dst_us(d): return (d.month, d.day) >= (3, 9) and (d.month, d.day) < (11, 2)
def dst_eu(d): return (d.month, d.day) >= (3, 30) and (d.month, d.day) < (10, 26)
SESS = {  # name -> (open h:m UTC (std), dst fn, length hours)
    'Asia (00:00 UTC, 8h)':   (lambda d: (0, 0), 8),
    'London (08/07 UTC, 8h)': (lambda d: (7, 0) if dst_eu(d) else (8, 0), 8),
    'New York (13:30/14:30, 6.5h)': (lambda d: (13, 30) if dst_us(d) else (14, 30), 6.5),
}

def run(mode):
    res = {k: [] for k in SESS}
    for sym, a in bt.load().items():
        ts = a[:, 0]; idx = {int(t): i for i, t in enumerate(ts)}
        hist = {k: [] for k in SESS}
        day0 = int(ts[0] // bt.DAY) + 1
        for day in range(day0, int(ts[-1] // bt.DAY)):
            d = dt.datetime.fromtimestamp(day * 86400, dt.UTC)
            for name, (fn, hours) in SESS.items():
                h, m = fn(d); t0 = (day * 86400 + h * 3600 + m * 60) * 1000
                i = idx.get(t0); n = int(hours * 4)
                if i is None or i + n > len(a): continue
                seg = a[i:i + n]; o = seg[0, 1]
                hist[name].append(min(seg[:, 2].max() - o, o - seg[:, 3].min()))
                if mode == 'range':
                    up, dn, start = seg[:2, 2].max(), seg[:2, 3].min(), 2
                else:
                    if len(hist[name]) < 11: continue
                    s = np.mean(hist[name][-11:-1]); up, dn, start = o + s, o - s, 0
                for b in range(i + start, i + n):
                    hu, hd = a[b, 2] >= up, a[b, 3] <= dn
                    if hu and hd: break
                    if hu or hd:
                        side = 1 if hu else -1
                        lvl = up if side > 0 else dn
                        entry = max(lvl, a[b, 1]) if side > 0 else min(lvl, a[b, 1])
                        stop = dn if side > 0 else up
                        if abs(entry - stop) / entry < 0.002: break
                        if side * ((a[b, 3] if side > 0 else a[b, 2]) - stop) <= 0:
                            R, mfe, xi = -1 - bt.cost(entry, abs(entry - stop)), 0, b
                        else:
                            R, mfe, xi = bt.orb_trade(a, None, b + 1, side, entry, stop, i + n, {})
                        res[name].append((ts[b], sym, side, R, mfe, ts[xi]))
                        break
    return res

if __name__ == '__main__':
  rep = []
  for mode, title in (('range', 'Session ORB: break of the first-30m range'), ('stretch', 'Session ORB: session open +- Stretch (Crabel)')):
    r = run(mode)
    rep.append(bt.table(title, r))
    print(rep[-1], flush=True)
  open('report_sessions.md', 'w').write('\n'.join(rep) + '\n')
