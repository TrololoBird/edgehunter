# Pumps / dumps and what follows (478 coins, 2021-04-17 .. 2023-09-21)

Rules: the docstring of `research_pumps.py` (pre-registered). 'fwd' = the return in the move's direction minus the universe mean (so negative = reversal).

## What follows the event

| class | kind | half | events | back to 50% before a new extreme | back to the base | fwd 6h | fwd 24h | fwd 72h |
|---|---|---|---:|---:|---:|---:|---:|---:|
| small caps | pump | older | 914 | 78% | 35% | -0.10% | -0.85% | -0.59% |
| majors | pump | older | 25 | 68% | 17% | -0.80% | -1.79% | +1.03% |
| small caps | dump | older | 257 | 65% | 26% | +0.41% | -0.54% | +0.18% |
| majors | dump | older | 9 | 67% | 33% | -0.54% | -0.97% | -5.86% |
| small caps | pump | newer | 462 | 73% | 36% | -0.62% | -1.02% | -1.28% |
| small caps | dump | newer | 235 | 41% | 10% | -0.04% | +0.24% | +0.80% |
| majors | dump | newer | 4 | 75% | 75% | -7.14% | -5.79% | -6.11% |
| majors | pump | newer | 8 | 100% | 50% | +5.10% | +5.50% | +6.11% |

## Trades

| class | kind | strategy | half | trades | TP1 hit | geometry | R TP1 net 0.20% [90%] | R TP1 at 0.40% | TP2 hit | geometry TP2 | R TP2 net | median stop |
|---|---|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| small caps | pump | FADE | older | 913 | 70% | 66% | +0.020 [-0.066..+0.107] | -0.005 | 35% | 37% | -0.070 | 8.7% |
| small caps | pump | DIP-BUY | older | 529 | 50% | 52% | -0.042 [-0.161..+0.069] | -0.078 | 14% | 25% | -0.402 | 6.4% |
| majors | pump | FADE | older | 25 | 52% | 59% | -0.116 [-0.541..+0.311] | -0.147 | 4% | 32% | -0.907 | 7.3% |
| small caps | dump | FADE | older | 256 | 51% | 52% | -0.046 [-0.251..+0.205] | -0.079 | 27% | 30% | -0.020 | 6.7% |
| small caps | dump | DIP-BUY | older | 100 | 69% | 52% | +0.356 [+0.150..+0.547] | +0.320 | 23% | 26% | -0.019 | 6.7% |
| small caps | pump | FADE | newer | 459 | 57% | 63% | -0.159 [-0.275..-0.039] | -0.192 | 38% | 37% | -0.042 | 8.1% |
| small caps | pump | DIP-BUY | newer | 218 | 51% | 48% | +0.133 [-0.019..+0.294] | +0.088 | 18% | 23% | -0.138 | 4.8% |
| small caps | dump | FADE | newer | 231 | 35% | 45% | -0.212 [-0.601..+0.183] | -0.255 | 12% | 25% | -0.228 | 4.9% |
| small caps | dump | DIP-BUY | newer | 86 | 62% | 45% | +0.340 [-0.339..+0.854] | +0.291 | 24% | 20% | +0.482 | 5.2% |
