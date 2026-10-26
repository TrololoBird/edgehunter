"""eng-169c (audit): a rejected restop with the price past the new stop closes at market; the eng-155b partial keeps
half of the ORIGINAL size after a TP1 third already left (live APE 2026-10-24: 15048 closed of 20065, 1/6 left)."""
import asyncio
import types

import executor as exm
from executor import DemoExecutor


class Ex:
    def __init__(self, last, pos):
        self.last, self.pos, self.orders = last, pos, []

    def amount_to_precision(self, s, q):
        return q

    def price_to_precision(self, s, p):
        return p

    async def fetch_ticker(self, s):
        return {'last': self.last}

    async def fetch_open_orders(self, s):
        return []

    async def create_order(self, s, typ, side, amount, price, params):
        if 'stopLossPrice' in params:
            raise RuntimeError('bingx 110412 Stop Loss price should be greater than the current price')
        if 'takeProfitPrice' in params:
            return {'id': 'tp'}
        self.orders.append((typ, side, amount, params))
        self.pos -= amount
        return {'id': 'm'}


def make(ex, trade):
    obj = DemoExecutor.__new__(DemoExecutor)
    obj.enabled, obj.open, obj._lock, obj.db_path = True, {'c': trade}, asyncio.Lock(), ':memory:'

    async def _exchange():
        return ex

    async def _position_qty(sym):
        return ex.pos
    obj._exchange, obj._position_qty = _exchange, _position_qty
    return obj


def card(sl):
    return types.SimpleNamespace(symbol='COMP/USDT:USDT', group_key='TL', entered_at=1, created=1, levels={'sl': sl,
                                 'entry': 23.42}, plan={})


def test_restop_rejected_past_new_stop_closes_at_market(monkeypatch):
    rep = []
    monkeypatch.setattr(exm.errors, 'report', lambda *a: rep.append(a))
    ex = Ex(23.54, 80.0)                       # a short: BE stop 23.43 already below the price
    trade = {'symbol': 'COMP/USDT:USDT', 'direction': -1, 'scale': 1.0, 'sl': 23.97, 'id': 1}
    obj = make(ex, trade)
    obj.open = {'COMP/USDT:USDT|TL|1': trade}
    asyncio.run(obj.on_restop(card(23.43)))
    assert ex.orders == [('market', 'buy', 80.0, {'reduceOnly': True})] and not rep


def test_restop_rejected_otherwise_reported_old_stop_kept(monkeypatch):
    rep = []
    monkeypatch.setattr(exm.errors, 'report', lambda *a: rep.append(a))
    ex = Ex(23.30, 80.0)                       # price still below the new stop: not a stop hit
    trade = {'symbol': 'COMP/USDT:USDT', 'direction': -1, 'scale': 1.0, 'sl': 23.97, 'id': 1}
    obj = make(ex, trade)
    obj.open = {'COMP/USDT:USDT|TL|1': trade}
    asyncio.run(obj.on_restop(card(23.43)))
    assert ex.orders == [] and rep and rep[-1][0] == 'executor.on_restop' and trade['sl'] == 23.97


def test_partial_after_tp1_third_keeps_half_of_original():
    assert exm.CONFIG.executor.partial_share == 0.5
    ex = Ex(0.13, 20065.0)                     # APE: 30097 opened, the TP1 third (10032) already out
    trade = {'symbol': 'APE/USDT:USDT', 'direction': -1, 'qty': 30097.0, 'id': 1, 'tp1': 0.1, 'tp2': 0.09, 'tp3': 0.08}
    obj = make(ex, trade)
    obj.open = {'APE/USDT:USDT|TL|1': trade}

    async def _place_tps(*a, **k):
        return None
    obj._place_tps = _place_tps
    s = types.SimpleNamespace(symbol='APE/USDT:USDT', group_key='TL', entered_at=1, created=1, levels={}, plan={})
    asyncio.run(obj.on_partial(s))
    closed = sum(o[2] for o in ex.orders)
    assert abs(closed - (20065 - 30097 * 0.5)) < 1 and abs(ex.pos - 15048.5) < 1
