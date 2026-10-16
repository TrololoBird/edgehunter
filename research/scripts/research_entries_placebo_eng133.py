"""
eng-133: live entry classes vs a matched placebo, and the shadow tags / macro features (protocol:
research/PROTOCOL_entries_vs_placebo_eng133.md, written BEFORE the run; every number here follows it, nothing is tuned).

Input: replay.py output (data/replay/<run>/group_*/entries.parquet; needs the eng-133 columns tf / shadow_veto written by
replay.py). The placebo is rebuilt from the 1m archive: the same coin and direction, stop / targets in units of the
ATR(14) of the setup's timeframe measured at the PLACEBO's own entry, a random time shifted by 3..14 days either way
(never within +-48 h of the real trade), the 4h-trend sign and the ATR/price tercile equal to the real entry's; the same
exit rules and costs (levels.simulate + stats.net_r, as replay.run).

AUDIT 2026-10-16 (R04 / R07): what this measures is NARROW - R of a full exit at TP1 (r_tp1) of levels.simulate over
the 8h CONFIG.levels.trade_ttl_sec window, the same for the real entry and its placebo; NOT the cards' full result
(cards.final_r: the Turtles' channel, Connors' SMA5, BB1's SAR, W / M's band, partials). Its verdicts are about "the
entry with a fixed geometry over 8 hours". The bootstrap block = 12 NON-EMPTY 4h buckets as the protocol fixed it,
which is more than 48 calendar hours when signals are rare; changing it needs a protocol amendment before a run.

    python research/scripts/research_entries_placebo_eng133.py --run data/replay/eng133 --placebos 100 --seed 133 \
        --boot 5000 --workers 4 --out research/entries_placebo_eng133.md
Smoke test (server, < 1 GB):  --run data/replay/smoke --placebos 10 --boot 200 --workers 1 --out <scratch>/smoke.md

Decisions fixed here BEFORE the run (not in the protocol text): the ATR is our own simple-mean ATR(14) of the closed
bars of the setup's timeframe for the real entry and the placebo alike (the replay's tf_atr covers 1h / 4h / 1d only);
the placebo candidates are the tf bars of the shift window (uniform), at most --placebos of them without replacement
(fewer = placebo_n < K, reported); the placebo funding is the real entry's; terciles of ATR/price are per coin and tf
over the replayed period; the bucket sequence for the block bootstrap is the sorted list of non-empty 4h buckets, block
= 12 of them.
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702
import argparse
import csv
import glob
import io
import json
import math
import os
import urllib.request
from datetime import date, datetime, timedelta, timezone
from multiprocessing import Pool

import numpy as np
import polars as pl

H4 = 4 * 3_600_000
HOUR = 3_600_000
DAY = 86_400_000
MIN = 60_000
TF_MS = {'5m': 5 * MIN, '15m': 15 * MIN, '1h': HOUR, '4h': 4 * HOUR, '1d': DAY}
SHIFT_LO, SHIFT_HI, EXCL = 3 * DAY, 14 * DAY, 48 * HOUR
HORIZONS = (4, 8, 12, 24)
BLOCK = 12                                   # 48 h of 4h buckets
TRADFI = {'xau': 'XAUUSDT', 'oil': 'CLUSDT', 'spy': 'SPYUSDT', 'qqq': 'QQQUSDT'}


# ------------------------------------------------------------------------------------------------ bars / states
def bars_of(m: np.ndarray, ms: int) -> np.ndarray:
    from pretrain import _bucket
    return _bucket(m, ms)


def atr14(b: np.ndarray) -> np.ndarray:
    """Simple mean of the last 14 true ranges at every bar (NaN before 15 bars)."""
    out = np.full(len(b), np.nan)
    if len(b) < 15:
        return out
    pc = b[:-1, 4]
    tr = np.maximum(b[1:, 2] - b[1:, 3], np.maximum(np.abs(b[1:, 2] - pc), np.abs(b[1:, 3] - pc)))
    c = np.cumsum(np.r_[0.0, tr])
    out[14:] = (c[14:] - c[:-14]) / 14
    return out


def trend_signs(h4: np.ndarray) -> np.ndarray:
    """strategies.structure.coin_trend at every 4h bar (EMA(trend_ema) of the closes, slope over trend_slope_bars)."""
    from config import CONFIG
    n_ema, n_slope = CONFIG.strategies.trend_ema, CONFIG.strategies.trend_slope_bars
    out = np.zeros(len(h4), dtype=np.int8)
    if len(h4) < n_ema + n_slope:
        return out
    k = 2 / (n_ema + 1)
    cl = h4[:, 4]
    ema = np.empty(len(cl))
    ema[0] = cl[0]
    for i in range(1, len(cl)):
        ema[i] = ema[i - 1] + k * (cl[i] - ema[i - 1])
    slope = np.r_[np.full(n_slope, np.nan), ema[n_slope:] - ema[:-n_slope]]
    out[(cl > ema) & (slope > 0)] = 1
    out[(cl < ema) & (slope < 0)] = -1
    out[: n_ema + n_slope - 1] = 0
    return out


class CoinStates:
    """Per timeframe: the state after each bar closed (close time, ATR, ATR/price tercile, 4h-trend sign)."""

    def __init__(self, m: np.ndarray):
        self.m = m
        h4 = bars_of(m, H4)
        self.h4_close = h4[:, 0] + H4
        self.h4_trend = trend_signs(h4)
        self.tf = {}
        for tf, ms in TF_MS.items():
            b = bars_of(m, ms)
            if len(b) < 20:
                continue
            a = atr14(b)
            rel = a / b[:, 4]
            ok = np.isfinite(rel)
            q = np.quantile(rel[ok], [1 / 3, 2 / 3]) if ok.sum() > 10 else (np.inf, np.inf)
            terc = np.where(~ok, -1, np.digitize(rel, q))
            close_t = b[:, 0] + ms
            j4 = np.searchsorted(self.h4_close, close_t, side='right') - 1
            tr = np.where(j4 >= 0, self.h4_trend[np.clip(j4, 0, None)], 0)
            self.tf[tf] = dict(t=close_t, atr=a, terc=terc.astype(np.int8), trend=tr.astype(np.int8))

    def state_at(self, tf: str, t: float):
        s = self.tf.get(tf)
        if s is None:
            return None
        j = int(np.searchsorted(s['t'], t, side='right')) - 1
        if j < 0 or not np.isfinite(s['atr'][j]) or s['terc'][j] < 0:
            return None
        return s['atr'][j], int(s['terc'][j]), int(s['trend'][j])


def sim_net(m, ts, d, entry_px, sl, tps, limit, vol, symbol, funding, ttl):
    from levels import simulate
    from stats import net_r
    a = int(np.searchsorted(m[:, 0], ts, side='left'))
    b = int(np.searchsorted(m[:, 0], ts + ttl, side='left'))
    if b - a < 5:
        return None
    lv = {'entry': entry_px, 'sl': sl, 'tp1': tps[0], 'tp2': tps[1], 'tp3': tps[2], 'limit_entry': limit,
          'volume_24h': vol, 'symbol': symbol}
    res = simulate(lv, d, m[a:b, :6].tolist(), funding_8h=funding)
    if res.get('r_tp1') is None:
        return None
    return net_r({'r_tp1': res['r_tp1'], 'entry': entry_px, 'entry_fill': res.get('entry_fill'), 'sl': sl}, 'r_tp1')


def path_profile(m, ts, d, risk, tf_ms):
    """Mark-to-market net R and MFE (in R) at fixed horizons of the setup's bars, with no stop and no target."""
    from config import CONFIG
    a = int(np.searchsorted(m[:, 0], ts, side='left'))
    if a + 2 >= len(m) or not risk:
        return None
    fill = m[a, 1]
    fee_r = CONFIG.journal.fee_round_trip * fill / risk
    out = []
    for h in HORIZONS:
        n = min(int(h * tf_ms / MIN), len(m) - a)
        seg = m[a:a + n]
        if n < int(h * tf_ms / MIN):
            out.append((np.nan, np.nan))
            continue
        ext = seg[:, 2].max() if d > 0 else seg[:, 3].min()
        out.append((d * (seg[-1, 4] - fill) / risk - fee_r, d * (ext - fill) / risk))
    return out


def struct_r(m, ts, d, atr_stop_level, sl, tf, ttl):
    """BB W-BOTTOM / M-TOP structural exit: the first 1m touch of the SMA20 of the tf closes known at the entry (else
    the stop, else the mark at the end of the lifetime); net of the fee."""
    from config import CONFIG
    b = bars_of(m[: int(np.searchsorted(m[:, 0], ts, side='left'))], TF_MS[tf])
    if len(b) < 20:
        return None
    target = b[-20:, 4].mean()
    a = int(np.searchsorted(m[:, 0], ts, side='left'))
    seg = m[a:int(np.searchsorted(m[:, 0], ts + ttl, side='left'))]
    if len(seg) < 5:
        return None
    fill = seg[0, 1]
    risk = abs(fill - sl)
    if not risk or d * (target - fill) <= 0 or d * (fill - sl) <= 0:
        return None
    exit_px = seg[-1, 4]
    for row in seg:
        if (row[3] <= sl) if d > 0 else (row[2] >= sl):
            exit_px = sl
            break
        if (row[2] >= target) if d > 0 else (row[3] <= target):
            exit_px = target
            break
    return d * (exit_px - fill) / risk - CONFIG.journal.fee_round_trip * fill / risk


# ------------------------------------------------------------------------------------------------ per-coin worker
def process_symbol(job):
    """All entries of one coin: the real structural exit / profile and K placebo copies. Returns plain row dicts."""
    from history import Archive
    from config import CONFIG
    symbol, rows, K, seed, start, end, rate = job
    fid = symbol.split('/')[0] + 'USDT'
    arch = Archive(rate_bytes=rate)
    m = arch.klines_1m('futures', fid, start, end)
    if len(m) < 1440 * 20:
        return [], [], [], None
    st = CoinStates(m)
    h1 = bars_of(m, HOUR)
    hourly = (symbol, h1[:, 0].astype(np.int64), h1[:, 4])
    ttl = CONFIG.levels.trade_ttl_sec * 1000
    pl_rows, real_rows, prof_rows = [], [], []
    for r in rows:
        tf, ts, d = r['tf'], int(r['ts']), int(r['direction'])
        s = st.state_at(tf, ts)
        if s is None:
            continue
        atr_r, terc_r, tr_r = s
        entry, sl = r['entry'], r['sl']
        k_sl = abs(entry - sl) / atr_r
        k_tp = [abs(t - entry) / atr_r if t is not None else None for t in (r['tp1'], r['tp2'], r['tp3'])]
        sp = st.tf[tf]
        t_c = sp['t']
        dt = t_c - ts
        win = ((dt >= SHIFT_LO) & (dt <= SHIFT_HI)) | ((dt <= -SHIFT_LO) & (dt >= -SHIFT_HI))
        win &= (np.abs(dt) > EXCL) & np.isfinite(sp['atr']) & (sp['terc'] == terc_r) & (sp['trend'] == tr_r)
        win &= (t_c > m[0, 0] + 2 * DAY) & (t_c + ttl < m[-1, 0])
        cand = np.flatnonzero(win)
        rng = np.random.default_rng([seed, int(r['_i'])])
        pick = rng.choice(cand, size=min(K, len(cand)), replace=False) if len(cand) else cand
        for c, j in enumerate(pick):
            tp_ = float(t_c[j])
            a = int(np.searchsorted(m[:, 0], tp_, side='left'))
            px = m[a - 1, 4]
            atr_p = sp['atr'][j]
            sl_p = px - d * k_sl * atr_p
            tps = [px + d * k * atr_p if k is not None else None for k in k_tp]
            x = sim_net(m, tp_, d, px, sl_p, tps, r['limit_entry'], r['volume_24h'], symbol, r['funding'], ttl)
            if x is None:
                continue
            pl_rows.append({'_i': r['_i'], 'copy': c, 'r': x})
            if c < 10:
                pp = path_profile(m, tp_, d, k_sl * atr_p, TF_MS[tf])
                if pp:
                    prof_rows.append({'_i': r['_i'], 'who': 'placebo', 'pp': pp})
                if r['setup'] in ('BB W-BOTTOM', 'BB M-TOP'):
                    xs = struct_r(m, tp_, d, None, sl_p, tf, ttl)
                    if xs is not None:
                        prof_rows.append({'_i': r['_i'], 'who': 'placebo_struct', 'pp': xs})
        pp = path_profile(m, ts, d, abs(entry - sl), TF_MS[tf])
        if pp:
            prof_rows.append({'_i': r['_i'], 'who': 'real', 'pp': pp})
        if r['setup'] in ('BB W-BOTTOM', 'BB M-TOP'):
            xs = struct_r(m, ts, d, None, sl, tf, ttl)
            if xs is not None:
                prof_rows.append({'_i': r['_i'], 'who': 'real_struct', 'pp': xs})
        real_rows.append({'_i': r['_i'], 'placebo_n': len(pick)})
    return pl_rows, real_rows, prof_rows, hourly


# ------------------------------------------------------------------------------------------------ statistics
def boot_idx(n, rng, n_boot):
    """Moving-block bootstrap indices: n_boot x n, blocks of BLOCK consecutive buckets."""
    nb = math.ceil(n / BLOCK)
    starts = rng.integers(0, max(n - BLOCK + 1, 1), size=(n_boot, nb))
    idx = (starts[:, :, None] + np.arange(BLOCK)[None, None, :]).reshape(n_boot, -1)[:, :n]
    return np.minimum(idx, n - 1)


def newey_west_p(x, lag):
    """One-sided p of mean(x) > 0 with a Bartlett-kernel HAC standard error."""
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 5:
        return 1.0
    mu = x.mean()
    e = x - mu
    v = (e * e).mean()
    for k in range(1, min(lag, n - 1) + 1):
        v += 2 * (1 - k / (lag + 1)) * (e[k:] * e[:-k]).mean()
    se = math.sqrt(max(v, 1e-12) / n)
    return 0.5 * math.erfc((mu / se) / math.sqrt(2))


def bucket_series(ts, vals):
    """Mean per non-empty 4h bucket, in time order."""
    b = (np.asarray(ts) // H4).astype(np.int64)
    order = np.argsort(b, kind='stable')
    b, v = b[order], np.asarray(vals, dtype=float)[order]
    u, start = np.unique(b, return_index=True)
    sums = np.add.reduceat(v, start)
    cnt = np.diff(np.r_[start, len(v)])
    return u, sums / cnt


def contrast(ts_a, v_a, ts_b, v_b, rng, n_boot, lag):
    """mean(A) - mean(B) over 4h buckets (A, B may be the real and the placebo series of the same entries, or two
    disjoint groups); 48 h moving-block bootstrap on the union of the buckets. Returns a dict or None (< 30 buckets)."""
    ua, xa = bucket_series(ts_a, v_a) if len(ts_a) else (np.array([], dtype=np.int64), np.array([]))
    ub, xb = bucket_series(ts_b, v_b) if len(ts_b) else (np.array([], dtype=np.int64), np.array([]))
    grid = np.union1d(ua, ub)
    A = np.full(len(grid), np.nan)
    B = np.full(len(grid), np.nan)
    A[np.searchsorted(grid, ua)] = xa
    B[np.searchsorted(grid, ub)] = xb
    if min(len(ua), len(ub)) < 30:
        return None
    idx = boot_idx(len(grid), rng, n_boot)
    with np.errstate(all='ignore'):
        ma = np.nanmean(A[idx], axis=1)
        mb = np.nanmean(B[idx], axis=1)
    diff = ma - mb
    d0 = np.nanmean(A) - np.nanmean(B)
    both = np.where(np.isfinite(A) & np.isfinite(B), A - B, np.nan)
    p_boot = float((diff <= 0).mean())                  # one-sided: A > B
    p_nw = newey_west_p(both if np.isfinite(both).sum() >= 30 else (A - np.nanmean(B)), lag)
    return dict(a=float(np.nanmean(A)), b=float(np.nanmean(B)), diff=float(d0), n_b=int(len(ua)),
                lo=float(np.percentile(diff, 5)), hi=float(np.percentile(diff, 95)),
                lo_a=float(np.percentile(ma, 5)), hi_a=float(np.percentile(ma, 95)),
                p=max(p_boot, p_nw), p_lo=max(1 - p_boot, 1 - p_nw))   # stricter of the two in each direction


def bh(pvals):
    """Benjamini-Hochberg adjusted q-values."""
    p = np.asarray(pvals, dtype=float)
    n = len(p)
    if n == 0:
        return p
    order = np.argsort(p)
    q = np.empty(n)
    run = 1.0
    for rank, i in enumerate(order[::-1]):
        k = n - rank
        run = min(run, p[i] * n / k)
        q[i] = run
    return q


# ------------------------------------------------------------------------------------------------ macro features
def _get(url, cache):
    if os.path.exists(cache):
        return open(cache, 'rb').read()
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    data = urllib.request.urlopen(req, timeout=60).read()
    open(cache, 'wb').write(data)
    return data


class Macro:
    """Offline rebuild of the shadow features exactly as the live bot journals them (extdata.py)."""

    def __init__(self, cache, etf_file, start, end, arch):
        os.makedirs(cache, exist_ok=True)
        from extdata import etf_flows_visible, us_session
        self._etf_vis, self._us = etf_flows_visible, us_session
        self.etf = json.load(open(etf_file)) if etf_file and os.path.exists(etf_file) else {}
        self.vix = {}
        try:
            txt = _get('https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv',
                       os.path.join(cache, 'vix.csv')).decode('utf-8')
            for r in csv.DictReader(io.StringIO(txt)):
                self.vix[datetime.strptime(r['DATE'], '%m/%d/%Y').strftime('%Y-%m-%d')] = float(r['CLOSE'])
        except Exception as e:
            print('VIX unavailable:', e)
        self.fng = {}
        try:
            d = json.loads(_get('https://api.alternative.me/fng/?limit=0', os.path.join(cache, 'fng.json')))
            for r in d['data']:
                self.fng[datetime.fromtimestamp(int(r['timestamp']), timezone.utc).strftime('%Y-%m-%d')] = float(r['value'])
        except Exception as e:
            print('Fear & Greed unavailable:', e)
        self.dxy = {}
        try:
            txt = _get('https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTWEXBGS',
                       os.path.join(cache, 'dtwexbgs.csv')).decode('utf-8')
            for r in csv.reader(io.StringIO(txt)):
                try:
                    self.dxy[r[0]] = float(r[1])
                except ValueError:
                    pass
        except Exception as e:
            print('DXY unavailable:', e)
        self.dxy_days = sorted(self.dxy)
        self.tf = {}
        for k, sym in TRADFI.items():
            try:
                m = arch.klines_1m('futures', sym, start - timedelta(days=3), end)
                b = bars_of(m, HOUR) if len(m) else np.empty((0, 8))
                self.tf[k] = (b[:, 0] + HOUR, b[:, 4])           # (close time, close) of CLOSED 1h candles
            except Exception as e:
                print(f'{sym} unavailable:', e)

    def features(self, ts_ms):
        t = ts_ms / 1000
        day = datetime.fromtimestamp(t, timezone.utc).strftime('%Y-%m-%d')
        out = {}
        dow, hr = datetime.fromtimestamp(t, timezone.utc).weekday(), datetime.fromtimestamp(t, timezone.utc).hour
        cme_closed = dow == 5 or (dow == 6 and hr < 22) or (dow == 4 and hr >= 21)
        sess = self._us(t)
        for k, (tc, cl) in self.tf.items():
            j = int(np.searchsorted(tc, ts_ms, side='right')) - 1       # the last CLOSED 1h candle
            ok = j >= 25
            c1 = cl[j] / cl[j - 1] - 1 if ok else np.nan
            c24 = cl[j] / cl[j - 24] - 1 if ok else np.nan
            masked = cme_closed if k in ('xau', 'oil') else (sess != 1)
            out[f'{k}_chg_1h'] = np.nan if masked or not ok else c1 * 100
            out[f'{k}_chg_24h'] = np.nan if masked or not ok else c24 * 100
        prev = [d for d in self.vix if d < day]
        out['vix_prev'] = self.vix[max(prev)] if prev else np.nan
        out['fng'] = self.fng.get(day, np.nan)
        f1, f3 = self._etf_vis(self.etf, t) if self.etf else (None, None)
        out['etf_flow_1d'] = np.nan if f1 is None else f1
        out['etf_flow_3d'] = np.nan if f3 is None else f3
        days = [d for d in self.dxy_days if d < day]
        out['dxy_chg_1d'] = ((self.dxy[days[-1]] / self.dxy[days[-2]] - 1) * 100) if len(days) >= 2 else np.nan
        return out


# ------------------------------------------------------------------------------------------------ main
def fmt(x, nd=3):
    return '—' if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{x:+.{nd}f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True)
    ap.add_argument('--placebos', type=int, default=100)
    ap.add_argument('--seed', type=int, default=133)
    ap.add_argument('--boot', type=int, default=5000)
    ap.add_argument('--workers', type=int, default=1)
    ap.add_argument('--rate', type=float, default=2e6)
    ap.add_argument('--etf-file', default='etf_flows.json')
    ap.add_argument('--macro-cache', default=os.path.join('data', 'macro_cache'))
    ap.add_argument('--no-macro', action='store_true')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    from config import CONFIG
    from history import Archive

    frames = [pl.read_parquet(p) for p in sorted(glob.glob(os.path.join(args.run, 'group_*', 'entries.parquet')))]
    if not frames:
        raise SystemExit('no entries.parquet under ' + args.run)
    e = pl.concat(frames, how='diagonal_relaxed')
    for col in ('tf', 'shadow_veto'):
        if col not in e.columns:
            raise SystemExit(f"entries.parquet has no '{col}': re-run replay.py with the eng-133 columns")
    e = e.filter((pl.col('stage') == 'entry') & pl.col('vetoed').is_null() & pl.col('r_tp1').is_not_null() &
                 pl.col('entry').is_not_null() & pl.col('sl').is_not_null() & pl.col('tf').is_not_null() &
                 pl.col('tp1').is_not_null() & pl.col('tf').is_in(list(TF_MS)))
    e = e.sort('ts').with_row_index('_i')
    if e.is_empty():
        raise SystemExit('no usable entries')
    ttl = CONFIG.levels.trade_ttl_sec * 1000
    t_min, t_max = int(e['ts'].min()), int(e['ts'].max())
    mid = t_min + (t_max - t_min) // 2
    start = datetime.fromtimestamp(t_min / 1000, timezone.utc).date() - timedelta(days=16)
    end = datetime.fromtimestamp(t_max / 1000, timezone.utc).date() + timedelta(days=16)
    end = min(end, date.today() - timedelta(days=1))
    half = np.where(e['ts'].to_numpy() + ttl <= mid, 'dev', np.where(e['ts'].to_numpy() >= mid + EXCL, 'holdout', 'purged'))
    e = e.with_columns(pl.Series('half', half))
    print(f"{e.height} entries; dev {int((half == 'dev').sum())}, holdout {int((half == 'holdout').sum())}, "
          f"purged {int((half == 'purged').sum())}; split at {datetime.fromtimestamp(mid / 1000, timezone.utc):%Y-%m-%d}")

    jobs = []
    cols = ['_i', 'ts', 'setup', 'direction', 'entry', 'sl', 'tp1', 'tp2', 'tp3', 'tf', 'limit_entry', 'volume_24h', 'funding']
    for sym, g in e.filter(pl.col('half') != 'purged').group_by('symbol'):
        jobs.append((sym[0], g.select(cols).to_dicts(), args.placebos, args.seed, start, end, args.rate))
    if args.workers > 1:
        with Pool(args.workers) as pool:
            outs = pool.map(process_symbol, jobs, chunksize=1)
    else:
        outs = [process_symbol(j) for j in jobs]
    pl_rows = [r for o in outs for r in o[0]]
    real_meta = [r for o in outs for r in o[1]]
    prof = [r for o in outs for r in o[2]]
    hourly = [o[3] for o in outs if o[3] is not None]
    pdf = pl.DataFrame(pl_rows) if pl_rows else pl.DataFrame({'_i': [], 'copy': [], 'r': []})
    meta = pl.DataFrame(real_meta) if real_meta else pl.DataFrame({'_i': [], 'placebo_n': []})
    pdf.write_parquet(os.path.splitext(args.out)[0] + '_placebo.parquet')

    d = e.join(meta, on='_i', how='inner').filter(pl.col('placebo_n') > 0)
    K = args.placebos
    macro_cols = []
    if not args.no_macro:
        mac = Macro(args.macro_cache, args.etf_file, start, end, Archive(rate_bytes=args.rate))
        feats = [mac.features(int(t)) for t in d['ts'].to_list()]
        macro_cols = list(feats[0]) if feats else []
        d = d.with_columns([pl.Series(k, [f[k] for f in feats], dtype=pl.Float64) for k in macro_cols])
    rng = np.random.default_rng(args.seed)

    # placebo net R per entry and copy -> matrix (copy k of an entry with fewer copies repeats its draws)
    pm = {}
    for i, grp in pdf.group_by('_i'):
        pm[int(i[0])] = grp.sort('copy')['r'].to_numpy()
    ids = d['_i'].to_numpy()
    PM = np.full((len(ids), K), np.nan)
    for row, i in enumerate(ids):
        v = pm.get(int(i))
        if v is not None and len(v):
            PM[row] = v[np.arange(K) % len(v)]
    keep = np.isfinite(PM).all(axis=1)
    d = d.filter(pl.Series(keep))
    PM = PM[keep]
    ts_all = d['ts'].to_numpy()
    R = d['r_tp1'].to_numpy().astype(float)
    pl_mean = PM.mean(axis=1)
    half_arr = d['half'].to_numpy()
    lifetime_b = max(BLOCK, math.ceil(0.9 * ttl / H4))

    # ---- families
    out = []
    fam_rows, p_all, tags = [], [], []
    for setup in sorted(set(d['setup'].to_list())):
        res = {}
        for h in ('dev', 'holdout'):
            sel = (d['setup'].to_numpy() == setup) & (half_arr == h)
            if sel.sum() == 0:
                res[h] = None
                continue
            c = contrast(ts_all[sel], R[sel], ts_all[sel], pl_mean[sel], rng, args.boot, lifetime_b)
            if c is not None:
                p90 = float(np.percentile([bucket_series(ts_all[sel], PM[sel, k])[1].mean() for k in range(K)], 90))
                c['p90'] = p90
                c['n'] = int(sel.sum())
            res[h] = c
        fam_rows.append((setup, res))
        if res.get('holdout'):
            p_all.append(res['holdout']['p'])
            tags.append(('fam', setup))

    # ---- shadow tags (with vs without) and macro features (top vs bottom tercile), real net R
    tag_rows, feat_rows = [], []
    sv = d['shadow_veto'].to_list()
    alltags = sorted({t for s in sv if s for t in s.split(',')})
    for tg in alltags:
        has = np.array([bool(s) and tg in s.split(',') for s in sv])
        res = {}
        for h in ('dev', 'holdout'):
            hs = half_arr == h
            res[h] = contrast(ts_all[hs & has], R[hs & has], ts_all[hs & ~has], R[hs & ~has], rng, args.boot, lifetime_b)
        tag_rows.append((tg, res))
        if res.get('holdout'):
            p_all.append(min(1.0, 2 * min(res['holdout']['p'], res['holdout']['p_lo'])))
            tags.append(('tag', tg))
    for col in macro_cols:
        v = d[col].to_numpy().astype(float)
        dev = (half_arr == 'dev') & np.isfinite(v)
        if dev.sum() < 60:
            feat_rows.append((col, None))
            continue
        lo_b, hi_b = np.quantile(v[dev], [1 / 3, 2 / 3])
        res = {}
        for h in ('dev', 'holdout'):
            hs = (half_arr == h) & np.isfinite(v)
            top, bot = hs & (v >= hi_b), hs & (v <= lo_b)
            res[h] = contrast(ts_all[top], R[top], ts_all[bot], R[bot], rng, args.boot, lifetime_b)
        res['bounds'] = (float(lo_b), float(hi_b))
        feat_rows.append((col, res))
        if res.get('holdout'):
            p_all.append(min(1.0, 2 * min(res['holdout']['p'], res['holdout']['p_lo'])))
            tags.append(('feat', col))
    q = dict(zip(tags, bh(p_all)))

    def verdict_family(res, qv):
        a, b = res.get('dev'), res.get('holdout')
        if not a or not b:
            return 'no verdict (< 30 buckets)'
        ok = (a['a'] > 0.05 and b['a'] > 0.05 and a['a'] > a['p90'] and b['a'] > b['p90'] and qv <= 0.05 and
              np.sign(a['diff']) == np.sign(b['diff']))
        return 'PASS' if ok else 'no evidence'

    def verdict_contrast(res, qv):
        a, b = res.get('dev') if res else None, res.get('holdout') if res else None
        if not a or not b:
            return 'no verdict (< 30 buckets)'
        return 'PASS' if (np.sign(a['diff']) == np.sign(b['diff']) and qv <= 0.05) else 'no evidence'

    out.append("# Entries vs placebo, shadow tags and macro features (eng-133 protocol)\n")
    out.append(f"Run `{args.run}`; {len(d)} entries with a placebo ({e.height} usable, "
               f"{int((half_arr == 'dev').sum())} dev / {int((half_arr == 'holdout').sum())} holdout after the purge), "
               f"split {datetime.fromtimestamp(mid / 1000, timezone.utc):%Y-%m-%d}; K = {K} copies, seed {args.seed}, "
               f"{args.boot} bootstrap draws, block = {BLOCK} buckets (48 h); lifetime lag for Newey-West = {lifetime_b}.\n")
    out.append("## Families (net R at TP1 with the replay's exits; real minus placebo; 90% intervals)\n")
    out.append("| Setup | part | n | buckets | mean R [90%] | placebo mean | P90 placebo | real - placebo [90%] | q (holdout) | verdict |")
    out.append("|---|---|---:|---:|---|---:|---:|---|---:|---|")
    for setup, res in fam_rows:
        qv = q.get(('fam', setup), 1.0)
        vd = verdict_family(res, qv)
        for h in ('dev', 'holdout'):
            c = res.get(h)
            if not c:
                out.append(f"| {setup} | {h} | — | < 30 | — | — | — | — | — | {vd if h == 'holdout' else ''} |")
                continue
            out.append(f"| {setup} | {h} | {c['n']} | {c['n_b']} | {fmt(c['a'])} [{fmt(c['lo_a'])}..{fmt(c['hi_a'])}] | "
                       f"{fmt(c['b'])} | {fmt(c['p90'])} | {fmt(c['diff'])} [{fmt(c['lo'])}..{fmt(c['hi'])}] | "
                       f"{('%.3f' % qv) if h == 'holdout' else ''} | {vd if h == 'holdout' else ''} |")
    out.append("\n## Shadow tags (entries with the tag minus entries without; real net R)\n")
    out.append("| tag | part | with | without | diff [90%] | q (holdout) | verdict |")
    out.append("|---|---|---:|---:|---|---:|---|")
    for tg, res in tag_rows:
        qv = q.get(('tag', tg), 1.0)
        for h in ('dev', 'holdout'):
            c = res.get(h)
            out.append(f"| {tg} | {h} | {fmt(c['a']) if c else '—'} | {fmt(c['b']) if c else '—'} | "
                       f"{(fmt(c['diff']) + ' [' + fmt(c['lo']) + '..' + fmt(c['hi']) + ']') if c else '—'} | "
                       f"{('%.3f' % qv) if h == 'holdout' else ''} | {verdict_contrast(res, qv) if h == 'holdout' else ''} |")
    out.append("\n## Macro features (top tercile minus bottom tercile of the dev-half bounds; real net R)\n")
    out.append("| feature | bounds (dev terciles) | part | top | bottom | diff [90%] | q (holdout) | verdict |")
    out.append("|---|---|---|---:|---:|---|---:|---|")
    for col, res in feat_rows:
        if not res:
            out.append(f"| {col} | — | — | — | — | — | — | no verdict (too few values) |")
            continue
        qv = q.get(('feat', col), 1.0)
        for h in ('dev', 'holdout'):
            c = res.get(h)
            out.append(f"| {col} | {res['bounds'][0]:.3g} / {res['bounds'][1]:.3g} | {h} | {fmt(c['a']) if c else '—'} | "
                       f"{fmt(c['b']) if c else '—'} | {(fmt(c['diff']) + ' [' + fmt(c['lo']) + '..' + fmt(c['hi']) + ']') if c else '—'} | "
                       f"{('%.3f' % qv) if h == 'holdout' else ''} | {verdict_contrast(res, qv) if h == 'holdout' else ''} |")

    # ---- descriptive extras (not pass-rule items)
    out.append("\n## Descriptive: horizon profile (no stop, no target; mark-to-market net R and MFE in R at 4 / 8 / 12 / 24 bars of the setup's timeframe; first 10 placebo copies)\n")
    out.append("| who | horizon (bars) | n | net R mean | MFE p25 | MFE p50 | MFE p75 |")
    out.append("|---|---:|---:|---:|---:|---:|---:|")
    for who in ('real', 'placebo'):
        arr = [r['pp'] for r in prof if r['who'] == who]
        for hi, h in enumerate(HORIZONS):
            net = np.array([p[hi][0] for p in arr if np.isfinite(p[hi][0])])
            mfe = np.array([p[hi][1] for p in arr if np.isfinite(p[hi][1])])
            if len(net):
                out.append(f"| {who} | {h} | {len(net)} | {fmt(net.mean())} | {fmt(np.percentile(mfe, 25))} | "
                           f"{fmt(np.percentile(mfe, 50))} | {fmt(np.percentile(mfe, 75))} |")
    out.append("\n## Descriptive: structural exit (BB W-BOTTOM / M-TOP: first touch of the SMA20; VA80 / AUCTION: POC not in the replay output, not computed)\n")
    for who in ('real_struct', 'placebo_struct'):
        v = np.array([r['pp'] for r in prof if r['who'] == who])
        out.append(f"- {who}: n = {len(v)}, mean net R = {fmt(v.mean()) if len(v) else '—'}")
    out.append("\n## Descriptive: counterfactual Cluster Cap (<= 2 cards of one side per 4h window, top by rr_tp1; NOT for production)\n")
    dd = d.with_columns((pl.col('ts') // H4).alias('_b')).sort('ts')
    capped = (dd.sort('rr_tp1', descending=True, nulls_last=True).group_by(['_b', 'direction'], maintain_order=True)
              .head(2).sort('ts'))
    for name, frame in (('without cap', dd), ('with cap', capped)):
        r = frame['r_tp1'].to_numpy().astype(float)
        cum = np.cumsum(r)
        dd_max = float((np.maximum.accumulate(cum) - cum).max()) if len(r) else 0.0
        out.append(f"- {name}: n = {len(r)}, mean = {fmt(r.mean()) if len(r) else '—'}, total = {fmt(r.sum(), 1)}, max drawdown = {dd_max:.1f} R")
    out.append("\n## Descriptive: measured correlation (pairwise mean of the replayed coins' 1h log returns) and N_eff\n")
    rho = float('nan')
    if len(hourly) >= 3:
        t0 = min(h[1][0] for h in hourly)
        t1 = max(h[1][-1] for h in hourly)
        grid = np.full((len(hourly), int((t1 - t0) // HOUR) + 1), np.nan)
        for i, (_, ht, hc) in enumerate(hourly):
            grid[i, ((ht - t0) // HOUR).astype(int)] = hc
        ret = np.diff(np.log(grid), axis=1)
        ok = np.isfinite(ret).all(axis=0)
        if ok.sum() > 100:
            cm = np.corrcoef(ret[:, ok])
            rho = float((cm.sum() - len(cm)) / (len(cm) * (len(cm) - 1)))
    out.append(f"- mean pairwise correlation of 1h returns across {len(hourly)} coins: rho = {fmt(rho)}")
    n_win = dd.group_by(['_b', 'direction']).len()['len'].to_numpy()
    nm = float(n_win.mean())
    out.append(f"- same-side entries per 4h window: mean {nm:.2f}, p90 {np.percentile(n_win, 90):.0f}, max {n_win.max()}; "
               f"N_eff at the mean N = {nm / (1 + (nm - 1) * rho) if math.isfinite(rho) else float('nan'):.2f}")
    out.append("\n## Counts\n")
    out.append(f"- placebo copies per entry: mean {meta['placebo_n'].mean():.1f}; entries without any placebo: "
               f"{e.filter(pl.col('half') != 'purged').height - meta.height}; entries with < {K}: "
               f"{int((meta['placebo_n'] < K).sum())}")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out) + '\n')
    print('written', args.out)


if __name__ == '__main__':
    main()
