"""Fixes of the external audit of 2026-10-18 (see backup/*.pre-audit for the code before)."""
from strategies import geometry
from strategies.leg import _to_4h
from zones import RawLevel, equal_pools, merge


def test_exit_target_remeasures_final_targets(monkeypatch):
    # _finish stored targets already pulled by the pierce: 'map' must not read them as levels again
    seen = {}

    def fake_select(zones, ref, direction, atr, intent, *a, **k):
        seen['called'] = True
        return [110.0], ['1h swing']
    monkeypatch.setattr(geometry, 'select_targets', fake_select)
    plan = {'targets': [109.5], 'target_src': ['1h swing'], 'targets_final': True, 'zones': [], 'tf': '1h', 'atr': 1.0}
    t, s, low = geometry.exit_target({'tp': ['map', 1.0]}, plan, 100.0, 2.0, 1)
    assert seen.get('called') and t == 110.0 and not low


def test_to_4h_groups_hours():
    h = 3_600_000
    h1 = [[i * h, 10 + i, 12 + i, 9 + i, 11 + i, 1.0] for i in range(8)]
    bars = _to_4h(h1)
    assert len(bars) == 2
    assert bars[0] == [0, 10, 15, 9, 14, 4.0]


def test_equal_pool_wick_beyond_edge_is_swept():
    lv = [RawLevel(100.0, 'swing_15m', 'h', +1, ts=1), RawLevel(100.02, 'swing_15m', 'h', +1, ts=2)]
    candles = [[t, 99, 99.5, 98, 99, 1] for t in range(3, 20)]
    assert equal_pools(lv, candles, 1.0)                         # untouched: a pool
    candles[-1] = [19, 99, 100.05, 98, 99, 1]                    # a wick just beyond the edge, back below
    assert not equal_pools(lv, candles, 1.0)


def test_merge_level_inside_the_zone_joins_it():
    lv = [RawLevel(100.0, 'round', 'r', 0),
          RawLevel(101.0, 'swing_1h', 's', +1, body=100.0),
          RawLevel(100.8, 'round', 'r2', 0)]
    zones = merge(lv, atr=5.0)
    assert len(zones) == 1 and zones[0].lo == 100.0 and zones[0].hi == 101.0


def test_expectancy_counts_each_third(monkeypatch):
    # TP1 often, TP2 / TP3 rarely, the stop stays after TP1: p1 x R1 alone looked positive, the thirds are not
    monkeypatch.setitem(geometry.HIT_RATE, 'TEST SETUP', (0.5, 40, 0.5, 0.1, 0.05))
    plan = {'setup': 'ENTRY TEST SETUP', 'symbol': None, 'tf': '15m', 'zones': [], 'min_rr': 0.0}
    out = geometry.finish_levels(plan, 100.0, 99.0, [101.5, 103.0, 104.0], ['1h swing'] * 3, 1, 'x')
    assert out['low_rr'] and out['rr_reason'].startswith('expectancy')
    monkeypatch.setitem(geometry.HIT_RATE, 'TEST SETUP', (0.6, 40, 0.6, 0.5, 0.4))
    out = geometry.finish_levels(plan, 100.0, 99.0, [101.5, 103.0, 104.0], ['1h swing'] * 3, 1, 'x')
    assert not (out['rr_reason'] or '').startswith('expectancy')


def test_entry_outcome_relabelled_over_trade_life(tmp_path, monkeypatch):
    # audit #21: a long trade 'OPEN' at 8h is relabelled once its 72h window closed (paged 1m klines)
    import asyncio
    import time
    from config import CONFIG
    from journal import SignalJournal
    j = SignalJournal(str(tmp_path / 'j.db'))
    ts = int((time.time() - 80 * 3600) * 1000) // 60_000 * 60_000 - 30_000
    j.conn.execute("INSERT INTO signals (group_key, ts_ms, symbol, kind, price, direction, entry, sl, tp1, tp2, tp3, outcome, "
                   "eval_failed, ret_8h) VALUES ('ENTRY T', ?, 'X/USDT:USDT', 'entry', 100, 1, 100, 98, 104, 106, 108, 'OPEN', 0, 0)",
                   (ts,))
    j.conn.commit()
    t0 = ts + 30_000
    hours = CONFIG.journal.outcome_life_h
    # flat for 20h (8h said OPEN), then a run through all three targets
    bars = [[t0 + i * 60_000, 100, 100.5, 99.5, 100, 1] for i in range(20 * 60)]
    bars += [[t0 + i * 60_000, 100, 109, 99.5, 108.5, 1] for i in range(20 * 60, hours * 60)]
    calls = []

    class F:
        async def fetch_minute_klines(self, symbol, start_ms, count):
            calls.append(count)
            first = -(-start_ms // 60_000) * 60_000
            k = (first - t0) // 60_000
            return bars[k:k + count]
    asyncio.run(j._evaluate_life_pass(F()))
    outcome, h = j.conn.execute("SELECT outcome, outcome_h FROM signals").fetchone()
    assert outcome == 'TP3' and h == hours and len(calls) == -(-hours * 60 // 1500)
    assert not j._pending_life(10)


def test_prefix_parsers_use_split_base():
    from event_risk import EventRisk
    from pretrain import _spot_pair
    assert EventRisk._base('10000WEN/USDT:USDT') == 'WEN'
    assert EventRisk._base('1000000MOG/USDT:USDT') == 'MOG'
    assert _spot_pair('10000WEN', {'WENUSDT'}) == 'WENUSDT'
    assert _spot_pair('1000PEPE', {'PEPEUSDT'}) == 'PEPEUSDT'
    assert _spot_pair('BTC', {'BTCUSDT'}) == 'BTCUSDT'


def test_unverified_venue_print_skipped_without_binance_price():
    from symbols import SymbolMap, VenueMarket
    m = SymbolMap.__new__(SymbolMap)
    m.dropped, m._verified = set(), set()
    vm = VenueMarket.__new__(VenueMarket)
    vm.verified = False
    assert m.check_price(vm, 1.0, None) is False and not vm.verified


def test_stale_fill_does_not_explain_a_later_pull():
    from depth import ATTRIBUTION_MS, DepthBook
    d = DepthBook.__new__(DepthBook)
    book = type('B', (), {})()
    book.synced, book.unexplained, book.executed = True, {}, {}
    d.books = {'X': book}
    d.on_trade('X', 1_000, 100.0, 10.0, -1)
    d.on_trade('X', 1_000 + ATTRIBUTION_MS + 1, 100.0, 0.01, -1)
    assert book.executed[(1, 100.0)][0] == 0.01


def test_every_futures_venue_keeps_the_hour():
    from config import CONFIG
    from flow import FUTURES_VENUES, FlowStore
    fs = FlowStore(capacity=4)
    assert all(fs.venues[v].H == CONFIG.venues.flow_history_sec for v in FUTURES_VENUES)


def test_success_accuracy_restarts_at_drift_reset():
    from ml import SuccessModel
    m = SuccessModel()
    m.load_pretrained({'model': m.model, 'n': 400_000, 'correct': 300_000})
    assert m.accuracy is None                    # not the archive's 75%
    m.learn({}, True)
    m.learn({}, True)
    assert m.seen == 2 and m.accuracy in (0.0, 0.5, 1.0)


# ------------------------------------------------------------------ third audit (formulas / failures, eng-141d)

def test_rolling_std_is_stable_at_large_prices():
    import numpy as np
    from strategies.ind_panel import rolling_std
    rng = np.random.default_rng(1)
    x = 1e8 + rng.normal(0, 0.001, 300)
    got = rolling_std(x, 20)[19:]
    ref = np.array([x[i - 19:i + 1].std() for i in range(19, 300)])
    assert np.allclose(got, ref, rtol=1e-6) and (got > 0).all()


def test_unitless_indicators_do_not_depend_on_the_price_unit():
    import numpy as np
    from strategies.ind_panel import indicators
    rng = np.random.default_rng(2)
    c = 100 + np.cumsum(rng.normal(0, 1, 300))
    k = np.column_stack([np.arange(300) * 3.6e6, c, c + 1, c - 1, c, np.full(300, 1e6), np.full(300, 5e5),
                         np.full(300, 1e4)])
    a, b = indicators(k), indicators(k * np.array([1, 1e-15, 1e-15, 1e-15, 1e-15, 1, 1, 1]))
    for f in ('stoch_k', 'pctb', 'cci'):
        assert np.allclose(np.nan_to_num(a[f][-50:]), np.nan_to_num(b[f][-50:]), rtol=1e-6), f


def test_obv_rule_unknown_without_base_volume():
    import numpy as np
    from strategies.ind_panel import panel
    rng = np.random.default_rng(3)
    c = 100 + np.cumsum(rng.normal(0, 1, 300))
    rows = [[i * 3.6e6, x, x + 1, x - 1, x, 1e6, 5e5] for i, x in enumerate(c)]     # no base volume column
    assert panel(rows, 1)['obv_slope'] is None and panel(rows, -1)['obv_slope'] is None


def test_panel_cache_sees_a_revised_candle():
    import numpy as np
    from strategies.ind_panel import panel
    rng = np.random.default_rng(4)
    c = 100 + np.cumsum(rng.normal(0, 1, 300))
    rows = [[i * 3.6e6, x, x + 1, x - 1, x, 1e6, 5e5, 1e4] for i, x in enumerate(c)]
    first = panel(rows, 1, key=('T', '1h'))
    rows[-1] = [rows[-1][0], c[-1], 9000.0, c[-1] - 1, 8999.0, 1e6, 5e5, 1e4]
    assert panel(rows, 1, key=('T', '1h')) != first


def test_htf_builders_reject_a_repeated_hour():
    from strategies.structure import bars_4h
    from zones import bars_of
    H = 3_600_000
    h1 = [[t * H, 1, 2, 0.5, 1.5, 10, 5, 1] for t in (0, 0, 2, 3)]
    assert bars_of(h1, 4) == []
    assert bars_4h(h1, 10 * H) == []


def test_risk_limits_unreadable_block_new_risk(tmp_path, monkeypatch):
    import dataclasses
    from types import SimpleNamespace
    import executor
    from config import CONFIG
    monkeypatch.setattr(executor, 'CONFIG', SimpleNamespace(executor=dataclasses.replace(CONFIG.executor, daily_loss_r=3.0)))
    ex = executor.DemoExecutor.__new__(executor.DemoExecutor)
    ex.db_path, ex.pending = str(tmp_path / 'missing_dir' / 'x.db'), {}
    assert (ex.risk_limit() or '').startswith('risk limits unreadable')


def test_bybit_oi_one_convention():
    from types import SimpleNamespace
    from venues import BybitStream
    got = {}

    class Sink:
        def on_deriv(self, market, **kw):
            got.update(kw)
    s = BybitStream.__new__(BybitStream)
    s._tickers, s.sink = {}, Sink()
    s.symbols = SimpleNamespace(lookup=lambda venue, native: SimpleNamespace(key='X/USDT:USDT'))
    s.handle({'topic': 'tickers.XUSDT', 'ts': 1, 'data': {'singleOpenInterest': '10', 'openInterest': '20',
              'singleOpenInterestValue': '1000', 'openInterestValue': '2000'}}, 0.0)
    assert got['oi_usd'] == 1000.0 and got['native_oi'] == 10.0


def test_one_atr_everywhere():
    # owner 2026-10-18: Wilder's ATR14 in the geometry, the detectors and the panel - the same number on the same candles
    import numpy as np
    from levels import atr_of
    from strategies.ind_panel import rma
    from strategies.maniac import true_range, wilder
    from sr import _atr as sr_atr
    from pumps import _atr as pump_atr
    rng = np.random.default_rng(5)
    c = 100 + np.cumsum(rng.normal(0, 1, 120))
    rows = [[i * 3.6e6, x, x + abs(rng.normal(0, 1)), x - abs(rng.normal(0, 1)), x + rng.normal(0, 0.3), 1.0]
            for i, x in enumerate(c)]
    h, l, cl = (np.array([r[k] for r in rows]) for k in (2, 3, 4))
    prev = cl[:-1]
    tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - prev), abs(l[1:] - prev)))
    ref = rma(tr, 14)[-1]
    assert abs(atr_of(rows) - ref) < 1e-9
    assert abs(sr_atr(h, l, cl)[-1] - ref) < 1e-9
    assert abs(pump_atr(rows, len(rows) - 1) - ref) < 1e-9
    assert abs(wilder(true_range(h, l, cl)[1:], 14)[-1] - ref) < 1e-9
