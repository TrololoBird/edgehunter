"""Read-only evidence coverage report for the registered playbooks."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategies import SETUPS, _OBJ  # noqa: E402
from strategies.base import Strategy  # noqa: E402

REFERENCE_DOC = {
    'pump_start': 'AUDIT_STRATEGIES_01_PUMP.md', 'dump_start': 'AUDIT_STRATEGIES_01_PUMP.md',
    'pump_top': 'AUDIT_STRATEGIES_01_PUMP.md', 'dump_bounce': 'AUDIT_STRATEGIES_01_PUMP.md',
    'trendline_break': 'AUDIT_STRATEGIES_02_TRENDLINE.md', 'trendline_touch': 'AUDIT_STRATEGIES_02_TRENDLINE.md',
    'supply_demand': 'AUDIT_STRATEGIES_03_SUPPLY_DEMAND.md',
    'bollinger_wm': 'AUDIT_STRATEGIES_04_BOLLINGER.md', 'bollinger_method3': 'AUDIT_STRATEGIES_04_BOLLINGER.md',
    'bollinger_method1': 'AUDIT_STRATEGIES_04_BOLLINGER.md', 'sweep': 'AUDIT_STRATEGIES_05_SWEEP.md',
    'silver_bullet': 'AUDIT_STRATEGIES_05_SWEEP.md', 'po3': 'AUDIT_STRATEGIES_06_PO3.md',
    'oi_build': 'AUDIT_STRATEGIES_07_OI_BUILD.md', 'breakout': 'AUDIT_STRATEGIES_08_BREAKOUT_CONTINUATION.md',
    'continuation': 'AUDIT_STRATEGIES_08_BREAKOUT_CONTINUATION.md', 'value_area': 'AUDIT_STRATEGIES_09_MARKET_PROFILE_AUCTION.md',
    'auction': 'AUDIT_STRATEGIES_09_MARKET_PROFILE_AUCTION.md', 'orb': 'AUDIT_STRATEGIES_10_ORB.md',
    'connors': 'AUDIT_STRATEGIES_11_CONNORS.md', 'cup_handle': 'AUDIT_STRATEGIES_12_CUP_HANDLE.md',
    'cascade': 'AUDIT_STRATEGIES_13_CASCADE.md', 'wyckoff': 'AUDIT_STRATEGIES_01_PUMP.md',
}


def audit() -> dict:
    docs = list(ROOT.glob('AUDIT_STRATEGIES_*.md'))
    rows = []
    for setup, (strategy, direction) in sorted(SETUPS.items()):
        owner = _OBJ[setup]
        rows.append({
            'setup': setup,
            'strategy': strategy,
            'direction': direction,
            'contract_owner': owner.__class__.entry_levels is not Strategy.entry_levels,
            'reference_docs': ([REFERENCE_DOC[strategy]] if REFERENCE_DOC.get(strategy) else
                               [str(p.relative_to(ROOT)) for p in docs
                                if strategy.replace('_', ' ').lower() in p.read_text(errors='ignore').lower()]),
        })
    return {
        'playbooks': len(rows),
        'contract_owners': sum(r['contract_owner'] for r in rows),
        'with_reference_document': sum(bool(r['reference_docs']) for r in rows),
        'missing_reference_document': [r['setup'] for r in rows if not r['reference_docs']],
        'rows': rows,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    result = audit()
    print(json.dumps(result, indent=2) if args.json else
          f"playbooks={result['playbooks']} owners={result['contract_owners']} "
          f"with_reference_document={result['with_reference_document']} "
          f"missing={len(result['missing_reference_document'])}")
