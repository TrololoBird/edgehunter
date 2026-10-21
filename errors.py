"""Visible failures: no exception handler may swallow an error or a missing input silently.

`report(source, exc, detail)` logs a WARNING for the first failure of a source and then at most once per
`WARN_EVERY_SEC` with the number of failures since (per-symbol REST failures would otherwise flood the log), and counts
every failure for the Health line (`health_text`).
"""
import logging
import threading
import time
from collections import Counter
from typing import Dict

logger = logging.getLogger('errors')

WARN_EVERY_SEC = 300.0

_lock = threading.Lock()
_minute: Counter = Counter()          # failures since the last Health line
_alert: Counter = Counter()           # failures since the last alert check (the Health line drains _minute every minute,
                                      # so an alert reading _minute saw only the last few seconds)
_suppressed: Counter = Counter()      # failures not logged since the source's last WARNING
_last_warn: Dict[str, float] = {}


def report(source: str, exc: BaseException, detail: str = '') -> None:
    now = time.time()
    with _lock:
        _minute[source] += 1
        _alert[source] += 1
        if now - _last_warn.get(source, 0.0) < WARN_EVERY_SEC:
            _suppressed[source] += 1
            return
        _last_warn[source] = now
        more = _suppressed.pop(source, 0)
    tail = f" (+{more} more since the last warning)" if more else ''
    logger.warning(f"{source} failed{(' ' + detail) if detail else ''}: {type(exc).__name__}: {exc}{tail}")


def health_text() -> str:
    """'errors: src N, ...' of the failures since the last call ('' when none), then resets the minute's counts."""
    with _lock:
        items = _minute.most_common()
        _minute.clear()
    return ('errors: ' + ', '.join(f"{k} {v}" for k, v in items)) if items else ''


def alert_text() -> str:
    """'src N, ...' of the failures since the previous call ('' when none): for the Telegram alert, not the Health line."""
    with _lock:
        items = _alert.most_common()
        _alert.clear()
    return ', '.join(f"{k} {v}" for k, v in items)
