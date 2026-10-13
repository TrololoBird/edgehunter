"""
OI build (eng-88, OI BUILD LONG): open interest building fast while price already moves up - the regime the live
journal of 11-13.10 measured as pump-prone (OI 1h > +5%: a >= 10% rise within 4h in 14.7% of cases vs 1.3% for all
coins), but with NO direction on average (-2.5% against the market over 4h: the pumps give it back). So the trade is
momentum with a tight percentage trailing stop, not a hold: in, the stop trailed oi_build_trail behind the best price,
out at the latest after the TTL. The minute study had +0.94% a trade on 26 trades only, and the result was fragile to
the trail width: this is a LIVE TEST on the demo, judged by its own journal rows.

Detection on every final 1m candle, once per coin per hour: Binance OI over 60 minutes >= oi_build_oi_1h AND price
over 60 minutes >= oi_build_price_1h; OI over 15 minutes still rising (the build is running, not over).
"""
from typing import Dict, Optional, Sequence

from config import CONFIG
from strategies.base import PlanInput, Strategy
from strategies.oi_signal import MINUTE_MS, _close_at, _oi_change


def oi_build(minutes: Sequence[Sequence[float]], oi_samples: Sequence, now_ms: int) -> Optional[Dict]:
    cfg = CONFIG.strategies
    if len(minutes) < 61 or len(oi_samples) < 20:
        return None
    oi15, oi60 = _oi_change(oi_samples, now_ms, 15), _oi_change(oi_samples, now_ms, 60)
    if oi15 is None or oi60 is None or oi60 < cfg.oi_build_oi_1h or oi15 <= 0:
        return None
    last = minutes[-1]
    t0 = int(last[0])
    c60 = _close_at(minutes, t0 - 60 * MINUTE_MS)
    c15 = _close_at(minutes, t0 - 15 * MINUTE_MS)
    if c60 is None or c15 is None:
        return None
    p60, p15 = last[4] / c60 - 1, last[4] / c15 - 1
    if p60 < cfg.oi_build_price_1h:
        return None
    return {'setup': 'OI BUILD LONG', 'direction': 1,
            'setup_note': f"OI 1h {oi60:+.2%} / 15m {oi15:+.2%}, price 1h {p60:+.2%} / 15m {p15:+.2%} "
                          f"(OI build, momentum with a {cfg.oi_build_trail:.0%} trailing stop, live test)",
            'anchor_level': last[4], 'anchor_extreme': last[4] * (1 - cfg.oi_build_trail), 'anchor_label': 'OI build',
            'anchor_ts': t0, 'anchor_close': last[4], 'oi_build_oi60': oi60, 'oi_build_p60': p60,
            'event_ts': t0 + MINUTE_MS}


class OiBuildStrategy(Strategy):
    name = 'oi_build'
    anchor_type = 'level'
    setups = {'OI BUILD LONG': 1}
    ttl_key = 'oi_build_ttl'
    time_exit = 'fixed'
    default_tf = '15m'

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('anchor_ts'), 'oi_build') if x.sig.get('oi_build_oi60') is not None else None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        from strategies.maniac_strategies import _confirm_plan
        if x.sig.get('oi_build_oi60') is None:
            return None
        pct = CONFIG.strategies.oi_build_trail
        exit = {'stop': ['price', x.sig['anchor_close'] * (1 - pct)], 'stop_src': f'{pct:.0%} below the entry',
                'tp': ['trail'], 'tp_src': f'none: a {pct:.0%} trailing stop', 'atr': x.atr}
        plan = _confirm_plan(x, self.name, '15m', exit, 'OI build: OI and price rising together')
        if plan and not plan.get('skip'):
            plan.update(no_tp=True, trail_pct=pct, be_after_r=None, trail_after_tp1=False)
        return plan
