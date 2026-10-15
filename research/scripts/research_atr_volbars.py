"""
Plan 3.5 and 3.7 (eng-59), pre-registered.

3.5 ATR: the bot's ATR14 is a SIMPLE mean of true ranges; Wilder defined an RMA (alpha 1/14). On the archive's 15m
candles: the ratio RMA / SMA per candle (its median and 10-90% spread) and how often the 1-ATR stop floor would move
by more than 10%. Decision: switch (and recalibrate every ATR threshold) only if the 10-90% spread of the ratio
exceeds +-10%; otherwise the difference is below the thresholds' own precision and the simple mean stays.

3.7 Volume bars (Lopez de Prado, AFML ch. 2): do bars of equal volume remove the hour-of-day seasonality the bot
corrects with indicators.seasonal_factors? On 1m candles: per hour of day (UTC) the mean |return| of 15-minute time
bars vs of volume bars (each holding the coin's average 15m volume). Seasonality = max/min of those hourly means.
Decision: volume bars help Tier-0 only if their max/min ratio is below 1.3 while the time bars' is above 1.5.

Run: .venv\\Scripts\\python research_atr_volbars.py [--coins 20] [--months 3] [--out research/atr_volbars.md]
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import argparse
import os
from datetime import date, timedelta

import numpy as np


def atrs(h, l, c, n=14):
    tr = np.maximum(h[1:], c[:-1]) - np.minimum(l[1:], c[:-1])
    sma = np.convolve(tr, np.ones(n) / n, 'valid')
    rma = np.empty(len(tr))
    rma[:n] = np.nan
    rma[n - 1] = tr[:n].mean()
    for i in range(n, len(tr)):
        rma[i] = rma[i - 1] + (tr[i] - rma[i - 1]) / n
    return sma, rma[n - 1:]


def main():
    from history import Archive
    ap = argparse.ArgumentParser()
    ap.add_argument('--coins', type=int, default=20)
    ap.add_argument('--months', type=int, default=3)
    ap.add_argument('--rate', type=float, default=2e6)
    ap.add_argument('--out', default=os.path.join('research', 'atr_volbars.md'))
    args = ap.parse_args()
    arch = Archive(rate_bytes=args.rate)
    end = date(date.today().year, date.today().month, 1) - timedelta(days=1)
    first = end.replace(day=1)
    for _ in range(args.months - 1):
        first = (first - timedelta(days=1)).replace(day=1)
    vols = []
    for s in arch.list_symbols('futures'):
        if not s.endswith('USDT') or '_' in s:
            continue
        try:
            d = arch.klines_ohlc('futures', s, '1d', first, end)
        except Exception:
            continue
        if len(d) >= 30:
            vols.append((float(d[-30:, 5].mean()), s))
    pick = [s for _, s in sorted(vols, reverse=True)[:args.coins]]
    ratios, floor_moves = [], []
    t_hour = np.zeros(24)
    t_n = np.zeros(24)
    v_hour = np.zeros(24)
    v_n = np.zeros(24)
    for sym in pick:
        m15 = arch.klines_ohlc('futures', sym, '15m', first, end)
        if len(m15) < 500:
            continue
        sma, rma = atrs(m15[:, 2], m15[:, 3], m15[:, 4])
        r = rma / sma
        r = r[np.isfinite(r)]
        ratios.append(r)
        floor_moves.append(float((np.abs(r - 1) > 0.10).mean()))
        m1 = arch.klines_1m('futures', sym, first, end)
        if len(m1) < 10_000:
            continue
        ts, close, qv = m1[:, 0], m1[:, 4], m1[:, 6]
        # time bars of 15 minutes
        k = (ts // 900_000).astype(np.int64)
        edges = np.flatnonzero(np.diff(k)) + 1
        starts = np.concatenate([[0], edges])
        ends = np.concatenate([edges, [len(k)]])
        for a, b in zip(starts, ends):
            if b - a < 10:
                continue
            ret = abs(close[b - 1] / close[a] - 1)
            hr = int((ts[a] // 3_600_000) % 24)
            t_hour[hr] += ret
            t_n[hr] += 1
        # volume bars holding the average 15m volume
        size = qv.sum() / max(1, len(starts))
        cum = np.cumsum(qv)
        cuts = np.searchsorted(cum, np.arange(size, cum[-1], size))
        prev = 0
        for e in cuts:
            if e <= prev:
                continue
            ret = abs(close[e] / close[prev] - 1)
            hr = int((ts[prev] // 3_600_000) % 24)
            v_hour[hr] += ret
            v_n[hr] += 1
            prev = e
        print(sym, flush=True)
    allr = np.concatenate(ratios) if ratios else np.array([np.nan])
    tm = t_hour / np.maximum(t_n, 1)
    vm = v_hour / np.maximum(v_n, 1)
    t_season = tm[t_n > 0].max() / tm[t_n > 0].min()
    v_season = vm[v_n > 0].max() / vm[v_n > 0].min()
    p10, p50, p90 = np.percentile(allr, [10, 50, 90])
    lines = [f"# ATR: Wilder RMA vs simple mean; volume bars vs time bars ({len(pick)} coins, {first} .. {end})", '',
             'Rules: the docstring of `research_atr_volbars.py` (pre-registered).', '',
             '## 3.5 ATR14 on 15m candles', '',
             f"- RMA / SMA: median {p50:.3f}, 10-90% {p10:.3f} .. {p90:.3f}",
             f"- candles where the 1-ATR stop floor would move by > 10%: {np.mean(floor_moves):.0%}",
             f"- verdict: {'switch to RMA and recalibrate' if (p90 - 1 > 0.10 or 1 - p10 > 0.10) else 'keep the simple mean'}",
             '', '## 3.7 Hour-of-day seasonality of |return|', '',
             '| hour UTC | time bars 15m | volume bars |', '|---:|---:|---:|']
    for h in range(24):
        lines.append(f"| {h} | {tm[h]:.4%} | {vm[h]:.4%} |")
    lines += ['', f"- max/min: time bars {t_season:.2f}, volume bars {v_season:.2f}",
              f"- verdict: {'volume bars remove the seasonality' if v_season < 1.3 and t_season > 1.5 else 'keep time bars + seasonal factors'}"]
    text = '\n'.join(lines)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(text + '\n')
    print(text)


if __name__ == '__main__':
    main()
