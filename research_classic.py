"""
Archive check of the strategies research_cards / research_maniac do not replay: Dalton's 80% rule (VA80), Crabel's
opening range breakout (ORB), Connors' daily RSI(2) and the owner's pump (PUMP START / PUMP TOP). The events come
from the live detectors (strategies/classic.py, strategies/pump.py, imported, not copied); the exits are each
method's OWN rule, simplified (the live card adds map targets and the measured pierce, which this does not):

- VA80: entry at the next minute's open, stop at the day's extreme so far, target the far edge of yesterday's value
  area, else out at the UTC day's end;
- ORB: stop at the range's other side, no target (Crabel), out at 16:00 New York;
- RSI2: entry at the next day's open, out at the first daily close beyond the SMA5 (Connors) or after 10 days, no
  stop: its "R" is the net return in % (a different unit, judged by the same sign rule);
- PUMP START: the live detector WITHOUT its OI / spot conditions (the archive's 5m OI and spot are not the live
  readings) - treated as passed; stop below the ignition low, target one more move of the same size, 12h max;
- PUMP TOP: the climax candle, entry on the first 5m close below the previous 5m low within 1h (the 5m shift), stop
  above the pump high, target the 0.5 retracement, 12h max.
Costs: the round-trip fee + 5 bps slippage each way. Placebo: the same trade (direction, stop / target distance in %,
holding limit) at the same time of day on a random other day within +-7 days. Only days the coin passed the volume floor.

    python research_classic.py --months 18 --end 2026-09-30 --holdout 6 --workers 4
"""
import argparse
import logging
import os
import math
import zlib
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

import numpy as np
import polars as pl

from config import CONFIG

logger = logging.getLogger('research_classic')
MINUTE_MS, QUARTER_MS, HOUR_MS, DAY_MS = 60_000, 900_000, 3_600_000, 86_400_000
COST = CONFIG.journal.fee_round_trip + 2 * 0.0005
_ROOT = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(_ROOT, 'research', 'classic_eng43.md')   # fixed outputs: no path comes from the command line
ROWS_PATH = os.path.join(_ROOT, 'research_classic.parquet')


def _sim(m: np.ndarray, i0: int, d: int, stop: Optional[float], target: Optional[float], end_ms: float):
    """Walk 1m candles [t, o, h, l, c, ...] from index i0 (entry at its open). -> (exit price, exit index)."""
    n = len(m)
    i = i0
    while i < n and m[i, 0] < end_ms:
        o, h, l = m[i, 1], m[i, 2], m[i, 3]
        if stop is not None and ((l <= stop) if d > 0 else (h >= stop)):
            return (min(o, stop) if d > 0 else max(o, stop)), i
        if target is not None and ((h >= target) if d > 0 else (l <= target)):
            return target, i
        i += 1
    i = min(i, n) - 1
    return m[i, 4], i


def _result(entry, exit_px, d, risk):
    ret = d * (exit_px / entry - 1) - COST
    return ret, (ret * entry / risk if risk else None)


def replay_coin(job: tuple) -> List[Dict]:
    key, fut_id, _spot_id, start_iso, end_iso, days_ok = job
    from history import Archive
    from strategies.classic import connors_event, orb_event, value_area_event
    from strategies.pump import pump_start, pump_top
    from research_cards import STREAM_COLS
    from pretrain import _bucket

    days_ok = set(days_ok)
    start, end = date.fromisoformat(start_iso), date.fromisoformat(end_iso)
    arch = Archive(rate_bytes=4e7)
    fut = arch.klines_1m('futures', fut_id, start, end)
    if len(fut) < 1440 * 20:
        return []
    ts = fut[:, 0]
    rng = np.random.default_rng(zlib.crc32(key.encode()))   # reproducible across runs (hash() is salted)
    out: List[Dict] = []

    def trade(setup, d, t_entry, stop, target, end_ms, unit='R'):
        i0 = int(np.searchsorted(ts, t_entry))
        if i0 >= len(fut):
            return
        entry = fut[i0, 1]
        risk = abs(entry - stop) if stop is not None else None
        if risk is not None and (risk <= 0 or (stop - entry) * d >= 0):
            return
        px, _ = _sim(fut, i0, d, stop, target, end_ms)
        ret, r = _result(entry, px, d, risk)
        row = {'symbol': key, 'setup': setup, 'direction': d, 'ts_ms': int(t_entry), 'ret': ret,
               'r': r if unit == 'R' else ret * 100, 'pl_r': None}
        # placebo: same distances in %, same holding time, random minute within +-7 days
        for _ in range(10):
            # same time of day, another day within +-7: a session-bound entry is compared with its own hour
            t = t_entry + int(rng.choice([d for d in range(-7, 8) if d])) * DAY_MS
            j0 = int(np.searchsorted(ts, t))
            if 0 < j0 < len(fut) - 1 and int(ts[j0] // DAY_MS) in days_ok:
                pe = fut[j0, 1]
                ps = pe * stop / entry if stop is not None else None
                pt = pe * target / entry if target is not None else None
                ppx, _ = _sim(fut, j0, d, ps, pt, ts[j0] + (end_ms - t_entry))
                pret, pr = _result(pe, ppx, d, abs(pe - ps) if ps is not None else None)
                row['pl_r'] = pr if unit == 'R' else pret * 100
                break
        out.append(row)

    to_list = lambda arr: [[r[0], r[1], r[2], r[3], r[4], r[6], r[7]] for r in arr]  # noqa: E731
    c15 = to_list(_bucket(fut, QUARTER_MS))
    h1 = to_list(_bucket(fut, HOUR_MS))
    h1_open = np.asarray([c[0] for c in h1])
    from strategies.classic import NY
    # --- VA80 / ORB at every 15m close
    busy = {}
    for q in range(200, len(c15)):
        cut = int(c15[q][0]) + QUARTER_MS
        if cut // DAY_MS not in days_ok:
            continue
        m15 = c15[max(0, q - 200):q + 1]
        k = int(np.searchsorted(h1_open, cut))
        h1w = h1[max(0, k - 24 * 8):k]
        for ev in (value_area_event(m15, cut), orb_event(m15, h1w, cut)):
            if not ev or cut < busy.get(ev['setup'], 0):
                continue
            d = ev['direction']
            if ev['setup'].startswith('VA80'):
                end_ms = cut - cut % DAY_MS + DAY_MS
                trade(ev['setup'], d, cut, ev['anchor_extreme'], ev['va_far'], end_ms)
            else:
                local = datetime.fromtimestamp(cut / 1000, tz=timezone.utc).astimezone(NY)
                end_ms = int(local.replace(hour=16, minute=0, second=0, microsecond=0).timestamp() * 1000)
                trade(ev['setup'], d, cut, ev['orb_lo'] if d > 0 else ev['orb_hi'], None, end_ms)
            busy[ev['setup']] = cut + DAY_MS // 2
    # --- Connors on daily candles (archive daily file: 200+ days before the window)
    d1 = arch.klines_ohlc('futures', fut_id, '1d', start - timedelta(days=260), end)
    d1 = [list(map(float, r[:6])) for r in d1]
    in_trade_until = 0
    for i in range(202, len(d1)):
        day_open = int(d1[i][0]) + DAY_MS
        if day_open // DAY_MS - 1 not in days_ok or day_open < in_trade_until or day_open > ts[-1]:
            continue
        ev = connors_event(d1[:i + 1])
        if not ev:
            continue
        d = ev['direction']
        exit_ms = None
        for j in range(i + 1, min(len(d1), i + 11)):
            sma5 = sum(x[4] for x in d1[j - 4:j + 1]) / 5
            if (d1[j][4] > sma5) if d > 0 else (d1[j][4] < sma5):
                exit_ms = int(d1[j][0]) + DAY_MS
                break
        exit_ms = exit_ms or day_open + 10 * DAY_MS
        trade(ev['setup'], d, day_open, None, None, exit_ms, unit='%')
        in_trade_until = exit_ms
    # --- pumps on 1m (prefiltered: +3% in 15m at a fresh 24h high / a 10% 4h run)
    closes = fut[:, 4]
    minutes = fut[:, STREAM_COLS]
    ret15 = np.zeros(len(fut))
    ret15[15:] = closes[15:] / closes[:-15] - 1
    r15q = np.array([c[4] / c[1] - 1 for c in c15])
    cand = np.nonzero(ret15 >= CONFIG.strategies.pump_start_min_pct)[0]
    next_ok = 0
    for i in cand:
        if i < 1500 or ts[i] < next_ok or int(ts[i] // DAY_MS) not in days_ok:
            continue
        win = minutes[i - 1455:i + 1].tolist()
        avg_min = float(np.mean(fut[i - 1455:i - 15, 6])) or 0.0
        m = {'rvol_1m': fut[i, 6] / avg_min if avg_min else 0, 'oi_change_5m': 1.0, 'spot_cvd_5m': 1.0}
        qi = int((ts[i] - c15[0][0]) // QUARTER_MS)
        vol = float(np.std(r15q[max(0, qi - 384):qi])) if qi > 50 else None
        ev = pump_start(win, m, vol, int(ts[i]) + MINUTE_MS)
        if not ev:
            continue
        t0 = ev['event_ts']
        entry_px = fut[min(i + 1, len(fut) - 1), 1]
        trade('PUMP START', 1, t0, ev['pump_low'], entry_px * (1 + ev['pump_move']), t0 + 12 * HOUR_MS)
        next_ok = t0 + HOUR_MS
    next_ok = 0
    c5 = to_list(_bucket(fut, 5 * MINUTE_MS))
    c5_open = np.asarray([c[0] for c in c5])
    for q in range(20, len(c15)):
        w = c15[q - 15:q + 1]
        if max(c[2] for c in w) / min(c[3] for c in w) - 1 < CONFIG.strategies.pump_top_min_pct:
            continue
        cut = int(c15[q][0]) + QUARTER_MS
        if cut < next_ok or cut // DAY_MS not in days_ok:
            continue
        lo_i = int(np.searchsorted(ts, cut - 21 * QUARTER_MS))
        hi_i = int(np.searchsorted(ts, cut))
        ev = pump_top(minutes[lo_i:hi_i].tolist(), {}, cut)
        if not ev:
            continue
        k = int(np.searchsorted(c5_open, cut))
        for j in range(k + 1, min(len(c5), k + 12)):
            if c5[j][4] < c5[j - 1][3]:
                t0 = int(c5[j][0]) + 5 * MINUTE_MS
                target = ev['pump_high'] - 0.5 * (ev['pump_high'] - ev['pump_low'])
                trade('PUMP TOP', -1, t0, ev['pump_high'], target, t0 + 12 * HOUR_MS)
                break
        next_ok = cut + 4 * HOUR_MS
    return out


def report(df: pl.DataFrame, start: date, end: date, split: date) -> str:
    from research_cards import H4_MS, _block_ci
    split_ms = int(datetime(split.year, split.month, split.day, tzinfo=timezone.utc).timestamp() * 1000)
    f = lambda v: '—' if v is None or math.isnan(v) else f"{v:+.3f}"  # noqa: E731
    lines = ['# Classic / pump strategies on the archive (own exits, placebo, holdout)', '',
             f"Window {start} .. {end}, holdout from {split}; {df['symbol'].n_unique() if df.height else 0} coins. "
             f"R net of {COST:.2%} per round trip (RSI2: net return in %). [90%] = block bootstrap over 4h x direction.",
             '', '| Setup | part | trades | win | mean [90%] | placebo | system − placebo [90%] |',
             '|---|---|---:|---:|---|---:|---|']
    for setup in sorted(df['setup'].unique().to_list()) if df.height else []:
        for part, cond in (('dev', pl.col('ts_ms') < split_ms), ('HOLDOUT', pl.col('ts_ms') >= split_ms)):
            e = df.filter((pl.col('setup') == setup) & cond & pl.col('r').is_not_null())
            mean = lo = hi = dm = dlo = dhi = float('nan')
            if e.height >= 10:
                b = (e['ts_ms'].to_numpy() // H4_MS) * 2 + (e['direction'].to_numpy() > 0)
                mean, lo, hi, _, _ = _block_ci(e['r'].to_numpy().astype(float), b)
                pe = e.filter(pl.col('pl_r').is_not_null())
                if pe.height >= 10:
                    pb = (pe['ts_ms'].to_numpy() // H4_MS) * 2 + (pe['direction'].to_numpy() > 0)
                    dm, dlo, dhi, _, _ = _block_ci((pe['r'] - pe['pl_r']).to_numpy().astype(float), pb)
            win = float((e['r'] > 0).mean()) if e.height else float('nan')
            lines.append(f"| {setup} | {part} | {e.height} | {'—' if math.isnan(win) else f'{win:.0%}'} | "
                         f"{f(mean)} [{f(lo)}..{f(hi)}] | {f(e['pl_r'].mean() if e.height else None)} | "
                         f"{f(dm)} [{f(dlo)}..{f(dhi)}] |")
    lines += ['', 'WORKS only if mean > 0 in both parts, the holdout interval > 0 and system − placebo > 0 in the holdout.']
    return '\n'.join(lines) + '\n'


def main():
    cfg = CONFIG.pretrain
    ap = argparse.ArgumentParser()
    ap.add_argument('--months', type=int, default=18)
    ap.add_argument('--holdout', type=int, default=6)
    ap.add_argument('--end', default='2026-09-30')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--min-volume', type=float, default=cfg.min_volume_usd)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-7s | %(message)s', datefmt='%H:%M:%S')
    from history import Archive
    from pretrain import select_coins
    end = date.fromisoformat(args.end)
    start = end - timedelta(days=30 * args.months)
    split = end - timedelta(days=30 * args.holdout)
    coins = select_coins(Archive(rate_bytes=4e7), start, end, args.min_volume)
    if args.limit:
        coins = coins[:args.limit]
    jobs = [(k, f, s, start.isoformat(), end.isoformat(), days) for k, f, s, days in coins]
    rows: List[Dict] = []
    t0 = time.time()
    import research_cache
    cache = research_cache.run_dir('classic', start, end, args.min_volume)
    todo = []
    for j in jobs:
        done = research_cache.load(cache, j[0])
        if done is None:
            todo.append(j)
        else:
            rows += done
    logger.info(f"classic: {len(jobs) - len(todo)} coins from the cache, {len(todo)} to replay")
    jobs = todo
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(replay_coin, j): j[0] for j in jobs}
        for n, fut in enumerate(as_completed(futs), 1):
            try:
                coin_rows = fut.result()
                rows += coin_rows
                research_cache.save(cache, futs[fut], coin_rows)
            except Exception as e:
                logger.warning(f"classic: {futs[fut]} failed ({type(e).__name__} {e})")
            if n % 10 == 0 or n == len(jobs):
                logger.info(f"classic: {n}/{len(jobs)} coins in {time.time() - t0:.0f}s ({len(rows)} trades)")
    df = pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()
    if df.height:
        df.write_parquet(ROWS_PATH)
    text = report(df, start, end, split)
    with open(REPORT_PATH, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)


if __name__ == '__main__':
    main()
