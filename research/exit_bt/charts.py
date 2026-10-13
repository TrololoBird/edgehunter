"""Charts of the demo trades for a manual review: Binance 15m candles from 36h before the entry to 8h after the close,
the entry / stop / targets / exit, the 1h swing highs / lows of the 3 days before the entry (5-bar fractals) and the
previous day's high / low. 4 trades a picture. Run: python -I charts.py OUT_DIR"""
import json, os, sqlite3, sys, time, urllib.request
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)


def kl(sym, interval, start, end):
    out, t = [], start
    while t < end:
        rows = json.load(urllib.request.urlopen(
            f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval={interval}&startTime={t}&limit=1500", timeout=30))
        if not rows:
            break
        out += [[r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4])] for r in rows]
        t = rows[-1][0] + 1
        time.sleep(0.2)
    return [r for r in out if r[0] <= end]


def fractals(k, n=2):
    hi, lo = [], []
    for i in range(n, len(k) - n):
        if all(k[i][2] > k[j][2] for j in range(i - n, i + n + 1) if j != i):
            hi.append(k[i][2])
        if all(k[i][3] < k[j][3] for j in range(i - n, i + n + 1) if j != i):
            lo.append(k[i][3])
    return hi, lo


db = sqlite3.connect('file:/opt/pump/demo_trades.db?mode=ro', uri=True)
db.row_factory = sqlite3.Row
trades = [dict(r) for r in db.execute("SELECT * FROM demo_trades WHERE entry_fill IS NOT NULL AND setup != 'UNTRACKED' ORDER BY id")]
now = int(time.time() * 1000)
for page in range(0, len(trades), 4):
    fig, axes = plt.subplots(2, 2, figsize=(22, 13))
    for ax, t in zip(axes.flat, trades[page:page + 4]):
        sym = t['symbol'].split('/')[0] + 'USDT'
        e0, e1 = t['opened_ms'], (t['closed_ms'] or now)
        k = kl(sym, '15m', e0 - 36 * 3600_000, min(now, e1 + 8 * 3600_000))
        h1 = kl(sym, '1h', e0 - 72 * 3600_000, e0)
        for x in k:
            col = '#26a69a' if x[4] >= x[1] else '#ef5350'
            ax.vlines(x[0], x[3], x[2], color=col, lw=0.8)
            ax.vlines(x[0], min(x[1], x[4]), max(x[1], x[4]), color=col, lw=3)
        hi, lo = fractals(h1)
        lo_p, hi_p = min(x[3] for x in k), max(x[2] for x in k)
        for v in hi:
            if lo_p <= v <= hi_p:
                ax.axhline(v, color='#b0b0b0', lw=0.6, ls=':')
        for v in lo:
            if lo_p <= v <= hi_p:
                ax.axhline(v, color='#b0b0b0', lw=0.6, ls=':')
        d = t['direction']
        ax.axhline(t['entry_fill'], color='#1e88e5', lw=1.5, label=f"вход {t['entry_fill']:.6g}")
        ax.axhline(t['sl'], color='#e53935', lw=1.5, label=f"стоп {t['sl']:.6g}")
        for i, key in enumerate(('tp1', 'tp2', 'tp3')):
            if t[key] and lo_p * 0.9 <= t[key] <= hi_p * 1.1:
                ax.axhline(t[key], color='#43a047', lw=1, ls='--', label=f"{key} {t[key]:.6g}")
        ax.axvline(e0, color='#1e88e5', lw=1, ls='--')
        if t['closed_ms']:
            ax.axvline(t['closed_ms'], color='#555', lw=1, ls='--')
        pnl = f"{t['pnl_usd']:+.0f}$ ({t['r']:+.2f}R)" if t['pnl_usd'] is not None else 'открыта'
        ax.set_title(f"#{t['id']} {sym} {t['setup']} {'LONG' if d > 0 else 'SHORT'}  {pnl}  {t['close_reason'] or ''}", fontsize=11)
        ax.legend(loc='upper left', fontsize=8)
        ax.set_xticks([])
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, f"trades_{page // 4 + 1:02d}.png"), dpi=70)
    plt.close(fig)
    print('page', page // 4 + 1, flush=True)
