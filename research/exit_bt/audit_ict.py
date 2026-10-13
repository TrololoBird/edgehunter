"""ICT audit: the bot's own po3() and silver_bullet() (strategies/po3.py, silver_bullet.py, unchanged) on Binance 5m
history of the top-5 majors (data5/*.npy). Called at every 5m close inside their windows; one signal per window and
direction (the bot's gate). Plan as in the bot: a resting limit at the FVG's CE (filled if price returns to it while
the card waits: 3h PO3 / 1h SB), invalid if the extreme breaks first; stop the raid's extreme; target po3_target /
sb_target (first target); time cap 12h PO3 / 4h SB. Bias variants: none, and the daily bias = the last closed day
vs its SMA20 (a proxy of the bot's weekly / daily bias). Costs 0.07% (limit entry) and 0.20%.
Run: python -I audit_ict.py"""
import os, sys
import numpy as np
sys.path.insert(0, '/opt/pump')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bt, tf                                                   # noqa: E402
from strategies.po3 import po3, london_window                 # noqa: E402
from strategies.silver_bullet import silver_bullet, window_of  # noqa: E402

F = 300_000


def daily_bias(a):
    d = a[:, 0] // bt.DAY
    keys, idx = np.unique(d, return_index=True)
    closes = [a[e - 1, 4] for e in list(idx[1:]) + [len(a)]]
    out = {}
    for n, k in enumerate(keys):
        if n >= 21:
            prev = closes[n - 21:n - 1]
            out[int(k)] = 1 if closes[n - 1] > np.mean(prev) else -1
    return out


def run(sym, a, fn, wait_bars, cap_bars, target_key, res):
    rows = a.tolist()
    bias = daily_bias(a)
    seen = set()
    for i in range(400, len(a) - 1):
        now = int(a[i, 0]) + F
        win = london_window(now) if fn is po3 else window_of(now)
        if win is None:
            continue
        ev = fn(rows[i - 299:i + 1], now)
        if not ev:
            continue
        key = (ev['anchor_ts'], ev['direction'])
        if key in seen:
            continue
        seen.add(key)
        d, ce, ext, tgt = ev['direction'], ev['anchor_level'], ev['anchor_extreme'], ev[target_key]
        if d * (tgt - ce) <= abs(ce - ext):          # min_rr 1.0
            continue
        fill = None
        for j in range(i + 1, min(len(a), i + 1 + wait_bars)):
            if d * ((a[j, 3] if d > 0 else a[j, 2]) - ext) <= 0:
                break                                   # invalid before the fill
            if d * ((a[j, 3] if d > 0 else a[j, 2]) - ce) <= 0:
                fill = j
                break
        if fill is None:
            continue
        r = None
        # the fill bar itself: the stop inside it counts (pessimistic)
        if d * ((a[fill, 3] if d > 0 else a[fill, 2]) - ext) <= 0:
            r = (-1 - bt.COST * ce / abs(ce - ext), fill)
        else:
            import audit
            r = audit.manage(a, fill + 1, d, ce, ext, tp=tgt, end_i=fill + 1 + cap_bars)
        if r:
            b = bias.get(int(a[i, 0] // bt.DAY), 0)
            res.setdefault(ev['setup'], []).append((a[i, 0], sym, d, r[0], 0.0, a[r[1], 0]))
            if b == d:
                res.setdefault(ev['setup'] + ' + daily bias', []).append((a[i, 0], sym, d, r[0], 0.0, a[r[1], 0]))


if __name__ == '__main__':
    data = tf.load('data5')
    rep = []
    for cost in (0.0007, 0.0020):
        bt.COST = cost
        res = {}
        for s, a in data.items():
            run(s, a, po3, 36, 144, 'po3_target', res)
            run(s, a, silver_bullet, 12, 48, 'sb_target', res)
        rep.append(bt.table(f"ICT audit (bot's po3 / silver_bullet), top-5 majors 5m, costs {cost:.2%}", dict(sorted(res.items()))))
        print(rep[-1], flush=True)
    open(os.path.join(tf.HERE, 'report_audit_ict.md'), 'w').write('\n'.join(rep) + '\n')
