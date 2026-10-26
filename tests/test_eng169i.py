import math

from strategies.oi_build import oi_build

T0 = 1_800_000_000_000 // 300_000 * 300_000


def _m15(step_pct, n=300, wiggle=0.004):
    # closes wiggling +-wiggle around a drift: the usual 1h move ~ a few tenths of a percent
    out, px = [], 100.0
    for k in range(n):
        px *= 1 + step_pct + wiggle * math.sin(k * 1.7)
        out.append([T0 - (n - k) * 900_000, px, px, px, px, 1e5, 5e4])
    return out


def _minutes(p60, base=100.0):
    return [[T0 - (120 - k) * 60_000, base, base, base, base * (1 + p60 * max(0, k - 60) / 60), 1e5, 6e4]
            for k in range(121)]


def build_case(p60=0.03, btc_p60=0.0, oi_jump=0.05):
    oi = [(T0 - (287 - k) * 300_000, 1000.0 * (1 + 0.002 * math.sin(k * 0.9))) for k in range(288)]
    samples = [(T0 - (63 - k) * 60_000, oi[-13][1]) for k in range(63)] + [(T0 + 30_000, oi[-13][1] * (1 + oi_jump))]
    oi[-1] = (oi[-1][0], oi[-13][1] * (1 + oi_jump))
    return (_minutes(p60), oi, T0 + 60_000, samples, _m15(0.0), _minutes(btc_p60, 50_000.0), _m15(0.0))


def test_fires_on_material_own_move():
    sig = oi_build(*build_case())
    assert sig and sig['direction'] == 1 and sig['oi_build_z'] >= 2 and sig['oi_build_rel_btc'] >= 1


def test_noise_oi_does_not_fire():
    assert oi_build(*build_case(oi_jump=0.001)) is None


def test_small_price_move_does_not_fire():
    assert oi_build(*build_case(p60=0.0005)) is None


def test_market_beta_move_does_not_fire():
    # the coin's 3% hour while BTC made the same move in its own units: the market's move, not the coin's
    assert oi_build(*build_case(p60=0.03, btc_p60=0.03)) is None


def test_btc_unknown_does_not_fire():
    a = list(build_case())
    a[5] = []
    assert oi_build(*a) is None


def test_tp1_not_paying_costs_is_low_rr():
    from strategies import geometry
    plan = {'setup': 'ENTRY OI BUILD LONG', 'symbol': None, 'tf': '15m', 'zones': []}   # no own min_rr, as OI BUILD
    # TP1 0.05% above the entry (under the round trip's cost), TP2 / TP3 far: the blend alone passed it
    out = geometry.finish_levels(plan, 100.0, 98.0, [100.05, 106.0, 108.0], ['1h swing'] * 3, 1, 'x')
    assert out['low_rr'] and 'does not pay the costs' in out['rr_reason']
    ok = geometry.finish_levels(plan, 100.0, 98.0, [102.5, 106.0, 108.0], ['1h swing'] * 3, 1, 'x')
    assert 'does not pay' not in (ok['rr_reason'] or '')
