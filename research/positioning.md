# Positioning as an entry source (349 coins, 132222 samples, 2025-10-09 .. 2026-08-28)

Forward return minus the universe mean, by decile of each feature (pooled over coins); the contrarian trade = long the bottom decile / short the top one (for oi_3d and px_3d both readings are shown). [90%] by calendar week. Rules: the docstring of `research_positioning.py`.

## funding (bottom decile < -0.0003171, top decile > 0.0001)

| half | horizon | bottom decile | middle 80% | top decile | spread bottom - top [90%] |
|---|---|---:|---:|---:|---|
| older | 24h | -0.21% | +0.03% | +0.10% | -0.20% [-0.42..+0.01] |
| older | 72h | -0.47% | +0.07% | +0.25% | -0.46% [-0.87..-0.04] |
| newer | 24h | -0.82% | +0.10% | -0.31% | -0.69% [-0.99..-0.41] |
| newer | 72h | -1.91% | +0.22% | -0.02% | -1.69% [-2.31..-1.06] |

## funding_z (bottom decile < -1.26, top decile > 0.909)

| half | horizon | bottom decile | middle 80% | top decile | spread bottom - top [90%] |
|---|---|---:|---:|---:|---|
| older | 24h | +0.00% | +0.00% | +0.02% | -0.01% [-0.12..+0.11] |
| older | 72h | +0.23% | -0.02% | +0.06% | +0.10% [-0.18..+0.39] |
| newer | 24h | -0.36% | +0.05% | +0.11% | -0.22% [-0.40..-0.04] |
| newer | 72h | -0.47% | +0.09% | +0.06% | -0.25% [-0.53..+0.02] |

## global_z (bottom decile < -1.636, top decile > 1.604)

| half | horizon | bottom decile | middle 80% | top decile | spread bottom - top [90%] |
|---|---|---:|---:|---:|---|
| older | 24h | -0.04% | -0.01% | +0.14% | -0.08% [-0.22..+0.04] |
| older | 72h | -0.14% | -0.00% | +0.23% | -0.18% [-0.42..+0.06] |
| newer | 24h | -0.24% | +0.05% | -0.04% | -0.07% [-0.26..+0.13] |
| newer | 72h | -0.63% | +0.15% | -0.24% | -0.11% [-0.59..+0.32] |

## top_pos_z (bottom decile < -1.508, top decile > 1.793)

| half | horizon | bottom decile | middle 80% | top decile | spread bottom - top [90%] |
|---|---|---:|---:|---:|---|
| older | 24h | -0.01% | +0.00% | +0.01% | -0.01% [-0.12..+0.11] |
| older | 72h | -0.05% | -0.00% | +0.12% | -0.08% [-0.33..+0.18] |
| newer | 24h | +0.07% | +0.02% | -0.03% | +0.05% [-0.16..+0.26] |
| newer | 72h | +0.18% | +0.05% | -0.12% | +0.14% [-0.30..+0.60] |

## oi_3d (bottom decile < -0.1231, top decile > 0.1088)

| half | horizon | bottom decile | middle 80% | top decile | spread bottom - top [90%] |
|---|---|---:|---:|---:|---|
| older | 24h | -0.06% | -0.00% | +0.09% | -0.07% [-0.25..+0.10] |
| older | 72h | -0.33% | +0.01% | +0.25% | -0.29% [-0.65..+0.04] |
| newer | 24h | -0.44% | +0.07% | +0.02% | -0.23% [-0.52..+0.06] |
| newer | 72h | -0.64% | +0.14% | -0.18% | -0.24% [-0.97..+0.44] |

## px_3d (bottom decile < -0.1156, top decile > 0.09021)

| half | horizon | bottom decile | middle 80% | top decile | spread bottom - top [90%] |
|---|---|---:|---:|---:|---|
| older | 24h | -0.16% | +0.02% | +0.07% | -0.12% [-0.31..+0.06] |
| older | 72h | -0.35% | +0.06% | +0.07% | -0.22% [-0.59..+0.11] |
| newer | 24h | +0.17% | +0.01% | -0.07% | +0.11% [-0.20..+0.42] |
| newer | 72h | +0.49% | +0.03% | -0.28% | +0.37% [-0.39..+1.03] |


## Pre-registered confirmation (written BEFORE the run)

The only feature passing the rule above: the funding LEVEL, read WITH the crowd (not contrarian): coins whose last
settlement is in the bottom decile keep underperforming (72h: -0.47% older, -1.91% newer half, both intervals below 0).
Rule fixed here, tested once on the untouched 2023-10 .. 2025-09 (`research_funding.py`): SHORT a coin when its last
funding settlement is <= -0.0317% (this window's bottom-decile cutoff), hold 72h, one position per coin at a time;
net of 0.20% round trip AND the funding the short pays. CONFIRMED only if the mean net return per trade vs the
universe mean is > 0 with its 90% interval above 0 AND the absolute net return per trade is > 0.
