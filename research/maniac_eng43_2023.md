# crypto_maniac's systems on the archive (card replay, placebo, holdout)

Window 2023-10-08 .. 2025-03-31: development before 2024-10-02, HOLDOUT from 2024-10-02. 351 coins, 444000 cards. R = net R of an entry replayed like the journal (next full minute's open + 5 bps, stop exits slipped, funding, 0.10% round-trip fee), exit at TP1 / stop / the trade's lifetime. Placebo = the same trade (direction, stop / target in %) at a random time of the same coin within +-7 days. [90%] = block bootstrap over 4h x direction blocks; q = Benjamini-Hochberg over the holdout rows.

| Setup | part | cards | entries | expired | invalid | win TP1 | R TP1 [90%] | placebo R | system - placebo [90%] | R TP2 |
|---|---|---:|---:|---:|---:|---:|---|---:|---|---:|
| AUCTION LONG | dev | 4140 | 552 | 191 | 0 | 21% | -0.341 [-0.472..-0.199] | -0.290 | -0.051 [-0.219..+0.125] | -0.340 |
| AUCTION LONG | HOLDOUT (q 0.032) | 1805 | 232 | 92 | 0 | 17% | -0.506 [-0.735..-0.238] | -0.398 | -0.108 [-0.426..+0.230] | -0.490 |
| AUCTION SHORT | dev | 3329 | 342 | 138 | 0 | 28% | -0.119 [-0.283..+0.058] | -0.241 | +0.122 [-0.113..+0.356] | -0.096 |
| AUCTION SHORT | HOLDOUT (q 0.452) | 1708 | 170 | 67 | 0 | 26% | -0.142 [-0.375..+0.109] | +0.077 | -0.219 [-0.584..+0.160] | -0.168 |
| BB M-TOP | dev | 122104 | 39509 | 80351 | 0 | 57% | -0.040 [-0.064..-0.016] | -0.050 | +0.011 [-0.015..+0.036] | -0.034 |
| BB M-TOP | HOLDOUT (q 0.496) | 74342 | 27078 | 46187 | 0 | 58% | -0.019 [-0.062..+0.021] | -0.043 | +0.024 [-0.021..+0.067] | +0.002 |
| BB W-BOTTOM | dev | 134582 | 40898 | 91817 | 0 | 52% | -0.067 [-0.100..-0.034] | -0.095 | +0.029 [-0.006..+0.064] | -0.062 |
| BB W-BOTTOM | HOLDOUT (q 0.068) | 82553 | 26114 | 55101 | 0 | 53% | -0.066 [-0.112..-0.022] | -0.085 | +0.019 [-0.030..+0.069] | -0.090 |
| CUP HANDLE | dev | 690 | 576 | 107 | 0 | 30% | -0.044 [-0.180..+0.093] | +0.239 | -0.283 [-0.452..-0.108] | -0.059 |
| CUP HANDLE | HOLDOUT (q 0.452) | 673 | 546 | 115 | 0 | 30% | -0.111 [-0.265..+0.054] | +0.277 | -0.385 [-0.555..-0.191] | -0.128 |
| SD DEMAND | dev | 5002 | 19 | 2308 | 11 | 37% | -0.056 [-0.525..+0.494] | +0.816 | -0.872 [-1.730..-0.001] | -0.165 |
| SD DEMAND | HOLDOUT (q 0.452) | 2816 | 21 | 1769 | 14 | 43% | +0.534 [-0.195..+1.334] | -0.483 | +1.017 [+0.211..+1.895] | +0.299 |
| SD SUPPLY | dev | 5215 | 12 | 2144 | 51 | 25% | -0.313 [-0.811..+0.288] | -0.041 | -0.273 [-1.015..+0.748] | -0.503 |
| SD SUPPLY | HOLDOUT (q 0.910) | 4216 | 17 | 1441 | 10 | 41% | -0.037 [-0.516..+0.634] | +0.229 | -0.266 [-0.871..+0.562] | -0.025 |
| TRENDLINE DOWN | dev | 199 | 0 | 0 | 0 | — | — [—..—] | — | — [—..—] | — |
| TRENDLINE DOWN | HOLDOUT | 72 | 0 | 0 | 0 | — | — [—..—] | — | — [—..—] | — |
| TRENDLINE UP | dev | 301 | 0 | 0 | 0 | — | — [—..—] | — | — [—..—] | — |
| TRENDLINE UP | HOLDOUT | 253 | 0 | 0 | 0 | — | — [—..—] | — | — [—..—] | — |

A system WORKS here only if R TP1 > 0 in both parts, its holdout interval is above 0 and it beats the placebo in the holdout (the system - placebo interval above 0).
