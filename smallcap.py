"""
eng-158: live 1m watch of the small caps outside the universe for the start of pumps and dumps.

The universe holds ~70 data-complete coins; the biggest pumps / dumps happen in the coins outside it (no spot pair,
fresh listings, < 2 other venues). Until now those were read once an hour on 1h candles and journaled only
(Scanner.wide_watch_loop), so a -45% dump (KAT, WET 24.10) was seen an hour late and never traded.

Here every such perpetual (wide_min_volume, the wide watch's list) gets its Binance futures 1m kline stream on ONE
dynamic connection (no restart of the universe's streams when the list changes - eng-102). Per coin only a ring of
the last `smallcap_minutes` final minutes is kept (tuples, ~7 MB for 150 coins). On each final minute a cheap gate
(|15m move| >= pump_start_min_pct) runs first; only then the coin's 15m volatility and its OI change are fetched by
REST and PUMP START / DUMP START (strategies.pump) decide. A hit becomes an ordinary setup signal for the SignalBook:
the card, the journal and the demo trade follow the same rules as in the universe. The coin's minutes / price feed
the card through Scanner._minute_candles / _price_of while it is not in the universe.

Inputs that differ from the universe (no spot pair, no order books here):
- spot taker flow -> the FUTURES taker flow of the last 5 minutes (sig 'flow_src' = 'futures': journaled);
- rvol_1m -> the last minute's quote volume / (24h quote volume / 1440), the universe's own definition;
- the plan's ATR -> the 1h ATR(14) of the wide watch's 1h candles / 2 (a 15m ATR by the square-root rule).
"""
import asyncio
import logging
import time
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from config import CONFIG

logger = logging.getLogger(__name__)
MINUTE_MS = 60_000


class _Sink:
    """BinanceStream's sink: only the 1m klines of the watched coins."""

    def __init__(self, owner: 'SmallCapWatch'):
        self.owner = owner

    def on_binance(self, market_type: str, stream: str, data, recv_ms: float) -> None:
        if data.get('e') == 'kline':
            self.owner.on_kline(data)


class SmallCapWatch:
    def __init__(self, fetcher):
        self.fetcher = fetcher
        self.rings: Dict[str, Deque[tuple]] = {}
        self.forming: Dict[str, tuple] = {}
        self.by_id: Dict[str, str] = {}             # 'KATUSDT' -> 'KAT/USDT:USDT'
        self.qv24: Dict[str, float] = {}
        self.h1: Dict[str, List] = {}               # the wide watch's closed 1h candles
        self.pending: List[Tuple[str, Dict]] = []   # signals for the next scan
        self._fired: set = set()
        from strategies.pd_features import ActivationLog
        self._activation = ActivationLog()          # eng-159: lead time (base: the 24h mean minute - no 15m history here)
        self._stream = None
        self._seeding: set = set()
        self.detections = 0
        self.checks = 0

    # ------------------------------------------------------------------ feed

    @property
    def symbols(self) -> List[str]:
        return list(self.by_id.values())

    def has(self, symbol: str) -> bool:
        return symbol in self.rings

    def minutes(self, symbol: str) -> List[List[float]]:
        ring = self.rings.get(symbol)
        return [list(c) for c in ring] if ring else []

    def price(self, symbol: str) -> Optional[float]:
        f = self.forming.get(symbol)
        ring = self.rings.get(symbol)
        now = time.time() * 1000
        if f is not None and now - f[8] <= 60_000:
            return f[4]
        if ring and now - (ring[-1][0] + MINUTE_MS) <= 120_000:
            return ring[-1][4]
        return None

    def on_kline(self, data) -> None:
        sym = self.by_id.get(data.get('s'))
        k = data.get('k') or {}
        if sym is None or not k:
            return
        try:
            row = (int(k['t']), float(k['o']), float(k['h']), float(k['l']), float(k['c']), float(k['q']),
                   float(k['Q']), float(k['v']))
        except (KeyError, TypeError, ValueError):
            return
        if not k.get('x'):
            self.forming[sym] = row + (time.time() * 1000,)
            return
        ring = self.rings.setdefault(sym, deque(maxlen=CONFIG.strategies.smallcap_minutes))
        if ring and ring[-1][0] >= row[0]:
            if ring[-1][0] == row[0]:
                ring[-1] = row
            return
        ring.append(row)
        self.forming.pop(sym, None)
        qv = self.qv24.get(sym)
        self._activation.update(sym, ring, qv / 1440 if qv else None)
        if len(ring) >= 120:
            asyncio.get_event_loop().create_task(self._check(sym))

    # ------------------------------------------------------------------ the coin list (from the wide watch)

    COINS_PATH = 'smallcap_coins.json'

    async def restore(self, universe) -> None:
        """eng-161: attach the last known small-cap list at start-up (was: ~10 min later, after the wide watch's first
        hourly scan) - the rings are seeded by REST at once, the 1h candles load on a coin's first check."""
        import json
        try:
            with open(self.COINS_PATH) as fh:
                saved = json.load(fh)
        except (OSError, ValueError):
            return
        wanted = [(s, b, float(q)) for s, b, q in saved if s not in universe]
        if wanted:
            await self.set_coins(wanted, self.h1)
            logger.info(f"Small caps: {len(wanted)} coins restored at start-up")

    async def set_coins(self, wanted: List[Tuple[str, str, float]], h1: Dict[str, List]) -> None:
        """wanted: (unified symbol, Binance id, 24h quote volume) of the perpetuals outside the universe."""
        from venues import BinanceStream
        import json
        for sym, rows in (h1 or {}).items():
            self.h1[sym] = rows
        try:
            from storage import atomic_write
        except ImportError:
            atomic_write = None
        try:
            payload = json.dumps([[sym, bid, qv] for sym, bid, qv in wanted])
            if atomic_write:
                atomic_write(self.COINS_PATH, payload.encode() if isinstance(payload, str) else payload)
            else:
                with open(self.COINS_PATH, 'w') as fh:
                    fh.write(payload)
        except Exception as e:
            logger.debug(f"small caps: list not saved: {e!r}")
        new = {bid: sym for sym, bid, _ in wanted}
        self.qv24 = {sym: qv for sym, _, qv in wanted}
        for sym in set(self.rings) - set(new.values()):
            self.rings.pop(sym, None)
            self.forming.pop(sym, None)
        self.by_id = new
        if self._stream is None:
            self._stream = BinanceStream(_Sink(self), self.fetcher.symbol_map, 'futures', [], 'Binance small caps 1m')
            await self._stream.start(dynamic=True)
        await self._stream.set_dynamic([f"{bid.lower()}@kline_1m" for bid in new])
        for sym, bid, _ in wanted:
            if sym not in self.rings and sym not in self._seeding:
                self._seeding.add(sym)
                asyncio.get_event_loop().create_task(self._seed(sym, bid))

    async def _seed(self, sym: str, bid: str) -> None:
        try:
            k = await self.fetcher._rest_call(self.fetcher.futures_exchange, 'fapiPublicGetKlines',
                                              {'symbol': bid, 'interval': '1m', 'limit': CONFIG.strategies.smallcap_minutes},
                                              priority=2, weight=2)
            now = time.time() * 1000
            rows = [(int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[7]), float(x[10]),
                     float(x[5])) for x in k or [] if int(x[6]) < now]
            ring = self.rings.setdefault(sym, deque(maxlen=CONFIG.strategies.smallcap_minutes))
            have = {r[0] for r in ring}
            merged = sorted([r for r in rows if r[0] not in have] + list(ring))
            ring.clear()
            ring.extend(merged[-CONFIG.strategies.smallcap_minutes:])
        except Exception as e:
            logger.debug(f"small caps: seed {sym} failed: {e!r}")
        finally:
            self._seeding.discard(sym)

    # ------------------------------------------------------------------ detection

    def _atr_15m(self, sym: str) -> Optional[float]:
        h1 = self.h1.get(sym) or []
        if len(h1) < 15:
            return None
        trs = [max(b[2] - b[3], abs(b[2] - a[4]), abs(b[3] - a[4])) for a, b in zip(h1[-15:-1], h1[-14:])]
        return sum(trs) / len(trs) / 2 if trs else None

    async def _check(self, sym: str) -> None:
        cfg = CONFIG.strategies
        ring = self.rings.get(sym)
        if not ring:
            return
        last = ring[-1]
        base = next((c for c in reversed(ring) if c[0] == last[0] - 15 * MINUTE_MS), None)
        if base is None or not base[4]:
            return
        move = last[4] / base[4] - 1
        if abs(move) < cfg.pump_start_min_pct:
            return                                           # the cheap gate: nothing moves for most minutes
        key = (sym, int(base[0]) // 3_600_000, 1 if move > 0 else -1)
        if key in self._fired:
            return
        self.checks += 1
        try:
            from strategies.pump import dump_start, pump_start
            bid = next(b for b, s in self.by_id.items() if s == sym)
            k15 = await self.fetcher._rest_call(self.fetcher.futures_exchange, 'fapiPublicGetKlines',
                                                {'symbol': bid, 'interval': '15m', 'limit': 98}, priority=1, weight=1)
            closes = [float(x[4]) for x in k15 or []][:-1]
            m15 = [[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[7])] for x in (k15 or [])[:-1]]
            from strategies import pd_features as pdf
            base1 = pdf.volume_base_1m(m15)
            rets = [b / a - 1 for a, b in zip(closes, closes[1:]) if a]
            vol = (sum(r * r for r in rets) / len(rets)) ** 0.5 if len(rets) > 20 else None
            oi = await self.fetcher._rest_call(self.fetcher.futures_exchange, 'fapiDataGetOpenInterestHist',
                                               {'symbol': bid, 'period': '5m', 'limit': 2}, priority=1, weight=0)
            oi_vals = [float(x.get('sumOpenInterest') or 0) for x in oi or []]
            oi_change = oi_vals[-1] / oi_vals[0] - 1 if len(oi_vals) == 2 and oi_vals[0] else 0.0
            minutes = [list(c) for c in ring]
            now_ms = int(last[0]) + MINUTE_MS
            flow = sum(2 * c[6] - c[5] for c in minutes if c[0] + MINUTE_MS > now_ms - 300_000)
            avg_minute = (self.qv24.get(sym) or 0) / 1440
            rvol = last[5] / avg_minute if avg_minute else 0.0
            m = {'rvol_1m': rvol, 'oi_change_5m': oi_change, 'spot_cvd_5m': flow}
            if base1:
                m['rvol_1m_med'] = last[5] / base1       # eng-159: the 24h median minute
            h1 = self.h1.get(sym) or []
            if len(h1) < 25:
                # eng-161: restored at start-up before the wide watch fetched it - the 1h history on the first check
                k1 = await self.fetcher._rest_call(self.fetcher.futures_exchange, 'fapiPublicGetKlines',
                                                   {'symbol': bid, 'interval': '1h', 'limit': 200}, priority=1, weight=2)
                now = time.time() * 1000
                h1 = [[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[7]), float(x[10])]
                      for x in k1 or [] if int(x[6]) < now]
                self.h1[sym] = h1
            found = (pump_start if move > 0 else dump_start)(minutes, m, vol, now_ms, h1)
            rvol = m.get('rvol_1m_med') or rvol
            why = found['setup'] if found else 'no setup: ' + self._why_not(minutes, m, vol, now_ms, h1, move)
            logger.info(f"Small caps: {sym} {move:+.1%} in 15m - RVOL {rvol:.1f}, OI 5m {oi_change:+.2%}, futures flow "
                        f"{flow:+,.0f}, vol15 {vol or 0:.3%} -> {why}")
            if not found:
                return
            self._fired.add(key)
            atr = self._atr_15m(sym)
            if not atr:
                logger.info(f"Small caps: {sym} {found['setup']} skipped - no 1h history for the ATR")
                return
            self.detections += 1
            found.update(pdf.features(minutes, m15, found['direction']))
            found['pd_activation_lead_s'] = self._activation.lead_s(sym, found['direction'], int(found['event_ts']))
            sig = dict(found, is_setup=True, is_structured=False, is_tier_0_anomaly=False, active_phases=[],
                       long_score=0, short_score=0, alert_type='LONG' if found['direction'] > 0 else 'SHORT',
                       atr_15m=atr, volume_24h=self.qv24.get(sym), smallcap=True, flow_src='futures',
                       strategy='pump')
            self.pending.append((sym, sig))
        except Exception as e:
            logger.warning(f"Small caps: check {sym} failed: {e!r}")

    @staticmethod
    def _why_not(minutes, m: Dict, vol, now_ms: int, h1, move: float) -> str:
        """eng-161: the first PUMP / DUMP START gate that failed (same order as strategies.pump.pump_start)."""
        cfg = CONFIG.strategies
        d = 1 if move > 0 else -1
        if not vol:
            return 'no 15m volatility (history)'
        need = max(cfg.pump_start_min_pct, cfg.pump_start_z * vol)
        if abs(move) < need:
            return f"move {abs(move):.1%} < {need:.1%} ({cfg.pump_start_z:g} x vol15)"
        rv = m.get('rvol_1m_med') or m.get('rvol_1m') or 0
        if rv < cfg.pump_start_rvol:
            return f"RVOL {rv:.1f} < {cfg.pump_start_rvol:g}"
        if (m.get('oi_change_5m') or 0) <= 0:
            return 'OI 5m not rising'
        if d * (m.get('spot_cvd_5m') or 0) <= 0:
            return 'taker flow against the move'
        cut = minutes[-15][0]
        ext = [c[2 if d > 0 else 3] for c in h1 if now_ms - 86_400_000 - MINUTE_MS <= c[0] < minutes[0][0]]
        ext += [c[2 if d > 0 else 3] for c in minutes if c[0] >= now_ms - 86_400_000 - MINUTE_MS and c[0] < cut]
        last = minutes[-1][2 if d > 0 else 3]
        if ext and d * (last - (max(ext) if d > 0 else min(ext))) <= 0:
            return f"not a fresh 24h {'high' if d > 0 else 'low'} ({max(ext) if d > 0 else min(ext):.6g})"
        return 'other (ATR / dedup)'

    def drain(self) -> List[Tuple[str, Dict]]:
        out, self.pending = self.pending, []
        return out

    def health(self) -> str:
        return f"small caps {len(self.rings)} coins, {self.checks} checks, {self.detections} setups"
