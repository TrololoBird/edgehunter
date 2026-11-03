# Read-only excerpts from /opt/edgehunter/executor.py at 79d08d5.
# Comments/docstrings removed by AST; not a standalone executable module.

def __init__(self, db_path: str='demo_trades.db'):
    cfg = CONFIG.executor
    self.enabled = bool(cfg.enabled and all(credentials()))
    self.db_path = db_path
    self._flat_seen: Dict[str, int] = {}
    self._finalized: Dict[str, tuple] = {}
    self._unknown_coins: Dict[str, float] = {}
    self._short_warned: set = set()
    self._band_warned: set = set()
    self._quotes_seen: Dict[str, tuple] = {}
    self.ex = None
    self.open: Dict[str, Dict] = {}
    self._tpsl_warned = 0.0
    self._tpsl_est = (0.0, 0)
    self._lock = asyncio.Lock()
    self._finished_cards: set = set()
    self.card_is_open = lambda card_id: True
    self.alert = lambda text: None
    self.pending: Dict[str, Dict] = {}
    self.pending_path = os.path.join(os.path.dirname(os.path.abspath(db_path)), 'demo_pending.json')
    self.unknown_path = os.path.join(os.path.dirname(os.path.abspath(db_path)), 'demo_unknown.json')
    try:
        with open(self.unknown_path, encoding='utf-8') as f:
            self._unknown_coins = {str(k): float(v) for (k, v) in json.load(f).items()}
    except (OSError, ValueError, AttributeError):
        pass
    try:
        with open(self.pending_path, encoding='utf-8') as f:
            self.pending = json.load(f)
    except (OSError, ValueError):
        pass
    self._markets_ready = False
    with sqlite3.connect(db_path) as c:
        c.execute(SCHEMA)
        c.execute('CREATE INDEX IF NOT EXISTS idx_demo_pending ON demo_trades(error, closed_ms)')
        have = {r[1] for r in c.execute('PRAGMA table_info(demo_trades)')}
        for (col, kind) in (('basis', 'REAL'), ('exit_ref', 'REAL'), ('no_stop', 'INTEGER'), ('scale', 'REAL'), ('entry_order', 'TEXT'), ('fill_confirmed', 'INTEGER'), ('funding_usd', 'REAL'), ('close_pending_reason', 'TEXT'), ('close_pending_r', 'REAL'), ('from_limit', 'INTEGER'), ('trail', 'INTEGER'), ('no_tp', 'INTEGER'), ('slip_bps', 'REAL'), ('latency_ms', 'INTEGER'), ('leverage', 'INTEGER'), ('logic_version', 'TEXT'), ('partial_done', 'INTEGER'), ('n_units', 'INTEGER'), ('r_unit', 'REAL'), ('exit_via', 'TEXT'), ('virt', 'INTEGER'), ('tp_done', 'INTEGER')):
            if col not in have:
                c.execute(f'ALTER TABLE demo_trades ADD COLUMN {col} {kind}')
        c.row_factory = sqlite3.Row
        for row in c.execute('SELECT * FROM demo_trades WHERE closed_ms IS NULL'):
            trade = dict(row)
            if trade.get('close_pending_reason') is not None:
                trade['close_pending'] = [trade['close_pending_reason'], trade['close_pending_r']]
            self.open[trade['card_id']] = trade
        c.execute('CREATE INDEX IF NOT EXISTS idx_demo_entry_order ON demo_trades(symbol, entry_order)')

async def _open(self, card_id: str, s) -> None:
    cfg = CONFIG.executor
    d = s.direction
    binance_now = float(s.last_price or s.levels['entry'])
    (symbol, scale) = await self._market_of(s.symbol, binance_now)
    if symbol is None:
        logger.info(f'Demo: {s.symbol} {s.group_key} skipped: {scale}')
        self._insert({'card_id': card_id, 'symbol': s.symbol, 'setup': s.group_key, 'strategy': s.mode, 'direction': d, 'opened_ms': int(time.time() * 1000), 'error': str(scale)[:300], 'closed_ms': int(time.time() * 1000), 'close_reason': 'NO_MARKET'})
        return
    quote = getattr(self, '_quote', None) or {}
    bx_last = float(quote.get('last') or binance_now * scale)
    ratio = bx_last / binance_now
    basis = ratio / scale - 1
    lv = {k: v * ratio if isinstance(v, (int, float)) and k in ('entry', 'sl', 'tp1', 'tp2', 'tp3') else v for (k, v) in s.levels.items()}
    fill_est = float((quote.get('ask') if d > 0 else quote.get('bid')) or bx_last)
    n_turtle = (getattr(s, 'plan', None) or {}).get('turtle_n')
    if n_turtle:
        lv['sl'] = fill_est - d * 2 * n_turtle * ratio
    reject = None
    if basis_reject(basis):
        reject = basis_reject(basis)
    elif d * (fill_est - lv['sl']) <= 0:
        reject = f"BingX {fill_est:.6g} already beyond the stop {lv['sl']:.6g}"
    elif s.levels.get('rr_tp1') is None and self._chase(s, lv, fill_est, d, n_turtle, ratio):
        reject = f'chase_limit: {self._chase(s, lv, fill_est, d, n_turtle, ratio)}'
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
        from strategies.geometry import is_synthetic
        tp1_real = not is_synthetic(s.levels.get('tp1_src'))
        if tp1_real and (plan.get('min_rr') is not None or plan.get('min_rr_on_tp1')) and (rrs[0] < need):
            reject = f"R:R to TP1 {rrs[0]:.2f} at BingX {fill_est:.6g} < {need:g} (the method's minimum)"
        elif tp1_real and floor > 0 and (need > 0) and (rrs[0] < floor):
            reject = f'R:R to TP1 {rrs[0]:.2f} at BingX {fill_est:.6g} < {floor:g}'
        elif plan_blend is not None and blend < need:
            reject = f'blended R:R {blend:.2f} at BingX {fill_est:.6g} < {need:g} (Binance plan {plan_blend:.2f})'
    if reject:
        logger.info(f'Demo: {s.symbol} {s.group_key} skipped: {reject} (basis {basis:+.3%})')
        self._insert({'card_id': card_id, 'symbol': s.symbol, 'setup': s.group_key, 'strategy': s.mode, 'direction': d, 'opened_ms': int(time.time() * 1000), 'error': f'{reject}; basis {basis:+.3%}', 'closed_ms': int(time.time() * 1000), 'close_reason': 'CHASE_LIMIT' if reject.startswith('chase_limit') else 'PRICE_GAP'})
        return
    scale = ratio
    ex = await self._exchange()
    no_slot = await self._ensure_sl_slot(symbol)
    if no_slot:
        logger.warning(f'Demo: {s.symbol} {s.group_key} skipped: {no_slot}')
        self._insert({'card_id': card_id, 'symbol': s.symbol, 'setup': s.group_key, 'strategy': s.mode, 'direction': d, 'opened_ms': int(time.time() * 1000), 'error': no_slot, 'closed_ms': int(time.time() * 1000), 'close_reason': 'NO_SLOT'})
        return
    balance = min(await self._balance(), cfg.account_usd)
    stop_dist = abs(fill_est - lv['sl'])
    if balance <= 0 or stop_dist <= 0:
        return
    risk_usd = balance * cfg.risk_pct / 100
    if (s.sig or {}).get('small_cap') or (s.sig or {}).get('smallcap'):
        risk_usd *= CONFIG.exchange.smallcap_risk_mult
    risk_usd *= self.regime_mult(s)
    n = (getattr(s, 'plan', None) or {}).get('turtle_n')
    risk_usd /= float(s.levels.get('risk_units') or 1.0)
    from strategies.geometry import cost_of
    fee = cost_of(fill_est, (s.sig or {}).get('volume_24h'), s.symbol)
    no_stop = bool((getattr(s, 'plan', None) or {}).get('no_stop'))
    leverage = 1 if no_stop else cfg.max_leverage
    if not no_stop and fill_est:
        frac = abs(fill_est - lv['sl']) / fill_est
        while leverage > 1 and 1.0 / leverage <= 1.2 * frac:
            leverage -= 1
    qty = min(risk_usd / (stop_dist + fee), balance * leverage / lv['entry'], cfg.max_notional_usd / lv['entry'])
    if n:
        fit = cfg.max_notional_usd / (lv['entry'] * CONFIG.strategies.turtle_max_units)
        if qty > fit:
            logger.info(f'Demo: {symbol} Turtle unit {qty:.6g} -> {fit:.6g} so {CONFIG.strategies.turtle_max_units} units fit ${cfg.max_notional_usd:,.0f} (risk at the stop {cfg.risk_pct * fit / qty:.2f}%)')
            qty = fit
    qty = float(ex.amount_to_precision(symbol, qty))
    min_qty = ((ex.markets[symbol].get('limits') or {}).get('amount') or {}).get('min') or 0
    if qty <= 0 or qty < min_qty:
        logger.info(f'Demo: {symbol} size {qty} below the minimum {min_qty}')
        return
    try:
        await ex.set_leverage(leverage, symbol, {'side': 'BOTH'})
    except Exception as e:
        errors.report('executor._open', e, f'Demo leverage {symbol}')
    (side, exit_side) = ('buy', 'sell') if d > 0 else ('sell', 'buy')
    import ccxt
    import uuid
    cid = f'pb{uuid.uuid4().hex[:24]}'
    try:
        try:
            order = await ex.create_order(symbol, 'market', side, qty, None, {'clientOrderId': cid})
        except (ccxt.NetworkError, ccxt.ExchangeNotAvailable):
            raise
        except Exception as e:
            import re
            m = re.search('position limit of ([0-9.]+) USDT', str(e))
            if not m:
                raise
            qty = float(ex.amount_to_precision(symbol, 0.9 * float(m.group(1)) / lv['entry']))
            if qty <= 0 or qty < min_qty:
                raise
            cid = f'pb{uuid.uuid4().hex[:24]}'
            order = await ex.create_order(symbol, 'market', side, qty, None, {'clientOrderId': cid})
    except (ccxt.NetworkError, ccxt.ExchangeNotAvailable) as e:
        order = await self._resolve_unknown_entry(symbol, d, cid, e)
        if order is None:
            raise
    fill = order.get('average') or order.get('price')
    filled = order.get('filled')
    if (not fill or not filled) and order.get('id'):
        try:
            o = await self._call('fetch_order', order['id'], symbol)
            fill = fill or o.get('average') or o.get('price')
            filled = filled or o.get('filled')
        except Exception as e:
            errors.report('executor._open', e, f'Demo fill price {symbol}')
    (pos_qty, pos_px) = await self._position_of(symbol, d)
    if pos_qty:
        filled = pos_qty
        fill = fill or pos_px
    confirmed = bool(fill and filled)
    if not confirmed:
        logger.warning(f'Demo ENTRY {symbol}: fill not confirmed by BingX (price {fill}, size {filled}): the quote / requested size stand in, the row is marked unconfirmed')
        self.alert(f'⚠️ Демо {symbol}: биржа не подтвердила цену/объём входа, записано как неподтверждённое')
    fill = float(fill or fill_est)
    qty = float(filled or 0) or qty
    trade = {'card_id': card_id, 'symbol': symbol, 'setup': s.group_key, 'strategy': s.mode, 'direction': d, 'opened_ms': int(time.time() * 1000), 'entry_plan': lv['entry'], 'entry_fill': fill, 'qty': qty, 'sl': lv['sl'], **{k: None if (getattr(s, 'plan', None) or {}).get('no_tp') else lv[k] for k in ('tp1', 'tp2', 'tp3')}, 'risk_usd': qty * (abs(fill - lv['sl']) + fee), 'no_stop': int(no_stop), 'slip_bps': d * (fill - fill_est) / fill_est * 10000.0 if fill_est else None, 'latency_ms': int(time.time() * 1000 - float(getattr(s, 'entered_at', 0) or 0) * 1000) if getattr(s, 'entered_at', None) else None, 'leverage': leverage, 'n_units': 1, 'entry_order': str(order.get('id') or '') or None, 'fill_confirmed': int(confirmed), 'trail': int(bool((getattr(s, 'plan', None) or {}).get('trail_after_tp1'))), 'no_tp': int(bool((getattr(s, 'plan', None) or {}).get('no_tp')))}
    try:
        if not no_stop:
            await self._place_stop(symbol, d, qty, lv['sl'])
        elif lv.get('sl'):
            far = fill - 3 * (lv['entry'] - lv['sl']) if lv.get('entry') else None
            if far and far > 0:
                await self._place_stop(symbol, d, qty, far)
    except Exception as e:
        trade['id'] = self._insert(trade)
        logger.warning(f'Demo ENTRY {symbol}: stop not placed ({e!r}): closed at market')
        self.alert(f'⛔ Демо {symbol}: стоп не поставлен ({str(e)[:120]}), позиция закрыта рынком')
        await self._close(trade, 'NO_STOP', None)
        return
    plan = getattr(s, 'plan', None) or {}
    trade['id'] = self._insert(trade)
    (trade['unit_qty'], trade['scale']) = (qty, scale)
    self._set_scale(trade['id'], scale)
    self._set_basis(trade['id'], basis)
    self.open[card_id] = trade
    await self._place_tps(trade, self.exit_parts(ex, trade, qty, bool(plan.get('trail_after_tp1')), bool(plan.get('no_tp'))), min_qty)
    logger.info(f"Demo ENTRY {symbol} {s.group_key} {('long' if d > 0 else 'short')} {qty} @ {fill:.6g}, SL {lv['sl']:.6g}, risk ${trade['risk_usd']:.2f}")

def _insert(self, row: Dict) -> int:
    row.setdefault('logic_version', CONFIG.journal.logic_version)
    cols = [k for k in row if k != 'id']
    with sqlite3.connect(self.db_path) as c:
        cur = c.execute(f"INSERT INTO demo_trades ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", [row[k] for k in cols])
        return cur.lastrowid

async def on_add(self, s) -> None:
    if not self.enabled or not s.entered_at:
        return
    card_id = f'{s.symbol}|{s.group_key}|{int(s.entered_at)}'
    if self.open.get(card_id) is None:
        return
    async with self._lock:
        trade = self.open.get(card_id)
        if trade is None or card_id in getattr(self, '_finished_cards', ()):
            return
        try:
            ex = await self._exchange()
            (symbol, d) = (trade['symbol'], trade['direction'])
            unit = float(trade.get('unit_qty') or float(trade['qty']) / max(1, len(s.units) - 1))
            import ccxt
            import uuid
            (before, before_px) = await self._position_of(symbol, d, strict=True)
            cid = f'pb{uuid.uuid4().hex[:24]}'
            try:
                order = await ex.create_order(symbol, 'market', 'buy' if d > 0 else 'sell', unit, None, {'clientOrderId': cid})
            except (ccxt.NetworkError, ccxt.ExchangeNotAvailable) as e:
                logger.warning(f'Demo ADD {symbol}: outcome unknown ({e!r}): resolving by position')
                order = {}
                await asyncio.sleep(4)
            after = after_px = None
            for wait in (0, 3, 6, 10, 20, 30):
                await asyncio.sleep(wait)
                try:
                    (after, after_px) = await self._position_of(symbol, d, strict=True)
                except Exception as e:
                    logger.warning(f'Demo ADD {symbol}: position unreadable ({e!r}), retrying')
                    continue
                if after - before > 0:
                    break
            if after is None:
                worst = before + unit
                self.alert(f'⚠️ Демо {symbol}: исход добора неизвестен (позиция не читается), стоп поставлен на максимально возможный объём {worst:g}')
                trade['add_unknown'] = True
                try:
                    new = await self._place_stop(symbol, d, worst, float(trade['sl']))
                    await self._cancel_orders(symbol, keep=new.get('id'), stops_only=True)
                except Exception as e:
                    errors.report('executor.on_add', e, f'Demo protective stop after an unknown add {symbol}')
                return
            added = after - before
            if added <= 0:
                logger.warning(f'Demo ADD {symbol}: no growth of the position ({before} -> {after}): not added')
                self.alert(f'⚠️ Демо {symbol}: добор не подтверждён позицией ({before} → {after}), стоп сверит проверка покрытия')
                return
            if after_px and before_px and (added > 0):
                fill = (after_px * after - before_px * before) / added
            else:
                fill = float(order.get('average') or order.get('price') or 0) or float(s.last_price)
            total = after
            if abs(added - unit) > 1e-09 * max(1.0, unit):
                logger.warning(f'Demo ADD {symbol}: filled {added} of the requested {unit}')
            trade['entry_fill'] = after_px or (float(trade['entry_fill']) * float(trade['qty']) + fill * added) / total
            (trade['qty'], trade['unit_qty']) = (total, unit)
            scale = float(trade.get('scale') or 0.0)
            if not scale and trade.get('entry_plan') and s.levels.get('entry'):
                scale = float(trade['entry_plan']) / float(s.levels['entry'])
                trade['scale'] = scale
            scale = scale or 1.0
            try:
                new = await self._place_stop(symbol, d, total, s.levels['sl'] * scale)
            except Exception as e:
                logger.warning(f'Demo ADD {symbol}: stop for {total} not placed ({e!r}): closed at market')
                self.alert(f'⛔ Демо {symbol}: стоп после добора не поставлен, закрыта рынком')
                await self._close(trade, 'NO_STOP', None)
                return
            await self._cancel_orders(symbol, keep=new.get('id'))
            trade['sl'] = s.levels['sl'] * scale
            if not (getattr(s, 'plan', None) or {}).get('no_tp'):
                for k in (1, 2, 3):
                    trade[f'tp{k}'] = s.levels[f'tp{k}'] * scale
                third = float(ex.amount_to_precision(symbol, total / 3))
                await self._place_tps(trade, zip((1, 2, 3), (third, third, float(ex.amount_to_precision(symbol, total - 2 * third)))))
            with sqlite3.connect(self.db_path) as c:
                c.execute('UPDATE demo_trades SET qty = ?, entry_fill = ?, sl = ?, n_units = ? WHERE id = ?', (total, trade['entry_fill'], s.levels['sl'] * scale, len(s.units), trade['id']))
            trade['n_units'] = len(s.units)
            logger.info(f"Demo ADD {symbol} unit {len(s.units)}: +{added} @ {fill:.6g}, position {total}, stop {s.levels['sl'] * scale:.6g}")
        except Exception as e:
            logger.warning(f"Demo add-unit failed for {trade['symbol']}: {e!r}")

def risk_limit(self) -> Optional[str]:
    cfg = CONFIG.executor
    day0 = int(time.time() // 86400 * 86400 * 1000)
    (loss_r, max_trades, pause_n) = (x if 0 < x < LIMIT_OFF_AT else 0 for x in (cfg.daily_loss_r, cfg.max_trades_day, cfg.pause_losses))
    if not (loss_r or max_trades or pause_n):
        return None
    try:
        with sqlite3.connect(self.db_path) as c:
            closed = c.execute('SELECT r FROM demo_trades WHERE closed_ms >= ? AND r IS NOT NULL', (day0,)).fetchall()
            opened = c.execute('SELECT COUNT(*) FROM demo_trades WHERE opened_ms >= ? AND entry_fill IS NOT NULL', (day0,)).fetchone()[0]
            last = c.execute('SELECT r, closed_ms FROM demo_trades WHERE r IS NOT NULL ORDER BY closed_ms DESC LIMIT ?', (pause_n,)).fetchall() if pause_n else []
    except sqlite3.Error as e:
        return f'risk limits unreadable: {e!r}'
    opened += sum((1 for p in self.pending.values() if not p.get('skip')))
    day_r = sum((r for (r,) in closed))
    if loss_r and day_r <= -loss_r:
        return f'daily loss limit: {day_r:+.2f}R today'
    if max_trades and opened >= max_trades:
        return f'daily trade limit: {opened} trades today'
    if pause_n and len(last) == pause_n and all((r < 0 for (r, _) in last)) and (time.time() * 1000 - last[0][1] < cfg.pause_hours * 3600000):
        return f'pause after {cfg.pause_losses} losses in a row'
    return None

def entry_gate(self, s) -> Optional[str]:
    cfg = CONFIG.executor
    d = s.direction
    if s.group_key in cfg.demo_off_setups:
        return f'setup off on demo: {s.group_key}'
    hit = self.cluster_hit(d)
    if hit is not None:
        return f"cluster: {hit} entered {('long' if d > 0 else 'short')} within {cfg.cluster_entry_sec // 60} min"
    return None

def cluster_hit(self, d: int) -> Optional[str]:
    window = CONFIG.executor.cluster_entry_sec
    if window <= 0:
        return None
    since = int((time.time() - window) * 1000)
    try:
        with sqlite3.connect(self.db_path) as c:
            row = c.execute('SELECT symbol FROM demo_trades WHERE direction = ? AND opened_ms >= ? AND entry_fill IS NOT NULL ORDER BY opened_ms DESC LIMIT 1', (d, since)).fetchone()
    except sqlite3.Error:
        row = None
    if row is not None:
        return row[0]
    return next((p.get('symbol') for p in self.pending.values() if not p.get('skip') and p.get('direction') == d and (max(p.get('placed_ms') or 0, p.get('entered_ms') or 0) >= since)), None)

async def _ensure_sl_slot(self, symbol: str) -> Optional[str]:
    cfg = CONFIG.executor
    (at, est) = self._tpsl_est
    if time.time() - at < 8 and est < cfg.tpsl_cap - 30:
        self._tpsl_est = (at, est + 5)
        return None
    ex = await self._exchange()
    try:
        n = sum((1 for o in await ex.fetch_open_orders() if 'STOP' in (t := str((o.get('info') or {}).get('type') or o.get('type') or '').upper()) or 'TAKE_PROFIT' in t))
    except Exception as e:
        logger.debug(f'Demo TP/SL count {symbol}: {e!r}')
        return None
    self._tpsl_est = (time.time(), n + 5)
    if n >= cfg.tpsl_warn and time.time() - self._tpsl_warned > 600:
        self._tpsl_warned = time.time()
        logger.warning(f'Demo: {n} of {cfg.tpsl_cap} TP / SL orders on BingX (warning from {cfg.tpsl_warn})')
    for _ in range(cfg.tpsl_reserve + 2):
        if n <= cfg.tpsl_cap - cfg.tpsl_reserve:
            return None
        if not await self._free_tp_slot(symbol):
            return f'{n} of {cfg.tpsl_cap} TP / SL orders on BingX: no slot left for the stop'
        n -= 1
        self._tpsl_est = (time.time(), n + 5)
    return None
