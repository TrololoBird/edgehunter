# Session opens and leaders (2025-10-01 .. 2026-09-30, 5m archive)

## Part 1: the first 30 / 60 min after each open (sum of 5m log returns, %)

| open | series | n | mean 30m | P(down) 30m | mean abs 30m | abs vs other times | mean 60m | P(down) 60m |
|---|---|---|---|---|---|---|---|---|
| Tokyo 00:00 UTC | BTC | 364 | -0.011 | 0.50 | 0.231 | 1.06x | +0.006 | 0.49 |
| Tokyo 00:00 UTC | ALTS median | 364 | -0.035 | 0.52 | 0.336 | 0.96x | -0.015 | 0.49 |
| London 08:00 | BTC | 261 | -0.007 | 0.50 | 0.203 | 0.93x | -0.026 | 0.56 |
| London 08:00 | ALTS median | 261 | -0.005 | 0.52 | 0.295 | 0.88x | -0.037 | 0.52 |
| NY 08:30 (macro) | BTC | 261 | -0.004 | 0.49 | 0.294 | 1.35x | -0.031 | 0.56 |
| NY 08:30 (macro) | ALTS median | 261 | -0.013 | 0.52 | 0.394 | 1.13x | -0.037 | 0.54 |
| NY 09:30 (cash open) | BTC | 261 | -0.024 | 0.51 | 0.526 | 2.47x | -0.044 | 0.52 |
| NY 09:30 (cash open) | ALTS median | 261 | +0.037 | 0.47 | 0.611 | 1.83x | -0.065 | 0.52 |
| placebo random minute | BTC | 400 | +0.013 | 0.47 | 0.204 | 0.96x | +0.011 | 0.52 |
| placebo random minute | ALTS median | 400 | +0.007 | 0.54 | 0.320 | 0.99x | +0.009 | 0.50 |

## Part 2: does the leader move first? (alt median 5m return)

| leader | bars of data | corr lag 0 | lag 1 | lag 2 | lag 3 | events (|15m| > 2.5 sd) | alts next 15m in its direction | next 60m | unconditional 15m |
|---|---|---|---|---|---|---|---|---|---|
| BTCUSDT | 105119 | 0.722 | 0.009 | -0.019 | -0.025 | 1082 | -0.044% | +0.029% | |abs| 0.240% |
| ETHUSDT | 105119 | 0.714 | 0.030 | -0.025 | -0.025 | 1087 | -0.044% | -0.028% | |abs| 0.240% |
| XAUUSDT | 84574 | 0.218 | 0.002 | 0.010 | 0.002 | 753 | +0.023% | +0.001% | |abs| 0.240% |
| CLUSDT | 52595 | -0.185 | -0.011 | -0.008 | -0.009 | 516 | -0.016% | -0.022% | |abs| 0.240% |

Reading: lag 0 = they move in the same 5 minutes; a leader LEADS only if lag 1+ correlations and the next-15m / 60m continuation are clearly above 0 (vs the cost of acting on it, ~0.1-0.2%).
