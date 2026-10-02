# B1 — realized-volatility forecast (pre-registered: research/prereg/B1_volatility.md)

425 coins, 3518380 coin-hours; development 2025-04-03 .. 2026-04-01, HOLDOUT 2026-04-01 .. 2026-09-30. QLIKE on variance (lower = better), MSE of log RV; DM = Diebold-Mariano p of the hourly cross-coin mean loss difference vs HAR-RV (Newey-West, 24 lags).

## Horizon 1h

| Forecast | QLIKE dev (in-sample) | median QLIKE dev | QLIKE HOLDOUT | MSE log HOLDOUT | vs HAR QLIKE HOLDOUT | DM p |
|---|---:|---:|---:|---:|---:|---:|
| ATR14 | 69.8813 | 0.1122 | 0.3446 | 0.494 | +18.9% | 1.16e-27 |
| max(ATR14, ATR 1h) | 62.5014 | 0.1033 | 0.3312 | 0.484 | +14.3% | 2.85e-15 |
| HAR-RV | 527.0131 | 0.0717 | 0.2897 | 0.385 | +0.0% | — |
| LightGBM | 177.0744 | 0.0539 | 0.2747 | 0.363 | -5.2% | 6.12e-05 |

LightGBM top features (splits): hcos 1025, hsin 818, btc_lrv_7d 794, btc_lrv_24h 793, btc_lrv_1h 765, btc_lrv_4h 755, mkt_lrv_1h 747, lrv_24h 529

## Horizon 4h

| Forecast | QLIKE dev (in-sample) | median QLIKE dev | QLIKE HOLDOUT | MSE log HOLDOUT | vs HAR QLIKE HOLDOUT | DM p |
|---|---:|---:|---:|---:|---:|---:|
| ATR14 | 51.1032 | 0.1138 | 0.3270 | 0.522 | +21.7% | 2.98e-27 |
| max(ATR14, ATR 1h) | 39.8971 | 0.1142 | 0.3306 | 0.543 | +23.0% | 1.19e-27 |
| HAR-RV | 501.1156 | 0.0747 | 0.2688 | 0.374 | +0.0% | — |
| LightGBM | 1066.9652 | 0.0488 | 0.2683 | 0.364 | -0.2% | 0.817 |

LightGBM top features (splits): btc_lrv_7d 1245, btc_lrv_24h 963, hcos 745, hsin 723, btc_lrv_4h 697, lrv_7d 506, mkt_lrv_1h 436, lrv_24h 428

## Decision (pre-registered rule)

HAR-RV is the forecast (LightGBM not >= 5% better; HAR >= 5% better than both ATR units)
