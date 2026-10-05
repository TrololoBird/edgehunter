"""
Market briefings and watch alerts for the owner's Telegram channel (the owner's request 2026-10-05: BTC, ETH, gold and
oil lead the altcoin market; the session opens move it).

- Briefings before the Asian (02:30 MSK), London (09:30) and New York (16:00) opens: per watched coin the top-down
  bias (strategies/bias.py: momentum blend, week, day, 4h), the key zones of the 1h+ map (the same map the plans
  use) with what holding / losing each means, the base / alternative scenario with its invalidation, the day's macro
  releases, BTC / USDT dominance and the market's breadth.
- Evening recap (23:30 MSK): which of the morning's zones were tested / broken, where each coin closed vs its scenario.
- Watch alerts: a 1h close beyond a briefing zone (acceptance) or a sweep of it with a close back (rejection); a market
  shock (a watched coin's 15m move >= shock_z of its typical 15m move, with the universe's breadth); a change of BTC /
  ETH / gold / oil bias; the bot's trades (cards via Notifier events, the demo's fills / exits from demo_trades.db);
  anomalies of the watched coins (liquidation cascades, whales, OI surges / flushes); the bot's health (venues down,
  failing components, the demo's daily risk stop).

Information built from mechanical rules, not advice. Every message goes through Notifier.post (Telegram only).
"""
import asyncio
import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import errors
from config import CONFIG

logger = logging.getLogger(__name__)
MSK = ZoneInfo('Europe/Moscow')
NY = ZoneInfo('America/New_York')
HOUR_MS = 3_600_000

# kinds that are no price-action zone of a briefing (models / pullable orders / dealer positions)
SKIP_KINDS = {'liq_est', 'liq_hl', 'book', 'wall', 'liq_hit'}
BIAS_RU = {'bull': 'бычье', 'bear': 'медвежье', 'range': 'флэт', 'conflict': 'конфликт ТФ', None: 'нет данных'}
ANOMALY_LABELS = ('LIQ CASCADE', 'WHALES BUY', 'WHALES SELL', 'OI SURGE', 'OI FLUSH', 'SHORT SQUEEZE', 'LONG FLUSH')


def _short(symbol: str) -> str:
    return symbol.split('/')[0]


def _fmt(p: float) -> str:
    if p >= 1000:
        return f"{p:,.0f}".replace(',', ' ')
    if p >= 10:
        return f"{p:.2f}"
    return f"{p:.6g}"


def _arrow(x: int) -> str:
    return {1: '↑', -1: '↓', 0: '→'}.get(x, '?')


def _label_rank(label: str) -> int:
    """Higher timeframes first: weekly / previous week, daily / previous day, 4h, 1h, sessions / profile, 15m."""
    for k, r in (('1w', 0), ('PW', 0), ('week', 0), ('1d', 1), ('PD', 1), ('day', 2), ('4h', 2), ('POC', 3),
                 ('VA', 3), ('1h', 4), ('Asia', 4), ('London', 4), ('New York', 4), ('EQ', 4), ('15m', 9)):
        if k in label:
            return r
    return 5


def macro_today(now: datetime) -> List[Tuple[datetime, str]]:
    """Today's (MSK) US releases: the calendar's dated CPI / FOMC plus the regular ones by their publication rule
    (NFP the first Friday 08:30 NY, ISM manufacturing the first business day 10:00, ISM services the third business
    day 10:00, jobless claims every Thursday 08:30) - rules, not a published calendar: holidays / shutdowns move them."""
    import macro_calendar
    day = now.astimezone(MSK).date()
    out = []
    for t, name in macro_calendar.TIMES:
        dt = datetime.fromtimestamp(t / 1000, MSK)
        if dt.date() == day:
            out.append((dt, name))
    ny_day = datetime(day.year, day.month, day.day, 12, tzinfo=MSK).astimezone(NY).date()
    first = ny_day.replace(day=1)
    business = [first + timedelta(days=k) for k in range(10) if (first + timedelta(days=k)).weekday() < 5]

    def at(hm):
        return datetime(ny_day.year, ny_day.month, ny_day.day, *hm, tzinfo=NY).astimezone(MSK)
    if ny_day.weekday() == 4 and ny_day.day <= 7:
        out.append((at((8, 30)), 'NFP (правило: 1-я пятница)'))
    if business and ny_day == business[0]:
        out.append((at((10, 0)), 'ISM производство (правило)'))
    if len(business) > 2 and ny_day == business[2]:
        out.append((at((10, 0)), 'ISM услуги (правило)'))
    if ny_day.weekday() == 3:
        out.append((at((8, 30)), 'заявки на пособие (четверг)'))
    return sorted(out)


class Briefing:
    def __init__(self, scanner):
        self.sc = scanner
        self.cfg = CONFIG.briefing
        self.zones: Dict[str, List[Dict]] = {}          # symbol -> the last briefing's zones (watched)
        self.scenario: Dict[str, Dict] = {}
        self._sent: Dict[str, float] = {}               # dedupe key -> last send time
        self._bias: Dict[str, Optional[str]] = {}
        self._last_h1: Dict[str, int] = {}
        self._demo_seen = 0
        self._anom_seen = int(time.time() * 1000)
        self._done_slots: set = set()

    # ------------------------------------------------------------------ helpers
    def watched(self) -> List[str]:
        out = []
        for base in self.cfg.coins:
            sym = f"{base}/USDT:USDT"
            if sym in self.sc.market_data:
                out.append(sym)
        return out

    def _post(self, text: str, key: Optional[str] = None, every_sec: float = 0.0):
        if key is not None:
            if time.time() - self._sent.get(key, 0.0) < every_sec:
                return
            self._sent[key] = time.time()
        loop = getattr(self, '_loop', None)
        if loop is not None and threading.current_thread() is not threading.main_thread():
            loop.call_soon_threadsafe(self.sc.notifier.post, text)     # checks reading SQLite run in a thread
        else:
            self.sc.notifier.post(text)

    def _bias_of(self, symbol: str) -> Tuple[Optional[str], Dict]:
        md = self.sc.market_data.get(symbol)
        b = self.sc.fetcher.htf_bias(md, time.time() * 1000) if md is not None else None
        coin = (b or {}).get('coin') or {}
        return coin.get('bias'), {**coin, 'range_mid': (b or {}).get('range_mid')}

    def key_zones(self, symbol: str) -> Tuple[Optional[float], List[Dict]]:
        """The 1h+ zones of the plans' map near the price: up to 3 above, 3 below and the one price sits in."""
        from strategies.geometry import htf_zones
        from zones import merge
        price = self.sc._price_of(symbol)
        levels = self.sc._levels_of(symbol)
        md = self.sc.market_data.get(symbol)
        atr15 = getattr(md, 'atr', None) if md else None
        tf = self.sc._tf_atrs(symbol)
        atr1d = tf.get('1d') or (tf.get('4h') or 0) * 2.5
        if not price or not levels or not atr1d:
            return price, []
        zs = merge([l for l in levels if l.kind not in SKIP_KINDS], atr15 or atr1d / 5, symbol=symbol)
        zs = [z for z in htf_zones(zs, '1h') if abs(z.price - price) <= self.cfg.span_atr_1d * atr1d]
        if not zs:
            return price, []
        # the owner's reference card: three resistances (local / resistance / global), the zone price is watched in,
        # two supports (next / key) - thin zones (<= 0.3 daily ATR: a wide merge is trimmed to its edge nearest the
        # price, where the reaction is expected) about a daily ATR apart, out to ~3 daily ATR
        cap = 0.3 * atr1d
        cands: List[Dict] = []
        for z in zs:
            lo, hi = z.lo, z.hi
            if hi - lo > cap:
                if lo > price:
                    hi = lo + cap
                elif hi < price:
                    lo = hi - cap
                elif hi - lo > 2 * cap:
                    continue          # a wide band around the price is no level to watch (trimming it around the
                    # price made the price always 'inside')
            # a zone of 15m / 1h swings and equal highs only is an intraday level, not a briefing zone: at least one
            # 4h+ / daily / weekly / monthly / prior-period / profile level, or a strong confluence
            if min(map(_label_rank, z.labels), default=9) > 3 and z.strength < 5:
                continue
            cands.append({'lo': lo, 'hi': hi, 'strength': z.strength, 'labels': list(z.labels)})
        if not cands:
            return price, []

        def rank(m):   # strongest first; ties to the higher timeframe's level (the week's / day's extreme)
            return -m['strength'], min(map(_label_rank, m['labels']), default=9)

        # the watched zone: the one price is in, else the strongest within 0.5 daily ATR, else the nearest
        near = [m for m in cands if m['lo'] - 0.5 * atr1d <= price <= m['hi'] + 0.5 * atr1d]
        inside = [m for m in near if m['lo'] <= price <= m['hi']]
        pool = inside or near or cands
        cur = sorted(pool, key=lambda m: (rank(m), min(abs(m['lo'] - price), abs(m['hi'] - price))))[0]
        def ladder(side, n):
            """Outward from the watched zone: each step takes the STRONGEST zone in the next one-daily-ATR window
            beyond the previous pick (+ a gap of 0.25 daily ATR), so the levels run near -> far like the reference
            (local / resistance / global), widening the window while it is empty."""
            chosen, edge = [], (cur['hi'] if side > 0 else cur['lo'])
            pool_ = [m for m in cands if (m['lo'] > cur['hi'] if side > 0 else m['hi'] < cur['lo'])]
            while len(chosen) < n:
                start = edge + side * (0.25 * atr1d if chosen else 0.1 * atr1d)
                for width in (1.0, 2.0, 4.0):
                    end = start + side * width * atr1d
                    win = [m for m in pool_ if (start <= m['lo'] <= end if side > 0 else end <= m['hi'] <= start)]
                    if win:
                        break
                if not win:
                    break
                best = sorted(win, key=rank)[0]
                chosen.append(best)
                edge = best['hi'] if side > 0 else best['lo']
            return chosen
        above, below = ladder(1, 3), ladder(-1, 2)
        out = []
        for side, group in ((1, above[::-1]), (0, [cur]), (-1, below)):
            for m in group:
                labels = sorted(m['labels'], key=_label_rank)
                out.append({'lo': m['lo'], 'hi': m['hi'], 'side': side, 'strength': m['strength'],
                            'label': ' · '.join(labels[:4])})
        return price, out

    # ------------------------------------------------------------------ briefing
    def coin_text(self, symbol: str) -> Optional[str]:
        price, zones = self.key_zones(symbol)
        if not price:
            return None
        bias, st = self._bias_of(symbol)
        self.zones[symbol] = zones
        md = self.sc.market_data.get(symbol)
        d1 = list(md.d1) if md else []
        chg = f"{(price / d1[-1][4] - 1) * 100:+.2f}% к закрытию дня" if d1 else ''
        lines = [f"<b>{_short(symbol)}</b> {_fmt(price)} ({chg})",
                 f"Старший ТФ: <b>{BIAS_RU.get(bias, bias)}</b> · моментум {st.get('tsm', '?')} · неделя "
                 f"{_arrow(st.get('w1'))} · день {_arrow(st.get('d1'))} · 4h {_arrow(st.get('h4'))}"
                 + (f" · ADX4h {st['adx4']:.0f}" if st.get('adx4') is not None else '')]
        up = [z for z in zones if z['side'] == 1]
        dn = [z for z in zones if z['side'] == -1]
        for z in zones:
            tag = {1: '🔴 сопр.', 0: '🔵 цена в зоне', -1: '🟢 подд.'}[z['side']]
            if z['side'] == 1:
                what = 'закрепление выше (1h) откроет следующую зону'
            elif z['side'] == -1:
                what = 'потеря (1h ниже) откроет следующую зону'
            else:
                what = 'ждём реакцию: выход из зоны задаст направление'
            lines.append(f"{tag} {_fmt(z['lo'])}–{_fmt(z['hi'])} [{z['strength']:.0f}] {z['label']} — {what}")
        near_up, near_dn = (up[-1] if up else None), (dn[0] if dn else None)
        sc = {}
        if bias == 'bull' and near_dn:
            sc = {'base': f"удержание {_fmt(near_dn['lo'])} → {_fmt(near_up['lo']) if near_up else 'обновление хаёв'}",
                  'alt': f"1h ниже {_fmt(near_dn['lo'])} → {_fmt(dn[1]['hi']) if len(dn) > 1 else 'глубже'}",
                  'dir': 1, 'inval': near_dn['lo']}
        elif bias == 'bear' and near_up:
            sc = {'base': f"отказ под {_fmt(near_up['hi'])} → {_fmt(near_dn['hi']) if near_dn else 'обновление лоёв'}",
                  'alt': f"1h выше {_fmt(near_up['hi'])} → {_fmt(up[-2]['lo']) if len(up) > 1 else 'выше'}",
                  'dir': -1, 'inval': near_up['hi']}
        elif near_up and near_dn:
            sc = {'base': f"диапазон {_fmt(near_dn['lo'])}–{_fmt(near_up['hi'])}: работа от границ"
                          + (f", середина 20 дней {_fmt(st['range_mid'])}" if st.get('range_mid')
                             and near_dn['lo'] < st['range_mid'] < near_up['hi'] else ''),
                  'alt': "выход 1h за границу задаст ход к следующей зоне", 'dir': 0, 'inval': None}
        if sc:
            lines.append(f"Базовый: {sc['base']}")
            lines.append(f"Альтернатива: {sc['alt']}")
            self.scenario[symbol] = {**sc, 'price': price, 'ts': time.time()}
        return '\n'.join(lines)

    def market_text(self) -> str:
        out = []
        dom = self.sc.fetcher.dominance_reading()
        if dom:
            out.append(f"BTC.D {dom['btc_d']:.2f}% ({dom.get('btc_d_4h', 0):+.2f} за 4h) · USDT.D {dom['usdt_d']:.2f}% "
                       f"({dom.get('usdt_d_4h', 0):+.2f} за 4h)")
        ms = getattr(self.sc, 'market_state', None) or {}
        if ms.get('breadth_w') is not None:
            out.append(f"Рынок: {ms['breadth_w'] * 100:.0f}% монет выше недельной EMA"
                       + (f", медиана 1h {ms['mkt_1h'] * 100:+.2f}%" if ms.get('mkt_1h') is not None else ''))
        # research_sessions.py (12 months to 2026-09): the NY cash open's first 30 min move BTC 2.5x / alts 1.8x a
        # usual half hour, direction ~50/50; 08:30 NY (releases) 1.35x; Tokyo / London no larger than other times
        out.append('Открытие NY (16:30 МСК): первые 30 мин BTC ×2.5, альты ×1.8 обычной амплитуды, направление ~50/50')
        events = macro_today(datetime.now(MSK))
        if events:
            out.append('Макро сегодня (МСК): ' + ', '.join(f"{dt:%H:%M} {name}" for dt, name in events))
        return '\n'.join(out)

    def cards(self, title: str) -> List[Tuple[bytes, str]]:
        """The briefing as pictures: (PNG, caption) per watched coin, the first caption carries the market / macro."""
        import briefing_chart
        out = []
        head = f"📋 <b>{title}</b> · {datetime.now(MSK):%d.%m %H:%M} МСК\n{self.market_text()}"
        for symbol in self.watched():
            try:
                text = self.coin_text(symbol)            # zones / scenario (also what the watch alerts follow)
                price = self.sc._price_of(symbol)
                md = self.sc.market_data.get(symbol)
                if not text or not price or md is None or len(md.h1) < 24:
                    continue
                bias, st = self._bias_of(symbol)
                tf = self.sc._tf_atrs(symbol)
                bias_line = (f"Старший ТФ: {BIAS_RU.get(bias, bias)} · неделя {_arrow(st.get('w1'))} · день "
                             f"{_arrow(st.get('d1'))} · 4h {_arrow(st.get('h4'))}")
                if len(md.h4) < 20:
                    continue
                png = briefing_chart.render(f"{_short(symbol)}USDT", list(md.h4), price, self.zones.get(symbol) or [],
                                            tf.get('4h'), bias_line, tf.get('1d'), candles_1h=list(md.h1))
                cap = f"<b>{_short(symbol)}</b> · {bias_line}"
                out.append((png, (head + '\n\n' + cap) if not out else cap))
            except Exception as e:
                errors.report('briefing.card', e, symbol)
        return out

    def briefing(self, title: str) -> str:
        parts = [f"📋 <b>{title}</b> · {datetime.now(MSK):%d.%m %H:%M} МСК", self.market_text()]
        for symbol in self.watched():
            try:
                t = self.coin_text(symbol)
            except Exception as e:
                errors.report('briefing.coin', e, symbol)
                t = None
            if t:
                parts.append(t)
        parts.append('<i>Механические правила бота, не совет. Закрепление = закрытие 1h за зоной.</i>')
        return '\n\n'.join(p for p in parts if p)

    def recap(self) -> str:
        parts = [f"🌙 <b>Итог дня</b> · {datetime.now(MSK):%d.%m} МСК"]
        day0 = int(time.time() // 86400 * 86400 * 1000)
        for symbol, zones in self.zones.items():
            md = self.sc.market_data.get(symbol)
            price = self.sc._price_of(symbol)
            if md is None or not price:
                continue
            today = [c for c in md.minute_klines if c[0] >= day0]
            if not today:
                continue
            hi, lo = max(c[2] for c in today), min(c[3] for c in today)
            lines = [f"<b>{_short(symbol)}</b> {_fmt(price)} · день {_fmt(lo)}–{_fmt(hi)}"]
            for z in zones:
                touched = lo <= z['hi'] and hi >= z['lo']
                if not touched:
                    continue
                if z['side'] == 1:
                    res = 'пробита' if price > z['hi'] else 'удержала (отказ)'
                elif z['side'] == -1:
                    res = 'пробита' if price < z['lo'] else 'удержала (отскок)'
                else:
                    res = 'цена в зоне' if z['lo'] <= price <= z['hi'] else ('вышли вверх' if price > z['hi'] else 'вышли вниз')
                lines.append(f"· {_fmt(z['lo'])}–{_fmt(z['hi'])}: {res}")
            sc = self.scenario.get(symbol)
            if sc and sc.get('dir'):
                ok = (price - sc['price']) * sc['dir'] > 0
                broken = sc.get('inval') is not None and (price - sc['inval']) * sc['dir'] < 0
                lines.append('Сценарий: ' + ('отменён' if broken else ('сработал' if ok else 'не сработал')))
            parts.append('\n'.join(lines))
        return '\n\n'.join(parts)

    # ------------------------------------------------------------------ watch
    def check_levels(self):
        """Acceptance / rejection of the briefing zones on each newly closed 1h candle."""
        now = time.time() * 1000
        for symbol, zones in self.zones.items():
            md = self.sc.market_data.get(symbol)
            if md is None or len(md.h1) < 2:
                continue
            closed = [c for c in md.h1 if c[0] + HOUR_MS <= now]
            if len(closed) < 2 or self._last_h1.get(symbol) == closed[-1][0]:
                continue
            self._last_h1[symbol] = closed[-1][0]
            c, p = closed[-1], closed[-2]
            for z in zones:
                lbl = f"{_fmt(z['lo'])}–{_fmt(z['hi'])}"
                msg = None
                if p[4] <= z['hi'] < c[4]:
                    msg = f"⬆️ {_short(symbol)}: закрепление 1h выше зоны {lbl} (закрытие {_fmt(c[4])})"
                elif p[4] >= z['lo'] > c[4]:
                    msg = f"⬇️ {_short(symbol)}: закрепление 1h ниже зоны {lbl} (закрытие {_fmt(c[4])})"
                elif c[2] > z['hi'] and c[4] < z['hi'] and p[4] < z['hi']:
                    msg = f"↩️ {_short(symbol)}: снятие верха {lbl} (хай {_fmt(c[2])}) и возврат под зону"
                elif c[3] < z['lo'] and c[4] > z['lo'] and p[4] > z['lo']:
                    msg = f"↪️ {_short(symbol)}: снятие низа {lbl} (лой {_fmt(c[3])}) и возврат над зону"
                if msg:
                    self._post(msg + f"\n{z['label']}", key=f"lvl|{symbol}|{z['lo']:.8g}|{msg[:2]}", every_sec=4 * 3600)

    def session_now(self) -> Optional[str]:
        now = datetime.now(MSK)
        for name, hm in (('Азии', (3, 0)), ('Лондона', (10, 0)), ('Нью-Йорка', (16, 30))):
            t = now.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
            if timedelta(0) <= now - t <= timedelta(minutes=60):
                return name
        return None

    def check_shock(self):
        """A watched coin's 15m move >= shock_z x its typical 15m move (and >= shock_min_pct), with the breadth."""
        moves = {}
        for symbol, md in self.sc.market_data.items():
            mk = list(md.minute_klines)[-16:]
            if len(mk) >= 16 and mk[0][4]:
                moves[symbol] = mk[-1][4] / mk[0][4] - 1
        if not moves:
            return
        for symbol in self.watched():
            md = self.sc.market_data[symbol]
            r = moves.get(symbol)
            std = getattr(md, 'ret_std', None)
            if r is None or not std or abs(r) < max(self.cfg.shock_z * std, self.cfg.shock_min_pct):
                continue
            d = 1 if r > 0 else -1
            same = sum(1 for v in moves.values() if v * d > 0.005)
            sess = self.session_now()
            self._post(f"{'🚀' if d > 0 else '🩸'} <b>{_short(symbol)} {r * 100:+.2f}% за 15 мин</b> "
                       f"({abs(r) / std:.1f}σ){' на открытии ' + sess if sess else ''}\n"
                       f"Вместе с ним {'выросли' if d > 0 else 'упали'} >0.5%: {same} из {len(moves)} монет",
                       key=f"shock|{symbol}|{d}", every_sec=1800)

    def check_bias(self):
        for symbol in self.watched():
            b, st = self._bias_of(symbol)
            old = self._bias.get(symbol, 'unset')
            self._bias[symbol] = b
            if old != 'unset' and b != old and b is not None:
                self._post(f"🧭 {_short(symbol)}: смещение старшего ТФ {BIAS_RU.get(old, old)} → <b>{BIAS_RU.get(b, b)}</b>"
                           + ("\nАльты: сделки против BTC фильтр больше не пропускает" if symbol.startswith('BTC/') else ''),
                           key=f"bias|{symbol}|{b}", every_sec=3600)

    def check_demo(self):
        ex = (self.sc.demo if self.sc.demo.enabled else None)
        path = getattr(ex, 'db_path', None) if ex else None
        if not path:
            return
        try:
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as c:
                c.row_factory = sqlite3.Row
                rows = c.execute("SELECT * FROM demo_trades WHERE MAX(COALESCE(opened_ms, 0), COALESCE(closed_ms, 0)) > ?"
                                 " ORDER BY COALESCE(closed_ms, opened_ms)", (self._demo_seen,)).fetchall()
        except sqlite3.Error as e:
            errors.report('briefing.demo', e)
            return
        first = self._demo_seen == 0
        for r in rows:
            r = dict(r)
            self._demo_seen = max(self._demo_seen, r.get('opened_ms') or 0, r.get('closed_ms') or 0)
            if first:
                continue
            side = '▲' if (r.get('direction') or 0) > 0 else '▼'
            name = _short(r['symbol'])
            if r.get('closed_ms') and r.get('close_reason'):
                rr = f" {r['r']:+.2f}R" if r.get('r') is not None else ''
                self._post(f"💼 Демо {side} {name} {r.get('setup')}: {r['close_reason']}{rr}"
                           + (f" ({r['error']})" if r.get('error') else ''))
            elif r.get('entry_fill'):
                self._post(f"💼 Демо {side} {name} {r.get('setup')}: вход {r['entry_fill']:.6g}"
                           + (f", стоп {r['sl']:.6g}" if r.get('sl') else ''))
        if first:
            self._demo_seen = max(self._demo_seen, int(time.time() * 1000))

    def check_anomalies(self):
        j = getattr(self.sc, 'journal', None)
        path = getattr(j, 'db_path', None) or CONFIG.journal.db_path
        watched = self.watched()
        if not watched:
            return
        try:
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as c:
                q = ("SELECT ts_ms, symbol, group_key, price FROM signals WHERE kind='anomaly' AND ts_ms > ? AND symbol IN (%s)"
                     " AND group_key IN (%s) ORDER BY ts_ms" % (','.join('?' * len(watched)), ','.join('?' * len(ANOMALY_LABELS))))
                rows = c.execute(q, (self._anom_seen, *watched, *ANOMALY_LABELS)).fetchall()
        except sqlite3.Error as e:
            errors.report('briefing.anomalies', e)
            return
        for ts, symbol, label, price in rows:
            self._anom_seen = max(self._anom_seen, ts)
            self._post(f"⚡ {_short(symbol)}: {label} у {_fmt(price)}", key=f"anom|{symbol}|{label}", every_sec=1800)

    def check_health(self):
        status = self.sc.fetcher.venue_status()
        down = [v for v, st in status.items() if not st.get('connected', 1)]
        if down:
            self._post(f"🛠 Бот: нет потока {', '.join(down)}", key='health|down|' + ','.join(sorted(down)), every_sec=3600)
        failed = errors.health_text()
        if failed:
            self._post(f"🛠 Бот: ошибки компонентов — {failed}", key='health|errors', every_sec=3 * 3600)
        ex = (self.sc.demo if self.sc.demo.enabled else None)
        if ex is not None:
            try:
                limit = ex.risk_limit()
            except Exception as e:
                errors.report('briefing.risk', e)
                limit = None
            if limit:
                self._post(f"🛑 Демо остановлено на сегодня: {limit}", key='health|risk', every_sec=6 * 3600)

    # ------------------------------------------------------------------ loop
    async def loop(self):
        self._loop = asyncio.get_running_loop()
        while not self.sc.fetcher.baselines_loaded():
            await asyncio.sleep(30)
        await asyncio.sleep(120)                            # the maps / histories of the watched coins
        # the zones to watch exist from the start (a briefing is not sent at start-up)
        for symbol in self.watched():
            try:
                self.key_zones(symbol) and self.coin_text(symbol)
            except Exception as e:
                errors.report('briefing.init', e, symbol)
        tick = 0
        while True:
            try:
                now = datetime.now(MSK)
                for hm, title in self.cfg.schedule:
                    h, m = map(int, hm.split(':'))
                    slot = f"{now:%Y-%m-%d} {hm}"
                    t = now.replace(hour=h, minute=m, second=0, microsecond=0)
                    if slot not in self._done_slots and timedelta(0) <= now - t <= timedelta(minutes=10):
                        self._done_slots.add(slot)
                        if title == 'recap':
                            self.sc.notifier.post(await asyncio.to_thread(self.recap))
                        else:
                            for png, cap in await asyncio.to_thread(self.cards, title):
                                self.sc.notifier.post_photo(png, cap)
                for dt, name in macro_today(now):
                    if timedelta(0) <= dt - now <= timedelta(minutes=30):
                        self._post(f"📅 Через {int((dt - now).total_seconds() // 60)} мин: {name} ({dt:%H:%M} МСК) — "
                                   f"входы бота за 30 мин до / 60 после CPI и FOMC блокируются",
                                   key=f"macro|{dt:%Y%m%d%H%M}", every_sec=86400)
                self.check_shock()
                await asyncio.to_thread(self.check_demo)          # SQLite reads off the event loop
                await asyncio.to_thread(self.check_anomalies)
                if tick % 2 == 0:
                    self.check_levels()
                if tick % 15 == 0:
                    await asyncio.to_thread(self.check_bias)
                    self.check_health()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                errors.report('briefing.loop', e)
            tick += 1
            await asyncio.sleep(60)
