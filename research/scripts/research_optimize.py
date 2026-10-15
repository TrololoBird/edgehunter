"""
Strategy optimization on the archive replay (2026-10-05, the owner's task: take the classic methods, adapt them to
crypto futures by searching filters, timeframes, coins, position management and risk, bring them to a positive
expectancy, then test them on the demo).

Data: every replayed entry of research/replay_summary.parquet (10 strategies, 40 coins, 12 months, vetoed entries
included) with its plan (entry, stop, targets); the archive's 5m candles after each entry (research_fetch5m.py), the
1h candles for the indicator panel and ATR (strategies/ind_panel.py, the live journal's `_ind`).

Search space, per strategy:
- position management (PM): target (1 / 1.5 / 2 / 3 R, the plan's TP1, or none), stop to breakeven after +1R, an ATR
  chandelier trail after +1R (2 / 3 x 1h ATR), half off at +1R, time stop (4 / 12 / 24 / 72h), the stop 1.0 / 1.5 x
  the plan's distance. Costs: 0.05% taker fee a side + slippage by the coin's 24h volume (levels.slippage_bps) a side.
- filters (none, one, or a pair): the 40 indicator rules (15m / 1h), coin class by 24h volume, session, weekend,
  BTC's 1h trend with / against the trade, the coin's volatility rank, the bot's own veto passed.

Overfitting guard (how the found profiles can survive the demo): selection on the first 8 months only, ranked by the
lower 90% bound of the mean R over 4h clusters (a small lucky sample cannot win), with >= MIN_CLUSTERS clusters and
>= MIN_PER_MONTH trades a month; the chosen profile is then evaluated ONCE on the last 4 months. Only profiles
positive there go to the demo (research/optimize.md lists every strategy's best, positive or not).
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import argparse
import os
import itertools
import logging
import math
from datetime import date, datetime, timezone

import numpy as np
import polars as pl

from history import Archive
from strategies.ind_panel import indicators, rules

log = logging.getLogger('optimize')
HOUR = 3_600_000
BLOCK = 4 * HOUR
FEE = 0.0005
MAX_BARS = 72 * 12                 # 72h of 5m bars
MIN_CLUSTERS = 30
MIN_PER_MONTH = 4
TRAIN_MONTHS = int(os.environ.get('OPT_TRAIN_MONTHS', 8))   # 16 for a 24-month replay (docs/CLOUD_OPTIMIZE.md)

TARGETS = ('1', '1.5', '2', '3', 'plan', 'none')
PM = [dict(target=t, be=be, trail=tr, half=h, hours=hr, stop=sm)
      for t in TARGETS for be in (False, True) for tr in (0, 2, 3) for h in (False, True)
      for hr in (4, 12, 24, 72) for sm in (1.0, 1.5)
      if not (t == 'none' and tr == 0 and hr == 72 and not be)          # no exit at all but the clock is kept
      and not (h and t in ('1',))]                                          # half at 1R with a 1R target = 1R target


def slippage(volume_24h: float) -> float:
    if not volume_24h or volume_24h <= 0:
        return 0.0025
    return min(0.0025, 0.0005 * math.sqrt(5e8 / max(volume_24h, 1.0))) if volume_24h < 5e8 else 0.0005


def simulate(path: np.ndarray, d: int, entry: float, stop0: float, tp_plan: float, atr: float, pm: dict,
             cost_r: float) -> float:
    """R of one trade under one PM over `path` ([open, high, low, close] 5m bars after the entry)."""
    risk = abs(entry - stop0) * pm['stop']
    if risk <= 0:
        return 0.0
    n = min(len(path), pm['hours'] * 12)
    if n == 0:
        return -cost_r
    o, h, l, c = path[:n, 0], path[:n, 1], path[:n, 2], path[:n, 3]
    fav = (h - entry) * d / risk if d > 0 else (entry - l) / risk          # best excursion of each bar, in R
    adv = (l - entry) / risk if d > 0 else (entry - h) / risk               # worst excursion of each bar, in R
    t = pm['target']
    target_r = {'1': 1.0, '1.5': 1.5, '2': 2.0, '3': 3.0}.get(t)
    if t == 'plan' and tp_plan and (tp_plan - entry) * d > 0:
        target_r = (tp_plan - entry) * d / risk
    # the dynamic stop in R, per bar (set after the bar that triggered the move, used from the next bar on)
    stop_r = np.full(n, -1.0)
    run = np.maximum.accumulate(fav)
    armed = np.concatenate(([False], run[:-1] >= 1.0))                      # +1R reached on an earlier bar
    if pm['be']:
        stop_r = np.where(armed, np.maximum(stop_r, 0.0), stop_r)
    if pm['trail'] and atr > 0:
        best_price_r = np.concatenate(([0.0], run[:-1]))
        trail = best_price_r - pm['trail'] * atr / risk
        stop_r = np.where(armed, np.maximum(stop_r, trail), stop_r)
    hit_stop = adv <= stop_r
    hit_tgt = fav >= target_r if target_r is not None else np.zeros(n, bool)
    i_s = int(np.argmax(hit_stop)) if hit_stop.any() else n
    i_t = int(np.argmax(hit_tgt)) if hit_tgt.any() else n
    half_r = None
    if pm['half']:
        # half off at +1R only when +1R traded on a bar strictly before the stop's bar (a bar touching both: the
        # stop first)
        hit_half = fav >= 1.0
        i_half = int(np.argmax(hit_half)) if hit_half.any() else n
        if i_half < n and i_half < i_s:
            half_r = 1.0
    if i_s < n and i_s <= i_t:                         # a bar touching both: the stop first (conservative)
        # a gap through the stop fills at the open
        level = stop_r[i_s]
        open_r = (o[i_s] - entry) * d / risk
        rest = min(level, open_r)
    elif i_t < n:
        rest = target_r
    else:
        rest = (c[n - 1] - entry) * d / risk           # time stop at the last bar's close
    r = 0.5 * half_r + 0.5 * rest if half_r is not None else rest
    return r - cost_r


def cluster_stats(r: np.ndarray, cl: np.ndarray):
    """Mean R and its lower 90% bound with 4h clusters as the independent units."""
    if len(r) == 0:
        return np.nan, np.nan, 0
    uniq, inv = np.unique(cl, return_inverse=True)
    s = np.bincount(inv, weights=r)
    k = np.bincount(inv)
    m = s.sum() / k.sum()
    resid = s - m * k
    se = math.sqrt((resid ** 2).sum()) / k.sum() if len(uniq) > 1 else float('inf')
    return m, m - 1.645 * se, len(uniq)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--rate', type=float, default=300_000)
    p.add_argument('--out', default='research/optimize')
    p.add_argument('--strategies', default='')
    p.add_argument('--replay', default='research/replay_summary.parquet', help='replay entries (replay.py output)')
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', datefmt='%H:%M:%S')
    arch = Archive(rate_bytes=args.rate)

    ent = (pl.read_parquet(args.replay)
           .filter(pl.col('r_tp1').is_not_null() & pl.col('entry').is_not_null() & pl.col('sl').is_not_null())
           .sort('ts'))
    if args.strategies:
        ent = ent.filter(pl.col('strategy').is_in(args.strategies.split(',')))
    t0, t1 = ent['ts'].min(), ent['ts'].max()
    first, last = (datetime.fromtimestamp(x / 1000, timezone.utc).date() for x in (t0, t1))
    start = date(first.year - (first.month <= 2), (first.month - 3) % 12 + 1, 1)
    split_ms = int(datetime(first.year + (first.month - 1 + TRAIN_MONTHS) // 12, (first.month - 1 + TRAIN_MONTHS) % 12 + 1, 1,
                            tzinfo=timezone.utc).timestamp() * 1000)

    # BTC's 1h trend for the regime filter
    btc = arch.klines_ohlc('futures', 'BTCUSDT', '1h', start, last)
    btc_ind = indicators(btc)
    btc_close_ms = btc[:, 0] + HOUR

    pm_n = len(PM)
    rows_r, meta, masks = [], [], []
    mask_names = None
    for sym in ent['symbol'].unique().sort().to_list():
        code = sym.split(':')[0].replace('/', '')
        part = ent.filter(pl.col('symbol') == sym)
        k5 = arch.klines_ohlc('futures', code, '5m', date(first.year, first.month, 1), last)
        k15 = arch.klines_ohlc('futures', code, '15m', start, last)
        k1h = arch.klines_ohlc('futures', code, '1h', start, last)
        if len(k5) < 1000 or len(k1h) < 300:
            log.info(f"{sym}: no candles, skipped")
            continue
        ind = {'15m': (indicators(k15), k15[:, 0] + 15 * 60_000), '1h': (indicators(k1h), k1h[:, 0] + HOUR)}
        rule_cache = {(tf, d): rules(ind[tf][0], d) for tf in ind for d in (1, -1)}
        atr_1h = ind['1h'][0]['c'] * 0 + np.nan
        prev_c = np.concatenate(([k1h[0, 4]], k1h[:-1, 4]))
        tr = np.maximum(k1h[:, 2] - k1h[:, 3], np.maximum(abs(k1h[:, 2] - prev_c), abs(k1h[:, 3] - prev_c)))
        atr_1h = np.convolve(tr, np.ones(14) / 14, mode='full')[:len(tr)]
        open5 = k5[:, 0]
        for r in part.iter_rows(named=True):
            ts, d = r['ts'], int(r['direction'])
            i5 = int(np.searchsorted(open5, ts, side='right'))           # the first 5m bar opening after the signal
            path = k5[i5:i5 + MAX_BARS, 1:5]
            if len(path) < 12:
                continue
            j1 = int(np.searchsorted(ind['1h'][1], ts, side='right')) - 1
            if j1 < 250:
                continue
            atr = float(atr_1h[j1])
            cost_r = (2 * FEE + 2 * slippage(r.get('volume_24h') or 0.0)) * r['entry'] / abs(r['entry'] - r['sl'])
            rr = np.empty(pm_n)
            for q, pm in enumerate(PM):
                rr[q] = simulate(path, d, r['entry'], r['sl'], r.get('tp1') or 0.0, atr, pm,
                                 cost_r / pm['stop'])
            m = {}
            for tf in ('15m', '1h'):
                arr_ms = ind[tf][1]
                j = int(np.searchsorted(arr_ms, ts, side='right')) - 1
                for name, arr in rule_cache[(tf, d)].items():
                    m[f'{tf}:{name}'] = bool(arr[j]) if j >= 250 else False
            vol = r.get('volume_24h') or 0.0
            m['coin:major'] = vol >= 1e9
            m['coin:large'] = 2e8 <= vol < 1e9
            m['coin:mid'] = 5e7 <= vol < 2e8
            m['coin:small'] = vol < 5e7
            hour = datetime.fromtimestamp(ts / 1000, timezone.utc).hour
            m['session:asia'] = hour < 8
            m['session:europe'] = 8 <= hour < 13
            m['session:us'] = 13 <= hour < 21
            m['session:late'] = hour >= 21
            m['weekend'] = datetime.fromtimestamp(ts / 1000, timezone.utc).weekday() >= 5
            jb = int(np.searchsorted(btc_close_ms, ts, side='right')) - 1
            slope = btc_ind['e50'][jb] - btc_ind['e50'][jb - 10] if jb >= 260 else 0.0
            m['btc:with'] = d * slope > 0
            m['btc:against'] = d * slope < 0
            m['passed_veto'] = r['vetoed'] is None
            m['atr:high'] = bool(ind['1h'][0]['atr_rank'][j1] > 0.5)
            if mask_names is None:
                mask_names = list(m)
            rows_r.append(rr)
            masks.append([m[k] for k in mask_names])
            meta.append((r['strategy'], ts, d, ts // BLOCK * 2 + (d > 0)))
        log.info(f"{sym}: {len(part)} entries, {len(rows_r)} simulated so far")

    R = np.asarray(rows_r)
    M = np.asarray(masks, dtype=bool)
    strat = np.array([x[0] for x in meta])
    tsv = np.array([x[1] for x in meta])
    clus = np.array([x[3] for x in meta])
    np.savez_compressed(args.out + '_matrix.npz', R=R, M=M, strat=strat, ts=tsv, clus=clus,
                        mask_names=np.array(mask_names), pm=np.array([str(p) for p in PM]))
    months_train = TRAIN_MONTHS
    months_val = max(1.0, (t1 - split_ms) / (30.4 * 86_400_000))
    lines = ['# Strategy optimization on the archive replay (research_optimize.py)', '',
             f'{len(R)} simulated entries, {pm_n} PM variants x filters (none / one / a pair of {len(mask_names)}); '
             f'selection < {datetime.fromtimestamp(split_ms / 1000, timezone.utc):%Y-%m-%d} <= validation.', '',
             '| strategy | profile (filters / PM) | train: trades, mean R [lower 90%] | validation: trades, mean R [lower 90%] | verdict |',
             '|---|---|---|---|---|']
    results = []
    for s in sorted(set(strat)):
        sel = strat == s
        train = sel & (tsv < split_ms)
        val = sel & (tsv >= split_ms)
        if train.sum() < 50:
            continue
        Rt, Mt, Ct = R[train], M[train], clus[train]
        best = None
        n_masks = M.shape[1]
        combos = [()] + [(i,) for i in range(n_masks)] + list(itertools.combinations(range(n_masks), 2))
        for combo in combos:
            mk = np.ones(len(Rt), bool)
            for i in combo:
                mk &= Mt[:, i]
            if mk.sum() < MIN_PER_MONTH * months_train:
                continue
            sub_c = Ct[mk]
            if len(np.unique(sub_c)) < MIN_CLUSTERS:
                continue
            means = Rt[mk].mean(axis=0)
            q = int(np.argmax(means))
            m, lo, ncl = cluster_stats(Rt[mk][:, q], sub_c)
            if best is None or lo > best[0]:
                best = (lo, m, combo, q, int(mk.sum()), ncl)
        if best is None:
            continue
        lo, m, combo, q, n_tr, _ = best
        mk_v = np.ones(val.sum(), bool)
        for i in combo:
            mk_v &= M[val][:, i]
        mv, lov, _ = cluster_stats(R[val][mk_v][:, q], clus[val][mk_v])
        verdict = 'DEMO' if mv > 0 else 'no'
        name = ' & '.join(mask_names[i] for i in combo) or 'all'
        results.append(dict(strategy=s, filters=name, pm=str(PM[q]), train_n=n_tr, train_mean=m, train_lo=lo,
                            val_n=int(mk_v.sum()), val_mean=mv, val_lo=lov, verdict=verdict))
        lines.append(f"| {s} | {name} / {PM[q]} | {n_tr}, {m:+.3f} [{lo:+.3f}] | {int(mk_v.sum())}, {mv:+.3f} "
                     f"[{lov:+.3f}] | {verdict} |")
    pl.DataFrame(results).write_parquet(args.out + '.parquet') if results else None
    lines += ['', f'Validation span: {months_val:.1f} months. DEMO = positive mean R on the untouched months.']
    with open(args.out + '.md', 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
