# Level overshoot before a rejection (260 coins, 2025-10-05 .. 2026-09-30)

Depth = how far beyond the level price traded before a 15m close back within 1h, % of the level. Coverage = share of the NEWER half's rejections within the OLDER half's p80 (80% = stable).

| kind | rejections | break share | p50 | p80 | p90 | p80 older half | coverage newer half |
|---|---:|---:|---:|---:|---:|---:|---:|
| swing_15m | 775976 | 25% | 0.251% | 0.684% | 1.135% | 0.692% | 81% |
| swing_1h | 254636 | 25% | 0.311% | 0.842% | 1.429% | 0.848% | 80% |
| equal | 42135 | 26% | 0.264% | 0.694% | 1.133% | 0.703% | 81% |
| pdhl | 117111 | 25% | 0.366% | 1.025% | 1.829% | 1.038% | 81% |
| round | 24833 | 25% | 0.466% | 1.338% | 2.436% | 1.299% | 78% |

Per coin p80 of swing_15m: min 0.141%, median 0.691%, max 2.327% (260 coins): one buffer for all coins would be wrong.
