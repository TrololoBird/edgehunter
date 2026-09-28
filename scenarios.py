"""
Two-sided level scenarios of one coin (the "scenario card"): the reaction zone the price is in, the next resistances
above and supports below on the 1h map, a LONG scenario (close above the reaction zone and a retest -> the
resistances above) and a SHORT scenario (a rejection at the first resistance -> the supports below), each with entry,
stop, three targets and R:R. Nothing is entered: the card says what would have to happen first.

The probability shown is P(the first resistance is reached before the first support), from a model trained on the
Binance archive with THE SAME level and feature code (`train_scenarios.py`, walk-forward, calibrated); without a
model file, or when the model did not beat the geometric baseline out of sample, the card shows the geometric
baseline of a driftless random walk, d_down / (d_up + d_down), labelled as such. Never a promise: a calibrated
frequency of similar past situations.

Levels (1h candles only, so live and training see the same inputs): intact 1h and 4h swings, equal highs / lows,
previous day / week and session highs / lows, the 8-day volume profile of the 1h candles, round numbers; merged at
`merge_atr` x ATR(1h); zones weaker than `min_strength` are skipped for the scenario ladder.
"""
import math
import os
import pickle
from typing import Dict, List, Optional, Sequence

from config import CONFIG
from levels import atr_of, resample_htf
from zones import RawLevel, Zone, day_levels, equal_pools, merge, round_levels, swings, volume_profile

MODEL_PATH = os.path.join('models', 'scenario_prob.pkl')
HOUR_MS = 3_600_000
FEATURES = ('d_up', 'd_down', 's_up', 's_down', 'p_geo', 'trend_1h', 'trend_4h', 'ret_24h', 'ret_7d', 'range_pos',
            'vol_ratio', 'btc_ret_24h', 'btc_ret_7d', 'btc_trend_4h', 'n_up', 'n_down')
_model_cache: Dict = {}


# ---------------------------------------------------------------------------------------------------- levels

def levels_1h(candles_1h: Sequence[Sequence[float]], atr: float, now_ms: float) -> List[RawLevel]:
    cfg = CONFIG.zones
    s1h = swings(candles_1h, cfg.swing_width_1h, 'swing_1h', '1h')
    c4h = resample_htf(candles_1h, 4)
    s4h = [RawLevel(s.price, 'swing_1h', s.label.replace('1h', '4h'), s.side, ts=s.ts)
           for s in swings(c4h, 2, 'swing_1h', '4h')]
    levels = s1h + s4h + equal_pools(s1h, candles_1h, atr) + day_levels(candles_1h, now_ms)
    levels += volume_profile(candles_1h, atr, '8d')
    last = candles_1h[-1][4]
    levels += [RawLevel(p, 'round', f"round {p:g}", +1 if p > last else -1)
               for p in round_levels(last, cfg.round_span_atr * atr)]
    return levels


def _ema(xs: Sequence[float], span: int) -> List[float]:
    a, out = 2 / (span + 1), []
    for x in xs:
        out.append(x if not out else out[-1] + a * (x - out[-1]))
    return out


def _trend(closes: Sequence[float], span: int = 20) -> float:
    """EMA slope over the last 5 bars, in % of price."""
    if len(closes) < span + 5:
        return 0.0
    e = _ema(closes, span)
    return (e[-1] / e[-6] - 1) * 100


def _ret(closes: Sequence[float], bars: int) -> float:
    return (closes[-1] / closes[-1 - bars] - 1) * 100 if len(closes) > bars and closes[-1 - bars] else 0.0


# ---------------------------------------------------------------------------------------------------- ladder

def ladder(zones: List[Zone], price: float, atr: float) -> Optional[Dict]:
    """The reaction zone (holding or nearest to the price), up to 3 zones above and 2 below, >= 1 ATR apart."""
    cfg = CONFIG.zones
    if not zones or not atr:
        return None
    pad = 0.15 * atr

    def band(z: Zone) -> Dict:
        lo, hi = min(z.lo, z.price - pad), max(z.hi, z.price + pad)
        return {'lo': lo, 'hi': hi, 'price': z.price, 'strength': round(z.strength, 2), 'label': z.label}

    inside = [z for z in zones if z.lo - pad <= price <= z.hi + pad]
    near = min(zones, key=lambda z: abs(z.price - price))
    if inside:
        react = band(max(inside, key=lambda z: z.strength))
    elif abs(near.price - price) <= 0.5 * atr:
        react = band(near)
    else:
        react = {'lo': price - pad, 'hi': price + pad, 'price': price, 'strength': 0.0, 'label': 'нет уровня у цены'}
    strong = [z for z in zones if z.strength >= cfg.min_strength]

    def pick(cands: List[Zone], edge: float, direction: int, n: int) -> List[Dict]:
        out, last = [], edge
        for z in sorted(cands, key=lambda z: direction * z.price):
            near_edge = z.lo if direction > 0 else z.hi
            if direction * (near_edge - last) >= atr:
                b = band(z)
                out.append(b)
                last = b['hi'] if direction > 0 else b['lo']
                if len(out) == n:
                    break
        return out

    above = pick([z for z in strong if z.lo > react['hi']], react['hi'], +1, 3)
    below = pick([z for z in strong if z.hi < react['lo']], react['lo'], -1, 2)
    if not above or not below:
        return None
    return {'reaction': react, 'above': above, 'below': below}


def features(lad: Dict, price: float, atr: float, closes_1h: Sequence[float],
             btc_closes_1h: Optional[Sequence[float]]) -> Dict[str, float]:
    up, down = lad['above'][0], lad['below'][0]
    d_up = (up['lo'] - price) / atr
    d_down = (price - down['hi']) / atr
    c4 = list(closes_1h[3::4]) if len(closes_1h) >= 4 else list(closes_1h)
    hi, lo = max(closes_1h[-192:]), min(closes_1h[-192:])
    tr = [abs(closes_1h[i] - closes_1h[i - 1]) for i in range(1, len(closes_1h))]
    recent = sum(tr[-6:]) / 6 if len(tr) >= 6 else 0.0
    base = sum(tr[-96:]) / len(tr[-96:]) if tr else 0.0
    b = btc_closes_1h or []
    return {
        'd_up': d_up, 'd_down': d_down, 's_up': up['strength'], 's_down': down['strength'],
        'p_geo': d_down / (d_up + d_down) if d_up + d_down > 0 else 0.5,
        'trend_1h': _trend(closes_1h), 'trend_4h': _trend(c4), 'ret_24h': _ret(closes_1h, 24),
        'ret_7d': _ret(closes_1h, 168), 'range_pos': (price - lo) / (hi - lo) if hi > lo else 0.5,
        'vol_ratio': recent / base if base else 1.0,
        'btc_ret_24h': _ret(b, 24) if b else 0.0, 'btc_ret_7d': _ret(b, 168) if b else 0.0,
        'btc_trend_4h': _trend(list(b[3::4])) if b else 0.0,
        'n_up': float(len(lad['above'])), 'n_down': float(len(lad['below'])),
    }


# ---------------------------------------------------------------------------------------------------- model

def load_model(path: str = MODEL_PATH) -> Optional[Dict]:
    """The trained model when it beat the geometric baseline out of sample (cached by file mtime)."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    if _model_cache.get('mtime') != mtime:
        try:
            with open(path, 'rb') as fh:
                _model_cache.update(mtime=mtime, model=pickle.load(fh))
        except Exception:
            _model_cache.update(mtime=mtime, model=None)
    m = _model_cache.get('model')
    return m if m and m.get('passed') else None


def probability(feats: Dict[str, float], model: Optional[Dict]) -> Dict:
    if model is None:
        return {'p_up': feats['p_geo'], 'source': 'геометрия (без модели)'}
    x = [[feats.get(k, float('nan')) for k in model['features']]]
    p = float(model['clf'].predict_proba(x)[0, 1])
    if model.get('calibrator') is not None:
        p = float(model['calibrator'].predict([p])[0])
    return {'p_up': min(0.97, max(0.03, p)), 'source': f"модель ({model['trained_on']})"}


# ---------------------------------------------------------------------------------------------------- scenario

def build(candles_1h: Sequence[Sequence[float]], price: Optional[float], now_ms: float,
          btc_closes_1h: Optional[Sequence[float]] = None, extra_levels: Sequence[RawLevel] = (),
          model=None, macro_feats: Optional[Dict[str, float]] = None) -> Optional[Dict]:
    """
    The scenario card of one coin from its 1h candles (>= 50) and the live price. model: None = the saved model when it
    passed, False = the geometric baseline (training), a dict = that model.
    """
    if not candles_1h or len(candles_1h) < 50:
        return None
    price = price or candles_1h[-1][4]
    atr = atr_of(candles_1h, 14)
    if not atr or not price:
        return None
    zones = merge(levels_1h(candles_1h, atr, now_ms) + list(extra_levels), atr)
    lad = ladder(zones, price, atr)
    if lad is None:
        return None
    closes = [c[4] for c in candles_1h]
    feats = features(lad, price, atr, closes, btc_closes_1h)
    feats.update(macro_feats or {})
    prob = probability(feats, None if model is False else model if model is not None else load_model())
    react, above, below = lad['reaction'], lad['above'], lad['below']
    buf = 0.25 * atr
    cost = (CONFIG.journal.fee_round_trip + 2 * CONFIG.levels.slippage_bps / 1e4) * price

    def rr(entry, stop, target):
        risk = abs(entry - stop)
        return round((abs(target - entry) - cost) / (risk + cost), 2) if risk else None

    long_entry = react['hi']
    long_stop = below[0]['lo'] - buf
    long_targets = [z['lo'] for z in above]
    short_entry = above[0]['lo']
    short_stop = (above[1]['hi'] if len(above) > 1 else above[0]['hi'] + atr) + buf
    short_targets = [react['hi'], below[0]['hi']] + ([below[1]['hi']] if len(below) > 1 else [])
    status = 'inside' if react['lo'] <= price <= react['hi'] else 'above' if price > react['hi'] else 'below'
    return {
        'price': price, 'atr_1h': atr, 'status': status,
        'reaction': react, 'above': above, 'below': below,
        'long': {'trigger': f"закрытие 1h выше {react['hi']:.6g} и ретест", 'entry': long_entry, 'stop': long_stop,
                 'targets': long_targets, 'rr': [rr(long_entry, long_stop, t) for t in long_targets]},
        'short': {'trigger': f"отказ от {above[0]['lo']:.6g}-{above[0]['hi']:.6g} (разворот на 15m)",
                  'entry': short_entry, 'stop': short_stop, 'targets': short_targets,
                  'rr': [rr(short_entry, short_stop, t) for t in short_targets]},
        'p_up_first': round(prob['p_up'], 3), 'p_source': prob['source'], 'features': feats,
    }


def label_first_touch(highs: Sequence[float], lows: Sequence[float], up: float, down: float) -> Optional[int]:
    """1 if `up` is touched before `down` in the candles, 0 if `down` first, None if neither (or both in one bar)."""
    for hi, lo in zip(highs, lows):
        hit_up, hit_dn = hi >= up, lo <= down
        if hit_up and hit_dn:
            return None
        if hit_up:
            return 1
        if hit_dn:
            return 0
    return None


def brier(p: Sequence[float], y: Sequence[int]) -> float:
    return sum((a - b) ** 2 for a, b in zip(p, y)) / max(1, len(y))


def logloss(p: Sequence[float], y: Sequence[int]) -> float:
    eps = 1e-6
    return -sum(b * math.log(max(eps, a)) + (1 - b) * math.log(max(eps, 1 - a)) for a, b in zip(p, y)) / max(1, len(y))
