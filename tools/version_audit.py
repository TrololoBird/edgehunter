"""Read-only audit for logic-version partitioning in a signals journal."""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.versioning import version_key


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='signals.db')
    args = parser.parse_args()
    conn = sqlite3.connect(args.db)
    rows = conn.execute(
        "SELECT COALESCE(logic_version, '<legacy>'), COUNT(*) FROM signals "
        "GROUP BY logic_version ORDER BY logic_version"
    ).fetchall()
    print('logic_version count family')
    for value, count in rows:
        print(f'{value} {count} {version_key(value)[0]}')


if __name__ == '__main__':
    main()
