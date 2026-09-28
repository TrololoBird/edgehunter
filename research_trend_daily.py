"""
Candidate REPLACEMENT strategies with documented evidence in crypto, tested on the Binance archive's daily candles
before any of them touches the bot. Pre-registered (fixed before looking at the results, no parameter search):

- TSMOM (time-series momentum; Moskowitz, Ooi & Pedersen 2012; crypto: Liu & Tsyvinski 2021, 1-4 week horizons):
  every Monday, each coin long when its 28-day return is > 0, short when < 0; held 7 days.
- XSMOM (cross-sectional momentum; Liu, Tsyvinski & Wu 2022, "Common Risk Factors in Cryptocurrency"): every Monday,
  long the top 10% of the universe by 28-day return (the last day skipped), short the bottom 10%; held 7 days.
- TREND (the classic trend filter, e.g. the Turtles / moving-average rules): long while close > EMA50 and
  EMA20 > EMA50, short while close < EMA50 and EMA20 < EMA50, flat otherwise; checked daily, 1-day holds chained.

Universe per day: USDT perpetuals with a Binance spot pair whose average daily quote volume over the 30 days BEFORE
is >= $10M (the live universe's floor), listed >= 9 days - delisted coins included (the archive listing). Costs: a
position change pays the round trip (0.1% taker fee + 2 x 5 bps slippage); funding is not modelled (at +0.01% / 8h a
week's long pays ~0.2%: stated next to the results). Results per trade, per week, vs the equal-weight universe mean,
in the older and the newer half separately, with week-block bootstrap intervals.

Run: .venv\\Scripts\\python research_trend_daily.py [--months 36] [--out research/trend_daily.md]
"""
import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Tuple

import numpy as np
import polars as pl

from config import CONFIG

DAY = 86_400_000
COST = CONFIG.journal.fee_round_trip + 2 * CONFIG.levels.slippage_bps / 1e4


def load(months: int) -> Tuple[np.ndarray, List[str], np.ndarray, np.ndarray]:
    """(day grid, symbols, closes [day x coin], quote volumes [day x coin]) from the archive's monthly 1d files."""
    from history import Archive
    from pretrain import _spot_pair
    archive = Archive(rate_bytes=4e7)
    end = datetime.now(timezone.utc).date() - timedelta(days=1)
    start = end - timedelta(days=30 * months + 60)
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
    return grid, coins, C, V


def eligible(C: np.ndarray, V: np.ndarray) -> np.ndarray:
    """[day x coin] in the universe that day: 30-day average volume BEFORE >= the live floor, >= 9 days of history."""
    floor = CONFIG.exchange.min_24h_quote_volume_usd
    vol = pl.DataFrame(np.nan_to_num(V)).select(pl.all().rolling_mean(30, min_samples=9).shift(1)).to_numpy()
    age = np.cumsum(~np.isnan(C), axis=0)
    return (vol >= floor) & (age >= CONFIG.exchange.min_listing_days + 1) & ~np.isnan(C)


def ema(C: np.ndarray, span: int) -> np.ndarray:
    return pl.DataFrame(C).select(pl.all().ewm_mean(span=span, adjust=False, ignore_nulls=True)).to_numpy()


def week_ci(pnl_by_week: Dict[int, List[float]], boot: int = 2000, seed: int = 7) -> Tuple[float, float, float, int]:
    """(mean per trade, lo, hi, weeks) with a bootstrap over weeks (the trades of one week ride one market move)."""
    weeks = [np.asarray(v) for v in pnl_by_week.values() if len(v)]
    if len(weeks) < 5:
        return float('nan'), float('nan'), float('nan'), len(weeks)
    sums, counts = np.asarray([w.sum() for w in weeks]), np.asarray([len(w) for w in weeks])
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(weeks), size=(boot, len(weeks)))
    means = sums[idx].sum(axis=1) / counts[idx].sum(axis=1)
    lo, hi = np.quantile(means, [0.05, 0.95])
    return float(sums.sum() / counts.sum()), float(lo), float(hi), len(weeks)


def evaluate(grid, C, E, signal_fn, hold: int, weekly: bool) -> Dict[str, Dict[int, List[float]]]:
    """Per-trade net returns (absolute and vs the universe mean) grouped by week, for each half of the window."""
    fwd = np.full_like(C, np.nan)
    fwd[:-hold] = C[hold:] / C[:-hold] - 1
    mkt = np.nanmean(np.where(E, fwd, np.nan), axis=1)
    out = {'abs': {}, 'rel': {}}
    step = 7 if weekly else hold
    first = 60
    mondays = [i for i in range(first, len(grid) - hold) if (grid[i] // DAY + 3) % 7 == 0] if weekly else \
        list(range(first, len(grid) - hold, step))
    for i in mondays:
        sig = signal_fn(i)                                   # +1 / -1 / 0 per coin, from data up to day i
        ok = E[i] & (sig != 0) & ~np.isnan(fwd[i])
        if not ok.any():
            continue
        week = int(grid[i] // (7 * DAY))
        r = sig[ok] * fwd[i, ok] - COST
        out['abs'].setdefault(week, []).extend(r.tolist())
        out['rel'].setdefault(week, []).extend((sig[ok] * (fwd[i, ok] - mkt[i]) - COST).tolist())
    return out


def evaluate_trend(grid, C, E, signal_fn) -> Dict[str, Dict[int, List[float]]]:
    """
    Daily position per coin held while the signal lasts: each coin-day earns pos x the next day's return and pays
    COST / 2 per unit of position change (a flip from long to short = 2 units = one round trip + one open).
    """
    ret1 = np.full_like(C, np.nan)
    ret1[:-1] = C[1:] / C[:-1] - 1
    mkt = np.nanmean(np.where(E, ret1, np.nan), axis=1)
    out = {'abs': {}, 'rel': {}}
    prev = np.zeros(C.shape[1])
    for i in range(60, len(grid) - 1):
        pos = np.where(E[i] & ~np.isnan(ret1[i]), signal_fn(i), 0.0)
        cost = np.abs(pos - prev) * COST / 2
        held = (pos != 0) | (prev != 0)
        week = int(grid[i] // (7 * DAY))
        r = np.nan_to_num(pos * ret1[i]) - cost
        rel = np.nan_to_num(pos * (ret1[i] - mkt[i])) - cost
        out['abs'].setdefault(week, []).extend(r[held].tolist())
        out['rel'].setdefault(week, []).extend(rel[held].tolist())
        prev = pos
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--months', type=int, default=36)
    parser.add_argument('--out', default=os.path.join('research', 'trend_daily.md'))
    args = parser.parse_args()
    grid, coins, C, V = load(args.months)
    E = eligible(C, V)
    ret28 = np.full_like(C, np.nan)
    ret28[29:] = C[28:-1] / C[:-29] - 1                      # 28 days up to YESTERDAY (the last day skipped)
    ret28_full = np.full_like(C, np.nan)
    ret28_full[28:] = C[28:] / C[:-28] - 1
    e20, e50 = ema(C, 20), ema(C, 50)

    def tsmom(i):
        return np.nan_to_num(np.sign(ret28_full[i]))

    def xsmom(i):
        r = np.where(E[i], ret28[i], np.nan)
        if np.sum(~np.isnan(r)) < 30:
            return np.zeros(C.shape[1])
        hi, lo = np.nanquantile(r, 0.9), np.nanquantile(r, 0.1)
        return np.where(r >= hi, 1.0, np.where(r <= lo, -1.0, 0.0))

    def trend(i):
        up = (C[i] > e50[i]) & (e20[i] > e50[i])
        down = (C[i] < e50[i]) & (e20[i] < e50[i])
        return np.where(up, 1.0, np.where(down, -1.0, 0.0))

    mid = grid[len(grid) // 2]
    lines = [f"# Candidate replacement strategies on daily candles ({len(coins)} coins with a spot pair, "
             f"{datetime.fromtimestamp(grid[60] / 1000, timezone.utc):%Y-%m-%d} .. "
             f"{datetime.fromtimestamp(grid[-1] / 1000, timezone.utc):%Y-%m-%d})", '',
             f"Per-trade returns net of {COST * 100:.2f}% per position change (taker fee + slippage); funding NOT "
             f"included (a week's long at +0.01% / 8h pays ~0.21%). 'vs mean' = minus the equal-weight universe mean "
             f"over the same days (market-neutral view). [90%] = bootstrap over weeks. Universe per day: $10M "
             f"average volume over the 30 days before, delisted coins included.", '',
             '| strategy | half | weeks | trades | mean net per trade [90%] | vs universe mean [90%] | long share |',
             '|---|---|---:|---:|---|---|---:|']
    for name, fn, hold, weekly in (('TSMOM 28d, hold 7d', tsmom, 7, True), ('XSMOM top/bottom 10%, hold 7d', xsmom, 7, True),
                                   ('TREND EMA20/50, daily', trend, 1, False)):
        res = evaluate_trend(grid, C, E, fn) if name.startswith('TREND') else evaluate(grid, C, E, fn, hold, weekly)
        longs = []
        for i in range(60, len(grid) - hold):
            s = fn(i)[E[i]]
            if len(s):
                longs.append(float((s > 0).sum() / max(1, (s != 0).sum())))
        for half, cond in (('older', lambda w: w * 7 * DAY < mid), ('newer', lambda w: w * 7 * DAY >= mid)):
            a = {w: v for w, v in res['abs'].items() if cond(w)}
            rel = {w: v for w, v in res['rel'].items() if cond(w)}
            m, lo, hi, n = week_ci(a)
            m2, lo2, hi2, _ = week_ci(rel)
            trades = sum(len(v) for v in a.values())
            lines.append(f"| {name} | {half} | {n} | {trades} | {m * 100:+.2f}% [{lo * 100:+.2f}..{hi * 100:+.2f}] | "
                         f"{m2 * 100:+.2f}% [{lo2 * 100:+.2f}..{hi2 * 100:+.2f}] | {np.mean(longs):.0%} |")
    lines += ['', "TREND is measured per coin-day of holding (the next day's return, costs only on position changes): "
              "its 'per trade' is per day held, not comparable in size to the 7-day holds above."]
    text = '\n'.join(lines) + '\n'
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)


if __name__ == '__main__':
    main()
