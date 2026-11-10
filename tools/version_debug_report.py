#!/usr/bin/env python3
"""Compare logic versions and trace anomalies into later setups and outcomes.

This report deliberately keeps old versions in the comparison. ``stats.py`` uses
the active version by default for clean evaluation; this tool answers a different
question: what changed from the month of ``eng-169l`` to ``eng-169m`` and what
did each anomaly lead to afterwards?

Usage::

    python tools/version_debug_report.py --db signals.db --demo-db demo_trades.db
"""
import argparse
import collections
import sqlite3
import statistics
from typing import Dict, Iterable, List, Optional


def _f(values: Iterable[Optional[float]]) -> Optional[float]:
    xs = [float(x) for x in values if x is not None]
    return statistics.fmean(xs) if xs else None


def _fmt(x: Optional[float], suffix: str = "") -> str:
    return "—" if x is None else f"{x:+.3f}{suffix}"


def _table(conn: sqlite3.Connection, version: str) -> None:
    rows = conn.execute(
        "SELECT group_key, direction, ret_4h, card_r, post_stop_mfe_r, market_crowd, regime "
        "FROM signals WHERE logic_version = ? AND kind = 'entry' ORDER BY group_key", (version,)
    ).fetchall()
    groups: Dict[str, List[tuple]] = collections.defaultdict(list)
    for row in rows:
        groups[row[0]].append(row)
    print(f"\n[{version}] entries={len(rows)}")
    print("setup\tn\tpassed 4h\tavg directional 4h\tavg card R\tavg post-stop MFE\tcrowded")
    for setup, members in sorted(groups.items()):
        directed = [r[2] * r[1] for r in members if r[2] is not None and r[1] in (-1, 1)]
        cards = [r[3] for r in members if r[3] is not None]
        post = [r[4] for r in members if r[4] is not None]
        crowded = sum(1 for r in members if r[5])
        print(f"{setup}\t{len(members)}\t{len(directed)}\t{_fmt(_f(directed))}\t{_fmt(_f(cards), 'R')}\t"
              f"{_fmt(_f(post), 'R')}\t{crowded}")


def _anomaly_chain(conn: sqlite3.Connection, version: str) -> None:
    anomalies = conn.execute(
        "SELECT id, ts_ms, symbol, group_key, direction, ret_4h FROM signals "
        "WHERE logic_version = ? AND kind = 'anomaly' AND direction IN (-1,1) ORDER BY ts_ms", (version,)
    ).fetchall()
    setups = conn.execute(
        "SELECT ts_ms, symbol, group_key, direction, ret_4h, card_r FROM signals "
        "WHERE logic_version = ? AND kind = 'setup' AND direction IN (-1,1) ORDER BY ts_ms", (version,)
    ).fetchall()
    by_symbol: Dict[str, List[tuple]] = collections.defaultdict(list)
    for row in setups:
        by_symbol[row[1]].append(row)
    chains, downstream = [], []
    for anomaly in anomalies:
        candidates = [s for s in by_symbol.get(anomaly[2], []) if 0 <= s[0] - anomaly[1] <= 30 * 60_000]
        if not candidates:
            continue
        chosen = candidates[0]
        chains.append((anomaly, chosen))
        if chosen[4] is not None:
            downstream.append(chosen[4] * chosen[3])
    print(f"\n[{version}] anomaly-to-setup chains={len(chains)} / directional anomalies={len(anomalies)}")
    print(f"downstream setup directional 4h return: {_fmt(_f(downstream))}")
    by_pair = collections.Counter((a[3], s[2]) for a, s in chains)
    for (anomaly, setup), n in by_pair.most_common(20):
        print(f"  {anomaly} -> {setup}: {n}")


def _demo(conn: sqlite3.Connection, version: str) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(demo_trades)")}
    if 'logic_version' not in cols:
        print("\nDemo database has no logic_version column")
        return
    rows = conn.execute("SELECT strategy, r, close_reason FROM demo_trades WHERE logic_version = ?", (version,)).fetchall()
    done = [r for r in rows if r[1] is not None]
    print(f"\n[{version}] demo rows={len(rows)} closed with R={len(done)} avg R={_fmt(_f(r[1] for r in done), 'R')}")
    by_strategy: Dict[str, List[tuple]] = collections.defaultdict(list)
    for row in done:
        by_strategy[row[0] or '?'].append(row)
    for strategy, members in sorted(by_strategy.items()):
        print(f"  {strategy}: n={len(members)} avg R={_fmt(_f(r[1] for r in members), 'R')}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default='signals.db')
    ap.add_argument('--demo-db', default='demo_trades.db')
    ap.add_argument('--versions', nargs='+', default=['eng-169l', 'eng-169m'])
    args = ap.parse_args()
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    try:
        for version in args.versions:
            _table(conn, version)
            _anomaly_chain(conn, version)
    finally:
        conn.close()
    try:
        demo = sqlite3.connect(f"file:{args.demo_db}?mode=ro", uri=True)
    except sqlite3.Error:
        demo = None
    if demo is not None:
        try:
            for version in args.versions:
                _demo(demo, version)
        finally:
            demo.close()


if __name__ == '__main__':
    main()
