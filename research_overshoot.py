"""
How far price pierces a level before it turns back: the stop buffer measured, not guessed (it replaces the 0.3 ATR
buffer and the 1 ATR stop floor).

Levels, each known only from the candle that confirms it (no look-ahead):
  swing_15m / swing_1h  a pivot high / low with 3 candles on each side (known 3 candles after it)
  equal                 two 1h pivots of one side within 0.1% of each other (the later pivot's time)
  pdhl                  the previous UTC day's high / low (known at the day's close)
  round                 round numbers: a tenth of the price's order of magnitude
The first 15m candle that trades beyond an untouched level is a TEST. It is a REJECTION when a close back on the
level's side comes within 4 candles (1h); its depth = the furthest price beyond the level until that close, in % of
the level. Else a BREAK. Per coin x kind: p50 / p80 / p90 of rejection depths, the break share.

Stability check (the number is only useful if it holds): p80 from the older half, then the share of the newer half's
rejections that stayed within it (80% expected if it is stable).

    python research_overshoot.py --months 12 --limit 80
Writes models/overshoot.json (read by the live stop rule: strategies/geometry.overshoot) and research/overshoot.md.
"""
import argparse
import json
import logging
import math
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List

import numpy as np

KINDS = ('swing_15m', 'swing_1h', 'equal', 'pdhl', 'round')
PIVOT = 3
RECLAIM = 4
DAY_MS = 86_400_000


def pivots(h: np.ndarray, l: np.ndarray, k: int):
    """(index, price, side) of pivots; side +1 = a high (resistance), -1 = a low (support)."""
    out = []
    for i in range(k, len(h) - k):
        if h[i] == h[i - k:i + k + 1].max() and (h[i - k:i + k + 1] == h[i]).sum() == 1:
            out.append((i, h[i], 1))
        if l[i] == l[i - k:i + k + 1].min() and (l[i - k:i + k + 1] == l[i]).sum() == 1:
            out.append((i, l[i], -1))
    return out


def levels_of(c15: np.ndarray) -> List[tuple]:
    """(known_from_ms, price, side, kind) of every level the 15m candles define."""
    ts, h, l = c15[:, 0], c15[:, 2], c15[:, 3]
    out = []
    for i, p, s in pivots(h, l, PIVOT):
        out.append((ts[i + PIVOT] + 900_000, p, s, 'swing_15m'))
    # 1h candles from the 15m ones (complete hours only)
    hour = (ts // 3_600_000).astype(np.int64)
    starts = np.flatnonzero(np.r_[True, hour[1:] != hour[:-1]])
    h1 = []
    for a, b in zip(starts, list(starts[1:]) + [len(ts)]):
        if b - a == 4:
            h1.append((ts[a], h[a:b].max(), l[a:b].min()))
    if len(h1) > 2 * PIVOT + 1:
        t1 = np.array([x[0] for x in h1])
        hh, ll = np.array([x[1] for x in h1]), np.array([x[2] for x in h1])
        piv = pivots(hh, ll, PIVOT)
        for i, p, s in piv:
            out.append((t1[i + PIVOT] + 3_600_000, p, s, 'swing_1h'))
        by_side = defaultdict(list)
        for i, p, s in piv:
            for j, q in by_side[s][-10:]:
                if abs(p / q - 1) <= 0.001:
                    out.append((t1[i + PIVOT] + 3_600_000, max(p, q) if s > 0 else min(p, q), s, 'equal'))
                    break
            by_side[s].append((i, p))
    day = (ts // DAY_MS).astype(np.int64)
    for d in np.unique(day)[:-1]:
        m = day == d
        out.append(((d + 1) * DAY_MS, h[m].max(), 1, 'pdhl'))
        out.append(((d + 1) * DAY_MS, l[m].min(), -1, 'pdhl'))
    # round numbers around each day's close, known from the start (they are fixed prices)
    for d in np.unique(day):
        close = c15[day == d][-1, 4]
        step = 10 ** (math.floor(math.log10(close)) - 1)
        base = math.floor(close / step) * step
        for k in (-2, -1, 1, 2, 3):
            p = base + k * step
            out.append(((d + 1) * DAY_MS, p, 1 if p > close else -1, 'round'))
    return out


def tests_of(c15: np.ndarray, lv: List[tuple]) -> List[tuple]:
    """(ts, kind, rejected, depth %) of each level's first test after it was known."""
    ts, h, l, c = c15[:, 0], c15[:, 2], c15[:, 3], c15[:, 4]
    out = []
    seen = set()
    for known, price, side, kind in lv:
        key = (kind, round(price, 10), side)
        if key in seen:
            continue
        seen.add(key)
        i0 = int(np.searchsorted(ts, known))
        if i0 >= len(ts):
            continue
        # the level must be on its side at the start (support below the close, resistance above)
        if side * (price - c[i0 - 1 if i0 else 0]) <= 0:
            continue
        beyond = (h[i0:] > price) if side > 0 else (l[i0:] < price)
        hit = np.flatnonzero(beyond)
        if not len(hit):
            continue
        i = i0 + int(hit[0])
        end = min(len(ts), i + RECLAIM)
        back = None
        for j in range(i, end):
            if (c[j] < price) if side > 0 else (c[j] > price):
                back = j
                break
        if back is None:
            out.append((ts[i], kind, False, None))
            continue
        ext = h[i:back + 1].max() if side > 0 else l[i:back + 1].min()
        out.append((ts[i], kind, True, abs(ext / price - 1) * 100))
    return out


def run_coin(job) -> Dict:
    symbol, start, end = job
    from history import Archive
    arch = Archive(rate_bytes=4e6)
    c15 = arch.klines_ohlc('futures', symbol, '15m', date.fromisoformat(start), date.fromisoformat(end))
    if len(c15) < 2000:
        return {'symbol': symbol, 'tests': []}
    return {'symbol': symbol, 'tests': tests_of(c15, levels_of(c15))}


def pct(xs, q):
    return float(np.percentile(xs, q)) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--months', type=int, default=12)
    ap.add_argument('--limit', type=int, default=80)
    ap.add_argument('--workers', type=int, default=1)
    ap.add_argument('--end', default=None)
    ap.add_argument('--min-volume', type=float, default=3e6)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-7s | %(message)s', datefmt='%H:%M:%S')
    from history import Archive
    from pretrain import select_coins
    end = date.fromisoformat(args.end) if args.end else datetime.now(timezone.utc).date().replace(day=1) - timedelta(days=1)
    start = end - timedelta(days=30 * args.months)
    coins = select_coins(Archive(rate_bytes=4e7), start, end, args.min_volume)[:args.limit]
    keys = {f: k for k, f, _, _ in coins}                 # futures id -> journal key (the live symbol)
    jobs = [(f, start.isoformat(), end.isoformat()) for _, f, _, _ in coins]
    results = []
    if args.workers > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(args.workers) as pool:
            for k, r in enumerate(pool.map(run_coin, jobs), 1):
                results.append(r)
                logging.info(f"overshoot: {k}/{len(jobs)} {r['symbol']} {len(r['tests'])} tests")
    else:
        for k, job in enumerate(jobs, 1):
            r = run_coin(job)
            results.append(r)
            logging.info(f"overshoot: {k}/{len(jobs)} {r['symbol']} {len(r['tests'])} tests")
    mid = (datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000 +
           datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000) / 2
    model = {'window': [start.isoformat(), end.isoformat()], 'global': {}, 'coins': {}}
    rows = []
    allk = defaultdict(list)
    halves = defaultdict(lambda: ([], []))
    breaks = defaultdict(lambda: [0, 0])
    for r in results:
        per = defaultdict(list)
        for ts, kind, rej, depth in r['tests']:
            breaks[kind][0] += 1
            breaks[kind][1] += 0 if rej else 1
            if rej:
                per[kind].append(depth)
                allk[kind].append(depth)
                halves[kind][0 if ts < mid else 1].append(depth)
        model['coins'][keys.get(r['symbol'], r['symbol'])] = {k: {'p50': pct(v, 50), 'p80': pct(v, 80), 'p90': pct(v, 90), 'n': len(v)}
                                       for k, v in per.items() if len(v) >= 20}
    for k in KINDS:
        v = allk[k]
        model['global'][k] = {'p50': pct(v, 50), 'p80': pct(v, 80), 'p90': pct(v, 90), 'n': len(v)}
        old, new = halves[k]
        p80_old = pct(old, 80)
        cover = float(np.mean(np.array(new) <= p80_old)) if old and new else None
        rows.append((k, len(v), breaks[k][1] / max(1, breaks[k][0]), pct(v, 50), pct(v, 80), pct(v, 90), p80_old, cover))
    os.makedirs('models', exist_ok=True)
    with open(os.path.join('models', 'overshoot.json'), 'w', encoding='utf-8') as f:
        json.dump(model, f, indent=1)
    lines = [f"# Level overshoot before a rejection ({len(results)} coins, {start} .. {end})", '',
             'Depth = how far beyond the level price traded before a 15m close back within 1h, % of the level. '
             'Coverage = share of the NEWER half\'s rejections within the OLDER half\'s p80 (80% = stable).', '',
             '| kind | rejections | break share | p50 | p80 | p90 | p80 older half | coverage newer half |',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for k, n, br, a, b, c, p, cov in rows:
        f = lambda x: '-' if x is None else f"{x:.3f}%"
        lines.append(f"| {k} | {n} | {br:.0%} | {f(a)} | {f(b)} | {f(c)} | {f(p)} | "
                     f"{'-' if cov is None else f'{cov:.0%}'} |")
    per_coin = [v.get('swing_15m', {}).get('p80') for v in model['coins'].values() if v.get('swing_15m')]
    if per_coin:
        lines += ['', f"Per coin p80 of swing_15m: min {min(per_coin):.3f}%, median {np.median(per_coin):.3f}%, "
                      f"max {max(per_coin):.3f}% ({len(per_coin)} coins): one buffer for all coins would be wrong."]
    os.makedirs('research', exist_ok=True)
    with open(os.path.join('research', 'overshoot.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
