"""Later observations must not rewrite decisions made at an earlier candle close."""
import pytest

from strategies import maniac, structure

M = 60_000
H = 60 * M
D = 24 * H
T = 100 * D


def mirror(rows, ceiling=200):
    return [[t, ceiling - o, ceiling - lo, ceiling - hi, ceiling - c, *rest]
            for t, o, hi, lo, c, *rest in rows]


@pytest.mark.parametrize('direction', [1, -1])
def test_later_volatility_does_not_erase_an_earlier_ifvg(direction):
    step = 5 * M
    rows = [[i * step, 100, 101, 99, 100, 1000] for i in range(12)]
    rows[2] = [2 * step, 111, 112, 110, 111, 1000]
    rows[3] = [3 * step, 110, 111, 104, 105, 1000]
    rows[4] = [4 * step, 105, 106, 104, 105, 1000]
    rows[5] = [5 * step, 106, 113, 105, 112, 1000]
    later = [[12 * step, 100, 10_000, 99, 100, 1000]]
    if direction < 0:
        rows, later = mirror(rows, 20_000), mirror(later, 20_000)
    before = maniac.ifvg_trigger(rows, direction, 3 * step, 0, step)
    assert before is not None and before['time'] == 6 * step
    assert maniac.ifvg_trigger(rows + later, direction, 3 * step, 0, step) == before


@pytest.mark.parametrize('direction', [1, -1])
@pytest.mark.parametrize('future_tf', ['4h', '1d'])
def test_supply_demand_uses_only_htf_bars_closed_at_signal(monkeypatch, direction, future_tf):
    cut = T + 4 * H
    h4 = [[cut - (40 - i) * 4 * H, 100, 120, 80, 100, 1000] for i in range(40)]
    d1 = [[T - (20 - i) * D, 100, 120, 80, 100, 1000] for i in range(20)]
    future_h4 = [[cut, 100, 120, 80, 100, 1000]]
    future_d1 = [[T, 90, 99, 1, 90, 1000]]
    event = {'setup': 'SD DEMAND', 'direction': 1, 'zone_lo': 89, 'zone_hi': 91, 'event_ts': cut}
    if direction < 0:
        h4, d1, future_h4, future_d1 = map(mirror, (h4, d1, future_h4, future_d1))
        event.update(setup='SD SUPPLY', direction=-1, zone_lo=109, zone_hi=111)
    monkeypatch.setattr(structure, '_BAR_DONE', {})
    monkeypatch.setattr(maniac, 'sd_zone_events', lambda *a: [dict(event)])
    before = structure.maniac_events('AUDIT', [], [], None, cut, h4, d1)
    assert len(before) == 1
    assert before[0]['curve_pos'] == pytest.approx(0.25 if direction > 0 else 0.75)
    structure._BAR_DONE.clear()
    after = structure.maniac_events('AUDIT', [], [], None, cut,
                                   h4 + (future_h4 if future_tf == '4h' else []),
                                   d1 + (future_d1 if future_tf == '1d' else []))
    assert after == before


@pytest.mark.parametrize('ahead_ms', [1, 15 * M])
def test_context_rejects_a_candle_that_has_not_closed(ahead_ms):
    close = T + H
    rows = [[close - 15 * M, 100, 101, 99, 100, 1000, 500]]
    assert structure.build_context(rows, [], 1.0, [], close - ahead_ms, symbol='AUDIT') is None


def test_context_accepts_the_exact_close_boundary():
    close = T + H
    rows = [[close - 15 * M, 100, 101, 99, 100, 1000, 500]]
    context = structure.build_context(rows, [], 1.0, [], close, symbol='AUDIT')
    assert context is not None and context.cut_ms == close
