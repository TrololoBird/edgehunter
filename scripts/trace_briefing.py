"""
Trace of the entered briefing scenarios (eng-168v, audit #7): per scenario the real geometry after the reaction, the
excursions BEFORE the first stop vs over the whole 72h, the first outcome and its time, and the obstacles between the
entry and TP1 that existed at the post:
- ladder: the zones the briefing itself published (record['zones']) - by construction none should lie in between;
- raw:    the sr.zones clusters rebuilt from Binance candles closed BEFORE the post (the same call key_zones makes,
          before its span filter, merge and ladder) - a raw zone in between = an obstacle the ladder dropped or merged;
- pdhl:   the previous day / week high / low from the closed daily candles (the map's PDH / PDL / PWH / PWL; the other
          map levels - FVG / OB / POC - cannot be rebuilt offline and are not counted).
Writes data/trace_briefing.csv and prints a summary plus the N worst traces. A measurement of the rules as they ran.
    PYTHONPATH=. .venv/bin/python scripts/trace_briefing.py [days=16] [traces=5]
"""
import csv
import json
import statistics as st
import sys
import time
import urllib.request

import sr
from briefing import Briefing, HOUR_MS
from levels import atr_of

DAY = 86_400_000
days = int(sys.argv[1]) if len(sys.argv) > 1 else 16
n_traces = int(sys.argv[2]) if len(sys.argv) > 2 else 5
now = time.time() * 1000


def klines(sym, tf, n, end=None):
    url = (f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval={tf}&limit={n}"
           + (f"&endTime={int(end)}" if end else ''))
    return [[float(x) for x in k[:6]] for k in json.load(urllib.request.urlopen(url, timeout=25))]


recs = [json.loads(x) for x in open('data/briefings.jsonl') if x.strip()]
recs = [r for r in recs if r['ts'] * 1000 > now - days * DAY and r.get('scenario')]
K = {}
for s in sorted({r['symbol'] for r in recs}):
    b = s.split('/')[0] + 'USDT'
    K[s] = {'1h': klines(b, '1h', 1500), '4h': klines(b, '4h', 600), '1d': klines(b, '1d', 300)}

rows = []
for r in recs:
    k = K[r['symbol']]
    post = r['ts'] * 1000
    first = (int(post) // HOUR_MS + 1) * HOUR_MS
    bars = [x[:5] for x in k['1h'] if first <= x[0] < post + 72 * HOUR_MS and x[0] + HOUR_MS <= now]
    before = {tf: [x for x in k[tf] if x[0] + {'1h': HOUR_MS, '4h': 4 * HOUR_MS, '1d': DAY}[tf] <= post] for tf in k}
    if len(before['1h']) < 30:
        continue
    a1h = atr_of(before['1h'][-200:])
    raw = sr.zones(before, post, tol=0.6 * a1h, max_width=1.5 * a1h)
    d1 = before['1d']
    pdhl = ([('PDH', d1[-1][2]), ('PDL', d1[-1][3])] if d1 else []) + \
        ([('PWH', max(x[2] for x in d1[-7:])), ('PWL', min(x[3] for x in d1[-7:]))] if len(d1) >= 7 else [])
    for key, side in (('long', 1), ('short', -1)):
        sc = r['scenario'].get(key)
        if not sc:
            continue
        txt, resolved, rv, entry = Briefing.score_detail(sc, side, bars)
        if entry is None:
            continue
        fill = next(x[4] for x in bars if x[0] + HOUR_MS == entry)
        after = [x for x in bars if x[0] >= entry]
        stop, tp1 = sc['stop'], sc['targets'][0]
        risk = abs(fill - stop)
        if not risk or not after:
            continue
        # excursions before the first stop touch, the whole window, and the MAE before the first outcome
        mfe_pre = mfe_all = 0.0
        mae_pre = 0.0
        first_out, first_h = 'open', None
        for c in after:
            fav = side * ((c[2] if side > 0 else c[3]) - fill) / risk
            adv = side * ((c[3] if side > 0 else c[2]) - fill) / risk
            mfe_all = max(mfe_all, fav)
            if first_out == 'open':
                stop_now = adv <= -1.0
                tp_now = side * ((c[2] if side > 0 else c[3]) - tp1) >= 0
                mae_pre = min(mae_pre, adv)
                if stop_now:                         # in one candle with TP1: the stop (order unknown)
                    first_out = 'stop' + ('?' if tp_now else '')
                    first_h = (c[0] + HOUR_MS - after[0][0]) / HOUR_MS
                    mfe_pre = max(mfe_pre, fav if not tp_now else mfe_pre)
                    continue
                mfe_pre = max(mfe_pre, fav)
                if tp_now:
                    first_out, first_h = 'tp1', (c[0] + HOUR_MS - after[0][0]) / HOUR_MS
        lo_, hi_ = sorted((fill, tp1))
        between = lambda p: lo_ < p < hi_
        lad = [z for z in (r.get('zones') or []) if between(z['lo']) or between(z['hi'])]
        rw = [z for z in raw if (between(z['lo']) or between(z['hi'])) and not
              any(abs(z['price'] - (y['lo'] + y['hi']) / 2) < 1e-9 * z['price'] + 0.5 * a1h for y in (r.get('zones') or []))]
        near_raw = min(rw, key=lambda z: abs(z['price'] - fill)) if rw else None
        pdl = [(n, p) for n, p in pdhl if between(p)]
        rows.append({
            'sym': r['symbol'].split('/')[0], 'side': 'L' if side > 0 else 'S', 'tag': sc.get('tag', ''),
            'rules_v': r.get('rules_v') or 'old', 'silent': int(bool(r.get('silent'))),
            'post': time.strftime('%m-%d %H:%M', time.gmtime(post / 1000)),
            'fill': fill, 'stop': stop, 'tp1': tp1, 'tp2': sc['targets'][1] if len(sc['targets']) > 1 else '',
            'stop_atr1h': round(risk / a1h, 2), 'risk_pct': round(risk / fill * 100, 2),
            'tp1_r': round(side * (tp1 - fill) / risk, 2), 'tp1_atr1h': round(abs(tp1 - fill) / a1h, 2),
            'mfe_pre_stop_r': round(mfe_pre, 2), 'mfe_72h_r': round(mfe_all, 2), 'mae_pre_r': round(mae_pre, 2),
            'first': first_out, 'first_h': first_h,
            'ladder_between': len(lad), 'raw_between': len(rw),
            'raw_nearest_r': round(side * (near_raw['price'] - fill) / risk, 2) if near_raw else '',
            'raw_nearest_str': round(near_raw['strength'], 1) if near_raw else '',
            'raw_nearest_tfs': '/'.join(near_raw['tfs']) if near_raw else '',
            'pdhl_between': ','.join(f"{n}@{round(side * (p - fill) / risk, 2)}R" for n, p in pdl),
        })

with open('data/trace_briefing.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)


def q(v):
    v = sorted(v)
    return [round(v[int(len(v) * p)], 2) for p in (0.25, 0.5, 0.75)] if v else None


print(f"entered {len(rows)} (data/trace_briefing.csv)")
for k in ('stop_atr1h', 'risk_pct', 'tp1_r', 'tp1_atr1h', 'mfe_pre_stop_r', 'mfe_72h_r', 'mae_pre_r'):
    print(f"{k:16} q25/50/75 {q([x[k] for x in rows])}")
fo = {}
for x in rows:
    fo[x['first']] = fo.get(x['first'], 0) + 1
print('first outcome', fo)
stops = [x for x in rows if x['first'].startswith('stop')]
print(f"stops {len(stops)}: MFE before the stop q {q([x['mfe_pre_stop_r'] for x in stops])}, MFE 72h q "
      f"{q([x['mfe_72h_r'] for x in stops])}, TP1 reached after the stop "
      f"{sum(x['mfe_72h_r'] >= x['tp1_r'] for x in stops)}")
for name, sel in (('raw zone between entry and TP1', lambda x: x['raw_between'] > 0),
                  ('PDH/PDL/PWH/PWL between', lambda x: bool(x['pdhl_between'])),
                  ('none of them', lambda x: not x['raw_between'] and not x['pdhl_between'])):
    v = [x for x in rows if sel(x)]
    if v:
        print(f"{name:32} n {len(v):3} tp1 {sum(x['first'] == 'tp1' for x in v):3} stop "
              f"{sum(x['first'].startswith('stop') for x in v):3} median TP1 {st.median([x['tp1_r'] for x in v])}R")
print('ladder zones between entry and TP1 (should be 0):', sum(x['ladder_between'] for x in rows))
print('\n--- traces: stops with an obstacle in between, the farthest MFE before the stop first')
for x in sorted([x for x in stops if x['raw_between'] or x['pdhl_between']], key=lambda x: -x['mfe_pre_stop_r'])[:n_traces]:
    print(x)
