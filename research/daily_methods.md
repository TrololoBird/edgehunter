# Daily methods on the archive (150 coins, 2023-10-01 .. 2026-09-30)

**Summary (cloud run 2026-10-04, 150 coins, 2023-10 .. 2026-09; the empty 'without NR4 / NR7' split fixed before this run).** By the pre-registered rule nothing is adopted. **ORB (Crabel, open +- Stretch, out at the close): NEGATIVE** in both halves (-0.113R / -0.070R, both 90% intervals below 0; 117,719 trades). **NR7 / NR4 filters: adopted by the NR sub-rule** (filtered days beat the unfiltered in both halves: NR7 -0.071 / -0.024 vs -0.124 / -0.085), but the filtered ORB is still negative - a filter of a losing trade, not an edge. **Cup with handle (daily)**: 17 trades in 3 years (4 in the older half) - too few to judge; the depth-in-weekly-ATR terciles (plan 2.10) were not printed (too few cups).

Rules: the docstring of `research_daily_methods.py` (pre-registered). Net of 0.20% round trip.

## ORB (Crabel, open +- Stretch, out at the close)
- older: 47457 trades, mean -0.113R [-0.155..-0.074], win 39%
- newer: 70262 trades, mean -0.070R [-0.109..-0.029], win 39%
- all: 117719 trades, mean -0.087R [-0.115..-0.058], win 39%

## ORB after an NR7 day
- older: 7527 trades, mean -0.071R [-0.157..+0.015], win 43%
- newer: 11596 trades, mean -0.024R [-0.081..+0.043], win 44%
- all: 19123 trades, mean -0.042R [-0.092..+0.009], win 43%

## ORB after an NR4 day (not NR7)
- older: 5506 trades, mean -0.105R [-0.153..-0.055], win 39%
- newer: 7578 trades, mean -0.038R [-0.115..+0.054], win 40%
- all: 13084 trades, mean -0.066R [-0.120..-0.010], win 40%

## ORB without NR4 / NR7
- older: 34424 trades, mean -0.124R [-0.172..-0.076], win 38%
- newer: 51088 trades, mean -0.085R [-0.131..-0.041], win 37%
- all: 85512 trades, mean -0.101R [-0.134..-0.066], win 37%

## Cup with handle (daily, O'Neil)
- older: 4 trades
- newer: 13 trades, mean -0.135R [-0.542..+0.173], win 46%
- all: 17 trades, mean -0.093R [-0.392..+0.145], win 47%

