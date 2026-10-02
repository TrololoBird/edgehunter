# G — cross-sectional ranking (pre-registered: research/prereg/G_xsec.md)

40 coins, 3052 rebalances; dev before 2026-04-01, HOLDOUT after. Long top / short bottom decile, 4h, per-rebalance return; [90%] = weekly block bootstrap.

| Score | part | rebalances | gross | net [90%] | turnover |
|---|---|---:|---:|---|---:|
| gbm | dev | 2135 | +0.292% | -0.068% [-0.148..+0.007] | 0.61 |
| gbm | HOLDOUT | 917 | -0.105% | -0.594% [-0.685..-0.495] | 0.61 |
| mom | dev | 2135 | -0.006% | -0.231% [-0.308..-0.157] | 0.39 |
| mom | HOLDOUT | 917 | +0.104% | -0.173% [-0.260..-0.085] | 0.38 |
| rev | dev | 2135 | +0.006% | -0.220% [-0.289..-0.146] | 0.39 |
| rev | HOLDOUT | 917 | -0.104% | -0.381% [-0.452..-0.307] | 0.38 |

Deflated Sharpe of LightGBM's holdout series with 133 trials counted: 0.00

## Decision (pre-registered rule)

DOES NOT WORK - the topic is closed (research-findings)

LightGBM features (splits): r_4h 4, lrv_7d 4, r_7d 3, r_24h 3, r_1h 3, lvol 3, funding 3, d_lo7 2, amihud 2, hod 1, lrv_24h 0, d_hi7 0
