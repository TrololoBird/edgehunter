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
import os
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

ANOMALY_RU = {'LIQ CASCADE': 'каскад ликвидаций (резкая принудительная распродажа / откуп)',
              'WHALES BUY': 'крупные рыночные покупки', 'WHALES SELL': 'крупные рыночные продажи',
              'OI SURGE': 'резкий рост открытого интереса (новые позиции)',
              'OI FLUSH': 'резкое падение открытого интереса (позиции закрываются)',
              'SHORT SQUEEZE': 'шорт-сквиз: рост с ликвидациями шортов',
              'LONG FLUSH': 'вынос лонгов: падение с ликвидациями лонгов'}

DEMO_RU = {'SL': 'стоп', 'EXCHANGE': 'закрыта биржей (стоп / цель)', 'CLOSED': 'закрыта по карточке',
           'NO_MARKET': 'не открыта: на BingX нет рынка', 'PRICE_GAP': 'не открыта: цена на BingX ушла',
           'NOT_FILLED': 'лимит не исполнен', 'LATE_FILL': 'поздний лимит закрыт', 'ORPHAN': 'закрыта без карточки',
           'OVERLAP': 'не открыта: монета уже в сделке', 'UNTRACKED': 'чужая позиция закрыта',
           'NO_LIMIT': 'не открыта: лимитный вход не выставлен', 'NO_STOP': 'закрыта: стоп не выставлен',
           'DAILY_LIMIT': 'не открыта: дневной лимит', 'PAUSE': 'не открыта: пауза после убытков',
           'ERROR': 'не открыта: ошибка биржи', 'UNKNOWN': 'исход входа неизвестен (биржа не ответила)'}


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


SIGNIFICANT_KINDS = {'swing_1d', 'swing_1w', 'pmhl', 'year', 'bpr_4h',
                     # eng-74, the 1h card (the owner's reference: zones of the 1h structure ~1 1h-ATR thick, the
                     # session's swings / consolidation edges / open 1h imbalances, the higher levels with them)
                     'swing_1h', 'equal', 'bpr_1h'}


def _significant(l) -> bool:
    """A level a briefing zone may stand on (key_zones)."""
    k, lb = l.kind, l.label or ''
    if k in SIGNIFICANT_KINDS or any(k.endswith(t) for t in ('_1h', '_4h', '_1d', '_1w')) and k.split('_')[0] in ('fvg', 'ob', 'breaker'):
        return True
    if k == 'pdhl':
        # + the last completed sessions' ranges: ICT - London runs the Asian range's liquidity, New York London's
        return lb in ('PDH', 'PDL', 'PWH', 'PWL', 'day high', 'day low') or lb.split(' ')[0] in ('Asia', 'London', 'New')
    if k == 'open':
        return lb in ('week open', 'month open')
    if k in ('poc', 'va'):
        return 'naked' in lb or '4d' in lb or lb.endswith(' PD')        # + the previous day's POC / VAH / VAL
    return False


LABEL_RU = (('PDH', 'максимум вчера'), ('PDL', 'минимум вчера'), ('PWH', 'максимум прошлой недели'),
            ('PWL', 'минимум прошлой недели'), ('PMH', 'максимум прошлого месяца'), ('PML', 'минимум прошлого месяца'),
            ('week open', 'открытие недели'), ('month open', 'открытие месяца'), ('day high', 'максимум дня'),
            ('day low', 'минимум дня'), ('Asia high', 'максимум Азии'), ('Asia low', 'минимум Азии'),
            ('London high', 'максимум Лондона'), ('London low', 'минимум Лондона'),
            ('New York high', 'максимум Нью-Йорка'), ('New York low', 'минимум Нью-Йорка'),
            ('1w high', 'недельная вершина'), ('1w low', 'недельное дно'), ('1d high', 'дневная вершина'),
            ('1d low', 'дневное дно'), ('1h high', 'вершина 1h'), ('1h low', 'дно 1h'), ('EQH', 'равные вершины: стопы'),
            ('EQL', 'равные минимумы: стопы'), ('naked POC', 'непротестированный POC'), ('POC PD', 'POC вчера'),
            ('VAH PD', 'VAH вчера'), ('VAL PD', 'VAL вчера'), ('POC 4d', 'POC 4 дней'), ('VAH 4d', 'VAH 4 дней'),
            ('VAL 4d', 'VAL 4 дней'), ('FVG', 'незакрытый имбаланс'), ('BPR', 'сбалансированный диапазон'),
            ('OB', 'ордер-блок'), ('breaker', 'брейкер'), ('d high', 'максимум года'), ('d low', 'минимум года'))


def describe(labels) -> str:
    """'What it is' for a zone: its levels in words, the highest timeframes first, at most three."""
    out = []
    for lb in sorted(labels, key=_label_rank):
        ru = next((r for k, r in LABEL_RU if lb.startswith(k) or k in lb), lb)
        tf = next((t for t in (' 1w', ' 1d', ' 4h', ' 1h') if t in lb), '') if ru != lb else ''
        text = ru + (tf if ru in ('незакрытый имбаланс', 'сбалансированный диапазон', 'ордер-блок', 'брейкер') else '')
        pos = next((w for k, w in ((' верх', ' (верх)'), (' низ', ' (низ)'), (' CE', ' (середина)')) if lb.endswith(k)), '')
        text += pos
        if text not in out:
            out.append(text)
    return ', '.join(out[:3])


def _label_rank(label: str) -> int:
    """Higher timeframes first: weekly / previous week, daily / previous day, 4h, 1h, sessions / profile, 15m."""
    for k, r in (('1w', 0), ('PW', 0), ('week', 0), ('PM', 0), ('52w', 0), ('month', 0), ('1d', 1), ('d high', 1),
                 ('d low', 1), ('PD', 1), ('day', 2), ('4h', 2), ('POC', 3),
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
    if macro_calendar.LIVE:
        # eng-72: the real week calendar (ForexFactory, USD high / medium impact) replaces the publication rules
        return [(datetime.fromtimestamp(t / 1000, MSK), f"{name}{' ❗' if imp == 'High' else ''}")
                for t, name, imp in macro_calendar.LIVE if datetime.fromtimestamp(t / 1000, MSK).date() == day]
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
        self.context: Dict[str, List[Dict]] = {}        # symbol -> wide zones the price sits inside (named, not traded)
        self._proxy: Dict[str, Tuple[float, Dict]] = {}  # base -> (fetched at, spot proxy candles)
        self._anom_buf: Dict[str, List[Tuple[int, str, float]]] = {}   # symbol -> the burst being collected
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

    def _post(self, text: str, key: Optional[str] = None, every_sec: float = 0.0, topic: str = 'alerts'):
        if key is not None:
            if time.time() - self._sent.get(key, 0.0) < every_sec:
                return
            self._sent[key] = time.time()
        loop = getattr(self, '_loop', None)
        if loop is not None and threading.current_thread() is not threading.main_thread():
            loop.call_soon_threadsafe(self.sc.notifier.post, text, topic)     # checks reading SQLite run in a thread
        else:
            self.sc.notifier.post(text, topic)

    # a contract younger than the 365-day momentum horizon gets the history of a spot proxy before its listing
    # (eng-74: XAUUSDT trades since 12.2025 - its momentum blend had only 30 / 90 days, the 12-month horizon
    # Moskowitz-Ooi-Pedersen found strongest was missing, and '52w' levels were the listing's extremes)
    PROXY = {'XAU': 'PAXGUSDT'}

    def _proxy_history(self, base: str) -> Dict[str, List]:
        sym = self.PROXY.get(base)
        if not sym:
            return {}
        cached = self._proxy.get(base)
        if cached and time.time() - cached[0] < 6 * 3600:
            return cached[1]
        import json
        import urllib.request
        out = {}
        try:
            for tf, n in (('1d', 1000), ('1w', 200)):
                url = f"https://api.binance.com/api/v3/klines?symbol={sym}&interval={tf}&limit={n}"
                with urllib.request.urlopen(url, timeout=20) as r:
                    out[tf] = [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])]
                               for k in json.loads(r.read())]
        except Exception as e:
            errors.report('briefing.proxy', e, sym)
            return cached[1] if cached else {}
        self._proxy[base] = (time.time(), out)
        return out

    @staticmethod
    def _splice(own: List, proxy: List) -> List:
        """The proxy's candles before the contract's first one, scaled to it at the overlap, then the contract's."""
        if not own or not proxy:
            return list(own)
        first = own[0][0]
        at = next((c for c in proxy if c[0] == first), None)
        if at is None or not at[4]:
            return list(own)
        k = own[0][4] / at[4]
        return [[c[0], c[1] * k, c[2] * k, c[3] * k, c[4] * k] + list(c[5:]) for c in proxy if c[0] < first] + list(own)

    def _bias_of(self, symbol: str, md=None) -> Tuple[Optional[str], Dict]:
        md = md if md is not None else self.sc.market_data.get(symbol)
        if md is None:
            return None, {}
        src, since = md, None
        base = _short(symbol)
        if base in self.PROXY and 0 < len(md.d1) < 366:
            hist = self._proxy_history(base)
            if hist.get('1d'):
                import types
                src = types.SimpleNamespace(symbol=md.symbol, h1=md.h1, h4=md.h4, last_price=md.last_price, d1=self._splice(list(md.d1), hist['1d']),
                                            w1=self._splice(list(md.w1), hist.get('1w') or []))
                since = (self.PROXY[base], md.d1[0][0] if md.d1 else None)
        b = self.sc.fetcher.htf_bias(src, time.time() * 1000)
        coin = (b or {}).get('coin') or {}
        return coin.get('bias'), {**coin, 'range_mid': (b or {}).get('range_mid'), 'proxy': since,
                                  'days': len(md.d1)}

    def _bias_line(self, symbol: str, bias: Optional[str], st: Dict) -> str:
        """The higher timeframe as BACKGROUND (Elder's tide: a filter of direction over weeks, not the session's
        forecast - it said 'bull' for BTC / ETH / SOL through 11 of 14 falling sessions, 2026-10-05..07)."""
        line = (f"Фон (недели): {BIAS_RU.get(bias, bias)} · неделя {_arrow(st.get('w1'))} · день "
                f"{_arrow(st.get('d1'))} · 4h {_arrow(st.get('h4'))}")
        if st.get('proxy'):
            sym, ts = st['proxy']
            since = datetime.fromtimestamp(ts / 1000, MSK).strftime('%m.%Y') if ts else '?'
            line += f" · история {_short(symbol)} с {since}, раньше {sym}"
        elif st.get('days') and st['days'] < 366:
            line += f" · история {st['days']} дн. (нет 12-мес. импульса)"
        return line

    def _extremes_24h(self, md) -> Tuple[Optional[float], Optional[float]]:
        """24h high / low: the closed 1h candles + the final 1m candles after the last of them (the 1h candles load
        a minute after the hour)."""
        now = time.time() * 1000
        h1 = [c for c in md.h1 if c[0] >= now - 24 * HOUR_MS and c[0] + HOUR_MS <= now]
        last = h1[-1][0] + HOUR_MS if h1 else now - 24 * HOUR_MS
        mins = [c for c in list(md.minute_klines) if c[0] >= last]
        rows = h1 + mins
        if not rows:
            return None, None
        return max(c[2] for c in rows), min(c[3] for c in rows)

    @staticmethod
    def _history_high(md) -> Tuple[Optional[float], int]:
        """The highest high of the daily / weekly history held (price discovery above it), with its depth in days."""
        d1, w1 = list(md.d1), list(md.w1)
        highs = [c[2] for c in d1] + [c[2] for c in w1]
        if not highs:
            return None, 0
        days = max(len(d1), len(w1) * 7)
        return max(highs), days

    def _context_text(self, symbol: str) -> str:
        """The wide zones the price sits inside (a big daily candle's order block / breaker): named, not traded."""
        ctx = self.context.get(symbol) or []
        if not ctx:
            return ''
        z = max(ctx, key=lambda m: m['strength'])
        return (f"Цена внутри широкой зоны {_fmt(z['lo'])}–{_fmt(z['hi'])} ({' · '.join(z['labels'][:3])}): "
                f"входы только от краёв, не из середины.")

    def key_zones(self, symbol: str, src: Optional[Dict] = None, keep_state: bool = True) -> Tuple[Optional[float], List[Dict]]:
        """
        The 1h+ zones of the plans' map around the price (eng-74, the 2026-10-07 review): whole zones, never trimmed
        (a trim to 0.3 daily ATR cut ETH's daily breaker 2 475-2 615 to 2 593-2 615, deleted the daily FVG 2 484-2 562
        inside it and every level above BTC's 87 177); a zone containing the price is shown, not dropped; supports are
        BELOW the price and resistances ABOVE it (they were counted from the watched zone: ETH's 'support' sat above
        the price). Each zone carries `tol` (the measured p50 pierce: a retest / acceptance within it counts - Murphy:
        zones, not prices; Bulkowski: what matters is the close beyond) and `pad` (the stop buffer beyond it: the
        measured p80 pierce, at least zone_buffer_atr x the 1h ATR - Osler: stops cluster just beyond a level).
        """
        from pierce import overshoot
        # src: a coin outside the universe (the web analysis): {'price', 'levels', 'tf', 'md'} built from REST candles
        src = src or {}
        price = src['price'] if 'price' in src else self.sc._price_of(symbol)
        levels = src['levels'] if 'levels' in src else self.sc._levels_of(symbol)
        tf = src['tf'] if 'tf' in src else self.sc._tf_atrs(symbol)
        atr1d = tf.get('1d') or (tf.get('4h') or 0) * 2.5
        atr1h = tf.get('1h') or (atr1d / 5 if atr1d else 0)
        if not price or (not levels and 'levels' not in src) or not atr1d:
            return price, []
        # only the levels a session forecast stands on (the owner 2026-10-08: minor levels made huge zones) - daily /
        # weekly swings, the previous day / week / month extremes, the week / month open, the year's extremes, 4h+ ICT
        # zones, naked daily POCs and the 4-day profile; the current day's / sessions' extremes, VWAP, the 24h profile,
        # 15m / 1h swings, equal highs / lows and round numbers are intraday detail. Each level is as thick as its wick
        # region, at most half a daily ATR from its price (a weekly high's body edge 4.2k below the wick made BTC's
        # 90 345-94 555 'zone'), and a merged zone is at most half a daily ATR wide
        import dataclasses
        cap = atr1h                    # eng-74: ~1 1h-ATR thick (the owner's reference card), was half a daily ATR
        keep = []
        for l in levels or []:
            if not _significant(l):
                continue
            if l.body is not None and abs(l.body - l.price) > cap and l.kind.split('_')[0] not in ('fvg', 'ob', 'breaker', 'bpr'):
                # a swing / previous-period extreme: the level IS its wick - a band of a 1h ATR from the wick inward
                keep.append(dataclasses.replace(l, body=l.price + cap * (1 if l.body > l.price else -1)))
                continue
            if l.body is not None and abs(l.body - l.price) > cap:
                # a level wider than a 1h ATR (a daily FVG / OB / breaker, a weekly candle's wick): its edges and,
                # for the ICT zones, its middle (consequent encroachment / mean threshold) as levels of their own -
                # capped from one side, BTC's daily FVG 81 473-82 688 kept only its top and vanished from the card
                lo, hi = sorted((l.body, l.price))
                parts = [(hi, 'верх'), (lo, 'низ')]
                if l.kind.split('_')[0] in ('fvg', 'ob', 'breaker', 'bpr'):
                    parts.append(((lo + hi) / 2, 'CE'))
                inward = {'верх': -0.25 * cap, 'низ': 0.25 * cap, 'CE': 0.15 * cap}     # a band, not a line
                keep += [dataclasses.replace(l, price=p_, body=p_ + inward[tag], label=f"{l.label} {tag}")
                         for p_, tag in parts]
                continue
            keep.append(l)
        # eng-75: the zones are where price TURNED (sr.py: clusters of 1h / 4h / daily swing pivots, strength from the
        # reactions, their volume, the timeframe, recency and the later rejections) - the map's constructs (PDH, FVG,
        # VAL, opens, sessions) only name a zone they coincide with ("здесь же"); they were the zones themselves, a
        # sum of labels whether or not price ever reacted there
        import sr
        md = src['md'] if 'md' in src else self.sc.market_data.get(symbol)
        now_ms = time.time() * 1000
        zs = sr.zones({'1h': list(md.h1) if md else [], '4h': list(md.h4) if md else [],
                       '1d': list(md.d1) if md else []}, now_ms, tol=0.6 * atr1h, max_width=1.5 * atr1h)
        zs = [z for z in zs if z['lo'] - price <= self.cfg.span_atr_1d * atr1d
              and price - z['hi'] <= self.cfg.span_atr_1d * atr1d]
        cands: List[Dict] = []
        for z in zs:
            near = [l for l in keep if z['lo'] - 0.6 * atr1h <= l.price <= z['hi'] + 0.6 * atr1h]
            kind = 'swing_1h'
            tol = min(overshoot(symbol, kind, z['price'], 'p50') or 0.1 * atr1h, 0.5 * atr1h)
            pad = min(max(overshoot(symbol, kind, z['price'], 'p80') or 0.0, 0.5 * atr1h), atr1h)
            tfs = '/'.join(z['tfs'])
            what = f"{z['touches']} касан{'ие' if z['touches'] == 1 else 'ия' if z['touches'] < 5 else 'ий'} ({tfs})"                 + (', смена роли' if z['flip'] else '')
            cands.append({'lo': z['lo'], 'hi': z['hi'], 'mid': z['price'], 'strength': z['strength'],
                          'labels': list(dict.fromkeys(l.label for l in near)), 'tol': tol, 'pad': pad,
                          'wide': False, 'sr_desc': what})
        if not cands:
            return price, []
        # zones that overlap are one place: merged (up to a daily ATR wide) - the cap above kept BTC's 81 857-82 500
        # and 81 511-82 414 apart and the card drew one inside the other (2026-10-08 09:30)
        cands.sort(key=lambda m: m['lo'])
        merged = [cands[0]]
        for m in cands[1:]:
            a = merged[-1]
            if m['lo'] <= a['hi'] and m['hi'] <= a['hi']:
                # entirely inside the previous zone: absorbed (a split would invert it - XAU '4 142 - 4 141')
                a['strength'] += m['strength']
                a['labels'] = list(dict.fromkeys(a['labels'] + m['labels']))
                continue
            if m['lo'] <= a['hi'] and max(a['hi'], m['hi']) - a['lo'] > 1.5 * atr1h:
                # overlapping but together wider than a daily ATR: split at the middle of the overlap (XAU 4 109-4 165
                # and 4 161-4 173 were drawn one inside the other)
                cut = (m['lo'] + min(a['hi'], m['hi'])) / 2
                a['hi'], m = cut, {**m, 'lo': cut}
                merged.append(m)
                continue
            if m['lo'] <= a['hi'] and max(a['hi'], m['hi']) - a['lo'] <= 1.5 * atr1h:
                strong = a if a['strength'] >= m['strength'] else m
                merged[-1] = {**strong, 'lo': a['lo'], 'hi': max(a['hi'], m['hi']),
                              'strength': a['strength'] + m['strength'],
                              'labels': list(dict.fromkeys(a['labels'] + m['labels'])),
                              'tol': max(a['tol'], m['tol']), 'pad': max(a['pad'], m['pad'])}
            else:
                merged.append(m)
        cands = merged

        def rank(m):   # strongest first; ties to the higher timeframe's level
            return -m['strength'], min(map(_label_rank, m['labels']), default=9)
        # the zone price is in (within its tolerance): the narrowest such zone (a wide daily candle around it is
        # context, named in the text, not the zone to trade off)
        inside = [m for m in cands if m['lo'] - m['tol'] <= price <= m['hi'] + m['tol']]
        cur = min(inside, key=lambda m: (m['hi'] - m['lo'], rank(m))) if inside else None
        # wider than a daily ATR around the price: context (named, not traded); the other zones around the price are
        # supports / resistances by their level price (a daily low whose candle body reaches above the price - BTC's
        # 82 500 / 83 461 - is a support at 82 500, not context: as context it vanished from the targets)
        wide = [m for m in inside if m is not cur and m['wide']]
        if keep_state:
            self.context[symbol] = wide
        for m in inside:
            if m is not cur and not m['wide']:
                lo, hi = (min(m['lo'], m['mid']), min(m['mid'], price - m['tol'])) if m['mid'] < price                     else (max(m['mid'], price + m['tol']), max(m['hi'], m['mid']))
                m['lo'], m['hi'] = min(lo, hi), max(lo, hi)        # never inverted (XAU '4 118 - 4 115')

        def ladder(side, n):
            """Outward from the PRICE, NEAREST first (a target is the next level price meets - the strongest zone of a
            daily-ATR window skipped BTC's 82 500 daily low and ETH's 2 475 edge for weaker or farther ones); the next
            pick must lie beyond the previous one by more than their pierce (closer = one place); a zone of
            15m / 1h levels only was already dropped above."""
            pool_ = sorted((m for m in cands if m is not cur and m not in wide
                            and (m['lo'] > price if side > 0 else m['hi'] < price)),
                           key=lambda m: m['lo'] if side > 0 else -m['hi'])
            chosen, edge = [], (cur['hi'] if cur and side > 0 else cur['lo'] if cur else price)
            for m in pool_:
                if len(chosen) >= n:
                    break
                near = m['lo'] if side > 0 else m['hi']
                # zones closer than 1.5 1h ATR to the previous pick are one step (a range's 1h turns made a zone every
                # ~300 on BTC 82.5-87k): the stronger stays
                if chosen and side * (near - edge) < max(m['tol'], chosen[-1]['tol'], 1.5 * atr1h):
                    # within the pierce of the previous pick: price treats them as one place - keep the stronger
                    if rank(m) < rank(chosen[-1]):
                        chosen[-1] = m
                        edge = m['hi'] if side > 0 else m['lo']
                    continue
                chosen.append(m)
                edge = m['hi'] if side > 0 else m['lo']
            return chosen
        # the edges of a wide zone around the price are levels of their own (ETH inside the daily FVG 2 484-2 568: its
        # low is the first support for a short's target, not 2 469 beyond it)
        for m in wide:
            for side, edge in ((-1, m['lo']), (1, m['hi'])):
                if side * (edge - price) > m['tol'] and not (cur and cur['lo'] <= edge <= cur['hi']):
                    cands.append({**m, 'lo': edge, 'hi': edge, 'mid': edge, 'wide': False,
                                  'labels': [f"край: {lb}" for lb in m['labels'][:2]]})
        for m in cands:
            m['lo'], m['hi'] = min(m['lo'], m['hi']), max(m['lo'], m['hi'])
        above, below = ladder(1, 3), ladder(-1, 2)
        out = []
        for side, group in ((1, above[::-1]), (0, [cur] if cur else []), (-1, below)):
            for m in group:
                labels = sorted(m['labels'], key=_label_rank)
                out.append({'lo': m['lo'], 'hi': m['hi'], 'mid': m['mid'], 'side': side, 'strength': m['strength'],
                            'tol': m['tol'],
                            'pad': m['pad'], 'wide': m['wide'], 'label': ' · '.join(labels[:4]),
                            'desc': (m.get('sr_desc', '') + (f"; здесь же: {', '.join(describe(m['labels']).split(', ')[:2])}" if m['labels'] else ''))
                            .lstrip('; ') or describe(m['labels'])})
        return price, out

    # ------------------------------------------------------------------ briefing
    def coin_text(self, symbol: str) -> Optional[str]:
        """The coin's zones and the two scenarios of the card (briefing_chart.plan: one source for the text, the
        picture, the watch alerts and the evening scoring)."""
        import briefing_chart
        price, zones = self.key_zones(symbol)
        if not price:
            return None
        bias, st = self._bias_of(symbol)
        self.zones[symbol] = zones
        md = self.sc.market_data.get(symbol)
        d1 = list(md.d1) if md else []
        chg = f"{(price / d1[-1][4] - 1) * 100:+.2f}% к закрытию дня" if d1 else ''
        lines = [f"<b>{_short(symbol)}</b> {_fmt(price)} ({chg})", self._bias_line(symbol, bias, st)]
        for z in zones:
            tag = {1: '🔴 сопр.', 0: '🔵 цена в зоне', -1: '🟢 подд.'}[z['side']]
            lines.append(f"{tag} {_fmt(z['lo'])}–{_fmt(z['hi'])} [{z['strength']:.0f}] {z['label']}")
        ctx = self._context_text(symbol)
        if ctx:
            lines.append(ctx)
        tf = self.sc._tf_atrs(symbol)
        ath, days = self._history_high(md) if md else (None, 0)
        p = briefing_chart.plan(price, zones, tf.get('1d'), ath, days)
        for side, name in (('long', 'Лонг'), ('short', 'Шорт')):
            sc = p[side]
            if sc:
                lines.append(f"{name}: {sc['cond']}; стоп {_fmt(sc['stop'])}; цели "
                             + ' / '.join(_fmt(t) for t in sc['targets']))
        self.scenario[symbol] = {'long': p['long'], 'short': p['short'], 'price': price, 'ts': time.time()}
        return '\n'.join(lines)

    @staticmethod
    def light_src(symbol: str, price: float, h1: List, h4: List, d1: List, w1: List):
        """A coin outside the universe, from REST candles only (rows [ts, o, h, l, c, ...]): the same shape key_zones /
        htf_bias read. No flows, liquidations or level map - the zones are the swing clusters of sr.zones alone."""
        import types
        md = types.SimpleNamespace(symbol=symbol, h1=h1, h4=h4, d1=d1, w1=w1, last_price=price, minute_klines=[])
        now = time.time() * 1000
        tf: Dict[str, float] = {}
        for k, rows, period in (('1h', h1, 3_600_000), ('4h', h4, 14_400_000), ('1d', d1, 86_400_000)):
            closed = [r for r in rows[-20:] if r[0] + period <= now]
            if len(closed) >= 15:
                trs = [max(c[2] - c[3], abs(c[2] - p[4]), abs(c[3] - p[4])) for p, c in zip(closed[-15:-1], closed[-14:])]
                tf[k] = sum(trs) / len(trs)
        return md, {'price': price, 'levels': [], 'tf': tf, 'md': md}

    def analyze(self, symbol: str, md=None, src: Optional[Dict] = None, cards: Optional[List[Dict]] = None) -> Dict:
        """The web analysis of one coin (pinned or typed in): zones, higher-timeframe bias, the long / short scenarios
        of briefing_chart.plan with their R:R and a mechanical checklist per side. Pure: the watched state (context,
        zones, scenario) is restored, nothing is posted. A rule list, not advice."""
        import briefing_chart
        price, zones = self.key_zones(symbol, src, keep_state=False)
        md = md if md is not None else self.sc.market_data.get(symbol)
        if not price or md is None:
            return {'symbol': symbol, 'error': 'нет данных'}
        if not zones:
            return {'symbol': symbol, 'error': 'история ещё загружается или зон рядом нет'}
        bias, st = self._bias_of(symbol, md)
        tf = (src or {}).get('tf') or self.sc._tf_atrs(symbol, md)
        atr1d, atr1h = tf.get('1d'), tf.get('1h')
        ath, days = self._history_high(md)
        p = briefing_chart.plan(price, zones, atr1d, ath, days)
        events = macro_today(datetime.now(MSK))
        d1c = [c for c in md.d1 if c[0] + 86_400_000 <= time.time() * 1000]       # closed days only (REST rows hold today's)
        out = {'symbol': symbol, 'base': _short(symbol), 'price': price, 'light': src is not None,
               'chg_day': (price / d1c[-1][4] - 1) * 100 if d1c else None,
               'bias': bias, 'bias_ru': BIAS_RU.get(bias, bias), 'bias_line': self._bias_line(symbol, bias, st),
               'atr1h': atr1h, 'atr1d': atr1d,
               'zones': [{k: z[k] for k in ('lo', 'hi', 'side', 'strength', 'label')} for z in zones],
               'macro': [f"{dt:%H:%M} {name}" for dt, name in events], 'scenarios': {}, 'cards': cards or []}
        if src is None:
            out['outcomes'] = self.outcomes(symbol, 14, md)
        for side, d, name in (('long', 1, 'Лонг'), ('short', -1, 'Шорт')):
            sc = p.get(side)
            if not sc:
                out['scenarios'][side] = None
                continue
            e = sum(sc['entry']) / 2
            risk, reward = abs(e - sc['stop']), abs(sc['targets'][0] - e)
            rr = reward / risk if risk else 0.0
            dist = abs(e - price) / atr1h if atr1h else None
            checks = []
            aligned = bias in ('bull', 'bear') and ((bias == 'bull') == (d == 1))
            against = bias in ('bull', 'bear') and not aligned
            checks.append(('Старший ТФ', 'ok' if aligned else 'bad' if against else 'warn', BIAS_RU.get(bias, bias)))
            checks.append(('R:R до TP1', 'ok' if rr >= 2 else 'warn' if rr >= 1 else 'bad', f"{rr:.1f}"))
            if dist is not None:
                checks.append(('Вход от цены', 'ok' if dist <= 1.5 else 'warn' if dist <= 4 else 'bad',
                               f"{dist:.1f} ATR(1h)"))
            if events:
                checks.append(('Макро сегодня', 'warn', ', '.join(n for _, n in events)[:80]))
            mine = [c for c in (cards or []) if c.get('direction') == d]
            against_cards = [c for c in (cards or []) if c.get('direction') == -d]
            if mine:
                checks.append(('Карточки бота', 'ok', f"{len(mine)} по направлению"))
            if against_cards:
                checks.append(('Карточки бота', 'bad', f"{len(against_cards)} против"))
            bad = sum(1 for _, s, _ in checks if s == 'bad')
            warn = sum(1 for _, s, _ in checks if s == 'warn')
            verdict = 'нет' if bad else 'осторожно' if warn >= 2 else 'условия выполнены' if warn == 0 else 'приемлемо'
            out['scenarios'][side] = {
                'name': name, 'cond': sc['cond'], 'tag': sc.get('tag'), 'entry': list(sc['entry']), 'stop': sc['stop'],
                'targets': list(sc['targets']), 'p': sc['p'], 'rr': rr, 'checks': checks, 'verdict': verdict}
        return out

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
        # audit N23: the NYSE 09:30 ET open in MSK for TODAY (16:30 in summer, 17:30 in winter), not a constant
        ny_open = datetime.now(NY).replace(hour=9, minute=30, second=0, microsecond=0).astimezone(MSK)
        out.append(f'Открытие NY ({ny_open:%H:%M} МСК): первые 30 мин BTC ×2.5, альты ×1.8 обычной амплитуды, '
                   f'направление ~50/50')
        # Deribit (eng-72): DVOL = the 30-day implied volatility; the move it prices for one day = DVOL / sqrt(365)
        for cur, o in sorted((getattr(self.sc.fetcher, 'options', None) or {}).items()):
            if o.get('dvol'):
                line = (f"Опционы {cur}: DVOL {o['dvol']:.0f} ({o['dvol'] - (o.get('dvol_24h') or o['dvol']):+.1f} за сутки)"
                        f" → рынок закладывает ±{o['dvol'] / 365 ** 0.5:.1f}% за день")
                if o.get('strikes'):
                    line += '; крупный OI: ' + ', '.join(f"{_fmt(k)} ({'колл' if c >= 0.6 else 'пут' if c <= 0.4 else 'смеш.'}, "
                                                        f"{e})" for k, _, c, e in o['strikes'][:3])
                out.append(line)
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
                bias_line = self._bias_line(symbol, bias, st)
                if len(md.h1) < 48:
                    continue
                hi24, lo24 = self._extremes_24h(md)
                ath, ath_days = self._history_high(md)
                png = briefing_chart.render(f"{_short(symbol)}USDT", list(md.h1)[-72:], price,
                                            self.zones.get(symbol) or [], tf.get('1h'), bias_line, tf.get('1d'),
                                            candles_1h=list(md.h1), tf_label='1h',
                                            ath=ath, ath_days=ath_days, hi24=hi24, lo24=lo24,
                                            context_text=self._context_text(symbol))
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
        # the archive verdict on these zones (research/sr_zones.md) was void - wrong method, redone before any claim
        parts.append('<i>Зоны — места, где цена разворачивалась (1h/4h/1d). Механические правила, не совет.</i>')
        return '\n\n'.join(p for p in parts if p)

    def _save(self, slot: str, title: str) -> None:
        """Each briefing's forecast per coin (bias, zones, scenario) to data/briefings.jsonl: the posts lived only in
        Telegram, so nothing could be scored afterwards (2026-10-07 review)."""
        import json
        os.makedirs('data', exist_ok=True)
        with open(os.path.join('data', 'briefings.jsonl'), 'a', encoding='utf-8') as f:
            for symbol in self.watched():
                bias, st = self._bias_of(symbol)
                f.write(json.dumps({'slot': slot, 'title': title, 'ts': time.time(), 'symbol': symbol,
                                    'price': self.sc._price_of(symbol), 'bias': bias,
                                    'state': {k: st.get(k) for k in ('tsm', 'w1', 'd1', 'h4', 'adx4')},
                                    'zones': self.zones.get(symbol) or [], 'scenario': self.scenario.get(symbol)},
                                   ensure_ascii=False, default=str) + '\n')
            # the other pinned coins: the same forecast kept silently (no post) so their scenarios are scored too
            import briefing_chart
            watched = set(self.watched())
            for base in CONFIG.exchange.pinned_bases:
                symbol = f"{base}/USDT:USDT"
                md = self.sc.market_data.get(symbol)
                if symbol in watched or md is None:
                    continue
                try:
                    price, zones = self.key_zones(symbol, keep_state=False)
                    if not price or not zones:
                        continue
                    bias, st = self._bias_of(symbol)
                    ath, days = self._history_high(md)
                    p = briefing_chart.plan(price, zones, self.sc._tf_atrs(symbol).get('1d'), ath, days)
                except Exception as e:
                    errors.report('briefing._save', e, f"Silent briefing record failed for {symbol}")
                    continue
                f.write(json.dumps({'slot': slot, 'title': title, 'ts': time.time(), 'symbol': symbol, 'silent': True,
                                    'price': price, 'bias': bias,
                                    'state': {k: st.get(k) for k in ('tsm', 'w1', 'd1', 'h4', 'adx4')},
                                    'zones': zones, 'scenario': {'long': p['long'], 'short': p['short'], 'price': price,
                                                                 'ts': time.time()}},
                                   ensure_ascii=False, default=str) + '\n')

    def outcomes_total(self, days: int = 14) -> Dict:
        """The tally over every pinned coin (long / short x outcome class) for the analysis page's header."""
        total: Dict[str, Dict[str, int]] = {}
        for base in CONFIG.exchange.pinned_bases:
            for side, m in (self.outcomes(f"{base}/USDT:USDT", days).get('tally') or {}).items():
                for k, n in m.items():
                    total.setdefault(side, {}).setdefault(k, 0)
                    total[side][k] += n
        return {'days': days, 'tally': total}

    def snapshot_outcomes(self) -> None:
        """The evening tally of the last 14 days per coin to data/briefing_outcomes.jsonl (one line a day): the trend of
        the plan rules' results over time, kept apart from the Telegram recaps."""
        import json
        coins = {}
        for base in CONFIG.exchange.pinned_bases:
            symbol = f"{base}/USDT:USDT"
            o = self.outcomes(symbol, 14)
            if o.get('tally'):
                coins[base] = o['tally']
        if not coins:
            return
        os.makedirs('data', exist_ok=True)
        with open(os.path.join('data', 'briefing_outcomes.jsonl'), 'a', encoding='utf-8') as f:
            f.write(json.dumps({'day': f"{datetime.now(MSK):%Y-%m-%d}", 'days': 14, 'coins': coins}, ensure_ascii=False) + '\n')

    @staticmethod
    def reaction(sc: Dict, side: int, c) -> bool:
        """The REACTION that enters a briefing scenario (eng-74; the cards said 'реакция' / 'отказ' and the scoring
        filled on a mere touch): a closed 1h candle that traded into the entry range and closed back beyond its far
        edge in the trade's direction, as a candle of that colour - the confirmation candle of the break-and-retest /
        range playbooks (a wick into the level, the close back out)."""
        e0, e1 = sorted(sc['entry'])
        if side > 0:
            return c[3] <= e1 and c[4] > e1 and c[4] > c[1]
        return c[2] >= e0 and c[4] < e0 and c[4] < c[1]

    @classmethod
    def score_scenario(cls, sc: Dict, side: int, bars: List) -> str:
        """
        One briefing scenario against the 1h candles after its post: 'закрепление' plans arm on a 1h close beyond the
        zone, then every plan enters on its reaction candle's close (`reaction`); then the first of the stop or TP1
        (both in one candle = the stop), R from the reaction close. A close beyond that never reacted is reported as
        the move without a retest (Bulkowski: no throwback after 26-32% of breakouts).
        """
        e0, e1 = sorted(sc['entry'])
        stop, tp1 = sc['stop'], sc['targets'][0]
        breakout = sc['tag'].startswith('закрепление')
        armed = not breakout
        fill = None
        touched = False
        for c in bars:
            if not armed:
                if (side > 0 and c[4] > e0) or (side < 0 and c[4] < e1):
                    armed = True
                continue
            if fill is None:
                touched = touched or (c[3] <= e1 and c[2] >= e0)
                if side * (c[4] - stop) <= 0:
                    return 'отменён: закрытие за стопом до реакции'
                if cls.reaction(sc, side, c):
                    fill = c[4]
                    if side * (tp1 - fill) <= 0:
                        # audit C15: the reaction closed at / beyond TP1 - no trade with a target ahead
                        return 'пропущен: реакция закрылась за TP1'
                continue
            if (c[3] <= stop) if side > 0 else (c[2] >= stop):
                return 'вход → стоп (−1R)'
            if (c[2] >= tp1) if side > 0 else (c[3] <= tp1):
                return f"вход → TP1 ({side * (tp1 - fill) / abs(fill - stop):+.1f}R)"
        if fill is not None:
            return 'вход, без исхода'
        if armed and breakout and not touched:
            far = max(c[2] for c in bars) if side > 0 else min(c[3] for c in bars)
            reached = (far >= tp1) if side > 0 else (far <= tp1)
            return 'закрепление без ретеста' + (' — цена дошла до TP1 без входа' if reached else '')
        return 'тест без реакции' if touched else 'не включился'

    def _score_today(self, symbol: str, md) -> List[str]:
        """Today's saved briefings of the coin (data/briefings.jsonl), each scenario scored on the closed 1h candles."""
        import json
        path = os.path.join('data', 'briefings.jsonl')
        today = f"{datetime.now(MSK):%Y-%m-%d}"
        out = []
        try:
            with open(path, encoding='utf-8') as f:
                recs = [json.loads(x) for x in f if x.strip()]
        except OSError:
            return out
        now = time.time() * 1000
        closed = [c for c in md.h1 if c[0] + HOUR_MS <= now]
        minutes = [c for c in md.minute_klines if c[0] + 60_000 <= now]
        for r in recs:
            if r.get('symbol') != symbol or not str(r.get('slot', '')).startswith(today):
                continue
            res, ambiguous = self._score_record(r, closed, minutes)
            if res:
                out.append(f"· {r['title']} ({r['slot'][-5:]}): " + '; '.join(f"{name}: {txt}" for name, txt, _ in res)
                           + (' (час публикации не оценён: нет минутных свечей)' if ambiguous else ''))
        return out

    def _score_record(self, r: Dict, closed: List, minutes: List, until_ms: Optional[float] = None):
        """One saved briefing record against the closed 1h candles after its post: ([(name, result, tag)], ambiguous).
        audit N22: only prices AFTER the post. The hour holding the post is scored on its 1m candles after the post's
        minute; without them that hour is left out and said so (its OHLC may be before the post)."""
        sc = r.get('scenario') or {}
        post_ms = r['ts'] * 1000
        first_full = (int(post_ms) // HOUR_MS + 1) * HOUR_MS
        head = [c for c in minutes if post_ms <= c[0] < first_full]
        ambiguous = not head and post_ms % HOUR_MS != 0
        # the post-hour's minutes after the post as ONE partial 1h bar (the reaction rule reads 1h candle shapes)
        part = [[head[0][0], head[0][1], max(c[2] for c in head), min(c[3] for c in head), head[-1][4]]] \
            if head and head[-1][0] + 60_000 >= first_full else []
        bars = part + [c for c in closed if c[0] >= first_full and (until_ms is None or c[0] < until_ms)]
        res = []
        for key, side, name in (('long', 1, 'лонг'), ('short', -1, 'шорт')):
            if sc.get(key):
                res.append((name, self.score_scenario(sc[key], side, bars), sc[key].get('tag', '')))
        return res, ambiguous

    @staticmethod
    def _outcome_class(txt: str) -> str:
        if txt.startswith('вход → TP1'):
            return 'tp1'
        if txt.startswith('вход → стоп'):
            return 'stop'
        if txt.startswith('вход, без исхода'):
            return 'open'
        if txt.startswith('отменён') or txt.startswith('пропущен'):
            return 'cancelled'
        return 'no_entry'

    def outcomes(self, symbol: Optional[str] = None, days: int = 7, md=None) -> Dict:
        """The saved briefings' scenarios scored on the closed candles (each against its own MSK day, as the recap):
        counts by scenario side and outcome class. A tally of what the plan rules did, not a verdict on them."""
        import json
        try:
            with open(os.path.join('data', 'briefings.jsonl'), encoding='utf-8') as f:
                recs = [json.loads(x) for x in f if x.strip()]
        except (OSError, ValueError):
            return {}
        since = time.time() - days * 86400
        now = time.time() * 1000
        tally: Dict[str, Dict[str, int]] = {}
        for r in recs:
            sym = r.get('symbol')
            if r.get('ts', 0) < since or (symbol and sym != symbol):
                continue
            m = md if (md is not None and sym == symbol) else self.sc.market_data.get(sym)
            if m is None:
                continue
            closed = [c for c in m.h1 if c[0] + HOUR_MS <= now]
            minutes = [c for c in list(getattr(m, 'minute_klines', []) or []) if c[0] + 60_000 <= now]
            day_end = datetime.strptime(str(r['slot'])[:10], '%Y-%m-%d').replace(tzinfo=MSK) + timedelta(days=1)
            res, _ = self._score_record(r, closed, minutes, until_ms=day_end.timestamp() * 1000)
            for name, txt, _tag in res:
                cls = self._outcome_class(txt)
                tally.setdefault(name, {}).setdefault(cls, 0)
                tally[name][cls] += 1
        return {'days': days, 'tally': tally}

    def recap(self) -> str:
        # audit N23: the MSK day the header names (was the UTC day), and the period actually covered by the minute
        # ring (~10 hours) is stated - not called the day's range
        day0 = int(datetime.now(MSK).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        parts = [f"🌙 <b>Итог дня</b> · {datetime.now(MSK):%d.%m} МСК"]
        for symbol, zones in self.zones.items():
            md = self.sc.market_data.get(symbol)
            price = self.sc._price_of(symbol)
            if md is None or not price:
                continue
            today = [c for c in md.minute_klines if c[0] >= day0]
            if not today:
                continue
            hi, lo = max(c[2] for c in today), min(c[3] for c in today)
            since = datetime.fromtimestamp(today[0][0] / 1000, MSK)
            span = 'день' if today[0][0] - day0 < 5 * 60_000 else f"с {since:%H:%M} МСК"
            lines = [f"<b>{_short(symbol)}</b> {_fmt(price)} · {span} {_fmt(lo)}–{_fmt(hi)}"]
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
            lines += self._score_today(symbol, md)
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
                    self._post(msg + f"\n{z.get('desc') or z['label']}" + self._scenario_note(symbol, c[4]),
                               key=f"lvl|{symbol}|{z['lo']:.8g}|{msg[:2]}", every_sec=4 * 3600)
            # the scenario's REACTION on this closed 1h candle (breakouts only after their 1h close beyond): the entry
            sc = self.scenario.get(symbol) or {}
            since = [x for x in closed if x[0] >= (sc.get('ts') or 0) * 1000 - HOUR_MS + 1]
            for key, side, name in (('long', 1, 'Лонг'), ('short', -1, 'Шорт')):
                x = sc.get(key)
                if not x:
                    continue
                e0, e1 = sorted(x['entry'])
                armed = not x['tag'].startswith('закрепление') or any(
                    (side > 0 and b[4] > e0) or (side < 0 and b[4] < e1) for b in since[:-1])
                # audit C15: the target must still be ahead of the reaction close (a signed reward, not abs)
                if armed and self.reaction(x, side, c) and side * (c[4] - x['stop']) > 0 \
                        and side * (x['targets'][0] - c[4]) > 0:
                    rr = side * (x['targets'][0] - c[4]) / abs(c[4] - x['stop'])
                    self._post(f"✅ {_short(symbol)}: реакция у зоны — {name.lower()}-сценарий включён\n"
                               f"Вход ~{_fmt(c[4])} (закрытие 1h) · стоп {_fmt(x['stop'])} · цели "
                               + ' / '.join(_fmt(t) for t in x['targets']) + f" · R:R {rr:.1f}",
                               key=f"react|{symbol}|{key}|{sc.get('ts')}", every_sec=24 * 3600)

    def session_now(self) -> Optional[str]:
        # audit N23: the opens in their own zones (DST of each), not fixed MSK hours: Tokyo 09:00, London 08:00,
        # New York 09:30 local
        utc_now = datetime.now(MSK)
        for name, zone, hm in (('Азии', ZoneInfo('Asia/Tokyo'), (9, 0)), ('Лондона', ZoneInfo('Europe/London'), (8, 0)),
                               ('Нью-Йорка', NY, (9, 30))):
            local = utc_now.astimezone(zone)
            t = local.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
            if timedelta(0) <= local - t <= timedelta(minutes=60):
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
                           # audit N23: no BTC veto exists since eng-100 (regime_against_mult = 1): no such claim
                           ,
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
                rr = f" · {r['r']:+.2f}R" if r.get('r') is not None else ''
                why = DEMO_RU.get(r['close_reason'], r['close_reason'])
                self._post(f"💼 Демо {side} {name} {r.get('setup')}: {why}{rr}"
                           + (f"\n{r['error']}" if r.get('entry_fill') is None and r.get('error') else ''), topic='demo')
            elif r.get('entry_fill'):
                self._post(f"💼 Демо {side} {name} {r.get('setup')}: открыта по {r['entry_fill']:.6g}"
                           + (f", стоп {r['sl']:.6g}" if r.get('sl') else ''), topic='demo')
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
                q = ("SELECT ts_ms, symbol, group_key, price, liq_long_5m, liq_short_5m FROM signals WHERE kind='anomaly'"
                     " AND ts_ms > ? AND symbol IN (%s)"
                     " AND group_key IN (%s) ORDER BY ts_ms" % (','.join('?' * len(watched)), ','.join('?' * len(ANOMALY_LABELS))))
                rows = c.execute(q, (self._anom_seen, *watched, *ANOMALY_LABELS)).fetchall()
        except sqlite3.Error as e:
            errors.report('briefing.anomalies', e)
            return
        for ts, symbol, label, price, liq_l, liq_s in rows:
            self._anom_seen = max(self._anom_seen, ts)
            self._anom_buf.setdefault(symbol, []).append((ts, label, price, liq_l or 0.0, liq_s or 0.0))
        # one message per coin and burst (eng-74): ETH sent 'sweep of the low', then the cascade, the OI flush and the
        # whale buying as four unrelated lines within 12 minutes - the events of 5 minutes go out together, with the
        # zone they happened at and what that means for the briefing's scenarios
        now = time.time() * 1000
        for symbol, evs in list(self._anom_buf.items()):
            if now - evs[0][0] < 5 * 60_000:
                continue
            del self._anom_buf[symbol]
            # which side was liquidated, with the sums (the label alone said 'распродажа / откуп' - both ways)
            liq_l, liq_s = max(e[3] for e in evs), max(e[4] for e in evs)
            side = ((f"ликвидации лонгов ${liq_l / 1e6:.1f}M" if liq_l >= liq_s else f"ликвидации шортов ${liq_s / 1e6:.1f}M")
                    if liq_l or liq_s else '')
            labels = list(dict.fromkeys(
                (f"каскад: {side}" if lb == 'LIQ CASCADE' and side else ANOMALY_RU.get(lb, lb)) for _, lb, *_ in evs))
            lo, hi = min(e[2] for e in evs), max(e[2] for e in evs)
            where = _fmt(lo) if lo == hi else f"{_fmt(lo)}–{_fmt(hi)}"
            price = self.sc._price_of(symbol) or evs[-1][2]
            self._post(f"⚡ {_short(symbol)} {where}: " + '; '.join(labels) + self._zone_note(symbol, lo, hi)
                       + self._scenario_note(symbol, price),
                       key=f"anom|{symbol}|{'|'.join(sorted(set(e[1] for e in evs)))}", every_sec=1800)

    def _zone_note(self, symbol: str, lo: float, hi: float) -> str:
        """Which briefing zone (or wide context zone) the events happened at, within its tolerance."""
        for z in (self.zones.get(symbol) or []) + (self.context.get(symbol) or []):
            t = z.get('tol') or 0.0
            if z['lo'] - t <= hi and lo <= z['hi'] + t:
                role = {1: 'сопротивления', -1: 'поддержки', 0: 'реакции'}.get(z.get('side'), '')
                what = z.get('desc') or describe(z.get('labels') or [z.get('label', '')])
                inside = z['lo'] <= lo and hi <= z['hi']
                return f"\n{'В зоне' if inside else 'У зоны'} {role} {_fmt(z['lo'])}–{_fmt(z['hi'])}: {what}"
        return '\nВне зон брифинга'

    def _scenario_note(self, symbol: str, price: float) -> str:
        """What the price now means for the briefing's two scenarios: which one is armed / where it is cancelled."""
        sc = self.scenario.get(symbol) or {}
        notes = []
        for key, side, name in (('long', 1, 'Лонг'), ('short', -1, 'Шорт')):
            x = sc.get(key)
            if not x:
                continue
            e0, e1 = sorted(x['entry'])
            if side * (price - x['stop']) <= 0:
                notes.append(f"{name}-сценарий отменён: цена за стопом {_fmt(x['stop'])}")
            elif x['tag'].startswith('закрепление') and side * (price - (e0 if side > 0 else e1)) > 0:
                notes.append(f"{name}: закрепление есть — ждём ретест {_fmt(e0)}–{_fmt(e1)}, стоп {_fmt(x['stop'])}")
            else:
                notes.append(f"{name}: ждём {x['cond']}")
        return ('\n' + '\n'.join(notes)) if notes else ''

    def check_health(self):
        status = self.sc.fetcher.venue_status()
        down = [v for v, st in status.items() if not st.get('connected', 1)]
        if down:
            self._post(f"🛠 Бот: нет потока {', '.join(down)}", key='health|down|' + ','.join(sorted(down)), every_sec=3600, topic='service')
        failed = errors.health_text()
        if failed:
            self._post(f"🛠 Бот: ошибки компонентов — {failed}", key='health|errors', every_sec=3 * 3600, topic='service')
        ex = (self.sc.demo if self.sc.demo.enabled else None)
        if ex is not None:
            try:
                limit = ex.risk_limit()
            except Exception as e:
                errors.report('briefing.risk', e)
                limit = None
            if limit:
                self._post(f"🛑 Демо остановлено на сегодня: {limit}", key='health|risk', every_sec=6 * 3600, topic='demo')

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
        # the 1h candles closed before the start were judged by the previous run: alerts only for candles that close
        # from now on (each restart re-alerted the last closed hour: CL at 01:02 and 01:07)
        now_ms = time.time() * 1000
        for symbol in self.watched():
            md = self.sc.market_data.get(symbol)
            closed = [c for c in (md.h1 if md else []) if c[0] + HOUR_MS <= now_ms]
            if closed:
                self._last_h1[symbol] = closed[-1][0]
        self._sent.update({f"shock|{s}|{d}": time.time() for s in self.watched() for d in (1, -1)})
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
                            self.sc.notifier.post(await asyncio.to_thread(self.recap), 'briefing')
                            await asyncio.to_thread(self.snapshot_outcomes)
                        else:
                            for png, cap in await asyncio.to_thread(self.cards, title):
                                self.sc.notifier.post_photo(png, cap)
                            await asyncio.to_thread(self._save, slot, title)
                for dt, name in macro_today(now):
                    if timedelta(0) <= dt - now <= timedelta(minutes=30):
                        self._post(f"📅 Через {int((dt - now).total_seconds() // 60)} мин: {name} ({dt:%H:%M} МСК) — "
                                   f"входы бота за 30 мин до / 60 после CPI и FOMC блокируются",
                                   key=f"macro|{dt:%Y%m%d%H%M}", every_sec=86400, topic='briefing')
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
