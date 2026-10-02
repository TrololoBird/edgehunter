# crypto_maniac's systems on the archive (card replay, placebo, holdout)

Window 2025-04-08 .. 2026-09-30: development before 2026-04-03, HOLDOUT from 2026-04-03. 422 coins, 465905 cards. R = net R of an entry replayed like the journal (next full minute's open + 5 bps, stop exits slipped, funding, 0.10% round-trip fee), exit at TP1 / stop / the trade's lifetime. Placebo = the same trade (direction, stop / target in %) at a random time of the same coin within +-7 days. [90%] = block bootstrap over 4h x direction blocks; q = Benjamini-Hochberg over the holdout rows.

| Setup | part | cards | entries | expired | invalid | win TP1 | R TP1 [90%] | placebo R | system - placebo [90%] | R TP2 |
|---|---|---:|---:|---:|---:|---:|---|---:|---|---:|
| AUCTION LONG | dev | 4694 | 681 | 257 | 0 | 25% | -0.042 [-0.186..+0.125] | -0.129 | +0.088 [-0.106..+0.287] | -0.026 |
| AUCTION LONG | HOLDOUT (q 0.864) | 1994 | 156 | 88 | 0 | 30% | -0.043 [-0.286..+0.213] | -0.226 | +0.183 [-0.138..+0.484] | -0.047 |
| AUCTION SHORT | dev | 3441 | 325 | 169 | 0 | 32% | -0.040 [-0.214..+0.136] | -0.024 | -0.016 [-0.234..+0.196] | -0.038 |
| AUCTION SHORT | HOLDOUT (q 0.864) | 1137 | 165 | 94 | 0 | 29% | -0.027 [-0.260..+0.213] | -0.337 | +0.310 [-0.018..+0.644] | -0.060 |
| BB M-TOP | dev | 158231 | 48255 | 106988 | 0 | 56% | -0.048 [-0.074..-0.024] | -0.052 | +0.004 [-0.023..+0.030] | -0.044 |
| BB M-TOP | HOLDOUT (q 0.004) | 52586 | 15306 | 36280 | 0 | 56% | -0.056 [-0.082..-0.029] | -0.082 | +0.026 [-0.001..+0.056] | -0.072 |
| BB W-BOTTOM | dev | 169517 | 43762 | 121881 | 0 | 51% | -0.109 [-0.140..-0.080] | -0.098 | -0.011 [-0.043..+0.020] | -0.109 |
| BB W-BOTTOM | HOLDOUT (q 0.003) | 55106 | 12021 | 41503 | 0 | 51% | -0.111 [-0.145..-0.078] | -0.077 | -0.034 [-0.071..+0.002] | -0.116 |
| CUP HANDLE | dev | 751 | 605 | 136 | 0 | 27% | -0.208 [-0.337..-0.067] | +0.253 | -0.461 [-0.607..-0.321] | -0.212 |
| CUP HANDLE | HOLDOUT (q 0.864) | 223 | 177 | 37 | 0 | 35% | +0.022 [-0.159..+0.217] | +0.564 | -0.518 [-0.744..-0.289] | -0.025 |
| SD DEMAND | dev | 6574 | 60 | 4326 | 43 | 37% | -0.144 [-0.392..+0.134] | -0.454 | +0.310 [-0.021..+0.664] | -0.213 |
| SD DEMAND | HOLDOUT (q 0.864) | 2300 | 30 | 1585 | 27 | 33% | -0.084 [-0.531..+0.380] | -0.255 | +0.171 [-0.489..+0.798] | +0.075 |
| SD SUPPLY | dev | 6665 | 12 | 2027 | 32 | 25% | -1.307 [-2.140..+1.196] | -0.250 | -1.057 [-2.061..+1.661] | -1.241 |
| SD SUPPLY | HOLDOUT | 1840 | 2 | 507 | 4 | 0% | — [—..—] | -1.082 | — [—..—] | -1.075 |
| TRENDLINE DOWN | dev | 132 | 0 | 0 | 0 | — | — [—..—] | — | — [—..—] | — |
| TRENDLINE DOWN | HOLDOUT | 27 | 0 | 0 | 0 | — | — [—..—] | — | — [—..—] | — |
| TRENDLINE UP | dev | 486 | 0 | 0 | 0 | — | — [—..—] | — | — [—..—] | — |
| TRENDLINE UP | HOLDOUT | 201 | 0 | 0 | 0 | — | — [—..—] | — | — [—..—] | — |

A system WORKS here only if R TP1 > 0 in both parts, its holdout interval is above 0 and it beats the placebo in the holdout (the system - placebo interval above 0).
