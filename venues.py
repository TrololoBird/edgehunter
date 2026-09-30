"""
Raw WebSocket clients for every venue, normalized to a few events delivered to a sink (DataFetcher):

    sink.on_trade(market, ts_ms, price, size, side, recv_ms)          side: +1 taker buy, -1 taker sell
    sink.on_liquidation(market, ts_ms, price, size, side_liq, recv_ms) side_liq: +1 long liquidated, -1 short
    sink.on_deriv(market, oi_usd=, funding_8h=, mark=, ts_ms=)          open interest (USD), 8h-equivalent funding
    sink.on_binance(market_type, stream, data, recv_ms)                 Binance's own streams (klines, depth, ...)

`market` is a symbols.VenueMarket (native id -> canonical key). Taker-side conventions differ per venue and are
handled here: Binance aggTrade m=true = taker SELL; Bybit `S` / OKX `side` / Bitget `side` = taker side;
Hyperliquid `B` = taker buy; Coinbase market_trades `side` is the MAKER side (inverted).

Transport: picows (Cython WebSocket client, frames handled in the data callback). Each VenueStream splits its
subscriptions over connections within the venue's limits, subscribes in paced batches, pings at the application
level where required, detects dead sockets with protocol pings when idle, and reconnects with backoff that only
resets once data flowed. A 'dynamic' connection supports runtime subscribe / unsubscribe
(Binance order books and Hyperliquid trades of hot symbols).
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

import orjson


def _import_picows():
    """
    picows imports aiofastnet, whose C code prints an OpenSSL DLL lookup error straight to stderr on some Python
    builds (it then falls back to the standard ssl module, which is what we use: use_aiofastnet=False). Silence that
    one print by pointing fd 2 at the null device during the import.
    """
    import os
    import sys
    try:
        sys.stderr.flush()
        saved = os.dup(2)
    except (OSError, ValueError):
        import picows
        return picows
    try:
        with open(os.devnull, 'w') as null:
            os.dup2(null.fileno(), 2)
            import picows
    finally:
        os.dup2(saved, 2)
        os.close(saved)
    return picows


_picows = _import_picows()
WSListener, WSMsgType, WSTransport, ws_connect = _picows.WSListener, _picows.WSMsgType, _picows.WSTransport, _picows.ws_connect

from config import CONFIG
from netstate import NETWORK
from symbols import SymbolMap

logger = logging.getLogger(__name__)

_SSL_CONTEXT = None


def ssl_context():
    """
    One shared client SSL context: ws_connect built a new one per connection, and loading the Windows certificate
    stores (ssl.create_default_context) blocked the loop 1-1.5s at every reconnect wave.
    """
    global _SSL_CONTEXT
    if _SSL_CONTEXT is None:
        import ssl
        _SSL_CONTEXT = ssl.create_default_context()
    return _SSL_CONTEXT
# picows logs every connect / disconnect at INFO; ours already does
logging.getLogger('picows').setLevel(logging.WARNING)

MAX_FRAME_SIZE = 64 * 1024 * 1024


def _now_ms() -> float:
    return time.time() * 1000


def _f(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class _Listener(WSListener):
    """
    picows callback: every frame is handled synchronously the moment its bytes arrive (no task switch per
    message), so a busy socket is drained at the speed data comes in. With aiohttp one message was consumed per
    event-loop iteration: the busiest Binance socket fell 5-15s behind at peaks and its pong queued behind the
    backlog, which made the heartbeat drop the connection (code 1006) every ~30s.
    """

    def __init__(self, stream: 'VenueStream'):
        super().__init__()
        self.stream = stream
        self.frames = 0
        self._parts: List[bytes] = []

    def on_ws_frame(self, transport: WSTransport, frame):
        msg_type = frame.msg_type
        self.stream.bytes += frame.payload_size
        if msg_type == WSMsgType.TEXT or msg_type == WSMsgType.CONTINUATION:
            if not frame.fin or self._parts:
                self._parts.append(frame.get_payload_as_bytes())
                if not frame.fin:
                    return
                data = b''.join(self._parts)
                self._parts = []
            else:
                data = frame.get_payload_as_bytes()
            self.frames += 1
            self.stream._on_text(data)
        elif msg_type == WSMsgType.CLOSE:
            self.stream.last_close = f"code {frame.get_close_code()} {frame.get_close_message() or b''!r}"
            transport.send_close(frame.get_close_code())
            transport.disconnect()


class VenueStream:
    venue = ''
    url = ''
    ping_payload: Optional[str] = None
    ping_interval = 20.0
    subs_per_connection = 300
    subs_per_request = 100
    request_interval = 0.5
    connect_stagger = 0.4
    # Protocol ping when a connection is idle this long; no pong within the same time = dead, reconnect
    idle_timeout = 20.0

    def __init__(self, sink, symbols: SymbolMap, name: str = ''):
        self.sink = sink
        self.symbols = symbols
        self.name = name or self.venue
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._transports: Set[WSTransport] = set()
        self.connected = 0
        self.messages = 0
        self.bytes = 0
        self.errors = 0
        self.last_close = ''
        # dynamic connection state
        self._dynamic_wanted: Set[Any] = set()
        self._dynamic_active: Set[Any] = set()
        self._dynamic_transport: Optional[WSTransport] = None
        self._dynamic_lock = asyncio.Lock()

    # ------------------------------------------------------------------ venue specifics

    def subscriptions(self) -> List[Any]:
        """Static subscriptions for the current symbol map."""
        return []

    def subscribe_messages(self, subs: Sequence[Any]) -> List[Any]:
        raise NotImplementedError

    def unsubscribe_messages(self, subs: Sequence[Any]) -> List[Any]:
        return []

    def handle(self, payload: Any, recv_ms: float):
        raise NotImplementedError

    def connection_url(self, index: int) -> str:
        return self.url

    # ------------------------------------------------------------------ lifecycle

    async def start(self, dynamic: bool = False):
        self._running = True
        subs = self.subscriptions()
        # Round-robin over the sockets: subscriptions come sorted by volume, and contiguous chunks put the most active
        # coins on one socket, which then fell behind and was dropped at every market burst
        n = -(-len(subs) // self.subs_per_connection) if subs else 0
        chunks = [subs[k::n] for k in range(n)]
        for i, chunk in enumerate(chunks):
            self._tasks.append(asyncio.create_task(self._connection(chunk, i * self.connect_stagger, i)))
        if dynamic:
            self._tasks.append(asyncio.create_task(
                self._connection([], len(chunks) * self.connect_stagger, -1, dynamic=True)))
        if chunks or dynamic:
            logger.info(f"{self.name} WS: {len(subs)} subscriptions on {len(chunks)} connection(s)"
                        f"{' + dynamic' if dynamic else ''}")

    async def stop(self):
        self._running = False
        for transport in list(self._transports):
            transport.disconnect()
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=5)
        self._tasks.clear()

    async def restart(self, dynamic: bool = False):
        """Re-subscribe after the symbol map changed (universe refresh)."""
        wanted = set(self._dynamic_wanted)
        await self.stop()
        await self.start(dynamic=dynamic)
        if dynamic:
            await self.set_dynamic(wanted)

    # ------------------------------------------------------------------ messages

    def _on_text(self, data: bytes):
        if data == b'pong' or data == b'ping':
            return
        self.messages += 1
        try:
            payload = orjson.loads(data)
        except orjson.JSONDecodeError:
            return
        try:
            self.handle(payload, _now_ms())
        except Exception as e:
            self.errors += 1
            if self.errors <= 20 or self.errors % 1000 == 0:
                logger.error(f"{self.name} handler error: {e}", exc_info=self.errors <= 3)

    async def _send_all(self, transport: WSTransport, messages: Iterable[Any]):
        for message in messages:
            if transport.is_disconnected:
                return
            data = message.encode() if isinstance(message, str) else orjson.dumps(message)
            transport.send(WSMsgType.TEXT, data)
            await asyncio.sleep(self.request_interval)

    async def _pinger(self, transport: WSTransport):
        """Application-level ping for venues that require it (protocol pings are handled by picows)."""
        payload = self.ping_payload.encode()
        while not transport.is_disconnected:
            await asyncio.sleep(self.ping_interval)
            if not transport.is_disconnected:
                transport.send(WSMsgType.TEXT, payload)

    # ------------------------------------------------------------------ connections

    async def _connection(self, subs: List[Any], delay: float, index: int = 0, dynamic: bool = False):
        await asyncio.sleep(delay)
        backoff = 1.0
        failures = 0   # consecutive connections that delivered no data
        while self._running:
            transport = ping_task = None
            # our own listener object: its frame count is read after the connection ends, whatever ws_connect returns
            listener = _Listener(self)
            try:
                transport, _ = await ws_connect(
                    lambda: listener, self.connection_url(index),
                    enable_auto_ping=True, auto_ping_idle_timeout=self.idle_timeout,
                    auto_ping_reply_timeout=self.idle_timeout, enable_auto_pong=True,
                    max_frame_size=MAX_FRAME_SIZE, websocket_handshake_timeout=15, use_aiofastnet=False,
                    ssl_context=ssl_context() if self.connection_url(index).startswith('wss') else None,
                )
                self._transports.add(transport)
                self.connected += 1
                if self.ping_payload:
                    ping_task = asyncio.create_task(self._pinger(transport))
                if dynamic:
                    async with self._dynamic_lock:
                        self._dynamic_transport = transport
                        self._dynamic_active = set()
                        if self._dynamic_wanted:
                            await self._send_all(transport, self.subscribe_messages(sorted(self._dynamic_wanted, key=str)))
                            self._dynamic_active = set(self._dynamic_wanted)
                else:
                    await self._send_all(transport, self.subscribe_messages(subs))
                await transport.wait_disconnected()
                if self._running:
                    # A single drop that reconnects at once is routine for public feeds (exchange gateway restarts,
                    # network blips): INFO. Repeated connections without data mean the venue is really down: WARNING.
                    # (`failures` is reset only after this: a socket that delivered data counts as healthy here)
                    level = logging.WARNING if failures >= 2 and not listener.frames else logging.INFO
                    logger.log(level, f"{self.name} WS disconnected ({self.last_close or 'no close frame'}) after "
                                      f"{listener.frames} messages, reconnecting")
            except asyncio.CancelledError:
                if transport is not None:
                    transport.disconnect()
                raise
            except Exception as e:
                if not NETWORK.failed(f"{self.name} WS", e):
                    level = logging.WARNING if failures >= 2 else logging.INFO
                    logger.log(level, f"{self.name} WS connect failed ({type(e).__name__} {e}), retry in {backoff:.0f}s")
            finally:
                if ping_task:
                    ping_task.cancel()
                if transport is not None:
                    self._transports.discard(transport)
                    self.connected -= 1
                if dynamic:
                    self._dynamic_transport = None
            if listener is not None and listener.frames:
                backoff, failures = 1.0, 0  # reset only once data actually flowed
                NETWORK.ok()
            else:
                failures += 1
            if self._running:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    # ------------------------------------------------------------------ dynamic subscriptions

    async def set_dynamic(self, wanted: Iterable[Any]):
        """Make the dynamic connection subscribe exactly `wanted` (diffs are sent while connected)."""
        async with self._dynamic_lock:
            self._dynamic_wanted = set(wanted)
            transport = self._dynamic_transport
            if transport is None or transport.is_disconnected:
                return
            add = sorted(self._dynamic_wanted - self._dynamic_active, key=str)
            remove = sorted(self._dynamic_active - self._dynamic_wanted, key=str)
            try:
                if remove:
                    await self._send_all(transport, self.unsubscribe_messages(remove))
                if add:
                    await self._send_all(transport, self.subscribe_messages(add))
                self._dynamic_active = set(self._dynamic_wanted)
            except Exception as e:
                logger.debug(f"{self.name} dynamic update failed: {e}")


# ====================================================================== Binance

BINANCE_URLS = {
    'spot': 'wss://stream.binance.com:9443/stream',
    # Since the 2026 URL split USD-M streams are routed: klines / aggTrade / markPrice / miniTicker / forceOrder
    # under /market, order books under /public; unrouted legacy URLs connect but push nothing
    'futures': 'wss://fstream.binance.com/market/stream',
    'futures_public': 'wss://fstream.binance.com/public/stream',
}


class BinanceStream(VenueStream):
    """One Binance connection group: `streams` are raw stream names ('btcusdt@kline_15m', '!forceOrder@arr')."""
    venue = 'binance'
    subs_per_connection = 1000  # limit 1024
    subs_per_request = 200
    request_interval = 0.5      # incoming message limits: spot 5/s, futures 10/s

    def __init__(self, sink, symbols: SymbolMap, market_type: str, streams: List[str], name: str,
                 url_key: Optional[str] = None):
        super().__init__(sink, symbols, name=name)
        self.market_type = market_type
        self.streams = streams
        self.url = BINANCE_URLS[url_key or market_type]
        self._request_id = 0

    def subscriptions(self) -> List[str]:
        return list(self.streams)

    def _message(self, method: str, subs: Sequence[str]) -> List[dict]:
        out = []
        for i in range(0, len(subs), self.subs_per_request):
            self._request_id += 1
            out.append({'method': method, 'params': list(subs[i:i + self.subs_per_request]), 'id': self._request_id})
        return out

    def subscribe_messages(self, subs):
        return self._message('SUBSCRIBE', subs)

    def unsubscribe_messages(self, subs):
        return self._message('UNSUBSCRIBE', subs)

    def handle(self, payload, recv_ms: float):
        if 'error' in payload:
            logger.warning(f"{self.name} error reply: {payload['error']}")
            return
        data = payload.get('data')
        if data is not None:
            self.sink.on_binance(self.market_type, payload.get('stream', ''), data, recv_ms)


# ====================================================================== Bybit

class BybitStream(VenueStream):
    venue = 'bybit'
    url = 'wss://stream.bybit.com/v5/public/linear'
    ping_payload = '{"op":"ping"}'
    ping_interval = 20.0
    subs_per_connection = 200
    subs_per_request = 10
    request_interval = 0.2

    def __init__(self, sink, symbols: SymbolMap):
        super().__init__(sink, symbols)
        self._tickers: Dict[str, dict] = {}

    def subscriptions(self):
        subs = []
        # OI / funding come from one bulk REST call (fetcher._bulk_deriv_loop): the tickers topic pushes a delta
        # every 100ms per symbol, thousands of messages a second for a number needed twice a minute
        for native in self.symbols.natives(self.venue):
            subs += [f"publicTrade.{native}", f"allLiquidation.{native}"]
        return subs

    def subscribe_messages(self, subs):
        return [{'op': 'subscribe', 'args': list(subs[i:i + self.subs_per_request])}
                for i in range(0, len(subs), self.subs_per_request)]

    def handle(self, payload, recv_ms: float):
        topic = payload.get('topic')
        if not topic:
            if payload.get('success') is False:
                logger.warning(f"bybit reply: {payload.get('ret_msg')}")
            return
        kind, _, native = topic.partition('.')
        market = self.symbols.lookup(self.venue, native)
        if market is None:
            return
        data = payload.get('data')
        if kind == 'publicTrade':
            for t in data:
                self.sink.on_trade(market, int(t['T']), _f(t['p']), _f(t['v']), 1 if t['S'] == 'Buy' else -1, recv_ms)
        elif kind == 'tickers':
            state = self._tickers.setdefault(native, {})
            state.update({k: v for k, v in data.items() if v not in (None, '')})
            oi_usd = _f(state.get('singleOpenInterestValue')) or _f(state.get('openInterestValue'))
            interval = _f(state.get('fundingIntervalHour'), 8.0) or 8.0
            funding = state.get('fundingRate')
            self.sink.on_deriv(market, oi_usd=oi_usd or None,
                               funding_8h=_f(funding) * 8 / interval if funding not in (None, '') else None,
                               mark=_f(state.get('markPrice')) or None, ts_ms=payload.get('ts'))
        elif kind == 'allLiquidation':
            for liq in data:
                # S = side of the liquidated position: Buy = a long was liquidated
                self.sink.on_liquidation(market, int(liq['T']), _f(liq['p']), _f(liq['v']),
                                         1 if liq['S'] == 'Buy' else -1, recv_ms)


# ====================================================================== OKX

class OkxStream(VenueStream):
    venue = 'okx'
    url = 'wss://ws.okx.com:8443/ws/v5/public'
    ping_payload = 'ping'
    ping_interval = 20.0
    subs_per_connection = 240
    subs_per_request = 60
    request_interval = 0.4
    connect_stagger = 0.5  # 3 connection requests / s per IP

    def subscriptions(self):
        subs = [('liquidation-orders', 'SWAP')]
        for native in self.symbols.natives(self.venue):
            subs += [('trades', native), ('open-interest', native), ('funding-rate', native)]
        return subs

    @staticmethod
    def _arg(sub):
        channel, value = sub
        return {'channel': channel, 'instType': value} if channel == 'liquidation-orders' else {'channel': channel, 'instId': value}

    def subscribe_messages(self, subs):
        return [{'op': 'subscribe', 'args': [self._arg(s) for s in subs[i:i + self.subs_per_request]]}
                for i in range(0, len(subs), self.subs_per_request)]

    def handle(self, payload, recv_ms: float):
        if 'event' in payload:
            if payload['event'] == 'error':
                logger.warning(f"okx reply: {payload.get('msg')}")
            return
        channel = (payload.get('arg') or {}).get('channel')
        data = payload.get('data') or []
        if channel == 'trades':
            for t in data:
                market = self.symbols.lookup(self.venue, t['instId'])
                if market:
                    self.sink.on_trade(market, int(t['ts']), _f(t['px']), _f(t['sz']), 1 if t['side'] == 'buy' else -1, recv_ms)
        elif channel == 'open-interest':
            for item in data:
                market = self.symbols.lookup(self.venue, item['instId'])
                if market:
                    self.sink.on_deriv(market, oi_usd=_f(item.get('oiUsd')) or None, ts_ms=int(item.get('ts') or 0))
        elif channel == 'funding-rate':
            for item in data:
                market = self.symbols.lookup(self.venue, item['instId'])
                if market and item.get('fundingRate') not in (None, ''):
                    hours = (_f(item.get('nextFundingTime')) - _f(item.get('fundingTime'))) / 3_600_000
                    hours = hours if 0 < hours <= 24 else 8.0
                    self.sink.on_deriv(market, funding_8h=_f(item['fundingRate']) * 8 / hours)
        elif channel == 'liquidation-orders':
            for item in data:
                market = self.symbols.lookup(self.venue, item.get('instId', ''))
                if market is None:
                    continue
                for d in item.get('details', []):
                    pos = d.get('posSide')
                    if pos == 'long':
                        side_liq = 1
                    elif pos == 'short':
                        side_liq = -1
                    else:  # net mode: a forced sell closes a long
                        side_liq = 1 if d.get('side') == 'sell' else -1
                    self.sink.on_liquidation(market, int(d['ts']), _f(d.get('bkPx')), _f(d.get('sz')), side_liq, recv_ms)


# ====================================================================== Hyperliquid

class HyperliquidStream(VenueStream):
    venue = 'hyperliquid'
    url = 'wss://api.hyperliquid.xyz/ws'
    ping_payload = '{"method":"ping"}'
    ping_interval = 30.0
    subs_per_connection = 400
    subs_per_request = 1
    request_interval = 0.06  # 2000 messages / min per IP

    def subscriptions(self):
        return [('activeAssetCtx', native) for native in self.symbols.natives(self.venue)]

    def subscribe_messages(self, subs):
        return [{'method': 'subscribe', 'subscription': {'type': t, 'coin': c}} for t, c in subs]

    def unsubscribe_messages(self, subs):
        return [{'method': 'unsubscribe', 'subscription': {'type': t, 'coin': c}} for t, c in subs]

    def handle(self, payload, recv_ms: float):
        channel = payload.get('channel')
        data = payload.get('data')
        if channel == 'activeAssetCtx':
            market = self.symbols.lookup(self.venue, data.get('coin', ''))
            ctx = data.get('ctx') or {}
            if market:
                mark = _f(ctx.get('markPx'))
                funding = ctx.get('funding')
                self.sink.on_deriv(market, oi_usd=_f(ctx.get('openInterest')) * mark or None,
                                   # hourly funding -> 8h equivalent
                                   funding_8h=_f(funding) * 8 if funding not in (None, '') else None,
                                   mark=mark or None)
        elif channel == 'trades':
            for t in data:
                market = self.symbols.lookup(self.venue, t.get('coin', ''))
                if market:
                    self.sink.on_trade(market, int(t['time']), _f(t['px']), _f(t['sz']), 1 if t['side'] == 'B' else -1, recv_ms)


# ====================================================================== Bitget

class BitgetStream(VenueStream):
    venue = 'bitget'
    url = 'wss://ws.bitget.com/v2/ws/public'
    ping_payload = 'ping'
    ping_interval = 25.0
    subs_per_request = 15
    request_interval = 0.25  # <= 10 messages / s per connection
    connect_stagger = 0.3

    def __init__(self, sink, symbols: SymbolMap, funding_hours: Optional[Dict[str, float]] = None):
        super().__init__(sink, symbols)
        self.subs_per_connection = CONFIG.venues.bitget_channels_per_connection
        self.funding_hours = funding_hours or {}

    def subscriptions(self):
        # Trades only: OI / funding come from one bulk REST call (the ticker channel pushes every ~150ms per symbol)
        return [('trade', native) for native in self.symbols.natives(self.venue)]

    def subscribe_messages(self, subs):
        return [{'op': 'subscribe', 'args': [{'instType': 'USDT-FUTURES', 'channel': c, 'instId': i}
                                              for c, i in subs[k:k + self.subs_per_request]]}
                for k in range(0, len(subs), self.subs_per_request)]

    def handle(self, payload, recv_ms: float):
        if 'event' in payload:
            if payload['event'] == 'error':
                logger.warning(f"bitget reply: {payload.get('msg')}")
            return
        arg = payload.get('arg') or {}
        market = self.symbols.lookup(self.venue, arg.get('instId', ''))
        if market is None:
            return
        channel = arg.get('channel')
        if channel == 'trade':
            if payload.get('action') == 'snapshot':
                return  # the initial snapshot replays old trades
            for t in payload.get('data', []):
                self.sink.on_trade(market, int(t['ts']), _f(t['price']), _f(t['size']), 1 if t['side'] == 'buy' else -1, recv_ms)
        elif channel == 'ticker':
            for item in payload.get('data', []):
                mark = _f(item.get('markPrice'))
                hours = self.funding_hours.get(market.native, 8.0) or 8.0
                funding = item.get('fundingRate')
                self.sink.on_deriv(market, oi_usd=_f(item.get('holdingAmount')) * mark or None,
                                   funding_8h=_f(funding) * 8 / hours if funding not in (None, '') else None,
                                   mark=mark or None, ts_ms=int(item.get('ts') or 0))


# ====================================================================== Coinbase (spot)

def _iso_ms(value: str) -> int:
    """'2026-09-26T11:36:31.632752Z' (up to nanoseconds) -> epoch ms."""
    value = value.rstrip('Z')
    if '.' in value:
        head, frac = value.split('.', 1)
        value = f"{head}.{frac[:6]}"
    return int(datetime.fromisoformat(value + '+00:00').timestamp() * 1000)


class CoinbaseStream(VenueStream):
    venue = 'coinbase'
    url = 'wss://advanced-trade-ws.coinbase.com'
    subs_per_connection = 100
    subs_per_request = 100
    request_interval = 0.3

    def subscriptions(self):
        return self.symbols.natives(self.venue)

    def subscribe_messages(self, subs):
        # heartbeats keep quiet channels from being closed after 60-90s
        return [{'type': 'subscribe', 'product_ids': list(subs), 'channel': 'market_trades'},
                {'type': 'subscribe', 'channel': 'heartbeats'}]

    def handle(self, payload, recv_ms: float):
        if payload.get('channel') != 'market_trades':
            return
        for event in payload.get('events', []):
            if event.get('type') != 'update':
                continue  # the snapshot replays old trades
            for t in event.get('trades', []):
                market = self.symbols.lookup(self.venue, t.get('product_id', ''))
                if market:
                    # `side` is the maker side: a SELL maker means the taker bought
                    side = 1 if t['side'] == 'SELL' else -1
                    self.sink.on_trade(market, _iso_ms(t['time']), _f(t['price']), _f(t['size']), side, recv_ms)


class BybitSpotStream(BybitStream):
    """Bybit spot trades, only for the coins without a Binance spot pair (the sink decides): their spot flow and spot
    1m candles, so they join the universe with a spot market."""
    venue = 'bybit_spot'
    url = 'wss://stream.bybit.com/v5/public/spot'

    def subscriptions(self):
        wanted = getattr(self.sink, 'needs_alt_spot', lambda key: False)
        return [f"publicTrade.{n}" for n in self.symbols.natives(self.venue)
                if wanted(self.symbols.lookup(self.venue, n).key)]


VENUE_STREAMS = {
    'bybit': BybitStream,
    'bybit_spot': BybitSpotStream,
    'okx': OkxStream,
    'hyperliquid': HyperliquidStream,
    'bitget': BitgetStream,
    'coinbase': CoinbaseStream,
}

# ccxt ids / market filters for loading each venue's instrument list
# ccxt options restrict load_markets to the needed instrument type (Bybit's full list with spot + options timed out)
VENUE_MARKETS = {
    'bybit': ('bybit', {'defaultType': 'swap', 'fetchMarkets': {'types': ['linear']}},
              lambda m: m.get('swap') and m.get('linear') and m.get('settle') == 'USDT'),
    'okx': ('okx', {'defaultType': 'swap', 'fetchMarkets': {'types': ['swap']}},
            lambda m: m.get('swap') and m.get('settle') == 'USDT'),
    'hyperliquid': ('hyperliquid', {'defaultType': 'swap', 'fetchMarkets': {'types': ['swap']}},
                    lambda m: m.get('swap') and ':' not in ((m.get('info') or {}).get('name') or ':')),
    'bitget': ('bitget', {'defaultType': 'swap', 'fetchMarkets': {'types': ['swap']}},
               lambda m: m.get('swap') and m.get('settle') == 'USDT'),
    'coinbase': ('coinbase', {}, lambda m: m.get('spot') and m.get('quote') == 'USD'),
    'bybit_spot': ('bybit', {'defaultType': 'spot', 'fetchMarkets': {'types': ['spot']}},
                   lambda m: m.get('spot') and m.get('quote') == 'USDT'),
}


def venue_market_rows(venue: str, markets: Dict[str, dict]) -> List[dict]:
    """ccxt markets -> [{'native', 'base', 'contract_value'}] as SymbolMap.add_venue expects."""
    _, _, keep = VENUE_MARKETS[venue]
    rows = []
    for m in markets.values():
        if not keep(m) or m.get('active') is False:
            continue
        info = m.get('info') or {}
        if venue == 'hyperliquid':
            native, base = info.get('name'), info.get('name')
        else:
            native, base = m['id'], m.get('base')
        contract_value = m.get('contractSize') if venue == 'okx' else 1.0
        rows.append({'native': native, 'base': base, 'contract_value': contract_value or 1.0})
    return rows
