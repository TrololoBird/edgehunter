"""Small, serialisable provenance types for v2 market observations.

This module is intentionally independent of exchange clients. It gives data
adapters one vocabulary for availability and quality without implying that a
missing observation is zero or that a public stream is complete.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class MarketDataState(str, Enum):
    OBSERVED = "observed"
    STALE = "stale"
    MISSING = "missing"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DataProvenance:
    venue: str
    market: str
    symbol: str
    field: str
    event_ts_ms: Optional[int]
    received_ts_ms: Optional[int]
    available_ts_ms: Optional[int]
    source: str
    state: MarketDataState
    units: str = ""
    sequence: Optional[int] = None
    raw_hash: Optional[str] = None
    reason: Optional[str] = None

    @property
    def is_decision_safe(self) -> bool:
        """Whether the envelope contains a complete, timestamped observation.

        This property does not know the decision timestamp.  Call
        :meth:`safe_at` when a caller has an as-of time; an observation with no
        availability timestamp is never admitted by either check.
        """
        return (self.state is MarketDataState.OBSERVED
                and self.event_ts_ms is not None
                and self.available_ts_ms is not None)

    def safe_at(self, asof_ts_ms: int) -> bool:
        """Return whether this observation was available by ``asof_ts_ms``.

        Event time and availability time are separate.  A delayed event may
        be historically earlier while still being unavailable when a decision
        was made; that event is not causal input for the decision.
        """
        if not self.is_decision_safe:
            return False
        asof = int(asof_ts_ms)
        assert self.event_ts_ms is not None and self.available_ts_ms is not None
        return self.event_ts_ms <= asof and self.available_ts_ms <= asof


def require_decision_safe(provenance: DataProvenance, asof_ts_ms: Optional[int] = None) -> None:
    """Raise unless an observation is complete and available at the decision time."""
    safe = provenance.is_decision_safe if asof_ts_ms is None else provenance.safe_at(asof_ts_ms)
    if not safe:
        suffix = "" if asof_ts_ms is None else f" at {int(asof_ts_ms)}"
        raise ValueError(f"market observation is not decision-safe{suffix}: {provenance}")

