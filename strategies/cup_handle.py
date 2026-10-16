"""
Cup with handle (William O'Neil, "How to Make Money in Stocks"; statistics: Thomas Bulkowski, "Encyclopedia of Chart
Patterns"), on DAILY candles at the UTC day's close (eng-58; was 1h / 4h):

- a prior advance of >= 30% into the left rim (the lowest low of the 2x cup-length before it to the rim);
- the cup: 12-33% deep (O'Neil; eng-58, was up to 50%), 49..455 daily candles (his 7 .. 65 weeks: crypto trades 7
  days a week - audit 2026-10-16: 35 candles were 5 calendar weeks); rounded, not a V - OUR approximation of his U
  (he gives no number): >= cup_u_share of the cup's candles have their low in the cup's bottom third;
- the handle after the right rim: 7 days (O'Neil: at least one to two weeks) .. 56 candles, drifting in the cup's UPPER half and no deeper than 12% of the
  rim, on lower volume than the cup's;
- the entry: the first close above the handle's high (the pivot) on >= 1.4x the average volume (O'Neil: +40-50%).
- stop below the handle's low; TP1 the pivot + 61% of the depth, TP2 + the full depth (Bulkowski's measure rule); O'Neil's own rule
  (cut losses at 7-8%, take 20-25%) is an exit rule, not an entry filter: the stop is the nearer of the handle's low
  and 8% below the entry, the minimum R:R to the measured target is 1. The 8% is a hard limit (audit C06): a stop the
  common ATR floor / pool clearing would push farther rejects the entry instead of widening it.
"""
from typing import Dict, List, Optional, Sequence

from config import CONFIG
from strategies.base import PlanInput, Strategy
from strategies.maniac_strategies import _System, _confirm_plan  # noqa: F401  (_System: the gate key)


CUP_U_SHARE = 0.20                 # audit 2026-10-16: our U-vs-V rule (no source number), journaled with the setup


def _pivots_high(h: List[float], k: int = 3) -> List[int]:
    return [i for i in range(k, len(h) - k) if h[i] == max(h[i - k:i + k + 1])]


def cup_handle(candles: Sequence[Sequence[float]], tf: str, period_ms: int, skips: Optional[List] = None) -> Optional[Dict]:
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
            if not 49 <= cup_len <= 455:
                continue
            rim = min(h[left], h[r])
            bottom = min(l[left:r + 1])
            depth = (rim - bottom) / rim
            if not 0.12 <= depth <= 0.33:
                continue
            # eng-118: the rims within 5% and the U-vs-V quarter count were ours (O'Neil gives no numbers): removed - the
            # shape is held by his depth 12-33%, the 30% prior advance and the handle in the upper half <= 12% deep
            third = bottom + (rim - bottom) / 3
            if sum(1 for i in range(left, r + 1) if l[i] <= third) < CUP_U_SHARE * (cup_len + 1):
                continue                             # a V, not a rounded cup (our approximation, see the docstring)
            if left < 2 * cup_len:
                # eng-132: the prior advance is measured over 2x the cup's length before the left rim; a shorter history
                # measured it on a cut window (a rise looked smaller or bigger than it was): skipped, and said so
                if skips is not None and not any(s[0] == 'cup_handle' for s in skips):
                    skips.append(('cup_handle', left, 2 * cup_len))
                continue
            before = l[left - 2 * cup_len:left]
            if not before or h[left] / min(before) - 1 < 0.30:
                continue                             # no prior advance
            if not 7 <= len(handle) <= 56:     # eng-121: O'Neil's handle >= 1 week, <= 8 weeks (longer = stalling)
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
            if c[last] > pivot * 1.05:
                return None                          # O'Neil: 5% past the pivot the buy point is missed - no chase
            # Bulkowski's measure rule as his site states it now (thepatternsite.com/cup.html, 06/2026): the depth from
            # the RIGHT cup lip to the lowest valley x the share of patterns that met the full target (bullish cups in a
            # bull market: 61%, 913 trades), added to the breakout price - TP1; TP2 the full depth. Was half the
            # height of the lower rim 'met 76%' (eng-51), a figure his current page does not give
            height = h[r] - bottom
            target = pivot + CONFIG.strategies.cup_target_share * height
            target_full = pivot + height
            return {'setup': 'CUP HANDLE', 'direction': 1,
                    'setup_note': f"{tf} cup with handle: rims {h[left]:.6g} / {h[r]:.6g}, depth {depth:.0%} over "
                                  f"{cup_len} candles, handle {len(handle)} candles to {h_lo:.6g}; closed above the "
                                  f"pivot {pivot:.6g} on {v[last] / avg_vol:.1f}x volume (O'Neil)",
                    'anchor_level': pivot, 'anchor_extreme': h_lo, 'anchor_label': f'{tf} cup-with-handle pivot',
                    'anchor_ts': int(candles[left][0]), 'anchor_close': c[last], 'ch_stop': h_lo,
                    'ch_target': target, 'ch_target_full': target_full, 'ch_tf': tf, 'event_ts': int(candles[last][0]) + period_ms}
    return None


class CupHandleStrategy(_System):
    """O'Neil's cup with handle: entry at the breakout close, stop below the handle, target the measured move."""
    name = 'cup_handle'
    setups = {'CUP HANDLE': 1}
    ttl_key = 'cup_ttl'
    time_exit = 'fixed'                # the method's own exit (eng-47)
    min_rr = 1.0                                     # the measured target must pay more than the risk (O'Neil's 3:1 is an exit rule)

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig = x.sig
        if sig.get('ch_stop') is None:
            return None
        # O'Neil: sell at 7-8% below the buy point; Bulkowski: below the handle - the nearer of the two
        stop = max(sig['ch_stop'], sig['anchor_close'] * 0.92)
        src = 'below the handle' if stop == sig['ch_stop'] else "8% below the buy point (O'Neil)"
        exit = {'stop': ['price', stop], 'stop_src': src,
                'tp': ['level', sig['ch_target'], 0.0, None], 'tp_src': f"{CONFIG.strategies.cup_target_share:.0%} of the cup depth (Bulkowski's measure rule)",
                'tp2': ['level', sig.get('ch_target_full') or sig['ch_target'], 0.0, None],
                'atr': x.atr, 'own_targets': True, 'max_stop_pct': 0.08}
        return _confirm_plan(x, self.name, sig.get('ch_tf', '1d'), exit, 'close above the handle pivot on volume')


__all__ = ['cup_handle', 'CupHandleStrategy', 'Strategy']
