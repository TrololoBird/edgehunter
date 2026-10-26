"""eng-169e: no stop is anchored on / pushed beyond a round number (Osler: stops cascade just beyond it); it stays a TP3 pool."""
from zones import POOL_KINDS, STOP_POOL_KINDS, STRUCTURE_KINDS, RawLevel, merge, stop_beyond, targets


def test_round_is_not_a_stop_pool_but_still_a_target_pool():
    assert 'round' in POOL_KINDS and 'round' not in STOP_POOL_KINDS and 'round' not in STRUCTURE_KINDS


def test_stop_not_pushed_beyond_a_round_number(monkeypatch):
    import pierce
    monkeypatch.setattr(pierce, 'model', lambda: None)
    zones = merge([RawLevel(99.8, 'round', 'round 99.8', -1)], atr=1.0)
    base, label = stop_beyond(zones, 100.0, 101.0, 1, 1.0)
    assert base == 100.0 and label == 'beyond the swing'
    zones = merge([RawLevel(99.8, 'equal', 'EQL×2', -1)], atr=1.0)
    assert stop_beyond(zones, 100.0, 101.0, 1, 1.0)[0] == 99.8


def test_round_still_reachable_as_tp3():
    z = merge([RawLevel(105.0, 'swing_1d', 'a', 1), RawLevel(110.0, 'swing_1d', 'b', 1), RawLevel(115.0, 'round', 'round 115', 1)],
              atr=1.0)
    assert [p for p, _ in targets(z, 100.0, 1, 1.0)] == [105.0, 110.0, 115.0]
