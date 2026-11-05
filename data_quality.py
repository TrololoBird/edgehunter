"""Small, dependency-free data freshness contract shared by fetcher and scanners."""
from dataclasses import dataclass
try:
    from enum import StrEnum
except ImportError:  # Python 3.10/3.11 compatibility for offline validators
    from enum import Enum

    class StrEnum(str, Enum):
        pass
from typing import Optional


class QualityState(StrEnum):
    FRESH = 'fresh'
    DEGRADED = 'degraded'
    STALE = 'stale'
    MISSING = 'missing'
    INVALID = 'invalid'
    # Backwards-compatible names used by the existing callers.
    FAILED = 'failed'
    DEAD = 'dead'


@dataclass(frozen=True)
class DataQuality:
    state: QualityState
    fetched_at: Optional[float]
    age_sec: Optional[float]
    coverage: Optional[float] = None
    source: str = ''
    error: Optional[str] = None

    @property
    def usable_for_entry(self) -> bool:
        return self.state is QualityState.FRESH

    @property
    def stale(self) -> bool:
        return self.state in (QualityState.DEGRADED, QualityState.STALE, QualityState.MISSING,
                              QualityState.INVALID, QualityState.FAILED, QualityState.DEAD)


def quality(now: float, fetched_at: Optional[float], ttl: float, max_age: float,
            source: str, error: Optional[str] = None, coverage: Optional[float] = None) -> DataQuality:
    if error:
        age = None if fetched_at is None else max(0.0, now - fetched_at)
        state = QualityState.FAILED if fetched_at is None else QualityState.INVALID
        if age is not None and age > max_age:
            state = QualityState.DEAD
        return DataQuality(state, fetched_at, age, coverage, source, error)
    if fetched_at is None:
        return DataQuality(QualityState.MISSING, None, None, coverage, source, 'missing')
    age = max(0.0, now - fetched_at)
    if age <= ttl:
        state = QualityState.DEGRADED if coverage is not None and coverage < 1.0 else QualityState.FRESH
    else:
        state = QualityState.STALE if age <= max_age else QualityState.DEAD
    return DataQuality(state, fetched_at, age, coverage, source)
