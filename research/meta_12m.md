# Meta-labeling of the card trades (332316 trades, 400 coins, 2025-10-03 .. 2026-09-26)

Samples: every trade the card replay took plus the first trigger each card's vetoes skipped (low_rr, no_oi, no_spring_test), with the features at the entry and the net R (fees, slippage, funding) exiting at TP1 / the stop / 8h. Label: TP1 before the stop (r_tp1 > 0). Everything below is out of sample.

## 1. Purged walk-forward

| fold | train | test | base AUC | logistic AUC | LightGBM AUC | LightGBM log-loss skill |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 65952 | 59248 | 0.500 | 0.590 | 0.612 | +2.40% |
| 2 | 125138 | 55005 | 0.500 | 0.621 | 0.624 | +3.27% |
| 3 | 180365 | 55902 | 0.500 | 0.607 | 0.629 | +3.70% |
| 4 | 236139 | 50479 | 0.500 | 0.612 | 0.627 | +3.53% |
| 5 | 286745 | 45167 | 0.500 | 0.598 | 0.625 | +3.66% |

### Net R of the trades the model takes (walk-forward, all folds pooled)

| trades | n | mean R all [90%] | taken | mean R taken [90%] | win |
|---|---:|---|---:|---|---:|
| all strategies | 265801 | -0.151 [-0.162..-0.141] | 47550 (18%) | -0.100 [-0.114..-0.087] | 70% |

## 3. Holdout: trained before 2026-03-31, tested after

LightGBM AUC 0.626, logistic AUC 0.603; takes the trades scoring above the training top 20% (0.678).

| trades | n | mean R all [90%] | taken | mean R taken [90%] | win |
|---|---:|---|---:|---|---:|
| all strategies | 151549 | -0.160 [-0.172..-0.148] | 26181 (17%) | -0.103 [-0.118..-0.088] | 70% |
| breakout | 71954 | -0.157 [-0.173..-0.139] | 10471 (15%) | -0.122 [-0.158..-0.088] | 65% |
| momentum | 1349 | -0.048 [-0.097..+0.002] | 50 (4%) | -0.019 [-0.144..+0.096] | 72% |
| sweep | 39473 | -0.150 [-0.162..-0.138] | 14290 (36%) | -0.094 [-0.104..-0.084] | 74% |
| trend | 3814 | -0.182 [-0.211..-0.152] | 230 (6%) | -0.026 [-0.084..+0.030] | 74% |
| wyckoff | 34959 | -0.180 [-0.199..-0.160] | 1140 (3%) | -0.057 [-0.088..-0.027] | 71% |
| trigger veto: none (taken) | 15340 | -0.205 [-0.232..-0.177] | 0 (0%) | +nan [+nan..+nan] | nan% |
| trigger veto: low_rr | 97370 | -0.153 [-0.163..-0.142] | 19797 (20%) | -0.093 [-0.103..-0.083] | 73% |
| trigger veto: no_oi | 38839 | -0.160 [-0.181..-0.139] | 6384 (16%) | -0.133 [-0.177..-0.090] | 64% |

### Taken trades by month (holdout)

| month | taken | mean R taken | mean R all |
|---|---:|---:|---:|
| 2026-03 | 865 | -0.084 | -0.176 |
| 2026-04 | 4330 | -0.069 | -0.161 |
| 2026-05 | 5434 | -0.103 | -0.138 |
| 2026-06 | 5019 | -0.125 | -0.161 |
| 2026-07 | 3614 | -0.102 | -0.190 |
| 2026-08 | 3529 | -0.106 | -0.149 |
| 2026-09 | 3390 | -0.114 | -0.164 |

### Most informative features (LightGBM gain, holdout model)

rr_tp1 (42%), btc_4h_dir (12%), btc_1h_dir (10%), risk_pct (5%), hour_cos (5%), hour_sin (5%), tp1_atr (4%), rv_1h_atr (3%), trigger_veto= (3%), ret_24h_dir (3%), direction (2%), ret_4h_dir (2%), risk_atr (2%), ema20_1h_atr_dir (2%), pos_24h_dir (2%)

## 4. Holdout, target = net R (regression), trained on the older half

Correlation of the predicted and the realized R on the holdout: +0.083.

| selection | n | mean R all [90%] | taken | mean R taken [90%] | win |
|---|---:|---|---:|---|---:|
| predicted R > 0 | 151549 | -0.160 [-0.172..-0.148] | 6179 (4%) | -0.146 [-0.205..-0.086] | 55% |
| top 20% of training predictions | 151549 | -0.160 [-0.172..-0.148] | 22070 (15%) | -0.109 [-0.137..-0.082] | 59% |
| breakout: predicted R > 0 | 71954 | -0.157 [-0.173..-0.139] | 4998 (7%) | -0.163 [-0.236..-0.086] | 54% |
| momentum: predicted R > 0 | 1349 | -0.048 [-0.097..+0.002] | 15 (1%) | +0.207 [-0.210..+0.650] | 67% |
| sweep: predicted R > 0 | 39473 | -0.150 [-0.162..-0.138] | 622 (2%) | -0.100 [-0.147..-0.053] | 67% |
| trend: predicted R > 0 | 3814 | -0.182 [-0.211..-0.152] | 22 (1%) | -0.402 [-0.664..-0.112] | 36% |
| wyckoff: predicted R > 0 | 34959 | -0.180 [-0.199..-0.160] | 522 (1%) | -0.038 [-0.120..+0.048] | 54% |

## Verdict: NOT PASSED

The trades the model would take on the holdout: mean net R -0.103 [-0.118..-0.088]. Its 90% interval is not above 0: the model does not turn the strategies' trades into a profitable selection; not shipped.
