# Scenario-card triggers vs the geometry of their levels (478 coins, 2024-02-16 .. 2026-09-27, 615349 trades)

Rules: the docstring of `research_level_triggers.py`. 'geometry' = the hit rate a driftless random walk gives the same entry / stop / target (risk / (risk + reward)); 'excess' = hit rate minus it (a trigger with information is > 0); R net of 0.20% round trip. [90%] = bootstrap by calendar week.

### By trigger, older / newer half

| type | half | trades | TP1 hit | geometry | excess [90%] | R TP1 net [90%] | TP2 hit | geometry TP2 | R TP2 net | median stop |
|---|---|---:|---:|---:|---|---|---:|---:|---:|---:|
| SHORT breakdown-retest | older | 132667 | 70.6% | 68.9% | +1.7 pp [-0.6..+3.8] | -0.002 [-0.044..+0.040] | 46.3% | 44.9% | +0.033 | 7.3% |
| LONG breakout-retest | older | 129007 | 69.1% | 71.2% | -2.2 pp [-4.6..+0.2] | -0.080 [-0.120..-0.040] | 42.5% | 45.6% | -0.111 | 7.4% |
| LONG rejection | older | 43210 | 67.8% | 69.8% | -2.0 pp [-4.7..+0.9] | -0.069 [-0.109..-0.025] | 48.9% | 51.8% | -0.100 | 7.9% |
| SHORT rejection | older | 42586 | 70.3% | 69.6% | +0.7 pp [-1.7..+3.2] | -0.022 [-0.061..+0.018] | 52.1% | 51.6% | -0.013 | 7.5% |
| LONG breakout-retest | newer | 96880 | 69.8% | 71.4% | -1.6 pp [-3.6..+0.3] | -0.080 [-0.112..-0.048] | 43.6% | 45.6% | -0.112 | 6.5% |
| LONG rejection | newer | 31940 | 68.3% | 69.3% | -0.9 pp [-3.6..+1.7] | -0.067 [-0.108..-0.026] | 49.2% | 51.1% | -0.105 | 6.8% |
| SHORT rejection | newer | 33526 | 72.1% | 71.2% | +1.0 pp [-1.2..+3.1] | -0.023 [-0.057..+0.009] | 53.4% | 52.7% | -0.003 | 7.1% |
| SHORT breakdown-retest | newer | 105533 | 69.3% | 68.7% | +0.5 pp [-1.5..+2.5] | -0.025 [-0.065..+0.015] | 43.9% | 44.9% | -0.001 | 6.6% |

### By the weekly trend (with / against the trade)

| type | weekly trend | trades | TP1 hit | geometry | excess [90%] | R TP1 net [90%] | TP2 hit | geometry TP2 | R TP2 net | median stop |
|---|---|---:|---:|---:|---|---|---:|---:|---:|---:|
| SHORT breakdown-retest | against | 93052 | 69.5% | 68.3% | +1.1 pp [-1.1..+3.3] | -0.008 [-0.051..+0.032] | 44.9% | 43.8% | +0.045 | 7.6% |
| LONG breakout-retest | with | 73473 | 69.8% | 72.0% | -2.3 pp [-4.8..+0.3] | -0.088 [-0.125..-0.052] | 43.6% | 46.9% | -0.139 | 7.7% |
| LONG rejection | with | 23690 | 68.9% | 70.9% | -2.0 pp [-5.0..+1.1] | -0.068 [-0.111..-0.025] | 50.0% | 53.1% | -0.108 | 8.5% |
| LONG breakout-retest | against | 152414 | 69.2% | 70.9% | -1.8 pp [-3.6..-0.1] | -0.076 [-0.107..-0.046] | 42.8% | 45.0% | -0.099 | 6.7% |
| SHORT rejection | against | 29798 | 70.6% | 69.4% | +1.3 pp [-1.1..+3.5] | -0.011 [-0.051..+0.028] | 51.6% | 51.0% | -0.002 | 7.8% |
| SHORT breakdown-retest | with | 145148 | 70.3% | 69.2% | +1.2 pp [-0.5..+2.9] | -0.015 [-0.046..+0.019] | 45.6% | 45.6% | -0.001 | 6.6% |
| SHORT rejection | with | 46314 | 71.5% | 70.9% | +0.6 pp [-1.3..+2.5] | -0.030 [-0.059..+0.000] | 53.4% | 52.8% | -0.013 | 7.0% |
| LONG rejection | against | 51460 | 67.6% | 69.0% | -1.4 pp [-3.6..+0.8] | -0.068 [-0.102..-0.035] | 48.5% | 50.8% | -0.100 | 7.0% |

### By the place in the 30-day range

| type | 30d range | trades | TP1 hit | geometry | excess [90%] | R TP1 net [90%] | TP2 hit | geometry TP2 | R TP2 net | median stop |
|---|---|---:|---:|---:|---|---|---:|---:|---:|---:|
| SHORT breakdown-retest | upper third | 42564 | 72.7% | 70.6% | +2.1 pp [-0.4..+4.8] | +0.005 [-0.036..+0.048] | 49.0% | 46.5% | +0.067 | 7.7% |
| LONG breakout-retest | upper third | 39858 | 68.0% | 70.6% | -2.6 pp [-5.5..-0.0] | -0.084 [-0.129..-0.043] | 40.8% | 44.9% | -0.142 | 7.4% |
| LONG rejection | upper third | 15960 | 67.5% | 69.8% | -2.3 pp [-5.8..+0.9] | -0.077 [-0.128..-0.029] | 48.6% | 51.8% | -0.111 | 8.2% |
| LONG breakout-retest | middle | 80886 | 66.7% | 70.0% | -3.4 pp [-5.6..-1.3] | -0.105 [-0.142..-0.067] | 40.0% | 44.6% | -0.153 | 6.9% |
| LONG breakout-retest | lower third | 105143 | 71.9% | 72.5% | -0.6 pp [-2.6..+1.3] | -0.059 [-0.090..-0.031] | 46.0% | 46.6% | -0.071 | 6.9% |
| SHORT rejection | upper third | 13292 | 68.5% | 67.4% | +1.1 pp [-1.5..+3.9] | -0.021 [-0.064..+0.024] | 52.6% | 50.0% | +0.019 | 7.2% |
| SHORT breakdown-retest | middle | 86658 | 71.0% | 69.1% | +2.0 pp [-0.1..+4.0] | +0.004 [-0.036..+0.045] | 46.9% | 44.9% | +0.066 | 7.1% |
| SHORT rejection | middle | 25784 | 73.1% | 71.3% | +1.8 pp [-0.3..+3.9] | -0.004 [-0.039..+0.031] | 56.0% | 53.3% | +0.041 | 7.8% |
| SHORT rejection | lower third | 37036 | 70.7% | 70.6% | +0.1 pp [-2.0..+2.2] | -0.035 [-0.068..-0.002] | 50.3% | 52.0% | -0.053 | 7.1% |
| LONG rejection | middle | 27718 | 67.3% | 70.3% | -3.0 pp [-5.6..-0.6] | -0.090 [-0.127..-0.053] | 47.0% | 51.5% | -0.140 | 7.5% |
| LONG rejection | lower third | 31472 | 69.0% | 68.9% | +0.1 pp [-2.4..+2.6] | -0.044 [-0.083..-0.006] | 50.9% | 51.4% | -0.065 | 7.0% |
| SHORT breakdown-retest | lower third | 108978 | 68.1% | 68.0% | +0.2 pp [-1.9..+2.2] | -0.032 [-0.070..+0.006] | 42.0% | 44.1% | -0.050 | 6.7% |

### Weekly trend x place in the range

| type | weekly trend | 30d range | trades | TP1 hit | geometry | excess [90%] | R TP1 net [90%] | TP2 hit | geometry TP2 | R TP2 net | median stop |
|---|---|---|---:|---:|---:|---|---|---:|---:|---:|---:|
| SHORT breakdown-retest | against | upper third | 19471 | 71.7% | 69.7% | +2.0 pp [-1.6..+5.7] | +0.008 [-0.052..+0.071] | 47.7% | 45.1% | +0.079 | 8.0% |
| LONG breakout-retest | with | upper third | 16268 | 70.0% | 72.6% | -2.7 pp [-6.6..+0.8] | -0.079 [-0.135..-0.029] | 45.5% | 49.0% | -0.115 | 7.8% |
| LONG rejection | with | upper third | 6343 | 68.8% | 71.4% | -2.6 pp [-7.6..+2.2] | -0.075 [-0.151..-0.008] | 51.2% | 54.6% | -0.100 | 9.0% |
| LONG breakout-retest | against | upper third | 23590 | 66.7% | 69.2% | -2.5 pp [-5.7..+0.4] | -0.088 [-0.142..-0.038] | 38.4% | 42.8% | -0.156 | 7.1% |
| LONG breakout-retest | against | middle | 53836 | 66.6% | 69.6% | -3.0 pp [-5.1..-1.0] | -0.095 [-0.136..-0.054] | 40.2% | 43.9% | -0.128 | 6.6% |
| LONG breakout-retest | with | lower third | 30155 | 72.3% | 72.8% | -0.5 pp [-3.6..+2.2] | -0.061 [-0.105..-0.023] | 46.4% | 47.0% | -0.090 | 7.8% |
| LONG breakout-retest | with | middle | 27050 | 66.9% | 70.9% | -4.0 pp [-7.7..-0.3] | -0.123 [-0.178..-0.068] | 39.6% | 45.9% | -0.203 | 7.5% |
| SHORT rejection | against | upper third | 6506 | 65.8% | 65.5% | +0.3 pp [-2.7..+3.5] | -0.034 [-0.087..+0.022] | 49.4% | 47.8% | +0.002 | 7.0% |
| SHORT breakdown-retest | against | middle | 34149 | 70.9% | 68.7% | +2.2 pp [-0.9..+5.0] | +0.017 [-0.042..+0.077] | 47.5% | 44.0% | +0.122 | 7.6% |
| SHORT breakdown-retest | with | upper third | 23093 | 73.5% | 71.3% | +2.2 pp [-0.4..+4.8] | +0.003 [-0.039..+0.042] | 50.1% | 47.6% | +0.057 | 7.4% |
| SHORT rejection | with | middle | 15559 | 73.0% | 71.6% | +1.4 pp [-0.9..+3.7] | -0.015 [-0.050..+0.022] | 55.5% | 53.5% | +0.021 | 7.4% |
| SHORT rejection | against | lower third | 13067 | 71.0% | 70.1% | +0.9 pp [-1.9..+3.5] | -0.017 [-0.061..+0.025] | 48.6% | 51.2% | -0.061 | 7.8% |
| SHORT rejection | with | upper third | 6786 | 71.2% | 69.3% | +1.9 pp [-1.3..+5.0] | -0.009 [-0.063..+0.040] | 55.9% | 52.2% | +0.036 | 7.3% |
| SHORT breakdown-retest | with | middle | 52509 | 71.1% | 69.3% | +1.8 pp [-0.5..+4.0] | -0.004 [-0.049..+0.040] | 46.5% | 45.4% | +0.029 | 6.8% |
| LONG rejection | with | middle | 8843 | 66.7% | 71.0% | -4.3 pp [-8.1..-0.4] | -0.104 [-0.154..-0.051] | 45.9% | 52.2% | -0.178 | 8.3% |
| SHORT rejection | against | middle | 10225 | 73.3% | 70.9% | +2.4 pp [-1.1..+5.7] | +0.011 [-0.049..+0.071] | 56.8% | 53.0% | +0.070 | 8.4% |
| LONG rejection | against | upper third | 9617 | 66.6% | 68.7% | -2.1 pp [-5.9..+1.5] | -0.078 [-0.135..-0.021] | 46.8% | 50.0% | -0.119 | 7.7% |
| LONG rejection | against | middle | 18875 | 67.5% | 70.0% | -2.5 pp [-5.1..+0.2] | -0.084 [-0.123..-0.044] | 47.5% | 51.2% | -0.123 | 7.1% |
| LONG rejection | with | lower third | 8504 | 71.3% | 70.4% | +0.9 pp [-2.3..+4.1] | -0.026 [-0.076..+0.023] | 53.4% | 52.9% | -0.041 | 8.2% |
| SHORT breakdown-retest | against | lower third | 39432 | 67.2% | 67.3% | -0.2 pp [-2.8..+2.6] | -0.039 [-0.087..+0.013] | 40.8% | 42.8% | -0.045 | 7.3% |
| SHORT breakdown-retest | with | lower third | 69546 | 68.7% | 68.4% | +0.3 pp [-1.8..+2.5] | -0.028 [-0.070..+0.013] | 42.8% | 44.9% | -0.054 | 6.4% |
| LONG breakout-retest | against | lower third | 74988 | 71.8% | 72.4% | -0.6 pp [-2.7..+1.3] | -0.058 [-0.091..-0.028] | 45.8% | 46.4% | -0.064 | 6.6% |
| SHORT rejection | with | lower third | 23969 | 70.5% | 70.9% | -0.4 pp [-2.8..+2.0] | -0.045 [-0.083..-0.009] | 51.3% | 52.5% | -0.049 | 6.8% |
| LONG rejection | against | lower third | 22968 | 68.1% | 68.3% | -0.2 pp [-2.8..+2.6] | -0.051 [-0.092..-0.007] | 50.0% | 50.8% | -0.074 | 6.6% |

