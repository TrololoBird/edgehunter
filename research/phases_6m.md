# Historical card replay (logic eng-7)

Window 2026-03-31 .. 2026-09-27, 357 coins, 60445 cards. R = result in stop units of an entry replayed like the journal (fill at the next full minute's open + 5 bps, stop exits slipped, targets traded 2 bps through, funding), NET of the 0.10% round-trip fee. R TP1 = everything exits at TP1 (or the stop / the 8h mark); R TP2 likewise at TP2; R BE = stop to breakeven once TP1 traded, exit at TP2. [90%] = block bootstrap over 4h x direction blocks; q = Benjamini-Hochberg over the rows of the table.

| Setup | vetoed | cards | entries | invalid | missed | expired | avg R:R | win TP1 | R TP1 [90%] | q | R TP2 | R BE | median risk |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|
| BEAR C | — | 17503 | 3771 | 5869 | 6474 | 246 | +1.57 | 35% | -0.230 [-0.278..-0.181] | 0.002 | -0.256 | -0.255 | 0.84% |
| BEAR D | — | 3869 | 188 | 512 | 0 | 2657 | +1.31 | 40% | -0.150 [-0.299..-0.000] | 0.151 | -0.151 | -0.149 | 1.14% |
| BEAR D | against_tide | 781 | 33 | 122 | 0 | 383 | +1.29 | 33% | -0.376 [-0.773..+0.016] | 0.152 | -0.097 | -0.097 | 0.98% |
| BEAR D | perp_led | 306 | 12 | 55 | 0 | 191 | +1.47 | 42% | -0.205 [-0.770..+0.429] | 0.526 | -0.080 | -0.080 | 1.38% |
| BULL A | — | 17787 | 4803 | 2021 | 2489 | 1232 | +1.86 | 35% | -0.197 [-0.240..-0.150] | 0.002 | -0.200 | -0.206 | 1.16% |
| BULL B | — | 8811 | 1934 | 2405 | 2925 | 408 | +1.81 | 38% | -0.125 [-0.186..-0.065] | 0.003 | -0.138 | -0.128 | 1.25% |
| BULL E | — | 172 | 45 | 21 | 98 | 7 | +1.48 | 64% | +0.317 [-0.288..+0.561] | 0.466 | +0.410 | +0.402 | 2.34% |
| BULL F | — | 8948 | 434 | 1028 | 0 | 6857 | +1.33 | 34% | -0.224 [-0.309..-0.135] | 0.002 | -0.250 | -0.254 | 1.35% |
| BULL F | against_tide | 2244 | 98 | 300 | 0 | 1354 | +1.24 | 30% | -0.337 [-0.527..-0.143] | 0.013 | -0.390 | -0.374 | 1.43% |
| BULL F | perp_led | 24 | 3 | 1 | 0 | 18 | +1.29 | 0% | — [—..—] | — | -1.159 | -1.159 | 0.83% |

## What the vetoed triggers would have given (the first vetoed trigger of each card, taken anyway)

| Setup | card veto | trigger veto | trades | avg R:R | win TP1 | R TP1 [90%] | q | R TP2 |
|---|---|---|---:|---:|---:|---|---:|---:|
| BEAR C | — | low_rr | 12521 | +0.56 | 54% | -0.182 [-0.207..-0.155] | 0.001 | -0.198 |
| BEAR D | — | low_rr | 763 | +0.48 | 59% | -0.092 [-0.143..-0.037] | 0.011 | -0.045 |
| BEAR D | against_tide | low_rr | 160 | +0.52 | 52% | -0.171 [-0.318..-0.032] | 0.053 | -0.032 |
| BEAR D | perp_led | low_rr | 73 | +0.50 | 58% | -0.031 [-0.199..+0.141] | 0.770 | -0.024 |
| BULL A | — | low_rr | 6297 | +0.61 | 50% | -0.145 [-0.176..-0.115] | 0.001 | -0.147 |
| BULL B | — | low_rr | 5766 | +0.57 | 52% | -0.184 [-0.220..-0.150] | 0.001 | -0.185 |
| BULL E | — | low_rr | 128 | +0.53 | 72% | +0.188 [+0.041..+0.310] | 0.053 | +0.201 |
| BULL F | — | low_rr | 1886 | +0.49 | 53% | -0.164 [-0.197..-0.130] | 0.001 | -0.168 |
| BULL F | against_tide | low_rr | 515 | +0.50 | 49% | -0.225 [-0.287..-0.158] | 0.001 | -0.246 |
| BULL F | perp_led | low_rr | 7 | +0.46 | 14% | — [—..—] | — | -0.843 |
