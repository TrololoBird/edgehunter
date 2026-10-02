# Meta-labeling of the card trades (52266 trades, 421 coins, 2025-04-09 .. 2026-08-31)

Samples: every trade the card replay took plus the first trigger each card's vetoes skipped (low_rr, no_oi, no_spring_test), with the features at the entry and the net R (fees, slippage, funding) exiting at TP1 / the stop / 8h. Label: TP1 before the stop (r_tp1 > 0). Everything below is out of sample.

## 1. Purged walk-forward

| fold | train | test | base AUC | logistic AUC | LightGBM AUC | LightGBM log-loss skill |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 8904 | 9709 | 0.500 | 0.602 | 0.647 | +4.29% |
| 2 | 18602 | 9491 | 0.500 | 0.574 | 0.625 | +2.22% |
| 3 | 28103 | 9063 | 0.500 | 0.582 | 0.647 | +4.79% |
| 4 | 37175 | 7667 | 0.500 | 0.576 | 0.659 | +6.01% |
| 5 | 44835 | 7386 | 0.500 | 0.602 | 0.666 | +6.32% |

### Net R of the trades the model takes (walk-forward, all folds pooled)

| trades | n | mean R all [90%] | taken | mean R taken [90%] | win |
|---|---:|---|---:|---|---:|
| all strategies | 43316 | -0.073 [-0.084..-0.061] | 7407 (17%) | -0.056 [-0.067..-0.046] | 78% |

## 3. Holdout: trained before 2025-12-19, tested after

LightGBM AUC 0.654, logistic AUC 0.579; takes the trades scoring above the training top 20% (0.769).

| trades | n | mean R all [90%] | taken | mean R taken [90%] | win |
|---|---:|---|---:|---|---:|
| all strategies | 24117 | -0.077 [-0.090..-0.064] | 4263 (18%) | -0.057 [-0.071..-0.045] | 78% |
| continuation | 1330 | -0.034 [-0.065..-0.003] | 371 (28%) | -0.023 [-0.058..+0.013] | 81% |
| sweep | 22166 | -0.081 [-0.094..-0.067] | 3679 (17%) | -0.058 [-0.072..-0.044] | 78% |
| wyckoff | 621 | -0.040 [-0.082..-0.003] | 213 (34%) | -0.105 [-0.159..-0.056] | 76% |
| trigger veto: none (taken) | 3072 | -0.095 [-0.138..-0.048] | 82 (3%) | -0.085 [-0.174..-0.005] | 77% |
| trigger veto: low_rr | 19956 | -0.074 [-0.086..-0.063] | 3975 (20%) | -0.058 [-0.071..-0.045] | 78% |
| trigger veto: no_confirmation | 1089 | -0.075 [-0.109..-0.042] | 206 (19%) | -0.037 [-0.087..+0.011] | 80% |

### Taken trades by month (holdout)

| month | taken | mean R taken | mean R all |
|---|---:|---:|---:|
| 2025-12 | 344 | -0.034 | -0.077 |
| 2026-01 | 513 | -0.067 | -0.086 |
| 2026-02 | 704 | -0.081 | -0.099 |
| 2026-03 | 431 | -0.097 | -0.103 |
| 2026-04 | 553 | -0.057 | -0.050 |
| 2026-05 | 541 | -0.048 | -0.084 |
| 2026-06 | 497 | -0.051 | -0.053 |
| 2026-07 | 403 | -0.057 | -0.070 |
| 2026-08 | 277 | +0.022 | -0.069 |

### Most informative features (LightGBM gain, holdout model)

rr_tp1 (35%), btc_4h_dir (9%), tp1_atr (9%), btc_1h_dir (8%), rv_1h_atr (5%), risk_pct (4%), ret_24h_dir (4%), hour_sin (4%), hour_cos (3%), ret_4h_dir (3%), adx (3%), risk_atr (3%), ema20_1h_atr_dir (3%), wait_min (3%), ret_1h_dir (3%)

## 4. Holdout, target = net R (regression), trained on the older half

Correlation of the predicted and the realized R on the holdout: +0.019.

| selection | n | mean R all [90%] | taken | mean R taken [90%] | win |
|---|---:|---|---:|---|---:|
| predicted R > 0 | 24117 | -0.077 [-0.090..-0.064] | 3099 (13%) | -0.059 [-0.088..-0.031] | 61% |
| top 20% of training predictions | 24117 | -0.077 [-0.090..-0.064] | 4115 (17%) | -0.058 [-0.081..-0.036] | 62% |
| continuation: predicted R > 0 | 1330 | -0.034 [-0.065..-0.003] | 339 (25%) | +0.027 [-0.050..+0.108] | 68% |
| sweep: predicted R > 0 | 22166 | -0.081 [-0.094..-0.067] | 2716 (12%) | -0.073 [-0.102..-0.044] | 60% |
| wyckoff: predicted R > 0 | 621 | -0.040 [-0.082..-0.003] | 44 (7%) | +0.167 [+0.011..+0.313] | 77% |

## Verdict: NOT PASSED

The trades the model would take on the holdout: mean net R -0.057 [-0.071..-0.045]. Its 90% interval is not above 0: the model does not turn the strategies' trades into a profitable selection; not shipped.
