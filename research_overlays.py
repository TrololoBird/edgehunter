"""
Exit overlays and the alts-vs-BTC filter (2026-10-05, the owner: "if we KNOW the setup is broken, do not wait for the
stop; react to a market crash / surge; BTC / USDT dominance").

Data: the replay's entries (research/replay_summary.parquet) with their 5m paths (history_cache, research_fetch5m.py),
BTC's 5m path for the shock overlay, every coin's 1h closes for the alt basket.

For each entry two base position-management plans are simulated (research_optimize.simulate): the method's own plan
(`plan`: the plan's TP1 for the whole position, 72h) and the strategy's profile (models/profiles.json, when it has
one). Each base is then cut by an OVERLAY that ends the trade earlier at a bar's close:
- noprog_H (H = 2 / 4 / 8 hours): after H hours the trade never traded +0.3R in its favour -> out (a setup that does
  not move is a broken setup: "a failed break usually resolves within about thirty minutes");
- struct: a 15m close (3 5m bars) at or below -0.5R -> out (the structure the trade stood on gave way; no wait for -1R);
- btc_K (K = 0.7 / 1.0 / 1.5 %), altcoins only: BTC moved K% against the trade over the last 15 minutes -> out
  (altcoins are BTC with a beta of 1.3-1.6; in cascades correlations go to 1);
- noprog_4 + btc_1.0 together.
The filter: `alts_with` = the median 4h return of the replay's coins minus BTC's, in the trade's direction, > 0 (the
alt basket leads BTC the trade's way: the risk-on / altseason side of the dominance reading).

PRE-REGISTERED RULE: per strategy x base, an overlay is ADOPTED when the per-trade difference overlay - base has a
mean > 0 with the lower 90% cluster bound > 0 on the first 8 months AND a mean > 0 on the last 4 months. The filter is
KEPT under the same rule applied to mean R(filtered) - mean R(all). Output: research/overlays.md,
models/exit_overlays.json ({strategy: {"base": "plan" | "profile", "overlays": [...]}} of the adopted ones).
"""
import json
from datetime import date, datetime, timezone

import numpy as np
import polars as pl

from history import Archive
from research_optimize import FEE, MAX_BARS, TRAIN_MONTHS, cluster_stats, simulate, slippage

HOUR = 3_600_000
BLOCK = 4 * HOUR
OVERLAYS = ['noprog_2', 'noprog_4', 'noprog_8', 'struct', 'btc_0.7', 'btc_1.0', 'btc_1.5', 'noprog_4+btc_1.0']
PLAN_PM = dict(target='plan', be=False, trail=0, half=False, hours=72, stop=1.0)


def overlay_exit(name: str, path: np.ndarray, d: int, entry: float, risk: float, btc_ret15: np.ndarray,
                 is_btc: bool) -> int:
    """Index of the 5m bar whose close ends the trade under the overlay (len(path) = never)."""
    n = len(path)
    out = n
    for part in name.split('+'):
        kind, _, arg = part.partition('_')
        if kind == 'noprog':
            k = int(arg) * 12 - 1
            if k < n:
                fav = ((path[:k + 1, 1] - entry) / risk) if d > 0 else ((entry - path[:k + 1, 2]) / risk)
                if fav.max() < 0.3:
                    out = min(out, k)
        elif kind == 'struct':
            closes = (path[2::3, 3] - entry) * d / risk
            hit = np.nonzero(closes <= -0.5)[0]
            if len(hit):
                out = min(out, int(hit[0]) * 3 + 2)
        elif kind == 'btc' and not is_btc:
            limit = float(arg) / 100
            against = d * btc_ret15[:n] <= -limit
            hit = np.nonzero(against)[0]
            if len(hit):
                out = min(out, int(hit[0]))
    return out


def main():
    arch = Archive(rate_bytes=300_000)
    ent = (pl.read_parquet('research/replay_summary.parquet')
           .filter(pl.col('r_tp1').is_not_null() & pl.col('entry').is_not_null() & pl.col('sl').is_not_null())
           .sort('ts'))
    profiles = json.load(open('models/profiles.json', encoding='utf-8'))
    t0, t1 = ent['ts'].min(), ent['ts'].max()
    first, last = (datetime.fromtimestamp(x / 1000, timezone.utc).date() for x in (t0, t1))
    start = date(first.year, first.month, 1)
    split = int(datetime(first.year + (first.month - 1 + TRAIN_MONTHS) // 12, (first.month - 1 + TRAIN_MONTHS) % 12 + 1,
                         1, tzinfo=timezone.utc).timestamp() * 1000)
    symbols = ent['symbol'].unique().sort().to_list()
    code = {s: s.split(':')[0].replace('/', '') for s in symbols}

    # the alt basket: median 4h return of the replay's coins, on a common 1h grid
    closes = {}
    for s in symbols:
        k = arch.klines_ohlc('futures', code[s], '1h', start, last)
        if len(k):
            closes[s] = dict(zip((k[:, 0] + HOUR).astype(np.int64).tolist(), k[:, 4].tolist()))
    grid = np.array(sorted(set().union(*[set(v) for v in closes.values()])), dtype=np.int64)
    mat = np.array([[closes[s].get(int(t), np.nan) for t in grid] for s in closes])
    r4 = mat[:, 4:] / mat[:, :-4] - 1
    basket = np.full(len(grid), np.nan)
    basket[4:] = np.nanmedian(r4, axis=0)
    btc_key = next(s for s in closes if s.startswith('BTC/'))
    btc_row = list(closes).index(btc_key)
    btc4 = np.full(len(grid), np.nan)
    btc4[4:] = r4[btc_row]

    btc5 = arch.klines_ohlc('futures', 'BTCUSDT', '5m', start, last)
    btc_open = btc5[:, 0]
    btc_close = btc5[:, 4]
    btc_r15 = np.concatenate((np.zeros(3), btc_close[3:] / btc_close[:-3] - 1))

    rows = []
    for s in symbols:
        part = ent.filter(pl.col('symbol') == s)
        k5 = arch.klines_ohlc('futures', code[s], '5m', start, last)
        if len(k5) < 1000:
            continue
        for r in part.iter_rows(named=True):
            ts, d = r['ts'], int(r['direction'])
            i5 = int(np.searchsorted(k5[:, 0], ts, side='right'))
            path = k5[i5:i5 + MAX_BARS, 1:5]
            if len(path) < 12:
                continue
            ib = int(np.searchsorted(btc_open, k5[i5, 0], side='left'))
            bret = btc_r15[ib:ib + len(path)]
            if len(bret) < len(path):
                bret = np.concatenate((bret, np.zeros(len(path) - len(bret))))
            jg = int(np.searchsorted(grid, ts, side='right')) - 1
            alts = (basket[jg] - btc4[jg]) * d if jg >= 4 else np.nan
            cost_r = (2 * FEE + 2 * slippage(r.get('volume_24h') or 0.0)) * r['entry'] / abs(r['entry'] - r['sl'])
            bases = {'plan': PLAN_PM}
            prof = (profiles.get(r['strategy']) or {}).get('pm')
            if prof:
                bases['profile'] = prof
            for bname, pm in bases.items():
                risk = abs(r['entry'] - r['sl']) * float(pm.get('stop') or 1.0)
                base_r = simulate(path, d, r['entry'], r['sl'], r.get('tp1') or 0.0, 0.0, pm, cost_r / pm['stop'])
                row = dict(strategy=r['strategy'], base=bname, ts=ts, cluster=ts // BLOCK * 2 + (d > 0),
                           alts_with=bool(alts > 0) if alts == alts else None, r_base=base_r)
                for ov in OVERLAYS:
                    k = overlay_exit(ov, path, d, r['entry'], risk, bret, s.startswith('BTC/'))
                    if k >= len(path):
                        row[ov] = base_r
                        continue
                    # the base's own exit if it came first, else out at the overlay bar's close
                    cut = simulate(path[:k + 1], d, r['entry'], r['sl'], r.get('tp1') or 0.0, 0.0,
                                   {**pm, 'hours': 10 ** 6}, cost_r / pm['stop'])
                    row[ov] = cut
                rows.append(row)
        print(f"{s}: {len(rows)} simulated", flush=True)

    df = pl.DataFrame(rows, infer_schema_length=None)
    lines = ['# Exit overlays and the alts-vs-BTC filter (research_overlays.py, pre-registered)', '',
             f'{df.height} trade x base rows; train < {datetime.fromtimestamp(split / 1000, timezone.utc):%Y-%m-%d} '
             '<= validation. Difference = overlay R - base R on the same trades.', '',
             '| strategy | base | overlay | train: n, diff [lower 90%] | validation: n, diff | verdict |',
             '|---|---|---|---|---|---|']
    adopted = {}
    for (strat, base), g in df.group_by(['strategy', 'base'], maintain_order=True):
        tr, va = g.filter(pl.col('ts') < split), g.filter(pl.col('ts') >= split)
        if tr.height < 50:
            continue
        best = None
        for ov in OVERLAYS + ['filter:alts_with']:
            if ov.startswith('filter'):
                a = tr.filter(pl.col('alts_with') == True)       # noqa: E712
                m_in, lo, _ = cluster_stats(a['r_base'].to_numpy(), a['cluster'].to_numpy())
                m_all = tr['r_base'].mean()
                diff, lo_d = m_in - m_all, lo - m_all
                v = va.filter(pl.col('alts_with') == True)       # noqa: E712
                vdiff = (v['r_base'].mean() - va['r_base'].mean()) if v.height and va.height else np.nan
                nt, nv = a.height, v.height
            else:
                dd = (tr[ov] - tr['r_base']).to_numpy()
                diff, lo_d, _ = cluster_stats(dd, tr['cluster'].to_numpy())
                vdiff = float((va[ov] - va['r_base']).mean()) if va.height else np.nan
                nt, nv = tr.height, va.height
            verdict = 'ADOPT' if lo_d > 0 and vdiff > 0 else 'no'
            lines.append(f'| {strat} | {base} | {ov} | {nt}, {diff:+.3f} [{lo_d:+.3f}] | {nv}, {vdiff:+.3f} | {verdict} |')
            if verdict == 'ADOPT' and (best is None or diff > best[1]):
                best = (ov, diff)
        if best:
            adopted.setdefault(strat, {})[base] = best[0]
    lines += ['', 'Base means (train / validation): '] + [
        f"- {s} {b}: {g.filter(pl.col('ts') < split)['r_base'].mean():+.3f} / {g.filter(pl.col('ts') >= split)['r_base'].mean():+.3f}"
        for (s, b), g in df.group_by(['strategy', 'base'], maintain_order=True)]
    with open('research/overlays.md', 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    with open('models/exit_overlays.json', 'w', encoding='utf-8') as fh:
        json.dump(adopted, fh, indent=1)
    print('\n'.join(lines))
    print('adopted:', adopted)


if __name__ == '__main__':
    main()
