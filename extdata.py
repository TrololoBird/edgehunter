"""
Public data beyond the streams (verified live 2026-09-30), all REST, light on bandwidth; context for the journal /
stats / P(edge), never a trigger until the journal proves one:

- Deribit (no other source has options): the DVOL implied-volatility index of BTC / ETH (hourly candles) and the
  put / call open-interest ratio of each one's options (get_book_summary_by_currency) -> market_state
  `dvol_btc`, `dvol_chg_1h`, `pc_oi_btc`; a DVOL jump is logged as a market anomaly.
- Hyperliquid `predictedFundings`: the NEXT funding of Binance, Bybit and Hyperliquid for every coin in one call ->
  per coin `funding_spread` (max - min of the venues' 8h-equivalent rates): crowding on one venue.
- OKX `rubik/stat/taker-volume` (5m taker buy / sell of each coin's contracts): the OKX flow windows are seeded at
  start-up for the minutes before the streams (Binance's are seeded from its 1m klines).
- Order books of OKX (`market/books`, 50 levels) and Bybit (`market/orderbook`, 50) for the hot coins every 60s ->
  per coin `okx_book_imb` / `bybit_book_imb`: (bid - ask) / (bid + ask) within 0.5% of the mid (Binance has its own).
"""
import asyncio
import json
import logging
import errors
import time
from typing import Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)

DERIBIT = 'https://www.deribit.com/api/v2/public'
HL = 'https://api.hyperliquid.xyz/info'
OKX = 'https://www.okx.com/api/v5'
BYBIT = 'https://api.bybit.com/v5'


class ExternalData:
    def __init__(self, fetcher):
        self.fetcher = fetcher
        self.market: Dict[str, Optional[float]] = {'dvol_btc': None, 'dvol_chg_1h': None, 'pc_oi_btc': None}
        self.coin: Dict[str, Dict[str, float]] = {}
        self._session: Optional[aiohttp.ClientSession] = None

    async def _json(self, url: str, payload=None):
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        if payload is None:
            async with self._session.get(url) as r:
                return await r.json(content_type=None)
        async with self._session.post(url, data=json.dumps(payload), headers={'Content-Type': 'application/json'}) as r:
            return await r.json(content_type=None)

    async def close(self):
        if self._session is not None:
            await self._session.close()

    def of(self, symbol: str) -> Dict[str, float]:
        return self.coin.get(symbol, {})

    # ------------------------------------------------------------------ Deribit
    async def deribit_loop(self, running):
        while running():
            try:
                now = int(time.time() * 1000)
                d = await self._json(f"{DERIBIT}/get_volatility_index_data?currency=BTC&start_timestamp="
                                     f"{now - 4 * 3_600_000}&end_timestamp={now}&resolution=3600")
                rows = (d.get('result') or {}).get('data') or []
                if len(rows) >= 2:
                    last, prev = rows[-1][4], rows[-2][4]
                    self.market['dvol_btc'] = float(last)
                    self.market['dvol_chg_1h'] = float(last) - float(prev)
                    if abs(last - prev) >= 3:
                        logger.warning(f"Market anomaly: BTC DVOL {prev:.1f} -> {last:.1f} in 1h")
                b = await self._json(f"{DERIBIT}/get_book_summary_by_currency?currency=BTC&kind=option")
                puts = calls = 0.0
                for o in b.get('result') or []:
                    name, oi = o.get('instrument_name', ''), float(o.get('open_interest') or 0)
                    if name.endswith('-P'):
                        puts += oi
                    elif name.endswith('-C'):
                        calls += oi
                self.market['pc_oi_btc'] = puts / calls if calls else None
            except Exception as e:
                errors.report('extdata.deribit_loop', e, "Deribit")
            await asyncio.sleep(300)

    # ------------------------------------------------------------------ Hyperliquid predicted fundings
    def _key_of_coin(self, coin: str) -> Optional[str]:
        sm = self.fetcher.symbol_map
        m = sm.lookup('hyperliquid', coin)
        if m is not None:
            return m.key
        for key in (f"{coin}/USDT:USDT", f"1000{coin}/USDT:USDT"):
            if key in self.fetcher.markets:
                return key
        return None

    async def funding_loop(self, running):
        while running():
            try:
                rows = await self._json(HL, {'type': 'predictedFundings'})
                for coin, venues in rows or []:
                    key = self._key_of_coin(coin)
                    if key is None:
                        continue
                    rates = []
                    for _, v in venues:
                        if not v:
                            continue
                        hours = float(v.get('fundingIntervalHours') or 8) or 8
                        rates.append(float(v['fundingRate']) * 8 / hours)
                    if len(rates) >= 2:
                        self.coin.setdefault(key, {})['funding_spread'] = max(rates) - min(rates)
            except Exception as e:
                errors.report('extdata.funding_loop', e, "predictedFundings")
            await asyncio.sleep(300)

    # ------------------------------------------------------------------ OKX flow seed
    async def seed_okx_flow(self):
        """Once, after the streams started: 5m OKX taker volume of the 15 minutes before them into the flow windows."""
        started = self.fetcher.streams_started_ms
        if not started:
            return
        coins = {}
        for key in list(self.fetcher.markets):
            for m in self.fetcher.symbol_map.by_key.get(key, {}).values():
                if m.venue == 'okx':
                    coins[m.coin] = key
        seeded = 0
        for coin, key in coins.items():
            try:
                d = await self._json(f"{OKX}/rubik/stat/taker-volume?ccy={coin}&instType=CONTRACTS&period=5m")
                for ts, sell, buy in (d.get('data') or [])[:4]:
                    t = int(ts)
                    if started - 15 * 60_000 <= t and t + 300_000 <= started:
                        for k in range(5):      # the 5m bucket spread over its minutes
                            self.fetcher.flow.seed_minute('okx', key, t + k * 60_000, float(buy) / 5, float(sell) / 5, 0)
                        seeded += 1
            except Exception as e:
                errors.report('extdata.seed_okx_flow', e, f"OKX taker volume {coin}")
            await asyncio.sleep(0.45)           # rubik: 5 requests / 2s
        logger.info(f"OKX flow seeded: {seeded} 5m buckets for {len(coins)} coins")

    # ------------------------------------------------------------------ cross-venue books
    @staticmethod
    def _imbalance(bids, asks) -> Optional[float]:
        if not bids or not asks:
            return None
        mid = (float(bids[0][0]) + float(asks[0][0])) / 2
        bid = sum(float(p) * float(q) for p, q, *_ in bids if float(p) >= mid * 0.995)
        ask = sum(float(p) * float(q) for p, q, *_ in asks if float(p) <= mid * 1.005)
        return (bid - ask) / (bid + ask) if bid + ask else None

    async def books_loop(self, running):
        while running():
            started = time.time()
            for key in self.fetcher.depth.active():
                venues = self.fetcher.symbol_map.by_key.get(key, {})
                try:
                    okx = next((m for m in venues.values() if m.venue == 'okx'), None)
                    if okx is not None:
                        d = await self._json(f"{OKX}/market/books?instId={okx.native}&sz=50")
                        book = (d.get('data') or [{}])[0]
                        self.coin.setdefault(key, {})['okx_book_imb'] = self._imbalance(book.get('bids'), book.get('asks'))
                    byb = next((m for m in venues.values() if m.venue == 'bybit'), None)
                    if byb is not None:
                        d = await self._json(f"{BYBIT}/market/orderbook?category=linear&symbol={byb.native}&limit=50")
                        r = d.get('result') or {}
                        self.coin.setdefault(key, {})['bybit_book_imb'] = self._imbalance(r.get('b'), r.get('a'))
                except Exception as e:
                    errors.report('extdata.books_loop', e, f"books {key}")
                await asyncio.sleep(0.3)
            await asyncio.sleep(max(5.0, 60 - (time.time() - started)))
