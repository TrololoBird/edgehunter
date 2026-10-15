# Level overshoot before a rejection (80 coins, 2025-10-05 .. 2026-09-30)

Depth = how far beyond the level price traded before a 15m close back within 1h, % of the level. Coverage = share of the NEWER half's rejections within the OLDER half's p80 (80% = stable).

| kind | rejections | break share | p50 | p80 | p90 | p80 older half | coverage newer half |
|---|---:|---:|---:|---:|---:|---:|---:|
| swing_15m | 231724 | 50% | 0.138% | 0.364% | 0.597% | 0.376% | 82% |
| swing_1h | 76851 | 50% | 0.177% | 0.454% | 0.745% | 0.465% | 81% |
| equal | 22856 | 50% | 0.162% | 0.405% | 0.655% | 0.416% | 81% |
| pdhl | 25277 | 50% | 0.219% | 0.571% | 0.946% | 0.583% | 81% |
| round | 4969 | 50% | 0.306% | 0.823% | 1.426% | 0.793% | 76% |

Per coin p80 of swing_15m: min 0.083%, median 0.392%, max 0.849% (80 coins): one buffer for all coins would be wrong.
