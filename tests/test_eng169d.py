"""eng-169d: a stalled / empty 1m stream is no reading (None), not a negative confirmation (False)."""
from strategies import confirm

M = 60_000


def bars(t0, n, buy=60.0, vol=100.0):
    # [open_ms, o, h, l, c, quote_vol, taker_buy_quote]
    return [[t0 + i * M, 1, 1, 1, 1, vol, buy] for i in range(n)]


def ev(minutes, spot):
    return confirm.evaluate('sweep', 1, minutes, spot, None, 0, 60 * M, None, None)


def test_empty_spot_stream_is_no_reading():
    out = ev(bars(0, 60), [])
    assert out['spot'] is None and out['flow'] is True


def test_stalled_streams_are_no_reading():
    out = ev(bars(0, 30), bars(0, 30))          # both stopped 30 minutes before the entry
    assert out['flow'] is None and out['spot'] is None


def test_covered_selling_is_still_negative():
    out = ev(bars(0, 60, buy=40.0), bars(0, 60, buy=40.0))
    assert out['flow'] is False and out['spot'] is False


def test_none_does_not_veto_a_required_confirmation(monkeypatch):
    monkeypatch.setattr(confirm, 'PROMOTED', {('sweep', 'spot')})
    assert confirm.missing('sweep', {'spot': None}) is None or confirm.missing('sweep', {'spot': None}) == 'no_confirmation'
    assert confirm.missing('sweep', {'spot': False}) == 'no_spot'
