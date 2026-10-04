# Regimes: Gaussian HMM vs GaussianMixture (plan 3.4)

14374 candles of 15m (10061 train / 4313 test); k = 6 by BIC (2: 135390, 3: 36628, 4: 32768, 5: 27302, 6: 26576).

| model | test log-lik / candle | mean regime duration (candles) | switches per day |
|---|---:|---:|---:|
| GMM (live, full cov.) | -0.248 | 9.9 | 9.7 |
| HMM (diag. cov.) | -1.998 | 9.0 | 10.6 |

HMM stay probabilities: 0.895, 0.744, 0.673, 0.765, 0.878, 0.668

Verdict: keep the GMM (rule: higher test likelihood and at least 2x the mean duration).
