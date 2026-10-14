"""
eng-104: ONE market regime per coin on the horizon of the trades (hours), replacing the eight scattered "trends"
(1h EMA20, daily EMA50 + 30/90/365-day momentum, weekly EMA, 4h ADX, ICT daily / weekly closes ...). The daily /
weekly reads lagged by weeks: 2026-10-14 BTC was 'bull' by them while it fell for a week inside an 8.6% 20-day range.

- direction of a timeframe (1h, 4h): market structure - the last two confirmed swing highs AND lows (fractal 2) both
  higher (+1) / both lower (-1) - agreeing with the EMA20 slope over 4 bars; else 0;
- the range: the high / low of the last 20 CLOSED days; `pos` = where the price sits in it (0 low .. 1 high);
- regime:
  'trend_up' / 'trend_down': 1h and 4h point the same way AND (ADX(14) of 4h >= 25 or the last 4h close is outside
  the 20-day range - the breakout already happened);
  'range': ADX(4h) < 25 and the price inside the 20-day range;
  'mixed': anything else.

Shadow use (SignalBook._enter): a trend / breakout setup in a range pointing at the range's near edge
('rg_breakout_in_range': buying the top / selling the bottom of a range), any setup against a trend
('rg_countertrend'). Journaled in `regime2` and shadow_veto, nothing is blocked until the journal shows it.
"""
from typing import Dict, Optional, Sequence

import numpy as np

# setups that need the move to continue / a breakout to hold, and setups that fade an extreme back into a range
TREND_MODES = ('continuation', 'pump', 'oi_signal', 'oi_build', 'breakout', 'orb')
RANGE_MODES = ('sweep', 'market_profile', 'bollinger', 'wyckoff', 'supply_demand', 'po3', 'connors', 'cascade')
EDGE = 0.25          # the outer quarter of the range is its edge


def _ema(x: np.ndarray, n: int) -> np.ndarray:
    k = 2 / (n + 1)
    out = np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = out[i - 1] + k * (x[i] - out[i - 1])
    return out


def direction(bars: Sequence[Sequence[float]]) -> int:
    """+1 / -1 / 0 of closed bars [ts, o, h, l, c, ...]: swing structure confirmed by the EMA20 slope."""
    if len(bars) < 30:
        return 0
    h = np.asarray([b[2] for b in bars], dtype=float)
    l = np.asarray([b[3] for b in bars], dtype=float)
    c = np.asarray([b[4] for b in bars], dtype=float)
    highs = [h[i] for i in range(2, len(h) - 2) if h[i] == h[i - 2:i + 3].max()]
    lows = [l[i] for i in range(2, len(l) - 2) if l[i] == l[i - 2:i + 3].min()]
    e = _ema(c, 20)
    slope = e[-1] - e[-5]
    if len(highs) >= 2 and len(lows) >= 2:
        if highs[-1] > highs[-2] and lows[-1] > lows[-2] and slope > 0:
            return 1
        if highs[-1] < highs[-2] and lows[-1] < lows[-2] and slope < 0:
            return -1
    return 0


def adx(bars: Sequence[Sequence[float]], n: int = 14) -> Optional[float]:
    if len(bars) < 3 * n:
        return None
    k = np.asarray([b[:5] for b in bars], dtype=float)
    h, l, c = k[:, 2], k[:, 3], k[:, 4]
    prev = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(abs(h - prev), abs(l - prev)))
    up, dn = h - np.concatenate(([h[0]], h[:-1])), np.concatenate(([l[0]], l[:-1])) - l
    pdm, mdm = np.where((up > dn) & (up > 0), up, 0.0), np.where((dn > up) & (dn > 0), dn, 0.0)

    def rma(x):
        out = np.full_like(x, np.nan)
        out[n - 1] = x[:n].mean()
        for i in range(n, len(x)):
            out[i] = (out[i - 1] * (n - 1) + x[i]) / n
        return out
    atr = rma(tr)
    pdi, mdi = 100 * rma(pdm) / atr, 100 * rma(mdm) / atr
    dx = np.nan_to_num(100 * abs(pdi - mdi) / np.maximum(pdi + mdi, 1e-12))
    return float(rma(dx)[-1])


def state(h1: Sequence, h4: Sequence, d1: Sequence, price: Optional[float]) -> Optional[Dict]:
    """The coin's regime from CLOSED 1h / 4h / daily bars and the current price; None without the history."""
    if len(d1) < 20 or len(h4) < 45 or len(h1) < 30 or not price:
        return None
    h1_dir, h4_dir = direction(h1), direction(h4)
    hi, lo = max(b[2] for b in d1[-20:]), min(b[3] for b in d1[-20:])
    pos = (price - lo) / (hi - lo) if hi > lo else 0.5
    a4 = adx(h4)
    outside = h4[-1][4] > hi or h4[-1][4] < lo
    if h1_dir and h1_dir == h4_dir and ((a4 is not None and a4 >= 25) or outside):
        regime = 'trend_up' if h1_dir > 0 else 'trend_down'
    elif a4 is not None and a4 < 25 and lo <= price <= hi:
        regime = 'range'
    else:
        regime = 'mixed'
    return {'regime': regime, 'h1': h1_dir, 'h4': h4_dir, 'adx4': None if a4 is None else round(a4, 1),
            'pos': round(pos, 3), 'range_hi': hi, 'range_lo': lo}


def verdict(st: Optional[Dict], mode: str, d: int) -> Optional[str]:
    """The shadow veto of a setup in this regime, None when it fits (or the regime is unknown / mixed)."""
    if not st:
        return None
    r = st['regime']
    if r == 'range' and mode in TREND_MODES and ((d > 0 and st['pos'] >= 1 - EDGE) or (d < 0 and st['pos'] <= EDGE)):
        return 'rg_breakout_in_range'
    if (r == 'trend_up' and d < 0) or (r == 'trend_down' and d > 0):
        return 'rg_countertrend'
    return None


def label(st: Optional[Dict]) -> Optional[str]:
    """A compact journal text: 'range pos 0.40 adx 23.6 h1 -1 h4 -1'."""
    if not st:
        return None
    return f"{st['regime']} pos {st['pos']:.2f} adx {st['adx4']} h1 {st['h1']:+d} h4 {st['h4']:+d}"
