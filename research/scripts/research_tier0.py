"""
Tier-0 thresholds measured on the live journal: for each input of the anomaly rules (RVOL, price z, OI z, whale
sweeps, liquidations, one-venue share), the effect of the rows in each bin = median of |4h move after| / the coin's
usual |4h move| (universe snapshots of the same journal). x1.0 = the reading adds nothing to the coin's normal
volatility; a threshold is worth something where the effect rises clearly above it.

    python research_tier0.py signals.eng6.bak.db signals.db
Writes research/tier0_thresholds.md.
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import bisect
import os
import sqlite3
import statistics
import sys
from collections import defaultdict

BINS = {
    'rvol_1m': [0, 2, 3, 5, 8, 12, 1e9],
    'abs(price_z)': [0, 1, 2, 3, 4, 6, 1e9],
    'abs(oi_z)': [0, 1, 2, 3, 4, 6, 1e9],
    'abs(whale_net_5m)': [0, 1, 2, 3, 5, 10, 1e9],
    'liq_long_5m + liq_short_5m': [0, 1, 1e4, 5e4, 2e5, 1e6, 1e12],
    'top_venue_share': [0, 0.5, 0.65, 0.8, 0.9, 1.01],
}


def usual_moves(conn):
    norm = lambda s: s.replace('/USDT:USDT', 'USDT').replace('/', '')
    series = defaultdict(list)
    for t, s, p in conn.execute("SELECT ts_ms, symbol, price FROM universe ORDER BY ts_ms"):
        series[norm(s)].append((t, p))
    out = {}
    for s, v in series.items():
        ts = [x[0] for x in v]
        moves = []
        for t, p in v:
            j = bisect.bisect_left(ts, t + 4 * 3_600_000)
            if j < len(v) and abs(ts[j] - t - 4 * 3_600_000) <= 600_000 and p:
                moves.append(abs(v[j][1] / p - 1))
        if len(moves) > 20:
            out[s] = statistics.mean(moves)
    return out, norm


def main(paths):
    rows = defaultdict(list)          # metric -> [(value, ratio)]
    for path in paths:
        conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        usual, norm = usual_moves(conn)
        for metric in BINS:
            q = f"SELECT {metric}, symbol, ret_4h FROM signals WHERE kind='anomaly' AND ret_4h IS NOT NULL AND {metric} IS NOT NULL"
            for value, s, r4 in conn.execute(q):
                base = usual.get(norm(s))
                if base:
                    rows[metric].append((value, abs(r4) / base))
    lines = ['# Tier-0 inputs vs what followed (live journal)', '',
             f"Journals: {', '.join(paths)}. Effect = median of |4h move after| / the coin's usual |4h move| "
             '(x1.0 = nothing beyond the coin\'s normal volatility). n per bin; bins with < 25 rows are marked.', '']
    for metric, edges in BINS.items():
        lines += [f"## {metric}", '', '| bin | n | effect (median) | effect (mean) |', '|---|---:|---:|---:|']
        for lo, hi in zip(edges, edges[1:]):
            vals = [r for v, r in rows[metric] if lo <= v < hi]
            if not vals:
                continue
            flag = '' if len(vals) >= 25 else ' (few)'
            lines.append(f"| {lo:g} .. {hi:g} | {len(vals)}{flag} | x{statistics.median(vals):.2f} | x{statistics.mean(vals):.2f} |")
        lines.append('')
    os.makedirs('research', exist_ok=True)
    with open(os.path.join('research', 'tier0_thresholds.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main(sys.argv[1:] or ['signals.db'])
