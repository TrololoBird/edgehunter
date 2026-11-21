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

from config import CONFIG
from strategies.base import CardLevels, PlanInput, Strategy
from zones import liq_only, merge

MINUTE_MS = 60_000
OI_TARGET_MIN_NET_RR = 1.0
# Keep the OI map search finite.  Six working ATRs is the existing zone-map merge span and is the
# same practical discovery window used by the map, while still allowing the first structural pool
# beyond a micro level to be selected.
OI_TARGET_MAX_ATR = 6.0


def _oi_targets(x: PlanInput, direction: int):
    """OI-build-owned opposite-liquidity targets with a cost-aware first target floor.

    OI's raw level map often contains a near micro-level immediately in front of the entry.  It is
    still a valid map observation, but it is not a usable TP1 when the net reward is below one unit
    of the actual stop risk.  Skip those levels before writing the contract targets so the shared
    geometry layer sees the first structural level that can pay the trade's round-trip cost.
    """
    atr = float(x.atr or 0)
    ref = float(x.sig.get('anchor_close') or 0)
    stop_ref = x.sig.get('anchor_extreme')
    stop = float(stop_ref) - direction * 0.25 * atr if stop_ref is not None else None
    risk = direction * (ref - stop) if stop is not None else 0.0
    from strategies.geometry import cost_of
    fee = cost_of(ref, x.sig.get('volume_24h'), x.symbol) if ref else 0.0
    gap = CONFIG.zones.min_target_atr * atr
    zones = merge(list(x.raw_levels or []), atr, symbol=x.symbol)
    targets, sources = [], []
    for zone in sorted((z for z in zones if not liq_only(z)),
                       key=lambda z: direction * ((z.lo if direction > 0 else z.hi) - ref)):
        price = zone.lo if direction > 0 else zone.hi
        distance = direction * (price - ref)
        net_rr = ((distance - fee) / (risk + fee)) if risk > 0 else -float('inf')
        if (0 < distance <= OI_TARGET_MAX_ATR * atr and net_rr >= OI_TARGET_MIN_NET_RR
                and (not targets or direction * (price - targets[-1]) >= gap)):
            targets.append(price)
            sources.append(zone.label)
        if len(targets) >= 3:
            break
    # No structural level that pays the minimum: keep the plan unexecutable instead of manufacturing
    # an ATR target at/inside the entry.  With one or two levels the shared geometry contract repeats
    # the last real map level for the remaining slots.
    if not targets:
        return [], []
    while len(targets) < 3:
        targets.append(targets[-1]); sources.append(sources[-1])
    return targets, sources


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


def _abs_move_1h(m15: Sequence[Sequence[float]], bars: int = 288) -> Optional[float]:
    """The coin's usual 1h move: the mean |close / close 4 bars back - 1| over the last `bars` closed 15m candles."""
    closes = [float(c[4]) for c in list(m15)[-bars:] if c[4]]
    moves = [abs(closes[k] / closes[k - 4] - 1) for k in range(4, len(closes))]
    return sum(moves) / len(moves) if len(moves) >= 92 else None


def oi_build(minutes: Sequence[Sequence[float]], oi_5m: Sequence, now_ms: int, oi_samples: Sequence = (),
             m15: Sequence = (), btc_minutes: Optional[Sequence] = None, btc_m15: Optional[Sequence] = None) -> Optional[Dict]:
    """minutes: final 1m candles; oi_5m: (ts_ms, OI) one sample per 5 minutes over the last day; oi_samples: the live
    OI samples (the journal's oi_chg_60m reads the same series); m15: closed 15m candles; btc_*: BTC's, None for BTC.

    eng-169i: Pring's "faster than its average" as a material move, not any tick above the mean (26.10: entries on OI
    +0.11% at a mean of +0.11%, price +0.04%; 18 longs in 2h, 15 stopped, all on BTC's +0.87% hour):
    - OI: the 1h change >= 2 robust sigmas above the day's 1h changes (median + 2 x 1.4826 MAD), and > 0;
    - price: the 1h move >= the coin's usual 1h move (mean |1h change| over 3 days of 15m candles);
    - the coin's own move: its 1h move in units of its usual move beats BTC's in BTC's units by >= 1 (a beta 2 alt
      on a BTC hour moves 2x BTC in % but not in its own units)."""
    oi = [(int(t), float(v)) for t, v in oi_5m if v]
    if len(oi) < 13 * 2 or len(minutes) < 61:
        return None
    if now_ms - oi[-1][0] > 10 * MINUTE_MS:
        return None                            # the OI feed stalled: no reading
    changes = [oi[k][1] / oi[k - 12][1] - 1 for k in range(12, len(oi))
               if 55 * MINUTE_MS <= oi[k][0] - oi[k - 12][0] <= 65 * MINUTE_MS]
    if len(changes) < 12:
        return None
    now_chg = _oi_change(list(oi_samples), now_ms, 60) if oi_samples else None
    if now_chg is None:
        return None
    srt = sorted(changes)
    med = srt[len(srt) // 2]
    mad = sorted(abs(x - med) for x in changes)[len(changes) // 2]
    sigma = 1.4826 * mad
    if not (now_chg > 0 and sigma > 0 and (now_chg - med) / sigma >= 2.0):
        return None
    mean = med
    last = minutes[-1]
    t0 = int(last[0])
    c60 = _close_at(minutes, t0 - 60 * MINUTE_MS)
    if c60 is None:
        return None
    p60 = last[4] / c60 - 1
    if p60 == 0:
        return None
    d = 1 if p60 > 0 else -1
    usual = _abs_move_1h(m15)
    if not usual or abs(p60) < usual:
        return None
    rel = None
    if btc_minutes is not None:
        b_last = btc_minutes[-1] if btc_minutes else None
        b60 = _close_at(btc_minutes, int(b_last[0]) - 60 * MINUTE_MS) if b_last else None
        b_usual = _abs_move_1h(btc_m15 or ())
        if b60 is None or not b_usual:
            return None                        # BTC unknown: the coin's own move cannot be told from the market's
        rel = p60 / usual - (b_last[4] / b60 - 1) / b_usual
        if d * rel < 1.0:
            return None
    hour = [c for c in minutes if c[0] > t0 - 60 * MINUTE_MS]
    extreme = min(c[3] for c in hour) if d > 0 else max(c[2] for c in hour)
    z = (now_chg - med) / sigma
    return {'setup': 'OI BUILD LONG' if d > 0 else 'OI BUILD SHORT', 'direction': d,
            'setup_note': f"price 1h {p60:+.2%} ({abs(p60) / usual:.1f}x its usual 1h move"
                          + (f", {d * rel:+.1f} vs BTC in own units" if rel is not None else '')
                          + f") with OI 1h {now_chg:+.2%}, {z:.1f} robust sigma above the day's median {med:+.2%} (Pring)",
            'anchor_level': last[4], 'anchor_extreme': extreme, 'anchor_label': 'OI build (Pring)',
            'anchor_ts': t0, 'anchor_close': last[4], 'oi_build_oi60': now_chg, 'oi_build_mean': mean,
            'oi_build_p60': p60, 'oi_build_z': z, 'oi_build_rel_btc': rel, 'event_ts': t0 + MINUTE_MS}


class OiBuildStrategy(Strategy):
    name = 'oi_build'
    anchor_type = 'level'
    setups = {'OI BUILD LONG': 1, 'OI BUILD SHORT': -1}
    ttl_key = 'oi_build_ttl'
    time_exit = 'fixed'
    default_tf = '15m'
    requires = ('flow', 'oi')

    def entry_levels(self, plan: Dict, entry: float, extreme: Optional[float], direction: int) -> Optional[CardLevels]:
        """Pring OI-build contract: hour extreme stop and opposite-liquidity targets."""
        atr, ref = float(plan.get('atr') or 0), plan.get('stop_ref')
        targets = list(plan.get('targets') or ())[:3]
        if direction not in (-1, 1) or not atr or ref is None or not targets or not entry:
            return None
        sl = float(ref) - direction * 0.25 * atr
        risk = direction * (entry - sl)
        if risk <= 0 or sl <= 0:
            return None
        targets += [targets[-1]] * (3 - len(targets))
        from strategies.geometry import cost_of
        fee = cost_of(entry, plan.get('volume_24h'), plan.get('symbol'))
        rr = [(direction * (t - entry) - fee) / (risk + fee) for t in targets]
        plan['contract_source'] = 'oi_build_pring'
        src = list(plan.get('target_src') or ()) + ['opposite liquidity'] * 3
        return {'entry': float(entry), 'sl': sl, 'tp1': targets[0], 'tp2': targets[1], 'tp3': targets[2],
                'rr_tp1': rr[0], 'rr_tp2': rr[1], 'rr_blend': sum(rr) / 3, 'low_rr': False, 'rr_reason': None,
                'risk_units': 1.0, 'risk0': risk, 'stop_pierce': None,
                'sl_src': "beyond hour's extreme + 0.25 ATR", 'tp1_src': src[0], 'tp2_src': src[1], 'tp3_src': src[2],
                'zone_src': plan.get('zone_src'), 'range_pos': None, 'limit_entry': None,
                'volume_24h': plan.get('volume_24h')}

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('anchor_ts'), 'oi_build') if x.sig.get('oi_build_oi60') is not None else None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        from strategies.maniac_strategies import _confirm_plan
        if x.sig.get('oi_build_oi60') is None:
            return None
        exit = {'stop': ['price', x.sig['anchor_extreme']], 'tp': ['map', 0.0], 'atr': x.atr,
                'stop_src': "beyond the hour's extreme", 'tp_src': 'the opposite liquidity'}
        targets, sources = _oi_targets(x, x.direction)
        return _confirm_plan(x, self.name, '15m', exit, "Pring: price and OI (faster than its average) together",
                             stop_ref=x.sig['anchor_extreme'], intent='opposite_liquidity',
                             contract_targets=targets, contract_target_src=sources)
