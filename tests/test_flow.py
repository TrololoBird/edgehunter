import random

from config import CONFIG
from flow import BUY, SELL, Footprint, FlowStore, Sweep, SweepTracker, WhaleBook, stacked_imbalance


def test_flowstore_windows_match_naive_sums():
    rng = random.Random(1)
    store = FlowStore(venues=('binance', 'bybit'), capacity=2)
    store.register(['A', 'B', 'C'])            # grows past the initial capacity
    now = 1_790_000_000
    trades = []
    for _ in range(3000):
        sym = rng.choice('ABC')
        venue = rng.choice(('binance', 'bybit'))
        ts = (now - rng.randint(0, 1200)) * 1000 + rng.randint(0, 999)
        usd = rng.uniform(10, 1000)
        side = rng.choice((1, -1))
        trades.append((venue, sym, ts, usd, side))
    trades.sort(key=lambda t: t[2])
    for venue, sym, ts, usd, side in trades:
        store.trade(venue, sym, ts, usd, side)
    for window in (60, 300, 900):
        got = store.net(('binance', 'bybit'), window, now)
        for sym in 'ABC':
            expect = sum(u * s for v, sy, ts, u, s in trades if sy == sym and ts // 1000 > now - window)
            assert abs(got[store.rows[sym]] - expect) < 1e-2 * max(1, abs(expect)) + 0.5


def test_flowstore_old_slots_are_cleared():
    store = FlowStore(venues=('binance',))
    store.register(['A'])
    store.trade('binance', 'A', 1_000_000 * 1000, 100.0, 1)
    later = 1_000_000 + 7200                 # beyond the 1h buffer: the old trade must not come back
    assert store.window(('binance',), BUY, 3600, later)[store.rows['A']] == 0


def test_flowstore_reuses_freed_rows_clean():
    store = FlowStore(venues=('binance',))
    store.register(['A'])
    store.trade('binance', 'A', 1_000_000_000, 500.0, -1)
    store.unregister('A')
    store.register(['B'])
    assert store.window(('binance',), SELL, 60, 1_000_000)[store.rows['B']] == 0


def test_sweeps_merge_same_taker_order():
    got = []
    tracker = SweepTracker(got.append)
    for px in (100.0, 100.1, 100.2):              # one taker order walking three levels (same trade time)
        tracker.add('binance', 'A', 5_000, px, 20_000, 1)
    tracker.add('binance', 'A', 5_100, 100.2, 5_000, 1)   # within the merge window
    tracker.add('binance', 'A', 5_200, 100.1, 7_000, -1)  # other side closes the sweep
    assert len(got) == 1 and got[0].usd == 65_000 and got[0].levels == 3 and got[0].prints == 4
    tracker.flush(10_000)
    assert len(got) == 2 and got[1].side == -1


def test_whale_size_percentile_with_floor_and_cluster():
    book = WhaleBook()
    book.set_ranks(['BTC', 'ETH', 'SMALL'])
    assert book.whale_size('BTC') == CONFIG.sweeps.floor_top_usd_1
    rng = random.Random(3)
    for i in range(2000):
        book.add(Sweep('binance', 'SMALL', i, i, 1, rng.uniform(100, 5_000), 1.0, 1.0, 1, 1))
    size = book.whale_size('SMALL')
    assert size == CONFIG.sweeps.floor_top_usd_2         # rank 3 (top 30 tier); p99.5 of <= $5k sweeps is below it
    for i in range(300):
        book.add(Sweep('binance', 'SMALL', 3000 + i, 3000 + i, 1, 400_000.0, 1.0, 1.0, 1, 1))
    book._threshold_cache.clear()
    assert book.whale_size('SMALL') > CONFIG.sweeps.floor_top_usd_2
    # cluster: many notable same-side sweeps within a minute summing to a whale
    c = WhaleBook()
    c.set_ranks([f'S{i}' for i in range(40)] + ['X'])   # a small coin: $25k whale floor
    now = 1_000_000_000
    for i in range(400):   # the coin's sweep-size distribution must be known before clusters are detected
        c.add(Sweep('binance', 'X', now - 10**7 - i, now - 10**7 - i, 1, 1_000.0 + i, 1, 1, 1, 1))
    c._threshold_cache.clear()
    for i in range(10):   # >= cluster_min_count notable sells summing to >= 2 whale sizes
        c.add(Sweep('binance', 'X', now - i * 1000, now - i * 1000, -1, 30_000.0, 1, 1, 1, 1))
    assert c.cluster('X', now) == -1
    assert c.flow('X', 60, now)['sells'] == 10


def test_whale_state_roundtrip():
    book = WhaleBook()
    book.add(Sweep('binance', 'A', 1, 1, 1, 50_000.0, 1, 1, 1, 1))
    restored = WhaleBook()
    restored.load_state(book.state())
    assert restored.hist['A'].sum() == 1


def test_footprint_stacked_imbalance():
    fp = Footprint()
    fp.enable('A', 1.0)
    t = 60_000 * 1000
    # buyers lift three consecutive levels while sellers one level below are thin
    for level in (100, 101, 102, 103):
        fp.add('A', t, level + 0.5, 30_000, 1)
        fp.add('A', t, level + 0.5, 2_000, -1)
    assert fp.stacked_imbalance('A', t, +1) >= CONFIG.orderflow.stacked_levels
    assert fp.stacked_imbalance('A', t, -1) == 0
    assert stacked_imbalance({}, 1) == 0
