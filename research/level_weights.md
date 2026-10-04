# Do level kinds hold better than random prices nearby? (60 coins, 2025-10-05 .. 2026-09-30)

Rejection = a 15m close back on the level's side within 1h of the first candle beyond it. Placebo = the same level shifted 0.3-1.5% (same side, same time). OR = odds ratio real / placebo; [90%] by coin bootstrap. OR ~1: the kind holds no better than any price.

| kind | tests | rejected | placebo rejected | OR [90%] | OR older half | OR newer half |
|---|---:|---:|---:|---|---:|---:|
| swing_15m | 274785 | 75.4% | 78.2% | 0.85 [0.84..0.87] | 0.87 | 0.83 |
| swing_1h | 85596 | 74.4% | 78.4% | 0.80 [0.79..0.82] | 0.82 | 0.79 |
| equal | 15209 | 74.1% | 78.6% | 0.78 [0.74..0.82] | 0.81 | 0.76 |
| pdhl | 38099 | 73.7% | 77.8% | 0.80 [0.78..0.83] | 0.81 | 0.79 |
| round | 6987 | 75.4% | 77.9% | 0.87 [0.82..0.92] | 0.93 | 0.74 |
| fvg_15m | 236695 | 74.4% | 77.7% | 0.83 [0.81..0.85] | 0.85 | 0.81 |
| fvg_1h | 63557 | 75.8% | 77.8% | 0.90 [0.87..0.92] | 0.92 | 0.87 |
| ob_1h | 35652 | 77.4% | 78.4% | 0.94 [0.92..0.97] | 0.98 | 0.91 |
| breaker_1h | 34941 | 73.7% | 77.1% | 0.83 [0.81..0.86] | 0.87 | 0.80 |
| poc | 20853 | 78.4% | 78.4% | 1.00 [0.96..1.04] | 1.03 | 0.97 |
| va | 41163 | 78.5% | 78.4% | 1.01 [0.98..1.03] | 1.02 | 0.99 |
| hvn | 7322 | 78.6% | 78.2% | 1.02 [0.96..1.08] | 1.09 | 0.96 |
| lvn | 21614 | 78.6% | 78.9% | 0.98 [0.94..1.02] | 0.96 | 1.00 |
