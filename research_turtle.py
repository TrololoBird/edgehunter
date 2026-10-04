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


def trades(d1, cost=COST):
    """Replays the systems over daily candles [ts, o, h, l, c, ...] -> [(entry day ts, system, direction, R, units)]."""
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
        # a flat-lined market (delisted / settled contract: N ~ 1e-17 of the price) is no data: R explodes (-1.9e15)
        if not n or n < 1e-4 * d1[i - 1][4]:
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


def summary(rows):
    if not rows:
        return 'no trades'
    rs = [r[3] for r in rows]
    return (f"{len(rs)} trades, mean {statistics.fmean(rs):+.3f}R, median {statistics.median(rs):+.2f}R, "
            f"win {sum(r > 0 for r in rs) / len(rs):.0%}, avg units {statistics.fmean(r[4] for r in rows):.2f}, "
            f"total {sum(rs):+.1f}R")


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
    dev, test = [], []
    for key, fut, _spot, _days in coins:
        arr = archive.klines_ohlc('futures', fut, '1d', start, end)
        d1 = [list(map(float, row)) for row in arr]
        for t in trades(d1):
            (test if t[0] >= hold_ms else dev).append(t)
        print(f"{key}: {len([t for t in dev + test])} trades so far", flush=True)
    lines = ['# Turtles on the daily archive', '',
             f"{args.coins} coins, {args.start} .. {args.end}, holdout from {args.holdout}; cost {COST:.2%} per unit", '']
    for name, rows in (('development', dev), ('holdout', test)):
        lines.append(f"- {name}: {summary(rows)}")
        for sys in (1, 2):
            lines.append(f"  - System {sys}: {summary([r for r in rows if r[1] == sys])}")
    text = '\n'.join(lines)
    print(text)
    with open('research/turtle.md', 'w', encoding='utf-8') as f:
        f.write(text + '\n')


if __name__ == '__main__':
    main()
