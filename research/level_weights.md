# Do level kinds hold better than random prices nearby? (60 coins, 2025-10-05 .. 2026-09-30)

Rejection = a 15m close back on the level's side within 1h of the first candle beyond it. Placebo = the same level shifted 0.3-1.5% (same side, same time). OR = odds ratio real / placebo; [90%] by coin bootstrap. OR ~1: the kind holds no better than any price.

| kind | tests | rejected | placebo rejected | OR [90%] | OR older half | OR newer half |
|---|---:|---:|---:|---|---:|---:|
| swing_15m | 274785 | 75.4% | 78.1% | 0.86 [0.84..0.87] | 0.88 | 0.84 |
| swing_1h | 85596 | 74.4% | 78.4% | 0.80 [0.79..0.82] | 0.82 | 0.79 |
| equal | 15209 | 74.1% | 78.1% | 0.80 [0.76..0.84] | 0.82 | 0.79 |
| pdhl | 38099 | 73.7% | 77.9% | 0.79 [0.77..0.82] | 0.81 | 0.78 |
| round | 6987 | 75.4% | 78.0% | 0.86 [0.81..0.92] | 0.95 | 0.72 |
