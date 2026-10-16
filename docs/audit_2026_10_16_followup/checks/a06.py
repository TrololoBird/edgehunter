"""A06 before / after: temporary SQLite, the exchange calls faked (no network). Run from the tree root."""
import asyncio, sqlite3, sys, tempfile, time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, '.')
from executor import DemoExecutor

def run(label, fills, orders, closed_ago_h=None):
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / 'demo.db')
        with patch('executor.credentials', return_value=('', '')):
            DemoExecutor(db)
            opened = int(time.time() * 1000) - 60_000 - int((closed_ago_h or 0) * 3_600_000)
            with sqlite3.connect(db) as c:
                rid = c.execute('INSERT INTO demo_trades (card_id,symbol,strategy,direction,opened_ms,entry_plan,entry_fill,'
                                'qty,sl,risk_usd) VALUES (?,?,?,?,?,?,?,?,?,?)',
                                ('card', 'X', 'breakout', 1, opened, 100., 100., 1., 90., 10.)).lastrowid
            ex = DemoExecutor(db)
        t = ex.open['card']
        async def fake(method, *a, **k):
            if method == 'fetch_my_trades':
                return [dict(f, timestamp=opened + f['dt']) for f in fills]
            if method == 'fetch_order':
                if a[0] not in orders:
                    raise RuntimeError('order not found')
                # a finished order as BingX reports it (status, executedQty, avgPrice, commission): since the review of
                # 6b771ba the exit price and fees come from the order, so the fixture states them
                f = [x for x in fills if x.get('order') == a[0]]
                avg = sum(x['price'] * x['amount'] for x in f) / sum(x['amount'] for x in f)
                return {'id': a[0], 'status': 'closed', 'filled': orders[a[0]], 'average': avg,
                        'fee': {'currency': 'USDT', 'cost': .0005 * avg * orders[a[0]]}}
            raise AssertionError(method)
        ex._call = fake
        if closed_ago_h is None:
            asyncio.run(ex._finalize(t, 'SL', None))
        else:      # a FILL_PENDING row closed closed_ago_h ago, recovered by _refinalize
            with sqlite3.connect(db) as c:
                c.execute('UPDATE demo_trades SET closed_ms=?, close_reason=?, error=? WHERE id=?',
                          (opened + 60_000, 'SL', ex.FILL_PENDING, rid))
            asyncio.run(ex._refinalize())
        with sqlite3.connect(db) as c:
            row = c.execute('SELECT exit_avg, round(pnl_usd, 3), error FROM demo_trades WHERE id=?', (rid,)).fetchone()
        print(f"{label:58s} exit, pnl, error = {row}")

entry = {'side': 'buy', 'price': 100., 'amount': 100., 'dt': -1000, 'order': 'E'}
tp1 = {'side': 'sell', 'price': 110., 'amount': 50., 'dt': 1000, 'order': 'T1'}       # ccxt amount in another unit (x100)
sl = {'side': 'sell', 'price': 90., 'amount': 50., 'dt': 2000, 'order': 'S'}
run('audit case: only TP1 listed, no entry fill', [dict(tp1, amount=.5)], {'T1': .5})
run('entry fill outside the window, only TP1 listed', [dict(entry, dt=-300_000), tp1], {'T1': .5})
run('TP1 + stop listed, fills 100x the position', [entry, tp1, sl], {'T1': .5, 'S': .5})
run('one market close, fills 100x', [entry, dict(sl, amount=100.)], {'S': 1.})
run('exit fill without an order id', [dict(tp1, order=None), dict(sl, order=None)], {})
run('exit order unreadable', [tp1, sl], {'T1': .5})
run('_refinalize after 7h, only TP1 listed', [tp1], {'T1': .5}, closed_ago_h=7)
run('_refinalize after 7h, TP1 + stop', [tp1, sl], {'T1': .5, 'S': .5}, closed_ago_h=7)
