#!/usr/bin/env python3
"""Fail-fast check for sufficient replay history before expensive jobs."""
import argparse, json
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--manifest', required=True); ap.add_argument('--min-days', type=int, default=90); a=ap.parse_args()
    data=json.loads(Path(a.manifest).read_text())
    rows=data.get('coins') or data.get('symbols') or []
    bad=[]
    for row in rows:
        if isinstance(row, str): continue
        if (row.get('history_days') or 0) < a.min_days: bad.append(row.get('symbol') or row.get('key'))
    result={'ready': not bad and bool(rows), 'required_days': a.min_days, 'insufficient': bad}
    print(json.dumps(result, ensure_ascii=False, indent=2)); raise SystemExit(0 if result['ready'] else 2)
if __name__ == '__main__': main()
