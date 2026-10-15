"""
Plan 2.1 / 2.2 / 2.10 (eng-59), pre-registered before the run, on the Binance archive's 1h candles (daily = 1h
aggregated by UTC day):

- ORB (Crabel, as live since eng-55): stop orders at the UTC day's open +- the Stretch (SMA10 of min(H - O, O - L) of
  the closed days); the first level touched (in 1h order) is the trade, the other level its stop, out at the day's
  close. An hour touching the entry level and the stop counts the stop (conservative). Split by NR4 / NR7 of the day
  before (Crabel's contraction filter).
- Cup with handle (O'Neil, the live detector `strategies.cup_handle.cup_handle` on daily candles): entry at the
  breakout day's close, stop the handle's low, half out at half the cup's height, the rest at the full height, else
  the stop, capped at 60 days. 2.10: the depth in % (the rule 12-33%) vs in weekly ATRs - terciles of the depth / the
  20-week ATR, cut on the older half.
Costs: 0.10% round trip + 5 bps slippage each side. R = net result / initial risk.
Decision rule: a variant / split is adopted only if its mean net R > 0 in BOTH halves (older / newer) and the newer
half's 90% month-cluster interval is above 0; NR4 / NR7 only if the filtered days beat the unfiltered in both halves.

Run: .venv\\Scripts\\python research_daily_methods.py [--months 36] [--coins 150] [--out research/daily_methods.md]
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import argparse
import os
from datetime import date, timedelta
from typing import Dict, List

import numpy as np

from strategies.classic import narrow_range, stretch
from strategies.cup_handle import cup_handle

COST = 0.001 + 2 * 0.0005
DAY_MS = 86_400_000


def daily_of(h1: np.ndarray) -> List[List[float]]:
    days: Dict[int, List[float]] = {}
    for t, o, h, lo, c, v in h1:
        k = int(t // DAY_MS * DAY_MS)
        d = days.get(k)
        if d is None:
            days[k] = [k, o, h, lo, c, v]
        else:
            d[2], d[3], d[4], d[5] = max(d[2], h), min(d[3], lo), c, d[5] + v
    return [days[k] for k in sorted(days)]


def orb_trades(h1: np.ndarray, d1: List[List[float]]) -> List[Dict]:
    out = []
    by_day: Dict[int, List] = {}
    for row in h1:
        by_day.setdefault(int(row[0] // DAY_MS * DAY_MS), []).append(row)
    for i in range(11, len(d1)):
        day = d1[i][0]
        bars = by_day.get(day)
        if not bars or len(bars) < 20:
            continue
        hist = d1[:i]
        s = stretch(hist, 10)
        if not s or s <= 0:
            continue
        op = bars[0][1]
        up, dn = op + s, op - s
        side = None
        for k, b in enumerate(bars):
            hit_up, hit_dn = b[2] >= up, b[3] <= dn
            if hit_up or hit_dn:
                if hit_up and hit_dn:
                    side, entry, stop, exit_px = 1, up, dn, dn       # both in one hour: the stop counts
                    break
                side = 1 if hit_up else -1
                entry, stop = (up, dn) if side > 0 else (dn, up)
                entry = max(b[1], entry) if side > 0 else min(b[1], entry)
                exit_px = None
                for b2 in bars[k + 1:]:
                    if (b2[3] <= stop) if side > 0 else (b2[2] >= stop):
                        exit_px = min(b2[1], stop) if side > 0 else max(b2[1], stop)
                        break
                if exit_px is None:
                    exit_px = bars[-1][4]
                break
        if side is None:
            continue
        risk = abs(entry - stop)
        if risk <= 0:
            continue
        r = (side * (exit_px - entry) - COST * entry) / risk
        out.append({'ts': day, 'r': r, 'nr4': narrow_range(hist, 4), 'nr7': narrow_range(hist, 7)})
    return out


def cup_trades(d1: List[List[float]]) -> List[Dict]:
    out = []
    i, n = 60, len(d1)
    while i < n - 1:
        ev = cup_handle(d1[:i + 1], '1d', DAY_MS)
        if ev is None:
            i += 1
            continue
        entry, stop = d1[i][4], ev['ch_stop']
        risk = entry - stop
        if risk <= 0:
            i += 1
            continue
        t1, t2 = ev['ch_target'], ev['ch_target_full']
        half, res, j = False, None, i + 1
        while j < n and j - i <= 60:
            o, h, lo = d1[j][1], d1[j][2], d1[j][3]
            if lo <= stop:
                px = min(o, stop)
                res = (0.5 * (t1 - entry) + 0.5 * (px - entry)) if half else (px - entry)
                break
            if not half and h >= t1:
                half = True
            if half and h >= t2:
                res = 0.5 * (t1 - entry) + 0.5 * (t2 - entry)
                break
            j += 1
        if res is None:
            px = d1[min(j, n - 1)][4]
            res = (0.5 * (t1 - entry) + 0.5 * (px - entry)) if half else (px - entry)
        rim_bottom = (ev['ch_target_full'] - ev['anchor_level'])
        weeks = [d1[k] for k in range(max(0, i - 140), i)]
        wk = [weeks[k:k + 7] for k in range(0, len(weeks) - 6, 7)]
        trs = [max(x[2] for x in w) - min(x[3] for x in w) for w in wk]
        watr = float(np.mean(trs[-20:])) if trs else None
        out.append({'ts': d1[i][0], 'r': (res - COST * entry) / risk,
                    'depth_watr': rim_bottom / watr if watr else None})
        i = j + 1
    return out


def summary(rs: List[float], ts: List[int], rng) -> str:
    if len(rs) < 5:
        return f"{len(rs)} trades"
    r = np.array(rs)
    mon = np.array([t // (30 * DAY_MS) for t in ts])
    u = np.unique(mon)
    idx = {m: np.where(mon == m)[0] for m in u}
    bs = [r[np.concatenate([idx[m] for m in rng.choice(u, len(u))])].mean() for _ in range(2000)]
    lo, hi = np.percentile(bs, [5, 95])
    return f"{len(r)} trades, mean {r.mean():+.3f}R [{lo:+.3f}..{hi:+.3f}], win {(r > 0).mean():.0%}"


def main():
    from history import Archive
    from pretrain import _spot_pair
    ap = argparse.ArgumentParser()
    ap.add_argument('--months', type=int, default=36)
    ap.add_argument('--coins', type=int, default=150)
    ap.add_argument('--rate', type=float, default=2e6)
    ap.add_argument('--out', default=os.path.join('research', 'daily_methods.md'))
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
    vols = []
    for s in coins:
        try:
            d = arch.klines_ohlc('futures', s, '1d', first, end)
        except Exception:
            continue
        if len(d) >= 120:
            vols.append((float(d[-90:, 5].mean()), s))
    pick = [s for _, s in sorted(vols, reverse=True)[:args.coins]]
    orb, cup = [], []
    for k, s in enumerate(pick):
        try:
            h1 = arch.klines_ohlc('futures', s, '1h', first, end)
        except Exception:
            continue
        if len(h1) < 24 * 30:
            continue
        d1 = daily_of(h1)
        orb += orb_trades(h1, d1)
        cup += cup_trades(d1)
        print(f"{k + 1}/{len(pick)} {s}: orb {len(orb)} cup {len(cup)}", flush=True)
    rng = np.random.default_rng(9)
    allts = [t['ts'] for t in orb + cup]
    mid = (min(allts) + max(allts)) / 2 if allts else 0
    lines = [f"# Daily methods on the archive ({len(pick)} coins, {first} .. {end})", '',
             'Rules: the docstring of `research_daily_methods.py` (pre-registered). Net of 0.20% round trip.', '']

    def block(title, rows):
        lines.append(f"## {title}")
        for half, sel in (('older', [t for t in rows if t['ts'] < mid]), ('newer', [t for t in rows if t['ts'] >= mid]),
                          ('all', rows)):
            lines.append(f"- {half}: {summary([t['r'] for t in sel], [t['ts'] for t in sel], rng)}")
        lines.append('')

    block('ORB (Crabel, open +- Stretch, out at the close)', orb)
    block('ORB after an NR7 day', [t for t in orb if t['nr7']])
    block('ORB after an NR4 day (not NR7)', [t for t in orb if t['nr4'] and not t['nr7']])
    block('ORB without NR4 / NR7', [t for t in orb if t['nr4'] is not None and t['nr7'] is not None and not t['nr4'] and not t['nr7']])
    block('Cup with handle (daily, O\'Neil)', cup)
    deep = [t for t in cup if t['depth_watr'] is not None]
    old = [t['depth_watr'] for t in deep if t['ts'] < mid]
    if len(old) >= 15:
        q1, q2 = np.percentile(old, [33.3, 66.7])
        lines.append(f"Depth in 20-week ATRs, terciles cut on the older half: {q1:.2f} / {q2:.2f}")
        lines.append('')
        block('Cup: shallow (T1)', [t for t in deep if t['depth_watr'] <= q1])
        block('Cup: middle (T2)', [t for t in deep if q1 < t['depth_watr'] <= q2])
        block('Cup: deep (T3)', [t for t in deep if t['depth_watr'] > q2])
    text = '\n'.join(lines)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(text + '\n')
    print(text)


if __name__ == '__main__':
    main()
