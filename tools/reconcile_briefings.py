"""Fail-closed reconciliation for briefing publications and outcomes."""
import json
import os
import sys


def read(path):
    if not os.path.exists(path):
        return []
    return [json.loads(line) for line in open(path, encoding='utf-8') if line.strip()]


def main():
    briefings = read('data/briefings.jsonl')
    outcomes = read('data/briefing_outcomes.jsonl')
    ids = set()
    errors = []
    for row in briefings:
        pid = row.get('publication_id')
        if not pid or not row.get('schema_v') or not row.get('rules_v'):
            errors.append(('invalid_snapshot', row.get('symbol'), row.get('slot')))
        if pid in ids:
            errors.append(('duplicate_publication', pid))
        if pid:
            ids.add(pid)
    for row in outcomes:
        if row.get('publication_id') and row['publication_id'] not in ids:
            errors.append(('orphan_outcome', row['publication_id']))
    print(json.dumps({'briefings': len(briefings), 'outcome_snapshots': len(outcomes),
                      'publication_ids': len(ids), 'errors': errors}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
