import pytest
from iceberg import IcebergDetector, REPLENISH_TIMEOUT_MS

def test_iceberg_replenishment_timeout_and_no_gluing():
    detector = IcebergDetector()
    symbol = "BTC/USDT:USDT"
    
    # 1. Book snapshot shows bid at 100.0
    detector.on_book(symbol, bids=[(100.0, 10.0)], asks=[], ts_ms=1000)
    assert 100.0 in detector.levels[symbol][1]
    
    # Trade hits bid at 100.0 -> l.executed > 0
    detector.on_trade(symbol, ts_ms=1100, price=100.0, usd=200.0, taker_side=-1)
    lvl = detector.levels[symbol][1][100.0]
    assert lvl.executed == 200.0
    
    # 2. Liquidity disappears from book at t=1200
    detector.on_book(symbol, bids=[], asks=[], ts_ms=1200)
    assert 100.0 in detector.levels[symbol][1]  # kept because executed > 0 and within timeout
    
    # 3. Within REPLENISH_TIMEOUT_MS (e.g. at t=1500, elapsed 300ms <= 400ms): level is still kept
    detector.on_book(symbol, bids=[], asks=[], ts_ms=1500)
    assert 100.0 in detector.levels[symbol][1]
    
    # 4. After REPLENISH_TIMEOUT_MS (e.g. at t=1700, elapsed 500ms > 400ms from disappearance at 1200): level is deleted
    detector.on_book(symbol, bids=[], asks=[], ts_ms=1700)
    assert 100.0 not in detector.levels[symbol][1]
    
    # 5. New liquidity appears at 100.0 at t=2000: creates new _Level with executed=0 and refills=0 (no gluing)
    detector.on_book(symbol, bids=[(100.0, 5.0)], asks=[], ts_ms=2000)
    assert 100.0 in detector.levels[symbol][1]
    new_lvl = detector.levels[symbol][1][100.0]
    assert new_lvl.executed == 0.0
    assert new_lvl.refills == 0
