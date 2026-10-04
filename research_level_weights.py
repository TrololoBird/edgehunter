"""
Do level kinds hold price better than random prices nearby? The data behind the map's source weights
(CONFIG.zones.weights were set by hand in the first commit; eng-57 audit).

For every level of research_overshoot.levels_of (swing_15m, swing_1h, equal, pdhl, round) a PLACEBO level is drawn at
the same known time, on the same side of price, shifted by a random 0.3-1.5% of the level (seeded per coin). Both get
research_overshoot.tests_of: the first 15m candle beyond the level is a test, a 15m close back within 1h is a
REJECTION. Per kind: rejection rate of the real levels vs their placebos, the odds ratio, and a 90% interval by
bootstrapping coins (a coin's tests ride one market). Halves (older / newer) for stability.

A kind whose odds ratio stays ~1 holds price no better than any price: a weight above the placebo's has no support.

    python research_level_weights.py --months 12 --limit 60 --workers 2
Writes research/level_weights.md and models/level_weights.json.
"""
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
    lv = levels_of(c15)
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
    for kind in KINDS:
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
