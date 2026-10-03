# Pumps / dumps and what follows (478 coins, 2023-11-18 .. 2026-09-26)

Rules: the docstring of `research_pumps.py` (pre-registered). 'fwd' = the return in the move's direction minus the universe mean (so negative = reversal).

## What follows the event

| class | kind | half | events | back to 50% before a new extreme | back to the base | fwd 6h | fwd 24h | fwd 72h |
|---|---|---|---:|---:|---:|---:|---:|---:|
| small caps | dump | older | 982 | 67% | 43% | +0.25% | +0.68% | +0.56% |
| small caps | pump | older | 1465 | 79% | 30% | -0.32% | -0.58% | -0.61% |
| majors | dump | older | 14 | 86% | 80% | -0.24% | +0.82% | +0.55% |
| majors | pump | older | 9 | 78% | 43% | +1.63% | +2.38% | +0.78% |
| small caps | pump | newer | 1093 | 83% | 40% | -0.41% | -0.47% | -0.13% |
| small caps | dump | newer | 392 | 55% | 20% | +0.81% | +1.43% | -1.65% |
| majors | pump | newer | 6 | 67% | 20% | -5.30% | -4.75% | -8.71% |

## Trades

| class | kind | strategy | half | trades | TP1 hit | geometry | R TP1 net 0.20% [90%] | R TP1 at 0.40% | TP2 hit | geometry TP2 | R TP2 net | median stop |
|---|---|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| small caps | dump | FADE | older | 980 | 64% | 57% | +0.048 [-0.266..+0.322] | +0.017 | 44% | 31% | +0.339 | 7.1% |
| small caps | pump | FADE | older | 1458 | 64% | 65% | -0.073 [-0.167..+0.013] | -0.101 | 31% | 37% | -0.161 | 8.7% |
| small caps | pump | DIP-BUY | older | 738 | 57% | 52% | +0.073 [-0.074..+0.228] | +0.035 | 20% | 24% | -0.177 | 5.8% |
| small caps | dump | DIP-BUY | older | 403 | 49% | 43% | +0.177 [-0.411..+0.776] | +0.136 | 13% | 19% | -0.199 | 5.2% |
| small caps | pump | FADE | newer | 1088 | 64% | 66% | -0.024 [-0.124..+0.096] | -0.050 | 41% | 41% | +0.092 | 10.5% |
| small caps | pump | DIP-BUY | newer | 540 | 55% | 49% | +0.120 [-0.095..+0.318] | +0.084 | 16% | 23% | -0.269 | 6.2% |
| small caps | dump | FADE | newer | 390 | 39% | 49% | -0.309 [-0.416..-0.198] | -0.349 | 22% | 28% | -0.235 | 6.5% |
| small caps | dump | DIP-BUY | newer | 152 | 66% | 57% | +0.147 [-0.007..+0.308] | +0.115 | 21% | 27% | -0.039 | 7.2% |

## Trades by the size of the move (whole window)

| class | kind | strategy | size | trades | TP1 hit | geometry | R TP1 net | R TP2 net |
|---|---|---|---|---:|---:|---:|---:|---:|
| small caps | pump | FADE | 15-30% | 2264 | 65% | 66% | -0.046 | -0.062 |
| small caps | pump | DIP-BUY | 15-30% | 1096 | 56% | 51% | +0.084 | -0.210 |
| small caps | dump | FADE | 15-30% | 1293 | 58% | 55% | -0.040 | +0.184 |
| small caps | dump | DIP-BUY | 15-30% | 522 | 54% | 47% | +0.187 | -0.156 |
| small caps | pump | FADE | 30-60% | 195 | 63% | 63% | -0.069 | +0.126 |
| small caps | pump | FADE | 60%+ | 87 | 40% | 63% | -0.194 | -0.223 |
| small caps | pump | DIP-BUY | 60%+ | 75 | 71% | 48% | +0.242 | +0.113 |
| small caps | pump | DIP-BUY | 30-60% | 107 | 56% | 50% | +0.080 | -0.505 |
| small caps | dump | FADE | 30-60% | 69 | 50% | 48% | -0.079 | +0.041 |
| small caps | dump | DIP-BUY | 30-60% | 30 | 50% | 46% | -0.069 | -0.116 |
