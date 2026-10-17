"""
The published crypto trend-following method that survived its own long sample, re-tested after its publication:
Zarattini, Pagani & Barbon (2025), "Catching Crypto Trends; A Tactical Approach for Bitcoin and Altcoins" (SSRN
5209907; Jan 2015 - Mar 2025, top-20 liquid coins, net CAGR 18%, Sharpe > 1.5 in their test). Rules as published
(fixed, no parameter search):

- universe: each month, the 20 USDT perpetuals with a Binance spot pair and the largest average daily volume over the
  30 days before, listed >= 1 year (point in time, delisted coins included);
- per coin and lookback L in {5, 10, 20, 30, 60, 90, 150, 250, 360} days: a daily close above the highest close of
  the L days before opens that lookback's sub-position; it closes when the close falls below its trailing stop = the
  higher of the previous stop and the channel midpoint (highest + lowest close of the L days before) / 2;
- coin exposure = the share of its lookbacks that are long x min(2, 25% / the coin's 90-day annualized volatility)
  (audit N31: the 2025-04-09 version caps the volatility scaling at 200%; 100% was ours);
  each coin gets 1/20 of the capital; long-only; decided at the daily close, held from the next day.
- the phase gate alone, for comparison: the top-20 equal weight (or BTC) held only on days whose PREVIOUS close was
  in the UP phase (Faber 2007's 200-day rule + breadth), 0.10% per switch, funding paid;
- the market phase of a day is the one known at the previous close;
- costs: 0.10% of each traded notional (half of the 0.20% round trip: taker fee + slippage), funding of the
  perpetuals held (archive rates); a 0.05%-per-side run for sensitivity.

Reported: the whole window, the part before the paper's end (their sample, overlapping) and the part AFTER it
(2025-04 on: out of sample for the method), each by market phase (BTC vs its 200-day SMA + breadth, as
research_htf.py), against BTC buy-and-hold and the equal-weight top-20 held all the time.

Known remaining differences from the paper (audit N31, reported, not hidden): the universe is the Binance perpetuals
with a spot pair (the paper: CoinMarketCap top coins), and the channel / initial stop follow our reading of the text
where its formulas leave the current close's inclusion open.

Run: python research_ensemble.py [--start 2020-01-01] [--out research/ensemble_trend.md]
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import numpy as np

DAY = 86_400_000
LOOKBACKS = (5, 10, 20, 30, 60, 90, 150, 250, 360)
SIDE_COST = 0.0010
# audit N31: the first SSRN version is dated 2025-04-04 and the one replicated 2025-04-09 - 'after publication'
# starts after it, not on 04-01
PAPER_END = date(2025, 4, 9)


def load(start: date):
    from history import Archive
    from pretrain import _spot_pair
    archive = Archive(rate_bytes=4e7, cache_dir=os.environ.get('HTF_CACHE') or None)
    today = datetime.now(timezone.utc).date()
    end = date(today.year, today.month, 1) - timedelta(days=1)
    futures = [s for s in archive.list_symbols('futures') if s.endswith('USDT') and '_' not in s and 'SETTLED' not in s]
    spot_ids = set(archive.list_symbols('spot'))
    coins = [f for f in futures if _spot_pair(f[:-4], spot_ids)]
    with ThreadPoolExecutor(max_workers=16) as pool:
        data = list(pool.map(lambda f: archive.klines_1d('futures', f, start, end), coins))
    grid = np.arange((start - date(1970, 1, 1)).days, (end - date(1970, 1, 1)).days + 1) * DAY
    C = np.full((len(grid), len(coins)), np.nan)
    V = np.full((len(grid), len(coins)), np.nan)
    for j, arr in enumerate(data):
        if len(arr):
            i = ((arr[:, 0] - grid[0]) // DAY).astype(int)
            ok = (i >= 0) & (i < len(grid))
            C[i[ok], j], V[i[ok], j] = arr[ok, 1], arr[ok, 2]
    return archive, grid, coins, C, V, start, end


def membership(grid, C, V, n_top=20):
    """[day x coin] top-n by the 30-day average volume before the month's first day, listed >= 365 days."""
    n, m = C.shape
    M = np.zeros((n, m), bool)
    age = np.cumsum(~np.isnan(C), axis=0)
    Vz = np.nan_to_num(V)
    cs = np.cumsum(Vz, axis=0)
    days = [datetime.fromtimestamp(t / 1000, timezone.utc).date() for t in grid]
    month_start = [i for i, d in enumerate(days) if d.day == 1 and i >= 31]
    for k, i in enumerate(month_start):
        stop = month_start[k + 1] if k + 1 < len(month_start) else n
        avg = (cs[i - 1] - cs[i - 31]) / 30
        ok = (age[i - 1] >= 365) & ~np.isnan(C[i - 1])
        avg = np.where(ok, avg, -1)
        top = np.argsort(-avg)[:n_top]
        top = top[avg[top] > 0]
        M[i:stop, top] = True
    return M


def exposure(c: np.ndarray) -> np.ndarray:
    """The ensemble's long share per day (0..1) for one coin's daily closes."""
    n = len(c)
    out = np.zeros(n)
    for L in LOOKBACKS:
        pos = np.zeros(n)
        on, stop = False, -np.inf
        for d in range(L, n):
            w = c[d - L:d]
            if np.isnan(c[d]) or np.isnan(w).any():
                on, stop = False, -np.inf
                continue
            hi, lo = w.max(), w.min()
            mid = (hi + lo) / 2
            if on:
                stop = max(stop, mid)
                if c[d] < stop:
                    on, stop = False, -np.inf
            elif c[d] > hi:
                on, stop = True, mid
            pos[d] = 1.0 if on else 0.0
        out += pos
    return out / len(LOOKBACKS)


def market_phase(C, M, btc_j):
    n = C.shape[0]
    def sma(x, k):
        if len(x) < k:
            return np.full(len(x), np.nan)
        return np.concatenate([np.full(k - 1, np.nan), np.convolve(x, np.ones(k) / k, 'valid')])

    btc = C[:, btc_j]
    b200 = sma(np.nan_to_num(btc, nan=np.nan), 200)
    above = np.full(C.shape, np.nan)
    for j in range(C.shape[1]):
        s = sma(C[:, j], 50)
        above[:, j] = np.where(~np.isnan(s) & ~np.isnan(C[:, j]), (C[:, j] > s).astype(float), np.nan)
    # breadth over coins listed >= 100 days with a price (broad market, not only the top 20)
    age = np.cumsum(~np.isnan(C), axis=0)
    breadth = np.nanmean(np.where(age >= 100, above, np.nan), axis=1)
    ph = np.full(n, 'n/a', dtype=object)
    ok = ~np.isnan(b200) & ~np.isnan(breadth)
    up, wide = btc > b200, breadth >= 0.5
    ph[ok & up & wide] = 'UP'
    ph[ok & ~up & ~wide] = 'DOWN'
    ph[ok & (up != wide)] = 'MIXED'
    return ph


def stats(r: np.ndarray):
    r = r[~np.isnan(r)]
    if len(r) < 20:
        return None
    eq = np.cumprod(1 + r)
    years = len(r) / 365
    cagr = eq[-1] ** (1 / years) - 1 if eq[-1] > 0 else -1
    vol = r.std() * np.sqrt(365)
    sharpe = r.mean() * 365 / vol if vol > 0 else np.nan
    dd = (eq / np.maximum.accumulate(eq) - 1).min()
    return cagr, sharpe, dd, eq[-1] - 1, len(r)


def block_ci(r: np.ndarray, block: int = 7, boot: int = 2000, seed: int = 5):
    """90% interval of the annualized mean daily return (weekly blocks)."""
    r = r[~np.isnan(r)]
    nb = len(r) // block
    if nb < 5:
        return np.nan, np.nan
    b = r[:nb * block].reshape(nb, block).mean(axis=1)
    rng = np.random.default_rng(seed)
    means = b[rng.integers(0, nb, size=(boot, nb))].mean(axis=1) * 365
    return tuple(np.quantile(means, [0.05, 0.95]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', default='2020-01-01')
    parser.add_argument('--out', default=os.path.join('research', 'ensemble_trend.md'))
    args = parser.parse_args()
    archive, grid, coins, C, V, start, end = load(date.fromisoformat(args.start))
    M = membership(grid, C, V)
    members = np.flatnonzero(M.any(axis=0))
    print(f"{len(coins)} coins, {len(members)} ever in the top 20, {len(grid)} days", flush=True)
    ret = np.full_like(C, np.nan)
    ret[1:] = C[1:] / C[:-1] - 1
    E = np.zeros_like(C)
    for j in members:
        c = C[:, j]
        lr = np.log(c[1:] / c[:-1])
        vol = np.full(len(c), np.nan)
        for d in range(91, len(c)):
            w = lr[d - 90:d]
            if not np.isnan(w).any():
                vol[d] = w.std() * np.sqrt(365)
        scale = np.where(np.isnan(vol) | (vol <= 0), 0.0, np.minimum(2.0, 0.25 / np.where(vol > 0, vol, 1)))
        E[:, j] = exposure(c) * scale
    W = np.where(M, E, 0.0) / 20
    # funding per coin and day (8h rates summed within the UTC day)
    F = np.zeros_like(C)

    def fund(j):
        return j, archive.funding(coins[j], start, end, raw=True)

    with ThreadPoolExecutor(max_workers=16) as pool:
        for j, f in pool.map(fund, members):
            if len(f):
                i = ((f[:, 0] - grid[0]) // DAY).astype(int)
                ok = (i >= 0) & (i < len(grid))
                np.add.at(F[:, j], i[ok], f[ok, 1])             # the rate paid at each settlement
    btc_j = coins.index('BTCUSDT')
    phase_now = market_phase(C, M, btc_j)
    phase = np.concatenate([['n/a'], phase_now[:-1]])       # known at the PREVIOUS close: the day's return is after it
    n = len(grid)
    r_net, r_low, r_gross, expo = (np.full(n, np.nan) for _ in range(4))
    r_btc, r_ew = np.full(n, np.nan), np.full(n, np.nan)
    r_ew_gate, r_btc_gate = np.full(n, np.nan), np.full(n, np.nan)
    first = 400
    for d in range(first, n):
        w_prev = W[d - 1]
        rr = np.nan_to_num(ret[d])
        gross = float((w_prev * rr).sum())
        turn = float(np.abs(W[d] - W[d - 1]).sum())
        fund_d = float((w_prev * F[d]).sum())
        r_gross[d] = gross
        r_net[d] = gross - turn * SIDE_COST - fund_d
        r_low[d] = gross - turn * SIDE_COST / 2 - fund_d
        expo[d] = w_prev.sum()
        r_btc[d] = ret[d, btc_j]
        mem = M[d - 1] & ~np.isnan(ret[d])
        r_ew[d] = float(ret[d, mem].mean()) if mem.any() else np.nan
        # the phase gate alone (Faber-style): long the top 20 / BTC only while yesterday's phase was UP
        on, was = phase[d] == 'UP', phase[d - 1] == 'UP'
        switch = SIDE_COST if on != was else 0.0
        r_ew_gate[d] = (r_ew[d] - float(F[d, mem].mean()) if on and mem.any() else 0.0) - switch
        r_btc_gate[d] = (ret[d, btc_j] - F[d, btc_j] if on else 0.0) - switch
    days = np.array([datetime.fromtimestamp(t / 1000, timezone.utc).date() for t in grid])
    after = PAPER_END + timedelta(days=1)
    periods = (('whole window', (days >= days[first])),
               (f"paper's sample overlap ({days[first]} .. {PAPER_END})", (days >= days[first]) & (days <= PAPER_END)),
               (f"AFTER publication ({after} .. {days[-1]})", days > PAPER_END))
    lines = ["# Ensemble Donchian trend (Zarattini et al. 2025) re-tested on the Binance archive", '',
             f"{len(members)} coins were in the monthly top 20 at some point; returns net of "
             f"{SIDE_COST * 100:.2f}% per traded side and funding; long-only, 25% vol target per coin, 1/20 of "
             f"capital per coin. Rules: the "
             f"docstring of `research_ensemble.py`. [90%] = weekly-block bootstrap of the annualized mean return.", '']
    for name, mask in periods:
        lines += [f"## {name}", '',
                  '| series | CAGR | Sharpe | max drawdown | total | mean exposure | ann. mean [90%] |',
                  '|---|---:|---:|---:|---:|---:|---|']
        for label, r in (('ensemble net', r_net), ('ensemble at 0.05%/side', r_low), ('ensemble gross', r_gross),
                         ('BTC buy & hold', r_btc), ('top-20 equal weight held', r_ew),
                         ('top-20 EW only in UP phase', r_ew_gate), ('BTC only in UP phase', r_btc_gate)):
            s = stats(r[mask])
            if not s:
                continue
            lo, hi = block_ci(r[mask])
            ex = np.nanmean(expo[mask]) if label.startswith('ensemble') else \
                (float(np.mean(phase[mask] == 'UP')) if 'UP phase' in label else 1.0)
            lines.append(f"| {label} | {s[0] * 100:+.1f}% | {s[1]:.2f} | {s[2] * 100:.1f}% | {s[3] * 100:+.1f}% | "
                         f"{ex:.0%} | {np.nanmean(r[mask]) * 36500:+.1f}% [{lo * 100:+.1f}..{hi * 100:+.1f}] |")
        lines += ['', '| market phase | days | ensemble net ann. mean [90%] | exposure | BTC ann. mean | '
                  'top-20 EW ann. mean |',
                  '|---|---:|---|---:|---:|---:|']
        for ph in ('UP', 'MIXED', 'DOWN'):
            pm = mask & (phase == ph)
            if pm.sum() < 20:
                continue
            lo, hi = block_ci(r_net[pm])
            lines.append(f"| {ph} | {int(pm.sum())} | {np.nanmean(r_net[pm]) * 36500:+.1f}% [{lo * 100:+.1f}.."
                         f"{hi * 100:+.1f}] | {np.nanmean(expo[pm]):.0%} | {np.nanmean(r_btc[pm]) * 36500:+.1f}% | "
                         f"{np.nanmean(r_ew[pm]) * 36500:+.1f}% |")
        lines.append('')
    text = '\n'.join(lines) + '\n'
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)


if __name__ == '__main__':
    main()
