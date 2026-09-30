# Tier-0 inputs vs what followed (live journal)

Journals: signals.eng6.bak.db, signals.db. Effect = median of |4h move after| / the coin's usual |4h move| (x1.0 = nothing beyond the coin's normal volatility). n per bin; bins with < 25 rows are marked.

## rvol_1m

| bin | n | effect (median) | effect (mean) |
|---|---:|---:|---:|
| 0 .. 2 | 1790 | x0.97 | x1.08 |
| 2 .. 3 | 568 | x1.01 | x1.15 |
| 3 .. 5 | 674 | x1.01 | x1.18 |
| 5 .. 8 | 1415 | x1.02 | x1.20 |
| 8 .. 12 | 519 | x1.02 | x1.22 |
| 12 .. 1e+09 | 496 | x1.01 | x1.22 |

## abs(price_z)

| bin | n | effect (median) | effect (mean) |
|---|---:|---:|---:|
| 0 .. 1 | 2177 | x0.99 | x1.12 |
| 1 .. 2 | 1518 | x0.98 | x1.13 |
| 2 .. 3 | 741 | x1.03 | x1.21 |
| 3 .. 4 | 371 | x1.01 | x1.17 |
| 4 .. 6 | 560 | x1.00 | x1.23 |
| 6 .. 1e+09 | 95 | x1.08 | x1.50 |

## abs(oi_z)

| bin | n | effect (median) | effect (mean) |
|---|---:|---:|---:|
| 0 .. 1 | 3992 | x0.98 | x1.13 |
| 1 .. 2 | 778 | x1.02 | x1.21 |
| 2 .. 3 | 318 | x1.09 | x1.24 |
| 3 .. 4 | 126 | x1.05 | x1.22 |
| 4 .. 6 | 155 | x1.01 | x1.21 |
| 6 .. 1e+09 | 93 | x1.18 | x1.31 |

## abs(whale_net_5m)

| bin | n | effect (median) | effect (mean) |
|---|---:|---:|---:|
| 0 .. 1 | 945 | x0.99 | x1.18 |
| 1 .. 2 | 755 | x0.95 | x1.15 |
| 2 .. 3 | 546 | x0.95 | x1.18 |
| 3 .. 5 | 1671 | x1.02 | x1.14 |
| 5 .. 10 | 932 | x1.01 | x1.13 |
| 10 .. 1e+09 | 613 | x1.00 | x1.18 |

## liq_long_5m + liq_short_5m

| bin | n | effect (median) | effect (mean) |
|---|---:|---:|---:|
| 0 .. 1 | 2163 | x1.01 | x1.15 |
| 1 .. 10000 | 2239 | x1.02 | x1.19 |
| 10000 .. 50000 | 729 | x0.90 | x1.07 |
| 50000 .. 200000 | 240 | x0.92 | x1.10 |
| 200000 .. 1e+06 | 76 | x1.20 | x1.40 |
| 1e+06 .. 1e+12 | 15 (few) | x1.36 | x1.35 |

## top_venue_share

| bin | n | effect (median) | effect (mean) |
|---|---:|---:|---:|
| 0 .. 0.5 | 1653 | x0.99 | x1.16 |
| 0.5 .. 0.65 | 1589 | x1.00 | x1.16 |
| 0.65 .. 0.8 | 1131 | x0.99 | x1.12 |
| 0.8 .. 0.9 | 842 | x1.04 | x1.19 |
| 0.9 .. 1.01 | 247 | x1.02 | x1.19 |

