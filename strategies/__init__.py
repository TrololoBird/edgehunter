"""Source-gated strategy registry.

Legacy strategy modules remain in the checkout for forensic analysis, but the
production router does not import or register them. A name such as ``wyckoff``
or ``orb`` is not evidence that the implementation is the published method.

To admit a v2 strategy, add a reviewed ``SourceRecord`` with a primary URL and
the exact rule fragment used by the implementation, then register the new
implementation here. Configuration alone can never enable an unverified
strategy.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from core.source_manifest import SOURCE_MANIFEST_VERSION, VERIFIED_SOURCE_RECORDS, source_manifest_hash
from strategies.base import PlanInput, Strategy, finalize_card_levels


# Deliberately empty during the rebuild. Old strategy classes are not a
# fallback and are never made eligible by a configuration value.
STRATEGIES: Dict[str, Strategy] = {}
SETUPS: Dict[str, Tuple[str, int]] = {}
_OBJ: Dict[str, Strategy] = {}


def strategy_of(group_key: str) -> Optional[Strategy]:
    return _OBJ.get(group_key)


def entry_levels_for(plan: dict, entry: float, extreme, direction: int):
    """Dispatch only a source-verified strategy contract."""
    strategy = strategy_of(str(plan.get('setup') or plan.get('group_key') or ''))
    if strategy is None:
        strategy = STRATEGIES.get(str(plan.get('strategy') or ''))
    if strategy is None:
        raise ValueError(f"unregistered or unverified playbook: {plan.get('setup') or plan.get('strategy')}")
    levels = strategy.entry_levels(plan, entry, extreme, direction)
    return finalize_card_levels(plan, levels, direction)


def unknown_names() -> Dict[str, list]:
    """Return legacy mode-table names that have no v2 registered strategy."""
    from strategies import bias, confirm, regime
    known = set(STRATEGIES)
    tables = {'regime.TREND_MODES': regime.TREND_MODES, 'regime.RANGE_MODES': regime.RANGE_MODES,
              'bias.TREND': bias.TREND, 'bias.WITH_BIAS': bias.WITH_BIAS,
              'bias.RANGE': bias.RANGE, 'bias.EXEMPT': bias.EXEMPT, 'bias.DAILY': bias.DAILY,
              'confirm.OI_EXPECT': tuple(confirm.OI_EXPECT)}
    return {k: sorted(set(v) - known) for k, v in tables.items() if set(v) - known}


__all__ = [
    "PlanInput", "Strategy", "STRATEGIES", "SETUPS", "strategy_of", "entry_levels_for",
    "SOURCE_MANIFEST_VERSION", "VERIFIED_SOURCE_RECORDS", "source_manifest_hash",
]
