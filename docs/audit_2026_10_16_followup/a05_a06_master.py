"""Master check of A05/A06 (temp sqlite, exchange call faked). Run with cwd = tree root."""
import asyncio, sqlite3, sys, tempfile, time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, '.')
from executor import DemoExecutor

def case(fills, label, scale=.001):
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / 'demo.db')
        with patch('executor.credentials', return_value=('', '')):
            DemoExecutor(db)
            opened = int(time.time() * 1000) - 60_000
            with sqlite3.connect(db) as c:
                cols = [r[1] for r in c.execute('PRAGMA table_info(demo_trades)')]
                has = 'scale' in cols
                rid = c.execute('INSERT INTO demo_trades (card_id,symbol,strategy,direction,opened_ms,entry_plan,entry_fill,qty,sl,risk_usd'
                                + (',scale' if has else '') + ') VALUES (?,?,?,?,?,?,?,?,?,?' + (',?' if has else '') + ')',
                                ('card', 'X', 'breakout', 1, opened, .0001, 100., 1., 90., 10.) + ((scale,) if has else ())).lastrowid
            ex = DemoExecutor(db)
        t = ex.open['card']
        print(label, 'scale column:', has, 'restored scale:', t.get('scale'))
        async def fake(*a, **k):
            return [dict(f, timestamp=opened + f.pop('dt')) for f in [dict(x) for x in fills]]
        ex._call = fake
        asyncio.run(ex._finalize(t, 'SL', None))
        with sqlite3.connect(db) as c:
            print('   exit_avg,pnl,error,close_reason:', c.execute('SELECT exit_avg,pnl_usd,error,close_reason FROM demo_trades WHERE id=?', (rid,)).fetchone())

case([{'side': 'sell', 'price': 110., 'amount': .5, 'dt': 1000}], 'A06 audit case (no entry fill listed):')
case([{'side': 'buy', 'price': 100., 'amount': 1., 'dt': -1000}, {'side': 'sell', 'price': 110., 'amount': .5, 'dt': 1000}], 'A06 entry 1 / exit .5:')
case([{'side': 'buy', 'price': 100., 'amount': 1., 'dt': -1000}, {'side': 'sell', 'price': 110., 'amount': .5, 'dt': 1000},
      {'side': 'sell', 'price': 90., 'amount': .5, 'dt': 2000}], 'A06 entry 1 / exits .5+.5:')
case([{'side': 'buy', 'price': 100., 'amount': 1., 'dt': -300_000}, {'side': 'sell', 'price': 110., 'amount': .5, 'dt': 1000}],
     'A06 entry filled 5 min before opened_ms:')
