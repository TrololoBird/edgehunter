# Exact AST extracts from executor.py commit 79d08d5; docstrings removed; code is for audit reading.

# --- _place_stop ---

async def _place_stop(self, symbol: str, d: int, qty: float, price: float) -> Dict:
    ex = await self._exchange()

    async def place():
        return await ex.create_order(symbol, 'market', 'sell' if d > 0 else 'buy', qty, None, {'stopLossPrice': float(ex.price_to_precision(symbol, price)), 'reduceOnly': True, 'workingType': 'MARK_PRICE'})
    for attempt in range(3):
        try:
            return await place()
        except Exception as e:
            if '110206' not in str(e) or attempt == 2 or (not await self._free_tp_slot(symbol)):
                raise

# --- _place_tps ---

async def _place_tps(self, trade: Dict, parts, min_qty: float=0.0, on_exchange: int=1) -> None:
    ex = await self._exchange()
    (symbol, d) = (trade['symbol'], trade['direction'])
    parts = list(parts)
    if CONFIG.executor.virtual_tps and (parts or on_exchange == 0):
        trade['virt'] = 2 if parts and parts[0][0] == 0 or trade.get('partial_done') else 1
        trade['tp_done'] = int(trade.get('tp_done') or 0)
        if trade.get('id'):
            with sqlite3.connect(self.db_path) as c:
                c.execute('UPDATE demo_trades SET virt = ?, tp_done = ? WHERE id = ?', (trade['virt'], trade['tp_done'], trade['id']))
        parts = parts[:on_exchange]
    for (k, amount) in parts:
        if amount <= 0 or amount < min_qty or (not trade.get(f'tp{k}')):
            continue
        try:
            await ex.create_order(symbol, 'market', 'sell' if d > 0 else 'buy', amount, None, {'takeProfitPrice': float(ex.price_to_precision(symbol, float(trade[f'tp{k}']))), 'reduceOnly': True})
        except Exception as err:
            fail: Exception = err
            try:
                last = float((await ex.fetch_ticker(symbol)).get('last') or 0)
            except Exception:
                last = 0.0
            if last and d * (last - float(trade[f'tp{k}'])) >= 0:
                try:
                    await ex.create_order(symbol, 'market', 'sell' if d > 0 else 'buy', amount, None, {'reduceOnly': True})
                    logger.info(f'Demo TP{k} {symbol}: price {last} already beyond the target, {amount} taken at market')
                    continue
                except Exception as e2:
                    fail = e2
            errors.report('executor._place_tps', fail, f'Demo TP{k} {symbol}: the trade keeps its stop')

# --- _cancel_orders ---

async def _cancel_orders(self, symbol: str, keep: str=None, stops_only: bool=False) -> None:
    ex = await self._exchange()
    for o in await ex.fetch_open_orders(symbol):
        if o.get('id') == keep or (stops_only and (not self._is_stop(o))):
            continue
        try:
            await ex.cancel_order(o['id'], symbol)
        except Exception as e:
            errors.report('executor._cancel_orders', e, f"Demo cancel {symbol} {o.get('id')}")

# --- _cancel_targets ---

async def _cancel_targets(self, symbol: str) -> None:
    ex = await self._exchange()
    for o in await ex.fetch_open_orders(symbol):
        if not self._is_stop(o):
            try:
                await ex.cancel_order(o['id'], symbol)
            except Exception as e:
                errors.report('executor._cancel_targets', e, f"Demo cancel {symbol} {o.get('id')}")

# --- _dedupe_stops ---

async def _dedupe_stops(self) -> None:
    ex = await self._exchange()
    for trade in list(self.open.values()):
        stops = [o for o in await ex.fetch_open_orders(trade['symbol']) if self._is_stop(o)]
        if not stops:
            await self._restore_stop(trade)
            continue
        if not (trade.get('no_stop') or trade.get('strategy') == 'connors' or (not trade.get('sl'))):
            try:
                left = await self._position_qty(trade['symbol'])
            except Exception as e:
                errors.report('executor._dedupe_stops', e, f"Demo position {trade['symbol']}")
                left = 0.0
            if left > 0 and trade.pop('add_unknown', False) and (abs(left - float(trade.get('qty') or 0)) > 1e-09 * max(1.0, left)):
                logger.warning(f"Demo {trade['symbol']}: position {left} after an unknown add (booked {trade.get('qty')}): booked as is")
                trade['qty'] = left
                with sqlite3.connect(self.db_path) as c:
                    c.execute('UPDATE demo_trades SET qty = ? WHERE id = ?', (left, trade['id']))
            ref0 = float(trade.get('sl') or 0)
            spx = lambda o: float((o.get('info') or {}).get('stopPrice') or o.get('stopPrice') or o.get('triggerPrice') or 0)
            stays = min(stops, key=lambda o: abs(spx(o) - ref0)) if ref0 else max(stops, key=lambda o: o.get('timestamp') or 0)
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
        px = lambda o: float((o.get('info') or {}).get('stopPrice') or o.get('stopPrice') or o.get('triggerPrice') or 0)
        keep = min(stops, key=lambda o: abs(px(o) - ref)) if ref else max(stops, key=lambda o: o.get('timestamp') or 0)
        for o in stops:
            if o is keep:
                continue
            try:
                await ex.cancel_order(o['id'], trade['symbol'])
                logger.warning(f"Demo {trade['symbol']}: extra stop {px(o):.6g} cancelled (kept {px(keep):.6g})")
            except Exception as e:
                errors.report('executor._dedupe_stops', e, f"Demo extra stop {trade['symbol']}")

# --- _restore_stop ---

async def _restore_stop(self, trade: Dict) -> None:
    if trade.get('no_stop') or trade.get('strategy') == 'connors' or (not trade.get('sl')):
        return
    (symbol, d, sl) = (trade['symbol'], trade['direction'], float(trade['sl']))
    left = await self._position_qty(symbol)
    if left <= 0:
        return
    ex = await self._exchange()
    t = await ex.fetch_ticker(symbol)
    last = float(t.get('last') or 0)
    if last and d * (last - sl) <= 0:
        logger.warning(f'Demo {symbol}: no stop on BingX and the price {last:.6g} is beyond it ({sl:.6g}): closed')
        self.alert(f'⛔ Демо {symbol}: стопа на бирже не было, цена уже за стопом, закрыта рынком')
        await self._close(trade, 'SL', None)
        return
    await self._place_stop(symbol, d, left, sl)
    logger.warning(f'Demo {symbol}: the position {left} had no stop on BingX: re-placed at {sl:.6g}')
    self.alert(f'⚠️ Демо {symbol}: у позиции не было стопа на бирже, поставлен заново ({sl:.6g})')

# --- check_limits ---

async def check_limits(self) -> None:
    ex = await self._exchange()
    now = time.time() * 1000
    terminal = {'canceled', 'cancelled', 'closed', 'expired', 'rejected'}
    for (key, p) in list(self.pending.items()):
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
                self.pending[key] = {'skip': True, 'reason': f"limit {o['status']} without a fill"}
                self._save_pending()
        elif p.get('entered') and now - p['entered_ms'] > CONFIG.executor.limit_wait_min * 60000:
            await self._cancel_limit(key, f'Binance touched the line, BingX did not fill within {CONFIG.executor.limit_wait_min} min', record=True)

# --- on_target ---

async def on_target(self, s, k: int) -> None:
    if not self.enabled or not s.entered_at or k not in (1, 2):
        return
    card_id = f'{s.symbol}|{s.group_key}|{int(s.entered_at)}'
    trade = self.open.get(card_id) or self.open.get(f'{s.symbol}|{s.group_key}|c{int(s.created)}')
    if trade is None or not trade.get('virt') or int(trade.get('tp_done') or 0) >= k or (not trade.get('qty')):
        return
    async with self._lock:
        if all((t is not trade for t in self.open.values())) or int(trade.get('tp_done') or 0) >= k:
            return
        try:
            ex = await self._exchange()
            (symbol, d) = (trade['symbol'], trade['direction'])
            await self._cancel_targets(symbol)
            await asyncio.sleep(2)
            left = await self._position_qty(symbol)
            if left <= 0:
                return
            want = float(trade['qty']) * self._left_fraction(trade, k)
            min_qty = ((ex.markets[symbol].get('limits') or {}).get('amount') or {}).get('min') or 0
            import ccxt
            try:
                excess = float(ex.amount_to_precision(symbol, left - want)) if left > want else 0.0
            except ccxt.InvalidOrder:
                excess = 0.0
            if excess > 0 and excess >= min_qty:
                await ex.create_order(symbol, 'market', 'sell' if d > 0 else 'buy', excess, None, {'reduceOnly': True})
            else:
                excess = 0.0
            trade['tp_done'] = k
            with sqlite3.connect(self.db_path) as c:
                c.execute('UPDATE demo_trades SET tp_done = ? WHERE id = ?', (k, trade['id']))
            logger.info(f"Demo TP{k} {symbol}: {excess} closed at market (virtual target), {('rest' if excess else 'already out')} {max(left - excess, 0):.6g}")
        except Exception as e:
            errors.report('executor.on_target', e, f'Demo TP{k} {s.symbol}: retried on the next sync')

# --- on_partial ---

async def on_partial(self, s) -> None:
    cfg = CONFIG.executor
    if not self.enabled or not s.entered_at or (not cfg.partial_share):
        return
    card_id = f'{s.symbol}|{s.group_key}|{int(s.entered_at)}'
    trade = self.open.get(card_id) or self.open.get(f'{s.symbol}|{s.group_key}|c{int(s.created)}')
    if trade is None or trade.get('partial_done') or trade.get('units') or (not trade.get('qty')):
        return
    async with self._lock:
        if all((t is not trade for t in self.open.values())):
            return
        try:
            ex = await self._exchange()
            (symbol, d, qty) = (trade['symbol'], trade['direction'], float(trade['qty']))
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
                            if '109400' in str(e):
                                logger.info(f"Demo partial {symbol}: order {o.get('id')} already gone (filled)")
                            else:
                                errors.report('executor.on_partial', e, f"Demo partial {symbol}: cancel {o.get('id')}")
                left = await self._position_qty(symbol)
                if left <= qty * (rest_share + 0.05):
                    done = 'out by its tp0 meanwhile'
                else:
                    half = float(ex.amount_to_precision(symbol, left - qty * rest_share))
                    if half > 0:
                        await ex.create_order(symbol, 'market', 'sell' if d > 0 else 'buy', half, None, {'reduceOnly': True})
                    done = f'{half} closed at market'
                rest = await self._position_qty(symbol)
                if rest > 0:
                    trade['partial_done'] = 1
                    await self._place_tps(trade, self.tp_parts(ex, symbol, rest, bool(trade.get('trail')), bool(trade.get('no_tp'))), on_exchange=0)
            else:
                return
            trade['partial_done'] = 1
            with sqlite3.connect(self.db_path) as c:
                c.execute('UPDATE demo_trades SET partial_done = 1 WHERE id = ?', (trade['id'],))
            logger.info(f'Demo PARTIAL {symbol}: {done}')
        except Exception as e:
            logger.warning(f'Demo partial {s.symbol}: {e!r}')

# --- _close ---

async def _close(self, trade: Dict, reason: str, journal_r: Optional[float], passive: bool=False) -> None:
    self.open.setdefault(trade['card_id'], trade)
    trade['close_pending'] = [reason, journal_r]
    try:
        with sqlite3.connect(self.db_path) as c:
            c.execute('UPDATE demo_trades SET close_pending_reason = ?, close_pending_r = ? WHERE id = ? AND closed_ms IS NULL', (reason, journal_r, trade['id']))
    except sqlite3.Error as e:
        errors.report('executor._close', e, 'Demo close intent not persisted')
    ex = await self._exchange()
    (symbol, d) = (trade['symbol'], trade['direction'])
    side = 'sell' if d > 0 else 'buy'
    try:
        for o in await ex.fetch_open_orders(symbol):
            if not self._is_stop(o):
                try:
                    await ex.cancel_order(o['id'], symbol)
                except Exception as e:
                    errors.report('executor._close', e, f'Demo cancel TP {symbol}')
    except Exception as e:
        errors.report('executor._close', e, f'Demo cancel {symbol}')
    left = await self._position_qty(symbol)
    if left > 0 and passive:
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
            except Exception as e:
                logger.debug(f'Demo cancel passive close {symbol}: {e!r}')
        except Exception as e:
            if '109400' in str(e) or '101290' in str(e):
                logger.debug(f'Demo passive close {symbol}: {e!r}')
            else:
                errors.report('executor._close', e, f'Demo passive close {symbol}')
        left = await self._position_qty(symbol)
    if left > 0:
        try:
            await ex.create_order(symbol, 'market', side, left, None, {'reduceOnly': True})
        except Exception as e:
            if '101290' in str(e) and await self._position_qty(symbol) == 0:
                reason = 'EXCHANGE'
            elif '102202' in str(e):
                t = await ex.fetch_ticker(symbol)
                px = float((t.get('bid') if d > 0 else t.get('ask')) or t.get('last'))
                await ex.create_order(symbol, 'limit', side, left, px, {'reduceOnly': True})
                if symbol not in self._band_warned:
                    self._band_warned.add(symbol)
                    logger.warning(f"Demo: {symbol} market close rejected by BingX's price band: reduce-only limit {left} @ {px} (re-placed each pass until filled)")
                self.open.setdefault(trade['card_id'], trade)
                return
            else:
                self.open.setdefault(trade['card_id'], trade)
                self.alert(f'⚠️ Демо {symbol}: закрытие ({reason}) не прошло ({str(e)[:120]}), стоп на месте, повтор')
                raise
    seen: List[bool] = []
    for wait in (2, 2, 2, 2):
        await asyncio.sleep(wait)
        seen.append(await self._position_qty(symbol) != 0)
        if seen[-2:] == [False, False] or seen[-3:] == [True, True, True]:
            break
    if seen[-2:] != [False, False]:
        logger.warning(f'Demo {symbol}: position not confirmed flat after the close (reads {seen}): stops kept, trade stays tracked')
        trade['close_pending'] = [reason, journal_r]
        self.open.setdefault(trade['card_id'], trade)
        return
    try:
        await ex.cancel_all_orders(symbol)
    except Exception as e:
        errors.report('executor._close', e, f'Demo cancel {symbol}')
    await self._finalize(trade, reason, journal_r)

# --- close_untracked ---

async def close_untracked(self) -> None:
    ex = await self._exchange()
    mine = {t['symbol'] for t in self.open.values()} | {p.get('symbol') for p in self.pending.values() if not p.get('skip')}
    positions = await ex.fetch_positions()
    await self._release_unknown(ex, positions)
    for pos in positions:
        qty = float(pos.get('contracts') or 0)
        if not qty or pos['symbol'] in mine:
            continue
        last = self._finalized.get(pos['symbol'])
        if last and time.time() - last[1] < 900 and last[0].get('id') and ((1 if pos.get('side') == 'long' else -1) == last[0].get('direction')) and (qty <= float(last[0].get('qty') or 0) * 1.001):
            trade = last[0]
            await asyncio.sleep(5)
            if await self._position_qty(pos['symbol']) <= 0:
                continue
            with sqlite3.connect(self.db_path) as c:
                c.execute('UPDATE demo_trades SET closed_ms = NULL, close_reason = NULL, exit_avg = NULL, fees_usd = NULL, pnl_usd = NULL, r = NULL, journal_r = NULL, error = NULL WHERE id = ?', (trade['id'],))
            self.open[trade['card_id']] = trade
            self._finalized.pop(pos['symbol'], None)
            logger.warning(f"Demo: {pos['symbol']} was finalized {time.time() - last[1]:.0f}s ago but BingX still holds {qty}: back in tracking")
            self.alert(f"⚠️ Демо {pos['symbol']}: позиция жива после закрытия в базе, возвращена в отслеживание")
            try:
                await self._restore_stop(trade)
                min_qty = ((ex.markets[trade['symbol']].get('limits') or {}).get('amount') or {}).get('min') or 0
                await self._place_tps(trade, self.exit_parts(ex, trade, qty, bool(trade.get('trail')), bool(trade.get('no_tp'))), min_qty, on_exchange=0 if trade.get('virt') else 1)
            except Exception as e:
                errors.report('executor.close_untracked', e, f"Demo re-protect {trade['symbol']}")
            continue
        d = 1 if pos.get('side') == 'long' else -1
        entry = float(pos.get('entryPrice') or 0)
        trade = {'card_id': f"{pos['symbol']}|UNTRACKED|{int(time.time())}", 'symbol': pos['symbol'], 'setup': 'UNTRACKED', 'strategy': None, 'direction': d, 'opened_ms': int(time.time() * 1000), 'entry_plan': entry, 'entry_fill': entry, 'qty': qty, 'error': 'a BingX position no card owned (lost limit fill): closed at market'}
        trade['id'] = self._insert(trade)
        logger.warning(f"Demo: untracked BingX position {pos['symbol']} {pos.get('side')} {qty}: closed at market")
        self.alert(f"⚠️ Демо: чужая позиция {pos['symbol']} {pos.get('side')} {qty} без карточки, закрыта рынком")
        await self._close(trade, 'UNTRACKED', None)

# --- _resolve_unknown_entry ---

async def _resolve_unknown_entry(self, symbol: str, d: int, cid: str, err: Exception) -> Optional[Dict]:
    logger.warning(f'Demo ENTRY {symbol}: outcome unknown ({err!r}): resolving by client id {cid} / position')
    flat = 0
    for wait in (2, 4, 8, 15):
        await asyncio.sleep(wait)
        try:
            (qty, px) = await self._position_of(symbol, d, strict=True)
        except Exception as e:
            errors.report('executor._resolve_unknown_entry', e, f'Demo position {symbol}')
            continue
        if qty:
            return {'id': None, 'filled': qty, 'average': px}
        flat += 1
        if flat >= 3:
            logger.info(f'Demo ENTRY {symbol}: no position after the lost reply (3 reads): not filled')
            return None
    raise EntryUnknown(f'entry {cid} on {symbol}: the exchange stayed unreadable, outcome unknown')

# --- reconcile_loop ---

async def reconcile_loop(self, running) -> None:
    while running():
        for _ in range(6):
            await asyncio.sleep(10)
            if self.enabled and self.pending:
                async with self._lock:
                    try:
                        await self.check_limits()
                    except Exception as e:
                        if time.time() - getattr(self, '_limits_warned', 0) > 60:
                            self._limits_warned = time.time()
                            logger.warning(f'Demo limits: {e!r}')
        if not self.enabled:
            continue
        if time.time() - getattr(self, '_untracked_at', 0) > 300:
            self._untracked_at = time.time()
            async with self._lock:
                try:
                    await self.close_untracked()
                except Exception as e:
                    logger.warning(f'Demo untracked check: {e!r}')
                try:
                    await self._refinalize()
                except Exception as e:
                    logger.warning(f'Demo result recovery: {e!r}')
                try:
                    await self._dedupe_stops()
                except Exception as e:
                    logger.warning(f'Demo stop check: {e!r}')
        if not self.open:
            continue
        async with self._lock:
            for trade in list(self.open.values()):
                try:
                    age_ms = time.time() * 1000 - trade['opened_ms']
                    if trade.get('close_pending'):
                        await self._close(trade, *trade['close_pending'])
                        continue
                    if age_ms > 120000 and (not self.card_is_open(trade['card_id'])):
                        if (trade.get('from_limit') or str(trade.get('card_id', '')).rsplit('|', 1)[-1].startswith('c')) and age_ms < ORPHAN_LIMIT_HOLD_MS:
                            pass
                        elif not trade.get('no_stop') and age_ms < ORPHAN_EXCHANGE_HOLD_MS:
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
                        self._untracked_at = 0
                except Exception as e:
                    import ccxt
                    transient = isinstance(e, (ccxt.NetworkError, ccxt.ExchangeNotAvailable)) or '109400' in str(e)
                    logger.warning(f"Demo reconcile {trade['symbol']}: {e!r}", exc_info=not transient)

# --- sync_targets ---

async def sync_targets(self, cards) -> None:
    for s in cards:
        if s.entered_at and (not s.finished) and (s.best_target in (1, 2)):
            await self.on_target(s, int(s.best_target))
