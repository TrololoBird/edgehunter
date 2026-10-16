"""A02 / A18 / S04 / S05 / S06 / S11 before / after. Run: python checks/strat.py <repo root>. Offline."""
import inspect
import sys
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])


def run(name, fn):
    try:
        print(name, fn())
    except Exception as e:
        print(name, 'ERROR', type(e).__name__, e)


def a02():
    # the window's detector sees a LONG first, later a SHORT as well; the loop must reach the SHORT
    import strategies.silver_bullet as sbm
    from strategies.loopside import LoopDetectors
    takes_skip = 'skip' in inspect.signature(sbm.silver_bullet).parameters

    def fake(bars, now_ms, pdh=None, pdl=None, skip=()):
        for d in (1, -1):
            if d in skip:
                continue
            if d == 1 or now_ms >= 2:
                return {'direction': d, 'setup': 'L' if d > 0 else 'S'}
        return None
    if not takes_skip:
        fake_old = lambda bars, now_ms, pdh=None, pdl=None: fake(bars, now_ms, pdh, pdl)   # noqa: E731
    out = []
    loop = SimpleNamespace(_sb_checked={}, _sb_fired=set(), minutes_of=lambda s: [], m15_of=lambda s: [])
    md = SimpleNamespace(minute_closed_until=None, d1=[])
    with patch.object(sbm, 'silver_bullet', fake if takes_skip else fake_old), \
            patch.object(sbm, 'window_of', lambda now: 0):
        for now, minute in ((1, 240_000), (2, 540_000), (3, 840_000)):
            md.minute_closed_until = minute
            f = LoopDetectors._silver_bullet(loop, 'X', md, now)
            out.append(f and f['setup'])
    return f'calls -> {out} (a SHORT appears from the 2nd call)'


def a18():
    from strategies.pump import dump_bounce
    hourly = [[i * 3_600_000, 100., 101., 99., 100., 1.] for i in range(190)]
    hourly[175] = [175 * 3_600_000, 100., 100., 59., 60., 100.]
    for i in range(176, 189):
        hourly[i] = [i * 3_600_000, 65., 75., 60., 65., 1.]
    hourly[189] = [189 * 3_600_000, 65., 65., 49., 50., 1.]
    no_ex = dump_bounce(hourly, 190 * 3_600_000)
    # with an exhaustion close (hour 177 closes above hour 176's high) the bounce is read after it
    h2 = [list(c) for c in hourly]
    h2[176] = [176 * 3_600_000, 60., 62., 55., 61., 1.]
    h2[177] = [177 * 3_600_000, 61., 66., 60., 65., 1.]
    for i in range(178, 189):
        h2[i] = [i * 3_600_000, 70., 76., 69., 72., 1.]
    h2[189] = [189 * 3_600_000, 72., 72., 66., 67., 1.]
    ex = dump_bounce(h2, 190 * 3_600_000)
    return (f'no exhaustion -> {no_ex and (no_ex["setup"], no_ex["dump_low"])}; '
            f'with exhaustion -> {ex and (ex["setup"], ex["dump_low"])}')


def s04():
    from levels import pullback_spread_ok
    # 4h spring range 8; test 15m candles of range 2.5: old / 2 limit 2.4 lets it pass, sqrt(240/15) = 4 gives 1.2
    minutes = [[i * 60_000, 100., 100.0 + (2.0 if i % 15 == 0 else 0), 100., 100., 1., .5, .01] for i in range(30)]
    kw = {'spring_tf_min': 240} if 'spring_tf_min' in inspect.signature(pullback_spread_ok).parameters else {}
    ratio = __import__('config').CONFIG.levels.spring_test_spread_ratio
    return (f'test avg range 2.0, spring 4h range 8, ratio {ratio}: passes={pullback_spread_ok(minutes, 0, 30 * 60_000, 8.0, **kw)} '
            f'(limit {ratio} x 8 / 4 = {ratio * 2:g})')


def s06():
    from strategies.geometry import system_levels
    plan = {'exit': {'stop': ['price', 95.], 'tp': ['trail'], 'pad': True, 'tp1_price': 104., 'atr': 3.},
            'atr': 3., 'tf_atr': 3., 'min_rr': 1.0, 'symbol': 'X', 'tf': '1h', 'volume_24h': 1e9}
    lv = system_levels(plan, 100., 95., 1)
    return f"entry 100, stop {lv['sl']:.4g}, TP1 104: rr_tp1 {lv['rr_tp1']:.3f} low_rr={lv['low_rr']} ({lv['rr_reason']})"


def s05():
    from strategies.geometry import finish_levels
    plan = {'min_rr': 3.0, 'min_rr_on_tp1': True, 'atr': 1., 'tf': '4h', 'symbol': 'X', 'strategy': 'supply_demand',
            'volume_24h': 1e9, 'zones': [], 'exit': {}}
    lv = finish_levels(plan, 100., 99., [100.3, 110., 110.], ['zone', 'zone', 'zone'], 1, 'distal')
    return f"TP1 rr {lv['rr_tp1']:.3f}, blend {lv['rr_blend']:.2f}: low_rr={lv['low_rr']} ({lv.get('rr_reason')})"


def s11():
    import strategies.wyckoff_range as wr
    got = {}
    with patch.object(wr, 'base_plan', lambda x, *a, **kw: got.update(kw) or kw), \
            patch.object(wr, 'select_targets', lambda *a: ([110., 140., 140.], ['far', 'P&F', 'P&F'])), \
            patch.object(wr, 'merge', lambda *a, **k: []):
        sig = {'range_lo': 90., 'range_hi': 110., 'anchor_level': 90., 'anchor_extreme': 88., 'anchor_ts': 0,
               'pnf_target': 140., 'wy_tf': '4h'}
        x = SimpleNamespace(sig=sig, direction=1, atr=1., raw_levels=[], symbol='X')
        wr.WyckoffRangeStrategy().plan(x)
    return f"fillers passed to the plan: {got.get('fillers')}"


for name, fn in [('A02', a02), ('A18', a18), ('S04', s04), ('S05', s05), ('S06', s06), ('S11', s11)]:
    run(name, fn)
