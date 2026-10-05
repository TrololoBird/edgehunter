"""
How far price pierces a level before it turns back, measured (research_overshoot.py -> models/overshoot.json: per coin
and level kind the p50 / p80 / p90 of the depth of rejections, 80 coins x 12 months, stable across halves). The stop
buffer beyond a level and the "just behind" distance of a stop pool come from here instead of ATR constants.
"""
import json
import os
from typing import Dict, Iterable, Optional

KINDS = ('swing_15m', 'swing_1h', 'equal', 'pdhl', 'round')
# map-zone kinds (zones.py) -> the measured kinds
ZONE_KIND = {'swing_15m': 'swing_15m', 'swing_1h': 'swing_1h', 'equal': 'equal', 'pdhl': 'pdhl', 'round': 'round',
             'range': 'swing_1h', 'book': 'swing_15m',
             # eng-70: daily / weekly / monthly extremes take the closest measured kinds
             'swing_1d': 'swing_1h', 'swing_1w': 'swing_1h', 'pmhl': 'pdhl', 'year': 'pdhl'}
_MODEL: Optional[Dict] = None


def model() -> Dict:
    global _MODEL
    if _MODEL is None:
        # PIERCE_MODEL: an archive replay points it at a model measured BEFORE its window (research_overshoot.py --end
        # <the replay's start>), so the stop buffer does not know the months it is tested on
        path = os.environ.get('PIERCE_MODEL') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models',
                                                               'overshoot.json')
        try:
            with open(path, encoding='utf-8') as f:
                _MODEL = json.load(f)
        except (OSError, ValueError):
            _MODEL = {}
    return _MODEL


def overshoot(symbol: Optional[str], kind: str, price: float, q: str = 'p80') -> Optional[float]:
    """The q-quantile pierce of this kind of level on this coin (its own figure with >= 20 rejections, else all
    coins'), in price units; None without the model."""
    m = model()
    if not m:
        return None
    kind = kind if kind in KINDS else 'swing_15m'
    row = ((m.get('coins') or {}).get(symbol) or {}).get(kind) or (m.get('global') or {}).get(kind) or {}
    value = row.get(q)
    return price * value / 100 if value else None


def measured_kind(kinds: Iterable[str]) -> Optional[str]:
    """The measured kind of a map zone (its first kind that has one)."""
    for k in kinds:
        if k in ZONE_KIND:
            return ZONE_KIND[k]
    return None


def kind_of_label(label: str, tf: str = '15m') -> str:
    """The measured kind behind a pool / level text label (pools carry labels only)."""
    s = label or ''
    if 'EQ' in s or 'equal' in s:
        return 'equal'
    if any(k in s for k in ('PDH', 'PDL', 'PWH', 'PWL', 'London', 'New York', 'Asia', 'day high', 'day low', 'week')):
        return 'pdhl'
    if 'round' in s:
        return 'round'
    return 'swing_1h' if tf in ('1h', '4h') or '1h' in s else 'swing_15m'
