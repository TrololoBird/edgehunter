# B1 — realized-volatility forecast (pre-registered: research/prereg/B1_volatility.md)

425 coins, 3518380 coin-hours; development 2025-04-03 .. 2026-04-01, HOLDOUT 2026-04-01 .. 2026-09-30. QLIKE on variance (lower = better), MSE of log RV; DM = Diebold-Mariano p of the hourly cross-coin mean loss difference vs HAR-RV (Newey-West, 24 lags).

## Horizon 1h

| Forecast | QLIKE dev | QLIKE HOLDOUT | MSE log HOLDOUT | vs HAR QLIKE HOLDOUT | DM p |
|---|---:|---:|---:|---:|---:|
| ATR14 | 13608.9929 | 0.3511 | 0.493 | +18.5% | 1.33e-28 |
| max(ATR14, ATR 1h) | 11279.9437 | 0.3359 | 0.482 | +13.4% | 3.91e-14 |
| HAR-RV | 265619.8433 | 0.2963 | 0.387 | +0.0% | — |
| LightGBM | 177.0744 | 0.2747 | 0.363 | -7.3% | 1.04e-07 |

LightGBM top features (splits): hcos 1027, hsin 816, btc_lrv_7d 794, btc_lrv_24h 793, btc_lrv_1h 765, btc_lrv_4h 755, mkt_lrv_1h 747, lrv_24h 529

## Horizon 4h

| Forecast | QLIKE dev | QLIKE HOLDOUT | MSE log HOLDOUT | vs HAR QLIKE HOLDOUT | DM p |
|---|---:|---:|---:|---:|---:|
| ATR14 | 5931.9400 | 0.3239 | 0.479 | +20.3% | 1.25e-27 |
| max(ATR14, ATR 1h) | 4245.6990 | 0.3268 | 0.499 | +21.3% | 8.09e-27 |
| HAR-RV | 200368.1009 | 0.2693 | 0.364 | +0.0% | — |
| LightGBM | 1066.9652 | 0.2683 | 0.364 | -0.4% | 0.905 |

LightGBM top features (splits): btc_lrv_7d 1245, btc_lrv_24h 963, hcos 745, hsin 723, btc_lrv_4h 697, lrv_7d 506, mkt_lrv_1h 436, lrv_24h 428

## Decision (pre-registered rule)

HAR-RV is the forecast (LightGBM not >= 5% better; HAR >= 5% better than both ATR units)
