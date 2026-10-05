"""
Do our entries have a directional edge at all, or does the geometry eat it? (2026-10-05, the owner: "we pick ever
better entries yet they only lose less - the geometry is wrong or the entry filters do not work")

Data: every PASSED replayed entry (research/replay_summary.parquet, vetoed IS NULL) and its 5m path (history_cache).
For each entry, in R of its own stop distance and from its entry price: which comes first within 72h - +1R or -1R,
+2R or -1R, +0.5R or -0.5R - and the max favourable / adverse excursion within 24h. The round-trip cost in R of the
entry (0.1% fee + slippage by its 24h volume) is reported beside.

Baseline (placebo): for each entry 10 random entries in the SAME coin, same direction, same stop distance in %,
same hour of the day, on random other days of the replay span. If our entries reach +1R before -1R no more often than
the placebo, the entries have no edge and no geometry can create one; if they do, the edge is there and the
targets / stops / costs waste it.
"""
import random
from datetime import date, datetime, timezone

import numpy as np
import polars as pl

from history import Archive
from research_optimize import FEE, slippage

DAY = 86_400_000
H72 = 72 * 12
H24 = 24 * 12


def first_hit(path: np.ndarray, d: int, entry: float, risk: float, up: float, down: float) -> int:
    """+1 when +up R traded before -down R, -1 for the reverse (a bar touching both counts the stop), 0 neither."""
    fav = (path[:, 1] - entry) / risk if d > 0 else (entry - path[:, 2]) / risk
    adv = (path[:, 2] - entry) / risk if d > 0 else (entry - path[:, 1]) / risk
    i_up = np.argmax(fav >= up) if (fav >= up).any() else len(path)
    i_dn = np.argmax(adv <= -down) if (adv <= -down).any() else len(path)
    if i_dn <= i_up and i_dn < len(path):
        return -1
    return 1 if i_up < len(path) else 0


def stats(path, d, entry, risk):
    p72, p24 = path[:H72], path[:H24]
    fav = ((p24[:, 1] - entry) / risk if d > 0 else (entry - p24[:, 2]) / risk).max()
    adv = ((p24[:, 2] - entry) / risk if d > 0 else (entry - p24[:, 1]) / risk).min()
    return dict(h1=first_hit(p72, d, entry, risk, 1, 1), h2=first_hit(p72, d, entry, risk, 2, 1),
                h05=first_hit(p72, d, entry, risk, 0.5, 0.5), mfe=fav, mae=adv)


def main():
    rnd = random.Random(11)
    arch = Archive(rate_bytes=300_000)
    ent = (pl.read_parquet('research/replay_summary.parquet')
           .filter(pl.col('r_tp1').is_not_null() & pl.col('vetoed').is_null() & pl.col('entry').is_not_null())
           .select('symbol', 'strategy', 'direction', 'ts', 'entry', 'sl', 'volume_24h'))
    t0, t1 = ent['ts'].min(), ent['ts'].max()
    first, last = (datetime.fromtimestamp(x / 1000, timezone.utc).date() for x in (t0, t1))
    rows = []
    for sym in ent['symbol'].unique().sort().to_list():
        k5 = arch.klines_ohlc('futures', sym.split(':')[0].replace('/', ''), '5m', date(first.year, first.month, 1), last)
        if len(k5) < 2000:
            continue
        opens = k5[:, 0]
        for r in ent.filter(pl.col('symbol') == sym).iter_rows(named=True):
            d, e = int(r['direction']), r['entry']
            risk_pct = abs(e - r['sl']) / e
            if risk_pct <= 0:
                continue
            i = int(np.searchsorted(opens, r['ts'], side='right'))
            if i + H72 > len(k5):
                continue
            cost_r = (2 * FEE + 2 * slippage(r.get('volume_24h') or 0.0)) / risk_pct
            ours = stats(k5[i:i + H72, 1:5], d, e, e * risk_pct)
            rows.append(dict(strategy=r['strategy'], kind='ours', cost_r=cost_r, risk_pct=risk_pct, **ours))
            for _ in range(10):
                # a random other day, the same time of day
                shift = rnd.randint(-120, 120) * DAY
                j = int(np.searchsorted(opens, r['ts'] + shift, side='right'))
                if shift == 0 or j < 1 or j + H72 > len(k5):
                    continue
                pe = k5[j, 1]                               # entry at that bar's open
                rows.append(dict(strategy=r['strategy'], kind='placebo', cost_r=cost_r, risk_pct=risk_pct,
                                 **stats(k5[j:j + H72, 1:5], d, pe, pe * risk_pct)))
        print(sym, len(rows), flush=True)
    df = pl.DataFrame(rows)

    def share(col, v):
        return (pl.col(col) == v).mean()
    out = (df.group_by(['strategy', 'kind'])
           .agg(pl.len().alias('n'), share('h1', 1).alias('p_1R_first'), share('h2', 1).alias('p_2R_first'),
                share('h05', 1).alias('p_05R_first'), pl.col('mfe').median().alias('mfe24_med'),
                pl.col('mae').median().alias('mae24_med'), pl.col('cost_r').median().alias('cost_R'),
                pl.col('risk_pct').median().alias('stop_pct'))
           .sort(['strategy', 'kind']))
    allr = (df.group_by('kind').agg(pl.len().alias('n'), share('h1', 1).alias('p_1R_first'), share('h2', 1).alias('p_2R_first'),
                                    share('h05', 1).alias('p_05R_first'), pl.col('cost_r').median().alias('cost_R')))
    pl.Config.set_tbl_rows(60)
    pl.Config.set_tbl_width_chars(220)
    lines = ['# Entry edge vs placebo (research_entry_edge.py)', '', '```', str(allr), '', str(out), '```']
    with open('research/entry_edge.md', 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
