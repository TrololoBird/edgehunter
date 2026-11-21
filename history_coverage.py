"""Deterministic coverage of closed candles; never infer readiness from a loading flag."""
import math

TF_MS = {'1m': 60_000, '5m': 300_000, '15m': 900_000,
         '1h': 3_600_000, '4h': 14_400_000, '1d': 86_400_000, '1w': 604_800_000}
GRACE_MS = {'1m': 90_000, '5m': 90_000, '15m': 90_000,
            '1h': 120_000, '4h': 300_000, '1d': 600_000, '1w': 600_000}
TF_ANCHOR_MS = {'1w': 4 * 86_400_000}


def coverage(rows, timeframe, now_ms, required=500, calculation_bars=200, listed_ms=None):
    """Report depth, freshness and real gaps without synthesizing candles.

    Rows use exchange OHLCV order and opening timestamps in milliseconds.
    Freshness is measured against the last expected closed candle, allowing
    the configured publication grace after its close.
    """
    step = TF_MS[timeframe]
    anchor = TF_ANCHOR_MS.get(timeframe, 0)
    valid, invalid, duplicates, conflicts = {}, 0, 0, 0
    for row in rows:
        try:
            raw_ts = float(row[0])
            ts = int(raw_ts)
            if not math.isfinite(raw_ts) or raw_ts != ts:
                invalid += 1
                continue
            if ts + step > now_ms:
                continue
            o, h, l, c, v = map(float, row[1:6])
            if (ts % step != anchor or not all(math.isfinite(x) for x in (o, h, l, c, v))
                    or min(o, h, l, c) <= 0 or v < 0 or l > min(o, c) or h < max(o, c) or l > h):
                invalid += 1
                continue
            normalized = (o, h, l, c, v)
            previous = valid.get(ts)
            if previous is not None:
                duplicates += 1
                if previous != normalized:
                    conflicts += 1
                continue
            valid[ts] = normalized
        except (IndexError, TypeError, ValueError, OverflowError):
            invalid += 1
    stamps = sorted(valid)
    recent = stamps[-max(required, calculation_bars):]
    gaps = []
    for a, b in zip(recent, recent[1:]):
        count = max(0, (b-a)//step-1)
        if count:
            gaps.append({'start_ms': a + step, 'end_ms': b - step, 'missing_bars': count})
    missing = sum(g['missing_bars'] for g in gaps)
    latest = stamps[-1] if stamps else None
    overdue = None if latest is None else max(0, now_ms-(latest+2*step))
    state = ('INVALID' if invalid or conflicts else 'LOADING' if not stamps else 'DATA_GAP' if missing
             else 'STALE' if overdue > GRACE_MS[timeframe]
             else 'LOADING' if len(stamps) < required else 'READY')
    # If the full possible interval since listing is present, more REST
    # requests cannot create the remaining pre-listing candles.
    if listed_ms and state == 'LOADING' and stamps:
        first_possible = (int(listed_ms) - anchor) // step * step + anchor
        last_expected = (int(now_ms) - anchor) // step * step + anchor - step
        possible = max(0, (last_expected - first_possible) // step + 1)
        if 0 < possible < required and stamps[0] == first_possible and missing == 0:
            state = 'LISTING_TOO_RECENT'
    return {'timeframe': timeframe, 'state': state, 'ready': state == 'READY',
            'available_bars': len(stamps), 'required_bars': required,
            'progress_pct': min(100, round(100*len(stamps)/required, 1)),
            'oldest_closed_ms': stamps[0] if stamps else None, 'latest_closed_ms': latest,
            'missing_bars': missing, 'gaps': gaps[:100], 'invalid_bars': invalid,
            'duplicate_bars': duplicates, 'conflicting_bars': conflicts, 'overdue_ms': overdue}
