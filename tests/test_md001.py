import pytest
from types import SimpleNamespace
from collections import deque
from iceberg import IcebergDetector
from depth import DepthBook, BookState
from fetcher import DataFetcher
from unittest.mock import Mock

def test_iceberg_invalidate_and_clear():
    detector = IcebergDetector()
    symbol = "BTC/USDT:USDT"
    
    detector.levels.setdefault(symbol, {1: {}, -1: {}})
    detector.events.setdefault(symbol, deque()).append((1000, 1, 100.0, 1000.0))
    
    assert symbol in detector.levels
    assert symbol in detector.events
    
    detector.invalidate(symbol)
    assert symbol not in detector.levels
    assert symbol not in detector.events
    
    detector.levels[symbol] = {1: {}, -1: {}}
    detector.events[symbol] = deque([(1000, 1, 100.0, 1000.0)])
    detector.clear_symbol(symbol)
    assert symbol not in detector.levels
    assert symbol not in detector.events

def test_fetcher_unsynced_orderbook_blocks_iceberg():
    fetcher = DataFetcher.__new__(DataFetcher)
    fetcher.icebergs = IcebergDetector()
    fetcher.depth = DepthBook()
    
    symbol = "BTC/USDT:USDT"
    fetcher._binance_keys = {('futures', 'BTCUSDT'): symbol}
    fetcher.flow = Mock()
    fetcher.sweeps = Mock()
    fetcher.rush = Mock()
    fetcher.markets = {}
    fetcher.footprint = SimpleNamespace(bucket={})
    fetcher.entry_trackers = {}
    fetcher._last_agg = {}
    
    fetcher.icebergs.levels.setdefault(symbol, {1: {}, -1: {}})
    
    fetcher.depth.start(symbol)
    book = fetcher.depth.books[symbol]
    assert not book.synced
    
    data = {
        'e': 'aggTrade',
        's': 'BTCUSDT',
        'p': '100.0',
        'q': '10.0',
        'm': False,
        'T': 1000,
        'a': 1,
        'l': 1,
        'f': 1
    }
    
    fetcher.on_binance('futures', 'aggTrade', data, 1000.0)
    
    book.synced = True
    fetcher.on_binance('futures', 'aggTrade', data, 1000.0)

def test_resync_triggers_iceberg_invalidation():
    fetcher = DataFetcher.__new__(DataFetcher)
    fetcher.icebergs = IcebergDetector()
    fetcher.depth = DepthBook(on_resync=fetcher._resync)
    
    symbol = "BTC/USDT:USDT"
    fetcher.icebergs.levels.setdefault(symbol, {1: {}, -1: {}})
    fetcher.depth.start(symbol)
    book = fetcher.depth.books[symbol]
    book.synced = True
    
    assert symbol in fetcher.icebergs.levels
    
    fetcher.depth._resync(book)
    fetcher.depth._resync_book(book)
    assert symbol not in fetcher.icebergs.levels
