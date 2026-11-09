"""Regressions from BingX's 2026-11-09 endpoint throttling."""
import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import ccxt
import pytest

from executor import DemoExecutor


def test_busy_read_retries_but_invalid_request_does_not(monkeypatch):
    async def run():
        monkeypatch.setattr(asyncio, 'sleep', AsyncMock())
        ex = DemoExecutor.__new__(DemoExecutor)
        read = AsyncMock(side_effect=[ccxt.OperationFailed('bingx {"code":100410}'), []])
        ex._exchange = AsyncMock(return_value=SimpleNamespace(fetch_positions=read))
        assert await ex._call('fetch_positions', ['BTC']) == []
        assert read.await_count == 2
        ex._read_resume_at = 0
        read.reset_mock(side_effect=True)
        read.side_effect = ccxt.AuthenticationError('bad key')
        with pytest.raises(ccxt.AuthenticationError):
            await ex._call('fetch_positions', ['BTC'])
        assert read.await_count == 1
    asyncio.run(run())


def test_explicit_ban_blocks_following_reads_without_waiting(monkeypatch):
    async def run():
        sleep = AsyncMock()
        monkeypatch.setattr(asyncio, 'sleep', sleep)
        ex = DemoExecutor.__new__(DemoExecutor)
        until = int((time.time() + 240) * 1000)
        read = AsyncMock(side_effect=ccxt.OperationFailed(
            f'bingx {{"code":100410,"msg":"unblocked after {until}"}}'))
        ex._exchange = AsyncMock(return_value=SimpleNamespace(fetch_positions=read))
        with pytest.raises(ccxt.OperationFailed):
            await ex._call('fetch_positions')
        with pytest.raises(ccxt.ExchangeNotAvailable):
            await ex._call('fetch_positions')
        assert read.await_count == 1
        sleep.assert_not_awaited()
    asyncio.run(run())


def test_pending_restop_is_retried_during_sync():
    ex = DemoExecutor.__new__(DemoExecutor)
    card = SimpleNamespace(symbol='BTC', group_key='g', entered_at=10, created=5,
                           finished=False, best_target=1)
    ex.open = {'BTC|g|10': {'restop_pending': True}}
    ex.on_target = AsyncMock()
    ex.on_restop = AsyncMock()
    asyncio.run(ex.sync_targets([card]))
    ex.on_restop.assert_awaited_once_with(card)


def test_incomplete_non_breakout_cup_does_not_claim_history_failure():
    from strategies.cup_handle import cup_handle
    from test_audit_2026_10_16 import _cup, DAY
    bars = _cup('u')[150:]  # shape exists, but insufficient prior advance history
    skips = []
    assert cup_handle(bars, '1d', DAY, skips) is None
    assert skips  # actual breakout is unverifiable
    bars[-1][4] = 98  # no breakout: insufficient history is irrelevant
    skips = []
    assert cup_handle(bars, '1d', DAY, skips) is None
    assert not skips


def test_memory_deferral_sets_retry_deadline(monkeypatch):
    import memory_guard
    from ml import AnomalyModel
    model = AnomalyModel()
    monkeypatch.setattr(memory_guard, 'pressured', lambda ratio: True)
    asyncio.run(model.afit())
    assert model._fit_retry_at > time.time() + 290
    assert not model.due(time.time())
