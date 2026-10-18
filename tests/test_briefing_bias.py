"""Owner 2026-10-18: the briefing background vs a strong 4h trend; sent slots survive a restart."""
from types import SimpleNamespace

import pytest

import briefing
from config import CONFIG


def _brief(coin):
    b = briefing.Briefing.__new__(briefing.Briefing)
    b.cfg = CONFIG.briefing
    md = SimpleNamespace(symbol='BTC/USDT:USDT', d1=[[0]] * 400, w1=[], h1=[], h4=[], last_price=1.0)
    b.sc = SimpleNamespace(market_data={'BTC/USDT:USDT': md},
                           fetcher=SimpleNamespace(htf_bias=lambda src, now: {'coin': coin}))
    return b


@pytest.mark.parametrize('coin, want', [
    ({'bias': 'bull', 'h4': -1, 'adx4': 49.2}, 'conflict'),     # BTC 2026-10-18 02:30
    ({'bias': 'bull', 'h4': -1, 'adx4': 20.0}, 'bull'),         # weak 4h trend: the weeks stand
    ({'bias': 'bull', 'h4': 1, 'adx4': 40.0}, 'bull'),
    ({'bias': 'bear', 'h4': 1, 'adx4': 30.0}, 'conflict'),
    ({'bias': 'bear', 'h4': -1, 'adx4': 30.0}, 'bear'),
    ({'bias': 'range', 'h4': -1, 'adx4': 40.0}, 'range'),
    ({'bias': 'bull', 'h4': -1, 'adx4': None}, 'bull'),
])
def test_bias_vs_4h(coin, want):
    assert _brief(coin)._bias_of('BTC/USDT:USDT')[0] == want


def test_slots_persist(tmp_path, monkeypatch):
    monkeypatch.setattr(briefing.Briefing, 'SLOTS_PATH', str(tmp_path / 'slots.json'))
    b = briefing.Briefing.__new__(briefing.Briefing)
    b._done_slots = b._load_slots()
    assert b._done_slots == set()
    b._done_slots.update(f"2026-10-{d:02d} 02:30" for d in range(1, 31))
    b._done_slots.update(f"2026-10-{d:02d} 09:30" for d in range(1, 31))
    b._save_slots()
    again = briefing.Briefing.__new__(briefing.Briefing)._load_slots()
    assert len(again) == 40 and '2026-10-30 09:30' in again and '2026-10-01 02:30' not in again
