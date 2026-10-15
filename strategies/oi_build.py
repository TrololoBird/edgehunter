"""
OI build (eng-127): Martin Pring's open-interest rules (as summarized from his writing) - "prices rising and open
interest increasing at a rate faster than its average = bullish", prices falling with open interest rising faster
than its average = bearish (new positions behind the move). A formula without our thresholds:

- at each 5m close, the 1h OI change (Binance, the 5-minute OI series of the last day) is above the MEAN of the
  day's 1h OI changes and above zero, and the 1h price change has the trade's sign;
- in at that close, the stop beyond the hour's extreme + the measured pierce, targets the opposite liquidity on the map.

No study shows OI changes predict crypto perpetual returns (and Binance's reported OI is known to be misquoted at
times, arXiv 2310.14973), so the setup is journaled in SHADOW only ('oi_shadow': SignalBook) until its own rows show
an edge. Replaces the OI robots of eng-56 / eng-88 (cryptomillion's OI [15m] alert and our +5% / VWAP / ER floors).
"""
from typing import Dict, Optional, Sequence

from strategies.base import PlanInput, Strategy

MINUTE_MS = 60_000


def _oi_change(samples: Sequence, now_ms: int, minutes: int) -> Optional[float]:
    """The OI change over `minutes`, None without a sample within 3 minutes of that time (eng-74: the last sample
    before it was taken whatever its age - after a feed gap NEAR's '15m' and '1h' changes were both +4.68% against an
    OI that Binance's own history shows flat, and the trade entered on it)."""
    if not samples:
        return None
    target = now_ms - minutes * MINUTE_MS
    old = [(t, v) for t, v in samples if t <= target]
    if not old or not old[-1][1] or target - old[-1][0] > 3 * MINUTE_MS or now_ms - samples[-1][0] > 3 * MINUTE_MS:
        return None
    return samples[-1][1] / old[-1][1] - 1


def _close_at(minutes: Sequence[Sequence[float]], ts_ms: int) -> Optional[float]:
    """The close of the 1m candle that opened at ts_ms (a gap there -> None: no move measured across a hole)."""
    for c in reversed(minutes):
        if c[0] == ts_ms:
            return c[4]
        if c[0] < ts_ms:
            return None
    return None


def oi_build(minutes: Sequence[Sequence[float]], oi_5m: Sequence, now_ms: int) -> Optional[Dict]:
    """minutes: final 1m candles; oi_5m: (ts_ms, OI) one sample per 5 minutes over the last day."""
    oi = [(int(t), float(v)) for t, v in oi_5m if v]
    if len(oi) < 13 * 2 or len(minutes) < 61:
        return None
    if now_ms - oi[-1][0] > 10 * MINUTE_MS:
        return None                            # the OI feed stalled: no reading
    changes = [oi[k][1] / oi[k - 12][1] - 1 for k in range(12, len(oi))
               if 55 * MINUTE_MS <= oi[k][0] - oi[k - 12][0] <= 65 * MINUTE_MS]
    if len(changes) < 12:
        return None
    now_chg, mean = changes[-1], sum(changes) / len(changes)
    if not (now_chg > 0 and now_chg > mean):
        return None
    last = minutes[-1]
    t0 = int(last[0])
    c60 = _close_at(minutes, t0 - 60 * MINUTE_MS)
    if c60 is None:
        return None
    p60 = last[4] / c60 - 1
    if p60 == 0:
        return None
    d = 1 if p60 > 0 else -1
    hour = [c for c in minutes if c[0] > t0 - 60 * MINUTE_MS]
    extreme = min(c[3] for c in hour) if d > 0 else max(c[2] for c in hour)
    return {'setup': 'OI BUILD LONG' if d > 0 else 'OI BUILD SHORT', 'direction': d,
            'setup_note': f"price 1h {p60:+.2%} with OI 1h {now_chg:+.2%} above its 24h average {mean:+.2%} "
                          f"(Pring: open interest rising faster than its average), shadow",
            'anchor_level': last[4], 'anchor_extreme': extreme, 'anchor_label': 'OI build (Pring)',
            'anchor_ts': t0, 'anchor_close': last[4], 'oi_build_oi60': now_chg, 'oi_build_mean': mean,
            'oi_build_p60': p60, 'event_ts': t0 + MINUTE_MS}


class OiBuildStrategy(Strategy):
    name = 'oi_build'
    anchor_type = 'level'
    setups = {'OI BUILD LONG': 1, 'OI BUILD SHORT': -1}
    ttl_key = 'oi_build_ttl'
    time_exit = 'fixed'
    default_tf = '15m'

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('anchor_ts'), 'oi_build') if x.sig.get('oi_build_oi60') is not None else None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        from strategies.maniac_strategies import _confirm_plan
        if x.sig.get('oi_build_oi60') is None:
            return None
        exit = {'stop': ['ref', 0.0], 'tp': ['map', 0.0], 'atr': x.atr,
                'stop_src': "beyond the hour's extreme", 'tp_src': 'the opposite liquidity'}
        return _confirm_plan(x, self.name, '15m', exit, "Pring: price and OI (faster than its average) together",
                             stop_ref=x.sig['anchor_extreme'], intent='opposite_liquidity')
