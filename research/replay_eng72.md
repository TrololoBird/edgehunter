# Archive replay of the live card lifecycle (B9)

167175 cards, 139955 entries (passed + vetoed), run `data/replay/eng72`. Rules: the docstring of `research_replay_report.py`.

## Cards (final_r: the lifecycle exit, net)

| strategy | cards | mean | 90% (4h clusters) | older | newer | win | verdict |
|---|---:|---:|---|---:|---:|---:|---|
| bollinger | 36821 | -0.134 | [-0.153..-0.115] | -0.101 | -0.163 | 52% | - |
| breakout | 1687 | +0.571 | [+0.171..+1.006] | +0.823 | +0.315 | 24% | POSITIVE |
| connors | 1220 | -0.044 | [-0.092..+0.005] | -0.058 | -0.032 | 58% | - |
| continuation | 15 | -0.100 | [-0.425..+0.243] | -0.045 | -0.209 | 53% | - |
| market_profile | 12493 | -0.155 | [-0.188..-0.122] | -0.138 | -0.170 | 36% | - |
| orb | 48093 | -0.107 | [-0.134..-0.079] | -0.106 | -0.107 | 41% | - |
| pump | 1777 | -0.068 | [-0.146..+0.014] | +0.023 | -0.125 | 38% | - |
| supply_demand | 20 | +1.091 | [+0.114..+2.211] | +0.033 | +2.149 | 55% | POSITIVE |
| sweep | 696 | -0.103 | [-0.190..-0.011] | -0.042 | -0.153 | 40% | - |
| trendline | 563 | -0.025 | [-0.205..+0.165] | +0.177 | -0.268 | 22% | - |
| wyckoff | 20 | -0.239 | [-0.543..+0.103] | -0.003 | -0.318 | 30% | - |

## Exits by nature (3.1): the same entered cards, mean net R

| strategy | lifecycle exit (final_r) | all at TP1 (r_tp1) | all at TP2 (r_tp2) | BE after TP1 (r_be) |
|---|---:|---:|---:|---:|
| bollinger | -0.134 | -0.095 | -0.095 | -0.095 |
| breakout | +0.571 | +0.027 | +0.027 | +0.027 |
| connors | -0.044 | -0.021 | -0.021 | -0.021 |
| continuation | -0.100 | +0.093 | +0.186 | +0.179 |
| market_profile | -0.155 | -0.135 | -0.143 | -0.144 |
| orb | -0.107 | -0.089 | -0.089 | -0.089 |
| pump | -0.068 | -0.031 | -0.028 | -0.026 |
| supply_demand | +1.091 | +0.478 | +0.350 | +0.412 |
| sweep | -0.103 | -0.111 | -0.077 | -0.075 |
| trendline | -0.025 | -0.129 | -0.134 | -0.126 |
| wyckoff | -0.239 | -0.054 | -0.109 | -0.131 |

## Vetoes: entries rejected vs passed (r_tp1 net, journal replay)

| strategy | veto | n | mean r_tp1 | passed mean | rejected worse? |
|---|---|---:|---:|---:|---|
| bollinger | low_rr | 1513 | -0.376 | -0.095 | yes |
| breakout | unit_limit | 775 | -0.013 | +0.027 | yes |
| continuation | against_btc | 426 | +0.084 | +0.093 | yes |
| continuation | against_day | 1154 | -0.006 | +0.093 | yes |
| continuation | killzone | 7400 | -0.058 | +0.093 | yes |
| continuation | low_rr | 987 | -0.069 | +0.093 | yes |
| continuation | variant_shift | 20 | +0.111 | +0.093 | no |
| market_profile | low_rr | 2669 | -0.177 | -0.135 | yes |
| orb | low_rr | 388 | -0.276 | -0.089 | yes |
| pump | low_rr | 827 | +0.020 | -0.031 | no |
| supply_demand | against_day | 242 | -0.042 | +0.478 | yes |
| supply_demand | low_rr | 82 | -0.090 | +0.478 | yes |
| sweep | against_btc | 227 | -0.169 | -0.111 | yes |
| sweep | against_day | 1194 | -0.113 | -0.111 | yes |
| sweep | flow_entry | 9405 | -0.101 | -0.111 | no |
| sweep | killzone | 3749 | -0.111 | -0.111 | yes |
| sweep | low_rr | 369 | -0.098 | -0.111 | no |
| sweep | variant_shift | 728 | -0.092 | -0.111 | no |
| sweep | weak_mss | 1772 | -0.084 | -0.111 | no |
| trendline | against_day | 367 | -0.303 | -0.129 | yes |
| trendline | low_rr | 292 | -0.527 | -0.129 | yes |
| wyckoff | against_day | 78 | -0.118 | -0.054 | yes |
| wyckoff | flow_entry | 385 | -0.167 | -0.054 | yes |
| wyckoff | low_rr | 88 | +0.080 | -0.054 | no |
| wyckoff | no_spring_test | 593 | -0.111 | -0.054 | yes |

## Setups that never became a card (by reason)

| setup | reason | n |
|---|---|---:|
| SWEEP LOW | against_bias | 59731 |
| BB W-BOTTOM | low_rr | 46835 |
| SWEEP HIGH | against_bias | 43456 |
| BB M-TOP | low_rr | 39963 |
| SWEEP LOW | against_trend | 31309 |
| SWEEP HIGH | against_trend | 28372 |
| BULL F | against_tide | 10594 |
| BULL F | no_level | 6896 |
| SWEEP HIGH | discount | 4341 |
| BULL F | no_leg | 4192 |
| BEAR D | no_level | 4117 |
| SWEEP LOW | premium | 4000 |
| SILVER BULLET LONG | against_bias | 3868 |
| BB W-BOTTOM | same_leg | 3851 |
| BEAR D | against_tide | 3488 |
| BB M-TOP | same_leg | 3452 |
| SILVER BULLET SHORT | against_bias | 3217 |
| SD DEMAND | big_picture | 2587 |
| SWEEP HIGH | no_htf_poi | 2442 |
| VA80 LONG | same_leg | 2441 |
| BEAR D | perp_led | 2415 |
| SWEEP LOW | no_htf_poi | 2223 |
| BEAR D | no_leg | 2197 |
| VA80 SHORT | same_leg | 2141 |
| BULL F | no_bos | 1973 |
| SILVER BULLET LONG | against_trend | 1635 |
| SILVER BULLET SHORT | against_trend | 1420 |
| IMPULSE UP | no_leg | 1281 |
| SILVER BULLET SHORT | discount | 1271 |
| IMPULSE UP | against_tide | 1201 |
| SILVER BULLET LONG | premium | 1122 |
| SD SUPPLY | big_picture | 1019 |
| BEAR D | no_bos | 977 |
| BULL F | no_displacement | 783 |
| IMPULSE UP | no_level | 769 |
| SD SUPPLY | curve | 726 |
| SPRING | against_htf | 676 |
| IMPULSE DOWN | no_leg | 610 |
| BEAR D | no_displacement | 571 |
| SD DEMAND | curve | 497 |
