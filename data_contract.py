"""Fail-closed validity checks for production briefing inputs."""

from typing import Any, Dict


class SystemValidityError(RuntimeError):
    """Raised when a required production input is absent or incomplete."""


def require_briefing_inputs(symbol: str, price: Any, levels: Any, tf: Dict[str, Any]) -> None:
    missing = []
    if price is None or price <= 0:
        missing.append('live_price')
    if not levels:
        missing.append('levels')
    for name in ('1h', '4h', '1d'):
        value = tf.get(name)
        if value is None or value <= 0:
            missing.append(f'atr_{name}')
    if missing:
        raise SystemValidityError(f'{symbol}: required briefing inputs missing: {", ".join(missing)}')
