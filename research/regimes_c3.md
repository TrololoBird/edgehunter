# Regimes: GaussianMixture vs sticky HMM (C3), 49030 market candles from pretrained.pkl

Walk-forward labels (weekly refits on the past only). Longer runs / fewer switches = a steadier context.

| Model | names used | mean run (candles) | median run | switches / day | fit time |
|---|---|---:|---:|---:|---:|
| gmm | down·normal, down·volatile, flat·normal, flat·normal#2, flat·quiet, flat·volatile, up·normal | 5.8 | 3 | 15.7 | 95s |
| hmm | down·normal, down·volatile, flat·normal, flat·normal#2, flat·normal#3, flat·quiet, flat·volatile, flat·volatile#2, up·normal, up·volatile | 7.2 | 4 | 12.6 | 88s |

## Edge 4h of directional pretraining rows by gmm regime

| Regime | rows | Edge 4h [90%] |
|---|---:|---|
| down·normal | 50976 | -0.020% [-0.038..-0.004] |
| down·volatile | 9991 | +0.017% [-0.021..+0.058] |
| flat·normal | 594285 | -0.002% [-0.010..+0.006] |
| flat·normal#2 | 290195 | -0.000% [-0.010..+0.009] |
| flat·quiet | 281691 | +0.002% [-0.008..+0.012] |
| flat·volatile | 163780 | -0.013% [-0.030..+0.004] |
| up·normal | 5504 | +0.022% [-0.052..+0.103] |

## Edge 4h of directional pretraining rows by hmm regime

| Regime | rows | Edge 4h [90%] |
|---|---:|---|
| down·normal | 223313 | -0.007% [-0.017..+0.003] |
| down·volatile | 70658 | +0.007% [-0.014..+0.026] |
| flat·normal | 413909 | -0.001% [-0.010..+0.008] |
| flat·normal#2 | 247545 | +0.006% [-0.005..+0.018] |
| flat·normal#3 | 147995 | +0.010% [-0.005..+0.027] |
| flat·quiet | 81536 | -0.005% [-0.023..+0.013] |
| flat·volatile | 92758 | -0.034% [-0.060..-0.011] |
| flat·volatile#2 | 85335 | -0.015% [-0.034..+0.005] |
| up·normal | 3087 | -0.011% [-0.107..+0.086] |
| up·volatile | 30286 | -0.007% [-0.040..+0.025] |

Decision rule (ML_PLAN.md C3): switch CONFIG.ml.regime_model to hmm only if its runs are longer and its Edge split separates at least as well.
