# Regimes: Gaussian HMM vs GaussianMixture (plan 3.4)

34534 candles of 15m (24173 train / 10361 test); k = 6 by BIC (2: 316947, 3: 184764, 4: 177750, 5: 170637, 6: 168292).

| model | test log-lik / candle | mean regime duration (candles) | switches per day |
|---|---:|---:|---:|
| GMM (live, full cov.) | 0.837 | 4.1 | 23.3 |
| HMM (diag. cov.) | -0.519 | 13.0 | 7.4 |

HMM stay probabilities: 0.697, 0.742, 0.704, 0.920, 0.753, 0.849

Verdict: keep the GMM (rule: higher test likelihood and at least 2x the mean duration).
