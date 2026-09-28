# Historical card replay: SWEEP / BREAKOUT (logic eng-7)

Window 2026-03-31 .. 2026-09-27, 360 coins, 202143 cards. R = result in stop units of an entry replayed like the journal (fill at the next full minute's open + 5 bps, stop exits slipped, targets traded 2 bps through, funding), NET of the 0.10% round-trip fee. R TP1 = everything exits at TP1 (or the stop / the 8h mark); R TP2 likewise at TP2; R BE = stop to breakeven once TP1 traded, exit at TP2. [90%] = block bootstrap over 4h x direction blocks; q = Benjamini-Hochberg over the rows of the table.

| Setup | vetoed | cards | entries | invalid | missed | expired | avg R:R | win TP1 | R TP1 [90%] | q | R TP2 | R BE | median risk |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|
| BREAKOUT DOWN | — | 39441 | 661 | 9749 | 16721 | 12306 | +1.24 | 41% | -0.134 [-0.233..-0.035] | 0.029 | -0.154 | -0.141 | 1.43% |
| BREAKOUT UP | — | 32457 | 810 | 8572 | 15105 | 7969 | +1.30 | 38% | -0.183 [-0.255..-0.109] | 0.001 | -0.209 | -0.217 | 1.66% |
| SWEEP HIGH | — | 24093 | 389 | 11631 | 8799 | 3274 | +1.42 | 41% | -0.064 [-0.182..+0.055] | 0.375 | -0.099 | -0.087 | 1.18% |
| SWEEP HIGH | against_trend | 39279 | 585 | 19280 | 14661 | 4751 | +1.39 | 36% | -0.233 [-0.317..-0.145] | 0.001 | -0.283 | -0.274 | 1.24% |
| SWEEP LOW | — | 23845 | 428 | 10833 | 8220 | 4364 | +1.40 | 34% | -0.270 [-0.375..-0.159] | 0.001 | -0.273 | -0.271 | 1.34% |
| SWEEP LOW | against_trend | 43028 | 1002 | 20519 | 14673 | 6834 | +1.44 | 32% | -0.328 [-0.408..-0.253] | 0.001 | -0.281 | -0.285 | 1.23% |

## What the vetoed triggers would have given (the first vetoed trigger of each card, taken anyway)

| Setup | card veto | trigger veto | trades | avg R:R | win TP1 | R TP1 [90%] | q | R TP2 |
|---|---|---|---:|---:|---:|---|---:|---:|
| BREAKOUT DOWN | — | low_rr | 12119 | +0.46 | 56% | -0.169 [-0.197..-0.141] | 0.001 | -0.193 |
| BREAKOUT DOWN | — | no_oi | 26673 | +0.50 | 56% | -0.153 [-0.182..-0.123] | 0.001 | -0.176 |
| BREAKOUT UP | — | low_rr | 19556 | +0.46 | 58% | -0.143 [-0.163..-0.124] | 0.001 | -0.144 |
| BREAKOUT UP | — | no_oi | 12223 | +0.48 | 55% | -0.181 [-0.209..-0.154] | 0.001 | -0.183 |
| SWEEP HIGH | — | low_rr | 6595 | +0.28 | 63% | -0.136 [-0.156..-0.117] | 0.001 | -0.127 |
| SWEEP HIGH | against_trend | low_rr | 10959 | +0.29 | 64% | -0.129 [-0.145..-0.113] | 0.001 | -0.161 |
| SWEEP LOW | — | low_rr | 6833 | +0.30 | 61% | -0.150 [-0.171..-0.128] | 0.001 | -0.163 |
| SWEEP LOW | against_trend | low_rr | 12526 | +0.30 | 61% | -0.158 [-0.178..-0.137] | 0.001 | -0.167 |
