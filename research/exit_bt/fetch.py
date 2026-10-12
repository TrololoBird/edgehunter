"""Download Binance USDT-M 15m klines from data.binance.vision (monthly + daily zips) into data/<SYM>.npy."""
import io, sys, zipfile, urllib.request, numpy as np, datetime as dt
from concurrent.futures import ThreadPoolExecutor
TRADFI = set('XAU CL SKHYNIX XAG SOXL SNDK BZ KORU SPCX MU SAMSUNG SOXS MSTR CRCL SKHY US BTW'.split())
syms = [s for s in open('symbols.txt').read().split() if s[:-4] not in TRADFI]
months = [f"{y}-{m:02d}" for y in (2025, 2026) for m in range(1, 13) if "2025-08" <= f"{y}-{m:02d}" <= "2026-09"]
days = [f"2026-10-{d:02d}" for d in range(1, 12)]
B = "https://data.binance.vision/data/futures/um"
def get(url):
    try:
        z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(url, timeout=60).read()))
        rows = []
        for line in z.read(z.namelist()[0]).decode().splitlines():
            p = line.split(',')
            if p[0].isdigit(): rows.append([float(x) for x in p[:6]])
        return rows
    except Exception: return []
def one(s):
    urls = [f"{B}/monthly/klines/{s}/15m/{s}-15m-{m}.zip" for m in months] + [f"{B}/daily/klines/{s}/15m/{s}-15m-{d}.zip" for d in days]
    rows = [r for u in urls for r in get(u)]
    if rows:
        a = np.array(sorted({r[0]: r for r in rows}.values())); np.save(f"data/{s}.npy", a)
    return s, len(rows)
with ThreadPoolExecutor(8) as ex:
    for s, n in ex.map(one, syms): print(s, n, flush=True)
