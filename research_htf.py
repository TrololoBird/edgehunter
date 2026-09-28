# ruff: noqa: E741  (O / H / L / C and h / l are the candle fields)
"""
Higher-timeframe strategies by MARKET PHASE, on the Binance archive's 1h candles (4h / daily / weekly built from them).
The question: does the owner's scheme - the weekly / daily trend gives the direction, 4h the pullback, 1h the entry,
held for days - or a classic HTF method earn money net of costs in some market phase, on data not used to pick it?

Pre-registered (fixed before looking at any result; no parameter search - only the phase cells are selected):

Market phase (at the last closed day, BTC + breadth; Faber 2007 200-day rule, breadth = share of the universe above
its 50-day SMA): UP = BTC above its 200-day SMA and breadth >= 50%; DOWN = below and < 50%; MIXED otherwise.
Also reported: BTC volatility state (30-day realized vs its trailing 1-year median) and the coin's own phase
(daily ADX14 >= 25 with EMA20 vs EMA50 = trend up / down, ADX14 < 20 = range, else transition).

Strategies:
- TRIPLE (Elder's triple screen, the owner's scheme): tide = the weekly EMA13 rising (falling) and the daily close
  above (below) its EMA50; wave = a 4h candle trading into its EMA20 against the tide (a pullback to value), armed
  for 24h; ripple = a 1h close beyond the extreme of the 3 previous 1h candles in the tide's direction. Entry at the
  next 1h open; stop = beyond the pullback's extreme of the last 12h + 0.5 ATR14(4h), at least 1 ATR14(4h) away;
  exit = chandelier trail 3 ATR14(4h) from the best price since entry (LeBeau), or 14 days.
- TURTLE (Donchian System 1, Faith 2003; Concretum 2025 for crypto): the daily close beyond the prior 20-day high
  (low); entry at the next 1h open; stop 2 N (N = ATR20 daily); exit on a daily close beyond the prior 10-day low
  (high), or 60 days.
- RANGE (Bollinger mean reversion, for the range phase): coin daily ADX14 < 20; a 4h close outside its Bollinger
  band (20, 2) armed for 12h; entry on a 1h close beyond the previous 1h candle back inward; target = the 4h band's
  middle at the signal; stop as TRIPLE; or 72h.

One position per coin, strategy and direction at a time. Costs: 0.10% taker round trip + 2 x 5 bps slippage (0.20%),
funding of every 8h settlement held (archive rates), stops filled at the stop or at the open beyond it, targets once
traded 2 bps through. R = net return / the initial stop distance. 'vs mean' = minus the equal-weight universe's mean
return over the same hours (a placebo for the market move). Universe per day: USDT perpetuals with a Binance spot
pair, >= $10M average daily volume over the 30 days BEFORE, >= 100 days of history; delisted coins included.

Protocol: the older half of the window picks the cells (strategy x direction x market phase) whose mean net R > 0
with a Benjamini-Hochberg q <= 0.10 (week-block bootstrap); the newer half is looked at ONCE for those cells. A cell
passes only if its newer-half mean net R is > 0 with the 90% interval above 0.

Run: python research_htf.py [--months 38] [--limit N] [--out research/htf_phases.md]
"""
import argparse
import multiprocessing as mp
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List

import numpy as np

from config import CONFIG

HOUR = 3_600_000
COST = CONFIG.journal.fee_round_trip + 2 * CONFIG.levels.slippage_bps / 1e4
LOW_COST = 0.0010                     # sensitivity: BNB-discounted / partly maker fees, 1-2 bps slippage
THROUGH = 2e-4
G: Dict = {}                          # shared with the forked workers


# ---------------------------------------------------------------------------------------------------- data

def load(months: int, limit: int = 0, end_month: str = ''):
    """end_month 'YYYY-MM': the window's last month (default: the last complete one)."""
    from history import Archive
    from pretrain import _spot_pair
    archive = Archive(rate_bytes=4e7, cache_dir=os.environ.get('HTF_CACHE') or None)
    today = datetime.now(timezone.utc).date()
    if end_month:
        y, m = map(int, end_month.split('-'))
        today = date(y + (m == 12), m % 12 + 1, 1)
    end = date(today.year, today.month, 1) - timedelta(days=1)            # the last complete month
    first = date(end.year, end.month, 1)
    for _ in range(months - 1):
        first = (first - timedelta(days=1)).replace(day=1)
    futures = [s for s in archive.list_symbols('futures') if s.endswith('USDT') and '_' not in s and 'SETTLED' not in s]
    spot_ids = set(archive.list_symbols('spot'))
    coins = [f for f in futures if _spot_pair(f[:-4], spot_ids)]
    if 'BTCUSDT' in coins:
        coins.remove('BTCUSDT')
    coins = ['BTCUSDT'] + coins
    if limit:
        coins = coins[:limit]

    def one(sym):
        return archive.klines_ohlc('futures', sym, '1h', first, end), archive.funding(sym, first, end, raw=True)

    with ThreadPoolExecutor(max_workers=16) as pool:
        data = list(pool.map(one, coins))
    start = first - timedelta(days=first.weekday())                     # a Monday: daily / weekly bars align
    t0 = (datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp()) * 1000
    t1 = (datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=1)).timestamp() * 1000
    n = int((t1 - t0) // HOUR)
    n = (n // 168 + 1) * 168
    shape = (n, len(coins))
    O, H, L, C, V = (np.full(shape, np.nan) for _ in range(5))
    funding = []
    for j, (k, f) in enumerate(data):
        if len(k):
            i = ((k[:, 0] - t0) // HOUR).astype(int)
            ok = (i >= 0) & (i < n)
            O[i[ok], j], H[i[ok], j], L[i[ok], j], C[i[ok], j], V[i[ok], j] = (k[ok, c] for c in range(1, 6))
        funding.append(f)
    return t0, coins, O, H, L, C, V, funding


# ---------------------------------------------------------------------------------------------------- indicators

def bars(O, H, L, C, k):
    """Bars of k hours from hourly arrays (1-D); NaN where an hour is missing."""
    m = len(C) // k
    o, h, l, c = (x[:m * k].reshape(m, k) for x in (O, H, L, C))
    return o[:, 0], h.max(axis=1), l.min(axis=1), c[:, -1]


def ema(x, span):
    out = np.full_like(x, np.nan)
    a = 2.0 / (span + 1)
    prev = np.nan
    for i, v in enumerate(x):
        if np.isnan(v):
            prev = np.nan
            continue
        prev = v if np.isnan(prev) else prev + a * (v - prev)
        out[i] = prev
    return out


def sma(x, n):
    out = np.full_like(x, np.nan)
    if len(x) >= n:
        w = np.lib.stride_tricks.sliding_window_view(x, n)
        out[n - 1:] = w.mean(axis=1)
    return out


def rolling_std(x, n):
    out = np.full_like(x, np.nan)
    if len(x) >= n:
        w = np.lib.stride_tricks.sliding_window_view(x, n)
        out[n - 1:] = w.std(axis=1)
    return out


def true_range(h, l, c):
    pc = np.concatenate([[np.nan], c[:-1]])
    return np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0) * np.where(np.isnan(h), np.nan, 1)


def atr(h, l, c, n):
    return sma(true_range(h, l, c), n)          # a simple mean, as the bot's ATR


def adx(h, l, c, n=14):
    """Wilder's ADX."""
    up = np.diff(h, prepend=np.nan)
    dn = -np.diff(l, prepend=np.nan)
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = true_range(h, l, c)
    out = np.full_like(c, np.nan)
    s_tr = s_p = s_n = np.nan
    dx_hist = []
    adx_v = np.nan
    for i in range(len(c)):
        if np.isnan(tr[i]) or np.isnan(up[i]):
            s_tr = s_p = s_n = np.nan
            dx_hist, adx_v = [], np.nan
            continue
        if np.isnan(s_tr):
            s_tr, s_p, s_n = tr[i], pdm[i], ndm[i]
        else:
            s_tr = s_tr - s_tr / n + tr[i]
            s_p = s_p - s_p / n + pdm[i]
            s_n = s_n - s_n / n + ndm[i]
        if s_tr <= 0:
            continue
        pdi, ndi = 100 * s_p / s_tr, 100 * s_n / s_tr
        dx = 100 * abs(pdi - ndi) / (pdi + ndi) if pdi + ndi > 0 else 0.0
        if np.isnan(adx_v):
            dx_hist.append(dx)
            if len(dx_hist) >= n:
                adx_v = float(np.mean(dx_hist))
        else:
            adx_v = (adx_v * (n - 1) + dx) / n
        out[i] = adx_v
    return out


def rolling_max_prior(x, n):
    """max of the n values BEFORE i (NaN until n exist)."""
    out = np.full_like(x, np.nan)
    if len(x) > n:
        w = np.lib.stride_tricks.sliding_window_view(x, n)
        out[n:] = w[:-1].max(axis=1)
    return out


def rolling_min_prior(x, n):
    out = np.full_like(x, np.nan)
    if len(x) > n:
        w = np.lib.stride_tricks.sliding_window_view(x, n)
        out[n:] = w[:-1].min(axis=1)
    return out


def asof(t, k):
    """Index of the last k-hour bar completed when hour t has closed."""
    return (t + 1) // k - 1


# ---------------------------------------------------------------------------------------------------- market phase

def market_state(C, V, coins):
    """Per day: eligibility [day x coin], market phase (0 UP, 1 DOWN, 2 MIXED), BTC vol state (0 LOW, 1 HIGH)."""
    n_days = C.shape[0] // 24
    Cd = C[:n_days * 24].reshape(n_days, 24, -1)[:, -1, :]
    Vd = np.nansum(V[:n_days * 24].reshape(n_days, 24, -1), axis=1)
    Vd[np.isnan(Cd)] = np.nan
    avg = np.full_like(Vd, np.nan)
    cs = np.nancumsum(np.nan_to_num(Vd), axis=0)
    cnt = np.cumsum(~np.isnan(Vd), axis=0)
    for d in range(31, n_days):
        s = cs[d - 1] - cs[d - 31]
        c = cnt[d - 1] - cnt[d - 31]
        avg[d] = np.where(c >= 9, s / np.maximum(c, 1), np.nan)
    age = np.cumsum(~np.isnan(Cd), axis=0)
    elig = (avg >= CONFIG.exchange.min_24h_quote_volume_usd) & (age >= 100) & ~np.isnan(Cd)
    sma50 = np.vstack([sma(Cd[:, j], 50) for j in range(Cd.shape[1])]).T
    above = np.where(elig & ~np.isnan(sma50), (Cd > sma50).astype(float), np.nan)
    breadth = np.nanmean(above, axis=1)
    btc = Cd[:, coins.index('BTCUSDT')]
    btc200 = sma(btc, 200)
    phase = np.full(n_days, -1)
    ok = ~np.isnan(btc200) & ~np.isnan(breadth)
    up = btc > btc200
    wide = breadth >= 0.5
    phase[ok & up & wide] = 0
    phase[ok & ~up & ~wide] = 1
    phase[ok & (up != wide)] = 2
    lr = np.diff(np.log(btc), prepend=np.nan)
    rv = rolling_std(lr, 30)
    volstate = np.full(n_days, -1)
    for d in range(180, n_days):
        hist = rv[max(0, d - 365):d]
        hist = hist[~np.isnan(hist)]
        if len(hist) >= 150 and not np.isnan(rv[d]):
            volstate[d] = int(rv[d] > np.median(hist))
    return elig, phase, volstate, Cd


PHASES = {0: 'UP', 1: 'DOWN', 2: 'MIXED', -1: '?'}
VOLS = {0: 'low vol', 1: 'high vol', -1: '?'}


# ---------------------------------------------------------------------------------------------------- simulation

def simulate(j, e, d, entry, stop0, trail_atr=None, target=None, max_hold=336, exit_flag=None):
    """
    Walk one trade from the open of hour e: (exit hour, exit price, reason). d = +1 long / -1 short.
    trail_atr: chandelier distance (from the best high / low of the hours BEFORE the current one).
    exit_flag: bool array over hours; True at hour t = exit at the next hour's open.
    """
    O, H, L, C = G['O'][:, j], G['H'][:, j], G['L'][:, j], G['C'][:, j]
    last = min(len(C) - 1, e + max_hold - 1)
    seg = slice(e, last + 1)
    h, l, o, c = H[seg], L[seg], O[seg], C[seg]
    valid = ~np.isnan(c)
    if not valid.all():
        stop_at = int(np.argmin(valid))
        if stop_at == 0:
            return None
        h, l, o, c = h[:stop_at], l[:stop_at], o[:stop_at], c[:stop_at]
    n = len(c)
    if trail_atr:
        best = np.maximum.accumulate(h) if d > 0 else np.minimum.accumulate(l)
        prev_best = np.concatenate([[np.nan], best[:-1]])
        trail = prev_best - d * trail_atr
        stop = np.where(np.isnan(trail), stop0, np.maximum(stop0, trail) if d > 0 else np.minimum(stop0, trail))
    else:
        stop = np.full(n, stop0)
    hit_stop = (l <= stop) if d > 0 else (h >= stop)
    if target is not None:
        hit_tgt = (h >= target * (1 + THROUGH)) if d > 0 else (l <= target * (1 - THROUGH))
    else:
        hit_tgt = np.zeros(n, bool)
    if exit_flag is not None:
        flag = exit_flag[e:e + n].copy()
    else:
        flag = np.zeros(n, bool)
    i_stop = int(np.argmax(hit_stop)) if hit_stop.any() else n
    i_tgt = int(np.argmax(hit_tgt)) if hit_tgt.any() else n
    i_flag = int(np.argmax(flag)) + 1 if flag.any() else n      # exit at the NEXT hour's open
    i = min(i_stop, i_tgt, i_flag)
    if i >= n:
        return e + n - 1, float(c[-1]), 'time'
    if i == i_stop:                                             # a stop and a target in one hour: the stop
        s = stop[i]
        px = min(o[i], s) if d > 0 else max(o[i], s)
        if i == 0:
            px = s if (d > 0 and o[i] >= s) or (d < 0 and o[i] <= s) else o[i]
        return e + i, float(px), 'trail' if trail_atr and s != stop0 else 'stop'
    if i == i_tgt:
        return e + i, float(target), 'target'
    return e + i, float(o[i]), 'exit'


def funding_paid(j, d, t_in, t_out):
    f = G['funding'][j]
    if not len(f):
        return 0.0
    m = (f[:, 0] > t_in) & (f[:, 0] <= t_out)
    return float(d * f[m, 1].sum())


def record(out, j, strat, d, t_sig, e, entry, stop0, res):
    if res is None:
        return None
    x, px, why = res
    risk = abs(entry - stop0) / entry
    if risk <= 0:
        return None
    t0 = G['t0']
    fund = funding_paid(j, d, t0 + e * HOUR, t0 + (x + 1) * HOUR)
    gross = d * (px / entry - 1)
    C = G['C']
    day = asof(t_sig, 24)
    base = C[e - 1]
    mkt = C[x] / base - 1
    ok = G['elig'][day] & ~np.isnan(mkt)
    mean_mkt = float(np.nanmean(mkt[ok])) if ok.sum() >= 10 else np.nan
    out.append({
        'coin': G['coins'][j], 'strategy': strat, 'dir': 'long' if d > 0 else 'short', 'ts': t0 + e * HOUR,
        'hold_h': x - e + 1, 'reason': why, 'risk': risk, 'gross': gross, 'fund': fund,
        'net': gross - COST - fund, 'net_low': gross - LOW_COST - fund,
        'rel': d * ((px / entry - 1) - mean_mkt) - COST - fund if not np.isnan(mean_mkt) else np.nan,
        'phase': PHASES[int(G['phase'][day])], 'vol': VOLS[int(G['vol'][day])], 'coin_phase': G['cphase'][j][day],
    })
    return x


def coin_trades(j: int) -> List[Dict]:
    O, H, L, C = G['O'][:, j], G['H'][:, j], G['L'][:, j], G['C'][:, j]
    elig = G['elig'][:, j]
    if not elig.any():
        return []
    n = len(C)
    out: List[Dict] = []
    # --- timeframes
    o4, h4, l4, c4 = bars(O, H, L, C, 4)
    od, hd, ld, cd = bars(O, H, L, C, 24)
    ow, hw, lw, cw = bars(O, H, L, C, 168)
    e20_4, atr4 = ema(c4, 20), atr(h4, l4, c4, 14)
    mid4, sd4 = sma(c4, 20), rolling_std(c4, 20)
    e20d, e50d, adxd, n20 = ema(cd, 20), ema(cd, 50), adx(hd, ld, cd), atr(hd, ld, cd, 20)
    hi20, lo20, hi10, lo10 = rolling_max_prior(hd, 20), rolling_min_prior(ld, 20), rolling_max_prior(hd, 10), \
        rolling_min_prior(ld, 10)
    e13w = ema(cw, 13)
    cph = np.full(len(cd), '?', dtype=object)
    trend = adxd >= 25
    cph[trend & (e20d > e50d)] = 'trend up'
    cph[trend & (e20d < e50d)] = 'trend down'
    cph[adxd < 20] = 'range'
    cph[(adxd >= 20) & (adxd < 25)] = 'transition'
    G['cphase'][j] = cph

    hours = np.arange(n)
    f4, fd, fw = asof(hours, 4), asof(hours, 24), asof(hours, 168)
    okf = (f4 >= 1) & (fd >= 1) & (fw >= 1)
    fdc, fwc = np.clip(fd, 0, None), np.clip(fw, 0, None)
    el_h = np.where(okf, elig[np.clip(fdc, 0, len(elig) - 1)], False)

    prev3_hi = np.full(n, np.nan)
    prev3_lo = np.full(n, np.nan)
    w = np.lib.stride_tricks.sliding_window_view(H, 3)
    prev3_hi[3:] = w[:-1].max(axis=1)
    w = np.lib.stride_tricks.sliding_window_view(L, 3)
    prev3_lo[3:] = w[:-1].min(axis=1)
    low12 = np.full(n, np.nan)
    high12 = np.full(n, np.nan)
    w = np.lib.stride_tricks.sliding_window_view(L, 12)
    low12[11:] = w.min(axis=1)
    w = np.lib.stride_tricks.sliding_window_view(H, 12)
    high12[11:] = w.max(axis=1)

    def armed(flag4: np.ndarray, hours_armed: int) -> np.ndarray:
        """Hours within `hours_armed` after the close of a flagged 4h bar."""
        end_hour = np.where(flag4, np.arange(len(flag4)) * 4 + 3, -10 ** 9)
        last = np.maximum.accumulate(end_hour)
        per_hour = np.full(n, -10 ** 9)
        idx = np.clip(f4, 0, len(last) - 1)
        per_hour[f4 >= 0] = last[idx[f4 >= 0]]
        return (hours - per_hour >= 0) & (hours - per_hour < hours_armed)

    def take(signal: np.ndarray, d: int, strat: str, plan):
        busy_until = -1
        for t in np.flatnonzero(signal):
            if t <= busy_until or t + 1 >= n or np.isnan(O[t + 1]):
                continue
            p = plan(t)
            if p is None:
                continue
            x = record(out, j, strat, d, t, t + 1, O[t + 1], p['stop0'], simulate(j, t + 1, d, O[t + 1], **p))
            if x is not None:
                busy_until = x

    # --- TRIPLE
    wr = np.concatenate([[False], e13w[1:] > e13w[:-1]])
    wf = np.concatenate([[False], e13w[1:] < e13w[:-1]])
    tide_up = okf & wr[fwc] & (cd[fdc] > e50d[fdc])
    tide_dn = okf & wf[fwc] & (cd[fdc] < e50d[fdc])
    pb_long = armed(l4 <= e20_4, 24)
    pb_short = armed(h4 >= e20_4, 24)
    for d, sig in ((1, el_h & tide_up & pb_long & (C > prev3_hi)), (-1, el_h & tide_dn & pb_short & (C < prev3_lo))):
        def plan(t, d=d):
            a = atr4[f4[t]]
            entry = O[t + 1]
            if np.isnan(a) or a <= 0:
                return None
            ext = low12[t] - 0.5 * a if d > 0 else high12[t] + 0.5 * a
            stop = min(ext, entry - a) if d > 0 else max(ext, entry + a)
            return {'stop0': stop, 'trail_atr': 3 * a, 'max_hold': 336}
        take(sig, d, 'TRIPLE', plan)

    # --- TURTLE (daily closes; the signal hour is the day's last hour)
    day_end = (hours % 24 == 23) & okf
    brk_up = day_end & (cd[np.clip(asof(hours, 24), 0, None)] > hi20[fdc])
    brk_dn = day_end & (cd[fdc] < lo20[fdc])
    ex_long = np.zeros(n, bool)
    ex_short = np.zeros(n, bool)
    ex_long[day_end] = (cd[fdc] < lo10[fdc])[day_end]
    ex_short[day_end] = (cd[fdc] > hi10[fdc])[day_end]
    for d, sig, exf in ((1, el_h & brk_up, ex_long), (-1, el_h & brk_dn, ex_short)):
        def plan(t, d=d, exf=exf):
            nn = n20[fd[t]]
            if np.isnan(nn) or nn <= 0:
                return None
            stop = O[t + 1] - d * 2 * nn
            return {'stop0': stop, 'max_hold': 60 * 24, 'exit_flag': exf}
        take(sig, d, 'TURTLE', plan)

    # --- RANGE
    rng_d = okf & (adxd[fdc] < 20)
    below = armed(c4 < mid4 - 2 * sd4, 12)
    above = armed(c4 > mid4 + 2 * sd4, 12)
    prev_hi = np.concatenate([[np.nan], H[:-1]])
    prev_lo = np.concatenate([[np.nan], L[:-1]])
    for d, sig in ((1, el_h & rng_d & below & (C > prev_hi)), (-1, el_h & rng_d & above & (C < prev_lo))):
        def plan(t, d=d):
            a = atr4[f4[t]]
            tgt = mid4[f4[t]]
            entry = O[t + 1]
            if np.isnan(a) or a <= 0 or np.isnan(tgt) or d * (tgt - entry) <= 0:
                return None
            ext = low12[t] - 0.5 * a if d > 0 else high12[t] + 0.5 * a
            stop = min(ext, entry - a) if d > 0 else max(ext, entry + a)
            return {'stop0': stop, 'target': tgt, 'max_hold': 72}
        take(sig, d, 'RANGE', plan)
    return out


def _worker(j):
    try:
        return coin_trades(j)
    except Exception as e:                                        # one broken coin must not kill the run
        return [{'error': f"{G['coins'][j]}: {type(e).__name__} {e}"}]


# ---------------------------------------------------------------------------------------------------- statistics

def week_boot(vals: np.ndarray, weeks: np.ndarray, boot: int = 2000, seed: int = 11):
    """(mean, lo, hi, p one-sided mean<=0) with a bootstrap over calendar weeks."""
    if len(vals) < 10:
        return np.nan, np.nan, np.nan, np.nan
    uw, inv = np.unique(weeks, return_inverse=True)
    if len(uw) < 5:
        return float(vals.mean()), np.nan, np.nan, np.nan
    sums = np.bincount(inv, weights=vals)
    cnts = np.bincount(inv)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(uw), size=(boot, len(uw)))
    means = sums[idx].sum(axis=1) / cnts[idx].sum(axis=1)
    lo, hi = np.quantile(means, [0.05, 0.95])
    return float(vals.mean()), float(lo), float(hi), float((means <= 0).mean())


def bh(p: List[float]) -> List[float]:
    p = np.asarray(p, float)
    q = np.full_like(p, np.nan)
    ok = ~np.isnan(p)
    if not ok.any():
        return q.tolist()
    pv = p[ok]
    order = np.argsort(pv)
    m = len(pv)
    ranked = pv[order] * m / (np.arange(m) + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(ranked, 1)
    q[ok] = out
    return q.tolist()


def table(df, keys, title):
    rows = []
    for key, g in df.group_by(keys, maintain_order=True):
        r = (g['net'] / g['risk']).to_numpy()
        wk = (g['ts'].to_numpy() // (7 * 86_400_000)).astype(int)
        m, lo, hi, p = week_boot(r, wk)
        rel = g['rel'].drop_nans().drop_nulls().to_numpy()
        rows.append({'key': key, 'n': len(g), 'R': m, 'lo': lo, 'hi': hi, 'p': p,
                     'win': float((g['net'] > 0).mean()), 'net': float(g['net'].mean()),
                     'gross': float(g['gross'].mean()), 'net_low': float((g['net_low'] / g['risk']).mean()),
                     'rel': float(rel.mean()) if len(rel) else np.nan, 'hold': float(g['hold_h'].median()),
                     'risk': float(g['risk'].median())})
    qs = bh([r['p'] for r in rows])
    lines = [f"### {title}", '',
             '| ' + ' | '.join(keys) + ' | trades | win | net per trade | gross | vs mean | median stop | '
             'median hold | R net [90%] | q | R at 0.10% cost |',
             '|' + '---|' * len(keys) + '---:|---:|---:|---:|---:|---:|---:|---|---:|---:|']
    for r, q in zip(rows, qs):
        key = r['key'] if isinstance(r['key'], tuple) else (r['key'],)
        ci = f"{r['R']:+.3f} [{r['lo']:+.3f}..{r['hi']:+.3f}]" if not np.isnan(r['lo']) else \
            (f"{r['R']:+.3f} [—]" if not np.isnan(r['R']) else '—')
        lines.append('| ' + ' | '.join(str(k) for k in key) +
                     f" | {r['n']} | {r['win']:.0%} | {r['net'] * 100:+.2f}% | {r['gross'] * 100:+.2f}% | "
                     f"{r['rel'] * 100:+.2f}% | {r['risk'] * 100:.1f}% | {r['hold']:.0f}h | {ci} | "
                     f"{q:.3f} | {r['net_low']:+.3f} |" if not np.isnan(q) else
                     '| ' + ' | '.join(str(k) for k in key) +
                     f" | {r['n']} | {r['win']:.0%} | {r['net'] * 100:+.2f}% | {r['gross'] * 100:+.2f}% | "
                     f"{r['rel'] * 100:+.2f}% | {r['risk'] * 100:.1f}% | {r['hold']:.0f}h | {ci} | — | "
                     f"{r['net_low']:+.3f} |")
    return lines, rows, qs


def main():
    import polars as pl
    parser = argparse.ArgumentParser()
    parser.add_argument('--months', type=int, default=38)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument('--out', default=os.path.join('research', 'htf_phases.md'))
    parser.add_argument('--trades', default='')
    args = parser.parse_args()
    t0, coins, O, H, L, C, V, funding = load(args.months, args.limit)
    elig, phase, vol, _ = market_state(C, V, coins)
    G.update(t0=t0, coins=coins, O=O, H=H, L=L, C=C, elig=elig, phase=phase, vol=vol, funding=funding,
             cphase={})
    print(f"loaded {len(coins)} coins, {C.shape[0]} hours; eligible coin-days {int(elig.sum())}", flush=True)
    ctx = mp.get_context('fork')
    trades: List[Dict] = []
    with ctx.Pool(args.workers) as pool:
        for k, res in enumerate(pool.imap_unordered(_worker, range(len(coins)), chunksize=2)):
            trades.extend(res)
            if k % 50 == 0:
                print(f"  {k}/{len(coins)} coins, {len(trades)} trades", flush=True)
    errors = [t['error'] for t in trades if 'error' in t]
    trades = [t for t in trades if 'error' not in t]
    for e in errors[:10]:
        print('ERROR', e)
    df = pl.DataFrame(trades).sort('ts')
    if args.trades:
        df.write_parquet(args.trades)
    first_sig = df['ts'].min()
    last_sig = df['ts'].max()
    mid = first_sig + (last_sig - first_sig) // 2
    dev = df.filter(pl.col('ts') < mid)
    hold = df.filter(pl.col('ts') >= mid)
    def fmt(ms):
        return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime('%Y-%m-%d')

    lines = [f"# Higher-timeframe strategies by market phase ({len(coins)} coins, signals {fmt(first_sig)} .. "
             f"{fmt(last_sig)})", '',
             f"Rules, costs and the protocol: the docstring of `research_htf.py` (pre-registered). Net = after "
             f"{COST * 100:.2f}% round trip and funding. R = net / initial stop. 'vs mean' = minus the universe's "
             f"mean over the same hours. [90%] = bootstrap over calendar weeks; q = Benjamini-Hochberg over the "
             f"table's rows. Dev (picks the cells) = before {fmt(mid)}, holdout = from {fmt(mid)}.", '']
    if errors:
        lines += [f"{len(errors)} coins failed (first: {errors[0]})", '']
    keys = ['strategy', 'dir', 'phase']
    dl, drows, dq = table(dev, keys, 'Dev half: strategy x direction x market phase')
    hl, hrows, _ = table(hold, keys, 'Holdout half: the same cells (looked at once)')
    lines += dl + [''] + hl + ['']
    picked = [r['key'] for r, q in zip(drows, dq) if not np.isnan(q) and q <= 0.10 and r['R'] > 0]
    hmap = {r['key']: r for r in hrows}
    lines += ['## Verdict', '']
    if not picked:
        lines.append("No cell has a positive mean net R with q <= 0.10 on the dev half: nothing to confirm.")
    for k in picked:
        r = hmap.get(k)
        ok = r is not None and r['R'] > 0 and not np.isnan(r['lo']) and r['lo'] > 0
        lines.append(f"- {' / '.join(k)}: dev picked; holdout " +
                     (f"{r['R']:+.3f}R [{r['lo']:+.3f}..{r['hi']:+.3f}], {r['n']} trades -> "
                      f"{'PASSED' if ok else 'not confirmed'}" if r else 'no trades -> not confirmed'))
    lines.append('')
    for keys2, title in ((['strategy', 'dir', 'vol'], 'Whole window: by BTC volatility state'),
                         (['strategy', 'dir', 'coin_phase'], "Whole window: by the coin's own daily phase"),
                         (['strategy', 'dir', 'reason'], 'Whole window: by exit reason'),
                         (['strategy', 'dir'], 'Whole window: all phases')):
        tl, _, _ = table(df, keys2, title)
        lines += tl + ['']
    text = '\n'.join(lines) + '\n'
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)


if __name__ == '__main__':
    main()
