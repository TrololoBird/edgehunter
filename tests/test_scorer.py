import polars as pl

from conftest import CUR15, N, frame
from indicators import TIER0_COLUMNS, TIMEFRAME_MS, compute_indicators, compute_indicators_batch
from scorer import PhaseScorer, score_all_symbols, score_closed, signals_from_rows

sc = PhaseScorer()


def last(raw, funding=0.0001, tier0=None):
    ind = compute_indicators(raw, funding, funding)
    return sc.calculate_scores(ind, ind, tier0).row(-1, named=True)


BASE = [100 + 0.3 * ((i % 4) - 1.5) for i in range(N - 1)]
LOWS = [c - 0.2 for c in BASE]
PRIOR_LOW = min(LOWS[-20:])
B_CLOSE = PRIOR_LOW + 0.35
RAW_B = frame(BASE + [B_CLOSE], open_=BASE + [PRIOR_LOW + 0.3], high=[c + 0.2 for c in BASE] + [B_CLOSE + 0.01],
              low=LOWS + [PRIOR_LOW - 0.5], qv=[1e5] * (N - 1) + [3e5], delta=[0.0] * (N - 1) + [-6e4])


def test_spring_alone_alerts_and_carries_range(monkeypatch):
    # the legacy 15m B / C scores (off in the deployment, replaced by strategies/wyckoff_range.py)
    import dataclasses
    import config as config_mod
    monkeypatch.setattr(sc, 'cfg', dataclasses.replace(config_mod.CONFIG.metrics, legacy_wyckoff_bc=True))
    rb = last(RAW_B)
    assert rb['phase_b_active'] and rb['total_long_score'] >= 3
    sig = sc.signal_from_row(rb)
    assert sig['is_structured'] and sig['alert_type'] == 'LONG'
    assert sig['prior_range_high'] > sig['prior_low'] and sig['candle_minute_usd'] == 3e5 / 15


def test_spring_rejected_in_downtrend_or_deep_break():
    down = [130 - 0.3 * i for i in range(N - 1)]
    d_low = [c - 0.2 for c in down]
    pl_ = min(d_low[-20:])
    d_close = pl_ + 0.3
    raw_down = frame(down + [d_close], open_=down + [pl_ + 0.25], high=[c + 0.2 for c in down] + [d_close + 0.01],
                     low=d_low + [pl_ - 0.5], delta=[0.0] * (N - 1) + [-6e4])
    assert not last(raw_down)['phase_b_active']
    assert not last(RAW_B.with_columns(pl.Series('low', LOWS + [PRIOR_LOW - 5.0])))['phase_b_active']


def test_accumulation_is_absorbed_selling():
    tight = [100 + 0.05 * ((i % 2) - 0.5) for i in range(N)]
    ra = last(frame(tight, delta=[0.0] * (N - 10) + [-3e4] * 10,
                    oi=[1e6] * (N - 12) + [1e6 * (1 + 0.003 * i) for i in range(12)]))
    assert ra['score_phase_a'] == 4 and ra['phase_a_active']
    assert last(frame(tight, delta=[0.0] * (N - 10) + [3e4] * 10))['score_phase_a'] <= 1


def test_distribution_funding_and_spot_points(monkeypatch):
    # the legacy 15m B / C scores (off in the deployment, replaced by strategies/wyckoff_range.py)
    import dataclasses
    import config as config_mod
    monkeypatch.setattr(sc, 'cfg', dataclasses.replace(config_mod.CONFIG.metrics, legacy_wyckoff_bc=True))
    up = [100 + 0.1 * i for i in range(N)]
    kwargs = dict(delta=[5e3] * 70 + [-8e3] * 29, oi=[1e6 * (1 + 0.001 * i) for i in range(N)])
    rc = last(frame(up, **kwargs), funding=0.0001)
    # divergence (2) + spot selling at the high (1: the single test frame is both spot and perp)
    assert rc['phase_c_active'] and rc['score_phase_c'] == 3
    assert last(frame(up, **kwargs), funding=0.0015)['score_phase_c'] == 5


def test_breakdown_needs_oi_rise():
    wave = [100 * (1 + 0.01 * ((i % 8) - 4) / 4) for i in range(N)]
    close_d = wave[:N - 1] + [94.0]
    small = last(frame(close_d, delta=[0.0] * (N - 1) + [-4e4], oi=[1e6] * (N - 1) + [1.002e6]))
    big = last(frame(close_d, delta=[0.0] * (N - 1) + [-4e4], oi=[1e6] * (N - 1) + [1.02e6]))
    assert not small['phase_d_active'] and big['phase_d_active']


def _capitulation():
    decl = [100 - 0.4 * i for i in range(N - 1)]
    cap = decl[-1] - 1.0
    return frame(decl + [cap], open_=decl + [decl[-1]], high=[c + 0.1 for c in decl] + [decl[-1] + 0.05],
                 low=[c - 0.1 for c in decl] + [cap - 3.0], qv=[1e5] * (N - 1) + [6e5], delta=[0.0] * (N - 1) + [-1e5],
                 oi=[1e6] * (N - 1) + [0.95e6])


def test_capitulation_decline_and_liquidation_bonus():
    raw_e = _capitulation()
    plain = last(raw_e, funding=-0.002)
    liq = last(raw_e, funding=-0.002, tier0={'liq_long_5m': 2e5, 'avg_minute_usd': 5e4})
    assert plain['phase_e_active'] and liq['liq_cascade'] and liq['score_phase_e'] == plain['score_phase_e'] + 1
    flat_decl = [100 - 0.001 * i for i in range(N - 1)]
    assert not last(raw_e.with_columns(pl.Series('close', flat_decl + [flat_decl[-1] - 0.01])), funding=-0.002)['phase_e_active']


def test_tie_is_not_a_signal():
    assert sc.signal_from_row({'total_long_score': 3, 'total_short_score': 3, 'is_tier_0_anomaly': False}) is None


def test_spot_vs_perp_and_asof_join():
    up = [100 + 0.1 * i for i in range(N)]
    spot = frame(up, delta=[-2e4] * N)
    fut = frame(up[:N - 1], delta=[3e4] * (N - 1), oi=[1e6 * (1 + 0.001 * i) for i in range(N - 1)])
    s_all = compute_indicators_batch({'S': spot}, {'S': (0.0012, 0.0012)})
    f_all = compute_indicators_batch({'S': fut, 'F': fut}, {'S': (0.0012, 0.0012), 'F': (0.0, 0.0)})
    scored = sc.calculate_scores(s_all, f_all, None)
    row = scored.filter(pl.col('symbol') == 'S').row(-1, named=True)
    # spot one bucket ahead of futures: OI / RVOL still joined (as-of), funding kept
    assert row['oi_change_pct'] is not None and row['rvol'] is not None and row['predicted_funding'] == 0.0012
    assert row['has_spot'] and row['spot_delta_1h'] < 0 < row['perp_delta_1h'] and row['perp_led_long']
    frow = scored.filter(pl.col('symbol') == 'F').row(-1, named=True)
    assert not frow['has_spot'] and not frow['perp_led_long']   # futures-only: no spot, no veto


def test_aggregate_perp_flow_used_when_ready():
    up = [100 + 0.1 * i for i in range(N)]
    raw = frame(up, delta=[1e4] * N)
    ind = compute_indicators_batch({'S': raw}, {'S': (0.0, 0.0)})
    extras = pl.DataFrame({'symbol': ['S'], 'agg_fut_delta_1h': [1e6], 'agg_spot_extra_1h': [0.0], 'agg_ready': [1.0]})
    row = sc.calculate_scores(ind, ind, None, extras).row(-1, named=True)
    assert row['perp_delta_1h'] == 1e6 and row['perp_led_long']      # spot 40k vs perp 1M: perp-led


def test_scores_come_from_closed_candle_only():
    up = [100 + 0.1 * i for i in range(N)]
    all_ = compute_indicators_batch({'S': frame(up)}, {'S': (0.0, 0.0)})
    rows = score_closed(all_, all_, {}, {'S': CUR15 - TIMEFRAME_MS})
    assert rows['S']['timestamp'] == CUR15 - TIMEFRAME_MS
    assert score_all_symbols(all_, all_, {}) == []  # convenience path runs (no setup on a flat, delta-free trend)


def _t0(**values):
    base = {c: 0.0 for c in TIER0_COLUMNS}
    base['sec_into_quarter'] = 300.0
    base.update(values)
    return base


def test_tier0_flags(monkeypatch):
    # the formulas of every rule at the thresholds the rows were built for (the deployment flags with fewer rules
    # at measured thresholds: research/tier0_thresholds.md)
    import dataclasses
    import config as config_mod
    monkeypatch.setattr(config_mod.CONFIG, 'tier0', dataclasses.replace(
        config_mod.CONFIG.tier0, price_z_threshold=4.0, oi_z_threshold=4.0,
        flag_rules=('rvol', 'price', 'oi', 'whales', 'cluster', 'liq', 'venue')))
    monkeypatch.setattr(config_mod.CONFIG, 'liquidations', dataclasses.replace(
        config_mod.CONFIG.liquidations, cascade_min_usd=50_000))
    t = config_mod.CONFIG.tier0
    rows = {
        'rvol_small_minute': _t0(rvol_1m=6.0, minute_usd=10_000.0),
        'rvol_ok': _t0(rvol_1m=6.0, minute_usd=30_000.0),
        'rvol_quarter_boundary': _t0(rvol_1m=6.0, minute_usd=30_000.0, sec_into_quarter=10.0),
        'price_low_z': _t0(price_change_5m=0.015, price_z=2.0),
        'price_high_z': _t0(price_change_5m=0.015, price_z=5.0),
        'price_unknown_vol_big': _t0(price_change_5m=0.025),
        'oi_high_z': _t0(oi_change_5m=0.01, oi_z=5.0),
        'cascade': _t0(liq_long_5m=80_000.0, avg_minute_usd=50_000.0),
        'cascade_thin': _t0(liq_long_5m=80_000.0, avg_minute_usd=500_000.0),
        'one_venue': _t0(venues_active=3.0, top_venue_share=0.9, top_venue_net=400_000.0),
        'algo': _t0(cluster=1.0),
    }
    frame_ = pl.DataFrame([dict(symbol=k, **v) for k, v in rows.items()])
    flags = dict(zip(frame_['symbol'], sc.flag_tier_0_anomaly(frame_)['is_tier_0_anomaly']))
    assert flags == {'rvol_small_minute': False, 'rvol_ok': True, 'rvol_quarter_boundary': False,
                     'price_low_z': False, 'price_high_z': True, 'price_unknown_vol_big': True, 'oi_high_z': True,
                     'cascade': True, 'cascade_thin': False, 'one_venue': True, 'algo': True}
    assert t.rvol_1m_threshold == 5.0


def test_light_pass_joins_cached_rows_with_live_tier0():
    up = [100 + 0.1 * i for i in range(N)]
    all_ = compute_indicators_batch({'S': frame(up)}, {'S': (0.0, 0.0)})
    rows = score_closed(all_, all_, {}, {'S': CUR15})
    sigs = signals_from_rows(rows, {'S': _t0(price_change_5m=0.05), 'X': _t0(price_change_5m=0.05)})
    got = {s: sig['is_tier_0_anomaly'] for s, sig in sigs}
    assert got == {'S': True, 'X': True}   # X has no candle history but still gets the Tier-0 check
