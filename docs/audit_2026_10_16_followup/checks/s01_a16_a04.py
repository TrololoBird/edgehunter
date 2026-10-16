"""S01 (VWAP), A16 (MFI / OBV volume), A04 (incomplete buckets): before / after.
Run: python checks/s01_a16_a04.py <repo root>. Offline, no network / DB."""
import sys
sys.path.insert(0, sys.argv[1])
import numpy as np
from levels import resample
from zones import vwap
from strategies.ind_panel import indicators

# S01: two candles, price 100 x 10 coins and 200 x 10 coins: true VWAP = 3000 / 20 = 150
rows = [[0, 100., 100., 100., 100., 1000., 500., 10.], [60_000, 200., 200., 200., 200., 2000., 1000., 10.]]
print('S01 VWAP (true 150):', [round(lv.price, 4) for lv in vwap(rows, 0, 'v')])
print('S01 VWAP old 7-col row (no base):', [round(lv.price, 4) for lv in vwap([r[:7] for r in rows], 0, 'v')])

# A16: alternating price 100 / 200, 10 coins each candle; quote = price x 10
price = np.array([100., 200.] * 150)
n = len(price)
k = np.column_stack([np.arange(n) * 60_000, price, price, price, price, price * 10, price * 5, np.full(n, 10.)])
ind = indicators(k)
print('A16 MFI (classic on base 66.667):', round(float(ind['mfi'][-1]), 3), 'OBV last:', float(ind['obv'][-1]))

# A04: only the last minute of a 4h bucket exists
one = [[239 * 60_000, 100., 101., 99., 100., 1., .5, .01]]
print('A04 one-minute 4h bucket ->', resample(one, 240, 240 * 60_000))
full = [[i * 60_000, 100., 101., 99., 100., 1., .5, .01] for i in range(240)]
print('A04 full 4h bucket ->', [[b[0], b[5], b[7]] for b in resample(full, 240, 240 * 60_000)])
gap = [c for c in full if c[0] != 100 * 60_000]
print('A04 4h bucket missing minute 100 ->', resample(gap, 240, 240 * 60_000))
print('chart (complete=False) keeps it:', len(resample(gap, 240, 240 * 60_000, complete=False)))
