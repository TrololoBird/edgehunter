#!/usr/bin/env python3
"""Bound operational journal tables without making accidental destructive changes.

Default mode is read-only.  Applying retention requires both ``--apply`` and
``--backup``; the backup is created with SQLite's online backup API before the
first delete.  Deletes are batched so the writer never holds one long table
lock.
"""
from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path

TABLES = ('universe', 'liq_levels', 'liquidations')


def _cutoff(days: int) -> int:
    return int((time.time() - days * 86_400) * 1000)


def _counts(conn: sqlite3.Connection, cutoff: int) -> dict[str, int]:
    return {
        table: int(conn.execute(f'SELECT COUNT(*) FROM {table} WHERE ts_ms < ?', (cutoff,)).fetchone()[0])
        for table in TABLES
    }


def _backup(src: sqlite3.Connection, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f'backup already exists: {path}')
    dst = sqlite3.connect(path)
    try:
        src.backup(dst)
    finally:
        dst.close()


def _delete(conn: sqlite3.Connection, table: str, cutoff: int, batch: int) -> int:
    total = 0
    while True:
        with conn:
            cur = conn.execute(
                f'DELETE FROM {table} WHERE rowid IN '
                f'(SELECT rowid FROM {table} WHERE ts_ms < ? LIMIT ?)',
                (cutoff, batch),
            )
            removed = cur.rowcount
        if removed <= 0:
            return total
        total += removed


def main() -> int:
    ap = argparse.ArgumentParser(description='Dry-run/apply retention for operational EdgeHunter tables')
    ap.add_argument('--db', default='signals.db')
    ap.add_argument('--days', type=int, default=90)
    ap.add_argument('--batch', type=int, default=10_000)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--backup', type=Path)
    args = ap.parse_args()
    if args.days < 1 or args.batch < 1:
        ap.error('--days and --batch must be positive')
    if args.apply and args.backup is None:
        ap.error('--backup is required with --apply')
    if not args.apply and args.backup is not None:
        ap.error('--backup is only valid with --apply')

    db = Path(args.db)
    cutoff = _cutoff(args.days)
    conn = sqlite3.connect(f'file:{db.resolve()}?mode=ro', uri=True) if not args.apply else sqlite3.connect(db)
    try:
        counts = _counts(conn, cutoff)
        print(f'cutoff_ms={cutoff}')
        for table, n in counts.items():
            print(f'{table}: {n}')
        if not args.apply:
            return 0
        _backup(conn, args.backup)
        # Reopen after backup so the backup connection is never used for deletes.
    finally:
        conn.close()

    conn = sqlite3.connect(db, timeout=30.0)
    try:
        conn.execute('PRAGMA busy_timeout=30000')
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        for table in TABLES:
            print(f'{table}: deleted {_delete(conn, table, cutoff, args.batch)}')
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
