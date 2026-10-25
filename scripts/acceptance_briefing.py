"""
False acceptance of the published briefing zones (eng-168z1, audit #9) - a DESCRIPTIVE measurement of the zones the
briefings actually showed (frozen in data/briefings.jsonl), not of today's map and not a backtest of new rules.

Per published record (silent ones excluded) and zone: the first CONFIRMING close after the post - a close above the
zone's hi (up) or below its lo (down) on the confirmation timeframe - when price was NOT already beyond that edge at the
post. Counted twice, independently, on 1h and on 4h closes (the paired report), and once on the zone's own conf_tf when
the record has it (the policy report). After the confirming close, on the 1h closes that follow (the clock starts at
the confirming candle's CLOSE, for 1h and 4h alike), within N = 1 / 2 / 4 / 8 / 12 hours:
  inside  - a 1h close back between lo and hi;
  origin  - a 1h close back beyond the opposite edge (the side the move came from);
  retouch - a 1h candle's range back into the band (wick, the close may stay beyond).
F_N = events with that return within N h / confirmations with the full N h observed (younger ones are left out of the
denominator, not counted as held). One breakout of one zone posted in several briefings counts once (key: coin, zone
edges rounded to 0.1 ATR, direction, confirming candle).
Zone type: the timeframes of its pivots from the saved 'tfs' (new records) or parsed from its description '(1h/4h)'.
    PYTHONPATH=. .venv/bin/python scripts/acceptance_briefing.py [days=16]
"""
import json
import re
import sys
import time
import urllib.request
from collections import defaultdict

H = 3_600_000
H4 = 4 * H
HORIZONS = (1, 2, 4, 8, 12)
days = int(sys.argv[1]) if len(sys.argv) > 1 else 16
now = time.time() * 1000


def klines(sym):
    out = []
    end = None
    for _ in range(2):                          # ~1500 + 1500 hours back
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval=1h&limit=1500" + (f"&endTime={end}" if end else '')
        rows = [[float(x) for x in k[:5]] for k in json.load(urllib.request.urlopen(url, timeout=25))]
        out = rows + out
        end = int(rows[0][0]) - 1
    seen = {}
    for r in out:
        seen[int(r[0])] = r
    return [seen[t] for t in sorted(seen) if t + H <= now]


def to_4h(bars):
    g = defaultdict(dict)
    for b in bars:
        g[int(b[0]) // H4 * H4][int(b[0])] = b
    out = []
    for t in sorted(g):
        hrs = g[t]
        if sorted(hrs) == [t + k * H for k in range(4)]:
            v = [hrs[k] for k in sorted(hrs)]
            out.append([t, v[0][1], max(x[2] for x in v), min(x[3] for x in v), v[-1][4]])
    return out


def zone_type(z):
    tfs = z.get('tfs') or re.findall(r'\b(1h|4h|1d|1w)\b', (re.search(r'\(([^)]*)\)', z.get('desc') or '') or ['', ''])[1])
    if z.get('map_level') or 'уровень карты' in (z.get('desc') or ''):
        return 'map level'
    return 'pivots 4h+' if set(tfs) & {'4h', '1d', '1w'} else ('pivots 1h only' if tfs else 'unknown')


recs = [json.loads(x) for x in open('data/briefings.jsonl') if x.strip()]
recs = [r for r in recs if r['ts'] * 1000 > now - days * 86_400_000 and not r.get('silent') and r.get('zones')]
K = {s: klines(s.split('/')[0] + 'USDT') for s in {r['symbol'] for r in recs}}
K4 = {s: to_4h(v) for s, v in K.items()}

events = {}                                     # key -> event (dedup)
for r in recs:
    post = r['ts'] * 1000
    h1 = K[r['symbol']]
    price_at = next((b[4] for b in reversed(h1) if b[0] + H <= post), None)
    if price_at is None:
        continue
    atr = sum(b[2] - b[3] for b in h1 if post - 24 * H <= b[0] < post) / 24 or 1.0
    for z in r['zones']:
        lo, hi = z['lo'], z['hi']
        policy = z.get('conf_tf')
        for tf, bars in (('1h', h1), ('4h', K4[r['symbol']])):
            step = H if tf == '1h' else H4
            for d, edge in ((1, hi), (-1, lo)):
                if d * (price_at - edge) > 0:
                    continue                    # already beyond this edge at the post: no new confirmation
                conf = next((b for b in bars if b[0] >= post and d * (b[4] - edge) > 0), None)
                if conf is None:
                    continue
                t_conf = conf[0] + step         # the confirming close
                key = (r['symbol'], round(lo / (0.1 * atr)), round(hi / (0.1 * atr)), d, tf, conf[0])
                if key in events:
                    continue
                after = [b for b in h1 if b[0] >= t_conf]
                res = {}
                for n in HORIZONS:
                    win = [b for b in after if b[0] < t_conf + n * H]
                    if t_conf + n * H > now or len(win) < n:
                        res[n] = None           # not fully observed
                        continue
                    res[n] = {'inside': any(lo <= b[4] <= hi for b in win),
                              'origin': any(d * (b[4] - (lo if d > 0 else hi)) < 0 for b in win),
                              'retouch': any(b[3] <= hi and b[2] >= lo for b in win)}
                events[key] = {'sym': r['symbol'].split('/')[0], 'tf': tf, 'dir': d, 'type': zone_type(z),
                               'policy': policy == tf if policy else None, 'res': res}


def report(title, sel):
    ev = [e for e in events.values() if sel(e)]
    print(f"\n{title}: confirmations {len(ev)}")
    for n in HORIZONS:
        obs = [e['res'][n] for e in ev if e['res'].get(n)]
        if not obs:
            continue
        f = lambda k: sum(o[k] for o in obs) / len(obs) * 100
        print(f"  {n:>2}h (n={len(obs):3}): inside {f('inside'):5.1f}%  origin {f('origin'):5.1f}%  retouch {f('retouch'):5.1f}%")


print(f"published records {len(recs)} over {days} days, unique confirmations {len(events)}")
for tf in ('1h', '4h'):
    for ty in ('pivots 1h only', 'pivots 4h+', 'map level', 'unknown'):
        if any(e['tf'] == tf and e['type'] == ty for e in events.values()):
            report(f"[paired] {tf} close, zone {ty}", lambda e, tf=tf, ty=ty: e['tf'] == tf and e['type'] == ty)
if any(e['policy'] for e in events.values()):
    report('[policy] the zone\'s own conf_tf (records since eng-168y)', lambda e: e['policy'] is True)
