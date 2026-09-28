"""
Exit rules and costs for the bot's trades, chosen without fooling ourselves (Bailey, Borwein, Lopez de Prado & Zhu
2014, "The Probability of Backtest Overfitting"): the card replay's samples (research_cards.py --samples) carry, for
every trade, the gross result of twelve pre-registered exit rules on the same 1m path after the entry (EXIT_RULES:
stop / TP1, TP2, breakeven after +0.5% or +1R, a 1R trailing stop, time exits, fixed 1-3R targets, a doubled stop).

Protocol:
1. DEVELOPMENT = the older half of the window: every strategy x exit rule x cost scenario (market entry 0.20% round
   trip; a limit entry 0.07%, approximated on the same path) gets its mean net result per trade with a 4h x direction
   block-bootstrap interval and a Benjamini-Hochberg q-value over the whole grid;
2. the best rule of each strategy on development is taken ONCE to the newer half (the holdout) and reported there.
A rule is an improvement only if the holdout confirms it; the grid's best on development alone is expected to look
good by chance.

Run: .venv\\Scripts\\python research_exits.py --samples samples_12m.parquet [--out research/exits_12m.md]
"""
import argparse
import os

import numpy as np
import polars as pl

from research_cards import EXIT_RULES
from research_edges import bh, block_stats

COSTS = {'market 0.20%': 0.0020, 'limit 0.07%': 0.0007}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--samples', default='research_samples.parquet')
    parser.add_argument('--out', default=os.path.join('research', 'exits_12m.md'))
    parser.add_argument('--all-trades', action='store_true', help='include the trades the bot\'s vetoes skipped')
    args = parser.parse_args()
    df = pl.read_parquet(args.samples).filter(pl.col('card_veto') == '')
    if not args.all_trades:
        df = df.filter(pl.col('trigger_veto') == '')
    cols = [f"x_{r}" for r in EXIT_RULES if f"x_{r}" in df.columns]
    df = df.drop_nulls(cols).sort('ts_ms')
    ts = df['ts_ms'].to_numpy()
    mid = ts.min() + (ts.max() - ts.min()) // 2
    blocks = (ts // (4 * 3_600_000)) * 2 + (df['direction'].to_numpy() > 0)
    strategies = sorted(df['strategy'].unique().to_list())
    dev, hold = ts < mid, ts >= mid
    date = lambda t: pl.from_epoch(pl.Series([int(t)]), 'ms')[0].strftime('%Y-%m-%d')  # noqa: E731

    grid = []
    for s in strategies + ['ALL']:
        ms = np.ones(len(df), bool) if s == 'ALL' else (df['strategy'] == s).to_numpy()
        for c_name, cost in COSTS.items():
            for col in cols:
                m = ms & dev
                if m.sum() < 30:
                    continue
                v = df[col].to_numpy()[m] - cost
                mean, lo, hi, p, k = block_stats(v, blocks[m])
                grid.append({'strategy': s, 'cost': c_name, 'rule': col[2:], 'n': int(m.sum()), 'mean': mean, 'lo': lo,
                             'hi': hi, 'p': p, 'win': float((v > 0).mean())})
    qs = bh([g['p'] for g in grid])
    for g, q in zip(grid, qs):
        g['q'] = q

    lines = [f"# Exit rules and costs on the card replay ({len(df)} trades {'incl. vetoed triggers' if args.all_trades else 'the bot took'}, "
             f"{df['symbol'].n_unique()} coins)", '',
             f"Development: {date(ts.min())} .. {date(mid)}; holdout: {date(mid)} .. {date(ts.max())}. Result = net move "
             "of price per trade (% of the position; x leverage for the margin), after the round-trip cost. The limit "
             "scenario reuses the market path (the replay's --entry maker measures the fill rate and adverse selection).",
             '', '## Development: every strategy x rule x cost (BH q over the whole grid)', '',
             '| strategy | cost | rule | n | mean net % [90%] | q | win |', '|---|---|---|---:|---|---:|---:|']
    for g in sorted(grid, key=lambda g: (g['strategy'], g['cost'], -g['mean'])):
        lines.append(f"| {g['strategy']} | {g['cost']} | {g['rule']} | {g['n']} | {g['mean'] * 100:+.3f} "
                     f"[{g['lo'] * 100:+.3f}..{g['hi'] * 100:+.3f}] | {g['q']:.3f} | {g['win']:.0%} |")

    lines += ['', '## Holdout: the best development rule of each strategy, tested once', '',
              '| strategy | cost | rule (chosen on development) | dev mean net % | holdout n | holdout mean net % [90%] | holdout win |',
              '|---|---|---|---:|---:|---|---:|']
    verdicts = []
    for s in strategies + ['ALL']:
        ms = np.ones(len(df), bool) if s == 'ALL' else (df['strategy'] == s).to_numpy()
        for c_name, cost in COSTS.items():
            cand = [g for g in grid if g['strategy'] == s and g['cost'] == c_name]
            if not cand:
                continue
            best = max(cand, key=lambda g: g['mean'])
            m = ms & hold
            if m.sum() < 30:
                continue
            v = df[f"x_{best['rule']}"].to_numpy()[m] - cost
            mean, lo, hi, p, k = block_stats(v, blocks[m])
            lines.append(f"| {s} | {c_name} | {best['rule']} | {best['mean'] * 100:+.3f} | {int(m.sum())} | "
                         f"{mean * 100:+.3f} [{lo * 100:+.3f}..{hi * 100:+.3f}] | {float((v > 0).mean()):.0%} |")
            if lo > 0:
                verdicts.append(f"{s} / {c_name} / {best['rule']}: holdout {mean * 100:+.3f}% [{lo * 100:+.3f}..{hi * 100:+.3f}]")
    lines += ['', '## Verdict', '',
              ('Confirmed on the holdout (90% interval above 0): ' + '; '.join(verdicts)) if verdicts else
              'No strategy x exit rule chosen on development stays above 0 on the holdout: changing the exits '
              '(breakeven, trailing, time, fixed targets, wider stops) does not make these entries profitable.']
    text = '\n'.join(lines) + '\n'
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)


if __name__ == '__main__':
    main()
