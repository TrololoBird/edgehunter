import math
import sqlite3
import subprocess
import asyncio
from pathlib import Path
from types import SimpleNamespace
import pytest

from core.source_manifest import VERIFIED_SOURCE_RECORDS
from core.execution_contract import ExecutionPhase, validate_transition
from core.data_provenance import DataProvenance, MarketDataState, require_decision_safe
from core.execution_reconciler import ExchangeOrderEvent, ExecutionReconciler
from executor import DemoExecutor
from levels import simulate
from macro import Macro
from strategies import STRATEGIES, SETUPS
from fetcher import DataFetcher, VenueDeriv
from journal import SignalJournal
from scanner import Scanner


def test_deploy_precheck_accepts_empty_v2_registry_and_version():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([str(root / 'deploy' / 'precheck.sh')], cwd=root, text=True,
                            capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_ml_status_reports_removed_runtime_without_fake_model_fields():
    scanner = Scanner.__new__(Scanner)
    scanner.regime = None
    status = scanner._ml_status()
    assert status == {'ml_runtime': 'removed', 'regime': None}
    assert 'anomaly_ready' not in status and 'pretrained_rows' not in status


def test_disabled_notifier_does_not_retry_queued_messages():
    from notifier import Notifier

    notifier = Notifier.__new__(Notifier)
    notifier.cfg = SimpleNamespace(enabled=False)
    notifier._outbox = [{'text': 'local fixture', 'chat': 'fixture'}]
    notifier._retry_task = None
    asyncio.run(asyncio.to_thread(notifier.resume))
    assert notifier._retry_task is None
    assert len(notifier._outbox) == 1


def test_v2_registry_has_no_unverified_strategy_fallback():
    assert STRATEGIES == {}
    assert SETUPS == {}
    assert VERIFIED_SOURCE_RECORDS == {}


def test_limit_touch_is_not_a_historical_fill():
    result = simulate(
        {'entry': 100.0, 'sl': 95.0, 'tp1': 105.0, 'tp2': 110.0, 'tp3': 115.0,
         'limit_entry': True},
        1,
        [[0, 100.0, 101.0, 99.0, 100.0, 0.0]],
        use_fill=True,
    )
    assert result['filled'] == 0
    assert result['outcome'] == 'UNSUPPORTED_LIMIT_MODEL'
    assert result['execution_status'] == 'UNSUPPORTED_LIMIT'


def test_macro_pit_uses_latest_release_for_each_observation():
    rows = [(0, 1.0, 100), (0, 2.0, 200), (86_400_000, 3.0, 300)]
    macro = Macro({'us10y': rows}, strict_pit=True)
    assert macro._asof('us10y', 150) == 1.0
    assert macro._asof('us10y', 250) == 2.0
    assert macro._asof('us10y', 350) == 3.0
    assert macro._asof('us10y', 350, back=1) == 2.0


def test_macro_current_two_field_rows_are_unavailable_in_strict_mode():
    macro = Macro({'us10y': [(0, 1.0)]}, strict_pit=True)
    assert macro._asof('us10y', 10_000) is None
    assert math.isnan(macro.features(10_000)['us10y_5d_bp'])


def test_executor_is_source_gated_even_if_config_is_changed(monkeypatch, tmp_path):
    monkeypatch.setattr('executor.credentials', lambda: ('key', 'secret'))
    monkeypatch.setattr('executor.STRATEGIES', {})
    demo = DemoExecutor(str(tmp_path / 'demo.sqlite'))
    assert demo.enabled is False


def test_execution_contract_rejects_skipping_exchange_evidence():
    validate_transition(None, ExecutionPhase.SIGNAL)
    validate_transition(ExecutionPhase.SIGNAL, ExecutionPhase.VALIDATED)
    validate_transition(ExecutionPhase.VALIDATED, ExecutionPhase.ORDER_SUBMITTED)
    with pytest.raises(ValueError):
        validate_transition(ExecutionPhase.VALIDATED, ExecutionPhase.FILLED)


def test_funding_aggregate_keeps_settlement_provenance():
    fetcher = DataFetcher.__new__(DataFetcher)
    settled = VenueDeriv(oi_usd=100.0, funding_8h=0.001, funding_kind='settled', oi_ts=1_000, funding_ts=1_000)
    predicted = VenueDeriv(oi_usd=100.0, funding_8h=0.002, funding_kind='predicted', oi_ts=1_000, funding_ts=1_000)
    fetcher.venue_derivs = {'BTC': {'binance': settled, 'bybit': predicted}}
    result = fetcher._deriv_snapshot('BTC', 2_000)
    assert result['agg_funding_kind'] == 'mixed'
    assert result['agg_funding_observations'] == 2


def test_unmarked_legacy_journal_is_rejected(tmp_path):
    path = tmp_path / 'legacy.sqlite'
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE signals (id INTEGER PRIMARY KEY, ts_ms INTEGER, symbol TEXT, group_key TEXT, kind TEXT)')
    conn.execute("INSERT INTO signals(id, ts_ms, symbol, group_key, kind) VALUES (1, 1, 'BTC', 'legacy', 'entry')")
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match='unmarked journal'):
        SignalJournal(str(path))


def test_data_provenance_requires_availability_at_decision_time():
    observed = DataProvenance(
        venue='binance', market='spot', symbol='BTCUSDT', field='close',
        event_ts_ms=100, received_ts_ms=150, available_ts_ms=150,
        source='kline', state=MarketDataState.OBSERVED, units='USDT',
    )
    assert observed.is_decision_safe
    assert observed.safe_at(150)
    assert not observed.safe_at(149)
    require_decision_safe(observed, 150)
    with pytest.raises(ValueError, match='decision-safe'):
        require_decision_safe(observed, 149)


def test_execution_reconciler_does_not_invent_fill_from_terminal_status():
    reconciler = ExecutionReconciler()
    reconciler.register_submission('card-1', 'binance', 'BTCUSDT', order_id='o-1', event_ts_ms=100)
    unknown = reconciler.apply(ExchangeOrderEvent(
        card_id='card-1', venue='binance', symbol='BTCUSDT', order_id='o-1',
        status='CANCELED', event_ts_ms=110, received_ts_ms=111,
    ))
    assert unknown.phase is ExecutionPhase.UNKNOWN
    assert unknown.executed_qty == 0
    unresolved = reconciler.apply(ExchangeOrderEvent(
        card_id='card-1', venue='binance', symbol='BTCUSDT', order_id='o-1',
        status='FILLED', event_ts_ms=112, received_ts_ms=113,
    ))
    assert unresolved.phase is ExecutionPhase.UNKNOWN
    assert unresolved.executed_qty == 0


def test_execution_reconciler_requires_exchange_fill_evidence():
    reconciler = ExecutionReconciler()
    reconciler.register_submission('card-2', 'binance', 'ETHUSDT', order_id='o-2', event_ts_ms=100)
    filled = reconciler.apply(ExchangeOrderEvent(
        card_id='card-2', venue='binance', symbol='ETHUSDT', order_id='o-2',
        status='FILLED', executed_qty=2, average_price=2000, event_ts_ms=110, received_ts_ms=111,
        event_id='evt-1',
    ))
    assert filled.phase is ExecutionPhase.FILLED
    assert filled.executed_qty == 2
    assert reconciler.apply(ExchangeOrderEvent(
        card_id='card-2', venue='binance', symbol='ETHUSDT', order_id='o-2',
        status='FILLED', executed_qty=2, average_price=2000, event_ts_ms=110, received_ts_ms=111,
        event_id='evt-1',
    )) == filled
