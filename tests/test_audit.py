"""Regression checks for the bugs the eng-7 audit found (each reproduced before the fix)."""
from datetime import date

import numpy as np

from conftest import frame
from indicators import compute_indicators_batch
from levels import funding_r, simulate
from pretrain import closed_minutes, eligible_days
from scorer import PhaseScorer
from stats import bh_q
from zones import RawLevel, equal_pools, estimated_liquidations

H = 3_600_000
DAY = 86_400_000


def test_pretrain_reads_only_closed_minutes():
    # a scan 5s after a 15m close must not read the minute that opened at the close (the archive holds all of it)
    close = 1_000 * 900_000
    opens = np.asarray([close - 120_000, close - 60_000, close], dtype=float)
    assert closed_minutes(opens, close + 5_000) == 2
    assert closed_minutes(opens, close + 60_000) == 3


def test_eligible_days_use_the_past_only():
    # quiet for 60 days, then $50M a day: the coin joins only once the 30 days BEFORE a day average above the floor
    start = date(2026, 3, 1)
    d0 = (start - date(1970, 1, 1)).days - 60
    daily = np.asarray([[(d0 + k) * DAY, 1.0, 1e6 if k < 60 else 5e7] for k in range(90)])
    days = eligible_days(daily, start, date(2026, 3, 30), 3e6)
    first_loud = d0 + 60
    assert days and min(days) > first_loud                        # not on the first loud day: its volume is future
    assert all(d > first_loud for d in days)


def test_liquidation_estimate_ignores_price_only_oi_growth():
    candles, oi, p = [], [], 100.0
    for i in range(24):
        candles.append([i * H, p, p * 1.01, p * 0.999, p * 1.01, 1e6, 6e5])
        p *= 1.01
        oi.append(((i + 1) * H, 1_000_000.0))                    # contracts constant (coins), price +1%/h
    assert estimated_liquidations(candles, oi, atr=1.0) == []


def test_spring_candle_minute_comes_from_futures():
    spot = compute_indicators_batch({'X': frame([100.0] * 60, qv=[15_000.0] * 60)}, {})
    fut = compute_indicators_batch({'X': frame([100.0] * 60, qv=[150_000.0] * 60)}, {})
    row = PhaseScorer().calculate_scores(spot, fut).row(-1, named=True)
    assert row['candle_minute_usd'] == 1_000.0 and row['fut_candle_minute_usd'] == 10_000.0


def test_equal_pool_swept_long_ago_is_gone():
    levels = [RawLevel(110.0, 'swing_15m', 'a', +1, ts=0), RawLevel(110.05, 'swing_15m', 'b', +1, ts=60_000)]
    candles = [[k * 60_000, 100, 101, 99, 100] for k in range(40)]
    candles[5] = [5 * 60_000, 100, 112, 99, 100]                 # swept 35 candles ago (the old check saw 12)
    assert equal_pools(levels, candles, atr=1.0) == []


def test_target_needs_a_trade_through_and_funding_costs_r():
    lv = {'entry': 100, 'sl': 98, 'tp1': 104, 'tp2': 106, 'tp3': 108}
    touch = simulate(lv, 1, [[0, 100, 104.0, 99.5, 103], [60_000, 103, 103.5, 102, 103]], use_fill=False)
    assert touch['outcome'] == 'OPEN'                            # a touch of TP1 is not a fill
    assert funding_r(0.001, 1, 100, 2, 0, 9 * H) == 0.001 * 1 * 100 / 2   # one 8h settlement crossed
    assert funding_r(0.001, -1, 100, 2, 0, 9 * H) < 0            # shorts receive a positive rate


def test_bh_q_values():
    q = bh_q([0.01, 0.04, None, 0.5])
    assert q[2] is None and abs(q[0] - 0.03) < 1e-9 and q[1] <= q[3] == 0.5



def test_indicators_and_phases_do_not_look_ahead():
    # freqtrade-style look-ahead check: every value at a candle must be the same whether later candles exist or not
    import math
    import random
    rng = random.Random(3)
    n, close = 99, [100.0]
    for _ in range(n - 1):
        close.append(close[-1] * (1 + rng.gauss(0, 0.004)))
    qv = [1e5 * (1 + rng.random()) for _ in range(n)]
    delta = [rng.uniform(-3e4, 3e4) for _ in range(n)]
    oi = [1e6 * (1 + 0.001 * k + rng.gauss(0, 0.002)) for k in range(n)]
    full = frame(close, qv=qv, delta=delta, oi=oi)
    scorer = PhaseScorer()
    scored_full = scorer.calculate_scores(None, compute_indicators_batch({'X': full}, {}))
    for cut in (60, 80):
        part = scorer.calculate_scores(None, compute_indicators_batch({'X': full.head(cut)}, {}))
        a, b = scored_full.head(cut), part
        for col in ('atr', 'bb_upper', 'bb_lower', 'rvol', 'adx', 'oi_change_short', 'flow_flat', 'ret_std',
                    'is_squeezed', 'total_long_score', 'total_short_score'):
            for x, y in zip(a[col].to_list(), b[col].to_list()):
                if isinstance(x, float) and isinstance(y, float):
                    assert (math.isnan(x) and math.isnan(y)) or abs(x - y) <= 1e-9 * max(1.0, abs(x)), (col, cut)
                else:
                    assert x == y, (col, cut)
