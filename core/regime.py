"""Deterministic market regime labels for analytics only.

This module deliberately has no ML dependency and never vetoes a signal.
"""

def tag(*, trend: float | None, volatility: float | None, breadth: float | None = None) -> str:
    if trend is None or volatility is None:
        return 'unknown'
    direction = 'up' if trend > 0.001 else 'down' if trend < -0.001 else 'range'
    vol = 'volatile' if volatility >= 1.5 else 'quiet' if volatility <= 0.75 else 'normal'
    return f'{direction}_{vol}'
