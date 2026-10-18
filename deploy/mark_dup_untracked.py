"""eng-132 one-off: UNTRACKED rows 110-112 (2026-10-15 10:04) re-booked the same positions as the EXCHANGE rows 55-57
(identical USD result): mark them so the summaries do not count the $49 twice. Idempotent; run once at the restart."""
import sqlite3
import sys

path = sys.argv[1] if len(sys.argv) > 1 else '/opt/edgehunter/demo_trades.db'
with sqlite3.connect(path) as c:
    for dup, orig in ((110, 55), (111, 56), (112, 57)):
        c.execute("UPDATE demo_trades SET error = ? WHERE id = ? AND setup = 'UNTRACKED' AND pnl_usd = "
                  "(SELECT pnl_usd FROM demo_trades WHERE id = ?)", (f"duplicate of id {orig} (eng-132)", dup, orig))
    print(c.execute("SELECT id, error FROM demo_trades WHERE id IN (110, 111, 112)").fetchall())
