"""
eng-168t (audit #6): the macro releases from their OFFICIAL schedules - the primary source of the entry blackout and of
the briefing's macro line; ForexFactory's weekly feed (macro_calendar.LIVE) stays the fallback / cross-check.

Sources (each fetched with a neutral User-Agent, cached in models/official_calendar.json):
- BLS iCalendar (https://www.bls.gov/schedule/news_release/bls.ics): CPI, Employment Situation (NFP), PPI; times in
  the feed's own zone (TZID=US-Eastern -> America/New_York);
- ISM release calendar (rob-report-calendar): the year's table of Manufacturing / Services PMI release days (holiday
  moves included), 10:00 a.m. ET;
- FOMC calendar (fomccalendars.htm): meeting dates; the policy statement at 2:00 p.m. ET on the meeting's last day and
  the press conference at 2:30 p.m. ET (two events, the statement is the blackout's anchor). Notation votes skipped.

Every event: {id, type, source, t (UTC ms), tz, title, status}. status 'scheduled' or 'unconfirmed' - an event a
previous fetch listed in the future and the new fetch no longer lists is KEPT as 'unconfirmed' (a partial response is
not a cancellation; a reschedule then blocks both times, the conservative side).

Coverage (completeness, not just reachability): a category is covered when its source was fetched successfully within
OFFICIAL_MAX_AGE_SEC AND that source's schedule reaches at least COVER_DAYS ahead (an empty / short schedule - ISM before
it posts next year's table - is NOT 'no events'). Uncovered categories fall back to the fresh ForexFactory week; with
neither, macro_calendar.live_ok() is False and new entries wait (fail-closed, eng-168s).
"""
import html
import json
import os
import re
import time
import urllib.request
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
UA = {'User-Agent': 'edgehunter-bot/1.0'}
CACHE = os.path.join('models', 'official_calendar.json')
OFFICIAL_MAX_AGE_SEC = 36 * 3600.0           # refreshed every 6h; a day and a half of failures = stale
COVER_DAYS = 7
BLOCKING = ('CPI', 'NFP', 'PPI', 'FOMC', 'ISM_M', 'ISM_S')          # FOMC_PC is inside the statement's window
CATEGORY_SOURCE = {'CPI': 'BLS', 'NFP': 'BLS', 'PPI': 'BLS', 'FOMC': 'FED', 'ISM_M': 'ISM', 'ISM_S': 'ISM'}
URLS = {'BLS': 'https://www.bls.gov/schedule/news_release/bls.ics',
        'ISM': 'https://www.ismworld.org/supply-management-news-and-reports/reports/rob-report-calendar/',
        'FED': 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'}
MONTHS = {m: i for i, m in enumerate(('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
                                      'September', 'October', 'November', 'December'), 1)}
MON3 = {k[:3]: v for k, v in MONTHS.items()}

STATE: Dict = {'events': [], 'sources': {}}     # sources: name -> {fetched_at, cover_end, n, error}


def _et(y: int, mo: int, d: int, h: int, mi: int) -> int:
    return int(datetime(y, mo, d, h, mi, tzinfo=NY).timestamp() * 1000)


def parse_bls(text: str) -> List[Dict]:
    t = text.replace('\r\n ', '').replace('\n ', '')
    out = []
    for e in re.findall(r'BEGIN:VEVENT(.*?)END:VEVENT', t, re.S):
        m = re.search(r'^DTSTART([^:]*):(\d{8})T(\d{4})', e, re.M)
        s = re.search(r'^SUMMARY[^:]*:(.*)$', e, re.M)
        if not m or not s:
            continue
        title = s.group(1).strip()
        typ = ('CPI' if title.startswith('Consumer Price Index') else
               'NFP' if title == 'Employment Situation' else
               'PPI' if title.startswith('Producer Price Index') else None)
        if typ is None:
            continue
        params, ymd, hm = m.groups()
        if 'TZID' in params and 'Eastern' not in params and 'New_York' not in params:
            continue                                  # an unexpected zone: not guessed
        y, mo, d, h, mi = int(ymd[:4]), int(ymd[4:6]), int(ymd[6:]), int(hm[:2]), int(hm[2:])
        out.append({'id': f"BLS:{typ}:{ymd}", 'type': typ, 'source': 'BLS', 't': _et(y, mo, d, h, mi),
                    'tz': 'America/New_York', 'title': title, 'status': 'scheduled'})
    return out


def parse_ism(text: str) -> List[Dict]:
    txt = html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', text)))
    out = []
    for mon, year, man, srv in re.findall(r'(January|February|March|April|May|June|July|August|September|October|'
                                          r'November|December) (\d{4}) (\d{1,2})\*{0,3} (\d{1,2})\*{0,3}', txt):
        y, mo = int(year), MONTHS[mon]
        for typ, d in (('ISM_M', int(man)), ('ISM_S', int(srv))):
            out.append({'id': f"ISM:{typ}:{y}{mo:02d}", 'type': typ, 'source': 'ISM', 't': _et(y, mo, d, 10, 0),
                        'tz': 'America/New_York', 'title': f"ISM {'Manufacturing' if typ == 'ISM_M' else 'Services'} PMI",
                        'status': 'scheduled'})
    return out


def parse_fed(text: str) -> List[Dict]:
    heads = [(m.start(), int(m.group(1))) for m in re.finditer(r'(\d{4}) FOMC Meetings', text)]
    out = []
    for m in re.finditer(r'fomc-meeting__month[^>]*>\s*<strong>([^<]+)</strong>.*?fomc-meeting__date[^>]*>([^<]+)<',
                         text, re.S):
        year = next((y for pos, y in sorted(heads, reverse=True) if pos < m.start()), None)
        mon_txt, date_txt = m.group(1).strip(), html.unescape(m.group(2)).strip()
        if year is None or 'notation' in date_txt.lower() or 'unscheduled' in date_txt.lower():
            continue
        days = re.findall(r'\d{1,2}', date_txt)
        months = [MON3.get(x[:3]) for x in re.split(r'[/-]', mon_txt)]
        if not days or not months or None in months:
            continue
        mo = months[-1]                              # 'Apr/May' '30-1': the last day falls in the second month
        d = int(days[-1])
        out.append({'id': f"FED:FOMC:{year}{mo:02d}{d:02d}", 'type': 'FOMC', 'source': 'FED',
                    't': _et(year, mo, d, 14, 0), 'tz': 'America/New_York', 'title': 'FOMC statement',
                    'status': 'scheduled'})
        out.append({'id': f"FED:FOMC_PC:{year}{mo:02d}{d:02d}", 'type': 'FOMC_PC', 'source': 'FED',
                    't': _et(year, mo, d, 14, 30), 'tz': 'America/New_York', 'title': 'FOMC press conference',
                    'status': 'scheduled'})
    return out


PARSERS = {'BLS': parse_bls, 'ISM': parse_ism, 'FED': parse_fed}


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', errors='replace')


def merge(old: List[Dict], new: List[Dict], source: str, now_ms: float) -> List[Dict]:
    """The new list of `source` replaces its old events; an old FUTURE event the new list lacks stays 'unconfirmed'."""
    ids = {e['id'] for e in new}
    kept = [dict(e, status='unconfirmed') for e in old
            if e['source'] == source and e['id'] not in ids and e['t'] > now_ms]
    others = [e for e in old if e['source'] != source]
    return sorted(others + new + kept, key=lambda e: e['t'])


def refresh(now: Optional[float] = None, fetch=_fetch) -> Dict:
    """Fetch every source; a source that fails or parses to nothing keeps its previous events and its old fetched_at
    (it ages into 'stale'). Returns the new STATE (also written to the cache)."""
    now = now or time.time()
    load()
    events, sources = list(STATE['events']), dict(STATE['sources'])
    for name, url in URLS.items():
        try:
            evs = PARSERS[name](fetch(url))
        except Exception as e:
            sources[name] = {**sources.get(name, {}), 'error': f"{type(e).__name__}: {e}"[:200]}
            continue
        if not evs:
            sources[name] = {**sources.get(name, {}), 'error': 'parsed no events (layout changed?)'}
            continue
        events = merge(events, evs, name, now * 1000)
        sources[name] = {'fetched_at': now, 'cover_end': max(e['t'] for e in evs), 'n': len(evs), 'error': None}
    STATE.update(events=events, sources=sources)
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        tmp = CACHE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(STATE, f)
        os.replace(tmp, CACHE)
    except OSError:
        pass
    return STATE


_loaded = False


def load() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        with open(CACHE, encoding='utf-8') as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get('events'), list):
            STATE.update(events=d['events'], sources=d.get('sources') or {})
    except (OSError, ValueError):
        pass


def covered(category: str, now_ms: float) -> bool:
    """The category's official source is fresh AND its schedule reaches COVER_DAYS ahead."""
    load()
    s = STATE['sources'].get(CATEGORY_SOURCE[category]) or {}
    fresh = s.get('fetched_at') and now_ms / 1000 - s['fetched_at'] <= OFFICIAL_MAX_AGE_SEC
    return bool(fresh and (s.get('cover_end') or 0) >= now_ms + COVER_DAYS * 86_400_000)


def uncovered(now_ms: float) -> List[str]:
    return [c for c in BLOCKING if not covered(c, now_ms)]


def blocking_events() -> List[Tuple[int, str]]:
    load()
    return [(e['t'], e['title'] + (' (не подтверждено)' if e['status'] == 'unconfirmed' else ''))
            for e in STATE['events'] if e['type'] in BLOCKING]


def all_events() -> List[Dict]:
    load()
    return list(STATE['events'])


def status_text(now_ms: float) -> Optional[str]:
    """Why the official schedule is incomplete now, else None."""
    load()
    why = []
    for name in URLS:
        s = STATE['sources'].get(name) or {}
        if not s.get('fetched_at'):
            why.append(f"{name}: не загружен" + (f" ({s['error']})" if s.get('error') else ''))
        elif now_ms / 1000 - s['fetched_at'] > OFFICIAL_MAX_AGE_SEC:
            why.append(f"{name}: устарел {(now_ms / 1000 - s['fetched_at']) / 3600:.0f}ч")
        elif (s.get('cover_end') or 0) < now_ms + COVER_DAYS * 86_400_000:
            why.append(f"{name}: расписание кончается раньше чем через {COVER_DAYS} дн.")
    return '; '.join(why) or None
