"""
Do level kinds hold price better than random prices nearby? The data behind the map's source weights
(CONFIG.zones.weights were set by hand in the first commit; eng-57 audit).

Levels: research_overshoot.levels_of (swing_15m, swing_1h, equal, pdhl, round), plus ICT zones and the day's volume
profile, each known only from the candle that confirms it (eng-57 extension):
  fvg_15m / fvg_1h  a fair value gap (gap >= 0.1 of the middle candle, as zones.imbalances), known at the third
                    candle's close; the level = its near edge (a bullish gap's top is support)
  ob_1h             zones.imbalances' order block: the last opposite candle before a displacement that closed beyond
                    the last ICT 3-candle swing within 3 candles and left an FVG; known at the end of that window;
                    the level = its open (the near edge)
  breaker_1h        such an order block closed through its far side later: the level = that far side, flipped
  poc / va / hvn / lvn  zones.volume_profile of each UTC day's 15m candles, known at the day's close
For every level a PLACEBO level is drawn at
the same known time, on the same side of price, shifted by a random 0.3-1.5% of the level (seeded per coin). Both get
research_overshoot.tests_of: the first 15m candle beyond the level is a test, a 15m close back within 1h is a
REJECTION. Per kind: rejection rate of the real levels vs their placebos, the odds ratio, and a 90% interval by
bootstrapping coins (a coin's tests ride one market). Halves (older / newer) for stability.

A kind whose odds ratio stays ~1 holds price no better than any price: a weight above the placebo's has no support.

    python research_level_weights.py --months 12 --limit 60 --workers 2
Writes research/level_weights.md and models/level_weights.json.
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import argparse
import json
import logging
import math
import os
import random
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Dict

import numpy as np

from research_overshoot import KINDS, levels_of, tests_of

HOUR_MS = 3_600_000
DAY_MS = 86_400_000
EXTRA_KINDS = ('fvg_15m', 'fvg_1h', 'ob_1h', 'breaker_1h', 'poc', 'va', 'hvn', 'lvn')
ALL_KINDS = tuple(KINDS) + EXTRA_KINDS


def hourly(c15: np.ndarray) -> np.ndarray:
    """Complete 1h candles [ts, o, h, l, c, v] from 15m ones."""
    ts = c15[:, 0]
    hour = (ts // HOUR_MS).astype(np.int64)
    starts = np.flatnonzero(np.r_[True, hour[1:] != hour[:-1]])
    rows = []
    for a, b in zip(starts, list(starts[1:]) + [len(ts)]):
        if b - a == 4:
            rows.append((ts[a], c15[a, 1], c15[a:b, 2].max(), c15[a:b, 3].min(), c15[b - 1, 4], c15[a:b, 5].sum()))
    return np.asarray(rows, dtype=float)


def fvg_levels(c: np.ndarray, tf_ms: int, kind: str):
    ts, h, l = c[:, 0], c[:, 2], c[:, 3]
    out = []
    for i in range(2, len(c)):
        min_gap = 0.1 * (h[i - 1] - l[i - 1])
        if h[i - 2] < l[i] and l[i] - h[i - 2] >= min_gap:
            out.append((ts[i] + tf_ms, l[i], -1, kind))           # bullish gap: its top is support
        elif l[i - 2] > h[i] and l[i - 2] - h[i] >= min_gap:
            out.append((ts[i] + tf_ms, h[i], 1, kind))            # bearish gap: its bottom is resistance
    return out


def ob_levels(c: np.ndarray, tf_ms: int):
    """zones.imbalances' order blocks / breakers as events in time (same rules, ICT 3-candle swings)."""
    ts, o, h, l, cl = c[:, 0], c[:, 1], c[:, 2], c[:, 3], c[:, 4]
    n = len(c)
    last_hi, last_lo = [None] * n, [None] * n
    hi_p = lo_p = None
    for j in range(n):
        k = j - 1
        if k >= 1:
            if h[k] > max(h[k - 1], h[k + 1]):
                hi_p = h[k]
            if l[k] < min(l[k - 1], l[k + 1]):
                lo_p = l[k]
        last_hi[j], last_lo[j] = hi_p, lo_p
    out = []
    for j in range(10, n - 3):
        nxt = range(j + 1, j + 4)
        if cl[j] < o[j] and last_hi[j] is not None:
            broke = any(cl[k] > last_hi[j] for k in nxt)
            gap = any(h[k - 2] < l[k] for k in range(j + 2, j + 4))
            if broke and gap:
                out.append((ts[j + 3] + tf_ms, o[j], -1, 'ob_1h'))
                below = np.flatnonzero(cl[j + 4:] < l[j])
                if len(below):
                    b = j + 4 + int(below[0])
                    out.append((ts[b] + tf_ms, l[j], 1, 'breaker_1h'))
        elif cl[j] > o[j] and last_lo[j] is not None:
            broke = any(cl[k] < last_lo[j] for k in nxt)
            gap = any(l[k - 2] > h[k] for k in range(j + 2, j + 4))
            if broke and gap:
                out.append((ts[j + 3] + tf_ms, o[j], 1, 'ob_1h'))
                above = np.flatnonzero(cl[j + 4:] > h[j])
                if len(above):
                    b = j + 4 + int(above[0])
                    out.append((ts[b] + tf_ms, h[j], -1, 'breaker_1h'))
    return out


def profile_levels(c15: np.ndarray):
    """The day's volume profile (zones.volume_profile on its 15m candles), known at the UTC day's close."""
    from zones import volume_profile
    ts = c15[:, 0]
    day = (ts // DAY_MS).astype(np.int64)
    tr = np.maximum(c15[1:, 2] - c15[1:, 3], np.maximum(abs(c15[1:, 2] - c15[:-1, 4]), abs(c15[1:, 3] - c15[:-1, 4])))
    out = []
    for d in np.unique(day)[:-1]:
        idx = np.flatnonzero(day == d)
        if len(idx) < 90:
            continue
        atr = float(tr[max(0, idx[-1] - 14):idx[-1]].mean()) if idx[-1] > 14 else None
        if not atr:
            continue
        close = c15[idx[-1], 4]
        for lv in volume_profile(c15[idx].tolist(), atr, '24h'):
            kind = lv.kind if lv.kind in ('poc', 'va', 'hvn', 'lvn') else None
            if kind:
                out.append(((d + 1) * DAY_MS, lv.price, 1 if lv.price > close else -1, kind))
    return out


def all_levels(c15: np.ndarray):
    h1 = hourly(c15)
    return (levels_of(c15) + fvg_levels(c15, 900_000, 'fvg_15m') + fvg_levels(h1, HOUR_MS, 'fvg_1h') +
            ob_levels(h1, HOUR_MS) + profile_levels(c15))


def placebo_of(levels, seed: int):
    rnd = random.Random(seed)
    out = []
    for known, price, side, kind in levels:
        shift = rnd.uniform(0.003, 0.015) * rnd.choice((-1, 1))
        out.append((known, price * (1 + shift), side, kind))
    return out


def run_coin(job) -> Dict:
    symbol, start, end = job
    from history import Archive
    arch = Archive(rate_bytes=4e6)
    c15 = arch.klines_ohlc('futures', symbol, '15m', date.fromisoformat(start), date.fromisoformat(end))
    if len(c15) < 2000:
        return {'symbol': symbol, 'real': [], 'placebo': []}
    lv = sorted(all_levels(c15))
    seed = sum(map(ord, symbol))
    real = [(ts, k, rej) for ts, k, rej, _ in tests_of(c15, lv)]
    fake = [(ts, k, rej) for ts, k, rej, _ in tests_of(c15, placebo_of(lv, seed))]
    return {'symbol': symbol, 'real': real, 'placebo': fake}


def odds(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return p / (1 - p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--months', type=int, default=12)
    ap.add_argument('--limit', type=int, default=60)
    ap.add_argument('--workers', type=int, default=1)
    ap.add_argument('--min-volume', type=float, default=3e6)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-7s | %(message)s', datefmt='%H:%M:%S')
    from history import Archive
    from pretrain import select_coins
    end = datetime.now(timezone.utc).date().replace(day=1) - timedelta(days=1)
    start = end - timedelta(days=30 * args.months)
    coins = select_coins(Archive(rate_bytes=4e7), start, end, args.min_volume)[:args.limit]
    jobs = [(f, start.isoformat(), end.isoformat()) for _, f, _, _ in coins]
    results = []
    if args.workers > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(args.workers) as pool:
            for k, r in enumerate(pool.map(run_coin, jobs), 1):
                results.append(r)
                logging.info(f"level weights: {k}/{len(jobs)} {r['symbol']} {len(r['real'])} tests")
    else:
        for k, job in enumerate(jobs, 1):
            results.append(run_coin(job))
            logging.info(f"level weights: {k}/{len(jobs)} {results[-1]['symbol']} {len(results[-1]['real'])} tests")
    mid = (datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp() +
           datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc).timestamp()) * 500
    # per coin x kind x (real / placebo) x half: [rejections, tests]
    cnt = defaultdict(lambda: [0, 0])
    for r in results:
        for which in ('real', 'placebo'):
            for ts, k, rej in r[which]:
                for half in ('all', 'old' if ts < mid else 'new'):
                    c = cnt[(r['symbol'], k, which, half)]
                    c[0] += int(rej)
                    c[1] += 1
    symbols = [r['symbol'] for r in results]
    rng = np.random.default_rng(7)

    def rate(kind, which, half, picks):
        rej = sum(cnt[(s, kind, which, half)][0] for s in picks)
        n = sum(cnt[(s, kind, which, half)][1] for s in picks)
        return rej / n if n else None, n

    lines = [f"# Do level kinds hold better than random prices nearby? ({len(results)} coins, {start} .. {end})", '',
             'Rejection = a 15m close back on the level\'s side within 1h of the first candle beyond it. Placebo = the '
             'same level shifted 0.3-1.5% (same side, same time). OR = odds ratio real / placebo; [90%] by coin '
             'bootstrap. OR ~1: the kind holds no better than any price.', '',
             '| kind | tests | rejected | placebo rejected | OR [90%] | OR older half | OR newer half |',
             '|---|---:|---:|---:|---|---:|---:|']
    model = {'window': [start.isoformat(), end.isoformat()], 'kinds': {}}
    for kind in ALL_KINDS:
        pr, n = rate(kind, 'real', 'all', symbols)
        pp, npl = rate(kind, 'placebo', 'all', symbols)
        if not n or not npl or pr is None or pp is None:
            continue
        orr = odds(pr) / odds(pp)
        boots = []
        for _ in range(500):
            picks = list(rng.choice(symbols, len(symbols)))
            a, _ = rate(kind, 'real', 'all', picks)
            b, _ = rate(kind, 'placebo', 'all', picks)
            if a is not None and b is not None:
                boots.append(odds(a) / odds(b))
        lo, hi = (float(np.percentile(boots, 5)), float(np.percentile(boots, 95))) if boots else (None, None)
        halves = []
        for half in ('old', 'new'):
            a, _ = rate(kind, 'real', half, symbols)
            b, _ = rate(kind, 'placebo', half, symbols)
            halves.append(odds(a) / odds(b) if a is not None and b is not None else None)
        model['kinds'][kind] = {'tests': n, 'rejected': pr, 'placebo_rejected': pp, 'odds_ratio': orr,
                                'or_lo': lo, 'or_hi': hi, 'or_old': halves[0], 'or_new': halves[1],
                                'log_or': math.log(orr)}
        f = lambda x: '-' if x is None else f"{x:.2f}"
        lines.append(f"| {kind} | {n} | {pr:.1%} | {pp:.1%} | {orr:.2f} [{f(lo)}..{f(hi)}] | {f(halves[0])} | "
                     f"{f(halves[1])} |")
    os.makedirs('models', exist_ok=True)
    with open(os.path.join('models', 'level_weights.json'), 'w', encoding='utf-8') as fh:
        json.dump(model, fh, indent=1)
    os.makedirs('research', exist_ok=True)
    with open(os.path.join('research', 'level_weights.md'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
