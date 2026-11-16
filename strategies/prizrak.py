"""Small, deterministic primitives for the Prizrak Trade structural contract.

The helpers deliberately do not place orders or choose a strategy.  They make the four observable rules explicit so
that a playbook can opt in without re-implementing wick/body, freshness, target-timeframe, or trap logic in several
modules.  Candle rows are ``[open_time, open, high, low, close, ...]`` and must be closed bars.
"""
from __future__ import annotations

import math
from typing import Iterable, Optional, Sequence


TF_MINUTES = {'1m': 1, '5m': 5, '15m': 15, '1h': 60, '4h': 240, '1d': 1440, '1w': 10080}


def _body(candle: Sequence[float]) -> tuple[float, float]:
    return min(float(candle[1]), float(candle[4])), max(float(candle[1]), float(candle[4]))


def full_body_beyond(candle: Sequence[float], level: float, direction: int) -> bool:
    """True when the *whole* candle body closed beyond ``level`` in ``direction``.

    A wick alone is intentionally not a break.  Requiring the open and close on the same side is the probe/PP
    distinction from the course and prevents one-minute spikes from invalidating a higher-timeframe level.
    """
    if direction not in (-1, 1) or level is None:
        return False
    lo, hi = _body(candle)
    return lo > float(level) if direction > 0 else hi < float(level)


def body_break_confirmed(candles: Sequence[Sequence[float]], level: float, direction: int,
                         confirmations: int = 2) -> bool:
    """Return whether the last ``confirmations`` closed bodies all broke ``level``."""
    n = max(2, int(confirmations or 2))
    if len(candles) < n:
        return False
    return all(full_body_beyond(c, level, direction) for c in candles[-n:])


def body_break_since(candles: Iterable[Sequence[float]], since_ms: int, level: float, direction: int,
                     confirmations: int = 2) -> Optional[float]:
    """First close time of a confirmed full-body break after ``since_ms``; ``None`` if not confirmed."""
    bars = [c for c in candles if int(c[0]) >= int(since_ms)]
    n = max(2, int(confirmations or 2))
    for i in range(n - 1, len(bars)):
        if all(full_body_beyond(c, level, direction) for c in bars[i - n + 1:i + 1]):
            return float(bars[i][0])
    return None


def classify_interaction(candles: Sequence[Sequence[float]], level: float, direction: int,
                         confirmations: int = 2) -> str:
    """Classify the latest level interaction as ``probe``, ``pp_break`` or ``none``.

    ``probe`` means a wick crossed the level but the next one or two closed bodies returned to the original side.  It is
    a valid level reaction, not an invalidation.  ``pp_break`` requires full-body acceptance for the configured count.
    """
    if body_break_confirmed(candles, level, direction, confirmations):
        return 'pp_break'
    if not candles:
        return 'none'
    # A long level is probed by a wick *below* support; a short level is probed by a wick *above* resistance.
    # The previous implementation inverted these sides and labelled ordinary continuation candles as probes.
    crossed = any((float(c[3]) < level if direction > 0 else float(c[2]) > level) for c in candles)
    returned = any((float(c[4]) >= level if direction > 0 else float(c[4]) <= level) for c in candles[-2:])
    return 'probe' if crossed and returned else 'none'


def trap_detected(candles: Sequence[Sequence[float]], entry_level: float, direction: int,
                  confirmations: int = 2) -> bool:
    """A confirmed full-body break against the position, used to arm a BE exit on the retest."""
    return body_break_confirmed(candles, entry_level, -int(direction), confirmations)


def target_timeframe_allowed(entry_tf: str, target_tf: str) -> bool:
    """A target may be on the entry timeframe or a higher one, never on an LTF."""
    e, t = TF_MINUTES.get(str(entry_tf), 0), TF_MINUTES.get(str(target_tf), 0)
    return bool(e and t and t >= e)


def accumulation_poc(candles: Sequence[Sequence[float]], base_lo: float, base_hi: float, atr: float,
                     min_touches: int = 4, buckets_per_atr: int = 8) -> Optional[dict]:
    """Build a POC only for a compact base with four boundary contacts and a later body exit.

    This is intentionally a pure candidate builder.  ``base_lo``/``base_hi`` come from a strategy's detected base;
    volume is distributed over price buckets exactly as the existing profile code does.  The returned ``fresh`` flag is
    true for the first post-exit touch and is meant to be persisted by the caller after a reaction.
    """
    if len(candles) < 4 or not math.isfinite(float(atr)) or atr <= 0 or base_hi <= base_lo:
        return None
    width = max(atr / max(2, int(buckets_per_atr)), (base_hi - base_lo) / 32)
    exit_i = None
    for i, c in enumerate(candles):
        lo, hi = _body(c)
        if hi < base_lo or lo > base_hi:
            exit_i = i
            break
    if exit_i is None:
        return None
    base = candles[:exit_i]
    # Boundary contacts belong to the accumulation before the exit.  Counting post-exit bars would manufacture a
    # four-touch base after the fact and would mark an already-reacted level as fresh.
    touches = [c for c in base if float(c[3]) <= base_hi and float(c[2]) >= base_lo and
               (abs(float(c[3]) - base_lo) <= width or abs(float(c[2]) - base_hi) <= width)]
    if len(touches) < int(min_touches):
        return None
    n = max(1, int((base_hi - base_lo) / width) + 1)
    vol = [0.0] * n
    for c in base:
        lo, hi = max(base_lo, float(c[3])), min(base_hi, float(c[2]))
        if hi < lo:
            continue
        a = max(0, min(n - 1, int((lo - base_lo) / width)))
        b = max(0, min(n - 1, int((hi - base_lo) / width)))
        share = float(c[5] or 0.0) / (b - a + 1)
        for k in range(a, b + 1):
            vol[k] += share
    if not any(vol):
        return None
    poc_bucket = max(range(n), key=vol.__getitem__)
    poc = base_lo + (poc_bucket + 0.5) * width
    post_touch = next((c for c in candles[exit_i + 1:] if float(c[3]) <= poc <= float(c[2])), None)
    return {
        'poc': poc,
        'base_lo': float(base_lo),
        'base_hi': float(base_hi),
        'touch_count': len(touches),
        'exit_ts': int(candles[exit_i][0]),
        'first_touch_ts': int(post_touch[0]) if post_touch is not None else None,
        'fresh': post_touch is None,
    }
