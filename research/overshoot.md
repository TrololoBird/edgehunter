# Level overshoot before a rejection (80 coins, 2025-09-05 .. 2026-08-31)

Depth = how far beyond the level price traded before a 15m close back within 1h, % of the level. Coverage = share of the NEWER half's rejections within the OLDER half's p80 (80% = stable).

| kind | rejections | break share | p50 | p80 | p90 | p80 older half | coverage newer half |
|---|---:|---:|---:|---:|---:|---:|---:|
| swing_15m | 274672 | 25% | 0.228% | 0.627% | 1.036% | 0.662% | 83% |
| swing_1h | 83816 | 26% | 0.288% | 0.773% | 1.278% | 0.818% | 83% |
| equal | 14297 | 26% | 0.232% | 0.609% | 0.999% | 0.638% | 82% |
| pdhl | 37091 | 26% | 0.336% | 0.918% | 1.552% | 0.976% | 83% |
| round | 8042 | 25% | 0.455% | 1.364% | 2.455% | 1.400% | 83% |

Per coin p80 of swing_15m: min 0.147%, median 0.650%, max 1.395% (80 coins): one buffer for all coins would be wrong.
