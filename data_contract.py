"""Fail-closed validity checks for production briefing inputs."""

from typing import Any, Dict


class SystemValidityError(RuntimeError):
    """P0: required production input is absent or incomplete."""

    def __init__(self, symbol: str, missing: list[str]):
        self.symbol = symbol
        self.missing = tuple(missing)
        super().__init__(f'{symbol}: required briefing inputs missing: {", ".join(missing)}')


class SystemValidityGate:
    """Fail-closed gate. No partial/degraded production calculation is allowed."""

    @staticmethod
    def briefing(symbol: str, price: Any, levels: Any, tf: Dict[str, Any]) -> None:
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
            raise SystemValidityError(symbol, missing)


def require_briefing_inputs(symbol: str, price: Any, levels: Any, tf: Dict[str, Any]) -> None:
    SystemValidityGate.briefing(symbol, price, levels, tf)
