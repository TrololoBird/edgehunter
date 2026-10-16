"""Offline audit examples. Run from repo root: python docs/audit_2026_10_16/reproduce.py.

No bot, exchange account, network call, or production database is used.
Assertions describe observed defects, not desired behavior.
"""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import signal_book as sb
from levels import resample
from replay import Replay
from scanner import Scanner
from strategies.maniac import parabolic_sar_step


def run():
    # A01: true TPO counts peak in the lower rows, not the last row.
    from strategies.classic import value_area
    profile = [[i * 1_800_000, lo, hi, lo, hi, 1.] for i, (lo, hi) in
               enumerate([(100., 110.), (109., 110.), (100., 104.), (100., 104.)])]
    va = value_area(profile, buckets=10, tpo=True)
    assert va == (102., 109.5, 110.)
    print('A01 TPO POC at wrong peak:', va)

    # A05/A06: temporary SQLite only, executor enabled flag off, exchange call replaced.
    import asyncio
    import sqlite3
    import tempfile
    import time
    from executor import DemoExecutor
    with tempfile.TemporaryDirectory(prefix='pump-audit-') as td:
        db = str(Path(td) / 'demo.db')
        with patch('executor.credentials', return_value=('', '')):
            DemoExecutor(db)
            opened = int(time.time() * 1000) - 60_000
            with sqlite3.connect(db) as conn:
                cur = conn.execute('INSERT INTO demo_trades '
                                   '(card_id,symbol,strategy,direction,opened_ms,entry_plan,entry_fill,qty,sl,risk_usd) '
                                   'VALUES (?,?,?,?,?,?,?,?,?,?)',
                                   ('card', 'X', 'breakout', 1, opened, .0001, 100., 1., 90., 10.))
                row_id = cur.lastrowid
            executor = DemoExecutor(db)
        restored = executor.open['card']
        assert 'entry_plan' not in restored and 'scale' not in restored
        print('A05 stored entry_plan absent after restart:', sorted(restored))

        async def fake_call(*args, **kwargs):
            return [{'side': 'sell', 'timestamp': opened + 1000, 'price': 110., 'amount': .5}]

        executor._call = fake_call
        asyncio.run(executor._finalize(restored, 'SL', None))
        with sqlite3.connect(db) as conn:
            row = conn.execute('SELECT exit_avg,pnl_usd,error FROM demo_trades WHERE id=?', (row_id,)).fetchone()
        assert row[0] == 110. and row[1] > 9. and row[2] is None
        print('A06 half exit accepted as complete (exit,pnl,error):', row)

    # A03: previous low=90 is not available to this API; next SAR crosses it.
    nxt, *_ = parabolic_sar_step(89., 120., .2, 1, 120., 100.)
    assert nxt > 90
    print('A03 SAR:', nxt, '(two-bar clamp would be 90)')

    # A04: only the last minute of a 4h bucket exists.
    one = [[239 * 60_000, 100., 101., 99., 100., 1., .5]]
    bars = resample(one, 240, 240 * 60_000)
    assert len(bars) == 1
    print('A04 one minute accepted as a full 4h bar:', bars)

    # A10: realized R changes with a later scan quote, despite an identical stop fill.
    s = sb.TrackedSignal('X', 'BREAKOUT UP', 1, 'breakout', 1000., 100., {},
                         entered_at=1000., last_seen=2000., last_price=105.,
                         levels={'entry': 100., 'sl': 95., 'risk0': 10.,
                                 'tp1': float('inf'), 'tp2': float('inf'), 'tp3': float('inf')},
                         plan={'no_tp': True}, units=[[100., 1000.]], exit_fill=90., finished_at=2000.)
    before = sb.SignalBook._exit_r(s, 'SL')
    s.last_price = 90.
    after = sb.SignalBook._exit_r(s, 'SL')
    assert before > 0 and after < 0
    print('A10 same stop fill=90, scan=105 / scan=90:', before, after)

    # A08: a minute's wick crosses the channel, while scan price has already recovered.
    b = sb.SignalBook()
    b.daily_of = lambda sym: [[(-10 + i) * 86_400_000, 100., 110., 95., 100., 1.] for i in range(10)]
    s = sb.TrackedSignal('X', 'BREAKOUT UP', 1, 'breakout', 0., 100., {},
                         plan={'trail_days': 10, 'no_tp': True},
                         levels={'entry': 100., 'sl': 80., 'risk0': 20.,
                                 'tp1': 10_000., 'tp2': 20_000., 'tp3': 30_000.},
                         entered_at=1., managed_ms=60_000, last_price=100., units=[[100., 1.]], status='ENTRY')
    b._manage_trade(s, 100., 180., lambda sym: [[60_000, 100., 102., 94., 100., 1., .5]])
    assert s.status == 'ENTRY' and not s.finished
    print('A08 channel95 crossed at94, trade stays:', s.status)

    # A13: two independently valid candidates in one scan bypass the shared-side gate.
    b = sb.SignalBook()
    b._card_gate = lambda *a: None
    b._advance = lambda *a: None
    st = SimpleNamespace(name='fake', enabled=True, context_veto=lambda *a: None,
                         has_data=lambda *a: True)
    with patch.object(sb, 'classify', lambda sig: ('setup', sig['g'], 1)), \
            patch.object(sb, 'strategy_of', lambda g: st), \
            patch.object(sb, 'veto_reason', lambda *a: None):
        created, _ = b.update([('X', {'g': 'A'}), ('X', {'g': 'B'})], {},
                              lambda s: 100., lambda s: [], 1000.)
    assert len(created) == 2
    print('A13 same coin/direction, same scan: created', len(created))

    # A11: current live and replay band functions receive equivalent price history.
    h1 = [[i * 3_600_000, 100 + i, 101 + i, 99 + i, 100 + i, 1.] for i in range(120)]
    m15 = [[i * 900_000, 100 + i / 4, 101 + i / 4, 99 + i / 4, 100 + i / 4, 1.]
           for i in range(480)]
    live = SimpleNamespace(market_data={'X': SimpleNamespace(h1=h1)})
    replay = SimpleNamespace(coins={'X': SimpleNamespace(m15=lambda t: m15)}, now_ms=120 * 3_600_000)
    a, b = Scanner._opposite_band(live, 'X', 1), Replay._band(replay, 'X', 1)
    assert abs(a - b) > 1
    print('A11 live 4h / replay 15m opposite band:', a, b)

    # A12: a later 4h bar moves the stop while the third minute is still being managed.
    minutes = [[i * 60_000, 100., 101., 99., 100., 1., .5] if i < 240 else
               [i * 60_000, 120., 121., 119., 120., 1., .5] for i in range(480)]
    s = sb.TrackedSignal('X', 'BB1 UP', 1, 'continuation', 0., 100., {},
                         levels={'entry': 100., 'sl': 90., 'risk0': 10.,
                                 'tp1': float('inf'), 'tp2': float('inf'), 'tp3': float('inf')},
                         plan={'sar': {'sar': 90., 'ep': 150., 'af': .2, 'tf_min': 240,
                                       'last_ts': -14_400_000}, 'no_tp': True},
                         status='ENTRY', entered_at=1., managed_ms=60_000, last_price=120.)
    sb.SignalBook()._manage_trade(s, 120., 480 * 60., lambda sym: minutes)
    assert s.finished and s.managed_ms == 180_000 and s.levels['sl'] > 109
    print('A12 false stop in minute3 using later 4h bar:', s.levels['sl'], s.exit_fill)

    # A16: using quote notional as MFI volume adds a second price weighting.
    import numpy as np
    from strategies.ind_panel import indicators
    price = np.array([100., 200.] * 150)
    volume = np.full(len(price), 10.)
    k = np.column_stack([np.arange(len(price)) * 60_000, price, price, price, price, price * volume])
    quote_mfi = indicators(k)['mfi'][-1]
    k[:, 5] = volume
    base_mfi = indicators(k)['mfi'][-1]
    assert abs(quote_mfi - 80.) < 1e-10 and abs(base_mfi - 200 / 3) < 1e-10
    print('A16 MFI quote/base volume:', quote_mfi, base_mfi)

    # A18: no exhaustion close ever occurs, yet the dump detector emits a bounce entry.
    from strategies.pump import dump_bounce
    hourly = [[i * 3_600_000, 100., 101., 99., 100., 1.] for i in range(190)]
    hourly[175] = [175 * 3_600_000, 100., 100., 59., 60., 100.]
    for i in range(176, 189):
        hourly[i] = [i * 3_600_000, 65., 75., 60., 65., 1.]
    hourly[189] = [189 * 3_600_000, 65., 65., 49., 50., 1.]
    exhaustion = [i for i in range(176, 190) if hourly[i][4] > hourly[i - 1][2]]
    found = dump_bounce(hourly, 190 * 3_600_000)
    assert not exhaustion and found is not None and found['dump_low'] == 49.
    print('A18 no exhaustion, emitted:', found['setup'], 'dump_low:', found['dump_low'])


if __name__ == '__main__':
    run()
