"""
Support / resistance from where price actually turned (eng-75, the owner: "you don't understand what support and
resistance are and what forms them"; web-checked 2026-10-08: Fidelity, Investing.com, Capital.com, Dukascopy,
Wealthsimple, FTMO, Traders Agency).

What forms a level, by the sources:
- price reversed there: a swing high / low is where supply and demand changed hands (old highs resist, old lows
  support);
- memory: traders trapped at that price exit at breakeven when it returns, those who missed it buy / sell there -
  hence ROLE REVERSAL: a broken support resists from below, a broken resistance supports from above;
- strength: how many times price reacted there, how big the reaction was (size and duration), the volume on the
  touches, the timeframe (4h / daily / weekly outweigh 1h) and recency; touches alone are not enough (FTMO: a level
  tested too often may be weaker - orders rest behind it), the quality of the reaction counts.

So a zone here is a CLUSTER OF SWING PIVOTS of the 1h / 4h / daily candles, not a catalogue of constructs:
- pivots: fractal swings (the candle's high above `width` neighbours on both sides; lows mirrored), each with its
  reaction (the largest move away in the next `react_bars` candles, in that timeframe's ATR) and its volume
  (the candle's volume / the median of the 20 before);
- pivots within `tol` of each other (by price) form one zone, its band = the pivots' wicks (at most `max_width`);
- touches = pivots + the later 1h candles that wicked into the band and closed back out on the side they came
  from (rejections); flip = the cluster holds both swing highs and swing lows (the level changed role);
- strength = sum over the pivots of tf weight x (1 + reaction, capped) x volume factor x recency decay, plus half a
  point per rejection. The weights are hypotheses - research_sr.py measures whether these zones hold price better
  than placebo prices before anything trades on them.
"""
from typing import Dict, List, Optional, Sequence

import numpy as np

HOUR_MS = 3_600_000
TF_MS = {'1h': HOUR_MS, '4h': 4 * HOUR_MS, '1d': 24 * HOUR_MS}
TF_WEIGHT = {'1h': 1.0, '4h': 2.0, '1d': 4.0}          # sources: higher timeframes carry more weight (a hypothesis)


def _atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int = 14) -> np.ndarray:
    prev = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - prev), abs(l - prev)))
    # Wilder's ATR (the bot's one ATR, levels.atr_of); the first candle has no previous close: from the second on
    from strategies.ind_panel import rma
    out = np.full(len(tr), np.nan)
    if len(tr) > 1:
        out[1:] = rma(tr[1:].astype(float), n)
    return out


def pivots(candles: Sequence[Sequence[float]], tf: str, width: int = 2, react_bars: int = 10,
           until_ms: Optional[float] = None) -> List[Dict]:
    """Confirmed fractal swings of [ts, o, h, l, c, v] candles (a pivot needs `width` closed candles after it)."""
    a = np.asarray([r[:6] for r in candles], dtype=float)
    if until_ms is not None:
        a = a[a[:, 0] + TF_MS[tf] <= until_ms]
    if len(a) < 2 * width + 15:
        return []
    ts, o, h, l, c, v = a.T
    atr = _atr(h, l, c)
    out = []
    for i in range(width, len(a) - width):
        if not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        win = slice(i - width, i + width + 1)
        med = np.median(v[max(0, i - 20):i]) if i >= 5 else 0.0
        vol = float(v[i] / med) if med > 0 else 1.0
        after = slice(i + 1, min(len(a), i + 1 + react_bars))
        if h[i] == h[win].max() and (h[i] > h[i - width:i]).all() and (h[i] >= h[i + 1:i + width + 1]).all():
            react = (h[i] - l[after].min()) / atr[i] if after.stop > after.start else 0.0
            out.append({'ts': ts[i], 'price': h[i], 'body': max(o[i], c[i]), 'side': 1, 'tf': tf,
                        'react': float(react), 'vol': vol, 'react_full': after.stop - after.start >= react_bars})
        if l[i] == l[win].min() and (l[i] < l[i - width:i]).all() and (l[i] <= l[i + 1:i + width + 1]).all():
            react = (h[after].max() - l[i]) / atr[i] if after.stop > after.start else 0.0
            out.append({'ts': ts[i], 'price': l[i], 'body': min(o[i], c[i]), 'side': -1, 'tf': tf,
                        'react': float(react), 'vol': vol, 'react_full': after.stop - after.start >= react_bars})
    return out


def zones(candles: Dict[str, Sequence[Sequence[float]]], now_ms: float, tol: float, max_width: float,
          half_life_days: float = 30.0, lookback_days: Dict[str, float] = None, min_react: float = 1.0) -> List[Dict]:
    """
    S/R zones from the pivots of the given timeframes ({'1h': [...], '4h': [...], '1d': [...]}), as of now_ms.
    tol: the price distance within which pivots are one place; max_width: the band's widest.
    """
    lookback_days = lookback_days or {'1h': 10, '4h': 45, '1d': 120}
    piv: List[Dict] = []
    for tf, rows in candles.items():
        if not rows or tf not in TF_MS:
            continue
        # a turn counts when price then moved away at least 1 ATR of that timeframe (Fidelity: 'the more significant
        # the bounce, the more important the level') - every 2-candle fractal of a range was a 'level'
        piv += [p for p in pivots(rows, tf, until_ms=now_ms)
                if p['ts'] >= now_ms - lookback_days[tf] * 86_400_000 and p['react'] >= min_react]
    if not piv:
        return []
    piv.sort(key=lambda p: p['price'])
    groups: List[List[Dict]] = [[piv[0]]]
    for p in piv[1:]:
        g = groups[-1]
        if p['price'] - g[0]['price'] <= tol and p['price'] - g[0]['price'] <= max_width:
            g.append(p)
        else:
            groups.append([p])
    h1 = np.asarray([r[:6] for r in candles.get('1h') or []], dtype=float)
    h1 = h1[h1[:, 0] + HOUR_MS <= now_ms] if len(h1) else h1
    out = []
    for g in groups:
        lo, hi = min(p['price'] for p in g), max(p['price'] for p in g)
        if hi - lo < 0.25 * tol:
            # a single place: the band reaches from the wick toward the bodies, a quarter of the tolerance
            mid = (lo + hi) / 2
            lo, hi = mid - 0.125 * tol, mid + 0.125 * tol
        # eng-168n (audit #3): the zone's STRUCTURE (its pivots: timeframe, volume, age; the strongest first move once)
        # apart from its REACTIONS after it formed - the reaction was counted three times (the react >= 1 filter, the
        # (1 + react) factor per pivot, +0.5 per wick back incl. the pivots' own bars) and breaks through were free
        base, sides = 0.0, set()
        for p in g:
            age_d = max(0.0, (now_ms - p['ts']) / 86_400_000)
            decay = 0.5 ** (age_d / half_life_days)
            vol = 0.75 + 0.25 * min(p['vol'], 3.0)            # 1.0 at an average candle, 1.5 at 3x volume
            base += TF_WEIGHT[p['tf']] * vol * decay
            sides.add(p['side'])
        structure = base * (1.0 + 0.15 * min(max(p['react'] for p in g), 5.0))
        first = min(p['ts'] for p in g)
        stats = reaction_stats(h1, lo, hi, first, g)
        rejections = stats['rejections']
        chop = 0.65 if stats['approaches'] >= 3 and stats['breaks'] > rejections else 1.0
        strength = (structure + 0.5 * min(rejections, 5)) * chop
        if len(g) == 1 and g[0]['tf'] == '1h' and g[0]['react'] < 2.0 and rejections == 0:
            continue                                   # one minor 1h turn, never revisited: not a level
        out.append({'lo': lo, 'hi': hi, 'price': (lo + hi) / 2, 'touches': len(g) + rejections,
                    'pivots': len(g), 'rejections': rejections, 'flip': len(sides) == 2,
                    'structure_score': round(structure, 2), 'reaction_stats': stats,
                    # eng-169 (audit #9): a pivot younger than its 10-bar reaction window - its reaction is preliminary
                    'fresh': any(not p.get('react_full', True) for p in g),
                    'tfs': sorted({p['tf'] for p in g}, key=list(TF_MS).index),
                    'react': max(p['react'] for p in g), 'last_ts': max(p['ts'] for p in g),
                    'strength': strength})
    return out


def reaction_stats(h1: np.ndarray, lo: float, hi: float, first_ms: float, group: List[Dict]) -> Dict:
    """eng-168n: how price met the band [lo, hi] on the closed 1h candles AFTER its first pivot, the pivots' own bars
    (within one candle of their timeframe) left out. An approach starts on a candle that came from outside (the
    previous close beyond one edge) and traded into the band; it ends on the first close outside: back on the
    approach side = a rejection, beyond the far edge = a break (closes inside keep it open). max_pierce_atr: the deepest
    wick past the near edge on a rejection (max_pierce_on_rejection), in ATR14(1h)."""
    out = {'approaches': 0, 'rejections': 0, 'breaks': 0, 'hold_rate': None, 'max_pierce_atr': None}
    if not len(h1):
        return out
    atr = _atr(h1[:, 2], h1[:, 3], h1[:, 4])
    skip = [(p['ts'], TF_MS[p['tf']]) for p in group]
    prev_close, side, deepest = None, 0, 0.0           # side: +1 an approach from above, -1 from below, 0 none open
    pierce = []
    for k in range(len(h1)):
        r = h1[k]
        if r[0] <= first_ms or any(abs(r[0] - t) <= w for t, w in skip):
            prev_close = r[4]
            continue
        if side == 0 and prev_close is not None:
            if prev_close > hi and r[3] <= hi:
                side, deepest = 1, hi - r[3]
                out['approaches'] += 1
            elif prev_close < lo and r[2] >= lo:
                side, deepest = -1, r[2] - lo
                out['approaches'] += 1
        elif side:
            deepest = max(deepest, (hi - r[3]) if side > 0 else (r[2] - lo))
        if side:
            if (side > 0 and r[4] > hi) or (side < 0 and r[4] < lo):
                out['rejections'] += 1
                a = atr[k] if np.isfinite(atr[k]) and atr[k] > 0 else None
                if a:
                    pierce.append(float(deepest / a))
                side = 0
            elif (side > 0 and r[4] < lo) or (side < 0 and r[4] > hi):
                out['breaks'] += 1
                side = 0
        prev_close = r[4]
    # eng-168o (audit #4): the window the statistics actually cover (the loaded 1h history may start after the
    # zone's first pivot - a daily pivot can be 120 days old, the 1h list ~20 days)
    out['from_ms'] = int(max(first_ms, h1[0, 0]))
    if out['approaches']:
        out['hold_rate'] = round(out['rejections'] / out['approaches'], 2)
    if pierce:
        out['max_pierce_atr'] = round(float(max(pierce)), 2)
    return out
