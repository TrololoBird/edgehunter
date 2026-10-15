"""
Leg strategies: a real leg (levels.find_impulse: its end on the last 12h of 15m candles, its start searched back over
15m and 1h history; its timeframe by duration 15m / 1h / 4h, the entry 3-6x finer).

continuation (IMPULSE UP / DOWN: Tier-0; BULL F / BEAR D removed in eng-127 - Bollinger's Method I is BB1) by ICT's optimal trade entry: a leg
that BROKE STRUCTURE (its end beyond the last swing before its start, eng-58) with displacement (a fair value gap);
the pullback zone = the strongest support inside 0.62-0.79 of the leg (else the EMA20 there, Raschke's Holy Grail);
a resting limit at the zone's near edge (eng-58, ICT enters on a limit in the OTE, not on a later 5m shift); invalid
beyond the leg's start; half out at TP1 and the rest trailed (eng-58); targets re-measured from the entry toward the
leg's trend-based extensions.
"""
from typing import Dict, List, Optional

import polars as pl

from config import CONFIG
from levels import _leg_levels, fib_price, find_impulse, retracement_of
from strategies.base import TRIGGER_MINUTES, PlanInput, Strategy, base_plan
from strategies.geometry import select_targets
from zones import is_structural, merge, support_in


def _leg_anchor(impulse: Dict) -> Dict:
    return {'type': 'leg', 'tf': impulse['tf'], 'start': impulse['start'], 'end': impulse['end'],
            'start_ts': impulse['start_ts'], 'end_ts': impulse['end_ts']}


def _rows(df: pl.DataFrame) -> List[List[float]]:
    return [list(r) for r in df.select(['timestamp', 'open', 'high', 'low', 'close']).rows()]


def _ema_of_tf(x: PlanInput, tf: str, span: int) -> Optional[float]:
    """The EMA of the leg's own timeframe: 15m from the frame, 1h from the 1h candles, 4h = 4 x span on 1h."""
    if tf == '15m':
        closes = x.df['close'].to_list() if x.df is not None and not x.df.is_empty() else []
    else:
        closes = [c[4] for c in (x.h1 or [])]
        span = span * 4 if tf == '4h' else span
    if len(closes) < span:
        return None
    alpha, ema = 2 / (span + 1), closes[0]
    for c in closes[1:]:
        ema += alpha * (c - ema)
    return ema


def broke_structure(candles: List[List[float]], start_ts: int, end: float, direction: int) -> bool:
    """ICT: the impulse must break structure - its end beyond the last 3-candle swing high (up; low down) formed in the
    48 candles before the leg's start (a swing high below the start does not count for an up leg)."""
    before = [c for c in candles if c[0] < start_ts][-48:]
    for k in range(len(before) - 2, 0, -1):
        a, b, c = before[k - 1], before[k], before[k + 1]
        if direction > 0 and b[2] > a[2] and b[2] > c[2]:
            return end > b[2]
        if direction < 0 and b[3] < a[3] and b[3] < c[3]:
            return end < b[3]
    return True                     # no swing in reach: nothing to break (a leg out of price discovery)


def displacement(candles: List[List[float]], start_ts: int, end_ts: int, direction: int) -> bool:
    """
    ICT's displacement: the leg left a fair value gap in its direction - three candles inside the leg where the first's
    high is below the third's low (up; mirrored down): price moved too fast for the other side to trade there.
    """
    leg = [c for c in candles if start_ts <= c[0] <= end_ts]
    for a, c in zip(leg, leg[2:]):
        if (direction > 0 and a[2] < c[3]) or (direction < 0 and a[3] > c[2]):
            return True
    return False


class LegContinuation(Strategy):
    anchor_type = 'leg'
    requires = ('spot',)
    frozen_in_zone = True
    follows_live_candle = True

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        impulse = find_impulse(x.df, x.direction, x.h1)
        return (impulse['end_ts'], impulse['end']) if impulse else None

    def context_veto(self, sig: Dict, direction: int) -> Optional[str]:
        """
        Elder's triple screen: a pullback trade only with the tide - the coin's 1h trend (EMA20 slope; 1h is ~4-5x
        the 15m structure) not against the trade, and BTC (alts follow it: BTC -> alt Granger causality) not
        moving hard against it over the last hour. Breakouts take no trend filter (Turtle / Bollinger method I).
        """
        btc = sig.get('btc_1h')
        if btc is not None and direction * btc <= -CONFIG.strategies.tide_btc_against:
            return 'btc_against'     # eng-110: BTC is not Elder's tide (his is the coin's longer timeframe) - shadow
        return None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        cfg = CONFIG.levels
        d = x.direction
        impulse = find_impulse(x.df, d, x.h1)
        atr = x.atr
        if impulse is None or not atr:
            return None
        # Elder's tide on the timeframe ~5x the leg's (his factor of five): a 15m leg needs the 1h trend, a 1h leg the
        # 4h one, a 4h leg the daily one - not against the trade (was the 1h trend for every leg)
        tide = {'15m': 'coin_trend', '1h': 'trend_4h', '4h': 'trend_1d'}.get(impulse['tf'], 'coin_trend')
        if x.sig.get(tide) == -d:
            return {'skip': 'against_tide'}
        if CONFIG.strategies.require_displacement:
            candles = _rows(x.df) if impulse['tf'] == '15m' else [list(c) for c in (x.h1 or [])]
            if not displacement(candles, impulse['start_ts'], impulse['end_ts'], d):
                return {'skip': 'no_displacement'}
            if not broke_structure(candles, impulse['start_ts'], impulse['end'], d):
                return {'skip': 'no_bos'}
        zones = merge(list(x.raw_levels or []) + _leg_levels(x.df, impulse, None), atr, symbol=x.symbol)
        lo_ratio, hi_ratio = cfg.continuation_zone
        fib_lo, fib_hi = sorted((fib_price(impulse, lo_ratio), fib_price(impulse, hi_ratio)))
        # eng-121: the zone is ICT's OTE band itself (a map level inside it / Raschke's EMA20 + ADX were ours / another
        # method mixed in)
        level_lo, level_hi, zone_src, half = fib_lo, fib_hi, f"OTE {lo_ratio:g}-{hi_ratio:g}", 0.0
        stop_ref = stop_ref_src = None
        near, far = (level_hi + half, level_lo - half) if d > 0 else (level_lo - half, level_hi + half)
        lo_ratio = max(0.0, retracement_of(impulse, near))
        hi_ratio = min(1.0, retracement_of(impulse, far))
        # the trend-based extension from the pullback's expected extreme (the zone's deep edge) until the real one is
        # known at the entry (geometry.entry_levels re-measures from it)
        c_est = fib_price(impulse, hi_ratio)
        leg = impulse['end'] - impulse['start']
        extensions = [c_est + k * leg for k in cfg.continuation_targets]
        worst_entry = fib_price(impulse, lo_ratio)
        # targets spaced in the ATR of the leg's own timeframe (15m ATR steps put TP1 inside a 1h / 4h leg's noise)
        targets, sources = select_targets(zones, worst_entry, d, impulse['atr'], 'extension', extensions, 'fib ext')
        zone = sorted((fib_price(impulse, lo_ratio), fib_price(impulse, hi_ratio)))
        # eng-117, the sources on ICT's OTE (LuxAlgo, ChartingLens: "stop beyond the swing that anchors the measurement"
        # = the 100% level, the impulse's start): the stop is beyond the leg's start, not the OTE zone's deep edge /
        # a structural zone inside it (ours, tighter)
        stop_ref, stop_ref_src = impulse['start'], "beyond the impulse's start (the 100% level, ICT OTE)"
        tf = impulse['tf']
        return base_plan(x, self.name, _leg_anchor(impulse), tf, trigger_minutes=TRIGGER_MINUTES.get(tf, 5),
                         leg_atr=impulse['atr'], entry='pullback', zone_lo=zone[0], zone_hi=zone[1], zone_src=zone_src,
                         # ICT: the idea is wrong beyond the impulse's start (the 100% level), not at 0.786 inside
                         # the OTE band
                         trigger='touch', trail_after_tp1=True,
                         invalid=fib_price(impulse, CONFIG.levels.continuation_invalid), reset=impulse['end'],
                         missable=False, retarget=True,
                         stop_ref=stop_ref, stop_ref_src=stop_ref_src,
                         intent='extension', fillers=tuple(extensions), fill_label='ext', targets=targets,
                         target_src=sources, zones=zones, key=(impulse['end_ts'], impulse['end']), impulse=impulse)


class MomentumStrategy(LegContinuation):
    """The impulse detected by Tier-0 (5m move + OI + flow); the same pullback trade (eng-35: one strategy)."""
    name = 'continuation'
    setups = {'IMPULSE UP': 1, 'IMPULSE DOWN': -1}
