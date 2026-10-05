# Exit overlays and the alts-vs-BTC filter (research_overlays.py, pre-registered)

32515 trade x base rows; train < 2026-06-01 <= validation. Difference = overlay R - base R on the same trades.

| strategy | base | overlay | train: n, diff [lower 90%] | validation: n, diff | verdict |
|---|---|---|---|---|---|
| bollinger | plan | noprog_2 | 4826, -0.011 [-0.039] | 2795, -0.002 | no |
| bollinger | plan | noprog_4 | 4826, -0.008 [-0.021] | 2795, -0.010 | no |
| bollinger | plan | noprog_8 | 4826, -0.002 [-0.006] | 2795, +0.001 | no |
| bollinger | plan | struct | 4826, -0.076 [-0.162] | 2795, -0.075 | no |
| bollinger | plan | btc_0.7 | 4826, -0.028 [-0.154] | 2795, -0.198 | no |
| bollinger | plan | btc_1.0 | 4826, +0.058 [-0.018] | 2795, -0.075 | no |
| bollinger | plan | btc_1.5 | 4826, +0.051 [-0.013] | 2795, -0.055 | no |
| bollinger | plan | noprog_4+btc_1.0 | 4826, +0.046 [-0.030] | 2795, -0.091 | no |
| bollinger | plan | filter:alts_with | 1209, -0.090 [-0.364] | 805, -0.471 | no |
| bollinger | profile | noprog_2 | 4826, -0.007 [-0.018] | 2795, +0.006 | no |
| bollinger | profile | noprog_4 | 4826, -0.005 [-0.009] | 2795, -0.000 | no |
| bollinger | profile | noprog_8 | 4826, -0.001 [-0.002] | 2795, -0.000 | no |
| bollinger | profile | struct | 4826, -0.384 [-0.448] | 2795, -0.288 | no |
| bollinger | profile | btc_0.7 | 4826, -0.027 [-0.095] | 2795, +0.105 | no |
| bollinger | profile | btc_1.0 | 4826, +0.049 [-0.128] | 2795, -0.009 | no |
| bollinger | profile | btc_1.5 | 4826, +0.055 [-0.117] | 2795, +0.045 | no |
| bollinger | profile | noprog_4+btc_1.0 | 4826, +0.039 [-0.135] | 2795, -0.013 | no |
| bollinger | profile | filter:alts_with | 1209, +0.017 [-0.203] | 805, -0.436 | no |
| connors | plan | noprog_2 | 136, +0.034 [-0.079] | 77, +0.108 | no |
| connors | plan | noprog_4 | 136, +0.030 [-0.076] | 77, +0.099 | no |
| connors | plan | noprog_8 | 136, +0.025 [-0.074] | 77, +0.065 | no |
| connors | plan | struct | 136, +0.027 [+0.007] | 77, +0.074 | ADOPT |
| connors | plan | btc_0.7 | 136, -0.028 [-0.109] | 77, +0.094 | no |
| connors | plan | btc_1.0 | 136, -0.012 [-0.052] | 77, +0.149 | no |
| connors | plan | btc_1.5 | 136, -0.003 [-0.013] | 77, +0.096 | no |
| connors | plan | noprog_4+btc_1.0 | 136, +0.031 [-0.075] | 77, +0.120 | no |
| connors | plan | filter:alts_with | 70, +0.154 [+0.016] | 46, +0.161 | ADOPT |
| connors | profile | noprog_2 | 136, +0.001 [-0.018] | 77, +0.009 | no |
| connors | profile | noprog_4 | 136, +0.000 [+0.000] | 77, +0.000 | no |
| connors | profile | noprog_8 | 136, -0.008 [-0.040] | 77, -0.047 | no |
| connors | profile | struct | 136, -0.127 [-0.181] | 77, -0.139 | no |
| connors | profile | btc_0.7 | 136, -0.032 [-0.075] | 77, -0.035 | no |
| connors | profile | btc_1.0 | 136, -0.047 [-0.110] | 77, +0.000 | no |
| connors | profile | btc_1.5 | 136, -0.016 [-0.034] | 77, -0.056 | no |
| connors | profile | noprog_4+btc_1.0 | 136, -0.003 [-0.010] | 77, +0.011 | no |
| connors | profile | filter:alts_with | 70, +0.005 [-0.032] | 46, +0.016 | no |
| trendline | plan | noprog_2 | 219, +0.016 [+0.005] | 115, +0.025 | ADOPT |
| trendline | plan | noprog_4 | 219, +0.006 [-0.001] | 115, -0.005 | no |
| trendline | plan | noprog_8 | 219, +0.004 [-0.001] | 115, +0.000 | no |
| trendline | plan | struct | 219, +0.060 [+0.006] | 115, -0.052 | no |
| trendline | plan | btc_0.7 | 219, -0.014 [-0.066] | 115, -0.073 | no |
| trendline | plan | btc_1.0 | 219, -0.031 [-0.074] | 115, -0.077 | no |
| trendline | plan | btc_1.5 | 219, -0.001 [-0.005] | 115, -0.037 | no |
| trendline | plan | noprog_4+btc_1.0 | 219, -0.025 [-0.068] | 115, -0.082 | no |
| trendline | plan | filter:alts_with | 103, -0.181 [-0.445] | 62, +0.053 | no |
| trendline | profile | noprog_2 | 219, +0.002 [-0.005] | 115, +0.001 | no |
| trendline | profile | noprog_4 | 219, +0.000 [+0.000] | 115, +0.000 | no |
| trendline | profile | noprog_8 | 219, -0.003 [-0.006] | 115, +0.000 | no |
| trendline | profile | struct | 219, -0.012 [-0.064] | 115, -0.016 | no |
| trendline | profile | btc_0.7 | 219, -0.031 [-0.066] | 115, -0.067 | no |
| trendline | profile | btc_1.0 | 219, -0.030 [-0.060] | 115, -0.028 | no |
| trendline | profile | btc_1.5 | 219, -0.020 [-0.041] | 115, -0.008 | no |
| trendline | profile | noprog_4+btc_1.0 | 219, -0.028 [-0.058] | 115, -0.028 | no |
| trendline | profile | filter:alts_with | 103, -0.031 [-0.241] | 62, -0.005 | no |
| sweep | plan | noprog_2 | 1020, +0.023 [-0.004] | 564, +0.035 | no |
| sweep | plan | noprog_4 | 1020, +0.022 [+0.002] | 564, +0.018 | ADOPT |
| sweep | plan | noprog_8 | 1020, +0.007 [-0.006] | 564, +0.008 | no |
| sweep | plan | struct | 1020, -0.019 [-0.051] | 564, +0.002 | no |
| sweep | plan | btc_0.7 | 1020, +0.006 [-0.019] | 564, +0.001 | no |
| sweep | plan | btc_1.0 | 1020, +0.008 [-0.006] | 564, -0.007 | no |
| sweep | plan | btc_1.5 | 1020, +0.005 [-0.003] | 564, -0.001 | no |
| sweep | plan | noprog_4+btc_1.0 | 1020, +0.026 [+0.002] | 564, +0.008 | ADOPT |
| sweep | plan | filter:alts_with | 394, +0.028 [-0.060] | 213, -0.043 | no |
| sweep | profile | noprog_2 | 1020, -0.028 [-0.056] | 564, +0.005 | no |
| sweep | profile | noprog_4 | 1020, -0.009 [-0.033] | 564, -0.001 | no |
| sweep | profile | noprog_8 | 1020, +0.001 [-0.013] | 564, +0.000 | no |
| sweep | profile | struct | 1020, -0.013 [-0.035] | 564, -0.023 | no |
| sweep | profile | btc_0.7 | 1020, -0.007 [-0.027] | 564, +0.031 | no |
| sweep | profile | btc_1.0 | 1020, -0.006 [-0.020] | 564, +0.008 | no |
| sweep | profile | btc_1.5 | 1020, +0.002 [-0.004] | 564, +0.002 | no |
| sweep | profile | noprog_4+btc_1.0 | 1020, -0.011 [-0.036] | 564, -0.002 | no |
| sweep | profile | filter:alts_with | 394, -0.035 [-0.099] | 213, -0.009 | no |
| market_profile | plan | noprog_2 | 2173, +0.007 [-0.019] | 1014, +0.005 | no |
| market_profile | plan | noprog_4 | 2173, +0.007 [-0.012] | 1014, -0.020 | no |
| market_profile | plan | noprog_8 | 2173, -0.001 [-0.011] | 1014, -0.014 | no |
| market_profile | plan | struct | 2173, +0.011 [-0.020] | 1014, +0.006 | no |
| market_profile | plan | btc_0.7 | 2173, +0.046 [+0.015] | 1014, +0.010 | ADOPT |
| market_profile | plan | btc_1.0 | 2173, +0.025 [-0.005] | 1014, +0.001 | no |
| market_profile | plan | btc_1.5 | 2173, +0.024 [+0.006] | 1014, +0.003 | ADOPT |
| market_profile | plan | noprog_4+btc_1.0 | 2173, +0.035 [-0.000] | 1014, -0.018 | no |
| market_profile | plan | filter:alts_with | 1502, +0.033 [-0.052] | 656, -0.012 | no |
| market_profile | profile | noprog_2 | 2173, -0.005 [-0.042] | 1014, +0.035 | no |
| market_profile | profile | noprog_4 | 2173, -0.002 [-0.031] | 1014, -0.001 | no |
| market_profile | profile | noprog_8 | 2173, -0.010 [-0.027] | 1014, -0.002 | no |
| market_profile | profile | struct | 2173, -0.002 [-0.048] | 1014, -0.027 | no |
| market_profile | profile | btc_0.7 | 2173, +0.003 [-0.040] | 1014, -0.073 | no |
| market_profile | profile | btc_1.0 | 2173, -0.020 [-0.051] | 1014, -0.025 | no |
| market_profile | profile | btc_1.5 | 2173, +0.001 [-0.011] | 1014, -0.002 | no |
| market_profile | profile | noprog_4+btc_1.0 | 2173, -0.009 [-0.048] | 1014, -0.019 | no |
| market_profile | profile | filter:alts_with | 1502, +0.058 [-0.067] | 656, -0.003 | no |
| breakout | plan | noprog_2 | 368, -0.035 [-0.094] | 234, -0.073 | no |
| breakout | plan | noprog_4 | 368, -0.042 [-0.092] | 234, -0.040 | no |
| breakout | plan | noprog_8 | 368, -0.032 [-0.077] | 234, -0.014 | no |
| breakout | plan | struct | 368, +0.005 [-0.011] | 234, +0.013 | no |
| breakout | plan | btc_0.7 | 368, +0.027 [-0.096] | 234, -0.117 | no |
| breakout | plan | btc_1.0 | 368, +0.074 [-0.048] | 234, -0.051 | no |
| breakout | plan | btc_1.5 | 368, +0.073 [-0.047] | 234, -0.071 | no |
| breakout | plan | noprog_4+btc_1.0 | 368, +0.052 [-0.072] | 234, -0.077 | no |
| breakout | plan | filter:alts_with | 257, -0.053 [-0.144] | 149, -0.166 | no |
| pump | plan | noprog_2 | 345, -0.022 [-0.075] | 104, +0.010 | no |
| pump | plan | noprog_4 | 345, -0.009 [-0.048] | 104, +0.000 | no |
| pump | plan | noprog_8 | 345, +0.018 [-0.018] | 104, -0.006 | no |
| pump | plan | struct | 345, +0.004 [-0.044] | 104, -0.017 | no |
| pump | plan | btc_0.7 | 345, -0.005 [-0.052] | 104, -0.032 | no |
| pump | plan | btc_1.0 | 345, -0.005 [-0.039] | 104, -0.016 | no |
| pump | plan | btc_1.5 | 345, +0.009 [-0.003] | 104, -0.005 | no |
| pump | plan | noprog_4+btc_1.0 | 345, +0.000 [-0.045] | 104, +0.005 | no |
| pump | plan | filter:alts_with | 194, -0.046 [-0.166] | 54, +0.008 | no |
| pump | profile | noprog_2 | 345, +0.019 [-0.063] | 104, +0.014 | no |
| pump | profile | noprog_4 | 345, -0.007 [-0.083] | 104, +0.010 | no |
| pump | profile | noprog_8 | 345, +0.013 [-0.047] | 104, +0.051 | no |
| pump | profile | struct | 345, +0.008 [-0.071] | 104, +0.051 | no |
| pump | profile | btc_0.7 | 345, +0.003 [-0.095] | 104, +0.002 | no |
| pump | profile | btc_1.0 | 345, -0.037 [-0.107] | 104, +0.065 | no |
| pump | profile | btc_1.5 | 345, +0.005 [-0.021] | 104, -0.003 | no |
| pump | profile | noprog_4+btc_1.0 | 345, +0.003 [-0.086] | 104, +0.056 | no |
| pump | profile | filter:alts_with | 194, +0.045 [-0.167] | 54, -0.089 | no |
| supply_demand | plan | noprog_2 | 83, -0.029 [-0.116] | 31, -0.035 | no |
| supply_demand | plan | noprog_4 | 83, +0.041 [-0.009] | 31, +0.026 | no |
| supply_demand | plan | noprog_8 | 83, +0.004 [-0.030] | 31, +0.000 | no |
| supply_demand | plan | struct | 83, +0.038 [-0.029] | 31, +0.035 | no |
| supply_demand | plan | btc_0.7 | 83, +0.037 [-0.015] | 31, +0.024 | no |
| supply_demand | plan | btc_1.0 | 83, +0.023 [-0.012] | 31, +0.000 | no |
| supply_demand | plan | btc_1.5 | 83, +0.004 [-0.029] | 31, +0.000 | no |
| supply_demand | plan | noprog_4+btc_1.0 | 83, +0.078 [+0.023] | 31, +0.026 | ADOPT |
| supply_demand | plan | filter:alts_with | 17, +0.317 [+0.043] | 3, -0.310 | no |
| supply_demand | profile | noprog_2 | 83, -0.095 [-0.251] | 31, -0.035 | no |
| supply_demand | profile | noprog_4 | 83, +0.036 [-0.073] | 31, -0.121 | no |
| supply_demand | profile | noprog_8 | 83, -0.036 [-0.122] | 31, -0.144 | no |
| supply_demand | profile | struct | 83, -0.150 [-0.484] | 31, -0.051 | no |
| supply_demand | profile | btc_0.7 | 83, -0.409 [-0.852] | 31, -0.141 | no |
| supply_demand | profile | btc_1.0 | 83, +0.251 [-0.132] | 31, -0.038 | no |
| supply_demand | profile | btc_1.5 | 83, +0.250 [-0.114] | 31, +0.089 | no |
| supply_demand | profile | noprog_4+btc_1.0 | 83, +0.323 [-0.053] | 31, -0.079 | no |
| supply_demand | profile | filter:alts_with | 17, +1.471 [-1.114] | 3, -0.409 | no |
| continuation | plan | noprog_2 | 1895, -0.011 [-0.112] | 523, +0.135 | no |
| continuation | plan | noprog_4 | 1895, -0.020 [-0.105] | 523, +0.061 | no |
| continuation | plan | noprog_8 | 1895, -0.026 [-0.097] | 523, +0.009 | no |
| continuation | plan | struct | 1895, -0.110 [-0.213] | 523, +0.024 | no |
| continuation | plan | btc_0.7 | 1895, +0.033 [-0.052] | 523, +0.037 | no |
| continuation | plan | btc_1.0 | 1895, +0.031 [-0.038] | 523, +0.068 | no |
| continuation | plan | btc_1.5 | 1895, -0.035 [-0.075] | 523, +0.003 | no |
| continuation | plan | noprog_4+btc_1.0 | 1895, -0.030 [-0.131] | 523, +0.098 | no |
| continuation | plan | filter:alts_with | 726, +0.099 [-0.122] | 199, +0.112 | no |
| continuation | profile | noprog_2 | 1895, -0.302 [-0.524] | 523, +0.290 | no |
| continuation | profile | noprog_4 | 1895, -0.296 [-0.497] | 523, +0.237 | no |
| continuation | profile | noprog_8 | 1895, -0.244 [-0.408] | 523, +0.096 | no |
| continuation | profile | struct | 1895, -0.260 [-0.407] | 523, +0.195 | no |
| continuation | profile | btc_0.7 | 1895, -0.133 [-0.299] | 523, +0.253 | no |
| continuation | profile | btc_1.0 | 1895, -0.168 [-0.341] | 523, +0.302 | no |
| continuation | profile | btc_1.5 | 1895, -0.007 [-0.063] | 523, +0.002 | no |
| continuation | profile | noprog_4+btc_1.0 | 1895, -0.284 [-0.499] | 523, +0.327 | no |
| continuation | profile | filter:alts_with | 726, +0.097 [-0.170] | 199, -0.062 | no |

Base means (train / validation): 
- bollinger plan: -0.547 / -0.732
- bollinger profile: -0.626 / -1.077
- connors plan: -0.051 / -0.170
- connors profile: -0.008 / -0.061
- trendline plan: -0.553 / -0.580
- trendline profile: -0.490 / -0.544
- sweep plan: -0.201 / -0.272
- sweep profile: -0.056 / -0.127
- market_profile plan: -0.309 / -0.340
- market_profile profile: -0.259 / -0.320
- breakout plan: +0.042 / +0.167
- pump plan: -0.099 / -0.045
- pump profile: -0.117 / +0.145
- supply_demand plan: -0.092 / -0.333
- supply_demand profile: +0.751 / -0.340
- wyckoff plan: -0.173 / +0.006
- continuation plan: -0.122 / -0.331
- continuation profile: +0.273 / -0.540
