"""The owner's proposal on the bot's REAL demo trades, in USDT: once price moves +X in the trade's favour, the stop
goes to break-even INCLUDING costs (entry +- fees + slippage); if that stop fills and price then crosses back beyond
the exit level in the trade's direction while the original trade would still be alive, re-enter at market (same qty,
original stop, same BE rule), at most `max_re` times. Baseline = the demo trade's actual USDT result.
Path: Binance 1m klines from the actual fill to the actual close (open trades: to now). Costs per side: taker 0.05% +
slippage 0.05% of notional. Stop first inside a minute (pessimistic). Run: python -I demo_be.py"""
import json, sqlite3, time, urllib.request

FEE = 0.0005 + 0.0005          # per side, fraction of notional
NOW = int(time.time() * 1000)


def klines(sym, start, end):
    out, t = [], start - start % 60000
    while t < end:
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval=1m&startTime={t}&limit=1500"
        rows = json.load(urllib.request.urlopen(url, timeout=30))
        if not rows:
            break
        out += [[r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4])] for r in rows]
        t = rows[-1][0] + 60000
        time.sleep(0.25)
    return [r for r in out if r[0] <= end]


def sim(path, d, entry, sl, qty, trig, max_re, base_exit):
    """USDT result with the BE + re-entry rule. trig = favourable move (fraction of price) that arms break-even."""
    pnl, pos_entry, stop, armed, re_left, flat_at = 0.0, entry, sl, False, max_re, None
    be_of = lambda e: e * (1 + d * 2 * FEE)                     # covers both sides' costs
    pnl -= FEE * entry * qty
    for i, (ts, o, h, l, c) in enumerate(path):
        if pos_entry is None:
            # flat after a BE stop: re-enter when price trades back beyond the exit level in our direction
            if re_left and d * (c - flat_at) > 0:
                pos_entry, stop, armed, re_left = c, sl, False, re_left - 1
                pnl -= FEE * c * qty
            continue
        adverse, fav = (l, h) if d > 0 else (h, l)
        if d * (adverse - stop) <= 0:
            px = stop if d * (o - stop) >= 0 else o
            pnl += d * (px - pos_entry) * qty - FEE * px * qty
            if armed:
                pos_entry, flat_at = None, px
                continue
            return pnl                                          # the original stop: the trade is over
        if not armed and d * (fav - pos_entry) >= trig * pos_entry:
            armed, stop = True, (max(stop, be_of(pos_entry)) if d > 0 else min(stop, be_of(pos_entry)))
    if pos_entry is not None:
        pnl += d * (base_exit - pos_entry) * qty - FEE * base_exit * qty
    return pnl


if __name__ == '__main__':
    db = sqlite3.connect('file:/opt/pump/demo_trades.db?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    trades = [dict(r) for r in db.execute("SELECT * FROM demo_trades WHERE entry_fill IS NOT NULL AND setup != 'UNTRACKED' "
                                          "AND qty > 0 ORDER BY id")]
    variants = [(f"BE at +{x:.1%}, re-entry x{m}", x, m) for x in (0.005, 0.01, 0.02) for m in (0, 2)]
    tot = {v[0]: 0.0 for v in variants}
    base_tot = 0.0
    lines = []
    for t in trades:
        sym = t['symbol'].split('/')[0] + 'USDT'
        end = t['closed_ms'] or NOW
        try:
            path = klines(sym, t['opened_ms'], end)
        except Exception as e:
            lines.append(f"{t['id']} {sym}: no klines ({e})"); continue
        if not path:
            continue
        d, entry, qty = t['direction'], t['entry_fill'], t['qty']
        exit_px = t['exit_avg'] or path[-1][4]
        base = t['pnl_usd'] if t['pnl_usd'] is not None else d * (exit_px - entry) * qty - 2 * FEE * entry * qty
        mfe = max(d * ((r[2] if d > 0 else r[3]) - entry) for r in path) * qty
        base_tot += base
        row = [f"{t['id']:>3} {sym:<14} {t['setup']:<18} база {base:+8.1f}  пик {mfe:+8.1f}"]
        for name, x, m in variants:
            r = sim(path, d, entry, t['sl'], qty, x, m, exit_px)
            tot[name] += r
            row.append(f"{r:+8.1f}")
        lines.append(' '.join(row))
    out = ["# Demo trades in USDT: actual vs break-even (+costs) and re-entry", "", "```",
           "id  symbol         setup              base / peak / " + ' | '.join(v[0] for v in variants), *lines, "```", "",
           f"**Total actual: {base_tot:+.1f} USDT**", ""]
    out += [f"- {k}: {v:+.1f} USDT ({v - base_tot:+.1f} vs actual)" for k, v in tot.items()]
    open('/opt/pump/research/exit_bt/report_demo_be.md', 'w').write('\n'.join(out) + '\n')
    print('\n'.join(out))
