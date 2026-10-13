"""
Order books of the hot symbols, built the way Binance documents a local book ("How to manage a local order book
correctly"): the <sym>@depth@500ms diff stream, buffered until a 1000-level REST snapshot arrives, events with
u < lastUpdateId dropped, the first applied one spanning lastUpdateId, then every event's `pu` must equal the
previous `u` (else the book is re-synced from a new snapshot). Each event carries absolute quantities: 0 removes a
level. Within a minute of streaming the book reaches far beyond the 1000 levels of the snapshot (any level that
changes is sent): 2026-10-05 the 500-level snapshots of the old design covered BTC only +-0.07% (less than one 0.1%
heat bucket) and ETH +-0.2%.

COVERAGE (eng-80): the REST snapshot holds 1000 levels per side (BTC ~+-0.07%); beyond it the local book knows only
the levels that CHANGED since the sync - a large order that just rests far from the price never appears, which is
exactly what walls / bands look for. So heat snapshots, walls and bands use only the price range the last snapshot
covered (`cov_lo` .. `cov_hi`), and a book whose mid left that range is re-synced (at most every 5 minutes)
from a fresh snapshot (Binance's guidance: keep the book to the depth you actually hold).

Every decrease of a level is split into FILLED (taker trades at that price on that side, from the aggTrade stream,
within ATTRIBUTION_MS) and PULLED (cancelled): liquidity that disappears without trades is the spoofing signature
(~31% of large crypto orders could spoof, arXiv 2504.15908); liquidity that is traded into and stays / refills is
absorption. Additions are counted as ADDED. Per heat bucket and minute: [added, pulled, filled] of each side.

Heatmap (as Bookmap draws it): a snapshot of the whole local book within +-heat_range_pct every heat_snapshot_sec,
bucketed by heat_bucket_pct of price on a grid fixed per coin. Walls: single levels >= wall_multiple x the median
level notional within +-wall_range_pct that stood wall_min_age_sec (book depth refills within 5-10s after a trade -
arXiv 1602.00731 - so a 10s-old order said little). Liquidity bands: heat buckets that held heat_band_multiple x the
snapshot's median bucket in >= heat_band_presence of the snapshots of heat_band_window_sec AND were not mostly
pulled (pulled USD over the window < the band's average resting USD, or fills >= half of the pulls).

What the book is used for is decided elsewhere and measured: depth is context, sweep sizing and the slippage of an
entry; bands / walls are not support or resistance by themselves (no study shows resting depth holds price on an
hours horizon; order-flow imbalance explains price over seconds - Cont, Kukanov & Stoikov 2014).
"""
import heapq
import statistics
import time
from array import array
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from config import CONFIG

ATTRIBUTION_MS = 1500          # a trade and the book decrease it caused arrive on different sockets
FLOW_MINUTES = 60
ADDED, PULLED, FILLED = 0, 1, 2


class BookState:
    """One coin's local book and everything derived from it."""

    __slots__ = ('bids', 'asks', 'last_u', 'synced', 'buffer', 'ts_ms', 'recv', 'resyncs', 'executed', 'flow',
                 'heat', 'heat_step', 'heat_ts', 'walls', 'bands', 'bands_ts', 'deep_bids', 'deep_asks', 'deep_ts',
                 'snapshot_wanted', 'pending', 'cov_lo', 'cov_hi', 'cov_ts')

    def __init__(self):
        self.bids: Dict[float, float] = {}
        self.asks: Dict[float, float] = {}
        self.last_u = 0
        self.synced = False
        self.snapshot_wanted = True
        self.pending: Optional[Dict] = None     # a REST snapshot newer than every buffered event (applied once caught up)
        self.buffer: List[Dict] = []
        self.ts_ms = 0                 # exchange time of the last applied event
        self.recv = 0.0                # epoch seconds of the last applied event
        self.resyncs = 0
        # (side +1 bid / -1 ask, price) -> [quantity executed, last trade ms]
        self.executed: Dict[Tuple[int, float], List[float]] = {}
        # minute ms -> {bucket: [bid added, pulled, filled, ask added, pulled, filled]} (USD)
        self.flow: Dict[int, Dict[int, List[float]]] = {}
        # (epoch seconds, mid, first bucket index, USD per bucket: + bids / - asks)
        self.heat: Deque[Tuple[float, float, int, array]] = deque(maxlen=CONFIG.depth.heat_snapshots)
        self.heat_step = 0.0
        self.heat_ts = 0.0
        self.walls: Dict[Tuple[int, float], float] = {}
        self.bands: List[Tuple[float, int, float]] = []
        self.bands_ts = 0.0
        # the book within +-heat_range_pct at the last heat snapshot (data recorder: depth files)
        self.deep_bids: List[Tuple[float, float]] = []
        self.deep_asks: List[Tuple[float, float]] = []
        self.deep_ts = 0.0
        # the price range the last REST snapshot covered (levels outside it are known only once they change)
        self.cov_lo = 0.0
        self.cov_hi = 0.0
        self.cov_ts = 0.0

    # best prices are recomputed on demand: dict sizes are a few thousand levels
    def best(self) -> Tuple[Optional[float], Optional[float]]:
        return (max(self.bids) if self.bids else None, min(self.asks) if self.asks else None)


class DepthBook:
    def __init__(self):
        self.books: Dict[str, BookState] = {}

    # ------------------------------------------------------------------ lifecycle

    def start(self, symbol: str):
        """A hot coin's diff stream was subscribed: buffer its events until the snapshot arrives."""
        if symbol not in self.books:
            self.books[symbol] = BookState()

    def drop(self, symbol: str):
        """The stream was unsubscribed: the book stops (heat history and bands are kept for the page)."""
        book = self.books.get(symbol)
        if book is None:
            return
        book.bids, book.asks, book.buffer, book.executed, book.walls = {}, {}, [], {}, {}
        book.synced, book.snapshot_wanted, book.bands = False, True, []

    def forget(self, symbol: str):
        self.books.pop(symbol, None)

    def active(self) -> List[str]:
        """Coins with a synced live book."""
        return [s for s, b in self.books.items() if b.synced]

    def wanting_snapshot(self) -> List[str]:
        """Coins whose stream runs but whose book needs a (new) REST snapshot."""
        return [s for s, b in self.books.items() if b.snapshot_wanted and b.buffer]

    # ------------------------------------------------------------------ stream

    def on_diff(self, symbol: str, event: Dict, now: Optional[float] = None):
        book = self.books.get(symbol)
        if book is None:
            return
        if not book.synced:
            book.buffer.append(event)
            if len(book.buffer) > 2000:           # the snapshot is late: keep the newest
                del book.buffer[:1000]
            if book.pending is not None and int(event.get('u', 0)) >= int(book.pending.get('lastUpdateId') or 0):
                self.set_snapshot(symbol, book.pending, now)
            return
        if event.get('pu') != book.last_u:
            self._resync(book)
            book.buffer.append(event)
            return
        self._apply(book, event, now or time.time())

    def set_snapshot(self, symbol: str, snapshot: Dict, now: Optional[float] = None):
        """REST /fapi/v1/depth (limit 1000): the book from lastUpdateId, then the buffered events."""
        book = self.books.get(symbol)
        if book is None or book.synced:          # a second request that returned after the book synced
            return
        last_id = int(snapshot.get('lastUpdateId') or 0)
        events = [e for e in book.buffer if int(e.get('u', 0)) >= last_id]
        if not events:
            # the snapshot is newer than every buffered event (REST ran ahead of the stream): keep it until the
            # stream catches up (on_diff)
            book.pending = snapshot
            return
        book.pending = None
        if int(events[0].get('U', 0)) > last_id:
            # the buffer starts after the snapshot (events between them were missed): a new snapshot
            book.snapshot_wanted = True
            return
        book.bids = {float(p): float(q) for p, q in snapshot.get('bids') or [] if float(q) > 0}
        book.asks = {float(p): float(q) for p, q in snapshot.get('asks') or [] if float(q) > 0}
        book.cov_lo = min(book.bids) if book.bids else 0.0
        book.cov_hi = max(book.asks) if book.asks else 0.0
        book.cov_ts = now or time.time()
        book.last_u = int(events[0].get('pu', 0))      # the first event is applied unconditionally
        book.synced, book.snapshot_wanted, book.buffer = True, False, []
        now = now or time.time()
        for e in events:
            if int(e.get('pu', -1)) != book.last_u and e is not events[0]:
                self._resync(book)
                return
            self._apply(book, e, now, count=e is not events[0])

    def on_trade(self, symbol: str, ts_ms: int, price: float, qty: float, taker_side: int):
        """aggTrade: a taker SELL executes against the bids at `price`, a taker BUY against the asks."""
        book = self.books.get(symbol)
        if book is None or not book.synced:
            return
        key = (1 if taker_side < 0 else -1, price)
        cell = book.executed.get(key)
        if cell is None:
            book.executed[key] = [qty, ts_ms]
        else:
            cell[0] += qty
            cell[1] = ts_ms

    @staticmethod
    def _resync(book: BookState):
        book.synced, book.snapshot_wanted, book.buffer, book.pending = False, True, [], None
        book.resyncs += 1

    def _apply(self, book: BookState, event: Dict, now: float, count: bool = True):
        ts = int(event.get('E') or event.get('T') or now * 1000)
        minute = ts // 60_000 * 60_000
        step = book.heat_step
        cells = book.flow.setdefault(minute, {}) if count and step else None
        for side, rows, levels in ((1, event.get('b') or [], book.bids), (-1, event.get('a') or [], book.asks)):
            off = 0 if side > 0 else 3
            for p, q in rows:
                price, qty = float(p), float(q)
                old = levels.get(price, 0.0)
                if qty > 0:
                    levels[price] = qty
                elif old:
                    del levels[price]
                if cells is None or qty == old:
                    continue
                cell = cells.setdefault(int(price // step), [0.0] * 6)
                if qty > old:
                    cell[off + ADDED] += (qty - old) * price
                    continue
                drop = old - qty
                ex = book.executed.get((side, price))
                filled = 0.0
                if ex is not None and ts - ex[1] <= ATTRIBUTION_MS:
                    filled = min(drop, ex[0])
                    ex[0] -= filled
                cell[off + FILLED] += filled * price
                cell[off + PULLED] += (drop - filled) * price
        book.last_u = int(event.get('u', book.last_u))
        book.ts_ms, book.recv = ts, now
        if count and len(book.flow) > FLOW_MINUTES:
            for m in sorted(book.flow)[:-FLOW_MINUTES]:
                del book.flow[m]
        if now - book.heat_ts >= CONFIG.depth.heat_snapshot_sec:
            book.heat_ts = now
            # executed quantities older than the attribution window can no longer explain a decrease
            book.executed = {k: v for k, v in book.executed.items() if ts - v[1] <= ATTRIBUTION_MS}
            self._snapshot(book, now)

    # ------------------------------------------------------------------ snapshots: heat, walls, bands

    def _snapshot(self, book: BookState, now: float):
        cfg = CONFIG.depth
        best_bid, best_ask = book.best()
        if best_bid is None or best_ask is None:
            return
        mid = (best_bid + best_ask) / 2
        # the grid is fixed per coin so snapshots line up; a move of > 20% re-bases it (old snapshots no longer fit)
        if not book.heat_step or abs(mid / (book.heat_step / cfg.heat_bucket_pct) - 1) > 0.2:
            book.heat_step = mid * cfg.heat_bucket_pct
            book.heat.clear()
            book.flow.clear()
        step = book.heat_step
        if book.cov_hi > book.cov_lo and not (book.cov_lo <= mid <= book.cov_hi) and now - book.cov_ts >= 300:
            # the price left the range the snapshot covered: a fresh snapshot re-centres it (at most every 5 min:
            # a 1000-level snapshot weighs 20)
            self._resync(book)
            return
        lo, hi = mid * (1 - cfg.heat_range_pct), mid * (1 + cfg.heat_range_pct)
        if book.cov_hi > book.cov_lo:
            lo, hi = max(lo, book.cov_lo), min(hi, book.cov_hi)
        k0 = int(lo // step)
        n = int(hi // step) - k0 + 1
        values = array('d', bytes(8 * n))
        # eng-84: both bounds on both sides. A bid above `hi` (the price ran past the snapshot's coverage, cov_hi) raised
        # IndexError on the whole stream handler ("array index out of range", 7x 12.10); an ask below `lo` gave a
        # NEGATIVE index that Python wraps silently - asks written into the top buckets of the heatmap
        bids = [(p, q) for p, q in book.bids.items() if lo <= p <= hi]
        asks = [(p, q) for p, q in book.asks.items() if lo <= p <= hi]
        for p, q in bids:
            values[int(p // step) - k0] += p * q
        for p, q in asks:
            values[int(p // step) - k0] -= p * q            # asks negative: the side survives the aggregation
        book.heat.append((now, mid, k0, values))
        book.deep_bids = sorted(bids, reverse=True)
        book.deep_asks = sorted(asks)
        book.deep_ts = now
        # walls: single levels near the price, persistent
        w_lo, w_hi = max(lo, mid * (1 - cfg.wall_range_pct)), min(hi, mid * (1 + cfg.wall_range_pct))
        near = [p * q for p, q in bids if p >= w_lo] + [p * q for p, q in asks if p <= w_hi]
        current = set()
        if near:
            threshold = cfg.wall_multiple * statistics.median(near)
            current = {(1, p) for p, q in bids if p >= w_lo and p * q >= threshold} | \
                      {(-1, p) for p, q in asks if p <= w_hi and p * q >= threshold}
        book.walls = {w: book.walls.get(w, now) for w in current}
        book.bands = self._bands(book)
        book.bands_ts = now

    @staticmethod
    def _bands(book: BookState) -> List[Tuple[float, int, float]]:
        cfg = CONFIG.depth
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
        since_minute = int(cutoff * 1000) // 60_000 * 60_000
        out_bands = []
        for k, n in present.items():
            if n < need:
                continue
            side = 1 if total[k] > 0 else -1
            price, avg = (k + 0.5) * book.heat_step, abs(total[k]) / n
            # a bid band below the price, an ask band above it (a band price already crossed is being eaten)
            if (side > 0 and price >= mid) or (side < 0 and price <= mid):
                continue
            out_bands.append((price, side, avg, k))
        # Market makers cancel and re-quote all the time (BTC 2026-10-05: $305M pulled vs $0.6M filled within 1% in
        # 5 minutes), so pulling as such says nothing: a band is spoof-like when ITS pull turnover (USD pulled over
        # the window / its average resting USD) is > 3x the median turnover of the buckets on its side
        def turnover(k, side, rest):
            off = 0 if side > 0 else 3
            pulled = sum(c[k][off + PULLED] for m, c in book.flow.items() if m >= since_minute and k in c)
            return pulled / rest if rest else 0.0
        last = recent[-1]
        typical = {}
        for side in (1, -1):
            rows = [(last[2] + i, abs(v)) for i, v in enumerate(last[3]) if v and (v > 0) == (side > 0)]
            values = sorted(turnover(k, side, rest) for k, rest in rows)
            typical[side] = values[len(values) // 2] if values else 0.0
        out_bands = [(p, s, a) for p, s, a, k in out_bands
                     if not typical[s] or turnover(k, s, a) <= 3 * typical[s]]
        out: List[Tuple[float, int, float]] = []
        for side in (1, -1):
            same = sorted((b for b in out_bands if b[1] == side), key=lambda b: -b[2])
            out += same[:cfg.heat_band_max_per_side]
        return out

    # ------------------------------------------------------------------ readers

    def _fresh(self, book: Optional[BookState], now: float) -> bool:
        return book is not None and book.synced and now - book.recv <= CONFIG.depth.stale_sec

    def top(self, symbol: str, n: int = 20) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
        """The best n levels per side (iceberg tracking reads the near book as the old depth20 stream gave it)."""
        book = self.books.get(symbol)
        if book is None or not book.synced:
            return [], []
        bids = heapq.nlargest(n, book.bids.items())
        asks = heapq.nsmallest(n, book.asks.items())
        return bids, asks

    def liquidity_bands(self, symbol: str, now: Optional[float] = None) -> List[Tuple[float, int, float]]:
        """Persistent, not-mostly-pulled liquidity bands: [(price, side +1 bid / -1 ask, average USD)]."""
        book = self.books.get(symbol)
        if not self._fresh(book, now or time.time()) or not book.bands:
            return []
        return list(book.bands)

    def bands_version(self, symbol: str) -> float:
        book = self.books.get(symbol)
        return book.bands_ts if book is not None else 0.0

    def heatmap(self, symbol: str) -> Optional[Dict]:
        """The coin's heatmap for the page: grid step, per snapshot [epoch ms, [[price, USD +bid / -ask], ...]], and per
        minute the pulled / filled USD per bucket [[minute ms, [[price, bid pulled, bid filled, ask pulled, ask filled]]]]."""
        book = self.books.get(symbol)
        if book is None or not book.heat:
            return None
        step = book.heat_step
        flow = [[m, [[(k + 0.5) * step, round(c[PULLED]), round(c[FILLED]), round(c[3 + PULLED]), round(c[3 + FILLED])]
                     for k, c in cells.items() if c[PULLED] or c[FILLED] or c[3 + PULLED] or c[3 + FILLED]]]
                for m, cells in sorted(book.flow.items())]
        return {'step': step, 'cov': [book.cov_lo, book.cov_hi],
                'snapshots': [[int(ts * 1000), [[(k0 + i + 0.5) * step, round(v)] for i, v in enumerate(values) if v]]
                              for ts, _, k0, values in book.heat],
                'flow': flow}

    def metrics(self, symbol: str, now: Optional[float] = None) -> Dict[str, float]:
        """Spread, depth within the configured bands (USD per side), imbalance, the nearest persistent walls, and
        the last 5 minutes' pulled / filled USD within 1% per side."""
        now = now or time.time()
        book = self.books.get(symbol)
        if not self._fresh(book, now):
            return {}
        best_bid, best_ask = book.best()
        if best_bid is None or best_ask is None:
            return {}
        mid = (best_bid + best_ask) / 2
        out: Dict[str, float] = {'mid': mid, 'spread_bps': (best_ask - best_bid) / mid * 1e4, 'deep': 1.0,
                                 'levels': float(len(book.bids) + len(book.asks)), 'resyncs': float(book.resyncs)}
        for band in CONFIG.depth.band_pcts:
            bid = sum(p * q for p, q in book.bids.items() if p >= mid * (1 - band))
            ask = sum(p * q for p, q in book.asks.items() if p <= mid * (1 + band))
            tag = f"{band * 100:g}".replace('.', '_')
            out[f'bid_usd_{tag}'] = bid
            out[f'ask_usd_{tag}'] = ask
            out[f'imbalance_{tag}'] = (bid - ask) / (bid + ask) if bid + ask else 0.0
        min_age = CONFIG.depth.wall_min_age_sec
        persistent = [(side, price) for (side, price), since in book.walls.items() if now - since >= min_age]
        bid_walls = sorted((p for s, p in persistent if s > 0 and p in book.bids), reverse=True)
        ask_walls = sorted(p for s, p in persistent if s < 0 and p in book.asks)
        out['bid_wall'] = bid_walls[0] if bid_walls else 0.0
        out['ask_wall'] = ask_walls[0] if ask_walls else 0.0
        if book.heat_step:
            since = int(now * 1000) // 60_000 * 60_000 - 4 * 60_000
            k_lo, k_hi = int(mid * 0.99 // book.heat_step), int(mid * 1.01 // book.heat_step)
            sums = [0.0] * 6
            for m, cells in book.flow.items():
                if m >= since:
                    for k, c in cells.items():
                        if k_lo <= k <= k_hi:
                            for i in range(6):
                                sums[i] += c[i]
            out.update(bid_pulled_5m=sums[PULLED], bid_filled_5m=sums[FILLED],
                       ask_pulled_5m=sums[3 + PULLED], ask_filled_5m=sums[3 + FILLED])
        return out

    def sweep_vs_depth(self, symbol: str, usd: float, side: int, band: float = 0.005) -> Optional[float]:
        """A taker sweep's size relative to the visible liquidity it hits within `band` (> 1 = it ate the book)."""
        book = self.books.get(symbol)
        if not self._fresh(book, time.time()):
            return None
        best_bid, best_ask = book.best()
        if best_bid is None or best_ask is None:
            return None
        mid = (best_bid + best_ask) / 2
        if side > 0:
            depth = sum(p * q for p, q in book.asks.items() if p <= mid * (1 + band))
        else:
            depth = sum(p * q for p, q in book.bids.items() if p >= mid * (1 - band))
        return usd / depth if depth else None

    def slippage_bps(self, symbol: str, usd: float, side: int) -> Optional[float]:
        """Average price impact (bps from the touch) of a market order of `usd` walking the live book; None without
        a fresh book or when the book within reach is thinner than the order."""
        book = self.books.get(symbol)
        if not self._fresh(book, time.time()) or usd <= 0:
            return None
        levels = heapq.nsmallest(400, book.asks.items()) if side > 0 else heapq.nlargest(400, book.bids.items())
        if not levels:
            return None
        touch, left, cost, qty = levels[0][0], usd, 0.0, 0.0
        for p, q in levels:
            take = min(left, p * q)
            cost += take
            qty += take / p
            left -= take
            if left <= 0:
                return abs(cost / qty / touch - 1) * 1e4
        return None
