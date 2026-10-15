"""
Entry vs geometry, separated (2026-10-05, the owner: "you look at them wrong, and the trade geometry is built wrong").

Part 1 - geometry audit of every passed replayed entry: the stop distance and TP1 distance in units of the coin's 1h
ATR(14) at the entry (a stop inside one hour's normal range is inside the noise), the plan's R:R to TP1, the
round-trip cost in R, by strategy and by the stop's source label.

Part 2 - the entry WITHOUT our geometry: the return in the trade's direction after 1h / 4h / 24h in ATR units, and
which comes first of +-1 ATR and +-2 ATR (symmetric barriers, no stop / target of ours), vs 10 placebo entries per
entry (same coin, direction, hour of day, random other days within +-120 days). If our entries beat the placebo
here, the setup carries direction and our stop / targets waste it; if not, the setup itself has no signal.
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import os
import random
from datetime import date, datetime, timezone

import numpy as np
import polars as pl

from history import Archive
from research_optimize import FEE, slippage

HOUR, DAY = 3_600_000, 86_400_000


def atr_series(k1h: np.ndarray) -> np.ndarray:
    h, l, c = k1h[:, 2], k1h[:, 3], k1h[:, 4]
    prev = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(abs(h - prev), abs(l - prev)))
    return np.convolve(tr, np.ones(14) / 14, mode='full')[:len(tr)]


def barrier(path, d, entry, step):
    fav = (path[:, 1] - entry) if d > 0 else (entry - path[:, 2])
    adv = (path[:, 2] - entry) if d > 0 else (entry - path[:, 1])
    up = np.argmax(fav >= step) if (fav >= step).any() else len(path)
    dn = np.argmax(adv <= -step) if (adv <= -step).any() else len(path)
    if dn <= up and dn < len(path):
        return -1
    return 1 if up < len(path) else 0


def forward(k5, i, d, entry, atr):
    out = {}
    for tag, bars in (('r1h', 12), ('r4h', 48), ('r24h', 288)):
        j = min(i + bars, len(k5)) - 1
        out[tag] = d * (k5[j, 4] - entry) / atr
    path = k5[i:i + 288, 1:5]
    out['b1'] = barrier(path, d, entry, atr)
    out['b2'] = barrier(path, d, entry, 2 * atr)
    return out


def main():
    rnd = random.Random(5)
    arch = Archive(rate_bytes=300_000)
    ent = (pl.read_parquet(os.environ.get('REPLAY_SUMMARY', 'research/replay_summary.parquet'))
           .filter(pl.col('r_tp1').is_not_null() & pl.col('vetoed').is_null() & pl.col('entry').is_not_null()))
    t0, t1 = ent['ts'].min(), ent['ts'].max()
    first, last = (datetime.fromtimestamp(x / 1000, timezone.utc).date() for x in (t0, t1))
    geo, fw = [], []
    for sym in ent['symbol'].unique().sort().to_list():
        code = sym.split(':')[0].replace('/', '')
        k5 = arch.klines_ohlc('futures', code, '5m', date(first.year, first.month, 1), last)
        k1 = arch.klines_ohlc('futures', code, '1h', date(first.year, max(1, first.month - 1), 1), last)
        if len(k5) < 2000 or len(k1) < 100:
            continue
        atr = atr_series(k1)
        close1 = k1[:, 0] + HOUR
        for r in ent.filter(pl.col('symbol') == sym).iter_rows(named=True):
            ts, d, e = r['ts'], int(r['direction']), r['entry']
            ja = int(np.searchsorted(close1, ts, side='right')) - 1
            i = int(np.searchsorted(k5[:, 0], ts, side='right'))
            if ja < 20 or i + 288 > len(k5):
                continue
            a = atr[ja]
            stop = abs(e - r['sl'])
            tp1 = abs((r['tp1'] or e) - e) if r['tp1'] is not None and abs((r['tp1'] or e) - e) < 50 * stop else None
            geo.append(dict(strategy=r['strategy'], sl_src=(r.get('sl_src') or '')[:40],
                            stop_atr=stop / a, tp1_atr=tp1 / a if tp1 else None, rr=tp1 / stop if tp1 else None,
                            cost_r=(2 * FEE + 2 * slippage(r.get('volume_24h') or 0.0)) * e / stop))
            fw.append(dict(strategy=r['strategy'], kind='ours', **forward(k5, i, d, k5[i, 1], a)))
            for _ in range(10):
                shift = rnd.randint(-120, 120) * DAY
                j = int(np.searchsorted(k5[:, 0], ts + shift, side='right'))
                jb = int(np.searchsorted(close1, ts + shift, side='right')) - 1
                if shift == 0 or j < 1 or j + 288 > len(k5) or jb < 20:
                    continue
                fw.append(dict(strategy=r['strategy'], kind='placebo', **forward(k5, j, d, k5[j, 1], atr[jb])))
        print(sym, len(geo), flush=True)
    g, f = pl.DataFrame(geo), pl.DataFrame(fw)
    pl.Config.set_tbl_rows(80)
    pl.Config.set_tbl_width_chars(240)
    geo_t = (g.group_by('strategy').agg(
        pl.len().alias('n'), pl.col('stop_atr').median().alias('stop_ATR_med'),
        (pl.col('stop_atr') < 1).mean().alias('stops_<1ATR'), pl.col('tp1_atr').median().alias('tp1_ATR_med'),
        pl.col('rr').median().alias('rr_med'), pl.col('cost_r').median().alias('cost_R_med')).sort('n', descending=True))
    src_t = (g.group_by(['strategy', 'sl_src']).agg(pl.len().alias('n'), pl.col('stop_atr').median().alias('stop_ATR'))
             .filter(pl.col('n') >= 30).sort(['strategy', 'n'], descending=[False, True]))

    def s1(col, v):
        return (pl.col(col) == v).mean()
    fw_t = (f.group_by(['strategy', 'kind']).agg(
        pl.len().alias('n'), pl.col('r1h').mean().alias('r1h_ATR'), pl.col('r4h').mean().alias('r4h_ATR'),
        pl.col('r24h').mean().alias('r24h_ATR'), s1('b1', 1).alias('p_+1ATR_first'), s1('b1', -1).alias('p_-1ATR_first'),
        s1('b2', 1).alias('p_+2ATR_first'), s1('b2', -1).alias('p_-2ATR_first')).sort(['strategy', 'kind']))
    lines = ['# Entry vs geometry (research_geometry_audit.py)', '', '## Part 1: geometry of the passed entries (ATR = the coin\'s 1h ATR14 at the entry)',
             '', '```', str(geo_t), '', str(src_t), '```', '',
             '## Part 2: the entry without our stop / targets, vs placebo (same coin, side, hour; other days)', '',
             '```', str(fw_t), '```']
    with open(f"research/geometry_audit{os.environ.get('REPORT_SUFFIX', '')}.md", 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
