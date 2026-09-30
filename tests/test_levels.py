from conftest import CUR15, minute
from levels import find_impulse, fill_price, ltf_trigger, pullback_volume_ok, resample, retracement_of, simulate
from strategies import STRATEGIES, PlanInput
from strategies.geometry import entry_levels

FIVE = 5 * 60_000


def bull_ltf(t0=CUR15, interval=FIVE, final_q=8e3):
    """Pullback into the zone, extreme 109.2, then a close above the structure high 111.2 on net buying."""
    def bar(i, o, h, l, c, q=1e4, Q=5e3):
        return [t0 + i * interval, o, h, l, c, q, Q]
    return [bar(-3, 111, 111.2, 110.6, 110.8), bar(-2, 110.8, 110.9, 110.2, 110.3), bar(-1, 110.3, 110.4, 109.9, 110.0),
            bar(0, 110.0, 110.1, 109.4, 109.6, Q=4e3), bar(1, 109.6, 109.8, 109.2, 109.3, Q=4e3),
            bar(2, 109.3, 110.2, 109.3, 110.1, Q=6e3), bar(3, 110.1, 111.5, 110.0, 111.4, Q=final_q)]


def _x(df, direction, setup, sig=None):
    return PlanInput(symbol='X', direction=direction, setup=setup, sig=sig or {}, df=df, minutes=[], raw_levels=[],
                     h1=[], context=None, reached=None)


def test_impulse_plan_continuation_and_reversal(rally_frame):
    imp = find_impulse(rally_frame, +1)
    assert imp and imp['end'] > 119 and imp['start'] < 101 and imp['candles'] >= 4
    plan = STRATEGIES['trend'].plan(_x(rally_frame, +1, 'BULL F'))
    assert plan['zone_lo'] < plan['zone_hi'] and plan['targets'][0] >= imp['end'] - 1e-9
    assert plan['invalid'] == imp['start'] and plan['reset'] == imp['end'] and not plan['missable']
    assert 0.382 <= retracement_of(imp, 109.5) <= 0.786
    rplan = STRATEGIES['wyckoff'].plan(_x(rally_frame, -1, 'BEAR C'))
    # Targets start beyond the lowest price reached since the leg's end; the invalidation sits beyond the end
    assert rplan['targets'][0] > rplan['targets'][1] > rplan['targets'][2] and rplan['targets'][0] < rplan['reached']
    assert rplan['invalid'] > imp['end'] and rplan['fix_invalid'] and rplan['entry'] == 'confirm'


def test_spring_targets_the_range_high():
    from conftest import CHOP, N, frame
    from indicators import compute_indicators
    drop = [120 - 1.0 * i for i in range(1, 21)]
    ind = compute_indicators(frame((CHOP[:70] + drop + [100.5] * 9)[-N:]))
    plan = STRATEGIES['wyckoff'].plan(_x(ind, +1, 'BULL B', {'prior_range_high': 112.0}))
    assert plan['intent'] == 'range' and 112.0 in plan['targets']


def test_resample_to_5m_only_closed_buckets():
    t0 = CUR15
    ones = [minute(t0, i, 100 + i, 101 + i, 99 + i, 100.5 + i, q=10, Q=6) for i in range(12)]
    bars = resample(ones, 5, now_ms=t0 + 12 * 60_000)
    assert len(bars) == 2                          # the third bucket (minutes 10-11) is still open
    assert bars[0][0] == t0 and bars[0][1] == 100 and bars[0][4] == 104.5
    assert bars[0][2] == 105 and bars[0][3] == 99 and bars[0][5] == 50 and bars[0][6] == 30


def test_ltf_trigger_bull_bear_and_flow():
    trig = ltf_trigger(bull_ltf(), +1, CUR15, FIVE)
    assert trig and trig['entry'] == 111.4 and trig['extreme'] == 109.2 and trig['time'] == CUR15 + 4 * FIVE
    assert ltf_trigger(bull_ltf()[:-1], +1, CUR15, FIVE) is None
    assert ltf_trigger(bull_ltf(final_q=1e3), +1, CUR15, FIVE) is None     # break on net selling
    bear = [[c[0], 220 - c[1], 220 - c[3], 220 - c[2], 220 - c[4], c[5], c[5] - c[6]] for c in bull_ltf()]
    tb = ltf_trigger(bear, -1, CUR15, FIVE)
    assert tb and abs(tb['entry'] - (220 - 111.4)) < 1e-9 and abs(tb['extreme'] - (220 - 109.2)) < 1e-9


def test_entry_levels_reversal_stop_beyond_leg_end(rally_frame):
    plan = STRATEGIES['trend'].plan(_x(rally_frame, +1, 'BULL F'))
    trig = ltf_trigger(bull_ltf(), +1, CUR15, FIVE)
    lv = entry_levels(plan, trig['entry'], trig['extreme'], +1)
    assert lv['sl'] < 109.2 and lv['tp1'] > trig['entry'] and lv['rr_tp1'] > 0 and 'low_rr' in lv
    # Reversal short after the rally: a trigger whose LTF extreme is BELOW the leg end must still stop above the leg end
    rplan = STRATEGIES['wyckoff'].plan(_x(rally_frame, -1, 'BEAR C'))
    leg_end = rplan['impulse']['end']
    lv2 = entry_levels(rplan, leg_end - 3, leg_end - 1, -1)
    assert lv2 and lv2['sl'] > leg_end


def test_low_rr_flag(rally_frame):
    # the synthetic rally has no swing between its origin and the pullback: no protected swing (strategies/ict.py)
    plan = dict(STRATEGIES['trend'].plan(_x(rally_frame, +1, 'BULL F')), protected=None)
    atr = plan['atr']
    far = STRATEGIES['trend'].plan(_x(rally_frame, +1, 'BULL F'))['targets'][0]
    tight = entry_levels(dict(plan, retarget=False, targets=[far, far + atr, far + 2 * atr], target_src=['a', 'b', 'c']),
                         far - 0.1, far - 5, +1)
    assert tight['low_rr'] is True
    good = entry_levels(plan, 110.0, 109.5, +1)
    assert good['low_rr'] is False


def test_spring_test_volume():
    t0 = CUR15
    quiet = [minute(t0, i, 1, 1, 1, 1, q=500) for i in range(5)]
    loud = [minute(t0, i, 1, 1, 1, 1, q=5000) for i in range(5)]
    assert pullback_volume_ok(quiet, t0, t0 + 5 * 60_000, reference_minute_usd=2000)
    assert not pullback_volume_ok(loud, t0, t0 + 5 * 60_000, reference_minute_usd=2000)
    assert pullback_volume_ok(loud, t0, t0 + 5 * 60_000, reference_minute_usd=0)   # unknown reference: no veto


def test_simulate_trigger_and_manual_fill():
    lv = {'entry': 100, 'sl': 98, 'tp1': 104, 'tp2': 106, 'tp3': 108}
    candles = [[0, 100, 104.2, 99.5, 104], [0, 104, 106.1, 103, 105], [0, 105, 105, 97.9, 98]]
    sim = simulate(lv, 1, candles, use_fill=False)
    assert sim['outcome'] == 'TP2' and sim['r_tp1'] == 2.0 and sim['r_tp2'] == 3.0
    filled = simulate(lv, 1, candles, use_fill=True)
    fill = fill_price(lv, 1, candles)
    assert filled['entry_fill'] == fill and fill > 100          # slippage against a long
    assert filled['r_tp1'] < 2.0                                 # worse fill -> smaller R
    skipped = simulate(lv, 1, [[0, 97.5, 98, 97, 97.5]], use_fill=True)
    assert skipped['outcome'] == 'SKIPPED' and skipped['filled'] == 0
