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

import numpy as np

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

# ---------------------------------------------------------------------- regime switch (research_optimize_regime.py)

REGIME_PATH = os.path.join(os.path.dirname(PATH), 'profiles_regime.json')
_regime_cache: Dict = {'mtime': None, 'data': {}}


def regime_profiles() -> Dict[str, Dict]:
    try:
        mtime = os.path.getmtime(REGIME_PATH)
    except OSError:
        return {}
    if _regime_cache['mtime'] != mtime:
        with open(REGIME_PATH, encoding='utf-8') as fh:
            _regime_cache.update(mtime=mtime, data=json.load(fh))
    return _regime_cache['data']


# strategies whose regime profiles are NOT applied live (the Turtles keep their own exits, validated in every regime)
REGIME_EXEMPT = ('breakout',)


def select(strategy: str, regime: Optional[str]):
    """(profile, veto): the regime's profile when the strategy has regime profiles (veto 'regime_off' in a regime
    without one), else its plain profile (models/profiles.json), else (None, None)."""
    cells = regime_profiles().get(strategy)
    if cells and strategy not in REGIME_EXEMPT:
        cell = cells.get(regime or '')
        if cell is None:
            return None, 'regime_off'
        return {**cell, 'status': f'regime {regime}'}, None
    return profile(strategy), None


_BTC_REGIME: Dict = {}


def btc_regime(h4: List) -> Optional[str]:
    """The regime of BTC's last closed 4h candle ([ts, o, h, l, c, ...], oldest first); cached per last candle (the
    Python RMA loop ran for every confirmation: watchdog stalls in regime_labels)."""
    if len(h4) < 145:
        return None
    key = (len(h4), h4[-1][0], h4[-1][4])
    if key not in _BTC_REGIME:
        import numpy as np
        k = np.asarray([row[:5] for row in h4], dtype=float)
        _BTC_REGIME.clear()
        _BTC_REGIME[key] = regime_labels(k, last_only=True)[-1]
    return _BTC_REGIME[key]


def regime_labels(k: np.ndarray, last_only: bool = False) -> list:
    """Regime of each 4h candle of k ([open_ms, o, h, l, c]), as strategies/profiles.regime does live."""
    h, l, c = k[:, 2], k[:, 3], k[:, 4]
    prev = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(abs(h - prev), abs(l - prev)))
    up, dn = h - np.concatenate(([h[0]], h[:-1])), np.concatenate(([l[0]], l[:-1])) - l
    pdm, mdm = np.where((up > dn) & (up > 0), up, 0.0), np.where((dn > up) & (dn > 0), dn, 0.0)

    def rma(x, n=14):
        out = np.full_like(x, np.nan)
        if len(x) < n:
            return out
        out[n - 1] = x[:n].mean()
        for i in range(n, len(x)):
            out[i] = (out[i - 1] * (n - 1) + x[i]) / n
        return out
    atr = rma(tr)
    pdi, mdi = 100 * rma(pdm) / atr, 100 * rma(mdm) / atr
    adx = rma(np.nan_to_num(100 * abs(pdi - mdi) / np.maximum(pdi + mdi, 1e-12)))
    out = []
    # last_only: the live caller reads the last label only (the per-candle nanmedian loop stalled the loop 1.5s)
    for i in (range(len(k) - 1, len(k)) if last_only else range(len(k))):
        if i < 140 or np.isnan(adx[i]) or np.isnan(atr[i]):
            out.append(None)
            continue
        med = np.nanmedian(atr[i - 124:i + 1])
        out.append(('trend' if adx[i] >= 25 else 'range') + ('_hv' if atr[i] > med else '_lv'))
    return out


# ---------------------------------------------------------------------- exit overlays (research_overlays.py)

OVERLAY_PATH = os.path.join(os.path.dirname(PATH), 'exit_overlays.json')
_overlay_cache: Dict = {'mtime': None, 'data': {}}


def exit_overlays(strategy: str, base: str) -> List[str]:
    """The early-exit overlays adopted for this strategy and base ('plan' = the method's own plan, 'profile' = its
    optimized profile): e.g. ['noprog_4', 'btc_1.0'] from 'noprog_4+btc_1.0'; [] when none passed the rule."""
    try:
        mtime = os.path.getmtime(OVERLAY_PATH)
    except OSError:
        return []
    if _overlay_cache['mtime'] != mtime:
        with open(OVERLAY_PATH, encoding='utf-8') as fh:
            _overlay_cache.update(mtime=mtime, data=json.load(fh))
    name = (_overlay_cache['data'].get(strategy) or {}).get(base)
    return name.split('+') if name else []


def overlay_filters(strategy: str, base: str) -> List[str]:
    """Entry filters adopted with the overlays (research_overlays.py) for the method's own plan: e.g. ['alts_with']
    (the median 4h return of the universe beat BTC's in the trade's direction)."""
    exit_overlays(strategy, base)                     # refreshes the cache
    if base != 'plan':
        return []
    return list((_overlay_cache['data'].get(strategy) or {}).get('filters') or [])

