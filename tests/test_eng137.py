"""eng-137: audit 2026-10-17 A01 (invalidation in time order), A02 (the entry minute), A04 (Turtle S1 states)."""
import types

import pytest

from signal_book import SignalBook, TrackedSignal

M = 60_000
DAY = 86_400_000


def card(direction=1, created_ms=10 * M, **kw):
    return TrackedSignal(symbol='X', group_key='SWEEP LOW', direction=direction, mode='sweep',
                         created=created_ms / 1000, price_at_signal=100.0, sig={}, logic_version='eng-137', **kw)


def bar(t, o, h, lo, c):
    return [t, o, h, lo, c, 1.0, 0.5, 1.0]


# ---------------------------------------------------------------------- A01

def test_a01_wick_through_invalidation_between_scans():
    book, s = SignalBook(), card()
    mins = [bar(11 * M, 100, 101, 99, 100), bar(12 * M, 100, 100, 90, 99), bar(13 * M, 99, 101, 98, 100)]
    assert book._invalid_since(s, lambda _: mins, 95.0, None) == 90.0     # price back at 100: still INVALID


def test_a01_minutes_before_creation_and_already_checked_are_skipped():
    book, s = SignalBook(), card(created_ms=12 * M + 5_000)
    mins = [bar(12 * M, 100, 100, 90, 99), bar(13 * M, 99, 101, 98, 100)]  # the 90 wick predates the card
    assert book._invalid_since(s, lambda _: mins, 95.0, None) is None
    assert s.inv_ms == 14 * M
    mins.append(bar(14 * M, 100, 100, 94, 99))
    assert book._invalid_since(s, lambda _: mins, 95.0, None) == 94.0


def test_a01_close_rule_keeps_the_close():
    book, s = SignalBook(), card(created_ms=0)
    # 5m bars: a wick to 90 closing at 97 (allowed), then a bar closing at 94 (beyond 95)
    mins = [bar(k * M, 100, 100, 90 if k == 2 else 98, 97) for k in range(1, 5)] + [bar(0, 100, 100, 99, 100)]
    mins = sorted(mins)
    assert book._invalid_since(s, lambda _: mins, 95.0, 5) is None
    mins += [bar(k * M, 97, 97, 93, 94 if k == 9 else 96) for k in range(5, 10)]
    assert book._invalid_since(s, lambda _: mins, 95.0, 5) == 94.0


def test_a01_short_mirror():
    book, s = SignalBook(), card(direction=-1)
    mins = [bar(11 * M, 100, 106, 99, 100)]
    assert book._invalid_since(s, lambda _: mins, 105.0, None) == 106.0


# ---------------------------------------------------------------------- A02

def entered(sl=90.0, tp1=110.0):
    s = card(entered_at=(5 * M + 1) / 1000)
    s.levels = {'entry': 100.0, 'sl': sl, 'tp1': tp1, 'tp2': 120.0, 'tp3': 130.0, 'risk0': 10.0}
    s.plan = {}
    return s


def test_a02_entry_minute_from_trades_after_the_entry():
    book, s = SignalBook(), entered()
    book.tracked_of = lambda sym, since, until: {'hi': 101.0, 'lo': 99.0}
    c = bar(5 * M, 100, 101, 89, 100)                 # the 89 low traded before the entry
    assert book._entry_minute(s, c, 5 * M + 1, 6 * M / 1000 + 20) == (100.0, 101.0, 99.0)
    assert s.entry_min == 'trades'


def test_a02_no_trades_and_a_touch_is_ambiguous_with_a_low_bound():
    book, s = SignalBook(), entered()
    c = bar(5 * M, 100, 101, 89, 100)
    assert book._entry_minute(s, c, 5 * M + 1, 7 * M / 1000) is False
    assert s.entry_min == 'ambiguous'
    assert s.r_low is not None and s.r_low <= -1.0


def test_a02_no_touch_is_clean():
    book, s = SignalBook(), entered()
    c = bar(5 * M, 100, 101, 95, 100)
    assert book._entry_minute(s, c, 5 * M + 1, 7 * M / 1000) == (100.0, 101.0, 95.0)
    assert s.entry_min == 'clean' and s.r_low is None


def test_a02_waits_for_the_minutes_trades():
    book, s = SignalBook(), entered()
    book.tracked_of = lambda sym, since, until: {'pending': True}
    assert book._entry_minute(s, bar(5 * M, 100, 101, 89, 100), 5 * M + 1, 6 * M / 1000 + 2) is None


def test_a02_the_old_pass_missed_the_stop():
    """The audit's case: SL 90, the entry minute low 89 AFTER the entry, price back at 100."""
    book, s = SignalBook(), entered()
    s.managed_ms = 5 * M
    book.tracked_of = lambda sym, since, until: {'hi': 100.0, 'lo': 89.0}
    book._manage_trade(s, 100.0, 6 * M / 1000 + 20, lambda _: [bar(5 * M, 100, 100, 89, 100)])
    assert s.status == 'SL' and s.exit_fill == 90.0


def test_a02_fetcher_tracker_needs_contiguous_ids():
    from fetcher import DataFetcher
    f = types.SimpleNamespace(entry_trackers={}, _last_agg={'X': 10})
    DataFetcher.track_from(f, 'X', 1000)
    tr = f.entry_trackers['X']
    DataFetcher._track_trade(tr, 11, 999, 50.0)       # before the entry: continuity only
    DataFetcher._track_trade(tr, 12, 1500, 101.0)
    DataFetcher._track_trade(tr, 13, 2500, 99.0)
    assert DataFetcher.tracked_of(f, 'X', 1000, 2000) == {'hi': 101.0, 'lo': 99.0}
    assert DataFetcher.tracked_of(f, 'X', 1000, 3000) == {'pending': True}
    DataFetcher._track_trade(tr, 15, 3500, 98.0)      # id 14 lost
    assert DataFetcher.tracked_of(f, 'X', 1000, 2000) is None


# ---------------------------------------------------------------------- A04

def flat(n, lo=99.0, hi=101.0):
    return [[i * DAY, 100, hi, lo, 100, 1e6] for i in range(n)]


def test_a04_open_ambiguous_s1_blocks_a_new_s1():
    from strategies.turtle import n_series, s1_blocked, s1_state, turtle_breakout
    d1 = flat(59)
    d1.append([59 * DAY, 100, 103, 90, 100, 1e6])     # breakout above 101 and the 2N stop the same day, still open
    state, prior = s1_state(d1, n_series(d1))
    assert state == 'ambiguous' and s1_blocked(state, prior)
    assert turtle_breakout(d1, 103.1, 100, 60 * DAY) is None or \
        turtle_breakout(d1, 103.1, 100, 60 * DAY)['turtle_system'] == 2


@pytest.mark.parametrize('state,prior,blocked', [
    ('none', None, False), ('loss', None, False), ('win', None, True), ('ambiguous', None, True),
    ('open', None, False), ('open', 'loss', False), ('open', 'win', True), ('open', 'ambiguous', True)])
def test_a04_states(state, prior, blocked):
    from strategies.turtle import s1_blocked
    assert s1_blocked(state, prior) is blocked
