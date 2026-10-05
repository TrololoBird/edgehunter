# Do level kinds hold better than random prices nearby? (100 coins, 2025-10-05 .. 2026-09-30)

Rejection = a 15m close back on the level's side within 1h of the first candle beyond it. Placebo = the same level shifted 0.3-1.5% (same side, same time). OR = odds ratio real / placebo; [90%] by coin bootstrap. OR ~1: the kind holds no better than any price.

| kind | tests | rejected | placebo rejected | OR [90%] | OR older half | OR newer half |
|---|---:|---:|---:|---|---:|---:|
| swing_15m | 442601 | 75.4% | 78.2% | 0.86 [0.84..0.87] | 0.87 | 0.84 |
| swing_1h | 139377 | 74.6% | 78.4% | 0.81 [0.79..0.82] | 0.82 | 0.80 |
| equal | 23439 | 74.0% | 78.6% | 0.78 [0.75..0.81] | 0.82 | 0.75 |
| pdhl | 62796 | 74.1% | 78.0% | 0.81 [0.79..0.83] | 0.82 | 0.80 |
| round | 12541 | 75.5% | 78.3% | 0.85 [0.82..0.89] | 0.91 | 0.76 |
| fvg_15m | 384165 | 74.1% | 77.6% | 0.82 [0.81..0.84] | 0.84 | 0.81 |
| fvg_1h | 105015 | 75.6% | 77.8% | 0.88 [0.86..0.90] | 0.90 | 0.87 |
| ob_1h | 58152 | 77.3% | 78.2% | 0.95 [0.93..0.98] | 0.96 | 0.94 |
| breaker_1h | 57038 | 73.6% | 77.2% | 0.82 [0.80..0.84] | 0.86 | 0.79 |
| poc | 34384 | 78.2% | 78.4% | 0.99 [0.96..1.02] | 1.02 | 0.95 |
| va | 67919 | 78.2% | 78.5% | 0.98 [0.96..1.00] | 0.99 | 0.97 |
| hvn | 12310 | 78.5% | 78.4% | 1.01 [0.96..1.05] | 1.01 | 1.00 |
| lvn | 35496 | 78.9% | 79.0% | 0.99 [0.97..1.03] | 0.97 | 1.02 |
