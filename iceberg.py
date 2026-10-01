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
    __slots__ = ('executed', 'visible', 'first_ms', 'last_ms', 'fired', 'hit', 'refills', 'shown')

    def __init__(self, ts: int):
        self.executed = 0.0
        self.visible = 0.0
        self.first_ms = ts
        self.last_ms = ts
        self.fired = False
        self.hit = False       # traded against since the last book snapshot
        self.refills = 0       # snapshots that showed the level again after it was traded against
        self.shown = 0.0       # size in the last snapshot


class IcebergDetector:
    """
    Bids and asks are kept apart so a trade only touches its own side: scanning every tracked level on every aggTrade
    stalled the event loop on ETH / BTC (live 2026-10-01, watchdog: iceberg.on_trade). A level must REFILL - be shown
    again in >= `min_refills` book snapshots after trades hit it - before it counts: depth20 arrives every 500 ms, so
    "executed > the largest size ever shown" alone fired on every busy ETH level where new orders simply arrived
    between two snapshots (112 of 157 events on ETH, "$61k executed vs $212 shown").
    """

    def __init__(self):
        # symbol -> side (+1 bid / -1 ask) -> price -> level
        self.levels: Dict[str, Dict[int, Dict[float, _Level]]] = {}
        self.events: Dict[str, Deque[Tuple[int, int, float, float]]] = {}   # symbol -> (ts, side, price, usd)

    def on_book(self, symbol: str, bids, asks, ts_ms: int):
        """Largest size seen at each price of the live book (USD); a level traded against and shown again = a refill."""
        book = self.levels.setdefault(symbol, {1: {}, -1: {}})
        for side, rows in ((1, bids), (-1, asks)):
            levels = book[side]
            for p, q in rows:
                price, size = float(p), float(q)
                usd = price * size
                lvl = levels.get(price)
                if lvl is None:
                    if size > 0:
                        lvl = levels[price] = _Level(ts_ms)
                        lvl.visible = lvl.shown = usd
                    continue
                if lvl.hit and usd > 0:
                    lvl.refills += 1
                lvl.hit = False
                lvl.shown = usd
                lvl.visible = max(lvl.visible, usd)
            # levels no longer shown that nothing traded against are forgotten: the per-trade scan stays ~depth20 long
            shown = {float(p) for p, _ in rows}
            for p in [p for p, l in levels.items() if p not in shown and not l.executed]:
                del levels[p]

    def on_trade(self, symbol: str, ts_ms: int, price: float, usd: float, taker_side: int):
        """A taker SELL hits the bid side at `price` (and breaks every bid above it), a taker BUY the asks."""
        cfg = CONFIG.iceberg
        side = 1 if taker_side < 0 else -1                        # the passive side the trade executed against
        book = self.levels.get(symbol)
        if not book:
            return
        levels = book[side]
        # a trade THROUGH a level ends it (the hidden order was exhausted): bids above / asks below the price
        through = [p for p in levels if (p > price if side > 0 else p < price)] if levels else ()
        for p in through:
            del levels[p]
        lvl = levels.get(price)
        if lvl is None:
            return
        if ts_ms - lvl.last_ms > cfg.window_sec * 1000:
            lvl.executed, lvl.first_ms, lvl.fired, lvl.refills = 0.0, ts_ms, False, 0
        lvl.executed += usd
        lvl.last_ms = ts_ms
        lvl.hit = True
        if not lvl.fired and lvl.visible > 0 and lvl.refills >= cfg.min_refills and lvl.executed >= cfg.min_usd and                 lvl.executed >= cfg.multiple * lvl.visible:
            lvl.fired = True
            self.events.setdefault(symbol, deque(maxlen=200)).append((ts_ms, side, price, lvl.executed))
            logger.info(f"Iceberg {'BID' if side > 0 else 'ASK'} {symbol} @ {price:.6g}: ${lvl.executed:,.0f} "
                        f"executed vs ${lvl.visible:,.0f} ever shown, {lvl.refills} refills "
                        f"({max(0, ts_ms - lvl.first_ms) / 1000:.0f}s)")

    def features(self, symbol: str, window_sec: int = 300, now_ms: float = None) -> Dict[str, float]:
        now_ms = now_ms or time.time() * 1000
        ev = [e for e in self.events.get(symbol, ()) if now_ms - e[0] <= window_sec * 1000]
        return {'iceberg_net_5m': sum(e[1] * e[3] for e in ev), 'iceberg_n_5m': float(len(ev))}

    def prune(self, now_ms: float = None):
        now_ms = now_ms or time.time() * 1000
        horizon = CONFIG.iceberg.window_sec * 1000 * 3
        for symbol, book in list(self.levels.items()):
            for levels in book.values():
                for key in [k for k, v in levels.items() if now_ms - v.last_ms > horizon]:
                    del levels[key]
            if not book[1] and not book[-1]:
                del self.levels[symbol]
