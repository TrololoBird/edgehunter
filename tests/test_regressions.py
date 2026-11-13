import pytest

from sqlsafe import identifier
from security import safe_urlopen
from strategies.base import validate_card_levels
from journal import EXTRA_COLUMNS
from depth import BookState, DepthBook


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
