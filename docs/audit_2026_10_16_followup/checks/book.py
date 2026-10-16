"""A03 / A08 / A10 / A12 / A13 / A15 / S10 before / after. Run: python checks/book.py <repo root>.
Offline: temporary SQLite only, no network, no exchange."""
import asyncio
import os
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
import signal_book as sb
from strategies.maniac import parabolic_sar_step


def run(name, fn):
    try:
        print(name, fn())
    except Exception as e:
        print(name, 'ERROR', type(e).__name__, e)


def a03():
    try:
        nxt = parabolic_sar_step(89., 120., .2, 1, 120., 100., prev_lo=90.)[0]
    except TypeError:
        nxt = parabolic_sar_step(89., 120., .2, 1, 120., 100.)[0]
    return f'next SAR {nxt:.4g} (TA-Lib two-bar clamp: 90)'


def a08():
    b = sb.SignalBook()
    b.daily_of = lambda sym: [[(-10 + i) * 86_400_000, 100., 110., 95., 100., 1.] for i in range(10)]
    s = sb.TrackedSignal('X', 'BREAKOUT UP', 1, 'breakout', 0., 100., {}, plan={'trail_days': 10, 'no_tp': True},
                         levels={'entry': 100., 'sl': 80., 'risk0': 20., 'tp1': 1e4, 'tp2': 2e4, 'tp3': 3e4},
                         entered_at=1., managed_ms=60_000, last_price=100., units=[[100., 1.]], status='ENTRY')
    b._manage_trade(s, 100., 180., lambda sym: [[60_000, 100., 102., 94., 100., 1., .5, .01]])
    return f'channel 95, minute low 94, scan 100: status={s.status} exit_fill={s.exit_fill} final_r={s.final_r}'


def a10():
    s = sb.TrackedSignal('X', 'BREAKOUT UP', 1, 'breakout', 1000., 100., {}, entered_at=1000., last_seen=2000.,
                         last_price=105., levels={'entry': 100., 'sl': 95., 'risk0': 10., 'tp1': float('inf'),
                                                  'tp2': float('inf'), 'tp3': float('inf')},
                         plan={'no_tp': True}, units=[[100., 1000.]], exit_fill=90., finished_at=2000.)
    before = sb.SignalBook._exit_r(s, 'SL')
    s.last_price = 90.
    return f'stop fill 90, scan 105 -> {before:+.3f}R; scan 90 -> {sb.SignalBook._exit_r(s, "SL"):+.3f}R'


def a12():
    minutes = [[i * 60_000, 100., 101., 99., 100., 1., .5, .01] if i < 240 else
               [i * 60_000, 120., 121., 119., 120., 1., .5, .01] for i in range(480)]
    s = sb.TrackedSignal('X', 'BB1 UP', 1, 'continuation', 0., 100., {},
                         levels={'entry': 100., 'sl': 90., 'risk0': 10., 'tp1': float('inf'), 'tp2': float('inf'),
                                 'tp3': float('inf')},
                         plan={'sar': {'sar': 90., 'ep': 150., 'af': .2, 'tf_min': 240, 'last_ts': -14_400_000},
                               'no_tp': True},
                         status='ENTRY', entered_at=1., managed_ms=60_000, last_price=120.)
    sb.SignalBook()._manage_trade(s, 120., 480 * 60., lambda sym: minutes)
    return f'status={s.status} finished={s.finished} sl={s.levels["sl"]:.4g} managed_min={s.managed_ms // 60_000}'


def a13():
    b = sb.SignalBook()
    b._card_gate = lambda *a: None
    b._advance = lambda *a: None
    st = SimpleNamespace(name='fake', enabled=True, context_veto=lambda *a: None, has_data=lambda *a: True)
    with patch.object(sb, 'classify', lambda sig: ('setup', sig['g'], 1)), \
            patch.object(sb, 'strategy_of', lambda g: st), patch.object(sb, 'veto_reason', lambda *a: None):
        created, _ = b.update([('X', {'g': 'A'}), ('X', {'g': 'B'})], {}, lambda s: 100., lambda s: [], 1000.)
    return f'same coin / direction in one scan: cards created {len(created)}'


def s10():
    s = sb.TrackedSignal('X', 'BREAKOUT UP', 1, 'breakout', 0., 100., {}, plan={'no_tp': True, 'no_stop': True},
                         levels={'entry': 100., 'sl': 90., 'risk0': 10., 'tp1': 101., 'tp2': 102., 'tp3': 103.},
                         entered_at=1., managed_ms=60_000, last_price=100., status='ENTRY')
    sb.SignalBook()._manage_trade(s, 100., 180., lambda sym: [[60_000, 100., 110., 99., 100., 1., .5, .01]])
    return f'no_tp plan, placeholder tp3 103 traded: status={s.status} best_target={s.best_target}'


def a15():
    import webui
    with tempfile.TemporaryDirectory(prefix='pump-check-') as td:
        db = os.path.join(td, 'demo.db')
        with sqlite3.connect(db) as c:
            c.execute('CREATE TABLE demo_trades (id INTEGER PRIMARY KEY, opened_ms, closed_ms, symbol, strategy, setup, '
                      'direction, entry_fill, exit_avg, sl, tp1, r, pnl_usd, close_reason, card_id, error)')
            c.executemany('INSERT INTO demo_trades (opened_ms, closed_ms, symbol, strategy, r, close_reason) VALUES (?,?,?,?,?,?)',
                          [(i, i + 1, 'X', 's', 1.0, 'SL') for i in range(5000)] +
                          [(10_000, 10_001, 'X', 's', 5.0, 'UNTRACKED'), (10_002, 10_003, 'X', 's', -1.0, 'SL')])
        ui = SimpleNamespace(scanner=SimpleNamespace(demo=SimpleNamespace(db_path=db)),
                             _json=lambda d: d)
        out = asyncio.run(webui.WebUI._demo(ui, SimpleNamespace(query={})))
    tr = out['trades']
    return (f'rows {len(tr)}, newest closed_ms {tr[-1]["closed_ms"]}, UNTRACKED in API: '
            f'{any(t["reason"] == "UNTRACKED" for t in tr)}')


for name, fn in [('A03', a03), ('A08', a08), ('A10', a10), ('A12', a12), ('A13', a13), ('S10', s10), ('A15', a15)]:
    run(name, fn)
