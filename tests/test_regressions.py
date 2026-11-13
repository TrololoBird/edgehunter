import pytest

from sqlsafe import identifier
from security import safe_urlopen
from strategies.base import validate_card_levels
from journal import EXTRA_COLUMNS, shrinkage_upper, wilson_upper
from depth import BookState, DepthBook
from extdata import okx_completed_bucket, okx_taker_rows
from levels import simulate
from executor import credentials, DemoExecutor


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
    assert {'agg_oi_change_1h', 'oi_venues', 'feature_schema_version'} <= set(EXTRA_COLUMNS)


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


def test_shrinkage_gate_is_explicit_and_conservative_for_small_samples():
    assert 0.5 < shrinkage_upper(1, 1) < 1.0
    assert shrinkage_upper(1, 1) >= shrinkage_upper(0, 1)
    assert wilson_upper(1, 1) > 0.9
