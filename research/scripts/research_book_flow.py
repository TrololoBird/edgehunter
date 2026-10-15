"""
Task 2 of docs/CLOUD_TASKS.md: order book and order flow at the entries, on the Binance archive (pre-registered).

The rules below are fixed BEFORE the script is run on the Task 1 replay (committed first); a bug may be fixed and is
then named in the report, a rule is not changed after seeing results.

1. Inputs: every passed entry (`vetoed` null, stage 'entry') of the eng-72 replay (`--run`, default
   data/replay/eng72) on the 30 most liquid coins of that run (its groups 0..5, the replay's volume order) whose entry
   time lies in the last 6 months (2026-04-01 .. 2026-09-30), joined to its card (symbol, setup, entered_ms == ts)
   for the outcome. Plus 10 placebo entries per entry: same coin, same side, same minute of the day, a random other day
   within +-120 days of the entry (inside the archive's data, seed fixed: 7).
2. Features at the entry time t (only data with timestamps <= t; for a placebo the same definitions at its own time):
   - imb1_with / imb2_with: bookDepth (the archive's ~30 s snapshots of cumulative notional at +-0.2 / 1 / 2 .. 5% of
     the price), the last snapshot <= t (at most 5 min old): (bid - ask) / (bid + ask) of the 1% / 2% notional,
     signed by the trade's direction > 0 (the trade's side heavier);
   - opp_thinned: the OPPOSITE side's 2% notional now vs the snapshot 30 min before (+-5 min) fell (ratio < 1): a
     wall eaten or pulled in front of the trade;
   - delta15_with: taker delta (2 x taker buy quote - quote volume) of the 15 closed 1m futures candles before t,
     the trade's way (> 0 x direction);
   - delta_ext_with: the same delta from the setup's extreme (`f_anchor_ts`, at most 10 h back; placebos use the same
     offset) to t; missing anchor -> the cell excludes the row;
   - stacked: the footprint of aggTrades in 5 bp price buckets over [max(extreme, t - 30 min), t) has a run of
     >= orderflow.stacked_levels (3) diagonal imbalances >= orderflow.imbalance_ratio (3:1) the trade's way
     (flow.stacked_imbalance, as live);
   - absorption: flow.absorption_in on the 1m candles of the same window with the 15m ATR estimate
     flow.minute_atr_15m (a 1m delta >= p90 of the hour AGAINST the trade within <= 0.2 ATR), as live;
   - finished_auction: flow.Footprint.finished_auction's rule (<= 2% of the edge bucket's volume on the side that
     would continue the auction) on the same footprint.
   Spread at the entry (bookTicker) is NOT tested: the archive's futures bookTicker ends 2024-03-30.
   The footprint window is clipped at 00:00 UTC of t's day (aggTrades are read per day).
3. Outcome: entries - the card's full-trade final_r (net, the card's own exit); placebos - the entry's plan geometry
   (entry / stop / targets as the same percentages from the placebo minute's close) replayed by levels.simulate over
   the 8 h trade horizon, r_tp1 (net of the round-trip fee via stats.net_r). Secondary (reported, not tested): the
   entries' own levels.simulate r_tp1, so both sides share one exit model.
4. Test per strategy x feature: (mean R with - mean R without) on the entries MINUS the same difference on their
   placebos; 90% interval and two-sided p by bootstrap of 4h clusters (an entry and its placebos stay in the entry's
   cluster: floor(ts / 4h) x direction; 2000 draws); Benjamini-Hochberg over all tested cells at q 0.10; a cell needs
   >= 30 entry clusters on each side of the split. The cells passing are also shown by month (a feature that helps
   in one month only is noise).
5. Scope: 30 coins x 6 months only; promising cells may be extended later (a new run, reported separately).
6. Output research/book_flow_archive.md (Russian summary on top). A passing feature is PROPOSED as a required
   confirmation (CONFIG.orderflow.required_confirmations); the config is not changed here.
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import argparse
import glob
import io
import logging
import os
import re
import shutil
import zipfile
from datetime import date, datetime, timedelta, timezone

import numpy as np
import polars as pl

from config import CONFIG
from flow import absorption_in, minute_atr_15m, stacked_imbalance
from history import Archive
from levels import simulate
from stats import bh_q, net_r

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger('book_flow')

DAY = 86_400_000
H4 = 4 * 3_600_000
FEATURES = ['imb1_with', 'imb2_with', 'opp_thinned', 'delta15_with', 'delta_ext_with', 'stacked', 'absorption',
            'finished_auction']
AGG_CACHE = os.path.join(CONFIG.pretrain.cache_dir, 'futures', 'um', 'daily', 'aggTrades')
RUN = os.path.join('data', 'replay', 'eng72')
OUT = os.path.join('research', 'book_flow_archive.md')
SYMBOL = re.compile(r'^[A-Z0-9]{2,20}USDT$')


def book_day(arch: Archive, fid: str, d: date):
    """bookDepth of one day -> (ts_ms [n], bid1, ask1, bid2, ask2) arrays, one row per snapshot; None if missing."""
    data = arch._fetch(f"futures/um/daily/bookDepth/{fid}/{fid}-bookDepth-{d.isoformat()}.zip")
    if data is None:
        return None
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        df = pl.read_csv(zf.read(zf.namelist()[0]))
    df = (df.with_columns(pl.col('timestamp').str.to_datetime('%Y-%m-%d %H:%M:%S', time_zone='UTC')
                          .dt.epoch('ms').alias('ts'), pl.col('percentage').cast(pl.Float64))
          .filter(pl.col('percentage').is_in([-1.0, 1.0, -2.0, 2.0]))
          .pivot(on='percentage', index='ts', values='notional', aggregate_function='first').sort('ts'))
    cols = {float(c): c for c in df.columns if c != 'ts'}
    if not all(k in cols for k in (-1.0, 1.0, -2.0, 2.0)):
        return None
    return tuple(df[c].to_numpy().astype(np.float64) for c in ('ts', cols[-1.0], cols[1.0], cols[-2.0], cols[2.0]))


def agg_day(arch: Archive, fid: str, d: date):
    """aggTrades of one day -> (ts_ms, price, usd, side +1 taker buy); read through the archive's cache and deleted
    after each coin (AGG_CACHE removed: ~5-25 MB a day per coin
    would not fit the disk)."""
    if not SYMBOL.match(fid):
        return None
    path = f"futures/um/daily/aggTrades/{fid}/{fid}-aggTrades-{d.isoformat()}.zip"
    data = arch._fetch(path)
    if data is None:
        return None
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        raw = zf.read(zf.namelist()[0])
    has_header = not raw[:1].isdigit()
    df = pl.read_csv(raw, has_header=has_header,
                     new_columns=['id', 'price', 'qty', 'first', 'last', 'time', 'maker'])
    t = df['time'].to_numpy().astype(np.int64)
    if t.size and t[0] > 1e14:
        t = t // 1000
    p = df['price'].to_numpy().astype(np.float64)
    usd = p * df['qty'].to_numpy().astype(np.float64)
    maker = df['maker'].cast(pl.String).str.to_lowercase().to_numpy() == 'true'
    side = np.where(maker, -1, 1)
    return t, p, usd, side


def footprint(trades, since, until, bucket):
    t, p, usd, side = trades
    a, b = np.searchsorted(t, since), np.searchsorted(t, until)
    levels = {}
    for price, u, s in zip(p[a:b], usd[a:b], side[a:b]):
        cell = levels.setdefault(int(price // bucket), [0.0, 0.0])
        cell[0 if s > 0 else 1] += u
    return levels


def finished_auction(levels, direction, share=0.02):
    if len(levels) < 3:
        return False
    edge = min(levels) if direction > 0 else max(levels)
    buy, sell = levels[edge]
    total = buy + sell
    if total <= 0:
        return False
    return (sell if direction > 0 else buy) <= share * total


def features(t, d, ext_off, m1, books, trades):
    """The feature dict of one probe at time t (ms) for direction d; ext_off = t - extreme (ms) or None."""
    out = {}
    day = datetime.fromtimestamp(t / 1000, tz=timezone.utc).date()
    bk = books.get(day)
    if bk is not None:
        ts, b1, a1, b2, a2 = bk
        i = int(np.searchsorted(ts, t, side='right')) - 1
        if i >= 0 and t - ts[i] <= 300_000:
            out['imb1_with'] = d * (b1[i] - a1[i]) > 0
            out['imb2_with'] = d * (b2[i] - a2[i]) > 0
            j = int(np.searchsorted(ts, t - 1_800_000, side='right')) - 1
            if j >= 0 and abs(ts[j] - (t - 1_800_000)) <= 300_000:
                opp_now, opp_then = (a2[i], a2[j]) if d > 0 else (b2[i], b2[j])
                out['opp_thinned'] = opp_now < opp_then
    a = int(np.searchsorted(m1[:, 0], t - 75 * 60_000))
    b = int(np.searchsorted(m1[:, 0], t - 60_000, side='right'))          # minutes closed by t
    win = m1[a:b]
    if len(win) >= 15:
        delta = 2 * win[-15:, 7] - win[-15:, 6]
        out['delta15_with'] = d * delta.sum() > 0
    since = t - 1_800_000
    if ext_off is not None and 0 < ext_off <= 10 * 3_600_000:
        e = int(np.searchsorted(m1[:, 0], t - ext_off))
        seg = m1[e:b]
        if len(seg):
            out['delta_ext_with'] = d * (2 * seg[:, 7] - seg[:, 6]).sum() > 0
        since = max(t - ext_off, since)
    hour = m1[int(np.searchsorted(m1[:, 0], t - 3_600_000)):b]
    candles = hour[:, [0, 1, 2, 3, 4, 6, 7]].tolist()
    atr = minute_atr_15m(candles, t)
    if atr:
        out['absorption'] = absorption_in(candles, since, t, d, atr)
    tr = trades.get(day)
    if tr is not None and len(win):
        since_fp = max(since, int(day.toordinal() - date(1970, 1, 1).toordinal()) * DAY)
        levels = footprint(tr, since_fp, t, win[-1, 4] * 0.0005)
        if levels:
            out['stacked'] = stacked_imbalance(levels, d) >= CONFIG.orderflow.stacked_levels
            out['finished_auction'] = finished_auction(levels, d)
    return out


def boot_did(rows, feat, n_boot=2000, seed=11):
    """rows: dicts with cluster, kind ('entry'/'placebo'), R, feat value. Returns (stat, lo, hi, p, n_with, n_without)."""
    groups = {}
    for r in rows:
        if r.get(feat) is None or r['R'] is None or not np.isfinite(r['R']):
            continue
        groups.setdefault(tuple(r['cluster']), []).append((r['kind'] == 'entry', bool(r[feat]), r['R']))
    cl_with = {c for c, g in groups.items() if any(e and f for e, f, _ in g)}
    cl_without = {c for c, g in groups.items() if any(e and not f for e, f, _ in g)}
    if len(cl_with) < 30 or len(cl_without) < 30:
        return None
    keys = list(groups)

    def stat(sample):
        s = np.zeros((2, 2))
        n = np.zeros((2, 2))
        for k in sample:
            for e, f, r in groups[k]:
                s[int(e), int(f)] += r
                n[int(e), int(f)] += 1
        if (n == 0).any():
            return np.nan
        m = s / n
        return (m[1, 1] - m[1, 0]) - (m[0, 1] - m[0, 0])

    est = stat(keys)
    rng = np.random.default_rng(seed)
    draws = np.array([stat([keys[int(rng.integers(len(keys)))] for _ in keys]) for _ in range(n_boot)])
    draws = draws[np.isfinite(draws)]
    lo, hi = np.percentile(draws, [5, 95])
    below = (draws <= 0).mean()
    p = min(1.0, 2 * min(below, 1 - below) + 1 / len(draws))
    return est, lo, hi, p, len(cl_with), len(cl_without)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--groups', type=int, default=6, help='the run\'s first N groups = the 30 most liquid coins')
    ap.add_argument('--start', default='2026-04-01')
    ap.add_argument('--end', default='2026-09-30')
    ap.add_argument('--placebos', type=int, default=10)
    ap.add_argument('--rate', type=float, default=8e6)
    args = ap.parse_args()
    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc) + timedelta(days=1)
    s_ms, e_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    ents, cards = [], []
    for g in range(args.groups):
        for path in glob.glob(os.path.join(RUN, f'group_{g:02d}', '**', 'entries.parquet'), recursive=True):
            ents.append(pl.read_parquet(path))
            cards.append(pl.read_parquet(path.replace('entries.parquet', 'cards.parquet')))
    ent = pl.concat(ents, how='diagonal_relaxed').filter(
        (pl.col('stage') == 'entry') & pl.col('vetoed').is_null() & (pl.col('ts') >= s_ms) & (pl.col('ts') < e_ms))
    card = pl.concat(cards, how='diagonal_relaxed').filter(pl.col('entered_ms').is_not_null()).select(
        'symbol', 'setup', pl.col('entered_ms').alias('ts'), 'final_r').unique(['symbol', 'setup', 'ts'])
    ent = ent.join(card, on=['symbol', 'setup', 'ts'], how='inner')
    if 'f_anchor_ts' not in ent.columns:
        ent = ent.with_columns(pl.lit(None, pl.Int64).alias('f_anchor_ts'))
    log.info(f"{ent.height} passed entries with a card in {args.start} .. {args.end}")
    arch = Archive(rate_bytes=args.rate)
    rng = np.random.default_rng(7)
    ttl = CONFIG.levels.trade_ttl_sec * 1000
    rows = []
    for sym in sorted(ent['symbol'].unique().to_list()):
        se = ent.filter(pl.col('symbol') == sym)
        fid = sym.split('/')[0] + 'USDT'
        lo_day = (start - timedelta(days=121)).date()
        m1 = arch.klines_1m('futures', fid, lo_day, end.date())
        if len(m1) == 0:
            continue
        first, last = int(m1[0, 0]), int(m1[-1, 0])
        probes = []                                  # (kind, t, d, ext_off, entry_row, cluster)
        for r in se.iter_rows(named=True):
            t, d = int(r['ts']), int(r['direction'])
            ext = int(t - r['f_anchor_ts']) if r['f_anchor_ts'] else None
            cl = (t // H4, d)
            probes.append(('entry', t, d, ext, r, cl))
            for _ in range(args.placebos):
                for _try in range(50):
                    pt = t + int(rng.integers(-120, 121)) * DAY
                    if pt != t and first + DAY <= pt <= last - ttl and abs(pt - t) >= DAY:
                        probes.append(('placebo', pt, d, ext, r, cl))
                        break
        days = sorted({datetime.fromtimestamp(p[1] / 1000, tz=timezone.utc).date() for p in probes})
        books = {}
        for day in days:
            books[day] = book_day(arch, fid, day)
        for day in days:
            trades = {day: agg_day(arch, fid, day)}
            for kind, t, d, ext, r, cl in [p for p in probes
                                           if datetime.fromtimestamp(p[1] / 1000, tz=timezone.utc).date() == day]:
                f = features(t, d, ext, m1, books, trades)
                if kind == 'entry':
                    R = r['final_r']
                    a = int(np.searchsorted(m1[:, 0], t))
                    b = int(np.searchsorted(m1[:, 0], t + ttl))
                    lv = {k: r.get(k) for k in ('entry', 'sl', 'tp1', 'tp2', 'tp3', 'limit_entry', 'volume_24h')}
                    sim = simulate(lv, d, m1[a:b, :6].tolist(), funding_8h=r.get('funding'))
                    r_sim = net_r({'r_tp1': sim.get('r_tp1'), 'entry': lv['entry'], 'entry_fill': sim.get('entry_fill'),
                                   'sl': lv['sl']}, 'r_tp1') if sim.get('r_tp1') is not None else None
                else:
                    a = int(np.searchsorted(m1[:, 0], t))
                    b = int(np.searchsorted(m1[:, 0], t + ttl))
                    if a >= len(m1) or a == 0:
                        continue
                    px = m1[a - 1, 4]
                    k = px / r['entry']
                    lv = {key: (r[key] * k if r.get(key) is not None else None)
                          for key in ('entry', 'sl', 'tp1', 'tp2', 'tp3')}
                    lv['volume_24h'] = r.get('volume_24h')
                    sim = simulate(lv, d, m1[a:b, :6].tolist(), funding_8h=r.get('funding'))
                    R = net_r({'r_tp1': sim.get('r_tp1'), 'entry': lv['entry'], 'entry_fill': sim.get('entry_fill'),
                               'sl': lv['sl']}, 'r_tp1') if sim.get('r_tp1') is not None else None
                    r_sim = R
                rows.append(dict(kind=kind, strategy=r['strategy'], symbol=sym, ts=t, direction=d, cluster=cl,
                                 month=datetime.fromtimestamp(r['ts'] / 1000, tz=timezone.utc).strftime('%Y-%m'),
                                 R=R, r_sim=r_sim, **{k: f.get(k) for k in FEATURES}))
        shutil.rmtree(AGG_CACHE, ignore_errors=True)
        log.info(f"{sym}: {len(probes)} probes on {len(days)} days")
    df = pl.DataFrame(rows, infer_schema_length=None)
    os.makedirs('data/book_flow', exist_ok=True)
    df.write_parquet('data/book_flow/probes.parquet')
    report(df, args)


def report(df: pl.DataFrame, args):
    cells = []
    for strat in sorted(df['strategy'].unique().to_list()):
        sub = df.filter(pl.col('strategy') == strat).to_dicts()
        for feat in FEATURES:
            res = boot_did(sub, feat)
            if res is not None:
                cells.append(dict(strategy=strat, feature=feat, est=res[0], lo=res[1], hi=res[2], p=res[3],
                                  cl_with=res[4], cl_without=res[5]))
    qs = bh_q([c['p'] for c in cells])
    for c, q in zip(cells, qs):
        c['q'] = q
    passed = [c for c in cells if c['q'] is not None and c['q'] <= 0.10]
    ent = df.filter(pl.col('kind') == 'entry')
    lines = ['# Стакан и поток на входах: архив Binance (задача 2)', '',
             '## Итог', '',
             f"Входов: {ent.height} (eng-72 реплей, {args.groups * 5} самых ликвидных монет, {args.start} .. {args.end}), "
             f"плацебо: {df.height - ent.height}. Ячеек стратегия × признак с >= 30 кластерами по обе стороны: "
             f"{len(cells)}; прошли BH q <= 0.10: **{len(passed)}**.", '',
             'Правила зафиксированы до запуска в docstring `research_book_flow.py`. Спред (bookTicker) не проверялся: '
             'фьючерсный bookTicker в архиве обрывается на 2024-03-30.', '',
             '## Ячейки (R с признаком − R без, на входах, минус то же на плацебо; 90% кластерный бутстрэп)', '',
             '| стратегия | признак | DiD R | 90% | p | q | кластеров с / без |', '|---|---|---:|---|---:|---:|---|']
    for c in sorted(cells, key=lambda c: c['p']):
        lines.append(f"| {c['strategy']} | {c['feature']} | {c['est']:+.3f} | [{c['lo']:+.3f}..{c['hi']:+.3f}] | "
                     f"{c['p']:.3f} | {c['q']:.3f} | {c['cl_with']} / {c['cl_without']} |")
    if passed:
        lines += ['', '## Прошедшие ячейки по месяцам (только входы: R с − R без)', '']
        for c in passed:
            sub = ent.filter(pl.col('strategy') == c['strategy']).drop_nulls(c['feature'])
            lines.append(f"**{c['strategy']} / {c['feature']}**")
            lines.append('')
            lines.append('| месяц | с | без | n с / без |')
            lines.append('|---|---:|---:|---|')
            for m in sorted(sub['month'].unique().to_list()):
                s = sub.filter(pl.col('month') == m)
                w, wo = s.filter(pl.col(c['feature'])), s.filter(~pl.col(c['feature']))
                lines.append(f"| {m} | {w['R'].mean() if w.height else float('nan'):+.3f} | "
                             f"{wo['R'].mean() if wo.height else float('nan'):+.3f} | {w.height} / {wo.height} |")
            lines.append('')
    lines += ['', '## Покрытие признаков (доля входов, где признак посчитан)', '', '| признак | доля | доля True |',
              '|---|---:|---:|']
    for f in FEATURES:
        col = ent[f]
        lines.append(f"| {f} | {col.is_not_null().mean():.1%} | {col.drop_nulls().cast(pl.Float64).mean() or 0:.1%} |")
    with open(OUT, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
