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
    events = read('data/publication_events.jsonl')
    ids = set()
    intents, deliveries = set(), set()
    errors = []
    for row in briefings:
        pid = row.get('publication_id')
        if not pid or not row.get('schema_v') or not row.get('rules_v'):
            errors.append(('invalid_snapshot', row.get('symbol'), row.get('slot')))
        if pid in ids:
            errors.append(('duplicate_publication', pid))
        if pid:
            ids.add(pid)
    for row in events:
        pid = row.get('publication_id')
        if not pid:
            errors.append(('event_without_publication', row))
        elif row.get('status') == 'intent':
            intents.add(pid)
        elif row.get('status') == 'delivered':
            deliveries.add(pid)
            if pid not in intents:
                errors.append(('delivery_without_intent', pid))
    for pid in sorted(intents - deliveries):
        errors.append(('intent_without_delivery', pid))
    for pid in sorted(deliveries - ids):
        errors.append(('delivery_without_archive', pid))
    for row in outcomes:
        if row.get('publication_id') and row['publication_id'] not in ids:
            errors.append(('orphan_outcome', row['publication_id']))
    print(json.dumps({'briefings': len(briefings), 'outcome_snapshots': len(outcomes),
                      'events': len(events), 'intents': len(intents), 'deliveries': len(deliveries),
                      'publication_ids': len(ids), 'errors': errors}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
