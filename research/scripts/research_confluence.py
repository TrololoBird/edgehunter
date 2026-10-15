"""
Does confluence hold price? The data behind zones.min_strength (a target zone needs >= 2.5 of summed source weights;
with the measured kinds at weight 1 that is ~3 coinciding sources). eng-57 audit, after research_level_weights.py
found no single level kind holding price better than a placebo.

Levels: research_level_weights.all_levels (swings, equal, previous day, round, FVG 15m / 1h, order blocks, breakers,
the day's volume profile), each known only from its confirming candle. A level's CONFLUENCE at its first test = the
number of distinct kinds among the levels ALIVE at that moment - known in the 7 days before and not yet tested
(the map keeps only intact levels; itself included) - within TOL of its price (TOL = 0.25%: the measured p50 pierce of a swing / equal level, research/overshoot.md - the zones' merge gap).
Placebo levels (0.3-1.5% away, same side and time) get the same count of the REAL levels around them, so both sides
are compared at equal confluence. Rejection = a 15m close back within 1h of the first candle beyond (tests_of).

If real levels with 3+ coinciding kinds reject no more often than placebo prices with 3+ real kinds around them, a
confluence threshold carries no information.

    python research_confluence.py --months 12 --limit 60 --workers 2
Writes research/confluence.md.
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import argparse
import logging
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Dict

import numpy as np

from research_level_weights import all_levels, odds, placebo_of
from research_overshoot import RECLAIM

TOL = 0.0025
WINDOW_MS = 7 * 86_400_000
BUCKETS = ('1', '2', '3', '4+')


def first_tests(c15: np.ndarray, levels):
    """(ts, price, kind, rejected, level index) of each level's first test after it was known (as tests_of)."""
    ts, h, l, c = c15[:, 0], c15[:, 2], c15[:, 3], c15[:, 4]
    out, seen = [], set()
    for idx, (known, price, side, kind) in enumerate(levels):
        key = (kind, round(price, 10), side)
        if key in seen:
            continue
        seen.add(key)
        i0 = int(np.searchsorted(ts, known))
        if i0 >= len(ts) or side * (price - c[i0 - 1 if i0 else 0]) <= 0:
            continue
        hit = np.flatnonzero((h[i0:] > price) if side > 0 else (l[i0:] < price))
        if not len(hit):
            continue
        i = i0 + int(hit[0])
        back = any(((c[j] < price) if side > 0 else (c[j] > price)) for j in range(i, min(len(ts), i + RECLAIM)))
        out.append((ts[i], price, kind, back, idx))
    return out


def confluence(tests, levels, tested_at):
    """Distinct kinds of REAL levels alive at each test (known within WINDOW_MS before, first test not before it)
    within TOL of its price. `tested_at`: each real level's first-test time (inf = never tested)."""
    lk = np.array([x[0] for x in levels])
    lp = np.array([x[1] for x in levels])
    kinds = sorted({x[3] for x in levels})
    kid = np.array([kinds.index(x[3]) for x in levels])
    out = []
    for t, price, kind, rej, _ in tests:
        m = (lk <= t) & (lk >= t - WINDOW_MS) & (tested_at >= t) & (np.abs(lp / price - 1) <= TOL)
        n = len(np.unique(kid[m]))
        out.append((t, kind, rej, max(1, n)))
    return out


def bucket(n: int) -> str:
    return '4+' if n >= 4 else str(n)


def run_coin(job) -> Dict:
    symbol, start, end = job
    from history import Archive
    c15 = Archive(rate_bytes=4e6).klines_ohlc('futures', symbol, '15m', date.fromisoformat(start), date.fromisoformat(end))
    if len(c15) < 2000:
        return {'symbol': symbol, 'real': [], 'placebo': []}
    lv = sorted(all_levels(c15))
    fake = sorted(placebo_of(lv, sum(map(ord, symbol))))
    real = first_tests(c15, lv)
    tested_at = np.full(len(lv), np.inf)
    for t, _, _, _, idx in real:
        tested_at[idx] = t
    return {'symbol': symbol, 'real': confluence(real, lv, tested_at),
            'placebo': confluence(first_tests(c15, fake), lv, tested_at)}


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
                logging.info(f"confluence: {k}/{len(jobs)} {r['symbol']} {len(r['real'])} tests")
    else:
        for k, job in enumerate(jobs, 1):
            results.append(run_coin(job))
            logging.info(f"confluence: {k}/{len(jobs)} {results[-1]['symbol']} {len(results[-1]['real'])} tests")
    mid = (datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp() +
           datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc).timestamp()) * 500
    cnt = defaultdict(lambda: [0, 0])
    for r in results:
        for which in ('real', 'placebo'):
            for t, kind, rej, n in r[which]:
                for half in ('all', 'old' if t < mid else 'new'):
                    c = cnt[(r['symbol'], bucket(n), which, half)]
                    c[0] += int(rej)
                    c[1] += 1
    symbols = [r['symbol'] for r in results]
    rng = np.random.default_rng(7)

    def rate(b, which, half, picks):
        rej = sum(cnt[(s, b, which, half)][0] for s in picks)
        n = sum(cnt[(s, b, which, half)][1] for s in picks)
        return (rej / n if n else None), n

    lines = [f"# Does confluence hold price? ({len(results)} coins, {start} .. {end})", '',
             f"Confluence = distinct kinds of ALIVE levels (known in the last 7 days, not yet tested) within {TOL:.2%} of the price. "
             'Placebo prices (0.3-1.5% from a real level) are counted against the same REAL levels, so each row compares '
             'equal confluence. Rejection = a 15m close back within 1h. OR = odds real / placebo, [90%] coin bootstrap.', '',
             '| kinds together | real tests | real rejected | placebo tests | placebo rejected | OR [90%] | OR older | OR newer |',
             '|---|---:|---:|---:|---:|---|---:|---:|']
    for b in BUCKETS:
        pr, n = rate(b, 'real', 'all', symbols)
        pp, npl = rate(b, 'placebo', 'all', symbols)
        if not n or not npl:
            continue
        orr = odds(pr) / odds(pp)
        boots = []
        for _ in range(500):
            picks = list(rng.choice(symbols, len(symbols)))
            a, _ = rate(b, 'real', 'all', picks)
            c, _ = rate(b, 'placebo', 'all', picks)
            if a is not None and c is not None:
                boots.append(odds(a) / odds(c))
        halves = []
        for half in ('old', 'new'):
            a, _ = rate(b, 'real', half, symbols)
            c, _ = rate(b, 'placebo', half, symbols)
            halves.append(f"{odds(a) / odds(c):.2f}" if a is not None and c is not None else '-')
        lo, hi = np.percentile(boots, 5), np.percentile(boots, 95)
        lines.append(f"| {b} | {n} | {pr:.1%} | {npl} | {pp:.1%} | {orr:.2f} [{lo:.2f}..{hi:.2f}] | {halves[0]} | "
                     f"{halves[1]} |")
    os.makedirs('research', exist_ok=True)
    with open(os.path.join('research', 'confluence.md'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
