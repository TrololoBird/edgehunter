# Archive replay of the live card lifecycle (B9)

**Summary (cloud run 2026-10-05, top 40 coins by volume, 2025-10-01 .. 2026-09-30, 8 groups of 5 coins).** By the pre-registered rule (mean final_r > 0 in both halves and the 90% 4h-cluster interval above 0) **only `breakout` (Turtles) is POSITIVE**: +1.11R per card [+0.24..+2.18], older +1.25 / newer +0.99, win 29% (trend-following: few large winners; 342 entered cards). Clearly negative with tight intervals: **bollinger -0.25R** (3,109 cards), **market_profile -0.20R** (1,927), **sweep -0.23R** (141). Not significant: connors -0.09, pump -0.09, trendline +0.05, continuation +0.22 (16 cards), supply_demand (5 cards). Exits (3.1): for bollinger / market_profile / sweep the lifecycle exit is WORSE than all-at-TP1; for continuation / trendline the lifecycle (trailing) exit is better than fixed TPs. Vetoes: most reject worse trades (low_rr everywhere, killzone, weak_mss); against_day / against_btc for sweep and against_day / low_rr for continuation reject trades no worse than the passed ones. **Not in the replay at all** (no setup rows): ORB, OI SIGNAL, PO3, CUP HANDLE, the liquidation-cascade setups (no liquidations in the archive) - cause for ORB / OI SIGNAL / PO3 / CUP not investigated in this session. Cards rows + entries without f_* features: `research/replay_summary.parquet` (2.5 MB).

24631 cards, 17110 entries (passed + vetoed), run `data/replay/run12m`. Rules: the docstring of `research_replay_report.py`.

## Cards (final_r: the lifecycle exit, net)

| strategy | cards | mean | 90% (4h clusters) | older | newer | win | verdict |
|---|---:|---:|---|---:|---:|---:|---|
| bollinger | 3109 | -0.251 | [-0.300..-0.201] | -0.266 | -0.231 | 41% | - |
| breakout | 342 | +1.108 | [+0.240..+2.176] | +1.247 | +0.985 | 29% | POSITIVE |
| connors | 213 | -0.092 | [-0.198..+0.007] | -0.002 | -0.162 | 61% | - |
| continuation | 16 | +0.220 | [-0.495..+1.127] | +1.066 | -0.627 | 50% | - |
| market_profile | 1927 | -0.198 | [-0.276..-0.116] | -0.158 | -0.260 | 36% | - |
| pump | 97 | -0.090 | [-0.334..+0.150] | -0.083 | -0.097 | 40% | - |
| supply_demand | 5 | -0.373 | [-1.102..+0.470] | -0.199 | -1.069 | 20% | - |
| sweep | 141 | -0.227 | [-0.382..-0.076] | -0.114 | -0.360 | 33% | - |
| trendline | 84 | +0.047 | [-0.386..+0.513] | -0.035 | +0.133 | 23% | - |

## Exits by nature (3.1): the same entered cards, mean net R

| strategy | lifecycle exit (final_r) | all at TP1 (r_tp1) | all at TP2 (r_tp2) | BE after TP1 (r_be) |
|---|---:|---:|---:|---:|
| bollinger | -0.251 | -0.145 | -0.145 | -0.145 |
| breakout | +1.108 | +0.037 | +0.037 | +0.037 |
| connors | -0.092 | -0.032 | -0.032 | -0.032 |
| continuation | +0.220 | -0.176 | -0.238 | -0.256 |
| market_profile | -0.198 | -0.162 | -0.173 | -0.174 |
| pump | -0.090 | +0.049 | +0.088 | +0.054 |
| supply_demand | -0.373 | +0.663 | +0.663 | +0.663 |
| sweep | -0.227 | -0.168 | -0.140 | -0.162 |
| trendline | +0.047 | -0.332 | -0.288 | -0.273 |

## Vetoes: entries rejected vs passed (r_tp1 net, journal replay)

| strategy | veto | n | mean r_tp1 | passed mean | rejected worse? |
|---|---|---:|---:|---:|---|
| bollinger | low_rr | 4512 | -0.577 | -0.145 | yes |
| breakout | unit_limit | 243 | -0.005 | +0.037 | yes |
| continuation | against_btc | 262 | -0.312 | -0.176 | yes |
| continuation | against_day | 105 | -0.123 | -0.176 | no |
| continuation | killzone | 1756 | -0.224 | -0.176 | yes |
| continuation | low_rr | 269 | -0.125 | -0.176 | no |
| continuation | variant_shift | 10 | +0.116 | -0.176 | no |
| market_profile | low_rr | 1273 | -0.223 | -0.162 | yes |
| pump | low_rr | 353 | -0.052 | +0.049 | yes |
| supply_demand | against_day | 21 | +0.024 | +0.663 | yes |
| supply_demand | low_rr | 88 | -0.060 | +0.663 | yes |
| sweep | against_btc | 73 | -0.114 | -0.168 | no |
| sweep | against_day | 63 | -0.117 | -0.168 | no |
| sweep | killzone | 641 | -0.180 | -0.168 | yes |
| sweep | low_rr | 188 | -0.201 | -0.168 | yes |
| sweep | variant_shift | 116 | -0.138 | -0.168 | no |
| sweep | weak_mss | 363 | -0.175 | -0.168 | yes |
| trendline | against_day | 29 | -0.596 | -0.332 | yes |
| trendline | low_rr | 221 | -0.545 | -0.332 | yes |
| wyckoff | low_rr | 12 | +0.121 | — | — |
| wyckoff | no_spring_test | 61 | -0.086 | — | — |

## Setups that never became a card (by reason)

| setup | reason | n |
|---|---|---:|
| SWEEP LOW | against_bias | 12498 |
| BB W-BOTTOM | low_rr | 10054 |
| BB M-TOP | low_rr | 8653 |
| SWEEP HIGH | against_bias | 7493 |
| SWEEP LOW | against_trend | 6424 |
| SWEEP HIGH | against_trend | 5671 |
| BULL F | against_tide | 2400 |
| BB W-BOTTOM | same_leg | 1803 |
| BB M-TOP | same_leg | 1462 |
| VA80 LONG | same_leg | 1328 |
| BULL F | no_level | 1150 |
| SWEEP HIGH | discount | 1120 |
| SWEEP LOW | premium | 1025 |
| BULL F | no_leg | 975 |
| SWEEP HIGH | no_htf_poi | 862 |
| VA80 SHORT | same_leg | 721 |
| SILVER BULLET LONG | against_bias | 719 |
| SWEEP LOW | no_htf_poi | 678 |
| BEAR D | against_tide | 585 |
| BULL F | no_bos | 571 |
| SD DEMAND | big_picture | 566 |
| BEAR D | no_level | 525 |
| SILVER BULLET SHORT | against_bias | 518 |
| BEAR D | no_leg | 509 |
| BEAR D | perp_led | 465 |
| AUCTION LONG | no_target | 379 |
| IMPULSE UP | against_tide | 363 |
| SILVER BULLET SHORT | discount | 307 |
| IMPULSE UP | no_leg | 304 |
| SILVER BULLET LONG | against_trend | 303 |
| SILVER BULLET SHORT | against_trend | 275 |
| SILVER BULLET LONG | premium | 268 |
| BEAR D | no_bos | 225 |
| SD SUPPLY | curve | 204 |
| AUCTION SHORT | no_target | 192 |
| BEAR D | no_displacement | 165 |
| SPRING | against_htf | 156 |
| SD SUPPLY | big_picture | 154 |
| BULL F | no_displacement | 150 |
| IMPULSE UP | no_level | 97 |
