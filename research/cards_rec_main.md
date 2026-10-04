# our classes on the archive (card replay, placebo, holdout)

Window 2025-04-08 .. 2026-09-30: development before 2026-04-03, HOLDOUT from 2026-04-03. 422 coins, 606298 cards. R = net R of an entry replayed like the journal (next full minute's open + 5 bps, stop exits slipped, funding, 0.10% round-trip fee), exit at TP1 / stop / the trade's lifetime. Placebo = the same trade (direction, stop / target in %) at a random time of the same coin within +-7 days. [90%] = block bootstrap over 4h x direction blocks; q = Benjamini-Hochberg over the holdout rows.

| Setup | part | cards | entries | expired | invalid | win TP1 | R TP1 [90%] | placebo R | system - placebo [90%] | R TP2 |
|---|---|---:|---:|---:|---:|---:|---|---:|---|---:|
| BEAR D | dev | 7194 | 20 | 2521 | 423 | 55% | +0.092 [-0.229..+0.445] | +0.082 | +0.010 [-0.422..+0.448] | -0.134 |
| BEAR D | HOLDOUT | 1783 | 3 | 664 | 98 | 100% | — [—..—] | +2.150 | — [—..—] | +0.491 |
| BEAR D [against_tide] | dev | 93 | 0 | 24 | 6 | — | — [—..—] | — | — [—..—] | — |
| BEAR D [against_tide] | HOLDOUT | 33 | 0 | 6 | 3 | — | — [—..—] | — | — [—..—] | — |
| BEAR D [perp_led] | dev | 425 | 1 | 197 | 30 | 100% | — [—..—] | -1.222 | — [—..—] | +0.723 |
| BEAR D [perp_led] | HOLDOUT | 102 | 1 | 53 | 7 | 0% | — [—..—] | +0.845 | — [—..—] | -1.113 |
| BULL F | dev | 10303 | 88 | 3012 | 445 | 61% | -0.036 [-0.176..+0.111] | -0.040 | +0.004 [-0.185..+0.211] | -0.060 |
| BULL F | HOLDOUT (q 0.885) | 3882 | 48 | 1126 | 140 | 69% | -0.018 [-0.154..+0.114] | -0.049 | +0.032 [-0.138..+0.198] | -0.073 |
| BULL F [against_tide] | dev | 196 | 1 | 59 | 8 | 100% | — [—..—] | -0.330 | — [—..—] | +0.072 |
| BULL F [against_tide] | HOLDOUT | 105 | 1 | 31 | 11 | 100% | — [—..—] | -1.010 | — [—..—] | -0.591 |
| BULL F [perp_led] | dev | 1 | 0 | 1 | 0 | — | — [—..—] | — | — [—..—] | — |
| BULL F [perp_led] | HOLDOUT | 4 | 0 | 1 | 0 | — | — [—..—] | — | — [—..—] | — |
| IMPULSE DOWN | dev | 3609 | 30 | 1423 | 235 | 63% | +0.283 [+0.104..+0.545] | -0.047 | +0.330 [+0.093..+0.698] | +0.168 |
| IMPULSE DOWN | HOLDOUT (q 0.276) | 1111 | 12 | 408 | 77 | 67% | +0.767 [-0.022..+1.144] | -0.097 | +0.864 [+0.296..+1.178] | +0.990 |
| IMPULSE DOWN [against_tide] | dev | 123 | 1 | 27 | 7 | 0% | — [—..—] | -1.035 | — [—..—] | -1.041 |
| IMPULSE DOWN [against_tide] | HOLDOUT | 34 | 0 | 8 | 2 | — | — [—..—] | — | — [—..—] | — |
| IMPULSE DOWN [perp_led] | dev | 242 | 1 | 99 | 19 | 0% | — [—..—] | +0.305 | — [—..—] | -0.551 |
| IMPULSE DOWN [perp_led] | HOLDOUT | 83 | 0 | 28 | 5 | — | — [—..—] | — | — [—..—] | — |
| IMPULSE UP | dev | 8120 | 155 | 2629 | 310 | 50% | -0.129 [-0.231..-0.029] | +0.067 | -0.196 [-0.340..-0.065] | -0.200 |
| IMPULSE UP | HOLDOUT (q 0.485) | 3058 | 56 | 1041 | 117 | 66% | +0.094 [-0.044..+0.243] | -0.040 | +0.134 [-0.027..+0.313] | +0.043 |
| IMPULSE UP [against_tide] | dev | 868 | 8 | 147 | 16 | 50% | — [—..—] | +0.585 | — [—..—] | +0.268 |
| IMPULSE UP [against_tide] | HOLDOUT | 191 | 2 | 64 | 6 | 50% | — [—..—] | +0.041 | — [—..—] | -0.481 |
| IMPULSE UP [perp_led] | dev | 58 | 1 | 20 | 2 | 100% | — [—..—] | +0.222 | — [—..—] | +0.904 |
| IMPULSE UP [perp_led] | HOLDOUT | 3 | 0 | 2 | 0 | — | — [—..—] | — | — [—..—] | — |
| SPRING | dev | 6525 | 27 | 227 | 2165 | 30% | -0.314 [-0.601..+0.017] | -0.333 | +0.019 [-0.444..+0.522] | -0.308 |
| SPRING | HOLDOUT | 1840 | 9 | 88 | 627 | 67% | — [—..—] | -0.213 | — [—..—] | +0.203 |
| SPRING [against_htf] | dev | 3186 | 16 | 122 | 1018 | 69% | +0.468 [+0.064..+0.856] | -0.302 | +0.769 [+0.312..+1.193] | +0.457 |
| SPRING [against_htf] | HOLDOUT | 773 | 2 | 26 | 222 | 50% | — [—..—] | -0.113 | — [—..—] | +0.414 |
| SWEEP HIGH | dev | 102018 | 1681 | 18469 | 11825 | 53% | -0.046 [-0.094..+0.003] | -0.066 | +0.021 [-0.042..+0.079] | -0.030 |
| SWEEP HIGH | HOLDOUT (q 0.485) | 32762 | 539 | 6066 | 3469 | 55% | -0.043 [-0.113..+0.038] | -0.048 | +0.005 [-0.088..+0.103] | -0.043 |
| SWEEP HIGH [against_bias] | dev | 54730 | 1276 | 10010 | 7903 | 51% | -0.094 [-0.149..-0.037] | -0.104 | +0.009 [-0.059..+0.084] | -0.101 |
| SWEEP HIGH [against_bias] | HOLDOUT (q 0.885) | 19506 | 405 | 3140 | 2622 | 57% | +0.012 [-0.066..+0.089] | -0.186 | +0.197 [+0.097..+0.298] | +0.007 |
| SWEEP HIGH [against_trend] | dev | 39030 | 1141 | 11191 | 7028 | 52% | -0.042 [-0.092..+0.012] | -0.082 | +0.040 [-0.029..+0.111] | -0.071 |
| SWEEP HIGH [against_trend] | HOLDOUT (q 0.155) | 13969 | 338 | 3883 | 2301 | 51% | -0.108 [-0.187..-0.025] | -0.119 | +0.010 [-0.113..+0.126] | -0.061 |
| SWEEP LOW | dev | 79466 | 1962 | 16186 | 10678 | 50% | -0.105 [-0.155..-0.058] | -0.063 | -0.042 [-0.108..+0.025] | -0.112 |
| SWEEP LOW | HOLDOUT (q 0.059) | 27265 | 964 | 6549 | 3562 | 51% | -0.101 [-0.161..-0.043] | -0.021 | -0.080 [-0.157..-0.003] | -0.110 |
| SWEEP LOW [against_bias] | dev | 93107 | 2473 | 19037 | 11998 | 47% | -0.142 [-0.204..-0.085] | -0.103 | -0.039 [-0.112..+0.030] | -0.160 |
| SWEEP LOW [against_bias] | HOLDOUT (q 0.885) | 25779 | 645 | 5913 | 2846 | 52% | -0.016 [-0.099..+0.067] | -0.142 | +0.126 [+0.029..+0.220] | +0.006 |
| SWEEP LOW [against_trend] | dev | 42701 | 1187 | 11836 | 8058 | 47% | -0.152 [-0.220..-0.084] | -0.137 | -0.015 [-0.102..+0.071] | -0.177 |
| SWEEP LOW [against_trend] | HOLDOUT (q 0.276) | 14670 | 478 | 4747 | 2140 | 52% | -0.069 [-0.144..+0.003] | -0.144 | +0.075 [-0.031..+0.183] | -0.067 |
| UTAD | dev | 4292 | 7 | 138 | 1421 | 14% | — [—..—] | +0.367 | — [—..—] | -0.658 |
| UTAD | HOLDOUT | 1507 | 2 | 46 | 467 | 50% | — [—..—] | -0.365 | — [—..—] | -0.204 |
| UTAD [against_htf] | dev | 1224 | 1 | 30 | 417 | 100% | — [—..—] | -1.048 | — [—..—] | +0.656 |
| UTAD [against_htf] | HOLDOUT | 327 | 1 | 13 | 96 | 100% | — [—..—] | -1.021 | — [—..—] | +0.600 |

A system WORKS here only if R TP1 > 0 in both parts, its holdout interval is above 0 and it beats the placebo in the holdout (the system - placebo interval above 0).
