"""Exit-rule backtest for the bot's ORB (Crabel) and Turtle System 2 setups on Binance USDT-M 15m klines.

Entries are the bot's canon (strategies/classic.py stretch, strategies/turtle.py 55/20 channels, 2N, 0.5N adds);
only the exit / stop management varies. Intrabar order is unknown on 15m bars, so every bar checks the stop
FIRST (pessimistic), and trailing levels are updated from a bar only for the NEXT bar (no look-ahead).
Results are in R = the first unit's initial risk; costs 0.20% round trip per unit (taker 0.05% x2 + slippage).
Split: development = before SPLIT, holdout = after. Run: python bt.py
"""
import glob, os, random, datetime as dt
import numpy as np

COST = 0.0020
SPLIT = dt.datetime(2026, 3, 1, tzinfo=dt.UTC).timestamp() * 1000
DAY = 86_400_000


def load():
    out = {}
    for f in sorted(glob.glob(os.path.join(os.path.dirname(__file__), 'data', '*.npy'))):
        a = np.load(f)  # ts, o, h, l, c, v
        out[os.path.basename(f)[:-4]] = a
    return out


def daily(a):
    d = a[:, 0] // DAY
    keys, idx = np.unique(d, return_index=True)
    ends = list(idx[1:]) + [len(a)]
    rows = []
    for k, i, j in zip(keys, idx, ends):
        if j - i < 90:  # incomplete day
            continue
        rows.append((k * DAY, a[i, 1], a[i:j, 2].max(), a[i:j, 3].min(), a[j - 1, 4], i, j))
    return rows


def atr15(a, n=14):
    tr = np.maximum(a[1:, 2], a[:-1, 4]) - np.minimum(a[1:, 3], a[:-1, 4])
    tr = np.concatenate([[a[0, 2] - a[0, 3]], tr])
    out = np.convolve(tr, np.ones(n) / n, 'full')[:len(tr)]
    out[:n] = np.nan
    return out


# ------------------------------------------------------------------ ORB
ORB_RULES = {
    'A base: stop / session close':   dict(),
    'B breakeven at +1R':             dict(be=1.0),
    'C chandelier 3xATR15':           dict(trail=3),
    'D BE+1R & chandelier 3xATR15':   dict(be=1.0, trail=3),
    'E chandelier 6xATR15':           dict(trail=6),
    'F BE+1R & chandelier 6xATR15':   dict(be=1.0, trail=6),
    'G fixed TP 2R':                  dict(tp=2.0),
    'H 50% at 2R, rest BE -> close':  dict(part=2.0),
    'I time exit 8h':                 dict(hours=8),
    'J BE+1R & chand 6x, no session (max 3d)': dict(be=1.0, trail=6, nosession=True),
}


def orb_trade(a, atr, i0, side, entry, stop, end_i, r):
    """Manage one ORB trade from bar i0 under rule r. Returns (R net, MFE R, exit index)."""
    risk = abs(entry - stop)
    if r.get('nosession'):
        end_i = min(len(a), i0 + 3 * 96)
    if r.get('hours'):
        end_i = min(end_i, i0 + r['hours'] * 4)
    sl, best, half_done, realized, size = stop, entry, False, 0.0, 1.0
    tp = entry + side * r['tp'] * risk if r.get('tp') else None
    mfe = 0.0
    for i in range(i0, end_i):
        o, h, l, c = a[i, 1:5]
        adverse = l if side > 0 else h
        fav = h if side > 0 else l
        if side * (adverse - sl) <= 0:  # stop first (pessimistic); a gap through it fills at the open
            px = o if side * (o - sl) < 0 else sl
            return realized + size * side * (px - entry) / risk - cost(entry, risk, half_done), mfe, i
        mfe = max(mfe, side * (fav - entry) / risk)
        if tp is not None and side * (fav - tp) >= 0:
            return side * (tp - entry) / risk - cost(entry, risk), mfe, i
        if r.get('part') and not half_done and side * (fav - (entry + side * r['part'] * risk)) >= 0:
            realized += 0.5 * r['part']; size = 0.5; half_done = True; sl = entry
        best = max(best, fav) if side > 0 else min(best, fav)
        if r.get('be') and side * (best - entry) >= r['be'] * risk:
            sl = max(sl, entry) if side > 0 else min(sl, entry)
        if r.get('trail') and not np.isnan(atr[i]):
            lvl = best - side * r['trail'] * atr[i]
            sl = max(sl, lvl) if side > 0 else min(sl, lvl)
    c = a[end_i - 1, 4]
    return realized + size * side * (c - entry) / risk - cost(entry, risk, half_done), mfe, end_i - 1


def cost(entry, risk, extra=False):
    return COST * entry / risk * (1.0 + (0.0 if not extra else 0.0))


def run_orb(data):
    res = {k: [] for k in ORB_RULES}
    for sym, a in data.items():
        atr = atr15(a)
        days = daily(a)
        for k in range(10, len(days)):
            ts, o, _, _, _, i, j = days[k]
            s = np.mean([min(d[2] - d[1], d[1] - d[3]) for d in days[k - 10:k]])
            if s <= 0:
                continue
            up, dn = o + s, o - s
            for b in range(i, j):
                hit_up, hit_dn = a[b, 2] >= up, a[b, 3] <= dn
                if hit_up and hit_dn:
                    break  # both levels in one 15m bar: order unknown, skipped
                if hit_up or hit_dn:
                    side = 1 if hit_up else -1
                    lvl = up if side > 0 else dn
                    entry = max(lvl, a[b, 1]) if side > 0 else min(lvl, a[b, 1])
                    stop = dn if side > 0 else up
                    if abs(entry - stop) / entry < 0.002:
                        break
                    for name, r in ORB_RULES.items():
                        # the entry bar itself: only the part after the touch is unknown -> start managing at b+1,
                        # but a stop inside the entry bar counts (pessimistic)
                        if side * ((a[b, 3] if side > 0 else a[b, 2]) - stop) <= 0:
                            R, mfe, xi = -1.0 - cost(entry, abs(entry - stop)), 0.0, b
                        else:
                            R, mfe, xi = orb_trade(a, atr, b + 1, side, entry, stop, j, r)
                        res[name].append((a[b, 0], sym, side, R, mfe, a[xi, 0]))
                    break
    return res


# ------------------------------------------------------------------ Turtle System 2
TURTLE_RULES = {
    'T0 canon: 4 units, 2N stop, 20d-low exit': dict(units=4),
    'T1 no pyramid (1 unit)':                    dict(units=1),
    'T2 4 units + chandelier 3N':                dict(units=4, chand=3),
    'T3 4 units + stop to avg entry at +2N':     dict(units=4, be=2),
    'T4 1 unit + chandelier 3N':                 dict(units=1, chand=3),
    'T5 1 unit + 10d exit (S1 exit)':            dict(units=1, exit_days=10),
    'T6 4 units, adds need 1h close above':      dict(units=4, confirm_add=True),
    'T7 4 units + chandelier 3N + BE at +2N':    dict(units=4, chand=3, be=2),
}


def run_turtle(data):
    res = {k: [] for k in TURTLE_RULES}
    for sym, a in data.items():
        days = daily(a)
        if len(days) < 80:
            continue
        H = np.array([d[2] for d in days]); L = np.array([d[3] for d in days]); C = np.array([d[4] for d in days])
        tr = np.maximum(H[1:], C[:-1]) - np.minimum(L[1:], C[:-1])
        tr = np.concatenate([[H[0] - L[0]], tr])
        for name, r in TURTLE_RULES.items():
            ed = r.get('exit_days', 20)
            k = 56
            while k < len(days):
                hi55, lo55 = H[k - 55:k].max(), L[k - 55:k].min()
                N = tr[k - 20:k].mean()
                i, j = days[k][5], days[k][6]
                opened = None
                for b in range(i, j):
                    if a[b, 2] >= hi55 and a[b, 3] <= lo55:
                        break
                    if a[b, 2] >= hi55 or a[b, 3] <= lo55:
                        side = 1 if a[b, 2] >= hi55 else -1
                        lvl = hi55 if side > 0 else lo55
                        opened = (b, side, max(lvl, a[b, 1]) if side > 0 else min(lvl, a[b, 1]))
                        break
                if not opened:
                    k += 1
                    continue
                b0, side, e0 = opened
                R, mfe, xb = turtle_manage(a, days, H, L, b0, k, side, e0, N, r, ed)
                res[name].append((a[b0, 0], sym, side, R, mfe, a[xb, 0]))
                # flat again: the next entry is looked for from the day after the exit
                k = max(k + 1, int((a[xb, 0] // DAY) - days[0][0] // DAY) + 1)
    return res


def turtle_manage(a, days, H, L, b0, k0, side, e0, N, r, ed):
    risk = 2 * N
    units = [e0]
    sl = e0 - side * 2 * N
    best = e0
    mfe = 0.0
    day_idx = {d[0] // DAY: n for n, d in enumerate(days)}
    pending_add = None
    for b in range(b0 + 1, min(len(a), b0 + 96 * 200)):
        o, h, l, c = a[b, 1:5]
        dn = day_idx.get(a[b, 0] // DAY)
        if dn is None:
            continue
        chan = L[dn - ed:dn].min() if side > 0 else H[dn - ed:dn].max()
        exit_lvl = max(sl, chan) if side > 0 else min(sl, chan)
        adverse = l if side > 0 else h
        if side * (adverse - exit_lvl) <= 0:
            px = o if side * (o - exit_lvl) < 0 else exit_lvl
            pnl = sum(side * (px - u) for u in units) / risk - sum(COST * u for u in units) / risk
            return pnl, mfe, b
        fav = h if side > 0 else l
        best = max(best, fav) if side > 0 else min(best, fav)
        mfe = max(mfe, sum(side * (fav - u) for u in units) / risk)
        # pyramid: +1 unit every 0.5N from the last unit, the whole stop to 2N from the newest
        nxt = units[-1] + side * 0.5 * N
        if len(units) < r['units'] and side * (fav - nxt) >= 0:
            if r.get('confirm_add'):
                if pending_add is None:
                    pending_add = nxt
            else:
                units.append(max(nxt, o) if side > 0 else min(nxt, o))
                sl = units[-1] - side * 2 * N
        if pending_add is not None and (b + 1) % 4 == 0:  # 1h close
            if side * (c - pending_add) > 0:
                units.append(c); sl = c - side * 2 * N
            pending_add = None
        if r.get('be') and side * (best - e0) >= r['be'] * N:
            avg = sum(units) / len(units)
            sl = max(sl, avg) if side > 0 else min(sl, avg)
        if r.get('chand'):
            lvl = best - side * r['chand'] * N
            sl = max(sl, lvl) if side > 0 else min(sl, lvl)
    b = min(len(a), b0 + 96 * 200) - 1
    px = a[b, 4]
    return sum(side * (px - u) for u in units) / risk - sum(COST * u for u in units) / risk, mfe, b


# ------------------------------------------------------------------ report
def stats(rows):
    if not rows:
        return None
    R = np.array([x[3] for x in rows]); M = np.array([x[4] for x in rows])
    order = np.argsort([x[5] for x in rows])
    eq = np.cumsum(R[order]); dd = (np.maximum.accumulate(eq) - eq).max()
    wins, losses = R[R > 0].sum(), -R[R < 0].sum()
    # day-block bootstrap of the mean
    by_day = {}
    for x in rows:
        by_day.setdefault(int(x[0] // DAY), []).append(x[3])
    blocks = list(by_day.values()); rnd = random.Random(7); means = []
    for _ in range(400):
        s = [v for _ in blocks for v in rnd.choice(blocks)]
        means.append(np.mean(s))
    lo, hi = np.percentile(means, [5, 95])
    return dict(n=len(R), mean=R.mean(), lo=lo, hi=hi, total=R.sum(), win=(R > 0).mean(), pf=wins / losses if losses else np.inf,
                dd=dd, give=np.mean(M - R), big=(M >= 5).mean())


def table(title, res):
    out = [f"\n## {title}\n", "| rule | part | n | mean R | 90% CI | total R | win% | PF | maxDD R | giveback R | MFE>=5R |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, rows in res.items():
        for part, sel in (('dev', [x for x in rows if x[0] < SPLIT]), ('holdout', [x for x in rows if x[0] >= SPLIT])):
            s = stats(sel)
            if s:
                out.append(f"| {name} | {part} | {s['n']} | {s['mean']:+.3f} | [{s['lo']:+.3f}, {s['hi']:+.3f}] | {s['total']:+.0f} | "
                           f"{s['win']:.0%} | {s['pf']:.2f} | {s['dd']:.0f} | {s['give']:.2f} | {s['big']:.1%} |")
    return '\n'.join(out)


if __name__ == '__main__':
    data = load()
    print(f"{len(data)} symbols")
    rep = [f"# Exit backtest: {len(data)} Binance perps, 15m, {dt.datetime.fromtimestamp(min(a[0,0] for a in data.values())/1000, dt.UTC):%Y-%m-%d} .. "
           f"{dt.datetime.fromtimestamp(max(a[-1,0] for a in data.values())/1000, dt.UTC):%Y-%m-%d}; holdout from {dt.datetime.fromtimestamp(SPLIT/1000, dt.UTC):%Y-%m-%d}; costs {COST:.2%} round trip per unit"]
    rep.append(table('ORB (Crabel, open +- 10d Stretch)', run_orb(data)))
    print(rep[-1], flush=True)
    rep.append(table('Turtle System 2 (55d breakout)', run_turtle(data)))
    print(rep[-1])
    open(os.path.join(os.path.dirname(__file__), 'report.md'), 'w').write('\n'.join(rep) + '\n')
