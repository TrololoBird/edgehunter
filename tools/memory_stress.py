#!/usr/bin/env python
"""Bounded render stress check for the long-lived briefing worker."""
from __future__ import annotations

import argparse
import gc
import json
import pathlib
import resource
import sys
import time

import matplotlib.pyplot as plt

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import briefing_chart


def fixture():
    candles, price = [], 100.0
    for i in range(72):
        open_ = price
        high, low = price + 2, price - 2
        price += 0.1
        candles.append([i * 3_600_000, open_, high, low, price, 1000.0])
    zones = [
        {'side': -1, 'lo': 104, 'hi': 106, 'pad': 1, 'tol': 0.2, 'label': 'resistance', 'conf_tf': '1h'},
        {'side': 1, 'lo': 94, 'hi': 96, 'pad': 1, 'tol': 0.2, 'label': 'support', 'conf_tf': '1h'},
    ]
    return candles, price, zones


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--renders', type=int, default=1000)
    parser.add_argument('--max-growth-mb', type=float, default=256.0)
    args = parser.parse_args()
    if args.renders <= 0:
        raise SystemExit('--renders must be positive')
    candles, price, zones = fixture()
    gc.collect()
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    started = time.perf_counter()
    for _ in range(args.renders):
        briefing_chart.render('TESTUSDT', candles, price, zones, 2, atr_1d=5, candles_1h=candles)
    gc.collect()
    after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    growth_mb = (after - before) / 1024.0
    print(json.dumps({
        'renders': args.renders,
        'seconds': round(time.perf_counter() - started, 3),
        'rss_max_before_kb': before,
        'rss_max_after_kb': after,
        'rss_growth_mb': round(growth_mb, 2),
        'live_figures': len(plt.get_fignums()),
    }, sort_keys=True))
    if plt.get_fignums():
        raise SystemExit('render leaked live matplotlib figures')
    if growth_mb > args.max_growth_mb:
        raise SystemExit(f'render RSS growth {growth_mb:.1f} MB exceeds {args.max_growth_mb:.1f} MB')


if __name__ == '__main__':
    main()
