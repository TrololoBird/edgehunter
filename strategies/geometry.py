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
from strategies.base import CardLevels  # noqa: F401  (the return type of entry_levels)
from typing import Dict, List, Optional, Sequence, Tuple

from config import CONFIG
from zones import POOL_KINDS, STRUCTURE_KINDS, Zone, stop_beyond

MEAN_KINDS = ('vwap', 'poc', 'va', 'hvn')


def cost_of(price: float, volume_24h: Optional[float] = None, symbol: Optional[str] = None) -> float:
    """
    (volume_24h: the coin's; the slippage then grows as liquidity falls, levels.slippage_bps - the same model the
    journal's replay fills with, so an entry that passes R:R here is not a loser there by construction)
    Execution cost of a round trip in price units: the taker fees (0.05% a side at Binance VIP0) plus the slippage of
    a market entry and of a stop exit (levels.slippage_bps each). Fees alone made a 1-ATR stop on a quiet coin look
    ~0.3R cheaper than it trades.
    """
    from levels import slippage_bps
    return (CONFIG.journal.fee_round_trip + 2 * slippage_bps(volume_24h, symbol) / 1e4) * price


from pierce import measured_kind, overshoot  # noqa: E402  (measured level pierce)


def stop_pierce(plan: Dict, stop: float) -> Optional[str]:
    """
    eng-124: no source names the pierce quantile of a stop's buffer (p50 / p80 / p90) - the stop's level kind and its
    three measured quantiles (% of price) are journaled with each entry; with the row's sl / mae_4h / mfe_4h they show
    which buffer the stopped trades would have survived, to choose the quantile on live trades.
    """
    zones = plan.get('zones') or []
    try:
        kind = kind_at(htf_zones(zones, plan.get('target_tf') or plan.get('tf')), stop) if zones else None
    except Exception:
        kind = None
    kind = kind or 'swing_15m'
    qs = [overshoot(plan.get('symbol'), kind, stop, q) for q in ('p50', 'p80', 'p90')]
    if any(q is None for q in qs):
        return None
    return f"{kind} " + '/'.join(f"{100 * q / stop:.3f}" for q in qs)


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


def stop_too_far(plan: Dict, entry: float, stop: float) -> Optional[str]:
    """eng-91: a stop farther than levels.max_stop_pct from the entry is no trade (the 1.5 ATR(4h) pad of a coin whose 4h
    ATR a pump inflated put W's stop 48% away, PONS' 18% - live). Systems whose wide stop IS the method (the Turtles' 2N,
    Connors) are exempt."""
    cap = CONFIG.levels.max_stop_pct
    if not cap or not entry or plan.get('strategy') in ('breakout', 'connors'):
        return None
    dist = abs(entry - stop) / entry
    return f"stop {dist:.1%} > {cap:.0%} from the entry" if dist > cap else None


def stop_floor(atr: float, recent_atr: Optional[float]) -> float:
    """Minimum stop distance: min_stop_atr x the larger of ATR14 and the last hour's ATR (ATR14 lags a waking market)."""
    return CONFIG.levels.min_stop_atr * max(atr, recent_atr or 0.0)


def _near(zone: Zone, direction: int) -> float:
    return zone.lo if direction > 0 else zone.hi


TF_RANK = {'5m': 0, '15m': 1, '1h': 2, '4h': 3, '1d': 4, '1w': 5}


# untimed kinds that are references of a day or longer (valid for a plan of any timeframe)
HTF_UNTIMED = ('pdhl', 'pmhl', 'year', 'open', 'range', 'poc', 'va')
# untimed kinds built from intraday data: they rank as 15m (a 15m-swing zone does not become a 4h target through them)
LTF_UNTIMED = ('vwap', 'round', 'book', 'liq_est', 'liq_hit', 'liq_hl', 'equal', 'hvn', 'lvn', 'wall')


def _kind_rank(k: str) -> Optional[int]:
    """One level kind's timeframe rank (see _zone_rank); None = valid on every timeframe."""
    tf = k.rsplit('_', 1)[-1] if '_' in k else None
    if tf in TF_RANK:
        return TF_RANK[tf]
    if k in LTF_UNTIMED:
        return TF_RANK['15m']
    return None                            # HTF_UNTIMED or an unknown kind: valid everywhere (as before)


def _zone_rank(zone: Zone) -> Optional[int]:
    """The highest timeframe rank among the zone's kinds (swing_15m, fvg_1h, ob_4h ...); None = valid on every
    timeframe (it holds a daily-or-longer untimed reference: previous day / week / month, the year, an open, a completed
    day's profile, a range); intraday untimed kinds (VWAP, round, book, liquidations, equal highs / lows, profile nodes)
    rank as 15m. A plan may target the zone when this rank >= its own timeframe's."""
    best = -1
    for k in zone.kinds:
        r = _kind_rank(k)
        if r is None:
            return None
        best = max(best, r)
    return best if best >= 0 else None


def _trim(zone: Zone, rank: int) -> Zone:
    """audit D05: the zone as a plan of timeframe rank `rank` sees it - the edges of its own levels only. A lower
    timeframe's level merged into a 1h swing's zone moved the 1h target (130.1 -> 129.9, R:R 3.01 -> 2.99)."""
    if not zone.parts:
        return zone
    own = [p for p in zone.parts if (_kind_rank(p[0]) is None or _kind_rank(p[0]) >= rank)]
    if not own or len(own) == len(zone.parts):
        return zone
    return Zone(sum(p[1] for p in own) / len(own), min(p[2] for p in own), max(p[3] for p in own),
                [k for k in zone.kinds if any(p[0] == k for p in own)], zone.labels, zone.strength, zone.ts, own,
                zone.origin or id(zone))


def htf_zones(zones: List[Zone], tf: Optional[str]) -> List[Zone]:
    """The zones a plan of timeframe `tf` may target: its own timeframe and higher (2026-10-05, the owner: a 1h / 4h
    trade's TP1 was the nearest 15m swing / FVG, cutting the R:R of a stop now sized in the structure's ATR). A merged
    zone is cut back to the edges of the levels that qualify."""
    rank = TF_RANK.get(tf or '15m', 1)
    if rank <= 1:
        return zones
    return [_trim(z, rank) for z in zones if (_zone_rank(z) is None or _zone_rank(z) >= rank)]


def _ltf_prices(zones: List[Zone], tf: Optional[str], direction: int) -> List[float]:
    keep = {z.origin or id(z) for z in htf_zones(zones, tf)}
    # both prices a zone can be targeted at: the near edge and (liquidity intents) the swing's extreme
    return [px for z in zones if id(z) not in keep for px in {_near(z, direction), _liq_price(z, direction)}]


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


def is_synthetic(label: Optional[str]) -> bool:
    """A target that is no price level: an ATR step, an R multiple, a placeholder ('none: ...')."""
    if not label:
        return True
    import re
    return label == 'ATR step' or bool(re.fullmatch(r'[0-9.]+ R', label)) or label.startswith('none')


# (strategy -> (p(TP1 before the stop), n, upper end of p's 95% Wilson interval)) measured by the journal's replay
# (journal.refresh_hit_rates, hourly): the entry is vetoed when its expectancy is negative even at the upper end
# setup -> (p TP1, n, upper 95% of p TP1, upper of p TP2, upper of p TP3)
HIT_RATE: Dict[str, Tuple[float, ...]] = {}


def setup_key(name: Optional[str]) -> str:
    """HIT_RATE's key: the setup without the journal's 'ENTRY ' prefix (audit C13)."""
    name = (name or '').strip()
    return name[6:] if name.upper().startswith('ENTRY ') else name


def finish_levels(plan: Dict, entry: float, stop: float, targets: List[float], sources: List[str], direction: int,
                  sl_src: str, low: bool = False) -> Optional[Dict]:
    """
    Entry / stop / three targets and the R:R checks, the same for every path (eng-41):
    - a LEVEL target sits in front of its level by the level kind's typical pierce (p50): price often turns before
      the level, and the replay counts a target only once traded through it - the old target on the level overstated
      R:R by about that pierce;
    - R:R is measured on the level targets only (an ATR step / an R multiple / a placeholder passes any threshold by
      construction - SMT's '2.5 R' targets: 2 of 44 reached); ATR steps count where the map holds nothing beyond the
      entry at all (price discovery - the owner's rule);
    - the R:R that decides is the BLENDED one of the actual exit (a third at each target; a missing level slot exits
      at the last level);
    - risk must be >= cost_guard x the round-trip execution cost (audit F09: the text said 3x / 'a third of the
      risk'; the rule is CONFIG.levels.cost_guard, 1 since eng-108 - the risk at least pays one round trip)
    - with a journal-measured p(TP_k before the stop) for the setup the entry must have a positive expectancy of its
      three thirds, sum_k (p_k x R:R_k - (1 - p_k)) / 3 at the upper ends of the Wilson intervals; the method's
      minimum R:R (Strategy.min_rr, else the global one) holds as well.
    """
    risk = direction * (entry - stop)
    if risk <= 0 or not targets:
        return None
    sym, tf = plan.get('symbol'), plan.get('tf', '15m')
    zones: List[Zone] = plan.get('zones') or []
    # the pierce kind of a target from the zones its timeframe may target (merged lower-timeframe swings outweighed a
    # 1h swing in the raw zone's kinds and gave it the 15m pierce)
    kind_zones = htf_zones(zones, plan.get('target_tf') or tf)
    adj, on_map = [], []
    for t, s in zip(targets, sources):
        # a target ON a map zone of any kind (eng-74: was 'a zone of a MEASURED kind' - a Hyperliquid account's
        # liquidation price (liq_hl) has no pierce model, so NEAR's +76% / +100% TP2 / TP3 passed the reach check and
        # made a 0.31 R:R a blended 8.9); the anchor's own objectives (extensions, measured moves) stay exempt
        on_map.append(not is_synthetic(s) and any(z.lo - 1e-9 * abs(t) <= t <= z.hi + 1e-9 * abs(t) for z in zones))
        if not is_synthetic(s):
            kind = kind_at(kind_zones, t) or kind_at(zones, t) or kind_of_label(s, tf)
            p50 = overshoot(sym, kind, t, 'p50') if kind else None
            if p50 and direction * (t - direction * p50 - entry) > 0:
                t = t - direction * p50
        adj.append(t)
    # eng-132: the pierce pulls each target by its own kind's p50, so a nearer level of a deeper-piercing kind could end
    # behind a farther one: nearest first again (TP1 < TP2 < TP3), sources and map flags following their targets
    order = sorted(range(len(adj)), key=lambda i: direction * adj[i])
    targets = [adj[i] for i in order]
    sources = [sources[i] for i in order] + list(sources[len(adj):])
    on_map = [on_map[i] for i in order]
    while len(targets) < 3:
        targets.append(targets[-1])
        sources.append(sources[-1])
        on_map.append(on_map[-1])
    fee = cost_of(entry, plan.get('volume_24h'), plan.get('symbol'))
    rrs = [(abs(t - entry) - fee) / (risk + fee) for t in targets[:3]]
    beyond_map = not any(direction * ((z.lo if direction > 0 else z.hi) - entry) > 0 for z in zones)
    real = [not is_synthetic(s) or (s == 'ATR step' and beyond_map) for s in sources[:3]]
    # a MAP zone the trade cannot reach in its lifetime is no target: 3 sd of a random walk over the time stop's bars
    # (time_stop_bars x time_after_tp1) in the structure timeframe's ATR. FET AUCTION LONG 2026-10-07 judged a 15m POC
    # retest by TP2 / TP3 at the 52-week high +151% / +183% (blended R:R 28). The anchor's own objectives (extensions,
    # measured moves) are the method's targets and stay
    tf_atr = max(plan.get('tf_atr') or 0.0, plan.get('atr') or 0.0, plan.get('leg_atr') or 0.0)
    if tf_atr > 0:
        cfg = CONFIG.strategies
        reach = 3 * tf_atr * (cfg.time_stop_bars * cfg.time_after_tp1) ** 0.5
        for k in range(3):
            if real[k] and on_map[k] and direction * (targets[k] - entry) > reach:
                real[k] = False
                sources[k] = f"{sources[k]} (beyond reach)"
    blend = []
    last_real = None
    for k, (rr, ok) in enumerate(zip(rrs, real)):
        if ok:
            last_real = rr
        elif last_real is not None:
            # no level beyond: this third exits at the last level too (the demo places its order there, not at an
            # ATR step / R multiple in empty space)
            targets[k], rrs[k] = targets[k - 1], rrs[k - 1]
            sources[k] = f"{sources[k - 1]} (no level beyond)" if 'no level beyond' not in sources[k - 1] else sources[k - 1]
        blend.append(last_real)
    reason = None
    if last_real is None and not any(real):
        reason = 'no level target'
    blended = sum(b for b in blend if b is not None) / 3 if any(b is not None for b in blend) else None
    if risk < CONFIG.levels.cost_guard * fee:
        reason = reason or _cost_reason()
    reason = reason or stop_too_far(plan, entry, stop)
    # audit C09: the setup's own measured rate (SWEEP and SILVER BULLET share the strategy 'sweep', Turtle and BB1
    # 'breakout' - one rate for different stops / targets / methods is no probability of either)
    hit = HIT_RATE.get(setup_key(plan.get('setup')))
    exp, exp_note = None, None
    if reason is None:
        hi = (hit[2] if len(hit) > 2 else hit[0]) if hit else None
        if hit and real[0]:
            # audit 2026-10-18: the position exits in thirds and the stop stays put after TP1 (be_after_1r off), so
            # each third is its own bet: p_k x R_k - (1 - p_k) at its target, 1/3 of the size. p x R1 for the whole
            # position counted the two thirds that a TP1-then-stop loses as wins. A third that exits at an earlier
            # level (no level beyond) carries that level's p
            ps = [hi] + [hit[3 + k] if len(hit) > 3 + k else hi for k in range(2)]
            for k in range(1, 3):
                if targets[k] == targets[k - 1]:
                    ps[k] = ps[k - 1]
            exp = sum(p * r - (1 - p) for p, r in zip(ps, rrs)) / 3
        # audit 2026-10-18 P1 #5: the estimate models three thirds at TP1 / TP2 / TP3 against a fixed stop - it is the
        # expectancy of THAT exit only. A plan that exits otherwise (half + trail, the +1R partial, the averaging add,
        # Turtle units, no targets) is journaled with it (exp_model / exp_note) but not vetoed by it
        thirds = not (plan.get('trail_after_tp1') or plan.get('add_half') or plan.get('turtle_n') or plan.get('no_tp')
                      or CONFIG.executor.partial_share > 0)
        if exp is not None and exp <= 0 and not thirds:
            exp_note = f"shadow: expectancy {exp:+.2f}R of the thirds model, the plan exits otherwise"
        if exp is not None and exp <= 0 and thirds:
            # proven negative: even the upper ends of the 95% intervals do not pay these R:Rs
            reason = f"expectancy {exp:+.2f}R at p <= {hi:.0%} (measured {hit[0]:.0%} of {hit[1]})"
        elif plan.get('min_rr') is not None and real[0] and rrs[0] is not None and rrs[0] < plan['min_rr']:
            # audit C07: a method's OWN minimum (Strategy.min_rr - Seiden's 3:1 to the nearest opposing zone) is a
            # minimum to TP1; far targets lifting the blend (TP1 1.04R, blended 3.6) do not meet it
            reason = f"R:R to TP1 {rrs[0]:.2f} < {plan['min_rr']:g} (the method's minimum)"
        elif blended is not None and blended < _min_rr(plan):
            # the global rule is on the blended R:R of the actual three-part exit (named so in the reason)
            reason = f"blended R:R {blended:.2f} < {_min_rr(plan):g}"
    if reason is None and real[0] and _min_rr(plan) > 0 and rrs[0] is not None and \
            CONFIG.levels.min_rr_tp1_floor > 0 and rrs[0] < CONFIG.levels.min_rr_tp1_floor:
        reason = f"R:R to TP1 {rrs[0]:.2f} < {CONFIG.levels.min_rr_tp1_floor:g}"
    if reason is None and plan.get('min_rr_on_tp1') and (rrs[0] is None or rrs[0] < _min_rr(plan)):
        # audit S05, Seiden: the profit zone up to the FIRST opposing zone must pay min_rr itself (the blend let a
        # TP1 of 0.26R through behind a far TP2)
        reason = f"R:R to TP1 {rrs[0] if rrs[0] is not None else 0:.2f} < {_min_rr(plan):g} (to the first opposing zone)"
    # the averaging add (pump: one more unit at half the way to the stop) makes the position's risk 1.5 units
    risk_units = 1.5 if plan.get('add_half') else 1.0
    if plan.get('connors_exit') or (plan.get('exit') or {}).get('connors_exit'):
        # Connors (eng-48): no fixed target - the trade ends on a daily close beyond the moving SMA5 (SignalBook);
        # TP1-3 are 100 / 200 / 300 R placeholders the lifecycle never reaches, as the Turtles'
        risk_px = abs(entry - stop)
        label = 'none: exit on a daily close beyond the SMA5 (Connors)'
        targets = [entry + direction * k * risk_px for k in (100, 200, 300)]
        rrs, blended, reason, low, sources = [None, None, None], None, None, False, [label] * 3
    obstacle_r, obstacle_src = obstacle_before(zones, entry, targets[0], direction, risk)
    return {'entry': entry, 'sl': stop, 'tp1': targets[0], 'tp2': targets[1], 'tp3': targets[2],
            'stop_pierce': stop_pierce(plan, stop), 'rr_tp1': rrs[0], 'rr_tp2': rrs[1], 'rr_blend': blended, 'low_rr': bool(low or reason),
            'rr_reason': reason, 'risk_units': risk_units, 'exp_model': exp, 'exp_note': exp_note,
            'obstacle_r': obstacle_r, 'obstacle_src': obstacle_src,
            'tp1_src': sources[0], 'tp2_src': sources[1], 'tp3_src': sources[2], 'sl_src': sl_src}


def obstacle_before(zones: List[Zone], entry: float, tp1: float, direction: int,
                    risk: float) -> Tuple[Optional[float], Optional[str]]:
    """audit 2026-10-18 P2 #7, a diagnostic (journaled, never a filter): the nearest strong map zone the price meets
    between the entry and TP1 - (its near edge in R from the entry, its label). A method's own objective (a range's far
    side, an extension) skips the map on purpose; this shows what stands in the way, not that the target is wrong."""
    if not risk or not zones:
        return None, None
    path = [z for z in zones if z.strength >= CONFIG.zones.min_strength
            and 0 < direction * (_near(z, direction) - entry) < direction * (tp1 - entry) * 0.999]
    if not path:
        return None, None
    z = min(path, key=lambda z: direction * (_near(z, direction) - entry))
    return round(direction * (_near(z, direction) - entry) / risk, 3), z.label


def _cost_reason() -> str:
    """The cost guard's veto as the rule actually stands (CONFIG.levels.cost_guard x the round-trip cost)."""
    g = CONFIG.levels.cost_guard
    return f"risk < {g:g}x the round-trip costs" if g != 1 else "costs exceed the risk"


def _min_rr(plan: Dict) -> float:
    """The plan's minimum R:R to TP1: its method's own (Strategy.min_rr, from the source) else the global rule."""
    v = plan.get('min_rr')
    return CONFIG.levels.min_rr_tp1 if v is None else v


LIQUIDITY_KINDS = ('pdhl', 'equal', 'swing_1h', 'swing_1d', 'swing_1w', 'pmhl', 'year', 'htf')


def _liq_price(zone: Zone, direction: int) -> float:
    """The nearest untaken liquidity extreme of the zone in the trade's direction (its levels' own prices: a swing's
    wick, not the body edge the S/R zone starts from); the zone's near edge when it carries no liquidity part."""
    prices = [p[1] for p in zone.parts if p[0] in LIQUIDITY_KINDS and not p[4]]
    if not prices:
        return _near(zone, direction)
    return min(prices) if direction > 0 else max(prices)


def select_targets(zones: List[Zone], ref: float, direction: int, atr: float, intent: str,
                   fillers: Sequence[float] = (), fill_label: str = 'fib',
                   first: Optional[Tuple[float, str]] = None) -> Tuple[List[float], List[str]]:
    """
    Up to three targets beyond `ref` in the trade's direction by the strategy's intent; `first` forces a primary
    objective (a range's far side) into the candidates. Returns (prices, labels).
    """
    cfg = CONFIG.zones
    gap = cfg.min_target_atr * atr
    liquidity = intent in ('draw_liquidity', 'opposite_liquidity')
    if liquidity:
        # audit D09 / D12: the pool is where the stops rest - the swing's EXTREME (the wick), not the S/R zone's body
        # edge, and a swing a wick already took is no untaken pool. Zones without a liquidity part stay as before.
        def px(z: Zone) -> float:
            return _liq_price(z, direction)
        zones = [z for z in zones if not z.parts or not any(p[0] in LIQUIDITY_KINDS for p in z.parts)
                 or any(p[0] in LIQUIDITY_KINDS and not p[4] for p in z.parts)]
    else:
        def px(z: Zone) -> float:
            return _near(z, direction)
    beyond = [z for z in zones if direction * (px(z) - ref) >= gap]
    beyond.sort(key=lambda z: direction * (px(z) - ref))
    strong = [z for z in beyond if z.strength >= cfg.min_strength]
    # eng-115: Wyckoff's range ('range': the far side, the P&F count) and the continuation's trend-based extensions
    # ('extension': Carney / Pesavento) are the methods' own objectives - no map zone in between
    own = intent in ('range', 'extension')
    if liquidity:
        # eng-114, the sources (ICT / Turtle Soup: "target buy-side liquidity in the higher timeframe"): the targets are
        # the opposite LIQUIDITY only - old highs / lows (1h and higher swings), equal highs / lows, the previous day /
        # week / month / year and the sessions. Not any strong zone of the map (OB, FVG, VAL, VWAP) and no ATR step:
        # sweeps of 12-14.10 took TP1 0.2-0.8 R away from such zones and 'ATR steps'
        primary = [z for z in beyond if any(k in LIQUIDITY_KINDS for k in z.kinds)]
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
    candidates += [(px(z), z.label, 0) for z in primary]
    if own:
        candidates = [c for c in candidates if c[2] != 0 or (first is not None and c[0] == first[0])]
    elif not liquidity:
        candidates += [(px(z), z.label, 1) for z in strong if z not in primary]
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
    if own:
        for f in sorted(fillers, key=lambda x: direction * (x - ref)):
            if len(prices) < 3 and (not prices or direction * (f - prices[-1]) > 0) and f not in prices:
                prices.append(f)
                labels.append(fill_label)
    if liquidity or own:
        # no liquidity ahead = no target (no setup); fewer than three pools: the last one repeats (all out there)
        while prices and len(prices) < 3:
            prices.append(prices[-1])
            labels.append(labels[-1])
        return prices, labels
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


def zone_pad(plan: Dict, measured: Optional[float]) -> Tuple[Optional[float], str]:
    """The buffer beyond the stop's structure: the larger of the measured pierce of the level and
    zone_buffer_atr x the ATR of the structure's own timeframe (Seiden-style: 1-2 ATR of the zone's timeframe beyond
    its distal line; the owner: beyond the zone with a 3-5% margin - on alts' 4h that is ~1.5 ATR). eng-69."""
    k = CONFIG.levels.zone_buffer_atr
    tf_pad = k * (plan.get('tf_atr') or 0.0)
    if measured is None and not tf_pad:
        return None, ''
    if measured is None or tf_pad > measured:
        return tf_pad, f"{k:g} ATR {plan.get('tf', '15m')}"
    return measured, 'measured pierce'


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
    pad, how = zone_pad(plan, measured)
    if pad is not None:
        # beyond the level by its measured pierce or the structure timeframe's ATR buffer, whichever is wider; a stop
        # so far that it does not pay is a wrong entry (low_rr), not a reason to move it closer
        stop, src = base - direction * pad, f"{src} + {how} {pad / base:.2%}"
    else:
        stop = base - direction * cfg.stop_buffer_atr * (plan.get('leg_atr') or atr)
    # the floor in the structure's own ATR too (a 1h / 4h leg's stop floored by the 15m ATR sat inside its noise)
    # eng-58: the volatility floor holds with the pierce model too (it was skipped whenever the model existed - i.e.
    # always - while the docs and levels.min_leg_atr assumed it; live eng-6: stops < 1 ATR hit on 8 of 10 entries)
    floor = stop_floor(max(atr, plan.get('leg_atr') or 0.0, plan.get('tf_atr') or 0.0), plan.get('recent_atr'))
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
    refs = [r for r in (plan.get('stop_ref'), None if plan.get('stop_ref_only') else extreme) if r is not None]
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
    targets, sources = plan.get('targets') or [], plan.get('target_src') or []
    if not targets or plan.get('targets_final'):
        # a system entering at its signal's close (_confirm_plan) has no planned targets yet: the map's TP1 as of the
        # entry (eng-57, the cloud session's eng-44 fix d90605a: 'map' read the empty list, so trendline and oi_signal
        # never made a plan - journaled 'no_target'); Edwards & Magee: the next support / resistance on the map
        tz = htf_zones(plan.get('zones') or [], plan.get('target_tf') or plan.get('tf'))
        targets, sources = select_targets(tz, entry, direction,
                                          max(exit.get('atr') or plan.get('atr') or risk, plan.get('tf_atr') or 0.0),
                                          'opposite_liquidity')
    ltf = _ltf_prices(plan.get('zones') or [], plan.get('target_tf') or plan.get('tf'), direction)
    ahead = [(t, s) for t, s in zip(targets, sources) if direction * (t - entry) > 0 and s != 'ATR step'
             and not any(abs(t - p) <= 1e-9 * max(abs(t), 1.0) for p in ltf)]
    if not ahead:
        return None, '', True
    t, s = ahead[0]
    return t, s, direction * (t - entry) / risk < spec[1]


def structure_stop(zones: List[Zone], entry: float, direction: int, atr: float, floor: float,
                   symbol: Optional[str] = None, tf: str = '15m',
                   tf_atr: Optional[float] = None) -> Optional[Tuple[float, str]]:
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
        if measured is not None or tf_atr:
            # eng-69: beyond the structure by max(measured pierce, zone_buffer_atr x the structure timeframe's ATR)
            measured = max(measured or 0.0, cfg.zone_buffer_atr * (tf_atr or 0.0))
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


HTF_SWINGS = ('swing_1h', 'swing_1d', 'swing_1w')


def clear_pool(zones: List[Zone], stop: float, entry: float, direction: int, symbol: Optional[str],
               label: str) -> Tuple[float, str]:
    """eng-84: a system's fixed-price stop (AUCTION's test, a trendline pivot, Connors' 3 ATR) went straight to the
    exchange, never checked against the map: SKY's sat 0.24% beyond the 1h low - inside that pool's usual pierce, and
    the raid of the low took it (liquidated longs printed below). A resting-stop pool between the stop and the entry
    whose usual pierce (p90) reaches the stop moves the stop beyond the pool's pierce."""
    from pierce import measured_kind, overshoot
    best = None
    for z in zones:
        # resting stops sit beyond swings of 1h and higher too (the obvious '1h low' of SKY) - zones.POOL_KINDS
        # holds only equal levels / PDH-PDL / ranges / rounds
        if not any((k in POOL_KINDS and k != 'liq_est') or k in HTF_SWINGS for k in z.kinds):
            continue
        edge = z.lo if direction > 0 else z.hi
        if not 0 < direction * (edge - stop) < direction * (entry - stop):
            continue                                   # not between the stop and the entry
        reach = overshoot(symbol, measured_kind(z.kinds) or 'equal', edge, 'p90')
        if reach is None or direction * (edge - stop) > reach:
            continue                                   # the stop already clears this pool's usual pierce
        new = edge - direction * reach
        if best is None or direction * (best[0] - new) > 0:
            best = (new, f"{label}, beyond {z.label} + its p90 pierce")
    return best if best is not None else (stop, label)


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
        if exit.get('stop_n'):
            stop = entry - direction * exit['stop_n']          # review V05: a distance from the entry (Turtles' 2N)
        sl_src = exit.get('stop_src', 'the system stop')
        if exit.get('pad'):
            # a structural stop (Bollinger's retest): beyond it by the pierce / zone buffer, never inside 1 ATR
            pad, how = zone_pad(plan, overshoot(plan.get('symbol'), 'swing_15m', stop))
            if pad:
                stop, sl_src = stop - direction * pad, f"{sl_src} + {how} {pad / stop:.2%}"
            floor = stop_floor(max(atr, plan['atr'], plan.get('tf_atr') or 0.0), plan.get('recent_atr'))
            if 0 < direction * (entry - stop) < floor:
                stop, sl_src = entry - direction * floor, f"{sl_src}, widened to {CONFIG.levels.min_stop_atr:g} ATR"
        risk = direction * (entry - stop)
        if risk <= 0:
            return None
        label = exit.get('tp_src', 'none (trailing exit)')
        # eng-54: the cost guard holds here too - an ORB range of 0.15% put the stop 0.10% away, under one round trip's
        # cost (live ETH 2026-10-03: -2.2R in the demo); target-less plans skipped finish_levels and with it the guard
        fee = cost_of(entry, plan.get('volume_24h'), plan.get('symbol'))
        reason = _cost_reason() if risk < CONFIG.levels.cost_guard * fee else None
        reason = reason or stop_too_far(plan, entry, stop)
        out = {'entry': entry, 'sl': stop, 'tp1': entry + direction * 100 * risk, 'tp2': entry + direction * 200 * risk,
               'tp3': entry + direction * 300 * risk, 'rr_tp1': None, 'rr_tp2': None, 'rr_blend': None,
               'low_rr': bool(reason), 'rr_reason': reason, 'risk_units': 1.0,
               'tp1_src': label, 'tp2_src': label, 'tp3_src': label, 'sl_src': sl_src,
               'stop_pierce': stop_pierce(plan, stop)}
        tp1 = exit.get('tp1_price')
        if tp1 is not None:
            # eng-85: a trailing system with a real first target (Bollinger's band at the signal): half out there; it
            # must pay the TP1 floor net of costs after the stop's padding
            rr1 = (direction * (tp1 - entry) - fee) / (risk + fee)
            out.update(tp1=tp1, tp1_src=exit.get('tp1_src', 'TP1'), rr_tp1=rr1)
            # audit S06: after the stop's padding / ATR floor the method's own min_rr too (it was checked on the
            # signal's unpadded stop only: R:R 0.36 passed)
            floor_rr = max(CONFIG.levels.min_rr_tp1_floor, _min_rr(plan))
            if not reason and floor_rr > 0 and rr1 < floor_rr:
                out.update(low_rr=True, rr_reason=f"R:R to TP1 {rr1:.2f} < {floor_rr:g}")
        return out
    floor = stop_floor(max(atr, plan['atr'], plan.get('tf_atr') or 0.0), plan.get('recent_atr'))
    zones: List[Zone] = htf_zones(plan.get('zones') or [], plan.get('target_tf') or plan.get('tf'))
    fixed_stop = exit['stop'][0] in ('pct', 'atr')
    fixed_tp = exit['tp'][0] in ('pct', 'rr')
    structural = structure_stop(zones, entry, direction, atr, floor, plan.get('symbol'), plan.get('tf', '15m'),
                                plan.get('tf_atr')) \
        if fixed_stop else None
    prot = plan.get('protected')
    if structural is not None and prot is not None and direction * (entry - prot) > 0 \
            and direction * (structural[0] - prot) > 0:
        # ICT: beyond the protected swing (the one that broke structure) when it lies beyond the nearest structure
        buffer = overshoot(plan.get('symbol'), 'swing_15m', prot)
        base, src = stop_beyond(zones, prot, entry, direction, atr, 'beyond the protected swing (BOS)',
                                plan.get('symbol'))
        pad, how = zone_pad(plan, buffer)
        structural = (base - direction * (pad if pad is not None else CONFIG.levels.stop_buffer_atr * atr),
                      f"{src} + {how}" if pad is not None else src)
    if structural is not None:
        stop, sl_src = structural
    elif exit['stop'][0] == 'ref' and overshoot(plan.get('symbol'), 'swing_15m', entry) is not None:
        # the system's own structural reference (beyond the sweep / the zone / the test), but the buffer beyond it is
        # the measured pierce of this coin (live: GRT's demand stop sat 0.35% under the zone, inside the usual pierce)
        refs = [r for r in (plan.get('stop_ref'), None if plan.get('stop_ref_only') else extreme) if r is not None]
        ref = (min(refs) if direction > 0 else max(refs)) if refs else entry
        base, src = stop_beyond(zones, ref, entry, direction, atr, exit.get('stop_src', 'beyond the extreme'),
                                plan.get('symbol'))
        pad, how = zone_pad(plan, overshoot(plan.get('symbol'), kind_at(zones, base)
                                            or kind_of_label(src, plan.get('tf', '15m')), base))
        stop, sl_src = base - direction * pad, f"{src} + {how} {pad / base:.2%}"
    else:
        stop, sl_src = exit_stop(exit, plan, entry, extreme, direction)
        if exit['stop'][0] == 'price' and not exit.get('own_stop'):
            stop, sl_src = clear_pool(zones, stop, entry, direction, plan.get('symbol'), sl_src)
    risk = direction * (entry - stop)
    if 0 < risk < floor and not exit.get('own_stop'):                                # eng-58: with the pierce model too (stop_levels)
        stop, risk = entry - direction * floor, floor
        sl_src = f"{sl_src}, widened to {CONFIG.levels.min_stop_atr:g} ATR"
    cap = exit.get('max_loss_pct')
    if cap and entry and risk > cap * entry * (1 + 1e-9):
        # audit C06: the method's own loss limit outranks the shared floor / pool clearing: such a geometry is
        # rejected, never widened past the limit (cup: 8% became 20%)
        out = finish_levels(plan, entry, stop, [entry + direction * risk] * 3, ['n/a'] * 3, direction, sl_src) or {}
        return {**out, 'entry': entry, 'sl': stop, 'low_rr': True,
                'rr_reason': f"stop {risk / entry:.1%} away > the method's {cap:.0%} limit ({sl_src})"} if out else None
    if risk <= 0 or (exit.get('min_risk_atr') and risk < exit['min_risk_atr'] * atr):
        return None
    if fixed_tp and zones:
        targets, sources = select_targets(zones, entry, direction, atr, 'opposite_liquidity')
        if targets and sources[0] != 'ATR step':
            return finish_levels(plan, entry, stop, list(targets[:3]), list(sources[:3]), direction, sl_src)
    tp1, src1, low = exit_target(exit, plan, entry, risk, direction)
    if tp1 is None:
        return None
    gap = CONFIG.zones.min_target_atr * max(atr, plan.get("tf_atr") or 0.0)   # the structure timeframe's ATR
    # TP2 / TP3: the system's own second target where it has one (the OI robot's 4% / 6%), else the next levels on
    # the map beyond TP1 (any strength); ATR steps only where the map is empty (was: always TP1 + 1 ATR, + 2 ATR)
    prices, labels = [tp1], [src1]
    if exit.get('tp2'):
        tp2, src2, _ = exit_target({**exit, 'tp': exit['tp2']}, plan, entry, risk, direction)
        if tp2 is not None and direction * (tp2 - tp1) > 0:
            prices.append(tp2)
            labels.append(src2)
    if exit.get('own_targets'):
        # eng-115: the method's own targets only (Dalton's far edge, Bulkowski's cup heights) - the map / ATR steps
        # added TP2 / TP3 no source names; the last one repeats
        while len(prices) < 3:
            prices.append(prices[-1])
            labels.append(labels[-1])
    else:
        map_fill(zones, prices, labels, entry, direction, gap)
        while len(prices) < 3:
            if exit.get('no_atr_steps'):
                # eng-116: no level beyond = no further target (an ATR step has no source): the last one repeats
                prices.append(prices[-1])
                labels.append(labels[-1])
            else:
                prices.append(prices[-1] + direction * gap)
                labels.append('ATR step')
    # the R:R decision is finish_levels' alone (the blended R:R / expectancy against the method's min_rr); the exit
    # spec's own per-target minimum vetoed W-bottoms whose blended R:R passed (live QNT: TP1 0.71, blended 1.37)
    return finish_levels(plan, entry, stop, prices[:3], labels[:3], direction, sl_src)


def _ext_label(target: float, label: str, ratios: Dict[float, float], plan: Dict, direction: int) -> str:
    """'ext 1.272' for an extension target, '+ <zone>' when a 4h / daily / weekly zone sits within the pierce of it."""
    import re
    if label != 'ext':
        return label
    k = next((r for f, r in ratios.items() if abs(f - target) <= 1e-12 * max(1.0, abs(f))), None)
    text = f"ext {k:g}" if k is not None else 'ext'
    p50 = overshoot(plan.get('symbol'), 'swing_1h', target, 'p50') or 0.0
    for z in plan.get('zones') or []:
        if z.lo - p50 <= target <= z.hi + p50 and \
                any(re.search(r'_(4h|1d|1w)$', k_) or k_ in ('swing_1d', 'htf', 'pdhl') for k_ in z.kinds):
            return f"{text} + {z.label.split(' · ')[0]}"
    return text


def entry_levels(plan: Dict, entry: float, extreme: Optional[float], direction: int) -> Optional['CardLevels']:
    """Entry / stop / targets for an entry at `entry` (targets behind the entry are dropped, refilled beyond it)."""
    if plan.get('exit'):
        return system_levels(plan, entry, extreme, direction)
    stop, sl_src = stop_levels(plan, entry, extreme, direction)
    risk = abs(entry - stop)
    if not risk or direction * (entry - stop) <= 0:
        return None
    # targets are spaced in the structure's own ATR and drawn from its timeframe's zones and higher
    atr = max(plan.get('leg_atr') or plan['atr'], plan.get('tf_atr') or 0.0)
    tf_zones = htf_zones(plan.get('zones') or [], plan.get('target_tf') or plan.get('tf'))
    if plan.get('retarget'):
        # Continuation (audit, ICT OTE Primer): the prior high and the leg's 1.272 / 1.618 extensions measured on the
        # impulse A->B from A (A + k x (B - A)); the pullback's extreme C no longer moves them (eng-42's C + k x leg)
        fillers, fill_label = plan.get('fillers', ()), plan.get('fill_label', 'fib')
        imp = plan.get('impulse')
        if imp:
            leg = abs(imp['end'] - imp['start'])
            fillers = tuple(imp['start'] + direction * k * leg for k in CONFIG.levels.continuation_targets)
            fill_label = 'ext'
        targets, sources = select_targets(tf_zones, entry, direction, atr, plan['intent'], fillers, fill_label)
        if imp:
            # name each extension by its ratio, and mark the ones a higher-timeframe zone confirms (the screenshots'
            # daily + 4h extensions landing on one price)
            ratios = dict(zip(fillers, CONFIG.levels.continuation_targets))
            sources = [_ext_label(t, s, ratios, plan, direction) for t, s in zip(targets, sources)]
    else:
        ltf = _ltf_prices(plan.get('zones') or [], plan.get('target_tf') or plan.get('tf'), direction)
        ahead = [(t, s) for t, s in zip(plan['targets'], plan['target_src']) if direction * (t - entry) > 0
                 and not any(abs(t - p) <= 1e-9 * max(abs(t), 1.0) for p in ltf)]
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
        if plan.get('intent') in ('draw_liquidity', 'opposite_liquidity', 'range', 'extension'):
            # eng-114: liquidity targets only (the plan's pools ahead of the real entry); the last repeats
            while targets and len(targets) < 3:
                targets.append(targets[-1])
                sources.append(sources[-1])
        else:
            map_fill(tf_zones, targets, sources, entry, direction, gap)
            while targets and len(targets) < 3:
                targets.append(targets[-1] + direction * gap)
                sources.append('ATR step')
    if not targets:
        return None
    out = finish_levels(plan, entry, stop, list(targets[:3]), list(sources[:3]), direction, sl_src)
    if out is not None and extreme is not None:
        out['extreme'] = extreme
    return out


def cap_for_rr(tp1: float, stop_est: float, direction: int, atr: float, recent_atr: Optional[float],
               min_rr: Optional[float] = None, volume_24h: Optional[float] = None,
               symbol: Optional[str] = None) -> float:
    """
    The furthest entry (from the extreme toward TP1) that still pays min_rr_tp1 (net of fees) to TP1 with the stop at `stop_est`
    or the stop floor, whichever is wider: a waiting zone ends there.
    """
    rr = CONFIG.levels.min_rr_tp1 if min_rr is None else min_rr
    # R:R is net of the execution cost by the coin's liquidity, as finish_levels judges it (eng-58: was a flat 5 bps)
    fee = cost_of(tp1, volume_24h, symbol)
    by_stop = (tp1 + rr * stop_est - direction * (1 + rr) * fee) / (1 + rr)
    by_floor = tp1 - direction * (rr * stop_floor(atr, recent_atr) + (1 + rr) * fee)
    return min(by_stop, by_floor) if direction > 0 else max(by_stop, by_floor)
