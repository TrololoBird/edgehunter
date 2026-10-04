import asyncio
import json
import logging
import os
import platform
import statistics
import time
from collections import deque
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import polars as pl

from config import CONFIG
from ml import AnomalyModel, RegimeModel
from levels import resample
from positioning import Positioning
import scenarios
from macro import Macro
from pools import Pools
import sectors
from storage import atomic_write
from watchdog import LoopWatchdog
from zones import RawLevel, build_raw, merge
from fetcher import DataFetcher, MarketData
from flow import FUTURES_VENUES
from indicators import (TIER0_COLUMNS, calculate_tier0_metrics, compute_indicators_batch, merge_live_candle, minute_delta,
                        seasonal_scale)
from notifier import Notifier
from scorer import PhaseScorer, score_closed, signals_from_rows
from strategies import confirm
from strategies.detect import LiveDetector
from strategies.structure import PART_COLUMNS, build_maps, part_candles, trend_w_of
from netstate import NETWORK
from signal_book import SignalBook, TrackedSignal

logger = logging.getLogger(__name__)

ML_STATE_PATH = 'ml_state.pkl'


def play_alert_sound(level: str = "normal"):
    """Play Windows system sound asynchronously (non-blocking)."""
    if platform.system() != "Windows":
        return
    try:
        import winsound
        if level == "high":
            winsound.PlaySound("SystemHand", winsound.SND_ALIAS | winsound.SND_ASYNC)
        else:
            winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
    except Exception as e:
        logger.debug(f"Could not play sound: {e}")


class _FrameLookup:
    """
    dict-like .get(symbol) for the tracked cards: the symbol's closed 15m futures candles with indicators plus
    the in-progress candle's OHLC (so the 15m leg follows the live high / low between candle closes).
    `parts` = the closed frame split per symbol once per heavy pass: filtering the whole universe's frame for every
    card on every scan blocked the event loop for over a second with ~40 cards.
    """

    def __init__(self, parts: Dict[str, pl.DataFrame], markets: Dict[str, MarketData]):
        self.parts = parts
        self.markets = markets
        self._memo: Dict[str, Optional[pl.DataFrame]] = {}

    def get(self, symbol: str) -> Optional[pl.DataFrame]:
        # one lookup serves one scan: a coin's frame is built once however many cards / gates ask for it
        if symbol in self._memo:
            return self._memo[symbol]
        part = self.parts.get(symbol)
        if part is None or part.is_empty():
            self._memo[symbol] = None
            return None
        md = self.markets.get(symbol)
        live = md.live_candle('futures') if md else None
        if live and live['timestamp'] > part['timestamp'][-1]:
            # (measured: this diagonal concat ~2 ms; part.clear(1) + vstack of the ~110-column frame 67 ms)
            row = {c: live.get(c) for c in ('timestamp', 'open', 'high', 'low', 'close')}
            row.update(symbol=symbol, atr=part['atr'][-1])
            part = pl.concat([part, pl.DataFrame([row])], how='diagonal_relaxed')
        self._memo[symbol] = part
        return part


def _rr_text(lv: Dict) -> str:
    """R:R for a log line: to TP1 and blended, or 'none' (the Turtles have no target: rr_tp1 None crashed the entry's
    output and its demo order, live AAVE 2026-10-02 04:33)."""
    if lv.get('rr_tp1') is None:
        return 'none (trailing exit)'
    blend = lv.get('rr_blend')
    return f"{lv['rr_tp1']:.1f}" + (f" (blended {blend:.1f})" if blend is not None else '')


class Scanner:
    """
    Orchestration:
    - Tier-0 loop (every check_interval_sec): raw impulse metrics from the streams of every venue, anomaly flags
      with hysteresis, hot symbols (order books / Hyperliquid trades), footprints of cards in the zone;
    - scan loop (every scan_interval_sec): merge kline rows; the heavy Polars pass (indicators + phase scores of
      CLOSED 15m candles) only runs when a candle closed or history changed; the light pass every scan joins the
      cached scores with live Tier-0 metrics, feeds the signal book, journal, notifications and dashboard;
    - universe loop: re-selects the top symbols hourly; state loop: persists open cards / whale histograms.
    """

    def __init__(self, journal=None):
        self.fetcher = DataFetcher()
        self.scorer = PhaseScorer()
        self.web = None   # webui.WebUI, attached by main.py
        self.journal = journal
        self.notifier = Notifier()
        from executor import DemoExecutor
        self.demo = DemoExecutor()
        self.demo.card_is_open = lambda card_id: any(
            card_id in (f"{s.symbol}|{s.group_key}|{int(s.entered_at or 0)}", f"{s.symbol}|{s.group_key}|c{int(s.created)}")
            and not s.finished for s in self.book.signals.values())
        self._limits_synced = 0.0
        from extdata import ExternalData
        self.ext = ExternalData(self.fetcher)
        self.book = SignalBook()
        self.market_data: Dict[str, MarketData] = {}
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._baseline_task: Optional[asyncio.Task] = None
        self._started_at = time.time()
        self._previous_keys: Set[Tuple[str, str]] = set()
        # Heavy-pass cache: closed-candle rows per symbol, the closed futures indicator frame, its signature
        self._rows: Dict[str, Dict] = {}
        # pretrain.py run by pretrain_loop, the loaded pretrained models' metadata, and the retry pause after a failure
        self._pretrain_proc = None
        self._pretrained_meta: Optional[Dict] = None
        self._pretrain_retry_at = 0.0
        self._pretrain_checked = (None, False)      # (pretrained.pkl mtime, built by the current logic version)
        self._cb_median: Optional[float] = None        # the universe's median Coinbase premium (the USDT basis)
        self._futures_closed = pl.DataFrame()
        self._frame_parts: Dict[str, pl.DataFrame] = {}
        self._heavy_signature = None
        self.last_heavy_sec = 0.0
        self.last_scan_sec = 0.0
        self.last_tier0_sec = 0.0
        # Aggregated multi-venue futures / extra-spot flow per closed 15m candle: symbol -> deque[(ts, fut, spot)]
        self._agg_hist: Dict[str, deque] = {}
        self._agg_last_ts: Dict[str, int] = {}
        self._hot: List[str] = []
        # ml.py models
        self.anomaly_model = AnomalyModel() if CONFIG.ml.anomaly_enabled else None
        self.regime_model = RegimeModel() if CONFIG.ml.regime_enabled else None
        self.regime: Optional[str] = None
        self._background: set = set()
        # Level maps (zones.py) of coins with open cards: symbol -> raw levels, and the inputs they were built from
        self.watchdog = LoopWatchdog()
        self.positioning = Positioning(self.fetcher)
        self.macro = Macro()
        self._pump_cache: Dict = {}
        self.pools = Pools()      # pumps.monitor: symbol -> (last 1h candle ts, scan result)
        self._level_raw: Dict[str, List[RawLevel]] = {}
        self._level_sig: Dict[str, tuple] = {}
        self.book.levels_of = self._levels_of
        # 1h candles of the coin: the 8 days every coin has (hourly), else a card coin's level-map history
        self.book.daily_of = lambda symbol: (lambda md: md.d1 if md else None)(self.market_data.get(symbol))
        self.book.htf_of = lambda symbol: (lambda md: (md.h1 or md.htf_klines) if md else None)(self.market_data.get(symbol))
        self.book.context_of = lambda symbol: self.detector.context.get(symbol)
        self.book.band_of = self._opposite_band
        self.book.plan_key_of = self._plan_key
        self.book.map_ready_of = lambda symbol: symbol in self._level_raw
        self.fetcher.log_liquidations = self.journal is not None
        # Setup detectors (sweeps, liquidation exhaustion, absorption, whale accumulation) and the quick level map of
        # every coin they use (rebuilt from the closed 15m candles after each close; card coins get the full map)
        self.detector = LiveDetector()
        # Market state for every setup's context: universe median and BTC moves (see _update_market_state)
        self.market_state: Dict[str, float] = {}
        self._quick_raw: Dict[str, List[RawLevel]] = {}
        self._context_sig: Dict[str, tuple] = {}
        # crypto_maniac's OI robot: the last final minute checked and the last signal per coin (his 3h cooldown)
        self._oi_checked: Dict[str, int] = {}
        self._oi_fired: Dict[str, int] = {}
        self._context_task: Optional[asyncio.Task] = None
        self._maps_pool = None          # ProcessPoolExecutor (one worker) for level maps: see _maps_executor
        self._connors_checked: Dict[str, int] = {}   # symbol -> the daily close Connors' RSI(2) was checked at
        self._turtle_checked: Dict[str, int] = {}    # symbol -> the last final minute the Turtle channel was checked on
        self._turtle_fired: set = set()              # (symbol, direction, day) breakouts already fired
        self._orb_checked: Dict[str, int] = {}       # symbol -> the last final minute Crabel's ORB was checked on
        self._orb_fired: set = set()                 # (symbol, day) ORBs already fired (one a day)
        self._dump_checked: Dict[str, int] = {}      # symbol -> the last closed 1h candle the dump bounce was checked on
        self._dump_fired: set = set()                # (symbol, dump hour) bounces already fired
        self._sb_checked: Dict[str, int] = {}        # symbol -> the last final minute the Silver Bullet was checked on
        self._sb_fired: set = set()                  # (symbol, direction, window start) setups already fired
        self._pump_checked: Dict[str, int] = {}      # symbol -> the last final minute the pump checks ran on
        self._pump_fired: set = set()                # pump starts / tops already fired

    # ------------------------------------------------------------------ lifecycle

    async def initialize(self):
        logger.info("Initializing scanner...")
        # The watchdog covers the start-up too (market lists, symbol checks run on this loop)
        self._heartbeat_task = asyncio.create_task(self.watchdog.heartbeat())
        self.watchdog.start()
        await self.fetcher.initialize()
        # The venues' instrument lists first: the universe is the candidates' data-complete subset, and their
        # mappings are price-checked against Binance before anything is subscribed
        candidates = await self.fetcher.fetch_candidates()
        self.fetcher.symbol_map.set_universe({s: self.fetcher.futures_exchange.markets[s] for s in candidates
                                              if s in self.fetcher.futures_exchange.markets})
        await self.fetcher.load_venues()
        symbols = self.fetcher.select_universe(candidates)
        await asyncio.to_thread(self._load_ml_state)
        self._load_state()
        # Coins with open cards stay in the universe until their cards finish (as on the hourly refresh); a restored
        # card on a coin that left the top list had no data and broke the hot-symbol update
        carried = sorted({s.symbol for s in self.book.signals.values() if not s.finished} - set(symbols))
        carried = [s for s in carried if s in self.fetcher.futures_exchange.markets]
        if carried:
            logger.info(f"Keeping {len(carried)} coins with open cards outside the top list: {carried[:10]}")
            symbols = symbols + carried
        self.market_data = self.fetcher.create_market_data(symbols)

        # Streams first: Tier-0 warms up while the candle history downloads in the background
        await self.fetcher.start_websockets(symbols)
        self.watchdog.arm()
        self._started_at = time.time()
        self._baseline_task = asyncio.create_task(self.fetcher.fetch_rest_baselines(symbols))
        self._positioning_tasks = await self.positioning.start()
        logger.info(f"Scanner initialized for {len(self.market_data)} symbols (history loading in background)")

    def start(self):
        self._running = True
        loops = [self.tier0_loop(), self.scan_loop(), self.universe_loop(), self.positioning_loop(), self.state_loop(),
                 self.levels_loop(), self.pretrain_loop(), self.macro_loop(), self.pools_loop(), self.event_risk_loop()]
        if self.demo.enabled:
            loops.append(self.demo.reconcile_loop(lambda: self._running))
        running = lambda: self._running
        loops += [self.ext.deribit_loop(running), self.ext.funding_loop(running), self.ext.books_loop(running),
                  self._seed_okx_later()]
        if CONFIG.recorder.enabled:
            import recorder
            loops.append(recorder.record_loop(self.fetcher, self._maps_executor, CONFIG.recorder.root,
                                              lambda: self._running))
        if self.journal:
            loops.append(self.journal.evaluate_loop(self.fetcher))
            # P(edge) model state = the journal itself: replay the labelled rows, then the regime Edge table
            self._background_thread(self.journal.warm_start)
            self._background_thread(self.journal.refresh_regime_stats)
            self._background_thread(self.journal.refresh_confirm_stats)
            self._background_thread(self.journal.refresh_hit_rates)
            self._background_thread(self.journal.refresh_anomaly_effects)
        self._tasks = [asyncio.create_task(c) for c in loops]

    async def _seed_okx_later(self):
        await asyncio.sleep(5)                  # the streams' start time is known by then
        await self.ext.seed_okx_flow()

    def _background_task(self, coro):
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        return task

    def _background_thread(self, fn, *args):
        task = asyncio.create_task(asyncio.to_thread(fn, *args))
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        return task

    async def stop(self):
        self._running = False
        self.watchdog.stop()
        if self.anomaly_model is not None:
            self.anomaly_model.close()
        if self._maps_pool is not None:
            self._maps_pool.shutdown(wait=False, cancel_futures=True)
        tasks = [t for t in (*self._tasks, self._baseline_task, getattr(self, '_heartbeat_task', None),
                             *getattr(self, '_positioning_tasks', [])) if t]
        for task in tasks:
            task.cancel()
        # return_exceptions: a task that already died with an error must not skip closing the streams below
        for result in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                logger.error(f"Task ended with an error: {result!r}")
        self._save_state()
        await self.notifier.close()
        await self.demo.close()
        await self.ext.close()
        await self.positioning.close()
        await self.fetcher.stop()
        logger.info("Scanner stopped gracefully")

    # ------------------------------------------------------------------ Tier-0 / hot symbols

    async def tier0_loop(self):
        """Fast loop: Tier-0 raw anomaly detection, hot-symbol subscriptions, footprints."""
        while self._running:
            try:
                started = time.monotonic()
                self.fetcher.maintain()
                await self._check_tier0()
                self.last_tier0_sec = time.monotonic() - started
                model = self.anomaly_model
                if model is not None and model.due(time.time()):
                    model.fitting = True
                    task = asyncio.create_task(model.afit())
                    self._background.add(task)
                    task.add_done_callback(self._background.discard)
                await self._update_hot()
                self.fetcher.set_footprint(self.book.zone_symbols())
            except Exception as e:
                logger.error(f"Tier-0 check error: {e}", exc_info=True)
            await asyncio.sleep(CONFIG.tier0.check_interval_sec)

    def _tier0_metrics(self, now_ms: float) -> Dict[str, Dict[str, float]]:
        """Tier-0 metrics of every symbol: core (price / OI / RVOL) + order flow of all venues."""
        snapshot = self.fetcher.flow.snapshot(int(now_ms // 1000))
        whales = self.fetcher.whales
        out = {}
        for symbol, md in self.market_data.items():
            # the 24h averages scaled to this hour of the day / week (relative volume and volatility at time)
            vol_scale = seasonal_scale(md.season, now_ms, 'vol')
            ret_scale = seasonal_scale(md.season, now_ms, 'ret')
            m = calculate_tier0_metrics(md.ticker_samples, md.oi_samples, md.minute_klines, now_ms,
                                        ret_std=md.ret_std * ret_scale if md.ret_std else md.ret_std, oi_std=md.oi_std,
                                        avg_minute_usd=md.avg_minute_usd * vol_scale if md.avg_minute_usd else md.avg_minute_usd)
            flow = snapshot.get(symbol, {})
            m['whale_net_5m'] = whales.net_units(symbol, CONFIG.tier0.window_sec, now_ms)
            m['cluster'] = float(whales.cluster(symbol, now_ms))
            for key in ('liq_long_5m', 'liq_short_5m', 'agg_cvd_5m', 'top_venue_share', 'top_venue_net', 'venues_active'):
                m[key] = float(flow.get(key, 0.0) or 0.0)
            m['futures_cvd_5m'] = float(flow.get('cvd_5m', 0.0))
            m['spot_cvd_5m'] = minute_delta(md.spot_minute_klines, now_ms) + float(flow.get('agg_spot_cvd_5m', 0.0))
            m['agg_oi_change_5m'] = self.fetcher.deriv_snapshot(symbol, now_ms)['agg_oi_change_5m']
            m['top_venue'] = flow.get('top_venue', '')
            out[symbol] = m
        return out

    async def _check_tier0(self):
        if not self.market_data:
            return
        now_ms = time.time() * 1000
        metrics = self._tier0_metrics(now_ms)
        symbols = list(metrics)
        await self._score_anomalies(symbols, metrics, now_ms / 1000)
        frame = pl.DataFrame(
            {c: [float(metrics[s].get(c, 0.0) or 0.0) for s in symbols] for c in TIER0_COLUMNS},
            schema={c: pl.Float64 for c in TIER0_COLUMNS},
        )
        flagged = self.scorer.flag_tier_0_anomaly(frame)
        flags = flagged['is_tier_0_anomaly'].to_list()
        trigger_cols = [c for c in flagged.columns if c.startswith('t0_')]
        triggers = flagged.select(trigger_cols).rows()

        check_time = now_ms / 1000
        for symbol, is_anomaly, fired in zip(symbols, flags, triggers):
            md = self.market_data.get(symbol)
            if md is None:          # left the universe during the await above (hourly refresh)
                continue
            m = metrics[symbol]
            if is_anomaly:
                md.tier0_last_trigger = check_time
            # Hysteresis: stay anomalous for anomaly_hold_sec after the last trigger
            held = is_anomaly or check_time - md.tier0_last_trigger < CONFIG.tier0.anomaly_hold_sec
            if held and not md.is_tier_0_anomaly:
                reasons = ','.join(c[3:] for c, on in zip(trigger_cols, fired) if on)
                logger.info(
                    f"Tier-0 anomaly [{reasons}]: {symbol} | RVOL_1m={m['rvol_1m']:.2f} | OI_5m={m['oi_change_5m']:+.2%} | "
                    f"Price_5m={m['price_change_5m']:+.2%} (z {m['price_z']:+.1f}) | whales {m['whale_net_5m']:+.1f} | "
                    f"liq L/S {m['liq_long_5m']:,.0f}/{m['liq_short_5m']:,.0f}"
                )
            md.tier0 = m
            md.is_tier_0_anomaly = held

    async def _score_anomalies(self, symbols: List[str], metrics: Dict[str, Dict[str, float]], now: float):
        """
        IsolationForest score of every coin's feature vector (ml.AnomalyModel); also feeds its training window.
        Scoring runs in the model's worker PROCESS (ml.py): in a thread scikit-learn held the GIL and stalled the loop.
        """
        model = self.anomaly_model
        if model is None or not symbols:
            return
        X = np.asarray([AnomalyModel.vector(metrics[s]) for s in symbols], dtype=np.float64)
        scores = await model.ascore(X) if model.ready else None
        for i, symbol in enumerate(symbols):
            m = metrics[symbol]
            if scores is not None:
                m['ml_score'] = float(scores[i])
                m['ml_anomaly'] = 1.0 if scores[i] < model.threshold else 0.0
                # shadow (journaled ml_score / ml_anomaly): the rules decide unless anomaly_decides
                m['ml_ready'] = 1.0 if CONFIG.ml.anomaly_decides else 0.0
        model.observe(X, now, warmed_up=now - self._started_at >= CONFIG.ml.anomaly_skip_first_sec)

    async def _update_hot(self):
        """
        Hot symbols (order books, Hyperliquid trades): cards in a trade > in the zone > watching > anomalies /
        structured bursts, at most depth.max_symbols. A subscription younger than tier2_min_age_sec, or wanted within
        tier2_hold_sec, is kept so a slot is not re-subscribed and dropped every few seconds.
        """
        cfg = CONFIG.tier0
        now = time.time()
        wanted: Dict[str, int] = {s: p for s, p in self.book.hot_symbols().items() if s in self.market_data}
        for symbol, md in self.market_data.items():
            structured_burst = (max(md.current_long_score, md.current_short_score) >= CONFIG.scoring.tier2_min_score and
                                md.tier0.get('rvol_1m', 0.0) > CONFIG.scoring.micro_burst_rvol)
            if md.is_tier_0_anomaly or structured_burst:
                wanted.setdefault(symbol, 3 if md.is_tier_0_anomaly else 4)
        for symbol in wanted:
            md = self.market_data.get(symbol)
            if md is not None:
                md.tier2_wanted_at = now
        keep = [s for s in self._hot if s in self.market_data and (
            s in wanted or now - self.market_data[s].tier2_wanted_at < cfg.tier2_hold_sec
            or now - self.market_data[s].tier2_since < cfg.tier2_min_age_sec)]
        slots = CONFIG.depth.max_symbols
        ranked = sorted(wanted.items(), key=lambda kv: (kv[1], kv[0]))
        new = list(keep)
        for symbol, priority in ranked:
            if symbol in new:
                continue
            if len(new) >= slots:
                # Evict the idle kept symbol with the lowest priority for a higher-priority newcomer
                idle = [s for s in new if s not in wanted and now - self.market_data[s].tier2_since >= cfg.tier2_min_age_sec]
                if not idle or priority > 3:
                    continue
                victim = min(idle, key=lambda s: self.market_data[s].tier2_wanted_at)
                new.remove(victim)
            new.append(symbol)
            self.market_data[symbol].tier2_since = now
        if set(new) != set(self._hot):
            self._hot = new
            await self.fetcher.set_hot(new)

    # ------------------------------------------------------------------ phase scan

    async def scan_loop(self):
        logger.info("Starting scan loop...")
        while self._running:
            try:
                start = time.time()
                await self._perform_scan()
                elapsed = time.time() - start
                self.last_scan_sec = elapsed
                await asyncio.sleep(max(0, CONFIG.timeframe.scan_interval_sec - elapsed))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Scan error: {e}", exc_info=True)
                await asyncio.sleep(5)

    @staticmethod
    def _merge_frames(pending: List[tuple]) -> List[Tuple[pl.DataFrame, bool]]:
        """Worker thread: append finalized candles to their frames -> [(frame, needs_backfill)]."""
        out = []
        for _, _, df, rows, finalized in pending:
            needs = False
            for row in rows:
                df, needs_backfill = merge_live_candle(df, row, finalized)
                needs = needs or needs_backfill
            out.append((df, needs))
        return out

    async def _merge_rows(self) -> Tuple[Dict, Dict, Dict, Dict, tuple]:
        """Merge stream kline rows into the frames; returns closed-only frames, funding, closed_until, signature."""
        spot_frames, futures_frames, funding, closed_until = {}, {}, {}, {}
        signature = []
        # Only FINALIZED candles are merged: scoring reads closed candles, and the card plans take the in-progress
        # candle straight from md.live_klines (_FrameLookup). Until the REST history is in, rows stay queued and the
        # symbol is Tier-0 only. At a 15m close all ~600 frames get a candle: the Polars appends run in a worker
        # thread (on the loop they blocked it ~1.6s at every close).
        pending: List[tuple] = []
        for symbol, md in self.market_data.items():
            for market in ('spot', 'futures') if md.baseline_ready else ():
                if market in md.backfill_wanted:
                    self.fetcher.request_backfill(symbol, market, md.backfill_wanted.pop(market))
                rows = []
                for row in md.drain_kline_rows(market, include_live=False):
                    if market == 'futures':
                        row['open_interest'] = md.open_interest or None
                    if row == md.last_merged.get(market):
                        continue  # the live candle did not change since the last scan
                    md.last_merged[market] = row
                    rows.append(row)
                if rows:
                    pending.append((symbol, market, md.frame(market), rows, md.finalized_until[market]))
        if pending:
            merged = await asyncio.to_thread(self._merge_frames, pending)
            for (symbol, market, before, rows, finalized), (df, needs_backfill) in zip(pending, merged):
                md = self.market_data.get(symbol)
                if md is None:
                    continue
                if md.frame(market) is not before:
                    # A REST backfill replaced the frame meanwhile: apply the rows to the new one (rare, small)
                    df = md.frame(market)
                    for row in rows:
                        df, needs = merge_live_candle(df, row, finalized)
                        needs_backfill = needs_backfill or needs
                md.set_frame(market, df)
                if needs_backfill:
                    self.fetcher.request_backfill(symbol, market)
        for symbol, md in self.market_data.items():
            if not md.baseline_ready:
                continue
            for market, target in (('spot', spot_frames), ('futures', futures_frames)):
                df = md.frame(market)
                if df is None or df.is_empty():
                    continue
                final = md.finalized_until[market]
                if md.incomplete[market]:
                    # A candle built from missing minutes waits for its REST replacement: score the history before it
                    # (request_backfill ignores repeats while one is running and waits 10 min after a failed one).
                    # The cut frame is cached until the frame or the gap set changes: after every start all ~600
                    # frames have such a candle, and filtering them on every scan blocked the loop for ~5s.
                    self.fetcher.request_backfill(symbol, market, max(md.incomplete[market]))
                    key = (id(df), df.height, frozenset(md.incomplete[market]))
                    cached = md.scored_cut.get(market)
                    if cached is None or cached[0] != key:
                        cached = (key, df.filter(pl.col('timestamp') < min(md.incomplete[market])))
                        md.scored_cut[market] = cached
                    target[symbol] = cached[1]
                    continue
                # The in-progress candle is always the last row: slicing it off is free (no copy)
                target[symbol] = df if df['timestamp'][-1] <= final else df.head(df.height - 1)
            funding[symbol] = (md.funding_rate, md.predicted_funding)
            closed_until[symbol] = md.closed_until
            signature.append((symbol, md.finalized_until['spot'], md.finalized_until['futures'], md.history_version,
                              len(md.incomplete['spot']), len(md.incomplete['futures'])))
        return spot_frames, futures_frames, funding, closed_until, tuple(signature)

    def _accumulate_agg(self):
        """
        On each closed 15m futures candle, store its multi-venue futures net flow and extra-spot net flow. All
        symbols closing the same candle are computed in ONE vectorized pass (per-symbol passes copied the whole
        buffer 300 times and blocked the event loop for ~8s at every 15m close).
        """
        flow = self.fetcher.flow
        now_sec = int(time.time())
        started_sec = int(self._started_at)
        extra_spot = [v for v in flow.venues if v not in FUTURES_VENUES]
        by_ts: Dict[int, List[str]] = {}
        for symbol, md in self.market_data.items():
            ts = md.finalized_until['futures']
            if not ts or self._agg_last_ts.get(symbol) == ts:
                continue
            self._agg_last_ts[symbol] = ts
            if ts // 1000 >= started_sec:     # the buffers must cover the whole candle
                by_ts.setdefault(ts, []).append(symbol)
        for ts, symbols in by_ts.items():
            start, end = ts // 1000, (ts + 900_000) // 1000
            fut = flow.candle_net(FUTURES_VENUES, start, end, now_sec)
            spot = flow.candle_net(extra_spot, start, end, now_sec) if extra_spot else None
            for symbol in symbols:
                row = flow.rows.get(symbol)
                if row is None:
                    continue
                self._agg_hist.setdefault(symbol, deque(maxlen=CONFIG.timeframe.rest_lookback_candles)).append(
                    (ts, float(fut[row]), float(spot[row]) if spot is not None else 0.0))

    def _agg_extras(self) -> Dict[str, Dict[str, float]]:
        window = CONFIG.metrics.spot_perp_window
        need = CONFIG.venues.agg_min_candles
        out = {}
        for symbol, hist in self._agg_hist.items():
            recent = list(hist)[-window:]
            out[symbol] = {'agg_fut_delta_1h': sum(f for _, f, _ in recent),
                           'agg_spot_extra_1h': sum(s for _, _, s in recent),
                           'agg_ready': 1.0 if len(hist) >= need else 0.0}
        return out

    @staticmethod
    def _heavy_pass(spot_frames: Dict, futures_frames: Dict, funding: Dict, tier0: Dict, closed_until: Dict,
                    extras: Dict) -> Tuple[pl.DataFrame, Dict[str, Dict]]:
        spot_all = compute_indicators_batch(spot_frames, funding)
        futures_all = compute_indicators_batch(futures_frames, funding)
        rows = score_closed(spot_all, futures_all, tier0, closed_until, extras)
        return futures_all, rows

    async def _perform_scan(self):
        spot_frames, futures_frames, funding, closed_until, signature = await self._merge_rows()
        self._accumulate_agg()
        tier0 = {s: md.tier0 for s, md in self.market_data.items()}

        # Heavy pass only when a candle closed / history changed: closed-candle scores don't change in between
        if signature != self._heavy_signature:
            started = time.time()
            futures_all, rows = await asyncio.to_thread(self._heavy_pass, spot_frames, futures_frames, funding,
                                                        tier0, closed_until, self._agg_extras())
            self._futures_closed, self._rows, self._heavy_signature = futures_all, rows, signature
            self._frame_parts = await asyncio.to_thread(self._split_frame, futures_all)
            self.last_heavy_sec = time.time() - started
            if self._context_task is None or self._context_task.done():
                self._context_task = asyncio.create_task(self._refresh_contexts())
            self._update_volatility(futures_all)
            self._update_market_state(futures_all)
            # Regimes only once every symbol's history is in: during the cold start each heavy pass saw a
            # different subset of coins and the label flipped every few seconds
            if self.regime_model is not None and self.fetcher.baselines_loaded() >= len(self.market_data):
                try:
                    regime = await asyncio.to_thread(self.regime_model.update, futures_all)
                    if regime != self.regime:
                        logger.info(f"Market regime: {self.regime} -> {regime}")
                    self.regime = regime
                except Exception as e:
                    logger.warning(f"Regime model failed: {e}")
            logger.debug(f"Heavy pass: {len(rows)} symbols in {self.last_heavy_sec:.2f}s")

        signals = signals_from_rows(self._rows, tier0)
        premiums = [p for md in self.market_data.values() if (p := self._coinbase_premium(md)) is not None]
        self._cb_median = statistics.median(premiums) if len(premiums) >= 10 else None
        for md in self.market_data.values():
            md.current_long_score = md.current_short_score = 0
        for symbol, sig in signals:
            md = self.market_data.get(symbol)
            if md is None:
                continue
            md.current_long_score, md.current_short_score = sig['long_score'], sig['short_score']
            self._enrich(symbol, md, sig)

        # Before the Tier-0 warm-up ends the 5m metrics span less than 5 minutes: no new signals or journal rows yet.
        # Raw anomalies must be present on two consecutive scans (structured ones come from closed candles already,
        # detected setups fire once per event).
        warmed_up = time.time() - self._started_at >= CONFIG.tier0.warmup_sec
        if warmed_up:
            signals += self._detect_setups()
        current_keys = {(symbol, sig['alert_type']) for symbol, sig in signals if not sig.get('is_setup')}
        persistent = [(symbol, sig) for symbol, sig in signals
                      if sig['is_structured'] or sig.get('is_setup') or (symbol, sig['alert_type']) in self._previous_keys]
        self._previous_keys = current_keys

        now = time.time()
        created, entries = self.book.update(
            persistent if warmed_up else [], _FrameLookup(self._frame_parts, self.market_data), self._price_of,
            self._minute_candles, now, confirm_of=self.fetcher.confirmations,
        )
        if self.journal:
            if warmed_up:
                await self.journal.arecord(persistent, {symbol: self._price_of(symbol) for symbol, _ in persistent})
                for tracked in entries:
                    await self.journal.arecord_entry(tracked)
            for tracked in self.book.finished_now:
                logger.info(f"Card {tracked.symbol} {tracked.group_key}: {tracked.status} - {tracked.finish_reason}")
                await self.journal.arecord_card(tracked)
            # the market baseline: every USDT perpetual (REST mark prices), not only the streamed universe
            await self.journal.asnapshot_universe(self.fetcher.market_marks or
                                                  {s: self._price_of(s) for s in self.market_data})
            if self.fetcher.liq_log:
                events, self.fetcher.liq_log = self.fetcher.liq_log, []
                await self.journal.arecord_liquidations(events)
        await self._output(created, [e for e in entries if not e.vetoed])
        if self.demo.enabled:
            # Demo orders off the scan: each call is a few REST round trips
            for tracked in entries:
                if not tracked.vetoed and warmed_up:
                    self._background_task(self.demo.on_entry(tracked))
            if warmed_up and time.time() - self._limits_synced >= 30:
                # resting BingX limits for the waiting touch cards (Seiden's line, the Silver Bullet's CE)
                self._limits_synced = time.time()
                waiting = [s for s in self.book.signals.values() if not s.finished and not s.entered_at
                           and s.status in ('WATCH', 'ZONE') and self.demo.is_limit_plan(s)]
                self._background_task(self.demo.sync_limits(waiting))
            for tracked, event in self.book.events:
                if event == 'ADD':
                    self._background_task(self.demo.on_add(tracked))
            for tracked in self.book.finished_now:
                self._background_task(self.demo.on_finish(tracked))

    def _detect_setups(self) -> List[Tuple[str, Dict]]:
        """Detected setups of this scan as signals (the coin's live Tier-0 metrics + the setup's leg / note)."""
        out: List[Tuple[str, Dict]] = []
        now_ms = int(time.time() * 1000)
        for symbol, md in self.market_data.items():
            if not self.detector.wants(symbol, md.minute_closed_until, md.tier0):
                continue
            bands = self.fetcher.depth.liquidity_bands(symbol)
            setups = self.detector.scan(symbol, self._minute_candles(symbol), md.tier0, now_ms, bands)
            connors = self._connors_daily(symbol, md, now_ms)
            if connors:
                setups.append(connors)
            turtle = self._turtle_breakout(symbol, md, now_ms)
            if turtle:
                setups.append(turtle)
            orb = self._orb_touch(symbol, md, now_ms)
            if orb:
                setups.append(orb)
            dump = self._dump_bounce(symbol, md, now_ms)
            if dump:
                setups.append(dump)
            bullet = self._silver_bullet(symbol, md, now_ms)
            if bullet:
                setups.append(bullet)
            setups.extend(self._pumps(symbol, md, now_ms))
            for setup in setups:
                sig = dict(md.tier0)
                sig.update(is_setup=True, is_structured=False, is_tier_0_anomaly=False, active_phases=[],
                           long_score=0, short_score=0, alert_type='LONG' if setup['direction'] > 0 else 'SHORT')
                sig.update(setup)
                row = self._rows.get(symbol) or {}
                # the closed candle's 1h spot-vs-perp reading (a breakout is vetoed perp-led like D / F)
                sig['perp_led_long'] = bool(row.get('perp_led_long'))
                sig['perp_led_short'] = bool(row.get('perp_led_short'))
                # the closed candle's 1h spot / perp flows (journal features, like the phase setups carry)
                for key in ('spot_delta_1h', 'perp_delta_1h', 'adx'):
                    if row.get(key) is not None:
                        sig[key] = row[key]
                if setup['setup'].startswith('SWEEP'):
                    self._sweep_wick(symbol, md, setup, sig)
                self._enrich(symbol, md, sig)
                logger.info(f"Setup detected: {symbol} {setup['setup']} - {setup['setup_note']}")
                out.append((symbol, sig))
        return out

    def _pumps(self, symbol: str, md: MarketData, now_ms: int) -> List[Dict]:
        """The pump's start (every final minute) and top (every 15m close), cheap gates first (strategies.pump)."""
        from strategies.pump import pump_start, pump_top
        minute = md.minute_closed_until
        if not minute or self._pump_checked.get(symbol) == minute:
            return []
        self._pump_checked[symbol] = minute
        minutes = self._minute_candles(symbol)
        if len(minutes) < 120:
            return []
        out = []
        cfg = CONFIG.strategies
        if minutes[-1][4] / minutes[-16][4] - 1 >= cfg.pump_start_min_pct:
            closes = [c[4] for c in part_candles(self._frame_parts.get(symbol))[0][-97:]]
            rets = [b / a - 1 for a, b in zip(closes, closes[1:]) if a]
            vol = (sum(r * r for r in rets) / len(rets)) ** 0.5 if len(rets) > 20 else None
            found = pump_start(minutes, md.tier0 or {}, vol, now_ms)
            if found and (symbol, found['anchor_ts'] // 3_600_000) not in self._pump_fired:
                self._pump_fired.add((symbol, found['anchor_ts'] // 3_600_000))
                out.append(found)
        if (minute + 60_000) % 900_000 == 0:
            window = [c for c in minutes if c[0] >= minute - 4 * 3_600_000]
            if window and max(c[2] for c in window) / min(c[3] for c in window) - 1 >= cfg.pump_top_min_pct:
                found = pump_top(minutes, md.tier0 or {}, minute + 60_000)
                if found and (symbol, 'top', found['anchor_ts']) not in self._pump_fired:
                    self._pump_fired.add((symbol, 'top', found['anchor_ts']))
                    out.append(found)
        return out

    def _silver_bullet(self, symbol: str, md: MarketData, now_ms: int) -> Optional[Dict]:
        """ICT's Silver Bullet (strategies.silver_bullet), only inside its New York windows, once per window and
        direction per coin, on each new final 5m bar."""
        from strategies.silver_bullet import FIVE_MS, silver_bullet, window_of
        start = window_of(now_ms)
        minute = md.minute_closed_until
        if start is None or not minute or (minute + 60_000) % FIVE_MS:
            return None
        if self._sb_checked.get(symbol) == minute:
            return None
        self._sb_checked[symbol] = minute
        bars = resample([c for c in self._minute_candles(symbol) if c[0] >= start - 3_600_000], 5,
                        minute + 60_000)
        found = silver_bullet(bars, now_ms)
        if found is None:
            return None
        key = (symbol, found['direction'], start)
        if key in self._sb_fired:
            return None
        self._sb_fired.add(key)
        return found

    def _turtle_breakout(self, symbol: str, md: MarketData, now_ms: int) -> Optional[Dict]:
        """The Turtles' channel breakout on the touch (strategies.turtle), checked on each new final minute, once per
        coin, direction and day."""
        if len(md.d1) < 60:
            return None
        minute = md.minute_closed_until
        if not minute or self._turtle_checked.get(symbol) == minute:
            return None
        self._turtle_checked[symbol] = minute
        minutes = self._minute_candles(symbol)
        day_start = int(now_ms // 86_400_000 * 86_400_000)
        today = [c for c in minutes if c[0] >= day_start]
        if not today or int(md.d1[-1][0]) + 86_400_000 < day_start:
            return None                           # yesterday's daily candle not loaded yet
        last = today[-1]
        # cheap gate first: the minute reached the nearer of the 20 / 55-day channels at all (building the 15m candles
        # of every coin each minute stalled the loop 1.4s live)
        recent = md.d1[-20:]
        if not (last[2] > max(c[2] for c in recent) or last[3] < min(c[3] for c in recent)) and                 not (last[2] > max(c[2] for c in md.d1[-55:]) or last[3] < min(c[3] for c in md.d1[-55:])):
            return None
        # today's range BEFORE the last final minute: the 15m candles of the day (complete from 00:00 UTC whatever
        # the 1m history holds after a restart) plus the earlier minutes
        m15 = [c for c in part_candles(self._frame_parts.get(symbol))[0] if day_start <= c[0] < last[0] // 900_000 * 900_000]
        earlier = [c for c in today[:-1]] + m15
        if not earlier:
            return None                           # no record of the day before this minute: cannot tell a fresh touch
        from strategies.turtle import turtle_breakout
        found = turtle_breakout(md.d1, last[2], last[3], now_ms,
                                max(c[2] for c in earlier), min(c[3] for c in earlier))
        if found is None:
            return None
        key = (symbol, found['direction'], day_start)
        if key in self._turtle_fired:
            return None
        self._turtle_fired.add(key)
        return found

    def _opposite_band(self, symbol: str, direction: int) -> Optional[float]:
        """BB(20, 2) of the closed 15m candles: the upper band for a long, the lower for a short (Bollinger exit)."""
        closes = [c[4] for c in part_candles(self._frame_parts.get(symbol))[0][-20:]]
        if len(closes) < 20:
            return None
        mean = sum(closes) / 20
        sd = (sum((x - mean) ** 2 for x in closes) / 20) ** 0.5       # population sigma (Bollinger)
        return mean + direction * 2 * sd

    def _orb_touch(self, symbol: str, md: MarketData, now_ms: int) -> Optional[Dict]:
        """Crabel's ORB (strategies.classic.orb_event): the day's open +- Stretch touched by the last final minute,
        once per coin and day (eng-55)."""
        if len(md.d1) < 10:
            return None
        minute = md.minute_closed_until
        if not minute or self._orb_checked.get(symbol) == minute:
            return None
        self._orb_checked[symbol] = minute
        day_start = int(now_ms // 86_400_000 * 86_400_000)
        if (symbol, day_start) in self._orb_fired or int(md.d1[-1][0]) + 86_400_000 < day_start:
            return None                           # traded today / yesterday's daily candle not loaded yet
        minutes = self._minute_candles(symbol)
        today = [c for c in minutes if c[0] >= day_start]
        if not today:
            return None
        last = today[-1]
        m15 = [c for c in part_candles(self._frame_parts.get(symbol))[0] if day_start <= c[0] < last[0] // 900_000 * 900_000]
        first = m15[0] if m15 and m15[0][0] == day_start else today[0] if today[0][0] == day_start else None
        if first is None:
            return None                           # the day's open is not known (restart mid-day): no ORB today
        earlier = today[:-1] + m15
        from strategies.classic import orb_event
        found = orb_event(md.d1, first[1], last[2], last[3],
                          max(c[2] for c in earlier) if earlier else None,
                          min(c[3] for c in earlier) if earlier else None, now_ms)
        if found is not None:
            self._orb_fired.add((symbol, day_start))
        return found

    def _dump_bounce(self, symbol: str, md: MarketData, now_ms: int) -> Optional[Dict]:
        """The short of the first bounce after a dump (strategies.pump.dump_bounce) on each closed 1h candle."""
        h1 = list(md.h1)
        if len(h1) < 190:
            return None
        closed = int(h1[-1][0])
        if self._dump_checked.get(symbol) == closed:
            return None
        self._dump_checked[symbol] = closed
        from strategies.pump import MAJORS, dump_bounce
        if symbol.split('/')[0] in MAJORS:
            return None                           # measured on small caps (research_pumps: majors apart)
        found = dump_bounce(h1, now_ms)
        if found is None or (symbol, found['anchor_ts']) in self._dump_fired:
            return None
        self._dump_fired.add((symbol, found['anchor_ts']))
        return found

    def _connors_daily(self, symbol: str, md: MarketData, now_ms: int) -> Optional[Dict]:
        """Connors' RSI(2) on the coin's daily candles, once per closed day (fresh within the day's first 2 hours)."""
        if len(md.d1) < 202:
            return None
        day_close = int(md.d1[-1][0]) + 86_400_000
        if self._connors_checked.get(symbol) == day_close or now_ms - day_close > 2 * 3_600_000:
            return None
        self._connors_checked[symbol] = day_close
        from strategies.classic import connors_event
        return connors_event(md.d1)

    def _sweep_wick(self, symbol: str, md: MarketData, setup: Dict, sig: Dict):
        """
        What happened on the sweep candle (journal features; stats decide whether they matter): liquidations of the
        swept side on every venue (the stops that ran are forced exits) and the Binance OI change across the candle.
        """
        from flow import LIQ_LONG, LIQ_SHORT
        start = int(setup['anchor_ts']) // 1000
        field = LIQ_LONG if setup['direction'] > 0 else LIQ_SHORT          # a sweep of lows took the longs' stops
        sig['liq_on_wick'] = self.fetcher.flow.symbol_range(symbol, field, start, start + 900)
        before = [v for t, v in md.oi_samples if t <= start * 1000]
        after = [v for t, v in md.oi_samples if t <= (start + 900) * 1000]
        sig['oi_change_sweep'] = after[-1] / before[-1] - 1 if before and after and before[-1] else None

    def _maps_executor(self):
        """
        One worker PROCESS for level maps (zones.build_raw + detector contexts, pure Python): in threads they held the
        GIL after every 15m close while ~300 maps were rebuilt, and the loop stalled 1-4s.
        """
        if self._maps_pool is not None and getattr(self._maps_pool, '_broken', False):
            # a worker that died (killed when RAM ran out) breaks the pool for good: every later map failed until a
            # restart (live 2026-09-30 23:28) - a new pool instead
            logger.warning("Maps worker process died: starting a new one")
            self._maps_pool.shutdown(wait=False, cancel_futures=True)
            self._maps_pool = None
        if self._maps_pool is None:
            import multiprocessing
            import os
            from concurrent.futures import ProcessPoolExecutor
            from watchdog import exit_with_parent
            self._maps_pool = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context('spawn'),
                                                  initializer=exit_with_parent, initargs=(os.getpid(),))
        return self._maps_pool

    def _map_job(self, symbol: str, part: pl.DataFrame, with_context: bool, now_ms: float) -> tuple:
        """
        Inputs of one map, copied on the loop (the deques change under the loop; a copy is consistent); the 15m frame is
        sent as its few needed columns and turned into candles in the worker.
        """
        md = self.market_data[symbol]
        # What crosses to the process is pickled on a feeder thread (GIL): only liquidations of the 24h the map reads,
        # and no 4-day 5m history for a quick map of a coin whose full map (levels_loop) already has it
        liq = [e for e in md.liq_events if now_ms - e[0] <= 86_400_000]
        candles_4d = list(md.htf_5m) if not with_context or symbol not in self._level_raw else []
        # crypto_maniac's systems read 499 15m / 1h candles: sent as numpy arrays (pickled as one buffer, not ~3500
        # float objects per coin on the feeder thread)
        long_15m = np.asarray(md.m15_long, dtype=np.float64) if with_context and len(md.m15_long) else ()
        long_1h = np.asarray(md.h1_long, dtype=np.float64) if with_context and len(md.h1_long) else ()
        return (symbol, part.select(PART_COLUMNS), list(md.h1), list(md.htf_klines), list(md.htf_oi), liq, now_ms,
                candles_4d, with_context, long_15m, long_1h, list(md.d1)[-60:], list(md.h4), list(md.w1))

    def _correlates(self) -> Dict[str, np.ndarray]:
        """The SMT correlates' 15m histories (BTC for every coin, ETH for BTC): the long REST history + the frame."""
        out = {}
        for name in ('BTC', 'ETH', 'SOL'):
            symbol = f"{name}/USDT:USDT"
            md = self.market_data.get(symbol)
            if md is None:
                continue
            candles, _ = part_candles(self._frame_parts.get(symbol))
            merged = {int(c[0]): [float(v) for v in c] for c in md.m15_long}
            merged.update({int(c[0]): list(c) for c in candles})
            if merged:
                out[name] = np.asarray([merged[t] for t in sorted(merged)], dtype=np.float64)
        return out

    async def _build_maps(self, jobs: List[tuple]) -> Dict[str, tuple]:
        if not jobs:
            return {}
        corr = self._correlates() if any(job[8] for job in jobs) else None
        from concurrent.futures.process import BrokenProcessPool
        try:
            return await asyncio.get_running_loop().run_in_executor(self._maps_executor(), build_maps, jobs, corr)
        except BrokenProcessPool:
            logger.warning(f"Maps worker died during a pass of {len(jobs)} maps: retried on the next pass")
            return {}

    async def _refresh_contexts(self):
        """Quick level maps / sweep pools of every coin whose closed 15m candles changed (worker process)."""
        while True:
            parts = self._frame_parts
            now_ms = time.time() * 1000
            jobs, signatures = [], {}
            for symbol, part in parts.items():
                if symbol not in self.market_data or part.is_empty():
                    continue
                signature = (part['timestamp'][-1], part.height)
                if self._context_sig.get(symbol) == signature:
                    continue
                jobs.append(self._map_job(symbol, part, True, now_ms))
                signatures[symbol] = signature
            try:
                results = await self._build_maps(jobs)
            except Exception as e:
                logger.warning(f"Quick level maps failed: {e}")
                return
            for symbol, (raw, context) in results.items():
                if symbol not in self.market_data:
                    continue
                self._context_sig[symbol] = signatures[symbol]
                self._quick_raw[symbol] = raw
                self.detector.set_context(symbol, context, int(time.time() * 1000))
            if parts is self._frame_parts:
                return

    @staticmethod
    def _split_frame(frame: pl.DataFrame) -> Dict[str, pl.DataFrame]:
        if frame.is_empty() or 'symbol' not in frame.columns:
            return {}
        return {key[0]: part for key, part in frame.partition_by('symbol', as_dict=True, maintain_order=True).items()}

    def _update_volatility(self, futures_all: pl.DataFrame):
        """Typical 15m price / OI moves from the heavy pass (Tier-0 z-scores)."""
        if futures_all.is_empty() or 'ret_std' not in futures_all.columns:
            return
        last = futures_all.group_by('symbol', maintain_order=True).agg(pl.col('ret_std').last(), pl.col('oi_std').last())
        for symbol, ret_std, oi_std in last.iter_rows():
            md = self.market_data.get(symbol)
            if md is not None:
                md.ret_std, md.oi_std = ret_std, oi_std

    def _update_market_state(self, futures_all: pl.DataFrame):
        """
        The market every setup trades in (a feature, journaled and learned): the universe's median 15m-close move
        over the last 1h / 4h and BTC's last 1h - one market factor explains about half of all coins' moves.
        """
        if futures_all.is_empty():
            return
        last = futures_all.group_by('symbol', maintain_order=True).agg(
            (pl.col('close').last() / pl.col('close').tail(5).first() - 1).alias('r1h'),
            (pl.col('close').last() / pl.col('close').tail(17).first() - 1).alias('r4h'))
        r1h = last['r1h'].drop_nulls()
        r4h = last['r4h'].drop_nulls()
        btc = last.filter(pl.col('symbol') == 'BTC/USDT:USDT')
        # Weekly breadth: the share of the universe above its weekly EMA (a slow market state the 1h regimes miss;
        # 5-15% in April-July 2026, 75% in September)
        trends = [trend_w_of(md.w1_ref, self._price_of(s)) for s, md in self.market_data.items()]
        trends = [t for t in trends if t is not None]
        self.market_state = {
            'mkt_1h': float(r1h.median()) if len(r1h) else None,
            'mkt_4h': float(r4h.median()) if len(r4h) else None,
            'btc_1h': float(btc['r1h'][0]) if btc.height and btc['r1h'][0] is not None else None,
            'breadth_w': sum(t > 0 for t in trends) / len(trends) if len(trends) >= 20 else None,
        }

    def _positioning_features(self, symbol: str, md: MarketData) -> Dict:
        """
        eng-52 journal features (Compass review; context only, no rule uses them except the premium in `crowded`):
        the mark-vs-index premium over the last hour and its z-score against 24h (Binance's funding is stuck at 0.01%
        inside the premium's neutral band), the 1h funding mode (Binance moves a contract to hourly funding after a
        capped settlement), OI / 24h volume (leverage), Kaufman's efficiency ratio and the Choppiness index of the
        last 14 hours, and the coin's 24h return net of BTC x beta in its own residual std (relative strength).
        """
        import math
        out: Dict = {}
        oi5, p5 = (md.tier0 or {}).get('oi_change_5m'), (md.tier0 or {}).get('price_change_5m')
        out['liq_proxy'] = max(0.0, -oi5) if oi5 is not None and p5 is not None and p5 < 0 else 0.0 \
            if oi5 is not None else None
        hist = list(md.premium_hist)
        if len(hist) >= 20:
            now = hist[-1][0]
            last_h = [p for t, p in hist if now - t <= 3_600_000]
            vals = [p for _, p in hist]
            mean = sum(vals) / len(vals)
            sd = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
            out['prem_1h'] = sum(last_h) / len(last_h) if last_h else None
            out['prem_z'] = (out['prem_1h'] - mean) / sd if sd > 0 and out['prem_1h'] is not None else None
        hours = self.fetcher.funding_interval_hours.get(symbol)
        out['funding_1h'] = 1.0 if hours == 1 else 0.0 if hours else None
        state = (self.fetcher.venue_derivs.get(symbol) or {}).get('binance')
        out['oi_vol'] = state.oi_usd / md.quote_volume_24h if state is not None and state.oi_usd and \
            md.quote_volume_24h else None
        h1 = list(md.h1)[-15:]
        if len(h1) == 15:
            closes = [c[4] for c in h1]
            path = sum(abs(b - a) for a, b in zip(closes, closes[1:]))
            out['er_1h'] = abs(closes[-1] - closes[0]) / path if path else None
            trs = [max(c[2] - c[3], abs(c[2] - p[4]), abs(c[3] - p[4])) for p, c in zip(h1, h1[1:])]
            span = max(c[2] for c in h1[1:]) - min(c[3] for c in h1[1:])
            out['chop_1h'] = 100 * math.log10(sum(trs) / span) / math.log10(14) if span > 0 and sum(trs) > 0 else None
        btc = self.market_data.get('BTC/USDT:USDT')
        if btc is not None and not symbol.startswith('BTC/') and len(md.h1) >= 169 and len(btc.h1) >= 169:
            a = {int(c[0]): c[4] for c in list(md.h1)[-169:]}
            b = {int(c[0]): c[4] for c in list(btc.h1)[-169:]}
            ts = sorted(set(a) & set(b))
            ra = [a[y] / a[x] - 1 for x, y in zip(ts, ts[1:])]
            rb = [b[y] / b[x] - 1 for x, y in zip(ts, ts[1:])]
            if len(ra) >= 100:
                mb = sum(rb) / len(rb)
                vb = sum((x - mb) ** 2 for x in rb)
                beta = sum((x - mb) * (y - sum(ra) / len(ra)) for x, y in zip(rb, ra)) / vb if vb else 1.0
                resid = [y - beta * x for x, y in zip(rb, ra)]
                sd = (sum(e * e for e in resid) / len(resid)) ** 0.5
                r24 = sum(resid[-24:])
                out['rs_btc_z'] = r24 / (sd * 24 ** 0.5) if sd > 0 else None
        return out

    def _enrich(self, symbol: str, md: MarketData, sig: Dict):
        """Live context that is not part of the scored row."""
        sig.update(self.market_state)
        sig.update(self.ext.market)
        sig.update(self.ext.of(symbol))
        sig.update(self.fetcher.icebergs.features(symbol))
        ctx = self.detector.context.get(symbol)
        sig['coin_trend'] = ctx.trend if ctx is not None else None
        # ICT's daily bias: yesterday closed above the day before's high = bullish (the draw is the next buy-side
        # liquidity), below its low = bearish, inside = none (the 1h trend decides then)
        if len(md.d1) >= 2:
            prev, last = md.d1[-2], md.d1[-1]
            sig['daily_bias'] = 1 if last[4] > prev[2] else -1 if last[4] < prev[3] else 0
        # the trend of every higher timeframe (EMA20 slope, structure.coin_trend): Elder's tide is ~5x the leg's
        # timeframe (15m leg -> 1h, 1h -> 4h, 4h -> daily), Seiden's curve and Wyckoff's context read the daily one
        from strategies.structure import coin_trend
        sig['trend_4h'] = coin_trend(md.h4) if len(md.h4) >= 30 else None
        sig['trend_1d'] = coin_trend(md.d1) if len(md.d1) >= 30 else None
        # the weekly one, the top of ICT's top-down order (week -> day -> entry)
        if len(md.w1) >= 2:
            prev, last = md.w1[-2], md.w1[-1]
            sig['weekly_bias'] = 1 if last[4] > prev[2] else -1 if last[4] < prev[3] else 0
        sig['vol_ratio'] = ctx.vol_ratio if ctx is not None else None
        sig.update(self._positioning_features(symbol, md))
        # eng-53: Binance's Monitoring Tag / a scheduled delisting (longs vetoed 'event_risk'), the nearness to the
        # 52-week high (Jia et al. 2025: predicts next week's cross-section; ours: rank IC +0.09, t 2.9, quintile
        # spread n.s.), the coin's 24h volume rank (reversal after extremes is an illiquid-coin effect)
        risk = getattr(self, 'event_risk', None)
        sig['event_risk'] = risk.of(symbol) if risk is not None else None
        closes = [c[4] for c in list(md.d1)[-365:]]
        price = self._price_of(symbol)
        sig['near52'] = price / max(closes) if len(closes) >= 250 and price and max(closes) > 0 else None
        vols = sorted((m.quote_volume_24h or 0.0 for m in self.market_data.values()), reverse=True)
        sig['vol_rank'] = float(1 + sum(1 for v in vols if v > (md.quote_volume_24h or 0.0))) if vols else None
        sig['trend_w'] = trend_w_of(md.w1_ref, self._price_of(symbol))
        sig['volume_24h'] = md.quote_volume_24h or None
        sig['tier2_active'] = md.trades_subscribed
        sig['futures_cvd'] = sig.get('futures_cvd_5m', 0.0)
        sig['whales'] = self.fetcher.whales.flow(symbol, CONFIG.sweeps.window_sec)
        sig['whale_size'] = self.fetcher.whales.whale_size(symbol)
        sig['has_spot'] = bool(md.spot_symbol)
        sig['top_venue'] = md.tier0.get('top_venue', '')
        ratios = self.positioning.ratios.get(symbol, {})
        sig['top_ratio'] = ratios.get('binance_top_pos')
        sig['ls_global'] = ratios.get('binance_global')
        sig['ls_top'] = ratios.get('binance_top_acc')
        sig['ls_bybit'] = ratios.get('bybit')
        sig['ls_okx'] = ratios.get('okx')
        hl = self.positioning.hl_summary(symbol)
        sig.update(hl)
        # the tracked accounts' net position: 0 when none of them holds the coin; no value only where the coin
        # is not listed on Hyperliquid (or before the first positions refresh)
        on_hl = 'hyperliquid' in self.fetcher.symbol_map.by_key.get(symbol, {}) and self.positioning.hl_ts > 0
        sig['hl_net_usd'] = hl['hl_long_usd'] - hl['hl_short_usd'] if on_hl else None
        # relative to the universe median: the raw premium is USD vs USDT and carries the USDT basis (~a few bp)
        premium = self._coinbase_premium(md)
        sig['cb_premium'] = premium - self._cb_median if premium is not None and self._cb_median is not None else None
        now = time.gmtime()
        sig['hour_utc'], sig['weekend'] = now.tm_hour, int(now.tm_wday >= 5)
        sig['basis'] = md.basis
        sig['book_eaten'] = md.book_eaten
        depth = self.fetcher.depth.metrics(symbol)
        sig['depth_imb'] = depth.get('imbalance_1') if depth else None
        sig['depth'] = depth
        derivs = self.fetcher.deriv_snapshot(symbol)
        sig['agg_oi_change_1h'] = derivs['agg_oi_change_1h']
        sig['agg_funding_8h'] = derivs['agg_funding_8h']
        sig['oi_venues'] = derivs['oi_venues']
        sig['regime'] = self.regime
        success = self.journal.success if self.journal else None
        sig['p_mature'] = bool(success and success.mature)
        if not sig.get('funding_rate'):
            sig['funding_rate'] = md.funding_rate

    def _coinbase_premium(self, md: MarketData) -> Optional[float]:
        """
        Coinbase USD price vs Binance spot (USDT): the live Coinbase trade when it is fresh, else Coinbase's last price
        from the bulk products call (at most two calls old); no value only for a coin not listed on Coinbase.
        """
        now_ms = time.time() * 1000
        max_age = CONFIG.positioning.coinbase_max_age_sec * 1000
        spot = md.spot_minute_klines[-1] if md.spot_minute_klines else None
        if not spot or now_ms - spot[0] > max_age + 60_000:
            return None
        if md.coinbase_price and now_ms - md.coinbase_ts <= max_age:
            coinbase = md.coinbase_price
        elif md.coinbase_rest_price and now_ms - md.coinbase_rest_ts <= 2 * self.fetcher.COINBASE_PRODUCTS_INTERVAL_SEC * 1000:
            coinbase = md.coinbase_rest_price
        else:
            return None
        # Binance spot is quoted in the unprefixed coin (PEPE), the key's unit may be 1000PEPE
        binance = spot[4] * self.fetcher.symbol_map.key_multiplier.get(md.symbol, 1.0)
        return coinbase / binance - 1 if binance else None

    def _minute_candles(self, symbol: str):
        """FINAL futures 1m candles only: entry triggers are closes, and a running minute's close is just the live price."""
        md = self.market_data.get(symbol)
        if md is None:
            return []
        return [c for c in md.minute_klines if c[0] <= md.minute_closed_until]

    PRICE_MAX_AGE_SEC = 60

    def _price_of(self, symbol: str) -> Optional[float]:
        """
        Freshest futures price: the latest ticker sample or the 1m kline close, whichever is newer. None when both
        are older than PRICE_MAX_AGE_SEC, so a stalled stream never drives SL/TP decisions with a frozen price.
        """
        md = self.market_data.get(symbol)
        if md is None:
            return None
        now_ms = time.time() * 1000
        candidates = []
        if md.ticker_samples:
            ts, price, _ = md.ticker_samples[-1]
            candidates.append((ts, price))
        if md.minute_klines:
            candle = md.minute_klines[-1]
            candidates.append((min(now_ms, candle[0] + 60_000), candle[4]))
        fresh = [(ts, p) for ts, p in candidates if p and now_ms - ts <= self.PRICE_MAX_AGE_SEC * 1000]
        return float(max(fresh)[1]) if fresh else None

    # ------------------------------------------------------------------ level maps (zones.py)

    def _candles_15m(self, symbol: str) -> Tuple[List[List[float]], Optional[float]]:
        """Closed 15m futures candles [ts, o, h, l, c, quote_vol, taker_buy] and the latest ATR."""
        return self._part_candles(self._frame_parts.get(symbol))

    @staticmethod
    def _part_candles(part: Optional[pl.DataFrame]) -> Tuple[List[List[float]], Optional[float]]:
        return part_candles(part)

    def _build_levels(self, symbol: str) -> Tuple[List[RawLevel], Optional[float], List[List[float]]]:
        md = self.market_data.get(symbol)
        candles, atr = self._candles_15m(symbol)
        if md is None or not candles or not atr:
            return [], atr, candles
        raw = build_raw(candles, md.htf_klines, md.htf_oi, list(md.liq_events), atr, time.time() * 1000,
                        candles_4d=md.htf_5m)
        return raw, atr, candles

    async def levels_loop(self):
        """
        Keep the level map of every coin with an open card: 1h history (REST, hourly), rebuilt in a worker thread
        when a 15m candle closed, the 1h history changed or refresh_sec passed.
        """
        while self._running:
            await asyncio.sleep(15)
            try:
                symbols = sorted({s.symbol for s in self.book.signals.values() if not s.finished})
                for symbol in list(self._level_raw):
                    if symbol not in symbols:
                        self._level_raw.pop(symbol, None)
                        self._level_sig.pop(symbol, None)
                jobs, signatures = [], {}
                now_ms = time.time() * 1000
                for symbol in symbols:
                    md = self.market_data.get(symbol)
                    if md is None:
                        continue
                    await self.fetcher.load_htf(symbol)
                    signature = (md.closed_until, md.htf_loaded, int(time.time() // CONFIG.zones.refresh_sec))
                    if self._level_sig.get(symbol) == signature:
                        continue
                    part = self._frame_parts.get(symbol)
                    if part is not None and not part.is_empty():
                        jobs.append(self._map_job(symbol, part, False, now_ms))
                        signatures[symbol] = signature
                # Full maps of the card coins in the maps worker process (pure Python: off the GIL of the loop)
                for symbol, (raw, _) in (await self._build_maps(jobs)).items():
                    if raw and symbol in self.market_data:
                        self._level_raw[symbol], self._level_sig[symbol] = raw, signatures[symbol]
                        # Snapshot of the liquidation levels this map expects (forward test, see journal.py)
                        levels = [(l.kind, l.price, l.side, l.size) for l in raw + self._live_levels(symbol)
                                  if l.kind in ('liq_est', 'liq_hl')]
                        if self.journal and levels:
                            await self.journal.arecord_liq_levels(int(now_ms), symbol, self._price_of(symbol), levels)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"Level maps failed: {e}", exc_info=True)

    def _live_levels(self, symbol: str) -> List[RawLevel]:
        """Order-book walls standing >= 10s (hot coins only) and Hyperliquid large accounts' liquidation prices."""
        depth = self.fetcher.depth.metrics(symbol) or {}
        out = self.positioning.hl_levels(symbol, self._price_of(symbol))
        if depth.get('bid_wall'):
            out.append(RawLevel(depth['bid_wall'], 'wall', 'bid wall', -1))
        if depth.get('ask_wall'):
            out.append(RawLevel(depth['ask_wall'], 'wall', 'ask wall', +1))
        # Heatmap: resting liquidity that stayed in the book (not a flashed wall)
        for price, side, usd in self.fetcher.depth.liquidity_bands(symbol):
            out.append(RawLevel(price, 'book', f"{'bid' if side > 0 else 'ask'} liquidity ${usd / 1e3:,.0f}k", -side, usd))
        return out

    def _plan_key(self, symbol: str) -> Optional[tuple]:
        """
        Everything a card's plan is computed from; the book recomputes the plan only when this changes. Items 1-3 are
        the live 15m candle (only leg plans follow it: signal_book.LIVE_KEY).
        """
        md = self.market_data.get(symbol)
        part = self._frame_parts.get(symbol)
        if md is None or part is None:
            return None
        live = md.live_candle('futures') or {}
        depth = self.fetcher.depth.metrics(symbol) or {}
        walls = (depth.get('bid_wall'), depth.get('ask_wall'))
        return (id(part), live.get('timestamp'), live.get('high'), live.get('low'),
                self._level_sig.get(symbol), self._context_sig.get(symbol), md.htf_loaded, self.positioning.hl_ts, walls,
                self.fetcher.depth.bands_version(symbol))

    def _levels_of(self, symbol: str) -> Optional[List[RawLevel]]:
        # The full map of a card coin (1h history, liquidation estimates), else the quick map of its 15m candles
        levels = (self._level_raw.get(symbol) or self._quick_raw.get(symbol, [])) + self._live_levels(symbol)
        return levels or None

    async def coin_detail(self, symbol: str) -> Dict:
        """One coin for the web page: candles, the level map (the card's plan when there is one), open cards."""
        md = self.market_data[symbol]
        # The page must not wait for REST (3 requests, one of weight 10, queued behind the rate budget: ~40s when
        # many coins were opened): answer with what is in memory, load the history in the background, and the page
        # asks again while htf_loaded is 0
        if not md.htf_loaded:
            self.fetcher.load_htf_background(symbol)
        raw, atr, candles = await asyncio.to_thread(self._build_levels, symbol)
        live = md.live_candle('futures')
        if live and candles and live['timestamp'] > candles[-1][0]:
            candles = candles + [[live['timestamp'], live['open'], live['high'], live['low'], live['close'], 0.0, 0.0]]
        cards = [s for s in self.book.signals.values() if s.symbol == symbol]
        zones = []
        for s in cards:
            if s.plan and s.plan.get('zones'):
                zones = s.plan['zones']
                break
        if not zones and atr:
            zones = merge(raw + self._live_levels(symbol), atr, symbol=symbol)
        price = self._price_of(symbol)
        if price and atr:
            zones = [z for z in zones if abs(z.price - price) <= 25 * atr]
        from webui import card_view
        now = time.time()
        # 5m: the 4-day REST history (level-map input) extended by the live 1m stream
        stream_5m = resample(list(md.minute_klines), 5)
        history_5m = [c for c in md.htf_5m if not stream_5m or c[0] < stream_5m[0][0]]
        candles_5m = history_5m + stream_5m
        # 1h: 4 days, so a leg of hours or days is visible whole
        candles_1h = list(md.htf_klines)
        # the two-sided scenario card (1h ladder; the same level code the probability model was trained with)
        btc = self.market_data.get('BTC/USDT:USDT')
        btc_closes = [c[4] for c in btc.h1] if btc and btc.h1 else None
        try:
            scenario = await asyncio.to_thread(scenarios.build, list(md.h1), price, now * 1000, btc_closes,
                                               (), None, self.macro.features(now * 1000),
                                               list(md.htf_1d) or None, list(md.htf_1h_30d) or None)
            if scenario is not None:
                scenario['macro'] = self.macro.snapshot(now * 1000)
        except Exception as e:
            logger.warning(f"scenario for {symbol} failed: {e}")
            scenario = None
        return {
            'scenario': scenario,
            'symbol': symbol, 'price': price, 'atr': atr,
            'candles_15m': candles,
            'candles_5m': candles_5m,
            'candles_1h': candles_1h,
            'zones': [z.as_dict() for z in zones],
            'cards': [card_view(s, now) for s in cards],
            'liquidations': [list(e) for e in md.liq_events if now * 1000 - e[0] <= 86_400_000][-300:],
            'heatmap': self.fetcher.depth.heatmap(symbol),
            'htf_loaded': md.htf_loaded,
        }

    # ------------------------------------------------------------------ background loops

    async def event_risk_loop(self):
        """Binance's Monitoring Tag and scheduled perpetual delistings (event_risk.py), hourly, off the loop."""
        from event_risk import EventRisk
        self.event_risk = getattr(self, 'event_risk', None) or EventRisk()
        while self._running:
            try:
                await asyncio.to_thread(self.event_risk.refresh)
            except Exception as e:
                logger.warning(f"Event risk refresh failed: {e!r}")
            await asyncio.sleep(3600)

    async def pools_loop(self):
        """Per-strategy coin pools (pools.py), rebuilt every CONFIG.pools.refresh_sec off the loop."""
        self.book.pool_of = self.pools.allows
        await asyncio.sleep(120)                     # after the 1h candles and 24h volumes are in
        while self._running:
            try:
                since = int((time.time() - CONFIG.pools.lookback_days * 86400) * 1000)
                sector_map = await asyncio.to_thread(sectors.load)
                results = await asyncio.to_thread(self.journal.coin_results, since) if self.journal else []
                await asyncio.to_thread(self.pools.rebuild, dict(self.market_data), sector_map, results)
                sizes = {k: len(v) for k, v in self.pools.members.items()}
                excl = sum(len(v) for v in self.pools.excluded.values())
                logger.info(f"Coin pools rebuilt: {sizes}; {excl} coin x strategy pairs excluded by their results")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"Coin pools refresh failed: {e}")
            await asyncio.sleep(CONFIG.pools.refresh_sec)

    async def macro_loop(self):
        """FRED macro context (US10Y, dollar index, Brent) for the scenario card, refreshed every 6h off the loop."""
        while self._running:
            try:
                ok = await asyncio.to_thread(self.macro.refresh)
                if not ok:
                    logger.warning("Macro context (FRED) unavailable; scenario cards run without it")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"Macro refresh failed: {e}")
            await asyncio.sleep(6 * 3600)

    async def universe_loop(self):
        """Re-select the universe hourly: new listings join, dropped coins leave (open cards finish first)."""
        while self._running:
            try:
                # hourly, or a minute after Binance announced a listing / status change (!contractInfo)
                await asyncio.wait_for(self.fetcher.contract_event.wait(), CONFIG.exchange.universe_refresh_sec)
                self.fetcher.contract_event.clear()
                await asyncio.sleep(60)
            except asyncio.TimeoutError:
                pass
            try:
                symbols = await self.fetcher.fetch_top_symbols()
                keep = {s.symbol for s in self.book.signals.values() if not s.finished}
                added, removed = self.fetcher.apply_universe(symbols, keep)
                if not added and not removed:
                    continue
                logger.info(f"Universe refresh: +{len(added)} {added[:10]} / -{len(removed)} {removed[:10]}")
                self.market_data = self.fetcher.markets
                for s in removed:
                    self._rows.pop(s, None)
                    self._agg_hist.pop(s, None)
                    self._quick_raw.pop(s, None)
                    self._context_sig.pop(s, None)
                    self.detector.forget(s)
                self._heavy_signature = None
                await self.fetcher.restart_streams(list(self.market_data))
                if added:
                    self.fetcher._spawn(self.fetcher.fetch_rest_baselines(added))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if not NETWORK.failed("universe refresh", e):
                    logger.warning(f"Universe refresh failed: {e}")

    async def positioning_loop(self):
        """
        Long / short ratios (Binance, Bybit, OKX; context and journal features): coins with open cards every
        positioning_cache_sec, every other universe coin every positioning_universe_sec, cards first.
        """
        cfg = CONFIG.rest
        while self._running:
            await asyncio.sleep(30)
            try:
                cards = sorted({s.symbol for s in self.book.signals.values() if not s.finished})
                due = [s for s in cards if self.positioning.ratio_age(s) >= cfg.positioning_cache_sec]
                due += [s for s in self.market_data
                        if s not in cards and self.positioning.ratio_age(s) >= cfg.positioning_universe_sec]
                if due:
                    await self.positioning.refresh_ratios(due)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug(f"Positioning refresh failed: {e}")

    async def state_loop(self):
        """Every minute: persist state and log a health line (loop timings, per-venue message rates)."""
        last_counts: Dict[str, int] = {}
        last_bytes: Dict[str, int] = {}
        try:
            import psutil
            proc = psutil.Process()
            proc.cpu_percent(None)   # the first reading only starts the measurement
        except Exception:
            proc = None
        while self._running:
            await asyncio.sleep(60)
            await asyncio.to_thread(self._save_state)
            status = self.fetcher.venue_status()
            rates = []
            for venue, st in sorted(status.items()):
                count = st.get('messages', 0)
                lag = (st.get('lag_ms') or 0) / 1000
                kb = (st.get('bytes', 0) - last_bytes.get(venue, 0)) / 60 / 1024
                last_bytes[venue] = st.get('bytes', 0)
                rate = f"{venue} {(count - last_counts.get(venue, 0)) / 60:.0f}/s {kb:.0f}KB/s"
                if not st.get('connected', 1):
                    rate += " DOWN"
                if lag > 1.5:
                    rate += f" lag {lag:.1f}s"
                rates.append(rate)
                last_counts[venue] = count
            process = ""
            if proc is not None:
                # cpu: % of one core over the last minute
                process = f", cpu {proc.cpu_percent(None):.0f}%, mem {proc.memory_info().rss / 2**20:.0f}MB"
            ctxs = [c for c in self.detector.context.values() if c is not None]
            pairs = sum(1 for c in ctxs if getattr(c, 'smt_pair', None))
            logger.info(f"Health: tier0 {self.last_tier0_sec:.2f}s, scan {self.last_scan_sec:.2f}s "
                        f"(heavy {self.last_heavy_sec:.2f}s), books {len(self._hot)}{process}, "
                        f"smt pairs {pairs}/{len(ctxs)}, streams " + ", ".join(rates))

    def _save_state(self):
        path = CONFIG.journal.state_path
        try:
            import pickle
            ml_state = {'anomaly': self.anomaly_model.state() if self.anomaly_model else None,
                        'regime': self.regime_model.state() if self.regime_model else None}
            atomic_write(ML_STATE_PATH, pickle.dumps(ml_state))
        except Exception as e:
            logger.warning(f"ML state save failed: {e}")
        try:
            state = {'saved_at': time.time(), 'book': self.book.state(), 'whales': self.fetcher.whales.state(),
                     'fired_events': self.detector.state()}
            atomic_write(path, json.dumps(state).encode('utf-8'))
        except Exception as e:
            logger.warning(f"State save failed: {e}")

    def _load_ml_state(self):
        """Blocking (unpickling the models imports scikit-learn, ~1s): run it in a worker thread."""
        if os.path.exists(ML_STATE_PATH):
            try:
                import pickle
                with open(ML_STATE_PATH, 'rb') as f:
                    ml_state = pickle.load(f)   # our own file, written by _save_state
                if self.anomaly_model:
                    self.anomaly_model.load_state(ml_state.get('anomaly'))
                if self.regime_model:
                    self.regime_model.load_state(ml_state.get('regime'))
                logger.info(f"ML state restored: anomaly model {'ready' if self.anomaly_model and self.anomaly_model.ready else 'not fitted'}, "
                            f"{len(self.regime_model.history) if self.regime_model else 0} regime candles")
            except Exception as e:
                logger.warning(f"ML state restore failed ({e}); models start fresh")
        # The market regimes of the pretrained months (pretrain.py) under the live candles: the mixture is fitted on
        # both from the first heavy pass, instead of on the few days since the first start
        from journal import load_pretrained
        pretrained = load_pretrained()
        if pretrained:
            self._pretrained_meta = {k: pretrained.get(k) for k in ('created', 'start', 'end', 'coins', 'rows')}
        if self.regime_model is not None and pretrained and pretrained.get('regime_history'):
            before = len(self.regime_model.history)
            for ts, values in pretrained['regime_history'].items():
                if len(values) == len(self.regime_model.FEATURES):
                    self.regime_model.history.setdefault(int(ts), list(values))
            logger.info(f"Regimes: {len(self.regime_model.history) - before} pretrained market candles "
                        f"({pretrained['start']} .. {pretrained['end']}) under {before} live ones")

    def _load_state(self):
        path = CONFIG.journal.state_path
        if not os.path.exists(path):
            return
        try:
            with open(path, encoding='utf-8') as f:
                state = json.load(f)
            self.book.load_state(state.get('book'), time.time())
            self.fetcher.whales.load_state(state.get('whales'))
            self.detector.load_state(state.get('fired_events'), int(time.time() * 1000))
            open_cards = sum(1 for s in self.book.signals.values() if not s.finished)
            logger.info(f"State restored: {open_cards} open cards, {len(state.get('whales') or {})} whale histograms")
        except Exception as e:
            logger.warning(f"State restore failed ({e}); starting fresh")

    # ------------------------------------------------------------------ output

    def _market_context(self) -> Dict[str, Dict]:
        """BTC / ETH price, 5m move and funding for the header."""
        context = {}
        for symbol in ('BTC/USDT:USDT', 'ETH/USDT:USDT'):
            md = self.market_data.get(symbol)
            price = self._price_of(symbol)
            if md is not None and price:
                context[symbol.split('/')[0]] = {
                    'price': price,
                    'change_5m': md.tier0.get('price_change_5m', 0.0),
                    'funding': md.funding_rate,
                }
        return context

    def _warmup_status(self) -> str:
        parts = []
        loaded = self.fetcher.baselines_loaded()
        if loaded < len(self.market_data):
            parts.append(f"history {loaded}/{len(self.market_data)}")
        warmup_left = CONFIG.tier0.warmup_sec - (time.time() - self._started_at)
        if warmup_left > 0:
            parts.append(f"warm-up {int(warmup_left // 60)}:{int(warmup_left % 60):02d} (no signals yet)")
        return " | ".join(parts)

    # ------------------------------------------------------------------ pretraining (pretrain.py)

    def _pretrain_running(self) -> bool:
        """A pretrain.py process holds the lock (started by this loop or by hand)."""
        if self._pretrain_proc is not None and self._pretrain_proc.poll() is None:
            return True
        try:
            pid = int(open(CONFIG.pretrain.lock_path).read().strip() or 0)
            import psutil
            return bool(pid) and psutil.pid_exists(pid)
        except (OSError, ValueError, ImportError):
            return False

    def _pretrain_due(self) -> bool:
        """pretrained.pkl missing, older than auto_refresh_days, or built by an older logic_version."""
        path = CONFIG.pretrain.path
        if not os.path.exists(path) or time.time() - os.path.getmtime(path) > CONFIG.pretrain.auto_refresh_days * 86400:
            return True
        mtime = os.path.getmtime(path)
        if self._pretrain_checked[0] != mtime:
            from journal import load_pretrained, pretrained_current
            self._pretrain_checked = (mtime, pretrained_current(load_pretrained()))
        return not self._pretrain_checked[1]

    async def pretrain_loop(self):
        """
        Keeps the pretrained models fresh without the user: runs pretrain.py in a background process (below-normal
        priority, one worker, capped download) when pretrained.pkl is missing or older than auto_refresh_days, then
        loads the result into the running models (P(edge) restarts from it and replays the live journal on top,
        the regime history gets the new months). The process survives a bot restart (its lock prevents a second one).
        """
        import subprocess
        import sys
        cfg = CONFIG.pretrain
        loaded_mtime = os.path.getmtime(cfg.path) if os.path.exists(cfg.path) else 0.0
        await asyncio.sleep(600)            # after the start-up burst
        while self._running:
            try:
                if cfg.auto and not self._pretrain_running() and self._pretrain_due() and time.time() >= self._pretrain_retry_at:
                    flags = 0
                    if sys.platform == 'win32':
                        flags = subprocess.BELOW_NORMAL_PRIORITY_CLASS | subprocess.CREATE_NO_WINDOW
                    log = open(cfg.log_path, 'a', encoding='utf-8')
                    self._pretrain_proc = subprocess.Popen(
                        [sys.executable, 'pretrain.py', '--workers', str(cfg.auto_workers), '--rate', str(cfg.auto_bytes_per_sec)],
                        stdout=log, stderr=subprocess.STDOUT, creationflags=flags, cwd=os.path.dirname(os.path.abspath(__file__)))
                    logger.info(f"Pretraining started in the background (pid {self._pretrain_proc.pid}, log {cfg.log_path})")
                if self._pretrain_proc is not None and self._pretrain_proc.poll() is not None:
                    code, self._pretrain_proc = self._pretrain_proc.returncode, None
                    if code:
                        self._pretrain_retry_at = time.time() + 6 * 3600
                        logger.warning(f"Pretraining failed (exit code {code}, see {cfg.log_path}); retried in 6h")
                mtime = os.path.getmtime(cfg.path) if os.path.exists(cfg.path) else 0.0
                if mtime > loaded_mtime and not self._pretrain_running():
                    loaded_mtime = mtime
                    await self._reload_pretrained()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"Pretraining loop: {type(e).__name__} {e}")
            await asyncio.sleep(300)

    async def _reload_pretrained(self):
        from journal import load_pretrained
        state = await asyncio.to_thread(load_pretrained)
        if not state:
            return
        self._pretrained_meta = {k: state.get(k) for k in ('created', 'start', 'end', 'coins', 'rows')}
        success = self.journal.success if self.journal else None
        from journal import pretrained_current
        if success is not None and state.get('success') and pretrained_current(state):
            success.load_pretrained(state['success'])
            await asyncio.to_thread(self.journal.warm_start)
        if self.regime_model is not None and state.get('regime_history'):
            for ts, values in state['regime_history'].items():
                if len(values) == len(self.regime_model.FEATURES):
                    self.regime_model.history.setdefault(int(ts), list(values))
            self.regime_model.fitted_at = 0.0         # refit on the new months at the next heavy pass
        logger.info(f"Pretrained models reloaded: {state.get('rows')} rows of {state.get('coins')} coins "
                    f"({state.get('start')} .. {state.get('end')})")

    def _ml_status(self) -> Dict:
        model = self.anomaly_model
        success = self.journal.success if self.journal else None
        meta = self._pretrained_meta or {}
        return {
            'pretrained_rows': meta.get('rows'), 'pretrained_coins': meta.get('coins'),
            'pretrained_span': f"{meta['start']} .. {meta['end']}" if meta.get('start') else None,
            'pretrained_age_d': (time.time() - meta['created']) / 86400 if meta.get('created') else None,
            'pretrain_running': self._pretrain_running(),
            'regime_candles': len(self.regime_model.history) if self.regime_model else 0,
            'regime_age_h': (time.time() - self.regime_model.fitted_at) / 3600
            if self.regime_model and self.regime_model.fitted_at else None,
            'regime': self.regime,
            'anomaly_ready': bool(model and model.ready),
            'anomaly_age_min': (time.time() - model.fitted_at) / 60 if model and model.ready else None,
            'anomaly_samples': len(model.samples) if model else 0,
            'p_n': success.n if success else 0,
            'p_mature': bool(success and success.mature),
            'p_accuracy': success.accuracy if success else None,
            'p_drifts': success.drifts if success else 0,
        }

    def _notify(self):
        for s, event in self.book.events:
            arrow = '▲ LONG' if s.direction > 0 else '▼ SHORT'
            name = s.symbol.replace(':USDT', '').replace('/USDT', '')
            if event == 'ENTRY' and s.levels:
                lv = s.levels
                text = (f"entry {lv['entry']:.6g} | SL {lv['sl']:.6g} | TP {lv['tp1']:.6g} / {lv['tp2']:.6g} / "
                        f"{lv['tp3']:.6g} | R:R {_rr_text(lv)}{' (LOW RR)' if lv.get('low_rr') else ''}")
                confirms = [f"{'+' if confirm.positive(v) else '-'}{k}" for k, v in (s.confirms or {}).items()
                            if v is not None and v != confirm.NA]
                if confirms:
                    text += f" | confirms {' '.join(confirms)}"
            elif event == 'ZONE' and s.plan:
                text = f"in zone {s.plan['zone_lo']:.6g}–{s.plan['zone_hi']:.6g}, waiting for the {s.plan['trigger_minutes']}m trigger"
            else:
                text = f"{event} at {s.last_price:.6g}" + (f" ({s.r_now:+.1f}R)" if s.r_now is not None else '')
            self.notifier.send(event, f"{arrow} {name} {s.group_key}: {event}", text + " · rules, not advice")

    async def _output(self, created: List[TrackedSignal], entries: List[TrackedSignal]):
        # Sound on entries (the actionable moment), not on every new setup
        for tracked in entries:
            play_alert_sound("high" if tracked.direction < 0 else "normal")
        self._notify()

        if self.web is not None:
            self.web.publish()
        for t in created:
            logger.info(f"SETUP {t.symbol} {t.group_key} {'long' if t.direction > 0 else 'short'} @ {t.price_at_signal:.6g}")
        for t in entries:
            lv = t.levels
            logger.info(f"ENTRY {t.symbol} {t.group_key} entry {lv['entry']:.6g} SL {lv['sl']:.6g} ({lv.get('sl_src')}) "
                        f"TP1 {lv['tp1']:.6g} ({lv.get('tp1_src')}) TP2 {lv['tp2']:.6g} TP3 {lv['tp3']:.6g} "
                        f"R:R {_rr_text(lv)} | confirms {t.confirms}")
