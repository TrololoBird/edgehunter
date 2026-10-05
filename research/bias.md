# Top-down bias on the replay's trades (research_bias.py; the rule fixed by the sources, nothing fitted)

5688 entered cards, outcome = the card's final_r (its own exits). Bias mix: bear 3258, conflict 1170, bull 1068, range 192

| strategy | allowed: n, R [lower 90%] | blocked: n, R | diff | months allowed > blocked | longs allowed / blocked | shorts allowed / blocked | verdict |
|---|---|---|---|---|---|---|---|
| bollinger | 705, -0.251 [-0.337] | 2231, -0.262 | +0.010 | 6/12 | -0.08 (122) / -0.35 (1318) | -0.29 (583) / -0.13 (913) | no |
| breakout | 342 | 0 | - | - | - | - | too few |
| connors | 140, -0.051 [-0.188] | 73, -0.170 | +0.119 | 1/3 | +0.07 (9) / -0.10 (24) | -0.06 (131) / -0.20 (49) | no |
| continuation | 2 | 12 | - | - | - | - | too few |
| market_profile | 349, -0.185 [-0.315] | 1524, -0.208 | +0.024 | 5/12 | -0.34 (69) / -0.22 (1030) | -0.15 (280) / -0.19 (494) | no |
| pump | 12, +0.130 [-0.584] | 81, -0.109 | +0.239 | 0/0 | +0.12 (9) / -0.11 (67) | +0.16 (3) / -0.10 (14) | no |
| supply_demand | 1 | 4 | - | - | - | - | too few |
| sweep | 45, -0.123 [-0.425] | 89, -0.270 | +0.147 | 0/2 | -0.14 (12) / -0.51 (48) | -0.12 (33) / +0.02 (41) | no |
| trendline | 10, -0.901 [-1.278] | 68, +0.295 | -1.196 | 0/0 | -1.29 (1) / +0.11 (31) | -0.86 (9) / +0.45 (37) | no |

## Blocked by reason

- btc_bias: 2825 trades, mean R -0.229
- allowed: 1606 trades, mean R +0.071
- htf_conflict: 636 trades, mean R -0.196
- htf_bias: 621 trades, mean R -0.243

## All strategies by month (allowed vs blocked mean R)

- 2025-10: allowed +1.337 (132), blocked -0.188 (497)
- 2025-11: allowed -0.303 (134), blocked -0.241 (434)
- 2025-12: allowed -0.224 (149), blocked -0.118 (319)
- 2026-01: allowed +0.099 (187), blocked -0.196 (406)
- 2026-02: allowed -0.121 (144), blocked -0.302 (334)
- 2026-03: allowed -0.255 (194), blocked -0.325 (261)
- 2026-04: allowed +0.057 (141), blocked -0.240 (214)
- 2026-05: allowed +0.973 (93), blocked -0.237 (275)
- 2026-06: allowed -0.474 (109), blocked -0.231 (450)
- 2026-07: allowed -0.019 (127), blocked -0.214 (180)
- 2026-08: allowed +0.477 (105), blocked -0.301 (252)
- 2026-09: allowed -0.382 (91), blocked -0.189 (460)
