"""
Session opens and leaders (the owner, 2026-10-05: "BTC, ETH, gold and oil are most often the catalyst of the altcoin
market's fall or rise; the US open dumped BTC and every alt today").

Data: Binance USD-M 5m archive klines, the last `MONTHS` complete months: BTC, ETH, XAU, CL (whatever the archive
holds of the commodities: they listed recently) and ALTS (the altcoin median).

Part 1 - session opens (Tokyo 09:00 JST = 00:00 UTC, London 08:00 local, New York 09:30 local, DST-aware; and 08:30
NY, the macro release minute): BTC's and the alt median's return over the first 30 / 60 minutes after the open: mean,
P(down), mean |move|, and |move| relative to the same-length windows at every other time of day (the open's extra
volatility). A placebo row: the same statistics at a random minute-of-day.

Part 2 - who leads: the alt median's 5m return vs each leader's return 0 / 1 / 2 / 3 bars before (correlation), and an
event test: after a leader's 15m move beyond 2.5 of its typical 15m moves, the alt median's NEXT 15 / 60 min return in
the move's direction (vs the unconditional mean). A lead exists only if the next-bar effect is there - a same-bar
correlation says they move together, not who moves first.
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np

from history import Archive

MONTHS = int(sys.argv[1]) if len(sys.argv) > 1 else 12
LEADERS = ('BTCUSDT', 'ETHUSDT', 'XAUUSDT', 'CLUSDT')
ALTS = ('SOLUSDT', 'XRPUSDT', 'DOGEUSDT', 'ADAUSDT', 'LINKUSDT', 'AVAXUSDT', 'DOTUSDT', 'LTCUSDT', 'BCHUSDT',
        'NEARUSDT', 'SUIUSDT', 'APTUSDT', 'ARBUSDT', 'OPUSDT', 'INJUSDT', 'AAVEUSDT', 'UNIUSDT', 'FILUSDT',
        'ATOMUSDT', 'TIAUSDT')
STEP = 300_000


def load(arch, sym, start, end):
    try:
        k = arch.klines_ohlc('futures', sym, '5m', start, end)
    except Exception as e:
        print(sym, 'no data', e)
        return None
    if k is None or len(k) < 1000:
        print(sym, 'too short')
        return None
    return {int(t): c for t, c in zip(k[:, 0], k[:, 4])}


def main():
    today = date.today()
    end = date(today.year, today.month, 1) - timedelta(days=1)
    m = end.month - MONTHS + 1
    start = date(end.year + (m - 1) // 12, (m - 1) % 12 + 1, 1)
    arch = Archive(rate_bytes=500_000)
    series = {s: load(arch, s, start, end) for s in LEADERS + ALTS}
    t0 = int(datetime(start.year, start.month, 1, tzinfo=timezone.utc).timestamp() * 1000)
    t1 = int(datetime(end.year, end.month, end.day, 23, 55, tzinfo=timezone.utc).timestamp() * 1000)
    grid = np.arange(t0, t1 + 1, STEP)

    def arr(d):
        return np.array([d.get(int(t), np.nan) for t in grid]) if d else None
    px = {s: arr(d) for s, d in series.items()}
    ret = {s: np.diff(np.log(v), prepend=np.nan) for s, v in px.items() if v is not None}
    alt_mat = np.vstack([ret[s] for s in ALTS if s in ret])
    alt = np.nanmedian(alt_mat, axis=0)
    lines = [f"# Session opens and leaders ({start} .. {end}, 5m archive)", '']

    # ---------------- part 1
    def window_stats(r, idx, n):
        out = []
        for i in idx:
            if i + n < len(r):
                w = r[i + 1:i + 1 + n]
                # audit R08: a window with missing bars is no observation (nansum made an empty window a 0 return)
                if np.isfinite(w).all():
                    out.append(float(w.sum()))
        return np.array(out)
    opens = {'Tokyo 00:00 UTC': ('UTC', 0, 0), 'London 08:00': ('Europe/London', 8, 0),
             'NY 08:30 (macro)': ('America/New_York', 8, 30), 'NY 09:30 (cash open)': ('America/New_York', 9, 30)}
    lines += ['## Part 1: the first 30 / 60 min after each open (sum of 5m log returns, %)', '',
              '| open | series | n | mean 30m | P(down) 30m | mean abs 30m | abs vs other times | mean 60m | P(down) 60m |',
              '|---|---|---|---|---|---|---|---|---|']
    rng = np.random.default_rng(3)
    for name, (tz, hh, mm) in list(opens.items()) + [('placebo random minute', (None, 0, 0))]:
        idx = []
        if tz is None:
            idx = list(rng.integers(0, len(grid) - 20, 400))
        else:
            d = start
            while d <= end:
                if d.weekday() < 5 or name.startswith('Tokyo'):
                    t = int(datetime(d.year, d.month, d.day, hh, mm, tzinfo=ZoneInfo(tz)).timestamp() * 1000)
                    i = int((t - t0) // STEP) - 1                   # the bar BEFORE the open: returns from the open on
                    if 0 <= i < len(grid):
                        idx.append(i)
                d += timedelta(days=1)
        for label, r in (('BTC', ret.get('BTCUSDT')), ('ALTS median', alt)):
            if r is None:
                continue
            w30, w60 = window_stats(r, idx, 6), window_stats(r, idx, 12)
            base = window_stats(r, list(rng.integers(0, len(grid) - 20, 3000)), 6)
            lines.append(f"| {name} | {label} | {len(w30)} | {w30.mean() * 100:+.3f} | {(w30 < 0).mean():.2f} | "
                         f"{np.abs(w30).mean() * 100:.3f} | {np.abs(w30).mean() / np.abs(base).mean():.2f}x | "
                         f"{w60.mean() * 100:+.3f} | {(w60 < 0).mean():.2f} |")

    # ---------------- part 2
    lines += ['', '## Part 2: does the leader move first? (alt median 5m return)', '',
              '| leader | bars of data | corr lag 0 | lag 1 | lag 2 | lag 3 | events (|15m| > 2.5 sd) | alts next 15m in its direction | next 60m | unconditional 15m |',
              '|---|---|---|---|---|---|---|---|---|---|']
    for s in LEADERS:
        r = ret.get(s)
        if r is None:
            lines.append(f"| {s} | no data | | | | | | | | |")
            continue
        ok = np.isfinite(r) & np.isfinite(alt)
        cors = []
        for lag in range(4):
            a, b = alt[lag:], r[:len(r) - lag]
            mask = np.isfinite(a) & np.isfinite(b)
            cors.append(np.corrcoef(a[mask], b[mask])[0, 1] if mask.sum() > 100 else np.nan)
        r15 = np.convolve(np.nan_to_num(r), np.ones(3), 'full')[:len(r)]
        sd = np.nanstd(r15[ok])
        ev = [i for i in range(3, len(r) - 13) if abs(r15[i]) > 2.5 * sd and ok[i]]
        # one event per 1h
        kept, last = [], -99
        for i in ev:
            if i - last >= 12:
                kept.append(i)
                last = i
        # audit R08: an incomplete window is missing (NaN), not a 0 return
        nx15 = np.array([np.sign(r15[i]) * alt[i + 1:i + 4].sum() for i in kept])
        nx60 = np.array([np.sign(r15[i]) * alt[i + 1:i + 13].sum() for i in kept])
        nx15, nx60 = nx15[np.isfinite(nx15)], nx60[np.isfinite(nx60)]
        unc = np.nanmean(np.abs(np.convolve(np.nan_to_num(alt), np.ones(3), 'valid')))
        lines.append(f"| {s} | {int(ok.sum())} | " + ' | '.join(f"{c:.3f}" for c in cors)
                     + f" | {len(kept)} | {nx15.mean() * 100:+.3f}% | {nx60.mean() * 100:+.3f}% | |abs| {unc * 100:.3f}% |")
    lines += ['', 'Reading: lag 0 = they move in the same 5 minutes; a leader LEADS only if lag 1+ correlations and '
              'the next-15m / 60m continuation are clearly above 0 (vs the cost of acting on it, ~0.1-0.2%).']
    with open('research/sessions_leaders.md', 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
