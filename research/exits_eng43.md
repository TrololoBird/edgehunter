# Exit rules and costs on the card replay (2337 trades the bot took, 402 coins)

Development: 2025-04-09 .. 2025-12-19; holdout: 2025-12-19 .. 2026-08-30. Result = net move of price per trade (% of the position; x leverage for the margin), after the round-trip cost. The limit scenario reuses the market path (the replay's --entry maker measures the fill rate and adverse selection).

## Development: every strategy x rule x cost (BH q over the whole grid)

| strategy | cost | rule | n | mean net % [90%] | q | win |
|---|---|---|---:|---|---:|---:|
| ALL | limit 0.07% | be05_tp1 | 1212 | -0.064 [-0.173..+0.042] | 0.500 | 29% |
| ALL | limit 0.07% | be05_tp2 | 1212 | -0.076 [-0.197..+0.041] | 0.500 | 15% |
| ALL | limit 0.07% | time240 | 1212 | -0.081 [-0.230..+0.067] | 0.501 | 56% |
| ALL | limit 0.07% | fix1r | 1212 | -0.084 [-0.303..+0.144] | 0.599 | 49% |
| ALL | limit 0.07% | time60 | 1212 | -0.090 [-0.177..-0.010] | 0.299 | 48% |
| ALL | limit 0.07% | trail1r | 1212 | -0.118 [-0.374..+0.169] | 0.559 | 48% |
| ALL | limit 0.07% | wide2x | 1212 | -0.144 [-0.392..+0.119] | 0.500 | 52% |
| ALL | limit 0.07% | fix2r | 1212 | -0.144 [-0.416..+0.156] | 0.534 | 42% |
| ALL | limit 0.07% | tp1 | 1212 | -0.158 [-0.345..+0.029] | 0.431 | 55% |
| ALL | limit 0.07% | be1r_tp2 | 1212 | -0.181 [-0.424..+0.091] | 0.460 | 38% |
| ALL | limit 0.07% | fix3r | 1212 | -0.182 [-0.455..+0.115] | 0.500 | 41% |
| ALL | limit 0.07% | tp2 | 1212 | -0.212 [-0.470..+0.066] | 0.451 | 43% |
| ALL | market 0.20% | be05_tp1 | 1212 | -0.194 [-0.303..-0.088] | 0.062 | 28% |
| ALL | market 0.20% | be05_tp2 | 1212 | -0.206 [-0.327..-0.089] | 0.056 | 14% |
| ALL | market 0.20% | time240 | 1212 | -0.211 [-0.360..-0.063] | 0.122 | 53% |
| ALL | market 0.20% | fix1r | 1212 | -0.214 [-0.433..+0.014] | 0.383 | 49% |
| ALL | market 0.20% | time60 | 1212 | -0.220 [-0.307..-0.140] | 0.024 | 42% |
| ALL | market 0.20% | trail1r | 1212 | -0.248 [-0.504..+0.039] | 0.410 | 46% |
| ALL | market 0.20% | wide2x | 1212 | -0.274 [-0.522..-0.011] | 0.336 | 51% |
| ALL | market 0.20% | fix2r | 1212 | -0.274 [-0.546..+0.026] | 0.383 | 41% |
| ALL | market 0.20% | tp1 | 1212 | -0.288 [-0.475..-0.101] | 0.122 | 53% |
| ALL | market 0.20% | be1r_tp2 | 1212 | -0.311 [-0.554..-0.039] | 0.295 | 38% |
| ALL | market 0.20% | fix3r | 1212 | -0.312 [-0.585..-0.015] | 0.336 | 40% |
| ALL | market 0.20% | tp2 | 1212 | -0.342 [-0.600..-0.064] | 0.255 | 42% |
| continuation | limit 0.07% | time60 | 110 | -0.075 [-0.459..+0.280] | 0.770 | 49% |
| continuation | limit 0.07% | be05_tp1 | 110 | -0.186 [-0.508..+0.133] | 0.500 | 14% |
| continuation | limit 0.07% | be05_tp2 | 110 | -0.206 [-0.555..+0.146] | 0.500 | 7% |
| continuation | limit 0.07% | fix1r | 110 | -0.389 [-1.381..+0.677] | 0.613 | 47% |
| continuation | limit 0.07% | time240 | 110 | -0.391 [-1.057..+0.274] | 0.500 | 46% |
| continuation | limit 0.07% | trail1r | 110 | -0.651 [-1.615..+0.350] | 0.500 | 46% |
| continuation | limit 0.07% | tp1 | 110 | -0.716 [-1.659..+0.229] | 0.460 | 41% |
| continuation | limit 0.07% | fix2r | 110 | -0.826 [-1.946..+0.376] | 0.460 | 35% |
| continuation | limit 0.07% | be1r_tp2 | 110 | -1.052 [-2.002..-0.019] | 0.353 | 23% |
| continuation | limit 0.07% | tp2 | 110 | -1.156 [-2.160..-0.035] | 0.336 | 31% |
| continuation | limit 0.07% | fix3r | 110 | -1.436 [-2.381..-0.498] | 0.101 | 30% |
| continuation | limit 0.07% | wide2x | 110 | -1.653 [-2.688..-0.612] | 0.101 | 35% |
| continuation | market 0.20% | time60 | 110 | -0.205 [-0.589..+0.150] | 0.500 | 47% |
| continuation | market 0.20% | be05_tp1 | 110 | -0.316 [-0.638..+0.003] | 0.358 | 14% |
| continuation | market 0.20% | be05_tp2 | 110 | -0.336 [-0.685..+0.016] | 0.379 | 7% |
| continuation | market 0.20% | fix1r | 110 | -0.519 [-1.511..+0.547] | 0.557 | 47% |
| continuation | market 0.20% | time240 | 110 | -0.521 [-1.187..+0.144] | 0.451 | 44% |
| continuation | market 0.20% | trail1r | 110 | -0.781 [-1.745..+0.220] | 0.451 | 45% |
| continuation | market 0.20% | tp1 | 110 | -0.846 [-1.789..+0.099] | 0.410 | 41% |
| continuation | market 0.20% | fix2r | 110 | -0.956 [-2.076..+0.246] | 0.451 | 35% |
| continuation | market 0.20% | be1r_tp2 | 110 | -1.182 [-2.132..-0.149] | 0.290 | 23% |
| continuation | market 0.20% | tp2 | 110 | -1.286 [-2.290..-0.165] | 0.255 | 31% |
| continuation | market 0.20% | fix3r | 110 | -1.566 [-2.511..-0.628] | 0.056 | 30% |
| continuation | market 0.20% | wide2x | 110 | -1.783 [-2.818..-0.742] | 0.056 | 35% |
| sweep | limit 0.07% | wide2x | 1072 | -0.023 [-0.271..+0.234] | 0.817 | 54% |
| sweep | limit 0.07% | be05_tp1 | 1072 | -0.048 [-0.167..+0.058] | 0.570 | 32% |
| sweep | limit 0.07% | time240 | 1072 | -0.057 [-0.210..+0.080] | 0.580 | 57% |
| sweep | limit 0.07% | be05_tp2 | 1072 | -0.059 [-0.192..+0.063] | 0.546 | 16% |
| sweep | limit 0.07% | fix1r | 1072 | -0.066 [-0.278..+0.150] | 0.613 | 50% |
| sweep | limit 0.07% | trail1r | 1072 | -0.082 [-0.343..+0.207] | 0.613 | 49% |
| sweep | limit 0.07% | fix3r | 1072 | -0.085 [-0.367..+0.218] | 0.618 | 42% |
| sweep | limit 0.07% | time60 | 1072 | -0.097 [-0.186..-0.016] | 0.255 | 48% |
| sweep | limit 0.07% | fix2r | 1072 | -0.106 [-0.380..+0.190] | 0.580 | 43% |
| sweep | limit 0.07% | be1r_tp2 | 1072 | -0.115 [-0.366..+0.152] | 0.546 | 40% |
| sweep | limit 0.07% | tp1 | 1072 | -0.133 [-0.312..+0.045] | 0.451 | 56% |
| sweep | limit 0.07% | tp2 | 1072 | -0.146 [-0.404..+0.131] | 0.500 | 44% |
| sweep | market 0.20% | wide2x | 1072 | -0.153 [-0.401..+0.104] | 0.500 | 52% |
| sweep | market 0.20% | be05_tp1 | 1072 | -0.178 [-0.297..-0.072] | 0.056 | 30% |
| sweep | market 0.20% | time240 | 1072 | -0.187 [-0.340..-0.050] | 0.189 | 54% |
| sweep | market 0.20% | be05_tp2 | 1072 | -0.189 [-0.322..-0.067] | 0.101 | 15% |
| sweep | market 0.20% | fix1r | 1072 | -0.196 [-0.408..+0.020] | 0.410 | 49% |
| sweep | market 0.20% | trail1r | 1072 | -0.212 [-0.473..+0.077] | 0.451 | 46% |
| sweep | market 0.20% | fix3r | 1072 | -0.215 [-0.497..+0.088] | 0.456 | 41% |
| sweep | market 0.20% | time60 | 1072 | -0.227 [-0.316..-0.146] | 0.024 | 42% |
| sweep | market 0.20% | fix2r | 1072 | -0.236 [-0.510..+0.060] | 0.451 | 42% |
| sweep | market 0.20% | be1r_tp2 | 1072 | -0.245 [-0.496..+0.022] | 0.383 | 39% |
| sweep | market 0.20% | tp1 | 1072 | -0.263 [-0.442..-0.085] | 0.122 | 54% |
| sweep | market 0.20% | tp2 | 1072 | -0.276 [-0.534..+0.001] | 0.358 | 43% |
| wyckoff | limit 0.07% | wide2x | 30 | +1.081 [-0.375..+2.702] | 0.460 | 53% |
| wyckoff | limit 0.07% | tp1 | 30 | +1.020 [-0.330..+2.534] | 0.460 | 53% |
| wyckoff | limit 0.07% | fix2r | 30 | +1.012 [-0.539..+2.807] | 0.500 | 47% |
| wyckoff | limit 0.07% | fix3r | 30 | +0.939 [-0.610..+2.612] | 0.500 | 47% |
| wyckoff | limit 0.07% | tp2 | 30 | +0.885 [-0.620..+2.532] | 0.510 | 47% |
| wyckoff | limit 0.07% | be1r_tp2 | 30 | +0.667 [-0.682..+2.154] | 0.559 | 43% |
| wyckoff | limit 0.07% | trail1r | 30 | +0.537 [-0.735..+1.982] | 0.613 | 50% |
| wyckoff | limit 0.07% | fix1r | 30 | +0.375 [-0.736..+1.574] | 0.652 | 50% |
| wyckoff | limit 0.07% | time240 | 30 | +0.202 [-0.455..+0.761] | 0.616 | 53% |
| wyckoff | limit 0.07% | time60 | 30 | +0.087 [-0.251..+0.435] | 0.720 | 60% |
| wyckoff | limit 0.07% | be05_tp1 | 30 | -0.187 [-0.464..+0.052] | 0.451 | 7% |
| wyckoff | limit 0.07% | be05_tp2 | 30 | -0.200 [-0.483..+0.061] | 0.451 | 3% |
| wyckoff | market 0.20% | wide2x | 30 | +0.951 [-0.505..+2.572] | 0.500 | 50% |
| wyckoff | market 0.20% | tp1 | 30 | +0.890 [-0.460..+2.404] | 0.500 | 53% |
| wyckoff | market 0.20% | fix2r | 30 | +0.882 [-0.669..+2.677] | 0.522 | 47% |
| wyckoff | market 0.20% | fix3r | 30 | +0.809 [-0.740..+2.482] | 0.548 | 47% |
| wyckoff | market 0.20% | tp2 | 30 | +0.755 [-0.750..+2.402] | 0.559 | 47% |
| wyckoff | market 0.20% | be1r_tp2 | 30 | +0.537 [-0.812..+2.024] | 0.613 | 43% |
| wyckoff | market 0.20% | trail1r | 30 | +0.407 [-0.865..+1.852] | 0.684 | 50% |
| wyckoff | market 0.20% | fix1r | 30 | +0.245 [-0.866..+1.444] | 0.770 | 50% |
| wyckoff | market 0.20% | time240 | 30 | +0.072 [-0.585..+0.631] | 0.817 | 53% |
| wyckoff | market 0.20% | time60 | 30 | -0.043 [-0.381..+0.305] | 0.817 | 43% |
| wyckoff | market 0.20% | be05_tp1 | 30 | -0.317 [-0.594..-0.078] | 0.127 | 7% |
| wyckoff | market 0.20% | be05_tp2 | 30 | -0.330 [-0.613..-0.069] | 0.225 | 3% |

## Holdout: the best development rule of each strategy, tested once

| strategy | cost | rule (chosen on development) | dev mean net % | holdout n | holdout mean net % [90%] | holdout win |
|---|---|---|---:|---:|---|---:|
| continuation | market 0.20% | time60 | -0.205 | 74 | -0.570 [-0.974..-0.154] | 28% |
| continuation | limit 0.07% | time60 | -0.075 | 74 | -0.440 [-0.844..-0.024] | 36% |
| sweep | market 0.20% | wide2x | -0.153 | 1015 | -0.137 [-0.314..+0.029] | 53% |
| sweep | limit 0.07% | wide2x | -0.023 | 1015 | -0.007 [-0.184..+0.159] | 55% |
| wyckoff | market 0.20% | wide2x | +0.951 | 36 | -0.284 [-1.136..+0.544] | 50% |
| wyckoff | limit 0.07% | wide2x | +1.081 | 36 | -0.154 [-1.006..+0.674] | 50% |
| ALL | market 0.20% | be05_tp1 | -0.194 | 1125 | -0.284 [-0.360..-0.209] | 26% |
| ALL | limit 0.07% | be05_tp1 | -0.064 | 1125 | -0.154 [-0.230..-0.079] | 28% |

## Verdict

No strategy x exit rule chosen on development stays above 0 on the holdout: changing the exits (breakeven, trailing, time, fixed targets, wider stops) does not make these entries profitable.
