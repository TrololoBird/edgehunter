import os
import sys
import time

import polars as pl
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from indicators import RAW_SCHEMA, TIMEFRAME_MS  # noqa: E402

N = 99
NOW = time.time()
CUR15 = int(NOW * 1000 // TIMEFRAME_MS * TIMEFRAME_MS)


def frame(close, open_=None, high=None, low=None, qv=None, delta=None, oi=None, t0=None) -> pl.DataFrame:
    """RAW_SCHEMA frame of 15m candles ending at the current 15m bucket."""
    n = len(close)
    t0 = CUR15 - (n - 1) * TIMEFRAME_MS if t0 is None else t0
    open_ = open_ or [close[max(i - 1, 0)] for i in range(n)]
    high = high or [max(o, c) * 1.0008 for o, c in zip(open_, close)]
    low = low or [min(o, c) * 0.9992 for o, c in zip(open_, close)]
    return pl.DataFrame({'timestamp': [t0 + i * TIMEFRAME_MS for i in range(n)], 'open': open_, 'high': high,
                         'low': low, 'close': close, 'volume': [1.0] * n, 'quote_volume': qv or [1e5] * n,
                         'taker_delta': delta or [0.0] * n, 'open_interest': oi or [1e6] * n}, schema=RAW_SCHEMA)


def h1_of(df):
    """The 1h candles of a 15m frame (the leg's timeframe needs its own ATR since the 2026-10-18 audit)."""
    rows, out = df.select(['timestamp', 'open', 'high', 'low', 'close']).rows(), {}
    for t, o, h, lo, c in rows:
        k = int(t) // 3_600_000 * 3_600_000
        b = out.setdefault(k, [k, o, h, lo, c, 1.0])
        b[2], b[3], b[4] = max(b[2], h), min(b[3], lo), c
    return list(out.values())


class Frames:
    """dict-like frame lookup for SignalBook.update."""

    def __init__(self, df):
        self.df = df

    def get(self, symbol):
        return self.df


# A 15m series with a clean up-leg and a pullback into the 0.382-0.786 zone
CHOP = [100 * (1 + 0.004 * ((i % 6) - 3) / 3) for i in range(60)]
RALLY = [100 + 1.0 * i for i in range(1, 21)]          # +20% over 5h
PULLBACK = [120 - 1.2 * i for i in range(1, 10)]        # back to ~109.2 (~0.54 retracement)
CLOSES = CHOP + RALLY + PULLBACK + [109.5] * 10


@pytest.fixture
def rally_frame():
    from indicators import compute_indicators
    return compute_indicators(frame(CLOSES[-N:]))


def minute(t0: int, i: int, o, h, l, c, q=1e4, Q=5e3):
    return [t0 + i * 60_000, o, h, l, c, q, Q]


@pytest.fixture(autouse=True)
def all_strategies_enabled(monkeypatch):
    """The tests exercise the lifecycle of every strategy: the deployment's disabled strategies / setups do not apply."""
    import dataclasses
    import config as config_mod
    from strategies import STRATEGIES
    monkeypatch.setattr(config_mod.CONFIG, 'strategies', dataclasses.replace(
        config_mod.CONFIG.strategies, enabled=tuple(STRATEGIES), disabled_setups=(), require_displacement=False))
    # the fixtures' impulses carry no z-score (unknown volatility): the logic is tested with the 1% floor they were built
    # for (eng-123 deploys z >= 6 alone; test_unknown_z_is_no_impulse covers that)
    monkeypatch.setattr(config_mod.CONFIG, 'tier0', dataclasses.replace(config_mod.CONFIG.tier0,
                                                                        price_change_5m_threshold=0.01))
    # NOTE: the lifecycle fixtures' prices were built for R:R 1 and the OLD 0.382-0.618 zone / 0.786 invalidation, so
    # they test the lifecycle, NOT the live continuation geometry (OTE 0.62-0.79, invalid beyond the leg's start)
    monkeypatch.setattr(config_mod.CONFIG, 'levels', dataclasses.replace(
        config_mod.CONFIG.levels, min_rr_tp1=1.0, continuation_zone=(0.382, 0.618), continuation_invalid=0.786))
    monkeypatch.setattr(config_mod.CONFIG, 'orderflow', dataclasses.replace(config_mod.CONFIG.orderflow,
                                                                            min_confirmations=0))


@pytest.fixture(autouse=True)
def _no_optimized_profiles(monkeypatch):
    """The lifecycle tests judge the methods' own plans: the optimized profiles (models/profiles*.json, rewritten
    by every research_optimize run) are switched off."""
    from strategies import profiles
    monkeypatch.setattr(profiles, 'select', lambda strategy, regime: (None, None))
