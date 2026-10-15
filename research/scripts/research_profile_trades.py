"""
Plan 3.6 (eng-59): how far the bot's OHLC volume profile (zones.volume_profile: a candle's volume spread evenly over
its range) is from the profile of the actual trades. Pre-registered: the recorder keeps taker flow per second without
prices, so the reference is the Binance archive's futures aggTrades (every trade's price and size).

For `--coins` coins ranked 20.. by volume (BTC / ETH days are hundreds of MB) x `--days` recent UTC days: the day's
POC / VAH / VAL from (a) the trades (each price level is a zero-range "candle" carrying its volume - the same function,
the same bucket grid), (b) 1m, (c) 5m, (d) 15m candles of the same day. Error = |level_ohlc - level_trades| in the
day's ATR(15m) and in buckets. Decision: if the 15m / 5m profile's median POC error > 1 bucket while 1m stays <= 1
bucket, the live profile moves to 1m candles; otherwise it stays.

Run: .venv\\Scripts\\python research_profile_trades.py [--coins 8] [--days 5] [--out research/profile_trades.md]
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import argparse
import io
import os
import zipfile
from datetime import date, timedelta
from typing import Dict, List, Optional

import numpy as np

from config import CONFIG
from zones import volume_profile

DAY_MS = 86_400_000


def trades_of(arch, symbol: str, day: date) -> Optional[np.ndarray]:
    data = arch._fetch(f"futures/um/daily/aggTrades/{symbol}/{symbol}-aggTrades-{day.isoformat()}.zip")
    if data is None:
        return None
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        raw = zf.read(zf.namelist()[0])
    lines = raw.split(b'\n')
    if lines and not lines[0][:1].isdigit():
        lines = lines[1:]
    out = np.empty((len(lines), 3))
    n = 0
    for ln in lines:
        if not ln:
            continue
        f = ln.split(b',')
        out[n] = (float(f[5]), float(f[1]), float(f[1]) * float(f[2]))    # ts, price, quote
        n += 1
    return out[:n]


def candles(tr: np.ndarray, minutes: int) -> List[List[float]]:
    ms = minutes * 60_000
    keys = (tr[:, 0] // ms).astype(np.int64)
    out = []
    for k in np.unique(keys):
        s = tr[keys == k]
        out.append([float(k * ms), s[0, 1], s[:, 1].max(), s[:, 1].min(), s[-1, 1], s[:, 2].sum()])
    return out


def levels(profile) -> Dict[str, float]:
    out = {}
    for lv in profile:
        if lv.kind == 'poc':
            out['poc'] = lv.price
        elif lv.kind == 'va':
            out['vah' if lv.side > 0 else 'val'] = lv.price
    return out


def main():
    from history import Archive
    ap = argparse.ArgumentParser()
    ap.add_argument('--coins', type=int, default=8)
    ap.add_argument('--days', type=int, default=5)
    ap.add_argument('--rate', type=float, default=2e6)
    ap.add_argument('--out', default=os.path.join('research', 'profile_trades.md'))
    args = ap.parse_args()
    arch = Archive(rate_bytes=args.rate)
    end = date.today() - timedelta(days=2)
    first = end - timedelta(days=60)
    vols = []
    for s in arch.list_symbols('futures'):
        if not s.endswith('USDT') or '_' in s:
            continue
        try:
            d = arch.klines_ohlc('futures', s, '1d', first.replace(day=1), end)
        except Exception:
            continue
        if len(d) >= 20:
            vols.append((float(d[-20:, 5].mean()), s))
    pick = [s for _, s in sorted(vols, reverse=True)[20:20 + args.coins]]
    err: Dict[str, Dict[str, List[float]]] = {}
    step_of = CONFIG.zones.profile_buckets_per_atr
    for sym in pick:
        for k in range(args.days):
            day = end - timedelta(days=k)
            tr = trades_of(arch, sym, day)
            if tr is None or len(tr) < 1000:
                continue
            c15 = candles(tr, 15)
            trs = [max(c[2], p[4]) - min(c[3], p[4]) for p, c in zip(c15, c15[1:])]
            atr = float(np.mean(trs[-14:])) if len(trs) >= 14 else None
            if not atr:
                continue
            prices, inv = np.unique(np.round(tr[:, 1], 12), return_inverse=True)
            quote = np.bincount(inv, weights=tr[:, 2])
            pseudo = [[0.0, p, p, p, p, q] for p, q in zip(prices, quote)]
            ref = levels(volume_profile(pseudo, atr, 'trades'))
            for tf in (1, 5, 15):
                got = levels(volume_profile(candles(tr, tf) if tf != 15 else c15, atr, f'{tf}m'))
                for name in ('poc', 'vah', 'val'):
                    if name in ref and name in got:
                        err.setdefault(f'{tf}m', {}).setdefault(name, []).append(abs(got[name] - ref[name]) / atr)
            print(f"{sym} {day}: {len(tr)} trades", flush=True)
    lines = [f"# OHLC volume profile vs the trades' profile ({len(pick)} coins x {args.days} days)", '',
             f"Rules: the docstring of `research_profile_trades.py`. Bucket = 1/{step_of} ATR(15m).", '',
             '| candles | level | days | median error (ATR) | median (buckets) | p90 (buckets) |', '|---|---|---:|---:|---:|---:|']
    for tf, d in err.items():
        for name, v in d.items():
            a = np.array(v)
            lines.append(f"| {tf} | {name} | {len(a)} | {np.median(a):.3f} | {np.median(a) * step_of:.1f} | "
                         f"{np.percentile(a, 90) * step_of:.1f} |")
    text = '\n'.join(lines)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(text + '\n')
    print(text)


if __name__ == '__main__':
    main()
