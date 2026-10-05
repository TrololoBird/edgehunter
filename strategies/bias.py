"""
Top-down bias (HTF -> MTF -> LTF), the common ground of the sources (2026-10-05, the owner's rule "the higher
timeframe always comes first"; web-checked):
- Elder's triple screen: the long-term tide decides the side, the intermediate wave is a pullback AGAINST it (buy
  declines in an up tide), the short-term ripple times the entry; timeframes x5 apart.
- ICT top-down: monthly / weekly / daily / 4h give one bias - bullish = longs only, bearish = shorts only, neutral = no
  trade; an LTF setup against the HTF bias "is a trap, not a trade".
- Weinstein / Shannon: the higher timeframe's stage (base, markup, top, markdown) and its moving averages - longs in
  markup only.
- Time-series momentum (Moskowitz, Ooi & Pedersen 2012; crypto practice blends 1 / 3 / 12 months): the academic part.
- Ranges: mean reversion only inside a higher-timeframe range, from its edges, out at its middle.

State of one coin from its own candles (the last CLOSED ones):
- tsm: the sign mean of the 30 / 90 / 365-day returns (-1 .. +1), the momentum blend;
- w1: the weekly close vs the EMA20 of the weekly closes (+1 / -1);
- d1 / h4: +1 when the close is above the EMA50 and the EMA50 rose over 5 days / 6 candles, -1 mirrored, 0 else;
- adx4: ADX(14) of the 4h candles.
Bias:
- 'bull': tsm > 0 and the tide up - the daily trend for intraday methods (the 4h is their wave: a pullback against
  the tide is Elder's entry, not a veto), the weekly for daily methods (Connors, cup: the daily is their wave);
- 'bear': mirrored;
- 'range': d1 = 0 and adx4 < 25 (no daily trend, a non-trending 4h);
- 'conflict': anything else (the timeframes disagree: no trade - ICT's neutral).
"""
from typing import Dict, List, Optional, Sequence

import numpy as np

from strategies.ind_panel import ema

# the method's nature (how the bias gates it); the Turtles are the higher-timeframe rule themselves and stay free
TREND = ('continuation', 'orb', 'pump', 'cup_handle', 'oi_signal', 'po3')
WITH_BIAS = ('sweep', 'connors', 'supply_demand')        # trade a pullback / raid in the higher timeframe's direction
RANGE = ('market_profile', 'bollinger', 'wyckoff')       # range edges; in a trend only its direction
# trendline: a broken trendline signals a CHANGE of trend (Edwards & Magee) - gating it by the old trend contradicts
# the method (research/bias.md: its blocked trades +0.30R, the allowed -0.90R)
EXEMPT = ('breakout', 'trendline')


def _trend(closes: np.ndarray, slope_n: int) -> int:
    if len(closes) < 60:
        return 0
    e = ema(closes, 50)
    up, down = closes[-1] > e[-1] and e[-1] > e[-1 - slope_n], closes[-1] < e[-1] and e[-1] < e[-1 - slope_n]
    return 1 if up else -1 if down else 0


def _adx(k: np.ndarray, n: int = 14) -> Optional[float]:
    if len(k) < 3 * n:
        return None
    h, l, c = k[:, 2], k[:, 3], k[:, 4]
    prev = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(abs(h - prev), abs(l - prev)))
    up, dn = h - np.concatenate(([h[0]], h[:-1])), np.concatenate(([l[0]], l[:-1])) - l
    pdm, mdm = np.where((up > dn) & (up > 0), up, 0.0), np.where((dn > up) & (dn > 0), dn, 0.0)

    def rma(x):
        out = np.empty_like(x)
        out[:n] = np.nan
        out[n - 1] = x[:n].mean()
        for i in range(n, len(x)):
            out[i] = (out[i - 1] * (n - 1) + x[i]) / n
        return out
    atr = rma(tr)
    pdi, mdi = 100 * rma(pdm) / atr, 100 * rma(mdm) / atr
    dx = np.nan_to_num(100 * abs(pdi - mdi) / np.maximum(pdi + mdi, 1e-12))
    return float(rma(dx)[-1])


def state(d1: Sequence, h4: Sequence, w1: Sequence) -> Optional[Dict]:
    """The coin's higher-timeframe state from closed daily / 4h / weekly candles ([ts, o, h, l, c, ...], oldest
    first); None without enough daily history."""
    if len(d1) < 60 or len(h4) < 60:
        return None
    dk = np.asarray([r[:5] for r in d1], dtype=float)
    hk = np.asarray([r[:5] for r in h4], dtype=float)
    dc = dk[:, 4]
    rets = [dc[-1] / dc[-1 - n] - 1 for n in (30, 90, 365) if len(dc) > n]
    tsm = float(np.mean(np.sign(rets))) if rets else 0.0
    w = 0
    if len(w1) >= 21:
        wc = np.asarray([r[4] for r in w1], dtype=float)
        w = 1 if wc[-1] > ema(wc, 20)[-1] else -1
    return {'tsm': round(tsm, 3), 'w1': w, 'd1': _trend(dc, 5), 'h4': _trend(hk[:, 4], 6), 'adx4': _adx(hk),
            'range_hi': float(dk[-20:, 2].max()), 'range_lo': float(dk[-20:, 3].min())}


# daily-timeframe methods: their wave is the daily chart, their tide the momentum blend and the week
DAILY = ('connors', 'cup_handle')


def bias_of(st: Optional[Dict], daily_method: bool = False) -> Optional[str]:
    """The tide (Elder): the momentum blend and the daily trend for intraday methods - the 4h is their WAVE and may
    run against the tide (a pullback is the entry, not a veto); for daily methods the momentum blend and the week, the
    daily being their wave."""
    if not st:
        return None
    tide = st['w1'] if daily_method else st['d1']
    if st['tsm'] > 0 and tide == 1:
        return 'bull'
    if st['tsm'] < 0 and tide == -1:
        return 'bear'
    if not daily_method and st['d1'] == 0 and st['adx4'] is not None and st['adx4'] < 25:
        return 'range'
    return 'conflict'


def gate(strategy: str, direction: int, coin_bias: Optional[str], btc_bias: Optional[str],
         is_btc: bool) -> Optional[str]:
    """The veto reason of an entry against the top-down bias, None when allowed (also when the bias is unknown:
    missing data is no veto)."""
    if strategy in EXEMPT or coin_bias is None:
        return None
    side = 'bull' if direction > 0 else 'bear'
    other = 'bear' if direction > 0 else 'bull'
    if not is_btc and btc_bias == other:
        return 'btc_bias'                                  # the market first: no altcoin trade against BTC's bias
    if coin_bias == 'conflict':
        return 'htf_conflict'
    if strategy in TREND or strategy in WITH_BIAS:
        return None if coin_bias == side else 'htf_bias'
    if strategy in RANGE:
        return None if coin_bias in ('range', side) else 'htf_bias'
    return None if coin_bias == side else 'htf_bias'


def range_mid(st: Optional[Dict]) -> Optional[float]:
    """The middle of the 20-day range (a range trade's objective: out at the middle)."""
    if not st:
        return None
    return (st['range_hi'] + st['range_lo']) / 2


def describe(st: Optional[Dict], bias: Optional[str]) -> Dict:
    return {'bias': bias, **({k: st[k] for k in ('tsm', 'w1', 'd1', 'h4')} if st else {}),
            'adx4': round(st['adx4'], 1) if st and st.get('adx4') is not None else None}


def closed(rows: List, period_ms: int, now_ms: float) -> List:
    """The candles closed by now (the last one may be the forming one)."""
    return [r for r in rows if r[0] + period_ms <= now_ms]
