# Pumps / dumps and what follows (478 coins, 2023-10-16 .. 2026-08-29)

Rules: the docstring of `research_pumps.py` (pre-registered). 'fwd' = the return in the move's direction minus the universe mean (so negative = reversal).

## What follows the event

| class | kind | half | events | back to 50% before a new extreme | back to the base | fwd 6h | fwd 24h | fwd 72h |
|---|---|---|---:|---:|---:|---:|---:|---:|
| small caps | pump | older | 1492 | 78% | 30% | -0.17% | -0.56% | -0.72% |
| small caps | dump | older | 974 | 67% | 44% | +0.18% | +0.61% | +0.58% |
| majors | dump | older | 13 | 85% | 78% | -0.33% | +1.17% | +1.63% |
| majors | pump | older | 9 | 78% | 43% | +1.63% | +2.38% | +0.78% |
| small caps | pump | newer | 1089 | 82% | 39% | -0.48% | -0.43% | -0.01% |
| small caps | dump | newer | 404 | 55% | 20% | +0.89% | +1.59% | -1.50% |
| majors | dump | newer | 2 | 50% | 50% | +0.04% | -0.65% | -3.33% |
| majors | pump | newer | 6 | 67% | 20% | -5.30% | -4.75% | -8.71% |

## Trades

| class | kind | strategy | half | trades | TP1 hit | geometry | R TP1 net 0.20% [90%] | R TP1 at 0.40% | TP2 hit | geometry TP2 | R TP2 net | median stop |
|---|---|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| small caps | pump | FADE | older | 1485 | 64% | 65% | -0.075 [-0.160..+0.011] | -0.104 | 31% | 37% | -0.162 | 8.6% |
| small caps | pump | DIP-BUY | older | 762 | 58% | 51% | +0.129 [-0.045..+0.325] | +0.091 | 20% | 24% | -0.151 | 5.8% |
| small caps | dump | FADE | older | 972 | 64% | 57% | +0.060 [-0.251..+0.335] | +0.028 | 44% | 31% | +0.359 | 7.0% |
| small caps | dump | DIP-BUY | older | 403 | 49% | 43% | +0.170 [-0.442..+0.788] | +0.129 | 14% | 19% | -0.201 | 5.1% |
| small caps | pump | FADE | newer | 1084 | 63% | 65% | -0.030 [-0.130..+0.092] | -0.057 | 40% | 41% | +0.066 | 10.5% |
| small caps | pump | DIP-BUY | newer | 539 | 56% | 49% | +0.136 [-0.075..+0.341] | +0.100 | 16% | 23% | -0.273 | 6.2% |
| small caps | dump | FADE | newer | 402 | 39% | 49% | -0.310 [-0.410..-0.197] | -0.349 | 21% | 28% | -0.257 | 6.6% |
| small caps | dump | DIP-BUY | newer | 161 | 67% | 57% | +0.163 [+0.011..+0.324] | +0.130 | 21% | 27% | -0.019 | 7.2% |

## Trades by the size of the move (whole window)

| class | kind | strategy | size | trades | TP1 hit | geometry | R TP1 net | R TP2 net |
|---|---|---|---|---:|---:|---:|---:|---:|
| small caps | pump | FADE | 15-30% | 2290 | 64% | 65% | -0.049 | -0.074 |
| small caps | pump | DIP-BUY | 15-30% | 1122 | 57% | 51% | +0.130 | -0.196 |
| small caps | pump | FADE | 30-60% | 192 | 62% | 63% | -0.076 | +0.104 |
| small caps | dump | FADE | 15-30% | 1299 | 58% | 55% | -0.035 | +0.185 |
| small caps | dump | DIP-BUY | 15-30% | 532 | 54% | 47% | +0.187 | -0.147 |
| small caps | pump | FADE | 60%+ | 87 | 40% | 63% | -0.194 | -0.223 |
| small caps | pump | DIP-BUY | 60%+ | 75 | 71% | 48% | +0.242 | +0.113 |
| small caps | pump | DIP-BUY | 30-60% | 104 | 56% | 50% | +0.081 | -0.490 |
| small caps | dump | FADE | 30-60% | 67 | 52% | 48% | -0.049 | +0.072 |
| small caps | dump | DIP-BUY | 30-60% | 29 | 48% | 45% | -0.090 | -0.145 |
