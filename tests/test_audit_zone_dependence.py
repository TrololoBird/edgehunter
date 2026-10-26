"""eng-169e (audit S5): one price extreme seen as several kinds counts once in a zone's strength; separate touches of
one kind still add (<= 2x its weight). Was: 15m swing + 1h swing + EQL + day low of ONE candle = 4.0 > min_strength."""
from config import CONFIG
from zones import RawLevel, merge


def test_one_extreme_in_four_representations_counts_once():
    p, ts = 100.0, 1_700_000_000_000
    same_low = [RawLevel(p, 'swing_15m', '15m low', -1, ts=ts), RawLevel(p, 'swing_1h', '1h low', -1, ts=ts),
                RawLevel(p, 'equal', 'EQL×2', -1, ts=ts), RawLevel(p, 'pdhl', 'day low', -1, ts=ts)]
    z = merge(same_low, atr=1.0)
    assert len(z) == 1 and z[0].strength == 1.0 < CONFIG.zones.min_strength
    assert set(z[0].kinds) == {'swing_15m', 'swing_1h', 'equal', 'pdhl'}       # every kind still listed


def test_strongest_kind_of_an_event_wins():
    z = merge([RawLevel(100.0, 'swing_15m', '15m low', -1), RawLevel(100.0, 'swing_1d', '1d low', -1)], atr=1.0)
    assert z[0].strength == 2.5


def test_separate_touches_of_one_kind_still_add_capped():
    z = merge([RawLevel(100.0, 'swing_15m', '15m low', -1, ts=i) for i in range(5)], atr=1.0)
    assert z[0].strength == 2.0


def test_distinct_prices_are_distinct_events():
    lv = [RawLevel(100.0, 'swing_15m', 'a', -1), RawLevel(100.05, 'swing_1h', 'b', -1), RawLevel(100.1, 'pdhl', 'PDL', -1)]
    z = merge(lv, atr=1.0)
    assert len(z) == 1 and z[0].strength == 3.0
