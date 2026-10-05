"""
Loop-side detection of the event strategies. The coins' contexts (structure.Context) arrive from the maps worker
after each 15m close carrying that candle's events (sweeps, accepted breakouts); every scan this class
- releases those events once (a context rebuilt for the same candle does not fire it again),
- checks absorption on each new final 1m candle at the coin's significant levels,
- follows liquidation cascades until their leg is big enough (cascade.CascadeTracker).
It returns setup dicts that the scanner turns into signals (the coin's live Tier-0 metrics + the setup's anchor).
"""
from typing import Dict, List, Optional, Sequence, Tuple

from config import CONFIG
from strategies.cascade import CascadeTracker
from strategies.structure import Context


class LiveDetector:
    def __init__(self):
        self.context: Dict[str, Context] = {}
        self._pending: Dict[str, List[Dict]] = {}
        self._fired: Dict[Tuple[str, str, int], float] = {}
        self._last_minute: Dict[str, int] = {}
        self.cascades = CascadeTracker()

    def set_context(self, symbol: str, context: Optional[Context], now_ms: int):
        if context is None:
            self.context.pop(symbol, None)
            return
        self.context[symbol] = context
        for event in context.events:
            key = (symbol, event['setup'], event['event_ts'])
            if key in self._fired:
                continue
            self._fired[key] = now_ms
            self._pending.setdefault(symbol, []).append(event)
        # forget fired keys after a day
        if len(self._fired) > 5000:
            self._fired = {k: t for k, t in self._fired.items() if now_ms - t < 86_400_000}

    def state(self) -> list:
        """Fired close events [(symbol, setup, event_ts, fired_at)] of the last day (kept across restarts)."""
        return [[sym, setup, ts, at] for (sym, setup, ts), at in self._fired.items()]

    def load_state(self, items, now_ms: int):
        for item in items or []:
            if len(item) == 4 and now_ms - item[3] < 86_400_000:
                self._fired[(item[0], item[1], int(item[2]))] = item[3]

    def forget(self, symbol: str):
        self.context.pop(symbol, None)
        self._pending.pop(symbol, None)
        self._last_minute.pop(symbol, None)
        self.cascades.forget(symbol)

    def wants(self, symbol: str, minute_closed_until: int, metrics: Dict[str, float]) -> bool:
        """Anything to look at this scan: pending close events, a new final minute, a running / new cascade."""
        if symbol not in self.context:
            return False
        if self._pending.get(symbol) or self._last_minute.get(symbol) != minute_closed_until:
            return True
        if self.cascades.active(symbol):
            return True
        m = metrics or {}
        return (m.get('liq_long_5m') or 0.0) + (m.get('liq_short_5m') or 0.0) >= CONFIG.liquidations.cascade_min_usd

    def scan(self, symbol: str, minutes: Sequence[Sequence[float]], metrics: Dict[str, float], now_ms: int,
             bands: Sequence[Tuple[float, int, float]] = ()) -> List[Dict]:
        """`minutes`: FINAL 1m futures candles [open_time, o, h, l, c, quote_vol, taker_buy_quote]."""
        ctx = self.context.get(symbol)
        if ctx is None:
            return []
        out = self._pending.pop(symbol, [])
        if minutes:
            last = int(minutes[-1][0])

            self._last_minute[symbol] = last
            # (absorption at a level is an entry confirmation since eng-35 - fetcher.orderflow_confirm - not a setup)
            found = self.cascades.check(symbol, minutes, metrics or {}, ctx.atr, now_ms)
            if found:
                out.append(found)
        return out
