"""Offline counterexamples for the strategy audit; assertions describe current defects.

Run from the repository root. No bot, network, credentials, or production DB.
These examples do not measure profitability or claim to simulate exchange fills.
"""
import math
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import CONFIG
from levels import pullback_spread_ok
from signal_book import SignalBook, TrackedSignal
from strategies.base import PlanInput
from strategies.breakout import BreakoutStrategy
from strategies.cup_handle import CupHandleStrategy, cup_handle
from strategies.geometry import entry_levels
from strategies.maniac_strategies import BollingerStrategy, SupplyDemandStrategy
from strategies.wyckoff_range import WyckoffRangeStrategy
from zones import RawLevel, vwap


def plan_input(setup, extra, *, atr=1.0, native_atr=1.0, raw=None):
    sig = {'anchor_level': 100.0, 'anchor_close': 100.0, 'anchor_extreme': 90.0,
           'anchor_ts': 0, 'volume_24h': 1e9}
    sig.update(extra)
    return PlanInput('AUDIT', 1, setup, sig, None, [], raw or [], [],
                     SimpleNamespace(atr=atr), None,
                     {'1d': native_atr, '4h': native_atr})


def run():
    # S01: each bar trades exactly one asset; all prices in a bar are identical.
    bars = [[0, 100., 100., 100., 100., 100.],
            [60_000, 200., 200., 200., 200., 200.]]
    actual = vwap(bars, 0, 'audit')[0].price
    assert math.isclose(actual, 500 / 3) and not math.isclose(actual, 150)
    print(f'S01 VWAP: quote-weighted={actual:.6f}; quantity-weighted=150')

    x = plan_input('BREAKOUT UP', {'turtle_n': 5., 'trail_days': 10, 'turtle_system': 1})
    p = BreakoutStrategy().plan(x)
    lv = entry_levels(p, 110., 90., 1)
    assert lv['sl'] == 90 and (110 - lv['sl']) / 5 == 4
    print(f'S02 Turtle: channel=100 N=5 entry=110 SL={lv["sl"]}; distance=4N')

    # S04 is an inconsistency in the project's own sqrt-time heuristic.
    minutes = [[i * 60_000, 100., 101., 99., 100., 1., .5] for i in range(15)]
    accepted = pullback_spread_ok(minutes, 0, 900_000, 8.)
    heuristic_4h = CONFIG.levels.spring_test_spread_ratio * 8 / 4
    assert accepted and 2 > heuristic_4h
    print(f'S04 Wyckoff: test range=2 accepted; own 4h sqrt-time threshold={heuristic_4h}')

    x = plan_input('SD DEMAND', {'zone_lo': 95., 'zone_hi': 100., 'sd_strength': 2,
                                'sd_time': 1, 'trend_1d': 1, 'curve_pos': .2,
                                'sd_targets': [(102., 'near supply'), (130., 'far supply')]})
    p = SupplyDemandStrategy().plan(x)
    lv = entry_levels(p, 100., 95., 1)
    assert p['sd_score'] == 10 and lv['rr_tp1'] < .3 and lv['rr_blend'] > 3 and not lv['low_rr']
    print(f'S05 SupplyDemand: score={p["sd_score"]}; TP1 RR={lv["rr_tp1"]:.6f}; '
          f'blend={lv["rr_blend"]:.6f}; low_rr={lv["low_rr"]}')

    x = plan_input('BB W-BOTTOM', {'bb_stop': 99., 'bb_target': 102., 'bb_tf': '4h'}, native_atr=5.)
    p = BollingerStrategy().plan(x)
    lv = entry_levels(p, 100., 99., 1)
    assert lv['sl'] <= 95 and lv['rr_tp1'] < .4 and not lv['low_rr']
    print(f'S06 Bollinger: entry=100 bareSL=99 target=102 effectiveSL={lv["sl"]}; '
          f'RR={lv["rr_tp1"]:.6f}; low_rr={lv["low_rr"]}')

    x = plan_input('CUP HANDLE', {'ch_stop': 80., 'ch_target': 130.,
                                'ch_target_full': 140., 'ch_tf': '1d'}, native_atr=12.)
    p = CupHandleStrategy().plan(x)
    lv = entry_levels(p, 100., 80., 1)
    assert p['exit']['stop'][1] == 92 and lv['sl'] == 88
    print(f'S07 Cup: requestedSL=92; effectiveSL={lv["sl"]}; loss=12%')

    prices = [60 + .4 * i for i in range(101)]
    prices += [100 - 20 * j / 18 if j <= 18 else 80 + 20 * (j - 18) / 18
               for j in range(1, 37)]
    prices += [99, 98, 97, 96, 96, 96, 101.5]
    candles = [[i * 86_400_000, p, p + .2, p - .2, p,
                .5 if 137 <= i <= 142 else 1.6 if i == 143 else 1.]
               for i, p in enumerate(prices)]
    event = cup_handle(candles, '1d', 86_400_000)
    assert event and event['setup'] == 'CUP HANDLE'
    print('S08 Cup: strictly linear V-shape accepted:', event['setup_note'])

    threshold = CONFIG.strategies.dump_min_move
    ordinary = threshold / (1 + threshold)
    assert math.isclose(ordinary, .13043478260869565)
    print(f'S09 Dump: inverse threshold={threshold:.2%}; ordinary decline={ordinary:.6%}')

    s = TrackedSignal('AUDIT', 'RSI2 LONG', 1, 'connors', 0., 100., {},
                      entered_at=1., managed_ms=60_000, last_price=400., status='ENTRY',
                      levels={'entry': 100., 'sl': 99., 'risk0': 1.,
                              'tp1': 200., 'tp2': 300., 'tp3': 400.},
                      plan={'no_tp': True, 'no_stop': True})
    SignalBook()._manage_trade(s, 400., 180.,
                              lambda sym: [[60_000, 100., 401., 100., 400., 1.]])
    assert s.status == 'TP3' and s.finished
    print('S10 no_tp=True/no_stop=True, placeholder TP3 still finishes card:', s.status)

    x = plan_input('SPRING', {'range_lo': 95., 'range_hi': 110., 'anchor_level': 95.,
                            'wy_tf': '4h', 'pnf_target': 140.},
                   raw=[RawLevel(140., 'swing_15m', '15m high', 1)])
    p = WyckoffRangeStrategy().plan(x)
    lv = entry_levels(p, 100., 90., 1)
    assert 140 in p['targets'] and all(lv[f'tp{i}'] < 111 for i in (1, 2, 3))
    print(f'S11 Wyckoff: plan targets={p["targets"]}; '
          f'entry targets={[lv[f"tp{i}"] for i in (1, 2, 3)]}')
    print('PASS: 10 offline counterexamples. S03 is a static chronology finding, not an executed example.')


if __name__ == '__main__':
    run()
