"""Closed, complete UTC candles are required for structural ATR and HTF patterns."""
import polars as pl
import pytest

from levels import find_impulse, resample_htf
from strategies.structure import bars_4h, hours_from

M = 60_000
H = 60 * M
Q = 15 * M
T = 100 * 24 * H


def hourly(n=8):
    return [[i * H, 10 + i, 12 + i, 9 + i, 11 + i, 100, 50, 2] for i in range(n)]


@pytest.mark.parametrize('builder', ['atr', 'detector'])
def test_complete_4h_ohlc_agrees_between_builders(builder):
    rows = hourly()
    out = resample_htf(rows, 4) if builder == 'atr' else bars_4h(rows, 8 * H)
    assert [b[:5] for b in out] == [[0, 10, 15, 9, 14], [4 * H, 14, 19, 13, 18]]


@pytest.mark.parametrize('builder', ['atr', 'detector'])
@pytest.mark.parametrize('fault', ['duplicate', 'missing', 'off_grid', 'partial'])
def test_incomplete_or_malformed_hour_group_is_not_a_4h_candle(builder, fault):
    rows = hourly(4)
    if fault == 'duplicate':
        rows = [rows[i] for i in (0, 0, 2, 3)]
    elif fault == 'missing':
        rows.pop(1)
    elif fault == 'off_grid':
        rows[0][0] += M
    else:
        rows.pop()
    out = resample_htf(rows, 4) if builder == 'atr' else bars_4h(rows, 4 * H)
    assert out == []


def test_partial_leading_and_trailing_groups_do_not_change_closed_atr_inputs():
    rows = hourly(9)[1:]
    assert resample_htf(rows, 4) == [[4 * H, 14, 19, 13, 18]]


def test_quarters_repair_an_interior_hour_gap_without_replacing_rest():
    quarters = [[i * Q, 100 + i, 102 + i, 99 + i, 101 + i, 10, 6, 2] for i in range(12)]
    rest = [[0, 10, 15, 9, 14, 100, 50, 5], [2 * H, 30, 35, 29, 34, 300, 150, 15]]
    out = hours_from(quarters, rest, 3 * H)
    assert out == [rest[0], [H, 104, 109, 103, 108, 40, 24, 8], rest[1]]


def test_repaired_hours_stay_closed_at_the_observation_time():
    quarters = [[i * Q, 100, 101, 99, 100, 10, 6, 2] for i in range(8)]
    assert [r[0] for r in hours_from(quarters, [], H + Q)] == [0]


@pytest.mark.parametrize('direction', [1, -1])
def test_impulse_atr_does_not_read_hours_after_its_15m_frame(direction):
    rows = [[T + i * Q, 100, 101, 99, 100] for i in range(100)]
    rows[0][3] = 90
    rows[96] = [T + 96 * Q, 100, 140, 100, 130]
    rows[97] = [T + 97 * Q, 130, 135, 120, 125]
    rows[98] = [T + 98 * Q, 125, 130, 120, 125]
    rows[99] = [T + 99 * Q, 125, 129, 119, 123]
    history = [[T + (i - 75) * H, 100, 101, 99, 100] for i in range(100)]
    later = [[T + i * H, 100, 1000 if i == 25 else 101, 99, 100] for i in (25, 26, 27)]
    if direction < 0:
        def mirror(bars):
            return [[t, 2000 - o, 2000 - lo, 2000 - hi, 2000 - c] for t, o, hi, lo, c in bars]
        rows, history, later = map(mirror, (rows, history, later))
    frame = pl.DataFrame(rows, schema=['timestamp', 'open', 'high', 'low', 'close'], orient='row')
    frame = frame.with_columns(pl.lit(1.0).alias('atr'))
    before = find_impulse(frame, direction, history)
    assert before is not None and before['tf'] == '4h' and before['atr'] == pytest.approx(2.0)
    assert find_impulse(frame, direction, history + later) == before
