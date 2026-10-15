"""
Do the price-action S/R zones of sr.py hold price better than placebo prices? (eng-75, pre-registered before the
briefing trusts them.)

Each UTC day, per coin: sr.zones from the 1h / 4h / daily candles BEFORE the day (the reactions too: no look-ahead),
tol 0.6 x the 1h ATR, max width 1.5 x (as the briefing); the zones within 3 daily ATR of the day's open close become
levels - a support's near edge (its top) below the price, a resistance's (its bottom) above it. Classes:
  sr        every zone                         sr_top / sr_bot   the day's strongest / weakest third
  sr_flip   swing highs AND lows (role reversal) sr_t3            >= 3 touches (pivots + rejections)
  sr_1d     holds a daily pivot
Each level and a PLACEBO at the same time and side shifted 0.3-1.5% go through research_overshoot.tests_of (the first
15m candle beyond it = a test, a 15m close back on its side within 1h = a REJECTION), and the rejection rates are
compared as in research_level_weights.py: odds ratio real / placebo with a 90% coin-bootstrap interval and halves.

Pre-registered reading: a class is a support / resistance of its own only if its odds ratio is > 1 with the 90%
interval above 1 in BOTH halves; otherwise the zones are descriptive (where price turned), not an edge.

    python research_sr.py --months 12 --limit 40 --workers 2
Writes research/sr_zones.md.
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import argparse
import logging
import math
import os
import random
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import numpy as np

import sr
from research_overshoot import tests_of

HOUR_MS = 3_600_000
DAY_MS = 86_400_000
CLASSES = ('sr', 'sr_top', 'sr_bot', 'sr_flip', 'sr_t3', 'sr_1d')


def bars(c: np.ndarray, period_ms: int) -> np.ndarray:
    """Candles of `period_ms` from shorter ones [ts, o, h, l, c, v] (complete periods only)."""
    key = (c[:, 0] // period_ms).astype(np.int64)
    starts = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
    step = c[1, 0] - c[0, 0] if len(c) > 1 else period_ms
    need = int(round(period_ms / step))
    rows = []
    for a, b in zip(starts, list(starts[1:]) + [len(c)]):
        if b - a == need:
            rows.append((key[a] * period_ms, c[a, 1], c[a:b, 2].max(), c[a:b, 3].min(), c[b - 1, 4], c[a:b, 5].sum()))
    return np.asarray(rows, dtype=float)


def atr_at(c: np.ndarray, i: int, n: int = 14) -> float:
    lo = max(1, i - n)
    tr = [max(c[k, 2] - c[k, 3], abs(c[k, 2] - c[k - 1, 4]), abs(c[k, 3] - c[k - 1, 4])) for k in range(lo, i)]
    return float(np.mean(tr)) if tr else float('nan')


def levels_of(c15: np.ndarray):
    h1, h4, d1 = bars(c15, HOUR_MS), bars(c15, 4 * HOUR_MS), bars(c15, DAY_MS)
    out = []
    first_day = int(d1[0, 0] // DAY_MS) + 125 if len(d1) else 0
    for day in range(first_day, int(c15[-1, 0] // DAY_MS)):
        t = day * DAY_MS
        i1 = int(np.searchsorted(h1[:, 0], t))
        id_ = int(np.searchsorted(d1[:, 0], t))
        if i1 < 30 or id_ < 20:
            continue
        a1, ad = atr_at(h1, i1), atr_at(d1, id_)
        if not (a1 > 0 and ad > 0):
            continue
        price = h1[i1 - 1, 4]
        cand = {'1h': h1[max(0, i1 - 24 * 12):i1].tolist(),
                '4h': h4[(h4[:, 0] >= t - 50 * DAY_MS) & (h4[:, 0] < t)].tolist(),
                '1d': d1[max(0, id_ - 125):id_].tolist()}
        zs = [z for z in sr.zones(cand, t, tol=0.6 * a1, max_width=1.5 * a1) if abs(z['price'] - price) <= 3 * ad]
        if not zs:
            continue
        ranked = sorted(zs, key=lambda z: z['strength'])
        third = max(1, len(ranked) // 3)
        bot, top = {id(z) for z in ranked[:third]}, {id(z) for z in ranked[-third:]}
        for z in zs:
            if z['hi'] < price:
                lvl, side = z['hi'], -1
            elif z['lo'] > price:
                lvl, side = z['lo'], 1
            else:
                continue                                        # the price is inside: no test from one side
            kinds = ['sr']
            kinds += ['sr_top'] if id(z) in top else []
            kinds += ['sr_bot'] if id(z) in bot else []
            kinds += ['sr_flip'] if z['flip'] else []
            kinds += ['sr_t3'] if z['touches'] >= 3 else []
            kinds += ['sr_1d'] if '1d' in z['tfs'] else []
            out += [(t, lvl, side, k) for k in kinds]
    return out


def placebo_of(levels, seed: int):
    rnd = random.Random(seed)
    return [(known, price * (1 + rnd.uniform(0.003, 0.015) * rnd.choice((-1, 1))), side, kind)
            for known, price, side, kind in levels]


def run_coin(job):
    symbol, start, end = job
    from history import Archive
    c15 = Archive(rate_bytes=4e6).klines_ohlc('futures', symbol, '15m', date.fromisoformat(start),
                                              date.fromisoformat(end))
    if len(c15) < 10000:
        return {'symbol': symbol, 'real': [], 'placebo': []}
    lv = sorted(levels_of(c15))
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
    ap.add_argument('--limit', type=int, default=40)
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
                logging.info(f"sr zones: {k}/{len(jobs)} {r['symbol']} {len(r['real'])} tests")
    else:
        for k, job in enumerate(jobs, 1):
            results.append(run_coin(job))
            logging.info(f"sr zones: {k}/{len(jobs)} {results[-1]['symbol']} {len(results[-1]['real'])} tests")
    mid = (datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp() +
           datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc).timestamp()) * 500
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
        return (rej / n if n else None), n

    def ci(kind, half):
        boots = []
        for _ in range(500):
            picks = list(rng.choice(symbols, len(symbols)))
            a, _ = rate(kind, 'real', half, picks)
            b, _ = rate(kind, 'placebo', half, picks)
            if a is not None and b is not None:
                boots.append(odds(a) / odds(b))
        return (float(np.percentile(boots, 5)), float(np.percentile(boots, 95))) if boots else (None, None)

    f = lambda x: '-' if x is None else f"{x:.2f}"          # noqa: E731
    lines = [f"# Price-action S/R zones (sr.py) vs placebo prices ({len(results)} coins, {start} .. {end})", '',
             'Rejection = a 15m close back on the level\'s side within 1h of the first candle beyond it. Placebo = the '
             'same level shifted 0.3-1.5% (same side, same time). OR = odds ratio real / placebo; [90%] by coin '
             'bootstrap. Pre-registered: a class holds price only if OR > 1 with the interval above 1 in both halves.',
             '', '| class | tests | rejected | placebo | OR [90%] | older [90%] | newer [90%] | verdict |',
             '|---|---:|---:|---:|---|---|---|---|']
    for kind in CLASSES:
        pr, n = rate(kind, 'real', 'all', symbols)
        pp, npl = rate(kind, 'placebo', 'all', symbols)
        if not n or pr is None or pp is None:
            continue
        orr = odds(pr) / odds(pp)
        lo, hi = ci(kind, 'all')
        halves = []
        for half in ('old', 'new'):
            a, _ = rate(kind, 'real', half, symbols)
            b, _ = rate(kind, 'placebo', half, symbols)
            halves.append((odds(a) / odds(b) if a is not None and b is not None else None, ci(kind, half)))
        ok = all(h[0] is not None and h[1][0] is not None and h[1][0] > 1 for h in halves)
        lines.append(f"| {kind} | {n} | {pr:.1%} | {pp:.1%} | {orr:.2f} [{f(lo)}..{f(hi)}] | "
                     f"{f(halves[0][0])} [{f(halves[0][1][0])}..{f(halves[0][1][1])}] | "
                     f"{f(halves[1][0])} [{f(halves[1][1][0])}..{f(halves[1][1][1])}] | "
                     f"{'holds' if ok else 'descriptive'} |")
        _ = math
    os.makedirs('research', exist_ok=True)
    with open(os.path.join('research', 'sr_zones.md'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
