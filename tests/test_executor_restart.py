"""Restart recovery uses temporary SQLite/JSON state and never contacts an exchange."""
import asyncio
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import executor


@pytest.fixture
def factory(tmp_path, monkeypatch):
    monkeypatch.setattr(executor, 'credentials', lambda: ('', ''))
    path = str(tmp_path / 'demo.db')
    return lambda: executor.DemoExecutor(path)


def pending(ex):
    p = {'order_id': 'filled-1', 'symbol': 'AUDIT/USDT:USDT', 'qty': 10,
         'lv': {'entry': 100, 'sl': 98, 'tp1': 104, 'tp2': 106, 'tp3': 108},
         'scale': 1, 'basis': 0, 'setup': 'ORB UP', 'strategy': 'orb', 'direction': 1,
         'trail': True, 'no_tp': False}
    ex.pending = {'card': p}
    return p


def test_failed_close_intent_survives_restart(factory):
    ex = factory()
    p = pending(ex)
    trade = ex._limit_trade('card', p, 100.25, 10)
    ex._exchange = AsyncMock(side_effect=OSError('offline'))
    with pytest.raises(OSError, match='offline'):
        asyncio.run(ex._close(trade, 'LATE_FILL', -0.4))
    restored = factory().open['card']
    assert restored['close_pending'] == ['LATE_FILL', -0.4]
    assert restored['qty'] == 10 and restored['entry_fill'] == 100.25


def test_targets_and_execution_flags_survive_restart(factory):
    ex = factory()
    p = pending(ex)
    ex._limit_trade('card', p, 100, 10)
    restored = factory().open['card']
    assert [restored[f'tp{k}'] for k in (1, 2, 3)] == [104, 106, 108]
    assert restored['entry_order'] == p['order_id']
    assert restored['from_limit'] and restored['trail'] and not restored['no_tp']


@pytest.mark.parametrize('closed', [False, True])
def test_recorded_fill_is_not_reprocessed_from_stale_pending_json(factory, closed):
    ex = factory()
    p = pending(ex)
    ex._save_pending()
    trade = ex._limit_trade('card', p, 100, 10)
    if closed:
        with sqlite3.connect(ex.db_path) as c:
            c.execute('UPDATE demo_trades SET closed_ms = 1 WHERE id = ?', (trade['id'],))
    # Simulate a restart after SQLite commit but before removing the pending JSON entry.
    recovered = factory()
    # Still poll the exchange: a recorded trade alone does not prove the order is terminal.
    assert not recovered.pending['card'].get('skip')
    api = SimpleNamespace(fetch_order=AsyncMock(return_value={'status': 'closed', 'filled': 10, 'average': 100}),
                          fetch_open_orders=AsyncMock(return_value=[{'type': 'STOP_MARKET'}]))
    recovered._exchange = AsyncMock(return_value=api)
    asyncio.run(recovered.check_limits())
    assert recovered.pending['card']['skip']
    assert bool(recovered.open) == (not closed)
    with open(recovered.pending_path, encoding='utf-8') as f:
        assert json.load(f)['card']['skip']
    assert factory().pending['card']['skip']
    with sqlite3.connect(ex.db_path) as c:
        assert c.execute('SELECT COUNT(*) FROM demo_trades').fetchone()[0] == 1


def test_different_symbol_does_not_consume_a_pending_order(factory):
    ex = factory()
    p = pending(ex)
    ex._save_pending()
    ex._limit_trade('other', {**p, 'symbol': 'OTHER/USDT:USDT'}, 100, 10)
    restored = factory()
    assert not restored.pending['card'].get('skip')
    assert restored.pending['card']['order_id'] == 'filled-1'
    assert restored._limit_trade('card', p, 100, 10) is not None


@pytest.mark.parametrize('action', ['cancel', 'restore_stop', 'retry_close'])
def test_recorded_fill_still_recovers_needed_exchange_action(factory, action):
    ex = factory()
    p = pending(ex)
    original = ex._limit_trade('card', p, 100, 10)
    recovered = factory()
    recovered.pending = {'card': p}
    api = SimpleNamespace(cancel_order=AsyncMock(), fetch_open_orders=AsyncMock(return_value=[]),
                          fetch_order=AsyncMock(return_value={'status': 'closed', 'filled': 10, 'average': 100}))
    recovered._exchange = AsyncMock(return_value=api)
    recovered._close = AsyncMock()
    recovered._restore_stop = AsyncMock()
    if action == 'cancel':
        asyncio.run(recovered._cancel_limit('card', 'card ended'))
        recovered._close.assert_awaited_once_with(recovered.open['card'], 'LATE_FILL', None)
    else:
        if action == 'retry_close':
            recovered.open['card']['close_pending'] = ['NO_STOP', None]
        asyncio.run(recovered.check_limits())
        if action == 'restore_stop':
            recovered._restore_stop.assert_awaited_once_with(recovered.open['card'])
        else:
            recovered._close.assert_awaited_once_with(recovered.open['card'], 'NO_STOP', None)
    assert recovered.open['card']['id'] == original['id']
    with sqlite3.connect(ex.db_path) as c:
        assert c.execute('SELECT COUNT(*) FROM demo_trades').fetchone()[0] == 1


def test_original_schema_migrates_without_losing_targets(tmp_path, monkeypatch):
    monkeypatch.setattr(executor, 'credentials', lambda: ('', ''))
    path = str(tmp_path / 'old.db')
    with sqlite3.connect(path) as c:
        c.execute(executor.SCHEMA)
        c.execute("INSERT INTO demo_trades (card_id, symbol, direction, tp1, tp2, tp3) "
                  "VALUES ('old', 'OLD/USDT:USDT', 1, 104, 106, 108)")
    for _ in range(2):
        restored = executor.DemoExecutor(path).open['old']
        assert [restored[f'tp{k}'] for k in (1, 2, 3)] == [104, 106, 108]
        assert not restored.get('close_pending')


def test_storage_failure_does_not_block_emergency_close(factory, monkeypatch):
    ex = factory()
    trade = ex._limit_trade('card', pending(ex), 100, 10)
    ex._exchange = AsyncMock(side_effect=OSError('exchange reached'))
    monkeypatch.setattr(executor.errors, 'report', lambda *a: None)
    monkeypatch.setattr(executor.sqlite3, 'connect', lambda *a: (_ for _ in ()).throw(sqlite3.OperationalError('disk')))
    with pytest.raises(OSError, match='exchange reached'):
        asyncio.run(ex._close(trade, 'NO_STOP', None))
    ex._exchange.assert_awaited_once()
    assert ex.open['card']['close_pending'] == ['NO_STOP', None]
