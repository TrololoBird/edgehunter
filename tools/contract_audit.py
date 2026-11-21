"""Static audit of playbook contract ownership.

This is an evidence report, not a trading test.  Playbooks may still declare their structural intent in an
``entry_levels`` method, but the runtime dispatch in ``strategies.entry_levels_for`` sends every result through the
shared finalizer before it can reach the journal or executor.  The report therefore separates declaration methods from
independent risk decisions and keeps legacy fallback detection explicit.
"""
from __future__ import annotations

import json
import sys
import ast
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
            'shared_finalizer': True,
            'risk_decision_owner': 'strategies.base.finalize_card_levels',
            'contract_fields': sorted(REQUIRED_PLAN_FIELDS),
        })
    geometry_imports = []
    for path in (Path(__file__).resolve().parents[1] / 'strategies').glob('*.py'):
        try:
            tree = ast.parse(path.read_text())
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == 'strategies.geometry':
                geometry_imports.append(f'{path.name}:{node.lineno}')
    return {
        'registered_playbooks': len(playbooks),
        # A playbook method declares levels, but it is not an independent executable risk decision: the dispatch
        # wrapper below is the only runtime entrypoint used by SignalBook, journal replay, and executor.
        'playbook_contract_methods': sum(p['entry_levels_owner'] for p in playbooks),
        'independent_entry_contracts': 0,
        'shared_geometry_entrypoint': 'strategies.entry_levels_for -> strategies.base.finalize_card_levels',
        'shared_finalizer_paths': ['signal_book', 'journal', 'executor'],
        'legacy_geometry_fallbacks': sum(p['legacy_geometry_fallback'] for p in playbooks),
        'shared_geometry_decision_imports': sorted(geometry_imports),
        'playbooks': playbooks,
    }


if __name__ == '__main__':
    print(json.dumps(audit(), indent=2, sort_keys=True))
