"""Shared, as-of-bounded strategy and replay execution contract."""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class MarketSnapshot:
    """Immutable market view. Every candle/event must be known at ``asof_ms``."""

    asof_ms: int
    symbol: str
    candles: tuple[tuple[Any, ...], ...] = ()
    features: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self):
        if int(self.asof_ms) < 0:
            raise ValueError('snapshot asof_ms must be non-negative')
        if not self.symbol:
            raise ValueError('snapshot symbol is required')
        frozen = tuple(tuple(c) for c in self.candles)
        for candle in frozen:
            if not candle:
                raise ValueError('snapshot candle is empty')
            if int(candle[0]) >= int(self.asof_ms):
                raise ValueError('snapshot contains a candle at or after asof_ms')
        object.__setattr__(self, 'candles', frozen)
        object.__setattr__(self, 'features', MappingProxyType(dict(self.features)))


class StrategyEngine:
    """Single geometry and replay API shared by live cards and archive replay."""

    @staticmethod
    def evaluate_signal(plan: dict, entry: float, extreme: Optional[float], direction: int):
        from strategies import entry_levels_for
        return entry_levels_for(plan, entry, extreme, direction)

    @staticmethod
    def manage_position(snapshot: MarketSnapshot, levels: dict, direction: int,
                        *, funding_8h=None, funding_hours=None) -> dict:
        from levels import simulate
        return simulate(levels, direction, [list(c) for c in snapshot.candles],
                        funding_8h=funding_8h, funding_hours=funding_hours)
