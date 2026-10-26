"""eng-169g: only an opposite ENTRY closes cards; an entered trade yields only to a strictly higher timeframe."""
from types import SimpleNamespace

import signal_book
from signal_book import SignalBook


def card(name, d, tf, entered=False):
    return SimpleNamespace(symbol='X/USDT:USDT', direction=d, finished=False, entered_at=1.0 if entered else None,
                           group_key=name, best_target=0, last_price=None, sig={}, _tf=tf, _mode=name)


def book_with(*cards):
    b = SignalBook()
    b.signals = {c.group_key + str(i): c for i, c in enumerate(cards)}
    b._tf = lambda c: c._tf
    b.strategy = lambda c: SimpleNamespace(name='sweep', time_exit='bars')
    b.closed = []
    b._finish = lambda c, status, now, why='': (b.closed.append((c.group_key, status)), setattr(c, 'finished', True))
    return b


def test_activation_alone_closes_nothing():
    old = card('SWEEP HIGH', -1, '15m', entered=True)
    b = book_with(old)
    b._activate(card('OI BUILD LONG', 1, '15m'), {}, 1.0, 2.0)
    assert b.closed == []


def test_same_tf_entry_keeps_the_open_trade_and_tags():
    old = card('SWEEP HIGH', -1, '15m', entered=True)
    new = card('SWEEP LOW', 1, '15m')
    b = book_with(old, new)
    b._close_opposites(new, 1.0, 2.0)
    assert b.closed == [] and 'opposite_open' in new.sig['shadow_veto']


def test_higher_tf_entry_closes_the_open_trade():
    old = card('SWEEP HIGH', -1, '15m', entered=True)
    new = card('TL TOUCH UP', 1, '1h')
    b = book_with(old, new)
    b._close_opposites(new, 1.0, 2.0)
    assert b.closed == [('SWEEP HIGH', 'CLOSED')]


def test_same_tf_entry_cancels_a_waiting_card():
    old = card('SWEEP HIGH', -1, '15m')
    new = card('SWEEP LOW', 1, '15m')
    b = book_with(old, new)
    b._close_opposites(new, 1.0, 2.0)
    assert b.closed == [('SWEEP HIGH', 'INVALID')]


def test_lower_tf_entry_touches_nothing():
    old = card('TL TOUCH DOWN', -1, '1h')
    new = card('SWEEP LOW', 1, '15m')
    b = book_with(old, new)
    b._close_opposites(new, 1.0, 2.0)
    assert b.closed == [] and signal_book.TF_RANK['1h'] > signal_book.TF_RANK['15m']


def test_waiting_card_of_older_logic_is_replanned_not_expired(monkeypatch):
    from config import CONFIG
    from signal_book import TrackedSignal
    b = SignalBook()
    t = TrackedSignal('X/USDT:USDT', 'SPRING', 1, 'wyckoff', 0.0, 1.0, {}, plan={'entry': 'zone'}, status='WATCH',
                      activated=True, logic_version='eng-100')
    b.signals = {'k': t}
    b.update([], {}, lambda s: None, lambda s: [], 10.0)
    assert not t.finished_at and t.plan is None and not t.activated and t.logic_version == CONFIG.journal.logic_version


def test_confirm_card_of_older_logic_still_expires():
    from signal_book import TrackedSignal
    b = SignalBook()
    t = TrackedSignal('X/USDT:USDT', 'PUMP START', 1, 'pump', 0.0, 1.0, {}, plan={'entry': 'confirm'}, status='WATCH',
                      activated=True, logic_version='eng-100')
    b.signals = {'k': t}
    b.update([], {}, lambda s: None, lambda s: [], 10.0)
    assert t.status == 'EXPIRED'
