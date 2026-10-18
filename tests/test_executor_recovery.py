"""Offline reproductions of limit execution and recovery failures."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import executor


def waiting(ex):
    p = {'order_id': 'order-1', 'symbol': 'AUDIT/USDT:USDT', 'qty': 100,
         'lv': {'entry': 100, 'sl': 98, 'tp1': 104, 'tp2': 106, 'tp3': 108},
         'scale': 1, 'basis': 0, 'setup': 'ORB UP', 'strategy': 'orb', 'direction': 1}
    ex.pending = {'card': p}
    return p


def limits(order):
    ex = executor.DemoExecutor.__new__(executor.DemoExecutor)
    p = waiting(ex)
    api = SimpleNamespace(fetch_order=AsyncMock(return_value=order), cancel_order=AsyncMock())
    ex._exchange = AsyncMock(return_value=api)
    ex._limit_filled, ex._save_pending = AsyncMock(), Mock()
    return ex, api, p


@pytest.mark.parametrize('status', ['closed', 'canceled', 'cancelled', 'expired', 'rejected'])
def test_terminal_zero_fill_does_not_create_a_position(status):
    ex, api, p = limits({'status': status, 'filled': 0})
    asyncio.run(ex.check_limits())
    ex._limit_filled.assert_not_awaited()
    api.cancel_order.assert_not_awaited()
    if status == 'closed':
        assert ex.pending['card'] is p  # contradictory status: poll again for the actual fill
        ex._save_pending.assert_not_called()
    else:
        assert ex.pending['card']['skip']
        ex._save_pending.assert_called_once()


@pytest.mark.parametrize('status', ['closed', 'canceled', 'expired', 'rejected'])
def test_terminal_partial_fill_uses_actual_size(status):
    ex, api, p = limits({'status': status, 'filled': 17.5, 'average': 100.25})
    asyncio.run(ex.check_limits())
    ex._limit_filled.assert_awaited_once_with('card', p, 100.25, 17.5)
    api.cancel_order.assert_not_awaited()


@pytest.mark.parametrize('bad', [None, 'bad', float('nan'), float('inf'), -1])
@pytest.mark.parametrize('cancel', [False, True])
def test_invalid_fill_keeps_order_tracked(bad, cancel):
    ex, api, p = limits({'status': 'closed', 'filled': bad})
    if cancel:
        asyncio.run(ex._cancel_limit('card', 'test'))
    else:
        asyncio.run(ex.check_limits())
    assert ex.pending['card'] is p
    ex._limit_filled.assert_not_awaited()
    ex._save_pending.assert_not_called()


def test_nearly_complete_open_order_is_cancelled_before_conversion():
    ex, api, p = limits({})
    api.fetch_order.side_effect = [
        {'status': 'open', 'filled': 99.95, 'average': 100},
        {'status': 'canceled', 'filled': 99.97, 'average': 100.1},
    ]
    asyncio.run(ex.check_limits())
    api.cancel_order.assert_awaited_once_with('order-1', p['symbol'])
    ex._limit_filled.assert_awaited_once_with('card', p, 100.1, 99.97)


@pytest.mark.parametrize('stage', ['exchange', 'position'])
def test_failed_close_remains_tracked_for_retry(stage, tmp_path, monkeypatch):
    monkeypatch.setattr(executor, 'credentials', lambda: ('', ''))
    ex = executor.DemoExecutor(str(tmp_path / 'demo.db'))
    api = SimpleNamespace(fetch_open_orders=AsyncMock(return_value=[]))
    ex._exchange = AsyncMock(return_value=api)
    ex._position_qty = AsyncMock(side_effect=OSError('offline'))
    if stage == 'exchange':
        ex._exchange.side_effect = OSError('offline')
    trade = {'card_id': 'late-fill', 'symbol': 'AUDIT/USDT:USDT', 'direction': 1}
    trade['id'] = ex._insert(trade)
    with pytest.raises(OSError, match='offline'):
        asyncio.run(ex._close(trade, 'LATE_FILL', None))
    assert ex.open['late-fill'] is trade
    assert trade['close_pending'] == ['LATE_FILL', None]


@pytest.mark.parametrize('kind', ['pending', 'unknown'])
def test_state_replace_failure_preserves_previous_json(tmp_path, monkeypatch, kind):
    import storage
    ex = executor.DemoExecutor.__new__(executor.DemoExecutor)
    path = tmp_path / 'state.json'
    path.write_text('{"old": true}', encoding='utf-8')
    ex.pending_path = ex.unknown_path = str(path)
    ex.pending = {'new': {'order_id': 'order-2'}}
    ex._unknown_coins = {'AUDIT': 123.0}
    save = ex._save_pending if kind == 'pending' else ex._save_unknown
    monkeypatch.setattr(executor.errors, 'report', Mock())
    with monkeypatch.context() as patch:
        patch.setattr(storage.os, 'replace', Mock(side_effect=OSError('disk failure')))
        save()
    assert json.loads(path.read_text()) == {'old': True}
    assert sorted(p.name for p in tmp_path.iterdir()) == ['state.json']
    save()
    assert json.loads(path.read_text()) == (ex.pending if kind == 'pending' else ex._unknown_coins)
