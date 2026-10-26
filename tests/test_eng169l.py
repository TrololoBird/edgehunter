from signal_book import MANAGE_EXEMPT
from strategies.pump import pump_start


def test_oi_build_is_managed():
    assert 'oi_build' not in MANAGE_EXEMPT and 'breakout' in MANAGE_EXEMPT


def _minutes(move):
    t0 = 1_800_000_000_000
    out = [[t0 + k * 60_000, 100.0, 100.1, 99.9, 100.0, 1e4, 5e3] for k in range(120)]
    out[-1][4] = out[-1][2] = 100 * (1 + move)
    return out


def test_pump_note_names_the_flow_source():
    m = {'rvol_1m': 50, 'oi_change_5m': 0.01, 'spot_cvd_5m': 1e5}
    a = pump_start(_minutes(0.06), dict(m), 0.004, _minutes(0.06)[-1][0] + 60_000)
    b = pump_start(_minutes(0.06), dict(m, flow_src='futures'), 0.004, _minutes(0.06)[-1][0] + 60_000)
    assert a and 'spot buying' in a['setup_note']
    assert b and 'futures buying' in b['setup_note'] and 'spot' not in b['setup_note']


def test_trade_excursion_stops_at_the_exit():
    # risk 10: the trade goes to 106 (+0.6R), then the stop 90 is hit; the later 130 never counts
    from tests.test_eng137 import M, bar, entered
    from signal_book import SignalBook
    book, s = SignalBook(), entered()
    s.managed_ms = 6 * M
    book.tracked_of = lambda sym, since, until: {'hi': 100.0, 'lo': 100.0}
    mins = [bar(6 * M, 100, 106, 99, 104), bar(7 * M, 104, 104, 89, 90), bar(8 * M, 90, 130, 90, 129)]
    book._manage_trade(s, 129.0, 9 * M / 1000, lambda _: mins)
    assert s.status == 'SL'
    assert abs(s.trade_mfe_r - 0.6) < 1e-9 and s.trade_mae_r <= -1.0
