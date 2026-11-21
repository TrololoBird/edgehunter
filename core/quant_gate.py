"""Small, explicit cost-aware gates shared by briefing and scenario analytics."""
from __future__ import annotations

import math
from typing import Optional


def scenario_gate(p_base: Optional[float], reward: float, risk: float, cost: float) -> dict:
    """Return net EV and the fee-adjusted break-even probability.

    ``reward`` and ``risk`` are positive price distances before costs; cost is
    the round-trip price cost. A missing base probability is reported but does
    not silently become a trade approval.
    """
    if (p_base is not None and not math.isfinite(float(p_base))) or \
            not all(math.isfinite(float(v)) for v in (reward, risk, cost)) or risk <= 0 or reward < 0 or cost < 0:
        return {'p_base': p_base, 'p_breakeven': None, 'ev_net': None, 'trade_gate': False,
                'reason': 'invalid_inputs'}
    p_be = (risk + cost) / (risk + reward)
    base = float(p_base) if p_base is not None else None
    ev = None if base is None else base * (reward - cost) - (1.0 - base) * (risk + cost)
    approved = bool(base is not None and ev is not None and ev > 0 and base >= p_be)
    return {'p_base': p_base, 'p_breakeven': p_be, 'ev_net': ev, 'trade_gate': approved,
            'reason': 'ok' if approved else 'non_positive_ev_or_insufficient_probability'}
