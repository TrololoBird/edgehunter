"""One-time, reversible migration of pre-snapshot briefing records."""
import json
import os
import shutil
import time


def migrate(path='data/briefings.jsonl'):
    if not os.path.exists(path):
        return 0
    backup = f'{path}.pre_snapshot.{int(time.time())}.bak'
    shutil.copy2(path, backup)
    rows = []
    for idx, line in enumerate(open(path, encoding='utf-8')):
        if not line.strip():
            continue
        row = json.loads(line)
        if not row.get('publication_id'):
            row['publication_id'] = f"legacy|{row.get('slot', 'unknown')}|{row.get('symbol', 'unknown')}|{idx}"
        row.setdefault('schema_v', 1)
        row.setdefault('execution_model', 'legacy_model')
        row.setdefault('legacy', True)
        rows.append(row)
    tmp = f'{path}.tmp'
    with open(tmp, 'w', encoding='utf-8') as out:
        for row in rows:
            out.write(json.dumps(row, ensure_ascii=False, default=str) + '\n')
    os.replace(tmp, path)
    return len(rows), backup


if __name__ == '__main__':
    result = migrate()
    print(json.dumps({'migrated': result[0], 'backup': result[1]}, ensure_ascii=False))
