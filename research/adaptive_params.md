# Per-coin / per-volatility tuning of the exit geometry, walk-forward

200000 trades (the scenario-card triggers' entries), 36 geometries (stop in ATR14(1h) or in fixed %, target 1-3x the stop). Each month the choice is made on the 6 months before. Rules: the docstring of `research_adaptive.py`.

| choice | trades | mean net R |
|---|---:|---:|
| fixed | 192078 | -0.036 |
| per coin | 192078 | -0.049 |
| per volatility class | 192078 | -0.030 |
| random | 192078 | -0.101 |
| oracle (look-ahead, bound) | 192078 | +0.029 |

## Every geometry over the whole window (no choice)

| stop | target | mean net R |
|---|---|---:|
| 1 ATR | 1x | -0.211 |
| 1 ATR | 1.5x | -0.210 |
| 1 ATR | 2x | -0.204 |
| 1 ATR | 3x | -0.200 |
| 1.5 ATR | 1x | -0.142 |
| 1.5 ATR | 1.5x | -0.137 |
| 1.5 ATR | 2x | -0.134 |
| 1.5 ATR | 3x | -0.131 |
| 2 ATR | 1x | -0.104 |
| 2 ATR | 1.5x | -0.102 |
| 2 ATR | 2x | -0.098 |
| 2 ATR | 3x | -0.092 |
| 3 ATR | 1x | -0.070 |
| 3 ATR | 1.5x | -0.065 |
| 3 ATR | 2x | -0.060 |
| 3 ATR | 3x | -0.051 |
| 4 ATR | 1x | -0.054 |
| 4 ATR | 1.5x | -0.050 |
| 4 ATR | 2x | -0.044 |
| 4 ATR | 3x | -0.042 |
| 1% | 1x | -0.263 |
| 1% | 1.5x | -0.241 |
| 1% | 2x | -0.231 |
| 1% | 3x | -0.216 |
| 2% | 1x | -0.116 |
| 2% | 1.5x | -0.109 |
| 2% | 2x | -0.102 |
| 2% | 3x | -0.096 |
| 4% | 1x | -0.059 |
| 4% | 1.5x | -0.053 |
| 4% | 2x | -0.046 |
| 4% | 3x | -0.041 |
| 8% | 1x | -0.027 |
| 8% | 1.5x | -0.023 |
| 8% | 2x | -0.021 |
| 8% | 3x | -0.021 |
