# Regimes: GaussianMixture vs sticky HMM (C3), 17254 market candles from pretrained.eng-7.pkl

Walk-forward labels (weekly refits on the past only). Longer runs / fewer switches = a steadier context.

| Model | names used | mean run (candles) | median run | switches / day | fit time |
|---|---|---:|---:|---:|---:|
| gmm | down·volatile, flat·normal, flat·quiet, up·volatile | 7.2 | 3 | 13.3 | 38s |
| hmm | down·volatile, flat·quiet, flat·volatile, up·volatile | 10.8 | 4 | 8.9 | 42s |

Decision rule (ML_PLAN.md C3): switch CONFIG.ml.regime_model to hmm only if its runs are longer and its Edge split separates at least as well.
