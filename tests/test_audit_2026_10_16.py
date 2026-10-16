"""Regression checks for the 2026-10-16 strategy audit: each counterexample of the audit, reproduced on the fixed code."""
import asyncio
import sqlite3
from types import SimpleNamespace

import numpy as np
import pytest

H = 3_600_000
DAY = 86_400_000


# ---------------------------------------------------------------------- formulas (C02, C03, C04, sigma, SAR, N35)

def test_vwap_weights_by_base_volume():
    from zones import vwap
    # one coin at 100 and one at 200: quote volumes 100 / 200 -> the VWAP is 150 (was 166.67)
    candles = [[0, 100, 100, 100, 100, 100.0], [60_000, 200, 200, 200, 200, 200.0]]
    assert vwap(candles, 0, 'x')[0].price == pytest.approx(150.0)


def test_tpo_counts_one_mark_per_visited_row():
    from strategies.classic import value_area
    # one bracket over all ten rows, two later brackets on the bottom row only: the bottom row has 3 marks, the rest 1
    bars = [[0, 0, 10, 0, 5, 100], [1_800_000, 0.2, 0.8, 0, 0.4, 100], [3_600_000, 0.2, 0.8, 0, 0.4, 100]]
    val, poc, vah = value_area(bars, tpo=True, buckets=10)
    assert poc == pytest.approx(0.5)
    assert vah - val > 5           # the 70% area spans most rows (was squeezed into the bottom row)


def test_resample_drops_gapped_and_duplicated_minutes():
    from levels import resample
    gapped = [[0, 100, 101, 99, 100, 10, 5], [240_000, 100, 102, 99, 101, 10, 5]]
    assert resample(gapped, 5, 300_000) == []                    # 2 of 5 minutes: no closed 5m candle
    full = [[k * 60_000, 100, 101, 99, 100, 10, 5] for k in range(5)]
    dup = full[:3] + [full[2]] + full[3:]
    bars = resample(dup, 5, 300_000)
    assert len(bars) == 1 and bars[0][5] == 50                   # the repeated minute counted once


def test_bollinger_uses_population_sigma():
    from strategies.maniac import rolling_std
    x = np.arange(20, dtype=float)
    assert rolling_std(x, 20)[-1] == pytest.approx(np.std(x, ddof=0))


def test_sar_never_inside_the_previous_bar():
    from strategies.maniac import parabolic_sar_step
    nxt, _, _, stopped = parabolic_sar_step(93, 120, 0.04, 1, 121, 96, prev_lo=94)
    assert not stopped and nxt == pytest.approx(94)               # was 94.68, inside the previous bar's range


def test_mfi_money_flow_is_the_quote_volume():
    from strategies.ind_panel import indicators
    # one coin a bar, typical price alternating 100 / 200: the quote volume is 100 / 200, MFI over 14 changes = 66.67
    rows = []
    for i in range(30):
        p = 100.0 if i % 2 == 0 else 200.0
        rows.append([i * 60_000, p, p, p, p, p])
    mfi = indicators(np.asarray(rows))['mfi'][-1]
    assert mfi == pytest.approx(100 * 200 * 7 / (200 * 7 + 100 * 7), rel=1e-6)


# ---------------------------------------------------------------------- execution (N01, N13, N14)

def test_recovered_exit_is_not_cut_by_the_next_entry_margin():
    from executor import DemoExecutor
    fills = [{'side': 'sell', 'price': 101.0, 'amount': 1.0, 'timestamp': 99_000, 'order': 'exit1'},
             {'side': 'buy', 'price': 102.0, 'amount': 1.0, 'timestamp': 109_000, 'order': 'entry2'}]
    cutoff = DemoExecutor._next_entry_cutoff(fills, (110_000, 'entry2'))
    exits = DemoExecutor._exit_fills(fills, 'sell', 50_000, 100_000, cutoff)
    assert [f['order'] for f in exits] == ['exit1']                # was dropped (cutoff 95 000)


def test_realized_r_uses_the_exit_fill_not_the_mark():
    from signal_book import SignalBook, TrackedSignal
    s = TrackedSignal('T/USDT:USDT', 'X', 1, 'breakout', 1, 100, {}, entered_at=1, last_price=105,
                      levels={'entry': 100, 'sl': 90, 'tp1': 200, 'tp2': 300, 'tp3': 400, 'risk0': 10},
                      units=[[100, 1], [105, 2]])
    s.exit_fill = 90.0
    r = SignalBook._exit_r(s, 'SL') + SignalBook._cost_r(s, 10, 0) * 2
    assert r == pytest.approx(-2.5)                               # was +0.5 (the scan price 105)


def test_closed_trade_notifies():
    from signal_book import SignalBook, TrackedSignal
    b = SignalBook()
    s = TrackedSignal('T/USDT:USDT', 'X', 1, 'bollinger', 1, 100, {}, entered_at=1, last_price=101,
                      levels={'entry': 100, 'sl': 90, 'tp1': 110, 'tp2': 120, 'tp3': 130})
    b._finish(s, 'CLOSED', 2, 'band')
    assert [e for _, e in b.events] == ['CLOSED']


def test_finish_during_open_is_not_lost():
    from executor import DemoExecutor

    async def run():
        ex = DemoExecutor.__new__(DemoExecutor)
        ex.enabled, ex.open, ex.pending, ex._finished_cards = True, {}, {}, set()
        ex._lock = asyncio.Lock()
        ex.db_path = ':memory:'
        closed = []
        gate = asyncio.Event()

        async def fake_open(card_id, s):
            await gate.wait()
            ex.open[card_id] = {'id': 1, 'card_id': card_id, 'symbol': s.symbol}

        async def fake_close(trade, reason, journal_r, passive=False):
            closed.append(reason)
            ex.open.pop(trade['card_id'], None)
        ex._open, ex._close = fake_open, fake_close
        ex.risk_limit = lambda: None
        ex.strategy_killed = lambda m: None
        ex.is_limit_plan = lambda s: False
        ex._set_exit_ref = lambda *a: None
        s = SimpleNamespace(symbol='T/USDT:USDT', group_key='X', entered_at=5, levels={'entry': 1}, mode='m',
                            direction=1, status='CLOSED', final_r=0.1, finish_price=1.0, created=1)
        entry = asyncio.create_task(ex.on_entry(s))
        await asyncio.sleep(0)
        finish = asyncio.create_task(ex.on_finish(s))
        await asyncio.sleep(0)
        gate.set()
        await asyncio.gather(entry, finish)
        return closed, ex.open
    closed, still_open = asyncio.run(run())
    assert closed == ['CLOSED'] and not still_open               # was: 1 open position, 0 closes


# ---------------------------------------------------------------------- data (N05, N10, N12, N16, N19)

def test_ticker_multipliers():
    from sectors import base_of
    assert [base_of(x) for x in ('1000PEPE/USDT:USDT', '10000WEN/USDT:USDT', '100000TOKEN/USDT:USDT')] == \
        ['PEPE', 'WEN', 'TOKEN']


def test_zero_aggregate_flow_is_kept():
    from journal import perp_flow_5m
    assert perp_flow_5m({'venues_active': 2, 'agg_cvd_5m': 0.0, 'futures_cvd_5m': 100.0}) == 0.0


def test_finished_auction_sides():
    from flow import Footprint
    fp = Footprint.__new__(Footprint)
    levels = {1: [0.0, 50.0], 2: [30.0, 30.0], 3: [40.0, 0.0]}      # [taker buys, taker sells] per bucket
    fp.merged = lambda *a, **k: levels
    assert fp.finished_auction('X', 0, None, +1)                   # zero ASK (buys) at the low
    assert fp.finished_auction('X', 0, None, -1)                   # zero BID (sells) at the high


def test_mixed_journal_batch_keeps_every_column(tmp_path):
    from journal import SignalJournal
    j = SignalJournal.__new__(SignalJournal)
    j.conn = sqlite3.connect(':memory:')
    j.conn.execute("CREATE TABLE signals (kind TEXT, reason TEXT, x REAL)")
    j._insert([{'kind': 'anomaly', 'x': 1.0}, {'kind': 'setup', 'reason': 'r', 'x': 2.0}])
    j._insert([{'kind': 'setup', 'reason': 'r2', 'x': 3.0}, {'kind': 'anomaly', 'x': 4.0}])
    assert j.conn.execute("SELECT kind, reason FROM signals ORDER BY x").fetchall() == \
        [('anomaly', None), ('setup', 'r'), ('setup', 'r2'), ('anomaly', None)]


def test_duplicate_minute_does_not_hide_a_missing_one():
    from fetcher import MarketData
    md = MarketData(symbol='T/USDT:USDT')
    t0 = 1_000 * 900_000
    for k in [0, 1, 2, 3, 4, 5, 6, 6, 8, 9, 10, 11, 12, 13, 14]:       # 7 missing, 6 twice
        md._add_closed_minute('futures', [t0 + k * 60_000, 1, 1, 1, 1, 10.0, 5.0], 1.0)
    assert t0 in md.incomplete['futures']


# ---------------------------------------------------------------------- causality (R05, N15 base rate, N22)

def _dump_path(exhaust_before_touch: bool = True):
    bars = [[i * H, 100.0, 100.5, 99.5, 100.0, 1e6] for i in range(185)]
    bars += [[185 * H, 100, 100.5, 83, 84, 2e7], [186 * H, 84, 84.5, 80, 81, 1e6], [187 * H, 81, 82, 79, 80, 1e6]]
    if exhaust_before_touch:
        bars += [[188 * H, 80, 84, 79.5, 83.5, 1e6], [189 * H, 83.5, 88, 83, 87.5, 1e6],
                 [190 * H, 87.5, 89, 86.5, 88.5, 1e6], [191 * H, 88.5, 89.5, 85, 85.5, 1e6]]
    else:
        # the bounce touches 38.2% BEFORE any exhaustion close: no low is fixed yet, no trade from that touch
        bars += [[188 * H, 80, 88, 79.5, 81.5, 1e6], [189 * H, 81.5, 82, 78, 79, 1e6],
                 [190 * H, 79, 80, 77, 78, 1e6], [191 * H, 78, 78.5, 76, 76.5, 1e6]]
    return bars


def test_dump_bounce_fixes_the_low_at_the_exhaustion():
    from strategies.pump import dump_bounce
    found = dump_bounce(_dump_path(True), 192 * H)
    assert found is not None and found['dump_low'] == 79           # the low known at the exhaustion close (hour 188)
    assert dump_bounce(_dump_path(False), 192 * H) is None          # a touch before the exhaustion is no bounce


def test_research_meta_auc_ties():
    import sys
    sys.path.insert(0, 'research/scripts')
    from research_meta import auc
    assert auc(np.array([0, 1]), np.array([0.5, 0.5])) == pytest.approx(0.5)


def test_optimizer_no_partial_after_the_full_target():
    import sys
    sys.path.insert(0, 'research/scripts')
    import research_optimize as ro
    import inspect
    src = inspect.getsource(ro.simulate)
    assert 'i_half < i_t' in src


# ---------------------------------------------------------------------- methods (C06, C07, Wyckoff, Turtle, TL)

def test_cup_stop_limit_is_not_widened():
    from strategies.geometry import system_levels
    plan = {'exit': {'stop': ['price', 92.0], 'tp': ['level', 130.0, 0.0, None], 'atr': 20.0, 'own_targets': True,
                     'max_loss_pct': 0.08},
            'atr': 20.0, 'tf_atr': 20.0, 'symbol': 'T/USDT:USDT', 'zones': [], 'tf': '1d', 'strategy': 'cup_handle',
            'setup': 'CUP HANDLE'}
    lv = system_levels(plan, 100.0, None, 1)
    assert lv is None or lv['low_rr']                              # 8% would become 20%: rejected


def test_method_min_rr_is_to_tp1():
    from strategies.geometry import finish_levels
    plan = {'symbol': None, 'zones': [], 'min_rr': 3.0, 'setup': 'SD DEMAND', 'tf': '4h', 'atr': 1.0}
    lv = finish_levels(plan, 100.0, 90.0, [111.0, 150.0, 150.0], ['a', 'b', 'c'], 1, 'x')
    assert lv['low_rr'] and 'TP1' in lv['rr_reason']               # blended 3.6 used to pass it


def test_spring_must_close_inside_the_range():
    from strategies import wyckoff_range as wr
    bars = [[i * 4 * H, 100, 101, 99, 100, 10.0] for i in range(30)]
    wr._phase_a = lambda *a, **k: {'lo': 90.0, 'hi': 110.0, 'climax': 5}
    try:
        bars[-1] = [29 * 4 * H, 100, 116, 89, 115, 10.0]             # through the low, closed ABOVE the range
        assert wr.wyckoff_events(bars, 4 * H, '4h') == []
        bars[-1] = [29 * 4 * H, 95, 99, 89, 95, 10.0]                # through the low, closed inside
        assert [e['setup'] for e in wr.wyckoff_events(bars, 4 * H, '4h')] == ['SPRING']
    finally:
        import importlib
        importlib.reload(wr)


def test_unobserved_spring_test_is_not_passed():
    from levels import pullback_spread_ok, pullback_volume_ok
    assert pullback_volume_ok([], 0, 1, 1000.0) is None
    assert pullback_spread_ok([], 0, 1, 1.0, 240) is None


def test_trendline_percent_of_the_line():
    from strategies.maniac import trendline_em_event
    import inspect
    assert 'pct * value(j)' in inspect.getsource(trendline_em_event)


def test_turtle_open_breakout_is_no_winner():
    from strategies.turtle import _last_s1_was_winner, n_series
    d1 = [[i * DAY, 100, 101, 99, 100, 1e6] for i in range(60)]
    d1.append([60 * DAY, 100, 110, 100, 109, 1e6])                  # a 20-day breakout, still open
    assert _last_s1_was_winner(d1, n_series(d1)) is None           # was True (marked at the last close)


def test_funding_by_the_contracts_interval():
    from levels import funding_r
    assert funding_r(0.001, 1, 100, 10, 1 * H, 5 * H) == 0.0                     # 8h grid: no settlement
    assert funding_r(0.001, 1, 100, 10, 1 * H, 5 * H, interval_h=4) == pytest.approx(0.005)  # 4h: 04:00 paid


# ---------------------------------------------------------------------- PR #5 review (V-items that hit this code)

def test_fvg_not_built_across_a_hole():
    from strategies.ict import fvg_setup
    step = 300_000
    bars = [[k * step, 100, 101, 99, 100] for k in range(10)]
    bars[5] = [5 * step, 99, 100.5, 95, 96]                         # the sweep, then a swing high at bar 3
    bars[3] = [3 * step, 100, 102, 99, 101]
    # bar 6 missing (dropped as incomplete): 7 and 8 are no neighbours of 5
    bars = bars[:6] + [[7 * step, 96, 103, 96, 103], [8 * step, 103, 108, 104, 107]]
    assert fvg_setup(bars, 1, 5 * step, step) is None


def test_turtle_stop_is_2n_from_the_entry():
    from strategies.geometry import system_levels
    plan = {'exit': {'stop': ['price', 103.0], 'stop_n': 2.0, 'tp': ['trail'], 'atr': 1.0}, 'atr': 1.0,
            'symbol': None, 'zones': [], 'tf': '1d'}
    assert system_levels(plan, 106.0, None, 1)['sl'] == pytest.approx(104.0)


def test_turtle_entry_day_stop_is_ambiguous():
    from strategies.turtle import _last_s1_was_winner, n_series
    d1 = [[i * DAY, 100, 100.5, 99.5, 100, 1e6] for i in range(40)]
    d1.append([40 * DAY, 100, 101, 95, 100.8, 1e6])                 # breakout and the 2N stop on the same day
    d1 += [[(41 + i) * DAY, 101 + i, 102 + i, 100 + i, 101.5 + i, 1e6] for i in range(15)]   # runs up
    d1.append([56 * DAY, 116, 116, 104, 105, 1e6])                  # out on the 10-day low, far above the entry
    assert _last_s1_was_winner(d1, n_series(d1)) is None


def test_sd_opposing_zone_touched_by_a_wick_is_not_fresh():
    from strategies.maniac import sd_opposing
    zones = [{'side': -1, 'lo': 110.0, 'hi': 120.0, 'confirm': 0}]
    bars = [[0, 100, 100, 100, 100], [1, 100, 101, 99, 100], [2, 105, 115, 104, 105], [3, 103, 104, 102, 103]]
    assert sd_opposing(zones, bars, 1, 100.0) == []


def test_dump_bounce_needs_a_known_rank():
    from strategies.loopside import LoopDetectors
    ld = LoopDetectors(lambda s: [], lambda s: [])
    md = SimpleNamespace(h1=[[i * H, 1, 1, 1, 1, 1] for i in range(200)])
    assert ld._dump_bounce('X/USDT:USDT', md, 200 * H) is None      # rank unknown: not the studied class


def test_linear_v_is_no_cup():
    from strategies.cup_handle import cup_handle
    bars = []
    for i in range(200):                                            # prior advance 60 -> 100
        p = 60 + 40 * i / 199
        bars.append([i * DAY, p, p * 1.01, p * 0.99, p, 1e6])
    for k in range(61):                                             # a straight V of 60 days, 25% deep
        p = 100 - 25 * (1 - abs(k - 30) / 30)
        bars.append([(200 + k) * DAY, p, p * 1.005, p * 0.995, p, 1e6])
    for k in range(8):                                              # handle
        bars.append([(261 + k) * DAY, 98, 99, 96, 97, 5e5])
    bars.append([269 * DAY, 97, 104, 97, 103, 3e6])                 # breakout on volume
    assert cup_handle(bars, '1d', DAY) is None
