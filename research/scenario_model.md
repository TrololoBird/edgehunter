# Scenario probability model (439 coins, 306099 samples, 2023-10-09 .. 2026-08-31)

Label: the first resistance above touched before the first support below within 72h (the scenario card's two nearest ladder levels). Code and protocol: `train_scenarios.py`, `scenarios.py`.

Train < 2025-05-11, calibration 2025-05-11 .. 2025-10-03, TEST from 2025-10-03 (76549 samples, up first 46.8%).

Feature sets, Brier of the raw model on the CALIBRATION part (the choice): price 0.2251, price + macro 0.2298 -> **price**

| predictor (test part) | Brier | log loss |
|---|---:|---:|
| constant base rate 0.490 | 0.2495 | — |
| geometric p_geo = d_down / (d_up + d_down) | 0.2207 | 0.6301 |
| model (LightGBM + isotonic, price) | 0.2318 | 0.6563 |

Brier skill vs geometry: -5.01%. **NOT passed: the bot shows the geometric baseline**.

## Calibration of the model on the test part

| predicted | samples | observed up-first |
|---|---:|---:|
| 0.0-0.1 | 1505 | 11.2% |
| 0.1-0.2 | 1255 | 16.8% |
| 0.2-0.3 | 4226 | 25.5% |
| 0.3-0.4 | 12789 | 33.5% |
| 0.4-0.5 | 14885 | 42.3% |
| 0.5-0.6 | 17262 | 49.2% |
| 0.6-0.7 | 14831 | 57.3% |
| 0.7-0.8 | 5511 | 63.3% |
| 0.8-0.9 | 2712 | 71.2% |
| 0.9-1.0 | 1573 | 88.1% |

## Trading the call on the test part (entry at the price, target = the level, stop = the other level, 0.20% round trip)

| rule | trades | win | mean net R [90% by week] |
|---|---:|---:|---|
| model p >= 0.6 long / <= 0.4 short | 44402 | 66% | -0.092 [-0.120..-0.067] |
| geometry p >= 0.6 / <= 0.4 | 40029 | 71% | -0.064 [-0.080..-0.048] |

Feature importance (splits): btc_ret_7d 3273, btc_trend_4h 3026, btc_ret_24h 3019, p_geo 529, trend_1h 306, ret_24h 303, trend_4h 293, vol_ratio 291, ret_7d 266, range_pos 213, d_up 195, d_down 193, s_down 42, n_down 29, s_up 15, n_up 7

