import pytest

from sqlsafe import identifier
from security import safe_urlopen
from strategies.base import validate_card_levels
from journal import EXTRA_COLUMNS, shrinkage_upper, wilson_upper
from depth import BookState, DepthBook
from extdata import okx_completed_bucket, okx_taker_rows
from levels import simulate
from executor import credentials, DemoExecutor
from fetcher import DataFetcher
from core.quant_gate import scenario_gate
import pumps
from iceberg import IcebergDetector


def test_sql_identifier_requires_allowlist():
    assert identifier("logic_version", {"logic_version"}) == "logic_version"


@pytest.mark.parametrize("value", ["x; DROP TABLE signals", "1column", "name with spaces"])
def test_sql_identifier_rejects_injection_shapes(value):
    with pytest.raises(ValueError):
        identifier(value, {value})


def test_sql_identifier_rejects_unknown_names():
    with pytest.raises(ValueError):
        identifier("secret", {"public"})


def test_url_helper_rejects_non_https():
    with pytest.raises(ValueError):
        safe_urlopen("http://example.test", timeout=1)


@pytest.mark.parametrize(
    "direction,levels,valid",
    [
        (1, {'entry': 100, 'sl': 95, 'tp1': 105, 'tp2': 110, 'tp3': 115}, True),
        (-1, {'entry': 100, 'sl': 105, 'tp1': 95, 'tp2': 90, 'tp3': 85}, True),
        (1, {'entry': 100, 'sl': 95, 'tp1': 105, 'tp2': 103, 'tp3': 115}, False),
        (-1, {'entry': 100, 'sl': 105, 'tp1': 95, 'tp2': 97, 'tp3': 85}, False),
        (1, {'entry': 100, 'sl': 95, 'tp1': None, 'tp2': None, 'tp3': None}, True),
    ],
)
def test_card_geometry_is_side_aware(direction, levels, valid):
    assert validate_card_levels(levels, direction) is valid


def test_runtime_feature_contract_is_persisted():
    assert {'agg_oi_change_1h', 'oi_venues', 'iceberg_reason', 'feature_schema_version'} <= set(EXTRA_COLUMNS)


def test_depth_pruning_bounds_changed_levels():
    book = BookState()
    book.bids = {90.0: 1.0, 99.0: 1.0, 100.0: 1.0}
    book.asks = {100.0: 1.0, 101.0: 1.0, 110.0: 1.0}
    DepthBook._prune(book, 100.0)
    assert set(book.bids) == {99.0, 100.0}
    assert set(book.asks) == {100.0, 101.0}


def test_okx_taker_rows_normalize_timestamp_and_reject_bad_rows():
    rows = okx_taker_rows({'code': '0', 'data': [['1700000000', '2.5', '4'], ['bad', 1, 2], ['x']]})
    assert rows == [(1700000000000, 2.5, 4.0)]
    assert okx_completed_bucket(1_700_000_000_000, 1_700_000_600_000) == 1_700_000_000_000
    assert okx_completed_bucket(1_700_000_600_000, 1_700_000_600_000) == 1_700_000_300_000
    assert okx_completed_bucket(1_700_000_900_000, 1_700_000_600_000) is None


@pytest.mark.parametrize(
    "direction,levels,candle",
    [
        (1, {'entry': 100, 'sl': 95, 'tp1': 105, 'tp2': 110, 'tp3': 115}, [0, 100, 106, 94, 100, 0]),
        (-1, {'entry': 100, 'sl': 105, 'tp1': 95, 'tp2': 90, 'tp3': 85}, [0, 100, 106, 94, 100, 0]),
    ],
)
def test_replay_resolves_intrabar_stop_before_target(direction, levels, candle):
    result = simulate(levels, direction, [candle], use_fill=False)
    assert result['outcome'] == 'SL'


def test_executor_credentials_fail_closed_without_environment(monkeypatch):
    monkeypatch.delenv('BINGX_API_KEY', raising=False)
    monkeypatch.delenv('BINGX_API_SECRET', raising=False)
    assert credentials() == ('', '')


def test_executor_entry_intent_is_idempotent(tmp_path):
    demo = DemoExecutor(str(tmp_path / 'demo.sqlite'))
    assert demo._claim_execution('card-1', 'ENTRY') is True
    assert demo._claim_execution('card-1', 'ENTRY') is False
    assert demo._claim_execution('card-1', 'STOP') is True
    assert demo._protection_state({'direction': 1, 'entry_fill': 100, 'sl': 95, 'no_stop': 0}) == 'PROTECTED'
    assert demo._protection_state({'direction': -1, 'entry_fill': 100, 'sl': 95, 'no_stop': 0}) == 'INVALID_GEOMETRY'
    assert demo._protection_state({'strategy': 'connors', 'no_stop': 1}) == 'NO_STOP_ALLOWED'


def test_virtual_tp_parts_are_bounded_and_deterministic():
    class Exchange:
        @staticmethod
        def amount_to_precision(symbol, amount):
            return f'{amount:.8f}'

    assert DemoExecutor.tp_parts(Exchange(), 'BTC', 9, trail=False, no_tp=False) == [(1, 3.0), (2, 3.0), (3, 3.0)]
    assert DemoExecutor.tp_parts(Exchange(), 'BTC', 9, trail=True, no_tp=False) == [(1, 4.5)]
    assert DemoExecutor.tp_parts(Exchange(), 'BTC', 9, trail=False, no_tp=True) == []


def test_shrinkage_gate_is_explicit_and_conservative_for_small_samples():
    assert 0.5 < shrinkage_upper(1, 1) < 1.0
    assert shrinkage_upper(1, 1) >= shrinkage_upper(0, 1)
    assert wilson_upper(1, 1) > 0.9


def test_minute_backfill_counts_only_after_gap_is_verified(monkeypatch):
    class MD:
        minute_klines = [[0, 1, 1, 1, 1, 1, 1, 1],
                         [60_000, 1, 1, 1, 1, 1, 1, 1],
                         [180_000, 1, 1, 1, 1, 1, 1, 1]]
        minute_closed_until = 180_000

        def seed_minutes(self, market, rows, now_ms):
            self.minute_klines.extend(rows)
            self.minute_klines.sort(key=lambda row: row[0])

    fetcher = object.__new__(DataFetcher)
    fetcher.backfill_stats = {'requested': 0, 'attempted': 0, 'applied': 0, 'verified': 0,
                              'failed': 0, 'deferred': 0}

    async def rows(*args):
        return [[120_000, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0]]

    monkeypatch.setattr(fetcher, 'fetch_minute_klines', rows)
    md = MD()
    import asyncio
    assert asyncio.run(fetcher.patch_minute_holes('BTC', md, 200_000)) == 0
    assert fetcher.backfill_stats['applied'] == 1
    assert fetcher.backfill_stats['verified'] == 1


def test_briefing_quant_gate_rejects_non_positive_net_ev():
    rejected = scenario_gate(0.5, reward=1.0, risk=1.0, cost=0.01)
    accepted = scenario_gate(0.7, reward=2.0, risk=1.0, cost=0.01)
    assert rejected['trade_gate'] is False
    assert rejected['ev_net'] < 0
    assert accepted['trade_gate'] is True
    assert accepted['p_base'] >= accepted['p_breakeven']


def test_pump_monitor_is_explicitly_informational():
    assert pumps.STATS['pump']['verdict'].startswith('НЕ подтверждено')
    assert pumps.PUMP == 0.15 and pumps.WIN == 6


def test_iceberg_is_unknown_without_fresh_l2_coverage():
    detector = IcebergDetector()
    assert detector.features('BTC', now_ms=1000)['iceberg_net_5m'] is None
    detector.on_book('BTC', [[100, 2]], [[101, 2]], 1000)
    assert detector.features('BTC', now_ms=2000)['iceberg_reason'] == 'ok'
    assert detector.features('BTC', now_ms=1000 + 61_000)['iceberg_reason'] == 'stale_l2_coverage'
    detector.invalidate('BTC')
    assert detector.features('BTC', now_ms=2000)['iceberg_reason'] == 'sequence_resync_or_no_book'


def test_depth_records_sequence_gaps_and_buffer_drops():
    from depth import DepthBook
    book = DepthBook()
    book.start('BTC')
    for i in range(2001):
        book.on_diff('BTC', {'u': i + 1, 'U': i + 1, 'pu': 0, 'E': i})
    assert book.books['BTC'].buffer_drops == 1000
    book.books['BTC'].synced = True
    book.books['BTC'].last_u = 10
    book.on_diff('BTC', {'u': 12, 'U': 12, 'pu': 11, 'E': 1})
    assert book.books['BTC'].sequence_gaps == 1
    diag = book.diagnostics()
    assert diag['sequence_gaps'] == 1 and diag['buffer_drops'] == 1000
