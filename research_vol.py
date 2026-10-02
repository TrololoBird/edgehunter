"""
B1 of ML_PLAN.md (pre-registered in research/prereg/B1_volatility.md): forecast the realized variance of the next
1h / 4h of every coin and compare the bot's ATR stop unit, HAR-RV and LightGBM out of sample.

Per coin (worker processes): the futures 1m archive -> at every hour close h (eligible days only)
    target  rv1 = sum of squared 1m log returns over (h, h + 1h], rv4 over (h, h + 4h]
    HAR     log rv of the last 1h, 4h, 24h, 7d (per-hour averages)
    ATR     ATR14 of 15m candles / close, max(ATR14, the last hour's 15m ATR) / close
    extra   |log return| 1h / 4h / 24h, log(volume of the last hour / its 7-day hourly mean), distance of the close
            to the 24h high / low in log units, hour of day (sin / cos), weekend
BTC's HAR lags and the universe's median log RV of the last hour are joined in the main process.

    python research_vol.py --workers 4            # all coins, writes research/vol_b1.md
"""
import argparse
import logging
import math
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, datetime, timezone
from typing import Dict, Optional

import numpy as np
import polars as pl

logger = logging.getLogger('research_vol')
MIN_MS, H_MS = 60_000, 3_600_000
START, SPLIT, END = date(2025, 4, 3), date(2026, 4, 1), date(2026, 9, 30)
_ROOT = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(_ROOT, 'research', 'vol_b1.md')
ROWS_PATH = os.path.join(_ROOT, 'research_vol_rows.parquet')
HAR = ['lrv_1h', 'lrv_4h', 'lrv_24h', 'lrv_7d']


def _ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def coin_rows(job) -> Optional[pl.DataFrame]:
    key, fut_id, days_ok, start, end = job        # the window travels with the job (worker processes re-import)
    from history import Archive
    days_ok = set(days_ok)
    m = Archive(rate_bytes=4e7).klines_1m('futures', fut_id, start, end)
    if len(m) < 1440 * 30:
        return None
    ts = m[:, 0].astype(np.int64)
    # a complete minute grid (missing minutes: no return, the variance of the gap lands on the next minute)
    t0 = ts[0] // H_MS * H_MS
    n = int((ts[-1] - t0) // MIN_MS) + 1
    pos = ((ts - t0) // MIN_MS).astype(np.int64)
    close = np.full(n, np.nan)
    close[pos] = m[:, 4]
    high = np.full(n, np.nan)
    high[pos] = m[:, 2]
    low = np.full(n, np.nan)
    low[pos] = m[:, 3]
    vol = np.zeros(n)
    vol[pos] = m[:, 6]
    filled = pl.Series(close).fill_nan(None).fill_null(strategy='forward').to_numpy().copy()
    filled[np.isnan(filled)] = filled[~np.isnan(filled)][0]
    r2 = np.r_[0.0, np.diff(np.log(filled)) ** 2]
    hours = n // 60
    rv_h = r2[:hours * 60].reshape(hours, 60).sum(axis=1)               # variance of each hour
    vol_h = vol[:hours * 60].reshape(hours, 60).sum(axis=1)
    c_h = filled[59:hours * 60:60]
    hi_h = np.fmax.reduce(np.nan_to_num(high[:hours * 60], nan=-np.inf).reshape(hours, 60), axis=1)
    lo_h = np.fmin.reduce(np.nan_to_num(low[:hours * 60], nan=np.inf).reshape(hours, 60), axis=1)
    # 15m true ranges for ATR14 / the last hour's ATR
    q = hours * 4
    hq = np.fmax.reduce(np.nan_to_num(high[:q * 15], nan=-np.inf).reshape(q, 15), axis=1)
    lq = np.fmin.reduce(np.nan_to_num(low[:q * 15], nan=np.inf).reshape(q, 15), axis=1)
    cq = filled[14:q * 15:15]
    prev = np.r_[cq[0], cq[:-1]]
    tr = np.maximum(hq, prev) - np.minimum(lq, prev)
    tr[~np.isfinite(tr)] = np.nan
    cs = np.r_[0.0, np.nancumsum(tr)]

    def roll(x, k):                                                       # mean of the last k entries (incl.)
        c = np.r_[0.0, np.cumsum(x)]
        out = np.full(len(x), np.nan)
        out[k - 1:] = (c[k:] - c[:-k]) / k
        return out
    rv4_back, rv24, rv168 = roll(rv_h, 4), roll(rv_h, 24), roll(rv_h, 168)
    vol168 = roll(vol_h, 168)
    rows: Dict[str, list] = {k: [] for k in ('ts', 'rv1', 'rv4', *HAR, 'atr14', 'atr_max', 'ar_1h', 'ar_4h', 'ar_24h',
                                             'lvol', 'd_hi', 'd_lo', 'hsin', 'hcos', 'weekend')}
    eps = 1e-12
    for h in range(168, hours - 4):
        t_close = t0 + (h + 1) * H_MS
        if t_close // 86_400_000 not in days_ok:
            continue
        qe = (h + 1) * 4                                                   # 15m candles closed by t_close
        atr14 = (cs[qe] - cs[qe - 14]) / 14
        atr1h = (cs[qe] - cs[qe - 4]) / 4
        c = c_h[h]
        hi24, lo24 = np.max(hi_h[h - 23:h + 1]), np.min(lo_h[h - 23:h + 1])
        rows['ts'].append(t_close)
        rows['rv1'].append(rv_h[h + 1])
        rows['rv4'].append(rv_h[h + 1:h + 5].sum())
        rows['lrv_1h'].append(math.log(rv_h[h] + eps))
        rows['lrv_4h'].append(math.log(rv4_back[h] + eps))
        rows['lrv_24h'].append(math.log(rv24[h] + eps))
        rows['lrv_7d'].append(math.log(rv168[h] + eps))
        rows['atr14'].append(math.log((atr14 / c) ** 2 + eps))
        rows['atr_max'].append(math.log((max(atr14, atr1h) / c) ** 2 + eps))
        rows['ar_1h'].append(abs(math.log(c / c_h[h - 1])))
        rows['ar_4h'].append(abs(math.log(c / c_h[h - 4])))
        rows['ar_24h'].append(abs(math.log(c / c_h[h - 24])))
        rows['lvol'].append(math.log((vol_h[h] + 1) / (vol168[h] + 1)))
        rows['d_hi'].append(math.log(hi24 / c) if hi24 > 0 else 0.0)
        rows['d_lo'].append(math.log(c / lo24) if lo24 > 0 else 0.0)
        hod = (t_close // H_MS) % 24
        rows['hsin'].append(math.sin(2 * math.pi * hod / 24))
        rows['hcos'].append(math.cos(2 * math.pi * hod / 24))
        rows['weekend'].append(float(((t_close // 86_400_000) + 3) % 7 >= 5))   # 1970-01-01 was a Thursday
    if not rows['ts']:
        return None
    df = pl.DataFrame(rows).with_columns(pl.lit(key).alias('symbol'))
    return df.with_columns([pl.col(c).cast(pl.Float32) for c in df.columns if c not in ('ts', 'symbol')])


def _qlike(rv, f):
    x = rv / f
    return x - np.log(x) - 1


def _dm(d: np.ndarray, lags: int = 24) -> float:
    """Diebold-Mariano p-value (two-sided) of a mean loss differential series, Newey-West variance."""
    d = d[~np.isnan(d)]
    n = len(d)
    if n < 50:
        return float('nan')
    u = d - d.mean()
    s = u @ u / n
    for k in range(1, lags + 1):
        s += 2 * (1 - k / (lags + 1)) * (u[k:] @ u[:-k]) / n
    z = d.mean() / math.sqrt(max(s, 1e-300) / n)
    return math.erfc(abs(z) / math.sqrt(2))


def evaluate(df: pl.DataFrame) -> str:
    import lightgbm as lgb
    split = _ms(SPLIT)
    btc = df.filter(pl.col('symbol') == 'BTC/USDT:USDT').select(
        'ts', *[pl.col(c).alias(f"btc_{c}") for c in HAR])
    mkt = df.group_by('ts').agg(pl.col('lrv_1h').median().alias('mkt_lrv_1h'))
    df = df.join(btc, on='ts', how='left').join(mkt, on='ts', how='left').sort('ts')
    feats = HAR + ['atr14', 'atr_max', 'ar_1h', 'ar_4h', 'ar_24h', 'lvol', 'd_hi', 'd_lo', 'hsin', 'hcos', 'weekend',
                   'btc_lrv_1h', 'btc_lrv_4h', 'btc_lrv_24h', 'btc_lrv_7d', 'mkt_lrv_1h']
    ts = df['ts'].to_numpy()
    dev, hold = ts < split, ts >= split
    val = dev & (ts >= split - 60 * 86_400_000)
    fit = dev & ~val
    lines = ['# B1 — realized-volatility forecast (pre-registered: research/prereg/B1_volatility.md)', '',
             f"{df['symbol'].n_unique()} coins, {len(df)} coin-hours; development {START} .. {SPLIT}, "
             f"HOLDOUT {SPLIT} .. {END}. QLIKE on variance (lower = better), MSE of log RV; DM = Diebold-Mariano "
             f"p of the hourly cross-coin mean loss difference vs HAR-RV (Newey-West, 24 lags).", '']
    import validation
    verdict = {}
    for target in ('rv1', 'rv4'):
        raw = df[target].to_numpy().astype(float)
        y = np.log(raw + 1e-12)
        # hours without a single price change (untraded minutes, a halted coin) have RV 0: QLIKE explodes on them
        # (the first full run: dev QLIKE ~1e5-1e6); they are no forecasting problem and are excluded
        ok = np.isfinite(y) & (raw > 1e-10)
        preds = {}

        def ols(cols):
            X = np.column_stack([np.ones(len(df))] + [df[c].to_numpy().astype(float) for c in cols])
            m = dev & ok & np.isfinite(X).all(axis=1)
            beta, *_ = np.linalg.lstsq(X[m], y[m], rcond=None)
            return X @ beta
        preds['ATR14'] = ols(['atr14'])
        preds['max(ATR14, ATR 1h)'] = ols(['atr_max'])
        preds['HAR-RV'] = ols(HAR)
        X = df.select(feats).to_numpy().astype(np.float32)
        model = lgb.LGBMRegressor(n_estimators=3000, learning_rate=0.03, num_leaves=31, min_child_samples=500,
                                  subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0, verbose=-1)
        model.fit(X[fit & ok], y[fit & ok], eval_set=[(X[val & ok], y[val & ok])],
                  callbacks=[lgb.early_stopping(100, verbose=False)])
        preds['LightGBM'] = model.predict(X)
        rv = np.exp(y)
        lines += [f"## Horizon {'1h' if target == 'rv1' else '4h'}", '',
                  '| Forecast | QLIKE dev | QLIKE HOLDOUT | MSE log HOLDOUT | vs HAR QLIKE HOLDOUT | DM p |',
                  '|---|---:|---:|---:|---:|---:|']
        losses = {}
        for name, p in preds.items():
            s2 = np.nanvar((y - p)[dev & ok])
            f = np.exp(p + s2 / 2)                       # the mean of a log-normal forecast
            L = _qlike(rv, f)
            losses[name] = L
        har_h = np.nanmean(losses['HAR-RV'][hold & ok])
        hour_ix = ts // H_MS
        for name, L in losses.items():
            qd, qh = np.nanmean(L[dev & ok]), np.nanmean(L[hold & ok])
            mse = np.nanmean(((y - preds[name]) ** 2)[hold & ok])
            d = pl.DataFrame({'h': hour_ix[hold & ok], 'd': (L - losses['HAR-RV'])[hold & ok]}).group_by('h').agg(
                pl.col('d').mean()).sort('h')['d'].to_numpy()
            p = _dm(d) if name != 'HAR-RV' else float('nan')
            lines.append(f"| {name} | {qd:.4f} | {qh:.4f} | {mse:.3f} | {qh / har_h - 1:+.1%} | "
                         f"{'—' if math.isnan(p) else f'{p:.3g}'} |")
            verdict[(target, name)] = (qh, p)
            validation.record_trial('research_vol.py', f"{name} {target}", window=f"{START}..{END}", n=int(ok.sum()),
                                    metric='QLIKE', dev=float(qd), holdout=float(qh), source='research/vol_b1.md')
        imp = sorted(zip(model.feature_importances_, feats), reverse=True)[:8]
        lines += ['', 'LightGBM top features (splits): ' + ', '.join(f"{f} {v}" for v, f in imp), '']
    # the pre-registered decision
    def better(a, b, target):
        qa, pa = verdict[(target, a)]
        qb, _ = verdict[(target, b)]
        return qa <= 0.95 * qb and (pa < 0.05 if not math.isnan(pa) else True)
    if all(better('LightGBM', 'HAR-RV', t) for t in ('rv1', 'rv4')):
        decision = 'ACCEPT LightGBM (>= 5% lower QLIKE than HAR-RV on both horizons, DM p < 0.05)'
    elif all(verdict[(t, 'HAR-RV')][0] <= 0.95 * min(verdict[(t, 'ATR14')][0], verdict[(t, 'max(ATR14, ATR 1h)')][0])
             for t in ('rv1', 'rv4')):
        decision = 'HAR-RV is the forecast (LightGBM not >= 5% better; HAR >= 5% better than both ATR units)'
    else:
        decision = 'KILL: nothing beats the ATR units by the pre-registered margin; the stop unit stays'
    lines += ['## Decision (pre-registered rule)', '', decision, '']
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--window', default='', help='START,SPLIT,END (ISO dates): another period, e.g. the one before '
                    'the main window as an independent check; outputs get the suffix _<START year>')
    ap.add_argument('--from-rows', action='store_true', help='skip the archive pass: evaluate the saved rows')
    args = ap.parse_args()
    global START, SPLIT, END, REPORT_PATH, ROWS_PATH
    if args.window:
        START, SPLIT, END = (date.fromisoformat(x) for x in args.window.split(','))
        REPORT_PATH = REPORT_PATH.replace('.md', f'_{START.year}.md')
        ROWS_PATH = ROWS_PATH.replace('.parquet', f'_{START.year}.parquet')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-7s | %(message)s', datefmt='%H:%M:%S')
    if args.from_rows:
        df = pl.read_parquet(ROWS_PATH)
    else:
        from history import Archive
        from pretrain import select_coins
        coins = select_coins(Archive(rate_bytes=4e7), START, END, 3e6)
        if args.limit:
            coins = coins[:args.limit]
        parts, t0 = [], time.time()
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futs = {pool.submit(coin_rows, (k, f, d, START, END)): k for k, f, _s, d in coins}
            for i, fut in enumerate(as_completed(futs), 1):
                try:
                    r = fut.result()
                    if r is not None:
                        parts.append(r)
                except Exception as e:
                    logger.warning(f"vol: {futs[fut]} failed ({type(e).__name__} {e})")
                if i % 25 == 0 or i == len(futs):
                    logger.info(f"vol: {i}/{len(futs)} coins in {time.time() - t0:.0f}s")
        df = pl.concat(parts, how='vertical_relaxed')
        df.write_parquet(ROWS_PATH)
    text = evaluate(df)
    with open(REPORT_PATH, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)


if __name__ == '__main__':
    main()
