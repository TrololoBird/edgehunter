"""
OI build (eng-88, OI BUILD LONG): open interest building fast while price already moves up - the regime the live
journal of 11-13.10 measured as pump-prone (OI 1h > +5%: a >= 10% rise within 4h in 14.7% of cases vs 1.3% for all
coins), but with NO direction on average (-2.5% against the market over 4h: the pumps give it back). So the trade is
momentum with a tight percentage trailing stop, not a hold: in, the stop trailed oi_build_trail behind the best price,
out at the latest after the TTL. The minute study had +0.94% a trade on 26 trades only, and the result was fragile to
the trail width: this is a LIVE TEST on the demo, judged by its own journal rows.

Detection on every final 1m candle, once per coin per hour: Binance OI over 60 minutes >= oi_build_oi_1h AND price
over 60 minutes >= oi_build_price_1h; OI over 15 minutes still rising (the build is running, not over).

eng-90, after the live S trade of 13.10 (entered 12:10 at the top of a +11% hour, 2 minutes after it poked the previous
day's high, stopped in 30 s by a 2% stop inside one 15m candle of 5%, the high was a sweep):
- not extended: price at most oi_build_max_vwap_atr x ATR(15m) above the day's VWAP (breakout scorers rank a break far
  from VWAP in ATR units lower; an ADR% beyond 100% is 'overextended');
- the previous day's high: above it only after a CLOSED 5m candle above it (PDH sweep vs breakout: a sweep closes
  back inside; eng-91: 5m instead of the scripts' 15m - see oi_build());
- stop and trail: oi_build_trail_atr x ATR(5m) behind the best price, at least oi_build_trail (a chandelier exit: a
  volatility-scaled trail instead of one percentage in a calm market and a storm alike).
"""
from typing import Dict, Optional, Sequence

from config import CONFIG
from strategies.base import PlanInput, Strategy
from strategies.oi_signal import MINUTE_MS, _close_at, _oi_change


def _atr(bars: Sequence[Sequence[float]], n: int = 14) -> Optional[float]:
    if len(bars) < 3:
        return None
    trs = [max(b[2] - b[3], abs(b[2] - a[4]), abs(b[3] - a[4])) for a, b in zip(bars, bars[1:])][-n:]
    return sum(trs) / len(trs)


def _day_vwap(minutes: Sequence[Sequence[float]], now_ms: int) -> Optional[float]:
    """The UTC day's VWAP from the 1m candles kept (typical price weighted by quote volume; the buffer holds 10h, so
    late in the day it is the last 10 hours')."""
    day0 = now_ms // 86_400_000 * 86_400_000
    day = [c for c in minutes if c[0] >= day0 and c[5]]
    w = sum(c[5] for c in day)
    return sum((c[2] + c[3] + c[4]) / 3 * c[5] for c in day) / w if w else None


def oi_build(minutes: Sequence[Sequence[float]], oi_samples: Sequence, now_ms: int,
             m15: Sequence[Sequence[float]] = (), pdh: Optional[float] = None) -> Optional[Dict]:
    cfg = CONFIG.strategies
    if len(minutes) < 61 or len(oi_samples) < 20:
        return None
    oi15, oi60 = _oi_change(oi_samples, now_ms, 15), _oi_change(oi_samples, now_ms, 60)
    if oi15 is None or oi60 is None or oi60 < cfg.oi_build_oi_1h or oi15 <= 0:
        return None
    last = minutes[-1]
    t0 = int(last[0])
    c60 = _close_at(minutes, t0 - 60 * MINUTE_MS)
    c15 = _close_at(minutes, t0 - 15 * MINUTE_MS)
    if c60 is None or c15 is None:
        return None
    p60, p15 = last[4] / c60 - 1, last[4] / c15 - 1
    if p60 < cfg.oi_build_price_1h:
        return None
    price = last[4]
    # eng-91: a directional start, not a pump-and-dump chop (+-5-10% back and forth, live S 13.10: 0.0562 -> 0.0635 ->
    # 0.0604 within the hour): Kaufman's efficiency ratio of the last 60 one-minute closes (net move / the sum of the
    # minute moves; a trend reads >= ~0.3, a chop near 0) at least oi_build_min_er
    closes = [c[4] for c in minutes if c[0] > t0 - 61 * MINUTE_MS]
    path = sum(abs(b - a) for a, b in zip(closes, closes[1:]))
    er = abs(closes[-1] - closes[0]) / path if path else 0.0
    if er < cfg.oi_build_min_er:
        return None
    # eng-90: not extended - at most oi_build_max_vwap_atr ATR(15m) above the day's VWAP
    atr15 = _atr(list(m15)[-15:])
    vwap = _day_vwap(minutes, now_ms)
    if not atr15 or not vwap:
        return None
    ext = (price - vwap) / atr15
    if ext > cfg.oi_build_max_vwap_atr:
        return None
    from levels import resample
    bars5 = resample([c for c in minutes if c[0] > t0 - 75 * MINUTE_MS], 5, t0 + MINUTE_MS)
    # eng-91: above the previous day's high only after a CLOSED 5m candle above it. eng-90 waited for a 15m close (the
    # intraday PDH scripts' default, made for trades held for hours): up to 15 minutes of a move that fades within
    # 15-60 minutes. The 15m state is journaled beside it (pdh15) so the live data can tell which one was right
    pdh5 = pdh15 = None
    if pdh and price > pdh:
        pdh5 = bool(bars5) and bars5[-1][4] > pdh
        pdh15 = bool(m15) and m15[-1][4] > pdh
        if not pdh5:
            return None
    # eng-90: the trail / stop distance in the coin's own 5m volatility (a chandelier), at least oi_build_trail
    atr5 = _atr(bars5)
    trail = max(cfg.oi_build_trail, cfg.oi_build_trail_atr * atr5 / price) if atr5 else cfg.oi_build_trail
    return {'setup': 'OI BUILD LONG', 'direction': 1,
            'setup_note': f"OI 1h {oi60:+.2%} / 15m {oi15:+.2%}, price 1h {p60:+.2%} / 15m {p15:+.2%}, "
                          f"{ext:+.1f} ATR(15m) from the day's VWAP, ER(60m) {er:.2f}"
                          f"{'' if pdh5 is None else f', above PDH: 5m close yes, 15m close {"yes" if pdh15 else "no"}'}"
                          f" (OI build, momentum with a {trail:.1%} trailing "
                          f"stop, live test)",
            'anchor_level': last[4], 'anchor_extreme': last[4] * (1 - trail), 'anchor_label': 'OI build',
            'anchor_ts': t0, 'anchor_close': last[4], 'oi_build_oi60': oi60, 'oi_build_p60': p60,
            'oi_build_trail': trail, 'oi_build_ext': ext, 'oi_build_pdh15': pdh15, 'oi_build_er': er,
            'event_ts': t0 + MINUTE_MS}


class OiBuildStrategy(Strategy):
    name = 'oi_build'
    anchor_type = 'level'
    setups = {'OI BUILD LONG': 1}
    ttl_key = 'oi_build_ttl'
    time_exit = 'fixed'
    default_tf = '15m'

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('anchor_ts'), 'oi_build') if x.sig.get('oi_build_oi60') is not None else None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        from strategies.maniac_strategies import _confirm_plan
        if x.sig.get('oi_build_oi60') is None:
            return None
        pct = x.sig.get('oi_build_trail') or CONFIG.strategies.oi_build_trail
        exit = {'stop': ['price', x.sig['anchor_close'] * (1 - pct)], 'stop_src': f'{pct:.1%} below the entry (3 ATR 5m, >= 2%)',
                'tp': ['trail'], 'tp_src': f'none: a {pct:.1%} trailing stop', 'atr': x.atr}
        plan = _confirm_plan(x, self.name, '15m', exit, 'OI build: OI and price rising together')
        if plan and not plan.get('skip'):
            plan.update(no_tp=True, trail_pct=pct, be_after_r=None, trail_after_tp1=False)
        return plan
