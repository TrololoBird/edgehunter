# Historical card replay (logic eng-7)

Window 2026-03-31 .. 2026-09-27, 357 coins, 65556 cards. R = result in stop units of an entry replayed like the journal (fill at the next full minute's open + 5 bps, stop exits slipped, targets traded 2 bps through, funding), NET of the 0.10% round-trip fee. R TP1 = everything exits at TP1 (or the stop / the 8h mark); R TP2 likewise at TP2; R BE = stop to breakeven once TP1 traded, exit at TP2. [90%] = block bootstrap over 4h x direction blocks; q = Benjamini-Hochberg over the rows of the table.

| Setup | vetoed | cards | entries | invalid | missed | expired | avg R:R | win TP1 | R TP1 [90%] | q | R TP2 | R BE | median risk |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|
| BEAR C | — | 17444 | 3751 | 5850 | 6459 | 246 | +1.57 | 35% | -0.235 [-0.284..-0.186] | 0.002 | -0.261 | -0.259 | 0.84% |
| BEAR D | — | 3658 | 158 | 475 | 0 | 2514 | +1.31 | 39% | -0.191 [-0.345..-0.033] | 0.088 | -0.162 | -0.167 | 1.10% |
| BEAR D | against_tide | 771 | 32 | 119 | 0 | 377 | +1.25 | 34% | -0.353 [-0.758..+0.066] | 0.249 | -0.066 | -0.066 | 0.96% |
| BEAR D | perp_led | 285 | 11 | 49 | 0 | 177 | +1.44 | 36% | -0.323 [-0.883..+0.308] | 0.490 | -0.187 | -0.187 | 1.32% |
| BULL A | — | 17608 | 4752 | 2001 | 2478 | 1222 | +1.86 | 35% | -0.201 [-0.248..-0.154] | 0.002 | -0.203 | -0.209 | 1.16% |
| BULL B | — | 8658 | 1890 | 2369 | 2885 | 397 | +1.82 | 37% | -0.136 [-0.198..-0.076] | 0.002 | -0.153 | -0.142 | 1.24% |
| BULL E | — | 172 | 45 | 21 | 98 | 7 | +1.48 | 64% | +0.317 [-0.288..+0.561] | 0.490 | +0.410 | +0.402 | 2.34% |
| BULL F | — | 8025 | 370 | 912 | 0 | 6128 | +1.32 | 34% | -0.248 [-0.345..-0.149] | 0.002 | -0.270 | -0.271 | 1.33% |
| BULL F | against_tide | 2219 | 98 | 297 | 0 | 1334 | +1.24 | 30% | -0.337 [-0.527..-0.143] | 0.016 | -0.390 | -0.374 | 1.43% |
| BULL F | perp_led | 23 | 2 | 1 | 0 | 18 | +1.42 | 0% | — [—..—] | — | -1.189 | -1.189 | 0.83% |
| IMPULSE DOWN | — | 1235 | 96 | 171 | 0 | 787 | +1.33 | 50% | +0.058 [-0.183..+0.284] | 0.766 | -0.017 | +0.013 | 1.34% |
| IMPULSE DOWN | against_tide | 730 | 20 | 33 | 0 | 164 | +1.23 | 55% | -0.003 [-0.351..+0.337] | 0.994 | +0.157 | +0.155 | 1.45% |
| IMPULSE DOWN | perp_led | 136 | 7 | 14 | 0 | 55 | +1.31 | 29% | — [—..—] | — | -0.303 | -0.303 | 0.90% |
| IMPULSE UP | — | 2901 | 168 | 259 | 0 | 2203 | +1.36 | 33% | -0.290 [-0.429..-0.150] | 0.004 | -0.273 | -0.303 | 1.64% |
| IMPULSE UP | against_tide | 1687 | 78 | 109 | 0 | 607 | +1.26 | 40% | -0.129 [-0.327..+0.062] | 0.382 | -0.160 | -0.179 | 1.83% |
| IMPULSE UP | perp_led | 4 | 0 | 0 | 0 | 4 | — | — | — [—..—] | — | — | — | — |

## What the vetoed triggers would have given (the first vetoed trigger of each card, taken anyway)

| Setup | card veto | trigger veto | trades | avg R:R | win TP1 | R TP1 [90%] | q | R TP2 |
|---|---|---|---:|---:|---:|---|---:|---:|
| BEAR C | — | low_rr | 12487 | +0.56 | 54% | -0.181 [-0.207..-0.154] | 0.001 | -0.196 |
| BEAR D | — | low_rr | 705 | +0.48 | 59% | -0.100 [-0.155..-0.042] | 0.011 | -0.056 |
| BEAR D | against_tide | low_rr | 158 | +0.52 | 52% | -0.182 [-0.325..-0.043] | 0.071 | -0.047 |
| BEAR D | perp_led | low_rr | 68 | +0.49 | 59% | -0.013 [-0.183..+0.155] | 0.902 | -0.022 |
| BULL A | — | low_rr | 6251 | +0.61 | 50% | -0.144 [-0.174..-0.114] | 0.001 | -0.145 |
| BULL B | — | low_rr | 5678 | +0.57 | 52% | -0.184 [-0.220..-0.150] | 0.001 | -0.184 |
| BULL E | — | low_rr | 128 | +0.53 | 72% | +0.188 [+0.041..+0.310] | 0.074 | +0.201 |
| BULL F | — | low_rr | 1704 | +0.49 | 53% | -0.173 [-0.206..-0.137] | 0.001 | -0.162 |
| BULL F | against_tide | low_rr | 510 | +0.50 | 49% | -0.229 [-0.292..-0.164] | 0.001 | -0.244 |
| BULL F | perp_led | low_rr | 7 | +0.46 | 14% | — [—..—] | — | -0.843 |
| IMPULSE DOWN | — | low_rr | 225 | +0.54 | 67% | +0.071 [-0.040..+0.166] | 0.398 | +0.138 |
| IMPULSE DOWN | against_tide | low_rr | 57 | +0.59 | 56% | -0.028 [-0.209..+0.157] | 0.871 | +0.046 |
| IMPULSE DOWN | perp_led | low_rr | 16 | +0.54 | 38% | -0.409 [-0.727..-0.086] | 0.074 | -0.357 |
| IMPULSE UP | — | low_rr | 480 | +0.54 | 59% | -0.018 [-0.075..+0.039] | 0.695 | -0.097 |
| IMPULSE UP | against_tide | low_rr | 211 | +0.57 | 57% | -0.078 [-0.175..+0.022] | 0.269 | -0.085 |
| IMPULSE UP | perp_led | low_rr | 1 | +0.33 | 100% | — [—..—] | — | +0.910 |
