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
import json
import logging
import errors
import os
import sqlite3
import time
from typing import Dict, Optional

from config import CONFIG

logger = logging.getLogger(__name__)

BINGX_ALIAS = {'XAU': 'NCCOGOLD2USD/USDT:USDT', 'XAG': 'NCCOXAG2USD/USDT:USDT',
               'CL': 'NCCO1OILWTI2USD/USDT:USDT', 'BZ': 'NCCO1OILBRENT2USD/USDT:USDT'}

# eng-84: a limit-filled trade whose card ended keeps its exchange stop / targets this long, then is closed
ORPHAN_LIMIT_HOLD_MS = 24 * 3600_000
# eng-86: no market entry when BingX's price already ran this share of the planned risk past the plan's entry (laptop
# demo journal: a chase >= 0.25R cost -0.64R against the journal, n=15; < 0.25R -0.07R; live GRASS +3.6%: -2.32R)
CHASE_MAX_R = float('inf')       # eng-113: removed (the size follows the price)

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
        self._band_warned: set = set()       # coins whose market close BingX rejected (102202): warned once
        self._quotes_seen: Dict[str, tuple] = {}   # symbol -> (BingX last, since): a VST quote that stopped moving
        self.ex = None
        self.open: Dict[str, Dict] = {}          # card id -> trade
        self._lock = asyncio.Lock()
        # set by the scanner: is this card (symbol|setup|entered_at) still an open trade in the book? A card that
        # expired while the bot was down is never restored, so its finish never comes (3 demo positions stayed
        # open for 15h, 2026-10-01): the reconcile loop closes such orphans
        self.card_is_open = lambda card_id: True
        # resting limit entries of touch plans (Seiden's proximal line, the Silver Bullet's CE): waiting-card key ->
        # {order_id, symbol, levels in BingX prices, ...} (eng-46)
        self.pending: Dict[str, Dict] = {}
        self.pending_path = os.path.join(os.path.dirname(os.path.abspath(db_path)), 'demo_pending.json')
        try:
            with open(self.pending_path, encoding='utf-8') as f:
                self.pending = json.load(f)     # resting limits survive a restart (else they stay on BingX unseen)
        except (OSError, ValueError):
            pass
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
                                  # no recvWindow option: ccxt's bingx.sign never sends it (checked in ccxt 4.5.85: only
                                  # the deposit / withdraw endpoints read it); BingX's window stays 5s; the cause of
                                  # 'timestamp is invalid' was a dead VST address, see the session below
                                  'options': {'defaultType': 'swap'}})
            self.ex.set_sandbox_mode(True)       # VST demo: forced, the only mode this module has
            # ccxt's own connector tries the resolved addresses with happy_eyeballs_delay=0, which here meant one at a
            # time: one of VST's four CloudFront addresses (3.173.161.114, 2026-10-05) never answers, every new
            # connection to it waited the 21s TCP timeout, and BingX rejected the request signed before it ('timestamp
            # is invalid', its window is 5s; ccxt never sends the recvWindow option; eng-57's
            # sign wrapper adding recvWindow 60s treated the symptom - BingX documents 5000 ms as the maximum). Staggered attempts 250ms apart:
            # the first call took 0.9-1.4s instead of 21.7s. ccxt closes this session in ex.close().
            import ssl
            import aiohttp
            import certifi
            self.ex.session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(
                ssl=ssl.create_default_context(cafile=certifi.where()), enable_cleanup_closed=True,
                happy_eyeballs_delay=0.25))
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
        # eng-93: Binance's TradFi perpetuals are BingX's NCCO* contracts (the session ORB trades gold, silver and oil;
        # the price check below still decides - VST silver sat 7.7% off Binance's XAG on 14.10)
        alias = BINGX_ALIAS.get(base)
        if alias:
            candidates.insert(0, (alias, 1.0))
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
        if seen and last:
            # a VST contract whose price stopped (PONS 2026-10-07: 0.4192 for 7h while Binance moved 0.40 -> 0.39) is
            # a dead demo market, not a venue gap
            prev = self._quotes_seen.get(symbol)
            if prev and prev[0] == last and time.time() - prev[1] > 1800:
                reason = f"stale BingX quote {last} unchanged {(time.time() - prev[1]) / 3600:.1f}h vs {price:.6g}"
            elif not prev or prev[0] != last:
                self._quotes_seen[symbol] = (last, time.time())
        return None, reason

    async def _balance(self) -> float:
        ex = await self._exchange()
        bal = await ex.fetch_balance()
        return float((bal.get('total') or {}).get('VST') or (bal.get('total') or {}).get('USDT') or 0)

    # ------------------------------------------------------------------ card events

    async def on_entry(self, s) -> None:
        if not self.enabled or s.levels is None:
            return
        # eng-85: every check below reads the shared state (open trades, resting limits, the day's rows): two entries
        # scheduled as background tasks both passed 'coin free' before either took the lock
        async with self._lock:
            card_id = f"{s.symbol}|{s.group_key}|{int(s.entered_at or 0)}"
            if card_id in self.open:
                return
            if self.is_limit_plan(s):
                key = self.wait_key(s)
                p = self.pending.get(key)
                if key in self.open:                     # BingX filled the limit before Binance's touch: one trade
                    trade = self.open.pop(key)
                    trade['card_id'] = card_id
                    self.open[card_id] = trade
                    with sqlite3.connect(self.db_path) as c:
                        c.execute("UPDATE demo_trades SET card_id = ? WHERE id = ?", (card_id, trade['id']))
                    return
                if p is not None and not p.get('skip'):
                    p.update(entered=True, entered_ms=int(time.time() * 1000), card_id=card_id)
                    self._save_pending()
                    return                               # the limit stands; check_limits fills or cancels it
                if p is not None and p.get('skip'):
                    # eng-91: the plan enters with a resting limit and its limit was refused ('low R:R at the line',
                    # the coin held, no market...): the touch does not turn it into a market order
                    logger.info(f"Demo: {s.symbol} {s.group_key} skipped: its limit was not placed ({p.get('reason')})")
                    self._insert({'card_id': card_id, 'symbol': s.symbol, 'setup': s.group_key, 'strategy': s.mode,
                                  'direction': s.direction, 'opened_ms': int(time.time() * 1000),
                                  'error': f"limit not placed: {p.get('reason')}"[:300],
                                  'closed_ms': int(time.time() * 1000), 'close_reason': 'NO_LIMIT'})
                    return
            limit = self.risk_limit()
            if limit is not None:
                # eng-58: the day's risk rules (prop practice): not traded, recorded with the rule
                logger.info(f"Demo: {s.symbol} {s.group_key} skipped: {limit}")
                self._insert({'card_id': card_id, 'symbol': s.symbol, 'setup': s.group_key, 'strategy': s.mode,
                              'direction': s.direction, 'opened_ms': int(time.time() * 1000), 'error': limit,
                              'closed_ms': int(time.time() * 1000),
                              'close_reason': 'PAUSE' if limit.startswith('pause') else 'DAILY_LIMIT'})
                return
            coin = s.symbol.split('/')[0].replace('1000', '')
            busy = next((t for t in self.open.values() if t['symbol'].split('/')[0].replace('1000', '') == coin), None) or \
                next((p for p in self.pending.values() if not p.get('skip')
                      and p.get('symbol', '').split('/')[0].replace('1000', '') == coin), None)
            if busy is not None:
                # BingX's one-way mode nets every order of a coin into ONE position: a second card on the same coin would
                # merge with the first (one card's exit closes the other, their fills mix in both results) - recorded, not
                # traded
                logger.info(f"Demo: {s.symbol} {s.group_key} skipped: {busy.get('setup') or busy.get('card_id')} already holds the coin")
                self._insert({'card_id': card_id, 'symbol': s.symbol, 'setup': s.group_key, 'strategy': s.mode,
                              'direction': s.direction, 'opened_ms': int(time.time() * 1000),
                              'error': f"coin held by {busy.get('setup') or busy.get('card_id')}", 'closed_ms': int(time.time() * 1000),
                              'close_reason': 'OVERLAP'})
                return
            try:
                await self._open(card_id, s)
            except Exception as e:
                logger.warning(f"Demo entry failed for {s.symbol} {s.group_key}: {e!r}")
                self._insert({'card_id': card_id, 'symbol': s.symbol, 'setup': s.group_key, 'strategy': s.mode,
                              'direction': s.direction, 'opened_ms': int(time.time() * 1000), 'error': repr(e)[:300],
                              'closed_ms': int(time.time() * 1000), 'close_reason': 'ERROR'})

    @staticmethod
    def regime_mult(s) -> float:
        """eng-100: regime_against_mult when the trade runs against BTC's 7-day momentum (the market regime), else 1;
        the TradFi contracts (gold, silver, oil) are exempt."""
        cfg = CONFIG.exchange
        mom = (getattr(s, 'sig', None) or {}).get('btc_mom_7d')
        if mom is None or not mom or s.symbol.split('/')[0] in cfg.regime_exempt_bases:
            return 1.0
        return cfg.regime_against_mult if s.direction * mom < 0 else 1.0

    @staticmethod
    def _is_stop(o: Dict) -> bool:
        t = str((o.get('info') or {}).get('type') or o.get('type') or '').upper()
        return 'STOP' in t and 'TAKE' not in t

    async def _place_stop(self, symbol: str, d: int, qty: float, price: float) -> Dict:
        ex = await self._exchange()
        return await ex.create_order(symbol, 'market', 'sell' if d > 0 else 'buy', qty, None,
                                     {'stopLossPrice': float(ex.price_to_precision(symbol, price)), 'reduceOnly': True,
                                      'workingType': 'MARK_PRICE'})

    async def _cancel_orders(self, symbol: str, keep: str = None, stops_only: bool = False) -> None:
        """eng-85: cancel a coin's resting orders one by one (all but `keep`; only the stops with stops_only), never the
        blanket cancel-all before the replacement stands: the position is never left without a stop."""
        ex = await self._exchange()
        for o in await ex.fetch_open_orders(symbol):
            if o.get('id') == keep or (stops_only and not self._is_stop(o)):
                continue
            try:
                await ex.cancel_order(o['id'], symbol)
            except Exception as e:
                errors.report('executor._cancel_orders', e, f"Demo cancel {symbol} {o.get('id')}")

    async def _place_tps(self, trade: Dict, parts, min_qty: float = 0.0) -> None:
        """The take-profits; a failure leaves the trade tracked with its stop (eng-85: an exception here used to drop
        a stopped position out of self.open, and close_untracked then dumped it at market as UNTRACKED)."""
        ex = await self._exchange()
        symbol, d = trade['symbol'], trade['direction']
        for k, amount in parts:
            if amount <= 0 or amount < min_qty or not trade.get(f'tp{k}'):
                continue
            try:
                await ex.create_order(symbol, 'market', 'sell' if d > 0 else 'buy', amount, None,
                                      {'takeProfitPrice': float(ex.price_to_precision(symbol, float(trade[f'tp{k}']))),
                                       'reduceOnly': True})
            except Exception as e:
                errors.report('executor._place_tps', e, f"Demo TP{k} {symbol}: the trade keeps its stop")

    @staticmethod
    def tp_parts(ex, symbol: str, qty: float, trail: bool, no_tp: bool):
        """(target index, amount) of the take-profit orders: thirds at TP1-3; eng-58 trailing plans (continuation,
        pump, oi_signal) half at TP1 and the rest on the card's trailing stop (RESTOP); target-less plans none."""
        if no_tp:
            return []
        if trail:
            return [(1, float(ex.amount_to_precision(symbol, qty / 2)))]
        third = float(ex.amount_to_precision(symbol, qty / 3))
        return [(1, third), (2, third), (3, float(ex.amount_to_precision(symbol, qty - 2 * third)))]

    def exit_parts(self, ex, trade: Dict, qty: float, trail: bool, no_tp: bool):
        """eng-105: partial_share of the position at +partial_r R (trade['tp0']), the rest by tp_parts; the plain
        tp_parts when the plan's TP1 is already nearer than that (TP1 is the partial then)."""
        cfg = CONFIG.executor
        d, fill, sl = trade['direction'], trade.get('entry_fill'), trade.get('sl')
        if not cfg.partial_share or not fill or not sl or trade.get('units'):
            return self.tp_parts(ex, trade['symbol'], qty, trail, no_tp)
        p1r = fill + d * cfg.partial_r * abs(fill - sl)
        tp1 = trade.get('tp1')
        if not no_tp and tp1 and d * (tp1 - p1r) <= 0:
            return self.tp_parts(ex, trade['symbol'], qty, trail, no_tp)
        half = float(ex.amount_to_precision(trade['symbol'], qty * cfg.partial_share))
        if half <= 0:
            return self.tp_parts(ex, trade['symbol'], qty, trail, no_tp)
        trade['tp0'] = p1r
        rest = float(ex.amount_to_precision(trade['symbol'], qty - half))
        return [(0, half)] + list(self.tp_parts(ex, trade['symbol'], rest, trail, no_tp))

    def risk_limit(self) -> Optional[str]:
        """
        eng-58, the account's day (prop firms: a daily loss limit of 1-5%, 2-3 trades a day, a pause after a losing
        streak): no new demo trade once the UTC day's closed trades lost daily_loss_r R, after max_trades_day trades
        were opened today, or within pause_hours after pause_losses stops in a row. The numbers are ours, inside the
        prop firms' ranges. Cards and the journal are not limited (they measure the signals).
        """
        cfg = CONFIG.executor
        day0 = int(time.time() // 86400 * 86400 * 1000)
        try:
            with sqlite3.connect(self.db_path) as c:
                closed = c.execute("SELECT r FROM demo_trades WHERE closed_ms >= ? AND r IS NOT NULL", (day0,)).fetchall()
                opened = c.execute("SELECT COUNT(*) FROM demo_trades WHERE opened_ms >= ? AND entry_fill IS NOT NULL",
                                   (day0,)).fetchone()[0]
                last = c.execute("SELECT r, closed_ms FROM demo_trades WHERE r IS NOT NULL ORDER BY closed_ms DESC LIMIT ?",
                                 (cfg.pause_losses,)).fetchall()
        except sqlite3.Error:
            return None
        # eng-85: a resting limit holds a slot of the day (it fills without asking again)
        opened += sum(1 for p in self.pending.values() if not p.get('skip'))
        day_r = sum(r for (r,) in closed)
        if cfg.daily_loss_r > 0 and day_r <= -cfg.daily_loss_r:
            return f"daily loss limit: {day_r:+.2f}R today"
        if cfg.max_trades_day > 0 and opened >= cfg.max_trades_day:
            return f"daily trade limit: {opened} trades today"
        if cfg.pause_losses > 0 and len(last) == cfg.pause_losses and all(r < 0 for r, _ in last) and                 time.time() * 1000 - last[0][1] < cfg.pause_hours * 3_600_000:
            return f"pause after {cfg.pause_losses} losses in a row"
        return None

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
        plan_risk = abs(lv['entry'] - lv['sl'])
        if d * (fill_est - lv['sl']) <= 0:
            reject = f"BingX {fill_est:.6g} already beyond the stop {lv['sl']:.6g}"
        # eng-113 (the owner): no invented chase cap - the size is recomputed at BingX's price (stop_dist below), so the
        # risk stays 1 R; the trade is judged by the formula alone (TP1 ahead, positive expectancy at that price)
        elif d * (lv['tp1'] - fill_est) <= 0 and s.levels.get('rr_tp1') is not None:
            reject = f"BingX {fill_est:.6g} already beyond TP1 {lv['tp1']:.6g}"
        elif s.levels.get('rr_tp1') is not None:
            from strategies.geometry import cost_of
            fee = cost_of(fill_est, (s.sig or {}).get('volume_24h'), s.symbol)
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
        # sized from BingX's own bid / ask: the plan's entry understated the risk by the spread (WLD 2026-10-02: -1.45R)
        stop_dist = abs(fill_est - lv['sl'])
        if balance <= 0 or stop_dist <= 0:
            return
        risk_usd = balance * cfg.risk_pct / 100
        if (s.sig or {}).get('small_cap'):
            # eng-99: a small cap ($1-10M a day): wider spread and slippage, the demo's thin book (1000PEPE's stop
            # filled 1.6% beyond its price) - a fraction of the usual risk
            risk_usd *= CONFIG.exchange.smallcap_risk_mult
        risk_usd *= self.regime_mult(s)
        n = (getattr(s, 'plan', None) or {}).get('turtle_n')
        # eng-91: a Turtle unit risks risk_pct at its 2N stop like every other trade (the Turtles' 1% per N made the 2N
        # stop cost 2%: twice any other card, and 5-7 correlated breakouts at once were 10%+ of the account)
        # an averaging plan (one more unit at half the way to the stop) risks 1.5 units: each unit is sized so the
        # whole position risks risk_pct
        risk_usd /= float(s.levels.get('risk_units') or 1.0)
        # eng-91: the round trip's costs (fees + slippage by the coin's liquidity) inside the sized distance - sized on the
        # bare stop distance a stop-out cost -1.2..-1.5R (live HBAR, ACE, TIA)
        from strategies.geometry import cost_of
        fee = cost_of(fill_est, (s.sig or {}).get('volume_24h'), s.symbol)
        no_stop = bool((getattr(s, 'plan', None) or {}).get('no_stop'))
        # eng-127: a system without a stop (Connors: "stops hurt") - the 'stop' is only the R unit (1 daily ATR, the
        # Turtles' N sizing) and the position runs at 1x, so the account carries it to any price without a liquidation
        leverage = 1 if no_stop else cfg.max_leverage
        qty = min(risk_usd / (stop_dist + fee), balance * leverage / lv['entry'], cfg.max_notional_usd / lv['entry'])
        if n:
            # eng-55: the full pyramid (turtle_max_units units) must fit the notional cap - a smaller unit (a lower risk
            # per N, the same for every unit) instead of a first unit of full size and the rest cut off
            fit = cfg.max_notional_usd / (lv['entry'] * CONFIG.strategies.turtle_max_units)
            if qty > fit:
                logger.info(f"Demo: {symbol} Turtle unit {qty:.6g} -> {fit:.6g} so {CONFIG.strategies.turtle_max_units} "
                            f"units fit ${cfg.max_notional_usd:,.0f} (risk at the stop {cfg.risk_pct * fit / qty:.2f}%)")
                qty = fit
        qty = float(ex.amount_to_precision(symbol, qty))
        min_qty = ((ex.markets[symbol].get('limits') or {}).get('amount') or {}).get('min') or 0
        if qty <= 0 or qty < min_qty:
            logger.info(f"Demo: {symbol} size {qty} below the minimum {min_qty}")
            return
        try:
            await ex.set_leverage(leverage, symbol, {'side': 'BOTH'})   # one-way mode: BingX needs the side
        except Exception as e:
            errors.report('executor._open', e, f"Demo leverage {symbol}")
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
        # the exits use what was FILLED: a stop for the ordered size failed on a partial fill (live INJ 2026-10-03:
        # 'order size must be less than the available amount of 529', the position sat without a stop)
        qty = float(order.get('filled') or 0) or qty
        trade = {'card_id': card_id, 'symbol': symbol, 'setup': s.group_key, 'strategy': s.mode, 'direction': d,
                 'opened_ms': int(time.time() * 1000), 'entry_plan': lv['entry'], 'entry_fill': fill, 'qty': qty,
                 'sl': lv['sl'], **{k: (None if (getattr(s, 'plan', None) or {}).get('no_tp') else lv[k])
                                    for k in ('tp1', 'tp2', 'tp3')},     # no_tp: placeholders are no targets
                 'risk_usd': qty * abs(fill - lv['sl'])}
        try:
            if not no_stop:
                await ex.create_order(symbol, 'market', exit_side, qty, None,
                                      {'stopLossPrice': float(ex.price_to_precision(symbol, lv['sl'])), 'reduceOnly': True,
                                       'workingType': 'MARK_PRICE'})
        except Exception as e:
            # never an unprotected position: recorded and closed at market
            trade['id'] = self._insert(trade)
            logger.warning(f"Demo ENTRY {symbol}: stop not placed ({e!r}): closed at market")
            await self._close(trade, 'NO_STOP', None)
            return
        plan = getattr(s, 'plan', None) or {}
        trade['id'] = self._insert(trade)
        trade['unit_qty'], trade['scale'] = qty, scale          # in memory only (the pyramid's unit, BingX's price scale)
        self._set_basis(trade['id'], basis)
        self.open[card_id] = trade
        await self._place_tps(trade, self.exit_parts(ex, trade, qty, bool(plan.get('trail_after_tp1')),
                                                     bool(plan.get('no_tp'))), min_qty)
        logger.info(f"Demo ENTRY {symbol} {s.group_key} {'long' if d > 0 else 'short'} {qty} @ {fill:.6g}, "
                    f"SL {lv['sl']:.6g}, risk ${trade['risk_usd']:.2f}")

    # ------------------------------------------------------------------ resting limit entries (eng-46)

    @staticmethod
    def wait_key(s) -> str:
        return f"{s.symbol}|{s.group_key}|c{int(s.created)}"

    @staticmethod
    def is_limit_plan(s) -> bool:
        """
        Plans whose source enters with a resting limit at a price known in advance (trigger 'touch'). eng-58: ICT's
        limits (sweep CE, continuation OTE) rest only inside the London / New York kill zones - outside them the card
        would veto the fill ('killzone'), so the limit is cancelled there (the setup lives within its session).
        """
        if CONFIG.executor.touch_confirm_close:
            return False                 # eng-105: touch plans enter at a confirming close (market), no resting limit
        if not (bool(s.plan) and s.plan.get('trigger') == 'touch'):
            return False
        from signal_book import ict_gated
        if ict_gated(s.mode, s.group_key):
            from strategies.maniac import in_session
            return in_session(int(time.time() * 1000), tuple(CONFIG.strategies.smt_session))
        return True

    async def sync_limits(self, cards) -> None:
        """
        Every waiting touch card gets a limit order on BingX at its entry line (carried over by the current price
        ratio); a card that ended without an entry gets it cancelled. A zone Binance touched but BingX did not is then
        simply not filled - the trade is the venue's, not Binance's.
        """
        if not self.enabled:
            return
        alive = set()
        async with self._lock:
            for s in cards:
                key = self.wait_key(s)
                alive.add(key)
                if key in self.pending:
                    continue
                try:
                    await self._place_limit(key, s)
                except Exception as e:
                    logger.warning(f"Demo limit {s.symbol} {s.group_key}: {e!r}")
                    self.pending[key] = {'skip': True, 'reason': repr(e)[:200]}
            for key in [k for k, p in self.pending.items() if k not in alive and not p.get('entered')]:
                await self._cancel_limit(key, 'the card ended without an entry')

    def _save_pending(self) -> None:
        try:
            with open(self.pending_path, 'w', encoding='utf-8') as f:
                json.dump(self.pending, f)
        except OSError as e:
            errors.report('executor._save_pending', e, "Demo pending state")

    async def _place_limit(self, key: str, s) -> None:
        from strategies.geometry import entry_levels
        d, plan = s.direction, s.plan
        if self.risk_limit() is not None:
            return                                   # eng-58: the day's risk rules - no new resting limit (retried later)
        coin = s.symbol.split('/')[0].replace('1000', '')
        if any(t['symbol'].split('/')[0].replace('1000', '') == coin for t in self.open.values()) or                 any(p.get('symbol', '').split('/')[0].replace('1000', '') == coin for p in self.pending.values()
                    if not p.get('skip')):
            # BingX nets a coin's orders into one position: one trade or resting limit per coin
            self.pending[key] = {'skip': True, 'reason': 'the coin is held / has a resting limit'}
            return
        same = sum(1 for p in self.pending.values() if not p.get('skip') and p.get('direction') == d) + \
            sum(1 for t in self.open.values() if t.get('direction') == d and t.get('strategy') != 'breakout')
        if same >= CONFIG.strategies.crowd_max:
            # eng-51: open trades + resting limits in one direction are one correlated bet - at most crowd_max (not
            # marked: the card gets its limit once a slot frees)
            return
        line = plan['zone_hi'] if d > 0 else plan['zone_lo']
        levels = entry_levels(plan, line, None, d)
        if not levels or levels.get('low_rr'):
            self.pending[key] = {'skip': True, 'reason': 'no plan / low R:R at the line'}
            return
        binance_now = float(s.last_price or line)
        symbol, scale = await self._market_of(s.symbol, binance_now)
        if symbol is None:
            self.pending[key] = {'skip': True, 'reason': str(scale)}
            return
        quote = getattr(self, '_quote', None) or {}
        ratio = float(quote.get('last') or binance_now * scale) / binance_now
        lv = {k: levels[k] * ratio for k in ('entry', 'sl', 'tp1', 'tp2', 'tp3')}
        ex = await self._exchange()
        cfg = CONFIG.executor
        balance = min(await self._balance(), cfg.account_usd)
        stop_dist = abs(lv['entry'] - lv['sl'])
        if balance <= 0 or stop_dist <= 0:
            self.pending[key] = {'skip': True, 'reason': 'no balance / stop'}
            return
        risk_usd = balance * cfg.risk_pct / 100 / float(levels.get('risk_units') or 1.0)
        if (s.sig or {}).get('small_cap'):
            risk_usd *= CONFIG.exchange.smallcap_risk_mult          # eng-99
        risk_usd *= self.regime_mult(s)                             # eng-100
        from strategies.geometry import cost_of
        fee = cost_of(lv['entry'], (s.sig or {}).get('volume_24h'), s.symbol)         # eng-91: costs inside the sized distance
        qty = min(risk_usd / (stop_dist + fee), balance * cfg.max_leverage / lv['entry'], cfg.max_notional_usd / lv['entry'])
        qty = float(ex.amount_to_precision(symbol, qty))
        min_qty = ((ex.markets[symbol].get('limits') or {}).get('amount') or {}).get('min') or 0
        if qty <= 0 or qty < min_qty:
            self.pending[key] = {'skip': True, 'reason': f'size {qty} below the minimum'}
            return
        try:
            await ex.set_leverage(cfg.max_leverage, symbol, {'side': 'BOTH'})   # one-way mode: BingX needs the side
        except Exception as e:
            errors.report('executor._place_limit', e, f"Demo leverage {symbol}")
        price = float(ex.price_to_precision(symbol, lv['entry']))
        order = await ex.create_order(symbol, 'limit', 'buy' if d > 0 else 'sell', qty, price)
        self.pending[key] = {'order_id': order['id'], 'symbol': symbol, 'qty': qty, 'lv': lv, 'scale': ratio,
                             'basis': ratio / scale - 1, 'setup': s.group_key, 'strategy': s.mode, 'direction': d,
                             'placed_ms': int(time.time() * 1000), 'risk_usd': qty * stop_dist,
                             'trail': bool(plan.get('trail_after_tp1')), 'no_tp': bool(plan.get('no_tp'))}
        self._save_pending()
        logger.info(f"Demo LIMIT {symbol} {s.group_key} {'buy' if d > 0 else 'sell'} {qty} @ {price:.6g} "
                    f"(Binance line {line:.6g}, basis {ratio / scale - 1:+.3%}), SL {lv['sl']:.6g}")

    async def _cancel_limit(self, key: str, why: str, record: bool = False) -> None:
        p = self.pending.get(key)
        if not p or p.get('skip'):
            self.pending.pop(key, None)
            return
        ex = await self._exchange()
        try:
            await ex.cancel_order(p['order_id'], p['symbol'])
        except Exception as e:
            errors.report('executor._cancel_limit', e, f"Demo cancel limit {p['symbol']}")
        # the cancel may fail or come after a fill (live ARB / CAP 2026-10-02: 'cancelled' limits filled and sat
        # without a stop): the order's final state decides
        try:
            o = await ex.fetch_order(p['order_id'], p['symbol'])
        except Exception as e:
            logger.warning(f"Demo limit {p['symbol']}: state unknown after the cancel ({e!r}), retried next minute")
            return
        if o.get('status') not in ('canceled', 'cancelled', 'closed', 'expired', 'rejected'):
            logger.warning(f"Demo limit {p['symbol']}: still {o.get('status')} after the cancel, retried next minute")
            return
        filled = float(o.get('filled') or 0)
        self.pending.pop(key, None)
        self._save_pending()
        if filled > 0:
            trade = self._limit_trade(key, p, float(o.get('average') or o.get('price') or p['lv']['entry']), filled)
            logger.warning(f"Demo limit {p['symbol']} {p['setup']} was filled ({filled}) though its card ended "
                           f"({why}): closed at market")
            await self._close(trade, 'LATE_FILL', None)
            return
        logger.info(f"Demo: limit {p['symbol']} {p['setup']} cancelled: {why}")
        if record:
            self._insert({'card_id': p.get('card_id') or key, 'symbol': p['symbol'], 'setup': p['setup'],
                          'strategy': p['strategy'], 'direction': p['direction'], 'opened_ms': p['placed_ms'],
                          'entry_plan': p['lv']['entry'], 'error': why, 'closed_ms': int(time.time() * 1000),
                          'close_reason': 'NOT_FILLED'})

    async def check_limits(self) -> None:
        """A filled limit becomes a trade (stop + take-profits placed); one the card entered on Binance but BingX did
        not fill within limit_wait_min is cancelled and recorded NOT_FILLED."""
        ex = await self._exchange()
        now = time.time() * 1000
        for key, p in list(self.pending.items()):
            if p.get('skip'):
                continue
            try:
                o = await ex.fetch_order(p['order_id'], p['symbol'])
            except Exception as e:
                errors.report('executor.check_limits', e, f"Demo limit status {p['symbol']}")
                continue
            filled = float(o.get('filled') or 0)
            if 0 < filled < 0.999 * p['qty'] and o.get('status') != 'closed':
                # eng-85: a partly filled limit sat without a stop until limit_wait_min: the rest is cancelled and the
                # filled part becomes the trade (its stop / targets for the filled size)
                try:
                    await ex.cancel_order(p['order_id'], p['symbol'])
                except Exception as e:
                    errors.report('executor.check_limits', e, f"Demo cancel partial limit {p['symbol']}")
                try:
                    o = await ex.fetch_order(p['order_id'], p['symbol'])
                except Exception as e:
                    errors.report('executor.check_limits', e, f"Demo partial limit status {p['symbol']}")
                    continue
                if o.get('status') not in ('canceled', 'cancelled', 'closed', 'expired', 'rejected'):
                    continue
                filled = float(o.get('filled') or 0)
                await self._limit_filled(key, p, float(o.get('average') or o.get('price') or p['lv']['entry']), filled)
                continue
            if o.get('status') == 'closed' or (filled and filled >= 0.999 * p['qty']):
                await self._limit_filled(key, p, float(o.get('average') or o.get('price') or p['lv']['entry']),
                                         filled or p['qty'])
            elif p.get('entered') and now - p['entered_ms'] > CONFIG.executor.limit_wait_min * 60_000:
                await self._cancel_limit(key, f"Binance touched the line, BingX did not fill within "
                                              f"{CONFIG.executor.limit_wait_min} min", record=True)

    def _limit_trade(self, key: str, p: Dict, fill: float, qty: float) -> Dict:
        """The demo row of a filled limit, written before its exits are placed (a failure there still leaves it)."""
        lv = p['lv']
        trade = {'card_id': p.get('card_id') or key, 'symbol': p['symbol'], 'setup': p['setup'],
                 'strategy': p['strategy'], 'direction': p['direction'], 'opened_ms': int(time.time() * 1000),
                 'entry_plan': lv['entry'], 'entry_fill': fill, 'qty': qty, 'sl': lv['sl'], 'tp1': lv['tp1'],
                 'tp2': lv['tp2'], 'tp3': lv['tp3'], 'risk_usd': qty * abs(fill - lv['sl'])}
        trade['id'] = self._insert(trade)
        trade['unit_qty'], trade['scale'] = qty, p['scale']
        trade['from_limit'] = True
        self._set_basis(trade['id'], p['basis'])
        return trade

    async def _limit_filled(self, key: str, p: Dict, fill: float, qty: float) -> None:
        ex = await self._exchange()
        symbol, d, lv = p['symbol'], p['direction'], p['lv']
        exit_side = 'sell' if d > 0 else 'buy'
        trade = self._limit_trade(key, p, fill, qty)
        self.pending.pop(key, None)
        self._save_pending()
        try:
            await ex.create_order(symbol, 'market', exit_side, qty, None,
                                  {'stopLossPrice': float(ex.price_to_precision(symbol, lv['sl'])), 'reduceOnly': True,
                                   'workingType': 'MARK_PRICE'})
        except Exception as e:
            # found filled only after price ran through the stop (live CAP 2026-10-02): out at market, never unprotected
            logger.warning(f"Demo LIMIT FILLED {symbol}: stop not placed ({e!r}): closed at market")
            await self._close(trade, 'SL', None)
            return
        self.open[trade['card_id']] = trade
        min_qty = ((ex.markets[symbol].get('limits') or {}).get('amount') or {}).get('min') or 0
        await self._place_tps(trade, self.exit_parts(ex, trade, qty, bool(p.get('trail')), bool(p.get('no_tp'))), min_qty)
        logger.info(f"Demo LIMIT FILLED {symbol} {p['setup']} {qty} @ {fill:.6g}, SL {lv['sl']:.6g}")

    async def close_untracked(self) -> None:
        """Safety net: a BingX position no trade or resting limit of ours owns (a lost fill) is closed at market."""
        ex = await self._exchange()
        mine = {t['symbol'] for t in self.open.values()} | {p.get('symbol') for p in self.pending.values()
                                                             if not p.get('skip')}
        for pos in await ex.fetch_positions():
            qty = float(pos.get('contracts') or 0)
            if not qty or pos['symbol'] in mine:
                continue
            d = 1 if pos.get('side') == 'long' else -1
            entry = float(pos.get('entryPrice') or 0)
            trade = {'card_id': f"{pos['symbol']}|UNTRACKED|{int(time.time())}", 'symbol': pos['symbol'],
                     'setup': 'UNTRACKED', 'strategy': None, 'direction': d,
                     'opened_ms': int(time.time() * 1000),        # only the closing fill counts (older fills of the coin are other trades)
                     'entry_plan': entry, 'entry_fill': entry, 'qty': qty,
                     'error': 'a BingX position no card owned (lost limit fill): closed at market'}
            trade['id'] = self._insert(trade)
            logger.warning(f"Demo: untracked BingX position {pos['symbol']} {pos.get('side')} {qty}: closed at market")
            await self._close(trade, 'UNTRACKED', None)

    async def _dedupe_stops(self) -> None:
        """eng-98: one stop per open trade on BingX. Before eng-85 a failed / repeated restop could leave an older stop
        resting beside the live one (live HYPE 14.10: 12 @ 91.47 beside 24 @ 89.72) - it would later cut a new position
        of the coin. The stop nearest the trade's own stop stays, the others are cancelled."""
        ex = await self._exchange()
        for trade in list(self.open.values()):
            stops = [o for o in await ex.fetch_open_orders(trade['symbol']) if self._is_stop(o)]
            if len(stops) < 2:
                continue
            ref = float(trade.get('sl') or 0)
            px = lambda o: float((o.get('info') or {}).get('stopPrice') or o.get('stopPrice') or o.get('triggerPrice') or 0)  # noqa: E731
            keep = min(stops, key=lambda o: abs(px(o) - ref)) if ref else max(stops, key=lambda o: o.get('timestamp') or 0)
            for o in stops:
                if o is keep:
                    continue
                try:
                    await ex.cancel_order(o['id'], trade['symbol'])
                    logger.warning(f"Demo {trade['symbol']}: extra stop {px(o):.6g} cancelled (kept {px(keep):.6g})")
                except Exception as e:
                    errors.report('executor._dedupe_stops', e, f"Demo extra stop {trade['symbol']}")

    async def on_restop(self, s) -> None:
        """eng-58: the card trailed its stop (after TP1: the entry, then the EMA20): the remaining position's stop is
        moved on BingX (its TP1 half is already out, so no take-profit is left to re-place)."""
        if not self.enabled or not s.entered_at:
            return
        card_id = f"{s.symbol}|{s.group_key}|{int(s.entered_at)}"
        # eng-84: a trade entered by a resting limit is keyed by the waiting card (c<created>) - it was never restopped
        trade = self.open.get(card_id) or self.open.get(f"{s.symbol}|{s.group_key}|c{int(s.created)}")
        if trade is None or (getattr(s, 'plan', None) or {}).get('no_stop'):
            return
        async with self._lock:
            try:
                ex = await self._exchange()
                symbol, d = trade['symbol'], trade['direction']
                left = await self._position_qty(symbol)
                if left <= 0:
                    return
                scale = float(trade.get('scale') or 0.0)
                if not scale and trade.get('entry_plan') and s.levels.get('entry'):
                    scale = float(trade['entry_plan']) / float(s.levels['entry'])
                    trade['scale'] = scale
                scale = scale or 1.0
                # eng-85: the new stop first, then the old stop(s) by id - the cancel-all first left the position naked
                # whenever the new stop failed, and took TP2 / TP3 of the thirds plans with it for good
                new = await self._place_stop(symbol, d, left, s.levels['sl'] * scale)
                await self._cancel_orders(symbol, keep=new.get('id'), stops_only=True)
                trade['sl'] = s.levels['sl'] * scale
                logger.info(f"Demo RESTOP {symbol}: stop {s.levels['sl'] * scale:.6g} for {left}")
            except Exception as e:
                logger.warning(f"Demo restop {s.symbol}: {e!r}")

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
                # BingX's price ratio to Binance (contract scale x basis) lives in memory only: after a restart it is
                # the BingX plan entry over the card's Binance entry (1.0 put a 1000-unit contract's stop 1000x off)
                scale = float(trade.get('scale') or 0.0)
                if not scale and trade.get('entry_plan') and s.levels.get('entry'):
                    scale = float(trade['entry_plan']) / float(s.levels['entry'])
                    trade['scale'] = scale
                scale = scale or 1.0
                # eng-85: the whole position's stop first; only then the old orders go (the cancel-all first left the
                # grown position without any stop when the new one failed)
                try:
                    new = await self._place_stop(symbol, d, total, s.levels['sl'] * scale)
                except Exception as e:
                    logger.warning(f"Demo ADD {symbol}: stop for {total} not placed ({e!r}): closed at market")
                    await self._close(trade, 'NO_STOP', None)
                    return
                await self._cancel_orders(symbol, keep=new.get('id'))
                trade['sl'] = s.levels['sl'] * scale
                if not ((getattr(s, 'plan', None) or {}).get('no_tp')):
                    # an averaging add (pump strategies): the three take-profits again, for the whole position
                    for k in (1, 2, 3):
                        trade[f'tp{k}'] = s.levels[f'tp{k}'] * scale
                    third = float(ex.amount_to_precision(symbol, total / 3))
                    await self._place_tps(trade, zip((1, 2, 3), (third, third,
                                                                 float(ex.amount_to_precision(symbol, total - 2 * third)))))
                with sqlite3.connect(self.db_path) as c:
                    c.execute("UPDATE demo_trades SET qty = ?, entry_fill = ?, sl = ? WHERE id = ?",
                              (total, trade['entry_fill'], s.levels['sl'] * scale, trade['id']))
                logger.info(f"Demo ADD {symbol} unit {len(s.units)}: +{unit} @ {fill:.6g}, position {total}, "
                            f"stop {s.levels['sl'] * scale:.6g}")
            except Exception as e:
                logger.warning(f"Demo add-unit failed for {trade['symbol']}: {e!r}")

    async def on_finish(self, s) -> None:
        if not self.enabled:
            return
        if self.wait_key(s) in self.pending and not s.entered_at:
            async with self._lock:
                await self._cancel_limit(self.wait_key(s), f"the card ended {s.status} without an entry")
            return
        if not s.entered_at:
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
                self._set_exit_ref(trade['id'], s.finish_price)
                await self._close(trade, s.status, s.final_r, passive=True)
            except Exception as e:
                logger.warning(f"Demo close failed for {trade['symbol']}: {e!r}")

    async def _position_qty(self, symbol: str) -> float:
        ex = await self._exchange()
        for p in await ex.fetch_positions([symbol]):
            if p.get('symbol') == symbol and p.get('contracts'):
                return float(p['contracts'])
        return 0.0

    def _set_exit_ref(self, trade_id: int, price: Optional[float]) -> None:
        """The card's own exit price (Binance) next to the demo's fill: the demo lost ~0.15R a trade to the journal,
        almost all on the card-driven market closes (eng-74) - measured, not guessed."""
        with sqlite3.connect(self.db_path) as c:
            try:
                c.execute("ALTER TABLE demo_trades ADD COLUMN exit_ref REAL")
            except sqlite3.OperationalError:
                pass
            c.execute("UPDATE demo_trades SET exit_ref = ? WHERE id = ?", (price, trade_id))

    async def _close(self, trade: Dict, reason: str, journal_r: Optional[float], passive: bool = False) -> None:
        ex = await self._exchange()
        symbol, d = trade['symbol'], trade['direction']
        if not passive:
            try:
                await ex.cancel_all_orders(symbol)
            except Exception as e:
                errors.report('executor._close', e, f"Demo cancel {symbol}")
        else:
            # eng-85: the stop rests while the passive limit works (the cancel-all first left ~15s without one); only
            # the take-profits go, the stop is cancelled right before the market remainder below
            try:
                for o in await ex.fetch_open_orders(symbol):
                    if not self._is_stop(o):
                        try:
                            await ex.cancel_order(o['id'], symbol)
                        except Exception as e:
                            errors.report('executor._close', e, f"Demo cancel TP {symbol}")
            except Exception as e:
                errors.report('executor._close', e, f"Demo cancel {symbol}")
        left = await self._position_qty(symbol)
        if left > 0 and passive:
            # a card-driven exit (band / session / time / trail - no stop urgency): a reduce-only limit at the touch
            # first (the VST spread reached 0.4-3%: a market order paid all of it), the rest at market after 15s
            side = 'sell' if d > 0 else 'buy'
            try:
                t = await ex.fetch_ticker(symbol)
                px = float((t.get('ask') if d > 0 else t.get('bid')) or t.get('last'))
                order = await ex.create_order(symbol, 'limit', side, left, px, {'reduceOnly': True})
                for _ in range(5):
                    await asyncio.sleep(3)
                    if await self._position_qty(symbol) == 0:
                        break
                try:
                    await ex.cancel_order(order['id'], symbol)
                except Exception as e:                  # filled / gone: the position check below decides
                    logger.debug(f"Demo cancel passive close {symbol}: {e!r}")
            except Exception as e:
                # eng-98: 109400 'order not exist' / 101290 'reduce only': BingX's own stop closed the position first
                # (the card saw the stop on Binance at the same time) - the position check below records it
                if '109400' in str(e) or '101290' in str(e):
                    logger.debug(f"Demo passive close {symbol}: {e!r}")
                else:
                    errors.report('executor._close', e, f"Demo passive close {symbol}")
            left = await self._position_qty(symbol)
            try:
                await ex.cancel_all_orders(symbol)       # the stop, now that the market remainder follows
            except Exception as e:
                errors.report('executor._close', e, f"Demo cancel {symbol}")
        if left > 0:
            side = 'sell' if d > 0 else 'buy'
            try:
                await ex.create_order(symbol, 'market', side, left, None, {'reduceOnly': True})
            except Exception as e:
                if '101290' in str(e) and await self._position_qty(symbol) == 0:
                    # BingX's own stop / target filled between the position check and this order (BAT 2026-10-05
                    # 04:58: both stops at 0.1022, 'Reduce Only order can only decrease the position'): the exchange
                    # closed it, recorded as such
                    reason = 'EXCHANGE'
                elif '102202' in str(e):
                    # VST's thin book: the market order would fill beyond BingX's price band (102202). A reduce-only limit
                    # at the touch instead; the trade stays open, the next pass re-places it at the fresh price
                    t = await ex.fetch_ticker(symbol)
                    px = float((t.get('bid') if d > 0 else t.get('ask')) or t.get('last'))
                    await ex.create_order(symbol, 'limit', side, left, px, {'reduceOnly': True})
                    if symbol not in self._band_warned:
                        self._band_warned.add(symbol)
                        logger.warning(f"Demo: {symbol} market close rejected by BingX's price band: reduce-only limit "
                                       f"{left} @ {px} (re-placed each pass until filled)")
                    # kept open (an UNTRACKED row was not in self.open: each 5-min check would insert another row): the
                    # reconcile loop's orphan path re-places the limit and finalizes once the position is 0
                    self.open.setdefault(trade['card_id'], trade)
                    return
                else:
                    raise
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
            # eng-91: only fills after this trade's entry - the 5s margin let the previous trade's exit on the same
            # coin into this one's average (_refinalize already filtered it)
            exits = [f for f in fills if f.get('side') == exit_side and f.get('price')
                     and (f.get('timestamp') or 0) > trade['opened_ms'] - 1_000]
            if exits:
                break
            await asyncio.sleep(5)
        qty, entry = float(trade.get('qty') or 0), float(trade.get('entry_fill') or 0)
        weight = sum(f['amount'] for f in exits)
        exit_avg = sum(f['price'] * f['amount'] for f in exits) / weight if weight else None
        if exit_avg is None or not qty or not entry:
            # the fills list can lag a close (or the API is unreachable): retried by reconcile_loop (_refinalize)
            logger.warning(f"Demo {reason} {trade['symbol']}: no exit fill found yet, retried later")
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
            if pnl is None and qty and entry:
                c.execute("UPDATE demo_trades SET error = ? WHERE id = ?", (self.FILL_PENDING, trade['id']))
        self.open.pop(trade['card_id'], None)
        if pnl is not None:
            logger.info(f"Demo {reason} {trade['symbol']}: {pnl:+.2f} USD ({pnl / risk if risk else 0:+.2f}R)")

    FILL_PENDING = 'exit fill pending'

    async def _refinalize(self) -> None:
        """Closed trades whose exit fill was not listed at the close (1000PEPE 2026-10-06 11:07, the link failing):
        their result from BingX's fills, retried for 3 days."""
        with sqlite3.connect(self.db_path) as c:
            rows = c.execute("SELECT id, symbol, direction, opened_ms, closed_ms, qty, entry_fill, risk_usd FROM demo_trades "
                             "WHERE error = ? AND pnl_usd IS NULL AND closed_ms > ?",
                             (self.FILL_PENDING, int(time.time() * 1000) - 3 * 86_400_000)).fetchall()
        if not rows:
            return
        ex = await self._exchange()
        for tid, symbol, d, opened, closed, qty, entry, risk in rows:
            side = 'sell' if d > 0 else 'buy'
            fills = await ex.fetch_my_trades(symbol, since=opened - 5_000)
            exits = [f for f in fills if f.get('side') == side and f.get('price') and f.get('timestamp', 0) > opened]
            weight = sum(f['amount'] for f in exits)
            if not weight:
                continue
            exit_avg = sum(f['price'] * f['amount'] for f in exits) / weight
            fees = CONFIG.journal.fee_round_trip / 2 * (entry + exit_avg) * qty
            pnl = d * (exit_avg - entry) * qty - fees
            with sqlite3.connect(self.db_path) as c:
                c.execute("UPDATE demo_trades SET exit_avg = ?, fees_usd = ?, pnl_usd = ?, r = ?, error = NULL WHERE id = ?",
                          (exit_avg, fees, pnl, pnl / risk if risk else None, tid))
            logger.info(f"Demo result recovered {symbol}: {pnl:+.2f} USD ({pnl / risk if risk else 0:+.2f}R)")

    async def reconcile_loop(self, running) -> None:
        """Finalize demo trades the exchange closed on its own (stop / last target)."""
        while running():
            await asyncio.sleep(60)
            if not self.enabled:
                continue
            if self.pending:
                async with self._lock:
                    try:
                        await self.check_limits()
                    except Exception as e:
                        logger.warning(f"Demo limits: {e!r}")
            if time.time() - getattr(self, '_untracked_at', 0) > 300:
                self._untracked_at = time.time()
                async with self._lock:
                    try:
                        await self.close_untracked()
                    except Exception as e:
                        logger.warning(f"Demo untracked check: {e!r}")
                    try:
                        await self._refinalize()
                    except Exception as e:
                        logger.warning(f"Demo result recovery: {e!r}")
                    try:
                        await self._dedupe_stops()
                    except Exception as e:
                        logger.warning(f"Demo stop check: {e!r}")
            if not self.open:
                continue
            async with self._lock:
                for trade in list(self.open.values()):
                    try:
                        age_ms = time.time() * 1000 - trade['opened_ms']
                        if age_ms > 120_000 and not self.card_is_open(trade['card_id']):
                            if (trade.get('from_limit') or str(trade.get('card_id', '')).rsplit('|', 1)[-1].startswith('c')) \
                                    and age_ms < ORPHAN_LIMIT_HOLD_MS:
                                # eng-84: BingX filled the resting limit, then the card's check of the touch vetoed it
                                # (against_btc ...) and expired it: the position was closed at market at a loss while its
                                # stop and targets already rested on BingX (live SOL / DOGE PO3: closed -0.5R, then went
                                # to TP3). A filled limit keeps its exchange stop / targets; only a stale one is closed
                                pass
                            else:
                                logger.info(f"Demo: {trade['symbol']} has no open card any more: closing the orphan")
                                await self._close(trade, 'ORPHAN', None)
                                continue
                        if await self._position_qty(trade['symbol']) == 0:
                            await self._exchange()
                            try:
                                await self.ex.cancel_all_orders(trade['symbol'])
                            except Exception as e:
                                errors.report('executor.cancel_after_flat', e, f"{trade['symbol']}: its stop / targets may still rest on BingX")
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
