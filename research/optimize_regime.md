# Regime-switched profiles (research_optimize_regime.py, pre-registered)

Regime share of entries: trend_hv 30%, trend_lv 21%, range_hv 12%, range_lv 38%

| strategy | regime | profile | train: n, mean [lower 90%] | halves | validation: n, mean [lower 90%] | verdict |
|---|---|---|---|---|---|---|
| breakout | trend_hv | 15m:obv_slope / {'target': '3', 'be': True, 'trail': 3, 'half': False, 'hours': 72, 'stop': 1.0} | 85, +0.227 [+0.047] | +0.31 / +0.17 | 105, +0.418 [+0.179] | ON |
| breakout | range_hv | 1h:rvol_1_5 / {'target': '3', 'be': True, 'trail': 0, 'half': False, 'hours': 72, 'stop': 1.0} | 38, +1.263 [+0.687] | +1.44 / +0.47 | 7, -0.130 [-0.549] | off |
| breakout | range_lv | weekend / {'target': '3', 'be': False, 'trail': 0, 'half': False, 'hours': 72, 'stop': 1.0} | 25, +0.472 [+0.177] | +0.39 / +0.52 | 15, -0.335 [-0.568] | off |
| continuation | trend_hv | coin:mid / {'target': '3', 'be': True, 'trail': 2, 'half': False, 'hours': 72, 'stop': 1.5} | 236, +0.727 [+0.427] | +1.43 / +0.43 | 78, -0.205 [-0.779] | off |
| continuation | range_lv | weekend / {'target': 'none', 'be': True, 'trail': 0, 'half': False, 'hours': 72, 'stop': 1.0} | 316, +3.185 [+1.455] | +0.19 / +3.70 | 76, -0.955 [-1.151] | off |
| market_profile | trend_lv | 1h:rsi_extreme / {'target': '1.5', 'be': False, 'trail': 0, 'half': False, 'hours': 72, 'stop': 1.0} | 32, +0.407 [+0.070] | +0.55 / +0.33 | 7, -0.454 [-1.364] | off |
| market_profile | range_hv | 15m:rvol_1_5 / {'target': '3', 'be': False, 'trail': 0, 'half': False, 'hours': 72, 'stop': 1.0} | 55, +0.478 [+0.029] | +0.86 / +0.13 | 9, -0.460 [-1.280] | off |
| pump | trend_lv | coin:large / {'target': 'plan', 'be': False, 'trail': 0, 'half': True, 'hours': 72, 'stop': 1.0} | 18, +0.267 [+0.033] | +0.39 / +0.08 | 1, +0.858 [-inf] | ON |
| pump | range_hv | 15m:mfi_50 / {'target': 'none', 'be': True, 'trail': 0, 'half': False, 'hours': 12, 'stop': 1.0} | 32, +0.496 [+0.032] | +0.61 / +0.30 | 10, +0.503 [-0.458] | ON |
| pump | range_lv | 1h:adx_trend / {'target': '3', 'be': False, 'trail': 0, 'half': False, 'hours': 72, 'stop': 1.0} | 35, +0.590 [+0.110] | +0.64 / +0.50 | 11, +0.024 [-0.886] | ON |
| supply_demand | trend_hv | 1h:atr_high / {'target': 'none', 'be': True, 'trail': 0, 'half': False, 'hours': 72, 'stop': 1.0} | 18, +3.124 [+0.168] | +3.80 / +2.28 | 8, +0.245 [-0.357] | ON |
| supply_demand | range_lv | 1h:atr_high / {'target': 'none', 'be': True, 'trail': 0, 'half': False, 'hours': 72, 'stop': 1.0} | 17, +1.094 [+0.080] | +1.80 / +0.30 | 6, -0.806 [-1.141] | off |
| sweep | trend_hv | 15m:rsi_extreme / {'target': '1', 'be': False, 'trail': 0, 'half': False, 'hours': 24, 'stop': 1.5} | 24, +0.318 [+0.028] | +0.45 / +0.16 | 14, -0.203 [-0.591] | off |
| sweep | range_hv | 1h:macd_turn / {'target': 'plan', 'be': False, 'trail': 0, 'half': True, 'hours': 72, 'stop': 1.5} | 53, +0.263 [+0.111] | +0.30 / +0.23 | 21, -0.088 [-0.437] | off |
| sweep | range_lv | btc:against / {'target': 'plan', 'be': True, 'trail': 0, 'half': True, 'hours': 72, 'stop': 1.5} | 129, +0.135 [+0.010] | +0.20 / +0.05 | 130, -0.116 [-0.229] | off |
| trendline | trend_hv | 15m:rsi_50 / {'target': '3', 'be': True, 'trail': 0, 'half': False, 'hours': 24, 'stop': 1.5} | 17, +0.543 [+0.020] | +0.98 / +0.15 | 6, -0.437 [-0.685] | off |

Strategies / regimes not listed: no profile qualified on the training months.
