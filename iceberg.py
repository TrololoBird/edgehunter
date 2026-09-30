"""
Iceberg detection: how a whale really accumulates (resting limit orders refilled at one price), not the aggressive
market sweeps the old "whales" counted (measured x1.0: those were liquidations, stops and chasers).

For the hot coins with a live Binance book (depth20 @500ms): at one price level of one side, the volume EXECUTED
against it (aggTrades whose taker hit that side at that price) exceeds `multiple` x the largest size ever VISIBLE there
while the level held (no trade through it), and is at least `min_usd`. A bid iceberg = a hidden buyer absorbing sells
("whale buying"), an ask iceberg the hidden seller. Journaled as features (`iceberg_net_5m`: bid - ask iceberg USD over
5 minutes, `iceberg_n_5m`) and logged; measured before anything trades on it.
Sources: Bookmap's iceberg tracker, the usual definition (executed > displayed at a level that refills).
"""
import logging
import time
from collections import deque
from typing import Deque, Dict, Tuple

from config import CONFIG

logger = logging.getLogger(__name__)


class _Level:
    __slots__ = ('executed', 'visible', 'first_ms', 'last_ms', 'fired')

    def __init__(self, ts: int):
        self.executed = 0.0
        self.visible = 0.0
        self.first_ms = ts
        self.last_ms = ts
        self.fired = False


class IcebergDetector:
    def __init__(self):
        self.levels: Dict[str, Dict[Tuple[int, float], _Level]] = {}   # symbol -> (side +1 bid / -1 ask, price)
        self.events: Dict[str, Deque[Tuple[int, int, float, float]]] = {}   # symbol -> (ts, side, price, usd)

    def on_book(self, symbol: str, bids, asks, ts_ms: int):
        """Largest size seen at each price of the live book (USD)."""
        book = self.levels.setdefault(symbol, {})
        for side, rows in ((1, bids), (-1, asks)):
            for p, q in rows:
                price, size = float(p), float(q)
                lvl = book.get((side, price))
                if lvl is not None:
                    lvl.visible = max(lvl.visible, price * size)
                elif size > 0:
                    lvl = book[(side, price)] = _Level(ts_ms)
                    lvl.visible = price * size

    def on_trade(self, symbol: str, ts_ms: int, price: float, usd: float, taker_side: int):
        """A taker SELL hits the bid side at `price` (and breaks every bid above it), a taker BUY the asks."""
        cfg = CONFIG.iceberg
        side = 1 if taker_side < 0 else -1                        # the passive side the trade executed against
        book = self.levels.get(symbol)
        if not book:
            return
        # a trade THROUGH a level ends it (the hidden order was exhausted): bids above / asks below the price
        for key in [k for k in book if (k[0] > 0 and k[1] > price) or (k[0] < 0 and k[1] < price)]:
            del book[key]
        lvl = book.get((side, price))
        if lvl is None:
            return
        if ts_ms - lvl.last_ms > cfg.window_sec * 1000:
            lvl.executed, lvl.first_ms, lvl.fired = 0.0, ts_ms, False
        lvl.executed += usd
        lvl.last_ms = ts_ms
        if not lvl.fired and lvl.visible > 0 and lvl.executed >= cfg.min_usd and \
                lvl.executed >= cfg.multiple * lvl.visible:
            lvl.fired = True
            self.events.setdefault(symbol, deque(maxlen=200)).append((ts_ms, side, price, lvl.executed))
            logger.info(f"Iceberg {'BID' if side > 0 else 'ASK'} {symbol} @ {price:.6g}: ${lvl.executed:,.0f} "
                        f"executed vs ${lvl.visible:,.0f} ever shown ({(ts_ms - lvl.first_ms) / 1000:.0f}s)")

    def features(self, symbol: str, window_sec: int = 300, now_ms: float = None) -> Dict[str, float]:
        now_ms = now_ms or time.time() * 1000
        ev = [e for e in self.events.get(symbol, ()) if now_ms - e[0] <= window_sec * 1000]
        return {'iceberg_net_5m': sum(e[1] * e[3] for e in ev), 'iceberg_n_5m': float(len(ev))}

    def prune(self, now_ms: float = None):
        now_ms = now_ms or time.time() * 1000
        horizon = CONFIG.iceberg.window_sec * 1000 * 3
        for symbol, book in list(self.levels.items()):
            for key in [k for k, v in book.items() if now_ms - v.last_ms > horizon]:
                del book[key]
            if not book:
                del self.levels[symbol]
