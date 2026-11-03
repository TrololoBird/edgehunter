import pytest
import numpy as np
from flow import FlowStore, BUY, SELL

def test_flowstore_symbol_rotation_cache_invalidation():
    store = FlowStore(venues=['binance'], capacity=16)
    
    # 1. Register BTC, seed flow, and take snapshot to populate _hour_cache
    store.register(["BTC/USDT:USDT"])
    row_btc = store.rows["BTC/USDT:USDT"]
    
    # Add flow for BTC
    store.seed_minute('binance', "BTC/USDT:USDT", minute_ms=1000000, buy_usd=10000.0, sell_usd=2000.0, trades=10)
    
    snap1 = store.snapshot(now_sec=1005)
    assert snap1["BTC/USDT:USDT"]["agg_cvd_1h"] == 8000.0
    
    # 2. Unregister BTC
    store.unregister("BTC/USDT:USDT")
    
    # 3. Register ETH, which should reuse row_btc
    store.register(["ETH/USDT:USDT"])
    row_eth = store.rows["ETH/USDT:USDT"]
    assert row_eth == row_btc
    
    # 4. Snapshot should not inherit BTC's old CVD (must be reset/invalidated)
    snap2 = store.snapshot(now_sec=1010)
    assert snap2["ETH/USDT:USDT"]["agg_cvd_1h"] == 0.0
