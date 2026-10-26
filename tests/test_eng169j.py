import asyncio

import executor as exmod


class FakeEx:
    def __init__(self, orders, fail_first=True):
        self.orders, self.fail_first, self.created, self.cancelled = orders, fail_first, [], []

    def price_to_precision(self, symbol, p):
        return p

    async def create_order(self, symbol, *a):
        if self.fail_first:
            self.fail_first = False
            raise Exception('bingx {"code":110206,"msg":"The number of your TP/SL orders has exceeded the limit."}')
        self.created.append((symbol, a))
        return {'id': 'new'}

    async def fetch_open_orders(self, symbol=None):
        return self.orders

    async def cancel_order(self, oid, symbol):
        self.cancelled.append((oid, symbol))


def _tp(oid, sym, side, px):
    return {'id': oid, 'symbol': sym, 'side': side, 'triggerPrice': px, 'info': {'type': 'TAKE_PROFIT_MARKET'}}


def _run(orders, fail_first=True):
    e = exmod.DemoExecutor.__new__(exmod.DemoExecutor)
    fake = FakeEx(orders, fail_first)

    async def _exchange():
        return fake
    e._exchange = _exchange
    return e, fake


def test_stop_limit_frees_farthest_tp3_and_retries():
    orders = [_tp('a1', 'A', 'sell', 11), _tp('a2', 'A', 'sell', 12), _tp('a3', 'A', 'sell', 13),
              _tp('b1', 'B', 'buy', 9), _tp('b2', 'B', 'buy', 8)]
    e, fake = _run(orders)
    asyncio.run(e._place_stop('NEW', 1, 1.0, 95.0))
    assert fake.cancelled == [('a3', 'A')] and fake.created


def test_short_trade_far_tp_is_the_lowest():
    orders = [_tp('c1', 'C', 'buy', 9), _tp('c2', 'C', 'buy', 8), _tp('c3', 'C', 'buy', 7)]
    e, fake = _run(orders)
    asyncio.run(e._place_stop('NEW', -1, 1.0, 105.0))
    assert fake.cancelled == [('c3', 'C')]


def test_no_trade_with_three_tps_keeps_the_error():
    e, fake = _run([_tp('b1', 'B', 'buy', 9), _tp('b2', 'B', 'buy', 8)])
    try:
        asyncio.run(e._place_stop('NEW', 1, 1.0, 95.0))
        raised = False
    except Exception:
        raised = True
    assert raised and not fake.cancelled
