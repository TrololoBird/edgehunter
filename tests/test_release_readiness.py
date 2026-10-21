"""Regression cases reproduced during the October 2026 analytics audit; no network calls."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

import numpy as np
import pytest

from strategies import classic, geometry, ind_panel, maniac, pump

M = 60_000
Q = 15 * M
D = 1440 * M
T = 100 * D


def mirror(rows):
    return [[t, 200 - o, 200 - lo, 200 - hi, 200 - c, *rest]
            for t, o, hi, lo, c, *rest in rows]


def test_panel_rsi_matches_wilder_at_every_close():
    closes = 100 + np.cumsum(np.random.default_rng(42).normal(size=80))
    rows = np.array([[i * Q, c, c + 1, c - 1, c, 100, 50, 10] for i, c in enumerate(closes)])
    got = ind_panel.indicators(rows)['rsi']
    assert np.isnan(got[:14]).all()
    for n in range(15, len(closes) + 1):
        assert got[n - 1] == pytest.approx(classic.rsi(closes[:n], 14))


def test_panel_excludes_unclosed_rest_history(monkeypatch):
    import fetcher
    seen = {}

    def capture(rows, direction, key):
        seen[key[1]] = rows
        return {}

    monkeypatch.setattr(ind_panel, 'panel', capture)
    monkeypatch.setattr(fetcher, '_RESAMPLE_CACHE', {})
    md = SimpleNamespace(symbol='AUDIT', minute_klines=[],
                         m15_long=[[t, 100, 101, 99, 100, 1] for t in (0, Q)],
                         h1_long=[[t, 100, 101, 99, 100, 1] for t in (0, 4 * Q)])
    fetcher.DataFetcher.indicator_panel(md, 1, Q)
    assert [r[0] for r in seen['15m']] == [0]
    assert seen['1h'] == []


def test_oi_ignores_future_and_stale_samples():
    from fetcher import _pct_change
    from strategies.confirm import oi_change
    past = deque([(T - 10 * M, 100), (T - 5 * M, 110)])
    future = deque([*past, (T, 300)])
    assert _pct_change(past, T - 5 * M, 5 * M) == pytest.approx(0.1)
    assert _pct_change(future, T - 5 * M, 5 * M) == _pct_change(past, T - 5 * M, 5 * M)
    assert _pct_change(past, T, 5 * M) is None
    assert oi_change([(T - 60 * M, 100), (T - 30 * M, 120)], T - 60 * M, T) is None
    assert oi_change([(T - 60 * M, 100), (T, 120)], T - 60 * M, T) == pytest.approx(0.2)


def test_derivatives_reject_future_cache_weights_and_funding():
    from fetcher import DataFetcher, VenueDeriv
    state = VenueDeriv(oi_usd=1000, oi_ts=T + M, funding_8h=0.001, funding_ts=T + M,
                       samples=deque([(T - 60 * M, 100), (T, 120)]))
    # Only positioning state is needed; no exchange clients or live connections.
    f = DataFetcher.__new__(DataFetcher)
    f.venue_derivs = {'AUDIT': {'venue': state}}
    f._deriv_cache = {'AUDIT': (T + M, {'future_cache': True})}
    out = f.deriv_snapshot('AUDIT', T)
    assert out['agg_oi_change_1h'] is None and out['agg_funding_8h'] is None and out['oi_venues'] == 0
    state.oi_ts = state.funding_ts = T
    f._deriv_cache.clear()
    out = f.deriv_snapshot('AUDIT', T)
    assert out['agg_oi_change_1h'] == pytest.approx(0.2)
    assert out['agg_funding_8h'] == 0.001 and out['oi_venues'] == 1


@pytest.mark.parametrize('direction', [1, -1])
@pytest.mark.parametrize('kind', ['va', 'auction'])
def test_profile_requires_complete_session_periods(monkeypatch, direction, kind):
    previous = [[T - D + i * Q, 100, 111, 89, 100, 1000] for i in range(6)]
    if kind == 'va':
        rows = [[T + i * Q, 80 if i < 2 else 100, 101, 79, 80 if i < 2 else 100, 1000]
                for i in range(6)]
        detector, original_direction = classic.session_va_event, 1
    else:
        rows = [[T + i * Q, 100, 120 if i == 5 else 101, 99, 100, 1000] for i in range(6)]
        detector, original_direction = classic.failed_auction_event, -1
    if direction != original_direction:
        previous, rows = mirror(previous), mirror(rows)
    monkeypatch.setattr(classic, 'orb_sessions', lambda *a: [('London', T, T + 8 * Q)])
    monkeypatch.setattr(classic, 'previous_session', lambda *a: (T - D, T - D + 6 * Q))
    found = detector('BTC', previous + rows, T + 6 * Q)
    assert found is not None and found['direction'] == direction and found['event_ts'] == T + 6 * Q
    for indices in ((0, 3, 4, 5), (0, 0, 2, 3, 4, 5)):
        assert detector('BTC', previous + [rows[i] for i in indices], T + 6 * Q) is None
    monkeypatch.setattr(classic, 'orb_sessions', lambda *a: [('London', T, T + 6 * Q)])
    assert detector('BTC', previous + rows, T + 6 * Q) is None


@pytest.mark.parametrize('direction', [1, -1])
def test_ifvg_does_not_form_across_a_missing_candle(direction):
    step = 5 * M
    rows = [[i * step, 100, 101, 99, 100, 1000] for i in range(12)]
    rows[2] = [2 * step, 111, 112, 110, 111, 1000]
    rows[3] = [3 * step, 110, 111, 104, 105, 1000]
    rows[4] = [4 * step, 105, 106, 104, 105, 1000]
    rows[5] = [5 * step, 106, 113, 105, 112, 1000]
    if direction < 0:
        rows = mirror(rows)
    assert maniac.ifvg_trigger(rows, direction, 3 * step, 0, step) is not None
    gapped = [[r[0] + (step if i >= 3 else 0), *r[1:]] for i, r in enumerate(rows)]
    assert maniac.ifvg_trigger(gapped, direction, gapped[3][0], 0, step) is None


@pytest.mark.parametrize('count,volume,expected', [(20, 1000, False), (21, 195, False), (21, 200, True)])
def test_pump_top_requires_twenty_baseline_volumes(monkeypatch, count, volume, expected):
    rows = [[i * Q, 110, 112, 100, 110, 100] for i in range(count - 1)]
    rows.append([(count - 1) * Q, 110, 140, 100, 110, volume])
    monkeypatch.setattr(pump, 'resample', lambda *a: rows)
    assert (pump.pump_top([], {}, count * Q) is not None) == expected


@pytest.mark.parametrize('direction', [1, -1])
def test_sweep_rejects_zero_volume_baseline(monkeypatch, direction):
    import pierce
    from strategies.level import sweep_at_close
    monkeypatch.setattr(pierce, 'overshoot', lambda *a: None)
    rows = [[i * Q, 100, 101, 99, 100, 100] for i in range(20)]
    rows.append([20 * Q, 100, 101, 99.5, 100.5, 1000])
    if direction < 0:
        rows = mirror(rows)
    pools = [(100, -direction, '1h swing', 0)]
    assert sweep_at_close(rows, pools, 1, 0)['direction'] == direction
    for row in rows[:-1]:
        row[5] = 0
    assert sweep_at_close(rows, pools, 1, 0) is None


@pytest.mark.parametrize('direction', [1, -1])
@pytest.mark.parametrize('field,bad', [('stop', float('nan')), ('stop', 0), ('stop', 'bad'),
                                     ('tp1_price', float('inf')), ('tp1_price', 0), ('tp1_price', 'bad')])
def test_trailing_geometry_rejects_invalid_prices(direction, field, bad):
    plan = {'strategy': 'orb', 'tf': '15m', 'atr': 1.0, 'zones': [], 'min_rr': 0.0,
            'exit': {'stop': ['price', 100 - direction * 2], 'tp': ['trail']}}
    assert geometry.system_levels(plan, 100, None, direction) is not None
    if field == 'stop':
        plan['exit']['stop'][1] = bad
    else:
        plan['exit'][field] = bad
    assert geometry.system_levels(plan, 100, None, direction) is None


@pytest.mark.parametrize('direction', [1, -1])
def test_trailing_partial_target_and_turtle_stop_distance(direction):
    plan = {'strategy': 'breakout', 'tf': '1d', 'atr': 1.0, 'zones': [], 'min_rr': 0.0,
            'exit': {'stop': ['price', 100 - direction * 2], 'tp': ['trail'], 'stop_n': 4}}
    out = geometry.system_levels(plan, 100, None, direction)
    assert out['sl'] == 100 - direction * 4 and out['rr_tp1'] is None
    plan['exit']['tp1_price'] = 100 + direction * 8
    out = geometry.system_levels(plan, 100, None, direction)
    assert out['tp1'] == 100 + direction * 8 and np.isfinite(out['rr_tp1'])
    plan['exit']['tp1_price'] = 100 - direction * 8
    assert geometry.system_levels(plan, 100, None, direction) is None


def test_atomic_write_failure_preserves_old_file(tmp_path, monkeypatch):
    import storage
    path = tmp_path / 'state.json'
    path.write_bytes(b'old')

    def fail_replace(*args):
        raise OSError('injected replace failure')

    monkeypatch.setattr(storage.os, 'replace', fail_replace)
    with pytest.raises(OSError, match='injected'):
        storage.atomic_write(path, b'new')
    assert path.read_bytes() == b'old'
    assert sorted(p.name for p in tmp_path.iterdir()) == ['state.json']


def test_atomic_writers_use_separate_temporary_files(tmp_path, monkeypatch):
    import storage
    path = tmp_path / 'state.json'
    path.write_bytes(b'old')
    replace, barrier = storage.os.replace, Barrier(2)

    def simultaneous_replace(src, dst):
        barrier.wait(timeout=10)
        return replace(src, dst)

    monkeypatch.setattr(storage.os, 'replace', simultaneous_replace)
    payloads = [b'a' * 4096, b'b' * 4096]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda data: storage.atomic_write(path, data), payloads))
    assert path.read_bytes() in payloads
    assert sorted(p.name for p in tmp_path.iterdir()) == ['state.json']
