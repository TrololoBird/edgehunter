#!/usr/bin/env python
"""Read-only reconciliation report for demo ledger and persisted scanner cards."""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from pathlib import Path


def finite(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def audit(db_path: str, state_path: str) -> dict:
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        open_rows = db.execute("SELECT * FROM demo_trades WHERE closed_ms IS NULL ORDER BY opened_ms").fetchall()
        intents = {tuple(r) for r in db.execute(
            "SELECT card_id, execution_phase FROM execution_intents").fetchall()}
    state = json.loads(Path(state_path).read_text(encoding='utf-8'))
    cards = state.get('book', {}).get('cards', [])
    card_keys = {(str(c.get('symbol')), str(c.get('group_key'))) for c in cards
                 if c.get('finished_at') is None and c.get('status') not in ('EXPIRED', 'INVALID', 'CLOSED')}
    violations = []
    protected = 0
    for row in open_rows:
        direction = int(row['direction'] or 0)
        entry, stop = finite(row['entry_fill'] or row['entry_plan']), finite(row['sl'])
        no_stop = bool(row['no_stop'])
        if no_stop and str(row['strategy'] or '').lower() != 'connors':
            violations.append({'id': row['id'], 'kind': 'unexpected_no_stop'})
        elif not no_stop and entry is not None and stop is not None and direction in (-1, 1) \
                and direction * (entry - stop) > 0:
            protected += 1
        else:
            violations.append({'id': row['id'], 'kind': 'invalid_or_unprotected_geometry'})
        if (str(row['symbol']), str(row['setup'])) not in card_keys:
            # A card may finish after the row is opened; report it separately
            # so the operator can distinguish a normal orphan reconciliation.
            violations.append({'id': row['id'], 'kind': 'card_not_in_persisted_state'})
        if (row['card_id'], 'ENTRY') not in intents:
            violations.append({'id': row['id'], 'kind': 'missing_entry_intent'})
    return {
        'open_rows': len(open_rows),
        'protected_rows': protected,
        'card_keys': len(card_keys),
        'execution_intents': len(intents),
        'violations': violations,
        'status': 'ok' if not violations else 'attention_required',
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='demo_trades.db')
    parser.add_argument('--state', default='scanner_state.json')
    args = parser.parse_args()
    print(json.dumps(audit(args.db, args.state), sort_keys=True))


if __name__ == '__main__':
    main()
