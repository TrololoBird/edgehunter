# crypto_maniac's systems on the archive (card replay, placebo, holdout)

Window 2023-10-08 .. 2025-03-31: development before 2024-10-02, HOLDOUT from 2024-10-02. 351 coins, 415757 cards. R = net R of an entry replayed like the journal (next full minute's open + 5 bps, stop exits slipped, funding, 0.10% round-trip fee), exit at TP1 / stop / the trade's lifetime. Placebo = the same trade (direction, stop / target in %) at a random time of the same coin within +-7 days. [90%] = block bootstrap over 4h x direction blocks; q = Benjamini-Hochberg over the holdout rows.

| Setup | part | cards | entries | expired | invalid | win TP1 | R TP1 [90%] | placebo R | system - placebo [90%] | R TP2 |
|---|---|---:|---:|---:|---:|---:|---|---:|---|---:|
| AUCTION LONG | dev | 4079 | 673 | 10 | 0 | 22% | -0.292 [-0.433..-0.137] | -0.172 | -0.120 [-0.298..+0.062] | -0.332 |
| AUCTION LONG | HOLDOUT (q 0.004) | 1771 | 288 | 3 | 0 | 15% | -0.565 [-0.760..-0.348] | -0.278 | -0.286 [-0.547..-0.028] | -0.557 |
| AUCTION SHORT | dev | 3291 | 427 | 15 | 0 | 26% | -0.184 [-0.324..-0.046] | -0.330 | +0.146 [-0.041..+0.333] | -0.162 |
| AUCTION SHORT | HOLDOUT (q 0.655) | 1693 | 217 | 6 | 0 | 27% | -0.081 [-0.308..+0.152] | -0.272 | +0.190 [-0.117..+0.481] | -0.094 |
| BB M-TOP | dev | 114525 | 46183 | 66032 | 0 | 59% | -0.040 [-0.062..-0.015] | -0.049 | +0.009 [-0.015..+0.034] | -0.033 |
| BB M-TOP | HOLDOUT (q 0.596) | 68805 | 31697 | 35950 | 0 | 59% | -0.024 [-0.063..+0.015] | -0.048 | +0.023 [-0.018..+0.066] | +0.002 |
| BB W-BOTTOM | dev | 125874 | 48063 | 75916 | 0 | 54% | -0.064 [-0.095..-0.033] | -0.096 | +0.032 [-0.001..+0.064] | -0.059 |
| BB W-BOTTOM | HOLDOUT (q 0.023) | 76381 | 31284 | 43701 | 0 | 55% | -0.067 [-0.108..-0.025] | -0.093 | +0.026 [-0.017..+0.070] | -0.093 |
| CUP HANDLE | dev | 650 | 627 | 16 | 0 | 30% | -0.053 [-0.184..+0.091] | +0.195 | -0.248 [-0.401..-0.080] | -0.122 |
| CUP HANDLE | HOLDOUT (q 0.596) | 623 | 601 | 11 | 0 | 32% | -0.094 [-0.246..+0.070] | +0.364 | -0.458 [-0.614..-0.292] | -0.102 |
| SD DEMAND | dev | 4998 | 61 | 2261 | 11 | 34% | -0.186 [-0.410..+0.050] | +0.074 | -0.259 [-0.631..+0.128] | -0.310 |
| SD DEMAND | HOLDOUT (q 0.639) | 2811 | 80 | 1703 | 14 | 32% | -0.136 [-0.418..+0.173] | +0.017 | -0.152 [-0.564..+0.271] | -0.151 |
| SD SUPPLY | dev | 5215 | 69 | 2086 | 51 | 36% | -0.229 [-0.518..+0.060] | -0.241 | +0.012 [-0.383..+0.493] | -0.414 |
| SD SUPPLY | HOLDOUT (q 0.792) | 4216 | 53 | 1404 | 10 | 45% | -0.065 [-0.501..+0.312] | -0.356 | +0.292 [-0.021..+0.829] | -0.000 |
| TRENDLINE DOWN | dev | 199 | 0 | 0 | 0 | — | — [—..—] | — | — [—..—] | — |
| TRENDLINE DOWN | HOLDOUT | 72 | 0 | 0 | 0 | — | — [—..—] | — | — [—..—] | — |
| TRENDLINE UP | dev | 301 | 0 | 0 | 0 | — | — [—..—] | — | — [—..—] | — |
| TRENDLINE UP | HOLDOUT | 253 | 0 | 0 | 0 | — | — [—..—] | — | — [—..—] | — |

A system WORKS here only if R TP1 > 0 in both parts, its holdout interval is above 0 and it beats the placebo in the holdout (the system - placebo interval above 0).
