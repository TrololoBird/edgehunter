"""Characterization (audit of the levels geometry, 2026-10-26): the CURRENT rule - strength = sum of source weights,
deduplicated only within one kind (<= 2x) - lets ONE candle's low, seen as a 15m swing, a 1h swing, an equal-lows pool
and the day's low, form a zone above min_strength (2.5). This documents the behaviour; it is not a fix."""
from config import CONFIG
from zones import RawLevel, merge


def test_one_extreme_in_four_representations_passes_min_strength():
    p, ts = 100.0, 1_700_000_000_000
    same_low = [RawLevel(p, 'swing_15m', '15m low', -1, ts=ts), RawLevel(p, 'swing_1h', '1h low', -1, ts=ts),
                RawLevel(p, 'equal', 'EQL×2', -1, ts=ts), RawLevel(p, 'pdhl', 'day low', -1, ts=ts)]
    z = merge(same_low, atr=1.0)
    assert len(z) == 1
    assert z[0].strength == 4.0 > CONFIG.zones.min_strength          # 4 x 1.0 from a single price event


def test_one_kind_is_capped_at_twice_its_weight():
    p = 100.0
    z = merge([RawLevel(p, 'swing_15m', '15m low', -1, ts=i) for i in range(5)], atr=1.0)
    assert z[0].strength == 2.0                                        # the only dedup the code has
