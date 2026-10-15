"""
"The higher timeframe decides" (2026-10-05, the owner: a coin / market going up -> look for longs; in a range ->
trade the range's edges and its extensions; only then go down to the lower timeframe - Elder's triple screen, ICT's
top-down, Dow). Tested here on the coin's OWN higher timeframes for every strategy.

Data: every replayed entry of research/replay_summary.parquet with its outcome `r_tp1` (the method's own plan, net of
costs); the archive's daily, weekly (from daily) and 4h (from 1h) candles of the coin, read on the last candle CLOSED
before the entry.

States (fixed before the run):
- d1_up / d1_down: the daily close above / below its EMA50 AND the EMA50 rising / falling over 5 days, else d1_flat;
- h4_up / h4_down: the same on 4h candles (EMA50, slope over 6 candles = 1 day);
- h4_trend / h4_range: ADX(14) on 4h >= 25 / < 25;
- w1_up / w1_down: the weekly close above / below the EMA20 of the weekly closes.
Rules (a boolean per entry): with_d1 (the trade's direction = the daily trend), with_h4, with_d1_h4 (both), with_w1,
against_d1, h4_range, h4_trend, d1_flat.

PRE-REGISTERED RULE: per strategy x rule, KEEP when mean R(rule) - mean R(all) has a lower 90% cluster bound > 0 on the
first 8 months (>= 30 4h clusters in the rule's group) AND a mean > 0 on the last 4 months. Output: research/htf_filter.md
and models/htf_filters.json ({strategy: [rules kept]}).
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import json
from datetime import date, datetime, timezone

import numpy as np
import polars as pl

from history import Archive
from research_optimize import TRAIN_MONTHS, cluster_stats
from strategies.ind_panel import ema
from strategies.profiles import regime_labels

HOUR = 3_600_000
DAY = 24 * HOUR
BLOCK = 4 * HOUR
RULES = ('with_d1', 'with_h4', 'with_d1_h4', 'with_w1', 'against_d1', 'h4_range', 'h4_trend', 'd1_flat')


def trend_state(k: np.ndarray, slope_n: int) -> np.ndarray:
    """+1 up / -1 down / 0 flat per candle: close vs EMA50 and the EMA50's slope over slope_n candles."""
    c = k[:, 4]
    e = ema(c, 50)
    slope = e - np.concatenate((np.full(slope_n, np.nan), e[:-slope_n]))
    out = np.zeros(len(c))
    out[(c > e) & (slope > 0)] = 1
    out[(c < e) & (slope < 0)] = -1
    out[:60] = np.nan
    return out


def to_4h(k1h: np.ndarray) -> np.ndarray:
    size = 4 * HOUR
    bars = {}
    for r in k1h:
        b = int(r[0]) // size * size
        x = bars.get(b)
        if x is None:
            bars[b] = [b, r[1], r[2], r[3], r[4]]
        else:
            x[2], x[3], x[4] = max(x[2], r[2]), min(x[3], r[3]), r[4]
    return np.asarray([bars[b] for b in sorted(bars)], dtype=float)


def to_weekly(kd: np.ndarray) -> np.ndarray:
    """Weekly candles (Monday 00:00 UTC) from daily ones."""
    out = {}
    for r in kd:
        day = int(r[0]) // DAY
        week = (day - (day + 3) % 7) * DAY
        x = out.get(week)
        if x is None:
            out[week] = [week, r[1], r[2], r[3], r[4]]
        else:
            x[2], x[3], x[4] = max(x[2], r[2]), min(x[3], r[3]), r[4]
    return np.asarray([out[w] for w in sorted(out)], dtype=float)


def main():
    arch = Archive(rate_bytes=300_000)
    ent = pl.read_parquet('research/replay_summary.parquet',
                          columns=['symbol', 'strategy', 'direction', 'ts', 'r_tp1']).filter(pl.col('r_tp1').is_not_null())
    t0, t1 = ent['ts'].min(), ent['ts'].max()
    first, last = (datetime.fromtimestamp(x / 1000, timezone.utc).date() for x in (t0, t1))
    start = date(first.year - 1, first.month, 1)              # a year of warm-up for the daily / weekly EMAs
    split = int(datetime(first.year + (first.month - 1 + TRAIN_MONTHS) // 12, (first.month - 1 + TRAIN_MONTHS) % 12 + 1,
                         1, tzinfo=timezone.utc).timestamp() * 1000)
    rows = []
    for sym in ent['symbol'].unique().sort().to_list():
        code = sym.split(':')[0].replace('/', '')
        kd = arch.klines_ohlc('futures', code, '1d', start, last)
        k1 = arch.klines_ohlc('futures', code, '1h', date(first.year, first.month, 1) if first.month > 3 else start, last)
        if len(kd) < 80 or len(k1) < 1000:
            print(f'{sym}: not enough candles, skipped')
            continue
        k4 = to_4h(k1)
        kw = to_weekly(kd)
        d1, h4 = trend_state(kd, 5), trend_state(k4, 6)
        reg4 = regime_labels(k4)
        ew = ema(kw[:, 4], 20)
        w1 = np.where(kw[:, 4] > ew, 1.0, -1.0)
        w1[:25] = np.nan
        d_close, h_close, w_close = kd[:, 0] + DAY, k4[:, 0] + 4 * HOUR, kw[:, 0] + 7 * DAY
        part = ent.filter(pl.col('symbol') == sym)
        for r in part.iter_rows(named=True):
            ts, d = r['ts'], int(r['direction'])
            i, j, w = (int(np.searchsorted(x, ts, side='right')) - 1 for x in (d_close, h_close, w_close))
            if min(i, j, w) < 0 or np.isnan(d1[i]) or np.isnan(h4[j]) or np.isnan(w1[w]) or reg4[j] is None:
                continue
            flags = {'with_d1': d1[i] == d, 'with_h4': h4[j] == d, 'with_d1_h4': d1[i] == d and h4[j] == d,
                     'with_w1': w1[w] == d, 'against_d1': d1[i] == -d, 'h4_range': reg4[j].startswith('range'),
                     'h4_trend': reg4[j].startswith('trend'), 'd1_flat': d1[i] == 0}
            rows.append(dict(strategy=r['strategy'], ts=ts, cluster=ts // BLOCK * 2 + (d > 0), r=r['r_tp1'],
                             **{k: bool(v) for k, v in flags.items()}))
        print(f'{sym}: {len(rows)} entries so far', flush=True)
    df = pl.DataFrame(rows)
    lines = ['# The higher timeframe decides (research_htf_filter.py, pre-registered)', '',
             f"{df.height} entries; train < {datetime.fromtimestamp(split / 1000, timezone.utc):%Y-%m-%d} <= validation. "
             'Mean R of the method\'s own plan (r_tp1, net).', '',
             '| strategy | rule | train: n, R rule vs all, diff [lower 90%] | validation: n, R rule vs all | verdict |',
             '|---|---|---|---|---|']
    kept = {}
    for strat in df['strategy'].unique().sort().to_list():
        g = df.filter(pl.col('strategy') == strat)
        tr, va = g.filter(pl.col('ts') < split), g.filter(pl.col('ts') >= split)
        if tr.height < 50:
            continue
        for rule in RULES:
            a = tr.filter(pl.col(rule))
            if a['cluster'].n_unique() < 30:
                continue
            m_all = tr['r'].mean()
            m, lo, _ = cluster_stats(a['r'].to_numpy(), a['cluster'].to_numpy())
            v = va.filter(pl.col(rule))
            vm, vall = (v['r'].mean() if v.height else float('nan')), va['r'].mean()
            keep = (lo - m_all) > 0 and v.height > 0 and vm - vall > 0
            lines.append(f"| {strat} | {rule} | {a.height}, {m:+.3f} vs {m_all:+.3f}, {m - m_all:+.3f} [{lo - m_all:+.3f}] | "
                         f"{v.height}, {vm:+.3f} vs {vall:+.3f} | {'KEEP' if keep else 'no'} |")
            if keep:
                kept.setdefault(strat, []).append(rule)
    with open('research/htf_filter.md', 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    with open('models/htf_filters.json', 'w', encoding='utf-8') as fh:
        json.dump(kept, fh, indent=1)
    print('\n'.join(lines))
    print('kept:', kept)


if __name__ == '__main__':
    main()
