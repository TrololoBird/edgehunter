# Scenario probability model (478 coins, 75564 samples, 2025-07-10 .. 2026-09-30)

Label: the first resistance above touched before the first support below within 72h (the scenario card's two nearest ladder levels). Code and protocol: `train_scenarios.py`, `scenarios.py`.

Train < 2026-02-19, calibration 2026-02-19 .. 2026-05-05, TEST from 2026-05-05 (18936 samples, up first 49.8%).

Feature sets, Brier of the raw model on the CALIBRATION part (the choice): price 0.2469, price + macro 0.2473 -> **price**

| predictor (test part) | Brier | log loss |
|---|---:|---:|
| constant base rate 0.464 | 0.2511 | — |
| geometric p_geo = d_down / (d_up + d_down) | 0.2138 | 0.6156 |
| model (LightGBM + isotonic, price) | 0.2283 | 0.6480 |

Brier skill vs geometry: -6.78%. **NOT passed: the bot shows the geometric baseline**.

## Calibration of the model on the test part

| predicted | samples | observed up-first |
|---|---:|---:|
| 0.0-0.1 | 319 | 10.7% |
| 0.1-0.2 | 366 | 21.0% |
| 0.3-0.4 | 5004 | 35.2% |
| 0.4-0.5 | 4609 | 45.7% |
| 0.5-0.6 | 5526 | 58.0% |
| 0.6-0.7 | 1862 | 67.8% |
| 0.7-0.8 | 719 | 72.2% |
| 0.8-0.9 | 350 | 83.7% |
| 0.9-1.0 | 180 | 93.9% |

## Trading the call on the test part (entry at the price, target = the level, stop = the other level, 0.20% round trip)

| rule | trades | win | mean net R [90% by week] |
|---|---:|---:|---|
| model p >= 0.6 long / <= 0.4 short | 8801 | 69% | -0.022 [-0.061..+0.017] |
| geometry p >= 0.6 / <= 0.4 | 10814 | 73% | -0.001 [-0.018..+0.016] |

Feature importance (splits): btc_ret_24h 2699, btc_ret_7d 2507, btc_trend_4h 2364, p_geo 562, vol_ratio 554, ret_7d 546, trend_4h 492, trend_1h 467, ret_24h 433, d_down 401, d_up 368, range_pos 325, s_down 116, s_up 99, n_up 46, n_down 21

