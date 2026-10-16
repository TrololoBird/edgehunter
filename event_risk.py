"""
Event risk from Binance's own public data (eng-53; Compass "7 phases" review: scheduled / announced events are the
best-documented driver of dumps):
- the Monitoring Tag (Binance's delisting watch list): the spot product list carries tags['Monitoring'] - live after
  a tag, AVA -4.9%, SCR -7.5%, NFP -12%, WAN -34% within minutes / an hour (BeInCrypto, cryptorank);
- a scheduled delisting of the perpetual: futures exchangeInfo sets the contract's deliveryDate to the removal time
  (an ordinary perpetual carries 2100-12-25) - after Binance's delisting announcement of 2026-04-09: FUN -27.9%,
  MDT -22.8%, FIO -20.5% within minutes.
eng-135: exchange announcements, keyless, polled every 2 minutes (the tags / exchangeInfo stay hourly):
- Binance CMS delisting catalogue (161): "Binance Will Delist A, B on <date>" = a spot delisting - longs vetoed until
  the day after it (a futures delisting shows in deliveryDate above; Alpha / Margin removals are not a coin delisting);
- Binance new listings (48): "Binance Will List X (X)" - journal only ('news');
- Upbit trade notices: "... KRW 마켓 디지털 자산 추가" a KRW listing (journal only: listing effects fade in 1-2 days,
  RockawayX / The TIE), "거래지원 종료" an Upbit delisting and "유의 종목 지정" its warning list - longs vetoed 14 days.
  Upbit tickers can name another coin than Binance's (KRW-EDGE != EDGEUSDT): a false veto only costs a card.
Token unlocks (Keyrock: 90% of 16,000+ unlocks pressure the price for 30 days) need an external calendar: no free one
(DefiLlama emissions answer 402, Tokenomist is a paid API). A failed read keeps the last known state.
"""
import calendar
import json
import logging
import re
import time
import urllib.request
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

PRODUCTS_URL = 'https://www.binance.com/bapi/asset/v2/public/asset-service/product/get-products?includeEtf=true'
FAPI_INFO_URL = 'https://fapi.binance.com/fapi/v1/exchangeInfo'
DELIVERY_HORIZON_MS = 90 * 86400 * 1000      # a perpetual delivering within 90 days is being delisted
BN_CMS_URL = 'https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=1&catalogId={}&pageNo=1&pageSize=20'
UPBIT_URL = 'https://api-manager.upbit.com/api/v1/announcements?os=web&page=1&per_page=20&category=trade'
NEWS_KEEP_SEC = 7 * 86400                    # announcements kept for the journal / page
UPBIT_RISK_SEC = 14 * 86400                  # an Upbit delisting / warning vetoes longs this long after the notice
_TICKER = re.compile(r'\b[A-Z0-9]{2,15}\b')
_PAREN = re.compile(r'\(([A-Z0-9]{2,15})\)')
_BN_DELIST = re.compile(r'^Binance Will Delist (.+?) on (\d{4}-\d\d-\d\d)')
_BN_LIST = re.compile(r'^Binance Will List (.+)')


def parse_binance(title: str, release_ms: int, known) -> List[Tuple[str, str, float, Optional[float]]]:
    """(base, kind, ts, risk_until) of one Binance CMS title; only bases of known perpetuals."""
    ts = release_ms / 1000
    m = _BN_DELIST.match(title)
    if m:
        try:
            until = calendar.timegm(time.strptime(m.group(2), '%Y-%m-%d')) + 86400
        except ValueError:
            return []
        return [(b, 'binance_delist', ts, until) for b in _TICKER.findall(m.group(1)) if b in known]
    m = _BN_LIST.match(title)
    if m and 'bStocks' not in title:
        bases = _PAREN.findall(m.group(1)) or _TICKER.findall(m.group(1))[:1]
        return [(b, 'binance_listing', ts, None) for b in bases if b in known]
    return []


def parse_upbit(title: str, listed_at: str, known) -> List[Tuple[str, str, float, Optional[float]]]:
    """Titles: "X(X) KRW 마켓 디지털 자산 추가", "... KRW, USDT 마켓 디지털 자산 추가", "신규 거래지원 안내 (KRW, BTC
    마켓)" = a KRW listing; "거래지원 종료" a delisting (vetoed until the removal date in "(11/16 15:00)" or 14 days,
    whichever is later); "유의 종목 지정" the warning list (14 days), "... 해제" lifts it ('upbit_unwarn', no risk)."""
    try:
        ts = calendar.timegm(time.strptime(listed_at[:19], '%Y-%m-%dT%H:%M:%S')) - 9 * 3600   # KST
    except ValueError:
        return []
    krw = 'KRW' in title and '마켓' in title
    if '거래지원 종료' in title:
        kind, until = 'upbit_delist', ts + UPBIT_RISK_SEC
        m = re.search(r'\((\d{1,2})/(\d{1,2})', title)
        if m:
            year = time.gmtime(ts).tm_year
            try:
                end = calendar.timegm((year, int(m.group(1)), int(m.group(2)), 0, 0, 0)) + 86400
                until = max(until, end if end > ts else end + 365 * 86400)
            except (ValueError, OverflowError):
                pass
    elif '유의 종목' in title and '해제' in title:
        kind, until = 'upbit_unwarn', None
    elif '유의 종목' in title and '지정' in title:
        kind, until = 'upbit_warning', ts + UPBIT_RISK_SEC
    elif krw and ('추가' in title or '신규 거래지원' in title):
        kind, until = 'upbit_listing', None
    else:
        return []
    return [(b, kind, ts, until) for b in _PAREN.findall(title) if b in known]


def _get(url: str):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


class EventRisk:
    def __init__(self):
        self.by_base: Dict[str, str] = {}        # base asset (BTC, PEPE ...) -> 'monitoring' / 'delisting <date>'
        self.updated = 0.0
        self.known: set = set()                  # base assets of Binance USDT perpetuals (from exchangeInfo)
        self.news: Dict[str, Tuple[str, float, Optional[float]]] = {}   # base -> (kind, ts, risk until) - the newest
        self.news_risk: Dict[str, Tuple[str, float, float]] = {}       # base -> (kind, ts, until) of an active veto
        self.news_updated = 0.0

    @staticmethod
    def _base(symbol: str) -> str:
        base = symbol.split('/')[0]
        for prefix in ('1000000', '10000', '1000', '1M'):
            if base.startswith(prefix) and len(base) > len(prefix):
                return base[len(prefix):]
        return base

    def refresh(self) -> None:
        """Blocking (run in a thread): both sources; each keeps its last state when its read fails."""
        found: Dict[str, str] = {}
        ok = 0
        try:
            for p in _get(PRODUCTS_URL).get('data') or []:
                if 'Monitoring' in (p.get('tags') or []) and p.get('b'):
                    found[p['b']] = 'monitoring'
            ok += 1
        except Exception as e:
            logger.info(f"Event risk: Binance product tags failed ({e!r}), kept the last state")
            found.update({b: r for b, r in self.by_base.items() if r == 'monitoring'})
        try:
            now = time.time() * 1000
            symbols = _get(FAPI_INFO_URL).get('symbols') or []
            self.known = {self._base(s['baseAsset']) for s in symbols if s.get('quoteAsset') == 'USDT'}
            for s in symbols:
                due = int(s.get('deliveryDate') or 0)
                if s.get('contractType') == 'PERPETUAL' and now < due < now + DELIVERY_HORIZON_MS:
                    day = time.strftime('%Y-%m-%d', time.gmtime(due / 1000))
                    found[self._base(s['baseAsset'])] = f'delisting {day}'
            ok += 1
        except Exception as e:
            logger.info(f"Event risk: futures exchangeInfo failed ({e!r}), kept the last state")
            found.update({b: r for b, r in self.by_base.items() if r.startswith('delisting')})
        self.by_base = found
        if ok:
            self.updated = time.time()
        logger.info(f"Event risk: {sum(1 for r in found.values() if r == 'monitoring')} coins with the Monitoring Tag, "
                    f"{sum(1 for r in found.values() if r.startswith('delisting'))} perpetuals being delisted")

    def refresh_news(self) -> None:
        """Blocking (run in a thread): Binance delisting / listing catalogues and Upbit trade notices."""
        if not self.known:
            return
        now, items = time.time(), []
        for cat in (161, 48):
            try:
                for c in (_get(BN_CMS_URL.format(cat)).get('data') or {}).get('catalogs') or []:
                    for a in c.get('articles') or []:
                        items += parse_binance(a.get('title') or '', int(a.get('releaseDate') or 0), self.known)
            except Exception as e:
                logger.info(f"Event risk: Binance announcements {cat} failed ({e!r})")
        try:
            for n in (_get(UPBIT_URL).get('data') or {}).get('notices') or []:
                items += parse_upbit(n.get('title') or '', n.get('first_listed_at') or n.get('listed_at') or '', self.known)
        except Exception as e:
            logger.info(f"Event risk: Upbit notices failed ({e!r})")
        news = {b: v for b, v in self.news.items() if now - v[1] < NEWS_KEEP_SEC}
        risk = {b: v for b, v in self.news_risk.items() if v[2] > now}
        fresh = []
        for base, kind, ts, until in sorted(items, key=lambda x: x[2]):
            if kind == 'upbit_unwarn' and base in risk and risk[base][0] == 'upbit_warning' and risk[base][1] <= ts:
                del risk[base]                   # Upbit lifted its warning
            if until and until > now and (base not in risk or risk[base][2] < until):
                risk[base] = (kind, ts, until)   # a later listing never overwrites a veto (kept apart)
            if now - ts >= NEWS_KEEP_SEC:
                continue
            if news.get(base, (None, 0.0, None))[:2] != (kind, ts):
                fresh.append(f"{base} {kind}")
            news[base] = (kind, ts, until)
        self.news, self.news_risk, self.news_updated = news, risk, now
        if fresh:
            logger.info(f"Event risk: announcements {', '.join(fresh[-12:])}")

    def of(self, symbol: str) -> Optional[str]:
        base = self._base(symbol)
        risk = self.by_base.get(base)
        if risk:
            return risk
        n = self.news_risk.get(base)
        return n[0] if n and n[2] > time.time() else None

    def news_of(self, symbol: str) -> Optional[Dict]:
        base, now = self._base(symbol), time.time()
        n = self.news.get(base)
        if not n or now - n[1] >= NEWS_KEEP_SEC:
            return None
        return {'kind': n[0], 'age_h': round((now - n[1]) / 3600, 2), 'risk': base in self.news_risk}

    def view(self) -> List[Dict]:
        """The page: every kept announcement, newest first."""
        now = time.time()
        return [{'base': b, 'kind': k, 'ts': ts, 'risk': b in self.news_risk and self.news_risk[b][2] > now}
                for b, (k, ts, _u) in sorted(self.news.items(), key=lambda x: -x[1][1]) if now - ts < NEWS_KEEP_SEC]
