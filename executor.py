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
import math
import os
import sqlite3
import time
from typing import Dict, List, Optional

from config import CONFIG
from storage import atomic_write

logger = logging.getLogger(__name__)

BINGX_ALIAS = {'XAU': 'NCCOGOLD2USD/USDT:USDT', 'XAG': 'NCCOXAG2USD/USDT:USDT',
               'CL': 'NCCO1OILWTI2USD/USDT:USDT', 'BZ': 'NCCO1OILBRENT2USD/USDT:USDT'}

# eng-84: a limit-filled trade whose card ended keeps its exchange stop / targets this long, then is closed
ORPHAN_LIMIT_HOLD_MS = 24 * 3600_000
# eng-144: a position without a card rides its exchange stop / targets at most this long, then it is closed at market
ORPHAN_EXCHANGE_HOLD_MS = 3 * 24 * 3600_000
# eng-86: no market entry when BingX's price already ran this share of the planned risk past the plan's entry (laptop
# demo journal: a chase >= 0.25R cost -0.64R against the journal, n=15; < 0.25R -0.07R; live GRASS +3.6%: -2.32R)
CHASE_MAX_R = float('inf')       # eng-113: removed (the size follows the price)
# the day's risk rules at or above this are 'off' (config.local.toml set them to 1e6 to switch them off: risk_limit then
# read the whole table on every entry - LIMIT 1000000)
LIMIT_OFF_AT = 100_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS demo_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT, card_id TEXT, symbol TEXT, setup TEXT, strategy TEXT, direction INTEGER,
    opened_ms INTEGER, entry_plan REAL, entry_fill REAL, qty REAL, sl REAL, tp1 REAL, tp2 REAL, tp3 REAL,
    risk_usd REAL, closed_ms INTEGER, close_reason TEXT, exit_avg REAL, fees_usd REAL, pnl_usd REAL, r REAL,
    journal_r REAL, error TEXT)
"""


UNKNOWN_HOLD_SEC = 900.0     # a coin stays closed to new entries this long after an entry whose outcome is unknown


class EntryUnknown(Exception):
    """audit C02: a market entry whose outcome could not be read back (lost reply + unreadable exchange)."""


def _finite(x) -> Optional[float]:
    """x as a finite float, else None (None, '', non-numeric, NaN, +-inf): an exchange field never raises here."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _positive(x) -> Optional[float]:
    """x as a finite float > 0, else None."""
    v = _finite(x)
    return v if v is not None and v > 0 else None


def _coin(symbol: str) -> str:
    """The coin of a ccxt symbol, its unit multiplier dropped (audit N05: the shared parser, not '.replace(1000)')."""
    from symbols import split_base
    return split_base((symbol or '').split('/')[0])[0]


def credentials() -> tuple:
    """(key, secret): BINGX_API_KEY / BINGX_API_SECRET from the environment (systemd EnvironmentFile, mode 600)
    first, then config.local.toml [executor] - the key out of a file that sits next to the code."""
    cfg = CONFIG.executor
    return (os.environ.get('BINGX_API_KEY') or cfg.api_key, os.environ.get('BINGX_API_SECRET') or cfg.api_secret)


class DemoExecutor:
    def __init__(self, db_path: str = 'demo_trades.db'):
        cfg = CONFIG.executor
        self.enabled = bool(cfg.enabled and all(credentials()))
        self.db_path = db_path
        self._flat_seen: Dict[str, int] = {}      # card id -> consecutive reconcile passes that read the position as 0
        self._finalized: Dict[str, tuple] = {}    # symbol -> (trade, time) of the last finalize (close_untracked guard)
        self._unknown_coins: Dict[str, float] = {}  # coin -> when an entry's outcome stayed UNKNOWN: held until close_untracked has had its turn
        self._short_warned: set = set()            # FILL_PENDING rows already warned as short after 6h
        self._band_warned: set = set()      # coins whose market close BingX rejected (102202): warned once
        self._quotes_seen: Dict[str, tuple] = {}   # symbol -> (BingX last, since): a VST quote that stopped moving
        self.ex = None
        self.open: Dict[str, Dict] = {}          # card id -> trade
        self._lock = asyncio.Lock()
        # audit N02: cards whose finish already came (an entry still waiting for the lock must not open them)
        self._finished_cards: set = set()
        # set by the scanner: is this card (symbol|setup|entered_at) still an open trade in the book? A card that
        # expired while the bot was down is never restored, so its finish never comes (3 demo positions stayed
        # open for 15h, 2026-10-01): the reconcile loop closes such orphans
        self.card_is_open = lambda card_id: True
        # set by the scanner: a Telegram line to the demo topic for the incidents (NO_STOP / UNTRACKED / LATE_FILL /
        # a stop re-placed by the guard) - they are failures of the order handling, not statistics
        self.alert = lambda text: None
        # resting limit entries of touch plans (Seiden's proximal line, the Silver Bullet's CE): waiting-card key ->
        # {order_id, symbol, levels in BingX prices, ...} (eng-46)
        self.pending: Dict[str, Dict] = {}
        self.pending_path = os.path.join(os.path.dirname(os.path.abspath(db_path)), 'demo_pending.json')
        self.unknown_path = os.path.join(os.path.dirname(os.path.abspath(db_path)), 'demo_unknown.json')
        try:
            # audit F01: an entry of unknown outcome holds its coin across a restart too
            with open(self.unknown_path, encoding='utf-8') as f:
                self._unknown_coins = {str(k): float(v) for k, v in json.load(f).items()}
        except (OSError, ValueError, AttributeError):
            pass
        try:
            with open(self.pending_path, encoding='utf-8') as f:
                self.pending = json.load(f)     # resting limits survive a restart (else they stay on BingX unseen)
        except (OSError, ValueError):
            pass
        self._markets_ready = False
        with sqlite3.connect(db_path) as c:
            c.execute(SCHEMA)
            c.execute("CREATE INDEX IF NOT EXISTS idx_demo_pending ON demo_trades(error, closed_ms)")
            # columns added after the first schema: migrated once here (was an ALTER TABLE on every trade)
            have = {r[1] for r in c.execute("PRAGMA table_info(demo_trades)")}
            # audit N01/N04: the entry order's id (its own fills are told from the next trade's by it) and whether the
            # entry price / size came from the exchange (1) or are a quote / the requested size (0); scale: BingX's
            # price scale (restored trades re-stop at it)
            for col, kind in (('basis', 'REAL'), ('exit_ref', 'REAL'), ('no_stop', 'INTEGER'), ('scale', 'REAL'),
                              ('entry_order', 'TEXT'), ('fill_confirmed', 'INTEGER'), ('funding_usd', 'REAL'),
                              ('close_pending_reason', 'TEXT'), ('close_pending_r', 'REAL'),
                              ('from_limit', 'INTEGER'), ('trail', 'INTEGER'), ('no_tp', 'INTEGER'),
                              ('slip_bps', 'REAL'), ('latency_ms', 'INTEGER'), ('leverage', 'INTEGER'),
                              ('logic_version', 'TEXT'), ('partial_done', 'INTEGER')):
                if col not in have:
                    c.execute(f"ALTER TABLE demo_trades ADD COLUMN {col} {kind}")
            # scale: the Binance -> BingX price ratio on_restop / on_add convert with (1000FLOKI -> FLOKI is 0.001;
            # without it a restored trade's new stop went out at scale 1); rows from before the column: entry_plan
            c.row_factory = sqlite3.Row
            for row in c.execute("SELECT * FROM demo_trades WHERE closed_ms IS NULL"):
                trade = dict(row)
                if trade.get('close_pending_reason') is not None:
                    trade['close_pending'] = [trade['close_pending_reason'], trade['close_pending_r']]
                self.open[trade['card_id']] = trade
            c.execute("CREATE INDEX IF NOT EXISTS idx_demo_entry_order ON demo_trades(symbol, entry_order)")

    # ------------------------------------------------------------------ exchange

    async def _exchange(self):
        if self.ex is None:
            import ccxt.async_support as ccxt
            key, secret = credentials()
            self.ex = ccxt.bingx({'apiKey': key, 'secret': secret, 'enableRateLimit': True,
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
        if base in BINGX_ALIAS:
            # eng-132: BingX rejects the NCCO* contracts in one-way mode (101414 'non-crypto symbol ... not support
            # openapi', XAG 15.10 and CL 15.10): NO_MARKET, not an ERROR after a round of ticker calls
            return None, 'TradFi contract: BingX openapi does not trade it (101414)'
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
            if card_id in self.open or card_id in self._finished_cards:
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
            limit = self.risk_limit() or self.strategy_killed(s.mode)
            if limit is not None:
                # eng-58: the day's risk rules (prop practice): not traded, recorded with the rule
                logger.info(f"Demo: {s.symbol} {s.group_key} skipped: {limit}")
                self._insert({'card_id': card_id, 'symbol': s.symbol, 'setup': s.group_key, 'strategy': s.mode,
                              'direction': s.direction, 'opened_ms': int(time.time() * 1000), 'error': limit,
                              'closed_ms': int(time.time() * 1000),
                              'close_reason': 'PAUSE' if limit.startswith('pause') else
                              'STRATEGY_OFF' if limit.startswith('strategy') else 'DAILY_LIMIT'})
                return
            gate = self.entry_gate(s)
            if gate is not None:
                logger.info(f"Demo: {s.symbol} {s.group_key} skipped: {gate}")
                self._insert({'card_id': card_id, 'symbol': s.symbol, 'setup': s.group_key, 'strategy': s.mode,
                              'direction': s.direction, 'opened_ms': int(time.time() * 1000), 'error': gate,
                              'closed_ms': int(time.time() * 1000),
                              'close_reason': 'SETUP_OFF' if gate.startswith('setup') else 'CLUSTER'})
                return
            coin = _coin(s.symbol)
            busy = next((t for t in self.open.values() if _coin(t['symbol']) == coin), None) or \
                next((p for p in self.pending.values() if not p.get('skip')
                      and _coin(p.get('symbol', '')) == coin), None)
            if busy is None and coin in self._unknown_coins:
                busy = {'setup': 'an entry with an unknown outcome'}   # audit C02: its order may stand on BingX
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
                unknown = isinstance(e, EntryUnknown)
                logger.warning(f"Demo entry {'UNKNOWN' if unknown else 'failed'} for {s.symbol} {s.group_key}: {e!r}")
                if unknown:
                    self._unknown_coins[coin] = time.time()
                    self._save_unknown()
                    # not 'not filled': a position that turns up is closed by close_untracked (no card owns it)
                    self.alert(f"⚠️ Демо {s.symbol}: исход входа неизвестен (биржа недоступна), проверьте позицию")
                self._insert({'card_id': card_id, 'symbol': s.symbol, 'setup': s.group_key, 'strategy': s.mode,
                              'direction': s.direction, 'opened_ms': int(time.time() * 1000), 'error': repr(e)[:300],
                              'closed_ms': int(time.time() * 1000), 'close_reason': 'UNKNOWN' if unknown else 'ERROR'})

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
            except Exception as err:
                # eng-169b (ENA 2026-10-26: 14s entry latency, price passed TP1 before it was placed, BingX 110413
                # rejected it and that part stayed open without a target): a target the price already reached is
                # taken at market, the rest of the failures keep the stop
                fail: Exception = err
                try:
                    last = float((await ex.fetch_ticker(symbol)).get('last') or 0)
                except Exception:
                    last = 0.0
                if last and d * (last - float(trade[f'tp{k}'])) >= 0:
                    try:
                        await ex.create_order(symbol, 'market', 'sell' if d > 0 else 'buy', amount, None,
                                              {'reduceOnly': True})
                        logger.info(f"Demo TP{k} {symbol}: price {last} already beyond the target, {amount} taken at market")
                        continue
                    except Exception as e2:
                        fail = e2
                errors.report('executor._place_tps', fail, f"Demo TP{k} {symbol}: the trade keeps its stop")

    @staticmethod
    def tp_parts(ex, symbol: str, qty: float, trail: bool, no_tp: bool):
        """(target index, amount) of the take-profit orders: thirds at TP1-3; eng-58 trailing plans (continuation,
        pump) half at TP1 and the rest on the card's trailing stop (RESTOP); target-less plans none."""
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
        loss_r, max_trades, pause_n = (x if 0 < x < LIMIT_OFF_AT else 0
                                       for x in (cfg.daily_loss_r, cfg.max_trades_day, cfg.pause_losses))
        if not (loss_r or max_trades or pause_n):
            return None                              # all off: no three queries per entry
        try:
            with sqlite3.connect(self.db_path) as c:
                closed = c.execute("SELECT r FROM demo_trades WHERE closed_ms >= ? AND r IS NOT NULL", (day0,)).fetchall()
                opened = c.execute("SELECT COUNT(*) FROM demo_trades WHERE opened_ms >= ? AND entry_fill IS NOT NULL",
                                   (day0,)).fetchone()[0]
                last = c.execute("SELECT r, closed_ms FROM demo_trades WHERE r IS NOT NULL ORDER BY closed_ms DESC LIMIT ?",
                                 (pause_n,)).fetchall() if pause_n else []
        except sqlite3.Error as e:
            # audit T06: limits that are ON but cannot be read block new risk (was None - the entry went through
            # unchecked)
            return f"risk limits unreadable: {e!r}"
        # eng-85: a resting limit holds a slot of the day (it fills without asking again)
        opened += sum(1 for p in self.pending.values() if not p.get('skip'))
        day_r = sum(r for (r,) in closed)
        if loss_r and day_r <= -loss_r:
            return f"daily loss limit: {day_r:+.2f}R today"
        if max_trades and opened >= max_trades:
            return f"daily trade limit: {opened} trades today"
        if pause_n and len(last) == pause_n and all(r < 0 for r, _ in last) and \
                time.time() * 1000 - last[0][1] < cfg.pause_hours * 3_600_000:
            return f"pause after {cfg.pause_losses} losses in a row"
        return None

    def entry_gate(self, s) -> Optional[str]:
        """Owner 2026-10-18: one demo entry per direction per cluster_entry_sec; demo_off_setups are not traded."""
        cfg = CONFIG.executor
        d = s.direction
        if s.group_key in cfg.demo_off_setups:
            return f"setup off on demo: {s.group_key}"
        hit = self.cluster_hit(d)
        if hit is not None:
            return f"cluster: {hit} entered {'long' if d > 0 else 'short'} within {cfg.cluster_entry_sec // 60} min"
        return None

    def cluster_hit(self, d: int) -> Optional[str]:
        """The coin of a demo entry in direction d within cluster_entry_sec: a filled trade, or a resting limit placed /
        entered in the window (it fills without asking again), else None."""
        window = CONFIG.executor.cluster_entry_sec
        if window <= 0:
            return None
        since = int((time.time() - window) * 1000)
        try:
            with sqlite3.connect(self.db_path) as c:
                row = c.execute("SELECT symbol FROM demo_trades WHERE direction = ? AND opened_ms >= ? "
                                "AND entry_fill IS NOT NULL ORDER BY opened_ms DESC LIMIT 1", (d, since)).fetchone()
        except sqlite3.Error:
            row = None
        if row is not None:
            return row[0]
        return next((p.get('symbol') for p in self.pending.values() if not p.get('skip') and p.get('direction') == d
                     and max(p.get('placed_ms') or 0, p.get('entered_ms') or 0) >= since), None)

    @staticmethod
    def _chase(s, lv: Dict, fill_est: float, d: int, n_turtle, ratio: float) -> Optional[str]:
        """eng-147: why the BingX price ran too far past the signal price for a plan without targets, else None."""
        plan = getattr(s, 'plan', None) or {}
        unit = n_turtle or plan.get('tf_atr') or plan.get('leg_atr') or plan.get('atr')
        if not unit or lv.get('entry') is None:
            return None
        k = CONFIG.executor.chase_limit_n if n_turtle else CONFIG.executor.chase_limit_atr
        ran = d * (fill_est - lv['entry']) / (unit * ratio)
        return f"BingX {fill_est:.6g} {ran:.2f} {'N' if n_turtle else 'ATR'} past the signal {lv['entry']:.6g} > {k:g}" \
            if ran > k else None

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
        n_turtle = (getattr(s, 'plan', None) or {}).get('turtle_n')
        if n_turtle:
            # review V05: the Turtles' stop is 2N from the position's OWN entry - BingX's price, not Binance's
            lv['sl'] = fill_est - d * 2 * n_turtle * ratio
        reject = None
        if d * (fill_est - lv['sl']) <= 0:
            reject = f"BingX {fill_est:.6g} already beyond the stop {lv['sl']:.6g}"
        # eng-113 (the owner): no invented chase cap - the size is recomputed at BingX's price (stop_dist below), so the
        # risk stays 1 R; the trade is judged by the formula alone (TP1 ahead, positive expectancy at that price)
        elif s.levels.get('rr_tp1') is None and self._chase(s, lv, fill_est, d, n_turtle, ratio):
            # eng-147 (the owner): a plan without targets has no R:R to re-check, so a run past the signal price is
            # capped: 0.5 N for the Turtles, 0.5 ATR of the working timeframe for the others
            reject = f"chase_limit: {self._chase(s, lv, fill_est, d, n_turtle, ratio)}"
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
            plan = s.plan or {}
            floor = CONFIG.levels.min_rr_tp1_floor
            # the plan passed its R:R on Binance; on BingX it must still pass it (a worse price by the basis / the
            # spread / the move since the trigger). audit C05: the same TP1 gates as geometry.level_plan - a method's
            # own minimum (Seiden 3:1) and the floor are minimums to TP1, far targets lifting the blend do not meet them
            # geometry applies them only when TP1 is a real level (a synthetic 'ATR step' / 'N R' TP1 is not gated)
            from strategies.geometry import is_synthetic
            tp1_real = not is_synthetic(s.levels.get('tp1_src'))
            if tp1_real and (plan.get('min_rr') is not None or plan.get('min_rr_on_tp1')) and rrs[0] < need:
                reject = f"R:R to TP1 {rrs[0]:.2f} at BingX {fill_est:.6g} < {need:g} (the method's minimum)"
            elif tp1_real and floor > 0 and need > 0 and rrs[0] < floor:
                reject = f"R:R to TP1 {rrs[0]:.2f} at BingX {fill_est:.6g} < {floor:g}"
            elif plan_blend is not None and blend < need:
                reject = f"blended R:R {blend:.2f} at BingX {fill_est:.6g} < {need:g} (Binance plan {plan_blend:.2f})"
        if reject:
            logger.info(f"Demo: {s.symbol} {s.group_key} skipped: {reject} (basis {basis:+.3%})")
            self._insert({'card_id': card_id, 'symbol': s.symbol, 'setup': s.group_key, 'strategy': s.mode,
                          'direction': d, 'opened_ms': int(time.time() * 1000), 'error': f"{reject}; basis {basis:+.3%}",
                          'closed_ms': int(time.time() * 1000),
                          'close_reason': 'CHASE_LIMIT' if reject.startswith('chase_limit') else 'PRICE_GAP'})
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
        if not no_stop and fill_est:
            # eng-167 (trade-geometry review, section 11): the stop must come before a liquidation. BingX's estimate of
            # an isolated position's liquidation is entry x (1 -+ 1 / leverage): the leverage is cut until that lies
            # beyond the stop with a 20% margin (a Turtle 2N stop of 10-46% at 5x would have been liquidated first)
            frac = abs(fill_est - lv['sl']) / fill_est
            while leverage > 1 and 1.0 / leverage <= 1.2 * frac:
                leverage -= 1
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
        import ccxt
        import uuid
        # audit N03: a client order id, so a request whose reply was lost can be found; a timeout is an UNKNOWN outcome
        # (the exchange may have filled it), never 'not filled'
        cid = f"pb{uuid.uuid4().hex[:24]}"
        try:
            try:
                order = await ex.create_order(symbol, 'market', side, qty, None, {'clientOrderId': cid})
            except (ccxt.NetworkError, ccxt.ExchangeNotAvailable):
                raise
            except Exception as e:
                # BingX caps the position per coin (1000 USDT on small caps, live HUMA 2026-10-01) and names the cap
                # in the error: retry once at 90% of it
                import re
                m = re.search(r'position limit of ([0-9.]+) USDT', str(e))
                if not m:
                    raise
                qty = float(ex.amount_to_precision(symbol, 0.9 * float(m.group(1)) / lv['entry']))
                if qty <= 0 or qty < min_qty:
                    raise
                cid = f"pb{uuid.uuid4().hex[:24]}"
                order = await ex.create_order(symbol, 'market', side, qty, None, {'clientOrderId': cid})
        except (ccxt.NetworkError, ccxt.ExchangeNotAvailable) as e:
            order = await self._resolve_unknown_entry(symbol, d, cid, e)
            if order is None:
                raise
        fill = order.get('average') or order.get('price')
        filled = order.get('filled')
        if (not fill or not filled) and order.get('id'):
            # the create reply may carry no average / filled: the order's own state, never the plan's price
            try:
                o = await self._call('fetch_order', order['id'], symbol)
                fill = fill or o.get('average') or o.get('price')
                filled = filled or o.get('filled')
            except Exception as e:
                errors.report('executor._open', e, f"Demo fill price {symbol}")
        # audit N04: one position per coin (one-way mode, coin checked free above), so the exchange's position IS this
        # entry - its size and average price are confirmed data where the order reply was not
        pos_qty, pos_px = await self._position_of(symbol, d)
        if pos_qty:
            filled = pos_qty
            fill = fill or pos_px
        confirmed = bool(fill and filled)
        if not confirmed:
            logger.warning(f"Demo ENTRY {symbol}: fill not confirmed by BingX (price {fill}, size {filled}): the quote / "
                           f"requested size stand in, the row is marked unconfirmed")
            self.alert(f"⚠️ Демо {symbol}: биржа не подтвердила цену/объём входа, записано как неподтверждённое")
        fill = float(fill or fill_est)
        # the exits use what was FILLED: a stop for the ordered size failed on a partial fill (live INJ 2026-10-03:
        # 'order size must be less than the available amount of 529', the position sat without a stop)
        qty = float(filled or 0) or qty
        trade = {'card_id': card_id, 'symbol': symbol, 'setup': s.group_key, 'strategy': s.mode, 'direction': d,
                 'opened_ms': int(time.time() * 1000), 'entry_plan': lv['entry'], 'entry_fill': fill, 'qty': qty,
                 'sl': lv['sl'], **{k: (None if (getattr(s, 'plan', None) or {}).get('no_tp') else lv[k])
                                    for k in ('tp1', 'tp2', 'tp3')},     # no_tp: placeholders are no targets
                 # the risk the size was computed from (stop distance + the round trip's costs): R = -1 at the stop
                 'risk_usd': qty * (abs(fill - lv['sl']) + fee), 'no_stop': int(no_stop),
                 # eng-167 (section 17.2): entry slippage vs the decision quote (positive = adverse), the time from the
                 # card's entry to the order, the leverage used
                 'slip_bps': (d * (fill - fill_est) / fill_est * 1e4) if fill_est else None,
                 'latency_ms': int(time.time() * 1000 - float(getattr(s, 'entered_at', 0) or 0) * 1000)
                 if getattr(s, 'entered_at', None) else None,
                 'leverage': leverage,
                 'entry_order': str(order.get('id') or '') or None, 'fill_confirmed': int(confirmed),
                 'trail': int(bool((getattr(s, 'plan', None) or {}).get('trail_after_tp1'))),
                 'no_tp': int(bool((getattr(s, 'plan', None) or {}).get('no_tp')))}
        try:
            if not no_stop:
                await ex.create_order(symbol, 'market', exit_side, qty, None,
                                      {'stopLossPrice': float(ex.price_to_precision(symbol, lv['sl'])), 'reduceOnly': True,
                                       'workingType': 'MARK_PRICE'})
            elif lv.get('sl'):
                # eng-144: a perpetual is never left without a stop - a catastrophe stop 3 R units away (Connors trades
                # without one in his book; the exit stays the SMA5 close, this only caps a gap / delisting tail)
                far = fill - 3 * (lv['entry'] - lv['sl']) if lv.get('entry') else None
                if far and far > 0:
                    await ex.create_order(symbol, 'market', exit_side, qty, None,
                                          {'stopLossPrice': float(ex.price_to_precision(symbol, far)), 'reduceOnly': True,
                                           'workingType': 'MARK_PRICE'})
        except Exception as e:
            # never an unprotected position: recorded and closed at market
            trade['id'] = self._insert(trade)
            logger.warning(f"Demo ENTRY {symbol}: stop not placed ({e!r}): closed at market")
            self.alert(f"⛔ Демо {symbol}: стоп не поставлен ({str(e)[:120]}), позиция закрыта рынком")
            await self._close(trade, 'NO_STOP', None)
            return
        plan = getattr(s, 'plan', None) or {}
        trade['id'] = self._insert(trade)
        trade['unit_qty'], trade['scale'] = qty, scale          # the pyramid's unit (memory), BingX's price scale (+ db)
        self._set_scale(trade['id'], scale)
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
            atomic_write(self.pending_path, json.dumps(self.pending, allow_nan=False).encode('utf-8'))
        except (OSError, TypeError, ValueError) as e:
            errors.report('executor._save_pending', e, "Demo pending state")

    async def _place_limit(self, key: str, s) -> None:
        from strategies.geometry import entry_levels
        d, plan = s.direction, s.plan
        if self.risk_limit() is not None:
            return                                   # eng-58: the day's risk rules - no new resting limit (retried later)
        if s.group_key in CONFIG.executor.demo_off_setups:
            self.pending[key] = {'skip': True, 'reason': f"setup off on demo: {s.group_key}"}
            return
        if self.cluster_hit(d) is not None:
            return                                   # owner 2026-10-18: one entry per direction per window (retried later)
        coin = _coin(s.symbol)
        if coin in self._unknown_coins:
            return                                   # audit C02: an entry on the coin of unknown outcome (retried later)
        if any(_coin(t['symbol']) == coin for t in self.open.values()) or                 any(_coin(p.get('symbol', '')) == coin for p in self.pending.values()
                    if not p.get('skip')):
            # BingX nets a coin's orders into one position: one trade or resting limit per coin
            self.pending[key] = {'skip': True, 'reason': 'the coin is held / has a resting limit'}
            return
        same = sum(1 for p in self.pending.values() if not p.get('skip') and p.get('direction') == d) + \
            sum(1 for t in self.open.values() if t.get('direction') == d and t.get('strategy') != 'breakout')
        if 0 < CONFIG.strategies.crowd_max <= same:
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
        self.pending[key] = {'order_id': order['id'], 'symbol': symbol, 'qty': qty, 'lv': lv, 'scale': ratio, 'fee': fee,
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
            logger.warning(f"Demo limit {p['symbol']}: state unknown after the cancel ({e!r}), retried in 10s")
            return
        if o.get('status') not in ('canceled', 'cancelled', 'closed', 'expired', 'rejected'):
            logger.warning(f"Demo limit {p['symbol']}: still {o.get('status')} after the cancel, retried in 10s")
            return
        filled = _finite(o.get('filled'))
        if filled is None or filled < 0 or (filled == 0 and o.get('status') == 'closed'):
            logger.warning(f"Demo limit {p['symbol']}: unconfirmed fill after the cancel, state kept")
            return
        self.pending.pop(key, None)
        self._save_pending()
        if filled > 0:
            trade = self._limit_trade(key, p, float(o.get('average') or o.get('price') or p['lv']['entry']), filled)
            if trade is None:
                return
            logger.warning(f"Demo limit {p['symbol']} {p['setup']} was filled ({filled}) though its card ended "
                           f"({why}): closed at market")
            self.alert(f"⚠️ Демо {p['symbol']}: лимитка исполнилась после конца карточки ({why}), закрыта рынком")
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
        terminal = {'canceled', 'cancelled', 'closed', 'expired', 'rejected'}
        for key, p in list(self.pending.items()):
            if p.get('skip'):
                continue
            try:
                o = await ex.fetch_order(p['order_id'], p['symbol'])
            except Exception as e:
                errors.report('executor.check_limits', e, f"Demo limit status {p['symbol']}")
                continue
            filled = _finite(o.get('filled'))
            if filled is None or filled < 0 or (filled == 0 and o.get('status') == 'closed'):
                logger.warning(f"Demo limit {p['symbol']}: unconfirmed fill {o.get('filled')!r}, state kept")
                continue
            if filled > 0 and o.get('status') not in terminal:
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
                if o.get('status') not in terminal:
                    continue
                filled = _finite(o.get('filled'))
                if filled is None or filled < 0 or (filled == 0 and o.get('status') == 'closed'):
                    logger.warning(f"Demo limit {p['symbol']}: unconfirmed final fill, state kept")
                    continue
            if o.get('status') in terminal:
                if filled > 0:
                    await self._limit_filled(key, p, float(o.get('average') or o.get('price') or p['lv']['entry']), filled)
                else:
                    # Keep the card marked skipped so sync_limits cannot place the same entry again.
                    self.pending[key] = {'skip': True, 'reason': f"limit {o['status']} without a fill"}
                    self._save_pending()
            elif p.get('entered') and now - p['entered_ms'] > CONFIG.executor.limit_wait_min * 60_000:
                await self._cancel_limit(key, f"Binance touched the line, BingX did not fill within "
                                              f"{CONFIG.executor.limit_wait_min} min", record=True)

    def _limit_trade(self, key: str, p: Dict, fill: float, qty: float) -> Optional[Dict]:
        """The demo row of a filled limit, written before its exits are placed (a failure there still leaves it)."""
        # A crash can leave both the committed trade and its old pending JSON entry.
        # Callers verify the exchange order is terminal before reaching this point.
        order_id = str(p.get('order_id') or '') or None
        if order_id is not None:
            with sqlite3.connect(self.db_path) as c:
                c.row_factory = sqlite3.Row
                recorded = c.execute("SELECT * FROM demo_trades WHERE symbol = ? AND entry_order = ? ORDER BY id DESC LIMIT 1",
                                     (p['symbol'], order_id)).fetchone()
            if recorded is not None:
                logger.warning(f"Demo limit {p['symbol']}: entry order {order_id} already recorded")
                if recorded['closed_ms'] is not None:
                    return None
                trade = self.open.get(recorded['card_id'])
                if trade is None:
                    trade = dict(recorded)
                    if trade.get('close_pending_reason') is not None:
                        trade['close_pending'] = [trade['close_pending_reason'], trade['close_pending_r']]
                    self.open[trade['card_id']] = trade
                trade['_limit_recorded'] = True
                return trade
        lv = p['lv']
        trade = {'card_id': p.get('card_id') or key, 'symbol': p['symbol'], 'setup': p['setup'],
                 'strategy': p['strategy'], 'direction': p['direction'], 'opened_ms': int(time.time() * 1000),
                 'entry_plan': lv['entry'], 'entry_fill': fill, 'qty': qty, 'sl': lv['sl'], 'tp1': lv['tp1'],
                 'tp2': lv['tp2'], 'tp3': lv['tp3'], 'risk_usd': qty * (abs(fill - lv['sl']) + float(p.get('fee') or 0)),
                 'entry_order': str(p.get('order_id') or '') or None, 'from_limit': 1,
                 'trail': int(bool(p.get('trail'))), 'no_tp': int(bool(p.get('no_tp')))}
        trade['id'] = self._insert(trade)
        trade['unit_qty'], trade['scale'] = qty, p['scale']
        self._set_scale(trade['id'], p['scale'])
        trade['from_limit'] = True
        self._set_basis(trade['id'], p['basis'])
        return trade

    async def _limit_filled(self, key: str, p: Dict, fill: float, qty: float) -> None:
        ex = await self._exchange()
        symbol, d, lv = p['symbol'], p['direction'], p['lv']
        exit_side = 'sell' if d > 0 else 'buy'
        trade = self._limit_trade(key, p, fill, qty)
        if trade is None or trade.get('_limit_recorded'):
            if trade is not None:
                if trade.get('close_pending'):
                    await self._close(trade, *trade['close_pending'])
                elif not any(self._is_stop(o) for o in await ex.fetch_open_orders(symbol)):
                    await self._restore_stop(trade)
            self.pending[key] = {'skip': True, 'reason': 'entry order already recorded in demo_trades'}
            self._save_pending()
            return
        self.pending.pop(key, None)
        self._save_pending()
        try:
            await ex.create_order(symbol, 'market', exit_side, qty, None,
                                  {'stopLossPrice': float(ex.price_to_precision(symbol, lv['sl'])), 'reduceOnly': True,
                                   'workingType': 'MARK_PRICE'})
        except Exception as e:
            # found filled only after price ran through the stop (live CAP 2026-10-02): out at market, never unprotected
            logger.warning(f"Demo LIMIT FILLED {symbol}: stop not placed ({e!r}): closed at market")
            self.alert(f"⛔ Демо {symbol}: стоп после исполнения лимитки не поставлен, закрыта рынком")
            await self._close(trade, 'SL', None)
            return
        self.open[trade['card_id']] = trade
        min_qty = ((ex.markets[symbol].get('limits') or {}).get('amount') or {}).get('min') or 0
        await self._place_tps(trade, self.exit_parts(ex, trade, qty, bool(p.get('trail')), bool(p.get('no_tp'))), min_qty)
        logger.info(f"Demo LIMIT FILLED {symbol} {p['setup']} {qty} @ {fill:.6g}, SL {lv['sl']:.6g}")

    def _save_unknown(self) -> None:
        try:
            atomic_write(self.unknown_path, json.dumps(self._unknown_coins, allow_nan=False).encode('utf-8'))
        except (OSError, TypeError, ValueError) as e:
            errors.report('executor._save_unknown', e, "Demo unknown-entry state")

    async def _release_unknown(self, ex, positions: List[Dict]) -> None:
        """audit T03: a coin held for an entry of unknown outcome is released only once the outcome is resolved - no
        position and no open order of that coin on BingX, read after the minimum hold (a late fill / a resting order can
        still land). The hold was a 900 s timer: a new entry went in without ever confirming the old one."""
        due = [c for c, ts in self._unknown_coins.items() if time.time() - ts >= UNKNOWN_HOLD_SEC]
        if not due:
            return
        try:
            orders = await ex.fetch_open_orders()
        except Exception as e:
            errors.report('executor._release_unknown', e, "Demo open orders (unknown-entry release)")
            return                                           # unreadable: the hold stays
        held = {_coin(p['symbol']) for p in positions if float(p.get('contracts') or 0)} | \
            {_coin(o.get('symbol') or '') for o in orders}
        released = [c for c in due if c not in held]
        for c in released:
            self._unknown_coins.pop(c, None)
            logger.info(f"Demo: {c} released - the unknown entry left no position and no order")
        if released:
            self._save_unknown()

    async def close_untracked(self) -> None:
        """Safety net: a BingX position no trade or resting limit of ours owns (a lost fill) is closed at market."""
        ex = await self._exchange()
        mine = {t['symbol'] for t in self.open.values()} | {p.get('symbol') for p in self.pending.values()
                                                             if not p.get('skip')}
        positions = await ex.fetch_positions()
        await self._release_unknown(ex, positions)
        for pos in positions:
            qty = float(pos.get('contracts') or 0)
            if not qty or pos['symbol'] in mine:
                continue
            last = self._finalized.get(pos['symbol'])
            if (last and time.time() - last[1] < 900 and last[0].get('id')
                    and (1 if pos.get('side') == 'long' else -1) == last[0].get('direction')
                    and qty <= float(last[0].get('qty') or 0) * 1.001):
                # eng-132: finalized minutes ago yet the position is on BingX: the flat read was wrong. Back to tracking
                # (same side, not more than the trade held); dumping it at market wrote EXCHANGE + UNTRACKED for one
                # trade. The finalize cancelled its stop and take-profits: both are put back below
                trade = last[0]
                await asyncio.sleep(5)                   # a cached position snapshot lives a few seconds: read again
                if await self._position_qty(pos['symbol']) <= 0:
                    continue
                with sqlite3.connect(self.db_path) as c:
                    c.execute("UPDATE demo_trades SET closed_ms = NULL, close_reason = NULL, exit_avg = NULL, "
                              "fees_usd = NULL, pnl_usd = NULL, r = NULL, journal_r = NULL, error = NULL WHERE id = ?",
                              (trade['id'],))
                self.open[trade['card_id']] = trade
                self._finalized.pop(pos['symbol'], None)
                logger.warning(f"Demo: {pos['symbol']} was finalized {time.time() - last[1]:.0f}s ago but BingX still "
                               f"holds {qty}: back in tracking")
                self.alert(f"⚠️ Демо {pos['symbol']}: позиция жива после закрытия в базе, возвращена в отслеживание")
                try:
                    await self._restore_stop(trade)
                    min_qty = ((ex.markets[trade['symbol']].get('limits') or {}).get('amount') or {}).get('min') or 0
                    await self._place_tps(trade, self.exit_parts(ex, trade, qty, bool(trade.get('trail')),
                                                                 bool(trade.get('no_tp'))), min_qty)
                except Exception as e:
                    errors.report('executor.close_untracked', e, f"Demo re-protect {trade['symbol']}")
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
            self.alert(f"⚠️ Демо: чужая позиция {pos['symbol']} {pos.get('side')} {qty} без карточки, закрыта рынком")
            await self._close(trade, 'UNTRACKED', None)

    async def _restore_stop(self, trade: Dict) -> None:
        if trade.get('no_stop') or trade.get('strategy') == 'connors' or not trade.get('sl'):
            return                                   # eng-127: a system without a stop (Connors) - nothing to restore
        symbol, d, sl = trade['symbol'], trade['direction'], float(trade['sl'])
        left = await self._position_qty(symbol)
        if left <= 0:
            return                                   # flat: the reconcile pass finalizes it
        ex = await self._exchange()
        t = await ex.fetch_ticker(symbol)
        last = float(t.get('last') or 0)
        if last and d * (last - sl) <= 0:
            logger.warning(f"Demo {symbol}: no stop on BingX and the price {last:.6g} is beyond it ({sl:.6g}): closed")
            self.alert(f"⛔ Демо {symbol}: стопа на бирже не было, цена уже за стопом, закрыта рынком")
            await self._close(trade, 'SL', None)
            return
        await self._place_stop(symbol, d, left, sl)
        logger.warning(f"Demo {symbol}: the position {left} had no stop on BingX: re-placed at {sl:.6g}")
        self.alert(f"⚠️ Демо {symbol}: у позиции не было стопа на бирже, поставлен заново ({sl:.6g})")

    async def _dedupe_stops(self) -> None:
        """eng-98: one stop per open trade on BingX. Before eng-85 a failed / repeated restop could leave an older stop
        resting beside the live one (live HYPE 14.10: 12 @ 91.47 beside 24 @ 89.72) - it would later cut a new position
        of the coin. The stop nearest the trade's own stop stays, the others are cancelled.
        The guard the other way: an open position with NO stop (a cancel that went through while its replacement
        failed, a close that failed after the take-profits went) gets its stop back at the trade's level, or is closed
        at market when the price is already beyond it."""
        ex = await self._exchange()
        for trade in list(self.open.values()):
            stops = [o for o in await ex.fetch_open_orders(trade['symbol']) if self._is_stop(o)]
            if not stops:
                await self._restore_stop(trade)
                continue
            # audit B02: a stop that exists is not a stop that covers the position (a grown position kept the old size)
            if not (trade.get('no_stop') or trade.get('strategy') == 'connors' or not trade.get('sl')):
                try:
                    left = await self._position_qty(trade['symbol'])
                except Exception as e:
                    errors.report('executor._dedupe_stops', e, f"Demo position {trade['symbol']}")
                    left = 0.0
                if left > 0 and trade.pop('add_unknown', False) and \
                        abs(left - float(trade.get('qty') or 0)) > 1e-9 * max(1.0, left):
                    # audit V01: the size an add of unknown outcome left, booked once the position reads again
                    logger.warning(f"Demo {trade['symbol']}: position {left} after an unknown add (booked "
                                   f"{trade.get('qty')}): booked as is")
                    trade['qty'] = left
                    with sqlite3.connect(self.db_path) as c:
                        c.execute("UPDATE demo_trades SET qty = ? WHERE id = ?", (left, trade['id']))
                ref0 = float(trade.get('sl') or 0)
                spx = lambda o: float((o.get('info') or {}).get('stopPrice') or o.get('stopPrice')  # noqa: E731
                                      or o.get('triggerPrice') or 0)
                stays = min(stops, key=lambda o: abs(spx(o) - ref0)) if ref0 else \
                    max(stops, key=lambda o: o.get('timestamp') or 0)
                # audit V02: the coverage of the stop that STAYS after the dedupe below (two stops of 1 'covered' a
                # position of 2, then one was cancelled)
                covered = float((stays.get('info') or {}).get('origQty') or stays.get('amount') or 0)
                if left > 0 and covered < left * 0.999:
                    logger.warning(f"Demo {trade['symbol']}: stops cover {covered} of the position {left}: re-placed")
                    self.alert(f"⚠️ Демо {trade['symbol']}: стоп покрывал {covered} из {left}, переставлен")
                    try:
                        new = await self._place_stop(trade['symbol'], trade['direction'], left, float(trade['sl']))
                        await self._cancel_orders(trade['symbol'], keep=new.get('id'), stops_only=True)
                    except Exception as e:
                        errors.report('executor._dedupe_stops', e, f"Demo stop re-place {trade['symbol']}")
                    continue
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
            # audit C01: the trade may have been closed while this task waited for the lock
            if all(t is not trade for t in self.open.values()):
                return
            try:
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
                with sqlite3.connect(self.db_path) as c:     # the stop guard restores THIS stop after a restart
                    c.execute("UPDATE demo_trades SET sl = ? WHERE id = ?", (trade['sl'], trade['id']))
                logger.info(f"Demo RESTOP {symbol}: stop {s.levels['sl'] * scale:.6g} for {left}")
            except Exception as e:
                # eng-169c (audit: COMP 325, FET 302 - BingX 110412, the new stop already on the wrong side of the
                # price): the old stop stays (placed-first order), but a stop the price already passed is a stop hit -
                # the rest is closed at market as the stop order would have done; any other failure is reported
                # (was a WARNING only: card and exchange disagreed on the stop silently)
                await self._restop_failed(trade, s, e)

    async def _restop_failed(self, trade: Dict, s, e: Exception) -> None:
        symbol, d = trade['symbol'], trade['direction']
        try:
            scale = float(trade.get('scale') or 1.0)
            new_sl = float(s.levels['sl']) * scale
            ex = await self._exchange()
            last = float((await ex.fetch_ticker(symbol)).get('last') or 0)
            left = await self._position_qty(symbol)
            if last and left > 0 and d * (last - new_sl) <= 0:
                await ex.create_order(symbol, 'market', 'sell' if d > 0 else 'buy', left, None, {'reduceOnly': True})
                logger.info(f"Demo RESTOP {symbol}: price {last} already beyond the new stop {new_sl:.6g}, "
                            f"{left} closed at market")
                return
        except Exception as e2:
            errors.report('executor.on_restop', e2, f"Demo restop {symbol}: market close after a rejected stop")
        errors.report('executor.on_restop', e, f"Demo restop {symbol}: the old stop {trade.get('sl')} stays on BingX")

    async def on_partial(self, s) -> None:
        """eng-155: the card went +partial_r R - partial_share of the position out. A trade opened with its tp0 order
        (exit_parts) has usually given it already (the position is down to the rest: only marked); a trade opened
        before partials were on has none - its take-profits are cancelled, the half closed at market (it may be well
        past +1R by then) and the take-profits re-placed for the rest. The stop is never touched here."""
        cfg = CONFIG.executor
        if not self.enabled or not s.entered_at or not cfg.partial_share:
            return
        card_id = f"{s.symbol}|{s.group_key}|{int(s.entered_at)}"
        trade = self.open.get(card_id) or self.open.get(f"{s.symbol}|{s.group_key}|c{int(s.created)}")
        if trade is None or trade.get('partial_done') or trade.get('units') or not trade.get('qty'):
            return
        async with self._lock:
            if all(t is not trade for t in self.open.values()):
                return
            try:
                ex = await self._exchange()
                symbol, d, qty = trade['symbol'], trade['direction'], float(trade['qty'])
                rest_share = 1 - cfg.partial_share
                left = await self._position_qty(symbol)
                if 0 < left <= qty * (rest_share + 0.05):
                    done = 'already out by its tp0'
                elif left > 0:
                    for o in await ex.fetch_open_orders(symbol):
                        if not self._is_stop(o):
                            try:
                                await ex.cancel_order(o['id'], symbol)
                            except Exception as e:
                                errors.report('executor.on_partial', e, f"Demo partial {symbol}: cancel {o.get('id')}")
                    left = await self._position_qty(symbol)
                    if left <= qty * (rest_share + 0.05):
                        done = 'out by its tp0 meanwhile'
                    else:
                        # down to rest_share of the ORIGINAL size: a trade whose TP1 third already went out keeps
                        # its half, not 1/6 (live APE 2026-10-24: half of the original closed from 2/3 left)
                        half = float(ex.amount_to_precision(symbol, left - qty * rest_share))
                        if half > 0:
                            await ex.create_order(symbol, 'market', 'sell' if d > 0 else 'buy', half, None,
                                                  {'reduceOnly': True})
                        done = f"{half} closed at market"
                    rest = await self._position_qty(symbol)
                    if rest > 0:
                        await self._place_tps(trade, self.tp_parts(ex, symbol, rest, bool(trade.get('trail')),
                                                                   bool(trade.get('no_tp'))))
                else:
                    return
                trade['partial_done'] = 1
                with sqlite3.connect(self.db_path) as c:
                    c.execute("UPDATE demo_trades SET partial_done = 1 WHERE id = ?", (trade['id'],))
                logger.info(f"Demo PARTIAL {symbol}: {done}")
            except Exception as e:
                logger.warning(f"Demo partial {s.symbol}: {e!r}")

    async def on_add(self, s) -> None:
        """A Turtle unit added on the card: the same quantity again at market, the stop of the whole position moved."""
        if not self.enabled or not s.entered_at:
            return
        card_id = f"{s.symbol}|{s.group_key}|{int(s.entered_at)}"
        if self.open.get(card_id) is None:
            return
        async with self._lock:
            # audit C01: re-read under the lock - a close that ran while this task waited removed the trade, and an
            # add on the stale object opened a new, unowned position
            trade = self.open.get(card_id)
            if trade is None or card_id in getattr(self, '_finished_cards', ()):
                return
            try:
                ex = await self._exchange()
                symbol, d = trade['symbol'], trade['direction']
                # after a restart the unit is the position over the units it already holds
                unit = float(trade.get('unit_qty') or float(trade['qty']) / max(1, len(s.units) - 1))
                # audit B01: the add is confirmed by the exchange's own position (size and average price), never by the
                # requested unit; a lost reply is an UNKNOWN outcome resolved by the position, not a 'not filled'
                import ccxt
                import uuid
                before, before_px = await self._position_of(symbol, d, strict=True)
                cid = f"pb{uuid.uuid4().hex[:24]}"
                try:
                    order = await ex.create_order(symbol, 'market', 'buy' if d > 0 else 'sell', unit, None,
                                                  {'clientOrderId': cid})
                except (ccxt.NetworkError, ccxt.ExchangeNotAvailable) as e:
                    logger.warning(f"Demo ADD {symbol}: outcome unknown ({e!r}): resolving by position")
                    order = {}
                    await asyncio.sleep(4)
                after = after_px = None
                for wait in (0, 3, 6, 10, 20, 30):     # BingX's position snapshot lags the fill by a few seconds
                    await asyncio.sleep(wait)
                    try:
                        after, after_px = await self._position_of(symbol, d, strict=True)
                    except Exception as e:
                        logger.warning(f"Demo ADD {symbol}: position unreadable ({e!r}), retrying")
                        continue
                    if after - before > 0:
                        break
                if after is None:
                    # audit V01: the add went out and the position stayed unreadable - the outcome is UNKNOWN. The
                    # largest position it can be (before + the unit) gets the stop at once (reduce-only: a larger stop
                    # closes no more than there is); _dedupe_stops re-reads the real size, books it and resizes the stop
                    worst = before + unit
                    self.alert(f"⚠️ Демо {symbol}: исход добора неизвестен (позиция не читается), стоп поставлен на "
                               f"максимально возможный объём {worst:g}")
                    trade['add_unknown'] = True
                    try:
                        new = await self._place_stop(symbol, d, worst, float(trade['sl']))
                        await self._cancel_orders(symbol, keep=new.get('id'), stops_only=True)
                    except Exception as e:
                        errors.report('executor.on_add', e, f"Demo protective stop after an unknown add {symbol}")
                    return
                added = after - before
                if added <= 0:
                    logger.warning(f"Demo ADD {symbol}: no growth of the position ({before} -> {after}): not added")
                    self.alert(f"⚠️ Демо {symbol}: добор не подтверждён позицией ({before} → {after}), стоп сверит проверка покрытия")
                    return
                if after_px and before_px and added > 0:
                    fill = (after_px * after - before_px * before) / added   # the add's own average price
                else:
                    fill = float(order.get('average') or order.get('price') or 0) or float(s.last_price)
                total = after
                if abs(added - unit) > 1e-9 * max(1.0, unit):
                    logger.warning(f"Demo ADD {symbol}: filled {added} of the requested {unit}")
                trade['entry_fill'] = after_px or (float(trade['entry_fill']) * float(trade['qty']) + fill * added) / total
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
                    self.alert(f"⛔ Демо {symbol}: стоп после добора не поставлен, закрыта рынком")
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
                logger.info(f"Demo ADD {symbol} unit {len(s.units)}: +{added} @ {fill:.6g}, position {total}, "
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
        # audit N02: the open trade is read under the lock - an entry still opening (on_entry holds the lock through
        # _open) is waited for instead of the finish being dropped with the position left on BingX
        async with self._lock:
            self._finished_cards.add(card_id)
            if len(self._finished_cards) > 5000:
                self._finished_cards = {card_id}
            trade = self.open.get(card_id)
            if trade is None:
                # the exchange closed it first (stop / last target, reconciled as EXCHANGE): the card's own result
                # still belongs next to it - the demo exists to compare the two
                if s.final_r is not None:
                    with sqlite3.connect(self.db_path) as c:
                        c.execute("UPDATE demo_trades SET journal_r = ? WHERE card_id = ? AND journal_r IS NULL",
                                  (s.final_r, card_id))
                return
            try:
                self._set_exit_ref(trade['id'], s.finish_price)
                await self._close(trade, s.status, s.final_r, passive=True)
            except Exception as e:
                logger.warning(f"Demo close failed for {trade['symbol']}: {e!r}")

    def strategy_killed(self, strategy: Optional[str]) -> Optional[str]:
        """audit-80, opt-in: a strategy whose last strategy_kill_n closed demo trades sum to <= -strategy_kill_r R
        opens no new demo trade (its cards and the journal go on, so it can earn its way back on paper)."""
        cfg = CONFIG.executor
        if cfg.strategy_kill_r <= 0 or not strategy:
            return None
        try:
            with sqlite3.connect(self.db_path) as c:
                rows = c.execute("SELECT r FROM demo_trades WHERE strategy = ? AND r IS NOT NULL ORDER BY closed_ms DESC "
                                 "LIMIT ?", (strategy, cfg.strategy_kill_n)).fetchall()
        except sqlite3.Error:
            return None
        total = sum(r for (r,) in rows)
        if len(rows) >= cfg.strategy_kill_n and total <= -cfg.strategy_kill_r:
            return f"strategy {strategy} off: {total:+.1f}R over its last {len(rows)} trades"
        return None

    def day_summary(self, day0_ms: int) -> List[tuple]:
        """(strategy, trades, wins, sum R, avg slippage bps) of the trades closed in [day0, day0 + 1 day)."""
        with sqlite3.connect(self.db_path) as c:
            return c.execute(
                "SELECT COALESCE(strategy, '?'), COUNT(*), SUM(r > 0), SUM(r), "
                "AVG(CASE WHEN entry_plan > 0 AND entry_fill > 0 THEN direction * (entry_fill - entry_plan) / entry_plan * 1e4 END) "
                "FROM demo_trades WHERE r IS NOT NULL AND closed_ms >= ? AND closed_ms < ? GROUP BY 1 ORDER BY 4",
                (day0_ms, day0_ms + 86_400_000)).fetchall()

    def usd_without_r(self, day0_ms: int) -> tuple:
        """(trades, USD) closed in the day with a dollar result but no R (UNTRACKED: no planned stop) - they fell out
        of every R sum (11 rows, -12.54 USD by 15.10)."""
        with sqlite3.connect(self.db_path) as c:
            return c.execute("SELECT COUNT(*), COALESCE(SUM(pnl_usd), 0) FROM demo_trades WHERE r IS NULL AND "
                             "pnl_usd IS NOT NULL AND closed_ms >= ? AND closed_ms < ? "
                             "AND COALESCE(error, '') NOT LIKE 'duplicate of%'",
                             (day0_ms, day0_ms + 86_400_000)).fetchone()

    async def _call(self, method: str, *args, tries: int = 3, **kw):
        """A ccxt call with backoff on network / exchange-unavailable errors (the VST API hiccups for seconds)."""
        import ccxt
        ex = await self._exchange()
        for attempt in range(tries):
            try:
                return await getattr(ex, method)(*args, **kw)
            except (ccxt.NetworkError, ccxt.ExchangeNotAvailable):
                if attempt == tries - 1:
                    raise
                await asyncio.sleep(1.5 * 2 ** attempt)

    async def _position_of(self, symbol: str, d: int, strict: bool = False) -> tuple:
        """(size, average entry price) of the coin's position on the side d, (0, None) when there is none / unreadable.
        strict: an unreadable position raises instead (audit C02: an API error is no proof of a flat coin)."""
        try:
            for p in await self._call('fetch_positions', [symbol]):
                side = 1 if p.get('side') == 'long' else -1 if p.get('side') == 'short' else 0
                if p.get('symbol') == symbol and p.get('contracts') and side in (0, d):
                    return float(p['contracts']), float(p.get('entryPrice') or 0) or None
        except Exception as e:
            if strict:
                raise
            errors.report('executor._position_of', e, f"Demo position {symbol}")
        return 0.0, None

    async def _resolve_unknown_entry(self, symbol: str, d: int, cid: str, err: Exception) -> Optional[Dict]:
        """audit N03 / C02: a market entry whose reply was lost (timeout / network). The coin was free before the order
        (one position per coin, one-way mode), so the position read decides: a position found becomes the trade
        (protected by the caller); 'not filled' needs three SUCCESSFUL empty reads, the third >= 14s after the order (BingX's position snapshot lags a few seconds); the waits stay short since the lock is held. When the exchange stays unreadable the
        outcome is UNKNOWN: EntryUnknown is raised (the caller records it and alerts; close_untracked closes a position
        that turns up later). Never retried blindly (a second order would double the position)."""
        logger.warning(f"Demo ENTRY {symbol}: outcome unknown ({err!r}): resolving by client id {cid} / position")
        flat = 0
        for wait in (2, 4, 8, 15):
            await asyncio.sleep(wait)
            try:
                qty, px = await self._position_of(symbol, d, strict=True)
            except Exception as e:
                errors.report('executor._resolve_unknown_entry', e, f"Demo position {symbol}")
                continue
            if qty:
                return {'id': None, 'filled': qty, 'average': px}
            flat += 1
            if flat >= 3:
                logger.info(f"Demo ENTRY {symbol}: no position after the lost reply (3 reads): not filled")
                return None
        raise EntryUnknown(f"entry {cid} on {symbol}: the exchange stayed unreadable, outcome unknown")

    async def _position_qty(self, symbol: str) -> float:
        for p in await self._call('fetch_positions', [symbol]):
            if p.get('symbol') == symbol and p.get('contracts'):
                return float(p['contracts'])
        return 0.0

    def _set_exit_ref(self, trade_id: int, price: Optional[float]) -> None:
        """The card's own exit price (Binance) next to the demo's fill: the demo lost ~0.15R a trade to the journal,
        almost all on the card-driven market closes (eng-74) - measured, not guessed."""
        with sqlite3.connect(self.db_path) as c:
            c.execute("UPDATE demo_trades SET exit_ref = ? WHERE id = ?", (price, trade_id))

    async def _close(self, trade: Dict, reason: str, journal_r: Optional[float], passive: bool = False) -> None:
        """
        Out of the trade. The stop rests until the position is flat: only the take-profits (and an older closing limit)
        go first, the stop is cancelled after the position is 0. The cancel-all first left the position without a stop
        whenever the close then failed (any error but 101290 / 102202 raised past it; 102202 left a bare limit).
        """
        # Retain late fills / failed stops even when the first exchange read raises.
        self.open.setdefault(trade['card_id'], trade)
        trade['close_pending'] = [reason, journal_r]
        try:
            with sqlite3.connect(self.db_path) as c:
                c.execute("UPDATE demo_trades SET close_pending_reason = ?, close_pending_r = ? "
                          "WHERE id = ? AND closed_ms IS NULL", (reason, journal_r, trade['id']))
        except sqlite3.Error as e:
            # A storage failure must not prevent an emergency exchange close.
            errors.report('executor._close', e, "Demo close intent not persisted")
        ex = await self._exchange()
        symbol, d = trade['symbol'], trade['direction']
        side = 'sell' if d > 0 else 'buy'
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
        if left > 0:
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
                    # at the touch instead, the stop still resting; the trade stays open, the next pass re-places it
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
                    # the stop still rests: the trade stays tracked, the reconcile loop retries the close
                    self.open.setdefault(trade['card_id'], trade)
                    self.alert(f"⚠️ Демо {symbol}: закрытие ({reason}) не прошло ({str(e)[:120]}), стоп на месте, повтор")
                    raise
        # eng-132: the cancel-all only after a confirmed flat. BingX's position endpoint may serve a cached snapshot for
        # a few seconds: flat = two empty reads in a row (one empty read between two positions - 0, 1, 0 - is not);
        # anything else keeps the stops and the trade tracked, the reconcile loop judges it again
        seen: List[bool] = []
        for wait in (2, 2, 2, 2):
            await asyncio.sleep(wait)
            seen.append(await self._position_qty(symbol) != 0)
            if seen[-2:] == [False, False] or seen[-3:] == [True, True, True]:
                break
        if seen[-2:] != [False, False]:
            logger.warning(f"Demo {symbol}: position not confirmed flat after the close (reads {seen}): stops kept, "
                           f"trade stays tracked")
            # the reconcile loop closes it again with THIS reason / journal R (not as an ORPHAN held 24h for a limit)
            trade['close_pending'] = [reason, journal_r]
            self.open.setdefault(trade['card_id'], trade)
            return
        try:
            await ex.cancel_all_orders(symbol)           # flat: the stop and whatever else rests on the coin
        except Exception as e:
            errors.report('executor._close', e, f"Demo cancel {symbol}")
        await self._finalize(trade, reason, journal_r)

    async def _finalize(self, trade: Dict, reason: str, journal_r: Optional[float]) -> None:
        """
        Realized result: OUR quantity x (the exit price - the entry fill), minus taker fees on both sides. The fills'
        prices are right but ccxt's BingX swap fills report the amount in another unit than the position (live REZ:
        33,333,333 for 333,333 coins), so the quantity each exit closed is its ORDER's filled amount (_exit_summary),
        and right after a close the exit fill may not be listed yet (retried).
        """
        d = trade['direction']
        exit_side = 'sell' if d > 0 else 'buy'
        # one attempt: this runs under the executor's lock, and the old 4 x 5s retries held every entry / restop up
        # to 20s per close; a fill not listed yet is FILL_PENDING and _refinalize picks it up within 5 minutes
        try:
            fills = await self._call('fetch_my_trades', trade['symbol'], since=trade['opened_ms'] - 5_000)
        except Exception as e:
            # the API failing must not lose the close: the row is marked FILL_PENDING below, _refinalize retries
            logger.warning(f"Demo {reason} {trade['symbol']}: fills unavailable: {e!r}")
            fills = []
        exits = self._exit_fills(fills, exit_side, trade['opened_ms'], time.time() * 1000)
        qty, entry = float(trade.get('qty') or 0), float(trade.get('entry_fill') or 0)
        exit_avg = exit_fees = None
        if exits and qty:
            exit_avg, closed_qty, exit_fees = await self._exit_summary(trade['symbol'], exits, tries=1)   # under the lock
            if exit_avg is not None and not 0.98 * qty <= closed_qty <= 1.02 * qty:
                # TP1 listed, the final stop / close not yet (audit A06: TP1's price was taken for the whole quantity);
                # more than the position: an order of another trade got in - neither is this trade's result
                exit_avg = None
        if exit_avg is None or not qty or not entry:
            # the fills list can lag a close (or the API is unreachable): retried by reconcile_loop (_refinalize)
            logger.info(f"Demo {reason} {trade['symbol']}: no exit fill listed yet, recovered by the 5-min pass")
            pnl = fees = None
        else:
            fees = self._fees(entry, qty, exit_fees)
            pnl = d * (exit_avg - entry) * qty - fees
        # audit C12: the funding BingX actually settled on the coin while the trade was open (its ledger, signed:
        # paid < 0), in the result beside the fills; None when the ledger is unreadable (pnl then excludes it)
        funding = await self._funding_paid(trade['symbol'], trade['opened_ms'], time.time() * 1000)
        if pnl is not None and funding is not None:
            pnl += funding
        risk = trade.get('risk_usd') or 0
        if not risk:
            logger.warning(f"Demo {reason} {trade['symbol']}: risk_usd is 0 - R left empty")
        with sqlite3.connect(self.db_path) as c:
            c.execute("UPDATE demo_trades SET closed_ms = ?, close_reason = ?, exit_avg = ?, fees_usd = ?, pnl_usd = ?, "
                      "r = ?, journal_r = ?, funding_usd = ? WHERE id = ?",
                      (int(time.time() * 1000), reason, exit_avg, fees, pnl,
                       pnl / risk if risk and pnl is not None else None, journal_r, funding, trade['id']))
            if pnl is None and qty and entry:
                c.execute("UPDATE demo_trades SET error = ? WHERE id = ?", (self.FILL_PENDING, trade['id']))
            elif pnl is not None and trade.get('fill_confirmed') == 0:
                # audit EXTRA_3: the exit is read from the fills, the entry price is the quote / requested size
                c.execute("UPDATE demo_trades SET error = ? WHERE id = ?", (self.ENTRY_ESTIMATE, trade['id']))
        self.open.pop(trade['card_id'], None)
        self._finalized[trade['symbol']] = (trade, time.time())
        if pnl is not None:
            r_txt = f"{pnl / risk:+.2f}R" if risk else "R n/a"
            logger.info(f"Demo {reason} {trade['symbol']}: {pnl:+.2f} USD ({r_txt})")

    FILL_PENDING = 'exit fill pending'
    ENTRY_ESTIMATE = 'entry fill unconfirmed: the result is an estimate'

    async def _funding_paid(self, symbol: str, since_ms: float, until_ms: float) -> Optional[float]:
        """Sum of BingX's FUNDING_FEE ledger entries of the coin in [since, until] (USDT, signed), None unreadable."""
        try:
            rows = await self._call('fetch_funding_history', symbol, int(since_ms) - 1_000)
        except Exception as e:
            logger.debug(f"Demo funding ledger {symbol}: {e!r}")
            return None
        return sum(float(r.get('amount') or 0) for r in rows or []
                   if since_ms - 1_000 <= float(r.get('timestamp') or 0) <= until_ms + 1_000)

    @staticmethod
    def _exit_fills(fills: List[Dict], side: str, opened_ms: float, closed_ms: float,
                    next_open_ms: Optional[float] = None) -> List[Dict]:
        """eng-91: only exit-side fills after this trade's entry (the 1s margin covers BingX's clock; the 5s fetch
        margin let the previous trade's exit on the same coin in) and not after its close (+2 min for a fill listed
        late): _refinalize retried for 3 days and took the NEXT trades' exits on the coin into this one's result; the +2 min
        ends before the next trade on the coin opened (_refinalize passes its opened_ms - 14s; with this 1s margin, 15s:
        its entry fill is on the same side when it is the opposite direction)."""
        return [f for f in fills if f.get('side') == side and f.get('price') and f.get('amount')
                and opened_ms - 1_000 < (f.get('timestamp') or 0) <= min(closed_ms + 120_000, (next_open_ms or 1e18) - 1_000)]

    async def _exit_summary(self, symbol: str, exits: List[Dict], tries: int = 3) -> tuple:
        """(exit price, quantity closed, exit fees in USDT) of the listed exit fills' ORDERS, all three from each order
        itself (fetch_order): filled = executedQty in the position's unit, average = avgPrice over ALL its fills,
        fee = commission over all its fills. The fills only name the orders: a fill list missing part of an order no
        longer prices the whole order at the listed part (review of 6b771ba). Not proven -> (None, 0, None): a fill
        without an order id, an order not readable, still working (open: more fills may come), without filled /
        average, or without a reported fee (audit A06: no estimated result)."""
        oids = []
        for f in exits:
            if not f.get('order'):
                return None, 0.0, None
            if str(f['order']) not in oids:
                oids.append(str(f['order']))
        value = closed = fees = 0.0
        for oid in oids:
            try:
                o = await self._call('fetch_order', oid, symbol, tries=tries)
            except Exception as e:
                logger.info(f"Demo exit order {symbol} {oid}: {e!r}")
                return None, 0.0, None
            filled, avg = _positive(o.get('filled')), _positive(o.get('average'))
            fee = o.get('fee') or {}
            cost = _finite(fee.get('cost'))
            status = str(o.get('status') or '').lower()     # ccxt passes BingX's EXPIRED raw (upper case)
            if status not in ('closed', 'canceled', 'expired'):
                return None, 0.0, None                      # still working: more fills may come
            if filled is None:
                return None, 0.0, None                      # unknown / zero / negative / NaN / inf / non-numeric
            if avg is None:
                return None, 0.0, None
            if cost is None or fee.get('currency') not in (None, 'USDT', 'VST'):
                # currency None: BingX swap orders omit feeAsset; their commission is in the USDT margin
                return None, 0.0, None
            value += filled * avg
            closed += filled
            fees += abs(cost)
        return value / closed, closed, fees

    @staticmethod
    def _next_entry_cutoff(fills: List[Dict], nxt) -> Optional[float]:
        """audit N01: where the next trade on the coin begins. Its entry order's own fill time when the row carries the
        order id (exact: this trade's exit is never cut); for older rows without it, the row's opened_ms - 14s (a
        limit's opened_ms is when check_limits SAW the fill, a market entry's after fetch_order's retries) - that
        margin can drop an exit made in the last 15s before the next entry, which is why the id is stored now."""
        if not nxt:
            return None
        opened, order = nxt
        if order:
            own = [f.get('timestamp') for f in fills if str(f.get('order') or '') == str(order) and f.get('timestamp')]
            # +1s: _exit_fills subtracts its 1s clock margin; the entry fill itself is excluded by its order id
            return min(own) + 1_000 if own else opened + 1_000
        return opened - 14_000

    @staticmethod
    def _fees(entry: float, qty: float, exit_fees: float) -> float:
        """The entry side at the configured taker rate (an estimate: the entry order's commission is not stored),
        the exit side as BingX charged it on the exit orders (_exit_summary)."""
        return CONFIG.journal.fee_round_trip / 2 * entry * qty + exit_fees

    async def _refinalize(self) -> None:
        """Closed trades whose exit fill was not listed at the close (1000PEPE 2026-10-06 11:07, the link failing):
        their result from BingX's fills, retried for 3 days."""
        with sqlite3.connect(self.db_path) as c:
            rows = c.execute("SELECT id, symbol, direction, opened_ms, closed_ms, qty, entry_fill, risk_usd FROM demo_trades "
                             "WHERE error = ? AND pnl_usd IS NULL AND closed_ms > ?",
                             (self.FILL_PENDING, int(time.time() * 1000) - 3 * 86_400_000)).fetchall()
        if not rows:
            return
        cache: Dict[str, List[Dict]] = {}
        for tid, symbol, d, opened, closed, qty, entry, risk in rows:
            side = 'sell' if d > 0 else 'buy'
            if symbol not in cache:
                # one request per coin (the earliest open of its pending rows), one failing coin does not stop the rest
                since = min(r[3] for r in rows if r[1] == symbol) - 5_000
                try:
                    cache[symbol] = await self._call('fetch_my_trades', symbol, since=since)
                except Exception as e:
                    logger.warning(f"Demo result recovery {symbol}: {e!r}")
                    cache[symbol] = []
            with sqlite3.connect(self.db_path) as c:
                nxt = c.execute("SELECT opened_ms, entry_order FROM demo_trades WHERE symbol = ? AND opened_ms > ? "
                                "AND entry_fill IS NOT NULL ORDER BY opened_ms LIMIT 1", (symbol, closed)).fetchone()
                others = {o for (o,) in c.execute("SELECT entry_order FROM demo_trades WHERE symbol = ? AND id != ? "
                                                  "AND entry_order IS NOT NULL", (symbol, tid))}
            cutoff = self._next_entry_cutoff(cache[symbol], nxt)
            exits = [f for f in self._exit_fills(cache[symbol], side, opened, closed, cutoff)
                     if str(f.get('order') or '') not in others]
            if not exits or not qty:
                continue
            exit_avg, closed_qty, exit_fees = await self._exit_summary(symbol, exits)
            if exit_avg is None or not 0.98 * qty <= closed_qty <= 1.02 * qty:
                # not proven complete: stays FILL_PENDING (no result rather than a partial one), retried for 3 days
                if time.time() * 1000 - closed > 6 * 3_600_000 and tid not in self._short_warned:
                    self._short_warned.add(tid)
                    logger.warning(f"Demo result recovery {symbol}: exit orders cover {closed_qty:g} of {qty:g} after "
                                   f"6h - result left empty")
                continue
            fees = self._fees(entry, qty, exit_fees)
            pnl = d * (exit_avg - entry) * qty - fees
            funding = await self._funding_paid(symbol, opened, closed)          # audit C12
            if funding is not None:
                pnl += funding
            with sqlite3.connect(self.db_path) as c:
                c.execute("UPDATE demo_trades SET exit_avg = ?, fees_usd = ?, pnl_usd = ?, r = ?, funding_usd = ?, "
                          "error = CASE WHEN fill_confirmed = 0 THEN ? ELSE NULL END WHERE id = ?",
                          (exit_avg, fees, pnl, pnl / risk if risk else None, funding, self.ENTRY_ESTIMATE, tid))
            logger.info(f"Demo result recovered {symbol}: {pnl:+.2f} USD ({pnl / risk if risk else 0:+.2f}R)")

    async def reconcile_loop(self, running) -> None:
        """Finalize demo trades the exchange closed on its own (stop / last target)."""
        while running():
            # resting limits every 10s: a filled limit has no stop until check_limits sees the fill (was up to 60s)
            for _ in range(6):
                await asyncio.sleep(10)
                if self.enabled and self.pending:
                    async with self._lock:
                        try:
                            await self.check_limits()
                        except Exception as e:
                            if time.time() - getattr(self, '_limits_warned', 0) > 60:   # once a minute, not every 10s
                                self._limits_warned = time.time()
                                logger.warning(f"Demo limits: {e!r}")
            if not self.enabled:
                continue
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
                        if trade.get('close_pending'):
                            # a close not confirmed flat (_close): again, its own reason, no limit hold
                            await self._close(trade, *trade['close_pending'])
                            continue
                        if age_ms > 120_000 and not self.card_is_open(trade['card_id']):
                            if (trade.get('from_limit') or str(trade.get('card_id', '')).rsplit('|', 1)[-1].startswith('c')) \
                                    and age_ms < ORPHAN_LIMIT_HOLD_MS:
                                # eng-84: BingX filled the resting limit, then the card's check of the touch vetoed it
                                # (against_btc ...) and expired it: the position was closed at market at a loss while its
                                # stop and targets already rested on BingX (live SOL / DOGE PO3: closed -0.5R, then went
                                # to TP3). A filled limit keeps its exchange stop / targets; only a stale one is closed
                                pass
                            elif not trade.get('no_stop') and age_ms < ORPHAN_EXCHANGE_HOLD_MS:
                                # eng-144: no market close - the position keeps its stop / targets on BingX and ends
                                # there (EXCHANGE); a market close of 30 orphans cost -9.2R on 11-21.10
                                if not trade.get('orphan_seen'):
                                    trade['orphan_seen'] = True
                                    logger.warning(f"Demo: {trade['symbol']} has no open card: left to its exchange stop")
                                    self.alert(f"⚠️ Демо {trade['symbol']}: карточки нет, позиция оставлена под стопом на бирже")
                            else:
                                logger.info(f"Demo: {trade['symbol']} has no open card any more: closing the orphan")
                                await self._close(trade, 'ORPHAN', None)
                                continue
                        if await self._position_qty(trade['symbol']) != 0:
                            self._flat_seen.pop(trade['card_id'], None)
                        else:
                            # eng-132: ONE empty answer is not flat (a glitchy fetch_positions at 10:04 on 2026-10-15
                            # made cancel_all take the stops of HYPE / UNI / XPL): two in a row, a pass apart
                            self._flat_seen[trade['card_id']] = self._flat_seen.get(trade['card_id'], 0) + 1
                            if self._flat_seen[trade['card_id']] < 2:
                                continue
                            self._flat_seen.pop(trade['card_id'], None)
                            await self._exchange()
                            try:
                                await self.ex.cancel_all_orders(trade['symbol'])
                            except Exception as e:
                                errors.report('executor.cancel_after_flat', e, f"{trade['symbol']}: its stop / targets may still rest on BingX")
                            await self._finalize(trade, 'EXCHANGE', None)
                            self._untracked_at = 0          # eng-132: the untracked check on the next pass, not in 5 min
                    except Exception as e:
                        # network / signature hiccups of the VST API retry next minute: one line; anything else with
                        # its traceback
                        import ccxt
                        transient = isinstance(e, (ccxt.NetworkError, ccxt.ExchangeNotAvailable)) or '109400' in str(e)
                        logger.warning(f"Demo reconcile {trade['symbol']}: {e!r}", exc_info=not transient)

    def _set_scale(self, trade_id: int, scale: Optional[float]) -> None:
        with sqlite3.connect(self.db_path) as c:
            c.execute("UPDATE demo_trades SET scale = ? WHERE id = ?", (scale, trade_id))

    def _set_basis(self, trade_id: int, basis: float) -> None:
        """BingX vs Binance at the entry (journaled: the venue gap the demo trades through)."""
        with sqlite3.connect(self.db_path) as c:
            c.execute("UPDATE demo_trades SET basis = ? WHERE id = ?", (basis, trade_id))

    def _insert(self, row: Dict) -> int:
        row.setdefault('logic_version', CONFIG.journal.logic_version)   # eng-144: demo statistics per logic version
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
    if not all(credentials()):
        print("No BINGX_API_KEY / BINGX_API_SECRET in the environment nor [executor] api_key / api_secret in config.local.toml")
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
