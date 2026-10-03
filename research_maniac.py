"""
Archive replay of crypto_maniac's systems (strategies/maniac.py) through the bot's card lifecycle, like
research_cards.py replays ours: events from the live detectors on the Binance archive (15m / 1h windows of the live
length, BTC as the SMT correlate, the auction engine fed bar by bar, the OI robot on the archive's 5m OI), planned by
the live strategy classes (his entries / exits), walked minute by minute (his pinbar / inversion-FVG triggers, closes
beyond, sessions, entries only at the signal close) and every entry replayed like the journal (next full minute's
open + slippage, stop exits slipped, funding, NET of the round-trip fee).

Protocol (fixed before the run, no parameter is tuned here - his values as shipped):
- the window is split: the first months are the DEVELOPMENT part, the last `--holdout` months the HOLDOUT; a system
  counts as working only if its net R is above 0 in BOTH, with the 90% block-bootstrap interval above 0 in the holdout;
- PLACEBO: every entry is repeated at a random time of the same coin (+-7 days) with the same direction and the same
  stop / target distances in %: the system's timing must beat that, not only zero (a trend in the window pays random
  longs / shorts too);
- one open card per coin and setup (the live rule).
What differs from the live bot: no book walls / liquidity bands / real liquidations in the level maps (targets of
supply / demand come from the rest of the map), 1m candle extremes instead of ticks, the OI robot's OI from 5m points.

Run: .venv\\Scripts\\python research_maniac.py [--months 6] [--holdout 2] [--workers 2] [--limit 120]
"""
import argparse
import logging
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List

import numpy as np
import polars as pl

from config import CONFIG
from research_cards import H4_MS, HOUR_MS, MINUTE_MS, QUARTER_MS, STREAM_COLS, _block_ci, _lifecycle, htf_at, htf_frames

logger = logging.getLogger('research_maniac')
LONG = CONFIG.strategies.long_history_candles


def replay_coin(job: tuple):
    key, fut_id, spot_id, start_iso, end_iso, days_ok = job
    from history import Archive
    from indicators import compute_indicators_batch
    from levels import ltf_trigger, resample, simulate
    from pretrain import _asof, _bucket, _raw_frame
    from strategies import strategy_of
    from strategies.auction_engine import ENGINES
    from strategies.base import PlanInput
    from strategies.geometry import entry_levels
    from strategies.structure import Context, coin_trend, maniac_events, recent_atr
    from zones import build_raw, merge

    days_ok = set(days_ok)
    start, end = date.fromisoformat(start_iso), date.fromisoformat(end_iso)
    archive = Archive(rate_bytes=4e7)
    fut = archive.klines_1m('futures', fut_id, start, end)
    if len(fut) < 1440 * 20:
        return []
    spot = archive.klines_1m('spot', spot_id, start, end) if spot_id else np.empty((0, 8))
    spot_minutes = spot[:, STREAM_COLS] if len(spot) else None
    frames = htf_frames(archive, fut_id, fut, start)
    btc = fut if fut_id == 'BTCUSDT' else archive.klines_1m('futures', 'BTCUSDT', start, end)
    eth_corr = fut_id == 'BTCUSDT'
    if eth_corr:
        btc = archive.klines_1m('futures', 'ETHUSDT', start, end)
    met = archive.metrics(fut_id, start, end)
    fund = archive.funding(fut_id, start, end)
    c15 = _bucket(fut, QUARTER_MS)
    oi15 = {int((t - 1) // QUARTER_MS * QUARTER_MS): float(v) for t, v in zip(met['ts'], met['oi']) if int(t) % QUARTER_MS == 0 and v}
    fut_all = compute_indicators_batch({key: _raw_frame(c15, oi15)}, {key: (0.0, 0.0)})
    atr_by_ts = {int(t): a for t, a in zip(fut_all['timestamp'].to_list(), fut_all['atr'].to_list())}
    idx_by_ts = {int(t): i for i, t in enumerate(fut_all['timestamp'].to_list())}
    m_ts = fut[:, 0]
    minutes_all = fut[:, STREAM_COLS]
    to_list = lambda arr: [[r[0], r[1], r[2], r[3], r[4], r[6], r[7]] for r in arr]  # noqa: E731
    c15_list = to_list(c15)
    h1_list = to_list(_bucket(fut, HOUR_MS))
    h1_close = np.asarray([c[0] + HOUR_MS for c in h1_list])
    corr_list = to_list(_bucket(btc, QUARTER_MS))
    corr_close = np.asarray([c[0] + QUARTER_MS for c in corr_list])
    c5_list = to_list(_bucket(fut, 5 * MINUTE_MS))
    c5_close = np.asarray([c[0] + 5 * MINUTE_MS for c in c5_list])
    oi_ts, oi_v = np.asarray(met['ts']), np.asarray(met['oi'])
    oi_hour = [(int(t), float(v)) for t, v in zip(oi_ts, oi_v) if int(t) % HOUR_MS == 0 and v]
    oi_hour_ts = np.asarray([t for t, _ in oi_hour]) if len(oi_hour) else np.empty(0)
    oi5 = [(int(t), float(v)) for t, v in zip(oi_ts, oi_v) if v]
    ENGINES.pop(key, None)

    from research_cards import make_placebo
    placebo = make_placebo(m_ts, key)            # same time of day, another day within +-7 (session-matched)

    out: List[Dict] = []
    busy: Dict[str, float] = {}
    oi_fired = 0.0
    oi_ptr = 0

    def run_event(event, now_ms, q):
        d = event['direction']
        if now_ms < busy.get(event['setup'], 0.0):
            return
        strategy = strategy_of(event['setup'])
        last_open = int(c15_list[q][0])
        atr = atr_by_ts.get(last_open)
        if not atr or atr != atr:
            return
        window = c15_list[max(0, q - 98):q + 1]
        h = int(np.searchsorted(h1_close, now_ms, side='right'))
        h1_window = h1_list[max(0, h - 200):h]
        j = int(np.searchsorted(oi_hour_ts, now_ms, side='right')) if len(oi_hour_ts) else 0
        k5 = int(np.searchsorted(c5_close, now_ms, side='right'))
        h4w, d1w, w1w, htf_sig = htf_at(frames, now_ms)
        raw = build_raw(window, h1_window, oi_hour[max(0, j - 200):j], [], atr, now_ms,
                        candles_4d=c5_list[max(0, k5 - 4 * 288):k5], candles_1d=d1w, candles_4h=h4w, candles_1w=w1w)
        ctx = Context(atr=atr, recent_atr=recent_atr(window), cut_ms=last_open + QUARTER_MS, zones=merge(raw, atr),
                      pools=[], trend=0)
        closed = int(np.searchsorted(m_ts, now_ms - MINUTE_MS, side='right'))
        minutes_now = minutes_all[max(0, closed - 240):closed].tolist()
        i = idx_by_ts.get(last_open, 0)
        df = fut_all.slice(max(0, i - 98), 99)
        sig = dict(event, has_spot=True, coin_trend=coin_trend(h1_window), **htf_sig)
        plan = strategy.plan(PlanInput(key, d, event['setup'], sig, df, minutes_now, raw, h1_window, ctx, None))
        row = {'symbol': key, 'ts_ms': now_ms, 'setup': event['setup'], 'strategy': strategy.name, 'direction': d,
               'vetoed': strategy.context_veto(sig, d) or '', 'status': 'NO_PLAN', 'vetoed_triggers': 0, 'veto_log': '', 'r_tp1': None, 'r_tp2': None,
               'r_be': None, 'rr_tp1': None, 'risk_pct': None, 'outcome': None, 'hold_min': None,
               'vx_reason': '', 'vx_r_tp1': None, 'vx_r_tp2': None, 'vx_rr_tp1': None,
               'pl_r_tp1': None, 'pl_r_tp2': None}
        if plan is None or plan.get('skip') or not plan.get('targets'):
            if plan and plan.get('skip'):
                row['status'] = f"NO_PLAN ({plan['skip']})"
            out.append(row)
            return
        finished = _lifecycle(plan, strategy, d, row, now_ms, m_ts, minutes_all, fut, fund, oi_ts, oi_v,
                              entry_levels, ltf_trigger, resample, simulate, _asof, placebo=placebo,
                              spot_minutes=spot_minutes, sig=sig)
        if not row['vetoed']:
            busy[event['setup']] = finished
        out.append(row)

    for q in range(LONG, len(c15_list)):
        last_open = int(c15_list[q][0])
        cut = last_open + QUARTER_MS
        if cut // 86_400_000 not in days_ok:
            continue
        now_ms = cut + 5_000
        m15 = c15_list[q - LONG + 1:q + 1]
        h = int(np.searchsorted(h1_close, cut, side='right'))
        h1 = h1_list[max(0, h - LONG):h]
        k = int(np.searchsorted(corr_close, cut, side='right'))
        corr = corr_list[max(0, k - LONG):k]
        # 4h / daily candles built from the 1h archive (supply / demand zones of 4h, Seiden's curve on the daily)
        from zones import bars_of
        for event in maniac_events(key, m15, h1, corr, cut, bars_of(h1, 4), bars_of(h1, 24)):
            run_event(event, now_ms, q)
    ENGINES.pop(key, None)
    return out


def report(df: pl.DataFrame, start: date, end: date, split: date, title: str = "crypto_maniac's systems") -> str:
    from research_edges import bh
    split_ms = int(datetime(split.year, split.month, split.day, tzinfo=timezone.utc).timestamp() * 1000)
    f = lambda v, d=3: '—' if v is None or v != v else f"{v:+.{d}f}"  # noqa: E731
    lines = [f"# {title} on the archive (card replay, placebo, holdout)", '',
             f"Window {start} .. {end}: development before {split}, HOLDOUT from {split}. {df['symbol'].n_unique()} coins, "
             f"{len(df)} cards. R = net R of an entry replayed like the journal (next full minute's open + "
             f"{CONFIG.levels.slippage_bps:g} bps, stop exits slipped, funding, {CONFIG.journal.fee_round_trip * 100:.2f}% "
             f"round-trip fee), exit at TP1 / stop / the trade's lifetime. Placebo = the same trade (direction, stop / "
             f"target in %) at a random time of the same coin within +-7 days. [90%] = block bootstrap over 4h x "
             f"direction blocks; q = Benjamini-Hochberg over the holdout rows.", '',
             '| Setup | part | cards | entries | expired | invalid | win TP1 | R TP1 [90%] | placebo R | system - placebo [90%] | R TP2 |',
             '|---|---|---:|---:|---:|---:|---:|---|---:|---|---:|']
    rows, ps = [], []
    if 'vetoed' in df.columns:
        # a vetoed class (e.g. a sweep against the trend) is its own row, never mixed with the passed one
        df = df.with_columns(pl.when(pl.col('vetoed').fill_null('') == '').then(pl.col('setup'))
                             .otherwise(pl.col('setup') + ' [' + pl.col('vetoed') + ']').alias('setup'))
    for setup in sorted(df['setup'].unique().to_list()):
        for part, cond in (('dev', pl.col('ts_ms') < split_ms), ('HOLDOUT', pl.col('ts_ms') >= split_ms)):
            g = df.filter((pl.col('setup') == setup) & cond)
            e = g.filter(pl.col('status') == 'ENTRY').filter(pl.col('r_tp1').is_not_null())
            mean = lo = hi = p = float('nan')
            dmean = dlo = dhi = float('nan')
            if e.height >= 10:
                r1 = e['r_tp1'].to_numpy().astype(float)
                blocks = (e['ts_ms'].to_numpy() // H4_MS) * 2 + (e['direction'].to_numpy() > 0)
                mean, lo, hi, p, _ = _block_ci(r1, blocks)
                pe = e.filter(pl.col('pl_r_tp1').is_not_null())
                if pe.height >= 10:
                    diff = pe['r_tp1'].to_numpy().astype(float) - pe['pl_r_tp1'].to_numpy().astype(float)
                    pb = (pe['ts_ms'].to_numpy() // H4_MS) * 2 + (pe['direction'].to_numpy() > 0)
                    dmean, dlo, dhi, _, _ = _block_ci(diff, pb)
            rows.append((setup, part, g, e, mean, lo, hi, dmean, dlo, dhi))
            if part == 'HOLDOUT':
                ps.append(p)
    qs = iter(bh(ps))
    for setup, part, g, e, mean, lo, hi, dmean, dlo, dhi in rows:
        q = next(qs) if part == 'HOLDOUT' else None
        win = float((e['r_tp1'] > 0).mean()) if e.height else float('nan')
        pl_mean = e['pl_r_tp1'].mean() if e.height and e['pl_r_tp1'].null_count() < e.height else None
        lines.append(f"| {setup} | {part}{'' if q is None or q != q else f' (q {q:.3f})'} | {g.height} | {e.height} | "
                     f"{g.filter(pl.col('status') == 'EXPIRED').height} | {g.filter(pl.col('status') == 'INVALID').height} | "
                     f"{'—' if win != win else f'{win:.0%}'} | {f(mean)} [{f(lo)}..{f(hi)}] | {f(pl_mean)} | "
                     f"{f(dmean)} [{f(dlo)}..{f(dhi)}] | {f(e['r_tp2'].mean() if e.height else None)} |")
    lines += ['', 'A system WORKS here only if R TP1 > 0 in both parts, its holdout interval is above 0 and it beats the '
              'placebo in the holdout (the system - placebo interval above 0).']
    return '\n'.join(lines) + '\n'


def main():
    cfg = CONFIG.pretrain
    parser = argparse.ArgumentParser()
    parser.add_argument('--months', type=int, default=6)
    parser.add_argument('--holdout', type=int, default=2, help='the last N months are the holdout')
    parser.add_argument('--min-volume', type=float, default=cfg.min_volume_usd)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--limit', type=int, default=120, help='the N most liquid coins (0 = all)')
    parser.add_argument('--end', default=None)
    parser.add_argument('--out', default=os.path.join('research', 'maniac_6m.md'))
    parser.add_argument('--rows', default='research_maniac.parquet')
    parser.add_argument('--confirm', choices=('live', 'record'), default='live',
                        help='record: the minimum-confirmation rule is not applied (research_cards --confirm)')
    args = parser.parse_args()
    os.environ['RESEARCH_CONFIRM'] = args.confirm      # the worker processes read CONFIRM_MODE at import
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-7s | %(message)s', datefmt='%H:%M:%S')
    from history import Archive
    from pretrain import select_coins
    end = date.fromisoformat(args.end) if args.end else datetime.now(timezone.utc).date() - timedelta(days=1)
    start = end - timedelta(days=30 * args.months)
    split = end - timedelta(days=30 * args.holdout)
    coins = select_coins(Archive(rate_bytes=4e7), start, end, args.min_volume)
    if args.limit:
        coins = coins[:args.limit]
    jobs = [(k, f, s, start.isoformat(), end.isoformat(), days) for k, f, s, days in coins]
    rows: List[Dict] = []
    started = time.time()
    import research_cache
    cache = research_cache.run_dir('maniac', start, end, args.min_volume)
    todo = []
    for job in jobs:
        done = research_cache.load(cache, job[0])
        if done is None:
            todo.append(job)
        else:
            rows += done
    logger.info(f"maniac: {len(jobs) - len(todo)} coins from the cache, {len(todo)} to replay")
    jobs = todo
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(replay_coin, job): job[0] for job in jobs}
        for n, fut in enumerate(as_completed(futures), 1):
            try:
                coin_rows = fut.result()
                rows += coin_rows
                research_cache.save(cache, futures[fut], coin_rows)
            except Exception as e:
                logger.warning(f"maniac: {futures[fut]} failed ({type(e).__name__} {e})")
            logger.info(f"maniac: {n}/{len(jobs)} coins in {time.time() - started:.0f}s ({len(rows)} cards)")
            if n % 10 == 0 and rows:
                pl.DataFrame(rows, infer_schema_length=None).write_parquet(args.rows)
    df = pl.DataFrame(rows, infer_schema_length=None)
    df.write_parquet(args.rows)
    text = report(df, start, end, split)
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)


if __name__ == '__main__':
    main()
