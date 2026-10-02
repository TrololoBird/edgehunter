# G — cross-sectional ranking (pre-registered: research/prereg/G_xsec.md)

422 coins, 3052 rebalances; dev before 2026-04-01, HOLDOUT after. Long top / short bottom decile, 4h, per-rebalance return; [90%] = weekly block bootstrap.

| Score | part | rebalances | gross | net [90%] | turnover |
|---|---|---:|---:|---|---:|
| gbm | dev | 2135 | +0.336% | -0.136% [-0.187..-0.090] | 0.48 |
| gbm | HOLDOUT | 917 | +0.163% | -0.342% [-0.428..-0.257] | 0.50 |
| mom | dev | 2135 | -0.061% | -0.400% [-0.447..-0.351] | 0.35 |
| mom | HOLDOUT | 917 | -0.022% | -0.377% [-0.477..-0.285] | 0.35 |
| rev | dev | 2135 | +0.061% | -0.278% [-0.320..-0.238] | 0.35 |
| rev | HOLDOUT | 917 | +0.022% | -0.333% [-0.418..-0.244] | 0.35 |

Deflated Sharpe of LightGBM's holdout series with 149 trials counted: 0.00

## Decision (pre-registered rule)

DOES NOT WORK - the topic is closed (research-findings)

LightGBM features (splits): r_4h 201, funding 122, amihud 121, lrv_7d 118, r_1h 117, r_24h 105, lvol 98, lrv_24h 93, r_7d 79, d_hi7 78, d_lo7 67, hod 61
