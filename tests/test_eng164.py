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


def test_briefing_score_detail_marks_an_open_trade_to_market():
    """eng-168m: an entered scenario still undecided reports its mark-to-market R; a stop reports its candle's close."""
    from briefing import Briefing, HOUR_MS
    sc = {'entry': (99.0, 100.0), 'stop': 98.0, 'targets': [104.0], 'tag': 'отскок от поддержки'}
    t = 1_700_000_000_000
    react = [t, 99.5, 101.0, 99.2, 100.5]                     # low <= e1, close > e1 and > open: entry 100.5
    later = [t + HOUR_MS, 100.5, 101.5, 100.2, 101.75]
    txt, resolved, r, _e = Briefing.score_detail(sc, 1, [react, later])
    assert txt == 'вход, без исхода' and resolved is None and r == 0.5
    stop = [t + 2 * HOUR_MS, 101.0, 101.0, 97.5, 98.0]
    txt, resolved, r, _e = Briefing.score_detail(sc, 1, [react, later, stop])
    assert txt.startswith('вход → стоп') and resolved == t + 3 * HOUR_MS and r == -1.0


def _cur_zones():
    return [{'lo': 110.0, 'hi': 111.0, 'side': 1, 'tol': 0.1, 'pad': 0.2, 'mid': 110.5},
            {'lo': 100.0, 'hi': 103.0, 'side': 0, 'tol': 0.2, 'pad': 0.4, 'mid': 101.5},
            {'lo': 92.0, 'hi': 93.0, 'side': -1, 'tol': 0.1, 'pad': 0.2, 'mid': 92.5}]


def test_variant_inside_the_zone_follows_the_price_position():
    """eng-168n: price at the zone's top -> the long is the breakout; at its bottom of a wide zone -> from the low."""
    import briefing_chart
    top = briefing_chart.plan(102.8, _cur_zones(), atr_1d=5.0, atr_1h=1.0)
    assert top['long']['tag'] == 'закрепление выше'
    low = briefing_chart.plan(100.3, _cur_zones(), atr_1d=5.0, atr_1h=1.0)
    assert low['long']['tag'] == 'от низа зоны' and low['short']['tag'] == 'закрепление ниже'
    assert low.get('oco') and low['long'].get('cur_bound') and low['short'].get('cur_bound')


def test_oco_cancels_the_opposite_scenario_of_the_zone():
    """eng-168n: the long entered first -> the cur-bound short of the same post is cancelled at that candle."""
    from briefing import Briefing, HOUR_MS
    t = 472_223 * HOUR_MS                                            # an hour boundary
    lg = {'entry': (100.0, 100.6), 'stop': 99.6, 'targets': [103.0], 'tag': 'от низа зоны', 'cur_bound': True}
    sh = {'entry': (99.8, 100.0), 'stop': 103.4, 'targets': [93.0], 'tag': 'закрепление ниже', 'cur_bound': True}
    rec = {'ts': (t - 60_000) / 1000, 'scenario': {'long': lg, 'short': sh}}   # posted a minute before t
    bars = [[t, 100.2, 101.0, 100.1, 100.8],                         # long reaction: entry 100.8
            [t + HOUR_MS, 100.8, 100.9, 99.0, 99.5],                 # a close below the zone (would arm the short)
            [t + 2 * HOUR_MS, 99.5, 99.9, 99.2, 99.3]]
    res, _ = Briefing._score_record(Briefing.__new__(Briefing), rec, bars, [])
    short = next(x for x in res if x[0] == 'шорт')
    assert short[1].startswith('отменён: включился встречный') and short[3] == t + HOUR_MS


def test_xau_365_leg_needs_paxg_at_both_dates():
    """eng-168p: PAXG must exist within a day of both chain dates; a gap -> no proxy (tsm from the contract only)."""
    import time
    from types import SimpleNamespace
    from briefing import Briefing
    day = 86_400_000
    now = int(time.time() * 1000) // day * day
    d1 = [[now - (300 - k) * day, 100, 101, 99, 100 + k * 0.1] for k in range(300)]     # 300 days, rising
    paxg_full = [[d1[0][0] - (200 - k) * day, 50, 51, 49, 200 - k * 0.5] for k in range(201)]   # falling, ends at day 0
    b = Briefing.__new__(Briefing)
    b.cfg = SimpleNamespace(bias_h4_adx=0)
    coin = {'bias': 'bull', 'tsm': 1.0, 'w1': 1, 'd1': 1, 'h4': 1, 'adx4': 20.0}
    b.sc = SimpleNamespace(fetcher=SimpleNamespace(htf_bias=lambda md, t: {'coin': dict(coin)}))
    md = SimpleNamespace(d1=d1, symbol='XAU/USDT:USDT')
    b._proxy_history = lambda base: {'1d': paxg_full}
    bias, st = b._bias_of('XAU/USDT:USDT', md)
    assert st['proxy'] is not None and st['tsm'] < 1.0          # the PAXG leg (falling) entered the 365-day sign
    gap = [c for c in paxg_full if not (d1[0][0] - 70 * day <= c[0] <= d1[0][0] - 60 * day)]
    b._proxy_history = lambda base: {'1d': gap}
    bias, st = b._bias_of('XAU/USDT:USDT', md)
    assert st['proxy'] is None and st['tsm'] == 1.0             # no PAXG close near the start date: no proxy


def test_breakeven_share_from_the_worst_entry():
    """eng-168o: p uses the worst entry of the range (the same basis as the R:R >= 1 check)."""
    import briefing_chart
    zones = [{'lo': 110.0, 'hi': 111.0, 'side': 1, 'tol': 0.1, 'pad': 0.2, 'mid': 110.5},
             {'lo': 98.0, 'hi': 99.0, 'side': -1, 'tol': 0.2, 'pad': 0.5, 'mid': 98.5}]
    p = briefing_chart.plan(100.0, zones)
    lg = p['long']
    worst = max(lg['entry'])
    assert abs(lg['p'] - abs(worst - lg['stop']) / (abs(worst - lg['stop']) + abs(lg['targets'][0] - worst))) < 1e-12


def test_partial_post_hour_bar_carries_the_hour_open():
    """eng-168o: the bar built from the post-hour's minutes has the hour's open as its time."""
    from briefing import Briefing, HOUR_MS
    t = 472_300 * HOUR_MS
    post = t + 10 * 60_000
    minutes = [[post + k * 60_000, 100, 100.5, 99.5, 100] for k in range(50)]
    sc = {'long': {'entry': (99.0, 99.4), 'stop': 98.0, 'targets': [105.0], 'tag': 'отскок от поддержки'}}
    seen = []
    b = Briefing.__new__(Briefing)
    b.score_detail = lambda s, side, bars, cancel_at=None: (seen.append(bars) or ('не включился', None, None, None))
    b._score_record({'ts': post / 1000, 'scenario': sc}, [], minutes)
    assert seen and seen[0][0][0] == t


def test_history_high_ignores_forming_candles():
    """eng-168q: the forming day / week (REST rows of a coin outside the universe) is not the history's high."""
    import time
    from types import SimpleNamespace
    from briefing import Briefing
    day = 86_400_000
    now = int(time.time() * 1000)
    d1 = [[now - (40 - k) * day, 1, 10, 1, 5] for k in range(40)] + [[now - 1000, 1, 99, 1, 50]]   # forming: high 99
    hi, days = Briefing._history_high(SimpleNamespace(d1=d1, w1=[]))
    assert hi == 10 and 39 <= days <= 41


def test_empty_calendar_load_replaces_the_old_week():
    """eng-168q: a successful load with no USD High / Medium event clears the previous list; an error body keeps it."""
    import macro_calendar as mc
    mc.set_live([{'country': 'USD', 'impact': 'High', 'title': 'CPI', 'date': '2026-10-01T08:30:00-04:00'}], 1.0)
    assert mc.LIVE
    mc.set_live({'error': 'rate limited'}, 2.0)
    assert mc.LIVE and mc.LIVE_AT == 1.0
    mc.set_live([], 3.0)
    assert mc.LIVE == [] and mc.LIVE_AT == 3.0


def test_execution_model_v1_partial_then_break_even():
    """eng-168r: 50% at +1R, the rest's stop to break-even + costs: +1R then back to entry ~ +0.5R - costs."""
    from briefing import Briefing, HOUR_MS
    from config import CONFIG
    sc = {'stop': 98.0, 'targets': [104.0, 106.0], 'entry': (99, 100), 'tag': 'x'}
    t = 472_400 * HOUR_MS
    after = [[t, 100, 102.2, 100.5, 102.0],         # +1R (102) reached, low above break-even + costs
             [t + HOUR_MS, 102, 102.1, 99.5, 99.6]]   # back below break-even
    d = Briefing.exec_detail(sc, 1, 100.0, after)
    cost_frac = CONFIG.journal.fee_round_trip + 2 * CONFIG.levels.slippage_bps / 1e4
    cost_r = cost_frac * 100 / 2
    assert d['resolved'] and not d['ambiguous'] and not d['tp1_hit']
    assert abs(d['exec_r'] - round(0.5 + 0.5 * cost_frac * 100 / 2 - cost_r, 2)) < 0.011
    assert d['mfe_r'] == 1.1 and d['mae_r'] == -0.25


def test_execution_model_v1_stop_and_target_in_one_candle_is_ambiguous():
    """eng-168r: a candle through +1R and the stop - order unknown: the stop, marked ambiguous."""
    from briefing import Briefing, HOUR_MS
    sc = {'stop': 98.0, 'targets': [104.0], 'entry': (99, 100), 'tag': 'x'}
    d = Briefing.exec_detail(sc, 1, 100.0, [[472_400 * HOUR_MS, 100, 102.5, 97.5, 99.0]])
    assert d['ambiguous'] and d['exec_r'] < -1.0 and d['stop_hit']


def test_macro_gate_fails_closed_without_a_fresh_calendar(monkeypatch):
    """eng-168s: never loaded or older than LIVE_MAX_AGE_SEC -> live_ok False (new entries wait)."""
    import time
    import macro_calendar as mc
    now = time.time() * 1000
    monkeypatch.setattr(mc, 'LIVE_AT', 0.0)
    assert not mc.live_ok(now)
    monkeypatch.setattr(mc, 'LIVE_AT', time.time() - mc.LIVE_MAX_AGE_SEC - 60)
    assert not mc.live_ok(now)
    monkeypatch.setattr(mc, 'LIVE_AT', time.time() - 60)
    assert mc.live_ok(now)


def test_forecast_counts_tp1_only_before_the_stop():
    """eng-168u: stop first, TP1 later -> stop_hit only (TP1 after the stop is not a forecast hit)."""
    from briefing import Briefing, HOUR_MS
    sc = {'stop': 98.0, 'targets': [103.0], 'entry': (99, 100), 'tag': 'x'}
    t = 472_500 * HOUR_MS
    d = Briefing.exec_detail(sc, 1, 100.0, [[t, 100, 100.5, 97.5, 98.2], [t + HOUR_MS, 98.2, 104.0, 98.1, 103.5]])
    assert d['stop_hit'] and not d['tp1_hit']


def test_targets_include_the_current_zone_beyond_the_entry():
    """eng-168v: a support bounce under the zone price sits in targets that zone first (it was skipped)."""
    import briefing_chart
    zones = [{'lo': 110.0, 'hi': 111.0, 'side': 1, 'tol': 0.1, 'pad': 0.2, 'mid': 110.5},
             {'lo': 104.0, 'hi': 105.0, 'side': 0, 'tol': 0.1, 'pad': 0.2, 'mid': 104.5},
             {'lo': 98.0, 'hi': 99.0, 'side': -1, 'tol': 0.1, 'pad': 0.3, 'mid': 98.5}]
    p = briefing_chart.plan(104.5, zones, atr_1d=10.0, atr_1h=2.0)
    lg = p['long']
    assert lg is not None and lg['tag'] == 'отскок от поддержки' and lg['targets'][0] == 104.0


def test_sweep_and_reclaim_shadow_entry():
    """eng-168w: a candle below the entry range's low closing back above it enters; stop beyond its low."""
    from briefing import Briefing, HOUR_MS
    sc = {'entry': (99.0, 100.0), 'stop': 98.0, 'targets': [104.0], 'tag': 'отскок от поддержки'}
    t = 472_600 * HOUR_MS
    bars = [[t, 100.5, 100.6, 99.5, 99.8], [t + HOUR_MS, 99.8, 99.9, 98.6, 99.4],     # sweep below 99, close 99.4
            [t + 2 * HOUR_MS, 99.4, 104.2, 99.3, 104.0]]
    d = Briefing.sweep_variant(sc, 1, bars)
    assert d and d['fill'] == 99.4 and abs(d['stop'] - (98.6 - 0.25)) < 1e-9 and d['tp1_hit'] and d['resolved']
    assert Briefing.sweep_variant(sc, 1, bars[:1]) is None


def test_unfavourable_scenario_is_shown_and_marked():
    """eng-168x: TP1 closer than the stop -> the scenario stays (analysis), rr_ok False; the level map has a base view."""
    import briefing_chart
    from briefing import Briefing
    zones = [{'lo': 101.0, 'hi': 101.3, 'side': 1, 'tol': 0.1, 'pad': 0.2, 'mid': 101.1},
             {'lo': 100.4, 'hi': 100.6, 'side': 0, 'tol': 0.1, 'pad': 0.2, 'mid': 100.5},
             {'lo': 99.0, 'hi': 100.0, 'side': -1, 'tol': 0.1, 'pad': 1.0, 'mid': 99.5}]
    p = briefing_chart.plan(100.5, zones, atr_1d=5.0, atr_1h=1.0)
    assert p['long'] is not None and p['long']['rr_ok'] is False
    lm = Briefing.level_map(100.5, zones, 1)
    assert any(x.startswith('📌 Пока выше') for x in lm) and any(x.startswith('▲') for x in lm)


def test_confirmation_timeframe_follows_the_zone():
    """eng-168y: a zone of 4h / 1d pivots or a higher map level confirms on 4h; an intraday one on 1h; to_4h groups."""
    from briefing import conf_tf, to_4h, H4_MS
    assert conf_tf({'tfs': ['1h', '4h']}) == '4h'
    assert conf_tf({'tfs': ['1h'], 'labels': ['PDH', 'breaker 4h']}) == '1h'      # eng-168z: labels do not decide
    assert conf_tf({'tfs': ['1d'], 'labels': ['PDH']}) == '4h'                     # a PD map-level zone
    assert conf_tf({'tfs': ['1h'], 'labels': ['day high', 'Asia low']}) == '1h'
    t = 100 * H4_MS
    bars = [[t + k * 3_600_000, 10 + k, 11 + k, 9 + k, 10.5 + k] for k in range(6)]
    b4 = to_4h(bars)
    assert len(b4) == 1 and b4[0] == [t, 10, 14, 9, 13.5]       # the second 4h group is incomplete


def test_recap_words():
    from briefing import Briefing
    assert Briefing.human_outcome('вход, без исхода', 0.3) == 'вошли, в работе (+0.30R по рынку)'
    assert Briefing.human_outcome('не включился') == 'условие не наступило'


def test_to_4h_needs_all_four_hours():
    """eng-168z: a missing hour inside the interval -> no 4h bar."""
    from briefing import to_4h, H4_MS
    t = 200 * H4_MS
    bars = [[t + k * 3_600_000, 1, 2, 0.5, 1.5] for k in (0, 1, 3)]
    assert to_4h(bars) == []
