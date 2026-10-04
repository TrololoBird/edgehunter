# Coin attributes vs method (250 coins, 2022-10-01 .. 2026-09-30)

**Summary (cloud run 2026-10-04, 250 coins, 2022-10 .. 2026-09; research_turtle degenerate-N bug fixed before this run).** Of 18 strategy x attribute tests one passes the pre-registered rule: **Connors short, correlation to BTC** - avoid the most BTC-correlated tercile (corr > 0.738): T2 vs T3 newer half +2.1% per trade [+1.05..+3.90], q 0.07. But even the best tercile of Connors short is NEGATIVE in both halves (-0.33% / -0.07%), so the 'rule' only says where the losing short loses least - and Connors short fails its own verdict (research/connors_crypto.md). Turtles and Connors long: no attribute is a pool rule; pools stay 'all'.

Rules: the docstring of `research_pools.py` (pre-registered). Turtles in R, Connors in % net per trade.
Terciles cut on the older half; T1 = lowest attribute values.

| strategy | attribute | cuts | half | T1 | T2 | T3 | n |
|---|---|---|---|---:|---:|---:|---:|
| breakout (Turtles) | vol_rank | 50 / 122 | older | +0.147 | +0.460 | +0.038 | 3477 |
| breakout (Turtles) | vol_rank | 50 / 122 | newer | +0.023 | -0.240 | -0.250 | 6320 |
| breakout (Turtles) | atr_pct | 0.0542 / 0.0748 | older | +1.546 | -0.316 | -0.581 | 3477 |
| breakout (Turtles) | atr_pct | 0.0542 / 0.0748 | newer | +0.376 | -0.350 | -0.314 | 6320 |
| breakout (Turtles) | chop | 51.4 / 57.8 | older | +0.537 | +0.375 | -0.264 | 3477 |
| breakout (Turtles) | chop | 51.4 / 57.8 | newer | -0.292 | -0.246 | -0.050 | 6319 |
| breakout (Turtles) | er | 0.062 / 0.172 | older | -0.032 | +0.335 | +0.345 | 3477 |
| breakout (Turtles) | er | 0.062 / 0.172 | newer | -0.135 | -0.142 | -0.282 | 6319 |
| breakout (Turtles) | beta | 0.998 / 1.32 | older | -0.071 | +0.310 | +0.408 | 3477 |
| breakout (Turtles) | beta | 0.998 / 1.32 | newer | -0.203 | -0.259 | -0.152 | 6320 |
| breakout (Turtles) | corr | 0.583 / 0.715 | older | -0.017 | +0.204 | +0.460 | 3477 |
| breakout (Turtles) | corr | 0.583 / 0.715 | newer | -0.348 | -0.400 | +0.282 | 6320 |
| connors long | vol_rank | 30 / 83.2 | older | -0.383 | -0.046 | -1.087 | 472 |
| connors long | vol_rank | 30 / 83.2 | newer | +1.105 | +2.055 | +1.478 | 595 |
| connors long | atr_pct | 0.0823 / 0.109 | older | -2.097 | -0.567 | +1.147 | 472 |
| connors long | atr_pct | 0.0823 / 0.109 | newer | +1.300 | +1.159 | +1.943 | 595 |
| connors long | chop | 50.4 / 56.1 | older | +0.388 | +0.408 | -2.320 | 472 |
| connors long | chop | 50.4 / 56.1 | newer | +2.109 | +0.336 | +1.901 | 595 |
| connors long | er | 0.114 / 0.253 | older | -0.490 | -0.953 | -0.072 | 472 |
| connors long | er | 0.114 / 0.253 | newer | +0.561 | +2.013 | +2.417 | 595 |
| connors long | beta | 0.842 / 1.15 | older | -1.216 | -0.416 | +0.114 | 472 |
| connors long | beta | 0.842 / 1.15 | newer | +1.383 | +2.126 | +1.329 | 595 |
| connors long | corr | 0.441 / 0.592 | older | -0.339 | +0.111 | -1.294 | 472 |
| connors long | corr | 0.441 / 0.592 | newer | +1.867 | +1.638 | +0.955 | 595 |
| connors short | vol_rank | 66 / 139 | older | -0.625 | -0.912 | -0.840 | 907 |
| connors short | vol_rank | 66 / 139 | newer | -0.388 | -1.079 | -1.553 | 2410 |
| connors short | atr_pct | 0.0496 / 0.0677 | older | -0.777 | -0.355 | -1.241 | 907 |
| connors short | atr_pct | 0.0496 / 0.0677 | newer | -2.529 | -1.917 | -0.301 | 2410 |
| connors short | chop | 47.5 / 56.9 | older | -1.383 | -0.883 | -0.105 | 907 |
| connors short | chop | 47.5 / 56.9 | newer | +0.528 | -1.072 | -2.931 | 2410 |
| connors short | er | 0.105 / 0.223 | older | -0.487 | -0.810 | -1.075 | 907 |
| connors short | er | 0.105 / 0.223 | newer | -2.868 | -1.166 | +0.343 | 2410 |
| connors short | beta | 1.02 / 1.28 | older | -1.741 | -0.685 | +0.054 | 907 |
| connors short | beta | 1.02 / 1.28 | newer | -1.324 | -1.109 | -1.178 | 2410 |
| connors short | corr | 0.642 / 0.738 | older | -0.999 | -0.325 | -1.048 | 907 |
| connors short | corr | 0.642 / 0.738 | newer | -0.657 | -0.072 | -2.773 | 2410 |

## Verdict (newer half: best older tercile minus worst)

| strategy | attribute | best | worst | same sign | 90% interval | q (BH) | pool rule |
|---|---|---|---|---|---|---:|---|
| breakout (Turtles) | vol_rank | T2 | T3 | yes | [-0.346..+0.334] | 0.76 | - |
| breakout (Turtles) | atr_pct | T1 | T3 | yes | [-0.280..+2.184] | 0.74 | - |
| breakout (Turtles) | chop | T1 | T3 | no | [-0.716..+0.186] | 1.00 | - |
| breakout (Turtles) | er | T3 | T1 | no | [-0.812..+0.457] | 0.91 | - |
| breakout (Turtles) | beta | T3 | T1 | yes | [-0.748..+0.609] | 0.76 | - |
| breakout (Turtles) | corr | T3 | T1 | yes | [-0.091..+1.453] | 0.55 | - |
| connors long | vol_rank | T2 | T3 | yes | [-1.257..+2.350] | 0.76 | - |
| connors long | atr_pct | T3 | T1 | yes | [-1.471..+4.087] | 0.76 | - |
| connors long | chop | T2 | T3 | no | [-2.933..-0.002] | 1.00 | - |
| connors long | er | T3 | T2 | yes | [-2.659..+2.124] | 0.76 | - |
| connors long | beta | T3 | T1 | no | [-2.183..+2.816] | 0.76 | - |
| connors long | corr | T2 | T3 | yes | [-1.476..+3.723] | 0.76 | - |
| connors short | vol_rank | T1 | T2 | yes | [-0.150..+1.521] | 0.55 | - |
| connors short | atr_pct | T2 | T3 | no | [-3.969..+0.459] | 1.00 | - |
| connors short | chop | T3 | T1 | no | [-5.810..-1.160] | 1.00 | - |
| connors short | er | T1 | T3 | no | [-5.358..-1.300] | 1.00 | - |
| connors short | beta | T3 | T1 | yes | [-2.684..+3.327] | 0.76 | - |
| connors short | corr | T2 | T3 | yes | [+1.049..+3.896] | 0.07 | ADOPT |
