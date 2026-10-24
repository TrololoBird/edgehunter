"""
eng-159: the pump / dump detector's feature layer (docs/PUMP_DUMP_DETECTOR.md), from the owner's research.

Every feature is the coin against its OWN history:
- volume baselines are 24h MEDIANS (the closed 15m candles of the last 24h: a single spike no longer inflates the base
  the way the 24h mean did); per 1m = median15 / 15, per 5m = median15 / 3;
- the 5m layer is built from the final 1m candles: volume ratio and the cluster (5m bars >= 3x among the last 4),
  range_ratio (the bar's % range / the median of the 5m bars in the ring), move3 / move6 (15 / 30 minutes), the 2h
  breakout (close beyond the previous 24 x 5m extreme), the quiet period before (2-6h range vs its median);
- phases: LATE (move over 12 x 5m >= 12% with volume >= 10x and range >= 4x - the screener's late pump: seen, too late)
  and SPIKE_FAIL (a 5m bar >= 5% retraced >= 70% within the next 2 bars - a false start in the last 30 minutes).
Thresholds marked *screener* come from aleks-ent/pump-dump-crypto-screener (heuristics, not measured): the features are
journaled (pd_* columns) and LATE / SPIKE_FAIL are SHADOW vetoes (strategies.shadow_vetoes) until the live journal
shows what they are worth.
"""
from statistics import median
from typing import Dict, List, Optional, Sequence

MINUTE_MS = 60_000
FIVE_MS = 5 * MINUTE_MS


def bars_5m(minutes: Sequence[Sequence[float]]) -> List[List[float]]:
    """Final 1m candles -> complete 5m bars [ts, o, h, l, c, quote_vol, taker_buy_quote] (a bucket missing a minute is
    dropped - a hole beats a false bar)."""
    out: List[List[float]] = []
    count: List[int] = []
    for c in minutes:
        start = int(c[0]) // FIVE_MS * FIVE_MS
        if out and out[-1][0] == start:
            b = out[-1]
            b[2], b[3], b[4] = max(b[2], c[2]), min(b[3], c[3]), c[4]
            b[5] += c[5]
            b[6] += c[6] if len(c) > 6 else 0.0
            count[-1] += 1
        else:
            out.append([start, c[1], c[2], c[3], c[4], c[5], c[6] if len(c) > 6 else 0.0])
            count.append(1)
    return [b for b, n in zip(out, count) if n == 5]


def volume_base_1m(m15: Sequence[Sequence[float]]) -> Optional[float]:
    """The 24h MEDIAN quote volume of a minute: median of the last 96 closed 15m candles / 15."""
    vols = [float(b[5]) for b in list(m15)[-96:] if len(b) > 5 and b[5] is not None]
    if len(vols) < 48:
        return None
    med = median(vols)
    return med / 15 if med > 0 else None


def features(minutes: Sequence[Sequence[float]], m15: Sequence[Sequence[float]], direction: int) -> Dict:
    """pd_* features at the last final minute, for a move in `direction` (+1 pump, -1 dump)."""
    out: Dict = {}
    base1 = volume_base_1m(m15)
    if base1 and minutes:
        out['rvol_1m_med'] = float(minutes[-1][5]) / base1
    bars = bars_5m(minutes)
    if len(bars) < 13:
        return out
    base5 = base1 * 5 if base1 else None
    last = bars[-1]
    if base5:
        ratios = [b[5] / base5 for b in bars[-4:]]
        out['pd_vol_ratio_5m'] = ratios[-1]
        out['pd_vol_cluster'] = sum(1 for r in ratios if r >= 3.0)                 # *screener*: >= 3x
    rng = [(b[2] - b[3]) / b[4] for b in bars[:-1] if b[4]]
    med_rng = median(rng) if len(rng) >= 12 else None
    if med_rng and last[4]:
        out['pd_range_ratio'] = (last[2] - last[3]) / last[4] / med_rng
    if len(bars) >= 7:
        out['pd_move3'] = last[4] / bars[-4][4] - 1 if bars[-4][4] else None
        out['pd_move6'] = last[4] / bars[-7][4] - 1 if bars[-7][4] else None
    prev = bars[-25:-1]
    if len(prev) >= 12:
        edge = max(b[2] for b in prev) if direction > 0 else min(b[3] for b in prev)
        out['pd_breakout'] = direction * (last[4] / edge - 1) if edge else None        # > 0.003 = *screener* breakout
    before = bars[-72:-24]
    if len(before) >= 24 and med_rng:
        hi, lo = max(b[2] for b in before), min(b[3] for b in before)
        mid = (hi + lo) / 2
        # the 2-6h window's whole range in 5m-median units: low = a quiet base before the move
        out['pd_quiet'] = (hi - lo) / mid / med_rng if mid else None
    # LATE: the screener's late pump (12 x 5m >= 12% with volume >= 10x and range >= 4x), mirrored for a dump
    if len(bars) >= 13 and bars[-13][4]:
        move12 = direction * (last[4] / bars[-13][4] - 1)
        out['pd_move12'] = move12
        out['pd_late'] = int(move12 >= 0.12 and out.get('pd_vol_ratio_5m', 0) >= 10
                             and out.get('pd_range_ratio', 0) >= 4)
    # SPIKE_FAIL: a 5m bar >= 5% in the direction, >= 70% of it retraced within the next 2 bars (last 30 min)
    fail = 0
    tail = bars[-8:]
    for i in range(len(tail) - 2):
        a = tail[i]
        jump = direction * (a[4] - a[1])
        if a[1] and jump / a[1] >= 0.05:
            back = max(direction * (a[4] - b[4]) for b in tail[i + 1:i + 3])
            if back >= 0.7 * jump:
                fail = 1
    out['pd_spike_fail'] = fail
    out['pd_phase'] = 'LATE' if out.get('pd_late') else 'SPIKE_FAIL' if fail else 'ACTIVE'
    return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in out.items() if v is not None}


def activation(minutes: Sequence[Sequence[float]], base1: Optional[float], direction: int) -> bool:
    """ACTIVATION on the last final minute (*screener*): volume >= 3x the 24h median minute, its range >= 1.5x the
    median 1m range of the ring, and the candle moved in `direction`."""
    if not base1 or len(minutes) < 30:
        return False
    c = minutes[-1]
    if not c[4] or c[5] < 3 * base1 or direction * (c[4] - c[1]) <= 0:
        return False
    rngs = [(x[2] - x[3]) / x[4] for x in list(minutes)[-240:-1] if x[4]]
    med = median(rngs) if rngs else 0
    return bool(med) and (c[2] - c[3]) / c[4] >= 1.5 * med


class ActivationLog:
    """First ACTIVATION per (coin, direction) - the detector's lead time (journal pd_activation_lead_s)."""

    def __init__(self, keep_ms: int = 2 * 3_600_000):
        self.first: Dict[tuple, int] = {}
        self.keep_ms = keep_ms

    def update(self, symbol: str, minutes, base1: Optional[float]) -> None:
        if not minutes:
            return
        ts = int(minutes[-1][0])
        for d in (1, -1):
            key = (symbol, d)
            old = self.first.get(key)
            if old is not None and ts - old > self.keep_ms:
                self.first.pop(key, None)
                old = None
            if old is None and activation(minutes, base1, d):
                self.first[key] = ts

    def lead_s(self, symbol: str, direction: int, signal_ms: int) -> Optional[float]:
        ts = self.first.pop((symbol, direction), None)
        return (signal_ms - ts) / 1000 if ts is not None and ts <= signal_ms else None
