#!/usr/bin/env python3
"""
Statistics over the signal journal (signals.db): what the price did after each kind of signal.

    python stats.py                 # rows of the current signal logic (CONFIG.journal.logic_version)
    python stats.py --all-versions  # every row, including older logic
    python stats.py --days 7        # last 7 days
    python stats.py --last 30       # also list the 30 most recent signals with their outcomes

Returns are measured from the futures last price at the signal, in the signal's direction: for BEAR / IMPULSE
DOWN a falling price counts as a gain. "Net" figures subtract the round-trip fee (CONFIG.journal.fee_round_trip).

Market baseline: the MEAN return of the WHOLE universe over the same window (not the median: coins beat the median
by ~0.11% per 4h on average - right-skewed returns - which made every long look good and every short bad), from the price snapshots the
scanner stores every 15 minutes (older databases without snapshots fall back to the mean of the coins logged in
the same hour). "Edge" is a setup's return in its direction minus that baseline, so a falling market doesn't make
every short look good. [lo..hi] = 90% bootstrap interval of the mean: an interval that straddles 0 means the
sample cannot tell the setup from noise yet.
"""
import re
import argparse
import bisect
import json
import math
import os
import random
import sqlite3
import statistics
import time
from datetime import datetime

import numpy as np
from typing import Callable, Dict, List, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.text import Text

from config import CONFIG
from journal import HORIZONS
from strategies import SETUPS

MIN_SAMPLE = 30
BOOTSTRAP = 1000


def pct(value: Optional[float], digits: int = 2, colored: bool = True) -> Text:
    if value is None:
        return Text("—", style="dim")
    style = ("green" if value > 0 else "red" if value < 0 else "white") if colored else "white"
    return Text(f"{value * 100:+.{digits}f}%", style=style)


def rate(value: Optional[float]) -> Text:
    if value is None:
        return Text("—", style="dim")
    style = "bold green" if value >= 0.55 else "bold red" if value <= 0.45 else "white"
    return Text(f"{value * 100:.0f}%", style=style)


def cluster_of(row) -> tuple:
    """
    Signals of one direction whose 4h outcome windows overlap ride the same market move (15 breakouts at one close,
    the next closes of the same move): one 4h block of one direction is one cluster, and the bootstrap resamples
    clusters (block bootstrap) - intervals of overlapping labels, not of independent rows.
    """
    return row['ts_ms'] // (4 * 3_600_000), row['direction']


def bootstrap_ci(values: List[float], stat: Callable = statistics.fmean, seed: int = 7,
                 clusters: Optional[List] = None) -> Optional[Tuple[float, float]]:
    """90% percentile bootstrap interval of `stat`; with `clusters` (one key per value) whole clusters are resampled."""
    groups: Dict = {}
    for i, v in enumerate(values):
        groups.setdefault(clusters[i] if clusters is not None else i, []).append(v)
    blocks = list(groups.values())
    if len(blocks) < 5:
        return None
    k = len(blocks)
    if stat is statistics.fmean:
        means = np.sort(_block_means(blocks, seed))
        return float(means[int(0.05 * BOOTSTRAP)]), float(means[int(0.95 * BOOTSTRAP) - 1])
    rng = random.Random(seed)
    draws = sorted(stat([v for _ in range(k) for v in blocks[rng.randrange(k)]]) for _ in range(BOOTSTRAP))
    return draws[int(0.05 * BOOTSTRAP)], draws[int(0.95 * BOOTSTRAP) - 1]


def _block_means(blocks: List[List[float]], seed: int) -> 'np.ndarray':
    """BOOTSTRAP resampled means of whole blocks, vectorized: a draw's mean = the drawn blocks' sum / their count
    (the Python loop took 24s of a 38s report over 90 days)."""
    sums = np.fromiter((sum(b) for b in blocks), dtype=float, count=len(blocks))
    counts = np.fromiter((len(b) for b in blocks), dtype=float, count=len(blocks))
    idx = np.random.default_rng(seed).integers(0, len(blocks), size=(BOOTSTRAP, len(blocks)))
    return sums[idx].sum(axis=1) / counts[idx].sum(axis=1)


def ci_text(values: List[float], scale: float = 100, suffix: str = "%", stat: Callable = statistics.fmean,
            clusters: Optional[List] = None) -> Text:
    ci = bootstrap_ci(values, stat, clusters=clusters)
    if ci is None:
        return Text("")
    lo, hi = ci
    style = "green" if lo > 0 else "red" if hi < 0 else "dim"
    return Text(f" [{lo * scale:+.1f}..{hi * scale:+.1f}{suffix}]", style=style)


def hour_key(row) -> int:
    return row['ts_ms'] // 3_600_000


# ---------------------------------------------------------------------- market baseline

class UniverseBaseline:
    """Mean return of every universe coin between the snapshots nearest t and t + horizon (see ret)."""

    MAX_GAP_MS = 20 * 60_000

    def __init__(self, conn: sqlite3.Connection, since_ms: Optional[int] = None):
        self.snapshots: Dict[int, Dict[str, float]] = {}
        self.since_ms = since_ms
        try:
            # since_ms: only the window a caller needs - the dashboard loaded the WHOLE table (1.2M rows, ~100 MB of
            # dicts, rebuilt every 10 min and growing ~280k rows a day: the live bot's memory growth, eng-74)
            q, args = ("SELECT ts_ms, symbol, price FROM universe WHERE ts_ms >= ? ORDER BY ts_ms", (since_ms,))                 if since_ms is not None else ("SELECT ts_ms, symbol, price FROM universe ORDER BY ts_ms", ())
            for ts, symbol, price in conn.execute(q, args):
                self.snapshots.setdefault(ts, {})[symbol] = price
        except sqlite3.OperationalError:
            pass
        self.times = sorted(self.snapshots)
        self._cache: Dict[Tuple[int, int], Optional[float]] = {}

    def __bool__(self):
        return len(self.times) >= 2

    def _at(self, ts: int) -> Optional[int]:
        """The snapshot nearest to ts (either side), within MAX_GAP_MS."""
        i = bisect.bisect_left(self.times, ts)
        near = [t for t in self.times[max(0, i - 1):i + 1] if abs(t - ts) <= self.MAX_GAP_MS]
        return min(near, key=lambda t: abs(t - ts)) if near else None

    def ret(self, ts: int, minutes: int) -> Optional[float]:
        t0, t1 = self._at(ts), self._at(ts + minutes * 60_000)
        if t0 is None or t1 is None or t0 == t1:
            return None
        key = (t0, t1)
        if key not in self._cache:
            a, b = self.snapshots[t0], self.snapshots[t1]
            changes = [b[s] / a[s] - 1 for s in a if s in b and a[s]]
            # the MEAN: coins beat the median by ~0.11% per 4h on average (right-skewed returns), so an Edge against
            # the median favoured every long and penalised every short; an equal-weight universe has zero mean excess
            self._cache[key] = statistics.fmean(changes) if len(changes) >= 20 else None
        return self._cache[key]


class BetaEstimator:
    """
    Each coin's beta to the universe mean from the snapshots of the 7 days BEFORE a signal (hourly returns, OLS,
    Blume-adjusted toward 1: 0.67 x beta + 0.33). Signals are picked on volatile coins (impulses, cascades), and a coin
    with beta 2 in a falling market "beats" the mean on a short without any skill: Edge beta = the return in the
    signal's direction minus beta x the mean. None (plain Edge) with fewer than 48 hourly points.
    """

    HOUR_MS = 3_600_000
    LOOKBACK_H = 7 * 24
    MIN_POINTS = 48

    def __init__(self, universe: 'UniverseBaseline'):
        self.hours: List[int] = []
        self.market: Dict[int, float] = {}               # hour -> mean hourly return
        self.coin: Dict[str, Dict[int, float]] = {}      # symbol id -> hour -> hourly return
        self._cache: Dict[Tuple[str, int], Optional[float]] = {}
        if not universe:
            return
        hourly: Dict[int, Dict[str, float]] = {}
        for t in universe.times:                        # the first snapshot of each hour
            h = t // self.HOUR_MS
            if h not in hourly:
                hourly[h] = universe.snapshots[t]
        self.hours = sorted(hourly)
        for prev, h in zip(self.hours, self.hours[1:]):
            if h != prev + 1:
                continue
            a, b = hourly[prev], hourly[h]
            changes = {sym: b[sym] / a[sym] - 1 for sym in a if sym in b and a[sym]}
            if len(changes) < 20:
                continue
            self.market[h] = statistics.fmean(changes.values())
            for sym, v in changes.items():
                self.coin.setdefault(sym, {})[h] = v

    @staticmethod
    def symbol_id(symbol: str) -> str:
        """'1000PEPE/USDT:USDT' -> '1000PEPEUSDT' (the snapshots store Binance ids)."""
        return symbol.split('/')[0] + 'USDT' if '/' in symbol else symbol

    def beta(self, symbol: str, ts_ms: int) -> Optional[float]:
        sym, day = self.symbol_id(symbol), ts_ms // 86_400_000
        key = (sym, day)                                  # one estimate per coin and day (cached)
        if key in self._cache:
            return self._cache[key]
        end = day * 24                                    # hours before the signal's day: no overlap with the label
        series = self.coin.get(sym, {})
        pairs = [(self.market[h], series[h]) for h in range(end - self.LOOKBACK_H, end) if h in self.market and h in series]
        value = None
        if len(pairs) >= self.MIN_POINTS:
            m = [x for x, _ in pairs]
            c = [y for _, y in pairs]
            mm, mc = statistics.fmean(m), statistics.fmean(c)
            var = sum((x - mm) ** 2 for x in m)
            if var > 0:
                raw = sum((x - mm) * (y - mc) for x, y in zip(m, c)) / var
                value = 0.67 * raw + 0.33
        self._cache[key] = value
        return value


def bootstrap_p(values: List[float], clusters: Optional[List] = None, seed: int = 11) -> Optional[float]:
    """Two-sided block-bootstrap p-value of "the mean is 0" (whole clusters resampled, like bootstrap_ci)."""
    groups: Dict = {}
    for i, v in enumerate(values):
        groups.setdefault(clusters[i] if clusters is not None else i, []).append(v)
    blocks = list(groups.values())
    if len(blocks) < 5:
        return None
    means = _block_means(blocks, seed)
    below = float((means <= 0).mean())
    return min(1.0, 2 * min(below, 1 - below) + 1 / BOOTSTRAP)


def bh_q(pvalues: List[Optional[float]]) -> List[Optional[float]]:
    """Benjamini-Hochberg q-values of the p-values given (None stays None): the false discovery rate at which each
    result would be called significant when all of them are looked at together."""
    idx = sorted((p, i) for i, p in enumerate(pvalues) if p is not None)
    m = len(idx)
    q: List[Optional[float]] = [None] * len(pvalues)
    running = 1.0
    for rank in range(m, 0, -1):
        p, i = idx[rank - 1]
        running = min(running, p * m / rank)
        q[i] = running
    return q


def market_baseline(rows: List) -> Dict[str, Dict[int, float]]:
    """Fallback: per horizon, the mean raw return of all rows logged in the same hour."""
    baseline: Dict[str, Dict[int, float]] = {}
    for label in HORIZONS:
        buckets: Dict[int, List[float]] = {}
        for r in rows:
            if r[f'ret_{label}'] is not None:
                buckets.setdefault(hour_key(r), []).append(r[f'ret_{label}'])
        baseline[label] = {h: statistics.fmean(v) for h, v in buckets.items() if len(v) >= 5}
    return baseline


class Baseline:
    def __init__(self, rows: List, universe: Optional[UniverseBaseline] = None):
        self.universe = universe if universe else None
        self.fallback = market_baseline(rows)
        # the coins' betas need the universe snapshots (the fallback baseline has no per-coin history)
        self.betas = BetaEstimator(self.universe) if self.universe else None

    @property
    def source(self) -> str:
        return "whole-universe mean (snapshots)" if self.universe else "mean of logged coins per hour (no snapshots yet)"

    def of(self, row, label: str) -> Optional[float]:
        if self.universe:
            return self.universe.ret(row['ts_ms'], HORIZONS[label])
        return self.fallback[label].get(hour_key(row))


# ---------------------------------------------------------------------- per-group statistics

def excess_pairs(rows: List, label: str, baseline: Baseline, beta: bool = False) -> Tuple[List[float], List]:
    """Excess returns and their clusters (cluster_of); beta: the baseline scaled by the coin's beta (BetaEstimator)."""
    values, clusters = [], []
    betas = getattr(baseline, 'betas', None) if beta else None
    for r in rows:
        if r[f'ret_{label}'] is None or not r['direction']:
            continue
        base = baseline.of(r, label)
        if base is not None:
            b = betas.beta(r['symbol'], r['ts_ms']) if betas is not None else None
            values.append(r['direction'] * (r[f'ret_{label}'] - (b if b is not None else 1.0) * base))
            clusters.append(cluster_of(r))
    return values, clusters


def excess(rows: List, label: str, baseline: Baseline) -> List[float]:
    return excess_pairs(rows, label, baseline)[0]


def group_stats(rows: List, baseline) -> Dict:
    if isinstance(baseline, dict):  # legacy call: {label: {hour: median}}
        legacy = baseline
        baseline = Baseline([])
        baseline.fallback = legacy
    direction = rows[0]['direction']
    fee = CONFIG.journal.fee_round_trip
    out = {'n': len(rows), 'direction': direction}
    for label in HORIZONS:
        values = [r[f'ret_{label}'] for r in rows if r[f'ret_{label}'] is not None]
        out[f'n_{label}'] = len(values)
        if not values:
            out[f'win_{label}'] = out[f'avg_{label}'] = out[f'med_{label}'] = out[f'edge_{label}'] = None
            out[f'edge_values_{label}'] = []
            out[f'edge_clusters_{label}'] = []
            continue
        if direction:
            signed = [v * direction for v in values]
            out[f'win_{label}'] = sum(1 for v in signed if v > fee) / len(signed)
            out[f'avg_{label}'] = statistics.fmean(signed)
            out[f'med_{label}'] = statistics.median(signed)
            ex, clusters = excess_pairs(rows, label, baseline)
            out[f'edge_{label}'] = statistics.fmean(ex) if ex else None
            if label == '4h' and getattr(baseline, 'betas', None) is not None:
                bx, bclusters = excess_pairs(rows, label, baseline, beta=True)
                out['edge_beta_4h'] = statistics.fmean(bx) if bx else None
                out['edge_beta_values_4h'], out['edge_beta_clusters_4h'] = bx, bclusters
            out[f'edge_values_{label}'] = ex
            out[f'edge_clusters_{label}'] = clusters
        else:
            # No direction: share of up moves, and the average size of the move either way
            out[f'win_{label}'] = sum(1 for v in values if v > 0) / len(values)
            out[f'avg_{label}'] = statistics.fmean(abs(v) for v in values)
            out[f'med_{label}'] = statistics.median(values)
            out[f'edge_{label}'] = None
            out[f'edge_values_{label}'] = []
            out[f'edge_clusters_{label}'] = []

    done = [r for r in rows if r['mfe_4h'] is not None]
    if done:
        if direction >= 0:
            favorable = [r['mfe_4h'] for r in done]
            adverse = [r['mae_4h'] for r in done]
        else:
            favorable = [-r['mae_4h'] for r in done]
            adverse = [-r['mfe_4h'] for r in done]
        out['mfe'] = statistics.fmean(favorable)
        out['mae'] = statistics.fmean(adverse)
    else:
        out['mfe'] = out['mae'] = None
    return out


def _col(row, name: str, default=None):
    return row[name] if name in row.keys() else default


def net_r(row, col: str) -> Optional[float]:
    """R result minus the round-trip fee expressed in R (fee x entry / risk)."""
    r = _col(row, col)
    entry = _col(row, 'entry_fill') or _col(row, 'entry')
    sl = _col(row, 'sl')
    if r is None or not entry or sl is None or entry == sl:
        return r
    return r - CONFIG.journal.fee_round_trip * entry / abs(entry - sl)


# ---------------------------------------------------------------------- tables

def levels_table(console: Console, groups: Dict[str, List]):
    """Replay of every entry (ENTRY rows) per setup, filled like a human (next minute + slippage), fees included."""
    table = Table(title="Entries replayed on 1m candles (4h, manual fill, net of fees)", header_style="bold magenta",
                  border_style="blue")
    for name in ("Setup", "Entries", "Skipped", "LOW RR", "SL first", "TP1+", "TP2+", "TP3", "Avg R @TP1", "Med R @TP1",
                 "Avg R @TP2", "Avg R BE"):
        table.add_column(name, justify="left" if name == "Setup" else "right", no_wrap=True)
    shown = False
    for key in sorted(groups):
        rows = [r for r in groups[key] if _col(r, 'outcome') is not None]
        if not rows:
            continue
        shown = True
        filled = [r for r in rows if r['filled']]
        skipped = sum(1 for r in rows if r['outcome'] == 'SKIPPED')

        def share(pred, bad: bool = False) -> Text:
            if not filled:
                return Text("—", style="dim")
            value = sum(1 for r in filled if pred(r['outcome'])) / len(filled)
            # rate() colors high shares green; for the stop column a high share is the bad case
            return Text(f"{value * 100:.0f}%", style="red" if value >= 0.55 else "white") if bad else rate(value)

        def avg_r(col: str, median: bool = False) -> Text:
            pairs = [(v, cluster_of(r)) for r in filled if (v := net_r(r, col)) is not None]
            if not pairs:
                return Text("—", style="dim")
            values = [v for v, _ in pairs]
            value = statistics.median(values) if median else statistics.fmean(values)
            text = Text(f"{value:+.2f}R", style="green" if value > 0 else "red")
            if not median:
                text.append_text(ci_text(values, scale=1, suffix="R", clusters=[c for _, c in pairs]))
            return text

        low_rr = sum(1 for r in rows if _col(r, 'low_rr'))
        table.add_row(
            key,
            Text(str(len(filled)), style="dim" if len(filled) < MIN_SAMPLE else "white"),
            Text(f"{skipped}", style="dim"),
            Text(f"{low_rr}", style="dim"),
            share(lambda o: o == 'SL', bad=True),
            share(lambda o: o in ('TP1', 'TP2', 'TP3')),
            share(lambda o: o in ('TP2', 'TP3')),
            share(lambda o: o == 'TP3'),
            avg_r('r_tp1'),
            avg_r('r_tp1', median=True),
            avg_r('r_tp2'),
            avg_r('r_be'),
        )
    if shown:
        console.print(table)
        console.print(
            "[dim]Entries are filled at the open of the first full minute after the trigger plus slippage (a human "
            "reacting), Skipped = that price was already beyond the stop / first target. SL first / TPk+ = share of "
            "entries where the stop or target k was hit first (SL wins ties inside a candle).\nAvg / Med R @TPk = "
            "result in stop units when exiting everything at TPk, net of fees (open trades marked to the 4h close); "
            "R BE = the same trade with the stop moved to the entry once TP1 traded, exited at TP2 (compared, not live); "
            "[lo..hi] = 90% bootstrap interval. Only meaningful with N >= 30. Vetoed entries (✗) were not shown on "
            "screen: compare them with the passed ones to judge the filter.[/dim]"
        )


def _family(row) -> Optional[str]:
    """Strategy of a directional row ('ENTRY <setup>' rows too); None for anomaly labels without one."""
    key = row['group_key'][6:] if row['group_key'].startswith('ENTRY ') else row['group_key']
    entry = SETUPS.get(key)
    return entry[0] if entry else None


def _confirm_value(row, name: str) -> Optional[str]:
    raw = _col(row, 'confirms')
    if not raw:
        return None
    value = json.loads(raw).get(name)
    if value is None:
        return None
    if value == 'n/a':
        return 'n/a'
    return 'yes' if value is True or isinstance(value, str) else 'no'


# the nature of each method (its source's own logic): what price must do after the entry
NATURE = {'continuation': 'trend', 'breakout': 'trend', 'orb': 'trend', 'trendline': 'trend', 'cup_handle': 'trend',
          'oi_signal': 'trend', 'pump': 'trend', 'connors': 'reversion', 'market_profile': 'reversion',
          'bollinger': 'reversion', 'supply_demand': 'reversion', 'sweep': 'reversal', 'wyckoff': 'reversal',
          'po3': 'reversal'}


FEATURES: List[Tuple[str, Callable[[sqlite3.Row], Optional[str]]]] = [
    ('strategy', _family),
    ('market 1h vs the signal', lambda r: None if _col(r, 'mkt_1h') is None or not _col(r, 'direction') else
        ('with (> +0.2%)' if _col(r, 'mkt_1h') * _col(r, 'direction') > 0.002 else
         'against (< -0.2%)' if _col(r, 'mkt_1h') * _col(r, 'direction') < -0.002 else 'flat')),
    ('coin 1h trend vs the signal', lambda r: None if _col(r, 'coin_trend') is None or not _col(r, 'direction') else
        ('with' if _col(r, 'coin_trend') * _col(r, 'direction') > 0 else
         'against' if _col(r, 'coin_trend') * _col(r, 'direction') < 0 else 'none')),
    # the weekly trend (price vs the weekly EMA in weekly std) and the market's weekly breadth, both vs the signal:
    # touches in a strong weekly trend bounced 55-58% vs ~50% (history test 2026-09-27) - does it carry to 4h?
    ('coin weekly trend vs the signal', lambda r: None if _col(r, 'trend_w') is None or not _col(r, 'direction') else
        ('strongly with (>= 1 sd)' if _col(r, 'trend_w') * _col(r, 'direction') >= 1 else
         'with (0..1 sd)' if _col(r, 'trend_w') * _col(r, 'direction') >= 0 else
         'against (0..-1 sd)' if _col(r, 'trend_w') * _col(r, 'direction') > -1 else 'strongly against (<= -1 sd)')),
    ('market weekly breadth vs the signal', lambda r: None if _col(r, 'breadth_w') is None or not _col(r, 'direction') else
        (('long' if _col(r, 'direction') > 0 else 'short') + ' / ' +
         ('broad >= 60%' if _col(r, 'breadth_w') >= 0.6 else 'narrow <= 30%' if _col(r, 'breadth_w') <= 0.3 else 'mixed'))),
    # eng-4 (audit): time of day (volume / volatility peak at the US open), weekends (spreads x2, volume -20-40%),
    # a pullback zone on a real map level vs Fibonacci alone, what the sweep candle liquidated, funding vs the signal
    ('session (UTC)', lambda r: None if _col(r, 'hour_utc') is None else
        ('Asia 0-7' if _col(r, 'hour_utc') < 7 else 'London 7-13' if _col(r, 'hour_utc') < 13 else
         'NY 13-21' if _col(r, 'hour_utc') < 21 else 'late 21-24')),
    ('ADX14 (15m)', lambda r: None if _col(r, 'adx') is None else
        ('trending >= 30' if _col(r, 'adx') >= 30 else 'weak < 20' if _col(r, 'adx') < 20 else '20-30')),
    # eng-59 (the pool audit): does the method suit the coin's state? Dreiss' Choppiness of the coin's last hours
    # (> 61.8 a range, < 38.2 a trend - his levels) against the method's nature: trend methods should do better in a
    # trending coin, mean-reversion ones in a ranging one. Journal first, a pool / veto rule only once it is proven
    ('method nature x coin state (Choppiness 1h)', lambda r: None if _col(r, 'chop_1h') is None
        or NATURE.get(_col(r, 'strategy') or '') is None else
        f"{NATURE[_col(r, 'strategy')]} method in a " +
        ('ranging coin (> 61.8)' if _col(r, 'chop_1h') > 61.8 else 'trending coin (< 38.2)' if _col(r, 'chop_1h') < 38.2
         else 'mixed coin')),
    # eng-59 flow microstructure (journal only): who moved first, and VPIN's flow toxicity (Easley et al.: ~0.2-0.3
    # is normal for liquid futures; the cut is ours and only splits the journal)
    ('leading venue (1h)', lambda r: _col(r, 'lead_venue') if (_col(r, 'lead_corr') or 0) > 0.2 else
        ('none (corr <= 0.2)' if _col(r, 'lead_corr') is not None else None)),
    ('VPIN (1h)', lambda r: None if _col(r, 'vpin') is None else ('high >= 0.4' if _col(r, 'vpin') >= 0.4 else 'normal')),
    ('BTC bias vs the signal', lambda r: None if not _col(r, 'btc_bias') or not _col(r, 'direction') else
        ('with BTC' if _col(r, 'btc_bias') * _col(r, 'direction') > 0 else 'against BTC')),
    ('weekend', lambda r: None if _col(r, 'weekend') is None else ('weekend' if _col(r, 'weekend') else 'weekday')),
    ('pullback zone', lambda r: None if not _col(r, 'zone_src') or _col(r, 'kind') != 'entry' else
        ('Fibonacci only' if 'fib only' in _col(r, 'zone_src') else 'map level')),
    ('sweep: liquidations on the wick', lambda r: None if _col(r, 'liq_on_wick') is None else
        ('>= $50k' if _col(r, 'liq_on_wick') >= 50_000 else '> 0' if _col(r, 'liq_on_wick') > 0 else 'none')),
    ('funding vs the signal', lambda r: None if _col(r, 'agg_funding_8h') is None or not _col(r, 'direction') else
        ('crowded with (>= +0.03%)' if _col(r, 'agg_funding_8h') * _col(r, 'direction') >= 0.0003 else
         'crowded against (<= -0.03%)' if _col(r, 'agg_funding_8h') * _col(r, 'direction') <= -0.0003 else 'neutral')),
    ('coin 24h volume', lambda r: None if not _col(r, 'volume_24h') else
        ('< $10M' if _col(r, 'volume_24h') < 10e6 else '$10-50M' if _col(r, 'volume_24h') < 50e6 else
         '$50-250M' if _col(r, 'volume_24h') < 250e6 else '>= $250M')),
    ('volatility (last hour / ATR14)', lambda r: None if _col(r, 'vol_ratio') is None else
        ('expanding >= 1.3' if _col(r, 'vol_ratio') >= 1.3 else 'contracting <= 0.8' if _col(r, 'vol_ratio') <= 0.8 else 'normal')),
    ('market crowd', lambda r: None if _col(r, 'market_crowd') is None else
        (f"market move (>= {CONFIG.market.cluster_min} coins)" if _col(r, 'market_crowd') >= CONFIG.market.cluster_min
         else 'own move')),
    ('vetoed', lambda r: _col(r, 'vetoed') or 'passed'),
    ('perp-led', lambda r: None if _col(r, 'perp_led') is None else ('perp-led' if _col(r, 'perp_led') else 'spot-confirmed')),
    ('liquidations 5m', lambda r: None if _col(r, 'liq_long_5m') is None else
        ('>= $50k' if (_col(r, 'liq_long_5m') or 0) + (_col(r, 'liq_short_5m') or 0) >= 50_000 else '< $50k')),
    ('multi-venue flow', lambda r: None if _col(r, 'agg_ready') is None else ('aggregate' if _col(r, 'agg_ready') else 'binance only')),
    ('quarter-hour', lambda r: None if _col(r, 'sec_into_candle') is None else
        ('first 60s' if (_col(r, 'sec_into_candle') or 0) < 60 else 'later')),
    ('entry type', lambda r: None if _col(r, 'kind') != 'entry' else
        ('at the confirmation' if _col(r, 'zone_src') == 'setup confirmation' else 'trigger in the zone')),
    ('order-flow confirm', lambda r: _col(r, 'of_confirm') or ('none' if _col(r, 'kind') == 'entry' else None)),
    # entry confirmations (strategies/confirm.py): each one's Edge with and without it; the journal promotes one to
    # required for a strategy once entries without it prove negative
    *[(f"confirm: {name}", (lambda n: lambda r: _confirm_value(r, n))(name)) for name in ('flow', 'spot', 'oi', 'orderflow')],
    ('ICT premium / discount (entry in the 48h range)', lambda r: None if _col(r, 'range_pos') is None else
        ('deep discount < 30%' if _col(r, 'range_pos') < 0.3 else 'discount 30-50%' if _col(r, 'range_pos') < 0.5
         else 'premium >= 50%')),
    ('BTC DVOL 1h change (Deribit)', lambda r: None if _col(r, 'dvol_chg_1h') is None else
        ('vol rising >= +1' if _col(r, 'dvol_chg_1h') >= 1 else 'vol falling <= -1' if _col(r, 'dvol_chg_1h') <= -1 else 'flat')),
    ('funding spread across venues', lambda r: None if _col(r, 'funding_spread') is None else
        ('wide >= 0.03% / 8h' if _col(r, 'funding_spread') >= 0.0003 else 'narrow')),
    ('OKX + Bybit books vs the signal', lambda r: None if _col(r, 'okx_book_imb') is None or _col(r, 'direction') is None else
        ('books with it' if _col(r, 'direction') * ((_col(r, 'okx_book_imb') or 0) + (_col(r, 'bybit_book_imb') or 0)) > 0.1
         else 'books against it' if _col(r, 'direction') * ((_col(r, 'okx_book_imb') or 0) + (_col(r, 'bybit_book_imb') or 0)) < -0.1
         else 'balanced')),
    ('icebergs (hidden limit orders) vs the signal', lambda r: None if not _col(r, 'iceberg_n_5m') or _col(r, 'direction') is None else
        ('iceberg on its side' if _col(r, 'direction') * (_col(r, 'iceberg_net_5m') or 0) > 0 else 'iceberg against it')),
    ('confirmations positive', lambda r: None if _col(r, 'conf_n') is None else f"{_col(r, 'conf_n')} of 4"),
    ('market regime', lambda r: _col(r, 'regime')),
    ('P(edge) model', lambda r: None if _col(r, 'p_edge') is None else ('p >= 0.5' if _col(r, 'p_edge') >= 0.5 else 'p < 0.5')),
    ('P(trade) model (eng-174)', lambda r: None if _col(r, 'p_trade') is None else ('p >= 0.5' if _col(r, 'p_trade') >= 0.5 else 'p < 0.5')),
    ('crowd (Binance L/S accounts)', lambda r: None if _col(r, 'ls_global') is None else
        ('crowd long >= 2' if _col(r, 'ls_global') >= 2 else 'crowd short <= 1' if _col(r, 'ls_global') <= 1 else 'mixed')),
    ('HL large accounts', lambda r: None if not _col(r, 'hl_net_usd') or not _col(r, 'direction') else
        ('with the signal' if _col(r, 'hl_net_usd') * _col(r, 'direction') > 0 else 'against the signal')),
    ('Coinbase premium', lambda r: None if _col(r, 'cb_premium') is None else
        ('> +0.05%' if _col(r, 'cb_premium') > 0.0005 else '< -0.05%' if _col(r, 'cb_premium') < -0.0005 else 'flat')),
    # eng-57: Weis's effort into the spring / upthrust vs the range's earlier waves (< 1 = supply / demand drying up)
    ('Weis wave into the test (wyckoff)', lambda r: None if _col(r, 'weis_ratio') is None else
        ('< 0.8 (drying up)' if _col(r, 'weis_ratio') < 0.8 else '0.8-1.2' if _col(r, 'weis_ratio') <= 1.2 else '> 1.2 (effort)')),
]


def features_table(console: Console, rows: List, baseline: Baseline):
    """Edge 4h of directional rows split by each recorded feature: does the filter / context add anything?"""
    directional = [r for r in rows if r['direction'] and r['ret_4h'] is not None and r['kind'] != 'card']
    if not directional:
        return
    table = Table(title="Edge 4h by feature (directional signals)", header_style="bold magenta", border_style="blue")
    for name in ("Feature", "Value", "N", "Edge 4h", "90% interval", "q"):
        table.add_column(name, justify="left" if name in ("Feature", "Value") else "right", no_wrap=True)
    rows_out = []
    for feature, key in FEATURES:
        buckets: Dict[str, List] = {}
        for r in directional:
            value = key(r)
            if value is not None:
                buckets.setdefault(value, []).append(r)
        if len(buckets) < 2 and feature != 'vetoed':
            continue
        for value, members in sorted(buckets.items()):
            ex, clusters = excess_pairs(members, '4h', baseline)
            rows_out.append((feature, value, ex, clusters))
            feature = ""
    # q-values over every bucket of every feature: the splits are many tests at once
    qs = bh_q([bootstrap_p(ex, clusters) for _, _, ex, clusters in rows_out])
    for (feature, value, ex, clusters), q in zip(rows_out, qs):
        edge = statistics.fmean(ex) if ex else None
        table.add_row(feature, value, Text(str(len(ex)), style="dim" if len(ex) < MIN_SAMPLE else "white"),
                      pct(edge), ci_text(ex, clusters=clusters),
                      Text("—" if q is None else f"{q:.2f}", style="dim" if q is None or q > 0.10 else "bold"))
    console.print(table)
    console.print("[dim]q = Benjamini-Hochberg q-value over every bucket above (bold: <= 0.10). A bucket with a green "
                  "interval but a large q is what chance produces among this many splits.[/dim]")


SOURCE_KINDS = (('EQH', 'equal highs/lows'), ('EQL', 'equal highs/lows'), ('PDH', 'day high/low'),
                ('PDL', 'day high/low'), ('day ', 'day high/low'), ('POC', 'volume profile'), ('VAH', 'volume profile'),
                ('VAL', 'volume profile'), ('HVN', 'volume profile'), ('liq est', 'liquidations (est.)'),
                ('liq ', 'liquidations (seen)'), ('wall', 'order-book wall'), ('VWAP', 'VWAP'), ('fib', 'fibonacci'),
                ('range', 'range edge'), ('15m', 'swing'), ('1h', 'swing'), ('bid liquidity', 'book liquidity'),
                ('ask liquidity', 'book liquidity'), ('measured move', 'measured move'), ('ATR step', 'ATR step'),
                ('HL', 'liquidations (HL accounts)'))


def source_kind(label: Optional[str]) -> Optional[str]:
    """The strongest source of a level label ('EQH×2 · PDH · fib 0.5' -> 'equal highs/lows')."""
    if not label:
        return None
    first = label.split(' · ')[0]
    for prefix, kind in SOURCE_KINDS:
        if first.startswith(prefix):
            return kind
    return 'other'


def sources_table(console: Console, rows: List):
    """How often TP1 was reached, per the source of TP1 (entry rows with a replay): which level kinds hold up?"""
    entries = [r for r in rows if r['kind'] == 'entry' and _col(r, 'outcome') not in (None, 'SKIPPED', 'OPEN')
               and _col(r, 'tp1_src')]
    if not entries:
        return
    table = Table(title="TP1 reached by level source (entry replays, 4h)", header_style="bold magenta", border_style="blue")
    for name in ("TP1 source", "Entries", "TP1+", "SL first", "Avg R @TP1"):
        table.add_column(name, justify="left" if name == "TP1 source" else "right", no_wrap=True)
    buckets: Dict[str, List] = {}
    for r in entries:
        buckets.setdefault(source_kind(r['tp1_src']), []).append(r)
    for kind, members in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        hit = sum(1 for r in members if r['outcome'] in ('TP1', 'TP2', 'TP3')) / len(members)
        sl = sum(1 for r in members if r['outcome'] == 'SL') / len(members)
        values = [v for r in members if (v := net_r(r, 'r_tp1')) is not None]
        avg = Text(f"{statistics.fmean(values):+.2f}R", style="green" if statistics.fmean(values) > 0 else "red") \
            if values else Text("—", style="dim")
        table.add_row(kind, Text(str(len(members)), style="dim" if len(members) < MIN_SAMPLE else "white"),
                      rate(hit), Text(f"{sl * 100:.0f}%"), avg)
    console.print(table)


REVERSAL_SETUPS = ('SWEEP LOW', 'SWEEP HIGH', 'SILVER BULLET LONG', 'SILVER BULLET SHORT', 'SPRING', 'UTAD',
                   'FLUSH REVERSAL', 'SQUEEZE REVERSAL', 'BB W-BOTTOM', 'BB M-TOP')


def reversal_test_table(console: Console, rows: List):
    """
    Mahadzva's test (SSRN 2026, G10 FX: a swept level predicted CONTINUATION in 65 of 66 folds) on our journal: every
    reversal setup (passed or vetoed) with the move afterwards in the signal's direction. A negative mean = price
    continued the swept move: the reversal reading is wrong and the opposite side would have paid.
    """
    sets = [r for r in rows if r['kind'] == 'setup' and r['group_key'] in REVERSAL_SETUPS]
    if not sets:
        return
    table = Table(title="Reversal setups: reversal or continuation? (move in the signal's direction)",
                  header_style="bold magenta", border_style="blue")
    for name in ("Setup", "N", "1h", "4h", "4h > 0", "90% (4h)", "Reading"):
        table.add_column(name, justify="left" if name in ("Setup", "Reading") else "right", no_wrap=True)
    for key in REVERSAL_SETUPS:
        members = [r for r in sets if r['group_key'] == key and r['ret_4h'] is not None]
        if not members:
            continue
        r1 = [r['direction'] * r['ret_1h'] for r in members if r['ret_1h'] is not None]
        r4 = [r['direction'] * r['ret_4h'] for r in members]
        mean4 = statistics.fmean(r4)
        lo_hi = bootstrap_ci(r4, clusters=[cluster_of(r) for r in members]) if len(r4) >= 5 else None
        reading = '—' if lo_hi is None else ('continuation' if lo_hi[1] < 0 else 'reversal' if lo_hi[0] > 0 else "can't tell")
        table.add_row(key, Text(str(len(r4)), style="dim" if len(r4) < MIN_SAMPLE else "white"),
                      pct(statistics.fmean(r1)) if r1 else Text("—"), pct(mean4),
                      f"{sum(x > 0 for x in r4) / len(r4):.0%}",
                      f"[{lo_hi[0] * 100:+.2f}..{lo_hi[1] * 100:+.2f}%]" if lo_hi else "—", reading)
    console.print(table)


def vetoes_table(console: Console, rows: List):
    """
    Every filter judged by what it rejected: entries grouped by veto reason (passed = taken) with their replay - a
    filter earns its place only if the trades it vetoes do WORSE than the ones it lets through (R:R 2, the
    confirmation minimum, off-session, macro events ...). Per strategy too, where a strategy has both.
    """
    entries = [r for r in rows if r['kind'] == 'entry' and _col(r, 'outcome') not in (None, 'SKIPPED', 'OPEN')]
    if not entries:
        return
    table = Table(title="Filters: replay of the entries each veto rejected vs the passed ones (net R @TP1)",
                  header_style="bold magenta", border_style="blue")
    for name in ("Veto", "Entries", "TP1+", "SL first", "Avg R", "90%"):
        table.add_column(name, justify="left" if name == "Veto" else "right", no_wrap=True)
    groups: Dict[str, List] = {}
    for r in entries:
        groups.setdefault(_col(r, 'vetoed') or 'passed', []).append(r)
    for key, members in sorted(groups.items(), key=lambda kv: (kv[0] != 'passed', -len(kv[1]))):
        values = [v for r in members if (v := net_r(r, 'r_tp1')) is not None]
        hit = sum(1 for r in members if r['outcome'] in ('TP1', 'TP2', 'TP3')) / len(members)
        sl = sum(1 for r in members if r['outcome'] == 'SL') / len(members)
        avg = Text(f"{statistics.fmean(values):+.2f}R", style="green" if statistics.fmean(values) > 0 else "red") \
            if values else Text("—", style="dim")
        ci = ci_text(values, scale=1, suffix="R", clusters=[cluster_of(r) for r in members
                                                              if net_r(r, 'r_tp1') is not None]) \
            if len(values) >= MIN_SAMPLE else Text("—", style="dim")
        table.add_row(key, Text(str(len(members)), style="dim" if len(members) < MIN_SAMPLE else "white"),
                      rate(hit), Text(f"{sl * 100:.0f}%"), avg, ci)
    console.print(table)


def slices_table(console: Console, rows: List):
    """
    eng-148 (stage 0): the replayed entries (net R @TP1, passed and vetoed alike) split by the journal's new fields and
    the audit's splits. Each row is weighted 1 / c_t (c_t = entries of the same 15m window and direction: one BTC
    move is one observation, not twenty), the p-value is the cluster bootstrap, q the Benjamini-Hochberg FDR over
    every split shown. Read-only diagnostics: a split decides nothing without the pre-registered pass rule
    (>= 100 clusters, p < 0.05, E[R] > 0 after costs, both halves).
    """
    entries = [r for r in rows if r['kind'] == 'entry' and _col(r, 'outcome') not in (None, 'SKIPPED', 'OPEN')
               and net_r(r, 'r_tp1') is not None]
    if len(entries) < MIN_SAMPLE:
        return
    key = {id(r): (r['ts_ms'] // 900_000, r['direction']) for r in entries}
    count: Dict = {}
    for r in entries:
        count[key[id(r)]] = count.get(key[id(r)], 0) + 1

    def hour_bin(r):
        h = _col(r, 'hour_utc')
        return None if h is None else f"{h // 4 * 4:02d}-{h // 4 * 4 + 4:02d} UTC"

    def vol_bin(r):
        v = _col(r, 'volume_24h')
        return None if v is None else ('< $30M' if v < 30e6 else '>= $30M')

    def crowd_bin(r):
        p = _col(r, 'crowd_pos')
        return None if p is None else ('top 3' if p < 3 else 'rest')

    def flag(col, yes, no):
        return lambda r: None if _col(r, col) is None else (yes if _col(r, col) else no)

    splits = [('class', lambda r: _col(r, 'strat_class')), ('hour', hour_bin),
              ('weekend', flag('weekend', 'weekend', 'weekday')), ('volume', vol_bin), ('crowd', crowd_bin),
              ('time stop 8 bars', flag('time_stop', 'would fire', 'no')),
              ('limit fill', flag('optimistic_fill', 'touch only', 'traded through')),
              ('TP1 R:R', lambda r: None if _col(r, 'rr_tp1') is None else ('< 1R' if r['rr_tp1'] < 1 else '>= 1R')),
              # eng-149 labels (journal only)
              ('NR7 day', flag('nr7', 'NR7', 'no')), ('NR4 day', flag('nr4', 'NR4', 'no')),
              ('inside day', flag('inside_day', 'inside', 'no')), ('vol regime', lambda r: _col(r, 'vol_regime')),
              ('BTC 4h < EMA50', flag('btc_below_ema50_4h', 'below', 'above')),
              ('market_down alt', flag('mkt_down_alt', 'down', 'no')),
              ('SMT BTC/ETH', lambda r: None if _col(r, 'smt_majors') is None else
               ('with' if _col(r, 'smt_majors') == r['direction'] else 'none' if not _col(r, 'smt_majors') else 'against'))]
    out = []
    for name, fn in splits:
        groups: Dict = {}
        for r in entries:
            g = fn(r)
            if g is not None:
                groups.setdefault(g, []).append(r)
        for g, members in sorted(groups.items()):
            vals = [net_r(r, 'r_tp1') for r in members]
            w = [1 / count[key[id(r)]] for r in members]
            mean = sum(v * x for v, x in zip(vals, w)) / sum(w)
            cl = [key[id(r)] for r in members]
            out.append((name, str(g), len(members), len(set(cl)), mean, bootstrap_p(vals, cl)))
    qs = bh_q([o[5] for o in out])
    table = Table(title="eng-148 splits: replayed entries, net R @TP1 weighted 1/c_t (15m x direction clusters)",
                  header_style="bold magenta", border_style="blue")
    for col in ("Split", "Group", "Entries", "Clusters", "E[R] w", "p", "q (BH)"):
        table.add_column(col, justify="left" if col in ("Split", "Group") else "right", no_wrap=True)
    for (name, g, n, k, mean, p), q in zip(out, qs):
        table.add_row(name, g, str(n), Text(str(k), style="dim" if k < 100 else "white"),
                      Text(f"{mean:+.2f}R", style="green" if mean > 0 else "red"),
                      "—" if p is None else f"{p:.3f}", "—" if q is None else f"{q:.3f}")
    console.print(table)


def _wmean(pairs: List[Tuple[float, tuple]]) -> Tuple[Optional[float], int, Optional[float]]:
    """The 1/c_t-weighted mean of (value, cluster) pairs, the number of clusters and the cluster-bootstrap p."""
    if not pairs:
        return None, 0, None
    count: Dict = {}
    for _, c in pairs:
        count[c] = count.get(c, 0) + 1
    w = [1 / count[c] for _, c in pairs]
    mean = sum(v * x for (v, _), x in zip(pairs, w)) / sum(w)
    return mean, len(count), bootstrap_p([v for v, _ in pairs], [c for _, c in pairs])


def variants_table(console: Console, rows: List):
    """
    eng-149 (plan eng-148 stage 3): each shadow variant against the card's OWN entry on the same cards (pairs), R
    before costs to TP1 / the 8h window, weighted 1/c_t (15m x direction); p = cluster bootstrap of the paired
    difference variant - own. The card's own entry = its live row or its own veto (not another shadow entry:
    flow_entry / reclaim_entry / weak_mss / variant_shift). FVG split 50/50 = half at the edge + half at the CE
    (0 when the CE was not reached) vs the CE limit alone, both on the cards whose edge was touched. Diagnostics only:
    the pre-registered pass rule decides (>= 100 clusters, p < 0.05, E[R] > 0 after costs, both halves).
    """
    entries = [r for r in rows if r['kind'] == 'entry']
    if not entries:
        return
    other_shadows = ('flow_entry', 'reclaim_entry', 'weak_mss', 'variant_shift')
    clus = lambda r: (r['ts_ms'] // 900_000, r['direction'])   # noqa: E731
    by_card: Dict = {}
    for r in entries:
        by_card.setdefault((r['symbol'], r['group_key'], _col(r, 'setup_ts_ms')), []).append(r)
    lines = []      # (name, [(variant, own, cluster)])
    live = [r for r in entries if not (_col(r, 'vetoed') or '').startswith('variant_')
            and _col(r, 'vetoed') not in other_shadows]
    lines.append(('two-contour stop vs plain stop', [(r['two_stop_r'], r['base_stop_r'], clus(r)) for r in live
                  if _col(r, 'two_stop_r') is not None and _col(r, 'base_stop_r') is not None]))
    lines.append(('sweep second test vs its first entry', [(r['retest_r'], r['base_stop_r'], clus(r)) for r in live
                  if _col(r, 'retest_r') is not None and _col(r, 'base_stop_r') is not None]))
    for name in ('variant_st_stop', 'variant_ce_limit', 'variant_fvg_edge', 'variant_pool2'):
        pairs = []
        for members in by_card.values():
            var = next((r for r in members if _col(r, 'vetoed') == name), None)
            own = next((r for r in members if not (_col(r, 'vetoed') or '').startswith('variant_')
                        and _col(r, 'vetoed') not in other_shadows), None)
            if var is not None and own is not None and _col(var, 'base_stop_r') is not None \
                    and _col(own, 'base_stop_r') is not None:
                pairs.append((var['base_stop_r'], own['base_stop_r'], clus(var)))
        lines.append((f"{name} vs the card's own entry", pairs))
        if name != 'variant_st_stop':
            # the cards whose limit filled but whose own entry never came (own = 0R: no trade)
            none = [(r['base_stop_r'], 0.0, clus(r)) for members in by_card.values()
                    for r in members if _col(r, 'vetoed') == name and _col(r, 'base_stop_r') is not None
                    and not any(not (_col(x, 'vetoed') or '').startswith('variant_')
                                and _col(x, 'vetoed') not in other_shadows for x in members)]
            lines.append((f"{name}, no own entry (own = 0R)", none))
    split = []
    for members in by_card.values():
        edge = next((r for r in members if _col(r, 'vetoed') == 'variant_fvg_edge'), None)
        ce = next((r for r in members if _col(r, 'vetoed') == 'variant_ce_limit'), None)
        if edge is None or _col(edge, 'base_stop_r') is None:
            continue
        if ce is not None and _col(ce, 'base_stop_r') is None:
            continue                                # the CE filled but is not evaluated yet
        ce_r = ce['base_stop_r'] if ce is not None else 0.0
        split.append((0.5 * edge['base_stop_r'] + 0.5 * ce_r, ce_r, clus(edge)))
    lines.append(('FVG split 50/50 vs CE limit (edge touched)', split))
    table = Table(title="eng-149 shadow variants vs the card's own entry (paired, R before costs, weighted 1/c_t)",
                  header_style="bold magenta", border_style="blue")
    for col in ("Variant", "Pairs", "Clusters", "E[R] variant", "E[R] own", "Diff", "p (diff)"):
        table.add_column(col, justify="left" if col == "Variant" else "right", no_wrap=True)
    fmt = lambda m: Text("—", style="dim") if m is None else Text(f"{m:+.2f}R", style="green" if m > 0 else "red")   # noqa: E731
    for name, pairs in lines:
        mv, k, _ = _wmean([(v, c) for v, _, c in pairs])
        mo, _, _ = _wmean([(o, c) for _, o, c in pairs])
        md, _, pd = _wmean([(v - o, c) for v, o, c in pairs])
        table.add_row(name, str(len(pairs)), Text(str(k), style="dim" if k < 100 else "white"), fmt(mv), fmt(mo),
                      fmt(md), "—" if pd is None else f"{pd:.3f}")
    console.print(table)


def funnel_table(console: Console, rows: List):
    """
    eng-149 (plan eng-148 stage 0.3): where each strategy's cards fall out - cards by their finish (EXPIRED / MISSED /
    INVALID ... and the entered ones), entries passed vs vetoed and the top veto reasons (shadow variants left out).
    """
    by: Dict[str, Dict[str, int]] = {}
    reasons: Dict[str, Dict[str, int]] = {}
    for r in rows:
        strat = _col(r, 'strategy') or '?'
        if r['kind'] == 'card':
            st = (r['group_key'] or '').split(' ', 1)[0]
            by.setdefault(strat, {}).setdefault(f"card {st}", 0)
            by[strat][f"card {st}"] += 1
        elif r['kind'] == 'entry':
            v = _col(r, 'vetoed')
            if v and v.startswith('variant_'):
                continue
            key = 'entry vetoed' if v else 'entry passed'
            by.setdefault(strat, {}).setdefault(key, 0)
            by[strat][key] += 1
            if v:
                reasons.setdefault(strat, {}).setdefault(v, 0)
                reasons[strat][v] += 1
    if not by:
        return
    table = Table(title="Funnel by strategy (cards by finish, entries passed / vetoed, top vetoes)",
                  header_style="bold magenta", border_style="blue")
    for col in ("Strategy", "Cards by finish", "Entries passed", "Vetoed", "Top vetoes"):
        table.add_column(col, justify="left", no_wrap=False)
    for strat in sorted(by):
        c = by[strat]
        cards = ', '.join(f"{k[5:]} {n}" for k, n in sorted(c.items()) if k.startswith('card '))
        top = ', '.join(f"{k} {n}" for k, n in sorted((reasons.get(strat) or {}).items(), key=lambda kv: -kv[1])[:4])
        table.add_row(strat, cards or '—', str(c.get('entry passed', 0)), str(c.get('entry vetoed', 0)), top or '—')
    console.print(table)


def card_results_table(console: Console, rows: List):
    """Entered cards by their OWN exit (card_r: the lifecycle's trailing channel / pyramided units / TTL close): the only
    result of the Turtles or Connors, whose trades outlive the 8h replay."""
    cards = [r for r in rows if r['kind'] == 'card' and _col(r, 'card_r') is not None]
    if not cards:
        return
    table = Table(title="Entered cards by their own exit (card_r, R of one unit)", header_style="bold magenta",
                  border_style="blue")
    for name in ("Strategy", "Cards", "Mean R", "Win", "TP1", "TP2", "TP3", "SL before TP1", "Trail", "Avg units", "R / unit", "Ambig", "Mean R low"):
        table.add_column(name, justify="left" if name == "Strategy" else "right", no_wrap=True)
    groups: Dict[str, List] = {}
    for r in cards:
        groups.setdefault(_col(r, 'strategy') or '?', []).append(r)

    def best_tp(r) -> int:
        # the card's furthest target (journaled since eng-50; older rows: read from the status / exit reason)
        b = _col(r, 'best_tp')
        if b is not None:
            return int(b)
        if r['group_key'].startswith('TP3'):
            return 3
        import re
        m = re.search(r'after TP(\d)', _col(r, 'reason') or '')
        return int(m.group(1)) if m else 0

    for name, members in sorted(groups.items()):
        rs = [r['card_r'] for r in members]
        units = [_col(r, 'units') or 1 for r in members]
        tps = [best_tp(r) for r in members]
        n = len(rs)
        sl0 = sum(1 for r, b in zip(members, tps) if b == 0 and r['group_key'].startswith('SL') and r['card_r'] <= 0)
        # eng-132: a stop that ended IN PROFIT (the trailed / break-even stop) is not a loss: counted apart ('TRAIL')
        trail = sum(1 for r in members if r['group_key'].startswith('SL') and r['card_r'] > 0)
        # audit EXTRA_1: a card whose entry minute could not be judged ('ambiguous') shows its pessimistic R apart
        ambig = sum(1 for r in members if _col(r, 'entry_min') == 'ambiguous')
        low = [_col(r, 'card_r_low') if _col(r, 'entry_min') == 'ambiguous' and _col(r, 'card_r_low') is not None
               else r['card_r'] for r in members]
        per_unit = statistics.fmean(x / u for x, u in zip(rs, units))   # eng-132: R of a Turtle trade per unit held
        table.add_row(name, str(n), Text(f"{statistics.fmean(rs):+.2f}R", style="green" if statistics.fmean(rs) > 0 else "red"),
                      f"{sum(x > 0 for x in rs) / n:.0%}",
                      f"{sum(b >= 1 for b in tps)} ({sum(b >= 1 for b in tps) / n:.0%})",
                      f"{sum(b >= 2 for b in tps)} ({sum(b >= 2 for b in tps) / n:.0%})",
                      f"{sum(b >= 3 for b in tps)} ({sum(b >= 3 for b in tps) / n:.0%})",
                      f"{sl0} ({sl0 / n:.0%})", f"{trail} ({trail / n:.0%})", f"{statistics.fmean(units):.1f}",
                      f"{per_unit:+.2f}R", str(ambig), f"{statistics.fmean(low):+.2f}R")
    console.print(table)


def _moments(xs: List[float]) -> Tuple[float, float, float, float]:
    """Mean, sd, skewness, kurtosis (not excess) of xs."""
    n = len(xs)
    m = statistics.fmean(xs)
    sd = statistics.pstdev(xs) if n > 1 else 0.0
    if not sd:
        return m, 0.0, 0.0, 3.0
    g3 = sum((x - m) ** 3 for x in xs) / n / sd ** 3
    g4 = sum((x - m) ** 4 for x in xs) / n / sd ** 4
    return m, sd, g3, g4


def psr(sr: float, n: int, g3: float, g4: float, sr0: float = 0.0) -> Optional[float]:
    """Probabilistic Sharpe ratio (Bailey & Lopez de Prado 2012): P(true SR > sr0) given n observations."""
    den = 1 - g3 * sr + (g4 - 1) / 4 * sr * sr
    if n < 2 or den <= 0:
        return None
    return statistics.NormalDist().cdf((sr - sr0) * math.sqrt(n - 1) / math.sqrt(den))


def min_trl(sr: float, g3: float, g4: float, sr0: float = 0.0, conf: float = 0.95) -> Optional[float]:
    """Minimum track record length: observations for the observed SR to beat sr0 at `conf` (only if sr > sr0)."""
    if sr <= sr0:
        return None
    z = statistics.NormalDist().inv_cdf(conf)
    return 1 + (1 - g3 * sr + (g4 - 1) / 4 * sr * sr) * (z / (sr - sr0)) ** 2


def expected_max_sr(trials: int, n: int) -> float:
    """The SR the best of `trials` independent zero-edge trials reaches by luck (Bailey & Lopez de Prado's deflated
    Sharpe threshold; the variance of an SR estimate under the null ~ 1 / n)."""
    if trials <= 1 or n < 2:
        return 0.0
    gamma = 0.5772156649
    nd = statistics.NormalDist()
    return math.sqrt(1 / n) * ((1 - gamma) * nd.inv_cdf(1 - 1 / trials) + gamma * nd.inv_cdf(1 - 1 / (trials * math.e)))


def hl_haircut(sr: float, n: int, trials: int) -> Optional[float]:
    """
    Harvey & Liu (2015, "Backtesting", JPM): the Sharpe haircut for multiple testing - the t-stat of the per-cluster
    Sharpe (t = SR x sqrt(n)), its two-sided p-value Bonferroni-adjusted for `trials` (p x M, their most conservative
    rule), translated back to a Sharpe; haircut = 1 - SR_adj / SR (100% = nothing left once the trials are counted).
    Bonferroni is the strictest of their three (Bonferroni / Holm / BHY; they advocate BHY, which needs every trial's
    p-value - we have only the live cells'): an UPPER bound of the haircut.
    """
    if n < 2 or sr <= 0 or trials < 1:
        return None
    z = statistics.NormalDist()
    p = 2 * (1 - z.cdf(sr * math.sqrt(n)))
    p_adj = min(1.0, p * trials)
    if p_adj >= 1.0:
        return 1.0
    sr_adj = z.inv_cdf(1 - p_adj / 2) / math.sqrt(n)
    return max(0.0, 1 - sr_adj / sr)


def pbo_cscv(matrix: List[List[float]], blocks: int = 8) -> Optional[float]:
    """
    Bailey, Borwein, Lopez de Prado & Zhu (2017): the probability of backtest overfitting by combinatorially symmetric
    cross-validation. `matrix` = T periods x N configurations (here: days x strategies, the day's summed R). The T rows
    are cut into `blocks` contiguous parts; for every half / half split the in-sample best configuration's
    out-of-sample relative rank w gives logit ln(w / (1 - w)); PBO = the share of splits with logit <= 0 (the IS winner
    at or below the OOS median). ~0.5 = choosing the best strategy is a coin flip.
    """
    from itertools import combinations
    t, n = len(matrix), len(matrix[0]) if matrix else 0
    if n < 2 or t < 2 * blocks:
        return None
    size = t // blocks
    parts = [matrix[i * size:(i + 1) * size] for i in range(blocks)]
    below, total = 0, 0
    for ins in combinations(range(blocks), blocks // 2):
        is_rows = [r for b in ins for r in parts[b]]
        oos_rows = [r for b in range(blocks) if b not in ins for r in parts[b]]
        is_mean = [statistics.fmean(r[j] for r in is_rows) for j in range(n)]
        oos_mean = [statistics.fmean(r[j] for r in oos_rows) for j in range(n)]
        best = max(range(n), key=lambda j: is_mean[j])
        rank = sum(1 for j in range(n) if oos_mean[j] < oos_mean[best]) + 1
        w = rank / (n + 1)
        below += math.log(w / (1 - w)) <= 0
        total += 1
    return below / total if total else None


def robustness_table(console: Console, rows: List):
    """
    Is a strategy's result a few lucky trades? (the crypto-backtest-audit checks, chrisamz/crypto-skills): total card R
    without the best trade / the best 5, without the best coin / the best 5 coins, the best trade's share of the total;
    the mean R of the first and second half by entry time; the first card per coin only; the extra round-trip cost
    (bps of price) that brings the total to 0 = sum R / sum(1 / risk in bps). Below the table: PBO of picking the best
    strategy (days x strategies, CSCV).
    """
    cards = [dict(r, card_r=card_r_net(r)) for r in rows if r['kind'] == 'card' and _col(r, 'card_r') is not None]
    if not cards:
        return
    table = Table(title="Robustness: is the result a few lucky trades? (R sums; cost = extra bps per round trip to 0)",
                  header_style="bold magenta", border_style="blue")
    for name in ("Strategy", "Cards", "Total R", "-best", "-top5", "-best coin", "-top5 coins", "Best share",
                 "1st half", "2nd half", "1st/coin", "Cost to 0"):
        table.add_column(name, justify="left" if name == "Strategy" else "right", no_wrap=True)
    groups: Dict[str, List] = {}
    for r in cards:
        groups.setdefault(_col(r, 'strategy') or '?', []).append(r)
    for name, members in sorted(groups.items()):
        members.sort(key=lambda r: r['ts_ms'])
        rs = [r['card_r'] for r in members]
        total = sum(rs)
        top = sorted(rs, reverse=True)
        coins: Dict[str, float] = {}
        first: Dict[str, float] = {}
        for r in members:
            coins[r['symbol']] = coins.get(r['symbol'], 0.0) + r['card_r']
            first.setdefault(r['symbol'], r['card_r'])
        ctop = sorted(coins.values(), reverse=True)
        half = len(rs) // 2
        h1, h2 = rs[:half], rs[half:]
        inv = 0.0
        for r in members:
            entry, sl = _col(r, 'entry'), _col(r, 'sl')
            if entry and sl and entry != sl:
                inv += 1 / (abs(entry - sl) / entry * 1e4)
        cost = total / inv if inv and total > 0 else None
        share = top[0] / total if total > 0 else None
        f = lambda v: f"{v:+.1f}"
        table.add_row(name, str(len(rs)), f(total), f(total - top[0]), f(total - sum(top[:5])),
                      f(total - ctop[0]), f(total - sum(ctop[:5])), f"{share:.0%}" if share is not None else "-",
                      f"{statistics.fmean(h1):+.2f}R" if h1 else "-", f"{statistics.fmean(h2):+.2f}R" if h2 else "-",
                      f"{statistics.fmean(first.values()):+.2f}R", f"{cost:.0f}" if cost else "-")
    console.print(table)
    names = sorted(groups)
    days: Dict[int, Dict[str, float]] = {}
    for r in cards:
        d = days.setdefault(int(r['ts_ms'] // 86_400_000), {})
        key = _col(r, 'strategy') or '?'
        d[key] = d.get(key, 0.0) + r['card_r']
    if days:
        span = range(min(days), max(days) + 1)
        pbo = pbo_cscv([[days.get(d, {}).get(n, 0.0) for n in names] for d in span])
        console.print(f"PBO (CSCV, {len(span)} days x {len(names)} strategies, 8 blocks): "
                      + (f"{pbo:.0%} - the chance that the in-sample best strategy is below the median out of sample"
                         if pbo is not None else "not enough days (>= 16) or strategies (>= 2)"))


def version_no(v: Optional[str]) -> int:
    """'eng-57' -> 57, 'eng-169e' -> 169 (a letter suffix marks a sub-release of the same number; 0 for anything else).
    eng-169e: int('169e') raised -> 0, so every card of eng-169e read as the oldest logic (the >= 137 / 141 rules off)."""
    m = re.match(r'eng-(\d+)', str(v or ''))
    return int(m.group(1)) if m else 0


def card_r_net(row) -> Optional[float]:
    """A card's R net of costs: rows from eng-58 on are net already (SignalBook._exit_r); older ones were gross - the
    round trip's fees and slippage (by the coin's 24h volume) are taken off here (funding / gaps not known for them)."""
    r = _col(row, 'card_r')
    if r is None or version_no(_col(row, 'logic_version')) >= 58:
        return r
    entry, sl = _col(row, 'entry'), _col(row, 'sl')
    if not entry or sl is None or entry == sl:
        return r
    from levels import slippage_bps
    cost = CONFIG.journal.fee_round_trip + 2 * slippage_bps(_col(row, 'volume_24h'), _col(row, 'symbol')) / 1e4
    return r - cost * entry / abs(entry - sl)


def effective_trials(rows: List) -> Tuple[int, int]:
    """
    eng-59 (plan 3.2): the effective number of independent trials behind the DSR - Lopez de Prado's ONC idea: the
    trials are the (logic version x strategy) cells; their mean-R series per 4h block are correlated (one strategy across
    versions is nearly the same bet), so they are clustered on the correlation distance sqrt((1 - rho) / 2) by k-means
    for k = 2 .. n - 1 and the k with the best silhouette t-stat (mean / std of the samples' silhouettes) is the
    effective N. Cells with < 10 blocks of results stay single trials. Returns (effective N, raw N).
    """
    series: Dict[tuple, Dict[int, List[float]]] = {}
    for r in rows:
        if _col(r, 'kind') not in ('entry', 'card') or not _col(r, 'strategy'):
            continue
        v = card_r_net(r) if _col(r, 'kind') == 'card' else net_r(r, 'r_tp1') if _col(r, 'r_tp1') is not None else None
        if v is None or (_col(r, 'kind') == 'entry' and _col(r, 'vetoed')):
            continue
        series.setdefault((_col(r, 'logic_version'), _col(r, 'strategy')), {}).setdefault(
            int(_col(r, 'ts_ms') // 14_400_000), []).append(v)
    raw = len(series) or 1
    keys = [k for k, d in series.items() if len(d) >= 10]
    lone = raw - len(keys)
    if len(keys) < 3:
        return raw, raw
    days = sorted({d for k in keys for d in series[k]})
    import numpy as np
    m = np.full((len(keys), len(days)), np.nan)
    pos = {d: i for i, d in enumerate(days)}
    for i, k in enumerate(keys):
        for d, vs in series[k].items():
            m[i, pos[d]] = statistics.fmean(vs)
    corr = np.eye(len(keys))
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            ok = ~np.isnan(m[i]) & ~np.isnan(m[j])
            c = np.corrcoef(m[i, ok], m[j, ok])[0, 1] if ok.sum() >= 5 and m[i, ok].std() > 0 and m[j, ok].std() > 0 else 0.0
            corr[i, j] = corr[j, i] = 0.0 if np.isnan(c) else c
    dist = np.sqrt(np.clip((1 - corr) / 2, 0, 1))
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_samples
    best, best_k = -np.inf, len(keys)
    for k in range(2, len(keys)):
        labels = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(dist)
        if len(set(labels)) < 2:
            continue
        sil = silhouette_samples(dist, labels)
        t = sil.mean() / sil.std() if sil.std() > 0 else -np.inf
        if t > best:
            best, best_k = t, k
    return best_k + lone, raw


def verdict_table(console: Console, rows: List, all_rows: Optional[List] = None):
    """
    eng-55: the two-level verdict per strategy (the owner's decision after the audit, written before results):
    SUSPEND (no demo, still journaled) at >= 30 independent 4h clusters when the 90% cluster interval's LOWER bound is
    below -0.05R; DEPRECATE (delete the code) only at >= 200 clusters (MinTRL of a +0.1R edge with skew 1.8 / kurtosis
    7.8) with the UPPER bound below 0. PSR = P(true mean R > 0) per cluster mean (skew / kurtosis aware); DSR = the
    same against the SR the best of N trials reaches by luck, N = the effective number of trials (eng-59:
    `effective_trials`, ONC-style clustering of the version x strategy cells; was the raw cell count, an upper bound).
    """
    cards = [dict(r, card_r=card_r_net(r)) for r in rows if r['kind'] == 'card' and _col(r, 'card_r') is not None]
    if not cards:
        return
    pool = all_rows if all_rows is not None else rows
    trials, raw_trials = effective_trials(pool)
    table = Table(title=f"Verdict (suspend: >=30 clusters & low < -0.05R; deprecate: >=200 & high < 0); "
                        f"DSR trials N={trials} (ONC; {raw_trials} version x strategy cells)",
                  header_style="bold magenta", border_style="blue")
    for name in ("Strategy", "Cards", "Clusters", "Mean R/blk", "90% CI", "Skew", "Kurt", "PSR", "DSR", "HL haircut", "MinTRL",
                 "Verdict"):
        table.add_column(name, justify="left" if name in ("Strategy", "Verdict") else "right", no_wrap=True)
    groups: Dict[str, List] = {}
    for r in cards:
        groups.setdefault(_col(r, 'strategy') or '?', []).append(r)
    for name, members in sorted(groups.items()):
        rs = [r['card_r'] for r in members]
        keys = [cluster_of(r) for r in members]
        blocks: Dict = {}
        for k, v in zip(keys, rs):
            blocks.setdefault(k, []).append(v)
        means = [statistics.fmean(v) for v in blocks.values()]
        k = len(means)
        # audit (2nd part): ONE unit for every column - the independent 4h block's mean R. Mean R / CI were per card
        # (a cluster-weighted mean) while PSR / DSR / HL / MinTRL used the blocks' equal-weight mean: one block of a
        # -1R card and one of ten +0.2R cards read Mean R +0.09 with PSR / DSR blank (block mean -0.4)
        ci = bootstrap_ci(means)
        m, sd, g3, g4 = _moments(means)
        sr = m / sd if sd else 0.0
        p = psr(sr, k, g3, g4)
        dsr = psr(sr, k, g3, g4, expected_max_sr(trials, k))
        mt = min_trl(sr, g3, g4)
        hl = hl_haircut(sr, k, trials)
        if ci and k >= 200 and ci[1] < 0:
            verdict = Text("DEPRECATE", style="bold red")
        elif ci and k >= 30 and ci[0] < -0.05:
            verdict = Text("SUSPEND", style="red")
        elif k < 30:
            verdict = Text(f"wait ({k}/30)", style="dim")
        else:
            verdict = Text("keep", style="green")
        table.add_row(name, str(len(rs)), str(k), f"{m:+.2f}R",
                      f"[{ci[0]:+.2f}..{ci[1]:+.2f}]" if ci else "", f"{g3:+.1f}", f"{g4:.1f}",
                      f"{p:.0%}" if p is not None else "", f"{dsr:.0%}" if dsr is not None else "",
                      f"{hl:.0%}" if hl is not None else "-", f"{mt:.0f}" if mt else "-", verdict)
    console.print(table)


def demo_gap_table(console: Console, db: str = 'demo_trades.db'):
    """
    eng-55 (audit 3.8 / 3.9): where the demo's R differs from the journal's - the entry slip (BingX fill vs the plan's
    entry, carried by the basis), the stop slip on SL exits (exit vs the stop: the mark-price trigger's delay shows
    here) and the share of skipped trades by reason.
    """
    if not os.path.exists(db):
        return
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cols = {c[1] for c in conn.execute("PRAGMA table_info(demo_trades)")}
        rows = conn.execute("SELECT * FROM demo_trades" + _demo_where(cols), _demo_args(cols)).fetchall()
    finally:
        conn.close()
    if not rows or not {'entry_fill', 'exit_avg', 'direction'} <= cols:
        return
    table = Table(title="BingX demo vs plan: slippage in bps (+ = against us)", header_style="bold magenta",
                  border_style="blue")
    for name in ("Strategy", "Trades", "Entry slip", "SL exits", "Stop slip", "Demo R", "Journal R", "Skipped"):
        table.add_column(name, justify="left" if name == "Strategy" else "right", no_wrap=True)
    groups: Dict[str, List] = {}
    for r in rows:
        groups.setdefault(r['strategy'] or '?', []).append(r)

    def bps(a, b, d):
        return d * (a - b) / b * 1e4 if a and b else None

    for strategy, members in sorted(groups.items()):
        traded = [r for r in members if r['entry_fill'] and r['r'] is not None]
        plan_entry = 'entry_plan' if 'entry_plan' in cols else None
        e_slip = [x for x in (bps(r['entry_fill'], r[plan_entry], r['direction']) for r in traded)
                  if x is not None] if plan_entry else []
        stop_col = 'sl' if 'sl' in cols else 'stop' if 'stop' in cols else None
        sl_rows = [r for r in traded if (r['close_reason'] or '').startswith('SL')]
        s_slip = [x for x in (bps(r[stop_col], r['exit_avg'], r['direction']) for r in sl_rows) if x is not None] \
            if stop_col else []
        skipped = sum(1 for r in members if r['close_reason'] in ('PRICE_GAP', 'NOT_FILLED', 'LATE_FILL', 'NO_STOP'))
        jr = [r['journal_r'] for r in traded if 'journal_r' in cols and r['journal_r'] is not None]
        table.add_row(strategy, str(len(traded)),
                      f"{statistics.fmean(e_slip):+.1f}" if e_slip else "", str(len(sl_rows)),
                      f"{statistics.fmean(s_slip):+.1f}" if s_slip else "",
                      f"{statistics.fmean([r['r'] for r in traded]):+.2f}R" if traded else "",
                      f"{statistics.fmean(jr):+.2f}R" if jr else "", str(skipped))
    console.print(table)


def demo_table(console: Console, db: str = 'demo_trades.db', journal_db: str = CONFIG.journal.db_path):
    """
    The BingX demo fills next to the same card's own result (eng-59, research/demo_gap.md: the journal's replay
    trades thirds to fixed targets over 8h while the card and the demo exit by the method - time stop, session, band,
    SMA5 - so `journal_r` was the wrong partner: half of the -0.32R gap was that). The card is the first finished card
    of the coin and direction after the demo's entry (`card_r`, netted by card_r_net).
    """
    if not os.path.exists(db):
        return
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cols = {c[1] for c in conn.execute("PRAGMA table_info(demo_trades)")}
        raw = conn.execute("SELECT strategy, close_reason, r, symbol, direction, opened_ms, card_id, setup "
                           "FROM demo_trades" + _demo_where(cols), _demo_args(cols)).fetchall()
    finally:
        conn.close()
    rows = []
    jconn = sqlite3.connect(f"file:{journal_db}?mode=ro", uri=True) if os.path.exists(journal_db) else None
    if jconn is not None:
        jconn.row_factory = sqlite3.Row
    try:
        has_id = jconn is not None and 'card_id' in {c[1] for c in jconn.execute("PRAGMA table_info(signals)")}
        for strategy, reason, r, symbol, direction, opened, card_id, setup in raw:
            card = None
            if jconn is not None and r is not None and opened:
                # audit N24: the exact card by its id; older rows without one: the same SETUP (not any card of the
                # coin and side) finished after the entry
                row = jconn.execute("SELECT * FROM signals WHERE kind = 'card' AND card_id = ? AND card_r IS NOT NULL "
                                    "LIMIT 1", (card_id,)).fetchone() if has_id and card_id else None
                if row is None and setup:
                    row = jconn.execute(
                        "SELECT * FROM signals WHERE kind = 'card' AND symbol = ? AND direction = ? AND card_r IS NOT NULL "
                        "AND group_key LIKE ? AND ts_ms BETWEEN ? AND ? ORDER BY ts_ms LIMIT 1",
                        (symbol, direction, '% ' + setup, opened, opened + 40 * 86_400_000)).fetchone()
                card = card_r_net(row) if row is not None else None
            rows.append((strategy, reason, r, card))
    finally:
        if jconn is not None:
            jconn.close()
    if not rows:
        return
    table = Table(title="BingX demo vs the card's own net R (closed trades; ERROR / NO_MARKET / EARLY_CLOSE apart)",
                  header_style="bold magenta", border_style="blue")
    for name in ("Strategy", "Trades", "Demo R", "Card R", "Both", "Diff", "Not traded"):
        table.add_column(name, justify="left" if name == "Strategy" else "right", no_wrap=True)
    groups: Dict[str, List] = {}
    for r in rows:
        groups.setdefault(r[0] or '?', []).append(r)
    for strategy, members in sorted(groups.items()):
        done = [r for r in members if r[1] not in ('ERROR', 'NO_MARKET', 'EARLY_CLOSE', 'OVERLAP', 'INVALID_ENTRY', 'PRICE_GAP', 'LATE_FILL', 'UNTRACKED', 'NO_STOP', 'NOT_FILLED', 'ORPHAN') and r[2] is not None]
        demo = [r[2] for r in done]
        jr = [r[3] for r in done if r[3] is not None]
        both = [(r[2], r[3]) for r in done if r[3] is not None]
        fmt = lambda v: Text(f"{statistics.fmean(v):+.2f}R") if v else Text("—", style="dim")  # noqa: E731
        diff = Text(f"{statistics.fmean(a - b for a, b in both):+.2f}R") if both else Text("—", style="dim")
        table.add_row(strategy, str(len(done)), fmt(demo), fmt(jr), str(len(both)), diff,
                      str(len(members) - len(done)))
    console.print(table)


def cards_table(console: Console, rows: List):
    """Finished cards by status: why they ended and what price did afterwards in the card's direction."""
    cards = [r for r in rows if r['kind'] == 'card']
    if not cards:
        return
    table = Table(title="Finished cards: what price did afterwards (in the card's direction)",
                  header_style="bold magenta", border_style="blue")
    # audit N24: one header per horizon from HORIZONS (4 values with 8h were printed under 3 headers)
    for name in ("Card", "N", *(f"after {label}" for label in HORIZONS), "vetoed triggers"):
        table.add_column(name, justify="left" if name == "Card" else "right", no_wrap=True)
    groups: Dict[str, List] = {}
    for r in cards:
        groups.setdefault(r['group_key'], []).append(r)
    for key in sorted(groups):
        members = groups[key]
        cells = []
        for label in HORIZONS:
            values = [r['direction'] * r[f'ret_{label}'] for r in members if r[f'ret_{label}'] is not None]
            cells.append(pct(statistics.fmean(values)) if values else Text("—", style="dim"))
        vetoed = sum(1 for r in members if _col(r, 'vetoed'))
        table.add_row(key, str(len(members)), *cells, Text(f"{vetoed}", style="dim"))
    console.print(table)


def report(console: Console, db: str = CONFIG.journal.db_path, days: Optional[float] = None, last: int = 0,
           all_versions: bool = False):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        _report(console, conn, db, days, last, all_versions)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Signal journal statistics")
    parser.add_argument("--db", default=CONFIG.journal.db_path)
    parser.add_argument("--days", type=float, default=None, help="only signals from the last N days")
    parser.add_argument("--last", type=int, default=0, help="also list the N most recent signals")
    parser.add_argument("--all-versions", action="store_true", help="include rows produced by older signal logic")
    args = parser.parse_args()
    report(Console(), args.db, args.days, args.last, args.all_versions)


# eng-144: demo trades of the current logic version only (None = every version; rows before eng-144 have none)
_DEMO_VERSION: Optional[str] = None


def _demo_where(cols) -> str:
    return " WHERE logic_version = ?" if _DEMO_VERSION and 'logic_version' in cols else ""


def _demo_args(cols) -> tuple:
    return (_DEMO_VERSION,) if _DEMO_VERSION and 'logic_version' in cols else ()


def _report(console: Console, conn: sqlite3.Connection, db: str, days: Optional[float], last: int, all_versions: bool):
    global _DEMO_VERSION
    _DEMO_VERSION = None if all_versions else CONFIG.journal.logic_version
    since = int((time.time() - days * 86400) * 1000) if days else 0
    all_rows = conn.execute("SELECT * FROM signals WHERE ts_ms >= ? ORDER BY ts_ms", (since,)).fetchall()
    version = CONFIG.journal.logic_version
    has_version = bool(all_rows) and 'logic_version' in all_rows[0].keys()
    rows = all_rows if all_versions else [r for r in all_rows if has_version and r['logic_version'] == version]
    if not rows:
        if all_rows:
            console.print(f"[yellow]No rows from the current signal logic ({version}) yet; {len(all_rows)} rows come from "
                          f"older logic. Run the scanner for a while, or use --all-versions to see them anyway "
                          f"(mixing logic versions makes the numbers misleading).[/yellow]")
        else:
            console.print(f"[yellow]No signals in {db} yet. Run the scanner for a while (logging starts after the 5 min warm-up).[/yellow]")
        return
    baseline = Baseline([r for r in rows if r['kind'] not in ('entry', 'card')], UniverseBaseline(conn))

    first, last_ts = rows[0]['ts_ms'], rows[-1]['ts_ms']
    console.print(
        f"[bold]Signal journal[/bold]: {len(rows)} signals ({'all logic versions' if all_versions else 'logic ' + version}), "
        f"{datetime.fromtimestamp(first / 1000):%Y-%m-%d %H:%M} → {datetime.fromtimestamp(last_ts / 1000):%Y-%m-%d %H:%M}"
    )
    market = Text(f"Market baseline: {baseline.source}. Median move of logged coins: ")
    for label in HORIZONS:
        values = [r[f'ret_{label}'] for r in rows if r[f'ret_{label}'] is not None]
        if values:
            market.append(f"{label} ")
            market.append_text(pct(statistics.median(values)))
            market.append(f" ({sum(v > 0 for v in values) / len(values):.0%} up)   ", style="dim")
    console.print(market)

    groups: Dict[str, List] = {}
    for r in rows:
        key = r['group_key'] + (" ✗" if _col(r, 'vetoed') else "")
        groups.setdefault(key, []).append(r)

    table = Table(show_header=True, header_style="bold magenta", border_style="blue")
    table.add_column("Setup", style="cyan", no_wrap=True)
    table.add_column("N", justify="right", no_wrap=True)
    for label in HORIZONS:
        table.add_column(label, justify="right", no_wrap=True, min_width=13)
    table.add_column("Edge 4h [90%]", justify="right", no_wrap=True, min_width=7)
    table.add_column("q", justify="right", no_wrap=True)
    table.add_column("Edge β 4h", justify="right", no_wrap=True, min_width=7)
    table.add_column("Med 4h", justify="right", no_wrap=True, min_width=7)
    table.add_column("Best 4h", justify="right", no_wrap=True)
    table.add_column("Worst 4h", justify="right", no_wrap=True, min_width=8)

    order = sorted(groups, key=lambda g: ({'structured': 0, 'setup': 1, 'anomaly': 2, 'entry': 3, 'card': 4}.get(groups[g][0]['kind'], 3), g))
    all_stats = {key: group_stats(groups[key], baseline) for key in order}
    # q-values over every setup row shown: dozens of intervals at 90% make a few "significant" ones by chance
    keys_p = [k for k in order if all_stats[k]['direction']]
    qs = dict(zip(keys_p, bh_q([bootstrap_p(all_stats[k]['edge_values_4h'], all_stats[k].get('edge_clusters_4h'))
                               for k in keys_p])))
    for key in order:
        st = all_stats[key]
        n_label = Text(f"{st['n']}", style="dim" if st['n_4h'] < MIN_SAMPLE else "white")
        if st['n_4h'] < st['n']:
            n_label.append(f" ({st['n_4h']})", style="dim")
        cells = []
        for label in HORIZONS:
            cell = rate(st[f'win_{label}'])
            cell.append(" / ", style="dim")
            cell.append_text(pct(st[f'avg_{label}'], colored=bool(st['direction'])))
            cells.append(cell)
        name = key + ("" if st['direction'] else " ↕")
        edge = pct(st['edge_4h'])
        edge.append_text(ci_text(st['edge_values_4h'], clusters=st.get('edge_clusters_4h')))
        q = qs.get(key)
        q_text = Text("—" if q is None else f"{q:.2f}", style="dim" if q is None or q > 0.10 else "bold")
        beta_edge = pct(st.get('edge_beta_4h')) if st.get('edge_beta_values_4h') else Text("—", style="dim")
        if st.get('edge_beta_values_4h'):
            beta_edge.append_text(ci_text(st['edge_beta_values_4h'], clusters=st.get('edge_beta_clusters_4h')))
        table.add_row(name, n_label, *cells, edge, q_text, beta_edge, pct(st['med_4h']), pct(st['mfe']), pct(st['mae']))
    console.print(table)
    console.print(
        "[dim]15m / 1h / 4h cells: win rate (net of the round-trip fee) / average return.\nWin = share of signals where "
        "price moved in the signal's direction by more than the fee (↕ rows: share of up moves; Avg = average move "
        "size either way).\nEdge 4h = average 4h return in the signal's direction minus the market baseline over the "
        "same window; [lo..hi] = 90% bootstrap interval (green: above 0, red: below 0, grey: can't tell yet).\n"
        "q = Benjamini-Hochberg q-value of Edge 4h != 0 over every setup in the table (bold: <= 0.10; a green interval "
        "with a large q is likely chance among many rows). Edge β = Edge with the baseline x the coin's beta (7 days "
        "of hourly returns before the signal's day, Blume-adjusted): what is left once the coin's market sensitivity "
        "is taken out.\n"
        "✗ = vetoed setups (not shown as cards). Best/Worst 4h = average largest favorable / adverse move within 4h.\n"
        f"N (x) = x signals already have a 4h result. Grey N = fewer than {MIN_SAMPLE} results.[/dim]"
    )

    levels_table(console, {k: v for k, v in groups.items() if k.startswith('ENTRY')})
    sources_table(console, rows)
    vetoes_table(console, rows)
    slices_table(console, rows)
    variants_table(console, rows)
    funnel_table(console, rows)
    reversal_test_table(console, rows)
    card_results_table(console, rows)
    # eng-58: the verdict over the version family since CONFIG.journal.verdict_since (net card R)
    family = [r for r in all_rows if has_version and version_no(r['logic_version']) >= version_no(CONFIG.journal.verdict_since)]
    console.print(f"[dim]Verdict / robustness over logic {CONFIG.journal.verdict_since}+ ({len(family)} rows), card R net of "
                  f"costs[/dim]")
    verdict_table(console, family, all_rows)
    robustness_table(console, family)
    cards_table(console, rows)
    demo_table(console)
    demo_gap_table(console)
    features_table(console, rows, baseline)

    if last:
        recent = Table(title=f"Last {last} signals", header_style="bold magenta", border_style="dim")
        for col in ("Time", "Symbol", "Setup", "Price", "Px 5m", "RVOL", "15m", "1h", "4h"):
            recent.add_column(col, justify="right" if col not in ("Symbol", "Setup") else "left", no_wrap=True)
        for r in rows[-last:][::-1]:
            d = r['direction'] or 1
            recent.add_row(
                f"{datetime.fromtimestamp(r['ts_ms'] / 1000):%m-%d %H:%M}",
                r['symbol'].replace(':USDT', '').replace('/USDT', ''),
                r['group_key'] + (" ✗" if _col(r, 'vetoed') else ""),
                f"{r['price']:.6g}",
                pct(r['price_change_5m']),
                f"{(r['rvol_1m'] or 0):.1f}x",
                *[pct(r[f'ret_{label}'] * d if r[f'ret_{label}'] is not None else None) for label in HORIZONS],
            )
        console.print(recent)
        console.print("[dim]15m/1h/4h in the last table are in the signal's direction (↕ setups: raw price change).[/dim]")


if __name__ == "__main__":
    main()
