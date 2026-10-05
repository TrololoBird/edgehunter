# Strategy optimization on the archive replay (research_optimize.py)

16550 simulated entries, 524 PM variants x filters (none / one / a pair of 53); selection < 2026-06-01 <= validation.

| strategy | profile (filters / PM) | train: trades, mean R [lower 90%] | validation: trades, mean R [lower 90%] | verdict |
|---|---|---|---|---|
| bollinger | 15m:rsi_divergence & passed_veto / {'target': 'plan', 'be': False, 'trail': 2, 'half': False, 'hours': 12, 'stop': 1.0} | 143, +0.315 [-0.022] | 93, -0.706 [-0.881] | no |
| breakout | coin:large & passed_veto / {'target': '3', 'be': True, 'trail': 0, 'half': False, 'hours': 72, 'stop': 1.0} | 64, +0.719 [+0.312] | 21, +0.515 [+0.105] | DEMO |
| connors | coin:mid / {'target': '1', 'be': False, 'trail': 0, 'half': False, 'hours': 4, 'stop': 1.0} | 53, +0.006 [-0.026] | 36, -0.023 [-0.081] | no |
| continuation | 15m:stoch_cross & 1h:ema50_slope / {'target': '3', 'be': False, 'trail': 0, 'half': False, 'hours': 72, 'stop': 1.5} | 205, +1.016 [+0.597] | 60, -0.495 [-0.779] | no |
| market_profile | 15m:ema_stack & coin:large / {'target': '3', 'be': False, 'trail': 0, 'half': False, 'hours': 72, 'stop': 1.0} | 33, +0.765 [+0.146] | 13, -0.973 [-1.184] | no |
| pump | coin:mid & session:asia / {'target': '3', 'be': True, 'trail': 0, 'half': False, 'hours': 72, 'stop': 1.0} | 48, +0.515 [+0.099] | 11, +0.292 [-0.381] | DEMO |
| supply_demand | 1h:atr_high / {'target': 'none', 'be': True, 'trail': 0, 'half': False, 'hours': 72, 'stop': 1.0} | 62, +1.120 [+0.087] | 23, -0.237 [-0.533] | no |
| sweep | 15m:rsi_extreme & 1h:ema200_side / {'target': 'plan', 'be': False, 'trail': 0, 'half': True, 'hours': 24, 'stop': 1.5} | 40, +0.300 [+0.168] | 13, -0.536 [-0.863] | no |
| trendline | 15m:ema50_slope & coin:large / {'target': '2', 'be': True, 'trail': 0, 'half': False, 'hours': 4, 'stop': 1.0} | 45, +0.127 [-0.184] | 20, -0.802 [-1.112] | no |

Validation span: 4.0 months. DEMO = positive mean R on the untouched months.
