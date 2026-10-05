import asyncio
import bisect
import gc
import logging
import errors
import time
import zlib
import json
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

import ccxt.async_support as ccxt
import numpy as np
import polars as pl

from config import CONFIG
from depth import DepthBook
from strategies import confirm
from flow import SPOT_VENUES, Footprint, FlowStore, Sweep, SweepTracker, WhaleBook, absorption_in, minute_atr_15m
from indicators import RAW_SCHEMA, TIMEFRAME_MS, empty_raw_frame, merge_live_candle, seasonal_factors
from ratelimit import RATE_LIMIT_ERRORS, BanState, RestGate
from symbols import SymbolMap, VenueMarket
from netstate import NETWORK
from venues import BinanceStream, VENUE_MARKETS, VENUE_STREAMS, venue_market_rows

logger = logging.getLogger(__name__)

MARKETS = ('spot', 'futures')


@dataclass
class MarketData:
    symbol: str
    spot_df: "pl.DataFrame" = field(default=None)
    futures_df: "pl.DataFrame" = field(default=None)
    funding_rate: float = 0.0
    predicted_funding: float = 0.0
    open_interest: float = 0.0
    trades_subscribed: bool = False  # order book (hot symbol) subscription active
    current_long_score: int = 0
    current_short_score: int = 0
    volume_multiplier: float = 1.0
    spot_symbol: str = ""
    # Tier-0 raw samples: (ts_ms, last_price, rolling_24h_quote_volume) from the futures miniTicker (1/s),
    # and (ts_ms, open_interest). A few minutes deep.
    ticker_samples: deque = field(default_factory=lambda: deque(maxlen=400))
    oi_samples: deque = field(default_factory=lambda: deque(maxlen=64))
    tier0: dict = field(default_factory=dict)
    is_tier_0_anomaly: bool = False
    tier2_wanted_at: float = 0.0
    tier2_since: float = 0.0
    tier0_last_trigger: float = 0.0
    tier2_denied: bool = False
    # Kline stream state per market: latest in-progress candle, finalized candles waiting to be merged,
    # and the open time of the newest candle known to be final
    live_klines: dict = field(default_factory=dict)
    closed_klines: dict = field(default_factory=lambda: {m: [] for m in MARKETS})
    finalized_until: dict = field(default_factory=lambda: {m: 0 for m in MARKETS})
    # 1m candles [open_time_ms, open, high, low, close, quote_volume, taker_buy_quote], latest last: futures (Tier-0
    # RVOL_1m, the LTF trigger, absorption) and spot (live spot CVD)
    # 10h: PO3 reads the Asian range 20:00-00:00 New York from 02:00-05:00 NY (240 minutes held at most 21 of its 48
    # 5m bars: PO3 could never fire - research/replay_missing.md); every other reader takes a time window of it
    minute_klines: deque = field(default_factory=lambda: deque(maxlen=600))
    # Open time of the newest FINAL futures 1m candle (kline x=true): the last deque entry may still be running
    minute_closed_until: int = 0
    spot_minute_klines: deque = field(default_factory=lambda: deque(maxlen=60))
    _alt_minute: Optional[list] = None          # the Bybit spot minute being built [ts, o, h, l, c, q, Q]
    avg_minute_usd: float = 0.0
    # Intraday periodicity (indicators.seasonal_factors, 4 weeks of 1h candles, refreshed daily)
    season: Optional[Dict] = None
    quote_volume_24h: float = 0.0
    # 15m candles built from closed 1m candles per market: the bucket being filled, and markets whose last bucket
    # missed minutes (stream gap) and needs a REST backfill
    minute_bucket: dict = field(default_factory=dict)
    backfill_wanted: dict = field(default_factory=dict)   # market -> open time of the candle REST must replace
    # market -> open times of candles built from an incomplete set of minutes, not yet replaced by REST: scoring
    # sees the history only up to the first of them
    incomplete: dict = field(default_factory=lambda: {m: set() for m in MARKETS})
    # market -> (frame key, the frame cut before the first incomplete candle): see Scanner._merge_rows
    scored_cut: dict = field(default_factory=dict)
    # Listing time (futures onboardDate, ms): a listing younger than 24h spreads its 24h volume over fewer minutes
    listed_ms: int = 0
    # Last kline row merged per market (skip re-merging an unchanged live candle)
    last_merged: dict = field(default_factory=dict)
    # Finalized 15m rows recently received per market, re-applied after a backfill snapshot replaces the frame
    recent_closed: dict = field(default_factory=lambda: {m: deque(maxlen=8) for m in MARKETS})
    # Set once the REST candle history is loaded; until then only Tier-0 runs for the symbol
    baseline_ready: bool = False
    # Bumped whenever the REST history of a frame is (re)loaded: the scanner's heavy pass must rerun
    history_version: int = 0
    # Typical 15m move of price / OI (std of 15m changes, from the last heavy scan): Tier-0 z-scores
    ret_std: Optional[float] = None
    oi_std: Optional[float] = None
    # Mark / index price and basis from REST premiumIndex every 30s (no whole-market stream: bandwidth)
    mark_price: float = 0.0
    index_price: float = 0.0
    # (ts_ms, mark / index - 1) every premiumIndex pass: Binance's funding sits at 0.01% while the premium is inside
    # [-0.04%, +0.06%] (its formula), so the premium itself carries the positioning (eng-52)
    premium_hist: deque = field(default_factory=lambda: deque(maxlen=2880))
    # Largest whale sweep / visible depth it hit (> 1 = it ate the book), with its time
    book_eaten: float = 0.0
    book_eaten_ts: float = 0.0
    # Observed liquidations (ts_ms, price in Binance units, usd, side liquidated, venue): swept pools (zones.py)
    liq_events: deque = field(default_factory=lambda: deque(maxlen=2000))
    # Last Coinbase (USD) trade price in Binance units and its time: the Coinbase premium
    coinbase_price: float = 0.0
    coinbase_ts: float = 0.0
    # Coinbase's last price from the bulk products call (a coin without a recent live trade still has a premium)
    coinbase_rest_price: float = 0.0
    coinbase_rest_ts: float = 0.0
    # Level-map inputs loaded only for coins with cards: 1h klines (raw Binance rows) and 1h OI (ts_ms, oi_usd)
    htf_klines: list = field(default_factory=list)
    # the scenario card's higher-timeframe range: 200 daily candles and 30 days of 1h candles (load_htf)
    htf_1d: list = field(default_factory=list)
    htf_1h_30d: list = field(default_factory=list)
    htf_oi: list = field(default_factory=list)
    # 4 days of 5m candles for the 4-day volume profile (card coins only)
    htf_5m: list = field(default_factory=list)
    htf_loaded: float = 0.0
    # 1h candles of EVERY universe coin (~8 days, hourly): liquidity pools of the higher timeframes (previous day /
    # week, sessions, 1h swings) and the coin's own trend for the strategies; [ts, o, h, l, c, quote_vol, taker_buy]
    h1: list = field(default_factory=list)
    h1_loaded: float = 0.0
    # Longer histories of crypto_maniac's systems (strategies/maniac.py): 499 closed 1h / 15m candles (refreshed
    # hourly with h1; h1 itself stays the last h1_candles of it for everything else)
    h1_long: object = field(default_factory=list)      # np.ndarray (n, 7) once loaded
    m15_long: object = field(default_factory=list)
    # OI (coins) every 5 minutes over the last day (the OI robot's 1h / 24h OI growth): seeded from openInterestHist
    oi_5m: deque = field(default_factory=lambda: deque(maxlen=300))
    # Weekly trend reference (strategies.structure.weekly_ref: EMA of the closed weekly closes, weekly return std), a
    # context feature only (trend_w / breadth_w in the journal); reloaded after each weekly close
    w1_ref: Optional[tuple] = None
    w1_loaded: float = 0.0
    # 210 closed daily candles [open_time, o, h, l, c, quote_vol] of every universe coin (Connors' RSI(2) is a daily
    # system: SMA200 + RSI(2) of DAILY closes), reloaded once per UTC day by _daily_candles_loop
    d1: list = field(default_factory=list)
    d1_day: int = 0
    # POCs of the last completed UTC days from their 5m candles [(day_ms, poc)], refreshed once a day for every coin
    # (`_day_pocs_loop`): the map's naked POCs (Dalton) - 1h candles put a POC percents off, and 5m history is held
    # only for card coins
    day_pocs: list = field(default_factory=list)
    day_pocs_day: int = 0
    # 200 closed 4h candles (~33 days, ICT's main point-of-interest timeframe) and the 60 closed weekly candles
    h4: list = field(default_factory=list)
    h4_slot: int = 0
    w1: list = field(default_factory=list)


    def alt_spot_trade(self, ts_ms: int, price: float, usd: float, side: int):
        """A Bybit spot trade into the current minute; a new minute closes the last one into spot_minute_klines."""
        minute = ts_ms // 60_000 * 60_000
        cur = self._alt_minute
        if cur is not None and minute > cur[0]:
            self.spot_minute_klines.append(cur)
            cur = None
        if cur is None:
            cur = self._alt_minute = [minute, price, price, price, price, 0.0, 0.0]
        elif minute < cur[0]:
            return
        cur[2], cur[3], cur[4] = max(cur[2], price), min(cur[3], price), price
        cur[5] += usd
        if side > 0:
            cur[6] += usd
    def frame(self, market: str) -> Optional[pl.DataFrame]:
        return self.spot_df if market == 'spot' else self.futures_df

    def set_frame(self, market: str, df: pl.DataFrame):
        if market == 'spot':
            self.spot_df = df
        else:
            self.futures_df = df

    @property
    def basis(self) -> float:
        return self.mark_price / self.index_price - 1 if self.mark_price and self.index_price else 0.0

    def record_ticker(self, ticker: dict, now_ms: Optional[float] = None):
        """ticker: {'last', 'quoteVolume'} (ccxt shape: the REST 24h tickers every few minutes)."""
        quote_vol = ticker.get('quoteVolume')
        now_ms = now_ms or time.time() * 1000
        if quote_vol is not None:
            self.quote_volume_24h = float(quote_vol)
            minutes_listed = (now_ms - self.listed_ms) / 60_000 if self.listed_ms else 1440
            self.avg_minute_usd = self.quote_volume_24h / min(1440.0, max(1.0, minutes_listed))
        if ticker.get('last'):
            self.record_price(float(ticker['last']), now_ms)

    def record_price(self, price: float, now_ms: float):
        """Last futures trade price, one sample per second (Tier-0 5m price change)."""
        if self.ticker_samples and now_ms - self.ticker_samples[-1][0] < 1000:
            self.ticker_samples[-1] = (self.ticker_samples[-1][0], price, self.quote_volume_24h)
            return
        self.ticker_samples.append((now_ms, price, self.quote_volume_24h))

    def record_oi(self, ts_ms: float, open_interest: float):
        if not open_interest or open_interest <= 0:
            return
        if self.oi_samples and self.oi_samples[-1][0] >= ts_ms:
            return
        self.oi_samples.append((ts_ms, float(open_interest)))
        if not self.oi_5m or ts_ms // 300_000 > self.oi_5m[-1][0] // 300_000:
            self.oi_5m.append((ts_ms, float(open_interest)))

    def seed_minutes(self, market: str, rows: List[List[float]], now_ms: int):
        """
        Closed 1m candles from REST merged under the streamed ones (a streamed candle wins): flows, RVOL, absorption,
        the entry trigger and its confirmations work right after a start instead of after an hour of streaming.
        The futures closes also seed the price samples of Tier-0's 5m price change.
        """
        target = self.minute_klines if market == 'futures' else self.spot_minute_klines
        closed = [r for r in rows if r[0] + 60_000 <= now_ms]
        if not closed:
            return
        merged = {r[0]: r for r in closed}
        merged.update({c[0]: c for c in target})
        candles = sorted(merged.values(), key=lambda c: c[0])[-target.maxlen:]
        target.clear()
        target.extend(candles)
        if market == 'futures':
            self.minute_closed_until = max(self.minute_closed_until, closed[-1][0])
            samples = {ts: (ts, price, qv) for ts, price, qv in self.ticker_samples}
            for c in closed[-10:]:
                samples.setdefault(c[0] + 59_999, (c[0] + 59_999, c[4], self.quote_volume_24h))
            ordered = sorted(samples.values())[-self.ticker_samples.maxlen:]
            self.ticker_samples.clear()
            self.ticker_samples.extend(ordered)

    def seed_oi(self, samples: List[Tuple[float, float]]):
        """Older OI samples (REST history) merged under the live ones: the 5m OI change is known right after start."""
        merged = {ts: oi for ts, oi in list(self.oi_samples) + [(float(t), float(v)) for t, v in samples if v]}
        self.oi_samples.clear()
        self.oi_samples.extend(sorted(merged.items()))
        # the day of 5m points under the live ones, one per 5-minute bucket
        buckets = {}
        for ts, oi in sorted(list(self.oi_5m) + [(float(t), float(v)) for t, v in samples if v]):
            buckets.setdefault(int(ts) // 300_000, (ts, oi))
        self.oi_5m.clear()
        self.oi_5m.extend(buckets[k] for k in sorted(buckets))

    @property
    def last_price(self) -> Optional[float]:
        return self.ticker_samples[-1][1] if self.ticker_samples else None

    def apply_kline(self, market: str, k: dict):
        if k.get('i') == '1m':
            candle = [int(k['t']), float(k['o']), float(k['h']), float(k['l']), float(k['c']), float(k['q']), float(k['Q'])]
            target = self.minute_klines if market == 'futures' else self.spot_minute_klines
            if target and target[-1][0] == candle[0]:
                target[-1] = candle
            elif not target or candle[0] > target[-1][0]:
                target.append(candle)
            if k.get('x'):
                if market == 'futures':
                    self.minute_closed_until = max(self.minute_closed_until, candle[0])
                self._add_closed_minute(market, candle, float(k['v']))
            return

        quote_vol = float(k['q'])
        row = {
            'timestamp': int(k['t']),
            'open': float(k['o']),
            'high': float(k['h']),
            'low': float(k['l']),
            'close': float(k['c']),
            'volume': float(k['v']),
            'quote_volume': quote_vol,
            'taker_delta': 2 * float(k['Q']) - quote_vol,
            'open_interest': None,
        }
        if k.get('x'):
            self.closed_klines[market].append(row)
            if k.get('complete', True):
                self.recent_closed[market].append(dict(row))
                self.finalized_until[market] = max(self.finalized_until[market], row['timestamp'])
            # else: built from an incomplete set of minutes (stream gap / start mid-candle). It sits in the frame
            # but is NOT final: scoring skips it until the REST candle replaces it (request_backfill)
            live = self.live_klines.get(market)
            if live and live['timestamp'] <= row['timestamp']:
                del self.live_klines[market]
        else:
            self.live_klines[market] = row

    def _add_closed_minute(self, market: str, c: List[float], base_volume: float):
        """
        Build the 15m candle from closed 1m candles (open of the first, high / low extremes, close of the last,
        summed quote and taker-buy volume): exactly the exchange's 15m candle, without a second kline stream per
        symbol (the 15m stream pushed as often as the 1m one and doubled the bandwidth).
        """
        start = int(c[0]) // TIMEFRAME_MS * TIMEFRAME_MS
        bucket = self.minute_bucket.get(market)
        if bucket is not None and bucket['timestamp'] != start:
            self._finalize_bucket(market, bucket)   # its last minute never closed (stream gap)
            bucket = None
        if bucket is None:
            bucket = self.minute_bucket[market] = {
                'timestamp': start, 'open': c[1], 'high': c[2], 'low': c[3], 'close': c[4], 'volume': 0.0,
                'quote_volume': 0.0, 'taker_buy': 0.0, 'minutes': 0, 'first_minute': int(c[0]),
            }
        bucket['high'] = max(bucket['high'], c[2])
        bucket['low'] = min(bucket['low'], c[3])
        bucket['close'] = c[4]
        bucket['volume'] += base_volume
        bucket['quote_volume'] += c[5]
        bucket['taker_buy'] += c[6]
        bucket['minutes'] += 1
        if int(c[0]) == start + TIMEFRAME_MS - 60_000:
            self._finalize_bucket(market, bucket)

    def _finalize_bucket(self, market: str, bucket: dict):
        self.minute_bucket.pop(market, None)
        complete = bucket['minutes'] == TIMEFRAME_MS // 60_000 and bucket['first_minute'] == bucket['timestamp']
        if not complete:
            # Started mid-candle or missed minutes: the REST candle replaces it
            self.backfill_wanted[market] = max(self.backfill_wanted.get(market, 0), bucket['timestamp'])
            self.incomplete[market].add(bucket['timestamp'])
        self.apply_kline(market, {
            't': bucket['timestamp'], 'o': bucket['open'], 'h': bucket['high'], 'l': bucket['low'],
            'c': bucket['close'], 'v': bucket['volume'], 'q': bucket['quote_volume'], 'Q': bucket['taker_buy'],
            'x': True, 'i': CONFIG.timeframe.rest_timeframe, 'complete': complete,
        })

    def live_candle(self, market: str) -> Optional[dict]:
        """The in-progress 15m candle: the closed minutes of the bucket plus the live minute."""
        minutes = self.minute_klines if market == 'futures' else self.spot_minute_klines
        if not minutes:
            return None
        live = minutes[-1]
        start = int(live[0]) // TIMEFRAME_MS * TIMEFRAME_MS
        bucket = self.minute_bucket.get(market)
        if bucket is not None and bucket['timestamp'] == start:
            return {'timestamp': start, 'open': bucket['open'], 'high': max(bucket['high'], live[2]),
                    'low': min(bucket['low'], live[3]), 'close': live[4]}
        return {'timestamp': start, 'open': live[1], 'high': live[2], 'low': live[3], 'close': live[4]}

    def drain_kline_rows(self, market: str, include_live: bool = True) -> List[dict]:
        """Finalized candles since the last scan, then (optionally) the in-progress one."""
        rows = self.closed_klines[market]
        self.closed_klines[market] = []
        live = self.live_klines.get(market) if include_live else None
        if live and (not rows or live['timestamp'] > rows[-1]['timestamp']):
            rows.append(dict(live))
        return rows

    @property
    def closed_until(self) -> int:
        """Open time of the newest finalized candle of the base market (spot when listed, else futures)."""
        return self.finalized_until['spot' if self.spot_symbol else 'futures']


@dataclass
class VenueDeriv:
    oi_usd: float = 0.0
    funding_8h: Optional[float] = None
    mark: float = 0.0
    ts: float = 0.0
    # (ts_ms, open interest in COINS), sampled at most every 10s, ~70 min deep. Coins, not USD: the USD value moves
    # with price, so "OI rising" on a rally was true without a single new position (the OI confirmation of a
    # breakout read the price itself); oi_usd stays the venue's weight in the aggregate
    samples: deque = field(default_factory=lambda: deque(maxlen=420))


def _pct_change(samples: deque, now_ms: float, window_ms: float) -> Optional[float]:
    """Change of the last sample vs the first one at least ~window old (time-ordered samples, bisect lookup)."""
    if len(samples) < 2 or now_ms - samples[-1][0] > 3 * 60_000:
        return None
    last_ts, last = samples[-1]
    target = last_ts - window_ms
    # Prefer the newest sample at or before the window start (sparse samples: Binance OI once a minute) as long
    # as it is not much older; else the first one inside the window if it still spans >= 80% of it
    idx = bisect.bisect_right(samples, target, key=lambda s: s[0]) - 1
    if idx >= 0 and samples[idx][0] >= target - 0.5 * window_ms:
        base_ts, base = samples[idx]
    elif idx + 1 < len(samples) and samples[idx + 1][0] <= last_ts - 0.8 * window_ms:
        base_ts, base = samples[idx + 1]
    else:
        return None
    return last / base - 1 if base else None


class DataFetcher:
    """
    Binance REST (ccxt, through RestGate) for candle history, OI and journal outcomes; own WebSocket clients
    (venues.py) for everything live:
    - Binance spot + futures klines (15m, 1m), futures aggTrade for every symbol (CVD, sweeps / whales,
      footprint), !forceOrder@arr (liquidations), !markPrice@arr@1s (funding, mark, basis), !miniTicker@arr
      (price + 24h volume, Tier-0) and <sym>@depth20@500ms for hot symbols (dynamic);
    - Bybit / OKX / Hyperliquid / Bitget futures and Coinbase spot: trades, liquidations, OI and funding mapped
      onto the Binance universe (symbols.SymbolMap), aggregated in flow.FlowStore.
    """

    FUNDING_INFO_REFRESH_SEC = 3600

    def __init__(self):
        self.spot_exchange: Optional[ccxt.Exchange] = None
        # Universe selection inputs (fetch_candidates) and the market baseline's mark prices (every USDT perpetual)
        self.spreads: Dict[str, float] = {}
        self.baseline_ids: set = set()
        self.market_marks: Dict[str, float] = {}
        self.futures_exchange: Optional[ccxt.Exchange] = None
        self.venue_exchanges: Dict[str, ccxt.Exchange] = {}
        self.markets: Dict[str, MarketData] = {}
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._background_tasks: set = set()
        self._binance_streams: List[BinanceStream] = []
        # Order books of the hot symbols, spread over several sockets (one depth20 stream is ~1.5 KB every 500ms:
        # twenty on one socket reached its ~60 KB/s limit and Binance dropped it)
        self._depth_streams: List[BinanceStream] = []
        self.venue_streams: Dict[str, object] = {}
        # (market type, exchange id upper-case) -> futures symbol key of MarketData
        self._binance_keys: Dict[Tuple[str, str], str] = {}
        self._backfill_pending: set = set()
        self._backfill_retry_at: Dict[Tuple[str, str], float] = {}
        self._backfill_semaphore = asyncio.Semaphore(3)
        self.funding_interval_hours: Dict[str, int] = {}
        self.streams_started_ms = 0               # the flow windows before it are seeded from REST klines
        # set by a Binance listing / contract status event (!contractInfo): the universe is re-selected early
        self.contract_event = asyncio.Event()
        self.reference_prices: Dict[str, float] = {}
        self._htf_loading: set = set()
        self._deriv_cache: Dict[str, Tuple[float, Dict[str, float]]] = {}
        self.funding_info_updated: float = 0.0
        self.oi_last_updated: Dict[str, float] = {}

        ban = BanState()  # one IP: a ban on spot also stops futures calls
        self.gates = {
            'futures': RestGate('binance futures', CONFIG.rest.futures_weight_limit, ban, 'X-MBX-USED-WEIGHT-1M'),
            'spot': RestGate('binance spot', CONFIG.rest.spot_weight_limit, ban, 'X-MBX-USED-WEIGHT-1M'),
        }
        self._positioning_calls: deque = deque()

        # Order flow state (flow.py) and the cross-venue symbol map
        self.symbol_map = SymbolMap()
        # rows for the universe plus coins joining / held by open cards (it doubles if ever exceeded): 320 rows for a
        # 70-coin universe held ~60 MB of empty ring buffers
        self.flow = FlowStore(capacity=CONFIG.exchange.max_pairs + 40)
        self.whales = WhaleBook()
        self.sweeps = SweepTracker(self._on_sweep)
        self.footprint = Footprint()
        self.depth = DepthBook()
        from iceberg import IcebergDetector
        self.icebergs = IcebergDetector()
        # Live liquidations of every venue since the scanner last journaled them: (symbol, ts_ms, price, usd, side, venue)
        self.liq_log: List[tuple] = []
        self.log_liquidations = False     # set by the scanner when a journal takes them
        self.venue_derivs: Dict[str, Dict[str, VenueDeriv]] = {}
        self._zone_atr: Dict[str, float] = {}
        self._iceberg_fed: Dict[str, float] = {}
        # (epoch seconds, BTC dominance %, USDT dominance %) every 5 min, a day kept (CoinGecko /global)
        self.dominance: deque = deque(maxlen=300)

    # ------------------------------------------------------------------ setup

    async def initialize(self) -> None:
        logger.info("Initializing REST exchanges...")
        # Each instance loads only its own market type: by default both load spot + linear + inverse (~280 MB)
        spot_config = {'enableRateLimit': True, 'options': {'defaultType': 'spot', 'fetchMarkets': {'types': ['spot']}}}
        futures_config = {'enableRateLimit': True, 'options': {'defaultType': 'future', 'fetchMarkets': {'types': ['linear']}}}
        self.spot_exchange = getattr(ccxt, CONFIG.exchange.exchange_id)(spot_config)
        self.futures_exchange = getattr(ccxt, CONFIG.exchange.exchange_id)(futures_config)
        await asyncio.gather(self._load_markets_off_loop(self.spot_exchange, spot_config),
                             self._load_markets_off_loop(self.futures_exchange, futures_config))
        logger.info(f"Loaded {len(self.spot_exchange.markets)} spot, {len(self.futures_exchange.markets)} futures markets")

    @staticmethod
    async def _load_markets_off_loop(exchange, config: dict):
        """
        ccxt parses market lists (thousands of dicts) synchronously; on the event loop that blocked everything for
        ~2s at start. A synchronous ccxt instance loads them in a worker thread and the async one receives the result.
        """
        def load():
            import ccxt as ccxt_sync   # imported in the worker thread: the import alone takes ~1s
            sync = getattr(ccxt_sync, exchange.id)(config)
            sync.load_markets()
            return sync.markets, sync.currencies

        for attempt in range(1, 4):
            try:
                markets, currencies = await asyncio.to_thread(load)
                exchange.set_markets(markets, currencies)
                return
            except Exception as e:
                if attempt == 3:
                    raise
                logger.info(f"{exchange.id} market list failed ({type(e).__name__}); retry {attempt}")
                await asyncio.sleep(3 * attempt)

    async def load_venues(self):
        """
        Instrument lists and last prices of the other venues, loaded and parsed in worker threads (synchronous ccxt:
        parsing thousands of markets on the event loop blocked it); failures only disable that venue. Mappings
        whose price shows a different token under the same ticker are dropped before anything is subscribed.
        """
        def fetch(venue: str):
            import ccxt as ccxt_sync   # imported in the worker thread: the import alone takes ~1s
            eid, options, _ = VENUE_MARKETS[venue]
            exchange = getattr(ccxt_sync, eid)({'enableRateLimit': True, 'options': options, 'timeout': 30_000})
            exchange.load_markets()
            rows = venue_market_rows(venue, exchange.markets)
            prices: Dict[str, float] = {}
            try:
                for symbol, t in exchange.fetch_tickers().items():
                    market = exchange.markets.get(symbol) or {}
                    native = (market.get('info') or {}).get('name') if venue == 'hyperliquid' else market.get('id')
                    price = t.get('last') or t.get('close') or t.get('bid')
                    if native and price:
                        prices[native] = float(price)
            except Exception as e:
                logger.info(f"{venue}: tickers unavailable for the price check ({type(e).__name__}); "
                            f"live trades are checked instead")
            return rows, prices

        async def load(venue: str):
            for attempt in range(1, 4):
                try:
                    rows, prices = await asyncio.wait_for(asyncio.to_thread(fetch, venue), timeout=90)
                    break
                except Exception as e:
                    if attempt == 3:
                        logger.warning(f"{venue}: market list unavailable ({type(e).__name__} {e}); venue disabled")
                        return
                    await asyncio.sleep(3 * attempt)
            self.symbol_map.add_venue(venue, rows, spot=venue in ('coinbase', 'bybit_spot'))
            dropped = self.symbol_map.verify_prices(venue, prices, self.reference_prices)
            if dropped:
                logger.info(f"Symbol map: {venue} {', '.join(dropped)} dropped (a different token under the same ticker)")

        await asyncio.gather(*[load(v) for v in CONFIG.venues.enabled if v in VENUE_MARKETS])

    # ------------------------------------------------------------------ REST

    def _gate_for(self, exchange) -> RestGate:
        if exchange is self.spot_exchange:
            return self.gates['spot']
        if exchange is self.futures_exchange:
            return self.gates['futures']
        for venue, ex in self.venue_exchanges.items():
            if ex is exchange:
                return self.gates[venue]
        return self.gates['futures']

    async def _rest_call(self, exchange, method: str, *args, priority: int = 1, weight: float = 1, **kwargs):
        """Every REST call: proactive weight budget per priority, shared pause on 429/418 (ratelimit.RestGate)."""
        return await self._gate_for(exchange).call(exchange, method, *args, weight=weight, priority=priority, **kwargs)

    # ------------------------------------------------------------------ funding / OI

    async def _refresh_funding_info(self):
        """Funding interval per symbol (/fapi/v1/fundingInfo lists only non-default ones; default is 8h)."""
        if time.time() - self.funding_info_updated < self.FUNDING_INFO_REFRESH_SEC:
            return
        try:
            info = await self._rest_call(self.futures_exchange, 'fapiPublicGetFundingInfo', priority=1)
        except Exception as e:
            if not NETWORK.failed("Binance fundingInfo", e):
                logger.warning(f"Failed to fetch funding info: {e}")
            return
        intervals = {}
        for item in info:
            ccxt_symbol = self._binance_to_ccxt_symbol(item.get('symbol') or '')
            hours = int(item.get('fundingIntervalHours') or 8)
            if ccxt_symbol and hours > 0:
                intervals[ccxt_symbol] = hours
        self.funding_interval_hours = intervals
        self.funding_info_updated = time.time()

    async def _funding_info_loop(self):
        while self._running:
            await self._refresh_funding_info()
            await asyncio.sleep(300)

    async def fetch_open_interest(self, symbol: str) -> Optional[float]:
        binance_symbol = self._ccxt_to_binance_symbol(symbol)
        if not binance_symbol:
            return None
        try:
            res = await self._rest_call(self.futures_exchange, 'fapiPublicGetOpenInterest', {'symbol': binance_symbol},
                                        priority=1)
        except Exception as e:
            errors.report('fetcher.fetch_open_interest', e, f"OI fetch failed for {symbol}")
            return None
        self.oi_last_updated[symbol] = time.time()
        return float(res.get('openInterest', 0.0))

    async def _oi_loop(self):
        """
        Binance has no OI stream: poll every symbol once per oi_update_interval_sec, each at its own evenly spread
        slot, with a few requests in flight. Sequential polling took ~0.4s per request over this link, so one pass
        over 300 symbols took ~2 minutes and the 5m OI change often found no baseline sample.
        """
        interval = CONFIG.timeframe.oi_update_interval_sec
        in_flight = asyncio.Semaphore(8)

        async def poll(symbol: str, delay: float):
            await asyncio.sleep(delay)
            async with in_flight:
                oi = await self.fetch_open_interest(symbol)
            md = self.markets.get(symbol)
            if oi and md is not None:
                now_ms = time.time() * 1000
                md.open_interest = oi
                md.record_oi(now_ms, oi)
                if md.last_price:
                    self._record_venue_oi(symbol, 'binance', oi * md.last_price, now_ms)

        while self._running:
            symbols = list(self.markets)
            if not symbols:
                await asyncio.sleep(1)
                continue
            started = time.time()
            step = interval / len(symbols)
            await asyncio.gather(*[poll(s, i * step) for i, s in enumerate(symbols)], return_exceptions=True)
            await asyncio.sleep(max(0.0, interval - (time.time() - started)))

    def _record_venue_oi(self, key: str, venue: str, oi_usd: float, ts_ms: float):
        state = self.venue_derivs.setdefault(key, {}).setdefault(venue, VenueDeriv())
        state.oi_usd, state.ts = oi_usd, ts_ms
        price = state.mark or self._binance_price(key)
        if price and (not state.samples or ts_ms - state.samples[-1][0] >= 10_000):
            state.samples.append((ts_ms, oi_usd / price))

    async def _binance_rest_tickers_loop(self):
        """
        Funding / mark / index for every contract (premiumIndex, weight 10) every 30s and the 24h volumes (weight 40)
        every 5 min: the same numbers the whole-market streams pushed every second, at a tiny share of the bandwidth.
        """
        last_volumes = 0.0
        while self._running:
            try:
                await self._update_premium_index()
                if time.time() - last_volumes >= 300:
                    await self._update_24h_volumes()
                    last_volumes = time.time()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if not NETWORK.failed("Binance REST tickers", e):
                    logger.warning(f"Binance REST tickers failed ({type(e).__name__}): {e}")
            await asyncio.sleep(CONFIG.timeframe.bulk_funding_interval_sec)

    async def _update_premium_index(self):
        rows = await self._rest_call(self.futures_exchange, 'fapiPublicGetPremiumIndex', priority=1, weight=10)
        now_ms = time.time() * 1000
        # Mark prices of every USDT perpetual (the market baseline of the journal: universe snapshots)
        self.market_marks = {m['symbol']: float(m.get('markPrice') or 0.0) for m in rows
                             if m.get('symbol') in self.baseline_ids and float(m.get('markPrice') or 0.0) > 0}
        for m in rows:
            key = self._binance_keys.get(('futures', m.get('symbol')))
            md = self.markets.get(key)
            if md is None:
                continue
            md.mark_price, md.index_price = float(m.get('markPrice') or 0.0), float(m.get('indexPrice') or 0.0)
            if md.mark_price and md.index_price:
                md.premium_hist.append((now_ms, md.mark_price / md.index_price - 1))
            # lastFundingRate: the live estimate of the next funding; settlements run every 1/4/8h -> 8h-equivalent
            rate = float(m.get('lastFundingRate') or 0.0) * 8 / self.funding_interval_hours.get(key, 8)
            md.funding_rate = md.predicted_funding = rate
            state = self.venue_derivs.setdefault(key, {}).setdefault('binance', VenueDeriv())
            state.funding_8h, state.mark, state.ts = rate, md.mark_price, now_ms

    async def _update_24h_volumes(self):
        rows = await self._rest_call(self.futures_exchange, 'fapiPublicGetTicker24hr', priority=1, weight=40)
        now_ms = time.time() * 1000
        # eng-59: every USDT perpetual's 24h volume - the pools rank a coin in the whole market, not in the universe
        self.market_volumes = [float(t.get('quoteVolume') or 0.0) for t in rows
                               if str(t.get('symbol', '')).endswith('USDT')]
        for t in rows:
            md = self.markets.get(self._binance_keys.get(('futures', t.get('symbol'))))
            if md is not None:
                md.record_ticker({'quoteVolume': float(t.get('quoteVolume') or 0.0)}, now_ms)

    BULK_DERIV_URLS = {
        'bybit': 'https://api.bybit.com/v5/market/tickers?category=linear',
        'bitget': 'https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES',
        'bitget_funding': 'https://api.bitget.com/api/v2/mix/market/current-fund-rate?productType=USDT-FUTURES',
    }
    BULK_DERIV_INTERVAL_SEC = 30

    async def _bulk_deriv_loop(self):
        """
        OI and funding of every Bybit / Bitget contract in one public REST call per venue every 30s (2 requests a
        minute, far below their limits), instead of ticker streams pushing thousands of messages a second.
        """
        import aiohttp
        venues = [v for v in self.BULK_DERIV_URLS if v.split('_')[0] in CONFIG.venues.enabled]
        if not venues:
            return
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            while self._running:
                for venue in venues:
                    try:
                        async with session.get(self.BULK_DERIV_URLS[venue]) as resp:
                            payload = await resp.json(content_type=None)
                        self._apply_bulk_deriv(venue, payload)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        errors.report('fetcher._bulk_deriv_loop', e, f"{venue} bulk tickers failed")
                await asyncio.sleep(self.BULK_DERIV_INTERVAL_SEC)

    COINBASE_PRODUCTS_URL = 'https://api.coinbase.com/api/v3/brokerage/market/products?product_type=SPOT'
    COINBASE_PRODUCTS_INTERVAL_SEC = 60

    async def _coinbase_prices_loop(self):
        """
        Last prices of every Coinbase spot product in one public call a minute: the Coinbase premium of a coin whose
        live trades are older than coinbase_max_age_sec (thin USD books trade minutes apart) comes from it.
        """
        import aiohttp
        if 'coinbase' not in CONFIG.venues.enabled:
            return
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            while self._running:
                # only the universe's products (the full list is ~1.2 MB: 20 KB/s of a link that is the constraint)
                ids = self.symbol_map.natives('coinbase')
                if not ids:
                    await asyncio.sleep(self.COINBASE_PRODUCTS_INTERVAL_SEC)
                    continue
                try:
                    async with session.get(self.COINBASE_PRODUCTS_URL, params=[('product_ids', i) for i in ids]) as resp:
                        payload = await resp.json(content_type=None)
                    now_ms = time.time() * 1000
                    for p in payload.get('products') or []:
                        market = self.symbol_map.lookup('coinbase', p.get('product_id', ''))
                        md = self.markets.get(market.key) if market is not None else None
                        try:
                            price = float(p.get('price') or 0)
                        except (TypeError, ValueError):
                            price = 0.0
                        if md is None or price <= 0 or p.get('trading_disabled'):
                            continue
                        md.coinbase_rest_price = price / market.multiplier * self.symbol_map.key_multiplier.get(market.key, 1.0)
                        md.coinbase_rest_ts = now_ms
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.info(f"Coinbase products failed ({type(e).__name__} {e})")
                await asyncio.sleep(self.COINBASE_PRODUCTS_INTERVAL_SEC)

    def _apply_bulk_deriv(self, venue: str, payload: dict):
        def num(value) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0
        if venue == 'bybit':
            for t in (payload.get('result') or {}).get('list', []):
                market = self.symbol_map.lookup('bybit', t.get('symbol', ''))
                if market is None:
                    continue
                hours = num(t.get('fundingIntervalHour')) or 8.0
                funding = t.get('fundingRate')
                # singleOpenInterestValue: one side, comparable with the other venues
                oi = num(t.get('singleOpenInterestValue')) or num(t.get('openInterestValue'))
                self.on_deriv(market, oi_usd=oi or None, mark=num(t.get('markPrice')) or None,
                              funding_8h=num(funding) * 8 / hours if funding not in (None, '') else None)
        elif venue == 'bitget':
            for t in payload.get('data') or []:
                market = self.symbol_map.lookup('bitget', t.get('symbol', ''))
                if market is None:
                    continue
                mark = num(t.get('markPrice'))
                # holdingAmount is in coins; funding comes from current-fund-rate (it knows each interval)
                self.on_deriv(market, oi_usd=num(t.get('holdingAmount')) * mark or None, mark=mark or None)
        elif venue == 'bitget_funding':
            for t in payload.get('data') or []:
                market = self.symbol_map.lookup('bitget', t.get('symbol', ''))
                funding = t.get('fundingRate')
                if market is None or funding in (None, ''):
                    continue
                hours = num(t.get('fundingRateInterval')) or 8.0
                self.on_deriv(market, funding_8h=num(funding) * 8 / hours)

    DERIV_CACHE_MS = 10_000

    def deriv_snapshot(self, key: str, now_ms: Optional[float] = None) -> Dict[str, float]:
        """
        Aggregated positioning across venues: OI change over 5m / 1h (each venue's % change weighted by its current
        OI in USD, so unit and contract-size differences cancel), OI-weighted 8h funding, venues reporting.
        Cached per coin for DERIV_CACHE_MS: the inputs update every 10-60s, and recomputing all venues' windows
        for 300 coins on every 2s Tier-0 pass was a tenth of the event loop's busy time (profiled).
        """
        now_ms = now_ms or time.time() * 1000
        cached = self._deriv_cache.get(key)
        if cached is not None and now_ms - cached[0] < self.DERIV_CACHE_MS:
            return cached[1]
        out = self._deriv_snapshot(key, now_ms)
        self._deriv_cache[key] = (now_ms, out)
        return out

    def _deriv_snapshot(self, key: str, now_ms: float) -> Dict[str, float]:
        states = self.venue_derivs.get(key, {})
        # None, not 0, while no venue has the history for a window yet (0 would read "OI flat")
        out = {'agg_oi_change_5m': None, 'agg_oi_change_1h': None, 'agg_funding_8h': None, 'oi_venues': 0}
        for label, window in (('agg_oi_change_5m', 300_000), ('agg_oi_change_1h', 3_600_000)):
            num = den = 0.0
            for state in states.values():
                change = _pct_change(state.samples, now_ms, window)
                if change is not None and state.oi_usd:
                    num += change * state.oi_usd
                    den += state.oi_usd
            out[label] = num / den if den else None
        num = den = 0.0
        for state in states.values():
            if state.funding_8h is not None and state.oi_usd and now_ms - state.ts < 600_000:
                num += state.funding_8h * state.oi_usd
                den += state.oi_usd
        out['agg_funding_8h'] = num / den if den else None
        out['oi_venues'] = sum(1 for s in states.values() if s.oi_usd and now_ms - s.ts < 600_000)
        return out

    def _binance_to_ccxt_symbol(self, binance_symbol: str) -> Optional[str]:
        if binance_symbol.endswith('USDT'):
            return f"{binance_symbol[:-4]}/USDT:USDT"
        return None

    def _ccxt_to_binance_symbol(self, ccxt_symbol: str) -> Optional[str]:
        if ccxt_symbol.endswith(':USDT'):
            return f"{ccxt_symbol.split('/')[0]}USDT"
        return None

    # ------------------------------------------------------------------ positioning (top trader ratio)

    # ------------------------------------------------------------------ symbols / baselines

    async def fetch_top_symbols(self) -> List[str]:
        """The universe: the candidates' data-complete subset (fetch_candidates -> select_universe)."""
        return self.select_universe(await self.fetch_candidates())

    async def fetch_candidates(self) -> List[str]:
        """
        USD-M perpetuals above the volume floor, most liquid first; refreshes the reference prices (the other venues'
        mapping check), the spreads (bookTicker, weight 5) and the ids of every USDT perpetual (market baseline).
        """
        tickers = await self._rest_call(self.futures_exchange, 'fetch_tickers', priority=0, weight=40)
        quote = CONFIG.exchange.quote_currency
        excluded_types = set(CONFIG.exchange.excluded_underlying_types)
        excluded = 0

        usdt_pairs = []
        for s, t in tickers.items():
            if not (s.endswith(f"/{quote}") or s.endswith(f"/{quote}:{quote}")):
                continue
            market = self.futures_exchange.markets.get(s) or {}
            pinned = market.get('base') in CONFIG.exchange.pinned_bases
            if not pinned and (market.get('info', {}).get('underlyingType') in excluded_types or
                               market.get('base') in CONFIG.exchange.excluded_bases):
                excluded += 1
                continue
            if market.get('swap') is False:
                continue
            info = t.get('info', {})
            quote_vol_raw = (
                t.get('quoteVolume') or t.get('quoteAssetVolume') or
                info.get('quoteVolume') or info.get('quoteAssetVolume') or 0
            )
            try:
                quote_vol = float(quote_vol_raw)
            except (TypeError, ValueError):
                quote_vol = 0.0
            is_active = t.get('active', info.get('active', True))
            if (pinned or quote_vol >= CONFIG.exchange.min_24h_quote_volume_usd) and is_active:
                # pinned coins first (CONFIG.exchange.pinned_bases), then by volume
                usdt_pairs.append((s, float('inf') if pinned else quote_vol))

        # Last prices of the universe: the reference for the other venues' symbol mapping check
        self.reference_prices = {s: float(t['last']) for s, t in tickers.items() if t.get('last')}
        usdt_pairs.sort(key=lambda x: x[1], reverse=True)
        by_id = {m.get('id'): s for s, m in self.futures_exchange.markets.items()}
        # Every USDT perpetual except stocks / pre-IPO: the market baseline of the journal (universe snapshots)
        self.baseline_ids = {m.get('id') for s, m in self.futures_exchange.markets.items()
                             if s.endswith(f"/{quote}:{quote}") and m.get('swap') is not False
                             and (m.get('info') or {}).get('underlyingType') not in excluded_types}
        try:
            book = await self._rest_call(self.futures_exchange, 'fapiPublicGetTickerBookTicker', priority=0, weight=5)
            spreads = {}
            for b in book or []:
                bid, ask = float(b.get('bidPrice') or 0), float(b.get('askPrice') or 0)
                if bid > 0 and ask >= bid and b.get('symbol') in by_id:
                    spreads[by_id[b['symbol']]] = (ask - bid) / ((ask + bid) / 2)
            self.spreads = spreads
        except RATE_LIMIT_ERRORS:
            raise
        except Exception as e:
            logger.warning(f"Spreads unavailable for the universe selection ({type(e).__name__} {e}); previous kept")
        logger.info(f"Universe candidates: {len(usdt_pairs)} perpetuals >= ${CONFIG.exchange.min_24h_quote_volume_usd:,.0f} "
                    f"24h volume (excluded {excluded} stock / pre-IPO contracts)")
        return [s for s, _ in usdt_pairs]

    def select_universe(self, candidates: List[str]) -> List[str]:
        """
        The most liquid candidates with complete data (CONFIG.exchange): a Binance spot pair, enough other futures
        venues, enough history, a tradable spread; at most max_pairs. Venue coverage comes from every venue's
        instrument list (SymbolMap.coverage), so it is known for coins that are not in the universe yet.
        """
        cfg = CONFIG.exchange
        markets = {s: self.futures_exchange.markets[s] for s in candidates if s in self.futures_exchange.markets}
        coverage = self.symbol_map.coverage(markets)
        now_ms = time.time() * 1000
        excluded: Dict[str, int] = {}
        selected: List[str] = []
        for s in candidates:
            if s not in markets:
                continue
            if markets[s].get('base') in cfg.pinned_bases:
                selected.append(s)               # pinned: in the universe whatever its data coverage
                continue
            futures_venues = [v for v in coverage.get(s, []) if v not in SPOT_VENUES]
            listed = int((markets[s].get('info') or {}).get('onboardDate') or 0)
            spread = self.spreads.get(s)
            reason = None
            if cfg.require_spot and not self._spot_symbol_for(s) and 'bybit_spot' not in coverage.get(s, []):
                reason = 'no spot pair'
            elif len(futures_venues) < cfg.min_futures_venues:
                reason = f'< {cfg.min_futures_venues} other futures venues'
            elif listed and now_ms - listed < cfg.min_listing_days * 86_400_000:
                reason = f'listed < {cfg.min_listing_days}d'
            elif spread is not None and spread > cfg.max_spread:
                reason = f'spread > {cfg.max_spread:.2%}'
            if reason:
                excluded[reason] = excluded.get(reason, 0) + 1
                continue
            selected.append(s)
            if len(selected) >= cfg.max_pairs:
                break
        self.whales.set_ranks(selected)
        logger.info(f"Universe: {len(selected)} coins with complete data of {len(candidates)} candidates; "
                    f"excluded {excluded}")
        return selected

    def _to_spot_symbol(self, futures_symbol: str) -> str:
        """Convert futures symbol (BTC/USDT:USDT) to spot symbol (BTC/USDT)."""
        if ':' in futures_symbol:
            return futures_symbol.split(':')[0]
        return futures_symbol

    def _normalize_1000x_symbol(self, futures_symbol: str) -> str:
        """Normalize 1000x futures symbol to spot equivalent, e.g. 1000PEPE/USDT:USDT -> PEPE/USDT."""
        base = self._to_spot_symbol(futures_symbol)
        if base.startswith('1000') and '/' in base:
            return base[4:]
        return base

    def needs_alt_spot(self, key: str) -> bool:
        """A universe coin whose spot market is Bybit's (no Binance spot pair): its Bybit spot trades are streamed."""
        return key in self.markets and not self._spot_symbol_for(key) and \
            'bybit_spot' in self.symbol_map.venues_of(key)

    def _spot_symbol_for(self, futures_symbol: str) -> Optional[str]:
        """Spot pair for a futures symbol: same name, else the un-prefixed 1000x name (1000PEPE -> PEPE)."""
        for candidate in (self._to_spot_symbol(futures_symbol), self._normalize_1000x_symbol(futures_symbol)):
            market = self.spot_exchange.markets.get(candidate)
            if market and market.get('active', True):
                return candidate
        return None

    def get_volume_multiplier(self, symbol: str) -> float:
        """Returns 1000.0 for 1000x tokens, 1.0 otherwise."""
        base = self._to_spot_symbol(symbol)
        if base.startswith('1000') and '/' in base:
            return 1000.0
        return 1.0

    async def _fetch_klines(self, market: str, symbol: Optional[str], interval: Optional[str] = None,
                            limit: Optional[int] = None) -> List:
        # Raw Binance klines (not fetch_ohlcv): they carry quote volume and taker buy quote volume
        exchange = self.spot_exchange if market == 'spot' else self.futures_exchange
        if not symbol or symbol not in exchange.markets:
            return []
        method = 'publicGetKlines' if market == 'spot' else 'fapiPublicGetKlines'
        limit = limit or CONFIG.timeframe.rest_lookback_candles
        try:
            return await self._rest_call(exchange, method, {
                'symbol': exchange.market(symbol)['id'],
                'interval': interval or CONFIG.timeframe.rest_timeframe,
                'limit': limit,
            }, priority=0, weight=2 if market == 'spot' else
                # Binance futures klines: 1 below 100 candles, 2 to 499, 5 to 1000, 10 above (the 600-minute seed is 5)
                1 if limit < 100 else 2 if limit < 500 else 5 if limit <= 1000 else 10)
        except RATE_LIMIT_ERRORS:
            raise
        except Exception as e:
            errors.report('fetcher._fetch_klines', e, f"Klines fetch skipped for {symbol}")
            return []

    async def fetch_minute_klines(self, futures_symbol: str, start_ms: int, count: int) -> Optional[List]:
        """
        `count` futures 1m klines starting with the first full minute after start_ms (journal outcomes), so the
        signal's own minute never leaks into the outcome. None when the request failed (retry later), [] when the
        exchange has no data.
        """
        try:
            return await self._rest_call(self.futures_exchange, 'fapiPublicGetKlines', {
                'symbol': self.futures_exchange.market(futures_symbol)['id'],
                'interval': '1m',
                'startTime': -(-start_ms // 60_000) * 60_000,
                'limit': count,
            }, priority=2, weight=1 if count < 100 else 2)
        except Exception as e:
            errors.report('fetcher.fetch_minute_klines', e, f"Minute klines failed for {futures_symbol}")
            return None

    async def _fetch_oi_history(self, futures_symbol: str) -> List:
        # /futures/data/openInterestHist: weight 0, own limit of 1000 requests / 5 min
        try:
            return await self._rest_call(
                self.futures_exchange, 'fetch_open_interest_history', futures_symbol,
                CONFIG.timeframe.rest_timeframe, None, CONFIG.timeframe.rest_lookback_candles, priority=0, weight=0,
            )
        except RATE_LIMIT_ERRORS:
            raise
        except Exception as e:
            errors.report('fetcher._fetch_oi_history', e, f"OI history skipped for {futures_symbol}")
            return []

    async def _seed_minutes(self, symbol: str, md: MarketData):
        """The streams' 1m history (futures 4h, spot 1h) from REST at start-up / when a coin joins (MarketData.seed_minutes)."""
        now_ms = int(time.time() * 1000)
        spot_symbol = self._spot_symbol_for(symbol)
        jobs = [('futures', symbol, md.minute_klines.maxlen)]
        if spot_symbol:
            jobs.append(('spot', spot_symbol, md.spot_minute_klines.maxlen))
        for market, sym, limit in jobs:
            rows = await self._fetch_klines(market, sym, '1m', limit + 1)
            md.seed_minutes(market, [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[7]),
                                      float(k[10])] for k in rows or []], now_ms)
            if market == 'futures' and self.streams_started_ms:
                # Binance's taker flow of the 15 minutes the streams did not see (a minute that closed before they
                # started): Tier-0's 5m windows are valid at once (the other venues fill in live)
                for k in rows or []:
                    t = int(k[0])
                    if self.streams_started_ms - 15 * 60_000 <= t and t + 60_000 <= self.streams_started_ms:
                        buy, total = float(k[10]), float(k[7])
                        self.flow.seed_minute('binance', symbol, t, buy, max(0.0, total - buy), int(k[8]))

    async def _seed_oi(self, symbol: str, md: MarketData):
        """
        The last day of 5m OI history (289 points, weight 0): Tier-0's 5m OI change and the entries' 1h OI
        confirmation work from the start (with 3 points every confirmation of the first hour had no OI reading), and
        the OI robot's 24h OI growth (MarketData.oi_5m).
        """
        binance_symbol = self._ccxt_to_binance_symbol(symbol)
        if not binance_symbol:
            return
        try:
            rows = await self._rest_call(self.futures_exchange, 'fapiDataGetOpenInterestHist',
                                         {'symbol': binance_symbol, 'period': '5m', 'limit': 289}, priority=1, weight=0)
        except RATE_LIMIT_ERRORS:
            raise
        except Exception as e:
            errors.report('fetcher._seed_oi', e, f"OI history seed skipped for {symbol}")
            return
        # openInterestHist timestamps are period END times: the OI at that moment
        points = [(int(r['timestamp']), float(r.get('sumOpenInterest') or 0.0)) for r in rows or []]
        md.seed_oi(points)
        # the same hour (coins) under Binance's live samples in the venue aggregate: agg 1h OI works from the start
        state = self.venue_derivs.setdefault(symbol, {}).setdefault('binance', VenueDeriv())
        merged = dict(p for p in points if p[1]) | dict(state.samples)
        state.samples.clear()
        state.samples.extend(sorted(merged.items())[-state.samples.maxlen:])

    def load_htf_background(self, symbol: str):
        """load_htf without waiting for it (at most one request set per coin in flight)."""
        if symbol in self._htf_loading:
            return
        self._htf_loading.add(symbol)
        task = self._spawn(self.load_htf(symbol))
        task.add_done_callback(lambda _t: self._htf_loading.discard(symbol))

    async def load_htf(self, symbol: str) -> bool:
        """
        1h klines (~4 days) and 1h open-interest history of one card coin for the level map (zones.py), refreshed at
        most every zones.htf_refresh_sec. Klines weigh 1 (limit < 100), openInterestHist 0 (own 1000 / 5 min limit).
        """
        md = self.markets.get(symbol)
        binance_symbol = self._ccxt_to_binance_symbol(symbol)
        if md is None or not binance_symbol or time.time() - md.htf_loaded < CONFIG.zones.htf_refresh_sec:
            return False
        n = CONFIG.zones.htf_candles
        try:
            klines, oi, k5, k1d, k30 = await asyncio.gather(
                self._rest_call(self.futures_exchange, 'fapiPublicGetKlines',
                                {'symbol': binance_symbol, 'interval': '1h', 'limit': n}, priority=1, weight=1),
                self._rest_call(self.futures_exchange, 'fapiDataGetOpenInterestHist',
                                {'symbol': binance_symbol, 'period': '1h', 'limit': min(n, 500)}, priority=2, weight=0),
                # 4 days of 5m candles (limit > 1000 weighs 10; card coins only, hourly)
                self._rest_call(self.futures_exchange, 'fapiPublicGetKlines',
                                {'symbol': binance_symbol, 'interval': '5m', 'limit': 4 * 288}, priority=1, weight=10),
                # the higher-timeframe range of the scenario card (limit 100-500 weighs 2, 500-1000 weighs 5)
                self._rest_call(self.futures_exchange, 'fapiPublicGetKlines',
                                {'symbol': binance_symbol, 'interval': '1d', 'limit': 200}, priority=1, weight=2),
                self._rest_call(self.futures_exchange, 'fapiPublicGetKlines',
                                {'symbol': binance_symbol, 'interval': '1h', 'limit': 720}, priority=1, weight=5),
            )
        except Exception as e:
            errors.report('fetcher.load_htf', e, f"1h history failed for {symbol}")
            md.htf_loaded = time.time() - CONFIG.zones.htf_refresh_sec + 300  # retry in 5 min
            return False
        md.htf_klines = [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[7]), float(k[10])]
                         for k in self._closed_only(klines or [])]
        # OI in COINS: in USD a rally with no new contract read as "positions opened" (phantom liquidation clusters)
        md.htf_oi = [(int(r['timestamp']), float(r.get('sumOpenInterest') or 0.0)) for r in (oi or [])]
        md.htf_5m = [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[7]), float(k[10])]
                     for k in self._closed_only(k5 or [])]
        md.htf_1d = [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[7])]
                     for k in self._closed_only(k1d or [])]
        md.htf_1h_30d = [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[7])]
                         for k in self._closed_only(k30 or [])]
        md.htf_loaded = time.time()
        return True

    async def chart_candles(self, symbol: str) -> Optional[Dict]:
        """15m and 5m candles of any futures symbol for the web chart (coins no longer in the universe)."""
        binance_symbol = self._ccxt_to_binance_symbol(symbol)
        if not binance_symbol:
            return None
        try:
            k15, k5, k1h = await asyncio.gather(*[
                self._rest_call(self.futures_exchange, 'fapiPublicGetKlines',
                                {'symbol': binance_symbol, 'interval': tf, 'limit': 99}, priority=0, weight=1)
                for tf in ('15m', '5m', '1h')])
        except Exception as e:
            errors.report('fetcher.chart_candles', e, f"Chart candles failed for {symbol}")
            return None
        rows = lambda ks: [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[7]), float(k[10])]
                           for k in ks or []]
        c15 = rows(k15)
        return {'symbol': symbol, 'price': c15[-1][4] if c15 else None, 'atr': None, 'candles_15m': c15,
                'candles_5m': rows(k5), 'candles_1h': rows(k1h), 'zones': [], 'cards': [], 'liquidations': [], 'htf_loaded': 0,
                'note': 'coin is not in the current universe: no level map'}

    @staticmethod
    def _closed_only(klines: List) -> List:
        """
        Drop the in-progress candle (and one that closed < 3s ago, which REST may still be completing): frames hold
        closed candles only; a partial REST row taken for a closed one gave candles with a few seconds of volume.
        """
        cutoff = time.time() * 1000 - 3000
        return [k for k in klines if int(k[6]) < cutoff]

    async def _load_frame(self, market: str, futures_symbol: str) -> Tuple[pl.DataFrame, int]:
        """REST candles (closed only) for one market as RAW_SCHEMA plus the open time of the newest one."""
        if market == 'spot':
            klines = self._closed_only(await self._fetch_klines('spot', self._spot_symbol_for(futures_symbol)))
            return self._klines_to_df(klines), self._last_closed_open_time(klines)

        klines, oi_history = await asyncio.gather(
            self._fetch_klines('futures', futures_symbol), self._fetch_oi_history(futures_symbol)
        )
        klines = self._closed_only(klines)
        df = self._attach_oi_history(self._klines_to_df(klines), oi_history)
        return df, self._last_closed_open_time(klines)

    def _new_market_data(self, s: str) -> MarketData:
        return MarketData(
            symbol=s,
            spot_df=empty_raw_frame(),
            futures_df=empty_raw_frame(),
            volume_multiplier=self.get_volume_multiplier(s),
            spot_symbol=self._spot_symbol_for(s) or "",
            listed_ms=int((self.futures_exchange.markets.get(s) or {}).get('info', {}).get('onboardDate') or 0),
        )

    def create_market_data(self, symbols: List[str]) -> Dict[str, MarketData]:
        """Empty MarketData per symbol so streams can start before the REST history arrives."""
        self.markets = {s: self._new_market_data(s) for s in symbols}
        self.flow.register(symbols)
        self.symbol_map.set_universe({s: self.futures_exchange.markets[s] for s in symbols})
        return self.markets

    def apply_universe(self, symbols: List[str], keep: Iterable[str] = ()) -> Tuple[List[str], List[str]]:
        """
        Switch to a new universe: new symbols get MarketData, dropped ones are removed unless listed in `keep`
        (open cards finish on the old data). Returns (added, removed); the caller restarts streams and loads history.
        """
        keep = set(keep)
        added = [s for s in symbols if s not in self.markets]
        removed = [s for s in self.markets if s not in symbols and s not in keep]
        for s in added:
            self.markets[s] = self._new_market_data(s)
        for s in removed:
            self.markets.pop(s, None)
            self.flow.unregister(s)
            self.depth.forget(s)
            self.footprint.disable(s)
            self.venue_derivs.pop(s, None)
        self.flow.register(added)
        self.symbol_map.set_universe({s: self.futures_exchange.markets[s] for s in self.markets
                                      if s in self.futures_exchange.markets})
        return added, removed

    async def _hourly_candles_loop(self):
        """
        1h candles (limit 200 = ~8 days, weight 2) of every universe coin, refreshed a minute after each hour: the
        pools of previous day / week / sessions and the coins' trends must exist for all 300 coins, not only for card
        coins (~600 weight per hour against a ~1400 / minute budget). Waits for the 15m history first (priority).
        """
        cfg = CONFIG.strategies
        while self._running and self.baselines_loaded() < len(self.markets) * 0.9:
            await asyncio.sleep(10)
        while self._running:
            started = time.time()
            symbols = [s for s, md in self.markets.items() if started - md.h1_loaded >= cfg.h1_refresh_sec - 120]
            sem = asyncio.Semaphore(8)

            async def one(symbol: str):
                binance_symbol = self._ccxt_to_binance_symbol(symbol)
                md = self.markets.get(symbol)
                if not binance_symbol or md is None:
                    return
                parse = lambda rows: [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[7]),
                                       float(k[10])] for k in self._closed_only(rows or [])]
                async with sem:
                    try:
                        # limit 499 weighs 2 like 200 did: the long history of crypto_maniac's 1h systems
                        rows = await self._rest_call(self.futures_exchange, 'fapiPublicGetKlines',
                                                     {'symbol': binance_symbol, 'interval': '1h',
                                                      'limit': cfg.long_history_candles}, priority=1, weight=2)
                        rows_15m = await self._rest_call(self.futures_exchange, 'fapiPublicGetKlines',
                                                         {'symbol': binance_symbol, 'interval': '15m',
                                                          'limit': cfg.long_history_candles}, priority=1, weight=2)
                    except Exception as e:
                        errors.report('fetcher.candles_1h', e, f"1h / 15m candles failed for {symbol}")
                        return
                # the long histories as float arrays (~28 KB a coin instead of ~150 KB of candle lists: 6 GB box)
                hourly = parse(rows)
                md.h1 = hourly[-cfg.h1_candles:]
                md.h1_long = np.asarray(hourly, dtype=np.float64)
                md.m15_long = np.asarray(parse(rows_15m), dtype=np.float64)
                md.h1_loaded = time.time()

            await asyncio.gather(*(one(s) for s in symbols))
            if symbols:
                logger.info(f"1h candles loaded for {sum(1 for s in symbols if self.markets.get(s) and self.markets[s].h1)} "
                            f"of {len(symbols)} symbols in {time.time() - started:.0f}s")
            # The histories loaded so far are long-lived: move them out of the cyclic GC's reach. Full (gen 2)
            # collections scanned millions of candle lists and stalled the loop 1-3s (watchdog: 'gc 3.1s (gen 2)');
            # frozen objects are still freed by reference counting when dropped
            gc.freeze()
            logger.debug(f"gc: {gc.get_freeze_count()} objects frozen")
            # next pass one minute after the next full hour (the new 1h candle is closed then)
            now = time.time()
            await asyncio.sleep(max(60.0, 3600 - now % 3600 + 60))

    async def _h4_candles_loop(self):
        """200 closed 4h candles of every universe coin (limit 200, weight 2) after each 4h close and for joining coins."""
        while self._running and self.baselines_loaded() < len(self.markets) * 0.9:
            await asyncio.sleep(10)
        while self._running:
            now = time.time()
            slot = int(now // 14_400)
            symbols = [s for s, md in self.markets.items() if md.h4_slot < slot]
            sem = asyncio.Semaphore(4)

            async def one(symbol: str):
                binance_symbol = self._ccxt_to_binance_symbol(symbol)
                md = self.markets.get(symbol)
                if not binance_symbol or md is None:
                    return
                async with sem:
                    try:
                        rows = await self._rest_call(self.futures_exchange, 'fapiPublicGetKlines',
                                                     {'symbol': binance_symbol, 'interval': '4h', 'limit': 200},
                                                     priority=2, weight=2)
                    except Exception as e:
                        errors.report('fetcher.candles_4h', e, f"4h candles failed for {symbol}")
                        return
                md.h4 = [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[7])]
                         for k in self._closed_only(rows or [])]
                md.h4_slot = slot

            if symbols and now - slot * 14_400 >= 60:
                await asyncio.gather(*(one(s) for s in symbols))
            await asyncio.sleep(300)

    async def _daily_candles_loop(self):
        """
        210 daily candles of every universe coin (limit 210, weight 2) once per UTC day, a minute after the daily close,
        and for coins that join: Connors' RSI(2) system reads daily closes (~240 weight a day).
        """
        while self._running and self.baselines_loaded() < len(self.markets) * 0.9:
            await asyncio.sleep(10)
        while self._running:
            now = time.time()
            day = int(now // 86400)
            symbols = [s for s, md in self.markets.items() if md.d1_day < day]
            sem = asyncio.Semaphore(4)

            async def one(symbol: str):
                binance_symbol = self._ccxt_to_binance_symbol(symbol)
                md = self.markets.get(symbol)
                if not binance_symbol or md is None:
                    return
                async with sem:
                    try:
                        rows = await self._rest_call(self.futures_exchange, 'fapiPublicGetKlines',
                                                     {'symbol': binance_symbol, 'interval': '1d', 'limit': 370},
                                                     priority=2, weight=2)
                    except Exception as e:
                        errors.report('fetcher.candles_1d', e, f"daily candles failed for {symbol}")
                        return
                md.d1 = [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[7])]
                         for k in self._closed_only(rows or [])]
                md.d1_day = day

            if symbols and now - day * 86400 >= 60:
                await asyncio.gather(*(one(s) for s in symbols))
                logger.info(f"Daily candles: {sum(1 for s in symbols if len(self.markets.get(s).d1 or []) >= 202) if symbols else 0}"
                            f" of {len(symbols)} coins have >= 202 closed days")
            await asyncio.sleep(300)

    async def _dominance_loop(self):
        """
        BTC and USDT dominance (CoinGecko /global, free, no key) every 5 minutes: rising together = risk-off, falling
        together = money into altcoins (practice, not a measured rule: journaled as `_dom` on every entry until the
        journal can judge it; the archive has no dominance history).
        """
        import urllib.request
        url = 'https://api.coingecko.com/api/v3/global'
        while self._running:
            try:
                def fetch():
                    req = urllib.request.Request(url, headers={'User-Agent': 'pump-scanner'})
                    with urllib.request.urlopen(req, timeout=20) as resp:
                        return json.load(resp)
                data = (await asyncio.to_thread(fetch)).get('data') or {}
                pct = data.get('market_cap_percentage') or {}
                if 'btc' in pct and 'usdt' in pct:
                    self.dominance.append((time.time(), float(pct['btc']), float(pct['usdt'])))
            except Exception as e:
                errors.report('fetcher.dominance', e)
            await asyncio.sleep(300)

    def htf_bias(self, md: 'MarketData', now_ms: float) -> Optional[Dict]:
        """The top-down bias of the coin and of BTC (strategies/bias.py) from their closed daily / 4h / weekly candles:
        {'coin': {...}, 'btc': {...}, 'range_mid': the coin's 20-day range middle}."""
        from strategies import bias as htf
        try:
            out = {}
            for tag, m in (('coin', md), ('btc', self.markets.get('BTC/USDT:USDT'))):
                if m is None:
                    continue
                st = htf.state(htf.closed(list(m.d1), 86_400_000, now_ms), htf.closed(list(m.h4), 14_400_000, now_ms),
                               htf.closed(list(m.w1), 7 * 86_400_000, now_ms))
                out[tag] = htf.describe(st, htf.bias_of(st))
                out[tag]['bias_daily'] = htf.bias_of(st, daily_method=True)     # the tide of daily methods
                if tag == 'coin':
                    out['range_mid'] = htf.range_mid(st)
            return out
        except Exception as e:
            errors.report('fetcher.htf_bias', e, md.symbol)
            return None

    def dominance_reading(self) -> Optional[Dict]:
        """{btc_d, usdt_d, btc_d_1h, usdt_d_1h, btc_d_4h, usdt_d_4h} (changes in percentage points) or None."""
        if not self.dominance:
            return None
        now, btc, usdt = self.dominance[-1]
        out = {'btc_d': round(btc, 3), 'usdt_d': round(usdt, 3)}
        for tag, sec in (('1h', 3600), ('4h', 14400)):
            past = [x for x in self.dominance if now - x[0] >= sec - 150]
            if past:
                out[f'btc_d_{tag}'] = round(btc - past[-1][1], 3)
                out[f'usdt_d_{tag}'] = round(usdt - past[-1][2], 3)
        return out

    async def _day_pocs_loop(self):
        """
        Each universe coin's POCs of its last 4 completed UTC days, from 5 days of 5m candles (limit 1440, weight 10),
        once per UTC day a few minutes after the close and for coins that join (~700 weight a day).
        """
        from zones import day_poc
        while self._running and self.baselines_loaded() < len(self.markets) * 0.9:
            await asyncio.sleep(10)
        while self._running:
            now = time.time()
            day = int(now // 86400)
            symbols = [s for s, md in self.markets.items() if md.day_pocs_day < day]
            sem = asyncio.Semaphore(2)

            async def one(symbol: str):
                binance_symbol = self._ccxt_to_binance_symbol(symbol)
                md = self.markets.get(symbol)
                if not binance_symbol or md is None:
                    return
                async with sem:
                    try:
                        rows = await self._rest_call(self.futures_exchange, 'fapiPublicGetKlines',
                                                     {'symbol': binance_symbol, 'interval': '5m', 'limit': 1440},
                                                     priority=2, weight=10)
                    except Exception as e:
                        errors.report('fetcher.day_pocs', e, f"5m candles failed for {symbol}")
                        return
                candles = [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[7])]
                           for k in self._closed_only(rows or [])]
                md.day_pocs = day_poc(candles, day * 86_400_000)
                md.day_pocs_day = day

            if symbols and now - day * 86400 >= 180:
                await asyncio.gather(*(one(s) for s in symbols))
                logger.info(f"Day POCs: {sum(1 for s in symbols if self.markets.get(s) and self.markets[s].day_pocs)}"
                            f" of {len(symbols)} coins")
            await asyncio.sleep(300)

    async def _weekly_candles_loop(self):
        """
        Weekly candles of every universe coin (limit 60, weight 1): the weekly trend reference (weekly_ref), loaded
        once per weekly candle (Monday 00:00 UTC) and for coins that join; hourly check, ~150 weight a week.
        """
        from strategies.structure import weekly_ref
        while self._running and self.baselines_loaded() < len(self.markets) * 0.9:
            await asyncio.sleep(10)
        while self._running:
            now = time.time()
            week_start = (now // 86400 - (now // 86400 + 3) % 7) * 86400      # this week's Monday 00:00 UTC
            symbols = [s for s, md in self.markets.items() if md.w1_loaded < week_start + 60]
            sem = asyncio.Semaphore(4)

            async def one(symbol: str):
                binance_symbol = self._ccxt_to_binance_symbol(symbol)
                md = self.markets.get(symbol)
                if not binance_symbol or md is None:
                    return
                async with sem:
                    try:
                        rows = await self._rest_call(self.futures_exchange, 'fapiPublicGetKlines',
                                                     {'symbol': binance_symbol, 'interval': '1w', 'limit': 60},
                                                     priority=2, weight=1)
                    except Exception as e:
                        errors.report('fetcher.candles_1w', e, f"weekly candles failed for {symbol}")
                        return
                closed = self._closed_only(rows or [])
                md.w1_ref = weekly_ref([float(k[4]) for k in closed])
                md.w1 = [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[7])] for k in closed]
                md.w1_loaded = time.time()

            if symbols and now >= week_start + 60:
                await asyncio.gather(*(one(s) for s in symbols))
                logger.info(f"Weekly trend: {sum(1 for s in symbols if self.markets.get(s) and self.markets[s].w1_ref)} "
                            f"of {len(symbols)} coins have >= {CONFIG.strategies.trend_w_ema} closed weeks")
            await asyncio.sleep(3600)

    async def _seasonal_loop(self):
        """
        Each coin's time-of-day volume / volatility profile from its last 4 weeks of 1h candles (limit 672, weight 5),
        once a day after the 15m history (indicators.seasonal_factors): Tier-0's RVOL and z-scores compare a minute
        with the same hour instead of the flat 24h average. New coins get theirs on the next pass.
        """
        while self._running and self.baselines_loaded() < len(self.markets) * 0.9:
            await asyncio.sleep(10)
        while self._running:
            started = time.time()
            sem = asyncio.Semaphore(4)

            async def one(symbol: str):
                md = self.markets.get(symbol)
                if md is None:
                    return
                async with sem:
                    rows = await self._fetch_klines('futures', symbol, '1h', 672)
                md.season = seasonal_factors([[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]),
                                               float(k[7]), float(k[10])] for k in self._closed_only(rows or [])])

            await asyncio.gather(*(one(s) for s in list(self.markets)))
            logger.info(f"Seasonal profiles: {sum(1 for md in self.markets.values() if md.season)} of "
                        f"{len(self.markets)} coins in {time.time() - started:.0f}s")
            await asyncio.sleep(24 * 3600)

    def baselines_loaded(self) -> int:
        return sum(1 for md in self.markets.values() if md.baseline_ready)

    async def fetch_rest_baselines(self, symbols: List[str]):
        """
        Background cold start: fill candle history symbol by symbol (highest volume first) with bounded
        concurrency plus a fixed delay; the RestGate budget keeps the burst below Binance's weight limit.
        Streams and Tier-0 already run meanwhile; a symbol joins phase scoring once its history is in.
        """
        semaphore = asyncio.Semaphore(CONFIG.rest.baseline_concurrency)
        started = time.time()
        await self._refresh_funding_info()
        try:
            await self._update_24h_volumes()
        except Exception as e:
            if not NETWORK.failed("Binance 24h volumes", e):
                logger.warning(f"24h volumes unavailable: {e}")

        async def fetch_symbol(futures_symbol: str):
            md = self.markets.get(futures_symbol)
            if md is None:
                return
            async with semaphore:
                try:
                    (spot_df, spot_final), (futures_df, futures_final) = await asyncio.gather(
                        self._load_frame('spot', futures_symbol), self._load_frame('futures', futures_symbol)
                    )
                    md.spot_df, md.futures_df = spot_df, futures_df
                    md.history_version += 1
                    await asyncio.gather(self._seed_oi(futures_symbol, md), self._seed_minutes(futures_symbol, md))
                    md.finalized_until = {'spot': max(md.finalized_until['spot'], spot_final),
                                          'futures': max(md.finalized_until['futures'], futures_final)}
                except Exception as e:
                    # Frames stay empty; the first kline row flags a backfill that retries the download
                    logger.warning(f"Failed to fetch baselines for {futures_symbol}: {e}")
                finally:
                    md.baseline_ready = True
                    done = sum(1 for s in symbols if s in self.markets and self.markets[s].baseline_ready)
                    if done % 50 == 0 or done == len(symbols):
                        logger.info(f"REST baselines: {done}/{len(symbols)}")
                    await asyncio.sleep(CONFIG.rest.baseline_delay_sec)

        await asyncio.gather(*[fetch_symbol(s) for s in symbols])
        logger.info(f"REST baselines loaded for {len(symbols)} symbols in {time.time() - started:.0f}s")
        # Long-lived start-up objects (frames' Python side, market lists, deques) leave the cyclic GC's scope: a
        # full collection over them paused the event loop for ~1s (watchdog: 'gc 1.1s (gen 2)'). No gc.collect()
        # first: that full collection on the loop was itself the ~1s pause
        gc.freeze()

    BACKFILL_DELAYS_SEC = (0, 5, 15, 45, 120, 300)

    def request_backfill(self, symbol: str, market: str, need_ts: int = 0):
        """
        Re-download a symbol's candles after a stream gap (reconnect, missed candle close); `need_ts` = open time of
        a candle the snapshot must contain (REST publishes a closed candle a few seconds late: retry until it does).
        """
        key = (symbol, market)
        if key in self._backfill_pending or not self._running or time.time() < self._backfill_retry_at.get(key, 0):
            return
        self._backfill_pending.add(key)
        self._spawn(self._backfill(symbol, market, need_ts))

    def _spawn(self, coro):
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def _backfill(self, symbol: str, market: str, need_ts: int = 0):
        key = (symbol, market)
        try:
            for delay in self.BACKFILL_DELAYS_SEC:
                await asyncio.sleep(delay)
                try:
                    async with self._backfill_semaphore:
                        df, final = await self._load_frame(market, symbol)
                        await asyncio.sleep(CONFIG.rest.baseline_delay_sec)
                except Exception as e:
                    errors.report('fetcher._backfill', e, f"Backfill attempt failed for {symbol} ({market})")
                    continue
                md = self.markets.get(symbol)
                if md is None:
                    return
                if df.is_empty() or final < need_ts:
                    continue   # the candle to replace is not published yet: next attempt
                # REST is the authority for the candles it has; only complete stream candles NEWER than the snapshot
                # (closed while it was in flight) are applied on top. Re-applying older stream rows put an incomplete
                # candle back over the correct REST one.
                for row in list(md.recent_closed[market]):
                    if row['timestamp'] > final:
                        df, _ = merge_live_candle(df, dict(row), row['timestamp'])
                md.set_frame(market, df)
                md.incomplete[market] = {ts for ts in md.incomplete[market] if ts > final}
                md.history_version += 1
                md.last_merged.pop(market, None)  # re-apply the live candle on top of the new snapshot
                md.finalized_until[market] = max(md.finalized_until[market], final)
                logger.debug(f"Backfilled {market} candles for {symbol}")
                return
            (logger.debug if NETWORK.down else logger.warning)(f"Backfill failed for {symbol} ({market}) after {len(self.BACKFILL_DELAYS_SEC)} attempts")
            self._backfill_retry_at[key] = time.time() + 600
        finally:
            self._backfill_pending.discard(key)

    @staticmethod
    def _last_closed_open_time(klines: List) -> int:
        now_ms = time.time() * 1000
        closed = [int(k[0]) for k in klines if int(k[6]) < now_ms]
        return max(closed) if closed else 0

    def _klines_to_df(self, klines: List) -> pl.DataFrame:
        """Binance kline rows -> RAW_SCHEMA (base volume in the instrument's own units)."""
        if not klines:
            return empty_raw_frame()
        # [openTime, open, high, low, close, volume, closeTime, quoteVolume, trades, takerBuyBase, takerBuyQuote, ignore]
        return pl.DataFrame({
            'timestamp': [int(k[0]) for k in klines],
            'open': [float(k[1]) for k in klines],
            'high': [float(k[2]) for k in klines],
            'low': [float(k[3]) for k in klines],
            'close': [float(k[4]) for k in klines],
            'volume': [float(k[5]) for k in klines],
            'quote_volume': [float(k[7]) for k in klines],
            'taker_delta': [2 * float(k[10]) - float(k[7]) for k in klines],
            'open_interest': [None] * len(klines),
        }, schema=RAW_SCHEMA)

    def _attach_oi_history(self, df: pl.DataFrame, oi_history: List) -> pl.DataFrame:
        """Put OI snapshots onto candles: openInterestHist timestamps are period END times, so 12:15:00 closes the 12:00 candle."""
        points = [
            ((int(h['timestamp']) - 1) // TIMEFRAME_MS * TIMEFRAME_MS, float(h['openInterestAmount']))
            for h in oi_history if h.get('timestamp') and h.get('openInterestAmount') is not None
        ]
        if df.is_empty() or not points:
            return df
        oi_df = pl.DataFrame(points, schema={'timestamp': pl.Int64, 'oi_hist': pl.Float64}, orient='row')
        oi_df = oi_df.unique(subset='timestamp', keep='last')
        return (
            df.join(oi_df, on='timestamp', how='left')
            .with_columns(pl.col('oi_hist').alias('open_interest'))
            .select(list(RAW_SCHEMA))
        )

    # ------------------------------------------------------------------ websockets

    async def start_websockets(self, symbols: List[str]):
        self._running = True
        await self._start_binance_streams(symbols)
        await self._start_venue_streams()
        self._tasks.append(asyncio.create_task(self._oi_loop()))
        self._tasks.append(asyncio.create_task(self._funding_info_loop()))
        self._tasks.append(asyncio.create_task(self._bulk_deriv_loop()))
        self._tasks.append(asyncio.create_task(self._coinbase_prices_loop()))
        self._tasks.append(asyncio.create_task(self._book_sync_loop()))
        self._tasks.append(asyncio.create_task(self._binance_rest_tickers_loop()))
        self._tasks.append(asyncio.create_task(self._hourly_candles_loop()))
        self._tasks.append(asyncio.create_task(self._seasonal_loop()))
        self._tasks.append(asyncio.create_task(self._weekly_candles_loop()))
        self._tasks.append(asyncio.create_task(self._daily_candles_loop()))
        self._tasks.append(asyncio.create_task(self._day_pocs_loop()))
        self._tasks.append(asyncio.create_task(self._dominance_loop()))
        self._tasks.append(asyncio.create_task(self._h4_candles_loop()))

    async def _start_binance_streams(self, symbols: List[str]):
        ids = {'spot': [], 'futures': []}
        self._binance_keys = {}
        for symbol in symbols:
            fut_id = self.futures_exchange.market(symbol)['id']
            ids['futures'].append(fut_id)
            self._binance_keys[('futures', fut_id)] = symbol
            spot_symbol = self._spot_symbol_for(symbol)
            if spot_symbol:
                spot_id = self.spot_exchange.market(spot_symbol)['id']
                ids['spot'].append(spot_id)
                self._binance_keys[('spot', spot_id)] = symbol
        logger.info(f"Starting Binance streams for {len(ids['spot'])} spot, {len(ids['futures'])} futures symbols")
        self.streams_started_ms = self.streams_started_ms or int(time.time() * 1000)
        # Bandwidth matters more than message counts here: the link to Binance measured ~150 KB/s in total and a
        # single socket ~40-70 KB/s, beyond which the server's buffer fills and it drops the connection. So:
        # only 1m klines (15m candles are built from them), no whole-market ticker arrays (funding / mark / 24h
        # volume come from REST), and every stream group split over several sockets.
        plans = [
            ('spot', 'Binance spot klines', [f"{i.lower()}@kline_1m" for i in ids['spot']], 120),
            ('futures', 'Binance futures klines', [f"{i.lower()}@kline_1m" for i in ids['futures']], 120),
            # Every taker order (CVD, sweeps, footprint, price) and all liquidations
            ('futures', 'Binance futures trades', [f"{i.lower()}@aggTrade" for i in ids['futures']] + ['!forceOrder@arr', '!contractInfo'], 40),
        ]
        for market, name, streams, per_socket in plans:
            stream = BinanceStream(self, self.symbol_map, market, streams, name)
            stream.subs_per_connection = per_socket
            self._binance_streams.append(stream)
            await stream.start()
        if not self._depth_streams:
            for k in range(CONFIG.depth.sockets):
                stream = BinanceStream(self, self.symbol_map, 'futures', [], f'Binance order books {k + 1}', 'futures_public')
                self._depth_streams.append(stream)
                await stream.start(dynamic=True)

    async def _start_venue_streams(self):
        for venue in CONFIG.venues.enabled:
            cls = VENUE_STREAMS.get(venue)
            if cls is None or not self.symbol_map.natives(venue):
                continue
            stream = cls(self, self.symbol_map)
            self.venue_streams[venue] = stream
            await stream.start(dynamic=venue == 'hyperliquid')

    async def restart_streams(self, symbols: List[str]):
        """After a universe change: re-subscribe every static stream to the new symbol set."""
        for stream in self._binance_streams:
            await stream.stop()
        self._binance_streams = []
        await self._start_binance_streams(symbols)
        for venue, stream in list(self.venue_streams.items()):
            await stream.restart(dynamic=venue == 'hyperliquid')

    # ------------------------------------------------------------------ stream sinks (hot path)

    def on_binance(self, market_type: str, stream: str, data, recv_ms: float):
        if isinstance(data, list):
            if stream.startswith('!miniTicker'):
                for t in data:
                    md = self.markets.get(self._binance_keys.get(('futures', t.get('s'))))
                    if md is not None:
                        md.record_ticker({'last': float(t['c']), 'quoteVolume': float(t['q'])}, t.get('E'))
            elif stream.startswith('!markPrice'):
                for m in data:
                    key = self._binance_keys.get(('futures', m.get('s')))
                    md = self.markets.get(key)
                    if md is None:
                        continue
                    md.mark_price, md.index_price = float(m['p']), float(m.get('i') or 0.0)
                    # r: the live estimate of the next funding rate; settlements run every 1/4/8h -> 8h-equivalent
                    rate = float(m.get('r') or 0.0) * 8 / self.funding_interval_hours.get(key, 8)
                    md.funding_rate = md.predicted_funding = rate
                    state = self.venue_derivs.setdefault(key, {}).setdefault('binance', VenueDeriv())
                    state.funding_8h, state.mark, state.ts = rate, md.mark_price, recv_ms
            return

        event = data.get('e')
        if event == 'aggTrade':
            key = self._binance_keys.get(('futures', data['s']))
            if key is None:
                return
            price = float(data['p'])
            usd = price * float(data['q'])
            side = -1 if data['m'] else 1  # m: buyer is maker -> taker SELL
            ts = int(data['T'])
            self.flow.trade('binance', key, ts, usd, side, recv_ms)
            self.sweeps.add('binance', key, ts, price, usd, side)
            md = self.markets.get(key)
            if md is not None:
                md.record_price(price, ts)
            if key in self.footprint.bucket:
                self.footprint.add(key, ts, price, usd, side)
            if key in self.icebergs.levels:
                self.icebergs.on_trade(key, ts, price, usd, side)
            if key in self.depth.books:
                self.depth.on_trade(key, ts, price, float(data['q']), side)
        elif event == 'kline':
            md = self.markets.get(self._binance_keys.get((market_type, data.get('s'))))
            if md is not None:
                md.apply_kline(market_type, data['k'])
        elif event == 'contractInfo':
            if data.get('ct') == 'PERPETUAL' and str(data.get('s', '')).endswith('USDT'):
                logger.info(f"Binance contract event: {data.get('s')} {data.get('cs')}")
                self.contract_event.set()
        elif event == 'forceOrder':
            o = data['o']
            key = self._binance_keys.get(('futures', o.get('s')))
            if key is not None:
                price = float(o.get('ap') or o.get('p') or 0)
                usd = price * float(o.get('z') or o.get('q') or 0)
                # S = the liquidation order's side: a forced SELL closes a long
                side_liq = 1 if o['S'] == 'SELL' else -1
                self.flow.liquidation('binance', key, int(o['T']), usd, side_liq, recv_ms)
                md = self.markets.get(key)
                if md is not None and price:
                    md.liq_events.append((int(o['T']), price, usd, side_liq, 'binance'))
                    if self.log_liquidations:
                        self.liq_log.append((key, int(o['T']), price, usd, side_liq, 'binance'))
        elif event == 'depthUpdate':
            key = self._binance_keys.get(('futures', data.get('s')))
            if key is not None:
                self.depth.on_diff(key, data)
                # iceberg tracking reads the near book at most once a second (depth20 gave it every 500ms; the top
                # of a few-thousand-level book on every diff event is wasted work)
                now_s = recv_ms / 1000
                if now_s - self._iceberg_fed.get(key, 0.0) >= 1.0:
                    self._iceberg_fed[key] = now_s
                    bids, asks = self.depth.top(key)
                    if bids or asks:
                        self.icebergs.on_book(key, bids, asks, int(data.get('E') or recv_ms))

    def _binance_price(self, key: str) -> Optional[float]:
        md = self.markets.get(key)
        return md.last_price if md else None

    def on_trade(self, market: VenueMarket, ts_ms: int, price: float, size: float, side: int, recv_ms: float):
        if not market.verified and not self.symbol_map.check_price(market, price, self._binance_price(market.key)):
            return
        usd = self.symbol_map.usd(market, price, size)
        self.flow.trade(market.venue, market.key, ts_ms, usd, side, recv_ms)
        if market.venue == 'bybit_spot':
            md = self.markets.get(market.key)
            if md is not None:
                # the coin's spot 1m candles from Bybit (no Binance spot klines exist for it): spot confirmations
                md.alt_spot_trade(ts_ms, price / market.multiplier * self.symbol_map.key_multiplier.get(market.key, 1.0),
                                  usd, side)
        if market.venue == 'coinbase':
            md = self.markets.get(market.key)
            if md is not None:
                md.coinbase_price = price / market.multiplier * self.symbol_map.key_multiplier.get(market.key, 1.0)
                md.coinbase_ts = ts_ms
        if not market.spot:
            self.sweeps.add(market.venue, market.key, ts_ms, price, usd, side)

    def on_liquidation(self, market: VenueMarket, ts_ms: int, price: float, size: float, side_liq: int, recv_ms: float):
        usd = self.symbol_map.usd(market, price, size)
        self.flow.liquidation(market.venue, market.key, ts_ms, usd, side_liq, recv_ms)
        md = self.markets.get(market.key)
        if md is not None and price:
            binance_price = price / market.multiplier * self.symbol_map.key_multiplier.get(market.key, 1.0)
            md.liq_events.append((ts_ms, binance_price, usd, side_liq, market.venue))
            if self.log_liquidations:
                self.liq_log.append((market.key, ts_ms, binance_price, usd, side_liq, market.venue))

    def on_deriv(self, market: VenueMarket, oi_usd: Optional[float] = None, funding_8h: Optional[float] = None,
                 mark: Optional[float] = None, ts_ms: Optional[float] = None):
        if mark and not market.verified and not self.symbol_map.check_price(market, mark, self._binance_price(market.key)):
            return
        now_ms = time.time() * 1000
        state = self.venue_derivs.setdefault(market.key, {}).setdefault(market.venue, VenueDeriv())
        if funding_8h is not None:
            state.funding_8h = funding_8h
        if mark:
            state.mark = mark
        state.ts = now_ms
        if oi_usd:
            self._record_venue_oi(market.key, market.venue, oi_usd, now_ms)

    def _on_sweep(self, sweep: Sweep):
        # A liquidation is executed as a MARKET order and prints in the same trade stream: a "whale buy" during a
        # short squeeze was the shorts' forced buying (live eng-6: 36% of WHALES BUY / 52% of WHALES SELL rows had the
        # opposite side liquidated in the same 5 minutes). A sweep whose size is mostly forced flow of its side in
        # the same seconds is no whale decision: left out of the whale book (Binance's forceOrder feed is sampled,
        # Bybit's / OKX's complete - the check misses some forced flow, never adds any).
        # Checked only for sweeps big enough to count (notable / whale size): thousands of small sweeps a second each
        # read every venue's ring, and with the machine short of RAM those reads paged and stalled the loop
        whale, notable = self.whales.thresholds(sweep.symbol)
        if sweep.usd >= (notable or whale):
            from flow import LIQ_LONG, LIQ_SHORT
            forced = self.flow.symbol_range(sweep.symbol, LIQ_SHORT if sweep.side > 0 else LIQ_LONG,
                                            int(sweep.t_first // 1000) - 1, int(sweep.t_last // 1000) + 2,
                                            now_sec=int(sweep.t_last // 1000) + 1)
            if forced >= CONFIG.sweeps.forced_share * sweep.usd:
                return
        self.whales.add(sweep)
        if sweep.usd >= whale and sweep.venue == 'binance':
            ratio = self.depth.sweep_vs_depth(sweep.symbol, sweep.usd, sweep.side)
            md = self.markets.get(sweep.symbol)
            if ratio is not None and md is not None and ratio >= md.book_eaten:
                md.book_eaten, md.book_eaten_ts = ratio, time.time()

    def maintain(self, now: Optional[float] = None):
        """Periodic housekeeping from the Tier-0 loop: close finished sweeps, decay whale histograms."""
        now = now or time.time()
        self.sweeps.flush(now * 1000)
        self.icebergs.prune(now * 1000)
        self.whales.maintain(now)
        for md in self.markets.values():
            if md.book_eaten and now - md.book_eaten_ts > CONFIG.tier0.display_hold_sec:
                md.book_eaten = 0.0

    # ------------------------------------------------------------------ hot symbols: order books, footprint

    async def set_hot(self, symbols: Iterable[str]):
        """Order books (Binance) and Hyperliquid trades for the hot symbols only."""
        symbols = [s for s in symbols if s in self.markets]
        if self._depth_streams:
            # A symbol always goes to the same socket (stable hash): changing the hot set moves no other subscription
            n = len(self._depth_streams)
            wanted: List[set] = [set() for _ in range(n)]
            for s in symbols:
                native = self.futures_exchange.market(s)['id'].lower()
                # the diff stream (a local book, depth.py): depth20 showed BTC +-0.07%
                wanted[zlib.crc32(native.encode()) % n].add(f"{native}@depth@500ms")
            for stream, subs in zip(self._depth_streams, wanted):
                await stream.set_dynamic(subs)
        for s, md in self.markets.items():
            md.trades_subscribed = s in symbols
        for s in list(self.depth.books):
            if s not in symbols:
                self.depth.drop(s)
        for s in symbols:
            book = self.depth.books.get(s)
            if book is None:
                self.depth.start(s)
            elif not book.synced:
                book.snapshot_wanted = True
        hl = self.venue_streams.get('hyperliquid')
        if hl is not None:
            natives = [m.native for s in symbols if (m := self.symbol_map.by_key.get(s, {}).get('hyperliquid'))]
            await hl.set_dynamic({('trades', n) for n in natives[:CONFIG.venues.hyperliquid_trades_max]})

    async def _book_sync_loop(self):
        """
        Local books of the hot symbols (depth.py): a 1000-level REST snapshot (weight 20) for every book whose diff
        stream is buffering - at its start and after a sequence gap. The snapshot is taken a second after the first
        buffered event (Binance: buffer first, then fetch, so the snapshot overlaps the buffered events).
        """
        sem = asyncio.Semaphore(2)

        async def one(symbol: str):
            book = self.depth.books.get(symbol)
            if book is None:
                return
            book.snapshot_wanted = False
            async with sem:
                try:
                    snap = await self._rest_call(self.futures_exchange, 'fapiPublicGetDepth',
                                                 {'symbol': self._ccxt_to_binance_symbol(symbol), 'limit': 1000},
                                                 priority=1, weight=20)
                    self.depth.set_snapshot(symbol, snap or {})
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    book.snapshot_wanted = True
                    errors.report('fetcher.book_snapshot', e, f"{symbol} 1000-level snapshot")

        running: set = set()
        while self._running:
            await asyncio.sleep(1.0)
            for symbol in self.depth.wanting_snapshot():
                book = self.depth.books.get(symbol)
                if book is not None and book.buffer and time.time() * 1000 - int(book.buffer[0].get('E') or 0) >= 1000:
                    task = asyncio.create_task(one(symbol))
                    running.add(task)
                    task.add_done_callback(running.discard)

    def set_footprint(self, zone: Dict[str, float]):
        """
        Footprint accumulation for EVERY universe coin (the last Footprint.KEEP_MINUTES), bucketed by
        `footprint_bucket_pct` of price (one fixed bucket per coin: a size change would mix two grids). Before
        (2026-10-05) only cards waiting in a zone had one, so the systems entering at their signal's close (ORB,
        Bollinger, VA80, pump, OI signal: 14 positive order-flow readings in 217 entries) were never judged by it.
        `zone`: symbol -> the card's 15m ATR, kept for the absorption test.
        """
        for s in list(self.footprint.bucket):
            if s not in self.markets:
                self.footprint.disable(s)
        for s, md in self.markets.items():
            if s not in self.footprint.bucket:
                price = md.last_price
                if price:
                    self.footprint.enable(s, price * CONFIG.orderflow.footprint_bucket_pct)
        self._zone_atr = {s: atr for s, atr in zone.items() if atr}

    def orderflow_confirm(self, symbol: str, since_ms: int, until_ms: int, direction: int) -> Optional[str]:
        """
        Order-flow confirmation of an entry in the zone: 'imbalance' (stacked diagonal imbalances on the trade side
        in the footprint) or 'absorption' (a heavy 1m delta AGAINST the trade that barely moved price: the
        aggressive side was absorbed by resting orders). None when neither happened.
        """
        cfg = CONFIG.orderflow
        if self.footprint.stacked_imbalance(symbol, since_ms, direction, until_ms) >= cfg.stacked_levels:
            return 'imbalance'
        md = self.markets.get(symbol)
        atr = self._zone_atr.get(symbol) or (minute_atr_15m(md.minute_klines, until_ms) if md is not None else None)
        if md is not None and atr and absorption_in(md.minute_klines, since_ms, until_ms, direction, atr):
            return 'absorption'
        if self.footprint.finished_auction(symbol, since_ms, until_ms, direction):
            return 'finished_auction'
        return None

    def confirmations(self, symbol: str, strategy: str, direction: int, since_ms: int, until_ms: int,
                      extreme_ms: Optional[int] = None) -> Dict:
        """Entry confirmations (strategies.confirm): flow, spot, OI, order flow at the extreme."""
        md = self.markets.get(symbol)
        if md is None:
            return {}
        # the footprint holds its last KEEP_MINUTES: an extreme older than that is read as the flow into the entry
        of_since = max(extreme_ms or since_ms, until_ms - Footprint.KEEP_MINUTES * 60_000)
        orderflow = self.orderflow_confirm(symbol, of_since, until_ms, direction)
        spot = list(md.spot_minute_klines) if self._spot_symbol_for(symbol) or self.needs_alt_spot(symbol) else None
        # OI over the last hour: across venues (OI-weighted, as the phases' agg_oi_change_1h) when >= 2 report, else
        # Binance's samples (seeded with the last hour at start-up); the entry is evaluated at its trigger, i.e. now
        derivs = self.deriv_snapshot(symbol)
        if derivs['oi_venues'] >= 2 and derivs['agg_oi_change_1h'] is not None:
            oi = derivs['agg_oi_change_1h']
        else:
            oi = confirm.oi_change(list(md.oi_samples), until_ms - confirm.HOUR_MS, until_ms)
        if oi is None and confirm.OI_EXPECT.get(strategy):
            logger.warning(f"Confirmations: no OI history for {symbol} ({len(md.oi_samples)} samples)")
        # Multi-venue deltas over the evaluate() window (since the extreme, at most the last hour): Binance's candles
        # alone called a move "against" while Bybit / OKX bought more than Binance sold
        from flow import BUY, FUTURES_VENUES, SELL
        start = max(extreme_ms if extreme_ms is not None else since_ms, until_ms - confirm.HOUR_MS)
        a, b, now_sec = int(start // 1000), int(until_ms // 1000), int(time.time())

        def venue_delta(venues) -> Optional[float]:
            """Net taker USD of the venues whose ring covers the window; None when none does (no reading, not 0)."""
            row = self.flow.rows.get(symbol)
            if row is None:
                return None
            total, counted = 0.0, 0
            for v in venues:
                vf = self.flow.venues.get(v)
                # a venue whose ring is shorter than the window (Bitget / Hyperliquid / spot venues keep 15 min)
                # would add only its last part: left out rather than a partial sum skewing the total
                if vf is None or b - a > vf.H:
                    continue
                total += vf.row_range_sum(BUY, row, a, b, now_sec) - vf.row_range_sum(SELL, row, a, b, now_sec)
                counted += 1
            return total if counted else None

        flow_usd = venue_delta(FUTURES_VENUES)
        spot_usd = None
        if spot is not None:
            if self.needs_alt_spot(symbol):
                # None (the 15-min spot rings do not cover the window) -> evaluate() reads the Bybit-built 1m candles
                spot_usd = venue_delta(('bybit_spot', 'coinbase'))
            else:
                spot_usd = confirm.delta(spot, start, until_ms) + (venue_delta(('coinbase',)) or 0.0)
        out = confirm.evaluate(strategy, direction, list(md.minute_klines), spot, oi, since_ms, until_ms,
                               extreme_ms, orderflow, flow_usd=flow_usd, spot_usd=spot_usd)
        # the window the readings were taken over (journaled: a REST check can recompute them exactly)
        out['_window'] = [int(since_ms), int(until_ms), int(extreme_ms) if extreme_ms is not None else None]
        # the classic indicator panel on 15m and 1h (journaled, not a vote: research/indicator_confirms.md decides
        # which of them confirm an entry)
        out['_ind'] = self.indicator_panel(md, direction, until_ms)
        out['_btc_slope'], out['_atr_1h'] = self.profile_context(md)
        out['_dom'] = self.dominance_reading()
        out['_bias'] = self.htf_bias(md, until_ms)
        btc = self.markets.get('BTC/USDT:USDT')
        try:
            from strategies.profiles import btc_regime
            out['_regime'] = btc_regime(list(btc.h4)) if btc is not None else None
        except Exception as e:
            errors.report('fetcher.btc_regime', e)
            out['_regime'] = None
        # the local book's readings at the entry (hot coins only; features, not a vote until the journal proves one):
        # depth imbalance, what was pulled / filled within 1% in the last 5 minutes, the impact of a $50k market order
        book = self.depth.metrics(symbol)
        if book:
            out['_book'] = {k: round(v, 4) for k, v in book.items()
                            if k.startswith(('imbalance_', 'bid_pulled', 'bid_filled', 'ask_pulled', 'ask_filled'))}
            out['_book']['slip_50k_bps'] = self.depth.slippage_bps(symbol, 50_000, direction)
        return out

    def profile_context(self, md: 'MarketData'):
        """For the optimized profiles (strategies/profiles.py), as research_optimize.py measured them: BTC's 1h EMA50
        slope over 10 closed hours and the coin's 1h ATR14 (simple mean of true ranges)."""
        from strategies.ind_panel import ema
        slope = atr = None
        try:
            btc = self.markets.get('BTC/USDT:USDT')
            if btc is not None and len(btc.h1_long) >= 60:
                e = ema(np.asarray(btc.h1_long)[:, 4], 50)
                slope = float(e[-1] - e[-11])
            h = np.asarray(md.h1_long) if len(md.h1_long) else None
            if h is not None and len(h) >= 15:
                prev = h[:-1, 4]
                tr = np.maximum(h[1:, 2] - h[1:, 3], np.maximum(abs(h[1:, 2] - prev), abs(h[1:, 3] - prev)))
                atr = float(tr[-14:].mean())
        except Exception as e:
            errors.report('fetcher.profile_context', e, md.symbol)
        return slope, atr

    @staticmethod
    def indicator_panel(md: 'MarketData', direction: int, until_ms: int) -> Dict:
        """{'15m': {rule: bool}, '1h': {...}} on the candles closed by until_ms: the 499-candle REST histories
        (refreshed hourly) extended by the 1m stream's closed buckets since."""
        from levels import resample
        from strategies.ind_panel import panel
        minutes = [c for c in md.minute_klines if c[0] + 60_000 <= until_ms]
        out = {}
        for tf, size, hist in (('15m', 15, md.m15_long), ('1h', 60, md.h1_long)):
            base = [list(r) for r in hist] if len(hist) else []
            last = base[-1][0] if base else 0
            base += [b for b in resample(minutes, size, until_ms) if b[0] > last]
            try:
                out[tf] = panel(base, direction)
            except Exception as e:
                errors.report('fetcher.indicator_panel', e, f"{md.symbol} {tf}")
        return out

    def venue_status(self) -> Dict[str, Dict]:
        status = self.flow.venue_status()
        for venue, stream in self.venue_streams.items():
            status.setdefault(venue, {}).update(connected=stream.connected, bytes=stream.bytes)
        binance = list(self._binance_streams) + self._depth_streams
        status.setdefault('binance', {}).update(connected=sum(s.connected for s in self._binance_streams),
                                                bytes=sum(s.bytes for s in binance))
        return status

    # ------------------------------------------------------------------ stop

    async def stop(self):
        self._running = False
        streams = list(self._binance_streams) + self._depth_streams + \
            list(self.venue_streams.values())
        await asyncio.gather(*[s.stop() for s in streams], return_exceptions=True)
        tasks = self._tasks + list(self._background_tasks)
        for task in tasks:
            task.cancel()
        # Bounded waits: a hung socket must not keep the process from exiting
        if tasks:
            await asyncio.wait(tasks, timeout=10)
        exchanges = [self.spot_exchange, self.futures_exchange, *self.venue_exchanges.values()]
        closes = [asyncio.ensure_future(ex.close()) for ex in exchanges if ex]
        if closes:
            done, pending = await asyncio.wait(closes, timeout=10)
            for task in pending:
                task.cancel()
            for task in done:
                task.exception()  # retrieve, so failed closes are not reported as "never retrieved"
        logger.info("DataFetcher stopped gracefully")
