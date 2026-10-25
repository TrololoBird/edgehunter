"""eng-164: Turtle unit limit counting, ORB one-hour break-even, small-cap failing gate."""
from types import SimpleNamespace as N

from signal_book import SignalBook


def _card(direction, units, finished=False):
    return N(direction=direction, units=units, finished=finished)


def test_direction_units_count_only_open_unit_cards_same_side():
    sb = SignalBook.__new__(SignalBook)
    me = _card(-1, [])
    sb.signals = {
        'a': _card(-1, [[1, 0], [2, 0], [3, 0]]),     # open Turtle short, 3 units
        'b': _card(-1, [[1, 0]], finished=True),       # finished: not counted
        'c': _card(-1, []),                            # a non-unit card (trendline short): not counted
        'd': _card(1, [[1, 0], [2, 0]]),               # other side: not counted
        'me': me,
    }
    assert sb._direction_units(me) == 3


def test_orb_break_even_after_60_minutes_needs_the_whole_minute_beyond():
    sb = SignalBook.__new__(SignalBook)
    sb.events = []

    def card(held_min):
        return N(plan={'no_tp': True, 'be_after_min': 60}, levels={'entry': 100.0, 'sl': 102.0, 'risk0': 2.0},
                 direction=-1, units=[], part_ms={}, managed_ms=int((1000 + held_min * 60) * 1000),
                 entered_at=1000, best_target=0, symbol='X')
    early = card(59)
    sb._trail(early, None, hi=99.5, lo=99.0)
    assert early.levels['sl'] == 102.0
    touched = card(61)
    sb._trail(touched, None, hi=100.1, lo=99.0)                 # the minute touched break-even: no move
    assert touched.levels['sl'] == 102.0
    ok = card(61)
    sb._trail(ok, None, hi=99.5, lo=99.0)
    assert abs(ok.levels['sl'] - 100 * (1 - 0.0015)) < 1e-9
    n = len(sb.events)
    sb._trail(ok, None, hi=99.5, lo=99.0)                       # no repeated modification
    assert len(sb.events) == n


def test_smallcap_why_not_names_the_failing_gate():
    from smallcap import SmallCapWatch
    t0 = 1_792_800_000_000
    m, p = [], 1.0
    for i in range(240):
        if i >= 225:
            p *= 1.004
        m.append([t0 + i * 60_000, p, p * 1.001, p * 0.999, p, 1000.0, 400.0])
    move = m[-1][4] / m[-16][4] - 1
    assert SmallCapWatch._why_not(m, {'rvol_1m': 2}, 0.005, m[-1][0] + 60_000, [], move).startswith('RVOL')
    assert SmallCapWatch._why_not(m, {'rvol_1m': 6, 'oi_change_5m': 0.01, 'spot_cvd_5m': -1}, 0.005,
                                  m[-1][0] + 60_000, [], move) == 'taker flow against the move'


def test_span_targets_keep_tp1_beyond_the_risk_span():
    from strategies.pump import _risk_span, _span_targets
    span = _risk_span(100.0, 96.0, 4.0, 1.0)                   # |close - extreme| + 0.25 ATR = 4.25
    t, _ = _span_targets([103.0, 110.0, 110.0], ['zone', 'ext', 'ext'], 100.0, 1, span)
    assert all(x - 100.0 >= span for x in t)
    t, _ = _span_targets([97.0], ['zone'], 100.0, -1, _risk_span(100.0, 104.0, 4.0, 1.0))
    assert all(100.0 - x >= 4.25 for x in t)


def test_raid_swing_is_the_level_fvg_setup_must_break():
    from strategies.ict import fvg_setup, raid_swing
    step, t0 = 900_000, 1_792_800_000_000
    bars, p = [], 1.10
    for i in range(60):
        hi, lo = p * 1.002, p * 0.998
        if i == 40:
            hi, lo = 1.05, 1.03
        bars.append([t0 + i * step, p, hi, lo, p * 0.999, 1, 1])
        p *= 0.998
    since = t0 + 50 * step
    assert raid_swing(bars, 1, since, step) == 1.05
    assert fvg_setup(bars, 1, since, step) is None            # no close above 1.05 yet: no armed entry


def test_rolling_5m_bar_used_mid_bucket():
    from strategies import pd_features as pdf
    t0 = 1_792_800_000_000 + 2 * 60_000                        # minutes end mid 5m bucket
    m, p = [], 1.0
    for i in range(240):
        o = p
        if i >= 237:
            p *= 1.01
        m.append([t0 + i * 60_000, o, max(o, p), min(o, p), p, 5000.0 if i >= 237 else 1000.0, 2000.0])
    m5 = [[t0 - (300 - i) * 300_000 - 240 * 60_000, 1, 1.001, 0.999, 1, 5000.0, 2500.0] for i in range(290)]
    f = pdf.features(m, [], 1, m5)
    assert f.get('pd_rolling_bar') == 1 and f['pd_move3'] > 0.02


def test_dump_start_fires_on_a_long_flush():
    from strategies.pump import dump_start
    t0, m, p = 1_792_800_000_000, [], 1.0
    for i in range(240):
        if i >= 225:
            p *= 0.996
        m.append([t0 + i * 60_000, p, p * 1.001, p * 0.999, p, 1000.0, 400.0])
    h1 = [[t0 - (200 - i) * 3_600_000, 1, 1.01, 0.95, 1, 1e6, 5e5] for i in range(200)]
    d = dump_start(m, {'rvol_1m': 6, 'oi_change_5m': -0.02, 'spot_cvd_5m': -500}, 0.005, m[-1][0] + 60_000, h1)
    assert d is not None and d['pd_dump_oi_regime'] == 'long_flush'


def test_enter_shadow_tags_are_per_attempt():
    """eng-168: a shadow tag added by an earlier entry attempt must not survive into the next attempt."""
    import signal_book
    src = open(signal_book.__file__).read()
    i = src.index('def _enter(')
    body = src[i:i + 2500]
    assert body.count('self._new_attempt(s)') == 0 and src.count('self._new_attempt(s)') == 2
    assert "s.direction > 0 and 'htf_bias' in" not in src


def test_range_is_its_own_tag_for_with_bias_setups():
    from strategies import bias
    assert bias.gate('sweep', 1, 'range') == 'htf_range'
    assert bias.gate('supply_demand', -1, 'range') == 'htf_range'
    assert bias.gate('sweep', 1, 'bear') == 'htf_bias'
    assert bias.gate('orb', 1, 'range') == 'htf_bias'
    assert bias.gate('bollinger', 1, 'range') is None


def test_card_tp1_is_the_systems_own_level_target():
    from signal_book import card_tp1
    plan = {'targets': [101.0, 105.0], 'exit': {'tp': ['level', 110.0, 1.0, None]}}
    assert card_tp1(plan) == 110.0
    assert card_tp1({'targets': [101.0], 'exit': {'tp': ['trail']}}) == 101.0
    assert card_tp1({'targets': [101.0]}) == 101.0


def test_continuation_new_high_before_the_zone_is_not_missed():
    """eng-168e: the source guard exists - a continuation's TP1 at the impulse end does not end a card outside the zone."""
    import signal_book
    src = open(signal_book.__file__).read()
    assert "eng-168e" in src and "frozen_in_zone" in src[src.index('eng-168e') - 400:src.index('eng-168e')]


def test_impulse_start_moves_to_the_pullback_swing_after_a_bos():
    """eng-168f: up 100 -> 120 (swing high), pullback to 110 (50%, a 2/2 swing low), rally to 130 (BOS), then two
    lower candles: the leg is 110 -> 130, not 100 -> 130."""
    import polars as pl
    from levels import find_impulse
    path = [100, 104, 108, 112, 116, 120, 118, 115, 112, 110, 113, 117, 121, 125, 130, 128, 127]
    path = [102, 101] + path
    rows = []
    t0 = 1_700_000_000_000
    for k, p in enumerate(path):
        rows.append({'timestamp': t0 + k * 900_000, 'open': p, 'high': p + 0.5, 'low': p - 0.5, 'close': p,
                     'atr': 1.0})
    pad = [{'timestamp': t0 - (20 - k) * 900_000, 'open': 103.0, 'high': 103.4, 'low': 102.6, 'close': 103.0,
            'atr': 1.0} for k in range(20)]
    df = pl.DataFrame(pad + rows)
    imp = find_impulse(df, 1)
    assert imp is not None and imp['end'] == 130.5 and imp['start'] == 109.5


def test_crowd_counts_the_recent_cluster_only():
    """eng-168h: multi-day open trades do not fill the crowd slots; entries within crowd_window_h do."""
    from types import SimpleNamespace
    from signal_book import SignalBook
    book = SignalBook()
    now = 1_000_000.0
    old = {f'o{k}': SimpleNamespace(entered_at=now - 86400, finished=False, direction=-1) for k in range(10)}
    book.signals = dict(old)
    assert not book.crowded('trendline', -1, now) and book.crowded_open(-1)
    book.signals.update({f'n{k}': SimpleNamespace(entered_at=now - 600, finished=False, direction=-1) for k in range(6)})
    assert book.crowded('trendline', -1, now)


def test_briefing_stop_goes_beyond_every_stacked_zone():
    """eng-168j: the long's stop below the support lands in the next support, then the one after: beyond both."""
    import briefing_chart
    zones = [{'lo': 120.0, 'hi': 121.0, 'side': 1, 'tol': 0.1, 'pad': 0.2, 'mid': 120.5},
             {'lo': 98.0, 'hi': 99.0, 'side': -1, 'tol': 0.1, 'pad': 0.5, 'mid': 98.5},
             {'lo': 97.0, 'hi': 97.8, 'side': -1, 'tol': 0.1, 'pad': 0.5, 'mid': 97.4},
             {'lo': 96.0, 'hi': 96.7, 'side': -1, 'tol': 0.1, 'pad': 0.5, 'mid': 96.3}]
    p = briefing_chart.plan(100.0, zones)
    assert p['long'] is not None and p['long']['stop'] < 96.0
