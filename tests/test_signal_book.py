from conftest import CHOP, CUR15, N, Frames, frame
from indicators import compute_indicators
from strategies import STRATEGIES, PlanInput
from signal_book import SignalBook

FIVE = 5 * 60_000
T_ZONE = CUR15 / 1000 + 10          # scan time that puts zone_since_ms exactly at CUR15 (a 5m boundary)

IMPULSE_UP = dict(is_structured=False, alert_type='ANOMALY', price_change_5m=0.03, oi_change_5m=0.01,
                  futures_cvd_5m=5e5, delta_ratio=0.3, rvol_1m=4, whale_net_5m=0, has_spot=True, spot_cvd_5m=3e5)
# A 15m trend continuation (phase F markup): the setup the 15m-leg continuation lifecycle is tested with
MARKUP = dict(is_structured=True, alert_type='LONG', long_score=5, short_score=0, phase_f_score=5, active_phases=['F'],
              has_spot=True)


def minutes_for_bars(bars):
    """1m candles whose 5m resample reproduces `bars` (the whole bar in its first minute, flat fillers after)."""
    out = []
    for b in bars:
        out.append([b[0], b[1], b[2], b[3], b[4], b[5], b[6]])
        for k in range(1, 5):
            out.append([b[0] + k * 60_000, b[4], b[4], b[4], b[4], 0.0, 0.0])
    return out


def bull_bars(t0, final_q=8e3):
    def bar(i, o, h, l, c, q=1e4, Q=5e3):
        return [t0 + i * FIVE, o, h, l, c, q, Q]
    return [bar(-3, 111, 111.2, 110.6, 110.8), bar(-2, 110.8, 110.9, 110.2, 110.3), bar(-1, 110.3, 110.4, 109.9, 110.0),
            bar(0, 110.0, 110.1, 109.4, 109.6, Q=4e3), bar(1, 109.6, 109.8, 109.2, 109.3, Q=4e3),
            bar(2, 109.3, 110.2, 109.3, 110.1, Q=6e3), bar(3, 110.1, 111.5, 110.0, 111.4, Q=final_q)]


def _book_in_zone(rally_frame, confirm):
    book = SignalBook()
    price = {'X': 119.5}
    candles = {'X': []}
    pf = lambda s: price.get(s)
    cf = lambda s: candles[s]
    created, _ = book.update([('X', MARKUP)], Frames(rally_frame), pf, cf, T_ZONE - 100, confirm_of=confirm)
    s = created[0]
    assert s.mode == 'trend' and s.status == 'WATCH' and s.plan
    price['X'] = 109.6
    book.update([], Frames(rally_frame), pf, cf, T_ZONE, confirm_of=confirm)
    assert s.status == 'ZONE' and s.zone_since_ms == CUR15 and [e for _, e in book.events] == ['ZONE']
    candles['X'] = minutes_for_bars(bull_bars(CUR15))
    price['X'] = 111.4
    return book, s, price, candles, pf, cf


def test_continuation_lifecycle_with_orderflow_confirm(rally_frame):
    confirm = lambda sym, strategy, d, since, until, extreme: {'flow': True, 'oi': True, 'orderflow': 'imbalance'}
    book, s, price, candles, pf, cf = _book_in_zone(rally_frame, confirm)
    now = CUR15 / 1000 + 4 * 300 + 5
    _, entries = book.update([], Frames(rally_frame), pf, cf, now, confirm_of=confirm)
    assert entries == [s] and s.status == 'ENTRY' and s.levels['entry'] == 111.4 and s.of_confirm == 'imbalance'
    assert s.confirms['orderflow'] == 'imbalance'
    price['X'] = s.levels['tp1'] + 0.01
    book.update([], Frames(rally_frame), pf, cf, now + 60, confirm_of=confirm)
    assert s.status == 'TP1'
    price['X'] = s.levels['sl'] - 0.01
    book.update([], Frames(rally_frame), pf, cf, now + 120, confirm_of=confirm)
    assert s.status == 'SL' and book.session_results['SL after TP1'] == 1


def test_trigger_without_orderflow_is_vetoed_and_card_keeps_waiting(rally_frame, monkeypatch):
    import dataclasses
    import config as config_mod
    monkeypatch.setattr(config_mod.CONFIG, 'orderflow',
                        dataclasses.replace(config_mod.CONFIG.orderflow, require_orderflow_confirm=True))
    none = lambda sym, strategy, d, since, until, extreme: {'flow': True, 'oi': True, 'orderflow': False}
    book, s, price, candles, pf, cf = _book_in_zone(rally_frame, none)
    now = CUR15 / 1000 + 4 * 300 + 5
    _, entries = book.update([], Frames(rally_frame), pf, cf, now, confirm_of=none)
    assert len(entries) == 1 and entries[0].vetoed == 'no_orderflow' and entries[0] is not s
    assert s.status == 'ZONE' and s.entered_at is None and s.zone_since_ms == CUR15 + 4 * FIVE and s.vetoed_triggers == 1


def test_perp_led_impulse_is_vetoed(rally_frame):
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
    imp = find_impulse(rally_frame, +1)
    b2 = SignalBook()
    p2 = {'Y': 119.5}
    s2 = b2.update([('Y', MARKUP)], Frames(rally_frame), lambda x: p2.get(x), lambda x: [], T_ZONE)[0][0]
    p2['Y'] = imp['start'] - 0.5
    b2.update([], Frames(rally_frame), lambda x: p2.get(x), lambda x: [], T_ZONE + 10)
    assert s2.status == 'INVALID'
    b3 = SignalBook()
    b3.update([('Z', MARKUP)], Frames(rally_frame), lambda x: 119.5, lambda x: [], T_ZONE)
    spring = dict(is_structured=True, alert_type='LONG', long_score=3, short_score=0, phase_b_score=3, active_phases=['B'])
    created, _ = b3.update([('Z', spring)], Frames(rally_frame), lambda x: 119.5, lambda x: [], T_ZONE + 10)
    assert created == [] and len(b3.signals) == 1
    flat = compute_indicators(frame(CHOP + CHOP[:39]))
    b4 = SignalBook()
    created, _ = b4.update([('W', IMPULSE_UP)], Frames(flat), lambda x: 100.0, lambda x: [], T_ZONE)
    # No qualifying leg: not a card, shown as a vetoed setup
    assert created == [] and not b4.signals and [v[2] for v in b4.vetoed] == ['no_leg']


def test_reversal_confirmation_invalid_missed():
    drop = [120 - 1.0 * i for i in range(1, 21)]
    ind_r = compute_indicators(frame((CHOP[:70] + drop + [100.5] * 9)[-N:]))
    rp = STRATEGIES['wyckoff'].plan(PlanInput(symbol='R', direction=+1, setup='BULL A', sig={}, df=ind_r, minutes=[],
                                              raw_levels=[], h1=[], context=None, reached=None))
    assert rp is not None
    acc = dict(is_structured=True, alert_type='LONG', long_score=4, short_score=0, phase_a_score=4, active_phases=['A'])
    # Near the leg's end at the confirmation: entered at once, stop >= 1 ATR
    b5 = SignalBook()
    _, entries = b5.update([('R', acc)], Frames(ind_r), lambda x: rp['impulse']['end'] + 0.1, lambda x: [], T_ZONE)
    assert entries and entries[0].status == 'ENTRY' and entries[0].levels['zone_src'] == 'setup confirmation'
    assert entries[0].levels['entry'] - entries[0].levels['sl'] >= rp['impulse']['atr_15m'] - 1e-9
    # Too close to TP1 at the confirmation: the entry is vetoed (low R:R), the card waits
    b6 = SignalBook()
    p6 = {'R': rp['targets'][0] - 0.05}
    s6 = b6.update([('R', acc)], Frames(ind_r), lambda x: p6.get(x), lambda x: [], T_ZONE)[0][0]
    assert s6.status == 'WATCH' and s6.veto_log == ['low_rr']
    # ... price then really goes to TP1 without an entry: MISSED
    p6['R'] = rp['targets'][0] + 0.2
    b6.update([], Frames(ind_r), lambda x: p6.get(x), lambda x: [], T_ZONE + 10)
    assert s6.status == 'MISSED'
    # Beyond the leg's end and its stop pool before an entry: INVALID, not re-measured
    b7 = SignalBook()
    p7 = {'R': rp['targets'][0] - 0.05}
    s7 = b7.update([('R', acc)], Frames(ind_r), lambda x: p7.get(x), lambda x: [], T_ZONE)[0][0]
    p7['R'] = s7.invalid_price - 0.01
    b7.update([], Frames(ind_r), lambda x: p7.get(x), lambda x: [], T_ZONE + 10)
    assert s7.status == 'INVALID'


def test_state_roundtrip(rally_frame):
    book = SignalBook()
    book.update([('X', MARKUP)], Frames(rally_frame), lambda s: 119.5, lambda s: [], T_ZONE)
    book.session_results['TP1'] += 2
    state = book.state()
    restored = SignalBook()
    restored.load_state(state, T_ZONE + 60)
    assert list(restored.signals) == list(book.signals) and restored.session_results['TP1'] == 2
    expired = SignalBook()
    expired.load_state(state, T_ZONE + 25 * 3600)   # older than the longest (4h-leg) watch_ttl: dropped
    assert not expired.signals
