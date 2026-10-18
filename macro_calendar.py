"""
Scheduled US macro releases that move crypto at a known minute (FOMC statement 14:00 New York, CPI 08:30 New York):
an entry from `before_min` before to `after_min` after a release is journaled with vetoed='macro_event' (the spread
widens, stops are run both ways in the first minutes; the event, not the setup, decides the move). The dates are
published a year ahead: FOMC (federalreserve.gov, 2026 schedule), CPI (bls.gov/schedule/news_release/cpi.htm).
Add the next year's dates when they are published; a date list that ran out simply vetoes nothing.
"""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from config import CONFIG

NY = ZoneInfo('America/New_York')

# (date, HH:MM New York, name)
EVENTS = (
    ('2026-10-14', '08:30', 'CPI'), ('2026-10-28', '14:00', 'FOMC'), ('2026-11-06', '08:30', 'NFP'),
    ('2026-11-10', '08:30', 'CPI'),
    ('2026-12-09', '14:00', 'FOMC'), ('2026-12-10', '08:30', 'CPI'),
)


def _ms(date: str, hm: str) -> int:
    y, m, d = map(int, date.split('-'))
    hh, mm = map(int, hm.split(':'))
    return int(datetime(y, m, d, hh, mm, tzinfo=NY).timestamp() * 1000)


TIMES = tuple((_ms(d, t), name) for d, t, name in EVENTS)


# eng-72: the week's calendar from ForexFactory (nfs.faireconomy.media/ff_calendar_thisweek.json, hourly, fetcher):
# [(ms, title, impact)] of USD events. High-impact ones join the blackout (the hand list above held CPI / FOMC only;
# NFP / ISM / PCE / GDP were missing, and their dates were guessed by rule in the briefing)
LIVE: list = []
LIVE_AT = 0.0                     # when the live rows were fetched (epoch seconds); 0 = never
LIVE_MAX_AGE_SEC = 6 * 3600.0     # audit B06: older than this the weekly source counts as lost


def set_live(rows, fetched_at: float = None) -> None:
    global LIVE, LIVE_AT
    out = []
    for r in rows or []:
        if r.get('country') != 'USD' or r.get('impact') not in ('High', 'Medium'):
            continue
        try:
            t = int(datetime.fromisoformat(r['date']).timestamp() * 1000)
        except (KeyError, ValueError):
            continue
        out.append((t, r.get('title') or '?', r['impact']))
    if out:
        LIVE = sorted(out)
        LIVE_AT = fetched_at or time.time()


def blackout(now_ms: float):
    """The release whose window `now_ms` falls in, else None."""
    cfg = CONFIG.levels
    for t, name in list(TIMES) + [(t, n) for t, n, imp in LIVE if imp == 'High']:
        if t - cfg.macro_before_min * 60_000 <= now_ms <= t + cfg.macro_after_min * 60_000:
            return name
    return None


def upcoming(now_ms: float, within_ms: float):
    """eng-100: (time, name) of the next high-impact release within `within_ms` from now, else None."""
    soon = [(t, n) for t, n in list(TIMES) + [(t, n) for t, n, imp in LIVE if imp == 'High'] if now_ms < t <= now_ms + within_ms]
    return min(soon) if soon else None


def coverage(now_ms: float):
    """Audit B06: why the macro veto may be blind right now, else None. The veto fails open (no source = no window), so
    the degraded state must at least be visible: the weekly feed lost / stale, or the hand list of CPI / FOMC / NFP
    already past its last date."""
    why = []
    if not LIVE_AT:
        why.append('weekly calendar never loaded')
    elif now_ms / 1000 - LIVE_AT > LIVE_MAX_AGE_SEC:
        why.append(f"weekly calendar stale {(now_ms / 1000 - LIVE_AT) / 3600:.0f}h")
    if TIMES and now_ms > max(t for t, _ in TIMES):
        why.append('hand list of releases ended')
    return '; '.join(why) or None
