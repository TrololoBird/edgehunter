"""
Leg strategies: a real leg (levels.find_impulse: its end on the last 12h of 15m candles, its start searched back over
15m and 1h history; its timeframe by duration 15m / 1h / 4h, the entry 3-6x finer).

- trend (BULL F / BEAR D) and momentum (IMPULSE UP / DOWN): continuation. The pullback zone is the strongest support
  inside 0.382-0.786 of the leg (else the Fibonacci band); entry on a structure shift there; invalid beyond the leg's
  start; a new extreme resets the card to waiting; targets re-measured from the entry toward the leg's extensions.
- wyckoff (BULL A / B / E, BEAR C): reversal of the leg. Entry at the confirmation when R:R allows it, else a pullback
  near the leg's end; invalid beyond the end and the stop pool behind it; targets fixed beyond the furthest price
  reached since: a trading range's far side (A, B) or the mean (C, E), the leg's retracements fill empty slots.
"""
from typing import Dict, List, Optional

import polars as pl

from config import CONFIG
from levels import _leg_levels, fib_price, find_impulse, reached_after, retracement_of
from strategies.base import TRIGGER_MINUTES, PlanInput, Strategy, base_plan
from strategies.geometry import cap_for_rr, select_targets
from zones import RawLevel, is_structural, merge, stop_beyond, support_in


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
        if sig.get('coin_trend') == -direction:
            return 'against_tide'
        btc = sig.get('btc_1h')
        if btc is not None and direction * btc <= -CONFIG.strategies.tide_btc_against:
            return 'against_tide'
        return None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        cfg = CONFIG.levels
        d = x.direction
        impulse = find_impulse(x.df, d, x.h1)
        atr = x.atr
        if impulse is None or not atr:
            return None
        zones = merge(list(x.raw_levels or []) + _leg_levels(x.df, impulse, None), atr)
        lo_ratio, hi_ratio = cfg.continuation_zone
        fib_lo, fib_hi = sorted((fib_price(impulse, lo_ratio), fib_price(impulse, hi_ratio)))
        support = support_in(zones, fib_lo, fib_hi, d)
        half = CONFIG.zones.zone_half_atr * impulse['atr']
        stop_ref = stop_ref_src = None
        if support is not None:
            level_lo, level_hi, zone_src = support.lo, support.hi, support.label
            if is_structural(support):
                # the trade's structure is this zone (its edge drawn by wicks): the stop goes beyond all of it, not
                # beyond the entry trigger's 5m low inside it
                stop_ref, stop_ref_src = (support.lo if d > 0 else support.hi), f"beyond the zone ({support.label})"
        else:
            ema = _ema_of_tf(x, impulse['tf'], 20)
            if ema is None or not fib_lo <= ema <= fib_hi:
                return {'skip': 'no_level'}
            # Linda Raschke's Holy Grail, where the EMA20 pullback comes from: only in a strong trend, ADX(14) > 30
            adx = x.sig.get('adx')
            if adx is not None and adx <= CONFIG.strategies.holy_grail_adx:
                return {'skip': 'weak_trend'}
            level_lo = level_hi = ema
            zone_src = f"EMA20 {impulse['tf']}"
        near, far = (level_hi + half, level_lo - half) if d > 0 else (level_lo - half, level_hi + half)
        lo_ratio = max(0.0, retracement_of(impulse, near))
        hi_ratio = min(1.0, retracement_of(impulse, far))
        extensions = [fib_price(impulse, 1.0 - r) for r in cfg.continuation_targets]
        worst_entry = fib_price(impulse, lo_ratio)
        # targets spaced in the ATR of the leg's own timeframe (15m ATR steps put TP1 inside a 1h / 4h leg's noise)
        targets, sources = select_targets(zones, worst_entry, d, impulse['atr'], 'extension', extensions, 'fib ext')
        zone = sorted((fib_price(impulse, lo_ratio), fib_price(impulse, hi_ratio)))
        tf = impulse['tf']
        return base_plan(x, self.name, _leg_anchor(impulse), tf, trigger_minutes=TRIGGER_MINUTES.get(tf, 5),
                         leg_atr=impulse['atr'], entry='pullback', zone_lo=zone[0], zone_hi=zone[1], zone_src=zone_src,
                         invalid=impulse['start'], reset=impulse['end'], missable=False, retarget=True,
                         stop_ref=stop_ref, stop_ref_src=stop_ref_src,
                         intent='extension', fillers=tuple(extensions), fill_label='fib ext', targets=targets,
                         target_src=sources, zones=zones, key=(impulse['end_ts'], impulse['end']), impulse=impulse)


class TrendStrategy(LegContinuation):
    name = 'trend'
    setups = {'BULL F': 1, 'BEAR D': -1}


class MomentumStrategy(LegContinuation):
    """The Tier-0 impulse (5m move + OI + flow) is the event; the trade is the pullback of the leg it belongs to."""
    name = 'momentum'
    setups = {'IMPULSE UP': 1, 'IMPULSE DOWN': -1}


class WyckoffStrategy(Strategy):
    name = 'wyckoff'
    anchor_type = 'leg'
    follows_live_candle = True
    setups = {'BULL A': 1, 'BULL B': 1, 'BULL E': 1, 'BEAR C': -1}

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        impulse = find_impulse(x.df, -x.direction, x.h1)
        return (impulse['end_ts'], impulse['end']) if impulse else None

    @staticmethod
    def _range_far(x: PlanInput) -> Optional[float]:
        """A spring's / an accumulation's objective: the far side of the range it formed in (longs only)."""
        if x.direction < 0 or x.df is None:
            return None
        if x.setup == 'BULL B':
            # the range the spring swept, from the FUTURES frame (the scored row's prior_range_high is in spot units
            # for coins with a spot pair: 1000x off for 1000PEPE-type contracts, so the target was silently dropped)
            spring_ts = x.sig.get('candle_ts')
            if spring_ts is not None and 'timestamp' in x.df.columns:
                before = x.df.filter(pl.col('timestamp') < spring_ts)['high'].tail(CONFIG.metrics.spring_lookback)
                if before.len() >= CONFIG.metrics.spring_lookback // 2:
                    return float(before.max()) or None
            return None if x.sig.get('has_spot') else (x.sig.get('prior_range_high') or None)
        if x.setup == 'BULL A':
            window = CONFIG.metrics.price_flat_window
            return max(x.df['high'].tail(window + 1).head(window).to_list() or [0.0]) or None
        return None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        cfg = CONFIG.levels
        d = x.direction
        impulse = find_impulse(x.df, -d, x.h1)
        atr = x.atr
        if impulse is None or not atr:
            return None
        far = self._range_far(x)
        extra: List[RawLevel] = [RawLevel(far, 'range', 'range high', +1)] if far else []
        zones = merge(list(x.raw_levels or []) + _leg_levels(x.df, impulse, None) + extra, atr)
        end = impulse['end']
        base, _ = stop_beyond(zones, end, end, d, impulse['atr'])
        stop_est = base - d * cfg.stop_buffer_atr * impulse['atr']
        reached = x.reached if x.reached is not None else reached_after(_rows(x.df), impulse['end_ts'], end, d)
        retraces = [fib_price(impulse, r) for r in cfg.reversal_targets]
        intent = 'range' if x.setup in ('BULL A', 'BULL B') else 'mean'
        first = (far, 'range high') if far and d * (far - reached) > 0 else None
        targets, sources = select_targets(zones, reached, d, impulse['atr'], intent, retraces, 'fib', first=first)
        zone_max = cfg.accumulation_zone_max if x.setup == 'BULL A' else cfg.reversal_zone_max
        hi_ratio = zone_max
        zone_src = f"leg end (0-{hi_ratio:g})"
        capped = retracement_of(impulse, cap_for_rr(targets[0], stop_est, d, atr, x.recent_atr))
        if capped < hi_ratio:
            hi_ratio = max(0.0, capped)
            zone_src = f"leg end (0-{hi_ratio:.2f}, R:R >= {cfg.min_rr_tp1:g} to TP1)"
        zone = sorted((end, fib_price(impulse, hi_ratio)))
        tf = impulse['tf']
        return base_plan(x, self.name, _leg_anchor(impulse), tf, trigger_minutes=TRIGGER_MINUTES.get(tf, 5),
                         leg_atr=impulse['atr'], entry='confirm', zone_lo=zone[0], zone_hi=zone[1], zone_src=zone_src,
                         invalid=stop_est, fix_invalid=True, missable=True, stop_ref=end, intent=intent,
                         fillers=tuple(retraces), fill_label='fib', targets=targets, target_src=sources, zones=zones,
                         reached=reached, key=(impulse['end_ts'], end), impulse=impulse)
