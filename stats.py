#!/usr/bin/env python3
"""
Statistics over the signal journal (signals.db): what the price did after each kind of signal.

    python stats.py                 # rows of the current signal logic (CONFIG.journal.logic_version)
    python stats.py --all-versions  # every row, including older logic
    python stats.py --days 7        # last 7 days
    python stats.py --last 30       # also list the 30 most recent signals with their outcomes

Returns are measured from the futures last price at the signal, in the signal's direction: for BEAR / IMPULSE
DOWN a falling price counts as a gain. "Net" figures subtract the round-trip fee (CONFIG.journal.fee_round_trip).

Market baseline: the median return of the WHOLE universe over the same window, from the price snapshots the
scanner stores every 15 minutes (older databases without snapshots fall back to the median of the coins logged in
the same hour). "Edge" is a setup's return in its direction minus that baseline, so a falling market doesn't make
every short look good. [lo..hi] = 90% bootstrap interval of the mean: an interval that straddles 0 means the
sample cannot tell the setup from noise yet.
"""
import argparse
import bisect
import json
import random
import sqlite3
import statistics
import time
from datetime import datetime
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
    rng = random.Random(seed)
    k = len(blocks)
    draws = sorted(stat([v for _ in range(k) for v in blocks[rng.randrange(k)]]) for _ in range(BOOTSTRAP))
    return draws[int(0.05 * BOOTSTRAP)], draws[int(0.95 * BOOTSTRAP) - 1]


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
    """Median return of every universe coin between the snapshots at/after t and at/after t + horizon."""

    MAX_GAP_MS = 20 * 60_000

    def __init__(self, conn: sqlite3.Connection):
        self.snapshots: Dict[int, Dict[str, float]] = {}
        try:
            for ts, symbol, price in conn.execute("SELECT ts_ms, symbol, price FROM universe ORDER BY ts_ms"):
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
            self._cache[key] = statistics.median(changes) if len(changes) >= 20 else None
        return self._cache[key]


def market_baseline(rows: List) -> Dict[str, Dict[int, float]]:
    """Fallback: per horizon, the median raw return of all rows logged in the same hour."""
    baseline: Dict[str, Dict[int, float]] = {}
    for label in HORIZONS:
        buckets: Dict[int, List[float]] = {}
        for r in rows:
            if r[f'ret_{label}'] is not None:
                buckets.setdefault(hour_key(r), []).append(r[f'ret_{label}'])
        baseline[label] = {h: statistics.median(v) for h, v in buckets.items() if len(v) >= 5}
    return baseline


class Baseline:
    def __init__(self, rows: List, universe: Optional[UniverseBaseline] = None):
        self.universe = universe if universe else None
        self.fallback = market_baseline(rows)

    @property
    def source(self) -> str:
        return "whole universe (15m snapshots)" if self.universe else "median of logged coins per hour (no snapshots yet)"

    def of(self, row, label: str) -> Optional[float]:
        if self.universe:
            return self.universe.ret(row['ts_ms'], HORIZONS[label])
        return self.fallback[label].get(hour_key(row))


# ---------------------------------------------------------------------- per-group statistics

def excess_pairs(rows: List, label: str, baseline: Baseline) -> Tuple[List[float], List]:
    """Excess returns and their clusters (cluster_of)."""
    values, clusters = [], []
    for r in rows:
        if r[f'ret_{label}'] is None or not r['direction']:
            continue
        base = baseline.of(r, label)
        if base is not None:
            values.append(r['direction'] * (r[f'ret_{label}'] - base))
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
    ('confirmations positive', lambda r: None if _col(r, 'conf_n') is None else f"{_col(r, 'conf_n')} of 4"),
    ('market regime', lambda r: _col(r, 'regime')),
    ('P(edge) model', lambda r: None if _col(r, 'p_edge') is None else ('p >= 0.5' if _col(r, 'p_edge') >= 0.5 else 'p < 0.5')),
    ('crowd (Binance L/S accounts)', lambda r: None if _col(r, 'ls_global') is None else
        ('crowd long >= 2' if _col(r, 'ls_global') >= 2 else 'crowd short <= 1' if _col(r, 'ls_global') <= 1 else 'mixed')),
    ('HL large accounts', lambda r: None if not _col(r, 'hl_net_usd') or not _col(r, 'direction') else
        ('with the signal' if _col(r, 'hl_net_usd') * _col(r, 'direction') > 0 else 'against the signal')),
    ('Coinbase premium', lambda r: None if _col(r, 'cb_premium') is None else
        ('> +0.05%' if _col(r, 'cb_premium') > 0.0005 else '< -0.05%' if _col(r, 'cb_premium') < -0.0005 else 'flat')),
]


def features_table(console: Console, rows: List, baseline: Baseline):
    """Edge 4h of directional rows split by each recorded feature: does the filter / context add anything?"""
    directional = [r for r in rows if r['direction'] and r['ret_4h'] is not None and r['kind'] != 'card']
    if not directional:
        return
    table = Table(title="Edge 4h by feature (directional signals)", header_style="bold magenta", border_style="blue")
    for name in ("Feature", "Value", "N", "Edge 4h", "90% interval"):
        table.add_column(name, justify="left" if name in ("Feature", "Value") else "right", no_wrap=True)
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
            edge = statistics.fmean(ex) if ex else None
            table.add_row(feature, value, Text(str(len(ex)), style="dim" if len(ex) < MIN_SAMPLE else "white"),
                          pct(edge), ci_text(ex, clusters=clusters))
            feature = ""
    console.print(table)


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


def cards_table(console: Console, rows: List):
    """Finished cards by status: why they ended and what price did afterwards in the card's direction."""
    cards = [r for r in rows if r['kind'] == 'card']
    if not cards:
        return
    table = Table(title="Finished cards: what price did afterwards (in the card's direction)",
                  header_style="bold magenta", border_style="blue")
    for name in ("Card", "N", "after 15m", "after 1h", "after 4h", "vetoed triggers"):
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


def _report(console: Console, conn: sqlite3.Connection, db: str, days: Optional[float], last: int, all_versions: bool):
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
    table.add_column("Med 4h", justify="right", no_wrap=True, min_width=7)
    table.add_column("Best 4h", justify="right", no_wrap=True)
    table.add_column("Worst 4h", justify="right", no_wrap=True, min_width=8)

    order = sorted(groups, key=lambda g: ({'structured': 0, 'setup': 1, 'anomaly': 2, 'entry': 3, 'card': 4}.get(groups[g][0]['kind'], 3), g))
    for key in order:
        st = group_stats(groups[key], baseline)
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
        table.add_row(name, n_label, *cells, edge, pct(st['med_4h']), pct(st['mfe']), pct(st['mae']))
    console.print(table)
    console.print(
        "[dim]15m / 1h / 4h cells: win rate (net of the round-trip fee) / average return.\nWin = share of signals where "
        "price moved in the signal's direction by more than the fee (↕ rows: share of up moves; Avg = average move "
        "size either way).\nEdge 4h = average 4h return in the signal's direction minus the market baseline over the "
        "same window; [lo..hi] = 90% bootstrap interval (green: above 0, red: below 0, grey: can't tell yet).\n"
        "✗ = vetoed setups (not shown as cards). Best/Worst 4h = average largest favorable / adverse move within 4h.\n"
        f"N (x) = x signals already have a 4h result. Grey N = fewer than {MIN_SAMPLE} results.[/dim]"
    )

    levels_table(console, {k: v for k, v in groups.items() if k.startswith('ENTRY')})
    sources_table(console, rows)
    cards_table(console, rows)
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
