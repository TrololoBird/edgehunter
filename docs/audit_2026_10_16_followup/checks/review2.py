"""Counterexamples of the independent review of 6b771ba. Usage: python review2.py <repo> (no network, temp SQLite).

1. A06: an order filled in full, its fills listed only in part -> the exit price / fees must come from the order.
2. Prefix invariance of the 1m exit loop: the same minutes managed one hour at a time (live) and in one batch whose
   buffers already hold LATER bars / days (a restart, a stall) must decide the same exit at the same minute.
3. A04: an inner bucket with minutes missing, by the explicit quality policy.
4. FVG across a dropped bucket.

`python review2.py <repo> check` asserts the expected (fixed) results: every mismatch is printed as FAIL and the
script exits 1 - a printed wrong result is not a pass. Without `check` it only prints (the 'before' run on 6b771ba).
"""
import asyncio, sqlite3, sys, tempfile, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from executor import DemoExecutor          # noqa: E402
import signal_book as sb                   # noqa: E402
from scanner import Scanner                # noqa: E402
import levels                              # noqa: E402

M, H, D = 60_000, 3_600_000, 86_400_000
CHECK = len(sys.argv) > 2 and sys.argv[2] == 'check'
FAILED = []


def expect(name, got, want):
    """want: the expected value, or a callable(got) -> bool. Recorded only in check mode."""
    ok = want(got) if callable(want) else got == want
    if CHECK:
        print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else f": got {got!r}, want {want!r}"))
        if not ok:
            FAILED.append(name)


# ------------------------------------------------------------------------------------------------------------- A06
def a06(label, fills, orders, want):
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / 'demo.db')
        with patch('executor.credentials', return_value=('', '')):
            DemoExecutor(db)
            opened = int(time.time() * 1000) - 60_000
            with sqlite3.connect(db) as c:
                rid = c.execute('INSERT INTO demo_trades (card_id,symbol,strategy,direction,opened_ms,entry_plan,entry_fill,'
                                'qty,sl,risk_usd) VALUES (?,?,?,?,?,?,?,?,?,?)',
                                ('card', 'X', 'breakout', 1, opened, 100., 100., 1., 90., 10.)).lastrowid
            ex = DemoExecutor(db)
        t = ex.open['card']

        async def fake(method, *a, **k):
            if method == 'fetch_my_trades':
                return [dict(f, timestamp=opened + f['dt']) for f in fills]
            if method == 'fetch_order':
                return dict(orders[a[0]], id=a[0])
            raise AssertionError(method)
        ex._call = fake
        try:
            asyncio.run(ex._finalize(t, 'SL', None))
        except Exception as e:                                   # an exchange field must never raise here
            print(f"A06 {label:62s} RAISED {e!r}")
            expect(f"A06 {label}: no exception", repr(e), 'no exception')
            return
        with sqlite3.connect(db) as c:
            row = c.execute('SELECT exit_avg, round(fees_usd, 4), round(pnl_usd, 4), error FROM demo_trades WHERE id=?',
                            (rid,)).fetchone()
        print(f"A06 {label:62s} exit, fees, pnl, error = {row}")
        expect(f"A06 {label}", row, want)


part = {'side': 'sell', 'price': 110., 'amount': 30., 'dt': 1000, 'order': 'S',
        'fee': {'currency': 'USDT', 'cost': .0165}}               # 0.3 of the 1.0 order listed (ccxt unit x100)
full = {'status': 'closed', 'filled': 1., 'average': 95., 'fee': {'currency': 'USDT', 'cost': .0475}}
PENDING = (None, None, None, 'exit fill pending')
FULL = (95.0, 0.0975, -5.0975, None)          # 1.0 @95 from 100: -5, fees 0.05 entry (config rate) + 0.0475 exit
print('the true result of the fixture: exit 95 for 1.0, fees 0.0975, pnl -5.0975')
a06('order filled 1.0 @95 in full, only a 0.3 fill @110 listed', [part], {'S': full}, FULL)
a06('the same, status EXPIRED (BingX raw), filled in full', [part], {'S': dict(full, status='EXPIRED')}, FULL)
a06('EXPIRED with a partial fill 0.6 of 1.0', [part], {'S': dict(full, status='EXPIRED', filled=.6)}, PENDING)
a06('canceled with a partial fill 0.6 of 1.0', [part], {'S': dict(full, status='canceled', filled=.6)}, PENDING)
a06('order still working (status open)', [part], {'S': dict(full, status='open')}, PENDING)
a06('order without a reported fee', [part], {'S': dict(full, fee={})}, PENDING)
a06('fee cost NaN', [part], {'S': dict(full, fee={'currency': 'USDT', 'cost': float('nan')})}, PENDING)
for bad in (None, 0, 0., -95., float('nan'), float('inf'), 'abc', ''):
    a06(f'average = {bad!r}', [part], {'S': dict(full, average=bad)}, PENDING)
for bad in (None, 0, -1., float('nan'), float('inf'), 'abc'):
    a06(f'filled = {bad!r}', [part], {'S': dict(full, filled=bad)}, PENDING)
a06('two orders: TP1 0.5 @110 + stop 0.5 @90 (each listed in part)',
    [part, dict(part, order='T', price=110.)],
    {'S': dict(full, filled=.5, average=90., fee={'currency': 'USDT', 'cost': .0225}),
     'T': dict(full, filled=.5, average=110., fee={'currency': None, 'cost': -.0275})},
    (100.0, 0.1, -0.1, None))                  # avg 100; fees 0.05 + 0.0225 + 0.0275 (abs of a negative commission)
a06('two orders cover 1.5 of 1.0 (another trade\'s order got in)', [part, dict(part, order='T')],
    {'S': full, 'T': dict(full, filled=.5)}, PENDING)


# ------------------------------------------------------------------------------------------- prefix invariance
def card(plan, levels, status='ENTRY', best=0):
    return sb.TrackedSignal('X', 'G', 1, 'x', 0., 100., {}, plan=plan, levels=levels, entered_at=1., managed_ms=0,
                            last_price=100., units=[], status=status, best_target=best)


def outcome(s):
    return (s.status, None if s.exit_fill is None else round(s.exit_fill, 4), round(s.levels['sl'], 4),
            (s.managed_ms or 0) // M if s.finished else None)


def manage(make, minutes, d1=(), h1=(), step=60):
    """(live: an hour of minutes at a time, every buffer cut at that time; batch: one call, buffers hold it all)"""
    res = []
    for batch in (False, True):
        s, b = make(), sb.SignalBook()
        cuts = [len(minutes)] if batch else range(step, len(minutes) + step, step)
        for k in cuts:
            buf = minutes[:k]
            now = minutes[min(k, len(minutes)) - 1][0] + M
            vis = (lambda t: True) if batch else (lambda t, now=now, size=0: t <= now)
            b.daily_of = lambda sym, now=now: [x for x in d1 if vis(x[0] + D)]
            ns = SimpleNamespace(market_data={'X': SimpleNamespace(h1=[x for x in h1 if vis(x[0] + H)])})
            b.band_of = lambda sym, d, asof=None, ns=ns: (Scanner._opposite_band(ns, sym, d) if asof is None
                                                         else Scanner._opposite_band(ns, sym, d, asof))
            b._manage_trade(s, buf[-1][4], now / 1000, lambda sym, buf=buf: buf)
            if s.finished:
                break
        res.append(outcome(s))
    return res


def show(name, res, want):
    print(f"{name:8s} live {res[0]}  batch {res[1]}  ->", 'SAME' if res[0] == res[1] else 'DIFFERENT')
    expect(f"{name}: live == batch", res[1], res[0])
    expect(f"{name}: expected outcome", res[0], want)


inf = float('inf')
# SAR (BB1, 4h): flat 4h, then a 4h at 120; the stop must not use the second bar before it closed
mins = [[i * M, 100., 101., 99., 100., 1., .5, .01] if i < 240 else [i * M, 120., 121., 119., 120., 1., .5, .01]
        for i in range(480)]
show('SAR', manage(lambda: card({'sar': {'sar': 90., 'ep': 150., 'af': .2, 'tf_min': 240, 'last_ts': -4 * H},
                                 'no_tp': True}, {'entry': 100., 'sl': 90., 'risk0': 10., 'tp1': inf, 'tp2': inf,
                                                  'tp3': inf}), mins),
     ('ENTRY', None, 99.0, None))   # the 4h at 120 closes at minute 480: no SAR step before; stop 99 = prior bar low
# EMA20 trail after TP1 (5m): a slow rise, then a jump to 130 three hours later
mins = [[i * M, c, c + .02, c - .05, c, 1., .5, .01] for i, c in
        enumerate([105 + k * .01 for k in range(200)] + [130.] * 100)]
show('EMA', manage(lambda: card({'trail_after_tp1': True, 'trigger_minutes': 5},
                                {'entry': 100., 'sl': 95., 'risk0': 5., 'tp1': 101., 'tp2': 1e9, 'tp3': 1e9},
                                status='TP1', best=1), mins),
     lambda r: r[0] == 'TP1' and r[3] is None)       # the rise never trades below its own EMA20: no stop
# Turtle 3-day channel: days -3..-1 low 90, day 0 low 98, days 1..3 low 99
d1 = [[t * D, 100., 101., 90., 100., 1.] for t in (-3, -2, -1)] + \
     [[t * D, 100., 101., lo, 100., 1.] for t, lo in ((0, 98.), (1, 99.), (2, 99.), (3, 99.))]
mins = [[i * M, 100., 101., 98. if i // 1440 == 0 else 99., 100., 1., .5, .01] for i in range(4 * 1440)]
show('channel', manage(lambda: card({'trail_days': 3, 'no_tp': True},
                                    {'entry': 100., 'sl': 50., 'risk0': 50., 'tp1': inf, 'tp2': inf, 'tp3': inf}),
                       mins, d1=d1),
     ('ENTRY', None, 50.0, None))      # the channel known on days 0..3 is 90, 90, 90, 98: no low below it
# Bollinger opposite band (4h BB20): 80 past hours alternate 100 / 102 by 4h, the next 8 hours close 101
h1 = [[t * H, 101., 102., 100., 100. if (t // 4) % 2 else 102., 1.] for t in range(-80, 0)] + \
     [[t * H, 101., 102.92, 100.5, 101., 1.] for t in range(8)]
mins = [[i * M, 101., 102.92, 100.5, 101., 1., .5, .01] for i in range(8 * 60)]
_cl = [100. if (t // 4) % 2 else 102. for t in range(-80, 0, 4)][1:] + [101.]   # the 20 4h closes known at 4:00
_mu = sum(_cl) / 20
BAND1 = _mu + 2 * (sum((x - _mu) ** 2 for x in _cl) / 20) ** .5
expect('band fixture: bucket 0 band 103 > high 102.92 > bucket 1 band', 103. > 102.92 > BAND1, True)
show('band', manage(lambda: card({'band_exit': True, 'no_tp': True},
                                 {'entry': 100., 'sl': 90., 'risk0': 10., 'tp1': inf, 'tp2': inf, 'tp3': inf}),
                    mins, h1=h1),
     ('CLOSED', round(BAND1, 4), 90.0, 241))   # bucket 0 (band 103) never reached; bucket 1's band BAND1 at its open

# ---------------------------------------------------------------------------------------------------------- A04
base = [[i * M, 100., 101., 99., 100., 1., .5, .01] for i in range(60)]
for name, gone in (('5m bucket of minutes 10-14 lost minute 12 (inner)', {12}), ('5m bucket 2 lost its first minute 10', {10}),
                   ('5m bucket of minutes 10-14 lost its last minute 14', {14}), ('5m bucket 2 lost minutes 11, 12', {11, 12})):
    bars = levels.resample([c for c in base if c[0] // M not in gone], 5, 60 * M)
    kept = any(b[0] == 10 * M for b in bars)
    expect(f"A04 {name}: kept", kept, gone == {12})     # only the inner gap with first + last minute and 80% stays
    print(f"A04 {name:40s} -> 5m bars {len(bars)}, bucket at minute 10 kept: {kept}",
          getattr(levels, 'RESAMPLE_QUALITY', ''))

# ------------------------------------------------- FVG across a dropped bucket (review of bb73b99, finding 2)
from strategies.ict import fvg_setup       # noqa: E402
F = 300_000
bars = [[k * F, 100., 101., 99., 100.] for k in range(10)]          # flat; swing high 101.5 at bar 5
bars[5] = [5 * F, 100., 101.5, 99., 100.]
bars += [[10 * F, 100., 103., 100., 102.5],                          # the displacement
         [11 * F, 102.5, 104., 100.5, 103.5],                        # bar 11 trades 100.5-104: no gap
         [12 * F, 103.5, 105., 103., 104.5]]
dropped = bars[:11] + bars[12:]                                      # bucket 11 dropped (its first minute lost)
print('FVG all bars           ->', fvg_setup(bars, 1, 8 * F, F))
print('FVG bar 11 dropped     ->', fvg_setup(dropped, 1, 8 * F, F), '(a gap 101..103 that bar 11 traded through)')
expect('FVG all bars: none', fvg_setup(bars, 1, 8 * F, F), None)
expect('FVG bar 11 dropped: none', fvg_setup(dropped, 1, 8 * F, F), None)

if CHECK:
    print(f"\n{'FAILED: ' + ', '.join(FAILED) if FAILED else 'ALL EXPECTATIONS MET'}")
    sys.exit(1 if FAILED else 0)
