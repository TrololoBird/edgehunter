"""
Liquidation exhaustion (FLUSH REVERSAL / SQUEEZE REVERSAL). A cascade of forced liquidations overshoots mechanically
and price snaps back once the forced flow stops; the entry needs the extreme move AND a sign the flush is over.

Wyckoff (Pruden, Weis): a liquidation cascade is a selling / buying climax; the climax itself is not bought - the
trade comes on the SECONDARY TEST, a return toward the climax's extreme on lower volume (eng-30: the entry trigger
needs the pullback's average minute <= spring_test_volume_ratio x the climax's, like a spring's test).

Anchor: a real leg - the cascade, from the extreme of the exhaustion_pre_minutes before it to its extreme. The extreme
keeps following price until the entry (nobody knows where a running cascade ends), so there is no fixed invalidation;
the card waits near the extreme for a 5m structure shift against the cascade. Targets: the mean (VWAP anchored at the
cascade's start, the map's VWAP / POC / nodes), the cascade's 0.382 / 0.5 / 0.618 retracements fill empty slots.
"""
from typing import Dict, Optional, Sequence

from config import CONFIG
from levels import fib_price, retracement_of
from strategies.base import PlanInput, Strategy, base_plan
from strategies.geometry import cap_for_rr, select_targets
from strategies.level import reached_since
from zones import merge, vwap

MINUTE_MS = 60_000
FIVE_MIN_MS = 5 * MINUTE_MS


def cascade_leg(sig: Dict, minutes: Sequence[Sequence[float]], direction: int, atr: float) -> Optional[Dict]:
    """The cascade as a leg; its end follows new extremes of the final 1m candles."""
    if sig.get('leg_start') is None:
        return None
    start, end = sig['leg_start'], sig['leg_end']
    start_ts, end_ts = int(sig['leg_start_ts']), int(sig['leg_end_ts'])
    for c in minutes:
        if c[0] < end_ts:
            continue
        if direction > 0 and c[3] < end:
            end, end_ts = c[3], int(c[0])
        elif direction < 0 and c[2] > end:
            end, end_ts = c[2], int(c[0])
    return {'start': start, 'end': end, 'size': abs(end - start), 'candles': (end_ts - start_ts) // MINUTE_MS,
            'atr': atr, 'atr_15m': atr, 'tf': '5m', 'trigger_minutes': 5, 'start_ts': start_ts, 'end_ts': end_ts}


class CascadeTracker:
    """Loop-side detector state: a running cascade per coin, fired once its leg is big enough."""

    def __init__(self):
        self.events: Dict[str, Dict] = {}

    def forget(self, symbol: str):
        self.events.pop(symbol, None)

    def active(self, symbol: str) -> bool:
        event = self.events.get(symbol)
        return event is not None and not event['fired']

    def check(self, symbol: str, minutes: Sequence[Sequence[float]], m: Dict[str, float], atr: float,
              now_ms: int) -> Optional[Dict]:
        cfg = CONFIG.strategies
        liq = CONFIG.liquidations
        liq_long, liq_short = m.get('liq_long_5m') or 0.0, m.get('liq_short_5m') or 0.0
        total = liq_long + liq_short
        px = m.get('price_change_5m') or 0.0
        watch_ms = cfg.exhaustion_ttl[0] * 1000
        if total >= liq.cascade_min_usd and total >= liq.cascade_avg_minute_share * (m.get('avg_minute_usd') or 0.0):
            # Long liquidations on a drop -> a long reversal candidate; short liquidations on a rally -> a short one
            direction = 1 if liq_long > liq_short and px < 0 else -1 if liq_short > liq_long and px > 0 else 0
            event = self.events.get(symbol)
            if direction and (event is None or event['direction'] != direction or now_ms - event['ts'] > watch_ms):
                self.events[symbol] = {'direction': direction, 'ts': now_ms, 'fired': False,
                                       'usd': liq_long if direction > 0 else liq_short}
        event = self.events.get(symbol)
        if event is None or event['fired'] or now_ms - event['ts'] > watch_ms or not atr:
            return None
        direction = event['direction']
        cascade_from = event['ts'] - FIVE_MIN_MS
        during = [c for c in minutes if c[0] >= cascade_from]
        before = [c for c in minutes if cascade_from - cfg.exhaustion_pre_minutes * MINUTE_MS <= c[0] < cascade_from]
        if not during or not before:
            return None
        if direction > 0:
            end_c = min(during, key=lambda c: c[3])
            pre = before + [c for c in during if c[0] < end_c[0]]
            start_c = max(pre, key=lambda c: c[2])
            start, end = start_c[2], end_c[3]
        else:
            end_c = max(during, key=lambda c: c[2])
            pre = before + [c for c in during if c[0] < end_c[0]]
            start_c = min(pre, key=lambda c: c[3])
            start, end = start_c[3], end_c[2]
        if abs(start - end) < cfg.exhaustion_min_leg_atr * atr:
            return None
        event['fired'] = True
        side = 'longs' if direction > 0 else 'shorts'
        return {'setup': 'FLUSH REVERSAL' if direction > 0 else 'SQUEEZE REVERSAL', 'direction': direction,
                'setup_note': f"{side} liquidated {event['usd'] / 1e3:,.0f}k in 5m, move {abs(end / start - 1) * 100:.1f}% "
                              f"({abs(start - end) / atr:.1f} ATR); waiting for the exhaustion",
                'leg_start': start, 'leg_end': end, 'leg_start_ts': int(start_c[0]), 'leg_end_ts': int(end_c[0]),
                # the climax's average futures minute: Wyckoff's secondary test must trade on less
                'fut_candle_minute_usd': sum(c[5] for c in during) / len(during),
                'event_ts': int(event['ts'])}


class ExhaustionStrategy(Strategy):
    name = 'wyckoff'               # eng-35: Wyckoff's phase A (climax + secondary test), with SPRING / UTAD (phase C)
    own_leg = True                 # its anchor is the cascade, not a leg of the 15m / 1h history
    default_tf = '5m'
    anchor_type = 'leg'
    setups = {'FLUSH REVERSAL': 1, 'SQUEEZE REVERSAL': -1}
    ttl_key = 'exhaustion_ttl'
    uses_minutes = True

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('event_ts'), x.sig.get('leg_start')) if x.sig.get('leg_start') is not None else None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        d, atr = x.direction, x.atr
        leg = cascade_leg(x.sig, x.minutes, d, atr) if atr else None
        if leg is None:
            return None
        levels = list(x.raw_levels or []) + vwap(x.minutes, leg['start_ts'], 'VWAP pre-cascade')
        zones = merge(levels, atr, symbol=x.symbol)
        end = leg['end']
        from pierce import overshoot
        stop_est = end - d * (overshoot(x.symbol, 'swing_15m', end) or CONFIG.levels.stop_buffer_atr * atr)
        reached = x.reached if x.reached is not None else reached_since(x.minutes, leg['end_ts'] + MINUTE_MS, end, d)
        retraces = [fib_price(leg, r) for r in CONFIG.levels.reversal_targets]
        targets, sources = select_targets(zones, reached, d, atr, 'mean', retraces, 'retrace')
        hi_ratio = CONFIG.levels.reversal_zone_max
        capped = retracement_of(leg, cap_for_rr(targets[0], stop_est, d, atr, x.recent_atr))
        hi_ratio = max(0.0, min(hi_ratio, capped))
        zone = sorted((end, fib_price(leg, hi_ratio)))
        anchor = {'type': 'leg', 'tf': '5m', 'start': leg['start'], 'end': end, 'start_ts': leg['start_ts'],
                  'end_ts': leg['end_ts'], 'label': 'cascade'}
        return base_plan(x, self.name, anchor, '5m', entry='pullback', zone_lo=zone[0], zone_hi=zone[1],
                         zone_src=f"cascade extreme (0-{hi_ratio:.2f})", invalid=None, missable=True, stop_ref=end,
                         intent='mean', fillers=tuple(retraces), fill_label='retrace', targets=targets,
                         target_src=sources, zones=zones, reached=reached, key=(x.sig.get('event_ts'), leg['start']),
                         impulse=leg)
