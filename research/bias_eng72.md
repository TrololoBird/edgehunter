# Top-down bias on the replay's trades (research_bias.py; the rule fixed by the sources, nothing fitted)

99099 entered cards, outcome = the card's final_r (its own exits). Bias mix: bear 52014, bull 21703, conflict 21244, range 4138

| strategy | allowed: n, R [lower 90%] | blocked: n, R | diff | months allowed > blocked | longs allowed / blocked | shorts allowed / blocked | verdict |
|---|---|---|---|---|---|---|---|
| bollinger | 8738, -0.133 [-0.161] | 26424, -0.138 | +0.005 | 13/24 | -0.11 (3276) / -0.16 (16111) | -0.15 (5462) / -0.10 (10313) | no |
| breakout | 1687 | 0 | - | - | - | - | too few |
| connors | 623, -0.003 [-0.057] | 597, -0.087 | +0.084 | 13/20 | +0.02 (173) / -0.01 (117) | -0.01 (450) / -0.11 (480) | no |
| continuation | 3 | 10 | - | - | - | - | too few |
| market_profile | 2497, -0.193 [-0.243] | 9477, -0.146 | -0.047 | 12/24 | -0.19 (989) / -0.17 (5906) | -0.19 (1508) / -0.11 (3571) | no |
| orb | 10353, -0.070 [-0.117] | 35846, -0.120 | +0.049 | 15/24 | -0.10 (3209) / -0.11 (21763) | -0.06 (7144) / -0.14 (14083) | no |
| pump | 235, -0.117 [-0.296] | 1362, -0.070 | -0.047 | 5/15 | -0.09 (201) / -0.08 (1239) | -0.30 (34) / -0.02 (123) | no |
| supply_demand | 2 | 18 | - | - | - | - | too few |
| sweep | 191, -0.308 [-0.436] | 484, -0.034 | -0.273 | 4/17 | -0.32 (86) / -0.09 (330) | -0.30 (105) / +0.09 (154) | no |
| trendline | 532 | 0 | - | - | - | - | too few |
| wyckoff | 1 | 19 | - | - | - | - | too few |

## Blocked by reason

- btc_bias: 44062 trades, mean R -0.146
- allowed: 24862 trades, mean R -0.061
- htf_bias: 17089 trades, mean R -0.099
- htf_conflict: 13086 trades, mean R -0.103

## All strategies by month (allowed vs blocked mean R)

- 2024-10: allowed -0.149 (816), blocked -0.157 (2825)
- 2024-11: allowed +0.712 (871), blocked -0.109 (2589)
- 2024-12: allowed -0.220 (963), blocked -0.129 (2421)
- 2025-01: allowed -0.087 (517), blocked -0.087 (2947)
- 2025-02: allowed -0.015 (629), blocked -0.212 (2214)
- 2025-03: allowed +0.028 (928), blocked -0.124 (2274)
- 2025-04: allowed -0.002 (725), blocked -0.113 (2894)
- 2025-05: allowed -0.202 (674), blocked -0.094 (3269)
- 2025-06: allowed -0.022 (373), blocked -0.155 (3360)
- 2025-07: allowed -0.030 (805), blocked -0.137 (3088)
- 2025-08: allowed -0.103 (1078), blocked -0.065 (3360)
- 2025-09: allowed +0.020 (1041), blocked -0.006 (3229)
- 2025-10: allowed +0.053 (920), blocked -0.059 (3431)
- 2025-11: allowed -0.100 (1482), blocked -0.198 (2827)
- 2025-12: allowed -0.077 (1603), blocked -0.146 (2946)
- 2026-01: allowed -0.016 (1588), blocked -0.106 (3701)
- 2026-02: allowed -0.117 (1086), blocked -0.244 (2920)
- 2026-03: allowed -0.151 (1567), blocked -0.145 (3165)
- 2026-04: allowed -0.147 (1329), blocked -0.091 (3146)
- 2026-05: allowed -0.079 (1135), blocked -0.115 (3703)
- 2026-06: allowed -0.070 (1368), blocked -0.159 (3596)
- 2026-07: allowed -0.144 (1321), blocked -0.189 (3259)
- 2026-08: allowed -0.177 (935), blocked -0.136 (3390)
- 2026-09: allowed -0.142 (1108), blocked -0.132 (3683)
