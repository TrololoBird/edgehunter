# crypto_maniac's systems on the archive (card replay, placebo, holdout)

Window 2025-04-08 .. 2026-09-30: development before 2026-04-03, HOLDOUT from 2026-04-03. 422 coins, 438710 cards. R = net R of an entry replayed like the journal (next full minute's open + 5 bps, stop exits slipped, funding, 0.10% round-trip fee), exit at TP1 / stop / the trade's lifetime. Placebo = the same trade (direction, stop / target in %) at a random time of the same coin within +-7 days. [90%] = block bootstrap over 4h x direction blocks; q = Benjamini-Hochberg over the holdout rows.

| Setup | part | cards | entries | expired | invalid | win TP1 | R TP1 [90%] | placebo R | system - placebo [90%] | R TP2 |
|---|---|---:|---:|---:|---:|---:|---|---:|---|---:|
| AUCTION LONG | dev | 4608 | 833 | 20 | 0 | 24% | -0.095 [-0.233..+0.054] | -0.253 | +0.158 [-0.028..+0.344] | -0.068 |
| AUCTION LONG | HOLDOUT (q 0.650) | 1972 | 203 | 18 | 0 | 29% | -0.117 [-0.336..+0.103] | -0.408 | +0.291 [+0.027..+0.548] | -0.130 |
| AUCTION SHORT | dev | 3404 | 440 | 21 | 0 | 30% | -0.117 [-0.265..+0.030] | -0.098 | -0.019 [-0.234..+0.172] | -0.108 |
| AUCTION SHORT | HOLDOUT (q 0.650) | 1118 | 224 | 13 | 0 | 27% | -0.111 [-0.319..+0.092] | -0.299 | +0.188 [-0.105..+0.468] | -0.107 |
| BB M-TOP | dev | 147546 | 57273 | 87116 | 0 | 58% | -0.051 [-0.073..-0.027] | -0.051 | +0.000 [-0.023..+0.024] | -0.048 |
| BB M-TOP | HOLDOUT (q 0.005) | 49419 | 18063 | 30310 | 0 | 57% | -0.051 [-0.076..-0.026] | -0.076 | +0.026 [-0.001..+0.053] | -0.069 |
| BB W-BOTTOM | dev | 159152 | 52959 | 102237 | 0 | 53% | -0.110 [-0.137..-0.081] | -0.093 | -0.016 [-0.046..+0.014] | -0.109 |
| BB W-BOTTOM | HOLDOUT (q 0.004) | 52388 | 14566 | 36234 | 0 | 53% | -0.104 [-0.134..-0.072] | -0.080 | -0.023 [-0.056..+0.010] | -0.114 |
| CUP HANDLE | dev | 702 | 680 | 12 | 0 | 28% | -0.208 [-0.336..-0.081] | +0.193 | -0.402 [-0.540..-0.266] | -0.250 |
| CUP HANDLE | HOLDOUT (q 0.771) | 204 | 191 | 3 | 0 | 37% | +0.068 [-0.108..+0.251] | +0.616 | -0.553 [-0.776..-0.322] | -0.174 |
| SD DEMAND | dev | 6559 | 188 | 4185 | 43 | 38% | -0.040 [-0.217..+0.149] | +0.004 | -0.044 [-0.357..+0.252] | -0.142 |
| SD DEMAND | HOLDOUT (q 0.771) | 2293 | 80 | 1527 | 27 | 36% | +0.224 [-0.314..+0.981] | -0.173 | +0.397 [-0.204..+1.199] | +0.175 |
| SD SUPPLY | dev | 6661 | 37 | 1996 | 32 | 32% | -0.505 [-1.074..+0.279] | +0.357 | -0.863 [-1.577..+0.139] | -0.317 |
| SD SUPPLY | HOLDOUT | 1840 | 3 | 506 | 4 | 33% | — [—..—] | -1.057 | — [—..—] | +0.319 |
| TRENDLINE DOWN | dev | 132 | 16 | 112 | 0 | 31% | -0.455 [-0.837..-0.024] | +0.632 | -1.086 [-1.815..-0.321] | -0.076 |
| TRENDLINE DOWN | HOLDOUT | 27 | 6 | 21 | 0 | 67% | — [—..—] | +0.891 | — [—..—] | -0.398 |
| TRENDLINE UP | dev | 484 | 63 | 420 | 0 | 48% | +0.059 [-0.219..+0.360] | -0.140 | +0.200 [-0.163..+0.560] | -0.155 |
| TRENDLINE UP | HOLDOUT (q 0.781) | 201 | 27 | 173 | 0 | 37% | -0.076 [-0.522..+0.439] | -0.377 | +0.301 [-0.331..+0.985] | -0.129 |

A system WORKS here only if R TP1 > 0 in both parts, its holdout interval is above 0 and it beats the placebo in the holdout (the system - placebo interval above 0).
