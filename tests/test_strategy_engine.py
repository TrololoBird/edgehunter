import pytest

from core.strategy_engine import MarketSnapshot


def test_market_snapshot_rejects_future_candle():
    with pytest.raises(ValueError, match='at or after'):
        MarketSnapshot(1000, 'BTC/USDT:USDT', ((1000, 1, 1, 1, 1, 1),))


def test_market_snapshot_is_immutable_and_causal():
    source = [[100, 1, 2, 0, 1, 3]]
    snap = MarketSnapshot(1000, 'BTC/USDT:USDT', source, {'x': 1})
    source[0][1] = 99
    assert snap.candles[0][1] == 1
    with pytest.raises(TypeError):
        snap.features['x'] = 2
