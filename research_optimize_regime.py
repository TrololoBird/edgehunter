"""
Regime switch for the optimized profiles (2026-10-05): continuation was positive in both halves of its 8 training
months (+1.1R) and lost -0.56R on the 4 validation months - a regime change, not chance. Here every strategy gets a
profile PER MARKET REGIME and trades only in the regimes where that profile held.

Regimes, fixed before the run (no tuning): BTC on 4h candles (from the archive's 1h), the last CLOSED 4h candle at the
entry - TREND when ADX(14) >= 25 else RANGE; HIGH volatility when ATR(14) is above its median of the last 125 4h
candles (~3 weeks) else LOW: trend_hv, trend_lv, range_hv, range_lv.

PRE-REGISTERED RULE: per strategy x regime, candidates = position management alone or with ONE filter (no pairs:
fewer degrees of freedom than research_optimize.py); a candidate qualifies when, on the training months, its mean R
is > 0 with a lower 90% cluster bound > 0 AND its mean is > 0 in each half of the training period, with >= 15 4h
clusters; the qualifying one with the highest lower bound is validated once on the last 4 months. ON = validation
mean R > 0. Output: research/optimize_regime.md, models/profiles_regime.json (the ON cells).
"""
import json
import os
from datetime import date, datetime, timezone

import numpy as np

from history import Archive
from research_optimize import PM, TRAIN_MONTHS, cluster_stats

HOUR = 3_600_000
PREFIX = os.environ.get('OPT_PREFIX', 'research/optimize')   # research_optimize.py --out
REGIMES = ('trend_hv', 'trend_lv', 'range_hv', 'range_lv')


def btc_regime_series(k1h: np.ndarray):
    """(close ms of each 4h candle, regime label of each) from BTC 1h candles [open_ms, o, h, l, c, v]."""
    size = 4 * HOUR
    bars = {}
    for r in k1h:
        b = int(r[0]) // size * size
        if b not in bars:
            bars[b] = [b, r[1], r[2], r[3], r[4]]
        else:
            x = bars[b]
            x[2], x[3], x[4] = max(x[2], r[2]), min(x[3], r[3]), r[4]
    k = np.asarray([bars[b] for b in sorted(bars)], dtype=float)
    return k[:, 0] + size, regime_labels(k)


from strategies.profiles import regime_labels  # noqa: E402  (shared with the live bot)


def main():
    z = np.load(PREFIX + '_matrix.npz', allow_pickle=True)
    R, M, strat, ts, clus, names = z['R'], z['M'], z['strat'], z['ts'], z['clus'], list(z['mask_names'])
    first = datetime.fromtimestamp(ts.min() / 1000, timezone.utc)
    last = datetime.fromtimestamp(ts.max() / 1000, timezone.utc).date()
    split = int(datetime(first.year + (first.month - 1 + TRAIN_MONTHS) // 12, (first.month - 1 + TRAIN_MONTHS) % 12 + 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    mid = int(ts.min()) + (split - int(ts.min())) // 2
    start = date(first.year - (first.month <= 2), (first.month - 3) % 12 + 1, 1)
    close_ms, labels = btc_regime_series(Archive(rate_bytes=300_000).klines_ohlc('futures', 'BTCUSDT', '1h', start, last))
    idx = np.searchsorted(close_ms, ts, side='right') - 1
    reg = np.array([labels[i] if i >= 0 else None for i in idx], dtype=object)

    lines = ['# Regime-switched profiles (research_optimize_regime.py, pre-registered)', '',
             'Regime share of entries: ' + ', '.join(f"{g} {np.mean(reg == g):.0%}" for g in REGIMES), '',
             '| strategy | regime | profile | train: n, mean [lower 90%] | halves | validation: n, mean [lower 90%] | verdict |',
             '|---|---|---|---|---|---|---|']
    profiles = {}
    for s in sorted(set(strat)):
        for g in REGIMES:
            sel = (strat == s) & (reg == g)
            tr_, val = sel & (ts < split), sel & (ts >= split)
            h1, h2 = tr_ & (ts < mid), tr_ & (ts >= mid)
            best = None
            for combo in [()] + [(i,) for i in range(M.shape[1])]:
                mk = np.ones(len(R), bool)
                for i in combo:
                    mk &= M[:, i]
                a = tr_ & mk
                if len(np.unique(clus[a])) < 15:
                    continue
                means = R[a].mean(0)
                q = int(np.argmax(means))
                m, lo, _ = cluster_stats(R[a][:, q], clus[a])
                ma, mb = R[h1 & mk][:, q].mean() if (h1 & mk).any() else -1, R[h2 & mk][:, q].mean() if (h2 & mk).any() else -1
                if lo > 0 and ma > 0 and mb > 0 and (best is None or lo > best[0]):
                    best = (lo, m, combo, q, int(a.sum()), ma, mb)
            if best is None:
                continue
            lo, m, combo, q, n, ma, mb = best
            mk = np.ones(len(R), bool)
            for i in combo:
                mk &= M[:, i]
            v = val & mk
            mv, lov, _ = cluster_stats(R[v][:, q], clus[v]) if v.any() else (np.nan, np.nan, 0)
            on = bool(v.any() and mv > 0)
            name = ' & '.join(names[i] for i in combo) or 'all'
            lines.append(f"| {s} | {g} | {name} / {PM[q]} | {n}, {m:+.3f} [{lo:+.3f}] | {ma:+.2f} / {mb:+.2f} | "
                         f"{int(v.sum())}, {mv:+.3f} [{lov:+.3f}] | {'ON' if on else 'off'} |")
            if on:
                profiles.setdefault(s, {})[g] = {'filters': [names[i] for i in combo], 'pm': PM[q],
                                                 'train': {'n': n, 'mean_r': round(m, 3)},
                                                 'validation': {'n': int(v.sum()), 'mean_r': round(float(mv), 3)}}
    lines += ['', 'Strategies / regimes not listed: no profile qualified on the training months.']
    with open(PREFIX + '_regime.md', 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    with open(os.environ.get('OPT_PROFILES', 'models/profiles_regime.json'), 'w', encoding='utf-8') as fh:
        json.dump(profiles, fh, indent=1)
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
