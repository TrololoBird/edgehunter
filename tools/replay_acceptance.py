#!/usr/bin/env python3
"""Cluster-weighted acceptance statistics for replay/funnel evidence."""
import argparse, json, random, statistics
from collections import defaultdict

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('csv'); ap.add_argument('--value',default='demo_r'); ap.add_argument('--cluster',default='cluster_4h_id'); ap.add_argument('--bootstrap',type=int,default=2000); a=ap.parse_args()
    import csv
    groups=defaultdict(list)
    with open(a.csv, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try: v=float(row[a.value])
            except (KeyError,TypeError,ValueError): continue
            groups[row.get(a.cluster) or row.get('ts_ms','unknown')].append(v)
    means=[statistics.fmean(v) for v in groups.values() if v]
    if not means: result={'clusters':0,'mean':None,'ci95':[None,None]}
    else:
        random.seed(13)
        samples=[statistics.fmean(random.choices(means,k=len(means))) for _ in range(a.bootstrap)]
        samples.sort(); result={'clusters':len(means),'mean':statistics.fmean(means),
            'ci95':[samples[int(.025*len(samples))],samples[int(.975*len(samples))-1]]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
if __name__ == '__main__': main()
