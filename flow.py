"""
Order flow state shared by every venue, kept as fixed-size numpy ring buffers instead of per-trade Python objects.

- FlowStore: per venue, per symbol, per epoch second: taker buy USD, taker sell USD, long / short liquidation USD
  and the trade count. Writing is O(1) in the hot path; window sums (60s .. 1h) are computed for all symbols at once.
- SweepTracker: merges prints of one taker (same side, same trade time or within sweep_merge_ms) into one sweep
  before sizing, so an order that walks several price levels counts as one big order (the Aggr technique).
- WhaleBook: per-symbol log-histogram of sweep sizes (decayed hourly) -> whale size = rolling percentile, floored
  by liquidity tier; keeps whale sweeps and notable sweeps for algo-cluster (TWAP-like) detection.
- Footprint: bid x ask volume per price bucket per minute for the few symbols waiting for an entry.
"""
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from config import CONFIG

# Field order in FlowStore arrays
BUY, SELL, LIQ_LONG, LIQ_SHORT = range(4)
N_FIELDS = 4
FUTURES_VENUES = ('binance', 'bybit', 'okx', 'bitget', 'hyperliquid')
SPOT_VENUES = ('coinbase', 'bybit_spot')


class VenueFlow:
    """
    Ring buffer of one venue: data[second % H, field, symbol_row]. Second-major: advancing one second zeroes ~5 KB
    of contiguous memory and a window sum reads one contiguous block. The symbol-major layout it replaced touched
    ~1600 pages per venue every second (one per row and field), kept the whole buffer hot and stalled the loop
    whenever the machine had paged it out.
    """

    def __init__(self, venue: str, history_sec: int, capacity: int):
        self.venue = venue
        self.H = history_sec
        self.data = np.zeros((history_sec, N_FIELDS, capacity), dtype=np.float32)
        self.counts = np.zeros((history_sec, capacity), dtype=np.int32)
        self.last_sec = 0
        self.messages = 0
        self.last_event_ms = 0
        self.last_recv_ms = 0
        self.lag_ms = 0.0

    def grow(self, capacity: int):
        extra = capacity - self.data.shape[2]
        if extra > 0:
            self.data = np.concatenate([self.data, np.zeros((self.H, N_FIELDS, extra), np.float32)], axis=2)
            self.counts = np.concatenate([self.counts, np.zeros((self.H, extra), np.int32)], axis=1)

    def clear_row(self, row: int):
        self.data[:, :, row] = 0
        self.counts[:, row] = 0

    def advance(self, sec: int):
        """Move the head to `sec`, zeroing the slots of the seconds skipped since the last write."""
        if sec <= self.last_sec:
            return
        if self.last_sec == 0 or sec - self.last_sec >= self.H:
            self.data[:] = 0
            self.counts[:] = 0
        else:
            a, n = (self.last_sec + 1) % self.H, sec - self.last_sec
            for lo, hi in ((a, min(a + n, self.H)), (0, max(0, a + n - self.H))):
                if hi > lo:
                    self.data[lo:hi] = 0
                    self.counts[lo:hi] = 0
        self.last_sec = sec

    def add(self, row: int, sec: int, field: int, usd: float, count: int = 0):
        if sec > self.last_sec:
            self.advance(sec)
        elif sec <= self.last_sec - self.H:
            return  # older than the buffer
        slot = sec % self.H
        self.data[slot, field, row] += usd
        if count:
            self.counts[slot, row] += count

    def _span_sum(self, field: int, start_sec: int, end_sec: int) -> np.ndarray:
        """
        Per-row sum over seconds [start_sec, end_sec) as at most two contiguous slices of the ring (views, no copy).
        Fancy indexing copied the whole window first: ~90 MB per refresh of the 1h window over all venues, which
        blocked the event loop for about a second.
        """
        a, n = start_sec % self.H, end_sec - start_sec
        if a + n <= self.H:
            return self.data[a:a + n, field].sum(axis=0, dtype=np.float64)
        return (self.data[a:, field].sum(axis=0, dtype=np.float64) +
                self.data[:a + n - self.H, field].sum(axis=0, dtype=np.float64))

    def window(self, field: int, seconds: int, now_sec: int) -> np.ndarray:
        """Per-row sum over the last `seconds` seconds up to now_sec (inclusive)."""
        self.advance(now_sec)
        seconds = min(seconds, self.H)
        return self._span_sum(field, now_sec - seconds + 1, now_sec + 1)

    def row_range_sum(self, field: int, row: int, start_sec: int, end_sec: int, now_sec: int) -> float:
        """One row's sum over [start_sec, end_sec): the whole-matrix range_sum then one row cost ~1s on the loop per
        call (the whale forced-flow check ran it on every sweep)."""
        # read-only: no advance() (it rewrites slots - the whole buffer of a quiet venue - on a lookup); seconds after
        # the last write hold data from one ring period ago, so the window ends there
        start_sec = max(start_sec, self.last_sec - self.H + 1)
        end_sec = min(end_sec, self.last_sec + 1)
        if not self.last_sec or end_sec <= start_sec or row >= self.data.shape[2]:
            return 0.0
        a, n = start_sec % self.H, end_sec - start_sec
        if a + n <= self.H:
            return float(self.data[a:a + n, field, row].sum(dtype=np.float64))
        return float(self.data[a:, field, row].sum(dtype=np.float64) + self.data[:a + n - self.H, field, row].sum(dtype=np.float64))

    def range_sum(self, field: int, start_sec: int, end_sec: int, now_sec: int) -> np.ndarray:
        """Per-row sum over [start_sec, end_sec) (seconds still inside the buffer only)."""
        self.advance(now_sec)
        start_sec = max(start_sec, now_sec - self.H + 1)
        end_sec = min(end_sec, now_sec + 1)
        if end_sec <= start_sec:
            return np.zeros(self.data.shape[2])
        return self._span_sum(field, start_sec, end_sec)


class FlowStore:
    def __init__(self, venues: Iterable[str] = FUTURES_VENUES + SPOT_VENUES, capacity: int = 320):
        cfg = CONFIG.venues
        long_history = {'binance', 'bybit', 'okx'}
        self.capacity = capacity
        self._hour_cache = (0, np.zeros(0))
        self.rows: Dict[str, int] = {}
        self._free: List[int] = []
        self.venues: Dict[str, VenueFlow] = {
            v: VenueFlow(v, cfg.flow_history_sec if v in long_history else cfg.flow_history_short_sec, capacity)
            for v in venues
        }

    # ------------------------------------------------------------------ symbols

    def register(self, symbols: Iterable[str]):
        for symbol in symbols:
            if symbol in self.rows:
                continue
            if self._free:
                row = self._free.pop()
                for flow in self.venues.values():
                    flow.clear_row(row)
            else:
                row = len(self.rows) + len(self._free)
                if row >= self.capacity:
                    self.capacity = max(self.capacity * 2, row + 1)
                    for flow in self.venues.values():
                        flow.grow(self.capacity)
            self.rows[symbol] = row

    def unregister(self, symbol: str):
        row = self.rows.pop(symbol, None)
        if row is not None:
            self._free.append(row)

    # ------------------------------------------------------------------ writes (hot path)

    def seed_minute(self, venue: str, symbol: str, minute_ms: int, buy_usd: float, sell_usd: float, trades: int):
        """A closed minute from REST (a kline's taker buy / total quote volume) at its middle second: the 5m windows
        are valid right after a start instead of 5 minutes later. Only minutes before the streams started."""
        row = self.rows.get(symbol)
        flow = self.venues.get(venue)
        if row is None or flow is None:
            return
        sec = int(minute_ms // 1000) + 30
        flow.add(row, sec, BUY, buy_usd, trades // 2)
        flow.add(row, sec, SELL, sell_usd, trades - trades // 2)

    def trade(self, venue: str, symbol: str, ts_ms: int, usd: float, side: int, recv_ms: Optional[float] = None):
        row = self.rows.get(symbol)
        flow = self.venues.get(venue)
        if row is None or flow is None:
            return
        flow.add(row, int(ts_ms // 1000), BUY if side > 0 else SELL, usd, 1)
        self._mark(flow, ts_ms, recv_ms)

    def liquidation(self, venue: str, symbol: str, ts_ms: int, usd: float, side_liquidated: int,
                    recv_ms: Optional[float] = None):
        """side_liquidated: +1 a long position was liquidated (a forced sell), -1 a short (a forced buy)."""
        row = self.rows.get(symbol)
        flow = self.venues.get(venue)
        if row is None or flow is None:
            return
        flow.add(row, int(ts_ms // 1000), LIQ_LONG if side_liquidated > 0 else LIQ_SHORT, usd)
        self._mark(flow, ts_ms, recv_ms)

    @staticmethod
    def _mark(flow: VenueFlow, ts_ms: float, recv_ms: Optional[float]):
        flow.messages += 1
        recv_ms = recv_ms if recv_ms is not None else time.time() * 1000
        if ts_ms > flow.last_event_ms:
            flow.last_event_ms = ts_ms
            flow.last_recv_ms = recv_ms
            # Smoothed receive lag (exchange event time -> our clock)
            flow.lag_ms = 0.9 * flow.lag_ms + 0.1 * (recv_ms - ts_ms) if flow.lag_ms else recv_ms - ts_ms

    # ------------------------------------------------------------------ reads

    def window(self, venues: Sequence[str], field: int, seconds: int, now_sec: Optional[int] = None) -> np.ndarray:
        now_sec = int(now_sec if now_sec is not None else time.time())
        total = np.zeros(self.capacity)
        for v in venues:
            flow = self.venues.get(v)
            if flow is not None:
                part = flow.window(field, seconds, now_sec)
                total[:part.shape[0]] += part
        return total

    def net(self, venues: Sequence[str], seconds: int, now_sec: Optional[int] = None) -> np.ndarray:
        return self.window(venues, BUY, seconds, now_sec) - self.window(venues, SELL, seconds, now_sec)

    def symbol_net(self, venues: Sequence[str], symbol: str, seconds: int, now_sec: Optional[int] = None) -> float:
        row = self.rows.get(symbol)
        if row is None:
            return 0.0
        return float(self.net(venues, seconds, now_sec)[row])

    def symbol_range(self, symbol: str, field: int, start_sec: int, end_sec: int, now_sec: Optional[int] = None) -> float:
        """One field summed over [start_sec, end_sec) across every venue for one symbol (seconds still buffered)."""
        row = self.rows.get(symbol)
        if row is None:
            return 0.0
        now_sec = int(now_sec if now_sec is not None else time.time())
        total = 0.0
        for flow in self.venues.values():
            total += flow.row_range_sum(field, row, start_sec, end_sec, now_sec)
        return total

    def candle_net(self, venues: Sequence[str], start_sec: int, end_sec: int, now_sec: Optional[int] = None) -> np.ndarray:
        now_sec = int(now_sec if now_sec is not None else time.time())
        total = np.zeros(self.capacity)
        for v in venues:
            flow = self.venues.get(v)
            if flow is None:
                continue
            part = flow.range_sum(BUY, start_sec, end_sec, now_sec) - flow.range_sum(SELL, start_sec, end_sec, now_sec)
            total[:part.shape[0]] += part
        return total

    def snapshot(self, now_sec: Optional[int] = None) -> Dict[str, Dict[str, float]]:
        """
        Per symbol, the live order-flow metrics used by Tier-0, scoring and the dashboard:
        cvd_<w> (Binance futures), agg_cvd_<w> (all futures venues), agg_spot_cvd_5m (spot venues),
        liq_long_5m / liq_short_5m (all venues, USD), venue shares of the 5m gross flow.
        """
        now_sec = int(now_sec if now_sec is not None else time.time())
        liq_window = CONFIG.liquidations.window_sec
        futures = [v for v in FUTURES_VENUES if v in self.venues]
        spot = [v for v in SPOT_VENUES if v in self.venues]
        # The 1h window barely moves in 2s and is the expensive one (3600 slots x all rows x venues): refresh / 30s
        if now_sec - self._hour_cache[0] >= 30 or self._hour_cache[1].shape[0] != self.capacity:
            self._hour_cache = (now_sec, self.net(futures, 3600, now_sec))
        # Each futures venue's 5m net once: the aggregate, Binance's own and the venue shares all come from it (they
        # were summed three times over, a third of the Tier-0 pass)
        per_venue_net = {v: self.net((v,), 300, now_sec) for v in futures}
        zeros = np.zeros(self.capacity)
        cols = {
            'cvd_60s': self.net(('binance',), 60, now_sec),
            'cvd_5m': per_venue_net.get('binance', zeros),
            'agg_cvd_5m': sum(per_venue_net.values()) if per_venue_net else zeros,
            'agg_cvd_1h': self._hour_cache[1],
            'agg_spot_cvd_5m': self.net(spot, 300, now_sec),
            'liq_long_5m': self.window(list(self.venues), LIQ_LONG, liq_window, now_sec),
            'liq_short_5m': self.window(list(self.venues), LIQ_SHORT, liq_window, now_sec),
        }
        gross = sum(np.abs(a) for a in per_venue_net.values()) if per_venue_net else zeros
        out: Dict[str, Dict[str, float]] = {}
        for symbol, row in self.rows.items():
            metrics = {name: float(values[row]) for name, values in cols.items()}
            if gross[row] > 0:
                top_venue, top_net = max(((v, a[row]) for v, a in per_venue_net.items()), key=lambda x: abs(x[1]))
                metrics['top_venue'] = top_venue
                metrics['top_venue_share'] = float(abs(top_net) / gross[row])
                metrics['top_venue_net'] = float(top_net)
            else:
                metrics['top_venue'], metrics['top_venue_share'], metrics['top_venue_net'] = '', 0.0, 0.0
            metrics['venues_active'] = int(sum(1 for a in per_venue_net.values() if a[row] != 0))
            out[symbol] = metrics
        return out

    def micro_features(self, symbol: str, minutes: Sequence[Sequence[float]], now_sec: Optional[int] = None,
                       window: int = 3600, buckets: int = 50) -> Dict[str, Optional[float]]:
        """
        eng-59 journal features (context only, no rule uses them):
        - vpin: Easley, Lopez de Prado & O'Hara (2012) volume-synchronized probability of informed trading - the last
          hour's futures taker volume of all venues cut into `buckets` equal-volume buckets, mean |buy - sell| / bucket
          volume (exact taker sides, so no bulk classification);
        - vol_entropy: Shannon entropy of the hour's per-minute volume / ln(60): 1 = spread evenly, low = bursts;
        - lead_venue / lead_corr: the futures venue whose per-minute net taker flow best predicts the NEXT minute's
          Binance return over the hour (correlation; who moves first). `minutes`: final futures 1m candles.
        """
        out: Dict[str, Optional[float]] = {'vpin': None, 'vol_entropy': None, 'lead_venue': None, 'lead_corr': None}
        row = self.rows.get(symbol)
        if row is None:
            return out
        now_sec = int(now_sec or time.time())
        start = now_sec - window
        buy = np.zeros(window)
        sell = np.zeros(window)
        per_venue: Dict[str, np.ndarray] = {}
        for venue in FUTURES_VENUES:
            flow = self.venues.get(venue)
            if flow is None or not flow.last_sec or row >= flow.data.shape[2]:
                continue
            lo, hi = max(start, flow.last_sec - flow.H + 1), min(now_sec, flow.last_sec + 1)
            if hi <= lo:
                continue
            idx = np.arange(lo, hi) % flow.H
            b = flow.data[idx, BUY, row].astype(np.float64)
            sl = flow.data[idx, SELL, row].astype(np.float64)
            buy[lo - start:hi - start] += b
            sell[lo - start:hi - start] += sl
            per_venue[venue] = np.zeros(window)
            per_venue[venue][lo - start:hi - start] = b - sl
        vol = buy + sell
        total = vol.sum()
        if total <= 0:
            return out
        size = total / buckets
        cum = np.cumsum(vol)
        edges = np.searchsorted(cum, np.arange(1, buckets) * size)
        imb = []
        prev = 0
        for e in list(edges) + [window]:
            v = vol[prev:e + 1].sum()
            if v > 0:
                imb.append(abs(buy[prev:e + 1].sum() - sell[prev:e + 1].sum()) / v)
            prev = e + 1
        out['vpin'] = float(np.mean(imb)) if imb else None
        per_min = vol[:window // 60 * 60].reshape(-1, 60).sum(axis=1)
        p = per_min[per_min > 0] / per_min.sum()
        out['vol_entropy'] = float(-(p * np.log(p)).sum() / math.log(len(per_min))) if len(p) > 1 else 0.0
        closes = {int(m[0] // 1000): float(m[4]) for m in minutes if m[0] // 1000 >= start - 60}
        mins = [start + 60 * k for k in range(window // 60)]
        rets = []
        for t in mins:
            a, b = closes.get(t), closes.get(t + 60)
            rets.append(b / a - 1 if a and b else np.nan)
        rets = np.array(rets)
        best = None
        for venue, net in per_venue.items():
            f = net[:window // 60 * 60].reshape(-1, 60).sum(axis=1)
            x, y = f[:-1], rets[1:]
            ok = ~np.isnan(y) & (x != 0)
            if ok.sum() < 20 or x[ok].std() == 0 or y[ok].std() == 0:
                continue
            c = float(np.corrcoef(x[ok], y[ok])[0, 1])
            if best is None or c > best[1]:
                best = (venue, c)
        if best:
            out['lead_venue'], out['lead_corr'] = best
        return out

    def venue_status(self, now_ms: Optional[float] = None) -> Dict[str, Dict[str, float]]:
        now_ms = now_ms if now_ms is not None else time.time() * 1000
        return {v: {'messages': f.messages, 'lag_ms': f.lag_ms,
                    'silent_sec': (now_ms - f.last_recv_ms) / 1000 if f.last_recv_ms else None}
                for v, f in self.venues.items()}


# ---------------------------------------------------------------------- sweeps / whales

@dataclass
class Sweep:
    venue: str
    symbol: str
    t_first: int
    t_last: int
    side: int          # +1 taker buy, -1 taker sell
    usd: float
    px_first: float
    px_last: float
    prints: int
    levels: int

    @property
    def signed(self) -> float:
        return self.side * self.usd


class SweepTracker:
    """Per venue and symbol, the sweep being built; emits finished sweeps to `on_sweep`."""

    def __init__(self, on_sweep: Callable[[Sweep], None]):
        self.on_sweep = on_sweep
        self.pending: Dict[Tuple[str, str], Sweep] = {}
        self.merge_ms = CONFIG.sweeps.sweep_merge_ms

    def add(self, venue: str, symbol: str, ts_ms: int, price: float, usd: float, side: int):
        key = (venue, symbol)
        sweep = self.pending.get(key)
        if sweep is not None and sweep.side == side and (ts_ms == sweep.t_last or ts_ms - sweep.t_first <= self.merge_ms):
            sweep.usd += usd
            sweep.prints += 1
            if price != sweep.px_last:
                sweep.levels += 1
            sweep.t_last, sweep.px_last = max(sweep.t_last, ts_ms), price
            return
        if sweep is not None:
            self.on_sweep(sweep)
        self.pending[key] = Sweep(venue, symbol, ts_ms, ts_ms, side, usd, price, price, 1, 1)

    def flush(self, now_ms: float):
        """Emit sweeps whose merge window has passed (no newer print arrived to close them)."""
        stale = [k for k, s in self.pending.items() if now_ms - s.t_last > self.merge_ms]
        for key in stale:
            self.on_sweep(self.pending.pop(key))


N_BINS = 64
BINS_PER_DECADE = 8
MIN_LOG = 2.0  # $100


def _bin(usd: float) -> int:
    if usd <= 0:
        return 0
    return min(N_BINS - 1, max(0, int((math.log10(usd) - MIN_LOG) * BINS_PER_DECADE)))


def _bin_upper(b: int) -> float:
    return 10 ** (MIN_LOG + (b + 1) / BINS_PER_DECADE)


class WhaleBook:
    def __init__(self):
        self.hist: Dict[str, np.ndarray] = defaultdict(lambda: np.zeros(N_BINS))
        self.whales: Dict[str, deque] = defaultdict(lambda: deque(maxlen=2000))
        self.notable: Dict[str, deque] = defaultdict(lambda: deque(maxlen=500))
        self.floor_usd: Dict[str, float] = {}
        self._threshold_cache: Dict[str, Tuple[float, float]] = {}
        self._last_decay = time.time()
        self.sweeps_seen = 0

    # ------------------------------------------------------------------ sizing

    def set_ranks(self, symbols_by_volume: Sequence[str]):
        """Liquidity-tier floors from the 24h-volume rank (index 0 = most liquid)."""
        cfg = CONFIG.sweeps
        for rank, symbol in enumerate(symbols_by_volume):
            if rank < cfg.floor_top_n_1:
                self.floor_usd[symbol] = cfg.floor_top_usd_1
            elif rank < cfg.floor_top_n_2:
                self.floor_usd[symbol] = cfg.floor_top_usd_2
            else:
                self.floor_usd[symbol] = cfg.floor_rest_usd
        self._threshold_cache.clear()

    def _percentile(self, symbol: str, p: float) -> Optional[float]:
        hist = self.hist.get(symbol)
        if hist is None:
            return None
        total = hist.sum()
        if total < CONFIG.sweeps.min_samples:
            return None
        b = int(np.searchsorted(np.cumsum(hist), p * total))
        return _bin_upper(min(b, N_BINS - 1))

    def thresholds(self, symbol: str) -> Tuple[float, Optional[float]]:
        """(whale size, notable size or None while unknown) in USD for the symbol."""
        cached = self._threshold_cache.get(symbol)
        if cached is not None:
            return cached
        cfg = CONFIG.sweeps
        # eng-57: the coin's own p99.5 sweep IS the whale size once its distribution is known; the liquidity-tier USD
        # floors (set by hand, no source) only stand in during the cold start (< min_samples sweeps)
        whale = self._percentile(symbol, cfg.percentile) or self.floor_usd.get(symbol, cfg.floor_rest_usd)
        # Unknown until the coin's sweep-size distribution is known: no cluster detection before that (a fixed
        # guess made five small prints a minute look like an algo on quiet coins)
        notable = self._percentile(symbol, cfg.cluster_percentile)
        result = (whale, min(notable, whale) if notable else None)
        self._threshold_cache[symbol] = result
        return result

    def whale_size(self, symbol: str) -> float:
        return self.thresholds(symbol)[0]

    # ------------------------------------------------------------------ input

    def add(self, sweep: Sweep):
        self.sweeps_seen += 1
        self.hist[sweep.symbol][_bin(sweep.usd)] += 1
        whale, notable = self.thresholds(sweep.symbol)
        record = (sweep.t_last, sweep.signed, sweep.venue, sweep.px_first, sweep.px_last, sweep.levels)
        if sweep.usd >= whale:
            self.whales[sweep.symbol].append(record)
        if notable and sweep.usd >= notable:
            self.notable[sweep.symbol].append((sweep.t_last, sweep.signed))

    def maintain(self, now: Optional[float] = None):
        """Hourly decay of the size histograms; call from a periodic loop."""
        now = now or time.time()
        hours = (now - self._last_decay) / 3600
        if hours >= 1 / 12:  # decay in 5-minute steps
            factor = CONFIG.sweeps.hist_decay_per_hour ** hours
            for hist in self.hist.values():
                hist *= factor
            self._last_decay = now
            self._threshold_cache.clear()

    # ------------------------------------------------------------------ queries

    def flow(self, symbol: str, window_sec: int, now_ms: Optional[float] = None) -> Dict[str, float]:
        """Whale sweeps over the window: buy / sell USD, counts, largest, most levels eaten by one sweep."""
        now_ms = now_ms or time.time() * 1000
        cutoff = now_ms - window_sec * 1000
        buys, sells, levels = [], [], 0
        for ts, signed, _venue, _p0, _p1, lv in reversed(self.whales.get(symbol, ())):
            if ts < cutoff:
                break
            (buys if signed > 0 else sells).append(abs(signed))
            levels = max(levels, lv)
        return {'buy_usd': sum(buys), 'sell_usd': sum(sells), 'buys': len(buys), 'sells': len(sells),
                'largest': max(buys + sells, default=0.0), 'max_levels': levels}

    def net_units(self, symbol: str, window_sec: int, now_ms: Optional[float] = None) -> float:
        """Net whale flow over the window in units of the symbol's whale size (3.0 = three whales net buying)."""
        f = self.flow(symbol, window_sec, now_ms)
        size = self.whale_size(symbol)
        return (f['buy_usd'] - f['sell_usd']) / size if size else 0.0

    def cluster(self, symbol: str, now_ms: Optional[float] = None) -> int:
        """+1 / -1 when an algo cluster (many notable same-side sweeps summing to a whale) is running, else 0."""
        cfg = CONFIG.sweeps
        now_ms = now_ms or time.time() * 1000
        cutoff = now_ms - cfg.cluster_window_sec * 1000
        buys = sells = 0
        buy_usd = sell_usd = 0.0
        for ts, signed in reversed(self.notable.get(symbol, ())):
            if ts < cutoff:
                break
            if signed > 0:
                buys, buy_usd = buys + 1, buy_usd + signed
            else:
                sells, sell_usd = sells + 1, sell_usd - signed
        need = cfg.cluster_min_whales * self.whale_size(symbol)
        total = buys + sells
        if buys >= cfg.cluster_min_count and buy_usd >= need and buys >= cfg.cluster_side_share * total:
            return 1
        if sells >= cfg.cluster_min_count and sell_usd >= need and sells >= cfg.cluster_side_share * total:
            return -1
        return 0

    # ------------------------------------------------------------------ persistence

    def state(self) -> Dict[str, List[float]]:
        return {s: h.round(3).tolist() for s, h in self.hist.items() if h.sum() > 0}

    def load_state(self, state: Dict[str, List[float]]):
        for symbol, values in (state or {}).items():
            if len(values) == N_BINS:
                self.hist[symbol] = np.asarray(values, dtype=float)
        self._threshold_cache.clear()


# ---------------------------------------------------------------------- footprint

class Footprint:
    """Bid x ask USD per price bucket per minute, only for symbols explicitly enabled (cards waiting for an entry)."""

    KEEP_MINUTES = 30

    def __init__(self):
        self.bucket: Dict[str, float] = {}
        self.minutes: Dict[str, Dict[int, Dict[int, List[float]]]] = {}

    def enable(self, symbol: str, bucket_size: float):
        if bucket_size <= 0:
            return
        if symbol not in self.bucket:
            self.minutes[symbol] = {}
        self.bucket[symbol] = bucket_size

    def disable(self, symbol: str):
        self.bucket.pop(symbol, None)
        self.minutes.pop(symbol, None)

    def add(self, symbol: str, ts_ms: int, price: float, usd: float, side: int):
        size = self.bucket.get(symbol)
        if size is None:
            return
        minute = int(ts_ms // 60_000) * 60_000
        book = self.minutes[symbol]
        levels = book.get(minute)
        if levels is None:
            levels = book[minute] = {}
            for old in [m for m in book if m < minute - self.KEEP_MINUTES * 60_000]:
                del book[old]
        cell = levels.setdefault(int(price // size), [0.0, 0.0])
        cell[0 if side > 0 else 1] += usd

    def merged(self, symbol: str, since_ms: int, until_ms: Optional[int] = None) -> Dict[int, List[float]]:
        """Bucket -> [buy USD, sell USD] summed over the minutes in [since_ms, until_ms)."""
        out: Dict[int, List[float]] = {}
        for minute, levels in self.minutes.get(symbol, {}).items():
            if minute < since_ms or (until_ms is not None and minute >= until_ms):
                continue
            for level, (buy, sell) in levels.items():
                cell = out.setdefault(level, [0.0, 0.0])
                cell[0] += buy
                cell[1] += sell
        return out

    def stacked_imbalance(self, symbol: str, since_ms: int, direction: int, until_ms: Optional[int] = None) -> int:
        """
        Longest run of consecutive diagonal imbalances in the trade's direction: for longs, taker buys at a level
        >= imbalance_ratio x taker sells one bucket lower (initiative buying lifting offers); mirrored for shorts.
        """
        return stacked_imbalance(self.merged(symbol, since_ms, until_ms), direction)

    def finished_auction(self, symbol: str, since_ms: int, until_ms: Optional[int], direction: int,
                         share: float = 0.02) -> bool:
        """
        A finished auction at the extreme (footprint reading, ATAS / Market Profile: "a zero on the bid at the low"):
        at the window's lowest price (almost) no taker SOLD - the low was printed by buyers lifting offers, sellers
        were no longer hitting bids there: the sell auction ended. Mirrored at the highest price for shorts (no
        taker buys at the high). `share`: the limit of that side as a share of the price bucket's volume.
        """
        levels = self.merged(symbol, since_ms, until_ms)
        if len(levels) < 3:
            return False
        edge = min(levels) if direction > 0 else max(levels)
        buy, sell = levels[edge]
        total = buy + sell
        if total <= 0:
            return False
        late = sell if direction > 0 else buy        # the side that would have continued the auction
        return late <= share * total


def minute_atr_15m(minutes: Sequence[Sequence[float]], until_ms: int) -> Optional[float]:
    """A 15m ATR estimate from the last hour's closed 1m candles (mean 1m range x sqrt(15)) for coins without a zone
    card's ATR; None with fewer than 20 minutes."""
    closed = [c for c in minutes if c[0] + 60_000 <= until_ms][-60:]
    if len(closed) < 20:
        return None
    return math.sqrt(15) * sum(c[2] - c[3] for c in closed) / len(closed)


def absorption_in(minutes: Sequence[Sequence[float]], since_ms: int, until_ms: int, direction: int,
                  atr: float) -> bool:
    """
    Absorption against the trade in [since_ms, until_ms): a closed 1m candle whose taker delta is >= the
    absorption_percentile of the last hour's |delta|, AGAINST the trade (sellers for a long), while its range stayed
    <= absorption_max_move_atr x ATR: the aggressive side hit resting orders and could not move price.
    Candles are [open_time, open, high, low, close, quote_volume, taker_buy_quote].
    """
    cfg = CONFIG.orderflow
    closed = [c for c in minutes if c[0] + 60_000 <= until_ms]
    history = [abs(2 * c[6] - c[5]) for c in closed[-60:]]
    if len(history) < 20 or not atr:
        return False
    threshold = sorted(history)[min(len(history) - 1, int(cfg.absorption_percentile * len(history)))]
    for c in closed:
        if c[0] + 60_000 <= since_ms:
            continue
        delta = 2 * c[6] - c[5]
        if direction * delta < 0 and abs(delta) >= threshold and c[2] - c[3] <= cfg.absorption_max_move_atr * atr:
            return True
    return False


def stacked_imbalance(levels: Dict[int, List[float]], direction: int) -> int:
    ratio = CONFIG.orderflow.imbalance_ratio
    if not levels:
        return 0
    # Thin levels (a few prints) make any ratio: the initiative side must trade at least half an average level
    min_usd = 0.5 * sum(b + s for b, s in levels.values()) / len(levels)
    empty = [0.0, 0.0]
    best = run = 0
    for level in range(min(levels), max(levels) + 1):
        buy, sell = levels.get(level, empty)
        if direction > 0:
            opposite = levels.get(level - 1, empty)[1]
            hit = buy >= min_usd and buy >= ratio * opposite
        else:
            opposite = levels.get(level + 1, empty)[0]
            hit = sell >= min_usd and sell >= ratio * opposite
        run = run + 1 if hit else 0
        best = max(best, run)
    return best


# ---------------------------------------------------------------------- rush orders (eng-89)

class RushBook:
    """
    eng-89, "rush orders" (La Morgia et al., arXiv 2005.06610: pump detection on Binance within seconds): one taker
    market order that ate several price levels prints as several aggTrades with the SAME trade time and side. Counted
    per second per coin in a one-hour ring (Binance futures only: its aggTrade carries the match time T). Journaled as
    features and as RUSH rows - data collection, no trading.
    """
    RING = 3600

    def __init__(self):
        self.counts: Dict[str, np.ndarray] = {}    # symbol -> [RING, 2 sides] rush orders per second
        self.usd: Dict[str, np.ndarray] = {}
        self.secs: Dict[str, np.ndarray] = {}      # the second each ring slot holds (stale slots are zeroed lazily)
        self._open: Dict[str, list] = {}           # symbol -> [T, side, levels, usd, last price]
        self.started = time.time()                 # the z-score needs a full hour of history (0 before: no RUSH rows)

    def on_trade(self, symbol: str, ts_ms: int, side: int, usd: float, price: float):
        g = self._open.get(symbol)
        if g is not None and g[0] == ts_ms and g[1] == side:
            g[3] += usd
            if price != g[4]:
                g[2], g[4] = g[2] + 1, price
            return
        if g is not None:
            self._close(symbol, g)
        self._open[symbol] = [ts_ms, side, 1, usd, price]

    def _close(self, symbol: str, g: list):
        if g[2] < 2:
            return                                  # one level: an ordinary fill, not a sweep
        if symbol not in self.counts:
            self.counts[symbol] = np.zeros((self.RING, 2))
            self.usd[symbol] = np.zeros((self.RING, 2))
            self.secs[symbol] = np.full(self.RING, -1, dtype=np.int64)
        sec = int(g[0] // 1000)
        k = sec % self.RING
        if self.secs[symbol][k] != sec:
            self.counts[symbol][k] = 0
            self.usd[symbol][k] = 0
            self.secs[symbol][k] = sec
        j = 0 if g[1] > 0 else 1
        self.counts[symbol][k, j] += 1
        self.usd[symbol][k, j] += g[3]

    def stats(self, symbol: str, now_ms: float) -> Dict[str, float]:
        """Rush orders in the last 10 / 30 s (count, net buy - sell count, USD) and the 30 s count's z-score against
        the coin's own previous hour (120 buckets of 30 s, zeros included)."""
        g = self._open.get(symbol)
        if g is not None and now_ms - g[0] > 1000:
            self._close(symbol, g)
            self._open.pop(symbol, None)
        counts = self.counts.get(symbol)
        if counts is None:
            return {'rush_n_10s': 0.0, 'rush_n_30s': 0.0, 'rush_net_30s': 0.0, 'rush_usd_30s': 0.0, 'rush_z_30s': 0.0}
        now = int(now_ms // 1000)
        age = now - self.secs[symbol]
        valid = (age >= 0) & (age < self.RING)
        c = np.where(valid[:, None], counts, 0.0)
        u = np.where(valid[:, None], self.usd[symbol], 0.0)
        last10, last30 = valid & (age < 10), valid & (age < 30)
        n10 = float(c[last10].sum())
        n30 = float(c[last30].sum())
        net30 = float(c[last30, 0].sum() - c[last30, 1].sum())
        usd30 = float(u[last30].sum())
        base = np.zeros(self.RING // 30)
        hist = valid & (age >= 30)
        np.add.at(base, (age[hist] // 30).clip(0, self.RING // 30 - 1), c[hist].sum(axis=1))
        base = base[1:]
        z = (n30 - base.mean()) / max(base.std(), 0.5) if now_ms / 1000 - self.started >= self.RING else 0.0
        return {'rush_n_10s': n10, 'rush_n_30s': n30, 'rush_net_30s': net30, 'rush_usd_30s': usd30, 'rush_z_30s': float(z)}
