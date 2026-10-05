"""
What price DOES at a level, by mechanic, against placebo levels (eng-57 audit; research_level_weights.py only asked
"closed back within 1h or not", which lumps a bounce in front of the level, a wick-only false breakout, a one-close
false breakout and a breakout that came back - and misses a reversal that never touched the level at all).

Levels: research_level_weights.all_levels (swings, equal, previous day, round, FVG 15m / 1h, order blocks, breakers,
the day's volume profile), each known only from its confirming candle; placebo levels 0.3-1.5% away (same side, time).

The FIRST APPROACH after a level is known (price having started more than BAND away on the level's own side): the
first 15m candle whose extreme comes within BAND = 0.25 x ATR(15m) of it. The mechanic, decided within K = 8 candles:
  front    approached but never traded beyond it (a bounce in front of the level)
  wick     traded beyond, no 15m close beyond (a wick-only false breakout / sweep)
  close1   one close beyond, then a close back (a one-close false breakout)
  failed   two consecutive closes beyond (acceptance), then a close back inside (a failed breakout)
  break    two consecutive closes beyond and no close back (a breakout)
The class is decided at a candle (the K-th one for front / wick / break, the close back for close1 / failed); the
natural trade enters at that close: a reversal (away from the level) for front / wick / close1 / failed, a
continuation (through it) for break. WIN = +1 ATR(15m) in the trade's direction before -1 ATR, within the level's
horizon H (15m levels 4h, 1h levels 12h, daily levels 24h); also the excursions (MFE / MAE in ATR) over H.
A driftless walk wins 50%: the placebo row shows what any price nearby does with the same mechanic.
break -> retest: after a breakout, price coming back within BAND of the level from the far side within H; it HOLDS
when no close goes back through within the next K candles (the polarity flip of classic TA).

    python research_level_mechanics.py --months 12 --limit 60 --workers 2
Writes research/level_mechanics.md.
"""
import argparse
import logging
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Dict

import numpy as np

from research_level_weights import all_levels, placebo_of

BAND_ATR = 0.25
K = 8
MAX_WAIT = 7 * 96                    # 7 days of 15m candles to the first approach
CLASSES = ('front', 'wick', 'close1', 'failed', 'break')
H_OF = {'swing_15m': 16, 'fvg_15m': 16,
        'swing_1h': 48, 'equal': 48, 'fvg_1h': 48, 'ob_1h': 48, 'breaker_1h': 48,
        'pdhl': 96, 'round': 96, 'poc': 96, 'va': 96, 'hvn': 96, 'lvn': 96}


def atr15(c15: np.ndarray) -> np.ndarray:
    h, l, c = c15[:, 2], c15[:, 3], c15[:, 4]
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.r_[c[0], c[:-1]]), np.abs(l - np.r_[c[0], c[:-1]])))
    return np.convolve(tr, np.ones(14) / 14, mode='full')[:len(tr)]


def first_passage(h, l, i, d, entry, step, H):
    """+1 if price reaches entry + d*step before entry - d*step within candles i+1 .. i+H, -1 the reverse, 0 neither."""
    up, dn = entry + d * step, entry - d * step
    for j in range(i + 1, min(len(h), i + 1 + H)):
        win = h[j] >= up if d > 0 else l[j] <= up
        loss = l[j] <= dn if d > 0 else h[j] >= dn
        if loss:
            return -1                     # both in one candle: the loss first (conservative)
        if win:
            return 1
    return 0


def mechanics(c15: np.ndarray, levels, atr: np.ndarray):
    """(ts, kind, class, win, mfe_atr, mae_atr, retest) per level's first approach."""
    ts, h, l, c = c15[:, 0], c15[:, 2], c15[:, 3], c15[:, 4]
    n = len(ts)
    out, seen = [], set()
    for known, price, side, kind in levels:
        key = (kind, round(price, 10), side)
        if key in seen:
            continue
        seen.add(key)
        i0 = int(np.searchsorted(ts, known))
        if i0 < 15 or i0 >= n - K - 2:
            continue
        a0 = atr[i0 - 1]
        if not a0 > 0:
            continue
        band = BAND_ATR * a0
        if side * (price - c[i0 - 1]) <= band:   # must start beyond the band, on the level's own side
            continue
        end = min(n, i0 + MAX_WAIT)
        near = (h[i0:end] >= price - band) if side > 0 else (l[i0:end] <= price + band)
        hit = np.flatnonzero(near)
        if not len(hit):
            continue
        i = i0 + int(hit[0])
        if i >= n - K - 2:
            continue
        a = atr[i - 1] if atr[i - 1] > 0 else a0
        beyond_px = lambda j: (h[j] > price) if side > 0 else (l[j] < price)          # noqa: E731
        close_beyond = lambda j: (c[j] > price) if side > 0 else (c[j] < price)       # noqa: E731
        win_end = min(n, i + K)
        touched = any(beyond_px(j) for j in range(i, win_end))
        cls, decided = None, None
        if not touched:
            cls, decided = 'front', win_end - 1
        else:
            first = next((j for j in range(i, win_end) if close_beyond(j)), None)
            if first is None:
                cls, decided = 'wick', win_end - 1
            elif first + 1 < n and close_beyond(first + 1):
                back = next((j for j in range(first + 2, min(n, first + 2 + K)) if not close_beyond(j)), None)
                if back is None:
                    cls, decided = 'break', min(n - 1, first + 1 + K)
                    accept = first + 1
                else:
                    cls, decided = 'failed', back
            else:
                cls, decided = 'close1', first + 1
        H = H_OF.get(kind, 48)
        if decided >= n - 2:
            continue
        d = side if cls == 'break' else -side         # resistance (+1): reversal = short (-1), breakout = long
        entry = c[decided]
        res = first_passage(h, l, decided, d, entry, a, H)
        seg = slice(decided + 1, min(n, decided + 1 + H))
        if d > 0:
            mfe, mae = (h[seg].max() - entry) / a, (entry - l[seg].min()) / a
        else:
            mfe, mae = (entry - l[seg].min()) / a, (h[seg].max() - entry) / a
        retest = None
        if cls == 'break':
            # back within the band from the far side, then no close through it again within K candles
            far = (l[accept + 1:min(n, accept + 1 + H)] <= price + band) if side > 0 else \
                  (h[accept + 1:min(n, accept + 1 + H)] >= price - band)
            rh = np.flatnonzero(far)
            if len(rh):
                r = accept + 1 + int(rh[0])
                holds = not any((c[j] < price) if side > 0 else (c[j] > price) for j in range(r, min(n, r + K)))
                retest = 'held' if holds else 'lost'
            else:
                retest = 'none'
        out.append((ts[i], kind, cls, res, float(mfe), float(mae), retest))
    return out


def run_coin(job) -> Dict:
    symbol, start, end = job
    from history import Archive
    c15 = Archive(rate_bytes=4e6).klines_ohlc('futures', symbol, '15m', date.fromisoformat(start), date.fromisoformat(end))
    if len(c15) < 2000:
        return {'symbol': symbol, 'real': [], 'placebo': []}
    atr = atr15(c15)
    lv = sorted(all_levels(c15))
    fake = sorted(placebo_of(lv, sum(map(ord, symbol))))
    return {'symbol': symbol, 'real': mechanics(c15, lv, atr), 'placebo': mechanics(c15, fake, atr)}


def group_of(kind: str) -> str:
    return {16: '15m levels', 48: '1h levels', 96: 'daily levels'}[H_OF.get(kind, 48)]


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
                logging.info(f"mechanics: {k}/{len(jobs)} {r['symbol']} {len(r['real'])} approaches")
    else:
        for k, job in enumerate(jobs, 1):
            results.append(run_coin(job))
            logging.info(f"mechanics: {k}/{len(jobs)} {results[-1]['symbol']} {len(results[-1]['real'])} approaches")
    mid = (datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp() +
           datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc).timestamp()) * 500
    # (symbol, scope, which, half, class) -> [approaches, wins, losses, mfe sum, mae sum]
    agg = defaultdict(lambda: [0, 0, 0, 0.0, 0.0])
    retests = defaultdict(lambda: defaultdict(int))
    for r in results:
        for which in ('real', 'placebo'):
            for t, kind, cls, res, mfe, mae, retest in r[which]:
                for scope in ('all', group_of(kind), kind):
                    for half in ('all', 'old' if t < mid else 'new'):
                        a = agg[(r['symbol'], scope, which, half, cls)]
                        a[0] += 1
                        a[1] += res > 0
                        a[2] += res < 0
                        a[3] += mfe
                        a[4] += mae
                if retest is not None:
                    retests[(group_of(kind), which)][retest] += 1
    symbols = [r['symbol'] for r in results]
    rng = np.random.default_rng(7)

    def tot(scope, which, half, cls, picks):
        s = [0, 0, 0, 0.0, 0.0]
        for sym in picks:
            a = agg.get((sym, scope, which, half, cls))
            if a:
                for i in range(5):
                    s[i] += a[i]
        return s

    def winrate(s):
        return s[1] / (s[1] + s[2]) if s[1] + s[2] else None

    def share(scope, which, half, cls, picks):
        n = sum(tot(scope, which, half, c, picks)[0] for c in CLASSES)
        return tot(scope, which, half, cls, picks)[0] / n if n else None

    lines = [f"# What price does at a level, by mechanic, vs placebo ({len(results)} coins, {start} .. {end})", '',
             f"First approach within {BAND_ATR} ATR(15m); mechanic decided within {K} 15m candles (see the script's "
             "docstring). Win = +1 ATR before -1 ATR in the natural direction (reversal for front / wick / close1 / "
             "failed, continuation for break) within the level's horizon (15m 4h, 1h 12h, daily 24h); 50% = a "
             "driftless walk. Placebo = levels 0.3-1.5% away. [90%] = coin bootstrap of real minus placebo.", '']
    for scope in ('all', '15m levels', '1h levels', 'daily levels'):
        lines += [f"## {scope}", '',
                  '| mechanic | share real / placebo | win real | win placebo | real - placebo [90%] | older / newer half | '
                  'MFE / MAE real (ATR) | MFE / MAE placebo |',
                  '|---|---|---:|---:|---|---|---|---|']
        for cls in CLASSES:
            sr, sp = tot(scope, 'real', 'all', cls, symbols), tot(scope, 'placebo', 'all', cls, symbols)
            wr, wp = winrate(sr), winrate(sp)
            if not sr[0] or not sp[0] or wr is None or wp is None:
                continue
            boots = []
            for _ in range(300):
                picks = list(rng.choice(symbols, len(symbols)))
                a, b = winrate(tot(scope, 'real', 'all', cls, picks)), winrate(tot(scope, 'placebo', 'all', cls, picks))
                if a is not None and b is not None:
                    boots.append(a - b)
            halves = []
            for half in ('old', 'new'):
                a = winrate(tot(scope, 'real', half, cls, symbols))
                b = winrate(tot(scope, 'placebo', half, cls, symbols))
                halves.append(f"{(a - b) * 100:+.1f}" if a is not None and b is not None else '-')
            lo, hi = np.percentile(boots, 5) * 100, np.percentile(boots, 95) * 100
            shr, shp = share(scope, 'real', 'all', cls, symbols), share(scope, 'placebo', 'all', cls, symbols)
            lines.append(f"| {cls} | {shr:.1%} / {shp:.1%} | {wr:.1%} | {wp:.1%} | {(wr - wp) * 100:+.1f} pp "
                         f"[{lo:+.1f}..{hi:+.1f}] | {halves[0]} / {halves[1]} pp | "
                         f"{sr[3] / sr[0]:.2f} / {sr[4] / sr[0]:.2f} | {sp[3] / sp[0]:.2f} / {sp[4] / sp[0]:.2f} |")
        lines.append('')
    lines += ['## Retest after a breakout (polarity flip): held / lost / no retest within the horizon', '',
              '| levels | real held | real lost | real none | placebo held | placebo lost | placebo none |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for g in ('15m levels', '1h levels', 'daily levels'):
        R, P = retests[(g, 'real')], retests[(g, 'placebo')]
        rn, pn = sum(R.values()) or 1, sum(P.values()) or 1
        lines.append(f"| {g} | {R['held'] / rn:.1%} | {R['lost'] / rn:.1%} | {R['none'] / rn:.1%} | "
                     f"{P['held'] / pn:.1%} | {P['lost'] / pn:.1%} | {P['none'] / pn:.1%} |")
    lines += ['', '## By kind: win real - placebo, pp (approaches)', '',
              '| kind | ' + ' | '.join(CLASSES) + ' |', '|---|' + '---:|' * len(CLASSES)]
    for kind in H_OF:
        cells = []
        for cls in CLASSES:
            sr, sp = tot(kind, 'real', 'all', cls, symbols), tot(kind, 'placebo', 'all', cls, symbols)
            wr, wp = winrate(sr), winrate(sp)
            cells.append(f"{(wr - wp) * 100:+.1f} ({sr[0]})" if wr is not None and wp is not None else '-')
        lines.append(f"| {kind} | " + ' | '.join(cells) + ' |')
    os.makedirs('research', exist_ok=True)
    with open(os.path.join('research', 'level_mechanics.md'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
