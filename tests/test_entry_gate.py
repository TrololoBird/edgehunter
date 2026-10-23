"""Owner 2026-10-18: demo entry gate - one entry per direction per cluster_entry_sec, demo_off_setups not traded."""
import asyncio
import sqlite3
import time
from types import SimpleNamespace

import pytest

from executor import DemoExecutor


@pytest.fixture(autouse=True)
def _gate_on(monkeypatch):
    # eng-148: the owner turned both rules off on the demo (defaults 0 / ()); the mechanism is checked switched on
    import executor
    monkeypatch.setattr(executor.CONFIG, 'executor', SimpleNamespace(**{
        **vars(executor.CONFIG.executor), 'cluster_entry_sec': 900,
        'demo_off_setups': ('BB W-BOTTOM', 'VA80 LONG', 'AUCTION LONG')}))


def _executor(tmp_path, trades=(), pending=None):
    ex = DemoExecutor.__new__(DemoExecutor)
    ex.db_path = str(tmp_path / 'demo.db')
    ex.pending = pending or {}
    with sqlite3.connect(ex.db_path) as c:
        c.execute("CREATE TABLE demo_trades (symbol TEXT, direction INTEGER, opened_ms INTEGER, entry_fill REAL)")
        c.executemany("INSERT INTO demo_trades VALUES (?, ?, ?, ?)", trades)
    return ex


def _card(group_key='ORB UP', direction=1):
    return SimpleNamespace(group_key=group_key, direction=direction, sig={})


def _ago(minutes):
    return int((time.time() - minutes * 60) * 1000)


@pytest.mark.parametrize('setup', ['BB W-BOTTOM', 'VA80 LONG', 'AUCTION LONG'])
def test_off_setups_not_traded(tmp_path, setup):
    assert _executor(tmp_path).entry_gate(_card(setup)).startswith('setup off on demo')


def test_free_market_passes(tmp_path):
    assert _executor(tmp_path).entry_gate(_card()) is None


def test_same_direction_fill_in_window_blocks(tmp_path):
    ex = _executor(tmp_path, [('LDO/USDT:USDT', 1, _ago(5), 1.0)])
    assert ex.entry_gate(_card()).startswith('cluster: LDO/USDT:USDT entered long')


def test_other_direction_does_not_block(tmp_path):
    ex = _executor(tmp_path, [('LDO/USDT:USDT', 1, _ago(5), 1.0)])
    assert ex.entry_gate(_card('ORB DOWN', -1)) is None


def test_fill_outside_window_does_not_block(tmp_path):
    assert _executor(tmp_path, [('LDO/USDT:USDT', 1, _ago(20), 1.0)]).entry_gate(_card()) is None


def test_skipped_row_without_fill_does_not_block(tmp_path):
    # CLUSTER / SETUP_OFF / OVERLAP rows have no fill: a skip must not extend the window
    assert _executor(tmp_path, [('LDO/USDT:USDT', 1, _ago(1), None)]).entry_gate(_card()) is None


def test_resting_limit_in_window_blocks(tmp_path):
    ex = _executor(tmp_path, pending={'k': {'symbol': 'ATOM/USDT:USDT', 'direction': 1, 'placed_ms': _ago(3)}})
    assert ex.entry_gate(_card()).startswith('cluster: ATOM/USDT:USDT')


def test_old_or_skipped_limit_does_not_block(tmp_path):
    ex = _executor(tmp_path, pending={'a': {'symbol': 'A', 'direction': 1, 'placed_ms': _ago(30)},
                                      'b': {'skip': True, 'direction': 1, 'placed_ms': _ago(1)}})
    assert ex.entry_gate(_card()) is None


def test_window_off(tmp_path, monkeypatch):
    import executor
    monkeypatch.setattr(executor.CONFIG, 'executor',
                        SimpleNamespace(**{**vars(executor.CONFIG.executor), 'cluster_entry_sec': 0}))
    ex = _executor(tmp_path, [('LDO/USDT:USDT', 1, _ago(1), 1.0)])
    assert ex.entry_gate(_card()) is None


def test_place_limit_skips_off_setup_and_waits_on_cluster(tmp_path):
    ex = _executor(tmp_path, [('LDO/USDT:USDT', 1, _ago(5), 1.0)])
    ex.risk_limit = lambda: None
    ex._unknown_coins = {}
    ex.open = {}
    off = SimpleNamespace(group_key='BB W-BOTTOM', direction=1, plan={}, symbol='X/USDT:USDT')
    asyncio.run(ex._place_limit('off', off))
    assert ex.pending['off']['skip'] and 'setup off' in ex.pending['off']['reason']
    card = SimpleNamespace(group_key='ORB UP', direction=1, plan={}, symbol='Y/USDT:USDT')
    asyncio.run(ex._place_limit('c', card))
    assert 'c' not in ex.pending               # not marked skipped: retried once the window passes
