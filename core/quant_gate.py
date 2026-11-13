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
    values = (p_base, reward, risk, cost)
    if not all(v is None or math.isfinite(float(v)) for v in values) or risk <= 0 or reward < 0 or cost < 0:
        return {'p_base': p_base, 'p_breakeven': None, 'ev_net': None, 'trade_gate': False,
                'reason': 'invalid_inputs'}
    p_be = (risk + cost) / (risk + reward)
    ev = None if p_base is None else float(p_base) * (reward - cost) - (1.0 - float(p_base)) * (risk + cost)
    approved = bool(ev is not None and ev > 0 and float(p_base) >= p_be)
    return {'p_base': p_base, 'p_breakeven': p_be, 'ev_net': ev, 'trade_gate': approved,
            'reason': 'ok' if approved else 'non_positive_ev_or_insufficient_probability'}
