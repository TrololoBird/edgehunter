# Scenario-card triggers vs the geometry of their levels (478 coins, 2024-01-12 .. 2026-08-30, 771827 trades)

Rules: the docstring of `research_level_triggers.py`. 'geometry' = the hit rate a driftless random walk gives the same entry / stop / target (risk / (risk + reward)); 'excess' = hit rate minus it (a trigger with information is > 0); R net of 0.20% round trip. [90%] = bootstrap by calendar week.

### By trigger, older / newer half

| type | half | trades | TP1 hit | geometry | excess [90%] | R TP1 net [90%] | TP2 hit | geometry TP2 | R TP2 net | median stop |
|---|---|---:|---:|---:|---|---|---:|---:|---:|---:|
| SHORT breakdown-retest | older | 151222 | 69.0% | 67.0% | +2.0 pp [+0.0..+4.0] | -0.017 [-0.053..+0.018] | 45.6% | 43.3% | +0.015 | 4.8% |
| LONG breakout-retest | older | 149797 | 63.8% | 66.7% | -3.0 pp [-5.0..-0.9] | -0.108 [-0.143..-0.074] | 38.8% | 41.9% | -0.133 | 4.7% |
| SHORT rejection | older | 59171 | 72.0% | 71.3% | +0.7 pp [-1.1..+2.6] | -0.039 [-0.066..-0.008] | 53.3% | 52.0% | -0.024 | 5.3% |
| LONG rejection | older | 66168 | 68.9% | 71.2% | -2.3 pp [-4.5..-0.2] | -0.086 [-0.118..-0.054] | 47.9% | 51.2% | -0.123 | 5.3% |
| SHORT breakdown-retest | newer | 126643 | 67.5% | 66.6% | +0.9 pp [-0.9..+2.6] | -0.056 [-0.090..-0.023] | 43.2% | 42.4% | -0.033 | 4.5% |
| LONG breakout-retest | newer | 119946 | 64.7% | 66.8% | -2.1 pp [-3.9..-0.1] | -0.111 [-0.143..-0.076] | 39.6% | 42.1% | -0.149 | 4.3% |
| SHORT rejection | newer | 47907 | 72.6% | 72.1% | +0.5 pp [-1.2..+2.0] | -0.051 [-0.078..-0.026] | 53.2% | 52.3% | -0.038 | 5.0% |
| LONG rejection | newer | 50973 | 69.0% | 71.0% | -2.0 pp [-3.9..+0.1] | -0.093 [-0.122..-0.061] | 48.4% | 51.1% | -0.134 | 4.8% |

### By the weekly trend (with / against the trade)

| type | weekly trend | trades | TP1 hit | geometry | excess [90%] | R TP1 net [90%] | TP2 hit | geometry TP2 | R TP2 net | median stop |
|---|---|---:|---:|---:|---|---|---:|---:|---:|---:|
| SHORT breakdown-retest | against | 112829 | 68.2% | 66.8% | +1.4 pp [-0.4..+3.3] | -0.037 [-0.072..-0.002] | 44.7% | 42.6% | +0.005 | 5.0% |
| LONG breakout-retest | against | 179600 | 64.3% | 66.6% | -2.3 pp [-3.9..-0.8] | -0.105 [-0.132..-0.078] | 39.4% | 41.8% | -0.129 | 4.4% |
| LONG breakout-retest | with | 90143 | 64.1% | 67.1% | -3.0 pp [-5.2..-0.9] | -0.118 [-0.153..-0.085] | 38.7% | 42.3% | -0.163 | 4.7% |
| SHORT rejection | against | 43192 | 72.6% | 71.3% | +1.3 pp [-0.6..+3.1] | -0.031 [-0.060..-0.001] | 53.1% | 51.8% | -0.020 | 5.4% |
| LONG rejection | with | 39412 | 69.7% | 71.6% | -1.9 pp [-4.0..+0.1] | -0.085 [-0.115..-0.055] | 48.8% | 51.8% | -0.124 | 5.6% |
| SHORT breakdown-retest | with | 165036 | 68.4% | 66.9% | +1.5 pp [+0.1..+2.9] | -0.034 [-0.061..-0.006] | 44.5% | 43.1% | -0.016 | 4.5% |
| LONG rejection | against | 77729 | 68.5% | 70.9% | -2.3 pp [-4.0..-0.6] | -0.092 [-0.117..-0.065] | 47.8% | 50.8% | -0.130 | 4.9% |
| SHORT rejection | with | 63886 | 72.0% | 71.9% | +0.1 pp [-1.2..+1.5] | -0.053 [-0.075..-0.031] | 53.3% | 52.4% | -0.038 | 4.9% |

### By the place in the 30-day range

| type | 30d range | trades | TP1 hit | geometry | excess [90%] | R TP1 net [90%] | TP2 hit | geometry TP2 | R TP2 net | median stop |
|---|---|---:|---:|---:|---|---|---:|---:|---:|---:|
| SHORT breakdown-retest | middle | 97029 | 69.2% | 67.2% | +2.0 pp [+0.3..+3.7] | -0.021 [-0.053..+0.011] | 45.5% | 42.9% | +0.029 | 4.7% |
| LONG breakout-retest | middle | 92565 | 62.2% | 65.9% | -3.6 pp [-5.4..-2.0] | -0.132 [-0.163..-0.102] | 36.6% | 40.9% | -0.172 | 4.5% |
| LONG breakout-retest | upper third | 46456 | 63.7% | 66.8% | -3.1 pp [-5.4..-0.9] | -0.114 [-0.158..-0.075] | 38.6% | 42.0% | -0.156 | 5.1% |
| LONG breakout-retest | lower third | 130722 | 65.8% | 67.4% | -1.6 pp [-3.4..+0.2] | -0.091 [-0.120..-0.061] | 41.1% | 42.7% | -0.113 | 4.4% |
| SHORT rejection | middle | 35185 | 73.9% | 72.8% | +1.1 pp [-0.3..+2.7] | -0.037 [-0.061..-0.012] | 56.1% | 53.6% | +0.001 | 5.4% |
| SHORT breakdown-retest | lower third | 132376 | 67.0% | 66.1% | +1.0 pp [-0.8..+2.5] | -0.049 [-0.081..-0.019] | 42.7% | 42.2% | -0.050 | 4.4% |
| SHORT breakdown-retest | upper third | 48460 | 69.9% | 68.1% | +1.8 pp [-0.4..+4.1] | -0.024 [-0.060..+0.012] | 47.0% | 44.6% | +0.026 | 5.3% |
| LONG rejection | upper third | 22796 | 67.7% | 70.8% | -3.1 pp [-5.6..-0.8] | -0.102 [-0.143..-0.065] | 46.7% | 50.7% | -0.143 | 5.8% |
| LONG rejection | middle | 41158 | 68.6% | 71.4% | -2.9 pp [-4.8..-0.9] | -0.100 [-0.129..-0.072] | 47.0% | 51.1% | -0.148 | 5.2% |
| SHORT rejection | upper third | 18747 | 71.6% | 70.6% | +1.0 pp [-1.2..+3.3] | -0.041 [-0.076..-0.005] | 53.9% | 51.5% | -0.005 | 5.6% |
| SHORT rejection | lower third | 53146 | 71.4% | 71.3% | +0.1 pp [-1.6..+1.8] | -0.050 [-0.076..-0.023] | 51.2% | 51.4% | -0.060 | 4.9% |
| LONG rejection | lower third | 53187 | 69.7% | 71.1% | -1.3 pp [-3.1..+0.4] | -0.076 [-0.102..-0.049] | 49.6% | 51.4% | -0.105 | 4.8% |

### Weekly trend x place in the range

| type | weekly trend | 30d range | trades | TP1 hit | geometry | excess [90%] | R TP1 net [90%] | TP2 hit | geometry TP2 | R TP2 net | median stop |
|---|---|---|---:|---:|---:|---|---|---:|---:|---:|---:|
| SHORT breakdown-retest | against | middle | 40264 | 69.2% | 67.0% | +2.2 pp [-0.4..+4.8] | -0.014 [-0.062..+0.036] | 46.2% | 42.6% | +0.061 | 5.0% |
| LONG breakout-retest | against | middle | 60304 | 62.5% | 65.7% | -3.2 pp [-4.8..-1.5] | -0.123 [-0.156..-0.090] | 37.1% | 40.6% | -0.152 | 4.3% |
| LONG breakout-retest | with | upper third | 19877 | 64.7% | 67.8% | -3.1 pp [-6.5..-0.0] | -0.111 [-0.165..-0.061] | 40.8% | 43.9% | -0.133 | 5.2% |
| LONG breakout-retest | with | middle | 32261 | 61.7% | 66.2% | -4.5 pp [-7.5..-1.7] | -0.147 [-0.192..-0.103] | 35.7% | 41.3% | -0.211 | 4.7% |
| LONG breakout-retest | with | lower third | 38005 | 65.7% | 67.4% | -1.7 pp [-4.3..+0.8] | -0.097 [-0.138..-0.054] | 40.4% | 42.5% | -0.135 | 4.6% |
| SHORT rejection | against | middle | 14500 | 75.0% | 72.6% | +2.4 pp [+0.1..+4.9] | -0.013 [-0.049..+0.026] | 56.7% | 53.3% | +0.027 | 5.6% |
| SHORT breakdown-retest | against | lower third | 49147 | 66.9% | 66.0% | +0.9 pp [-1.1..+3.0] | -0.057 [-0.097..-0.018] | 42.5% | 41.8% | -0.050 | 4.8% |
| SHORT breakdown-retest | against | upper third | 23418 | 68.9% | 67.7% | +1.2 pp [-1.9..+4.2] | -0.034 [-0.086..+0.017] | 46.4% | 44.1% | +0.021 | 5.5% |
| LONG rejection | with | upper third | 9760 | 69.0% | 71.4% | -2.4 pp [-5.7..+0.6] | -0.089 [-0.141..-0.043] | 48.5% | 51.9% | -0.122 | 6.1% |
| LONG rejection | with | middle | 14224 | 68.3% | 71.6% | -3.3 pp [-6.1..-0.4] | -0.105 [-0.145..-0.064] | 46.2% | 51.3% | -0.166 | 5.5% |
| SHORT breakdown-retest | with | middle | 56765 | 69.1% | 67.3% | +1.9 pp [+0.0..+3.6] | -0.026 [-0.060..+0.009] | 45.1% | 43.1% | +0.007 | 4.5% |
| LONG breakout-retest | against | upper third | 26579 | 63.0% | 66.1% | -3.1 pp [-5.8..-0.8] | -0.116 [-0.170..-0.069] | 37.1% | 40.8% | -0.171 | 5.0% |
| SHORT rejection | against | upper third | 9441 | 69.9% | 69.5% | +0.4 pp [-2.4..+3.4] | -0.050 [-0.097..-0.001] | 51.6% | 50.1% | -0.022 | 5.5% |
| SHORT rejection | against | lower third | 19251 | 72.1% | 71.3% | +0.8 pp [-1.5..+3.1] | -0.035 [-0.070..+0.002] | 51.2% | 51.4% | -0.053 | 5.2% |
| LONG rejection | against | middle | 26934 | 68.7% | 71.3% | -2.6 pp [-4.8..-0.5] | -0.097 [-0.130..-0.066] | 47.4% | 50.9% | -0.139 | 5.0% |
| LONG rejection | with | lower third | 15428 | 71.5% | 71.9% | -0.4 pp [-2.6..+1.8] | -0.063 [-0.099..-0.029] | 51.3% | 52.1% | -0.085 | 5.3% |
| SHORT rejection | with | middle | 20685 | 73.2% | 72.9% | +0.2 pp [-1.3..+1.9] | -0.054 [-0.078..-0.027] | 55.6% | 53.8% | -0.017 | 5.2% |
| SHORT rejection | with | upper third | 9306 | 73.3% | 71.8% | +1.5 pp [-0.7..+3.9] | -0.032 [-0.066..+0.004] | 56.4% | 53.0% | +0.012 | 5.6% |
| LONG rejection | against | upper third | 13036 | 66.8% | 70.3% | -3.5 pp [-6.2..-1.1] | -0.112 [-0.158..-0.073] | 45.4% | 49.9% | -0.158 | 5.6% |
| LONG rejection | against | lower third | 37759 | 69.0% | 70.8% | -1.7 pp [-3.7..+0.3] | -0.081 [-0.110..-0.050] | 48.9% | 51.1% | -0.113 | 4.6% |
| SHORT breakdown-retest | with | upper third | 25042 | 70.9% | 68.4% | +2.5 pp [+0.2..+4.7] | -0.016 [-0.054..+0.022] | 47.7% | 45.1% | +0.031 | 5.1% |
| SHORT breakdown-retest | with | lower third | 83229 | 67.1% | 66.1% | +1.0 pp [-0.9..+2.8] | -0.044 [-0.078..-0.011] | 42.9% | 42.5% | -0.049 | 4.2% |
| LONG breakout-retest | against | lower third | 92717 | 65.8% | 67.4% | -1.6 pp [-3.6..+0.4] | -0.089 [-0.122..-0.056] | 41.4% | 42.8% | -0.104 | 4.3% |
| SHORT rejection | with | lower third | 33895 | 71.0% | 71.3% | -0.3 pp [-2.1..+1.5] | -0.059 [-0.086..-0.031] | 51.1% | 51.5% | -0.064 | 4.7% |

