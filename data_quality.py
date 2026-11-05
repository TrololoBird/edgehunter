"""Small, dependency-free data freshness contract shared by fetcher and scanners."""
from dataclasses import dataclass
from enum import StrEnum
from typing import Optional


class QualityState(StrEnum):
    FRESH = 'fresh'
    STALE = 'stale'
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
        return self.state in (QualityState.STALE, QualityState.FAILED, QualityState.DEAD)


def quality(now: float, fetched_at: Optional[float], ttl: float, max_age: float,
            source: str, error: Optional[str] = None, coverage: Optional[float] = None) -> DataQuality:
    if error:
        age = None if fetched_at is None else max(0.0, now - fetched_at)
        return DataQuality(QualityState.FAILED if age is None or age <= max_age else QualityState.DEAD,
                           fetched_at, age, coverage, source, error)
    if fetched_at is None:
        return DataQuality(QualityState.DEAD, None, None, coverage, source, 'missing')
    age = max(0.0, now - fetched_at)
    state = QualityState.FRESH if age <= ttl else QualityState.STALE if age <= max_age else QualityState.DEAD
    return DataQuality(state, fetched_at, age, coverage, source)
