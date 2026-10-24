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
