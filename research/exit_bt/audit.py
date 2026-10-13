"""Strategy audit: the bot's OWN detector functions (strategies/*.py, imported unchanged) called bar by bar on Binance
15m history (data/*.npy, 43 perps, 2025-08 .. 2026-10), each signal managed with the bot's exit plan in a simplified
form. Stop-first inside a bar (pessimistic); costs 0.20% round trip; R = initial risk; holdout from bt.SPLIT.

  BB W-BOTTOM / M-TOP   bollinger_wm_event(last 90 15m)   entry at the signal close; stop beyond the retest
                        (bb_stop, + 0.1 ATR pad); out when price reaches the live opposite band; 12h cap; the
                        plan's low_rr skip (band at the signal pays <= risk)
  VA80 LONG / SHORT     value_area_event(m15, cut)        entry at the close; stop the day's extreme; TP the far
                        value-area edge; out at the UTC day's close
  RSI2 LONG / SHORT     connors_event(daily)              entry at the daily close; out at the first close beyond
                        the SMA5; catastrophic stop 3 daily ATR; 60-day cap
  SPRING / UTAD         wyckoff_events(1h)                entry at the close; stop the spring / UTAD extreme; TP the
                        range's far side; 5-day cap
Not modelled: the bot's vetoes / confirmations / LTF triggers (they can only filter these signals).
Run: python -I audit.py [--setups bb,va,rsi2,wyckoff] [--symbols N]
"""
import argparse, os, sys, time
import numpy as np

sys.path.insert(0, '/opt/pump')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bt                                                    # noqa: E402
from strategies.maniac import bollinger_wm_event            # noqa: E402
from strategies.classic import value_area_event, connors_event   # noqa: E402
from strategies.wyckoff_range import wyckoff_events         # noqa: E402

Q = 900_000
H = 3_600_000


def agg(a, k):
    """15m rows -> k x 15m rows (ts, o, h, l, c, v), complete groups only, aligned to k*15m boundaries."""
    ms = k * Q
    g = a[:, 0] // ms
    out = []
    keys, idx = np.unique(g, return_index=True)
    for s, e in zip(idx, list(idx[1:]) + [len(a)]):
        if e - s == k:
            seg = a[s:e]
            out.append([seg[0, 0], seg[0, 1], seg[:, 2].max(), seg[:, 3].min(), seg[-1, 4], seg[:, 5].sum()])
    return np.array(out)


def manage(a, i0, side, entry, stop, tp=None, end_i=None, band=None, sma_exit=None):
    """From bar i0 on: stop first, then target / live band. Returns (R net, exit index)."""
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    end_i = min(len(a), end_i or len(a))
    for i in range(i0, end_i):
        o, h, l, c = a[i, 1:5]
        if side * ((l if side > 0 else h) - stop) <= 0:
            px = o if side * (o - stop) < 0 else stop
            return side * (px - entry) / risk - bt.COST * entry / risk, i
        fav = h if side > 0 else l
        if tp is not None and side * (fav - tp) >= 0:
            px = o if side * (o - tp) > 0 else tp
            return side * (px - entry) / risk - bt.COST * entry / risk, i
        if band is not None:
            lvl = band[i - 1]       # the band as it stood at the previous close (no look-ahead)
            if not np.isnan(lvl) and side * (fav - lvl) >= 0:
                px = o if side * (o - lvl) > 0 else lvl
                return side * (px - entry) / risk - bt.COST * entry / risk, i
        if sma_exit is not None and side * (c - sma_exit[i]) > 0:
            return side * (c - entry) / risk - bt.COST * entry / risk, i
    c = a[end_i - 1, 4]
    return side * (c - entry) / risk - bt.COST * entry / risk, end_i - 1


def atr_wilder(a, n=14):
    tr = np.concatenate([[a[0, 2] - a[0, 3]], np.maximum(a[1:, 2], a[:-1, 4]) - np.minimum(a[1:, 3], a[:-1, 4])])
    out = np.full(len(tr), np.nan)
    if len(tr) > n:
        out[n] = tr[1:n + 1].mean()
        for i in range(n + 1, len(tr)):
            out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


def bands(c, n=20, k=2.0):
    up, lo = np.full(len(c), np.nan), np.full(len(c), np.nan)
    cs, cs2 = np.cumsum(np.insert(c, 0, 0)), np.cumsum(np.insert(c * c, 0, 0))
    for i in range(n - 1, len(c)):
        s, s2 = cs[i + 1] - cs[i + 1 - n], cs2[i + 1] - cs2[i + 1 - n]
        m = s / n
        sd = max(s2 / n - m * m, 0) ** 0.5
        up[i], lo[i] = m + k * sd, m - k * sd
    return up, lo


def run_bb(sym, a, out):
    atr = atr_wilder(a)
    up, lo = bands(a[:, 4])
    rows = a.tolist()
    busy = -1
    for i in range(120, len(a) - 1):
        if i <= busy:
            continue
        ev = bollinger_wm_event(rows[i - 89:i + 1])
        if not ev:
            continue
        d, entry = ev['direction'], a[i, 4]
        if d * (ev['bb_target'] - entry) <= abs(entry - ev['bb_stop']):
            continue                                       # the plan's low_rr skip
        stop = ev['bb_stop'] - d * 0.1 * atr[i]
        r = manage(a, i + 1, d, entry, stop, end_i=i + 1 + 48, band=up if d > 0 else lo)
        if r:
            out.setdefault(ev['setup'], []).append((a[i, 0], sym, d, r[0], 0.0, a[r[1], 0]))
            busy = r[1]


def run_va(sym, a, out):
    rows = a.tolist()
    busy = -1
    for i in range(200, len(a) - 1):
        cut = int(a[i, 0]) + Q
        if cut % (2 * Q) or i <= busy:
            continue
        ev = value_area_event(rows[i - 199:i + 1], cut)
        if not ev:
            continue
        d, entry = ev['direction'], a[i, 4]
        day_end = ((cut // bt.DAY) + 1) * bt.DAY
        end_i = i + 1 + int((day_end - cut) // Q)
        r = manage(a, i + 1, d, entry, ev['anchor_extreme'], tp=ev['va_far'], end_i=end_i)
        if r:
            out.setdefault(ev['setup'], []).append((a[i, 0], sym, d, r[0], 0.0, a[r[1], 0]))
            busy = r[1]


def run_rsi2(sym, a, out):
    d1 = agg(a, 96)
    rows = d1.tolist()
    closes = d1[:, 4]
    sma5 = np.array([closes[max(0, k - 4):k + 1].mean() for k in range(len(closes))])
    busy = -1
    for k in range(205, len(d1) - 1):
        if k <= busy:
            continue
        ev = connors_event(rows[:k + 1])
        if not ev:
            continue
        d, entry = ev['direction'], d1[k, 4]
        stop = entry - d * 3.0 * (ev['connors_atr'] or 0)
        r = manage(d1, k + 1, d, entry, stop, end_i=k + 61, sma_exit=sma5)
        if r:
            out.setdefault(ev['setup'], []).append((d1[k, 0], sym, d, r[0], 0.0, d1[r[1], 0]))
            busy = r[1]


def run_wyckoff(sym, a, out):
    h1 = agg(a, 4)
    rows = h1.tolist()
    busy = -1
    for k in range(400, len(h1) - 1):
        if k <= busy:
            continue
        evs = wyckoff_events(rows[max(0, k - 499):k + 1])
        if not evs:
            continue
        ev = evs[0]
        d, entry = ev['direction'], h1[k, 4]
        far = ev['range_hi'] if d > 0 else ev['range_lo']
        if d * (far - entry) <= 0:
            continue
        r = manage(h1, k + 1, d, entry, ev['anchor_extreme'], tp=far, end_i=k + 1 + 120)
        if r:
            out.setdefault(ev['setup'], []).append((h1[k, 0], sym, d, r[0], 0.0, h1[r[1], 0]))
            busy = r[1]


RUNNERS = {'bb': run_bb, 'va': run_va, 'rsi2': run_rsi2, 'wyckoff': run_wyckoff}

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--setups', default='bb,va,rsi2,wyckoff')
    p.add_argument('--symbols', type=int, default=0)
    p.add_argument('--cost', type=float, default=0.002)
    args = p.parse_args()
    bt.COST = args.cost
    data = bt.load()
    syms = list(data)[:args.symbols] if args.symbols else list(data)
    res = {}
    for name in args.setups.split(','):
        t = time.time()
        for s in syms:
            RUNNERS[name](s, data[s], res)
        print(f"{name}: {time.time() - t:.0f}s", flush=True)
    rep = bt.table(f"Audit: the bot's detectors on {len(syms)} perps, costs {bt.COST:.2%}", res)
    print(rep)
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), f"report_audit_{args.setups.replace(',', '_')}_c{args.cost:g}.md"), 'w').write(rep + '\n')
