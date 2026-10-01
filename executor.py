"""
Demo execution on BingX (virtual VST, `open-api-vst`): every card that reaches ENTRY is traded there, so its result is
seen with real order handling next to the journal's own replay. DEMO ONLY: sandbox mode is forced and cannot be
switched off from the config. Never an order on a real balance.

- ENTRY: a market order sized so the stop costs `risk_pct` of the demo balance (capped by `max_leverage`), then a
  reduce-only stop-market at the card's SL and three reduce-only take-profits (thirds) at TP1 / TP2 / TP3.
- The card finishes (SL / TP3 / CLOSED / INVALID / EXPIRED / MISSED after an entry): open orders are cancelled and
  whatever is left of the position is closed at market.
- Every minute the open demo trades are reconciled: a position the exchange closed (stop / last target) is finalized.
- Each trade is a row of `demo_trades.db` (fills, fees, realized USD, R against the planned stop).

The API key is the owner's (config.local.toml, `[executor] api_key / api_secret`), a trade-only key.
    python executor.py --check           markets, balance, position mode
    python executor.py --test BTC/USDT:USDT    open and close the minimum size (checks order handling)
"""
import asyncio
import logging
import sqlite3
import time
from typing import Dict, Optional

from config import CONFIG

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS demo_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT, card_id TEXT, symbol TEXT, setup TEXT, strategy TEXT, direction INTEGER,
    opened_ms INTEGER, entry_plan REAL, entry_fill REAL, qty REAL, sl REAL, tp1 REAL, tp2 REAL, tp3 REAL,
    risk_usd REAL, closed_ms INTEGER, close_reason TEXT, exit_avg REAL, fees_usd REAL, pnl_usd REAL, r REAL,
    journal_r REAL, error TEXT)
"""


class DemoExecutor:
    def __init__(self, db_path: str = 'demo_trades.db'):
        cfg = CONFIG.executor
        self.enabled = bool(cfg.enabled and cfg.api_key and cfg.api_secret)
        self.db_path = db_path
        self.ex = None
        self.open: Dict[str, Dict] = {}          # card id -> trade
        self._lock = asyncio.Lock()
        # set by the scanner: is this card (symbol|setup|entered_at) still an open trade in the book? A card that
        # expired while the bot was down is never restored, so its finish never comes (3 demo positions stayed
        # open for 15h, 2026-10-01): the reconcile loop closes such orphans
        self.card_is_open = lambda card_id: True
        self._markets_ready = False
        with sqlite3.connect(db_path) as c:
            c.execute(SCHEMA)
            for row in c.execute("SELECT id, card_id, symbol, direction, opened_ms, entry_fill, qty, sl, risk_usd "
                                 "FROM demo_trades WHERE closed_ms IS NULL"):
                self.open[row[1]] = dict(zip(('id', 'card_id', 'symbol', 'direction', 'opened_ms', 'entry_fill',
                                              'qty', 'sl', 'risk_usd'), row))

    # ------------------------------------------------------------------ exchange

    async def _exchange(self):
        if self.ex is None:
            import ccxt.async_support as ccxt
            cfg = CONFIG.executor
            self.ex = ccxt.bingx({'apiKey': cfg.api_key, 'secret': cfg.api_secret, 'enableRateLimit': True,
                                  'options': {'defaultType': 'swap'}})
            self.ex.set_sandbox_mode(True)       # VST demo: forced, the only mode this module has
        if not self._markets_ready:
            await self.ex.load_markets()
            try:
                await self.ex.set_position_mode(False)   # one-way: reduce-only orders need no position side
            except Exception as e:
                logger.info(f"Demo: position mode unchanged ({e})")
            self._markets_ready = True
        return self.ex

    async def _market_of(self, symbol: str, price: float) -> Optional[str]:
        """The same contract on BingX, price-checked (a ticker can be a different token there)."""
        ex = await self._exchange()
        if symbol not in ex.markets:
            return None
        ticker = await ex.fetch_ticker(symbol)
        last = ticker.get('last')
        if not last or abs(last / price - 1) > 0.02:
            logger.info(f"Demo: {symbol} skipped, BingX price {last} vs {price:.6g}")
            return None
        return symbol

    async def _balance(self) -> float:
        ex = await self._exchange()
        bal = await ex.fetch_balance()
        return float((bal.get('total') or {}).get('VST') or (bal.get('total') or {}).get('USDT') or 0)

    # ------------------------------------------------------------------ card events

    async def on_entry(self, s) -> None:
        if not self.enabled or s.levels is None:
            return
        card_id = f"{s.symbol}|{s.group_key}|{int(s.entered_at or 0)}"
        if card_id in self.open:
            return
        async with self._lock:
            try:
                await self._open(card_id, s)
            except Exception as e:
                logger.warning(f"Demo entry failed for {s.symbol} {s.group_key}: {e!r}")
                self._insert({'card_id': card_id, 'symbol': s.symbol, 'setup': s.group_key, 'strategy': s.mode,
                              'direction': s.direction, 'opened_ms': int(time.time() * 1000), 'error': repr(e)[:300],
                              'closed_ms': int(time.time() * 1000), 'close_reason': 'ERROR'})

    async def _open(self, card_id: str, s) -> None:
        cfg = CONFIG.executor
        lv, d = s.levels, s.direction
        symbol = await self._market_of(s.symbol, lv['entry'])
        if symbol is None:
            return
        ex = await self._exchange()
        balance = min(await self._balance(), cfg.account_usd)
        stop_dist = abs(lv['entry'] - lv['sl'])
        if balance <= 0 or stop_dist <= 0:
            return
        risk_usd = balance * cfg.risk_pct / 100
        qty = min(risk_usd / stop_dist, balance * cfg.max_leverage / lv['entry'], cfg.max_notional_usd / lv['entry'])
        qty = float(ex.amount_to_precision(symbol, qty))
        min_qty = ((ex.markets[symbol].get('limits') or {}).get('amount') or {}).get('min') or 0
        if qty <= 0 or qty < min_qty:
            logger.info(f"Demo: {symbol} size {qty} below the minimum {min_qty}")
            return
        try:
            await ex.set_leverage(cfg.max_leverage, symbol)
        except Exception as e:
            logger.debug(f"Demo leverage {symbol}: {e}")
        side, exit_side = ('buy', 'sell') if d > 0 else ('sell', 'buy')
        try:
            order = await ex.create_order(symbol, 'market', side, qty)
        except Exception as e:
            # BingX caps the position per coin (1000 USDT on small caps, live HUMA 2026-10-01) and names the cap in
            # the error: retry once at 90% of it
            import re
            m = re.search(r'position limit of ([0-9.]+) USDT', str(e))
            if not m:
                raise
            qty = float(ex.amount_to_precision(symbol, 0.9 * float(m.group(1)) / lv['entry']))
            if qty <= 0 or qty < min_qty:
                raise
            order = await ex.create_order(symbol, 'market', side, qty)
        fill = float(order.get('average') or order.get('price') or lv['entry'])
        await ex.create_order(symbol, 'market', exit_side, qty, None,
                              {'stopLossPrice': float(ex.price_to_precision(symbol, lv['sl'])), 'reduceOnly': True})
        third = float(ex.amount_to_precision(symbol, qty / 3))
        parts = [third, third, float(ex.amount_to_precision(symbol, qty - 2 * third))]
        for k, amount in zip((1, 2, 3), parts):
            if amount > 0 and amount >= min_qty:
                await ex.create_order(symbol, 'market', exit_side, amount, None,
                                      {'takeProfitPrice': float(ex.price_to_precision(symbol, lv[f'tp{k}'])),
                                       'reduceOnly': True})
        trade = {'card_id': card_id, 'symbol': symbol, 'setup': s.group_key, 'strategy': s.mode, 'direction': d,
                 'opened_ms': int(time.time() * 1000), 'entry_plan': lv['entry'], 'entry_fill': fill, 'qty': qty,
                 'sl': lv['sl'], 'tp1': lv['tp1'], 'tp2': lv['tp2'], 'tp3': lv['tp3'], 'risk_usd': qty * stop_dist}
        trade['id'] = self._insert(trade)
        self.open[card_id] = trade
        logger.info(f"Demo ENTRY {symbol} {s.group_key} {'long' if d > 0 else 'short'} {qty} @ {fill:.6g}, "
                    f"SL {lv['sl']:.6g}, risk ${trade['risk_usd']:.2f}")

    async def on_finish(self, s) -> None:
        if not self.enabled or not s.entered_at:
            return
        card_id = f"{s.symbol}|{s.group_key}|{int(s.entered_at)}"
        trade = self.open.get(card_id)
        if trade is None:
            return
        async with self._lock:
            try:
                await self._close(trade, s.status, s.final_r)
            except Exception as e:
                logger.warning(f"Demo close failed for {trade['symbol']}: {e!r}")

    async def _position_qty(self, symbol: str) -> float:
        ex = await self._exchange()
        for p in await ex.fetch_positions([symbol]):
            if p.get('symbol') == symbol and p.get('contracts'):
                return float(p['contracts'])
        return 0.0

    async def _close(self, trade: Dict, reason: str, journal_r: Optional[float]) -> None:
        ex = await self._exchange()
        symbol, d = trade['symbol'], trade['direction']
        try:
            await ex.cancel_all_orders(symbol)
        except Exception as e:
            logger.debug(f"Demo cancel {symbol}: {e}")
        left = await self._position_qty(symbol)
        if left > 0:
            await ex.create_order(symbol, 'market', 'sell' if d > 0 else 'buy', left, None, {'reduceOnly': True})
        await self._finalize(trade, reason, journal_r)

    async def _finalize(self, trade: Dict, reason: str, journal_r: Optional[float]) -> None:
        """Realized result from the account's fills of this symbol since the entry."""
        ex = await self._exchange()
        fills = await ex.fetch_my_trades(trade['symbol'], since=trade['opened_ms'] - 5_000)
        d = trade['direction']
        exit_side = 'sell' if d > 0 else 'buy'
        exits = [f for f in fills if f.get('side') == exit_side]
        cash = sum((-1 if f['side'] == 'buy' else 1) * f['price'] * f['amount'] for f in fills)
        fees = sum(float((f.get('fee') or {}).get('cost') or 0) for f in fills)
        exit_qty = sum(f['amount'] for f in exits)
        pnl = cash - fees
        risk = trade.get('risk_usd') or 0
        with sqlite3.connect(self.db_path) as c:
            c.execute("UPDATE demo_trades SET closed_ms = ?, close_reason = ?, exit_avg = ?, fees_usd = ?, pnl_usd = ?, "
                      "r = ?, journal_r = ? WHERE id = ?",
                      (int(time.time() * 1000), reason,
                       sum(f['price'] * f['amount'] for f in exits) / exit_qty if exit_qty else None,
                       fees, pnl, pnl / risk if risk else None, journal_r, trade['id']))
        self.open.pop(trade['card_id'], None)
        logger.info(f"Demo {reason} {trade['symbol']}: {pnl:+.2f} USD ({pnl / risk if risk else 0:+.2f}R)")

    async def reconcile_loop(self, running) -> None:
        """Finalize demo trades the exchange closed on its own (stop / last target)."""
        while running():
            await asyncio.sleep(60)
            if not self.enabled or not self.open:
                continue
            async with self._lock:
                for trade in list(self.open.values()):
                    try:
                        if time.time() * 1000 - trade['opened_ms'] > 120_000 and not self.card_is_open(trade['card_id']):
                            logger.info(f"Demo: {trade['symbol']} has no open card any more: closing the orphan")
                            await self._close(trade, 'ORPHAN', None)
                            continue
                        if await self._position_qty(trade['symbol']) == 0:
                            await self._exchange()
                            try:
                                await self.ex.cancel_all_orders(trade['symbol'])
                            except Exception:
                                pass
                            await self._finalize(trade, 'EXCHANGE', None)
                    except Exception as e:
                        logger.debug(f"Demo reconcile {trade['symbol']}: {e!r}")

    def _insert(self, row: Dict) -> int:
        cols = [k for k in row if k != 'id']
        with sqlite3.connect(self.db_path) as c:
            cur = c.execute(f"INSERT INTO demo_trades ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                            [row[k] for k in cols])
            return cur.lastrowid

    async def close(self):
        if self.ex is not None:
            await self.ex.close()


async def _cli(args):
    ex = DemoExecutor(db_path=':memory:')
    if not (CONFIG.executor.api_key and CONFIG.executor.api_secret):
        print("No [executor] api_key / api_secret in config.local.toml")
        return
    try:
        x = await ex._exchange()
        print(f"BingX demo: {len([m for m in x.markets.values() if m.get('swap')])} swap markets, "
              f"balance {await ex._balance():.2f} VST")
        if args.test:
            symbol = args.test
            price = (await x.fetch_ticker(symbol))['last']
            qty = float(x.amount_to_precision(symbol, max((x.markets[symbol]['limits']['amount'] or {}).get('min') or 0,
                                                          6 / price)))
            o = await x.create_order(symbol, 'market', 'buy', qty)
            print('opened', o.get('id'), o.get('average'), qty)
            await asyncio.sleep(3)
            left = await ex._position_qty(symbol)
            await x.create_order(symbol, 'market', 'sell', left or qty, None, {'reduceOnly': True})
            print('closed', left or qty)
    finally:
        await ex.close()


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--check', action='store_true')
    p.add_argument('--test', default=None)
    asyncio.run(_cli(p.parse_args()))
