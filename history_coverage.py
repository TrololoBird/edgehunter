"""Deterministic coverage of closed candles; never infer readiness from a loading flag."""
import math

TF_MS = {'1m': 60_000, '5m': 300_000, '15m': 900_000,
         '1h': 3_600_000, '4h': 14_400_000, '1d': 86_400_000}
GRACE_MS = {'1m': 90_000, '5m': 90_000, '15m': 90_000,
            '1h': 120_000, '4h': 300_000, '1d': 600_000}


def coverage(rows, timeframe, now_ms, required=500, calculation_bars=200, listed_ms=None):
    """Report depth, freshness and real gaps without synthesizing candles.

    Rows use exchange OHLCV order and opening timestamps in milliseconds.
    Freshness is measured against the last expected closed candle, allowing
    the configured publication grace after its close.
    """
    step = TF_MS[timeframe]
    valid, invalid = {}, 0
    for row in rows:
        try:
            ts = int(row[0])
            if ts + step > now_ms:
                continue
            o, h, l, c, v = map(float, row[1:6])
            if ts % step or not all(math.isfinite(x) for x in (o, h, l, c, v)) or min(o, h, l, c) <= 0 or v < 0 or l > min(o, c) or h < max(o, c) or l > h:
                invalid += 1
                continue
            valid[ts] = row
        except (IndexError, TypeError, ValueError, OverflowError):
            invalid += 1
    stamps = sorted(valid)
    recent = stamps[-max(required, calculation_bars):]
    missing = sum(max(0, (b-a)//step-1) for a, b in zip(recent, recent[1:]))
    latest = stamps[-1] if stamps else None
    overdue = None if latest is None else max(0, now_ms-(latest+2*step))
    state = ('INVALID' if invalid else 'LOADING' if not stamps else 'DATA_GAP' if missing
             else 'STALE' if overdue > GRACE_MS[timeframe]
             else 'LOADING' if len(stamps) < required else 'READY')
    # If the full possible interval since listing is present, more REST
    # requests cannot create the remaining pre-listing candles.
    if listed_ms and state == 'LOADING' and stamps:
        first_possible = int(listed_ms) // step * step
        possible = now_ms // step - first_possible // step
        if 0 < possible == len(stamps) < required and stamps[0] == first_possible:
            state = 'LISTING_TOO_RECENT'
    return {'timeframe': timeframe, 'state': state, 'ready': state == 'READY',
            'available_bars': len(stamps), 'required_bars': required,
            'progress_pct': min(100, round(100*len(stamps)/required, 1)),
            'oldest_closed_ms': stamps[0] if stamps else None, 'latest_closed_ms': latest,
            'missing_bars': missing, 'invalid_bars': invalid, 'overdue_ms': overdue}
