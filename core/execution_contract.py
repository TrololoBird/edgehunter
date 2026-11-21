"""Explicit execution lifecycle used by the v2 design.

This is a state contract, not a simulator.  A reference price can create a
``SIGNAL``/``VALIDATED`` event, but only an exchange acknowledgement or fill
event can advance an order into the corresponding execution phases.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ExecutionPhase(str, Enum):
    SIGNAL = "SIGNAL"
    VALIDATED = "VALIDATED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIAL_FILL = "PARTIAL_FILL"
    FILLED = "FILLED"
    PROTECTED = "PROTECTED"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    CLOSED = "CLOSED"
    RECONCILED = "RECONCILED"
    UNKNOWN = "UNKNOWN"


_ALLOWED = {
    None: {ExecutionPhase.SIGNAL},
    ExecutionPhase.SIGNAL: {ExecutionPhase.VALIDATED, ExecutionPhase.UNKNOWN},
    ExecutionPhase.VALIDATED: {ExecutionPhase.ORDER_SUBMITTED, ExecutionPhase.UNKNOWN},
    ExecutionPhase.ORDER_SUBMITTED: {ExecutionPhase.ACKNOWLEDGED, ExecutionPhase.PARTIAL_FILL,
                                      ExecutionPhase.FILLED, ExecutionPhase.UNKNOWN},
    ExecutionPhase.ACKNOWLEDGED: {ExecutionPhase.PARTIAL_FILL, ExecutionPhase.FILLED, ExecutionPhase.CLOSED,
                                  ExecutionPhase.UNKNOWN},
    ExecutionPhase.PARTIAL_FILL: {ExecutionPhase.PARTIAL_FILL, ExecutionPhase.FILLED, ExecutionPhase.CLOSED,
                                  ExecutionPhase.UNKNOWN},
    ExecutionPhase.FILLED: {ExecutionPhase.PROTECTED, ExecutionPhase.PARTIAL_EXIT, ExecutionPhase.CLOSED,
                            ExecutionPhase.UNKNOWN},
    ExecutionPhase.PROTECTED: {ExecutionPhase.PARTIAL_EXIT, ExecutionPhase.CLOSED, ExecutionPhase.UNKNOWN},
    ExecutionPhase.PARTIAL_EXIT: {ExecutionPhase.PARTIAL_EXIT, ExecutionPhase.CLOSED, ExecutionPhase.UNKNOWN},
    ExecutionPhase.CLOSED: {ExecutionPhase.RECONCILED, ExecutionPhase.UNKNOWN},
    ExecutionPhase.RECONCILED: set(),
    ExecutionPhase.UNKNOWN: {ExecutionPhase.RECONCILED, ExecutionPhase.UNKNOWN},
}


@dataclass(frozen=True)
class ExecutionEvent:
    card_id: str
    phase: ExecutionPhase
    event_ts_ms: int
    venue: str = ""
    order_id: Optional[str] = None
    quantity: Optional[float] = None
    price: Optional[float] = None
    status: str = ""


def validate_transition(previous: Optional[ExecutionPhase], current: ExecutionPhase) -> None:
    """Raise when a lifecycle event skips an evidence-bearing state."""
    if current not in _ALLOWED.get(previous, set()):
        before = previous.value if previous is not None else "<start>"
        raise ValueError(f"invalid execution transition {before} -> {current.value}")

