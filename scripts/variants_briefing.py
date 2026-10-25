"""
Variants on the SAME entered briefing scenarios (eng-169 audit #10 check): every saved scenario of the last N days is
replayed with ONE rule changed at a time, scored with execution_model_v1 (Briefing.exec_detail: 50% at +1R, the rest at
break-even + costs to TP2, costs included) over the 72h horizon. A measurement of proposals on the scenarios the
briefings actually published - not a search for parameters.
  base      - as published: entry at the reaction candle's close, the scenario's stop and targets;
  tp_obst   - TP1 = the nearest obstacle beyond the entry by >= 1R: a raw sr.zones cluster rebuilt from candles before
              the post or PDH / PDL / PWH / PWL (audit: TP1 on the first real barrier), TP2 = the old TP1;
  stop_own  - stop at the scenario zone's far edge - 0.25 ATR(1h) (audit: no push_stop cascade, no big pad);
  retest    - after the reaction close, a limit at the zone's near edge (e1) within 6h, else no trade (audit: entry
              on the retest, not the reaction close);
  taker     - base, kept only when the reaction candle's taker-buy share agrees (>= 0.52 long, <= 0.48 short);
  react_4h  - the reaction looked for on complete 4h candles instead of 1h (the eng-168y policy for 4h zones).
    PYTHONPATH=. .venv/bin/python scripts/variants_briefing.py [days=16]
"""
import json
import sys
import time
import urllib.request

import sr
from briefing import Briefing, HOUR_MS, to_4h
from levels import atr_of

DAY = 86_400_000
days = int(sys.argv[1]) if len(sys.argv) > 1 else 16
now = time.time() * 1000


def kl(sym, tf, n):
    rows = json.load(urllib.request.urlopen(
        f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval={tf}&limit={n}", timeout=25))
    return [[float(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[7]), float(k[10])] for k in rows]


recs = [json.loads(x) for x in open('data/briefings.jsonl') if x.strip()]
recs = [r for r in recs if r['ts'] * 1000 > now - days * DAY and r.get('scenario')]
K = {}
for s in sorted({r['symbol'] for r in recs}):
    b = s.split('/')[0] + 'USDT'
    K[s] = {'1h': kl(b, '1h', 1500), '4h': kl(b, '4h', 600), '1d': kl(b, '1d', 300)}

res = {k: {'n': 0, 'r': 0.0, 'tp1': 0, 'stop': 0} for k in ('base', 'tp_obst', 'stop_own', 'retest', 'taker', 'react_4h')}


def add(key, det):
    if det and det.get('exec_r') is not None:
        a = res[key]
        a['n'] += 1
        a['r'] += det['exec_r']
        a['tp1'] += det['tp1_hit']
        a['stop'] += det['stop_hit']


for r in recs:
    k = K[r['symbol']]
    post = r['ts'] * 1000
    first = (int(post) // HOUR_MS + 1) * HOUR_MS
    full = [x for x in k['1h'] if first <= x[0] < post + 72 * HOUR_MS and x[0] + HOUR_MS <= now]
    bars = [x[:5] for x in full]
    before = {tf: [x[:6] for x in k[tf] if x[0] + {'1h': HOUR_MS, '4h': 4 * HOUR_MS, '1d': DAY}[tf] <= post] for tf in k}
    if len(before['1h']) < 30:
        continue
    a1h = atr_of(before['1h'][-200:])
    raw = sr.zones(before, post, tol=0.6 * a1h, max_width=1.5 * a1h)
    d1 = before['1d']
    pd = [d1[-1][2], d1[-1][3]] + ([max(x[2] for x in d1[-7:]), min(x[3] for x in d1[-7:])] if len(d1) >= 7 else [])
    for key, side in (('long', 1), ('short', -1)):
        sc = r['scenario'].get(key)
        if not sc:
            continue
        e0, e1 = sorted(sc['entry'])
        txt, _, _, entry = Briefing.score_detail(sc, side, bars)
        if entry is None:
            continue
        i = next(j for j, x in enumerate(bars) if x[0] + HOUR_MS == entry)
        fill, after = bars[i][4], bars[i + 1:]
        risk = abs(fill - sc['stop'])
        base = Briefing.exec_detail(sc, side, fill, after)
        add('base', base)
        # tp_obst
        obs = sorted([z['lo'] if side > 0 else z['hi'] for z in raw] + pd, key=lambda p: side * (p - fill))
        near = next((p for p in obs if side * (p - fill) >= risk), None)
        if near is not None and side * (near - sc['targets'][0]) < 0:
            add('tp_obst', Briefing.exec_detail(dict(sc, targets=[near, sc['targets'][0]]), side, fill, after))
        else:
            add('tp_obst', base)
        # stop_own
        far = e0 if side > 0 else e1
        stop2 = far - side * 0.25 * a1h
        add('stop_own', Briefing.exec_detail(dict(sc, stop=stop2), side, fill, after)
            if side * (fill - stop2) > 0 else base)
        # retest: a limit at the zone's near edge within 6h after the reaction close
        lim = e1 if side > 0 else e0
        j = next((j for j, x in enumerate(after[:6]) if (x[3] <= lim if side > 0 else x[2] >= lim)), None)
        if j is not None and side * (lim - sc['stop']) > 0:
            add('retest', Briefing.exec_detail(sc, side, lim, after[j:]))
        # taker filter on the reaction candle
        rc = full[i]
        share = rc[6] / rc[5] if rc[5] else 0.5
        if (side > 0 and share >= 0.52) or (side < 0 and share <= 0.48):
            add('taker', base)
        # reaction on 4h
        b4 = to_4h(bars)
        txt4, _, _, entry4 = Briefing.score_detail(sc, side, b4)
        j4 = next((j for j, x in enumerate(b4) if x[0] + 4 * HOUR_MS == entry4), None) if entry4 else None
        if j4 is not None:
            add('react_4h', Briefing.exec_detail(sc, side, b4[j4][4], [x for x in bars if x[0] >= entry4]))

print(f"scenario records {len(recs)} over {days} days; R = execution_model_v1, costs included")
for key, a in res.items():
    if a['n']:
        print(f"{key:9} n {a['n']:3}  TP1 {a['tp1']:3}  stop {a['stop']:3}  total {a['r']:+7.2f}R  per trade {a['r'] / a['n']:+.3f}R")
