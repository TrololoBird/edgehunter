# B1 — realized-volatility forecast (pre-registered: research/prereg/B1_volatility.md)

425 coins, 3518380 coin-hours; development 2025-04-03 .. 2026-04-01, HOLDOUT 2026-04-01 .. 2026-09-30. QLIKE on variance (lower = better), MSE of log RV; DM = Diebold-Mariano p of the hourly cross-coin mean loss difference vs HAR-RV (Newey-West, 24 lags).

## Horizon 1h

| Forecast | QLIKE dev | QLIKE HOLDOUT | MSE log HOLDOUT | vs HAR QLIKE HOLDOUT | DM p |
|---|---:|---:|---:|---:|---:|
| ATR14 | 182764.4869 | 0.4507 | 0.575 | +42.4% | 3.98e-26 |
| max(ATR14, ATR 1h) | 165675.4460 | 0.4256 | 0.574 | +34.5% | 1.12e-20 |
| HAR-RV | 863659.9284 | 0.3165 | 0.427 | +0.0% | — |
| LightGBM | 923762.7695 | 0.3062 | 0.382 | -3.3% | 0.0482 |

LightGBM top features (splits): hcos 1090, btc_lrv_7d 1029, btc_lrv_1h 1007, btc_lrv_24h 952, btc_lrv_4h 946, hsin 928, mkt_lrv_1h 901, lrv_1h 758

## Horizon 4h

| Forecast | QLIKE dev | QLIKE HOLDOUT | MSE log HOLDOUT | vs HAR QLIKE HOLDOUT | DM p |
|---|---:|---:|---:|---:|---:|
| ATR14 | 184024.6089 | 0.4615 | 0.654 | +50.2% | 8.37e-42 |
| max(ATR14, ATR 1h) | 148818.8233 | 0.4454 | 0.688 | +45.0% | 3.43e-46 |
| HAR-RV | 1262505.7525 | 0.3072 | 0.455 | +0.0% | — |
| LightGBM | 3545202.3573 | 0.2732 | 0.372 | -11.1% | 2.79e-05 |

LightGBM top features (splits): btc_lrv_7d 1235, btc_lrv_24h 875, hcos 753, hsin 723, btc_lrv_4h 666, lrv_1h 568, lrv_7d 465, mkt_lrv_1h 446

## Decision (pre-registered rule)

HAR-RV is the forecast (LightGBM not >= 5% better; HAR >= 5% better than both ATR units)
