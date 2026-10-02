"""
The Turtles' systems (strategies/turtle.py) on the Binance archive's DAILY candles: System 1 (20-day breakout, skipped
after a winning S1 breakout) with System 2 (55-day) as its fail-safe, entry on the touch of the channel (the open when
the day gapped past it), stop 2N, pyramid +1 unit every 1/2 N up to 4 (all stops to 2N from the newest), exit on the
10-day (S1) / 20-day (S2) opposite channel, the stop or the channel touched intraday (the stop first on a day that
touches both). Costs: the round-trip fee + 5 bps slippage per unit. R = the result in risk units of ONE unit (2N).

    python research_turtle.py --start 2023-10-01 --end 2026-09-30 --coins 60 --holdout 2025-10-01
Prints per-system R (development / holdout), win rate, average units, and writes research/turtle.md.
"""
import argparse
import statistics
from datetime import date

from config import CONFIG
from strategies.turtle import n_series

COST = CONFIG.journal.fee_round_trip + 2 * 0.0005
MIN_N_FRAC = 0.002      # N below 0.2% of the price = a flat, untraded stretch (all-coin run: +-1e9 R outliers)


def trades(d1, cost=COST, eligible=None, placebo=None):
    """Replays the systems over daily candles [ts, o, h, l, c, ...] -> [(entry day ts, system, direction, R, units)].
    eligible: epoch days on which the coin passed the universe's volume floor (entries only then; None = every day);
    placebo: {epoch day: direction} - enter at that day's open instead of on a breakout (same N, stop, pyramid, exit
    as System 1)."""
    ns = n_series(d1)
    out, pos, last_s1_win = [], None, None
    for i in range(56, len(d1)):
        ts, o, h, l, c = d1[i][:5]
        if pos is not None:
            d, n0, units, stop = pos['d'], pos['n'], pos['units'], pos['stop']
            # pyramid during the day (in favour by 1/2 N each)
            while len(units) < 4:
                nxt = units[-1] + d * 0.5 * n0
                if (h >= nxt) if d > 0 else (l <= nxt):
                    units.append(nxt)
                    stop = nxt - d * 2 * n0
                else:
                    break
            days = 10 if pos['sys'] == 1 else 20
            chan = min(x[3] for x in d1[i - days:i]) if d > 0 else max(x[2] for x in d1[i - days:i])
            exit_px = None
            if (l <= stop) if d > 0 else (h >= stop):
                exit_px = min(o, stop) if d > 0 else max(o, stop)
            elif (l <= chan) if d > 0 else (h >= chan):
                exit_px = min(o, chan) if d > 0 else max(o, chan)
            if exit_px is not None:
                risk = 2 * n0
                r = sum(d * (exit_px - u) - cost * u for u in units) / risk
                out.append((pos['ts'], pos['sys'], d, r, len(units)))
                if pos['sys'] == 1:
                    last_s1_win = r > 0
                pos = None
                continue
            pos['stop'] = stop
            continue
        n = ns[i - 1]
        day = int(ts // 86_400_000)
        if not n or n < MIN_N_FRAC * d1[i - 1][4] or (eligible is not None and day not in eligible):
            continue
        if placebo is not None:
            if day in placebo:
                d = placebo[day]
                pos = {'d': d, 'n': n, 'units': [o], 'stop': o - d * 2 * n, 'sys': 1, 'ts': ts}
            continue
        hi20, lo20 = max(x[2] for x in d1[i - 20:i]), min(x[3] for x in d1[i - 20:i])
        hi55, lo55 = max(x[2] for x in d1[i - 55:i]), min(x[3] for x in d1[i - 55:i])
        for d, l20, l55, hit20, hit55 in ((1, hi20, hi55, h > hi20, h > hi55), (-1, lo20, lo55, l < lo20, l < lo55)):
            system = None
            if hit20 and not last_s1_win:
                system, level = 1, l20
            elif hit55:
                system, level = 2, l55
            if hit20 and last_s1_win:
                # the skipped S1 breakout is still traded on paper for the skip rule
                last_s1_win = None
            if system is None:
                continue
            entry = max(o, level) if d > 0 else min(o, level)
            pos = {'d': d, 'n': n, 'units': [entry], 'stop': entry - d * 2 * n, 'sys': system, 'ts': ts}
            break
    return out


def boot_mean(rows, n=2000, seed=7):
    """90% interval of the mean R, resampling calendar months (trades of one month ride one market)."""
    import numpy as np
    blocks = {}
    for r in rows:
        blocks.setdefault(int(r[0] // (30 * 86_400_000)), []).append(r[3])
    keys = list(blocks)
    rnd, means = np.random.default_rng(seed), []
    for _ in range(n):
        pick = [x for k in rnd.choice(len(keys), len(keys)) for x in blocks[keys[k]]]
        means.append(statistics.fmean(pick))
    means.sort()
    return means[int(0.05 * n)], means[int(0.95 * n)]


def summary(rows):
    if not rows:
        return 'no trades'
    rs = [r[3] for r in rows]
    lo, hi = boot_mean(rows)
    return (f"{len(rs)} trades, mean {statistics.fmean(rs):+.3f}R, median {statistics.median(rs):+.2f}R, "
            f"win {sum(r > 0 for r in rs) / len(rs):.0%}, avg units {statistics.fmean(r[4] for r in rows):.2f}, "
            f"total {sum(rs):+.1f}R, 90% month-block interval [{lo:+.3f}..{hi:+.3f}]R")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', default='2023-10-01')
    ap.add_argument('--end', default='2026-09-30')
    ap.add_argument('--holdout', default='2025-10-01')
    ap.add_argument('--coins', type=int, default=60)
    ap.add_argument('--rate', type=float, default=300_000)
    args = ap.parse_args()
    from history import Archive
    from pretrain import select_coins
    start, end, hold = (date.fromisoformat(x) for x in (args.start, args.end, args.holdout))
    archive = Archive(rate_bytes=args.rate)
    coins = select_coins(archive, start, end, CONFIG.exchange.min_24h_quote_volume_usd)[:args.coins]
    from datetime import datetime, timezone
    hold_ms = int(datetime(hold.year, hold.month, hold.day, tzinfo=timezone.utc).timestamp() * 1000)
    import numpy as np
    rnd = np.random.default_rng(11)
    dev, test, pdev, ptest = [], [], [], []
    for key, fut, _spot, days in coins:
        arr = archive.klines_ohlc('futures', fut, '1d', start, end)
        d1 = [list(map(float, row)) for row in arr]
        eligible = set(days)
        real = trades(d1, eligible=eligible)
        for t in real:
            (test if t[0] >= hold_ms else dev).append(t)
        # placebo: as many entries, same directions, on random eligible days of the same coin
        pool = sorted(eligible)
        if pool and real:
            plac = {pool[int(rnd.integers(len(pool)))]: t[2] for t in real}
            for t in trades(d1, eligible=eligible, placebo=plac):
                (ptest if t[0] >= hold_ms else pdev).append(t)
        print(f"{key}: {len([t for t in dev + test])} trades so far", flush=True)
    lines = ['# Turtles on the daily archive', '',
             f"{len(coins)} coins (entries only on days a coin passed the volume floor, N >= {MIN_N_FRAC:.1%} of price), {args.start} .. {args.end}, holdout from {args.holdout}; cost {COST:.2%} per unit", '']
    for name, rows in (('development', dev), ('holdout', test), ('placebo development', pdev),
                       ('placebo holdout', ptest)):
        lines.append(f"- {name}: {summary(rows)}")
        for sys in (1, 2):
            lines.append(f"  - System {sys}: {summary([r for r in rows if r[1] == sys])}")
    text = '\n'.join(lines)
    print(text)
    with open('research/turtle.md', 'w', encoding='utf-8') as f:
        f.write(text + '\n')


if __name__ == '__main__':
    main()
