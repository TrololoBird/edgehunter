# G — cross-sectional ranking (pre-registered: research/prereg/G_xsec.md)

350 coins, 3244 rebalances; dev before 2024-10-01, HOLDOUT after. Long top / short bottom decile, 4h, per-rebalance return; [90%] = weekly block bootstrap.

| Score | part | rebalances | gross | net [90%] | turnover |
|---|---|---:|---:|---|---:|
| gbm | dev | 2153 | +0.079% | -0.221% [-0.255..-0.187] | 0.36 |
| gbm | HOLDOUT | 1091 | +0.020% | -0.325% [-0.370..-0.284] | 0.41 |
| mom | dev | 2153 | +0.004% | -0.278% [-0.322..-0.234] | 0.36 |
| mom | HOLDOUT | 1091 | -0.041% | -0.336% [-0.391..-0.284] | 0.36 |
| rev | dev | 2153 | -0.004% | -0.286% [-0.324..-0.247] | 0.36 |
| rev | HOLDOUT | 1091 | +0.041% | -0.255% [-0.303..-0.206] | 0.36 |

Deflated Sharpe of LightGBM's holdout series with 163 trials counted: 0.00

## Decision (pre-registered rule)

DOES NOT WORK - the topic is closed (research-findings)

LightGBM features (splits): d_lo7 3, r_7d 2, r_4h 2, r_1h 2, lrv_7d 2, funding 2, lvol 1, r_24h 0, lrv_24h 0, hod 0, d_hi7 0, amihud 0
