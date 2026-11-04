#!/usr/bin/env python3
"""Export reproducible strategy/card/demo audit rows from the live SQLite databases."""
import argparse
import csv
import json
import sqlite3
from collections import defaultdict
from pathlib import Path


FAMILIES = {'trendline', 'pump', 'bollinger', 'breakout', 'continuation'}


def rows(db: sqlite3.Connection, demo: sqlite3.Connection, versions):
    q = """SELECT * FROM signals
           WHERE kind = 'card' AND strategy IN (?,?,?,?,?) AND card_r IS NOT NULL
           AND (? IS NULL OR logic_version = ?)
           ORDER BY ts_ms"""
    args = [*sorted(FAMILIES), versions, versions]
    for row in db.execute(q, args):
        d = dict(row)
        card_id = d.get('card_id')
        trades = demo.execute(
            "SELECT * FROM demo_trades WHERE card_id = ? ORDER BY opened_ms DESC", (card_id,)
        ).fetchall() if card_id else []
        trade = dict(trades[0]) if trades else {}
        direction = d.get('direction') or 0
        yield {
            'signal_id': d.get('id'), 'card_id': card_id, 'ts_ms': d.get('ts_ms'),
            'symbol': d.get('symbol'), 'strategy': d.get('strategy'),
            'setup': d.get('group_key'), 'direction': direction,
            'logic_version': d.get('logic_version'), 'regime': d.get('regime2') or d.get('regime'),
            'vol_regime': d.get('vol_regime'), 'data_quality_ok': d.get('data_quality_ok'),
            'rvol_1m': d.get('rvol_1m'), 'atr_ratio': d.get('atr_ratio'),
            'adx': d.get('adx'), 'range_pos': d.get('range_pos'),
            'daily_bias': d.get('daily_bias'), 'weekly_bias': d.get('weekly_bias'),
            'btc_bias': d.get('btc_bias'), 'conf_n': d.get('conf_n'),
            'flow_pct_5m': d.get('flow_pct_5m'), 'spot_flow_pct_5m': d.get('spot_flow_pct_5m'),
            'oi_chg_15m': d.get('oi_chg_15m'), 'oi_chg_60m': d.get('oi_chg_60m'),
            'card_r': d.get('card_r'), 'mfe_r': d.get('mfe_r'), 'mae_r': d.get('mae_r'),
            'cluster_id': f"{int(d['ts_ms']) // (4 * 3_600_000)}:{direction}" if d.get('ts_ms') else None,
            'demo_id': trade.get('id'), 'demo_r': trade.get('r'),
            'demo_close_reason': trade.get('close_reason'), 'demo_error': trade.get('error'),
            'entry_plan': trade.get('entry_plan'), 'entry_fill': trade.get('entry_fill'),
            'slip_bps': trade.get('slip_bps'), 'latency_ms': trade.get('latency_ms'),
            'units': trade.get('n_units'),
        }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--signals', required=True)
    p.add_argument('--demo', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--logic-version')
    args = p.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.signals) as s, sqlite3.connect(args.demo) as d:
        s.row_factory = sqlite3.Row
        d.row_factory = sqlite3.Row
        data = list(rows(s, d, args.logic_version))
    fields = list(data[0]) if data else []
    with out.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(data)
    summary = defaultdict(lambda: {'n': 0, 'card_r': 0.0, 'demo_r': 0.0, 'clusters': set(), 'wins': 0})
    for r in data:
        x = summary[(r['strategy'], r['setup'], r['direction'])]
        x['n'] += 1; x['card_r'] += r['card_r'] or 0; x['demo_r'] += r['demo_r'] or 0
        x['clusters'].add(r['cluster_id']); x['wins'] += int((r['card_r'] or 0) > 0)
    report = []
    for key, x in sorted(summary.items()):
        report.append({'strategy': key[0], 'setup': key[1], 'direction': key[2], 'n': x['n'],
                       'card_sum_r': x['card_r'], 'card_mean_r': x['card_r'] / x['n'],
                       'demo_sum_r': x['demo_r'], 'clusters': len(x['clusters']), 'wins': x['wins']})
    out.with_suffix('.summary.json').write_text(json.dumps({'logic_version': args.logic_version,
                                                              'rows': len(data), 'groups': report}, indent=2))
    print(json.dumps({'rows': len(data), 'groups': len(report), 'out': str(out)}, indent=2))


if __name__ == '__main__':
    main()
