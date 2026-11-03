import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import pytest
import executor

def test_restop_failed_uses_mark_price_and_avoids_false_close():
    ex_exec = executor.DemoExecutor.__new__(executor.DemoExecutor)
    ex_exec._position_qty = AsyncMock(return_value=1.0)
    
    # Mock exchange api: fetch_ticker returns safe markPrice (100.0) and breached last (90.0) for a long trade (direction 1, SL = 95.0)
    api = SimpleNamespace(
        fetch_ticker=AsyncMock(return_value={'markPrice': 100.0, 'last': 90.0}),
        create_order=AsyncMock()
    )
    ex_exec._exchange = AsyncMock(return_value=api)
    
    trade = {'symbol': 'BTC/USDT:USDT', 'direction': 1, 'scale': 1.0, 'sl': 90.0}
    s = SimpleNamespace(levels={'sl': 95.0})
    
    asyncio.run(ex_exec._restop_failed(trade, s, Exception("stop failed")))
    
    # Since mark price (100.0) is safe (> new_sl 95.0 for long), create_order should NOT be called (no false market closure)
    api.create_order.assert_not_awaited()

def test_restop_failed_falls_back_to_last_when_mark_unavailable():
    ex_exec = executor.DemoExecutor.__new__(executor.DemoExecutor)
    ex_exec._position_qty = AsyncMock(return_value=1.0)
    
    # Mock exchange api: fetch_ticker has no markPrice, but last (90.0) is breached (SL = 95.0 for long)
    api = SimpleNamespace(
        fetch_ticker=AsyncMock(return_value={'last': 90.0}),
        create_order=AsyncMock()
    )
    ex_exec._exchange = AsyncMock(return_value=api)
    
    trade = {'symbol': 'BTC/USDT:USDT', 'direction': 1, 'scale': 1.0, 'sl': 90.0}
    s = SimpleNamespace(levels={'sl': 95.0})
    
    asyncio.run(ex_exec._restop_failed(trade, s, Exception("stop failed")))
    
    # Fallback to last (90.0 <= 95.0) triggers market close
    api.create_order.assert_awaited_once()
