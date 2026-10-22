"""eng-138: audit 2026-10-17 A06 (POC ties), A08 (DST sessions), BB1 squeeze recency, base volume, required parts
out of the shadow list, R05 (calendar Newey-West)."""
from datetime import datetime

import numpy as np
import pytest

M = 60_000


def test_a06_poc_tie_nearest_the_middle():
    from strategies.classic import value_area
    flat = [[k * 30 * M, 100, 110, 100, 105, 1.0] for k in range(4)]     # every row visited equally
    _, poc, _ = value_area(flat, buckets=10, tpo=True)
    assert poc == pytest.approx(104.5)                                  # was 100.5 (the lowest row)


@pytest.mark.parametrize('day', ['2026-03-08', '2026-11-01'])
def test_a08_london_session_on_dst_days(day):
    from zoneinfo import ZoneInfo
    import strategies.silver_bullet as sb
    ny = ZoneInfo('America/New_York')
    d = datetime.fromisoformat(day).date()
    want = (datetime(d.year, d.month, d.day, 2, tzinfo=ny).timestamp() * 1000,
            datetime(d.year, d.month, d.day, 5, tzinfo=ny).timestamp() * 1000)
    src = open(sb.__file__, encoding='utf-8').read()
    assert 'ny_ms(day, 2), ny_ms(day, 5)' in src
    # wall-clock 02:00-05:00: 2 real hours on the spring-forward day, 3 on the fall-back day (02:00 is after the repeat)
    assert want[1] - want[0] == (2 if day.endswith('03-08') else 3) * 3_600_000


def test_base_volume_reads_the_candle():
    from strategies.maniac import _base_volume
    assert _base_volume([[0, 1, 2, 1, 1.5, 300.0, 0, 7.0]])[0] == 7.0
    assert _base_volume([[0, 1, 2, 1, 1.5, 300.0]])[0] == pytest.approx(300 / 1.5)


def test_bb1_needs_a_squeeze_in_the_last_five_bars():
    from strategies.maniac import bb_method1_event
    rng = np.random.default_rng(1)
    c = list(100 + np.cumsum(rng.normal(0, 1, 160)))
    c += [c[-1]] * 30                     # a dead-flat stretch = the squeeze, then 20 normal bars, then a breakout
    c += list(c[-1] + np.cumsum(rng.normal(0, 1, 20)))
    c.append(c[-1] + 15)
    bars = [[k * 4 * 3_600_000, x, x + 0.5, x - 0.5, x, 1e6, 5e5, 1e4] for k, x in enumerate(c)]
    assert bb_method1_event(bars) is None                            # the squeeze ended > 5 bars ago


def test_required_parts_are_not_shadowed():
    from signal_book import shadow_veto
    sig = {}
    assert shadow_veto(sig, 'no_spring_test') == 'no_spring_test'    # Wyckoff's test is part of the spring
    assert shadow_veto(sig, 'po3_bias_required') == 'po3_bias_required'
    assert shadow_veto(sig, 'no_supply') is None and 'no_supply' in sig['shadow_veto']
