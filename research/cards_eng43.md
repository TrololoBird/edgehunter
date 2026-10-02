# our classes on the archive (card replay, placebo, holdout)

Window 2025-04-08 .. 2026-09-30: development before 2026-04-03, HOLDOUT from 2026-04-03. 422 coins, 615100 cards. R = net R of an entry replayed like the journal (next full minute's open + 5 bps, stop exits slipped, funding, 0.10% round-trip fee), exit at TP1 / stop / the trade's lifetime. Placebo = the same trade (direction, stop / target in %) at a random time of the same coin within +-7 days. [90%] = block bootstrap over 4h x direction blocks; q = Benjamini-Hochberg over the holdout rows.

| Setup | part | cards | entries | expired | invalid | win TP1 | R TP1 [90%] | placebo R | system - placebo [90%] | R TP2 |
|---|---|---:|---:|---:|---:|---:|---|---:|---|---:|
| BEAR D | dev | 7038 | 8 | 2842 | 490 | 62% | — [—..—] | +0.141 | — [—..—] | +0.292 |
| BEAR D | HOLDOUT | 1748 | 3 | 751 | 116 | 100% | — [—..—] | +1.753 | — [—..—] | +0.491 |
| BEAR D [against_tide] | dev | 92 | 0 | 29 | 8 | — | — [—..—] | — | — [—..—] | — |
| BEAR D [against_tide] | HOLDOUT | 33 | 0 | 6 | 3 | — | — [—..—] | — | — [—..—] | — |
| BEAR D [perp_led] | dev | 424 | 0 | 212 | 34 | — | — [—..—] | — | — [—..—] | — |
| BEAR D [perp_led] | HOLDOUT | 104 | 0 | 59 | 9 | — | — [—..—] | — | — [—..—] | — |
| BULL F | dev | 9707 | 21 | 4002 | 731 | 19% | -0.534 [-0.798..-0.253] | +0.032 | -0.566 [-1.088..-0.041] | -0.403 |
| BULL F | HOLDOUT | 3710 | 9 | 1472 | 208 | 22% | — [—..—] | -0.040 | — [—..—] | -0.585 |
| BULL F [against_tide] | dev | 191 | 0 | 80 | 12 | — | — [—..—] | — | — [—..—] | — |
| BULL F [against_tide] | HOLDOUT | 101 | 0 | 44 | 13 | — | — [—..—] | — | — [—..—] | — |
| BULL F [perp_led] | dev | 1 | 0 | 1 | 0 | — | — [—..—] | — | — [—..—] | — |
| BULL F [perp_led] | HOLDOUT | 4 | 0 | 1 | 0 | — | — [—..—] | — | — [—..—] | — |
| IMPULSE DOWN | dev | 3594 | 29 | 1562 | 262 | 48% | +0.058 [-0.156..+0.356] | +0.106 | -0.048 [-0.346..+0.491] | -0.061 |
| IMPULSE DOWN | HOLDOUT | 1114 | 7 | 435 | 98 | 57% | — [—..—] | -0.126 | — [—..—] | +1.090 |
| IMPULSE DOWN [against_tide] | dev | 123 | 1 | 32 | 7 | 0% | — [—..—] | -1.035 | — [—..—] | -1.041 |
| IMPULSE DOWN [against_tide] | HOLDOUT | 34 | 0 | 10 | 2 | — | — [—..—] | — | — [—..—] | — |
| IMPULSE DOWN [perp_led] | dev | 241 | 0 | 108 | 22 | — | — [—..—] | — | — [—..—] | — |
| IMPULSE DOWN [perp_led] | HOLDOUT | 82 | 1 | 33 | 5 | 100% | — [—..—] | +0.807 | — [—..—] | +0.036 |
| IMPULSE UP | dev | 7713 | 83 | 3499 | 572 | 36% | -0.186 [-0.330..-0.038] | +0.034 | -0.221 [-0.436..-0.021] | -0.224 |
| IMPULSE UP | HOLDOUT (q 0.776) | 2945 | 24 | 1365 | 206 | 42% | -0.053 [-0.383..+0.305] | +0.233 | -0.286 [-0.684..+0.121] | -0.199 |
| IMPULSE UP [against_tide] | dev | 857 | 3 | 200 | 36 | 67% | — [—..—] | +0.548 | — [—..—] | +1.256 |
| IMPULSE UP [against_tide] | HOLDOUT | 188 | 3 | 84 | 9 | 0% | — [—..—] | -0.468 | — [—..—] | -0.826 |
| IMPULSE UP [perp_led] | dev | 58 | 2 | 21 | 3 | 50% | — [—..—] | +0.011 | — [—..—] | +0.171 |
| IMPULSE UP [perp_led] | HOLDOUT | 3 | 0 | 3 | 0 | — | — [—..—] | — | — [—..—] | — |
| SPRING | dev | 10129 | 39 | 288 | 3258 | 51% | +0.024 [-0.252..+0.316] | -0.449 | +0.473 [+0.138..+0.804] | -0.011 |
| SPRING | HOLDOUT (q 0.145) | 2813 | 16 | 103 | 907 | 62% | +0.356 [+0.040..+0.650] | -0.004 | +0.360 [-0.226..+0.810] | +0.093 |
| SWEEP HIGH | dev | 79349 | 598 | 9722 | 5128 | 58% | -0.035 [-0.106..+0.033] | -0.053 | +0.020 [-0.068..+0.107] | -0.011 |
| SWEEP HIGH | HOLDOUT (q 0.776) | 27151 | 210 | 3551 | 1571 | 63% | +0.018 [-0.074..+0.113] | -0.072 | +0.089 [-0.041..+0.219] | +0.077 |
| SWEEP HIGH [against_trend] | dev | 120265 | 1174 | 22719 | 14106 | 54% | -0.027 [-0.076..+0.022] | -0.087 | +0.060 [-0.007..+0.124] | -0.027 |
| SWEEP HIGH [against_trend] | HOLDOUT (q 0.145) | 40326 | 375 | 7361 | 4556 | 47% | -0.126 [-0.233..-0.017] | -0.157 | +0.031 [-0.099..+0.161] | -0.193 |
| SWEEP LOW | dev | 75144 | 885 | 11396 | 6167 | 53% | -0.120 [-0.184..-0.056] | -0.086 | -0.034 [-0.117..+0.044] | -0.128 |
| SWEEP LOW | HOLDOUT (q 0.145) | 24157 | 394 | 4748 | 1839 | 53% | -0.075 [-0.143..-0.007] | -0.063 | -0.012 [-0.100..+0.080] | -0.060 |
| SWEEP LOW [against_trend] | dev | 142925 | 1800 | 27728 | 17147 | 45% | -0.169 [-0.238..-0.099] | -0.124 | -0.044 [-0.120..+0.033] | -0.188 |
| SWEEP LOW [against_trend] | HOLDOUT (q 0.259) | 44775 | 753 | 10116 | 4869 | 48% | -0.103 [-0.225..+0.024] | -0.011 | -0.092 [-0.217..+0.034] | -0.086 |
| UTAD | dev | 5984 | 4 | 149 | 1939 | 25% | — [—..—] | -0.001 | — [—..—] | -0.435 |
| UTAD | HOLDOUT | 1977 | 7 | 54 | 605 | 71% | — [—..—] | -0.460 | — [—..—] | +0.352 |

A system WORKS here only if R TP1 > 0 in both parts, its holdout interval is above 0 and it beats the placebo in the holdout (the system - placebo interval above 0).
