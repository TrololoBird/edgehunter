# B1 — realized-volatility forecast (pre-registered: research/prereg/B1_volatility.md)

3 coins, 36636 coin-hours; development 2025-04-03 .. 2026-04-01, HOLDOUT 2026-04-01 .. 2026-09-30. QLIKE on variance (lower = better), MSE of log RV; DM = Diebold-Mariano p of the hourly cross-coin mean loss difference vs HAR-RV (Newey-West, 24 lags).

## Horizon 1h

| Forecast | QLIKE dev | QLIKE HOLDOUT | MSE log HOLDOUT | vs HAR QLIKE HOLDOUT | DM p |
|---|---:|---:|---:|---:|---:|
| ATR14 | 0.3333 | 0.3410 | 0.536 | +17.1% | 3.65e-13 |
| max(ATR14, ATR 1h) | 0.3001 | 0.3090 | 0.496 | +6.2% | 0.0745 |
| HAR-RV | 0.2823 | 0.2911 | 0.440 | +0.0% | — |
| LightGBM | 0.2115 | 0.2670 | 0.378 | -8.3% | 0.0154 |

LightGBM top features (splits): hsin 1049, hcos 861, btc_lrv_7d 777, btc_lrv_4h 750, mkt_lrv_1h 747, btc_lrv_24h 705, btc_lrv_1h 681, lrv_7d 656

## Horizon 4h

| Forecast | QLIKE dev | QLIKE HOLDOUT | MSE log HOLDOUT | vs HAR QLIKE HOLDOUT | DM p |
|---|---:|---:|---:|---:|---:|
| ATR14 | 0.3054 | 0.3227 | 0.541 | +13.5% | 0.00033 |
| max(ATR14, ATR 1h) | 0.3022 | 0.3146 | 0.538 | +10.6% | 0.0742 |
| HAR-RV | 0.2789 | 0.2844 | 0.440 | +0.0% | — |
| LightGBM | 0.1741 | 0.2266 | 0.337 | -20.3% | 0.00587 |

LightGBM top features (splits): btc_lrv_7d 813, btc_lrv_24h 736, hcos 638, lrv_7d 631, hsin 576, btc_lrv_4h 400, mkt_lrv_1h 399, lrv_24h 398

## Decision (pre-registered rule)

ACCEPT LightGBM (>= 5% lower QLIKE than HAR-RV on both horizons, DM p < 0.05)
