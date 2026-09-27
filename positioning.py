"""
Positioning of other traders, from public data, for coins with open cards (context and level map, never a trigger):

- Long / short ratios: Binance global accounts, top-trader accounts and top-trader positions (/futures/data, own
  limit 1000 requests / 5 min shared with openInterestHist), Bybit account ratio, OKX account ratio (5m periods).
- Hyperliquid large accounts: the chain is public, so the real positions of big traders are known, with their
  liquidation prices. Accounts = the leaderboard's most active traders by monthly volume (the file is ~40 MB, so it is
  downloaded every `hl_accounts_refresh_sec` and cached in hl_accounts.json); positions of each account every
  `hl_positions_refresh_sec`. Their liquidation prices become 'liq_hl' levels (zones.py): real, not estimated.
- OKX liquidations (REST, the last 100 per contract): refill the observed-liquidation lists after a restart.
"""
import asyncio
import json
import logging
import time
from typing import Dict, Iterable, List, Optional, Tuple

import aiohttp
import orjson

from config import CONFIG
from storage import atomic_write
from zones import RawLevel

logger = logging.getLogger(__name__)

HL_INFO_URL = 'https://api.hyperliquid.xyz/info'
HL_LEADERBOARD_URL = 'https://stats-data.hyperliquid.xyz/Mainnet/leaderboard'
BYBIT_RATIO_URL = 'https://api.bybit.com/v5/market/account-ratio'
OKX_RATIO_URL = 'https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio-contract'
OKX_LIQ_URL = 'https://www.okx.com/api/v5/public/liquidation-orders'
HEADERS = {'User-Agent': 'Mozilla/5.0 (microstructure scanner)'}


class Positioning:
    def __init__(self, fetcher):
        self.fetcher = fetcher
        # symbol -> {'binance_global', 'binance_top_acc', 'binance_top_pos', 'bybit', 'okx': long/short ratio}, ts
        self.ratios: Dict[str, Dict[str, float]] = {}
        self._ratio_ts: Dict[str, float] = {}
        self._calls: List[float] = []
        # Hyperliquid: tracked accounts and, per canonical key, their positions
        # (side +1 long / -1 short, notional USD, liquidation price in Binance units or None, leverage)
        self.hl_accounts: List[str] = []
        self.hl_accounts_ts = 0.0
        self.hl_positions: Dict[str, List[Tuple[int, float, Optional[float], float]]] = {}
        self.hl_ts = 0.0
        self._okx_lock = asyncio.Lock()
        self._session: Optional[aiohttp.ClientSession] = None

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> List[asyncio.Task]:
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), headers=HEADERS)
        self._load_accounts()
        return [asyncio.create_task(self._hl_loop()), asyncio.create_task(self._okx_liquidations_backfill())]

    async def close(self):
        if self._session is not None:
            await self._session.close()

    async def _get(self, url: str, **params):
        async with self._session.get(url, params=params) as resp:
            return await resp.json(content_type=None)

    # ------------------------------------------------------------------ long / short ratios

    def ratio_age(self, symbol: str) -> float:
        return time.time() - self._ratio_ts.get(symbol, 0.0)

    async def refresh_ratios(self, symbols: Iterable[str]):
        """
        Ratios of the given (due) symbols in order, concurrently, as many as the /futures/data budget allows this
        5 minutes (3 Binance calls per coin); the rest stay due for the next pass. A coin keeps its previous ratios
        until new ones arrive.
        """
        cfg = CONFIG.rest
        now = time.time()
        self._calls = [t for t in self._calls if now - t < 300]
        batch = []
        for symbol in symbols:
            if len(self._calls) + 3 > cfg.positioning_budget_per_5m:
                break
            if not self.fetcher._ccxt_to_binance_symbol(symbol):
                continue
            self._calls += [now] * 3
            self._ratio_ts[symbol] = now
            batch.append(symbol)
        sem = asyncio.Semaphore(6)

        async def one(symbol: str):
            async with sem:
                out = await self._ratios_of(symbol)
            if out:
                self.ratios[symbol] = {**self.ratios.get(symbol, {}), **out}

        await asyncio.gather(*(one(s) for s in batch))

    async def _ratios_of(self, symbol: str) -> Dict[str, float]:
        f = self.fetcher
        out: Dict[str, float] = {}
        params = {'symbol': f._ccxt_to_binance_symbol(symbol), 'period': '5m', 'limit': 1}
        for name, method, field in (('binance_global', 'fapiDataGetGlobalLongShortAccountRatio', 'longShortRatio'),
                                    ('binance_top_acc', 'fapiDataGetTopLongShortAccountRatio', 'longShortRatio'),
                                    ('binance_top_pos', 'fapiDataGetTopLongShortPositionRatio', 'longShortRatio')):
            try:
                rows = await f._rest_call(f.futures_exchange, method, dict(params), priority=2, weight=0)
                if rows and float(rows[-1].get(field) or 0.0):
                    out[name] = float(rows[-1][field])
            except Exception as e:
                logger.debug(f"{name} ratio failed for {symbol}: {e}")
        mapping = f.symbol_map.by_key.get(symbol, {})
        if 'bybit' in mapping:
            try:
                r = await self._get(BYBIT_RATIO_URL, category='linear', symbol=mapping['bybit'].native, period='5min', limit=1)
                row = ((r.get('result') or {}).get('list') or [{}])[0]
                buy, sell = float(row.get('buyRatio') or 0), float(row.get('sellRatio') or 0)
                if buy and sell:
                    out['bybit'] = buy / sell
            except Exception as e:
                logger.debug(f"bybit ratio failed for {symbol}: {e}")
        if 'okx' in mapping:
            # OKX allows 5 requests / 2s on this endpoint: one at a time, spaced
            async with self._okx_lock:
                try:
                    r = await self._get(OKX_RATIO_URL, instId=mapping['okx'].native, period='5m', limit=1)
                    rows = r.get('data') or []
                    if rows:
                        out['okx'] = float(rows[0][1])
                except Exception as e:
                    logger.debug(f"okx ratio failed for {symbol}: {e}")
                await asyncio.sleep(0.45)
        return out

    # ------------------------------------------------------------------ Hyperliquid large accounts

    def _accounts_path(self) -> str:
        return CONFIG.positioning.hl_accounts_path

    def _load_accounts(self):
        try:
            with open(self._accounts_path(), encoding='utf-8') as fh:
                data = json.load(fh)
            if time.time() - data.get('ts', 0) < 24 * 3600:
                self.hl_accounts, self.hl_accounts_ts = data['accounts'], data['ts']
        except (OSError, ValueError, KeyError):
            pass

    @staticmethod
    def _pick_accounts(raw: bytes) -> List[str]:
        """The most active traders: top by monthly volume among accounts with enough equity (vaults trade little)."""
        cfg = CONFIG.positioning
        rows = orjson.loads(raw).get('leaderboardRows', [])
        picked = []
        for row in rows:
            try:
                value = float(row.get('accountValue') or 0)
                month = next((w[1] for w in row.get('windowPerformances', []) if w[0] == 'month'), {})
                volume = float(month.get('vlm') or 0)
            except (TypeError, ValueError):
                continue
            if value >= cfg.hl_min_account_usd and volume > 0:
                picked.append((volume, row['ethAddress']))
        picked.sort(reverse=True)
        return [address for _, address in picked[:cfg.hl_accounts]]

    async def _refresh_accounts(self):
        # ~40 MB: read at a capped rate, or it saturates the link and every stream lags (measured: 38s behind)
        rate = CONFIG.positioning.hl_download_bytes_per_sec
        chunks: List[bytes] = []
        async with self._session.get(HL_LEADERBOARD_URL, timeout=aiohttp.ClientTimeout(total=900)) as resp:
            async for chunk in resp.content.iter_chunked(64 * 1024):
                chunks.append(chunk)
                await asyncio.sleep(len(chunk) / rate)
        raw = b''.join(chunks)
        accounts = await asyncio.to_thread(self._pick_accounts, raw)
        if accounts:
            self.hl_accounts, self.hl_accounts_ts = accounts, time.time()
            atomic_write(self._accounts_path(), json.dumps({'ts': self.hl_accounts_ts, 'accounts': accounts}).encode())
            logger.info(f"Hyperliquid: tracking {len(accounts)} most active large accounts ({len(raw) / 1e6:.0f} MB leaderboard)")

    async def _account_positions(self, address: str) -> List[dict]:
        async with self._session.post(HL_INFO_URL, json={'type': 'clearinghouseState', 'user': address}) as resp:
            data = await resp.json(content_type=None)
        return [p.get('position') or {} for p in (data or {}).get('assetPositions', [])]

    async def _refresh_positions(self):
        f = self.fetcher
        positions: Dict[str, List[Tuple[int, float, Optional[float], float]]] = {}
        spacing = 60.0 / CONFIG.positioning.hl_requests_per_min
        for address in list(self.hl_accounts):
            try:
                rows = await self._account_positions(address)
            except Exception as e:
                logger.debug(f"Hyperliquid positions failed for {address[:10]}: {e}")
                rows = []
            for p in rows:
                market = f.symbol_map.lookup('hyperliquid', p.get('coin', ''))
                size = float(p.get('szi') or 0)
                if market is None or not size:
                    continue
                to_binance = f.symbol_map.key_multiplier.get(market.key, 1.0) / market.multiplier
                liq = float(p['liquidationPx']) * to_binance if p.get('liquidationPx') else None
                leverage = float((p.get('leverage') or {}).get('value') or 0)
                positions.setdefault(market.key, []).append(
                    (1 if size > 0 else -1, float(p.get('positionValue') or 0), liq, leverage))
            await asyncio.sleep(spacing)
        self.hl_positions, self.hl_ts = positions, time.time()

    async def _hl_loop(self):
        cfg = CONFIG.positioning
        while True:
            try:
                if time.time() - self.hl_accounts_ts >= cfg.hl_accounts_refresh_sec:
                    await self._refresh_accounts()
                started = time.time()
                if self.hl_accounts:
                    await self._refresh_positions()
                await asyncio.sleep(max(10.0, cfg.hl_positions_refresh_sec - (time.time() - started)))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.info(f"Hyperliquid positions unavailable ({type(e).__name__} {e}); retry in 5 min")
                await asyncio.sleep(300)

    def hl_summary(self, symbol: str) -> Dict[str, float]:
        rows = self.hl_positions.get(symbol, [])
        longs = [usd for side, usd, _, _ in rows if side > 0]
        shorts = [usd for side, usd, _, _ in rows if side < 0]
        return {'hl_long_usd': sum(longs), 'hl_short_usd': sum(shorts), 'hl_longs': len(longs), 'hl_shorts': len(shorts)}

    def hl_levels(self, symbol: str, price: Optional[float]) -> List[RawLevel]:
        """Liquidation prices of the tracked accounts, summed per price bucket: the 'liq_hl' levels of the map."""
        rows = [r for r in self.hl_positions.get(symbol, []) if r[2]]
        if not rows or not price:
            return []
        step = price * CONFIG.zones.liq_bucket
        buckets: Dict[Tuple[int, int], List[float]] = {}
        for side, usd, liq, _ in rows:
            buckets.setdefault((int(liq / step), side), []).append(usd)
        out = []
        for (bucket, side), sizes in buckets.items():
            usd = sum(sizes)
            if usd >= CONFIG.positioning.hl_min_level_usd:
                who = 'longs' if side > 0 else 'shorts'
                out.append(RawLevel((bucket + 0.5) * step, 'liq_hl', f"HL liq {who} ${usd / 1e6:.1f}M ({len(sizes)})",
                                    -side, usd))
        return out

    # ------------------------------------------------------------------ OKX liquidations after a restart

    async def _okx_liquidations_backfill(self):
        """The last 100 filled liquidations of every mapped OKX contract (one pass at start, paced)."""
        f = self.fetcher
        await asyncio.sleep(5)
        added = 0
        for market in list(f.symbol_map.by_venue.get('okx', {}).values()):
            md = f.markets.get(market.key)
            if md is None:
                continue
            try:
                r = await self._get(OKX_LIQ_URL, instType='SWAP', instFamily=market.native.replace('-SWAP', ''),
                                    state='filled', limit=100)
            except Exception as e:
                logger.debug(f"OKX liquidations failed for {market.native}: {e}")
                continue
            to_binance = f.symbol_map.key_multiplier.get(market.key, 1.0) / market.multiplier
            known = {(e[0], round(e[2])) for e in md.liq_events if e[4] == 'okx'}
            events = []
            for item in r.get('data') or []:
                for d in item.get('details', []):
                    price, size = float(d.get('bkPx') or 0), float(d.get('sz') or 0)
                    usd = price * size * market.contract_value
                    pos = d.get('posSide')
                    side = 1 if pos == 'long' or (pos == 'net' and d.get('side') == 'sell') else -1
                    event = (int(d['ts']), price * to_binance, usd, side, 'okx')
                    if (event[0], round(usd)) not in known:
                        events.append(event)
            if events:
                merged = sorted(list(md.liq_events) + events, key=lambda e: e[0])
                md.liq_events.clear()
                md.liq_events.extend(merged)
                added += len(events)
            await asyncio.sleep(0.12)   # OKX public limit: 20 requests / 2s
        logger.info(f"OKX liquidations restored: {added} events")
