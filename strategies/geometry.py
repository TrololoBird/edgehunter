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
from zones import STRUCTURE_KINDS, Zone, is_pool, stop_beyond

MEAN_KINDS = ('vwap', 'poc', 'va', 'hvn')


def cost_of(price: float, volume_24h: Optional[float] = None) -> float:
    """
    (volume_24h: the coin's; the slippage then grows as liquidity falls, levels.slippage_bps - the same model the
    journal's replay fills with, so an entry that passes R:R here is not a loser there by construction)
    Execution cost of a round trip in price units: the taker fees (0.05% a side at Binance VIP0) plus the slippage of
    a market entry and of a stop exit (levels.slippage_bps each). Fees alone made a 1-ATR stop on a quiet coin look
    ~0.3R cheaper than it trades.
    """
    from levels import slippage_bps
    return (CONFIG.journal.fee_round_trip + 2 * slippage_bps(volume_24h) / 1e4) * price


from pierce import model as _overshoot_model, measured_kind, overshoot  # noqa: E402  (measured level pierce)


def kind_at(zones: List[Zone], price: float) -> Optional[str]:
    """The measured kind of the map zone a stop base sits on (the zone's own kinds, not its text label)."""
    for z in zones:
        if z.lo - 1e-12 <= price <= z.hi + 1e-12:
            kind = measured_kind(z.kinds)
            if kind:
                return kind
    return None


def kind_of_label(label: str, tf: str) -> str:
    """The level kind behind a stop's source label (for its measured buffer)."""
    s = label or ''
    if 'EQ' in s:
        return 'equal'
    if any(k in s for k in ('PDH', 'PDL', 'PWH', 'PWL', 'London', 'New York', 'Asia', 'day high', 'day low')):
        return 'pdhl'
    if 'round' in s:
        return 'round'
    return 'swing_1h' if tf in ('1h', '4h') or '1h' in s else 'swing_15m'


def stop_floor(atr: float, recent_atr: Optional[float]) -> float:
    """Minimum stop distance: min_stop_atr x the larger of ATR14 and the last hour's ATR (ATR14 lags a waking market)."""
    return CONFIG.levels.min_stop_atr * max(atr, recent_atr or 0.0)


def _near(zone: Zone, direction: int) -> float:
    return zone.lo if direction > 0 else zone.hi


def map_fill(zones: List[Zone], prices: List[float], labels: List[str], ref: float, direction: int,
             gap: float) -> None:
    """
    Fill the empty target slots (up to 3) with the nearest map zones beyond the last target, ANY strength (a single
    swing, a session high, an FVG, an order block): a level on the chart before an ATR step (the steps sat in empty
    space while levels stood right there, 2026-10-01: TP2 / TP3 were ATR steps on 18 / 21 of 35 entries).
    """
    last = prices[-1] if prices else ref
    for z in sorted((z for z in zones if direction * (_near(z, direction) - last) >= gap),
                    key=lambda z: direction * (_near(z, direction) - last)):
        if len(prices) >= 3:
            return
        price = _near(z, direction)
        if direction * (price - last) >= gap:
            prices.append(price)
            labels.append(z.label)
            last = price


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
    map_fill(zones, prices, labels, ref, direction, gap)
    last = prices[-1] if prices else ref
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
        prot = plan.get('protected')
        if prot is not None and direction * (entry - prot) > 0 and (ref is None or direction * (ref - prot) > 0):
            # ICT: the stop beyond the swing that broke structure, not right behind an unswept pool
            ref, label = prot, 'beyond the protected swing (BOS)'
        base, src = stop_beyond(zones, ref, entry, direction, plan.get('leg_atr') or atr, label, plan.get('symbol'))
    kind = kind_at(zones, base) or kind_of_label(src, plan.get('tf', '15m'))
    measured = overshoot(plan.get('symbol'), kind, base)
    if measured is not None:
        # the measured pierce of this kind of level on this coin, no ATR constants: a stop closer than where price
        # usually pierces before turning back is inside the level's noise; a stop so far that it does not pay is a
        # wrong entry (low_rr), not a reason to move it closer
        return base - direction * measured, f"{src} + measured pierce {measured / base:.2%}"
    stop = base - direction * cfg.stop_buffer_atr * (plan.get('leg_atr') or atr)
    # the floor in the structure's own ATR too (a 1h / 4h leg's stop floored by the 15m ATR sat inside its noise)
    floor = stop_floor(max(atr, plan.get('leg_atr') or 0.0), plan.get('recent_atr'))
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


def structure_stop(zones: List[Zone], entry: float, direction: int, atr: float, floor: float,
                   symbol: Optional[str] = None, tf: str = '15m') -> Optional[Tuple[float, str]]:
    """
    Stop beyond the nearest price-action structure on the stop side (swings, equal highs / lows, previous day / week /
    sessions, range edges, round numbers, book bands) that leaves at least `floor` of risk, pushed beyond a stop pool
    right behind it, plus the ATR buffer. None when no such structure lies within max_stop_atr ATR (price discovery:
    then the fixed rule is all there is).
    """
    cfg = CONFIG.levels
    cands = []
    for z in zones:
        if not any(k in STRUCTURE_KINDS for k in z.kinds):
            continue
        edge = z.lo if direction > 0 else z.hi
        if direction * (entry - edge) <= 0:
            continue
        kind = next((k for k in z.kinds if k in ('equal', 'pdhl', 'round', 'swing_1h', 'swing_15m')), 'swing_15m')
        measured = overshoot(symbol, kind, edge)
        if measured is not None:
            # measured buffer; no minimum and no maximum: a structure too far away makes the entry low_rr
            cands.append((direction * (entry - edge) + measured, edge, z, measured))
        else:
            buffer = cfg.stop_buffer_atr * atr
            dist = direction * (entry - edge) + buffer
            if floor <= dist <= CONFIG.zones.max_stop_atr * atr:
                cands.append((dist, edge, z, buffer))
    if not cands:
        return None
    _, edge, z, buffer = min(cands, key=lambda c: c[0])
    base, src = stop_beyond(zones, edge, entry, direction, atr, f"beyond {z.label}", symbol)
    return base - direction * buffer, src


def system_levels(plan: Dict, entry: float, extreme: Optional[float], direction: int) -> Optional[Dict]:
    """
    Entry / stop / targets of the ported systems (strategies/maniac.py). Their own structural exits (beyond the sweep,
    the impulse's start, a level) are kept. Their FIXED exits (a % or ATR stop, a % or R target) ignore the map: a 1%
    stop on SUI (15m ATR 1.35%) sat inside one candle's noise and was taken before the move (live, 2026-09-30). Those
    are replaced by the map: the stop beyond the nearest structure, the targets at the next levels; the fixed rule is
    only the fallback where the map has nothing (price discovery).
    """
    exit = plan['exit']
    atr = exit.get('atr') or plan['atr']
    if exit['tp'][0] == 'trail':
        # a system without a profit target (the Turtles: out on the opposite N-day channel, SignalBook trails it):
        # its own stop; TP1-3 are 100 / 200 / 300 R placeholders the lifecycle never reaches (R:R never vetoes it)
        stop = exit['stop'][1]
        risk = direction * (entry - stop)
        if risk <= 0:
            return None
        label = exit.get('tp_src', 'none (trailing exit)')
        return {'entry': entry, 'sl': stop, 'tp1': entry + direction * 100 * risk, 'tp2': entry + direction * 200 * risk,
                'tp3': entry + direction * 300 * risk, 'rr_tp1': 100.0, 'rr_tp2': 200.0, 'low_rr': False,
                'tp1_src': label, 'tp2_src': label, 'tp3_src': label, 'sl_src': exit.get('stop_src', 'the system stop')}
    floor = stop_floor(max(atr, plan['atr']), plan.get('recent_atr'))
    zones: List[Zone] = plan.get('zones') or []
    fixed_stop = exit['stop'][0] in ('pct', 'atr')
    fixed_tp = exit['tp'][0] in ('pct', 'rr')
    structural = structure_stop(zones, entry, direction, atr, floor, plan.get('symbol'), plan.get('tf', '15m')) \
        if fixed_stop else None
    prot = plan.get('protected')
    if structural is not None and prot is not None and direction * (entry - prot) > 0 \
            and direction * (structural[0] - prot) > 0:
        # ICT: beyond the protected swing (the one that broke structure) when it lies beyond the nearest structure
        buffer = overshoot(plan.get('symbol'), 'swing_15m', prot)
        base, src = stop_beyond(zones, prot, entry, direction, atr, 'beyond the protected swing (BOS)',
                                plan.get('symbol'))
        structural = (base - direction * (buffer if buffer is not None else CONFIG.levels.stop_buffer_atr * atr), src)
    if structural is not None:
        stop, sl_src = structural
    elif exit['stop'][0] == 'ref' and overshoot(plan.get('symbol'), 'swing_15m', entry) is not None:
        # the system's own structural reference (beyond the sweep / the zone / the test), but the buffer beyond it is
        # the measured pierce of this coin (live: GRT's demand stop sat 0.35% under the zone, inside the usual pierce)
        refs = [r for r in (plan.get('stop_ref'), extreme) if r is not None]
        ref = (min(refs) if direction > 0 else max(refs)) if refs else entry
        base, src = stop_beyond(zones, ref, entry, direction, atr, exit.get('stop_src', 'beyond the extreme'),
                                plan.get('symbol'))
        pad = overshoot(plan.get('symbol'), kind_at(zones, base) or kind_of_label(src, plan.get('tf', '15m')), base)
        stop, sl_src = base - direction * pad, f"{src} + measured pierce {pad / base:.2%}"
    else:
        stop, sl_src = exit_stop(exit, plan, entry, extreme, direction)
    risk = direction * (entry - stop)
    if 0 < risk < floor and not _overshoot_model():
        stop, risk = entry - direction * floor, floor
        sl_src = f"{sl_src}, widened to {CONFIG.levels.min_stop_atr:g} ATR"
    if fixed_tp and zones:
        targets, sources = select_targets(zones, entry, direction, atr, 'opposite_liquidity')
        if targets and sources[0] != 'ATR step':
            tp1, tp2, tp3 = targets[:3]
            fee = cost_of(entry, plan.get('volume_24h'))
            rr1 = (abs(tp1 - entry) - fee) / (risk + fee)
            return {'entry': entry, 'sl': stop, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3, 'rr_tp1': rr1,
                    'rr_tp2': (abs(tp2 - entry) - fee) / (risk + fee), 'low_rr': rr1 < CONFIG.levels.min_rr_tp1,
                    'tp1_src': sources[0], 'tp2_src': sources[1], 'tp3_src': sources[2], 'sl_src': sl_src}
    if risk <= 0 or (exit.get('min_risk_atr') and risk < exit['min_risk_atr'] * atr):
        return None
    tp1, src1, low = exit_target(exit, plan, entry, risk, direction)
    if tp1 is None:
        return None
    gap = CONFIG.zones.min_target_atr * atr
    # TP2 / TP3: the system's own second target where it has one (the OI robot's 4% / 6%), else the next levels on
    # the map beyond TP1 (any strength); ATR steps only where the map is empty (was: always TP1 + 1 ATR, + 2 ATR)
    prices, labels = [tp1], [src1]
    if exit.get('tp2'):
        tp2, src2, _ = exit_target({**exit, 'tp': exit['tp2']}, plan, entry, risk, direction)
        if tp2 is not None and direction * (tp2 - tp1) > 0:
            prices.append(tp2)
            labels.append(src2)
    map_fill(zones, prices, labels, entry, direction, gap)
    while len(prices) < 3:
        prices.append(prices[-1] + direction * gap)
        labels.append('ATR step')
    tp2, tp3 = prices[1], prices[2]
    src2, src3 = labels[1], labels[2]
    fee = cost_of(entry, plan.get('volume_24h'))
    rr1 = (abs(tp1 - entry) - fee) / (risk + fee)
    # our minimum applies to the ported systems too (their own flag only knew the author's R:R rule: REZ FIB 0.5 was
    # entered at 0.74)
    return {'entry': entry, 'sl': stop, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3, 'rr_tp1': rr1,
            'rr_tp2': (abs(tp2 - entry) - fee) / (risk + fee), 'low_rr': low or rr1 < CONFIG.levels.min_rr_tp1,
            'tp1_src': src1, 'tp2_src': src2, 'tp3_src': src3, 'sl_src': sl_src}


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
        map_fill(plan.get('zones') or [], targets, sources, entry, direction, gap)
        while targets and len(targets) < 3:
            targets.append(targets[-1] + direction * gap)
            sources.append('ATR step')
    if not targets:
        return None
    tp1, tp2, tp3 = targets[:3]
    fee = cost_of(entry, plan.get('volume_24h'))
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
