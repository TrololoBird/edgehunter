"""
Cup with handle (William O'Neil, "How to Make Money in Stocks"; statistics: Thomas Bulkowski, "Encyclopedia of Chart
Patterns"), on 1h and 4h candles at their close:

- a prior advance of >= 30% into the left rim (the lowest low of the 2x cup-length before it to the rim);
- the cup: a U-shaped bottom (not a V: >= 20% of its candles in its lowest quarter), 12-50% deep (O'Neil 12-33%,
  up to ~50% in volatile markets), 20..300 candles, the right rim within 5% of the left one;
- the handle after the right rim: 3 .. cup/4 candles, drifting in the cup's UPPER half and no deeper than 12% of the
  rim, on lower volume than the cup's;
- the entry: the first close above the handle's high (the pivot) on >= 1.4x the average volume (O'Neil: +40-50%).
- stop below the handle's low; target the pivot + the cup's depth (Bulkowski's measured move); O'Neil's own rule
  (cut losses at 7-8%, take 20-25%) is a ~3:1 reward / risk - the strategy's minimum R:R.
"""
from typing import Dict, List, Optional, Sequence

from strategies.base import PlanInput, Strategy
from strategies.maniac_strategies import _System, _confirm_plan  # noqa: F401  (_System: the gate key)


def _pivots_high(h: List[float], k: int = 3) -> List[int]:
    return [i for i in range(k, len(h) - k) if h[i] == max(h[i - k:i + k + 1])]


def cup_handle(candles: Sequence[Sequence[float]], tf: str, period_ms: int) -> Optional[Dict]:
    """The breakout of a cup with handle on the candle that just closed ([ts, o, h, l, c, quote_vol]), else None."""
    n = len(candles)
    if n < 60:
        return None
    h = [c[2] for c in candles]
    l = [c[3] for c in candles]
    c = [c_[4] for c_ in candles]
    v = [c_[5] for c_ in candles]
    last = n - 1
    avg_vol = sum(v[-51:-1]) / 50 if n > 51 else sum(v[:-1]) / max(1, n - 1)
    if not avg_vol or v[last] < 1.4 * avg_vol:
        return None
    pivots = _pivots_high(h[:-1])
    for r in reversed(pivots):                       # the right rim: the handle starts after it
        handle = list(range(r + 1, last))
        for left in reversed([p for p in pivots if p < r]):
            cup_len = r - left
            if not 20 <= cup_len <= 300:
                continue
            if abs(h[r] / h[left] - 1) > 0.05:
                continue
            rim = min(h[left], h[r])
            bottom = min(l[left:r + 1])
            depth = (rim - bottom) / rim
            if not 0.12 <= depth <= 0.50:
                continue
            quarter = bottom + 0.25 * (rim - bottom)
            if sum(1 for i in range(left, r + 1) if l[i] <= quarter) < 0.2 * cup_len:
                continue                             # a V, not a U
            before = l[max(0, left - 2 * cup_len):left]
            if not before or h[left] / min(before) - 1 < 0.30:
                continue                             # no prior advance
            if not 3 <= len(handle) <= max(3, cup_len // 4):
                break
            h_lo = min(l[i] for i in handle)
            pivot = max(h[i] for i in [r] + handle)
            if h_lo < (rim + bottom) / 2 or (pivot - h_lo) / pivot > 0.12:
                break                                # the handle fell into the lower half / too deep
            cup_vol = sum(v[left:r + 1]) / (cup_len + 1)
            if sum(v[i] for i in handle) / len(handle) >= cup_vol:
                break                                # volume did not dry up in the handle
            if not (c[last] > pivot >= c[last - 1]):
                return None
            target = pivot + (rim - bottom)
            return {'setup': 'CUP HANDLE', 'direction': 1,
                    'setup_note': f"{tf} cup with handle: rims {h[left]:.6g} / {h[r]:.6g}, depth {depth:.0%} over "
                                  f"{cup_len} candles, handle {len(handle)} candles to {h_lo:.6g}; closed above the "
                                  f"pivot {pivot:.6g} on {v[last] / avg_vol:.1f}x volume (O'Neil)",
                    'anchor_level': pivot, 'anchor_extreme': h_lo, 'anchor_label': f'{tf} cup-with-handle pivot',
                    'anchor_ts': int(candles[left][0]), 'anchor_close': c[last], 'ch_stop': h_lo,
                    'ch_target': target, 'ch_tf': tf, 'event_ts': int(candles[last][0]) + period_ms}
    return None


class CupHandleStrategy(_System):
    """O'Neil's cup with handle: entry at the breakout close, stop below the handle, target the measured move."""
    name = 'cup_handle'
    setups = {'CUP HANDLE': 1}
    ttl_key = 'cup_ttl'
    min_rr = 3.0                                     # O'Neil: cut at 7-8%, take 20-25%

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig = x.sig
        if sig.get('ch_stop') is None:
            return None
        exit = {'stop': ['price', sig['ch_stop']], 'stop_src': 'below the handle (O\'Neil)',
                'tp': ['level', sig['ch_target'], 0.0, None], 'tp_src': 'the cup depth from the pivot (Bulkowski)',
                'atr': x.atr}
        return _confirm_plan(x, self.name, sig.get('ch_tf', '1h'), exit, 'close above the handle pivot on volume')


__all__ = ['cup_handle', 'CupHandleStrategy', 'Strategy']
