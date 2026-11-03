import pytest
import numpy as np
from flow import WhaleBook, RushBook, Sweep

def test_whalebook_and_rushbook_forget():
    # 1. Test WhaleBook forget
    whale_book = WhaleBook()
    symbol = "BTC/USDT:USDT"
    
    # Add a sweep to WhaleBook
    sweep = Sweep(venue='binance', symbol=symbol, t_first=1000, t_last=1000, side=1, usd=100000.0, px_first=100.0, px_last=101.0, prints=1, levels=2)
    whale_book.add(sweep)
    
    assert symbol in whale_book.hist
    assert symbol in whale_book.whales
    
    whale_book.forget(symbol)
    
    assert symbol not in whale_book.hist
    assert symbol not in whale_book.whales
    assert symbol not in whale_book.notable
    assert symbol not in whale_book.floor_usd
    assert symbol not in whale_book._threshold_cache
    
    # 2. Test RushBook forget
    rush_book = RushBook()
    
    # Add trades to RushBook (opens / closes a group)
    rush_book.on_trade(symbol, ts_ms=1000, side=1, usd=5000.0, price=100.0, fills=2)
    rush_book.on_trade(symbol, ts_ms=1000, side=1, usd=6000.0, price=101.0, fills=2)
    
    assert symbol in rush_book.counts or symbol in rush_book.fill_counts or symbol in rush_book._open
    
    rush_book.forget(symbol)
    
    assert symbol not in rush_book._open
    assert symbol not in rush_book.counts
    assert symbol not in rush_book.usd
    assert symbol not in rush_book.secs
    assert symbol not in rush_book.fill_counts
    assert symbol not in rush_book.fill_secs
    assert symbol not in rush_book._last_rush
