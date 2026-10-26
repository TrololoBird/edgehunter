"""Audit P1 (2026-10-26): zones.merge invariants - input order, the A-B-C chain, the 6 ATR width cap."""
import random

from zones import RawLevel, merge


def key(zs):
    return [(round(z.lo, 9), round(z.hi, 9), round(z.strength, 9), tuple(sorted(z.kinds))) for z in zs]


def levels():
    rnd = random.Random(7)
    kinds = ['swing_15m', 'swing_1h', 'equal', 'pdhl', 'fvg_1h', 'ob_4h', 'round', 'poc']
    out = []
    for i in range(60):
        p = 100 + rnd.uniform(-10, 10)
        body = p - rnd.uniform(0, 0.4) if rnd.random() < 0.5 else None
        out.append(RawLevel(p, rnd.choice(kinds), f"l{i}", rnd.choice((1, -1)), ts=i, body=body))
    return out


def test_merge_does_not_depend_on_input_order():
    base = key(merge(levels(), atr=1.0))
    for seed in range(20):
        lv = levels()
        random.Random(seed).shuffle(lv)
        assert key(merge(lv, atr=1.0)) == base


def test_chain_is_measured_from_the_zones_first_level():
    # A-B and B-C within 0.3 ATR, A-C not: the zone is not chained beyond the first level's reach
    a, b, c = (RawLevel(p, 'swing_15m', n, -1) for p, n in ((100.0, 'A'), (100.25, 'B'), (100.5, 'C')))
    zs = merge([a, b, c], atr=1.0)
    assert len(zs) == 2 and zs[0].lo == 100.0 and zs[0].hi == 100.25 and zs[1].lo == 100.5


def test_width_cap_six_atr():
    wide = RawLevel(100.0, 'ob_1d', 'wide', -1, body=93.5)        # 6.5 ATR wide: its own zone, absorbs nothing
    near = RawLevel(99.0, 'swing_15m', 'near', -1)
    zs = merge([wide, near], atr=1.0)
    assert len(zs) == 2 and any(z.lo == 93.5 and z.hi == 100.0 and z.strength == 3.0 for z in zs)
