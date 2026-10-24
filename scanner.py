import asyncio
import html
import json
import logging
import errors
import os
import platform
import statistics
import time
import zlib
from collections import deque
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import polars as pl

from config import CONFIG
from ml import AnomalyModel, RegimeModel
from levels import RESAMPLE_QUALITY, atr_of, resample
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
from extdata import us_session
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
        errors.report('scanner.play_alert_sound', e, "Could not play sound")


def _orb_shadow_row(found: Dict):
    """eng-150: what journal.record_entry reads of a card, for the 13:30 UTC ORB variant (vetoed 'variant_orb_open',
    the stop the opposite Stretch level, no targets: the replay's hold8_r measures it)."""
    from types import SimpleNamespace
    sig = dict(found)
    return SimpleNamespace(symbol=found['symbol'], direction=found['direction'], group_key=found['setup'], mode='orb',
                           sig=sig, levels={'entry': found['anchor_level'], 'sl': found['anchor_extreme'],
                                            'tp1': None, 'tp2': None, 'tp3': None},
                           plan={'no_tp': True, 'tf': '15m'}, entered_at=found['event_ts'] / 1000,
                           created=found['anchor_ts'] / 1000, vetoed='variant_orb_open', confirms={},
                           of_confirm=None, limit_variant=False)


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


def _row8(c) -> List[float]:
    """A candle as exactly 8 floats [t, o, h, l, c, quote, taker buy quote, base], None / missing fields NaN."""
    row = [float('nan') if v is None else float(v) for v in list(c)[:8]]
    return row + [float('nan')] * (8 - len(row))


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
        self.health: Dict = {}                   # the last Health reading (/api/health)
        self.scorer = PhaseScorer()
        self.web = None   # webui.WebUI, attached by main.py
        self.journal = journal
        self.notifier = Notifier()
        self.notifier.check = self._entry_still_actionable
        from executor import DemoExecutor
        self.demo = DemoExecutor()
        self.demo.alert = lambda text: self.notifier.post(html.escape(text), topic='demo')
        self.demo.card_is_open = lambda card_id: not getattr(self, '_state_loaded', False) or any(
            card_id in (f"{s.symbol}|{s.group_key}|{int(s.entered_at or 0)}", f"{s.symbol}|{s.group_key}|c{int(s.created)}")
            and not s.finished for s in self.book.signals.values())
        self._limits_synced = 0.0
        from extdata import ExternalData
        self.ext = ExternalData(self.fetcher)
        self.book = SignalBook()
        from smallcap import SmallCapWatch
        self.smallcap = SmallCapWatch(self.fetcher) if CONFIG.strategies.smallcap_watch else None
        self.market_data: Dict[str, MarketData] = {}
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._baseline_task: Optional[asyncio.Task] = None
        self._started_at = time.time()
        self._previous_keys: Set[Tuple[str, str]] = set()
        # Heavy-pass cache: closed-candle rows per symbol, the closed futures indicator frame, its signature
        self._rows: Dict[str, Dict] = {}
        self._recent_setup: Dict[str, int] = {}     # symbol -> ms of its last detected setup (hot-set filler)
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
        # wide watch (eng-57): 1h candles of every Binance perpetual OUTSIDE the universe -> pump / dump monitor + journal
        self.wide_h1: Dict[str, list] = {}
        self._wide_fired: set = set()
        self.pools = Pools()      # pumps.monitor: symbol -> (last 1h candle ts, scan result)
        self.pools.small_of = lambda: self.fetcher.small_caps    # eng-99: the small-cap tier trades its own strategies
        self._level_raw: Dict[str, List[RawLevel]] = {}
        self._level_sig: Dict[str, tuple] = {}
        self.book.levels_of = self._levels_of
        # 1h candles of the coin: the 8 days every coin has (hourly), else a card coin's level-map history
        self.book.daily_of = lambda symbol: (lambda md: md.d1 if md else None)(self.market_data.get(symbol))
        self.book.tf_atr_of = self._tf_atrs
        self.book.h4_of = lambda symbol: (lambda md: md.h4 if md else None)(self.market_data.get(symbol))
        self.book.htf_of = lambda symbol: (lambda md: (md.h1 or md.htf_klines) if md else None)(self.market_data.get(symbol))
        self.book.context_of = lambda symbol: self.detector.context.get(symbol)
        self.book.band_of = self._opposite_band
        # eng-137 (audit A02): the entry minute judged on the trades after the entry
        self.book.track_from = self.fetcher.track_from
        self.book.tracked_of = self.fetcher.tracked_of
        self.book.untrack = self.fetcher.untrack
        self.book.plan_key_of = self._plan_key
        self.book.map_ready_of = lambda symbol: symbol in self._level_raw
        self.book.btc_bias_of = self._btc_bias
        self.book.market_state_of = lambda: self.market_state
        self._micro: Dict[str, tuple] = {}
        self.fetcher.log_liquidations = self.journal is not None
        # Setup detectors (sweeps, liquidation exhaustion, absorption, whale accumulation) and the quick level map of
        # every coin they use (rebuilt from the closed 15m candles after each close; card coins get the full map)
        self.detector = LiveDetector()
        # Market state for every setup's context: universe median and BTC moves (see _update_market_state)
        self.market_state: Dict[str, float] = {}
        self._quick_raw: Dict[str, List[RawLevel]] = {}
        self._context_poll = 0.0
        self._context_sig: Dict[str, tuple] = {}
        # crypto_maniac's OI robot: the last final minute checked and the last signal per coin (his 3h cooldown)
        self._oi_checked: Dict[str, int] = {}
        self._oi_fired: Dict[str, int] = {}
        self._context_task: Optional[asyncio.Task] = None
        self._maps_pool = None          # ProcessPoolExecutor (one worker) for level maps: see _maps_executor
        self._blind_at: Dict[Tuple[str, str], float] = {}   # (symbol, strategy) -> when a history gate last stopped it
        from strategies.loopside import LoopDetectors
        # eng-59: the loop-side detectors live in strategies/loopside.py (the archive replay runs the same code)
        self.loopside = LoopDetectors(self._minute_candles,
                                      lambda symbol: part_candles(self._frame_parts.get(symbol))[0])
        self.loopside.volume_rank = self._volume_rank
        self._rank_cache: tuple = (0.0, {})

    def _volume_rank(self, symbol: str) -> Optional[int]:
        """The coin's rank by 24h quote volume among the scanned markets (1 = largest), refreshed once a minute."""
        at, ranks = self._rank_cache
        if time.time() - at > 60:
            ordered = sorted(self.market_data.items(), key=lambda kv: -(kv[1].quote_volume_24h or 0.0))
            ranks = {s: i + 1 for i, (s, _) in enumerate(ordered)}
            self._rank_cache = (time.time(), ranks)
        return ranks.get(symbol)

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
                 self.levels_loop(), self.pretrain_loop(), self.macro_loop(), self.pools_loop(), self.event_risk_loop(),
                 self.wide_watch_loop()]
        if CONFIG.briefing.enabled:
            from briefing import Briefing
            self.briefing = Briefing(self)
            loops.append(self.briefing.loop())
        loops.append(self._panel_prewarm_loop())
        if self.demo.enabled:
            loops.append(self.demo.reconcile_loop(lambda: self._running))
            loops.append(self._demo_report_loop())
        running = lambda: self._running
        loops += [self.ext.deribit_loop(running), self.ext.funding_loop(running), self.ext.books_loop(running),
                  self.ext.macro_loop(running), self.ext.upbit_loop(running),
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
        if self.smallcap is not None:
            # eng-161: the small caps on their 1m stream from the start (the wide watch refreshes the list hourly)
            self._tasks.append(asyncio.create_task(self.smallcap.restore(set(self.market_data))))
        self.notifier.resume()                  # audit B05: trading messages a previous run left undelivered

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

    async def _panel_prewarm_loop(self):
        """audit-80: the classic indicator panel of every coin with a live card, both directions, computed in a thread
        right after the 15m / 1h closes, so the confirmation asked on the loop finds it cached (strategies/ind_panel:
        rolling windows over 500 candles stalled the loop 1-2s at the closes)."""
        while self._running:
            await asyncio.sleep(20)
            try:
                syms = {s.symbol for s in self.book.signals.values() if not s.finished}
                now_ms = time.time() * 1000
                mds = [self.market_data[x] for x in syms if x in self.market_data]
                if mds:
                    await asyncio.to_thread(lambda: [self.fetcher.indicator_panel(md, d, now_ms) for md in mds for d in (1, -1)])
            except Exception as e:
                errors.report('scanner.panel_prewarm', e)

    async def _demo_report_loop(self):
        """audit-80: yesterday's demo trades per strategy to the demo topic at 00:05 UTC, and an alert (never a block)
        once today's closed trades lost CONFIG.executor.day_alert_r R."""
        cfg = CONFIG.executor
        sent_day, alerted_day = int(time.time() // 86400), None
        while self._running:
            await asyncio.sleep(300)
            try:
                day = int(time.time() // 86400)
                if cfg.daily_summary and day != sent_day and time.time() % 86400 >= 300:
                    sent_day = day
                    rows = await asyncio.to_thread(self.demo.day_summary, (day - 1) * 86_400_000)
                    if rows:
                        total = sum(r[3] or 0 for r in rows)
                        lines = [f"{k}: {n} сд., {w or 0} в плюс, {r or 0:+.2f}R"
                                 + (f", проскальз. {sl:+.1f} бп" if sl is not None else '') for k, n, w, r, sl in rows]
                        n_usd, usd = await asyncio.to_thread(self.demo.usd_without_r, (day - 1) * 86_400_000)
                        if n_usd:
                            lines.append(f"без R (UNTRACKED и т.п.): {n_usd} сд., {usd:+.2f} $")
                        self.notifier.post(f"📊 Демо за вчера ({CONFIG.journal.logic_version}): <b>{total:+.2f}R</b>\n"
                                           + "\n".join(lines), topic='demo')
                if cfg.day_alert_r > 0 and alerted_day != day:
                    today = await asyncio.to_thread(self.demo.day_summary, day * 86_400_000)
                    total = sum(r[3] or 0 for r in today)
                    if total <= -cfg.day_alert_r:
                        alerted_day = day
                        self.notifier.post(f"⚠️ Демо: за сегодня {total:+.2f}R (порог −{cfg.day_alert_r:g}R)", topic='demo')
            except Exception as e:
                errors.report('scanner.demo_report', e)

    async def stop(self):
        self._running = False
        self.watchdog.stop()
        if self.anomaly_model is not None:
            self.anomaly_model.close()
        if self._maps_pool is not None:
            self._maps_pool.shutdown(wait=False, cancel_futures=True)
        tasks = [t for t in (*self._tasks, self._baseline_task, getattr(self, '_heartbeat_task', None),
                             *getattr(self, '_positioning_tasks', []), self._context_task, *self._background) if t]
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
            # eng-88: OI over 15 / 60 minutes beside the 5m one (an OI build is a fast 5m step or a running hour)
            from strategies.oi_build import _oi_change
            samples = list(md.oi_samples)
            for label, minutes in (('oi_chg_15m', 15), ('oi_chg_60m', 60)):
                v = _oi_change(samples, now_ms, minutes)
                m[label] = float('nan') if v is None else float(v)
            # eng-89: rush orders of the last 10 / 30 s; the 5m futures flow against the visible book within 1% on its
            # side (Cont-Kukanov-Stoikov: short-horizon impact scales with the order-flow imbalance over the depth)
            m.update(self.fetcher.rush.stats(symbol, now_ms))
            from journal import present
            cvd = present(m.get('agg_cvd_5m'), m.get('futures_cvd_5m')) or 0.0      # audit N12: a measured 0 stays 0
            ratio = self.fetcher.depth.sweep_vs_depth(symbol, abs(cvd), 1 if cvd > 0 else -1, band=0.01) if cvd else None
            m['flow_depth_5m'] = float('nan') if ratio is None else float(ratio) * (1 if cvd > 0 else -1)
            m['top_venue'] = flow.get('top_venue', '')
            out[symbol] = m
            self._journal_rush(symbol, md, m, now_ms)
        return out

    def _journal_rush(self, symbol: str, md, m: Dict, now_ms: float) -> None:
        """eng-89: a burst of rush orders (30 s count >= rush_min_n and z >= rush_z against the coin's last hour) is
        journaled as a RUSH BUY / RUSH SELL row (kind 'rush': data only, never a card or an alert) - the journal's ret_*
        then show what followed the first seconds of an event."""
        cfg = CONFIG.tier0
        if not self.journal or m.get('rush_n_30s', 0) < cfg.rush_min_n or m.get('rush_z_30s', 0) < cfg.rush_z:
            return
        net = m.get('rush_net_30s', 0.0)
        if not net:
            return
        d = 1 if net > 0 else -1
        last = getattr(self, '_rush_logged', None)
        if last is None:
            last = self._rush_logged = {}
        if now_ms - last.get((symbol, d), 0) < cfg.rush_cooldown_sec * 1000:
            return
        price = md.last_price
        if not price:
            return
        last[(symbol, d)] = now_ms
        # audit (2nd part): in a thread like every other journal write - the journal's lock held by the evaluation
        # thread blocked the Tier-0 loop here
        def write(row=dict(m, volume_24h=md.quote_volume_24h or None)):
            try:
                self.journal.record_rush(symbol, d, price, row)
            except Exception as e:
                logger.debug(f"Rush journal {symbol}: {e!r}")
        self._background_thread(write)

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
        # free slots: coins with a setup in the last 3 hours (most recent first), then the pinned coins - the systems
        # entering at their signal's close (ORB, VA80, Bollinger, pump) never had a waiting card, so their coin had no
        # synced book at the entry (2026-10-05: 13 of 25 slots used, `_book` missing on nearly every entry)
        now_ms = int(now * 1000)
        fillers = [s for s, t in sorted(self._recent_setup.items(), key=lambda kv: -kv[1])
                   if now_ms - t <= 3 * 3_600_000 and s in self.market_data]
        pinned = set(CONFIG.exchange.pinned_bases)
        fillers += [s for s in self.market_data if s.split('/')[0] in pinned]
        for s in fillers:
            if len(wanted) >= slots:
                break
            wanted.setdefault(s, 6)
        ranked = sorted(wanted.items(), key=lambda kv: (kv[1], kv[0]))
        new = list(keep)
        for symbol, priority in ranked:
            if symbol in new:
                continue
            if len(new) >= slots:
                # Evict the idle kept symbol with the lowest priority for a higher-priority newcomer
                idle = [s for s in new if s not in wanted and now - self.market_data[s].tier2_since >= cfg.tier2_min_age_sec]
                if idle and priority <= 3:
                    victim = min(idle, key=lambda s: self.market_data[s].tier2_wanted_at)
                else:
                    # eng-139 (audit C18): slots full of wanted coins - a lower-priority one yields to a higher one
                    # (a card in a trade, priority 0, does not wait for the victim's min age)
                    lower = [s for s in new if wanted.get(s, 99) > priority and (
                        priority == 0 or now - self.market_data[s].tier2_since >= cfg.tier2_min_age_sec)]
                    if not lower:
                        continue
                    victim = max(lower, key=lambda s: (wanted.get(s, 99), -self.market_data[s].tier2_wanted_at))
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
        elif self._frame_parts and time.time() - self._context_poll > 60 and (
                self._context_task is None or self._context_task.done()):
            # between candle closes: rebuild the quick maps whose higher-timeframe histories arrived (the signature
            # carries their sizes; unchanged coins are skipped)
            self._context_poll = time.time()
            self._context_task = asyncio.create_task(self._refresh_contexts())

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
            if self.smallcap is not None:
                for symbol, sig in self.smallcap.drain():
                    if symbol in self.market_data:
                        continue                 # joined the universe meanwhile: its own detector decides
                    logger.info(f"Setup detected: {symbol} {sig['setup']} - {sig['setup_note']} (small cap, live 1m)")
                    signals.append((symbol, sig))
            for symbol, sig in signals:
                if sig.get('setup') in ('PUMP START', 'DUMP START'):
                    await self._pd_enrich(symbol, sig)
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
                # eng-150: the shadow ORB from a fixed 13:30 UTC open - a journal row only, never a card
                shadow, self.loopside.orb_shadow = self.loopside.orb_shadow, []
                for found in shadow:
                    await self.journal.arecord_entry(_orb_shadow_row(found))
            for tracked in self.book.finished_now:
                logger.info(f"Card {tracked.symbol} {tracked.group_key}: {tracked.status} - {tracked.finish_reason}")
                await self.journal.arecord_card(tracked)
            # the market baseline: every USDT perpetual (REST mark prices), not only the streamed universe
            # only fresh marks: during the 2026-10-06 outage the last REST marks were written every 5 min for 13h
            # (BTC 85770 flat), a flat market baseline for every signal in that window
            fresh = time.time() - self.fetcher.market_marks_at < 120
            await self.journal.asnapshot_universe((self.fetcher.market_marks if fresh else None) or
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
                elif event == 'RESTOP':
                    self._background_task(self.demo.on_restop(tracked))
                elif event == 'PARTIAL':
                    self._background_task(self.demo.on_partial(tracked))
            for tracked in self.book.finished_now:
                self._background_task(self.demo.on_finish(tracked))

    def _drain_history_skips(self) -> None:
        """eng-132: the strategies a history gate stopped (loop side and the maps worker's contexts) to the journal."""
        rows = self.detector.skip_log + self.loopside.skip_log
        if not rows:
            return
        self.detector.skip_log, self.loopside.skip_log = [], []
        self.loopside._skip_seen.clear()
        now = time.time()
        for symbol, strategy, *_ in rows:
            self._blind_at[(symbol, strategy)] = now
        if self.journal:
            self._background_thread(self.journal.record_history_skips, rows)   # the journal's lock: off the loop

    def blind_text(self, window_sec: float = 900.0, min_coins: int = 20) -> str:
        """'pump 284 coins, ...': the strategies a history gate stopped on at least `min_coins` coins within the window
        (after a restart the 1h / 1d histories load for about an hour: those strategies see nothing until then)."""
        cutoff = time.time() - window_sec
        for key in [k for k, t in self._blind_at.items() if t < cutoff]:
            del self._blind_at[key]
        per: Dict[str, int] = {}
        for _, strategy in self._blind_at:
            per[strategy] = per.get(strategy, 0) + 1
        return ', '.join(f"{s} {n} coins" for s, n in sorted(per.items(), key=lambda x: -x[1]) if n >= min_coins)

    def _detect_setups(self) -> List[Tuple[str, Dict]]:
        """Detected setups of this scan as signals (the coin's live Tier-0 metrics + the setup's leg / note)."""
        out: List[Tuple[str, Dict]] = []
        now_ms = int(time.time() * 1000)
        for symbol, md in self.market_data.items():
            if not self.detector.wants(symbol, md.minute_closed_until, md.tier0):
                continue
            bands = self.fetcher.depth.liquidity_bands(symbol)
            setups = self.detector.scan(symbol, self._minute_candles(symbol), md.tier0, now_ms, bands)
            setups.extend(self.loopside.scan(symbol, md, now_ms))
            if setups:
                self._recent_setup[symbol] = now_ms
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
                for key in ('spot_delta_1h', 'perp_delta_1h', 'adx', 'adx_prev'):
                    if row.get(key) is not None:
                        sig[key] = row[key]
                if setup['setup'].startswith('SWEEP'):
                    self._sweep_wick(symbol, md, setup, sig)
                self._enrich(symbol, md, sig)
                logger.info(f"Setup detected: {symbol} {setup['setup']} - {setup['setup_note']}")
                out.append((symbol, sig))
        self._drain_history_skips()                  # once a scan (was once per coin)
        return out

    def _opposite_band(self, symbol: str, direction: int, asof_ms: Optional[int] = None) -> Optional[float]:
        """BB(20, 2) of the closed 4h candles (eng-84: the W / M is read on 4h; was 15m): the upper band for a long,
        the lower for a short (Bollinger exit). The 4h candles are built from the coin's closed 1h candles; asof_ms:
        only the 4h candles closed by then (the 1m exit loop judges each minute on the band it could see)."""
        from strategies.structure import bars_4h
        md = self.market_data.get(symbol)
        h1 = list(getattr(md, 'h1', None) or [])
        cut = int(asof_ms) if asof_ms is not None else (int(h1[-1][0]) + 3_600_000 if h1 else 0)
        closes = [c[4] for c in bars_4h(h1, cut)[-20:]] if h1 else []
        if len(closes) < 20:
            return None
        mean = sum(closes) / 20
        sd = (sum((x - mean) ** 2 for x in closes) / 20) ** 0.5       # population sigma (Bollinger)
        return mean + direction * 2 * sd

    async def wide_watch_loop(self):
        """
        eng-57: the universe holds 70 coins with complete data (a spot pair, >= 2 other venues, >= $10M): the biggest
        small-cap pumps / dumps (no spot pair, a fresh listing) were never seen. Once an hour (a few minutes after the
        close) the 1h candles of every other USDT perpetual >= wide_min_volume run the pump / dump monitor (dashboard)
        and the dump-bounce rule; its events are JOURNALED (vetoed 'outside_universe': no streams there, so no card /
        demo trade) - the forward test of the research rule on the whole market it was measured on.
        """
        from strategies.pump import MAJORS, dump_bounce
        cfg = CONFIG.strategies
        await asyncio.sleep(600)
        while self._running:
            started = time.time()
            try:
                rows = await self.fetcher._rest_call(self.fetcher.futures_exchange, 'fapiPublicGetTicker24hr',
                                                     priority=2, weight=40)
                by_id = getattr(self.fetcher.futures_exchange, 'markets_by_id', {}) or {}
                wanted = []
                qv: Dict[str, float] = {}
                for t in rows or []:
                    m = by_id.get(t.get('symbol'))
                    m = m[0] if isinstance(m, list) else m
                    if not m or not m.get('swap') or m.get('quote') != 'USDT' or m['symbol'] in self.market_data:
                        continue
                    if (m.get('info', {}).get('underlyingType') in CONFIG.exchange.excluded_underlying_types or
                            m.get('base') in CONFIG.exchange.excluded_bases or m.get('base') in MAJORS):
                        continue
                    if float(t.get('quoteVolume') or 0) >= cfg.wide_min_volume:
                        wanted.append((m['symbol'], t['symbol'], float(t.get('lastPrice') or 0)))
                        qv[m['symbol']] = float(t.get('quoteVolume') or 0)
                sem = asyncio.Semaphore(4)

                async def one(sym, bid, last):
                    async with sem:
                        try:
                            k = await self.fetcher._rest_call(self.fetcher.futures_exchange, 'fapiPublicGetKlines',
                                                              {'symbol': bid, 'interval': '1h', 'limit': 200},
                                                              priority=2, weight=2)
                        except Exception as e:
                            logger.debug(f"wide watch: 1h candles failed for {sym}: {e}")
                            return
                    now_ms = time.time() * 1000
                    h1 = [[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[7]), float(x[10])]
                          for x in k or [] if int(x[6]) < now_ms]
                    self.wide_h1[sym] = h1
                    found = dump_bounce(h1, int(now_ms)) if len(h1) >= 190 else None
                    if found and (sym, found['anchor_ts']) not in self._wide_fired:
                        self._wide_fired.add((sym, found['anchor_ts']))
                        sig = dict(found, is_setup=True, is_structured=False, is_tier_0_anomaly=False,
                                   active_phases=[], long_score=0, short_score=0, alert_type='SHORT',
                                   card_veto='outside_universe')
                        logger.info(f"Wide watch: {sym} {found['setup']} - {found['setup_note']} (journal only)")
                        await self.journal.arecord([(sym, sig)], {sym: last or h1[-1][4]})

                await asyncio.gather(*(one(*w) for w in wanted))
                if self.smallcap is not None:
                    # eng-158: the same coins on the live 1m watch (one dynamic Binance connection)
                    await self.smallcap.set_coins([(s, b, qv.get(s, 0.0)) for s, b, _ in wanted], self.wide_h1)
                for sym in [s for s in self.wide_h1 if s in self.market_data or s not in {w[0] for w in wanted}]:
                    self.wide_h1.pop(sym, None)
                logger.info(f"Wide watch: {len(wanted)} perpetuals outside the universe scanned in "
                            f"{time.time() - started:.0f}s")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"Wide watch failed: {e}")
            now = time.time()
            await asyncio.sleep(max(600.0, 3600 - now % 3600 + 240))

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
                candles_4d, with_context, long_15m, long_1h, list(md.d1), list(md.h4), list(md.w1),
                list(md.day_pocs))

    def _correlates(self) -> Dict[str, np.ndarray]:
        """The SMT correlates' 15m histories (BTC for every coin, ETH for BTC): the long REST history + the frame."""
        out = {}
        for name in ('BTC', 'ETH', 'SOL'):
            symbol = f"{name}/USDT:USDT"
            md = self.market_data.get(symbol)
            if md is None:
                continue
            candles, _ = part_candles(self._frame_parts.get(symbol))
            # 8 fields each (the base volume NaN when absent): the long REST rows and the frame's candles differ in
            # width across versions, and one ragged row failed every quick map ('inhomogeneous shape')
            merged = {int(c[0]): _row8(c) for c in md.m15_long}
            merged.update({int(c[0]): _row8(c) for c in candles})
            if merged:
                out[name] = np.asarray([merged[t] for t in sorted(merged)], dtype=np.float64)
        return out

    async def _build_maps(self, jobs: List[tuple]) -> Dict[str, tuple]:
        if not jobs:
            return {}
        corr = self._correlates() if any(job[8] for job in jobs) else None
        from concurrent.futures.process import BrokenProcessPool
        try:
            out = await asyncio.get_running_loop().run_in_executor(self._maps_executor(), build_maps, jobs, corr)
            for err in out.pop('__errors__', ()):
                errors.report('scanner.maps', RuntimeError(err), f"Level map failed: {err}")
            return out
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
                md = self.market_data[symbol]
                # + the higher-timeframe histories: after a start the first quick map is built before the 1h / 4h /
                # daily / weekly candles load and held no level of theirs until the next 15m close (eng-69)
                # audit D04: the newest bar of each timeframe too - a full buffer replaces a bar without changing its length
                signature = (part['timestamp'][-1], part.height, len(md.h1), len(md.h4), len(md.d1), len(md.w1),
                             len(md.day_pocs), md.h1[-1][0] if md.h1 else 0, md.h4[-1][0] if md.h4 else 0,
                             md.d1[-1][0] if md.d1 else 0, md.w1[-1][0] if md.w1 else 0)
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

    def _tf_atrs(self, symbol: str, md=None) -> Dict[str, float]:
        """Wilder's ATR14 (levels.atr_of, the bot's one ATR) of the coin's closed 1h / 4h / daily candles."""
        md = md if md is not None else self.market_data.get(symbol)
        out: Dict[str, float] = {}
        if md is None:
            return out
        now_ms = time.time() * 1000
        for tf, rows, period in (('1h', md.h1, 3_600_000), ('4h', md.h4, 14_400_000), ('1d', md.d1, 86_400_000)):
            closed = [r for r in list(rows)[-200:] if r[0] + period <= now_ms]
            if len(closed) >= 15:
                out[tf] = atr_of(closed)
        return out

    def _update_market_state(self, futures_all: pl.DataFrame):
        """
        The market every setup trades in (a feature, journaled and learned): the universe's median 15m-close move
        over the last 1h / 4h and BTC's last 1h - one market factor explains about half of all coins' moves.
        """
        if futures_all.is_empty():
            return
        # audit (2nd part): the closes 1h / 4h before the last candle BY TIME - tail(5) / tail(17) took the frame's
        # first row when a coin had fewer candles (a 45-minute move read as 4h); no such candle -> null, left out
        ts_last = pl.col('timestamp').last()
        last = futures_all.group_by('symbol', maintain_order=True).agg(
            (pl.col('close').last() / pl.col('close').filter(pl.col('timestamp') == ts_last - 3_600_000).first() - 1)
            .alias('r1h'),
            (pl.col('close').last() / pl.col('close').filter(pl.col('timestamp') == ts_last - 14_400_000).first() - 1)
            .alias('r4h'),
            (pl.col('close').last() / pl.col('close').filter(pl.col('timestamp') == ts_last - 86_400_000).first() - 1)
            .alias('r1d'))
        r1d = last['r1d'].drop_nulls()
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
            'btc_4h': float(btc['r4h'][0]) if btc.height and btc['r4h'][0] is not None else None,
            # eng-145: the 24h moves for the falling-market long veto (SignalBook._market_down)
            'mkt_1d': float(r1d.median()) if len(r1d) else None,
            'btc_1d': float(btc['r1d'][0]) if btc.height and btc['r1d'][0] is not None else None,
            'breadth_w': sum(t > 0 for t in trends) / len(trends) if len(trends) >= 20 else None,
        }
        self.market_state.update(self._shadow_market())

    def _shadow_market(self) -> Dict:
        """
        eng-149 (plan eng-148, stages 2.4 / 3.8; journal only, no rule reads them):
        - btc_below_ema50_4h: BTC's last closed 4h close under the EMA50 of its 4h closes;
        - liq_cascade_2h: the universe's long liquidations of the last 2h over the 2h average of the 22h before
          (a falling-market cascade at >= 3, the heuristic of the plan's market_down variant);
        - mkt_down_alt: 1 when either holds - the shadow variant of market_down (BTC 4h EMA50 or a cascade);
        - smt_majors: ICT SMT between BTC and ETH on the last 24 closed 1h candles: +1 = one made a new low of the
          window and the other did not (bullish), -1 = the same at the highs, 0 = none.
        """
        out = {'btc_below_ema50_4h': None, 'liq_cascade_2h': None, 'mkt_down_alt': None, 'smt_majors': None}
        now_ms = time.time() * 1000
        btc = self.market_data.get('BTC/USDT:USDT')
        if btc is not None:
            closed = [c[4] for c in btc.h4 if c[0] + 14_400_000 <= now_ms]
            if len(closed) >= 100:
                k, ema = 2 / 51, sum(closed[:50]) / 50
                for x in closed[50:]:
                    ema += k * (x - ema)
                out['btc_below_ema50_4h'] = int(closed[-1] < ema)
        recent = before = 0.0
        # eng-151: from the fetcher's 5m buckets (the per-coin event deques overflow on BTC / ETH within a day)
        for b, usd in list(self.fetcher.liq_long_5m.items()):
            age = now_ms - (b + 300_000)
            if -300_000 < age <= 7_200_000 - 300_000:
                recent += usd
            elif 7_200_000 - 300_000 < age <= 86_400_000 - 300_000:
                before += usd
        # the 22h baseline must be covered (after a restart the buckets refill over a day: None until then)
        first = self.fetcher.liq_live_since      # review eng-151: the OKX backfill's old buckets do not cover the day
        if before > 0 and first is not None and now_ms - first >= 86_400_000:
            out['liq_cascade_2h'] = recent / (before / 11)
        flags = [v for v in (out['btc_below_ema50_4h'],
                             None if out['liq_cascade_2h'] is None else int(out['liq_cascade_2h'] >= 3)) if v is not None]
        out['mkt_down_alt'] = int(any(flags)) if flags else None
        eth = self.market_data.get('ETH/USDT:USDT')
        if btc is not None and eth is not None:
            a = [c for c in btc.h1 if c[0] + 3_600_000 <= now_ms][-25:]
            b = [c for c in eth.h1 if c[0] + 3_600_000 <= now_ms][-25:]
            if len(a) == 25 and len(b) == 25 and a[-1][0] == b[-1][0]:
                lo_a, lo_b = a[-1][3] < min(c[3] for c in a[:-1]), b[-1][3] < min(c[3] for c in b[:-1])
                hi_a, hi_b = a[-1][2] > max(c[2] for c in a[:-1]), b[-1][2] > max(c[2] for c in b[:-1])
                out['smt_majors'] = 1 if lo_a != lo_b else -1 if hi_a != hi_b else 0
        return out

    @staticmethod
    def _shadow_coin(md: MarketData) -> Dict:
        """
        eng-149 (plan eng-148, stages 3.5 / 3.7 / 0.4; journal only): Crabel's narrow-range days on the last closed
        daily candle (nr4 / nr7: its range is the smallest of the last 4 / 7; inside_day: inside the day before), and
        the coin's volatility regime on closed 1h candles - atr_ratio = ATR(14) / the mean ATR(14) of the last 100
        hours, vol_regime = 'climax' (>= 1.8), 'compression' (<= 0.7), 'trend' (efficiency ratio of 14h >= 0.4)
        or 'range' (heuristic cuts, a label to split by, not a rule).
        """
        out = {'nr4': None, 'nr7': None, 'inside_day': None, 'atr_ratio': None, 'vol_regime': None}
        now_ms = time.time() * 1000
        days = [c for c in md.d1 if c[0] + 86_400_000 <= now_ms]
        if len(days) >= 7:
            rng = [c[2] - c[3] for c in days[-7:]]
            out['nr4'] = int(rng[-1] <= min(rng[-4:]))
            out['nr7'] = int(rng[-1] <= min(rng))
            out['inside_day'] = int(days[-1][2] <= days[-2][2] and days[-1][3] >= days[-2][3])
        h1 = [c for c in md.h1 if c[0] + 3_600_000 <= now_ms][-128:]
        if len(h1) >= 128:
            tr = [max(c[2] - c[3], abs(c[2] - p[4]), abs(c[3] - p[4])) for p, c in zip(h1, h1[1:])]
            atr = [sum(tr[i - 14:i]) / 14 for i in range(14, len(tr) + 1)]
            base = sum(atr[-100:]) / 100
            if base > 0:
                ratio = atr[-1] / base
                closes = [c[4] for c in h1[-15:]]
                path = sum(abs(y - x) for x, y in zip(closes, closes[1:]))
                er = abs(closes[-1] - closes[0]) / path if path else 0.0
                out['atr_ratio'] = ratio
                out['vol_regime'] = 'climax' if ratio >= 1.8 else 'compression' if ratio <= 0.7 \
                    else 'trend' if er >= 0.4 else 'range'
        return out

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
        out['funding_interval_h'] = float(hours) if hours else None          # audit C12: the cost model's interval
        state = (self.fetcher.venue_derivs.get(symbol) or {}).get('binance')
        out['oi_vol'] = state.oi_usd / md.quote_volume_24h if state is not None and state.oi_usd and \
            md.quote_volume_24h and time.time() * 1000 - state.oi_ts < 600_000 else None     # audit N18: a fresh OI
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

    def _btc_momentum(self) -> Optional[float]:
        """eng-100: BTC's return over the last regime_days CLOSED daily candles (the market regime), None without them."""
        md = self.market_data.get('BTC/USDT:USDT')
        n = CONFIG.exchange.regime_days
        if md is None or len(md.d1) <= n:
            return None
        now_ms = time.time() * 1000
        closed = [c for c in md.d1 if c[0] + 86_400_000 <= now_ms]
        if len(closed) <= n or not closed[-1 - n][4]:
            return None
        return float(closed[-1][4] / closed[-1 - n][4] - 1)

    def _btc_bias(self) -> Optional[int]:
        """
        eng-59: BTC's ICT bias (weekly, else daily: the close beyond the previous candle's high / low), the direction
        altcoins' ICT models trade with (SignalBook._against_day: 'against_btc').
        """
        md = self.market_data.get('BTC/USDT:USDT')
        if md is None:
            return None
        seen = False
        for bars in (md.w1, md.d1):
            if len(bars) >= 2:
                seen = True
                prev, last = bars[-2], bars[-1]
                bias = 1 if last[4] > prev[2] else -1 if last[4] < prev[3] else 0
                if bias:
                    return bias
        # 0 = known and neutral (inside both previous candles), None = no data (journaled NULL was both)
        return 0 if seen else None

    def _enrich(self, symbol: str, md: MarketData, sig: Dict):
        """Live context that is not part of the scored row."""
        sig['small_cap'] = symbol in self.fetcher.small_caps      # eng-99: the demo risks less on them
        sig['btc_mom_7d'] = self._btc_momentum()                  # eng-100: the market regime (executor risk)
        sig.update(self.market_state)
        sig.update(self._shadow_coin(md))                         # eng-149: NR4 / NR7 / volatility regime (journal)
        sig.update(self.ext.market)
        sig['us_session'] = us_session(time.time())               # eng-133: computed at the card, not cached
        sig.update(self.ext.of(symbol))
        sig['kimchi_prem'] = self.ext.kimchi(symbol, self._price_of(symbol))   # eng-134: shadow only
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
        sig['btc_bias'] = self._btc_bias()
        # eng-59: VPIN / volume entropy / the leading venue of the last hour, once a minute per coin (~6 ms each:
        # every scan for 70 coins would cost the loop ~0.4s)
        minute = int((time.time() - zlib.crc32(symbol.encode()) % 60) // 60)      # coins spread over the minute
        cached = self._micro.get(symbol)
        if cached is None or cached[0] != minute:
            try:
                cached = (minute, self.fetcher.flow.micro_features(symbol, list(md.minute_klines)))
            except Exception as e:                   # context only: never break a scan
                logger.debug(f"micro features {symbol}: {e!r}")
                cached = (minute, {})
            self._micro[symbol] = cached
        sig.update(cached[1])
        sig.update(self._positioning_features(symbol, md))
        # eng-53: Binance's Monitoring Tag / a scheduled delisting (longs vetoed 'event_risk'), the nearness to the
        # 52-week high (Jia et al. 2025: predicts next week's cross-section; ours: rank IC +0.09, t 2.9, quintile
        # spread n.s.), the coin's 24h volume rank (reversal after extremes is an illiquid-coin effect)
        risk = getattr(self, 'event_risk', None)
        sig['event_risk'] = risk.of(symbol) if risk is not None else None
        news = risk.news_of(symbol) if risk is not None else None     # eng-135: shadow (the veto rides event_risk)
        sig['news'], sig['news_age_h'] = (news['kind'], news['age_h']) if news else (None, None)
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
        on_hl = 'hyperliquid' in self.fetcher.symbol_map.by_key.get(symbol, {}) and self.positioning.hl_current()
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

    async def _minute_hole_pass(self) -> None:
        """eng-161: which coins miss closed 1m candles (the source of '1m gaps dropped'), refilled from REST - at most
        15 coins a pass, the worst first; one log line with the worst offenders."""
        try:
            now_ms = int(time.time() * 1000)
            holes = {s: len(self.fetcher.minute_holes(md.minute_klines, md.minute_closed_until))
                     for s, md in list(self.market_data.items())}
            bad = sorted(((n, s) for s, n in holes.items() if n), reverse=True)
            if not bad:
                return
            left, done = 0, 0
            last = self.__dict__.setdefault('_hole_patched', {})
            for n, s in bad:
                if done >= 15:
                    break
                md = self.market_data.get(s)
                if md is None or now_ms - last.get(s, 0) < 600_000:
                    continue                    # one refill per coin per 10 minutes
                last[s] = now_ms
                done += 1
                left += await self.fetcher.patch_minute_holes(s, md, now_ms)
            if not done:
                return
            top = ", ".join(f"{s.split('/')[0]} {n}" for n, s in bad[:8])
            logger.info(f"Minute holes: {len(bad)} coins, {sum(n for n, _ in bad)} minutes missing in the last 4h "
                        f"(worst: {top}); refilled {done} coins, {left} minutes still missing there")
        except Exception as e:
            logger.warning(f"Minute holes pass: {e!r}")

    async def _btc_m5(self) -> List:
        """eng-160b: BTC's last 290 closed 5m candles for the beta residual (pd_vs_btc_resid), cached per 5 minutes."""
        now = time.time() * 1000
        cached = getattr(self, '_btc_m5_cache', None)
        if cached and now - cached[0] < 300_000:
            return cached[1]
        try:
            k = await self.fetcher._rest_call(self.fetcher.futures_exchange, 'fapiPublicGetKlines',
                                              {'symbol': 'BTCUSDT', 'interval': '5m', 'limit': 290}, priority=1, weight=2)
            rows = [[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4])] for x in k or [] if int(x[6]) < now]
            self._btc_m5_cache = (now, rows)
            return rows
        except Exception as e:
            logger.debug(f"BTC 5m for the beta residual: {e!r}")
            return []

    async def _pd_enrich(self, symbol: str, sig: Dict) -> None:
        """eng-159: the detector's features on the source's 24h baselines - the last 289 closed 5m candles (REST, once
        per PUMP / DUMP START) + the 1m ring; the activation lead time found by the detector is kept."""
        try:
            from strategies import pd_features as pdf
            bid = self.fetcher.futures_exchange.market(symbol)['id']
            k = await self.fetcher._rest_call(self.fetcher.futures_exchange, 'fapiPublicGetKlines',
                                              {'symbol': bid, 'interval': '5m', 'limit': 290}, priority=1, weight=2)
            now = time.time() * 1000
            m5 = [[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[7]), float(x[10]), float(x[8])]
                  for x in k or [] if int(x[6]) < now]
            lead = sig.get('pd_activation_lead_s')
            minutes = self._minute_candles(symbol)
            feats = pdf.features(minutes, [], int(sig['direction']), [r[:7] for r in m5])
            btc_m5 = await self._btc_m5()
            feats.update(pdf.extras(m5, minutes, self._minute_candles('BTC/USDT:USDT'), int(sig['direction']), btc_m5))
            if feats:
                sig.update(feats)
                sig['pd_activation_lead_s'] = lead
            logger.info(f"PD features {symbol} {sig['setup']}: phase {sig.get('pd_phase')}, vol x{sig.get('pd_vol_ratio_5m', 0):.1f} "
                        f"(cluster {sig.get('pd_vol_cluster')}), range x{sig.get('pd_range_ratio', 0):.1f} "
                        f"(cluster {sig.get('pd_range_cluster')}), move3 {sig.get('pd_move3', 0):+.1%}, "
                        f"breakout {sig.get('pd_breakout', 0):+.2%}, trades x{sig.get('pd_trades_ratio_5m', 0):.1f}, "
                        f"vs 12h MA {sig.get('pd_price_vs_ma12h', 0):+.1%}, vs BTC {sig.get('pd_vs_btc', 0):+.1%} "
                        f"(resid {sig.get('pd_vs_btc_resid', 0):+.1%}, beta {sig.get('pd_btc_beta', 0):.2f}), "
                        f"rush z {sig.get('rush_z_30s', 0):.1f}, base {sig.get('pd_base_n')} x 5m")
        except Exception as e:
            logger.warning(f"PD features {symbol}: {e!r}")

    def _minute_candles(self, symbol: str):
        """FINAL futures 1m candles only: entry triggers are closes, and a running minute's close is just the live price."""
        md = self.market_data.get(symbol)
        if md is None:
            # eng-158: a small cap's card is fed by the small-cap watch
            return self.smallcap.minutes(symbol) if self.smallcap is not None else []
        return [c for c in list(md.minute_klines) if c[0] <= md.minute_closed_until]

    PRICE_MAX_AGE_SEC = 60

    def _price_of(self, symbol: str) -> Optional[float]:
        """
        Freshest futures price: the latest ticker sample or the 1m kline close, whichever is newer. None when both
        are older than PRICE_MAX_AGE_SEC, so a stalled stream never drives SL/TP decisions with a frozen price.
        """
        md = self.market_data.get(symbol)
        if md is None:
            return self.smallcap.price(symbol) if self.smallcap is not None else None    # eng-158
        now_ms = time.time() * 1000
        candidates = []
        if md.ticker_samples:
            ts, price, _ = md.ticker_samples[-1]
            candidates.append((ts, price))
        if md.minute_klines:
            candle = md.minute_klines[-1]
            # audit C03: the kline's price is dated by its last stream event; without one, a final candle by its close
            # and a forming one by its open (open + 60s made a stale forming candle 'now' and beat a newer trade)
            ev_open, ev_ms = getattr(md, 'kline_event', (0, 0.0))
            if ev_open == candle[0] and ev_ms:
                ts = min(now_ms, ev_ms)
            elif candle[0] <= getattr(md, 'minute_closed_until', 0):
                ts = min(now_ms, candle[0] + 60_000)
            else:
                ts = candle[0]
            candidates.append((ts, candle[4]))
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
        # the map the plans use (worker-built: 1h swings, previous day / week, sessions, 4h / daily / weekly FVG / OB /
        # breakers); the page built its own map from the card-only 1h history - for a coin without a card it held no
        # 1h / 4h / daily / weekly level at all (BTC 2026-10-05: only 15m zones next to the weekly levels of the owner's
        # analyst). The fallback builds the same inputs as Scanner._map_job.
        raw = self._level_raw.get(symbol) or self._quick_raw.get(symbol)
        if raw:
            return list(raw), atr, candles
        h1 = list(md.h1) if len(md.h1) >= len(md.htf_klines) else list(md.htf_klines)
        raw = build_raw(candles, h1, md.htf_oi, list(md.liq_events), atr, time.time() * 1000,
                        candles_4d=list(md.htf_5m) or h1[-96:], candles_1d=list(md.d1), candles_4h=list(md.h4),
                        candles_1w=list(md.w1), day_pocs=md.day_pocs, symbol=symbol)
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
        # eng-105: without order-book WALLS - of ~1000 walls tracked on BTC / ETH / SOL / XRP / BNB in 10 minutes ~800
        # were pulled, ~170 shrank, 2 were traded through and NONE was filled (30-60 s lives): no target / level for a
        # plan (the chart still draws them)
        levels = (self._level_raw.get(symbol) or self._quick_raw.get(symbol, [])) + \
            [l for l in self._live_levels(symbol) if l.kind != 'wall']
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
        minutes = list(md.minute_klines)            # closed minutes + the forming one (updated in place)

        def forming(rows, tf_ms):
            # the in-progress candle of tf_ms built from the minute stream (the page showed 15m / 1h candles only
            # once they closed): replaces / extends the last bar of `rows`
            if not minutes:
                return rows
            start = int(minutes[-1][0]) // tf_ms * tf_ms
            part = [m for m in minutes if m[0] >= start]
            rows = [r for r in rows if r[0] < start]
            # the minute ring holds 10h: a 4h / daily candle that began earlier opens at the previous close (its
            # high / low before the ring are unknown - approximated by the part we hold)
            o = part[0][1] if minutes[0][0] <= start or not rows else rows[-1][4]
            bar = [start, o, max(o, max(m[2] for m in part)), min(o, min(m[3] for m in part)), part[-1][4], 0.0, 0.0]
            return rows + [bar]
        candles = forming(candles, 900_000)
        cards = [s for s in self.book.signals.values() if s.symbol == symbol]
        # the full map (all timeframes) on every chart; the card's own zone / targets / levels are drawn over it (the
        # card plan's zone list held a handful of zones - TAO 4 - and the chart lost its levels)
        zones = merge(raw + self._live_levels(symbol), atr, symbol=symbol) if atr else []
        if not zones:
            for s in cards:
                if s.plan and s.plan.get('zones'):
                    zones = s.plan['zones']
                    break
        price = self._price_of(symbol)
        if price and atr:
            # the 1h chart spans days: the window reaches 3 daily ATRs (25 x the 15m ATR was ~3% - levels vanished)
            span = max(25 * atr, 3 * (self._tf_atrs(symbol).get('1d') or 0.0))
            zones = [z for z in zones if abs(z.price - price) <= span]
        from webui import card_view
        now = time.time()
        # 5m: the 4-day REST history (level-map input) extended by the live 1m stream
        stream_5m = resample(list(md.minute_klines), 5, complete=False)   # display: the forming bar too
        history_5m = [c for c in md.htf_5m if not stream_5m or c[0] < stream_5m[0][0]]
        candles_5m = history_5m + stream_5m
        # 1h: 4 days, so a leg of hours or days is visible whole
        # every coin has 200 closed 1h candles (md.h1); the card-only REST history was empty for the rest (no chart, no
        # events on the 1h); + the forming hour
        base_1h = list(md.h1)[-120:] if len(md.h1) >= len(md.htf_klines) else list(md.htf_klines)
        if len(base_1h) < 24 and candles:
            # the 1h history loads a few minutes after a start (all coins, 2 requests each): until then the 1h chart
            # showed only the forming candle - the closed 15m candles grouped into complete hours stand in for it
            hours = {}
            for c in candles:
                hours.setdefault(int(c[0]) // 3_600_000 * 3_600_000, []).append(c)
            base_1h = [[t, g[0][1], max(x[2] for x in g), min(x[3] for x in g), g[-1][4], sum(x[5] for x in g)]
                       for t, g in sorted(hours.items()) if len(g) == 4]
        candles_1h = forming(base_1h, 3_600_000)
        # the two-sided scenario card (1h ladder; the same level code the probability model was trained with)
        btc = self.market_data.get('BTC/USDT:USDT')
        btc_closes = [c[4] for c in btc.h1] if btc and btc.h1 else None
        try:
            scenario = await asyncio.to_thread(scenarios.build, list(md.h1), price, now * 1000, btc_closes,
                                               (), None, self.macro.features(now * 1000),
                                               list(md.htf_1d) or list(md.d1) or None,
                                               list(md.htf_1h_30d) or list(md.h1) or None,
                                               symbol=symbol, volume_24h=md.quote_volume_24h or None)
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
            # 4h / daily from their own REST histories (200 / 370 closed candles) + the forming one from the minutes
            'candles_4h': forming([list(r) for r in md.h4][-200:], 14_400_000) if len(md.h4) else [],
            'candles_1d': forming([list(r) for r in md.d1][-370:], 86_400_000) if len(md.d1) else [],
            'zones': [z.as_dict() for z in zones],
            'cards': [card_view(s, now, md.d1) for s in cards],
            'liquidations': [list(e) for e in md.liq_events if now * 1000 - e[0] <= 86_400_000][-300:],
            'heatmap': self.fetcher.depth.heatmap(symbol),
            'htf_loaded': md.htf_loaded,
            'flow_15m': self._flow_series(md),
            'funding': md.funding_rate,
        }

    @staticmethod
    def _flow_series(md) -> List:
        """[[open ms, open interest (base), futures taker delta USD, spot taker delta USD]] of the last 500 15m candles
        (the chart's OI / CVD panes; the page accumulates the deltas into CVD over the visible window)."""
        fut = md.futures_df
        if fut is None or fut.is_empty():
            return []
        fut = fut.tail(500).select(['timestamp', 'open_interest', 'taker_delta'])
        spot = {}
        if md.spot_df is not None and not md.spot_df.is_empty():
            spot = dict(md.spot_df.tail(500).select(['timestamp', 'taker_delta']).iter_rows())
        return [[int(t), oi, fd, spot.get(t)] for t, oi, fd in fut.iter_rows()]

    # ------------------------------------------------------------------ background loops

    async def event_risk_loop(self):
        """Binance's Monitoring Tag and scheduled perpetual delistings (event_risk.py), hourly; the Binance / Upbit
        announcements (eng-135) every 2 minutes; all off the loop."""
        from event_risk import EventRisk
        self.event_risk = getattr(self, 'event_risk', None) or EventRisk()
        last_full = 0.0
        while self._running:
            try:
                if time.time() - last_full >= 3600:
                    await asyncio.to_thread(self.event_risk.refresh)
                    last_full = time.time()
                await asyncio.to_thread(self.event_risk.refresh_news)
            except Exception as e:
                logger.warning(f"Event risk refresh failed: {e!r}")
            await asyncio.sleep(120)

    async def pools_loop(self):
        """Per-strategy coin pools (pools.py), rebuilt every CONFIG.pools.refresh_sec off the loop."""
        self.book.pool_of = self.pools.allows
        await asyncio.sleep(120)                     # after the 1h candles and 24h volumes are in
        while self._running:
            try:
                since = int((time.time() - CONFIG.pools.lookback_days * 86400) * 1000)
                sector_map = await asyncio.to_thread(sectors.load)
                results = await asyncio.to_thread(self.journal.coin_results, since) if self.journal else []
                await asyncio.to_thread(self.pools.rebuild, dict(self.market_data), sector_map, results,
                                        list(getattr(self.fetcher, 'market_volumes', None) or []))
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
                errors.report('scanner.positioning_loop', e, "Positioning refresh failed")

    async def state_loop(self):
        """Every minute: persist state and log a health line (loop timings, per-venue message rates)."""
        last_counts: Dict[str, int] = {}
        last_bytes: Dict[str, int] = {}
        last_memory = 0.0
        try:
            import psutil
            proc = psutil.Process()
            proc.cpu_percent(None)   # the first reading only starts the measurement
        except Exception as e:
            errors.report('scanner.psutil', e, 'Health line without cpu / memory')
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
            process, cpu, rss = "", None, None
            if proc is not None:
                # cpu: % of one core over the last minute (read once: a second call measures since the first)
                cpu, rss = proc.cpu_percent(None), proc.memory_info().rss / 2**20
                process = f", cpu {cpu:.0f}%, mem {rss:.0f}MB"
            ctxs = [c for c in self.detector.context.values() if c is not None]
            pairs = sum(1 for c in ctxs if getattr(c, 'smt_pair', None))
            failed = errors.health_text()
            import macro_calendar
            macro_bad = macro_calendar.coverage(time.time() * 1000)
            if macro_bad:
                failed = (failed + '; ' if failed else '') + f"macro veto degraded: {macro_bad}"
            blind = self.blind_text()
            if blind:
                failed = (failed + '; ' if failed else '') + f"history gate stopped: {blind}"
            gc_line = self.watchdog.gc_text()
            # the same reading for /api/health (external monitoring, the dashboard's health tab)
            self.health = {'ts': time.time(), 'tier0_sec': self.last_tier0_sec, 'scan_sec': self.last_scan_sec,
                           'heavy_sec': self.last_heavy_sec, 'books': len(self._hot), 'streams': rates,
                           'down': [r.split()[0] for r in rates if ' DOWN' in r],
                           'cpu_pct': cpu, 'rss_mb': rss,
                           'gc': gc_line, 'errors': failed}
            await self._minute_hole_pass()
            logger.info(f"Health: tier0 {self.last_tier0_sec:.2f}s, scan {self.last_scan_sec:.2f}s "
                        f"(heavy {self.last_heavy_sec:.2f}s), books {len(self._hot)}{process}, "
                        f"smt pairs {pairs}/{len(ctxs)}, 1m gaps patched {RESAMPLE_QUALITY['patched']} / dropped "
                        f"{RESAMPLE_QUALITY['dropped']} (main process), streams " + ", ".join(rates)
                        + (f"; {gc_line}" if gc_line else '') + (f"; {failed}" if failed else '')
                        + (f"; {self.smallcap.health()}" if self.smallcap is not None else ''))
            if time.time() - last_memory >= 600:
                # where the memory sits (process classes + the bot's own structures), every 10 minutes
                last_memory = time.time()
                try:
                    import memreport
                    # off the loop: walking the containers took 1.2s (2026-10-05); a container changing size while
                    # it is read raises, reported and retried in 10 minutes
                    logger.info(await asyncio.to_thread(memreport.report, self.fetcher, self))
                except Exception as e:
                    errors.report('scanner.memreport', e)

    def _save_state(self):
        if not getattr(self, '_state_loaded', False):
            # a stop during start-up, before _load_state: saving now would overwrite the open cards with an empty
            # book, and the demo then closes every position as an orphan (2026-10-21 12:06 -> 11 ORPHAN closes)
            logger.warning("State not saved: the start-up stopped before the saved state was loaded")
            return
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
            self._state_loaded = True
            return
        try:
            with open(path, encoding='utf-8') as f:
                state = json.load(f)
            self.book.load_state(state.get('book'), time.time())
            self.fetcher.whales.load_state(state.get('whales'))
            self.detector.load_state(state.get('fired_events'), int(time.time() * 1000))
            open_cards = sum(1 for s in self.book.signals.values() if not s.finished)
            logger.info(f"State restored: {open_cards} open cards, {len(state.get('whales') or {})} whale histograms")
            self._state_loaded = True
        except Exception as e:
            # keep the file and never close demo trades as orphans this run (their stops stay on BingX); the state
            # stays unsaved until a restart reads it, so a bad read cannot wipe the open cards
            logger.warning(f"State restore failed ({e}); state is not saved and orphans are not closed this run")
            try:
                import shutil
                shutil.copy2(path, path + '.bad')
            except OSError:
                pass

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

    CONFIRM_RU = {'flow': 'поток', 'spot': 'спот', 'oi': 'OI', 'orderflow': 'ордерфлоу', 'vsa': 'VSA',
                  'htf_zone': 'зона ст.ТФ', 'smt': 'SMT', 'killzone': 'килзона'}
    EVENT_RU = {'ENTRY': 'вход', 'ZONE': 'в зоне', 'TP1': 'TP1', 'TP2': 'TP2', 'TP3': 'TP3', 'SL': 'стоп',
                'CLOSED': 'закрыта', 'INVALID': 'отменена', 'RESTOP': 'стоп перенесён', 'PARTIAL': 'половина зафиксирована', 'ADD': 'добавлен юнит'}

    @staticmethod
    def _why_ru(reason: Optional[str]) -> str:
        r = reason or ''
        for en, ru in (("the method's session ended", 'конец сессии метода'), ('time stop', 'по времени (нет движения)'),
                       ('trade open', 'по времени (лимит жизни сделки)'), ('opposite Bollinger band', 'дошли до противоположной полосы Боллинджера'),
                       ('Turtles', 'выход по каналу Turtles'), ('Connors', 'выход Connors (SMA5)'),
                       ('opposite', 'противоположный сигнал'), ('older signal logic', 'смена версии логики')):
            if en in r:
                return ru
        return r or 'по правилу метода'

    @staticmethod
    def _card_key(s) -> str:
        return f"{s.symbol}|{s.group_key}|{s.created:.3f}"

    def _entry_still_actionable(self, item) -> Optional[str]:
        """The notifier's retry check of a queued ENTRY (audit 2026-10-18 P1): None while the trade is open and the price
        still pays the plan's minimum R:R to TP1 against its stop (strategies.geometry's rule); else why not."""
        from strategies.geometry import _min_rr
        s = next((x for x in self.book.signals.values() if self._card_key(x) == item.get('card')), None)
        if s is None or s.finished or not s.entered_at:
            return f"the trade is no longer open ({s.status if s else 'card gone'})"
        lv, d, p = s.levels or {}, s.direction, s.last_price
        if not p or (s.plan or {}).get('no_stop') or not isinstance(lv.get('tp1'), (int, float)) or lv.get('rr_tp1') is None:
            return None
        risk, reward = d * (p - lv['sl']), d * (lv['tp1'] - p)
        if risk <= 0 or reward <= 0:
            return f"the price {p:.6g} is already beyond the stop / TP1"
        if reward / risk < _min_rr(s.plan or {}):
            return f"R:R from the price {p:.6g} is {reward / risk:.2f}, below the plan's minimum"
        return None

    def _notify(self):
        """Card events for Telegram / toasts in Russian (the owner, 2026-10-07: the English one-liner with internal
        confirmation keys and the no-target placeholders as TPs was unreadable)."""
        def px(p):
            return f"{p:.6g}"
        for s, event in self.book.events:
            side = '🟢 ЛОНГ' if s.direction > 0 else '🔴 ШОРТ'
            name = s.symbol.replace(':USDT', '').replace('/USDT', '')
            title = f"{side} {name} · {s.group_key} — {self.EVENT_RU.get(event, event)}"
            lv = s.levels or {}
            if event == 'ENTRY' and lv:
                e = lv['entry']
                if (s.plan or {}).get('no_stop'):
                    # audit B10: a system without a stop (Connors): 'sl' is only the R unit, never an order to place
                    lines = [f"Вход {px(e)} · стопа нет (система выходит по правилу; расчётная единица риска R = "
                             f"{px(lv['sl'])}, {(lv['sl'] / e - 1) * 100:+.1f}%, не ставить как стоп)"]
                else:
                    lines = [f"Вход {px(e)} · стоп {px(lv['sl'])} ({(lv['sl'] / e - 1) * 100:+.1f}%)"]
                if (s.plan or {}).get('no_tp') or lv.get('rr_tp1') is None:
                    exit_ru = {'bollinger': 'выход у противоположной полосы Боллинджера',
                               'breakout': 'выход по противоположному каналу Дончиана (Turtles)',
                               'orb': 'выход в конце торговой сессии (Crabel)',
                               'connors': 'выход по закрытию дня за SMA5 (Connors)'}
                    lines.append("Целей нет: " + exit_ru.get(self.book.strategy(s).name if self.book.strategy(s)
                                                             else '', lv.get('tp1_src') or 'выход по правилу метода'))
                else:
                    tps = [lv[k] for k in ('tp1', 'tp2', 'tp3') if isinstance(lv.get(k), (int, float))]
                    uniq = list(dict.fromkeys(tps))
                    lines.append("Цели " + " · ".join(f"{px(t)} ({(t / e - 1) * 100:+.1f}%)" for t in uniq)
                                 + f" · R:R {lv['rr_tp1']:.1f}" + (f" (средний {lv['rr_blend']:.1f})"
                                                                   if lv.get('rr_blend') is not None else ''))
                conf = [f"{self.CONFIRM_RU[k]} {'✓' if confirm.positive(v) else '✗'}"
                        for k, v in (s.confirms or {}).items()
                        if k in self.CONFIRM_RU and v is not None and v != confirm.NA]
                if conf:
                    lines.append("Подтверждения: " + ", ".join(conf))
                if lv.get('obstacle_r') is not None and lv.get('rr_tp1'):
                    # audit 2026-10-18 P2 #7: the nearest strong zone before TP1 (diagnostic, not a rule)
                    lines.append(f"Уровень на пути к цели 1: {lv['obstacle_r']:.2f}R из {lv['rr_tp1']:.2f}R "
                                 f"({str(lv.get('obstacle_src') or '')[:60]})")
                text = "\n".join(lines)
            elif event == 'ZONE' and s.plan:
                text = f"Зона {px(s.plan['zone_lo'])}–{px(s.plan['zone_hi'])}, ждём триггер {s.plan['trigger_minutes']}m"
            else:
                # what happened to the trade, against its entry - the follow-up of the entry message
                r = s.final_r if s.finished_at and s.final_r is not None else s.r_now
                r_txt = f" · {r:+.2f}R" if r is not None else ''
                head = f"Вход {px(lv['entry'])} → сейчас {px(s.last_price)}{r_txt}" if lv.get('entry') else \
                    f"Цена {px(s.last_price)}{r_txt}"
                if event.startswith('TP'):
                    k = event[2:]
                    rest = (f"\nСтоп теперь {px(lv['sl'])}" if lv.get('sl') and not (s.plan or {}).get('no_stop') else '') + \
                        (f", следующая цель {px(lv['tp' + str(int(k) + 1)])}" if k in ('1', '2')
                         and isinstance(lv.get('tp' + str(int(k) + 1)), (int, float)) else '')
                    text = f"Цель {k} взята {px(lv.get('tp' + k, s.last_price))}\n{head}{rest}"
                elif event == 'SL':
                    text = f"Стоп {px(lv.get('sl', s.last_price))} — сделка закрыта\n{head}"
                elif event == 'CLOSED':
                    text = f"Сделка закрыта: {self._why_ru(s.finish_reason)}\n{head}"
                elif event == 'RESTOP':
                    text = f"Стоп перенесён на {px(lv['sl'])} ({lv.get('sl_src') or 'трейлинг'})\n{head}"
                elif event == 'PARTIAL':
                    text = f"Половина позиции зафиксирована на +1R\n{head}"
                elif event == 'ADD':
                    text = (f"Добавлен юнит {len(s.units or [])} по {px(s.units[-1][0]) if s.units else px(s.last_price)}, "
                            f"стоп всех юнитов {px(lv['sl'])}\n{head}")
                else:
                    text = head
            self.notifier.send(event, title, text + "\n<i>механические правила, не совет</i>", card=self._card_key(s))

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
