"""
G of ML_PLAN.md (pre-registered in research/prereg/G_xsec.md, one attempt): rank the universe every 4h and trade the
top / bottom decile for 4h, LightGBM vs 24h momentum vs 24h reversal, net of turnover costs.

    python research_xsec.py --workers 4        # research/xsec_g.md
"""
import argparse
import logging
import math
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, datetime, timezone
from typing import Optional

import numpy as np
import polars as pl

logger = logging.getLogger('research_xsec')
H_MS = 3_600_000
START, SPLIT, END = date(2025, 4, 3), date(2026, 4, 1), date(2026, 9, 30)
_ROOT = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(_ROOT, 'research', 'xsec_g.md')
ROWS_PATH = os.path.join(_ROOT, 'research_xsec_rows.parquet')
FEATS = ['r_1h', 'r_4h', 'r_24h', 'r_7d', 'lrv_24h', 'lrv_7d', 'amihud', 'lvol', 'd_hi7', 'd_lo7', 'funding', 'hod']


def _ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def coin_rows(job) -> Optional[pl.DataFrame]:
    key, fut_id, days_ok, start, end = job        # the window travels with the job (worker processes re-import)
    from history import Archive
    from pretrain import _bucket
    days_ok = set(days_ok)
    arch = Archive(rate_bytes=4e7)
    m = arch.klines_1m('futures', fut_id, start, end)
    if len(m) < 1440 * 30:
        return None
    h = _bucket(m, H_MS)                          # [ts, o, h, l, c, v, qv, tbq] hourly
    ts, c, hi, lo, qv = h[:, 0].astype(np.int64), h[:, 4], h[:, 2], h[:, 3], h[:, 6]
    # a complete hourly grid so that index offsets are hours
    t0 = ts[0]
    n = int((ts[-1] - t0) // H_MS) + 1
    pos = ((ts - t0) // H_MS).astype(np.int64)
    C = np.full(n, np.nan)
    C[pos] = c
    C = pl.Series(C).fill_nan(None).fill_null(strategy='forward').to_numpy().copy()
    HI, LO, QV = np.full(n, np.nan), np.full(n, np.nan), np.zeros(n)
    HI[pos], LO[pos], QV[pos] = hi, lo, qv
    r1 = np.r_[np.nan, np.diff(np.log(C))]
    fund = arch.funding(fut_id, start, end)
    out = {k: [] for k in ['ts', 'fwd_4h', 'vol24', *FEATS]}
    for i in range(168, n - 4):
        t = t0 + (i + 1) * H_MS                    # the close of hour i = the rebalance time
        if t % (4 * H_MS) or t // 86_400_000 not in days_ok:
            continue
        w24, w168 = r1[i - 23:i + 1], r1[i - 167:i + 1]
        q24 = QV[i - 23:i + 1]
        vol24 = float(np.nansum(q24))
        if not vol24:
            continue
        out['ts'].append(t)
        out['fwd_4h'].append(C[i + 4] / C[i] - 1)
        out['vol24'].append(vol24)
        out['r_1h'].append(C[i] / C[i - 1] - 1)
        out['r_4h'].append(C[i] / C[i - 4] - 1)
        out['r_24h'].append(C[i] / C[i - 24] - 1)
        out['r_7d'].append(C[i] / C[i - 168] - 1)
        out['lrv_24h'].append(math.log(np.nansum(w24 ** 2) + 1e-12))
        out['lrv_7d'].append(math.log(np.nansum(w168 ** 2) / 7 + 1e-12))
        out['amihud'].append(math.log(np.nanmean(np.abs(w24) / np.maximum(q24, 1.0)) + 1e-18))
        out['lvol'].append(math.log((vol24 + 1) / (np.nansum(QV[i - 167:i + 1]) / 7 + 1)))
        out['d_hi7'].append(math.log(np.nanmax(HI[i - 167:i + 1]) / C[i]))
        out['d_lo7'].append(math.log(C[i] / np.nanmin(LO[i - 167:i + 1])))
        j = int(np.searchsorted(fund[:, 0], t, side='right')) - 1 if len(fund) else -1
        out['funding'].append(float(fund[j, 1]) if j >= 0 else 0.0)
        out['hod'].append(float((t // H_MS) % 24))
    if not out['ts']:
        return None
    return pl.DataFrame(out).with_columns(pl.lit(key).alias('symbol'))


def portfolio(df: pl.DataFrame, score: str) -> pl.DataFrame:
    """Per rebalance: long the top decile, short the bottom decile of `score`; gross / net 4h return."""
    from levels import slippage_bps
    from config import CONFIG
    fee = CONFIG.journal.fee_round_trip
    rows, prev_long, prev_short = [], set(), set()
    for (t,), g in df.sort('ts').group_by(['ts'], maintain_order=True):
        if g.height < 30:
            continue
        g = g.sort(score)
        k = max(1, g.height // 10)
        short, long_ = g.head(k), g.tail(k)
        gross = long_['ex_4h'].mean() - short['ex_4h'].mean()
        ls, ss = set(long_['symbol']), set(short['symbol'])
        turn = (len(ls - prev_long) + len(ss - prev_short)) / (2 * k)
        slip = np.mean([slippage_bps(v) for v in pl.concat([long_, short])['vol24'].to_list()]) / 1e4
        cost = turn * (fee + 2 * slip) * 2           # two legs, each re-traded on its turnover
        rows.append({'ts': t, 'gross': gross, 'net': gross - cost, 'turnover': turn})
        prev_long, prev_short = ls, ss
    return pl.DataFrame(rows)


def evaluate(df: pl.DataFrame) -> str:
    import lightgbm as lgb
    import validation
    split = _ms(SPLIT)
    df = df.with_columns((pl.col('fwd_4h') - pl.col('fwd_4h').mean().over('ts')).alias('ex_4h')).drop_nulls('ex_4h')
    ts = df['ts'].to_numpy()
    dev = ts < split
    val = dev & (ts >= split - 60 * 86_400_000)
    fit = dev & ~val
    X = df.select(FEATS).to_numpy().astype(np.float32)
    y = df['ex_4h'].to_numpy()
    model = lgb.LGBMRegressor(n_estimators=2000, learning_rate=0.02, num_leaves=15, min_child_samples=1000,
                              subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=10.0, verbose=-1)
    model.fit(X[fit], y[fit], eval_set=[(X[val], y[val])], callbacks=[lgb.early_stopping(100, verbose=False)])
    df = df.with_columns(pl.Series('s_gbm', model.predict(X)), pl.col('r_24h').alias('s_mom'),
                         (-pl.col('r_24h')).alias('s_rev'))
    lines = ['# G — cross-sectional ranking (pre-registered: research/prereg/G_xsec.md)', '',
             f"{df['symbol'].n_unique()} coins, {df['ts'].n_unique()} rebalances; dev before {SPLIT}, HOLDOUT after. "
             f"Long top / short bottom decile, 4h, per-rebalance return; [90%] = weekly block bootstrap.", '',
             '| Score | part | rebalances | gross | net [90%] | turnover |', '|---|---|---:|---:|---|---:|']
    res = {}
    for name in ('s_gbm', 's_mom', 's_rev'):
        p = portfolio(df, name)
        for part, cond in (('dev', pl.col('ts') < split), ('HOLDOUT', pl.col('ts') >= split)):
            g = p.filter(cond)
            if g.is_empty():
                continue
            net = g['net'].to_numpy()
            mean, lo, hi, _, _ = validation.block_stats(net, g['ts'].to_numpy() // (7 * 86_400_000))
            res[(name, part)] = (mean, lo, hi, net)
            lines.append(f"| {name[2:]} | {part} | {g.height} | {g['gross'].mean() * 100:+.3f}% | "
                         f"{mean * 100:+.3f}% [{lo * 100:+.3f}..{hi * 100:+.3f}] | {g['turnover'].mean():.2f} |")
            validation.record_trial('research_xsec.py', f"{name} long-short {part}", window=f"{START}..{END}",
                                    n=g.height, metric='net ret / 4h', holdout=mean if part == 'HOLDOUT' else None,
                                    dev=mean if part == 'dev' else None, source='research/xsec_g.md')
    gd, gh = res.get(('s_gbm', 'dev')), res.get(('s_gbm', 'HOLDOUT'))
    dsr = validation.deflated_sharpe(gh[3], validation.n_trials()) if gh else float('nan')
    ok = bool(gd and gh and gd[0] > 0 and gh[0] > 0 and gh[1] > 0 and dsr > 0.95 and
              all(gh[0] > res.get((b, 'HOLDOUT'), (np.inf,))[0] for b in ('s_mom', 's_rev')))
    lines += ['', f"Deflated Sharpe of LightGBM's holdout series with {validation.n_trials()} trials counted: {dsr:.2f}",
              '', '## Decision (pre-registered rule)', '',
              'WORKS' if ok else 'DOES NOT WORK - the topic is closed (research-findings)', '']
    imp = sorted(zip(model.feature_importances_, FEATS), reverse=True)
    lines.append('LightGBM features (splits): ' + ', '.join(f"{f} {v}" for v, f in imp))
    return '\n'.join(lines) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--window', default='', help='START,SPLIT,END (ISO dates): another period, e.g. the one before '
                    'the main window as an independent check; outputs get the suffix _<START year>')
    ap.add_argument('--from-rows', action='store_true')
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
                    logger.warning(f"xsec: {futs[fut]} failed ({type(e).__name__} {e})")
                if i % 25 == 0 or i == len(futs):
                    logger.info(f"xsec: {i}/{len(futs)} coins in {time.time() - t0:.0f}s")
        df = pl.concat(parts, how='vertical_relaxed')
        df.write_parquet(ROWS_PATH)
    text = evaluate(df)
    with open(REPORT_PATH, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)


if __name__ == '__main__':
    main()
