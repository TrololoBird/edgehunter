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


H4_MS = 4 * 3_600_000
HIGHER_LABELS = ('PDH', 'PDL', 'PWH', 'PWL', 'PMH', 'PML', 'POC', 'VAH', 'VAL', 'd high', 'd low', '52w')


def to_4h(bars: List) -> List:
    """eng-168y: closed 1h bars [ts, o, h, l, c] -> the complete 4h bars (UTC 4h boundaries) they make."""
    out, grp = [], {}
    for b in bars:
        grp.setdefault(int(b[0]) // H4_MS * H4_MS, []).append(b)
    for t in sorted(grp):
        # eng-168z / audit #9: exactly the four hours of the interval, one row each (a duplicate row of an hour or a
        # misaligned timestamp is no 4h bar)
        g = sorted({int(x[0]): x for x in grp[t]}.values(), key=lambda x: x[0])
        if [int(x[0]) for x in g] == [t + k * 3_600_000 for k in range(4)] and len(grp[t]) == 4:
            out.append([t, g[0][1], max(x[2] for x in g), min(x[3] for x in g), g[-1][4]])
    return out


def conf_tf(zone: Dict) -> str:
    """eng-168y (the owner: analysis is not the bot's strategies): the candle that confirms a close beyond a zone
    follows the zone's own timeframe - 4h for a zone of 4h / 1d / 1w pivots or a higher map level (previous day / week /
    month extremes, the value area), 1h for an intraday one (1h pivots, today's extremes, sessions)."""
    # eng-168z (audit #8): from the zone's structured origin only - the timeframes of its own pivots ('tfs') and, for a
    # map-level zone, the period of that level ('1d' for PD / PW / PM / year / weekly swing / POC / VA). The labels are
    # text for the reader: a nearby '1d low' or 'breaker 4h' named in them made almost every zone 4h.
    return '4h' if set(zone.get('tfs') or ()) & {'4h', '1d', '1w'} else '1h'


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
    # eng-168t: the official schedules (BLS / ISM / FOMC) first, then the live week's events not already listed (same
    # release within 10 minutes)
    import official_calendar
    official = [(datetime.fromtimestamp(e['t'] / 1000, MSK), e['title'] + ' ❗' + (' (не подтверждено)' if e['status'] == 'unconfirmed' else ''))
                for e in official_calendar.all_events() if datetime.fromtimestamp(e['t'] / 1000, MSK).date() == day]
    if macro_calendar.LIVE or official:
        # eng-72: the real week calendar (ForexFactory, USD high / medium impact) replaces the publication rules
        live = [(datetime.fromtimestamp(t / 1000, MSK), f"{name}{' ❗' if imp == 'High' else ''}")
                for t, name, imp in macro_calendar.LIVE if datetime.fromtimestamp(t / 1000, MSK).date() == day]
        live = [x for x in live if not any(abs((x[0] - o_[0]).total_seconds()) <= 600 for o_ in official)]
        return sorted(official + live)
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
        self._proxy: Dict[str, Tuple[float, Dict]] = {}  # base -> (fetched at, spot proxy candles)
        self._anom_buf: Dict[str, List[Tuple[int, str, float]]] = {}   # symbol -> the burst being collected
        self.scenario: Dict[str, Dict] = {}
        self._sent: Dict[str, float] = {}               # dedupe key -> last send time
        self._bias: Dict[str, Optional[str]] = {}
        self._last_h1: Dict[str, int] = {}
        self._demo_seen = 0
        self._anom_seen = int(time.time() * 1000)
        self._done_slots: set = self._load_slots()

    SLOTS_PATH = os.path.join('data', 'briefing_slots.json')

    def _load_slots(self) -> set:
        """The schedule slots already sent (owner 2026-10-18: a restart inside a slot's 10 minutes sent the 10-15 02:30
        briefing twice - the set lived in memory only)."""
        import json
        try:
            with open(self.SLOTS_PATH, encoding='utf-8') as f:
                return set(json.load(f))
        except (OSError, ValueError):
            return set()

    def _save_slots(self) -> None:
        import json
        keep = sorted(self._done_slots)[-40:]          # 'YYYY-MM-DD HH:MM' sorts by time; 10 days of 4 slots
        self._done_slots = set(keep)
        try:
            os.makedirs('data', exist_ok=True)
            tmp = self.SLOTS_PATH + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(keep, f)
            os.replace(tmp, self.SLOTS_PATH)
        except OSError as e:
            errors.report('briefing._save_slots', e, "Briefing slots state")

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
        since = None
        base = _short(symbol)
        b = self.sc.fetcher.htf_bias(md, time.time() * 1000)
        coin = dict((b or {}).get('coin') or {})
        if base in self.PROXY and 0 < len(md.d1) < 366 and coin.get('d1') is not None:
            # eng-168m (audit #3): every indicator (EMA / ADX / the 30 / 90-day signs) on the contract's OWN candles; the
            # proxy (PAXG spot) only completes the 365-day return as a product of the two legs' relative moves, each
            # on its own dates - no candle splice, no scale from one overlap candle
            hist = self._proxy_history(base)
            now_ms = time.time() * 1000
            d1 = [c for c in md.d1 if c[0] + 86_400_000 <= now_ms]
            paxg = list(hist.get('1d') or [])
            # eng-168p: the days the contract covers by its timestamps; the chain is contiguous - PAXG from (first
            # contract day - need) to the contract's FIRST day itself, the contract from that day's close on (the PAXG
            # leg ended the day before and the contract's first day's move fell out); both PAXG ends must exist within
            # 1 day of their date, else no proxy (a gap in PAXG made 'the nearest candle' weeks away)
            need = 365 - int(round((d1[-1][0] - d1[0][0]) / 86_400_000)) if d1 else 0
            day = 86_400_000

            def at(t):
                c = min(paxg, key=lambda x: abs(x[0] - t)) if paxg else None
                return c if c is not None and abs(c[0] - t) <= day else None
            p_end = at(d1[0][0]) if d1 else None
            p_start = at(d1[0][0] - need * day) if d1 and need > 0 else None
            if p_end is not None and p_start is not None and p_start[0] < p_end[0]:
                import numpy as np
                from strategies import bias as htf
                leg = d1[-1][4] / d1[0][4] * (p_end[4] / p_start[4])
                signs = [np.sign(d1[-1][4] / d1[-1 - n][4] - 1) for n in (30, 90) if len(d1) > n] + [np.sign(leg - 1)]
                coin['tsm'] = round(float(np.mean(signs)), 3)
                coin['bias'] = htf.bias_of({'tsm': coin['tsm'], 'w1': coin.get('w1'), 'd1': coin.get('d1'),
                                            'h4': coin.get('h4'), 'adx4': coin.get('adx4')})
                since = (self.PROXY[base], d1[0][0])
        bias, h4, adx4 = coin.get('bias'), coin.get('h4'), coin.get('adx4')
        if self.cfg.bias_h4_adx > 0 and bias in ('bull', 'bear') and h4 == (-1 if bias == 'bull' else 1) and \
                adx4 is not None and adx4 >= self.cfg.bias_h4_adx:
            bias = 'conflict'                        # owner 2026-10-18: a strong 4h trend against the weeks
        return bias, {**coin, 'range_mid': (b or {}).get('range_mid'), 'proxy': since,
                                  'days': len(md.d1)}

    @staticmethod
    def session_bias(md) -> Optional[int]:
        """eng-168l (audit #3): the fast background of the next 1-3 days beside the weekly one (which read 'bull' in 11 of
        14 falling sessions): +1 when the last closed 4h is above its EMA20, the EMA20 rose over 3 candles (12h) and the
        24h return is positive; -1 mirrored; 0 else. A display / checklist context, not a trading filter; the periods
        are this module's choice (no source)."""
        if md is None:
            return None
        now = time.time() * 1000
        h4 = [c[4] for c in md.h4 if c[0] + 4 * HOUR_MS <= now]
        h1 = [c[4] for c in md.h1 if c[0] + HOUR_MS <= now]
        if len(h4) < 30 or len(h1) < 25:
            return None
        from strategies.ind_panel import ema
        import numpy as np
        e = ema(np.asarray(h4, dtype=float), 20)
        r24 = h1[-1] / h1[-25] - 1
        if h4[-1] > e[-1] > e[-4] and r24 > 0:
            return 1
        if h4[-1] < e[-1] < e[-4] and r24 < 0:
            return -1
        return 0

    @staticmethod
    def level_map(price: float, zones: List[Dict], sb: Optional[int]) -> List[str]:
        """eng-168x (the owner: the briefing is analysis and possible scenarios): the levels as an if-then map - for the
        nearest resistance / support (and the zone price is in) what a 1h close beyond it opens (the next zone), plus ONE
        base view: with the fast 1-3 day background up 'while above S, a test of R first', down mirrored, neutral = the
        range between them. Conditions only, no probability claimed."""
        up = sorted([z for z in zones if z['side'] == 1], key=lambda z: z['lo'])
        dn = sorted([z for z in zones if z['side'] == -1], key=lambda z: -z['hi'])
        cur = next((z for z in zones if z['side'] == 0), None)
        lines = []
        if up:
            nxt = up[1]['lo'] if len(up) > 1 else None
            lines.append(f"▲ {_fmt(up[0]['lo'])}–{_fmt(up[0]['hi'])}: закрепление {up[0].get('conf_tf', '1h')} выше {_fmt(up[0]['hi'])}"
                         + (f" → {_fmt(nxt)}" if nxt else ' → выше уровней карты нет'))
        if cur:
            lines.append(f"◆ цена в зоне {_fmt(cur['lo'])}–{_fmt(cur['hi'])}: ждём закрытие {cur.get('conf_tf', '1h')} за ней")
        if dn:
            nxt = dn[1]['hi'] if len(dn) > 1 else None
            lines.append(f"▼ {_fmt(dn[0]['lo'])}–{_fmt(dn[0]['hi'])}: закрытие {dn[0].get('conf_tf', '1h')} ниже {_fmt(dn[0]['lo'])}"
                         + (f" → {_fmt(nxt)}" if nxt else ' → ниже уровней карты нет'))
        sup = cur['lo'] if cur else (dn[0]['lo'] if dn else None)
        res = cur['hi'] if cur else (up[0]['hi'] if up else None)
        tgt_up = up[0]['lo'] if up else None
        tgt_dn = dn[0]['hi'] if dn else None
        if sb == 1 and sup and tgt_up:
            lines.append(f"📌 Пока выше {_fmt(sup)}, приоритет — тест {_fmt(tgt_up)}; закрытие {(cur or dn[0]).get('conf_tf', '1h')} ниже {_fmt(sup)} сменит сценарий")
        elif sb == -1 and res and tgt_dn:
            lines.append(f"📌 Пока ниже {_fmt(res)}, приоритет — тест {_fmt(tgt_dn)}; закрепление {(cur or up[0]).get('conf_tf', '1h')} выше {_fmt(res)} сменит сценарий")
        elif tgt_up and tgt_dn:
            lines.append(f"📌 Импульс 1–3 дн. нейтрален: диапазон {_fmt(tgt_dn)}–{_fmt(tgt_up)}, сценарий решит выход за него")
        return lines

    def positioning_line(self, symbol: str) -> Optional[str]:
        """eng-168w: the crowd beside the levels - the Binance share of accounts long (global long / short ratio) and the
        open interest change over the last hour. Context only: no rule reads it."""
        try:
            r = (getattr(self.sc, 'positioning', None).ratios.get(symbol) or {}).get('binance_global')
        except AttributeError:
            r = None
        md = self.sc.market_data.get(symbol)
        oi = None
        if md is not None and getattr(md, 'oi_samples', None):
            from strategies.oi_build import _oi_change
            oi = _oi_change(list(md.oi_samples), time.time() * 1000, 60)
        parts = []
        if r:
            parts.append(f"лонгов {r / (1 + r) * 100:.0f}% счетов (Binance)")
        if oi is not None:
            parts.append(f"открытый интерес {oi * 100:+.1f}% за час")
        return ('Позиционирование: ' + ', '.join(parts)) if parts else None

    def _bias_line(self, symbol: str, bias: Optional[str], st: Dict) -> str:
        """The higher timeframe as BACKGROUND (Elder's tide: a filter of direction over weeks, not the session's
        forecast - it said 'bull' for BTC / ETH / SOL through 11 of 14 falling sessions, 2026-10-05..07)."""
        line = (f"Фон (недели): {BIAS_RU.get(bias, bias)} · неделя {_arrow(st.get('w1'))} · день "
                f"{_arrow(st.get('d1'))} · 4h {_arrow(st.get('h4'))}")
        sb = self.session_bias(self.sc.market_data.get(symbol))
        if sb is not None:
            line += f" · Импульс 1–3 дн.: {({1: 'рост', -1: 'падение', 0: 'нейтрально'})[sb]}"
        if st.get('proxy'):
            sym, ts = st['proxy']
            since = datetime.fromtimestamp(ts / 1000, MSK).strftime('%m.%Y') if ts else '?'
            line += f" · {_short(symbol)} с {since}, 365д-тренд дополнен {sym}"
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
        # eng-168q (audit #5): closed candles only (REST rows of a coin outside the universe hold the forming day / week)
        # and the depth by timestamps, not by the count of candles
        now = time.time() * 1000
        d1 = [c for c in md.d1 if c[0] + 86_400_000 <= now]
        w1 = [c for c in md.w1 if c[0] + 7 * 86_400_000 <= now]
        highs = [c[2] for c in d1] + [c[2] for c in w1]
        if not highs:
            return None, 0
        first = min([c[0] for c in d1[:1]] + [c[0] for c in w1[:1]])
        return max(highs), int(round((now - first) / 86_400_000))

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
            # eng-168q (audit #5): 'здесь же' only for a level whose price / band meets the zone; the others within
            # 0.6 ATR(1h) are 'рядом' with their distance (they were all called 'здесь же')
            def meets(l):
                lo_, hi_ = sorted((l.price, l.body if l.body is not None else l.price))
                return hi_ >= z['lo'] and lo_ <= z['hi']
            here_ = [l for l in near if meets(l)]
            beside = [(l, min(abs(l.price - z['lo']), abs(l.price - z['hi'])) / atr1h) for l in near if not meets(l)]
            # eng-168q: the pierce model measures swing_15m / swing_1h / equal / pdhl / round only - a zone of 4h / 1d
            # pivots takes swing_1h (the project's ZONE_KIND mapping); the source is kept and shown
            kind = 'swing_1h'
            tol = min(overshoot(symbol, kind, z['price'], 'p50') or 0.1 * atr1h, 0.5 * atr1h)
            pad = min(max(overshoot(symbol, kind, z['price'], 'p80') or 0.0, 0.5 * atr1h), atr1h)
            tfs = '/'.join(z['tfs'])
            what = f"{z['touches']} касан{'ие' if z['touches'] == 1 else 'ия' if z['touches'] < 5 else 'ий'} ({tfs})"                 + (', смена роли' if z['flip'] else '') \
                + (', свежий разворот (реакция ещё не досчитана)' if z.get('fresh') else '')
            higher = [t for t in z['tfs'] if t != '1h']
            cands.append({'lo': z['lo'], 'hi': z['hi'], 'mid': z['price'], 'strength': z['strength'],
                          'labels': list(dict.fromkeys(l.label for l in here_)),
                          'near': list(dict.fromkeys(f"{l.label} ({d:.1f} ATR)" for l, d in beside)),
                          'tol': tol, 'pad': pad, 'sr_desc': what,
                          'pierce_src': 'swing_1h' + (f" (для {'/'.join(higher)} нет своей статистики)" if higher else ''),
                          'tfs': list(z['tfs'])})
        # eng-168w (trace, audit #7): the key levels of the map are zones of their OWN when no pivot cluster holds
        # them - the previous day / week high / low and today's extremes (pdhl), equal highs / lows (equal: resting
        # stops), the week / month / year extremes, the value area (POC / VAH / VAL naked / 4-day / previous day).
        # They were labels of the pivot clusters only, so a PDH / PWH on the path to TP1 (73 traced scenarios) was no
        # obstacle and no target. Band: the level +- 0.15 ATR(1h) (or its body edge within one ATR); tol / pad from
        # the measured pierce of its own kind where the model has one (pdhl, equal), else swing_1h.
        prom = {'pdhl': ('pdhl', 2.0), 'equal': ('equal', 1.5), 'pmhl': ('pdhl', 3.0), 'year': ('pdhl', 3.0),
                'swing_1w': ('swing_1h', 3.0), 'poc': ('swing_1h', 2.0), 'va': ('swing_1h', 2.0)}
        for l in keep:
            spec = prom.get(l.kind.split('_')[0] if l.kind.startswith(('poc', 'va')) else l.kind)
            if spec is None or ' (pierce)' in (l.label or ''):
                continue
            if l.kind == 'pdhl' and l.label not in ('PDH', 'PDL', 'PWH', 'PWL', 'day high', 'day low'):
                continue                                   # session extremes stay labels (they would flood the ladder)
            if abs(l.price - price) > self.cfg.span_atr_1d * atr1d:
                continue
            if any(c['lo'] - c['tol'] <= l.price <= c['hi'] + c['tol'] for c in cands):
                continue                                   # a pivot cluster holds it: its label already names it
            pkind, strength = spec
            half = 0.15 * atr1h
            lo_, hi_ = l.price - half, l.price + half
            if l.body is not None and 0 < abs(l.body - l.price) <= atr1h:
                lo_, hi_ = sorted((l.price, l.body))
            tol_ = min(overshoot(symbol, pkind, l.price, 'p50') or 0.1 * atr1h, 0.5 * atr1h)
            pad_ = min(max(overshoot(symbol, pkind, l.price, 'p80') or 0.0, 0.5 * atr1h), atr1h)
            cands.append({'lo': lo_, 'hi': hi_, 'mid': l.price, 'strength': strength, 'labels': [l.label],
                          'near': [], 'tol': tol_, 'pad': pad_, 'sr_desc': 'уровень карты (без разворотов рядом)',
                          'pierce_src': pkind, 'map_level': True,
                          'tfs': ['1h'] if (l.kind == 'equal' or l.label in ('day high', 'day low')) else ['1d']})
        if not cands:
            return price, []
        # zones that overlap are one place: merged (up to 1.5 x ATR(1h) wide) - the cap above kept BTC's 81 857-82 500
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
                # overlapping but together wider than 1.5 x ATR(1h): split at the middle of the overlap (XAU 4 109-4 165
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
                              'near': list(dict.fromkeys(a.get('near', []) + m.get('near', []))),
                              'tfs': list(dict.fromkeys(a.get('tfs', []) + m.get('tfs', []))),
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
        # the other zones around the price are supports / resistances by their level price (a daily low whose candle
        # body reaches above the price - BTC's 82 500 / 83 461 - is a support at 82 500). audit (2nd part): the 'wide'
        # context branch is gone - sr.zones caps a zone at 1.5 x ATR(1h) and the merge above at the same width, so no
        # zone was ever wide: the branch, its text and its edge levels never ran
        for m in inside:
            if m is not cur:
                lo, hi = (min(m['lo'], m['mid']), min(m['mid'], price - m['tol'])) if m['mid'] < price                     else (max(m['mid'], price + m['tol']), max(m['hi'], m['mid']))
                m['lo'], m['hi'] = min(lo, hi), max(lo, hi)        # never inverted (XAU '4 118 - 4 115')

        def ladder(side, n):
            """Outward from the PRICE, NEAREST first (a target is the next level price meets - the strongest zone of a
            daily-ATR window skipped BTC's 82 500 daily low and ETH's 2 475 edge for weaker or farther ones); the next
            pick must lie beyond the previous one by more than their pierce (closer = one place); a zone of
            15m / 1h levels only was already dropped above."""
            pool_ = sorted((m for m in cands if m is not cur
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
                    # within the pierce of the previous pick: one place. eng-168j (audit): the NEAREST barrier stays
                    # (a stronger farther zone replaced it and TP1 jumped past a level price meets first); the
                    # farther zone's strength / labels are added to it as context
                    chosen[-1] = {**chosen[-1], 'strength': chosen[-1]['strength'] + m['strength'],
                                  'labels': list(dict.fromkeys(chosen[-1]['labels'] + m['labels']))}
                    continue
                chosen.append(m)
                edge = m['hi'] if side > 0 else m['lo']
            return chosen
        for m in cands:
            m['lo'], m['hi'] = min(m['lo'], m['hi']), max(m['lo'], m['hi'])
            # eng-168j (audit): after a split / merge / trim the level price stays INSIDE the zone (a split kept the
            # old 'mid' beyond the cut, and targets use it)
            m['mid'] = min(max(m['mid'], m['lo']), m['hi'])
        above, below = ladder(1, 3), ladder(-1, 2)
        out = []
        for side, group in ((1, above[::-1]), (0, [cur] if cur else []), (-1, below)):
            for m in group:
                labels = sorted(m['labels'], key=_label_rank)
                out.append({'lo': m['lo'], 'hi': m['hi'], 'mid': m['mid'], 'side': side, 'strength': m['strength'],
                            'near': m.get('near', [])[:3], 'pierce_src': m.get('pierce_src'),
                            'conf_tf': conf_tf(m), 'tfs': m.get('tfs', []),
                            'tol': m['tol'],
                            'pad': m['pad'], 'label': ' · '.join(labels[:4]),
                            'desc': (m.get('sr_desc', '') + (f"; здесь же: {', '.join(describe(m['labels']).split(', ')[:2])}" if m['labels'] else '')
                                     + (f"; рядом: {', '.join(m.get('near', [])[:2])}" if m.get('near') else ''))
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
        pos = self.positioning_line(symbol)
        if pos:
            lines.append(pos)
        md_ = self.sc.market_data.get(symbol)
        lines += self.level_map(price, zones, self.session_bias(md_))
        for z in zones:
            tag = {1: '🔴 сопр.', 0: '🔵 цена в зоне', -1: '🟢 подд.'}[z['side']]
            lines.append(f"{tag} {_fmt(z['lo'])}–{_fmt(z['hi'])} [{z['strength']:.0f}] {z['label']}")
        tf = self.sc._tf_atrs(symbol)
        ath, days = self._history_high(md) if md else (None, 0)
        p = briefing_chart.plan(price, zones, tf.get('1d'), ath, days, atr_1h=tf.get('1h'))
        for side, name in (('long', 'Лонг'), ('short', 'Шорт')):
            sc = p[side]
            if sc:
                lines.append(f"{name}: {sc['cond']}; стоп {_fmt(sc['stop'])}; цели "
                             + ' / '.join(_fmt(t) for t in sc['targets']))
        if p.get('oco'):
            lines.append('Включение одного сценария у текущей зоны отменяет встречный')
        self.scenario[symbol] = {'long': p['long'], 'short': p['short'], 'price': price, 'ts': time.time()}
        return '\n'.join(lines)

    @staticmethod
    def light_src(symbol: str, price: float, h1: List, h4: List, d1: List, w1: List, fetched_at: Optional[float] = None):
        """A coin outside the universe, from REST candles only (rows [ts, o, h, l, c, ...]): the same shape key_zones /
        htf_bias read. No flows, liquidations or level map - the zones are the swing clusters of sr.zones alone."""
        import types
        md = types.SimpleNamespace(symbol=symbol, h1=h1, h4=h4, d1=d1, w1=w1, last_price=price, minute_klines=[])
        now = time.time() * 1000
        tf: Dict[str, float] = {}
        for k, rows, period in (('1h', h1, 3_600_000), ('4h', h4, 14_400_000), ('1d', d1, 86_400_000)):
            closed = [r for r in rows[-200:] if r[0] + period <= now]
            if len(closed) >= 15:
                from levels import atr_of
                tf[k] = atr_of(closed)                       # Wilder's ATR14, the bot's one ATR
        return md, {'price': price, 'levels': [], 'tf': tf, 'md': md, 'fetched_at': fetched_at}

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
        p = briefing_chart.plan(price, zones, atr1d, ath, days, atr_1h=atr1h)
        events = macro_today(datetime.now(MSK))
        d1c = [c for c in md.d1 if c[0] + 86_400_000 <= time.time() * 1000]       # closed days only (REST rows hold today's)
        now_ms = time.time() * 1000
        h1c = [c for c in md.h1 if c[0] + HOUR_MS <= now_ms]
        notices = []
        if src is not None:
            # eng-168o (audit #4): a coin outside the universe is a LIMITED analysis - REST candles only, no level map,
            # no flow, pierce statistics of a liquidity group, no bot cards possible
            notices.append('Ограниченный анализ: только свечи Binance (нет карты уровней, потоков и своей статистики '
                           'проколов); монета вне контура сигналов бота')
        if bias is None and len([c for c in md.d1 if c[0] + 86_400_000 <= now_ms]) < 60:
            notices.append('Старший фон: недостаточно истории (нужно 60 закрытых дней)')
        out = {'symbol': symbol, 'base': _short(symbol), 'price': price, 'light': src is not None,
               'scope': 'limited' if src is not None else 'full', 'notices': notices,
               'data_as_of': {'last_closed_1h': int(h1c[-1][0] + HOUR_MS) if h1c else None,
                              'source': 'binance_rest' if src is not None else 'memory', 'generated_at': int(now_ms),
                              # eng-168q (audit #5): when the data set was actually fetched (REST rows come from a 5-min
                              # cache) and what the price is (the forming 1h candle's last close at that time)
                              'fetched_at': (src or {}).get('fetched_at'),
                              'price_src': 'close of the forming 1h at fetch' if src is not None else 'live last price'},
               'chg_day': (price / d1c[-1][4] - 1) * 100 if d1c else None,
               'bias': bias, 'bias_ru': BIAS_RU.get(bias, bias), 'bias_line': self._bias_line(symbol, bias, st),
               'atr1h': atr1h, 'atr1d': atr1d,
               'zones': [{k: z.get(k) for k in ('lo', 'hi', 'side', 'strength', 'label', 'near', 'pierce_src', 'conf_tf')}
                         for z in zones],
               # eng-168y: the if-then level map with its base view and the crowd (universe coins only)
               'level_map': self.level_map(price, zones, self.session_bias(md)),
               'positioning': self.positioning_line(symbol) if src is None else None,
               'macro': [f"{dt:%H:%M} {name}" for dt, name in events], 'scenarios': {}, 'cards': cards or []}
        if src is None:
            out['outcomes'] = self.outcomes(symbol, 14, md)
        for side, d, name in (('long', 1, 'Лонг'), ('short', -1, 'Шорт')):
            sc = p.get(side)
            if not sc:
                out['scenarios'][side] = None
                continue
            e = sum(sc['entry']) / 2
            # eng-168j (audit): R:R from the WORST price of the entry range (the far one for the trade), not its middle
            worst = max(sc['entry']) if d > 0 else min(sc['entry'])
            risk, reward = abs(worst - sc['stop']), d * (sc['targets'][0] - worst)
            rr = max(reward, 0.0) / risk if risk else 0.0
            dist = abs(e - price) / atr1h if atr1h else None
            checks = []
            aligned = bias in ('bull', 'bear') and ((bias == 'bull') == (d == 1))
            against = bias in ('bull', 'bear') and not aligned
            checks.append(('Старший ТФ', 'ok' if aligned else 'bad' if against else 'warn',
                           BIAS_RU.get(bias, bias) if bias is not None else 'недостаточно данных'))
            sb = self.session_bias(md)
            if sb is not None:
                # eng-168l: the fast background against the scenario is a warning (a counter-move inside the weekly tide)
                checks.append(('Импульс 1–3 дн.', 'ok' if sb == d else 'warn',
                               {1: 'рост', -1: 'падение', 0: 'нейтрально'}[sb]))
            checks.append(('R:R до TP1', 'ok' if rr >= 2 else 'warn' if rr >= 1 else 'bad', f"{rr:.1f}"))
            if dist is not None:
                checks.append(('Вход от цены', 'ok' if dist <= 1.5 else 'warn' if dist <= 4 else 'bad',
                               f"{dist:.1f} ATR(1h)"))
            if events:
                checks.append(('Макро сегодня', 'warn', ', '.join(n for _, n in events)[:80]))
            import macro_calendar
            if not macro_calendar.live_ok(time.time() * 1000):
                checks.append(('Макро-календарь', 'bad', 'не загружен / устарел - новые входы бота на паузе'))
            mine = [c for c in (cards or []) if c.get('direction') == d]
            against_cards = [c for c in (cards or []) if c.get('direction') == -d]
            if mine:
                checks.append(('Карточки бота', 'ok', f"{len(mine)} по направлению"))
            if against_cards:
                checks.append(('Карточки бота', 'bad', f"{len(against_cards)} против"))
            bad = sum(1 for _, s, _ in checks if s == 'bad')
            warn = sum(1 for _, s, _ in checks if s == 'warn')
            verdict = 'нет' if bad else 'осторожно' if warn >= 2 else 'формальные условия выполнены' if warn == 0 else 'приемлемо'
            if src is not None:
                verdict = f"ограниченный анализ: {verdict}"
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
        import macro_calendar
        why = macro_calendar.coverage(time.time() * 1000)
        if why:
            # eng-168q (audit #5): the calendar's degraded state is said where the user reads the macro line
            out.append(f"⚠️ Макро-календарь неполон ({why}): новые события могут отсутствовать"
                       + ("; новые входы бота на паузе до обновления" if not macro_calendar.live_ok(time.time() * 1000) else ''))
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
                                            ath=ath, ath_days=ath_days, hi24=hi24, lo24=lo24)
                pos = self.positioning_line(symbol)
                cap = f"<b>{_short(symbol)}</b> · {bias_line}" + (f"\n{pos}" if pos else '')
                lm = self.level_map(price, self.zones.get(symbol) or [], self.session_bias(md))
                if lm:
                    cap += '\n' + '\n'.join(lm)
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
                f.write(json.dumps({'slot': slot, 'title': title, 'ts': time.time(), 'symbol': symbol, 'rules_v': self.RULES_V,
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
                    p = briefing_chart.plan(price, zones, self.sc._tf_atrs(symbol).get('1d'), ath, days,
                                            atr_1h=self.sc._tf_atrs(symbol).get('1h'))
                except Exception as e:
                    errors.report('briefing._save', e, f"Silent briefing record failed for {symbol}")
                    continue
                f.write(json.dumps({'slot': slot, 'title': title, 'ts': time.time(), 'symbol': symbol, 'silent': True, 'rules_v': self.RULES_V,
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
                coins[base] = {**o['tally'], 'r': o.get('r') or {}, 'exec': o.get('exec') or {}}
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
        return cls.score_detail(sc, side, bars)[0]

    @classmethod
    def entry_ms(cls, sc: Dict, side: int, bars: List) -> Optional[float]:
        # eng-168n: the close time of the reaction candle that entered the scenario (None = not entered)
        return cls.score_detail(sc, side, bars)[3]

    @classmethod
    def score_detail(cls, sc: Dict, side: int, bars: List,
                     cancel_at: Optional[float] = None) -> Tuple[str, Optional[float], Optional[float], Optional[float]]:
        # eng-168n: 4th value = the entry candle's close time; cancel_at (OCO) = the opposite scenario of the same
        # zone entered at that time - not entered by then = cancelled
        """score_scenario's (text, resolved_ms, r). eng-168m: resolved_ms = the close of the candle that ended it (TP1 /
        stop / cancelled / missed), None while undecided; r = the result in R (TP1 R, -1), and for an entered scenario
        still undecided the mark-to-market R at the last candle's close (an 'expired open' trade is not dropped)."""
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
        fill, fill_ms = None, None
        touched = False
        step = H4_MS if len(bars) > 1 and bars[1][0] - bars[0][0] >= H4_MS else HOUR_MS
        for c in bars:
            end = c[0] + step
            if cancel_at is not None and fill is None and end >= cancel_at:
                return 'отменён: включился встречный сценарий', cancel_at, None, None
            if not armed:
                if (side > 0 and c[4] > e0) or (side < 0 and c[4] < e1):
                    armed = True
                continue
            if fill is None:
                touched = touched or (c[3] <= e1 and c[2] >= e0)
                if side * (c[4] - stop) <= 0:
                    return 'отменён: закрытие за стопом до реакции', end, None, None
                if cls.reaction(sc, side, c):
                    fill, fill_ms = c[4], end
                    if side * (tp1 - fill) <= 0:
                        # audit C15: the reaction closed at / beyond TP1 - no trade with a target ahead
                        return 'пропущен: реакция закрылась за TP1', end, None, None
                    if side * (tp1 - fill) < abs(fill - stop):
                        # eng-168l (audit #3): a reaction candle that closed most of the way to TP1 leaves R:R < 1
                        # from its close - the publication rule (R:R >= 1) applies to the real entry too
                        return 'пропущен: реакция закрылась слишком далеко (R:R < 1)', end, None, None
                continue
            if (c[3] <= stop) if side > 0 else (c[2] >= stop):
                return 'вход → стоп (−1R)', end, -1.0, fill_ms
            if (c[2] >= tp1) if side > 0 else (c[3] <= tp1):
                r = side * (tp1 - fill) / abs(fill - stop)
                return f"вход → TP1 ({r:+.1f}R)", end, round(r, 2), fill_ms
        if fill is not None:
            mtm = side * (bars[-1][4] - fill) / abs(fill - stop) if abs(fill - stop) > 0 else 0.0
            return 'вход, без исхода', None, round(mtm, 2), fill_ms
        if armed and breakout and not touched:
            far = max(c[2] for c in bars) if side > 0 else min(c[3] for c in bars)
            reached = (far >= tp1) if side > 0 else (far <= tp1)
            return 'закрепление без ретеста' + (' — цена дошла до TP1 без входа' if reached else ''), None, None, None
        return ('тест без реакции' if touched else 'не включился'), None, None, None

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
            res, ambiguous = self._score_record(r, closed, minutes, fetch_minutes=True)
            if res:
                out.append(f"· {r['slot'][-5:]} {r['title'].replace('Сводка ', '')}: "
                           + '; '.join(f"{name} — {self.human_outcome(txt, rv)}" for name, txt, _t, _res, rv, *_ in res)
                           + (' (час публикации не оценён)' if ambiguous else ''))
        return out

    def _resolved_today(self, symbol: str, md, day0: int) -> List[str]:
        """eng-168m (audit #3): the published scenarios of the previous days (within OUTCOME_HOURS) whose outcome came
        TODAY (MSK): TP1 / stop / cancelled / missed on a candle closed today, or the horizon ended today with the trade
        still open (marked to market). The recap scored only today's posts."""
        import json
        try:
            with open(os.path.join('data', 'briefings.jsonl'), encoding='utf-8') as f:
                recs = [json.loads(x) for x in f if x.strip()]
        except (OSError, ValueError):
            return []
        now = time.time() * 1000
        today = f"{datetime.now(MSK):%Y-%m-%d}"
        closed = [c for c in md.h1 if c[0] + HOUR_MS <= now]
        minutes = [c for c in md.minute_klines if c[0] + 60_000 <= now]
        out = []
        for r in recs:
            if r.get('symbol') != symbol or r.get('silent') or r.get('rules_v') != self.RULES_V \
                    or str(r.get('slot', '')).startswith(today):
                continue
            until = r['ts'] * 1000 + self.OUTCOME_HOURS * HOUR_MS
            if until < day0:
                continue
            res, _ = self._score_record(r, closed, minutes, until_ms=until, fetch_minutes=True)
            done = []
            for name, txt, _tag, resolved, rv, _det in res:
                if resolved is not None and resolved >= day0:
                    done.append(f"{name} — {self.human_outcome(txt, rv)}")
                elif resolved is None and txt.startswith('вход, без исхода') and day0 <= until <= now:
                    done.append(f"{name}: истёк открытым ({rv:+.2f}R по рынку)")
            if done:
                out.append(f"· завершились сегодня — {r['title']} {r['slot'][5:]}: " + '; '.join(done))
        return out

    EXEC_MODEL = 'execution_model_v1'

    @staticmethod
    def exec_detail(sc: Dict, side: int, fill: float, after: List) -> Dict:
        """eng-168r (audit #6): two measures of an ENTERED scenario, kept apart.
        Scenario (the forecast): whether TP1 / TP2 / the stop traded after the entry, MFE / MAE in R of price from the
        entry, hours to the first of TP1 / stop. Execution (execution_model_v1, the bot's own rule): 50% out at +1R,
        the rest's stop to break-even + costs, the rest out at TP2 (TP1 when there is no TP2 beyond +1R) or that stop;
        costs = journal.fee_round_trip + 2 x levels.slippage_bps (base) on the whole position, funding NOT included. One 1h candle
        touching a stop and a target: the order is unknown - the stop is taken (conservative) and the outcome is marked
        ambiguous. Undecided at the end of `after` (the 72h horizon): marked to market at the last close."""
        stop, tps = sc['stop'], list(sc['targets'])
        risk = abs(fill - stop)
        out = {'model': Briefing.EXEC_MODEL, 'tp1_hit': False, 'tp2_hit': False, 'stop_hit': False,
               'mfe_r': 0.0, 'mae_r': 0.0, 'hours': None, 'exec_r': None, 'ambiguous': False, 'resolved': False}
        if not risk or not after:
            return out
        cost_frac = CONFIG.journal.fee_round_trip + 2 * CONFIG.levels.slippage_bps / 1e4
        cost_r = cost_frac * fill / risk
        part = fill + side * risk                                    # +1R
        rest_t = next((t for t in tps[1:] if side * (t - part) > 0), tps[0])
        if side * (rest_t - part) < 0:
            rest_t = part
        be = fill + side * cost_frac * fill
        tp1, tp2 = tps[0], (tps[1] if len(tps) > 1 else None)
        partial = False
        t0 = after[0][0]
        for c in after:
            hi_r, lo_r = side * ((c[2] if side > 0 else c[3]) - fill) / risk, side * ((c[3] if side > 0 else c[2]) - fill) / risk
            out['mfe_r'], out['mae_r'] = max(out['mfe_r'], hi_r), min(out['mae_r'], lo_r)
            fav = c[2] if side > 0 else c[3]
            adv = c[3] if side > 0 else c[2]
            stop_now = side * (adv - stop) <= 0
            # eng-168u: the forecast counts the FIRST of TP1 / stop only (TP1 after the stop was counted as a hit too)
            if side * (fav - tp1) >= 0 and not out['tp1_hit'] and not out['stop_hit'] and not stop_now:
                out['tp1_hit'] = True
                out['hours'] = out['hours'] or round((c[0] + HOUR_MS - t0) / HOUR_MS, 1)
            if tp2 is not None and side * (fav - tp2) >= 0 and out['tp1_hit']:
                out['tp2_hit'] = True
            if stop_now and not out['tp1_hit'] and not out['stop_hit']:
                out['stop_hit'] = True
                out['hours'] = out['hours'] or round((c[0] + HOUR_MS - t0) / HOUR_MS, 1)
            if out['resolved']:
                continue
            if not partial:
                hit_part = side * (fav - part) >= 0
                if stop_now:
                    out['ambiguous'] = out['ambiguous'] or hit_part
                    out['exec_r'], out['resolved'] = -1.0 - cost_r, True
                    continue
                if hit_part:
                    partial = True
                    if side * (fav - rest_t) >= 0:
                        out['exec_r'], out['resolved'] = 0.5 + 0.5 * side * (rest_t - fill) / risk - cost_r, True
                        continue
                    if side * (adv - be) <= 0:                     # back to break-even inside the same candle
                        out['ambiguous'] = True
                        out['exec_r'], out['resolved'] = 0.5 + 0.5 * side * (be - fill) / risk - cost_r, True
                    continue
            else:
                hit_be, hit_t = side * (adv - be) <= 0, side * (fav - rest_t) >= 0
                if hit_be:
                    out['ambiguous'] = out['ambiguous'] or hit_t
                    out['exec_r'], out['resolved'] = 0.5 + 0.5 * side * (be - fill) / risk - cost_r, True
                elif hit_t:
                    out['exec_r'], out['resolved'] = 0.5 + 0.5 * side * (rest_t - fill) / risk - cost_r, True
        if not out['resolved']:
            mtm = side * (after[-1][4] - fill) / risk
            out['exec_r'] = (0.5 + 0.5 * mtm if partial else mtm) - cost_r
        out['mfe_r'], out['mae_r'] = round(out['mfe_r'], 2), round(out['mae_r'], 2)
        out['exec_r'] = round(out['exec_r'], 2)
        return out

    @classmethod
    def sweep_variant(cls, sc: Dict, side: int, bars: List) -> Optional[Dict]:
        """eng-168w / eng-169 (audit #10, the ICT liquidity sweep as defined there), a SHADOW entry measured beside the
        scenario's own - nothing is posted or traded on it. The pool is the scenario zone's FAR edge (a cluster of swing
        extremes / a map level: resting stops beyond it). A closed 1h candle:
          - trades beyond that edge by 0.05..0.8 ATR(1h) (deeper = a run, not a sweep);
          - closes back beyond the zone's MIDDLE (displacement), with the rejecting wick >= 40% of its range;
        entry at its close, stop beyond its extreme by max(0.25 ATR(1h), 0.25 x its range), the scenario's targets,
        R:R >= 1 from the close. Old records without the zone / ATR fall back to the entry range and its width.
        Scored with exec_detail (execution_model_v1). None = no such candle within the bars."""
        e0, e1 = sorted(sc['entry'])
        lo, hi = sc.get('zone') or (e0, e1)
        atr = sc.get('atr1h') or (e1 - e0) or None
        if not atr:
            return None
        far, mid = (lo if side > 0 else hi), (lo + hi) / 2
        tp1 = sc['targets'][0]
        for k, c in enumerate(bars):
            rng = max(c[2] - c[3], 1e-12)
            if side > 0:
                depth, wick = far - c[3], min(c[1], c[4]) - c[3]
                ok = 0.05 * atr <= depth <= 0.8 * atr and c[4] > mid and wick / rng >= 0.4
                stop = c[3] - max(0.25 * atr, 0.25 * rng)
            else:
                depth, wick = c[2] - far, c[2] - max(c[1], c[4])
                ok = 0.05 * atr <= depth <= 0.8 * atr and c[4] < mid and wick / rng >= 0.4
                stop = c[2] + max(0.25 * atr, 0.25 * rng)
            if not ok:
                continue
            fill = c[4]
            risk = abs(fill - stop)
            if not risk or side * (tp1 - fill) < risk:
                return {'skipped': 'R:R < 1 from the reclaim close'}
            det = cls.exec_detail(dict(sc, stop=stop), side, fill, bars[k + 1:])
            det.update(entry_ms=c[0] + HOUR_MS, stop=stop, fill=fill)
            return det
        return None

    _MIN_CACHE: Dict = {}

    def _post_minutes(self, symbol: str, post_ms: float, first_full: int) -> List:
        """eng-168y: the 1m candles of the post's hour after the post, from Binance REST when the bot's ~10h minute
        ring no longer holds them (the recap at 23:30 scored the 02:30 / 09:30 posts without their hour). Cached."""
        key = (symbol, int(post_ms) // 60_000)
        if key not in self._MIN_CACHE:
            import json
            import urllib.request
            out = []
            try:
                b = symbol.split('/')[0] + 'USDT'
                url = (f"https://fapi.binance.com/fapi/v1/klines?symbol={b}&interval=1m"
                       f"&startTime={int(post_ms) // 60_000 * 60_000}&endTime={first_full - 1}&limit=61")
                with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'edgehunter-bot/1.0'}),
                                            timeout=15) as resp:
                    out = [[float(x) for x in k[:5]] for k in json.loads(resp.read())]
            except Exception as e:
                errors.report('briefing.post_minutes', e, symbol)
            if len(self._MIN_CACHE) > 2000:
                self._MIN_CACHE.clear()
            self._MIN_CACHE[key] = out
        return [c for c in self._MIN_CACHE[key] if post_ms <= c[0] < first_full and c[0] + 60_000 <= time.time() * 1000]

    def _score_record(self, r: Dict, closed: List, minutes: List, until_ms: Optional[float] = None,
                      fetch_minutes: bool = False):
        """One saved briefing record against the closed 1h candles after its post: ([(name, result, tag)], ambiguous).
        audit N22: only prices AFTER the post. The hour holding the post is scored on its 1m candles after the post's
        minute; without them that hour is left out and said so (its OHLC may be before the post)."""
        sc = r.get('scenario') or {}
        post_ms = r['ts'] * 1000
        first_full = (int(post_ms) // HOUR_MS + 1) * HOUR_MS
        head = [c for c in minutes if post_ms <= c[0] < first_full]
        if not head and post_ms % HOUR_MS and fetch_minutes and r.get('symbol'):
            head = self._post_minutes(r['symbol'], post_ms, first_full)
        ambiguous = not head and post_ms % HOUR_MS != 0
        # the post-hour's minutes after the post as ONE partial 1h bar (the reaction rule reads 1h candle shapes)
        # eng-168o (audit #4): the partial bar carries the HOUR's open time (its end = that hour's close); it carried
        # the first minute's time, so its close time / an entry on it read up to an hour late
        part = [[first_full - HOUR_MS, head[0][1], max(c[2] for c in head), min(c[3] for c in head), head[-1][4]]] \
            if head and head[-1][0] + 60_000 >= first_full else []
        bars = part + [c for c in closed if c[0] >= first_full and (until_ms is None or c[0] < until_ms)]
        res = []
        bars4 = to_4h(bars)
        tfb = lambda x: bars4 if (x or {}).get('conf_tf') == '4h' else bars     # eng-168y: the scenario's candle
        # eng-168n (OCO): the long and short tied to the same current zone cancel each other - the one entered first
        # cancels the other unless that one had already entered
        cancel = {}
        lg, sh = sc.get('long'), sc.get('short')
        if lg and sh and lg.get('cur_bound') and sh.get('cur_bound'):
            tl, tsh = self.entry_ms(lg, 1, tfb(lg)), self.entry_ms(sh, -1, tfb(sh))
            if tl is not None and (tsh is None or tsh > tl):
                cancel['short'] = tl
            elif tsh is not None and (tl is None or tl > tsh):
                cancel['long'] = tsh
        for key, side, name in (('long', 1, 'лонг'), ('short', -1, 'шорт')):
            if sc.get(key):
                sb_ = tfb(sc[key])
                txt, resolved, rv, entry = self.score_detail(sc[key], side, sb_, cancel_at=cancel.get(key))
                det = None
                if entry is not None:
                    # the entry is the reaction candle's close: the trade lives on the 1h candles after it
                    step = H4_MS if sb_ is bars4 else HOUR_MS
                    fill = next((c[4] for c in sb_ if c[0] + step == entry), None)
                    after = [c for c in bars if c[0] >= entry]
                    if fill is not None:
                        det = self.exec_detail(sc[key], side, fill, after)
                sw = self.sweep_variant(sc[key], side, bars)
                if det is not None or sw:
                    det = dict(det or {}, sweep=sw)
                res.append((name, txt, sc[key].get('tag', ''), resolved, rv, det))
        return res, ambiguous

    @staticmethod
    def human_outcome(txt: str, r: Optional[float] = None) -> str:
        """eng-168y: the scorer's status in words for the recap."""
        if txt.startswith('вход → TP1'):
            return f"вошли, цель 1 взята ({r:+.1f}R)" if r is not None else 'вошли, цель 1 взята'
        if txt.startswith('вход → стоп'):
            return 'вошли, стоп (−1R)'
        if txt.startswith('вход, без исхода'):
            return 'вошли, в работе' + (f" ({r:+.2f}R по рынку)" if r is not None else '')
        if txt.startswith('отменён: включился встречный'):
            return 'отменён: сработал встречный сценарий'
        if txt.startswith('отменён'):
            return 'отменён: закрытие за стопом до входа'
        if 'слишком далеко' in txt:
            return 'пропущен: свеча входа закрылась почти у цели'
        if txt.startswith('пропущен'):
            return 'пропущен: свеча входа закрылась за целью'
        if txt.startswith('закрепление без ретеста'):
            return 'пробой без возврата к уровню' + (' (цена дошла до цели без входа)' if 'TP1' in txt else '')
        if txt.startswith('тест без реакции'):
            return 'цена дошла до зоны, разворотной свечи не было'
        return 'условие не наступило'

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

    OUTCOME_HOURS = 72
    # eng-168l (audit #3): the version of the briefing rules (zones / plan / scoring) in every saved record; the tally
    # counts only the current one (records of older rules are not mixed in). Bump on any change to sr.py, plan() or
    # score_scenario().
    RULES_V = 'b169a'

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
        r_sum: Dict[str, float] = {}
        ex: Dict[str, Dict] = {}
        for r in recs:
            sym = r.get('symbol')
            if r.get('ts', 0) < since or (symbol and sym != symbol) or r.get('rules_v') != self.RULES_V:
                continue
            m = md if (md is not None and sym == symbol) else self.sc.market_data.get(sym)
            if m is None:
                continue
            closed = [c for c in m.h1 if c[0] + HOUR_MS <= now]
            minutes = [c for c in list(getattr(m, 'minute_klines', []) or []) if c[0] + 60_000 <= now]
            # eng-168k (audit): a fixed horizon after the post (OUTCOME_HOURS), not the end of its MSK day - a target
            # 2-3 ATR away was cut at midnight; unresolved at the horizon = 'expired', not 'open'. Silent records (the
            # pinned coins not posted) are a separate shadow tally ('<side> (тихие)'), not mixed with the posted ones
            until = r['ts'] * 1000 + self.OUTCOME_HOURS * HOUR_MS
            res, _ = self._score_record(r, closed, minutes, until_ms=until)
            for name, txt, _tag, _resolved, rdet, det in res:
                cls = self._outcome_class(txt)
                rv = self._outcome_r(txt)
                if cls == 'open' and now >= until:
                    # eng-168m: entered and undecided at the horizon - 'expired_open', marked to market in R
                    cls, rv = 'expired_open', rdet
                if r.get('silent'):
                    name = f"{name} (тихие)"
                if ((r.get('scenario') or {}).get('long' if name.startswith('лонг') else 'short') or {}).get('rr_ok') is False:
                    name = f"{name} (R:R<1)"               # eng-168x: analysis-only scenarios tallied apart
                tally.setdefault(name, {}).setdefault(cls, 0)
                tally[name][cls] += 1
                # eng-168j (audit): the result in R, not only counts (TP1: its R from the reaction close; stop: -1)
                if rv is not None:
                    r_sum[name] = round(r_sum.get(name, 0.0) + rv, 2)
                sw = (det or {}).get('sweep')
                if sw and sw.get('exec_r') is not None:
                    # eng-168w: the shadow sweep-and-reclaim entry, its own tally beside the scenario's entry
                    w = ex.setdefault(name + ' · вынос', {'model': self.EXEC_MODEL, 'n': 0, 'exec_r': 0.0,
                                                           'exec_mtm_r': 0.0, 'tp1': 0, 'tp2': 0, 'stop': 0,
                                                           'mfe_r': 0.0, 'mae_r': 0.0, 'ambiguous': 0, 'unresolved': 0})
                    w['n'] += 1
                    w['exec_r' if sw['resolved'] else 'exec_mtm_r'] = round(
                        w['exec_r' if sw['resolved'] else 'exec_mtm_r'] + sw['exec_r'], 2)
                    w['tp1'] += sw['tp1_hit']; w['tp2'] += sw['tp2_hit']; w['stop'] += sw['stop_hit']
                    w['mfe_r'] = round(w['mfe_r'] + sw['mfe_r'], 2); w['mae_r'] = round(w['mae_r'] + sw['mae_r'], 2)
                    w['ambiguous'] += sw['ambiguous']; w['unresolved'] += not sw['resolved']
                if det is not None and 'exec_r' in det:
                    # eng-168r: the forecast's measures and the execution model's R, apart from the TP1-only 'r'
                    e = ex.setdefault(name, {'model': self.EXEC_MODEL, 'n': 0, 'exec_r': 0.0, 'exec_mtm_r': 0.0,
                                             'tp1': 0, 'tp2': 0, 'stop': 0, 'mfe_r': 0.0, 'mae_r': 0.0,
                                             'ambiguous': 0, 'unresolved': 0})
                    e['n'] += 1
                    # eng-168s (audit #6): realized R and the unrealized mark-to-market of undecided trades apart
                    key_r = 'exec_r' if det['resolved'] else 'exec_mtm_r'
                    e[key_r] = round(e[key_r] + det['exec_r'], 2)
                    e['tp1'] += det['tp1_hit']; e['tp2'] += det['tp2_hit']; e['stop'] += det['stop_hit']
                    e['mfe_r'] = round(e['mfe_r'] + det['mfe_r'], 2); e['mae_r'] = round(e['mae_r'] + det['mae_r'], 2)
                    e['ambiguous'] += det['ambiguous']; e['unresolved'] += not det['resolved']
        for e in ex.values():                     # sums -> means for the excursions
            e['mfe_r'] = round(e['mfe_r'] / e['n'], 2) if e['n'] else None
            e['mae_r'] = round(e['mae_r'] / e['n'], 2) if e['n'] else None
        return {'days': days, 'tally': tally, 'r': r_sum, 'exec': ex}

    @staticmethod
    def _outcome_r(txt: str) -> Optional[float]:
        import re
        if txt.startswith('вход → стоп'):
            return -1.0
        m = re.match(r'вход → TP1 \(([+-][0-9.]+)R\)', txt)
        return float(m.group(1)) if m else None

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
            # eng-168l (audit #3): the day's range from the closed 1h candles since 00:00 MSK plus the minutes after the
            # last of them (the ~10h minute ring alone missed Asia and the morning)
            now_ms = time.time() * 1000
            h1d = [c for c in md.h1 if c[0] >= day0 and c[0] + HOUR_MS <= now_ms]
            tail_from = h1d[-1][0] + HOUR_MS if h1d else day0
            today = h1d + [c for c in md.minute_klines if c[0] >= tail_from]
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
            lines += self._resolved_today(symbol, md, day0)
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
            h4_closed = to_4h(closed) if (closed[-1][0] + HOUR_MS) % H4_MS == 0 else []
            for z in zones:
                tf = z.get('conf_tf', '1h')
                # eng-168y: a 4h zone is judged on the 4h close (only when this 1h close ends a 4h candle)
                if tf == '4h':
                    if len(h4_closed) < 2:
                        continue
                    c, p = h4_closed[-1], h4_closed[-2]
                else:
                    c, p = closed[-1], closed[-2]
                lbl = f"{_fmt(z['lo'])}–{_fmt(z['hi'])}"
                msg = None
                if p[4] <= z['hi'] < c[4]:
                    msg = f"⬆️ {_short(symbol)}: закрепление {tf} выше зоны {lbl} (закрытие {_fmt(c[4])})"
                elif p[4] >= z['lo'] > c[4]:
                    msg = f"⬇️ {_short(symbol)}: закрепление {tf} ниже зоны {lbl} (закрытие {_fmt(c[4])})"
                elif c[2] > z['hi'] and c[4] < z['hi'] and p[4] < z['hi']:
                    msg = f"↩️ {_short(symbol)}: снятие верха {lbl} (хай {_fmt(c[2])}) и возврат под зону ({tf})"
                elif c[3] < z['lo'] and c[4] > z['lo'] and p[4] > z['lo']:
                    msg = f"↪️ {_short(symbol)}: снятие низа {lbl} (лой {_fmt(c[3])}) и возврат над зону ({tf})"
                if msg:
                    self._post(msg + f"\n{z.get('desc') or z['label']}" + self._scenario_note(symbol, c[4]),
                               key=f"lvl|{symbol}|{z['lo']:.8g}|{msg[:2]}", every_sec=4 * 3600)
            # the scenario's REACTION on this closed 1h candle (breakouts only after their 1h close beyond): the entry
            sc = self.scenario.get(symbol) or {}
            for key, side, name in (('long', 1, 'Лонг'), ('short', -1, 'Шорт')):
                x = sc.get(key)
                if not x:
                    continue
                if x.get('conf_tf') == '4h':
                    if len(h4_closed) < 2:
                        continue                         # eng-168y: a 4h scenario reacts on a 4h close only
                    c = h4_closed[-1]
                    since = [b for b in h4_closed if b[0] + H4_MS > (sc.get('ts') or 0) * 1000]
                else:
                    c = closed[-1]
                    since = [b for b in closed if b[0] >= (sc.get('ts') or 0) * 1000 - HOUR_MS + 1]
                e0, e1 = sorted(x['entry'])
                armed = not x['tag'].startswith('закрепление') or any(
                    (side > 0 and b[4] > e0) or (side < 0 and b[4] < e1) for b in since[:-1])
                # audit C15: the target must still be ahead of the reaction close (a signed reward, not abs)
                if x.get('cur_bound') and sc.get('oco_done') not in (None, key):
                    continue                     # eng-168n: the opposite scenario of this zone already entered
                import macro_calendar
                if not macro_calendar.live_ok(time.time() * 1000):
                    continue                     # eng-168s: fail-closed - no 'scenario on' without a fresh calendar
                if armed and self.reaction(x, side, c) and side * (c[4] - x['stop']) > 0 \
                        and (side * (x['targets'][0] - c[4]) >= abs(c[4] - x['stop'])            # eng-168l: R:R >= 1
                             or (x.get('rr_ok') is False and side * (x['targets'][0] - c[4]) > 0)):  # eng-168x
                    rr = side * (x['targets'][0] - c[4]) / abs(c[4] - x['stop'])
                    self._post(f"✅ {_short(symbol)}: реакция у зоны — {name.lower()}-сценарий включён"
                               + (" (как сделка невыгодно: цель ближе стопа)" if x.get('rr_ok') is False else '') + "\n"
                               f"Вход ~{_fmt(c[4])} (закрытие 1h) · стоп {_fmt(x['stop'])} · цели "
                               + ' / '.join(_fmt(t) for t in x['targets']) + f" · R:R {rr:.1f}",
                               key=f"react|{symbol}|{key}|{sc.get('ts')}", every_sec=24 * 3600)
                    if x.get('cur_bound'):
                        sc['oco_done'] = key

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
                       # eng-168l: the side is part of the key (a long flush then a short squeeze of the same types
                       # 12 minutes later is a new event, not a repeat)
                       key=f"anom|{symbol}|{'L' if liq_l >= liq_s else 'S'}|{'+' if evs[-1][2] >= evs[0][2] else '-'}|"
                           f"{'|'.join(sorted(set(e[1] for e in evs)))}", every_sec=1800)

    def _zone_note(self, symbol: str, lo: float, hi: float) -> str:
        """Which briefing zone the events happened at, within its tolerance."""
        for z in self.zones.get(symbol) or []:
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
            # eng-168l (audit #3): a scenario already resolved since its post (TP1 / stop / cancelled / missed) is
            # reported as such, not as still waiting
            md = self.sc.market_data.get(symbol)
            if md is not None and sc.get('ts'):
                now_ms = time.time() * 1000
                bars = [c for c in md.h1 if c[0] >= int(sc['ts'] * 1000) // HOUR_MS * HOUR_MS + HOUR_MS
                        and c[0] + HOUR_MS <= now_ms]
                res = self.score_scenario(x, side, bars)
                if res.startswith(('вход →', 'отменён', 'пропущен')):
                    notes.append(f"{name}-сценарий уже завершён: {res}")
                    continue
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
        failed = errors.alert_text()      # its own accumulator: the Health line drains health_text() every minute
        if failed:
            self._post(f"🛠 Бот: ошибки компонентов за 15 мин — {failed}", key='health|errors', every_sec=3600, topic='service')
        blind = self.sc.blind_text()
        if blind:
            self._post(f"🛠 Бот: стратегии без истории, сигналов от них нет — {blind}. После рестарта история "
                       f"грузится около часа", key='health|blind', every_sec=3600, topic='service')
        rss = (getattr(self.sc, 'health', None) or {}).get('rss_mb')
        try:
            import psutil
            total_mb = psutil.virtual_memory().total / 2**20
        except Exception as e:
            errors.report('briefing.memory', e)
            total_mb = 0.0
        if rss and total_mb and rss > 0.55 * total_mb:
            self._post(f"🛠 Бот: память {rss:.0f} МБ из {total_mb:.0f} МБ — ядро может убить процесс (OOM), "
                       f"перезапуск сбросит рост", key='health|memory', every_sec=2 * 3600, topic='service')
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
        # eng-168i: off the event loop - the zones (sr.zones, ~1-2 s CPU a coin) and the XAU proxy history (a blocking
        # urllib request, 20 s timeout) blocked the scanner's loop 1.5-2.2 s at a time (watchdog, 24-25.10)
        def init_zones():
            for symbol in self.watched():
                try:
                    self.key_zones(symbol) and self.coin_text(symbol)
                except Exception as e:
                    errors.report('briefing.init', e, symbol)
        await asyncio.to_thread(init_zones)
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
                        self._save_slots()             # before sending: a crash mid-send never sends twice
                        if title == 'recap':
                            self.sc.notifier.post(await asyncio.to_thread(self.recap), 'briefing')
                            await asyncio.to_thread(self.snapshot_outcomes)
                        else:
                            for png, cap in await asyncio.to_thread(self.cards, title):
                                self.sc.notifier.post_photo(png, cap)
                            await asyncio.to_thread(self._save, slot, title)
                for dt, name in macro_today(now):
                    if timedelta(0) <= dt - now <= timedelta(minutes=30):
                        # eng-168k (audit): the text says what the trading guard really does - signal_book's
                        # macro_calendar.blackout: CPI / FOMC dates and the live calendar's High events, from
                        # levels.macro_before_min before to macro_after_min after (was '30 / 60, CPI and FOMC': wrong)
                        import macro_calendar
                        lv = CONFIG.levels
                        guard = (f"новые входы бота блокируются с {lv.macro_before_min} мин до по "
                                 f"{lv.macro_after_min} мин после" if macro_calendar.blackout(dt.timestamp() * 1000)
                                 else "входы бота этим событием не блокируются")
                        self._post(f"📅 Через {int((dt - now).total_seconds() // 60)} мин: {name} ({dt:%H:%M} МСК) — "
                                   f"{guard}",
                                   key=f"macro|{dt:%Y%m%d%H%M}", every_sec=86400, topic='briefing')
                await asyncio.to_thread(self.check_shock)        # eng-168i: every check off the event loop
                await asyncio.to_thread(self.check_demo)          # SQLite reads off the event loop
                await asyncio.to_thread(self.check_anomalies)
                if tick % 2 == 0:
                    await asyncio.to_thread(self.check_levels)    # key_zones / coin_text: sr.zones CPU
                if tick % 15 == 0:
                    await asyncio.to_thread(self.check_bias)
                    await asyncio.to_thread(self.check_health)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                errors.report('briefing.loop', e)
            tick += 1
            await asyncio.sleep(60)
