#!/usr/bin/env python3
"""Build the auditable card -> execution -> closed funnel from journal/demo SQLite."""
import argparse, csv, sqlite3
from collections import defaultdict

FAMILIES = ('trendline','pump','bollinger','breakout','continuation')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--signals',required=True); ap.add_argument('--demo',required=True); ap.add_argument('--out',required=True); ap.add_argument('--logic-version',default='eng-169l'); a=ap.parse_args()
    s=sqlite3.connect(a.signals); s.row_factory=sqlite3.Row; d=sqlite3.connect(a.demo); d.row_factory=sqlite3.Row
    q='''select * from signals where kind='card' and logic_version=? and strategy in (?,?,?,?,?) order by ts_ms'''
    out=[]
    for r in s.execute(q,(a.logic_version,*FAMILIES)):
        x=dict(r); card=x.get('card_id'); trades=[dict(t) for t in d.execute('select * from demo_trades where card_id=? order by opened_ms desc',(card,))] if card else []
        t=trades[0] if trades else {}
        reason=' '.join(str(x.get(k) or '') for k in ('reason','vetoed','shadow_veto')).lower(); close=t.get('close_reason')
        if t.get('r') is not None: stage='closed_trade'
        elif close in {'NO_SLOT','OVERLAP'} or 'unit_limit' in reason: stage='blocked_capacity'
        elif close in {'NO_MARKET','PRICE_GAP','NOT_FILLED','LATE_FILL'} or 'low_rr' in reason or 'veto' in reason: stage='vetoed_or_execution_drop'
        elif t: stage='entered_open_or_unresolved'
        else: stage='card_without_demo'
        out.append({'card_id':card,'ts_ms':x.get('ts_ms'),'symbol':x.get('symbol'),'strategy':x.get('strategy'),'setup':x.get('group_key'),'direction':x.get('direction'),'logic_version':x.get('logic_version'),'regime':x.get('regime2') or x.get('regime'),'reason':reason,'data_quality_ok':x.get('data_quality_ok'),'card_r':x.get('card_r'),'mfe_r':x.get('mfe_r'),'mae_r':x.get('mae_r'),'demo_id':t.get('id'),'demo_r':t.get('r'),'close_reason':close,'stage':stage,'cluster_4h_id':(int(x['ts_ms'])//(4*3600*1000),x.get('direction')) if x.get('ts_ms') else None})
    fields=list(out[0]) if out else []
    with open(a.out,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(out)
    agg=defaultdict(lambda: defaultdict(float))
    clusters=defaultdict(set)
    for r in out:
        k=(r['strategy'],r['setup'],r['direction'],r['regime'])
        agg[k][r['stage']]+=1; clusters[k].add(r['cluster_4h_id'])
        if r['stage']=='closed_trade': agg[k]['closed_card_r']+=float(r['card_r'] or 0); agg[k]['closed_n']+=1
    summary_path = a.out[:-4] + '.summary.csv' if a.out.endswith('.csv') else a.out + '.summary.csv'
    with open(summary_path,'w',newline='',encoding='utf-8') as f:
        cols=['strategy','setup','direction','regime','total_cards','closed_trade','blocked_capacity','vetoed_or_execution_drop','entered_open_or_unresolved','card_without_demo','closed_card_r','clusters_4h']
        w=csv.DictWriter(f,fieldnames=cols); w.writeheader()
        for k,v in sorted(agg.items(), key=lambda item: tuple('' if x is None else str(x) for x in item[0])):
            total=sum(v.get(stage,0) for stage in ('closed_trade','blocked_capacity','vetoed_or_execution_drop','entered_open_or_unresolved','card_without_demo'))
            w.writerow(dict(zip(cols,[*k,int(total),int(v['closed_trade']),int(v['blocked_capacity']),int(v['vetoed_or_execution_drop']),int(v['entered_open_or_unresolved']),int(v['card_without_demo']),round(v['closed_card_r'],6),len(clusters[k])])) )
    print(f'rows={len(out)} summary={len(agg)} out={a.out} summary_out={summary_path}')
if __name__=='__main__': main()
