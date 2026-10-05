# Indicator confirmations on the archive replay (pre-registered, research_indicator_confirms.py)

Entries: 16595 of 10 strategies; discovery < 2026-04-01 <= validation. Cells tested in discovery: 208; kept at BH q 0.10: 0.

## Validation of the kept cells

| strategy | rule | n agree / all | mean R all | agree | disagree | diff [90%] | verdict |
|---|---|---|---|---|---|---|---|
| - | no cell passed discovery | | | | | | |

## Discovery: the 25 largest differences (before the BH correction)

| strategy | rule | n agree / all | agree | disagree | diff [90%] | p |
|---|---|---|---|---|---|---|
| bollinger | 15m:adx_trend | 198 / 3614 | +0.132 | -0.337 | +0.443 [-0.080..+1.046] | 0.1129 |
| trendline | 15m:mfi_50 | 59 / 158 | -0.023 | -0.649 | +0.392 [+0.098..+0.687] | 0.0115 |
| trendline | 15m:obv_slope | 35 / 158 | -0.169 | -0.486 | +0.246 [-0.156..+0.669] | 0.1759 |
| trendline | 15m:rsi_50 | 36 / 158 | -0.173 | -0.487 | +0.243 [-0.060..+0.556] | 0.0945 |
| trendline | 1h:macd_turn | 38 / 156 | -0.193 | -0.500 | +0.232 [-0.205..+0.674] | 0.2034 |
| continuation | 1h:adx_trend | 422 / 1404 | -0.060 | -0.352 | +0.205 [+0.048..+0.397] | 0.0125 |
| trendline | 15m:adx_range | 41 / 158 | -0.213 | -0.486 | +0.202 [-0.175..+0.583] | 0.2074 |
| bollinger | 15m:bb_outside | 170 / 3614 | -0.139 | -0.320 | +0.172 [-0.125..+0.477] | 0.1814 |
| bollinger | 15m:rsi_extreme | 432 / 3614 | -0.147 | -0.333 | +0.164 [-0.005..+0.347] | 0.0590 |
| trendline | 15m:atr_high | 81 / 158 | -0.287 | -0.551 | +0.129 [-0.078..+0.330] | 0.1514 |
| bollinger | 1h:adx_trend | 363 / 3602 | -0.183 | -0.325 | +0.128 [-0.116..+0.379] | 0.2164 |
| bollinger | 1h:atr_high | 1673 / 3602 | -0.188 | -0.417 | +0.122 [+0.030..+0.220] | 0.0125 |
| trendline | 1h:atr_high | 46 / 156 | -0.313 | -0.472 | +0.113 [-0.212..+0.437] | 0.2824 |
| sweep | 15m:rsi_extreme | 65 / 768 | -0.043 | -0.165 | +0.112 [-0.018..+0.238] | 0.0835 |
| continuation | 15m:bb_outside | 187 / 1404 | -0.154 | -0.281 | +0.110 [-0.036..+0.270] | 0.1054 |
| market_profile | 15m:stoch_cross | 41 / 1656 | -0.032 | -0.141 | +0.107 [-0.194..+0.386] | 0.2614 |
| bollinger | 15m:atr_high | 1974 / 3614 | -0.216 | -0.425 | +0.095 [+0.015..+0.171] | 0.0270 |
| pump | 15m:adx_range | 71 / 303 | +0.070 | -0.054 | +0.095 [-0.005..+0.199] | 0.0570 |
| trendline | 1h:adx_trend | 58 / 156 | -0.334 | -0.480 | +0.092 [-0.170..+0.393] | 0.2804 |
| bollinger | 15m:mfi_50 | 458 / 3614 | -0.229 | -0.323 | +0.082 [-0.171..+0.383] | 0.3553 |
| bollinger | 1h:squeeze | 742 / 3602 | -0.233 | -0.331 | +0.078 [-0.106..+0.269] | 0.2629 |
| market_profile | 15m:ema_stack | 133 / 1656 | -0.061 | -0.145 | +0.078 [-0.094..+0.232] | 0.2239 |
| sweep | 15m:mfi_50 | 211 / 768 | -0.077 | -0.183 | +0.077 [-0.005..+0.156] | 0.0610 |
| bollinger | 1h:ema_stack | 550 / 3602 | -0.236 | -0.324 | +0.074 [-0.135..+0.309] | 0.3133 |
| trendline | 1h:obv_slope | 115 / 156 | -0.353 | -0.629 | +0.073 [-0.050..+0.197] | 0.1684 |
