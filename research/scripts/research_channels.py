# ruff: noqa: E741  (O / H / L / C are the candle fields)
"""
Channel trading with the stop on the STRUCTURE's own timeframe (the owner's rule): a coin in an ascending channel is
bought at the lower boundary after a confirming candle, the stop goes beyond the boundary on the same timeframe,
wicks included, plus a margin; the target is the other side. Pre-registered, no parameter search:

Channel (4h and 1d candles built from the archive's 1h ones): the linear regression of the last N closes (N = 60 bars
on 4h = 10 days, 40 bars on 1d); the boundaries = the line shifted by the largest excursion of the HIGHS above it and
of the LOWS below it over those bars (the envelope includes every wick). A channel is valid when R^2 of the fit >= 0.5,
it is at least 3 ATR(14) of its timeframe wide, and both boundaries were touched (within 0.25 ATR) at least twice.
Its slope over the N bars >= +1.5 ATR = ascending, <= -1.5 ATR = descending, otherwise a range.

Trades (entry at the next bar's open; one trade per coin, timeframe and side at a time):
- long at the lower boundary of an ascending channel or a range: a bar's low within 0.25 ATR of the boundary (or
  below it) and the bar closes up (close > open) back above the boundary;
- short at the upper boundary of a descending channel or a range (mirror);
- stop = the boundary at the entry bar minus the deepest wick below it during the channel's N bars (already inside the
  envelope, so 0) minus 0.5 ATR: i.e. beyond every wick of the channel with a margin; TP1 = the channel's middle,
  TP2 = the opposite boundary (both projected to the entry bar, fixed); hold up to N/2 bars.
Against the random-walk hit rate of the same trade; net of 0.20% round trip and a 0.10% one for sensitivity; halves.

Run: python research_channels.py [--months 38] [--end-month YYYY-MM] [--limit N]
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import argparse
import multiprocessing as mp
import os
from datetime import datetime, timezone
from typing import Dict, List

import numpy as np

import research_htf as rh

G: Dict = {}
SPECS = (('4h', 4, 60), ('1d', 24, 40))


def bars(O, H, L, C, k):
    m = len(C) // k
    o, h, l, c = (x[:m * k].reshape(m, k) for x in (O, H, L, C))
    return o[:, 0], h.max(axis=1), l.min(axis=1), c[:, -1]


def atr(h, l, c, n=14):
    pc = np.concatenate([[np.nan], c[:-1]])
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    out = np.full_like(c, np.nan)
    if len(c) > n:
        w = np.lib.stride_tricks.sliding_window_view(tr, n)
        out[n - 1:] = w.mean(axis=1)
    return out


def coin_trades(j: int) -> List[Dict]:
    O, H, L, C = (G[k][:, j] for k in ('O', 'H', 'L', 'C'))
    coin, t0, elig = G['coins'][j], G['t0'], G['elig'][:, j]
    out = []
    for tf, k, n in SPECS:
        o, h, l, c = bars(O, H, L, C, k)
        a = atr(h, l, c)
        x = np.arange(n, dtype=float)
        xm = x.mean()
        sxx = ((x - xm) ** 2).sum()
        busy = {1: -1, -1: -1}
        for i in range(n + 14, len(c) - 1):
            day = (i + 1) * k // 24 - 1
            if day < 0 or day >= len(elig) or not elig[day]:
                continue
            sl = slice(i - n + 1, i + 1)
            cc, hh, ll = c[sl], h[sl], l[sl]
            if np.isnan(cc).any() or np.isnan(a[i]):
                continue
            b = ((x - xm) * (cc - cc.mean())).sum() / sxx
            line = cc.mean() + b * (x - xm)
            resid = cc - line
            ss_tot = ((cc - cc.mean()) ** 2).sum()
            r2 = 1 - (resid ** 2).sum() / ss_tot if ss_tot > 0 else 0
            up_off = np.max(hh - line)
            dn_off = np.min(ll - line)
            width = up_off - dn_off
            if width < 3 * a[i]:
                continue
            upper, lower = line + up_off, line + dn_off
            touch_up = int((hh >= upper - 0.25 * a[i]).sum())
            touch_dn = int((ll <= lower + 0.25 * a[i]).sum())
            if touch_up < 2 or touch_dn < 2:
                continue
            rise = b * (n - 1)
            kind = 'ascending' if rise >= 1.5 * a[i] else 'descending' if rise <= -1.5 * a[i] else 'range'
            if kind != 'range' and r2 < 0.5:
                continue
            lo_now, up_now, mid_now = lower[-1], upper[-1], line[-1]
            for d in (1, -1):
                if i <= busy[d]:
                    continue
                if d > 0 and kind == 'descending' or d < 0 and kind == 'ascending':
                    continue
                edge = lo_now if d > 0 else up_now
                tested = l[i] <= edge + 0.25 * a[i] if d > 0 else h[i] >= edge - 0.25 * a[i]
                confirm = (c[i] > o[i] and c[i] > edge) if d > 0 else (c[i] < o[i] and c[i] < edge)
                if not (tested and confirm) or np.isnan(o[i + 1]):
                    continue
                entry = o[i + 1]
                # beyond every wick of the channel (the envelope) and this bar's, plus 0.5 ATR of the timeframe
                stop = min(edge, l[i]) - 0.5 * a[i] if d > 0 else max(edge, h[i]) + 0.5 * a[i]
                risk = d * (entry - stop)
                tp1, tp2 = mid_now + b, (up_now if d > 0 else lo_now) + b
                if risk <= 0 or d * (tp1 - entry) <= 0:
                    continue
                res = {}
                last = min(len(c), i + 1 + n // 2)
                exit_i = last - 1
                for key, tgt in (('1', tp1), ('2', tp2)):
                    win, px = None, c[last - 1]
                    for m in range(i + 1, last):
                        if np.isnan(h[m]):
                            px = c[m - 1]
                            break
                        if (l[m] <= stop) if d > 0 else (h[m] >= stop):
                            win, px, exit_i = 0, stop, m
                            break
                        if (h[m] >= tgt) if d > 0 else (l[m] <= tgt):
                            win, px = 1, tgt
                            break
                    res[key] = (win, px, risk / (risk + d * (tgt - entry)) if d * (tgt - entry) > 0 else None)
                busy[d] = exit_i
                gross1 = d * (res['1'][1] - entry)
                gross2 = d * (res['2'][1] - entry)
                out.append({'coin': coin, 'tf': tf, 'kind': kind, 'dir': d, 'ts': t0 + (i + 1) * k * rh.HOUR,
                            'risk_pct': risk / entry, 'rr1': d * (tp1 - entry) / risk, 'rr2': d * (tp2 - entry) / risk,
                            'win1': res['1'][0], 'geo1': res['1'][2], 'win2': res['2'][0], 'geo2': res['2'][2],
                            'r1': (gross1 - 0.002 * entry) / risk, 'r2': (gross2 - 0.002 * entry) / risk,
                            'r2_low': (gross2 - 0.001 * entry) / risk, 'major': coin in G['majors']})
    return out


def _worker(j):
    try:
        return coin_trades(j)
    except Exception as e:
        return [{'error': f"{G['coins'][j]}: {type(e).__name__} {e}"}]


def fmt(ms) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime('%Y-%m-%d')


def main():
    import polars as pl
    parser = argparse.ArgumentParser()
    parser.add_argument('--months', type=int, default=38)
    parser.add_argument('--end-month', default='')
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument('--out', default=os.path.join('research', 'channels.md'))
    parser.add_argument('--trades', default='')
    args = parser.parse_args()
    t0, coins, O, H, L, C, V, _ = rh.load(args.months, args.limit, args.end_month)
    elig, _, _, _ = rh.market_state(C, V, coins)
    G.update(t0=t0, coins=coins, O=O, H=H, L=L, C=C, elig=elig,
             majors={'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'BNBUSDT'})
    rows: List[Dict] = []
    with mp.get_context('fork').Pool(args.workers) as pool:
        for k, res in enumerate(pool.imap_unordered(_worker, range(len(coins)), chunksize=2)):
            rows.extend(res)
            if k % 50 == 0:
                print(f"  {k}/{len(coins)} coins, {len(rows)} trades", flush=True)
    errors = [r['error'] for r in rows if 'error' in r]
    df = pl.DataFrame([r for r in rows if 'error' not in r], infer_schema_length=None).sort('ts')
    if args.trades:
        df.write_parquet(args.trades)
    mid = int(df['ts'].min() + (df['ts'].max() - df['ts'].min()) // 2)
    df = df.with_columns(pl.when(pl.col('ts') < mid).then(pl.lit('older')).otherwise(pl.lit('newer')).alias('half'),
                         pl.when(pl.col('major')).then(pl.lit('majors')).otherwise(pl.lit('others')).alias('class'),
                         pl.when(pl.col('dir') > 0).then(pl.lit('long')).otherwise(pl.lit('short')).alias('side'))
    lines = [f"# Channels with the stop on the structure's timeframe ({len(coins)} coins, {fmt(df['ts'].min())} .. "
             f"{fmt(df['ts'].max())}, {len(df)} trades)", '',
             "Rules: the docstring of `research_channels.py` (pre-registered). 'geometry' = the random-walk hit rate "
             "of the same entry / stop / target. R net of 0.20% round trip ('R TP2 @0.10%' for sensitivity). "
             "[90%] = bootstrap by calendar week.", '']
    for keys, title in ((['tf', 'kind', 'side', 'half'], 'By timeframe, channel, side, half'),
                        (['tf', 'kind', 'side', 'class'], 'Majors vs the rest (whole window)')):
        lines += [f"## {title}", '', '| ' + ' | '.join(keys) + ' | trades | median stop | R:R TP2 | TP1 hit | geo1 | '
                  'TP2 hit | geo2 | R TP1 | R TP2 [90%] | R TP2 @0.10% |',
                  '|' + '---|' * len(keys) + '---:|---:|---:|---:|---:|---:|---:|---:|---|---:|']
        for key, g in df.group_by(keys, maintain_order=True):
            if len(g) < 30:
                continue
            wk = (g['ts'].to_numpy() // (7 * 86_400_000)).astype(int)
            m, lo, hi, _ = rh.week_boot(g['r2'].to_numpy().astype(float), wk)
            w1, w2 = g.filter(pl.col('win1').is_not_null()), g.filter(pl.col('win2').is_not_null())
            lines.append('| ' + ' | '.join(str(x) for x in key) +
                         f" | {len(g)} | {g['risk_pct'].median() * 100:.1f}% | {g['rr2'].median():.1f} | "
                         f"{w1['win1'].mean():.0%} | {w1['geo1'].mean():.0%} | {w2['win2'].mean():.0%} | "
                         f"{w2['geo2'].mean():.0%} | {g['r1'].mean():+.3f} | {m:+.3f} [{lo:+.3f}..{hi:+.3f}] | "
                         f"{g['r2_low'].mean():+.3f} |")
        lines.append('')
    if errors:
        lines += [f"{len(errors)} coins failed, first: {errors[0]}"]
    text = '\n'.join(lines) + '\n'
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)


if __name__ == '__main__':
    main()
