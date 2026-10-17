"""
B9 (eng-59): the archive replay of the LIVE card lifecycle for every strategy - the live SignalBook stepped minute by
minute over the Binance public archive, fed by the live detectors (strategies.structure.build_maps / build_context and
LiveDetector for the 15m-close events, strategies.loopside.LoopDetectors for the loop-side ones, the scorer's phases and
Tier-0 rules for the continuation), with the scanner's hooks rebuilt from history. Its output is what pretraining /
meta-labeling and the per-strategy archive studies (plan 2.3-2.9, 3.1) need: every card and every entry (passed and
vetoed) with the card's own net result (`final_r`, eng-58: fees, slippage by liquidity, funding).

What the archive cannot give (the live bot has it, the replay runs without - an estimate, not the live result):
- other venues' flows / OI / funding, liquidations (so no liquidation-cascade setups: FLUSH / SQUEEZE REVERSAL), order
  books (no walls / liquidity bands / book confirmations), Hyperliquid accounts, Coinbase premium, whale sweeps;
- confirmations are Binance-only (futures / spot taker delta from the 1m candles, OI from the 5-minute metrics, VSA,
  CVD divergence); the footprint order-flow reading does not exist;
- pools / the crowd limit / BTC's bias across coins hold only for the coins replayed together (one SignalBook);
- prices are final 1m candles (the live bot sees each trade); a scan runs once per minute (live: every few seconds).

Run:  .venv\\Scripts\\python replay.py --months 6 --coins 20 [--workers 1] [--days N for a smoke test]
Writes data/replay/<run>/cards.parquet and entries.parquet (resumable per coin group).
"""
import argparse
import logging
import os
import time
from collections import deque
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import polars as pl

from config import CONFIG


logger = logging.getLogger('replay')

MINUTE_MS = 60_000
QUARTER_MS = 900_000
HOUR_MS = 3_600_000
DAY_MS = 86_400_000
STREAM_COLS = [0, 1, 2, 3, 4, 6, 7, 5]               # the stream format [t, o, h, l, c, quote, taker buy quote, base]


def _bucket_list(rows: np.ndarray, ms: int) -> List[List[float]]:
    """Complete candles of `ms` from 1m rows [ts, o, h, l, c, v, qv, tbq] as [ts, o, h, l, c, qv, tbq, v]."""
    from pretrain import _bucket
    out = _bucket(rows, ms)
    return [[int(r[0]), r[1], r[2], r[3], r[4], r[6], r[7], r[5]] for r in out]


class ArchiveCoin:
    """One coin's history and the MarketData stand-in the live detectors read (`d1`, `h1`, `h4`, `w1`, `tier0`,
    `oi_samples`, `minute_closed_until`, `quote_volume_24h`)."""

    def __init__(self, key: str, fut_id: str, spot_id: Optional[str], start: date, end: date, archive):
        from indicators import compute_indicators_batch, seasonal_factors
        from pretrain import _bucket, _raw_frame, _asof
        from scorer import PhaseScorer
        self.key, self.fut_id = key, fut_id
        warm = start - timedelta(days=12)                  # 1h / 15m history before the window (8 days of 1h + EMA)
        self.fut = archive.klines_1m('futures', fut_id, warm, end)
        self.spot = archive.klines_1m('spot', spot_id, warm, end) if spot_id else np.empty((0, 8))
        self.met = archive.metrics(fut_id, warm, end)
        self.fund = archive.funding(fut_id, warm, end)
        d = archive.klines_ohlc('futures', fut_id, '1d', start - timedelta(days=420), end)
        self.daily = [[int(r[0]), r[1], r[2], r[3], r[4], r[5]] for r in d]
        self.has_spot = bool(spot_id)
        self.m_ts = self.fut[:, 0] if len(self.fut) else np.empty(0)
        self.s_ts = self.spot[:, 0] if len(self.spot) else np.empty(0)
        self.qv_cum = np.concatenate(([0.0], np.cumsum(self.fut[:, 6]))) if len(self.fut) else np.zeros(1)
        # 15m frames with indicators and phase scores, as pretrain builds them
        c15 = _bucket(self.fut, QUARTER_MS)
        s15 = _bucket(self.spot, QUARTER_MS) if len(self.spot) else np.empty((0, 8))
        oi15 = {}
        for t, v in zip(self.met['ts'], self.met['oi']):
            if int(t) % QUARTER_MS == 0 and v:
                oi15[int((t - 1) // QUARTER_MS * QUARTER_MS)] = float(v)
        fut_all = compute_indicators_batch({key: _raw_frame(c15, oi15)}, {key: (0.0, 0.0)})
        spot_all = compute_indicators_batch({key: _raw_frame(s15, None)}, {key: (0.0, 0.0)}) if len(s15) else None
        if len(self.fund):
            closes = fut_all['timestamp'].to_numpy() + QUARTER_MS
            rates = [(_asof(self.fund[:, 0], self.fund[:, 1], t) or 0.0) for t in closes]
            fut_all = fut_all.with_columns(pl.Series('funding_rate', rates), pl.Series('predicted_funding', rates))
            if spot_all is not None:
                sc = spot_all['timestamp'].to_numpy() + QUARTER_MS
                sr = [(_asof(self.fund[:, 0], self.fund[:, 1], t) or 0.0) for t in sc]
                spot_all = spot_all.with_columns(pl.Series('funding_rate', sr), pl.Series('predicted_funding', sr))
        self.fut_all = fut_all.sort('timestamp')
        self.f_ts = self.fut_all['timestamp'].to_numpy()
        scored = PhaseScorer().calculate_scores(spot_all, fut_all, None, None)
        self.scored = scored.sort('timestamp') if not scored.is_empty() else scored
        self.sc_ts = self.scored['timestamp'].to_numpy() if not scored.is_empty() else np.empty(0)
        self.fut_ind = self.fut_all.select('timestamp', 'ret_std', 'oi_std', 'atr').to_numpy()
        self.h1_all = _bucket_list(self.fut, HOUR_MS)
        self.h1_close = np.array([c[0] + HOUR_MS for c in self.h1_all]) if self.h1_all else np.empty(0)
        self.c15_all = [[int(r[0]), r[1], r[2], r[3], r[4], r[6], r[7], r[5]] for r in c15]
        self.c15_close = np.array([c[0] + QUARTER_MS for c in self.c15_all]) if self.c15_all else np.empty(0)
        self.oi_pts = [(float(t), float(v)) for t, v in zip(self.met['ts'], self.met['oi']) if v]
        self.oi_ts = np.asarray([p[0] for p in self.oi_pts]) if self.oi_pts else np.empty(0)
        self.d_close = np.array([c[0] + DAY_MS for c in self.daily]) if self.daily else np.empty(0)
        self._season: Dict[int, Optional[Dict]] = {}
        self._seasonal_factors = seasonal_factors
        # live MarketData fields
        self.d1: List = []
        self.h1: List = []
        self.h4: List = []
        self.w1: List = []
        self.tier0: Dict = {}
        self.oi_samples: deque = deque(maxlen=64)
        self.oi_5m: deque = deque(maxlen=300)
        self.minute_closed_until = 0
        self.quote_volume_24h = 0.0
        self.j = 0                                         # minutes closed so far

    # ------------------------------------------------------------------ the live fields as of now
    def advance(self, now_ms: int):
        from pretrain import closed_minutes
        self.j = closed_minutes(self.m_ts, now_ms)
        self.minute_closed_until = int(self.m_ts[self.j - 1]) if self.j else 0
        n = min(self.j, 1440)
        self.quote_volume_24h = float(self.qv_cum[self.j] - self.qv_cum[self.j - n]) if n else 0.0
        k = int(np.searchsorted(self.oi_ts, now_ms, side='right')) if len(self.oi_ts) else 0
        self.oi_samples = deque(self.oi_pts[max(0, k - 13):k], maxlen=64)
        # audit R07: the OI robot's 5-minute OI over the last day (MarketData.oi_5m), one sample per 5-minute bucket -
        # without it the OI BUILD family never ran in the replay
        if k != getattr(self, '_oi5_k', None):
            self._oi5_k = k
            buckets: Dict[int, tuple] = {}
            for t, v in self.oi_pts[max(0, k - 2000):k]:
                if t > now_ms - 300 * 300_000:
                    buckets[int(t) // 300_000] = (t, v)
            self.oi_5m = deque((buckets[b] for b in sorted(buckets)), maxlen=300)
        h = int(np.searchsorted(self.h1_close, now_ms, side='right'))
        if not self.h1 or (h and self.h1[-1][0] != self.h1_all[h - 1][0]):
            self.h1 = self.h1_all[max(0, h - 200):h]
            hl = self.h1_all[max(0, h - 800):h]
            self.h4 = _group(hl, 4 * HOUR_MS)[-200:]
        dd = int(np.searchsorted(self.d_close, now_ms, side='right'))
        if not self.d1 or (dd and self.d1[-1][0] != self.daily[dd - 1][0]):
            self.d1 = self.daily[max(0, dd - 1400):dd]          # review V13: as live (fetcher, 1400 days)
            self.w1 = _weeks(self.daily[:dd])[-60:]

    def minutes(self, count: int = 600) -> List[List[float]]:
        """FINAL 1m futures candles in the stream format (the scanner's _minute_candles). audit R02: 600 as the live
        buffer (MarketData.minute_klines) - 240 left PO3 21 of its 24 required Asian 5m bars at 02:15 NY."""
        return self.fut[max(0, self.j - count):self.j][:, STREAM_COLS].tolist()

    def spot_minutes(self, now_ms: int, count: int = 60) -> Optional[List[List[float]]]:
        if not self.has_spot:
            return None
        from pretrain import closed_minutes
        js = closed_minutes(self.s_ts, now_ms)
        return self.spot[max(0, js - count):js][:, STREAM_COLS].tolist()

    def price(self) -> Optional[float]:
        return float(self.fut[self.j - 1, 4]) if self.j else None

    def frame(self, now_ms: int) -> pl.DataFrame:
        """The closed 15m futures frame with indicators (the scanner's frame part)."""
        n = int(np.searchsorted(self.f_ts + QUARTER_MS, now_ms, side='right'))
        return self.fut_all.slice(max(0, n - 300), min(n, 300))

    def scored_row(self, now_ms: int) -> Optional[Dict]:
        n = int(np.searchsorted(self.sc_ts + QUARTER_MS, now_ms, side='right'))
        return self.scored.row(n - 1, named=True) if n else None

    def compute_tier0(self, now_ms: int) -> Dict:
        """calculate_tier0_metrics exactly as pretrain.tier0_at (only CLOSED minutes)."""
        from indicators import calculate_tier0_metrics, minute_delta, seasonal_scale
        j = self.j
        minutes = deque(self.fut[max(0, j - 30):j][:, STREAM_COLS].tolist(), maxlen=240)
        ticker = deque(((k[0] + 59_999, k[4], 0.0) for k in self.fut[max(0, j - 10):j][:, STREAM_COLS].tolist()),
                       maxlen=400)
        n = min(j, 1440)
        avg_minute = (self.qv_cum[j] - self.qv_cum[j - n]) / max(1, n) if n else 0.0
        q = int(np.searchsorted(self.fut_ind[:, 0], now_ms - QUARTER_MS, side='right')) - 1
        ret_std = self.fut_ind[q, 1] if q >= 0 and self.fut_ind[q, 1] == self.fut_ind[q, 1] else None
        oi_std = self.fut_ind[q, 2] if q >= 0 and self.fut_ind[q, 2] == self.fut_ind[q, 2] else None
        day = now_ms // DAY_MS
        if day not in self._season:
            h = int(np.searchsorted(self.h1_close, day * DAY_MS, side='right'))
            self._season[day] = self._seasonal_factors(self.h1_all[max(0, h - 672):h])
        season = self._season[day]
        if ret_std:
            ret_std *= seasonal_scale(season, now_ms, 'ret')
        avg_minute *= seasonal_scale(season, now_ms, 'vol')
        m = calculate_tier0_metrics(ticker, self.oi_samples, minutes, now_ms, ret_std=ret_std, oi_std=oi_std,
                                    avg_minute_usd=avg_minute)
        m['futures_cvd_5m'] = minute_delta(minutes, now_ms)
        sm = self.spot_minutes(now_ms, 6)
        if sm is not None:
            m['spot_cvd_5m'] = minute_delta(sm, now_ms)
        m['whale_net_5m'] = None
        m['volume_24h'] = self.quote_volume_24h
        self.tier0 = m
        return m

    def m15(self, now_ms: int, count: int = 499) -> List[List[float]]:
        n = int(np.searchsorted(self.c15_close, now_ms, side='right'))
        return self.c15_all[max(0, n - count):n]

    def live_15m(self, now_ms: int) -> Tuple[int, Optional[float], Optional[float]]:
        """The running 15m candle's open time / high / low (the plan key: leg plans follow it)."""
        start = now_ms // QUARTER_MS * QUARTER_MS
        a = int(np.searchsorted(self.m_ts, start, side='left'))
        seg = self.fut[a:self.j]
        return (int(start), float(seg[:, 2].max()) if len(seg) else None, float(seg[:, 3].min()) if len(seg) else None)


def _group(rows: List[List[float]], ms: int) -> List[List[float]]:
    out: Dict[int, List[float]] = {}
    for r in rows:
        k = int(r[0] // ms * ms)
        c = out.get(k)
        if c is None:
            out[k] = [k, r[1], r[2], r[3], r[4], r[5]]
        else:
            c[2], c[3], c[4], c[5] = max(c[2], r[2]), min(c[3], r[3]), r[4], c[5] + r[5]
    return [out[k] for k in sorted(out)]


def _weeks(daily: List[List[float]]) -> List[List[float]]:
    """Binance weekly candles (Monday 00:00 UTC) from daily ones; the running week dropped."""
    out: Dict[int, List[float]] = {}
    for r in daily:
        monday = int(r[0] - ((r[0] // DAY_MS + 3) % 7) * DAY_MS)        # 1970-01-01 was a Thursday
        c = out.get(monday)
        if c is None:
            out[monday] = [monday, r[1], r[2], r[3], r[4], r[5]]
        else:
            c[2], c[3], c[4], c[5] = max(c[2], r[2]), min(c[3], r[3]), r[4], c[5] + r[5]
    weeks = [out[k] for k in sorted(out)]
    if weeks and daily and weeks[-1][0] + 7 * DAY_MS > daily[-1][0] + DAY_MS:
        weeks = weeks[:-1]
    return weeks


def _bias(bars: List[List[float]]) -> Optional[int]:
    if len(bars) < 2:
        return None
    prev, last = bars[-2], bars[-1]
    return 1 if last[4] > prev[2] else -1 if last[4] < prev[3] else 0


class Replay:
    """Several coins stepped together through one live SignalBook."""

    def __init__(self, coins: Dict[str, ArchiveCoin], btc: Optional[ArchiveCoin]):
        from signal_book import SignalBook
        from strategies.detect import LiveDetector
        from strategies.loopside import LoopDetectors
        self.coins, self.btc = coins, btc

        def minutes_of(s):
            # BTC is read by every group (BTC overlays, its bias) but replayed inside only one of them
            c = self.coins.get(s) or (self.btc if self.btc is not None and s == self.btc.key else None)
            return c.minutes() if c is not None else []
        self._minutes_of = minutes_of
        self.now_ms = 0
        self.book = SignalBook()
        # the replay measures the methods' OWN plans: the optimized profiles (models/profiles*.json, research_optimize*)
        # are fitted on this replay's output and must not shape it
        from strategies import profiles
        profiles.select = lambda strategy, regime: (None, None)
        self.detector = LiveDetector()
        self.loopside = LoopDetectors(self._minutes_of, lambda s: self.coins[s].m15(self.now_ms))
        self.loopside.volume_rank = lambda s: 1 + sum(1 for c in self.coins.values()
                                                      if c.quote_volume_24h > self.coins[s].quote_volume_24h)
        self.raw: Dict[str, list] = {}
        self.ctx_sig: Dict[str, int] = {}
        b = self.book
        b.levels_of = lambda s: self.raw.get(s) or None
        b.htf_of = lambda s: self.coins[s].h1
        b.daily_of = lambda s: self.coins[s].d1
        b.context_of = lambda s: self.detector.context.get(s)
        b.band_of = self._band
        b.plan_key_of = lambda s: (self.ctx_sig.get(s), self.coins[s].live_15m(self.now_ms))
        b.map_ready_of = lambda s: s in self.raw
        b.btc_bias_of = self._btc_bias
        # eng-67 / eng-69: the plans' own-timeframe ATR (stop floor, zone buffer, target spacing) - missing here until
        # eng-73, so the eng-72 replay measured those plans with the 15m ATR only
        b.tf_atr_of = self._tf_atrs
        self.cards: List[Dict] = []
        self.entries: List[Dict] = []

    def _btc_bias(self) -> Optional[int]:
        c = self.btc
        if c is None:
            return None
        for bars in (c.w1, c.d1):
            bias = _bias(bars)
            if bias:
                return bias
        return None

    def _tf_atrs(self, symbol: str) -> Dict[str, float]:
        """Scanner._tf_atrs on the archive: ATR14 (simple mean of true ranges) of the closed 1h / 4h / daily candles."""
        c = self.coins.get(symbol) or (self.btc if self.btc is not None and symbol == self.btc.key else None)
        out: Dict[str, float] = {}
        if c is None:
            return out
        for tf, rows, period in (('1h', c.h1, HOUR_MS), ('4h', c.h4, 4 * HOUR_MS), ('1d', c.d1, DAY_MS)):
            closed = [r for r in list(rows)[-20:] if r[0] + period <= self.now_ms]
            if len(closed) >= 15:
                trs = [max(k[2] - k[3], abs(k[2] - p[4]), abs(k[3] - p[4])) for p, k in zip(closed[-15:-1], closed[-14:])]
                out[tf] = sum(trs) / len(trs)
        return out

    def _band(self, symbol: str, direction: int, asof_ms: Optional[int] = None) -> Optional[float]:
        """audit R03: the live exit's band (Scanner._opposite_band) - BB(20, 2) of the closed 4h candles built from
        the closed 1h ones known at asof_ms (the as-of rule of _manage_trade; now when None)."""
        from strategies.structure import bars_4h
        cut = self.now_ms if asof_ms is None else int(asof_ms)
        h1 = [c for c in self.coins[symbol].h1 if c[0] + 3_600_000 <= cut]
        closes = [c[4] for c in bars_4h(h1, cut)[-20:]] if h1 else []
        if len(closes) < 20:
            return None
        mean = sum(closes) / 20
        sd = (sum((x - mean) ** 2 for x in closes) / 20) ** 0.5
        return mean + direction * 2 * sd

    def _enrich(self, c: ArchiveCoin, sig: Dict):
        """The subset of Scanner._enrich the archive can rebuild (the rest stays None)."""
        from strategies.structure import coin_trend
        ctx = self.detector.context.get(c.key)
        sig['coin_trend'] = ctx.trend if ctx is not None else None
        sig['vol_ratio'] = ctx.vol_ratio if ctx is not None else None
        sig['daily_bias'] = _bias(c.d1)
        sig['weekly_bias'] = _bias(c.w1)
        sig['trend_4h'] = coin_trend(c.h4) if len(c.h4) >= 30 else None
        sig['trend_1d'] = coin_trend(c.d1) if len(c.d1) >= 30 else None
        sig['btc_bias'] = self._btc_bias()
        sig['has_spot'] = c.has_spot
        sig['volume_24h'] = c.quote_volume_24h

    def _confirm(self, symbol: str, strategy: str, direction: int, since_ms: int, until_ms: int,
                 extreme_ms: Optional[int] = None) -> Dict:
        from strategies import confirm
        c = self.coins[symbol]
        oi = confirm.oi_change(list(c.oi_samples), until_ms - confirm.HOUR_MS, until_ms)
        out = confirm.evaluate(strategy, direction, c.minutes(), c.spot_minutes(until_ms), oi, since_ms, until_ms,
                               extreme_ms, None)
        out['_window'] = [int(since_ms), int(until_ms), int(extreme_ms) if extreme_ms is not None else None]
        return out

    def _maps(self, now_ms: int):
        """At a 15m close: every coin's quick map + context (build_maps, as the scanner's maps worker)."""
        from strategies.structure import PART_COLUMNS, build_maps
        jobs = []
        corr = {}
        for name in ('BTC', 'ETH'):
            ref = next((c for c in self.coins.values() if c.key.startswith(name + '/')), None)
            if ref is None and name == 'BTC':
                ref = self.btc
            if ref is not None:
                corr[name] = np.asarray(ref.m15(now_ms), dtype=np.float64)
        for s, c in self.coins.items():
            part = c.frame(now_ms)
            if part.is_empty():
                continue
            jobs.append((s, part.select(PART_COLUMNS), list(c.h1), [], [], [], now_ms, [], True,
                         np.asarray(c.m15(now_ms), dtype=np.float64),
                         np.asarray(c.h1_all[max(0, int(np.searchsorted(c.h1_close, now_ms, side='right')) - 499):
                                             int(np.searchsorted(c.h1_close, now_ms, side='right'))], dtype=np.float64),
                         # audit R01: the whole causal daily history (<= 370, as live) - 60 days never reached the
                         # cup detector's 120-day gate, the family was untested
                         list(c.d1), list(c.h4), list(c.w1)))
        for s, (raw, ctx) in build_maps(jobs, corr).items():
            self.raw[s] = raw
            self.detector.set_context(s, ctx, now_ms)
            self.ctx_sig[s] = now_ms

    def step(self, now_ms: int):
        from scorer import signals_from_rows
        self.now_ms = now_ms
        for c in self.coins.values():
            c.advance(now_ms)
        if self.btc is not None and self.btc.key not in self.coins:
            self.btc.advance(now_ms)
        if now_ms % QUARTER_MS < MINUTE_MS:
            self._maps(now_ms)
        rows, tier0 = {}, {}
        for s, c in self.coins.items():
            if not c.j:
                continue
            tier0[s] = c.compute_tier0(now_ms)
            row = c.scored_row(now_ms)
            if row is not None:
                rows[s] = row
        signals = signals_from_rows(rows, tier0)
        for s, sig in signals:
            self._enrich(self.coins[s], sig)
        for s, c in self.coins.items():
            setups = self.detector.scan(s, c.minutes(), c.tier0, now_ms, ()) if s in self.detector.context else []
            setups += self.loopside.scan(s, c, now_ms)
            row = rows.get(s) or {}
            for setup in setups:
                sig = dict(c.tier0)
                sig.update(is_setup=True, is_structured=False, is_tier_0_anomaly=False, active_phases=[],
                           long_score=0, short_score=0, alert_type='LONG' if setup['direction'] > 0 else 'SHORT')
                sig.update(setup)
                sig['perp_led_long'] = bool(row.get('perp_led_long'))
                sig['perp_led_short'] = bool(row.get('perp_led_short'))
                for k in ('spot_delta_1h', 'perp_delta_1h', 'adx', 'adx_prev'):
                    if row.get(k) is not None:
                        sig[k] = row[k]
                self._enrich(c, sig)
                signals.append((s, sig))
        prices = {s: c.price() for s, c in self.coins.items()}
        _, entries = self.book.update(signals, _Frames(self, now_ms), lambda s: prices.get(s),
                                      self._minutes_of, now_ms / 1000, confirm_of=self._confirm)
        for e in entries:
            self.entries.append(_entry_row(e, now_ms))
        for symbol, group_key, reason, sig in self.book.vetoed:
            self.entries.append({'ts': now_ms, 'symbol': symbol, 'setup': group_key, 'stage': 'setup',
                                 'vetoed': reason, 'direction': sig.get('direction')})
        for s in self.book.finished_now:
            self.cards.append(_card_row(s))


class _Frames:
    def __init__(self, rp: Replay, now_ms: int):
        self.rp, self.now_ms = rp, now_ms

    def get(self, symbol: str):
        c = self.rp.coins.get(symbol)
        return c.frame(self.now_ms) if c is not None else None


def _entry_row(e, now_ms: int) -> Dict:
    lv = e.levels or {}
    return {'ts': now_ms, 'symbol': e.symbol, 'setup': e.group_key, 'strategy': e.mode, 'direction': e.direction,
            'stage': 'entry', 'vetoed': e.vetoed, 'entry': lv.get('entry'), 'sl': lv.get('sl'), 'tp1': lv.get('tp1'),
            'tp2': lv.get('tp2'), 'tp3': lv.get('tp3'), 'rr_tp1': lv.get('rr_tp1'), 'sl_src': lv.get('sl_src'),
            'limit_entry': lv.get('limit_entry'), 'volume_24h': (e.sig or {}).get('volume_24h'),
            'funding': (e.sig or {}).get('funding_rate'),
            'funding_hours': (e.sig or {}).get('funding_interval_h'),     # review V09: the contract's interval
            # eng-133 research columns (written only): the setup's timeframe and its ATR(14) at the entry, the shadow
            # tags (strings are not picked up by f_*), the logic version
            'tf': (e.plan or {}).get('tf'), 'atr_tf': (e.plan or {}).get('tf_atr'),
            'shadow_veto': (e.sig or {}).get('shadow_veto'), 'logic_version': CONFIG.journal.logic_version,
            'tp1_src': lv.get('tp1_src'), 'conf_n': sum(1 for k, v in (e.confirms or {}).items()
                                                         if not k.startswith('_') and v is True),
            # the signal's numeric context (Tier-0 metrics, trends, biases): the meta-labeling features
            **{f"f_{k}": float(v) for k, v in (e.sig or {}).items()
               if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and k not in ('direction',)},
            **{f"c_{k}": (v if isinstance(v, bool) else None) for k, v in (e.confirms or {}).items()
               if not k.startswith('_')}}


def _card_row(s) -> Dict:
    lv = s.levels or {}
    return {'symbol': s.symbol, 'setup': s.group_key, 'strategy': s.mode, 'direction': s.direction,
            'created_ms': int(s.created * 1000), 'entered_ms': int(s.entered_at * 1000) if s.entered_at else None,
            'finished_ms': int(s.finished_at * 1000) if s.finished_at else None, 'status': s.status,
            'final_r': s.final_r, 'reason': s.finish_reason, 'entry': lv.get('entry'), 'sl': lv.get('sl'),
            'tp1': lv.get('tp1'), 'best_target': s.best_target, 'units': len(s.units or []) or None,
            'vetoed_triggers': s.vetoed_triggers}


def run(coins: List[Tuple[str, str, Optional[str]]], start: date, end: date, out_dir: str, rate: float) -> Tuple[int, int]:
    from history import Archive
    import strategies.loopside  # noqa: F401  (import errors before the long download)
    archive = Archive(rate_bytes=rate)
    loaded: Dict[str, ArchiveCoin] = {}
    for key, fut_id, spot_id in coins:
        t = time.time()
        c = ArchiveCoin(key, fut_id, spot_id, start, end, archive)
        if len(c.fut) < 1440 * 10:
            logger.info(f"{key}: too little history, skipped")
            continue
        loaded[key] = c
        logger.info(f"{key}: loaded in {time.time() - t:.0f}s ({len(c.fut)} minutes)")
    btc = loaded.get('BTC/USDT:USDT')
    if btc is None:
        btc = ArchiveCoin('BTC/USDT:USDT', 'BTCUSDT', 'BTCUSDT', start, end, archive)
    rp = Replay(loaded, btc)
    t0 = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp() * 1000)
    t1 = int(datetime(end.year, end.month, end.day, tzinfo=timezone.utc).timestamp() * 1000) + DAY_MS
    started = time.time()
    # the scan a few seconds after each minute's close (live: every ~10s)
    for k, now_ms in enumerate(range(t0 + 5_000, t1, MINUTE_MS)):
        rp.step(now_ms)
        if k % 1440 == 0 and k:
            logger.info(f"{datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc):%Y-%m-%d}: {len(rp.cards)} cards, "
                        f"{len(rp.entries)} entries / vetoes, {time.time() - started:.0f}s")
    # every entry - passed or vetoed - replayed like the journal does (levels.simulate over the trade's lifetime, net
    # of the round-trip fee): the veto's effect is measured on the same geometry (stats.vetoes_table's question)
    from levels import simulate
    from stats import net_r
    ttl = CONFIG.levels.trade_ttl_sec * 1000
    for e in rp.entries:
        if e.get('stage') != 'entry' or e.get('entry') is None or e.get('sl') is None or e.get('tp1') is None:
            continue
        c = loaded.get(e['symbol'])
        if c is None:
            continue
        a = int(np.searchsorted(c.m_ts, e['ts'], side='left'))
        b = int(np.searchsorted(c.m_ts, e['ts'] + ttl, side='left'))
        lv = {k: e.get(k) for k in ('entry', 'sl', 'tp1', 'tp2', 'tp3', 'limit_entry', 'volume_24h', 'symbol')}
        res = simulate(lv, e['direction'], c.fut[a:b, :6].tolist(), funding_8h=e.get('funding'),
                       funding_hours=e.get('funding_hours'))
        e['outcome'] = res.get('outcome')
        for col in ('r_tp1', 'r_tp2', 'r_be'):
            e[col] = net_r({col: res.get(col), 'entry': lv['entry'], 'entry_fill': res.get('entry_fill'),
                            'sl': lv['sl']}, col)                 if res.get(col) is not None else None
    os.makedirs(out_dir, exist_ok=True)
    pl.DataFrame(rp.cards, infer_schema_length=None).write_parquet(os.path.join(out_dir, 'cards.parquet'))
    pl.DataFrame(rp.entries, infer_schema_length=None).write_parquet(os.path.join(out_dir, 'entries.parquet'))
    return len(rp.cards), len(rp.entries)


def main():
    from history import Archive
    from pretrain import _spot_pair
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', datefmt='%H:%M:%S')
    ap = argparse.ArgumentParser()
    ap.add_argument('--months', type=int, default=6)
    ap.add_argument('--days', type=int, default=0, help='replay only the last N days (a smoke test)')
    ap.add_argument('--coins', type=int, default=20)
    ap.add_argument('--symbols', default='', help='comma-separated futures ids instead of the top --coins')
    ap.add_argument('--rate', type=float, default=2e6)
    ap.add_argument('--group', type=int, default=5, help='coins replayed together (one SignalBook)')
    ap.add_argument('--out', default=os.path.join('data', 'replay', 'run'))
    ap.add_argument('--shard', default='', help="k/N: run only the groups with index %% N == k (parallel processes "
                                                "on one --out; the same coin selection in every process)")
    args = ap.parse_args()
    arch = Archive(rate_bytes=args.rate)
    today = date.today()
    end = date(today.year, today.month, 1) - timedelta(days=1)
    start = end - timedelta(days=args.days - 1) if args.days else (end.replace(day=1) - timedelta(days=30 * (args.months - 1))).replace(day=1)
    spot = set(arch.list_symbols('spot'))
    if args.symbols:
        ids = [s.strip() for s in args.symbols.split(',') if s.strip()]
    else:
        vols = []
        for s in arch.list_symbols('futures'):
            if not s.endswith('USDT') or '_' in s or 'SETTLED' in s or not _spot_pair(s[:-4], spot):
                continue
            try:
                d = arch.klines_ohlc('futures', s, '1d', start, end)
            except Exception:
                continue
            if len(d) >= 20:
                vols.append((float(d[:, 5].mean()), s))
        ids = [s for _, s in sorted(vols, reverse=True)[:args.coins]]
    coins = []
    for fid in ids:
        base = fid[:-4]
        coins.append((f"{base}/USDT:USDT", fid, _spot_pair(base, spot)))
    # groups of --group coins share one SignalBook (crowd / unit limits hold within a group): RAM ~100 MB per coin
    k, n = (map(int, args.shard.split('/')) if args.shard else (0, 1))
    for g in range(0, len(coins), args.group):
        if (g // args.group) % n != k:
            continue
        out = os.path.join(args.out, f"group_{g // args.group:02d}")
        if os.path.exists(os.path.join(out, 'cards.parquet')):
            print(f"{out}: done before, skipped")
            continue
        part = coins[g:g + args.group]
        n_cards, n_entries = run(part, start, end, out, args.rate)
        print(f"replay {start} .. {end}: {[c[1] for c in part]}: {n_cards} cards, {n_entries} entries / vetoes -> {out}",
              flush=True)


if __name__ == '__main__':
    main()
