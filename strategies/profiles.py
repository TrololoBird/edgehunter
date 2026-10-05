"""
Optimized strategy profiles (research_optimize.py -> models/profiles.json): per strategy the entry FILTERS and the
POSITION MANAGEMENT that made it positive on the archive replay's untouched validation months. The live bot applies a
profile's filters to every entry of that strategy (`masks` computes them exactly as the research did) and the demo
trades only strategies with a profile.

profiles.json: {strategy: {"filters": ["1h:adx_trend", "coin:small", ...], "pm": {"target": "2", "be": true,
"trail": 3, "half": false, "hours": 24, "stop": 1.5}, "train": {...}, "validation": {...}}}
"""
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'models', 'profiles.json')
_cache: Dict = {'mtime': None, 'data': {}}


def load() -> Dict[str, Dict]:
    try:
        mtime = os.path.getmtime(PATH)
    except OSError:
        return {}
    if _cache['mtime'] != mtime:
        with open(PATH, encoding='utf-8') as fh:
            _cache.update(mtime=mtime, data=json.load(fh))
    return _cache['data']


def profile(strategy: str) -> Optional[Dict]:
    return load().get(strategy)


def masks(ind: Dict, volume_24h: Optional[float], ts_ms: float, direction: int, btc_slope: Optional[float],
          vetoed: Optional[str], atr_rank_1h: Optional[bool]) -> Dict[str, bool]:
    """The research's filter flags of one entry. `ind`: {'15m': {rule: bool}, '1h': {...}} (fetcher.indicator_panel)."""
    out = {f'{tf}:{k}': bool(v) for tf, panel in (ind or {}).items() for k, v in (panel or {}).items()}
    vol = volume_24h or 0.0
    out.update({'coin:major': vol >= 1e9, 'coin:large': 2e8 <= vol < 1e9, 'coin:mid': 5e7 <= vol < 2e8,
                'coin:small': vol < 5e7})
    t = datetime.fromtimestamp(ts_ms / 1000, timezone.utc)
    out.update({'session:asia': t.hour < 8, 'session:europe': 8 <= t.hour < 13, 'session:us': 13 <= t.hour < 21,
                'session:late': t.hour >= 21, 'weekend': t.weekday() >= 5})
    out['btc:with'] = bool(btc_slope is not None and direction * btc_slope > 0)
    out['btc:against'] = bool(btc_slope is not None and direction * btc_slope < 0)
    out['passed_veto'] = vetoed is None
    out['atr:high'] = bool(atr_rank_1h)
    return out


def failed(strategy: str, flags: Dict[str, bool]) -> List[str]:
    """The profile's filters this entry does not meet ([] = it passes or the strategy has no profile)."""
    p = profile(strategy)
    if not p:
        return []
    return [f for f in p.get('filters') or [] if not flags.get(f)]


def apply_pm(levels: Dict, pm: Dict, direction: int) -> Dict:
    """The profile's stop and targets on an entry's levels (in place): the stop at `stop` x the plan's distance, the
    targets at `target` R (all three: the whole position), the plan's TP1 (all three), or none (no take-profit
    orders: the trail / breakeven / time stop exit). Returns the levels."""
    d, entry = direction, levels['entry']
    mult = float(pm.get('stop') or 1.0)
    risk = abs(entry - levels['sl']) * mult
    levels['sl'] = entry - d * risk
    if mult != 1.0:
        levels['sl_src'] = f"{levels.get('sl_src')} x{mult:g} (profile)"
    target = str(pm.get('target'))
    if target in ('1', '1.5', '2', '3'):
        t = entry + d * float(target) * risk
        src = f'{target} R (profile)'
        levels.update(tp1=t, tp2=t, tp3=t, tp1_src=src, tp2_src=src, tp3_src=src)
    elif target == 'plan' and levels.get('tp1') is not None:
        levels.update(tp2=levels['tp1'], tp3=levels['tp1'], tp2_src=levels.get('tp1_src'),
                      tp3_src=levels.get('tp1_src'))
    elif target == 'none':
        far = entry + d * 100 * risk
        levels.update(tp1=far, tp2=far, tp3=far, tp1_src='none (profile exit)', tp2_src='none (profile exit)',
                      tp3_src='none (profile exit)')
    if pm.get('half') and target != 'none':
        # half off at +1R in the research; the live position exits in thirds: a third at +1R, the rest at the target
        levels.update(tp1=entry + d * risk, tp1_src='1 R (profile partial)')
    levels['rr_tp1'] = abs(levels['tp1'] - entry) / risk if risk else None
    return levels
