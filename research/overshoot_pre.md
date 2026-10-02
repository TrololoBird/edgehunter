# Level overshoot before a rejection (80 coins, 2025-04-05 .. 2026-03-31)

Depth = how far beyond the level price traded before a 15m close back within 1h, % of the level. Coverage = share of the NEWER half's rejections within the OLDER half's p80 (80% = stable).

| kind | rejections | break share | p50 | p80 | p90 | p80 older half | coverage newer half |
|---|---:|---:|---:|---:|---:|---:|---:|
| swing_15m | 287664 | 24% | 0.232% | 0.636% | 1.032% | 0.612% | 78% |
| swing_1h | 83045 | 25% | 0.290% | 0.786% | 1.305% | 0.736% | 77% |
| equal | 12706 | 26% | 0.237% | 0.642% | 1.080% | 0.601% | 77% |
| pdhl | 36017 | 26% | 0.334% | 0.940% | 1.642% | 0.845% | 75% |
| round | 7899 | 24% | 0.488% | 1.400% | 2.476% | 1.340% | 78% |

Per coin p80 of swing_15m: min 0.156%, median 0.654%, max 1.483% (80 coins): one buffer for all coins would be wrong.
