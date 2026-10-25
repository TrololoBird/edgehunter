"""Diagnostic (eng-168u): every saved briefing scenario of the last 16 days replayed on Binance 1h - entered / TP1 /
stop, TP1 distance vs MFE / MAE in R, by scenario type and TP1 distance. Run from the bot directory:
    PYTHONPATH=. .venv/bin/python scripts/diag_briefing.py
A measurement of the rules as they ran, not a backtest of new ones."""
import json, time, urllib.request, statistics as st, collections
from briefing import Briefing, HOUR_MS
recs=[json.loads(l) for l in open('data/briefings.jsonl') if l.strip()]
now=time.time()*1000
recs=[r for r in recs if r['ts']*1000 > now-16*86400000 and r.get('scenario')]
K={}
for s in sorted({r['symbol'] for r in recs}):
    b=s.split('/')[0]+'USDT'
    K[s]=[[float(x) for x in k[:5]] for k in json.load(urllib.request.urlopen(f"https://fapi.binance.com/fapi/v1/klines?symbol={b}&interval=1h&limit=500",timeout=20)) if k[0]+HOUR_MS<=now]
rows=[]
for r in recs:
    c=K[r['symbol']]; post=r['ts']*1000; first=(int(post)//HOUR_MS+1)*HOUR_MS
    bars=[x for x in c if first<=x[0]<post+72*HOUR_MS]
    for key,side in (('long',1),('short',-1)):
        sc=r['scenario'].get(key)
        if not sc: continue
        txt,res,rv,entry=Briefing.score_detail(sc,side,bars)
        row={'sym':r['symbol'].split('/')[0],'side':side,'tag':sc.get('tag',''),'txt':txt,'silent':r.get('silent',False),'sc':sc}
        if entry is not None:
            fill=next(x[4] for x in bars if x[0]+HOUR_MS==entry); risk=abs(fill-sc['stop'])
            after=[x for x in bars if x[0]>=entry]
            d=Briefing.exec_detail(sc,side,fill,after)
            row.update(det=d, tp1_r=side*(sc['targets'][0]-fill)/risk, risk_pct=risk/fill*100)
        rows.append(row)
cls=collections.Counter(Briefing._outcome_class(x['txt']) for x in rows)
print('scenarios',len(rows),dict(cls))
ent=[x for x in rows if 'det' in x]
print('entered',len(ent))
def q(v): v=sorted(v); return [round(v[int(len(v)*p)],2) for p in (0.25,0.5,0.75)] if v else None
print('TP1 distance R (q25/50/75):',q([x['tp1_r'] for x in ent]))
print('MFE R               :',q([x['det']['mfe_r'] for x in ent]))
print('MAE R               :',q([x['det']['mae_r'] for x in ent]))
print('risk % of price     :',q([x['risk_pct'] for x in ent]))
reach=[x['det']['mfe_r']/x['tp1_r'] for x in ent if x['tp1_r']>0]
print('MFE / TP1 distance  :',q(reach))
print('reached >=50% of TP1 path:',sum(r_>=0.5 for r_ in reach),'| >=80%:',sum(r_>=0.8 for r_ in reach),'| TP1 hit:',sum(x['det']['tp1_hit'] for x in ent),'| stop first:',sum(x['det']['stop_hit'] for x in ent),'of',len(ent))
print('reached +1R (partial):',sum(x['det']['mfe_r']>=1 for x in ent))
by=collections.defaultdict(list)
for x in ent: by[(x['tag'],'L' if x['side']>0 else 'S')].append(x)
for k,v in sorted(by.items(),key=lambda kv:-len(kv[1])):
    print(k,len(v),'TP1',sum(x['det']['tp1_hit'] for x in v),'stop',sum(x['det']['stop_hit'] for x in v),'medTP1R',round(st.median([x['tp1_r'] for x in v]),2),'medMFE',round(st.median([x['det']['mfe_r'] for x in v]),2),'execR',round(sum(x['det']['exec_r'] or 0 for x in v),2), 'reach1R', sum(x['det']['mfe_r']>=1 for x in v))
# reached +1R BEFORE the stop vs TP1 distance buckets
print('--- by TP1 distance (R from the fill)')
for lo_,hi_ in ((1,1.5),(1.5,2),(2,3),(3,99)):
    v=[x for x in ent if lo_<=x['tp1_r']<hi_]
    if v: print(f"TP1 {lo_}-{hi_}R: n {len(v)}, TP1 hit {sum(x['det']['tp1_hit'] for x in v)}, stop {sum(x['det']['stop_hit'] for x in v)}, +1R reached {sum(x['det']['mfe_r']>=1 for x in v)}, execR {round(sum(x['det']['exec_r'] or 0 for x in v),2)}, tp1-only R {round(sum((x['tp1_r'] if x['det']['tp1_hit'] else (-1 if x['det']['stop_hit'] else 0)) for x in v),2)}")
print('silent vs posted:', {k: (len(v), sum(x['det']['tp1_hit'] for x in v)) for k, v in {'posted':[x for x in ent if not x['silent']], 'silent':[x for x in ent if x['silent']]}.items()})
