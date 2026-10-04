"""
OI signal (eng-56, live test of cryptomillion's "OI [15m]" alerts, teletype.in/@cryptomillion/crypto-open-interest):
their rule - price + OI + CVD rising together = a likely pump (long); OI rising while price and CVD fall = a short;
signals agreeing on several timeframes are stronger. A commercial channel with no published evidence: this is a
LIVE TEST, judged by the journal like every strategy.

Detection on every final 1m candle (Scanner._oi_signal), once per coin / direction / 15m:
- 15m: OI (Binance, coins) >= oi_sig_oi_15m AND price move >= oi_sig_price_15m in the trade's direction AND the
  futures taker delta (CVD) of those 15 minutes in the trade's direction;
- 1h: OI rising and price moving the same way (their multi-timeframe agreement).
The thresholds are OURS (they publish none; their sample alert: OI +5.5% / price +3.6% on 15m).
Trade: at market, stop beyond the 15 minutes' extreme + the measured pierce, targets from the map.
"""
from typing import Dict, Optional, Sequence

from config import CONFIG
from strategies.base import PlanInput, Strategy

MINUTE_MS = 60_000


def _oi_change(samples: Sequence, now_ms: int, minutes: int) -> Optional[float]:
    if not samples:
        return None
    old = [v for t, v in samples if t <= now_ms - minutes * MINUTE_MS]
    if not old or not old[-1]:
        return None
    return samples[-1][1] / old[-1] - 1


def oi_signal(minutes: Sequence[Sequence[float]], oi_samples: Sequence, now_ms: int) -> Optional[Dict]:
    """minutes: final 1m futures candles [ts, o, h, l, c, quote_vol, taker_buy_quote]; oi_samples: (ts_ms, OI)."""
    cfg = CONFIG.strategies
    if len(minutes) < 61 or len(oi_samples) < 20:
        return None
    oi15, oi60 = _oi_change(oi_samples, now_ms, 15), _oi_change(oi_samples, now_ms, 60)
    if oi15 is None or oi60 is None or oi15 < cfg.oi_sig_oi_15m or oi60 <= 0:
        return None
    last = minutes[-1]
    p15 = last[4] / minutes[-16][4] - 1
    p60 = last[4] / minutes[-61][4] - 1
    window = minutes[-15:]
    cvd = sum(2 * c[6] - c[5] for c in window if len(c) > 6)
    if p15 >= cfg.oi_sig_price_15m and p60 > 0 and cvd > 0:
        d = 1
    elif p15 <= -cfg.oi_sig_price_15m and p60 < 0 and cvd < 0:
        d = -1
    else:
        return None
    extreme = min(c[3] for c in window) if d > 0 else max(c[2] for c in window)
    return {'setup': 'OI SIGNAL LONG' if d > 0 else 'OI SIGNAL SHORT', 'direction': d,
            'setup_note': f"15m OI {oi15:+.2%} / price {p15:+.2%}, 1h OI {oi60:+.2%} / price {p60:+.2%}, "
                          f"15m CVD {cvd / 1e3:+,.0f}k (cryptomillion OI [15m] rule, live test)",
            'anchor_level': last[4], 'anchor_extreme': extreme, 'anchor_label': 'OI signal',
            'anchor_ts': int(window[0][0]), 'anchor_close': last[4],
            'oi_sig_oi15': oi15, 'oi_sig_oi60': oi60, 'oi_sig_p15': p15, 'oi_sig_p60': p60,
            'event_ts': int(last[0]) + MINUTE_MS}


class OiSignalStrategy(Strategy):
    name = 'oi_signal'
    anchor_type = 'level'
    setups = {'OI SIGNAL LONG': 1, 'OI SIGNAL SHORT': -1}
    min_rr = 1.0                     # no rule in the source: only a trade paying more than its risk to the map's level
    ttl_key = 'pump_ttl'
    default_tf = '15m'

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('anchor_ts'), 'oi') if x.sig.get('oi_sig_oi15') is not None else None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        from strategies.maniac_strategies import _confirm_plan
        if x.sig.get('oi_sig_oi15') is None:
            return None
        exit = {'stop': ['ref', 0.0], 'stop_src': "beyond the 15 minutes' extreme", 'tp': ['map', 1.0], 'atr': x.atr}
        plan = _confirm_plan(x, self.name, '15m', exit, 'price + OI + CVD together (OI [15m])',
                             stop_ref=x.sig['anchor_extreme'])
        if plan and not plan.get('skip'):
            plan['trail_after_tp1'] = True        # eng-58: a momentum trade - half at TP1, the rest trailed
        return plan
