"""Static audit of playbook contract ownership.

This is an evidence report, not a trading test.  It deliberately reports
legacy geometry fallbacks instead of hiding them behind a green registry
check.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from strategies import SETUPS, _OBJ
from strategies.base import Strategy

REQUIRED_PLAN_FIELDS = {
    'entry', 'direction', 'anchor', 'tf', 'trigger', 'invalid', 'stop_ref',
    'targets', 'target_src', 'contract_id',
}


def audit() -> dict:
    playbooks = []
    for setup, (name, direction) in sorted(SETUPS.items()):
        owner = _OBJ[setup]
        playbooks.append({
            'setup': setup,
            'strategy': name,
            'direction': direction,
            'module': owner.__class__.__module__,
            'entry_levels_owner': owner.__class__.entry_levels is not Strategy.entry_levels,
            'legacy_geometry_fallback': owner.__class__.entry_levels is Strategy.entry_levels,
            'contract_fields': sorted(REQUIRED_PLAN_FIELDS),
        })
    return {
        'registered_playbooks': len(playbooks),
        'independent_entry_contracts': sum(p['entry_levels_owner'] for p in playbooks),
        'legacy_geometry_fallbacks': sum(p['legacy_geometry_fallback'] for p in playbooks),
        'playbooks': playbooks,
    }


if __name__ == '__main__':
    print(json.dumps(audit(), indent=2, sort_keys=True))
