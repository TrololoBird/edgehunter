"""
The top-down bias (strategies/bias.py) on the archive replay's TRADES (2026-10-05). The rule is fixed by the sources
(Elder, ICT, Weinstein, time-series momentum) before this run - nothing is fitted, so no train / validation split is
needed; what matters is whether the effect holds in EVERY market phase, month by month.

Outcome: the card's final_r (the whole trade under the method's own exits: targets in thirds, time stops, the
Turtles' channel exit - not a fixed 8h horizon) of every replayed card that entered. The bias at the card's entry
from the coin's and BTC's closed daily / 4h / weekly archive candles (the same functions as live).

Reported per strategy: mean R of the trades the gate ALLOWS vs BLOCKS (with a 90% 4h-cluster bound), by month, by
direction. Verdict per strategy (pre-registered): HELPS when allowed - blocked > 0 with the lower 90% bound > 0 AND
allowed > blocked in at least 2/3 of the months with >= 5 trades on each side.
"""
from datetime import date, datetime, timezone

import numpy as np
import polars as pl

from history import Archive
from research_htf_filter import to_4h, to_weekly
from research_optimize import cluster_stats
from strategies import bias

HOUR, DAY = 3_600_000, 86_400_000


def main():
    arch = Archive(rate_bytes=300_000)
    cards = (pl.read_parquet('research/replay_summary.parquet')
             .filter(pl.col('stage').is_null() | (pl.col('stage') == 'card'))      # cards (entries carry stage 'entry')
             .filter(pl.col('entered_ms').is_not_null() & pl.col('final_r').is_not_null())
             .select('symbol', 'strategy', 'direction', 'entered_ms', 'final_r'))
    t0, t1 = cards['entered_ms'].min(), cards['entered_ms'].max()
    first, last = (datetime.fromtimestamp(x / 1000, timezone.utc).date() for x in (t0, t1))
    start = date(first.year - 1, first.month, 1)

    def series(code):
        kd = arch.klines_ohlc('futures', code, '1d', start, last)
        k1 = arch.klines_ohlc('futures', code, '1h', date(first.year, max(1, first.month - 2), 1), last)
        return kd, to_4h(k1) if len(k1) else np.empty((0, 5)), to_weekly(kd) if len(kd) else np.empty((0, 5))

    btc = series('BTCUSDT')
    rows = []
    for sym in cards['symbol'].unique().sort().to_list():
        kd, k4, kw = series(sym.split(':')[0].replace('/', ''))
        if len(kd) < 60 or len(k4) < 60:
            continue
        for r in cards.filter(pl.col('symbol') == sym).iter_rows(named=True):
            ts, d = r['entered_ms'], int(r['direction'])

            def at(k, period):
                return [list(x) for x in k[(k[:, 0] + period) <= ts]]
            st = bias.state(at(kd, DAY)[-400:], at(k4, 4 * HOUR)[-200:], at(kw, 7 * DAY)[-60:])
            sb = bias.state(at(btc[0], DAY)[-400:], at(btc[1], 4 * HOUR)[-200:], at(btc[2], 7 * DAY)[-60:])
            daily = r['strategy'] in bias.DAILY
            cb, bb = bias.bias_of(st, daily), bias.bias_of(sb, daily)
            if cb is None:
                continue
            veto = bias.gate(r['strategy'], d, cb, bb, sym.startswith('BTC/'))
            rows.append(dict(strategy=r['strategy'], d=d, ts=ts, r=r['final_r'], coin=cb, btc=bb, veto=veto or '',
                             allowed=veto is None, month=datetime.fromtimestamp(ts / 1000, timezone.utc).strftime('%Y-%m'),
                             cluster=ts // (4 * HOUR) * 2 + (d > 0)))
        print(f'{sym}: {len(rows)} trades', flush=True)
    df = pl.DataFrame(rows)
    lines = ['# Top-down bias on the replay\'s trades (research_bias.py; the rule fixed by the sources, nothing fitted)', '',
             f'{df.height} entered cards, outcome = the card\'s final_r (its own exits). Bias mix: ' +
             ', '.join(f"{k} {v}" for k, v in df.group_by('coin').len().sort('len', descending=True).iter_rows()), '',
             '| strategy | allowed: n, R [lower 90%] | blocked: n, R | diff | months allowed > blocked | longs allowed / blocked | shorts allowed / blocked | verdict |',
             '|---|---|---|---|---|---|---|---|']
    for strat in df['strategy'].unique().sort().to_list():
        g = df.filter(pl.col('strategy') == strat)
        a, b = g.filter(pl.col('allowed')), g.filter(~pl.col('allowed'))
        if a.height < 5 or b.height < 5:
            lines.append(f'| {strat} | {a.height} | {b.height} | - | - | - | - | too few |')
            continue
        ma, la, _ = cluster_stats(a['r'].to_numpy(), a['cluster'].to_numpy())
        mb = b['r'].mean()
        # the bound of the difference: allowed's lower bound minus blocked's mean (conservative enough for a report)
        wins = tot = 0
        for m, gm in g.group_by('month'):
            x, y = gm.filter(pl.col('allowed')), gm.filter(~pl.col('allowed'))
            if x.height >= 5 and y.height >= 5:
                tot += 1
                wins += x['r'].mean() > y['r'].mean()
        side = {}
        for d in (1, -1):
            x, y = a.filter(pl.col('d') == d), b.filter(pl.col('d') == d)
            side[d] = f"{x['r'].mean() if x.height else float('nan'):+.2f} ({x.height}) / {y['r'].mean() if y.height else float('nan'):+.2f} ({y.height})"
        helps = (la - mb) > 0 and tot > 0 and wins >= 2 * tot / 3
        lines.append(f"| {strat} | {a.height}, {ma:+.3f} [{la:+.3f}] | {b.height}, {mb:+.3f} | {ma - mb:+.3f} | {wins}/{tot} | "
                     f"{side[1]} | {side[-1]} | {'HELPS' if helps else 'no'} |")
    lines += ['', '## Blocked by reason', ''] + [f"- {k or 'allowed'}: {n} trades, mean R {m:+.3f}" for k, n, m in
                                               df.group_by('veto').agg(pl.len(), pl.col('r').mean()).sort('len', descending=True).iter_rows()]
    lines += ['', '## All strategies by month (allowed vs blocked mean R)', ''] + [
        f"- {m}: allowed {gm.filter(pl.col('allowed'))['r'].mean():+.3f} ({gm.filter(pl.col('allowed')).height}), "
        f"blocked {gm.filter(~pl.col('allowed'))['r'].mean():+.3f} ({gm.filter(~pl.col('allowed')).height})"
        for (m,), gm in sorted(df.group_by('month'), key=lambda x: x[0])]
    with open('research/bias.md', 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
