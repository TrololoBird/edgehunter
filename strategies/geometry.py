"""
Geometry shared by every strategy: the stop floor, the stop pushed beyond a stop pool, targets picked from the coin's
level map by the strategy's INTENT, the entry levels and R:R, and the R:R cap of a waiting zone.

Target intents (the strategy says what it trades toward; Fibonacci only where a real leg exists):
- 'extension'          continuation: strong zones beyond the leg's end, the leg's extensions fill empty slots;
- 'opposite_liquidity' a sweep: the nearest resting-stop pools on the other side first;
- 'mean'               absorption / exhaustion / climaxes: VWAP, POC, value area, volume nodes first;
- 'range'              a trading range's far side first;
- 'measured'           a breakout: strong zones beyond the edge, measured moves of the range fill empty slots.
A target is always >= zones.min_target_atr beyond its reference (and beyond the previous target); slots still empty are
1-ATR steps ('ATR step'), never copies of one level.
"""
from typing import Dict, List, Optional, Sequence, Tuple

from config import CONFIG
from zones import Zone, is_pool, stop_beyond

MEAN_KINDS = ('vwap', 'poc', 'va', 'hvn')


def cost_of(price: float) -> float:
    """
    Execution cost of a round trip in price units: the taker fees (0.05% a side at Binance VIP0) plus the slippage of
    a market entry and of a stop exit (levels.slippage_bps each). Fees alone made a 1-ATR stop on a quiet coin look
    ~0.3R cheaper than it trades.
    """
    return (CONFIG.journal.fee_round_trip + 2 * CONFIG.levels.slippage_bps / 1e4) * price


def stop_floor(atr: float, recent_atr: Optional[float]) -> float:
    """Minimum stop distance: min_stop_atr x the larger of ATR14 and the last hour's ATR (ATR14 lags a waking market)."""
    return CONFIG.levels.min_stop_atr * max(atr, recent_atr or 0.0)


def _near(zone: Zone, direction: int) -> float:
    return zone.lo if direction > 0 else zone.hi


def select_targets(zones: List[Zone], ref: float, direction: int, atr: float, intent: str,
                   fillers: Sequence[float] = (), fill_label: str = 'fib',
                   first: Optional[Tuple[float, str]] = None) -> Tuple[List[float], List[str]]:
    """
    Up to three targets beyond `ref` in the trade's direction by the strategy's intent; `first` forces a primary
    objective (a range's far side) into the candidates. Returns (prices, labels).
    """
    cfg = CONFIG.zones
    gap = cfg.min_target_atr * atr
    beyond = [z for z in zones if direction * (_near(z, direction) - ref) >= gap]
    beyond.sort(key=lambda z: direction * (_near(z, direction) - ref))
    strong = [z for z in beyond if z.strength >= cfg.min_strength]
    if intent == 'opposite_liquidity':
        primary = [z for z in beyond if is_pool(z)]
    elif intent == 'mean':
        primary = [z for z in beyond if any(k in MEAN_KINDS for k in z.kinds)]
    else:
        primary = strong
    # (price, label, preference: 0 primary, 1 strong, 2 the anchor's own objective). The anchor's objectives (measured
    # moves, Fibonacci) compete with map zones by distance: filled in only after the zones, a breakout with no zone
    # nearby got a week-old 1h low 35% away as TP1 (R:R 19.8) and passed the R:R check on a target it never reaches
    candidates: List[Tuple[float, str, int]] = []
    if first is not None and direction * (first[0] - ref) >= gap:
        candidates.append((first[0], first[1], 0))
    candidates += [(_near(z, direction), z.label, 0) for z in primary]
    candidates += [(_near(z, direction), z.label, 1) for z in strong if z not in primary]
    candidates += [(f, fill_label, 2) for f in fillers if direction * (f - ref) >= gap]
    candidates.sort(key=lambda c: direction * (c[0] - ref))
    prices: List[float] = []
    labels: List[str] = []
    last = ref
    for price, label, pref in candidates:
        if len(prices) == 2:
            break
        # TP1 / TP2: the nearest primary or strong levels, spaced
        if direction * (price - last) >= gap:
            prices.append(price)
            labels.append(label)
            last = price
    if len(prices) == 2:
        # TP3 prefers the intent's primary kind beyond TP2 (pools for sweeps, means for reversions ...)
        rest = [c for c in candidates if direction * (c[0] - last) >= gap]
        pick = next((c for c in rest if c[2] == 0), rest[0] if rest else None)
        if pick is not None:
            prices.append(pick[0])
            labels.append(pick[1])
            last = pick[0]
    for f in sorted(fillers, key=lambda x: direction * (x - ref)):
        if len(prices) == 3:
            break
        if direction * (f - last) >= gap:
            prices.append(f)
            labels.append(fill_label)
            last = f
    while prices and len(prices) < 3:
        last = last + direction * gap
        prices.append(last)
        labels.append('ATR step')
    if not prices:
        # Nothing on the map and no fillers: ATR steps from the reference
        prices = [ref + direction * gap * k for k in (1, 2, 3)]
        labels = ['ATR step'] * 3
    return prices, labels


def stop_levels(plan: Dict, entry: float, extreme: Optional[float], direction: int) -> Tuple[float, str]:
    """
    The stop: beyond the strategy's reference (the anchor's extreme / the range middle / the trigger's swing) and a
    stop pool just behind it, then the ATR buffer, never closer than the stop floor.
    """
    cfg = CONFIG.levels
    atr = plan['atr']
    zones: List[Zone] = plan.get('zones') or []
    if plan.get('stop_mid') is not None:
        base, src = plan['stop_mid'], plan.get('stop_mid_src', 'range middle')
    else:
        # the farthest of the strategy's structural reference (a zone's edge, the anchor's extreme) and the deepest
        # wick that tested it since price came into the zone (the trigger's extreme)
        ref, label = plan.get('stop_ref'), plan.get('stop_ref_src') or 'beyond the swing'
        if ref is None or (extreme is not None and direction * (ref - extreme) > 0):
            if ref is not None:
                label = 'beyond the test wick'
            ref = extreme
        base, src = stop_beyond(zones, ref, entry, direction, plan.get('leg_atr') or atr, label)
    stop = base - direction * cfg.stop_buffer_atr * (plan.get('leg_atr') or atr)
    floor = stop_floor(atr, plan.get('recent_atr'))
    if direction * (entry - stop) < floor:
        stop = entry - direction * floor
        src = f"{src}, widened to the {cfg.min_stop_atr:g}x volatility floor"
    return stop, src


def exit_stop(exit: Dict, plan: Dict, entry: float, extreme: Optional[float], direction: int) -> Tuple[float, str]:
    """A system's own stop rule (plan['exit']['stop']): ['pct', f] / ['atr', k] / ['ref', pad ATR] / ['price', p]."""
    kind, value = exit['stop'][0], exit['stop'][1]
    atr = exit.get('atr') or plan['atr']
    if kind == 'pct':
        return entry * (1 - direction * value), f"{value:.2%} from the entry"
    if kind == 'atr':
        return entry - direction * value * atr, f"{value:g} ATR from the entry"
    if kind == 'price':
        return value, exit.get('stop_src', 'the system stop')
    refs = [r for r in (plan.get('stop_ref'), extreme) if r is not None]
    ref = (min(refs) if direction > 0 else max(refs)) if refs else entry
    return ref - direction * value * atr, exit.get('stop_src', 'beyond the extreme') + (f" + {value:g} ATR" if value else '')


def exit_target(exit: Dict, plan: Dict, entry: float, risk: float, direction: int) -> Tuple[Optional[float], str, bool]:
    """
    A system's own first target (plan['exit']['tp']): ['pct', f] / ['rr', r] / ['level', price, min R:R, fallback R]
    (the level when it pays min R:R, else the system skips - `low` True; no level -> fallback R) / ['map', min R:R]
    (the map's TP1). Returns (price, label, below the system's minimum R:R).
    """
    spec = exit['tp']
    kind = spec[0]
    if kind == 'pct':
        return entry * (1 + direction * spec[1]), f"{spec[1]:.1%} from the entry", False
    if kind == 'rr':
        return entry + direction * spec[1] * risk, f"{spec[1]:g} R", False
    if kind == 'level':
        price, min_rr, fallback = spec[1], spec[2], spec[3]
        if price is not None and direction * (price - entry) > 0:
            rr = direction * (price - entry) / risk
            if rr >= min_rr:
                return price, exit.get('tp_src', 'the system target'), False
            if not exit.get('fallback_when_close'):
                return price, exit.get('tp_src', 'the system target'), True
        if fallback is None:
            return None, '', True
        return entry + direction * fallback * risk, f"{fallback:g} R", False
    ahead = [(t, s) for t, s in zip(plan['targets'], plan['target_src']) if direction * (t - entry) > 0]
    if not ahead:
        return None, '', True
    t, s = ahead[0]
    return t, s, direction * (t - entry) / risk < spec[1]


def system_levels(plan: Dict, entry: float, extreme: Optional[float], direction: int) -> Optional[Dict]:
    """Entry / stop / targets by the system's own exit rules (the ported systems of strategies/maniac.py)."""
    exit = plan['exit']
    stop, sl_src = exit_stop(exit, plan, entry, extreme, direction)
    risk = direction * (entry - stop)
    atr = exit.get('atr') or plan['atr']
    if risk <= 0 or (exit.get('min_risk_atr') and risk < exit['min_risk_atr'] * atr):
        return None
    tp1, src1, low = exit_target(exit, plan, entry, risk, direction)
    if tp1 is None:
        return None
    gap = CONFIG.zones.min_target_atr * atr
    tp2, src2 = tp1 + direction * gap, 'ATR step'
    if exit.get('tp2'):
        # the system's own second target (the OI robot's 4% / 6% take-profits)
        tp2, src2, _ = exit_target({**exit, 'tp': exit['tp2']}, plan, entry, risk, direction)
        if tp2 is None or direction * (tp2 - tp1) <= 0:
            tp2, src2 = tp1 + direction * gap, 'ATR step'
    tp3 = tp2 + direction * gap
    fee = cost_of(entry)
    rr1 = (abs(tp1 - entry) - fee) / (risk + fee)
    return {'entry': entry, 'sl': stop, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3, 'rr_tp1': rr1,
            'rr_tp2': (abs(tp2 - entry) - fee) / (risk + fee), 'low_rr': low,
            'tp1_src': src1, 'tp2_src': src2, 'tp3_src': 'ATR step', 'sl_src': sl_src}


def entry_levels(plan: Dict, entry: float, extreme: Optional[float], direction: int) -> Optional[Dict]:
    """Entry / stop / targets for an entry at `entry` (targets behind the entry are dropped, refilled beyond it)."""
    if plan.get('exit'):
        return system_levels(plan, entry, extreme, direction)
    stop, sl_src = stop_levels(plan, entry, extreme, direction)
    risk = abs(entry - stop)
    if not risk or direction * (entry - stop) <= 0:
        return None
    atr = plan.get('leg_atr') or plan['atr']            # targets are spaced in the structure's own ATR
    if plan.get('retarget'):
        # Continuation: re-measured from the real entry
        targets, sources = select_targets(plan.get('zones') or [], entry, direction, atr, plan['intent'],
                                          plan.get('fillers', ()), plan.get('fill_label', 'fib'))
    else:
        ahead = [(t, s) for t, s in zip(plan['targets'], plan['target_src']) if direction * (t - entry) > 0]
        kept: List[Tuple[float, str]] = []
        for t, s in ahead:
            if not kept or direction * (t - kept[-1][0]) > 0:
                kept.append((t, s))
        targets, sources = [t for t, _ in kept], [s for _, s in kept]
        gap = CONFIG.zones.min_target_atr * atr
        fillers = [f for f in plan.get('fillers', ()) if not targets or direction * (f - targets[-1]) > 0]
        for f in sorted(fillers, key=lambda x: direction * (x - entry)):
            if len(targets) == 3:
                break
            if direction * (f - (targets[-1] if targets else entry)) >= gap:
                targets.append(f)
                sources.append(plan.get('fill_label', 'fib'))
        while targets and len(targets) < 3:
            targets.append(targets[-1] + direction * gap)
            sources.append('ATR step')
    if not targets:
        return None
    tp1, tp2, tp3 = targets[:3]
    fee = cost_of(entry)
    rr1 = (abs(tp1 - entry) - fee) / (risk + fee)
    return {'entry': entry, 'sl': stop, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3,
            'rr_tp1': rr1, 'rr_tp2': (abs(tp2 - entry) - fee) / (risk + fee), 'low_rr': rr1 < CONFIG.levels.min_rr_tp1,
            'tp1_src': sources[0], 'tp2_src': sources[1], 'tp3_src': sources[2], 'sl_src': sl_src}


def cap_for_rr(tp1: float, stop_est: float, direction: int, atr: float, recent_atr: Optional[float]) -> float:
    """
    The furthest entry (from the extreme toward TP1) that still pays min_rr_tp1 (net of fees) to TP1 with the stop at `stop_est`
    or the stop floor, whichever is wider: a waiting zone ends there.
    """
    rr = CONFIG.levels.min_rr_tp1
    fee = cost_of(tp1)                                  # R:R is net of the execution cost (entry_levels)
    by_stop = (tp1 + rr * stop_est - direction * (1 + rr) * fee) / (1 + rr)
    by_floor = tp1 - direction * (rr * stop_floor(atr, recent_atr) + (1 + rr) * fee)
    return min(by_stop, by_floor) if direction > 0 else max(by_stop, by_floor)
