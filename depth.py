"""
Order book metrics for hot symbols. Two sources:
- the Binance <sym>@depth20@500ms stream: the top 20 levels, live (spread, walls near price);
- a REST snapshot of 500 levels per hot symbol every ~30s (weight 10) (DataFetcher._deep_books_loop): on coins with a small tick
  the top 20 levels span far less than +-0.5%, so band depth / imbalance and "sweep ate the book" use the deeper of the
  two books (measured live: KITE top-20 held $4k of the $31k within 0.5%).
Partial-book streams only push when the book changes: a quiet book is not a stale one, so staleness is judged by
`stale_sec` (60s) rather than by the last update.

Walls are unreliable (spoofing: large orders pulled within seconds), so a level only counts as a wall after it has
stood `wall_min_age_sec`; depth is used as context and to size sweeps against visible liquidity, never as a
trigger on its own.

Heatmap: every snapshot is also bucketed by price (heat_bucket_pct of price, the grid fixed per coin) and kept for
~2h (`heat_snapshots`): the page draws it behind the chart, and a bucket that held heat_band_multiple x the
snapshot's median bucket in >= heat_band_presence of the last heat_band_window_sec is a liquidity band - resting size
that stayed, a level source of its own ('book'). Only hot coins have books (<= depth.max_symbols).
"""
import statistics
import time
from array import array
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from config import CONFIG


class BookState:
    __slots__ = ('bids', 'asks', 'ts_ms', 'walls', 'deep_bids', 'deep_asks', 'deep_ts', 'heat', 'heat_step',
                 'bands', 'bands_ts')

    def __init__(self):
        self.bids: List[Tuple[float, float]] = []
        self.asks: List[Tuple[float, float]] = []
        self.ts_ms = 0
        # REST snapshot (100 levels) and its epoch seconds
        self.deep_bids: List[Tuple[float, float]] = []
        self.deep_asks: List[Tuple[float, float]] = []
        self.deep_ts = 0.0
        # (side, price) -> first seen epoch seconds
        self.walls: Dict[Tuple[int, float], float] = {}
        # Heatmap per snapshot: (epoch seconds, mid, first bucket index, USD per bucket: + bids / - asks) on a
        # fixed price grid of heat_step, +-heat_range_pct around the mid
        self.heat: Deque[Tuple[float, float, int, array]] = deque(maxlen=CONFIG.depth.heat_snapshots)
        self.heat_step = 0.0
        # Liquidity bands of the last snapshot: [(price, side +1 bid / -1 ask, USD)], and when they were computed
        self.bands: List[Tuple[float, int, float]] = []
        self.bands_ts = 0.0


class DepthBook:
    def __init__(self):
        self.books: Dict[str, BookState] = {}

    def update(self, symbol: str, bids: List[List[str]], asks: List[List[str]], ts_ms: int, now: Optional[float] = None):
        now = now or time.time()
        book = self.books.get(symbol)
        if book is None:
            book = self.books[symbol] = BookState()
        book.bids = [(float(p), float(q)) for p, q in bids]
        book.asks = [(float(p), float(q)) for p, q in asks]
        book.ts_ms = ts_ms
        notionals = [p * q for p, q in book.bids + book.asks]
        if not notionals:
            return
        median = statistics.median(notionals)
        threshold = CONFIG.depth.wall_multiple * median
        current = {(1, p) for p, q in book.bids if p * q >= threshold} | {(-1, p) for p, q in book.asks if p * q >= threshold}
        book.walls = {w: book.walls.get(w, now) for w in current}

    def drop(self, symbol: str):
        """
        The coin left the hot set: its live book goes; its heatmap history stays (the chart still shows where
        liquidity rested) until it is older than the heatmap window, then the whole state goes.
        """
        book = self.books.get(symbol)
        if book is None:
            return
        book.bids, book.asks, book.walls, book.bands = [], [], {}, []
        if not book.heat or time.time() - book.heat[-1][0] > CONFIG.depth.heat_snapshots * CONFIG.depth.deep_interval_sec:
            self.books.pop(symbol, None)

    def forget(self, symbol: str):
        self.books.pop(symbol, None)

    def active(self) -> List[str]:
        """Coins with a live book stream (hot): the ones the 500-level snapshots are taken for."""
        return [s for s, b in self.books.items() if b.bids or b.asks]

    def set_deep(self, symbol: str, bids: List[List[str]], asks: List[List[str]], now: Optional[float] = None):
        book = self.books.get(symbol)
        if book is None:
            book = self.books[symbol] = BookState()
        book.deep_bids = [(float(p), float(q)) for p, q in bids]
        book.deep_asks = [(float(p), float(q)) for p, q in asks]
        book.deep_ts = now or time.time()
        self._record_heat(book)

    @staticmethod
    def _record_heat(book: BookState):
        cfg = CONFIG.depth
        if not book.deep_bids or not book.deep_asks:
            return
        mid = (book.deep_bids[0][0] + book.deep_asks[0][0]) / 2
        # The grid is fixed per coin so snapshots line up; a move of > 20% re-bases it (old snapshots no longer fit)
        if not book.heat_step or abs(mid / (book.heat_step / cfg.heat_bucket_pct) - 1) > 0.2:
            book.heat_step = mid * cfg.heat_bucket_pct
            book.heat.clear()
        step = book.heat_step
        k0 = int(mid * (1 - cfg.heat_range_pct) // step)
        n = int(mid * (1 + cfg.heat_range_pct) // step) - k0 + 1
        values = array('d', bytes(8 * n))
        for p, q in book.deep_bids:
            k = int(p // step) - k0
            if 0 <= k < n:
                values[k] += p * q
        for p, q in book.deep_asks:
            k = int(p // step) - k0
            if 0 <= k < n:
                values[k] -= p * q      # asks negative: the side survives the aggregation
        book.heat.append((book.deep_ts, mid, k0, values))
        book.bands = DepthBook._bands(book)
        book.bands_ts = book.deep_ts

    @staticmethod
    def _bands(book: BookState) -> List[Tuple[float, int, float]]:
        """Buckets that held heat_band_multiple x the median bucket in >= heat_band_presence of the recent snapshots."""
        cfg = CONFIG.depth
        if not book.heat:
            return []
        cutoff = book.heat[-1][0] - cfg.heat_band_window_sec
        recent = [h for h in book.heat if h[0] >= cutoff]
        if len(recent) < cfg.heat_band_min_snapshots:
            return []
        present: Dict[int, int] = {}
        total: Dict[int, float] = {}
        for _, _, k0, values in recent:
            sizes = [abs(v) for v in values if v]
            if not sizes:
                continue
            threshold = cfg.heat_band_multiple * statistics.median(sizes)
            for i, v in enumerate(values):
                if v and abs(v) >= threshold:
                    k = k0 + i
                    present[k] = present.get(k, 0) + 1
                    total[k] = total.get(k, 0.0) + v
        mid = recent[-1][1]
        need = cfg.heat_band_presence * len(recent)
        bands = [((k + 0.5) * book.heat_step, 1 if total[k] > 0 else -1, abs(total[k]) / n)
                 for k, n in present.items() if n >= need]
        # A bid band below the price, an ask band above it (a band price already crossed is being eaten, not resting)
        bands = [b for b in bands if (b[1] > 0 and b[0] < mid) or (b[1] < 0 and b[0] > mid)]
        out: List[Tuple[float, int, float]] = []
        for side in (1, -1):
            same = sorted((b for b in bands if b[1] == side), key=lambda b: -b[2])
            out += same[:cfg.heat_band_max_per_side]
        return out

    def liquidity_bands(self, symbol: str, now: Optional[float] = None) -> List[Tuple[float, int, float]]:
        """Persistent liquidity bands of a hot coin: [(price, side +1 bid / -1 ask, average USD)]; [] when stale."""
        book = self.books.get(symbol)
        if book is None or not book.bands:
            return []
        if (now or time.time()) - book.bands_ts > CONFIG.depth.deep_max_age_sec:
            return []
        return list(book.bands)

    def bands_version(self, symbol: str) -> float:
        """Changes when the coin's liquidity bands were recomputed (plan cache key)."""
        book = self.books.get(symbol)
        return book.bands_ts if book is not None else 0.0

    def heatmap(self, symbol: str) -> Optional[Dict]:
        """The coin's heatmap for the page: grid step, and per snapshot [epoch ms, [[price, USD +bid / -ask], ...]]."""
        book = self.books.get(symbol)
        if book is None or not book.heat:
            return None
        step = book.heat_step
        return {'step': step,
                'snapshots': [[int(ts * 1000), [[(k0 + i + 0.5) * step, round(v)] for i, v in enumerate(values) if v]]
                              for ts, _, k0, values in book.heat]}

    @staticmethod
    def _side_depth(levels: List[Tuple[float, float]], deep: List[Tuple[float, float]], inside) -> float:
        """USD within the band from whichever book reaches further (the live top 20 or the 500-level snapshot)."""
        live = sum(p * q for p, q in levels if inside(p))
        snap = sum(p * q for p, q in deep if inside(p))
        return max(live, snap)

    def _deep_fresh(self, book: BookState, now: float) -> bool:
        return now - book.deep_ts <= CONFIG.depth.deep_max_age_sec

    def metrics(self, symbol: str, now: Optional[float] = None) -> Dict[str, float]:
        """Depth within the configured bands (USD per side), imbalance, and the nearest persistent walls."""
        book = self.books.get(symbol)
        if book is None or not book.bids or not book.asks:
            return {}
        now = now or time.time()
        if now * 1000 - book.ts_ms > CONFIG.depth.stale_sec * 1000:
            return {}  # stale book (stream gap)
        mid = (book.bids[0][0] + book.asks[0][0]) / 2
        out: Dict[str, float] = {'mid': mid, 'spread_bps': (book.asks[0][0] - book.bids[0][0]) / mid * 1e4}
        deep = self._deep_fresh(book, now)
        out['deep'] = 1.0 if deep else 0.0
        for band in CONFIG.depth.band_pcts:
            bid = self._side_depth(book.bids, book.deep_bids if deep else [], lambda p: p >= mid * (1 - band))
            ask = self._side_depth(book.asks, book.deep_asks if deep else [], lambda p: p <= mid * (1 + band))
            tag = f"{band * 100:g}".replace('.', '_')
            out[f'bid_usd_{tag}'] = bid
            out[f'ask_usd_{tag}'] = ask
            out[f'imbalance_{tag}'] = (bid - ask) / (bid + ask) if bid + ask else 0.0
        min_age = CONFIG.depth.wall_min_age_sec
        persistent = [(side, price) for (side, price), since in book.walls.items() if now - since >= min_age]
        bid_walls = sorted((p for s, p in persistent if s > 0), reverse=True)
        ask_walls = sorted(p for s, p in persistent if s < 0)
        out['bid_wall'] = bid_walls[0] if bid_walls else 0.0
        out['ask_wall'] = ask_walls[0] if ask_walls else 0.0
        return out

    def sweep_vs_depth(self, symbol: str, usd: float, side: int, band: float = 0.005) -> Optional[float]:
        """A taker sweep's size relative to the visible liquidity it hits within `band` (> 1 = it ate the book)."""
        book = self.books.get(symbol)
        if book is None or not book.bids or not book.asks:
            return None
        mid = (book.bids[0][0] + book.asks[0][0]) / 2
        deep = self._deep_fresh(book, time.time())
        if side > 0:
            depth = self._side_depth(book.asks, book.deep_asks if deep else [], lambda p: p <= mid * (1 + band))
        else:
            depth = self._side_depth(book.bids, book.deep_bids if deep else [], lambda p: p >= mid * (1 - band))
        return usd / depth if depth else None
