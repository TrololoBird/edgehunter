import asyncio
import io
import json
import os
import time
from collections import Counter, deque

import orjson
import polars as pl
import pytest

from conftest import CUR15, Frames, frame
from config import CONFIG
from fetcher import DataFetcher, MarketData, VenueDeriv
from indicators import calculate_tier0_metrics, compute_indicators, merge_live_candle
from symbols import VenueMarket

SAMPLES = json.load(open(os.path.join(os.path.dirname(__file__), 'fixtures', 'ws_samples.json'), encoding='utf-8'))
NOW = time.time()


def fetcher_with(symbols=('BTC/USDT:USDT', 'SOL/USDT:USDT', 'PROM/USDT:USDT')):
    f = DataFetcher()
    f.markets = {s: MarketData(symbol=s) for s in symbols}
    f.flow.register(symbols)
    f._binance_keys = {('futures', s.split('/')[0] + 'USDT'): s for s in symbols}
    return f


# ---------------------------------------------------------------------- MarketData / Tier-0 core

def test_new_listing_average_and_stale_5m_base():
    md = MarketData(symbol='NEW/USDT:USDT', listed_ms=int((NOW - 3 * 3600) * 1000))
    md.record_ticker({'last': 1.0, 'quoteVolume': 3e7})
    assert abs(md.avg_minute_usd / (3e7 / 180) - 1) < 0.01
    ticks = deque([(NOW * 1000 - 40_000, 1.0, 1e6), (NOW * 1000 - 1000, 1.1, 1e6)])
    assert calculate_tier0_metrics(ticks, deque(), deque(), NOW * 1000)['price_change_5m'] == 0.0   # 40s is not 5m
    ticks5 = deque([(NOW * 1000 - 300_000, 1.0, 1e6), (NOW * 1000 - 1000, 1.03, 1e6)])
    m = calculate_tier0_metrics(ticks5, deque(), deque(), NOW * 1000, ret_std=0.005 * 3 ** 0.5)
    assert m['price_change_5m'] == pytest.approx(0.03) and m['price_z'] == pytest.approx(6.0)


def test_spot_and_futures_minute_klines_are_separate():
    md = MarketData(symbol='X/USDT:USDT', spot_symbol='X/USDT')
    k = {'i': '1m', 't': 60_000, 'o': '1', 'h': '1', 'l': '1', 'c': '1', 'q': '10', 'Q': '7'}
    md.apply_kline('spot', k)
    md.apply_kline('futures', dict(k, q='20'))
    assert md.spot_minute_klines[-1][5] == 10 and md.minute_klines[-1][5] == 20
    assert md.closed_until == 0


def test_backfill_snapshot_patched_with_stream_rows():
    up = [100 + 0.1 * i for i in range(10)]
    fr = frame(up)
    md = MarketData(symbol='Q/USDT:USDT', futures_df=fr)
    final_row = dict(fr.row(-1, named=True))
    final_row['close'] = 999.0
    md.recent_closed['futures'].append(final_row)
    snap = fr
    for r_ in list(md.recent_closed['futures']):
        snap, _ = merge_live_candle(snap, dict(r_), 0)
    assert snap['close'][-1] == 999.0 and snap.height == 10


# ---------------------------------------------------------------------- fetcher sinks

def test_binance_sinks_from_fixtures():
    f = fetcher_with()
    for key in ('binance_fut_market:aggTrade', 'binance_fut_market:forceOrder',
                'binance_fut_public:depth20@500ms', 'binance_fut_market:kline_1m'):
        for raw in SAMPLES[key]:
            payload = orjson.loads(raw)
            if 'data' in payload:
                f.on_binance('futures', payload['stream'], payload['data'], NOW * 1000)
    btc = f.markets['BTC/USDT:USDT']
    assert btc.ticker_samples and btc.minute_klines       # price samples come from the aggTrades now
    assert f.depth.metrics('BTC/USDT:USDT', now=f.depth.books['BTC/USDT:USDT'].ts_ms / 1000)['bid_usd_0_5'] > 0
    f.sweeps.flush(10 ** 15)
    assert f.flow.venues['binance'].messages >= 3
    liq = f.flow.window(('binance',), 2, 3600, 1790422647 + 60)  # LIQ_LONG at the time the fixture was recorded
    assert liq[f.flow.rows['PROM/USDT:USDT']] > 0            # PROM forced SELL = a long liquidated


def test_other_venue_trade_checks_price_and_counts_usd():
    f = fetcher_with()
    f.markets['BTC/USDT:USDT'].record_ticker({'last': 84000.0, 'quoteVolume': 1e9})
    good = VenueMarket('okx', 'BTC-USDT-SWAP', 'BTC/USDT:USDT', 'BTC', 1.0, contract_value=0.01)
    f.symbol_map._put(good)
    f.on_trade(good, int(NOW * 1000), 84010.0, 100, 1, NOW * 1000)     # 100 contracts x 0.01 BTC
    assert f.flow.symbol_net(('okx',), 'BTC/USDT:USDT', 60, int(NOW)) == pytest.approx(84010.0)
    bad = VenueMarket('bitget', 'BTCUSDT', 'BTC/USDT:USDT', 'BTC', 1.0)
    f.symbol_map._put(bad)
    f.on_trade(bad, int(NOW * 1000), 42000.0, 1, 1, NOW * 1000)       # other token under the same ticker
    assert f.flow.symbol_net(('bitget',), 'BTC/USDT:USDT', 60, int(NOW)) == 0
    assert f.symbol_map.lookup('bitget', 'BTCUSDT') is None


def test_aggregated_oi_change_weighted_by_usd():
    f = fetcher_with()
    key = 'BTC/USDT:USDT'
    now = NOW * 1000
    for venue, start, end in (('binance', 1000.0, 1010.0), ('bybit', 3000.0, 3000.0)):
        st = f.venue_derivs.setdefault(key, {}).setdefault(venue, VenueDeriv())
        st.samples.extend([(now - 310_000, start), (now - 1000, end)])
        st.oi_usd, st.ts, st.funding_8h = end, now, 0.0001 if venue == 'binance' else 0.0003
    snap = f.deriv_snapshot(key, now)
    assert snap['agg_oi_change_5m'] == pytest.approx((0.01 * 1010) / (1010 + 3000))
    assert snap['agg_funding_8h'] == pytest.approx((0.0001 * 1010 + 0.0003 * 3000) / 4010)
    assert snap['oi_venues'] == 2


def test_orderflow_confirm_absorption():
    f = fetcher_with()
    md = f.markets['BTC/USDT:USDT']
    t0 = CUR15 - 60 * 60_000
    for i in range(60):
        md.minute_klines.append([t0 + i * 60_000, 100, 100.5, 99.5, 100, 1e4, 5e3 + (i % 5) * 100])
    # heavy selling (delta -2e4) that barely moved price: absorbed -> confirms a LONG
    md.minute_klines.append([CUR15, 100, 100.05, 99.97, 100.02, 3e4, 5e3])
    f._zone_atr['BTC/USDT:USDT'] = 1.0
    assert f.orderflow_confirm('BTC/USDT:USDT', CUR15, CUR15 + 60_000, +1) == 'absorption'
    assert f.orderflow_confirm('BTC/USDT:USDT', CUR15, CUR15 + 60_000, -1) is None


# ---------------------------------------------------------------------- scanner

def scanner_with(markets):
    from scanner import Scanner
    sc = Scanner()
    sc.fetcher.markets = markets
    sc.market_data = markets
    sc.fetcher.flow.register(markets)
    return sc


def test_price_freshness():
    m = MarketData(symbol='P/USDT:USDT')
    m.ticker_samples.append((NOW * 1000 - 120_000, 5.0, 1e6))
    sc = scanner_with({'P/USDT:USDT': m})
    assert sc._price_of('P/USDT:USDT') is None
    m.minute_klines.append([int(NOW * 1000 // 60_000 * 60_000), 5, 5.2, 4.9, 5.1, 1e4, 5e3])
    assert sc._price_of('P/USDT:USDT') == 5.1


def test_hot_symbols_priority_and_min_age():
    markets = {s: MarketData(symbol=s) for s in ('A', 'B', 'C', 'D')}
    sc = scanner_with(markets)
    subscribed = []

    async def set_hot(symbols):
        subscribed.append(list(symbols))
    sc.fetcher.set_hot = set_hot
    markets['A'].is_tier_0_anomaly = True
    asyncio.run(sc._update_hot())
    assert subscribed[-1] == ['A']
    markets['A'].is_tier_0_anomaly = False
    asyncio.run(sc._update_hot())
    assert sc._hot == ['A']        # kept: wanted within tier2_hold_sec


def test_frame_lookup_appends_live_candle():
    ind = compute_indicators(frame([100 + 0.1 * i for i in range(40)]))
    md = MarketData(symbol='_')
    md.minute_klines.append([CUR15 + 900_000, 104, 130, 103, 129, 1e4, 5e3])   # the live 15m candle comes from 1m
    from scanner import _FrameLookup
    part = _FrameLookup({'_': ind}, {'_': md}).get('_')
    assert part['high'][-1] == 130 and part['atr'][-1] == ind['atr'][-1]


def test_tier0_metrics_combine_venues():
    md = MarketData(symbol='BTC/USDT:USDT', spot_symbol='BTC/USDT')
    now_ms = NOW * 1000
    md.ticker_samples.extend([(now_ms - 300_000, 100.0, 1.44e9), (now_ms - 500, 103.0, 1.44e9)])
    md.avg_minute_usd = 1e6
    md.spot_minute_klines.append([int(now_ms // 60_000 * 60_000), 1, 1, 1, 1, 1e5, 8e4])
    sc = scanner_with({'BTC/USDT:USDT': md})
    f = sc.fetcher
    f.flow.trade('binance', 'BTC/USDT:USDT', now_ms - 1000, 5e5, 1)
    f.flow.trade('bybit', 'BTC/USDT:USDT', now_ms - 1000, 3e5, 1)
    f.flow.liquidation('okx', 'BTC/USDT:USDT', now_ms - 1000, 7e4, -1)
    m = sc._tier0_metrics(now_ms)['BTC/USDT:USDT']
    assert m['futures_cvd_5m'] == pytest.approx(5e5) and m['agg_cvd_5m'] == pytest.approx(8e5)
    assert m['liq_short_5m'] == pytest.approx(7e4) and m['venues_active'] == 2
    assert m['spot_cvd_5m'] == pytest.approx(6e4) and m['price_change_5m'] == pytest.approx(0.03)


def test_state_save_and_restore(tmp_path, monkeypatch):
    import dataclasses
    import config as config_mod
    monkeypatch.setattr(config_mod.CONFIG, 'journal',
                        dataclasses.replace(config_mod.CONFIG.journal, state_path=str(tmp_path / 'state.json')))
    sc = scanner_with({})
    from flow import Sweep
    sc.fetcher.whales.add(Sweep('binance', 'A', 1, 1, 1, 9e4, 1, 1, 1, 1))
    sc.book.session_results['TP2'] += 1
    sc._save_state()
    sc2 = scanner_with({})
    sc2._load_state()
    assert sc2.fetcher.whales.hist['A'].sum() == 1 and sc2.book.session_results['TP2'] == 1
