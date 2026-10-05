# Robust second pass (research_optimize_robust.py)

| strategy | mode | profile | half 1 | half 2 | validation: n, mean [lower 90%] | verdict |
|---|---|---|---|---|---|---|
| bollinger | pm only | - | none stable in both halves | | | no |
| bollinger | filters + pm | - | none stable in both halves | | | no |
| breakout | pm only | - | none stable in both halves | | | no |
| breakout | filters + pm | coin:large & passed_veto / {'target': '3', 'be': True, 'trail': 0, 'half': False, 'hours': 72, 'stop': 1.0} | +0.795 [+0.252] | +0.564 [+0.073] | 21, +0.515 [+0.105] | DEMO |
| connors | pm only | - | none stable in both halves | | | no |
| connors | filters + pm | - | none stable in both halves | | | no |
| continuation | pm only | - | none stable in both halves | | | no |
| continuation | filters + pm | 15m:stoch_cross & btc:with / {'target': '3', 'be': False, 'trail': 0, 'half': False, 'hours': 72, 'stop': 1.5} | +1.096 [+0.319] | +1.104 [+0.398] | 58, -0.555 [-0.848] | no |
| market_profile | pm only | - | none stable in both halves | | | no |
| market_profile | filters + pm | - | none stable in both halves | | | no |
| pump | pm only | - | none stable in both halves | | | no |
| pump | filters + pm | - | none stable in both halves | | | no |
| supply_demand | pm only | - | none stable in both halves | | | no |
| supply_demand | filters + pm | - | none stable in both halves | | | no |
| sweep | pm only | - | none stable in both halves | | | no |
| sweep | filters + pm | 15m:rsi_extreme & 1h:ema50_slope / {'target': 'plan', 'be': True, 'trail': 0, 'half': True, 'hours': 24, 'stop': 1.5} | +0.285 [+0.130] | +0.276 [+0.060] | 18, +0.019 [-0.362] | DEMO |
| trendline | pm only | - | none stable in both halves | | | no |
| trendline | filters + pm | - | none stable in both halves | | | no |
| wyckoff | pm only | - | none stable in both halves | | | no |
| wyckoff | filters + pm | - | none stable in both halves | | | no |
