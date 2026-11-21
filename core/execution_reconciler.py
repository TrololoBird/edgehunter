"""Evidence-gated exchange order reconciliation for the v2 execution path.

This module is deliberately small and stateful only in memory.  It does not
submit orders and it does not turn a reference price or a candle touch into a
fill.  An adapter must register a submitted order and then feed idempotent
user-data events.  A fill phase is accepted only when the event contains an
order identifier, a positive cumulative executed quantity and a finite
execution price.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from typing import Dict, Optional

from .execution_contract import ExecutionPhase, validate_transition


class ReconciliationError(ValueError):
    """The exchange event cannot be reconciled without inventing state."""


@dataclass(frozen=True)
class ExchangeOrderEvent:
    """Cumulative user-data observation for one exchange order."""

    card_id: str
    venue: str
    symbol: str
    status: str
    event_ts_ms: int
    received_ts_ms: int
    order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    executed_qty: float = 0.0
    average_price: Optional[float] = None
    fee: Optional[float] = None
    reduce_only: bool = False
    event_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.card_id or not self.venue or not self.symbol:
            raise ReconciliationError("card, venue and symbol are required")
        if not self.order_id and not self.client_order_id:
            raise ReconciliationError("exchange event has no order identifier")
        if int(self.event_ts_ms) < 0 or int(self.received_ts_ms) < 0:
            raise ReconciliationError("event timestamps must be non-negative")
        qty = float(self.executed_qty)
        if not math.isfinite(qty) or qty < 0:
            raise ReconciliationError("executed quantity must be finite and non-negative")
        if qty > 0:
            if self.average_price is None or not math.isfinite(float(self.average_price)) or float(self.average_price) <= 0:
                raise ReconciliationError("a positive fill requires a finite execution price")
        if self.fee is not None and (not math.isfinite(float(self.fee)) or float(self.fee) < 0):
            raise ReconciliationError("fee must be finite and non-negative")

    @property
    def key(self) -> str:
        return f"{self.venue}:{self.order_id or self.client_order_id}"

    @property
    def fingerprint(self) -> str:
        payload = asdict(self)
        payload.pop("event_id", None)
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class ReconciledOrder:
    card_id: str
    venue: str
    symbol: str
    order_id: Optional[str]
    client_order_id: Optional[str]
    phase: ExecutionPhase
    executed_qty: float = 0.0
    average_price: Optional[float] = None
    fee: float = 0.0
    last_event_ts_ms: int = 0
    last_event_id: Optional[str] = None
    unknown_reason: Optional[str] = None


_ACK = {"NEW", "OPEN", "ACCEPTED", "WORKING"}
_PARTIAL = {"PARTIALLY_FILLED", "PARTIAL"}
_FILLED = {"FILLED", "CLOSED"}
_NO_FILL_TERMINAL = {"CANCELED", "CANCELLED", "EXPIRED", "REJECTED"}


class ExecutionReconciler:
    """Idempotently apply exchange user-data events to order observations."""

    def __init__(self) -> None:
        self._orders: Dict[str, ReconciledOrder] = {}
        self._events: Dict[str, str] = {}

    def register_submission(self, card_id: str, venue: str, symbol: str,
                            *, order_id: Optional[str] = None,
                            client_order_id: Optional[str] = None,
                            event_ts_ms: int = 0) -> ReconciledOrder:
        """Register local submission; this is not exchange acknowledgement."""
        if not order_id and not client_order_id:
            raise ReconciliationError("submission has no order identifier")
        key = f"{venue}:{order_id or client_order_id}"
        if key in self._orders:
            return self._orders[key]
        validate_transition(None, ExecutionPhase.SIGNAL)
        validate_transition(ExecutionPhase.SIGNAL, ExecutionPhase.VALIDATED)
        validate_transition(ExecutionPhase.VALIDATED, ExecutionPhase.ORDER_SUBMITTED)
        state = ReconciledOrder(card_id, venue, symbol, order_id, client_order_id,
                                ExecutionPhase.ORDER_SUBMITTED, last_event_ts_ms=int(event_ts_ms))
        self._orders[key] = state
        return state

    def apply(self, event: ExchangeOrderEvent) -> ReconciledOrder:
        """Apply an exchange event; duplicates are no-ops, contradictions fail."""
        key = event.key
        state = self._orders.get(key)
        if state is None:
            raise ReconciliationError(f"event for unregistered order: {key}")
        if state.card_id != event.card_id or state.symbol != event.symbol:
            raise ReconciliationError("order event identity does not match submission")

        event_key = event.event_id or f"{key}:{event.event_ts_ms}:{event.status}:{event.fingerprint}"
        old_fp = self._events.get(event_key)
        if old_fp is not None:
            if old_fp != event.fingerprint:
                raise ReconciliationError("event id was reused for different payload")
            return state
        self._events[event_key] = event.fingerprint

        status = str(event.status or "").upper()
        qty = float(event.executed_qty)
        if state.phase is ExecutionPhase.UNKNOWN and state.executed_qty <= 0 and qty > 0:
            raise ReconciliationError(
                "cannot promote an unresolved terminal order to a fill without manual reconciliation"
            )
        phase = state.phase
        reason = None
        if status in _ACK:
            phase = ExecutionPhase.ACKNOWLEDGED
        elif status in _PARTIAL:
            if qty <= 0:
                phase, reason = ExecutionPhase.UNKNOWN, "partial status without executed quantity"
            else:
                phase = ExecutionPhase.PARTIAL_FILL
        elif status in _FILLED:
            if qty <= 0:
                phase, reason = ExecutionPhase.UNKNOWN, "filled status without exchange fill evidence"
            else:
                phase = ExecutionPhase.FILLED
        elif status in _NO_FILL_TERMINAL:
            phase, reason = ExecutionPhase.UNKNOWN, "terminal order status without a position close event"
        else:
            phase, reason = ExecutionPhase.UNKNOWN, f"unrecognised exchange status: {status or '<empty>'}"

        # Cumulative exchange quantities are monotone.  A delayed lower event
        # cannot regress a filled order into a partial one.
        if qty < state.executed_qty:
            phase = state.phase
            qty = state.executed_qty
            reason = state.unknown_reason
        elif state.phase in {ExecutionPhase.FILLED, ExecutionPhase.RECONCILED} and phase == ExecutionPhase.PARTIAL_FILL:
            phase = state.phase
            reason = state.unknown_reason

        if phase != state.phase:
            validate_transition(state.phase, phase)
        avg = event.average_price if qty > 0 else state.average_price
        fee = float(event.fee) if event.fee is not None else state.fee
        next_state = replace(state, phase=phase, executed_qty=qty, average_price=avg,
                             fee=fee, last_event_ts_ms=int(event.event_ts_ms),
                             last_event_id=event.event_id or event_key, unknown_reason=reason)
        self._orders[key] = next_state
        return next_state

    def get(self, venue: str, order_id: str) -> Optional[ReconciledOrder]:
        return self._orders.get(f"{venue}:{order_id}")

    def snapshot(self) -> tuple[ReconciledOrder, ...]:
        return tuple(self._orders.values())
