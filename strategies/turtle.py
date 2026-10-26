"""
The Turtles' breakout systems as the original rules define them (Curtis Faith, "Way of the Turtle", 2007; "The
Original Turtle Trading Rules"), on DAILY candles (fetcher._daily_candles_loop), checked loop-side every final minute
(strategies.loopside.LoopDetectors._turtle_breakout):

- N = the 20-day exponential average of the true range: N = (19 x previous N + TR) / 20, seeded by the 20-day mean.
- System 1: a trade the moment price exceeds the high (low) of the previous 20 days by a tick - intraday, on the touch,
  not on a close. Skipped when the LAST System 1 breakout (either direction, traded or not) would have been a winner.
- System 2 (the fail-safe of a skipped System 1): the 55-day breakout, taken whatever the last one did.
- Stop: 2N from the entry. No profit target: System 1 exits on the 10-day low (a long) / high (a short), System 2 on
  the 20-day one (Scanner / SignalBook trail the exit, `trail_days`).
- Pyramiding (eng-34, SignalBook): +1 unit every 1/2 N from the previous unit's ACTUAL price (Faith), up to
  turtle_max_units; the stop of all units moves to 2N from the newest one. R stays the first unit's risk (2N), so a
  full pyramid stopped out loses ~2-2.5R. Not here: unit sizing (1% of equity per N).
"""
from typing import Dict, List, Optional, Sequence, Tuple

DAY_MS = 86_400_000


def true_ranges(d1: Sequence[Sequence[float]]) -> List[float]:
    return [max(c[2], p[4]) - min(c[3], p[4]) for p, c in zip(d1, d1[1:])]


def n_series(d1: Sequence[Sequence[float]]) -> List[Optional[float]]:
    """Turtle N per day (aligned with d1; None before 21 days)."""
    trs = true_ranges(d1)
    out: List[Optional[float]] = [None] * len(d1)
    if len(trs) < 20:
        return out
    n = sum(trs[:20]) / 20
    out[20] = n
    for i in range(21, len(d1)):
        n = (19 * n + trs[i - 1]) / 20
        out[i] = n
    return out


def s1_state(d1: Sequence[Sequence[float]], ns: List[Optional[float]]) -> Tuple[str, Optional[str]]:
    """
    Replays System 1 over the daily history (one hypothetical position at a time, either direction).
    Returns (state of the most recent S1 breakout, result of the last COMPLETED one before it):
      'none'      - no S1 breakout in the history,
      'open'      - its hypothetical trade is still open (no result yet),
      'ambiguous' - its entry day also traded through the 2N stop: daily OHLC cannot tell which came first (open or
                    closed, the result is unknown),
      'win' / 'loss' - completed (a long that exited above its entry is a win).
    audit: the N of a hypothetical entry is the one known BEFORE its day (ns[i - 1]); an open trade is never marked at
    the last close. eng-137 (audit A04): the open ambiguous breakout was reported as the PREVIOUS completed result (or
    none), which let a new S1 in while its own result was unknown.
    """
    pos = None
    last: Optional[str] = None
    for i in range(21, len(d1)):
        c = d1[i]
        if pos is not None:
            d, entry, stop = pos['d'], pos['entry'], pos['stop']
            lo10 = min(x[3] for x in d1[i - 10:i])
            hi10 = max(x[2] for x in d1[i - 10:i])
            exit_px = None
            chan = lo10 if d > 0 else hi10
            stop_hit = (d > 0 and c[3] <= stop) or (d < 0 and c[2] >= stop)
            chan_hit = (d > 0 and c[3] <= lo10) or (d < 0 and c[2] >= hi10)
            gapped = (d > 0 and c[1] <= stop) or (d < 0 and c[1] >= stop)      # opened beyond the stop: it came first
            chan_gap = (d > 0 and c[1] <= lo10) or (d < 0 and c[1] >= hi10)   # opened past the channel: it exits at the open
            if stop_hit and chan_hit and not gapped and chan_gap:
                exit_px = c[1]
            elif stop_hit and chan_hit and not gapped and d * (chan - entry) > 0:
                # audit E04: the day traded through the 2N stop AND a profitable channel exit - the OHLC does not say
                # which came first (a continuous path exits at the channel with a profit): the result is unknown
                pos['ambiguous'] = True
                exit_px = chan
            elif stop_hit:
                exit_px = stop
            elif chan_hit:
                exit_px = chan
            if exit_px is not None:
                last = 'ambiguous' if pos.get('ambiguous') else ('win' if d * (exit_px - entry) > 0 else 'loss')
                pos = None
            continue
        hi20 = max(x[2] for x in d1[i - 20:i])
        lo20 = min(x[3] for x in d1[i - 20:i])
        n = ns[i - 1]
        if not n:
            continue
        if c[2] > hi20:
            pos = {'d': 1, 'entry': hi20, 'stop': hi20 - 2 * n}
        elif c[3] < lo20:
            pos = {'d': -1, 'entry': lo20, 'stop': lo20 + 2 * n}
        if pos is not None and ((pos['d'] > 0 and c[3] <= pos['stop']) or (pos['d'] < 0 and c[2] >= pos['stop'])):
            # review V06: the entry day also traded through the 2N stop - the OHLC does not tell which came first
            pos['ambiguous'] = True
    if pos is not None:
        return ('ambiguous' if pos.get('ambiguous') else 'open'), last
    return (last or 'none'), None


def s1_blocked(state: str, prior: Optional[str]) -> bool:
    """S1 is skipped after a winner and whenever the last breakout's result is unknown (unknown is no permission); an
    open unambiguous hypothetical trade has no result yet - the last completed one decides. S2 is never blocked."""
    if state in ('win', 'ambiguous'):
        return True
    return state == 'open' and prior in ('win', 'ambiguous')


def turtle_breakout(d1: Sequence[Sequence[float]], price_hi: float, price_lo: float, now_ms: int,
                    before_hi: Optional[float] = None, before_lo: Optional[float] = None) -> Optional[Dict]:
    """
    The breakout the live minute made against the CLOSED daily candles `d1` ([open_time, o, h, l, c, quote_vol]):
    System 1 (20 days, unless the last S1 breakout was a winner) or System 2 (55 days). None without one.
    `before_hi` / `before_lo`: today's extremes BEFORE this minute - the Turtles enter on the touch, so a level
    already crossed earlier today is no entry now (live eng-32: started mid-day, the bot entered MOVR 26% above a
    55-day high crossed hours before).
    """
    d1 = d1[-370:]                 # the S1 replay runs every minute: the last year (the daily buffer holds 1400 days)
    if len(d1) < 60:
        return None
    ns = n_series(d1)
    n = ns[-1]
    if not n:
        return None
    hi20, lo20 = max(c[2] for c in d1[-20:]), min(c[3] for c in d1[-20:])
    hi55, lo55 = max(c[2] for c in d1[-55:]), min(c[3] for c in d1[-55:])
    s1, s1_prior = s1_state(d1, ns)
    skip = s1_blocked(s1, s1_prior)
    for d, level20, level55, crossed20, crossed55 in (
            (1, hi20, hi55, price_hi > hi20 and (before_hi is None or before_hi <= hi20),
             price_hi > hi55 and (before_hi is None or before_hi <= hi55)),
            (-1, lo20, lo55, price_lo < lo20 and (before_lo is None or before_lo >= lo20),
             price_lo < lo55 and (before_lo is None or before_lo >= lo55))):
        system, level, exit_days = None, None, None     # (pylint E0606: set below whenever system is)
        if crossed20 and not skip:
            system, level, exit_days = 1, level20, 10
        elif crossed55:
            system, level, exit_days = 2, level55, 20
        if system is None:
            continue
        side = 'UP' if d > 0 else 'DOWN'
        days = 20 if system == 1 else 55
        return {'setup': f'BREAKOUT {side}', 'direction': d,
                'setup_note': f"Turtle System {system}: price {'above' if d > 0 else 'below'} the {days}-day "
                              f"{'high' if d > 0 else 'low'} {level:.6g} (N {n:.6g}; stop 2N, exit on the "
                              f"{exit_days}-day {'low' if d > 0 else 'high'})"
                              + ((f"; S1 skipped: the last S1 breakout is {s1}" + (f" (the one before it: {s1_prior})"
                                                                                       if s1 == 'open' else ''))
                                 if system == 2 and skip else ''),
                'turtle_s1': s1,
                'anchor_level': level, 'anchor_extreme': level - d * 2 * n, 'anchor_label': f'{days}-day channel',
                'anchor_ts': int(d1[-days][0]), 'anchor_close': level, 'turtle_n': n, 'turtle_system': system,
                'trail_days': exit_days, 'range_hi': hi20 if system == 1 else hi55,
                'range_lo': lo20 if system == 1 else lo55, 'break_ts': int(now_ms // 60_000 * 60_000),
                'event_ts': int(now_ms // 60_000 * 60_000) + 60_000}
    return None


def trail_level(d1: Sequence[Sequence[float]], days: int, direction: int) -> Optional[float]:
    """The exit channel: the lowest low (a long) / highest high (a short) of the last `days` closed days."""
    if len(d1) < days:
        return None
    rows = d1[-days:]
    return min(c[3] for c in rows) if direction > 0 else max(c[2] for c in rows)
