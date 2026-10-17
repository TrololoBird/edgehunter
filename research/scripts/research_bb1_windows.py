"""
How often Bollinger's Method I (strategies.maniac.bb_method1_event) fires and how often it pays, per timeframe and per
Squeeze window (eng-132, the owner's question: 125 bars is 31 hours on 15m but Bollinger's six months on the daily).

Descriptive, nothing here changes the bot. Protocol (fixed before the run):
- the event = exactly bb_method1_event's rule, vectorized: BB(20, 2) on closes, BandWidth at its lowest of the last W
  bars, the FIRST close outside a band after the last Squeeze bar, Intraday Intensity (21) in the close's direction;
- windows W: 125 bars (our live value), 1 week, 1 month (30 d), 6 months (182 d), converted to bars of each timeframe
  (15m, 1h, 4h, 1d; at least 20 bars);
- the trade: entry at the NEXT bar's open, initial stop = the live sar0 (extreme of the last 20 bars), exit by Wilder's
  Parabolic SAR (0.02 / 0.20) bar by bar (a gap through the SAR fills at the open), at most 500 bars; R = move / initial
  risk, net of 0.08% round-trip taker fee (+ no slippage);
- the first half of the window (6 months) is warm-up for W; events are counted in the LAST `--test-months` months, split
  into halves; PLACEBO = the same direction and the same risk in %, at a random bar of the same coin and test period;
- reported: events per coin-month, win rate (net R > 0), mean / median net R, share reaching +1R, both halves, placebo mean.
"working" (a hypothesis, not a conclusion): mean net R > 0 in BOTH halves and above the placebo mean in both.

    python research_bb1_windows.py --months 12 --test-months 6 --limit 60
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import argparse
import logging
import os
import random
from datetime import date, datetime, timedelta, timezone

import numpy as np
import polars as pl

FEE = 0.0008
MAX_BARS = 500
TFS = {'15m': 900, '1h': 3600, '4h': 14400, '1d': 86400}
WINDOWS = {'125 bars': None, '1 week': 7, '1 month': 30, '6 months': 182}      # days; None = 125 bars


def window_bars(tf: str, days):
    return 125 if days is None else max(20, int(days * 86400 / TFS[tf]))


def events_of(bars: np.ndarray, W: int):
    """(index, direction, sar0) of every Method I event over the bars [ts, o, h, l, c, qv]."""
    n = len(bars)
    if n < 20 + W + 2:
        return []
    h, l, c, v = bars[:, 2], bars[:, 3], bars[:, 4], bars[:, 5]
    s = pl.Series(c)
    ma = s.rolling_mean(20).to_numpy()
    sd = s.rolling_std(20, ddof=0).to_numpy()
    up, lo = ma + 2 * sd, ma - 2 * sd
    with np.errstate(divide='ignore', invalid='ignore'):
        bw = (up - lo) / ma
    rmin = pl.Series(bw).rolling_min(W).to_numpy()
    sq = np.isfinite(bw) & np.isfinite(rmin) & (bw <= rmin)
    idx = np.arange(n)
    last_sq = np.maximum.accumulate(np.where(sq, idx, -1))
    outside = np.nan_to_num((c > up) | (c < lo), nan=0).astype(np.int64)
    cs = np.cumsum(outside)
    rng = h - l
    clv = np.where(rng > 0, (2 * c - h - l) / np.where(rng > 0, rng, 1), 0.0)
    num = pl.Series(clv * v).rolling_sum(21).to_numpy()
    den = pl.Series(v).rolling_sum(21).to_numpy()
    with np.errstate(divide='ignore', invalid='ignore'):
        ii = np.where(den > 0, num / den, 0.0)
    lo20 = pl.Series(l).rolling_min(20).to_numpy()
    hi20 = pl.Series(h).rolling_max(20).to_numpy()
    out = []
    for i in range(20 + W, n - 1):
        k0 = last_sq[i - 1]                        # the live rule: the Squeeze bar lies in [i - W, i - 1]
        if k0 < i - W or k0 < 0:
            continue
        if cs[i - 1] != cs[k0]:                    # a close outside a band since the Squeeze
            continue
        d = 1 if c[i] > up[i] else -1 if c[i] < lo[i] else 0
        if not d or d * ii[i] <= 0:
            continue
        out.append((i, d, float(lo20[i] if d > 0 else hi20[i])))
    return out


def sar_trade(bars: np.ndarray, i: int, d: int, risk_pct: float, entry=None):
    """Net R of a trade entered at bar i+1's open with the initial stop `risk_pct` away, exited by Parabolic SAR."""
    n = len(bars)
    o, h, l = bars[:, 1], bars[:, 2], bars[:, 3]
    entry = float(o[i + 1]) if entry is None else entry
    risk = entry * risk_pct
    if risk <= 0:
        return None
    sar = entry - d * risk
    ep = float(h[i] if d > 0 else l[i])
    af = 0.02
    mfe = 0.0
    for j in range(i + 1, min(n, i + 1 + MAX_BARS)):
        if (d > 0 and l[j] <= sar) or (d < 0 and h[j] >= sar):
            px = min(o[j], sar) if d > 0 else max(o[j], sar)
            r = d * (px - entry) / risk - FEE * entry / risk
            return r, mfe >= 1.0
        mfe = max(mfe, d * ((h[j] if d > 0 else l[j]) - entry) / risk)
        new_ep = float(h[j] if d > 0 else l[j])
        if d * (new_ep - ep) > 0:
            ep, af = new_ep, min(0.20, af + 0.02)
        nxt = sar + af * (ep - sar)
        # audit R06: Wilder / TA-Lib - never inside THIS or the PREVIOUS bar's range (as maniac.parabolic_sar_step)
        sar = min(nxt, l[j], l[j - 1]) if d > 0 else max(nxt, h[j], h[j - 1])
    px = float(bars[min(n, i + 1 + MAX_BARS) - 1, 4])
    return d * (px - entry) / risk - FEE * entry / risk, mfe >= 1.0


def run_coin(job):
    symbol, start, end, test_ms, mid_ms = job
    from history import Archive
    arch = Archive(rate_bytes=4e6)
    rng = random.Random(hash(symbol) & 0xffffffff)
    rows = []
    for tf in TFS:
        bars = arch.klines_ohlc('futures', symbol, tf, date.fromisoformat(start), date.fromisoformat(end))
        if len(bars) < 300:
            continue
        ts = bars[:, 0]
        test_idx = np.flatnonzero(ts >= test_ms)
        if len(test_idx) < 10:
            continue
        for wname, days in WINDOWS.items():
            W = window_bars(tf, days)
            for i, d, sar0 in events_of(bars, W):
                if ts[i] < test_ms or i + 1 >= len(bars):
                    continue
                entry = float(bars[i + 1, 1])
                risk_pct = abs(entry - sar0) / entry
                if not 0 < risk_pct < 0.5:
                    continue
                res = sar_trade(bars, i, d, risk_pct)
                j = int(rng.choice(test_idx[:-1])) if len(test_idx) > 1 else i
                pl_res = sar_trade(bars, j, d, risk_pct) if j + 1 < len(bars) else None
                if res:
                    rows.append((tf, wname, int(ts[i]), int(ts[i] >= mid_ms), d, res[0], res[1],
                                 pl_res[0] if pl_res else None, risk_pct))
    return symbol, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--months', type=int, default=12)
    ap.add_argument('--test-months', type=int, default=6)
    ap.add_argument('--limit', type=int, default=60)
    ap.add_argument('--end', default=None)
    ap.add_argument('--min-volume', type=float, default=3e6)
    ap.add_argument('--out', default=os.path.join('research', 'bb1_windows.md'))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-7s | %(message)s', datefmt='%H:%M:%S')
    from history import Archive
    from pretrain import select_coins
    end = date.fromisoformat(args.end) if args.end else datetime.now(timezone.utc).date().replace(day=1) - timedelta(days=1)
    start = end - timedelta(days=30 * args.months)
    test_start = end - timedelta(days=30 * args.test_months)
    ms = lambda d: datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000  # noqa: E731
    test_ms = ms(test_start)
    mid_ms = (test_ms + ms(end)) / 2
    coins = select_coins(Archive(rate_bytes=4e7), start, end, args.min_volume)[:args.limit]
    allrows = []
    for k, (_, f, _, _) in enumerate(coins, 1):
        sym, rows = run_coin((f, start.isoformat(), end.isoformat(), test_ms, mid_ms))
        allrows += rows
        logging.info(f"bb1: {k}/{len(coins)} {sym} {len(rows)} events")
    n_coins = len(coins)
    lines = [f"# Bollinger Method I by timeframe and Squeeze window ({n_coins} coins, test {test_start} .. {end}, "
             f"the {args.months - args.test_months} months before are warm-up)", '',
             'Net R after a 0.08% round-trip fee, exit by Parabolic SAR (see the script header for the protocol). '
             'Placebo = the same side and risk at a random bar of the coin. "Both halves" = mean net R > 0 in both halves '
             'of the test period AND above the placebo mean in both.', '',
             '| tf | window | bars | events | per coin-month | win % | mean R | median R | 1R reached % | '
             'mean R 1st half | mean R 2nd half | placebo mean R | works? |',
             '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|']
    months = args.test_months
    for tf in TFS:
        for wname, days in WINDOWS.items():
            sel = [r for r in allrows if r[0] == tf and r[1] == wname]
            if not sel:
                lines.append(f"| {tf} | {wname} | {window_bars(tf, days)} | 0 | - | - | - | - | - | - | - | - | - |")
                continue
            rs = np.array([r[5] for r in sel])
            half = [np.array([r[5] for r in sel if r[3] == h]) for h in (0, 1)]
            pls = [np.array([r[7] for r in sel if r[3] == h and r[7] is not None]) for h in (0, 1)]
            hm = [float(x.mean()) if len(x) else None for x in half]
            pm = [float(x.mean()) if len(x) else None for x in pls]
            ok = all(a is not None and b is not None and a > 0 and a > b for a, b in zip(hm, pm))
            fmt = lambda x: '-' if x is None else f"{x:+.2f}"  # noqa: E731
            plac = np.array([r[7] for r in sel if r[7] is not None])
            lines.append(f"| {tf} | {wname} | {window_bars(tf, days)} | {len(sel)} | {len(sel) / n_coins / months:.2f} | "
                         f"{(rs > 0).mean():.0%} | {rs.mean():+.2f} | {np.median(rs):+.2f} | "
                         f"{np.mean([r[6] for r in sel]):.0%} | {fmt(hm[0])} (n={len(half[0])}) | "
                         f"{fmt(hm[1])} (n={len(half[1])}) | {fmt(float(plac.mean()) if len(plac) else None)} | "
                         f"{'yes' if ok else 'no'} |")
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
