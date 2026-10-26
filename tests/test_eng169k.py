from strategies import geometry


def _plan():
    return {'setup': 'ENTRY SWEEP LOW', 'symbol': None, 'tf': '15m', 'zones': []}


def test_near_tp1_is_stepped_over_to_the_next_level():
    # risk 2: TP1 100.4 is ~0.15R, the next levels 103 / 106 are >= 0.5R
    out = geometry.finish_levels(_plan(), 100.0, 98.0, [100.4, 103.0, 106.0], ['1h swing'] * 3, 1, 'x')
    assert out['tp1'] > 102 and out['rr_tp1'] >= 0.5 and out['tp1_stepped'] == 1
    assert 'eng-169k' not in (out['rr_reason'] or '')


def test_no_level_beyond_half_r_is_low_rr():
    out = geometry.finish_levels(_plan(), 100.0, 98.0, [100.3, 100.5, 100.7], ['1h swing'] * 3, 1, 'x')
    assert out['low_rr']                    # the blended rule or eng-169k's 'no level beyond'
    own = dict(_plan(), min_rr=0.0)         # a method minimum of 0: the blend is not the rule, eng-169k decides
    out = geometry.finish_levels(own, 100.0, 98.0, [100.3, 100.5, 100.7], ['1h swing'] * 3, 1, 'x')
    assert out['low_rr']


def test_tp1_at_or_beyond_half_r_untouched():
    out = geometry.finish_levels(_plan(), 100.0, 98.0, [102.0, 104.0, 106.0], ['1h swing'] * 3, 1, 'x')
    assert out['tp1'] < 102 and out['rr_tp1'] >= 0.5 and out['tp1_stepped'] == 0


def test_short_mirrored():
    out = geometry.finish_levels(_plan(), 100.0, 102.0, [99.6, 97.0, 94.0], ['1h swing'] * 3, -1, 'x')
    assert out['tp1'] < 98 and out['rr_tp1'] >= 0.5
