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
    out = np.full(len(tr), np.nan)
    if len(tr) >= n:
        cs = np.cumsum(tr)
        out[n - 1:] = (cs[n - 1:] - np.r_[0.0, cs[:-n]]) / n
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
                        'react': float(react), 'vol': vol})
        if l[i] == l[win].min() and (l[i] < l[i - width:i]).all() and (l[i] <= l[i + 1:i + width + 1]).all():
            react = (h[after].max() - l[i]) / atr[i] if after.stop > after.start else 0.0
            out.append({'ts': ts[i], 'price': l[i], 'body': min(o[i], c[i]), 'side': -1, 'tf': tf,
                        'react': float(react), 'vol': vol})
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
        strength, sides = 0.0, set()
        for p in g:
            age_d = max(0.0, (now_ms - p['ts']) / 86_400_000)
            decay = 0.5 ** (age_d / half_life_days)
            vol = 0.75 + 0.25 * min(p['vol'], 3.0)            # 1.0 at an average candle, 1.5 at 3x volume
            strength += TF_WEIGHT[p['tf']] * (1 + min(p['react'], 5.0)) * vol * decay
            sides.add(p['side'])
        first = min(p['ts'] for p in g)
        rejections = 0
        if len(h1):
            later = h1[h1[:, 0] > first]
            piv_ts = {p['ts'] for p in g if p['tf'] == '1h'}
            prev_close, counted = None, False
            for r in later:
                # a rejection: the candle came from OUTSIDE (the previous close on one side), wicked into the band and
                # closed back out on that side; consecutive ones are one episode (a range's candles crossing the band
                # back and forth counted 20-29 'touches' everywhere)
                hit = False
                if prev_close is not None and r[0] not in piv_ts:
                    from_above = prev_close > hi and r[3] <= hi and r[4] > hi
                    from_below = prev_close < lo and r[2] >= lo and r[4] < lo
                    hit = from_above or from_below
                if hit and not counted:
                    rejections += 1
                counted = hit
                prev_close = r[4]
        strength += 0.5 * rejections
        if len(g) == 1 and g[0]['tf'] == '1h' and g[0]['react'] < 2.0 and rejections == 0:
            continue                                   # one minor 1h turn, never revisited: not a level
        out.append({'lo': lo, 'hi': hi, 'price': (lo + hi) / 2, 'touches': len(g) + rejections,
                    'pivots': len(g), 'rejections': rejections, 'flip': len(sides) == 2,
                    'tfs': sorted({p['tf'] for p in g}, key=list(TF_MS).index),
                    'react': max(p['react'] for p in g), 'last_ts': max(p['ts'] for p in g),
                    'strength': strength})
    return out
