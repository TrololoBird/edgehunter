"""Parsing of real WebSocket messages (tests/fixtures/ws_samples.json, recorded from each venue) into sink events."""
import json
import os

import orjson
import pytest

from symbols import SymbolMap, split_base
from venues import (BinanceStream, BitgetStream, BybitStream, CoinbaseStream, HyperliquidStream, OkxStream, _iso_ms,
                    venue_market_rows)

SAMPLES = json.load(open(os.path.join(os.path.dirname(__file__), 'fixtures', 'ws_samples.json'), encoding='utf-8'))


class Sink:
    def __init__(self):
        self.trades, self.liqs, self.derivs, self.binance = [], [], [], []

    def on_trade(self, market, ts, price, size, side, recv):
        self.trades.append((market.venue, market.key, ts, price, size, side))

    def on_liquidation(self, market, ts, price, size, side_liq, recv):
        self.liqs.append((market.venue, market.key, price, size, side_liq))

    def on_deriv(self, market, oi_usd=None, funding_8h=None, mark=None, ts_ms=None):
        self.derivs.append((market.venue, market.key, oi_usd, funding_8h, mark))

    def on_binance(self, market_type, stream, data, recv):
        self.binance.append((market_type, stream, data))


def smap():
    m = SymbolMap()
    m.set_universe({'BTC/USDT:USDT': {'base': 'BTC'}, 'ETH/USDT:USDT': {'base': 'ETH'},
                    '1000PEPE/USDT:USDT': {'base': '1000PEPE'}, 'BASED/USDT:USDT': {'base': 'BASED'},
                    'PROM/USDT:USDT': {'base': 'PROM'}})
    m.add_venue('bybit', [{'native': 'BTCUSDT', 'base': 'BTC'}, {'native': 'ETHUSDT', 'base': 'ETH'}])
    m.add_venue('okx', [{'native': 'BTC-USDT-SWAP', 'base': 'BTC', 'contract_value': 0.01},
                        {'native': 'BASED-USDT-SWAP', 'base': 'BASED', 'contract_value': 1.0}])
    m.add_venue('hyperliquid', [{'native': 'BTC', 'base': 'BTC'}, {'native': 'kPEPE', 'base': 'kPEPE'}])
    m.add_venue('bitget', [{'native': 'BTCUSDT', 'base': 'BTC'}])
    m.add_venue('coinbase', [{'native': 'BTC-USD', 'base': 'BTC'}, {'native': 'ETH-USD', 'base': 'ETH'}], spot=True)
    return m


def feed(stream_cls, prefix, **kwargs):
    sink = Sink()
    stream = stream_cls(sink, smap(), **kwargs)
    for key, messages in SAMPLES.items():
        if key.startswith(prefix):
            for raw in messages:
                if raw in ('pong', 'ping'):
                    continue  # VenueStream._read drops these before handle()
                stream.handle(orjson.loads(raw), 0.0)
    return sink


def test_split_base():
    assert split_base('1000PEPE') == ('PEPE', 1000.0)
    assert split_base('kPEPE', 'hyperliquid') == ('PEPE', 1000.0)
    assert split_base('KAVA', 'hyperliquid') == ('KAVA', 1.0)
    assert split_base('1MBABYDOGE') == ('BABYDOGE', 1e6)
    assert split_base('BTC') == ('BTC', 1.0)


def test_symbol_map_multiplier_and_price_check():
    m = smap()
    pepe = m.lookup('hyperliquid', 'kPEPE')
    assert pepe.key == '1000PEPE/USDT:USDT' and pepe.multiplier == 1000
    assert m.check_price(pepe, 0.0101, 0.0100)                  # both per-1000 units: same price
    btc = m.lookup('okx', 'BTC-USDT-SWAP')
    assert not m.check_price(btc, 50_000.0, 84_000.0)          # a different token under one ticker: dropped
    assert m.lookup('okx', 'BTC-USDT-SWAP') is None
    assert m.usd(m.lookup('okx', 'BASED-USDT-SWAP'), 2.0, 10) == 20.0


def test_venue_market_rows():
    markets = {'X': {'id': 'PEPE-USDT-SWAP', 'base': 'PEPE', 'swap': True, 'settle': 'USDT', 'contractSize': 1e7,
                     'active': True, 'info': {}}}
    assert venue_market_rows('okx', markets) == [{'native': 'PEPE-USDT-SWAP', 'base': 'PEPE', 'contract_value': 1e7}]
    hl = {'Y': {'id': '15', 'base': 'KPEPE', 'swap': True, 'active': True, 'info': {'name': 'kPEPE'}},
          'Z': {'id': '9', 'base': 'X', 'swap': True, 'active': True, 'info': {'name': 'hyna:1000PEPE'}}}
    assert venue_market_rows('hyperliquid', hl) == [{'native': 'kPEPE', 'base': 'kPEPE', 'contract_value': 1.0}]


def test_bybit_trades_tickers():
    sink = feed(BybitStream, 'bybit')
    assert sink.trades and all(t[0] == 'bybit' and t[1] == 'BTC/USDT:USDT' and t[5] in (1, -1) for t in sink.trades)
    venue, key, oi_usd, funding, mark = sink.derivs[0]
    assert oi_usd == pytest.approx(2411025444.07) and mark == pytest.approx(84141.89)   # one-sided OI value
    assert funding == pytest.approx(-0.00002199)                                        # 8h interval: unchanged
    # deltas without OI keep the merged state
    assert all(d[2] for d in sink.derivs)


def test_bybit_liquidation_side():
    sink = Sink()
    stream = BybitStream(sink, smap())
    stream.handle({'topic': 'allLiquidation.BTCUSDT', 'data': [{'T': 1, 's': 'BTCUSDT', 'S': 'Buy', 'v': '0.5', 'p': '80000'}]}, 0)
    assert sink.liqs == [('bybit', 'BTC/USDT:USDT', 80000.0, 0.5, 1)]


def test_okx_trades_oi_funding_liquidations():
    sink = feed(OkxStream, 'okx')
    assert sink.trades and sink.trades[0][1] == 'BTC/USDT:USDT'
    ois = [d for d in sink.derivs if d[2]]
    assert ois and ois[0][2] == pytest.approx(2388769938.8, rel=1e-6)
    fundings = [d for d in sink.derivs if d[3] is not None]
    assert fundings and fundings[0][3] == pytest.approx(0.0000117717850566)   # 8h between fundingTime / next
    assert sink.liqs == [('okx', 'BASED/USDT:USDT', 0.07107, 119.0, -1)]       # posSide short -> short liquidated


def test_hyperliquid_ctx_and_trades():
    sink = feed(HyperliquidStream, 'hyperliquid')
    btc = [d for d in sink.derivs if d[1] == 'BTC/USDT:USDT'][0]
    assert btc[2] == pytest.approx(37763.71524 * 84150.3) and btc[3] == pytest.approx(0.0000125 * 8)
    sides = {t[5] for t in sink.trades}
    assert sides <= {1, -1} and sink.trades[0][5] == -1                         # 'A' = taker sold


def test_bitget_skips_trade_snapshot():
    sink = feed(BitgetStream, 'bitget')
    snapshot_trades = sum(len(orjson.loads(r)['data']) for r in SAMPLES['bitget:trade:snapshot'])
    update_trades = sum(len(orjson.loads(r)['data']) for r in SAMPLES['bitget:trade:update'])
    assert len(sink.trades) == update_trades and snapshot_trades
    assert sink.derivs[0][2] == pytest.approx(31839.8542 * 84145, rel=1e-6)


def test_coinbase_maker_side_inverted():
    sink = feed(CoinbaseStream, 'coinbase')
    upd = orjson.loads(SAMPLES['coinbase:market_trades:update'][0])['events'][0]['trades'][0]
    first = sink.trades[0]
    assert first[1] == 'BTC/USDT:USDT' and first[5] == (1 if upd['side'] == 'SELL' else -1)
    assert _iso_ms('2026-09-26T11:36:31.632752123Z') == _iso_ms('2026-09-26T11:36:31.632752Z')


def test_binance_payloads_reach_sink():
    sink = Sink()
    stream = BinanceStream(sink, smap(), 'futures', [], 'test')
    for key in ('binance_fut_market:aggTrade', 'binance_fut_market:forceOrder', 'binance_fut_market:arr@1s'):
        for raw in SAMPLES[key]:
            stream.handle(orjson.loads(raw), 0.0)
    kinds = {s.split('@')[-1] for _, s, _ in sink.binance}
    assert 'aggTrade' in kinds and 'forceOrder' in kinds and '1s' in kinds
