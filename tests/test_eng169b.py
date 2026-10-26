import asyncio

from executor import DemoExecutor


class Ex:
    def __init__(self, last):
        self.last, self.orders = last, []

    def price_to_precision(self, s, p):
        return p

    async def fetch_ticker(self, s):
        return {'last': self.last}

    async def create_order(self, s, typ, side, amount, price, params):
        if 'takeProfitPrice' in params:
            raise RuntimeError('110413 Take Profit price should be greater than the current price')
        self.orders.append((typ, side, amount, params))


def run(last):
    ex = Ex(last)
    obj = DemoExecutor.__new__(DemoExecutor)

    async def _exchange():
        return ex
    obj._exchange = _exchange
    asyncio.run(obj._place_tps({'symbol': 'ENA/USDT:USDT', 'direction': 1, 'tp1': 0.2076}, [(1, 100.0)]))
    return ex.orders


def test_target_already_passed_is_taken_at_market():
    assert run(0.2080) == [('market', 'sell', 100.0, {'reduceOnly': True})]


def test_rejected_target_not_reached_keeps_stop_only():
    assert run(0.2070) == []
