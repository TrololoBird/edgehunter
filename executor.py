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
                                  'timeout': 30_000,   # the VST contract list (~1200 markets) took > 10s under load
                                  # VST round trips took 5-11s from here: a 5s signed window expired ('timestamp is invalid')
                                  'options': {'defaultType': 'swap', 'recvWindow': 60_000}})
            self.ex.set_sandbox_mode(True)       # VST demo: forced, the only mode this module has
        if not self._markets_ready:
            await self.ex.load_markets()
            try:
                await self.ex.set_position_mode(False)   # one-way: reduce-only orders need no position side
            except Exception as e:
                logger.info(f"Demo: position mode unchanged ({e})")
            self._markets_ready = True
        return self.ex

    async def _market_of(self, symbol: str, price: float):
        """
        The same contract on BingX, price-checked (a ticker can be a different token there), and the price scale
        BingX's contract has against Binance's: 1000FLOKI on Binance is FLOKI on BingX (scale 1/1000), and the other way.
        Returns (BingX symbol, scale) or (None, reason).
        """
        ex = await self._exchange()
        self._quote = None
        base, rest = symbol.split('/', 1)
        bare = base[4:] if base.startswith('1000') else base
        candidates = [(symbol, 1.0), (f"{bare}/{rest}", 1e-3 if bare != base else 1.0),
                      (f"1000{bare}/{rest}", 1e3 if bare == base else 1.0)]
        seen, last = set(), None
        for name, scale in candidates:
            if name in seen or name not in ex.markets:
                continue
            seen.add(name)
            ticker = await ex.fetch_ticker(name)
            last = ticker.get('last')
            if last and abs(last / (price * scale) - 1) <= 0.02:
                self._quote = ticker
                return name, scale
        reason = f"BingX price {last} vs {price:.6g}" if seen else 'not listed on BingX'
        return None, reason

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
        busy = next((t for t in self.open.values() if t['symbol'].split('/')[0].replace('1000', '') ==
                     s.symbol.split('/')[0].replace('1000', '')), None)
        if busy is not None:
            # BingX's one-way mode nets every order of a coin into ONE position: a second card on the same coin would
            # merge with the first (one card's exit closes the other, their fills mix in both results) - recorded, not
            # traded
            logger.info(f"Demo: {s.symbol} {s.group_key} skipped: {busy.get('setup') or busy['card_id']} already holds the coin")
            self._insert({'card_id': card_id, 'symbol': s.symbol, 'setup': s.group_key, 'strategy': s.mode,
                          'direction': s.direction, 'opened_ms': int(time.time() * 1000),
                          'error': f"coin held by {busy.get('setup') or busy['card_id']}", 'closed_ms': int(time.time() * 1000),
                          'close_reason': 'OVERLAP'})
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
        d = s.direction
        binance_now = float(s.last_price or s.levels['entry'])
        symbol, scale = await self._market_of(s.symbol, binance_now)
        if symbol is None:
            # recorded, so the demo / journal comparison knows which entries could not be traded (live GRAM)
            logger.info(f"Demo: {s.symbol} {s.group_key} skipped: {scale}")
            self._insert({'card_id': card_id, 'symbol': s.symbol, 'setup': s.group_key, 'strategy': s.mode,
                          'direction': d, 'opened_ms': int(time.time() * 1000), 'error': str(scale)[:300],
                          'closed_ms': int(time.time() * 1000), 'close_reason': 'NO_MARKET'})
            return
        # The trade is on BingX, the plan was drawn on Binance: every level is carried over by the CURRENT ratio of the
        # two prices (the contract scale x the basis between the venues) - a stop / take-profit at Binance's number
        # sits off by the basis on BingX, and a zone Binance touched may not be touched there (eng-45)
        quote = getattr(self, '_quote', None) or {}
        bx_last = float(quote.get('last') or binance_now * scale)
        ratio = bx_last / binance_now
        basis = ratio / scale - 1
        lv = {k: (v * ratio if isinstance(v, (int, float)) and k in ('entry', 'sl', 'tp1', 'tp2', 'tp3') else v)
              for k, v in s.levels.items()}
        # the fill is BingX's own ask (a long) / bid (a short): the trade is judged at that price, not at the plan's
        fill_est = float((quote.get('ask') if d > 0 else quote.get('bid')) or bx_last)
        reject = None
        if d * (fill_est - lv['sl']) <= 0:
            reject = f"BingX {fill_est:.6g} already beyond the stop {lv['sl']:.6g}"
        elif d * (lv['tp1'] - fill_est) <= 0 and s.levels.get('rr_tp1') is not None:
            reject = f"BingX {fill_est:.6g} already beyond TP1 {lv['tp1']:.6g}"
        elif s.levels.get('rr_tp1') is not None:
            from strategies.geometry import cost_of
            fee = cost_of(fill_est, (s.sig or {}).get('volume_24h'))
            risk = abs(fill_est - lv['sl'])
            rrs = [(d * (lv[f'tp{k}'] - fill_est) - fee) / (risk + fee) for k in (1, 2, 3)]
            blend = sum(rrs) / 3
            need = (s.plan or {}).get('min_rr')
            need = CONFIG.levels.min_rr_tp1 if need is None else need
            plan_blend = s.levels.get('rr_blend')
            # the plan passed its R:R on Binance; on BingX it must still pass it (a worse price by the basis / the
            # spread / the move since the trigger)
            if plan_blend is not None and blend < need:
                reject = f"blended R:R {blend:.2f} at BingX {fill_est:.6g} < {need:g} (Binance plan {plan_blend:.2f})"
        if reject:
            logger.info(f"Demo: {s.symbol} {s.group_key} skipped: {reject} (basis {basis:+.3%})")
            self._insert({'card_id': card_id, 'symbol': s.symbol, 'setup': s.group_key, 'strategy': s.mode,
                          'direction': d, 'opened_ms': int(time.time() * 1000), 'error': f"{reject}; basis {basis:+.3%}",
                          'closed_ms': int(time.time() * 1000), 'close_reason': 'PRICE_GAP'})
            return
        scale = ratio                      # every later conversion (pyramid / averaging stops) uses the same ratio
        ex = await self._exchange()
        balance = min(await self._balance(), cfg.account_usd)
        stop_dist = abs(lv['entry'] - lv['sl'])
        if balance <= 0 or stop_dist <= 0:
            return
        risk_usd = balance * cfg.risk_pct / 100
        n = (getattr(s, 'plan', None) or {}).get('turtle_n')
        if n:
            # the Turtles' unit: 1% of the account per N (their "dollar volatility"), so the 2N stop risks 2%
            risk_usd = balance * CONFIG.strategies.turtle_unit_risk * stop_dist / (n * scale)
        # an averaging plan (one more unit at half the way to the stop) risks 1.5 units: each unit is sized so the
        # whole position risks risk_pct
        risk_usd /= float(s.levels.get('risk_units') or 1.0)
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
        trailing = bool((getattr(s, 'plan', None) or {}).get('trail_days'))   # Turtles: out on the channel, no TPs
        for k, amount in zip((1, 2, 3), parts):
            if not trailing and amount > 0 and amount >= min_qty:
                await ex.create_order(symbol, 'market', exit_side, amount, None,
                                      {'takeProfitPrice': float(ex.price_to_precision(symbol, lv[f'tp{k}'])),
                                       'reduceOnly': True})
        trade = {'card_id': card_id, 'symbol': symbol, 'setup': s.group_key, 'strategy': s.mode, 'direction': d,
                 'opened_ms': int(time.time() * 1000), 'entry_plan': lv['entry'], 'entry_fill': fill, 'qty': qty,
                 'sl': lv['sl'], 'tp1': lv['tp1'], 'tp2': lv['tp2'], 'tp3': lv['tp3'], 'risk_usd': qty * stop_dist}
        trade['id'] = self._insert(trade)
        trade['unit_qty'], trade['scale'] = qty, scale          # in memory only (the pyramid's unit, BingX's price scale)
        self._set_basis(trade['id'], basis)
        self.open[card_id] = trade
        logger.info(f"Demo ENTRY {symbol} {s.group_key} {'long' if d > 0 else 'short'} {qty} @ {fill:.6g}, "
                    f"SL {lv['sl']:.6g}, risk ${trade['risk_usd']:.2f}")

    async def on_add(self, s) -> None:
        """A Turtle unit added on the card: the same quantity again at market, the stop of the whole position moved."""
        if not self.enabled or not s.entered_at:
            return
        card_id = f"{s.symbol}|{s.group_key}|{int(s.entered_at)}"
        trade = self.open.get(card_id)
        if trade is None:
            return
        async with self._lock:
            try:
                ex = await self._exchange()
                symbol, d = trade['symbol'], trade['direction']
                # after a restart the unit is the position over the units it already holds
                unit = float(trade.get('unit_qty') or float(trade['qty']) / max(1, len(s.units) - 1))
                order = await ex.create_order(symbol, 'market', 'buy' if d > 0 else 'sell', unit)
                fill = float(order.get('average') or order.get('price') or s.last_price)
                total = float(trade['qty']) + unit
                trade['entry_fill'] = (float(trade['entry_fill']) * float(trade['qty']) + fill * unit) / total
                trade['qty'], trade['unit_qty'] = total, unit
                try:
                    await ex.cancel_all_orders(symbol)
                except Exception as e:
                    logger.debug(f"Demo cancel {symbol}: {e}")
                scale = float(trade.get('scale') or 1.0)
                await ex.create_order(symbol, 'market', 'sell' if d > 0 else 'buy', total, None,
                                      {'stopLossPrice': float(ex.price_to_precision(symbol, s.levels['sl'] * scale)),
                                       'reduceOnly': True})
                if not (getattr(s, 'plan', None) or {}).get('trail_days'):
                    # an averaging add (pump strategies): the three take-profits again, for the whole position
                    third = float(ex.amount_to_precision(symbol, total / 3))
                    for k, amount in zip((1, 2, 3), (third, third, float(ex.amount_to_precision(symbol, total - 2 * third)))):
                        if amount > 0:
                            await ex.create_order(symbol, 'market', 'sell' if d > 0 else 'buy', amount, None,
                                                  {'takeProfitPrice': float(ex.price_to_precision(symbol, s.levels[f'tp{k}'] * scale)),
                                                   'reduceOnly': True})
                with sqlite3.connect(self.db_path) as c:
                    c.execute("UPDATE demo_trades SET qty = ?, entry_fill = ?, sl = ? WHERE id = ?",
                              (total, trade['entry_fill'], s.levels['sl'] * scale, trade['id']))
                logger.info(f"Demo ADD {symbol} unit {len(s.units)}: +{unit} @ {fill:.6g}, position {total}, "
                            f"stop {s.levels['sl'] * scale:.6g}")
            except Exception as e:
                logger.warning(f"Demo add-unit failed for {trade['symbol']}: {e!r}")

    async def on_finish(self, s) -> None:
        if not self.enabled or not s.entered_at:
            return
        card_id = f"{s.symbol}|{s.group_key}|{int(s.entered_at)}"
        trade = self.open.get(card_id)
        if trade is None:
            # the exchange closed it first (stop / last target, reconciled as EXCHANGE): the card's own result still
            # belongs next to it - the demo exists to compare the two
            if s.final_r is not None:
                with sqlite3.connect(self.db_path) as c:
                    c.execute("UPDATE demo_trades SET journal_r = ? WHERE card_id = ? AND journal_r IS NULL",
                              (s.final_r, card_id))
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
        """
        Realized result: OUR quantity x (the exit fills' volume-weighted price - the entry fill), minus taker fees on both
        sides. The fills' prices are right but ccxt's BingX swap fills report the amount 100x the position (live REZ:
        33,333,333 for 333,333 coins), and right after a close the exit fill may not be listed yet (retried).
        """
        ex = await self._exchange()
        d = trade['direction']
        exit_side = 'sell' if d > 0 else 'buy'
        exits = []
        for attempt in range(4):
            fills = await ex.fetch_my_trades(trade['symbol'], since=trade['opened_ms'] - 5_000)
            exits = [f for f in fills if f.get('side') == exit_side and f.get('price')]
            if exits:
                break
            await asyncio.sleep(5)
        qty, entry = float(trade.get('qty') or 0), float(trade.get('entry_fill') or 0)
        weight = sum(f['amount'] for f in exits)
        exit_avg = sum(f['price'] * f['amount'] for f in exits) / weight if weight else None
        if exit_avg is None or not qty or not entry:
            logger.warning(f"Demo {reason} {trade['symbol']}: no exit fill found, result not recorded")
            pnl = fees = None
        else:
            fees = CONFIG.journal.fee_round_trip / 2 * (entry + exit_avg) * qty
            pnl = d * (exit_avg - entry) * qty - fees
        risk = trade.get('risk_usd') or 0
        with sqlite3.connect(self.db_path) as c:
            c.execute("UPDATE demo_trades SET closed_ms = ?, close_reason = ?, exit_avg = ?, fees_usd = ?, pnl_usd = ?, "
                      "r = ?, journal_r = ? WHERE id = ?",
                      (int(time.time() * 1000), reason, exit_avg, fees, pnl,
                       pnl / risk if risk and pnl is not None else None, journal_r, trade['id']))
        self.open.pop(trade['card_id'], None)
        if pnl is not None:
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
                        # network / signature hiccups of the VST API retry next minute: one line; anything else with
                        # its traceback
                        import ccxt
                        transient = isinstance(e, (ccxt.NetworkError, ccxt.ExchangeNotAvailable)) or '109400' in str(e)
                        logger.warning(f"Demo reconcile {trade['symbol']}: {e!r}", exc_info=not transient)

    def _set_basis(self, trade_id: int, basis: float) -> None:
        """BingX vs Binance at the entry (journaled: the venue gap the demo trades through)."""
        with sqlite3.connect(self.db_path) as c:
            try:
                c.execute("ALTER TABLE demo_trades ADD COLUMN basis REAL")
            except sqlite3.OperationalError:
                pass
            c.execute("UPDATE demo_trades SET basis = ? WHERE id = ?", (basis, trade_id))

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
