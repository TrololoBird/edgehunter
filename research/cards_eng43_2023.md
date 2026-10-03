# our classes on the archive (card replay, placebo, holdout)

Window 2023-10-08 .. 2025-03-31: development before 2024-10-02, HOLDOUT from 2024-10-02. 359 coins, 600566 cards. R = net R of an entry replayed like the journal (next full minute's open + 5 bps, stop exits slipped, funding, 0.10% round-trip fee), exit at TP1 / stop / the trade's lifetime. Placebo = the same trade (direction, stop / target in %) at a random time of the same coin within +-7 days. [90%] = block bootstrap over 4h x direction blocks; q = Benjamini-Hochberg over the holdout rows.

| Setup | part | cards | entries | expired | invalid | win TP1 | R TP1 [90%] | placebo R | system - placebo [90%] | R TP2 |
|---|---|---:|---:|---:|---:|---:|---|---:|---|---:|
| BEAR D | dev | 5711 | 4 | 2247 | 413 | 0% | — [—..—] | +0.858 | — [—..—] | -0.834 |
| BEAR D | HOLDOUT | 3690 | 7 | 1487 | 276 | 57% | — [—..—] | -0.419 | — [—..—] | +0.045 |
| BEAR D [against_tide] | dev | 82 | 0 | 20 | 4 | — | — [—..—] | — | — [—..—] | — |
| BEAR D [against_tide] | HOLDOUT | 69 | 0 | 28 | 5 | — | — [—..—] | — | — [—..—] | — |
| BEAR D [perp_led] | dev | 85 | 0 | 49 | 3 | — | — [—..—] | — | — [—..—] | — |
| BEAR D [perp_led] | HOLDOUT | 73 | 0 | 43 | 8 | — | — [—..—] | — | — [—..—] | — |
| BULL F | dev | 8797 | 11 | 3919 | 663 | 27% | -0.362 [-0.839..+0.160] | +0.084 | -0.445 [-0.950..+0.071] | +0.024 |
| BULL F | HOLDOUT (q 0.727) | 4907 | 11 | 2200 | 364 | 45% | -0.145 [-0.687..+0.397] | -0.262 | +0.116 [-0.669..+0.859] | -0.224 |
| BULL F [against_tide] | dev | 175 | 2 | 79 | 20 | 100% | — [—..—] | -0.155 | — [—..—] | +2.395 |
| BULL F [against_tide] | HOLDOUT | 106 | 0 | 50 | 6 | — | — [—..—] | — | — [—..—] | — |
| BULL F [perp_led] | dev | 226 | 1 | 83 | 21 | 100% | — [—..—] | +0.069 | — [—..—] | +0.515 |
| BULL F [perp_led] | HOLDOUT | 50 | 0 | 34 | 7 | — | — [—..—] | — | — [—..—] | — |
| IMPULSE DOWN | dev | 2614 | 28 | 1166 | 310 | 25% | -0.434 [-0.875..+0.199] | +0.417 | -0.851 [-1.386..-0.130] | -0.392 |
| IMPULSE DOWN | HOLDOUT (q 0.727) | 1792 | 37 | 878 | 226 | 68% | +0.850 [-0.809..+1.180] | -0.023 | +0.874 [-1.187..+1.292] | +0.675 |
| IMPULSE DOWN [against_tide] | dev | 173 | 0 | 33 | 9 | — | — [—..—] | — | — [—..—] | — |
| IMPULSE DOWN [against_tide] | HOLDOUT | 73 | 0 | 19 | 1 | — | — [—..—] | — | — [—..—] | — |
| IMPULSE DOWN [perp_led] | dev | 51 | 0 | 25 | 5 | — | — [—..—] | — | — [—..—] | — |
| IMPULSE DOWN [perp_led] | HOLDOUT | 49 | 0 | 25 | 3 | — | — [—..—] | — | — [—..—] | — |
| IMPULSE UP | dev | 5647 | 28 | 2763 | 476 | 46% | -0.091 [-0.355..+0.190] | -0.160 | +0.069 [-0.322..+0.479] | -0.042 |
| IMPULSE UP | HOLDOUT (q 0.888) | 2842 | 21 | 1409 | 225 | 48% | -0.033 [-0.391..+0.306] | +0.186 | -0.219 [-0.785..+0.275] | -0.281 |
| IMPULSE UP [against_tide] | dev | 558 | 3 | 164 | 49 | 33% | — [—..—] | +0.110 | — [—..—] | -0.413 |
| IMPULSE UP [against_tide] | HOLDOUT | 372 | 2 | 76 | 26 | 0% | — [—..—] | +0.282 | — [—..—] | -0.978 |
| IMPULSE UP [perp_led] | dev | 234 | 2 | 100 | 26 | 50% | — [—..—] | +0.368 | — [—..—] | +0.217 |
| IMPULSE UP [perp_led] | HOLDOUT | 33 | 0 | 13 | 4 | — | — [—..—] | — | — [—..—] | — |
| SPRING | dev | 6515 | 22 | 285 | 2290 | 27% | -0.371 [-0.734..+0.127] | -0.282 | -0.089 [-0.507..+0.472] | -0.362 |
| SPRING | HOLDOUT (q 0.331) | 4328 | 14 | 148 | 1658 | 21% | -0.535 [-0.893..+0.111] | -0.131 | -0.404 [-1.079..+0.320] | -0.443 |
| SWEEP HIGH | dev | 53763 | 735 | 7274 | 4282 | 57% | -0.030 [-0.096..+0.034] | -0.018 | -0.012 [-0.102..+0.080] | -0.029 |
| SWEEP HIGH | HOLDOUT (q 0.331) | 37663 | 427 | 4311 | 2990 | 56% | -0.079 [-0.169..+0.007] | -0.053 | -0.026 [-0.137..+0.088] | -0.133 |
| SWEEP HIGH [against_trend] | dev | 99454 | 1226 | 17326 | 10549 | 53% | -0.049 [-0.106..+0.007] | -0.008 | -0.042 [-0.114..+0.028] | -0.027 |
| SWEEP HIGH [against_trend] | HOLDOUT (q 0.727) | 61017 | 788 | 10898 | 7883 | 58% | +0.029 [-0.036..+0.094] | -0.022 | +0.051 [-0.039..+0.138] | -0.001 |
| SWEEP LOW | dev | 69205 | 608 | 8409 | 5369 | 48% | -0.208 [-0.303..-0.116] | -0.156 | -0.052 [-0.162..+0.054] | -0.213 |
| SWEEP LOW | HOLDOUT (q 0.004) | 38647 | 438 | 4265 | 3858 | 45% | -0.289 [-0.402..-0.171] | -0.074 | -0.214 [-0.358..-0.070] | -0.327 |
| SWEEP LOW [against_trend] | dev | 109869 | 1679 | 20863 | 15330 | 50% | -0.076 [-0.170..+0.021] | -0.111 | +0.035 [-0.066..+0.138] | -0.067 |
| SWEEP LOW [against_trend] | HOLDOUT (q 0.046) | 71593 | 994 | 12918 | 10198 | 47% | -0.143 [-0.235..-0.047] | -0.171 | +0.028 [-0.071..+0.130] | -0.124 |
| UTAD | dev | 6651 | 2 | 174 | 2264 | 50% | — [—..—] | -1.047 | — [—..—] | +0.101 |
| UTAD | HOLDOUT | 3452 | 3 | 77 | 1198 | 67% | — [—..—] | -0.376 | — [—..—] | -1.029 |

A system WORKS here only if R TP1 > 0 in both parts, its holdout interval is above 0 and it beats the placebo in the holdout (the system - placebo interval above 0).
