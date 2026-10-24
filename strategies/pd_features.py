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
Thresholds come from aleks-ent/pump-dump-crypto-screener PUMP_DETECTION_RULES.md (read at the source 2026-10-24;
heuristics, not measured); the 288-candle 5m baselines are fetched by REST when a PUMP / DUMP START fires: the features are
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


def _ema(values: Sequence[float], n: int) -> List[float]:
    k, out = 2 / (n + 1), []
    for v in values:
        out.append(v if not out else out[-1] + k * (v - out[-1]))
    return out


def features(minutes: Sequence[Sequence[float]], m15: Sequence[Sequence[float]], direction: int,
             m5: Optional[Sequence[Sequence[float]]] = None) -> Dict:
    """pd_* features at the last final minute, for a move in `direction` (+1 pump, -1 dump).

    m5: closed 5m candles of the last 24h+ (REST, the source's 288-candle baselines); without it the 5m bars of the 1m
    ring are the base (pd_base_n says how many)."""
    out: Dict = {}
    ring = bars_5m(minutes)
    if m5:
        hist = [list(b[:7]) if len(b) >= 7 else list(b[:6]) + [0.0] for b in m5]
        cut = ring[0][0] if ring else float('inf')
        bars = [b for b in hist if b[0] < cut] + ring
    else:
        bars = ring
    if len(bars) < 13:
        return out
    last = bars[-1]
    prev = bars[-289:-1]
    out['pd_base_n'] = len(prev)
    # baselines: medians of the PREVIOUS candles only (the source: 288 x 5m, the current one excluded)
    vols = [b[5] for b in prev if b[5] is not None]
    base5 = median(vols) if len(vols) >= 12 else None
    if not base5:
        b1 = volume_base_1m(m15)
        base5 = b1 * 5 if b1 else None
    if base5 and minutes:
        out['rvol_1m_med'] = float(minutes[-1][5]) / (base5 / 5)
    rngs = [(b[2] - b[3]) / b[4] for b in prev if b[4]]
    med_rng = median(rngs) if len(rngs) >= 12 else None
    def vr(b):
        return b[5] / base5 if base5 else None
    def rr(b):
        return (b[2] - b[3]) / b[4] / med_rng if med_rng and b[4] else None
    if base5:
        out['pd_vol_ratio_5m'] = vr(last)
        out['pd_vol_cluster'] = sum(1 for b in bars[-4:] if (vr(b) or 0) >= 3.0)          # source: >= 2 of 4
    if med_rng:
        out['pd_range_ratio'] = rr(last)
        out['pd_range_cluster'] = sum(1 for b in bars[-4:] if (rr(b) or 0) >= 2.0)        # source: >= 2 of 4
    out['pd_move3'] = last[4] / bars[-4][4] - 1 if bars[-4][4] else None
    out['pd_move6'] = last[4] / bars[-7][4] - 1 if bars[-7][4] else None
    # green (red for a dump) candles of the last 4 / 6 (source: >= 3 of 4, strong >= 5 of 6)
    out['pd_green4'] = sum(1 for b in bars[-4:] if direction * (b[4] - b[1]) > 0)
    out['pd_green6'] = sum(1 for b in bars[-6:] if direction * (b[4] - b[1]) > 0)
    loc = bars[-25:-1]
    if len(loc) >= 12:
        edge = max(b[2] for b in loc) if direction > 0 else min(b[3] for b in loc)
        out['pd_breakout'] = direction * (last[4] / edge - 1) if edge else None             # source: > 0.003
    # eng-160: H_n for the retest variant - the edge of the 2h range BEFORE the move (the 24 bars before the last 3:
    # the 15-minute move that fired the signal), so the level is the range the pump broke, not a bar of the pump
    pre = bars[-27:-3]
    if len(pre) >= 12:
        out['pd_hn'] = max(b[2] for b in pre) if direction > 0 else min(b[3] for b in pre)
    trs = [max(b[2] - b[3], abs(b[2] - a[4]), abs(b[3] - a[4])) for a, b in zip(bars[-15:-1], bars[-14:])]
    if len(trs) >= 10:
        out['pd_atr5'] = sum(trs) / len(trs)                                                # ATR(14) of 5m
    closes = [b[4] for b in bars]
    if len(closes) >= 26:
        e20 = _ema(closes, 20)
        out['pd_above_ema20'] = int(direction * (closes[-1] - e20[-1]) > 0)
        out['pd_ema20_slope'] = direction * (e20[-1] / e20[-7] - 1) if e20[-7] else None   # source: > 0
    # impulse start: the first of the last 12 candles with volume >= 3x, range >= 2x, closing in the direction;
    # pullback = (impulse extreme - close) / (extreme - start price) (source: <= 0.30 shallow, > 0.50 no longer active)
    if base5 and med_rng:
        win = bars[-12:]
        start = next((i for i, b in enumerate(win) if (vr(b) or 0) >= 3 and (rr(b) or 0) >= 2
                      and direction * (b[4] - b[1]) > 0), None)
        if start is not None:
            s0 = win[start][1]
            ext = max(b[2] for b in win[start:]) if direction > 0 else min(b[3] for b in win[start:])
            leg = direction * (ext - s0)
            out['pd_pullback'] = direction * (ext - last[4]) / leg if leg > 0 else None
            before = bars[:len(bars) - 12 + start]
            pre = before[-72:-24] if len(before) >= 48 else []
            if pre and med_rng:
                hi, lo = max(b[2] for b in pre), min(b[3] for b in pre)
                mid = (hi + lo) / 2
                out['pd_quiet'] = (hi - lo) / mid / med_rng if mid else None              # 24-72 candles before
    # LATE (source: 12 candles >= 12%, volume >= 10x, range >= 4x), mirrored for a dump
    if bars[-13][4]:
        move12 = direction * (last[4] / bars[-13][4] - 1)
        out['pd_move12'] = move12
        out['pd_late'] = int(move12 >= 0.12 and (out.get('pd_vol_ratio_5m') or 0) >= 10
                             and (out.get('pd_range_ratio') or 0) >= 4)
    # SPIKE (source: one candle >= 5%, more than 70% retraced within the next 2 candles), last 30 minutes
    fail = 0
    tail = bars[-8:]
    for i in range(len(tail) - 2):
        a = tail[i]
        jump = direction * (a[4] - a[1])
        if a[1] and jump / a[1] >= 0.05:
            back = max(direction * (a[4] - b[4]) for b in tail[i + 1:i + 3])
            if back > 0.7 * jump:
                fail = 1
    out['pd_spike_fail'] = fail
    # the source's ACTIVATION / ACTIVE on this candle (journaled; the card's own trigger is PUMP / DUMP START)
    act = ((out.get('pd_vol_ratio_5m') or 0) >= 3 and (out.get('pd_range_ratio') or 0) >= 1.5
           and direction * (out.get('pd_move3') or 0) > 0
           and (out.get('pd_above_ema20') or (out.get('pd_breakout') or 0) > 0.003))
    active = ((out.get('pd_vol_cluster') or 0) >= 2 and (out.get('pd_range_cluster') or 0) >= 2
              and (direction * (out.get('pd_move3') or 0) >= 0.02 or direction * (out.get('pd_move6') or 0) >= 0.04)
              and (out.get('pd_green4') or 0) >= 3 and (out.get('pd_pullback') if out.get('pd_pullback') is not None else 1) <= 0.30
              and out.get('pd_above_ema20') and (out.get('pd_ema20_slope') or 0) > 0)
    out['pd_phase'] = ('LATE' if out.get('pd_late') else 'SPIKE_FAIL' if fail else 'ACTIVE' if active
                       else 'ACTIVATION' if act else 'NONE')
    return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in out.items() if v is not None}


def activation(minutes: Sequence[Sequence[float]], base1: Optional[float], direction: int) -> bool:
    """The source's ACTIVATION on the last CLOSED 5m bar of the ring: volume >= 3x the median 5m volume, range >= 1.5x
    the median 5m range, close above the bar 3 back, and close beyond EMA20 or a breakout of the previous 24 bars."""
    if not base1 or len(minutes) < 60:
        return False
    if (int(minutes[-1][0]) + MINUTE_MS) % FIVE_MS:
        return False                                  # only when a 5m bar just closed
    bars = bars_5m(minutes)
    if len(bars) < 26:
        return False
    b = bars[-1]
    rngs = [(x[2] - x[3]) / x[4] for x in bars[:-1] if x[4]]
    med = median(rngs) if rngs else 0
    if not med or not b[4] or b[5] < 3 * base1 * 5 or (b[2] - b[3]) / b[4] < 1.5 * med:
        return False
    if direction * (b[4] - bars[-4][4]) <= 0:
        return False
    e20 = _ema([x[4] for x in bars], 20)[-1]
    loc = bars[-25:-1]
    edge = max(x[2] for x in loc) if direction > 0 else min(x[3] for x in loc)
    return direction * (b[4] - e20) > 0 or direction * (b[4] / edge - 1) > 0.003


def extras(m5_rest: Sequence[Sequence[float]], minutes: Sequence[Sequence[float]],
           btc_minutes: Sequence[Sequence[float]], direction: int,
           btc_m5: Optional[Sequence[Sequence[float]]] = None) -> Dict:
    """eng-159c, from the other sources of the owner's research (read 2026-10-24):
    - pd_trades_ratio_5m: trades of the last closed 5m candle / the median of the previous 288 (La Morgia et al. 2020,
      'The Doge of Wall Street' 2023: StdTrades / rush orders jump at the pump's start); REST kline field n;
    - pd_price_vs_ma12h: close vs the 12h moving average of the open (Kamps & Kleinberg 2018 / the 2025 thresholding
      detector: price against a 12h moving average), signed by the direction;
    - pd_vs_btc: the coin's 30-minute move minus BTC's (the BOCD detector of RaibekTussupbekov judges an alt against
      BTC/USDT), signed by the direction."""
    out: Dict = {}
    rows = [r for r in m5_rest if len(r) > 7]
    if len(rows) >= 50:
        trades = [r[7] for r in rows]
        base = median(trades[-289:-1])
        if base >= 20:                   # a near-dead coin's ratio is noise, not a signal (review eng-159c)
            out['pd_trades_ratio_5m'] = trades[-1] / base
        opens = [r[1] for r in rows[-145:-1]]
        ma = sum(opens) / len(opens) if opens else None
        last = minutes[-1][4] if minutes else rows[-1][4]
        if ma:
            out['pd_price_vs_ma12h'] = direction * (last / ma - 1)
    if btc_m5 and len(rows) >= 60:
        # the BOCD detector's idea closer: the coin's 30-minute return minus beta x BTC's, beta from the PREVIOUS 5m
        # returns only (aligned by candle time, up to 288), so a high-beta alt moving with BTC is no anomaly
        bmap = {int(r[0]): r[4] for r in btc_m5}
        pairs = [(a[4], b[4], bmap.get(int(a[0])), bmap.get(int(b[0]))) for a, b in zip(rows[:-1], rows[1:])]
        rets = [(c1 / c0 - 1, b1 / b0 - 1) for c0, c1, b0, b1 in pairs if c0 and b0 and b1]
        hist = rets[-289:-6]
        if len(hist) >= 48:
            mx = sum(x for _, x in hist) / len(hist)
            my = sum(y for y, _ in hist) / len(hist)
            var = sum((x - mx) ** 2 for _, x in hist)
            beta = sum((x - mx) * (y - my) for y, x in hist) / var if var else 0.0
            b6, b0_ = bmap.get(int(rows[-1][0])), bmap.get(int(rows[-7][0]))
            if b6 and b0_ and rows[-7][4]:
                out['pd_btc_beta'] = beta
                out['pd_vs_btc_resid'] = direction * ((rows[-1][4] / rows[-7][4] - 1) - beta * (b6 / b0_ - 1))
    coin, btc = bars_5m(minutes), bars_5m(btc_minutes)
    if len(coin) >= 7 and len(btc) >= 7 and coin[-7][4] and btc[-7][4]:
        out['pd_vs_btc'] = direction * ((coin[-1][4] / coin[-7][4] - 1) - (btc[-1][4] / btc[-7][4] - 1))
    return {k: round(v, 6) for k, v in out.items()}


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
