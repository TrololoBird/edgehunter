"""Calendar observations for scheduled macro releases.

Official schedules identify expected publication times; they do not establish
the direction, size or execution consequences of a market move. A blackout
may be used as a reviewed risk policy, but a missing or stale calendar is an
unknown data state. New entries must fail closed when coverage is unknown;
open positions may be managed separately.
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
    # audit V09: NFP for November, BLS schedule (bls.gov/schedule/2026/12_sched_list.htm, checked 2026-10-18)
    ('2026-12-04', '08:30', 'NFP'),
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
    if rows is not None and not isinstance(rows, list):
        return                                   # not a calendar (an error body): keep the last good list
    out = []
    for r in rows or []:
        if r.get('country') != 'USD' or r.get('impact') not in ('High', 'Medium'):
            continue
        try:
            t = int(datetime.fromisoformat(r['date']).timestamp() * 1000)
        except (KeyError, ValueError):
            continue
        out.append((t, r.get('title') or '?', r['impact']))
    # eng-168q (audit #5): a successful load replaces the list even when it holds no USD High / Medium event (an
    # empty week kept the previous week's list as if current); a failed load never reaches here
    if rows is not None:
        LIVE = sorted(out)
        LIVE_AT = fetched_at or time.time()


def _sources():
    """eng-168t: every blocking release - the official schedules first (official_calendar), the hand list, the live
    week's High events. A release present in several sources blocks once in practice (same minute windows)."""
    import official_calendar
    return official_calendar.blocking_events() + list(TIMES) + [(t, n) for t, n, imp in LIVE if imp == 'High']


def blackout(now_ms: float):
    """The release whose window `now_ms` falls in, else None."""
    cfg = CONFIG.levels
    for t, name in _sources():
        if t - cfg.macro_before_min * 60_000 <= now_ms <= t + cfg.macro_after_min * 60_000:
            return name
    return None


def upcoming(now_ms: float, within_ms: float):
    """eng-100: (time, name) of the next high-impact release within `within_ms` from now, else None."""
    soon = [(t, n) for t, n in _sources() if now_ms < t <= now_ms + within_ms]
    return min(soon) if soon else None


def ff_fresh(now_ms: float) -> bool:
    return bool(LIVE_AT) and now_ms / 1000 - LIVE_AT <= LIVE_MAX_AGE_SEC


def live_ok(now_ms: float) -> bool:
    """eng-168s / eng-168t (audit #6, fail-closed): every blocking category (CPI, NFP, PPI, FOMC, ISM M / S) is
    covered - by its official schedule (fresh and reaching official_calendar.COVER_DAYS ahead) or, for the uncovered
    ones, by a fresh ForexFactory week. Otherwise a release may sit on a new entry unseen: new entries /
    recommendations wait; open positions are managed."""
    import official_calendar
    return not official_calendar.uncovered(now_ms) or ff_fresh(now_ms)


def coverage(now_ms: float):
    """Return why calendar coverage is incomplete, or ``None`` when complete.

    This describes the calendar data state. It is distinct from the policy
    that blocks new entries when ``live_ok`` is false; no event found in an
    unavailable calendar may be treated as proof that no event exists.
    """
    why = []
    import official_calendar
    off = official_calendar.status_text(now_ms)
    if off:
        why.append(f"official: {off}")
    if not LIVE_AT:
        why.append('weekly calendar never loaded')
    elif now_ms / 1000 - LIVE_AT > LIVE_MAX_AGE_SEC:
        why.append(f"weekly calendar stale {(now_ms / 1000 - LIVE_AT) / 3600:.0f}h")
    if TIMES and now_ms > max(t for t, _ in TIMES):
        why.append('hand list of releases ended')
    return '; '.join(why) or None
