from conftest import CHOP, CUR15, Frames, frame, h1_of
from indicators import compute_indicators
from signal_book import SignalBook

# the fixture leg spans 6h: a 1h structure (Elder's factor of five), its trigger on 15m bars (TRIGGER_MINUTES)
TRIG = 15 * 60_000
T_ZONE = CUR15 / 1000 + 10          # scan time that puts zone_since_ms exactly at CUR15 (a 5m boundary)

IMPULSE_UP = dict(is_structured=False, alert_type='ANOMALY', price_change_5m=0.03, oi_change_5m=0.01,
                  futures_cvd_5m=5e5, delta_ratio=0.3, rvol_1m=4, whale_net_5m=0, has_spot=True, spot_cvd_5m=3e5)
# A 15m trend continuation (phase F markup): the setup the 15m-leg continuation lifecycle is tested with
# eng-127: BULL F is gone (Bollinger's Method I is BB1); the continuation card comes from a Tier-0 impulse
MARKUP = dict(alert_type='LONG', price_change_5m=0.03, price_z=8.0, oi_change_5m=0.01, futures_cvd_5m=1e5,
              has_spot=True)


def minutes_for_bars(bars, per=TRIG // 60_000):
    """1m candles whose `per`-minute resample reproduces `bars` (the whole bar in its first minute, flat fillers after)."""
    out = []
    for b in bars:
        out.append([b[0], b[1], b[2], b[3], b[4], b[5], b[6]])
        for k in range(1, per):
            out.append([b[0] + k * 60_000, b[4], b[4], b[4], b[4], 0.0, 0.0])
    return out


def bull_bars(t0, final_q=8e3, interval=TRIG):
    def bar(i, o, h, l, c, q=1e4, Q=5e3):
        return [t0 + i * interval, o, h, l, c, q, Q]
    # eng-119: two candles before the 111.2 high make it a real 2/2 swing (no swing, no structure shift)
    return [bar(-5, 110.5, 110.9, 110.4, 110.7), bar(-4, 110.7, 111.0, 110.6, 110.9),
            bar(-3, 111, 111.2, 110.6, 110.8), bar(-2, 110.8, 110.9, 110.2, 110.3), bar(-1, 110.3, 110.4, 109.9, 110.0),
            bar(0, 110.0, 110.1, 109.4, 109.6, Q=4e3), bar(1, 109.6, 109.8, 109.2, 109.3, Q=4e3),
            bar(2, 109.3, 110.2, 109.3, 110.1, Q=6e3), bar(3, 110.1, 111.5, 110.0, 111.4, Q=final_q)]


def _shift_entry(monkeypatch):
    """eng-58: continuation enters on a resting limit in the kill zones; these lifecycle tests exercise the 5m
    structure-shift trigger (Wyckoff / cascade still use it) on the continuation fixture, outside any session gate."""
    import dataclasses
    import config as config_mod
    from strategies.leg import LegContinuation
    monkeypatch.setattr(config_mod.CONFIG, 'strategies',
                        dataclasses.replace(config_mod.CONFIG.strategies, smt_session=()))
    # audit (ICT OTE): TP1 is now the prior high; the fixture's shift entry at 111.4 sits above the OTE band (R:R to the
    # prior high < 1) - these tests exercise the lifecycle, so the R:R floor is lowered here
    monkeypatch.setattr(config_mod.CONFIG, 'levels', dataclasses.replace(config_mod.CONFIG.levels, min_rr_tp1=0.3))
    orig = LegContinuation.plan
    monkeypatch.setattr(LegContinuation, 'plan', lambda self, x: (
        lambda p: {**p, 'trigger': 'shift', 'trail_after_tp1': False} if p and not p.get('skip') else p)(orig(self, x)))


def _book_in_zone(rally_frame, confirm):
    book = SignalBook()
    book.htf_of = lambda _s: h1_of(rally_frame)
    price = {'X': 119.5}
    candles = {'X': []}
    pf = lambda s: price.get(s)
    cf = lambda s: candles[s]
    created, _ = book.update([('X', MARKUP)], Frames(rally_frame), pf, cf, T_ZONE - 100, confirm_of=confirm)
    s = created[0]
    assert s.mode == 'continuation' and s.status == 'WATCH' and s.plan
    price['X'] = 109.6
    book.update([], Frames(rally_frame), pf, cf, T_ZONE, confirm_of=confirm)
    assert s.status == 'ZONE' and s.zone_since_ms == CUR15 and [e for _, e in book.events] == ['ZONE']
    candles['X'] = minutes_for_bars(bull_bars(CUR15))
    price['X'] = 111.4
    return book, s, price, candles, pf, cf


def test_continuation_lifecycle_with_orderflow_confirm(rally_frame, monkeypatch):
    # the synthetic rally has no swing between its origin and the pullback: no protected swing (strategies/ict.py)
    monkeypatch.setattr('strategies.ict.protected_swing', lambda *a, **k: None)
    _shift_entry(monkeypatch)
    confirm = lambda sym, strategy, d, since, until, extreme: {'flow': True, 'oi': True, 'orderflow': 'imbalance'}
    book, s, price, candles, pf, cf = _book_in_zone(rally_frame, confirm)
    now = CUR15 / 1000 + 4 * TRIG / 1000 + 5
    _, entries = book.update([], Frames(rally_frame), pf, cf, now, confirm_of=confirm)
    assert entries == [s] and s.status == 'ENTRY' and s.levels['entry'] == 111.4 and s.of_confirm == 'imbalance'
    assert s.confirms['orderflow'] == 'imbalance'
    # the fixture's 1.272 / 1.618 extensions are out of reach, so all three targets sit on the prior high: spaced here
    # (the test is about the lifecycle)
    s.levels['tp2'], s.levels['tp3'] = s.levels['tp1'] + 2, s.levels['tp1'] + 4
    # eng-58: targets / stops on the final 1m candles' extremes (a target traded 2 bps through)
    # eng-137 (A02): the entry minute itself is judged on the trades after the entry; this is the next whole minute
    t = (int(s.entered_at * 1000) // 60_000 + 1) * 60_000
    tp1, sl = s.levels['tp1'], s.levels['sl']
    # the entry minute itself (audit V04: a missing minute is a hole the trade waits at, not 'nothing happened')
    candles['X'] += [[m, 111.4, 111.4, 111.4, 111.4, 1e4, 5e3] for m in range(candles['X'][-1][0] + 60_000, t, 60_000)]
    candles['X'].append([t, 111.4, tp1 * 1.0003, 111.3, tp1, 1e4, 6e3])
    price['X'] = tp1
    book.update([], Frames(rally_frame), pf, cf, now + 60, confirm_of=confirm)
    assert s.status == 'TP1'
    candles['X'].append([t + 60_000, tp1, tp1, sl * 0.999, sl * 0.999, 1e4, 3e3])
    price['X'] = sl * 0.999
    book.update([], Frames(rally_frame), pf, cf, now + 120, confirm_of=confirm)
    assert s.status == 'SL' and book.session_results['SL after TP1'] == 1
    e, risk = s.levels['entry'], s.levels['risk0']
    # eng-111: no break-even move (no source) - the stop stays where the plan put it
    assert s.levels['sl'] < e
    gross = ((tp1 - e) + 2 * (s.levels['sl'] - e)) / 3 / risk   # a third at TP1, the rest at the stop
    assert s.final_r is not None and 0 < gross - s.final_r < 0.5   # net of the round trip's costs (eng-58)


def test_trigger_without_orderflow_is_vetoed_and_card_keeps_waiting(rally_frame, monkeypatch):
    import dataclasses
    import config as config_mod
    monkeypatch.setattr(config_mod.CONFIG, 'orderflow',
                        dataclasses.replace(config_mod.CONFIG.orderflow, require_orderflow_confirm=True))
    monkeypatch.setattr(config_mod.CONFIG, 'strategies',
                        dataclasses.replace(config_mod.CONFIG.strategies, shadow_vetoes=()))
    _shift_entry(monkeypatch)
    none = lambda sym, strategy, d, since, until, extreme: {'flow': True, 'oi': True, 'orderflow': False}
    book, s, price, candles, pf, cf = _book_in_zone(rally_frame, none)
    now = CUR15 / 1000 + 4 * TRIG / 1000 + 5
    _, entries = book.update([], Frames(rally_frame), pf, cf, now, confirm_of=none)
    assert len(entries) == 1 and entries[0].vetoed == 'no_orderflow' and entries[0] is not s
    assert s.status == 'ZONE' and s.entered_at is None and s.zone_since_ms == CUR15 + 4 * TRIG and s.vetoed_triggers == 1


def test_shadow_veto_enters_and_journals_the_reason(rally_frame, monkeypatch):
    import dataclasses
    import config as config_mod
    monkeypatch.setattr(config_mod.CONFIG, 'orderflow',
                        dataclasses.replace(config_mod.CONFIG.orderflow, require_orderflow_confirm=True))
    _shift_entry(monkeypatch)
    none = lambda sym, strategy, d, since, until, extreme: {'flow': True, 'oi': True, 'orderflow': False}
    book, s, price, candles, pf, cf = _book_in_zone(rally_frame, none)
    now = CUR15 / 1000 + 4 * TRIG / 1000 + 5
    _, entries = book.update([], Frames(rally_frame), pf, cf, now, confirm_of=none)
    # the confirmation no longer blocks (the next real rule, the fixture's low_rr, decides)
    assert len(entries) == 1 and entries[0].vetoed != 'no_orderflow' and 'no_orderflow' in s.sig['shadow_veto']


def test_perp_led_impulse_is_vetoed(rally_frame, monkeypatch):
    import dataclasses
    import config as config_mod
    # eng-108: perp_led is a shadow veto; with the shadow list empty it blocks as before
    monkeypatch.setattr(config_mod.CONFIG, 'strategies',
                        dataclasses.replace(config_mod.CONFIG.strategies, shadow_vetoes=()))
    book = SignalBook()
    perp_led = dict(IMPULSE_UP, spot_cvd_5m=-1e5, agg_funding_8h=0.0005, agg_oi_change_1h=0.01)   # crowded
    created, _ = book.update([('X', perp_led)], Frames(rally_frame), lambda s: 119.5, lambda s: [], T_ZONE)
    assert created == [] and book.vetoed and book.vetoed[0][2] == 'perp_led'
    led_markup = dict(MARKUP, perp_led_long=True, agg_funding_8h=0.0005, agg_oi_change_1h=0.01)
    created, _ = book.update([('Z', led_markup)], Frames(rally_frame), lambda s: 119.5, lambda s: [], T_ZONE)
    assert created == [] and book.vetoed[0][2] == 'perp_led'
    futures_only = dict(MARKUP, has_spot=False)
    created, _ = book.update([('Y', futures_only)], Frames(rally_frame), lambda s: 119.5, lambda s: [], T_ZONE)
    # no spot market: a continuation cannot be told from a leverage-only move - not a card
    assert created == [] and book.vetoed[0][2] == 'no_data'


def test_invalid_dedupe_bias(rally_frame):
    from levels import find_impulse
    imp = find_impulse(rally_frame, +1, h1_of(rally_frame))
    b2 = SignalBook()
    b2.htf_of = lambda _s: h1_of(rally_frame)
    p2 = {'Y': 119.5}
    s2 = b2.update([('Y', MARKUP)], Frames(rally_frame), lambda x: p2.get(x), lambda x: [], T_ZONE)[0][0]
    p2['Y'] = imp['start'] - 0.5
    b2.update([], Frames(rally_frame), lambda x: p2.get(x), lambda x: [], T_ZONE + 10)
    assert s2.status == 'INVALID'
    b3 = SignalBook()
    b3.htf_of = lambda _s: h1_of(rally_frame)
    b3.update([('Z', MARKUP)], Frames(rally_frame), lambda x: 119.5, lambda x: [], T_ZONE)
    spring = dict(is_structured=True, alert_type='LONG', long_score=3, short_score=0, phase_b_score=3, active_phases=['B'])
    created, _ = b3.update([('Z', spring)], Frames(rally_frame), lambda x: 119.5, lambda x: [], T_ZONE + 10)
    assert created == [] and len(b3.signals) == 1
    flat = compute_indicators(frame(CHOP + CHOP[:39]))
    b4 = SignalBook()
    created, _ = b4.update([('W', IMPULSE_UP)], Frames(flat), lambda x: 100.0, lambda x: [], T_ZONE)
    # No qualifying leg: not a card, shown as a vetoed setup
    assert created == [] and not b4.signals and [v[2] for v in b4.vetoed] == ['no_leg']



def test_state_roundtrip(rally_frame):
    book = SignalBook()
    book.update([('X', MARKUP)], Frames(rally_frame), lambda s: 119.5, lambda s: [], T_ZONE)
    book.session_results['TP1'] += 2
    state = book.state()
    restored = SignalBook()
    restored.load_state(state, T_ZONE + 60)
    assert list(restored.signals) == list(book.signals) and restored.session_results['TP1'] == 2
    expired = SignalBook()
    expired.load_state(state, T_ZONE + 25 * 3600)
    # eng-108: no invented waiting clock - the card is restored and ends structurally (invalid / TP1 / no plan)
    assert list(expired.signals) == list(book.signals)
