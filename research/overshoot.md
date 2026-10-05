# Level overshoot before a rejection (120 coins, 2025-10-05 .. 2026-09-30)

Depth = how far beyond the level price traded before a 15m close back within 1h, % of the level. Coverage = share of the NEWER half's rejections within the OLDER half's p80 (80% = stable).

| kind | rejections | break share | p50 | p80 | p90 | p80 older half | coverage newer half |
|---|---:|---:|---:|---:|---:|---:|---:|
| swing_15m | 388767 | 25% | 0.241% | 0.661% | 1.089% | 0.678% | 81% |
| swing_1h | 122754 | 25% | 0.301% | 0.808% | 1.341% | 0.822% | 81% |
| equal | 20477 | 26% | 0.246% | 0.646% | 1.049% | 0.656% | 81% |
| pdhl | 55358 | 26% | 0.352% | 0.950% | 1.613% | 0.966% | 81% |
| round | 11193 | 25% | 0.463% | 1.346% | 2.347% | 1.304% | 77% |

Per coin p80 of swing_15m: min 0.141%, median 0.686%, max 1.345% (120 coins): one buffer for all coins would be wrong.
