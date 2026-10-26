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


def test_swept_and_active_parts_mixed_zone_is_not_swept():
    from zones import swept_zone
    a = RawLevel(100.0, 'equal', 'EQL×2', -1, swept=True)
    b = RawLevel(100.1, 'pdhl', 'PDL', -1, swept=False)
    z = merge([a, b], atr=1.0)
    assert len(z) == 1
    assert not swept_zone(z[0], ('equal', 'pdhl'))      # one live pool keeps the zone a pool
    assert swept_zone(z[0], ('equal',))                  # judged per kind set: the swept EQL alone is gone


def test_ties_are_deterministic():
    lv = [RawLevel(100.0, k, k, -1) for k in ('swing_15m', 'pdhl', 'equal', 'round')]
    assert key(merge(lv, atr=1.0)) == key(merge(list(reversed(lv)), atr=1.0))


def test_scale_invariance_price_and_atr():
    k = 1000.0
    lv = levels()
    big = [RawLevel(x.price * k, x.kind, x.label, x.side, ts=x.ts, body=None if x.body is None else x.body * k)
           for x in lv]
    a, b = merge(lv, atr=1.0), merge(big, atr=k)
    assert len(a) == len(b)
    for za, zb in zip(a, b):
        assert abs(za.lo * k - zb.lo) < 1e-6 * zb.lo and abs(za.hi * k - zb.hi) < 1e-6 * zb.hi
        assert za.strength == zb.strength


def test_closed_only_drops_forming_and_just_closed(monkeypatch):
    import fetcher
    monkeypatch.setattr(fetcher.time, 'time', lambda: 1_000_000.0)          # now = 1e9 ms
    rows = [[0, 0, 0, 0, 0, 0, 999_990_000], [0, 0, 0, 0, 0, 0, 999_998_000], [0, 0, 0, 0, 0, 0, 1_000_500_000]]
    assert fetcher.DataFetcher._closed_only(rows) == rows[:1]   # closed 10s ago kept; 2s ago and forming dropped
