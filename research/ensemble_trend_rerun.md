# Ensemble Donchian trend (Zarattini et al. 2025) re-tested on the Binance archive

142 coins were in the monthly top 20 at some point; returns net of 0.10% per traded side and funding; long-only, 25% vol target per coin, 1/20 of capital per coin. Rules: the docstring of `research_ensemble.py`. [90%] = weekly-block bootstrap of the annualized mean return.

## whole window

| series | CAGR | Sharpe | max drawdown | total | mean exposure | ann. mean [90%] |
|---|---:|---:|---:|---:|---:|---|
| ensemble net | +1.9% | 0.31 | -14.0% | +11.0% | 7% | +2.1% [-2.4..+6.7] |
| ensemble at 0.05%/side | +2.1% | 0.34 | -13.6% | +12.4% | 7% | +2.3% [-2.2..+7.0] |
| ensemble gross | +3.3% | 0.51 | -12.6% | +20.0% | 7% | +3.4% [-1.2..+8.2] |
| BTC buy & hold | +14.1% | 0.52 | -76.7% | +108.6% | 100% | +29.0% [-9.9..+67.1] |
| top-20 equal weight held | -24.0% | 0.09 | -95.1% | -78.4% | 100% | +7.1% [-43.2..+59.6] |
| top-20 EW only in UP phase | +13.4% | 0.52 | -48.3% | +104.2% | 25% | +20.6% [-4.9..+45.4] |
| BTC only in UP phase | +0.3% | 0.15 | -61.9% | +1.9% | 25% | +4.4% [-13.9..+23.6] |

| market phase | days | ensemble net ann. mean [90%] | exposure | BTC ann. mean | top-20 EW ann. mean |
|---|---:|---|---:|---:|---:|
| UP | 520 | +14.6% [-1.3..+30.1] | 15% | +47.7% | +115.9% |
| MIXED | 705 | -3.1% [-9.2..+3.2] | 8% | +37.4% | -37.3% |
| DOWN | 811 | -1.4% [-3.9..+0.6] | 3% | +9.7% | -24.0% |

## paper's sample overlap (2021-02-04 .. 2025-03-31)

| series | CAGR | Sharpe | max drawdown | total | mean exposure | ann. mean [90%] |
|---|---:|---:|---:|---:|---:|---|
| ensemble net | +3.1% | 0.46 | -14.0% | +13.6% | 8% | +3.3% [-2.3..+9.2] |
| ensemble at 0.05%/side | +3.3% | 0.49 | -13.6% | +14.6% | 8% | +3.6% [-2.1..+9.5] |
| ensemble gross | +4.8% | 0.68 | -12.6% | +21.6% | 8% | +5.0% [-0.8..+11.1] |
| BTC buy & hold | +20.8% | 0.61 | -76.7% | +119.2% | 100% | +37.1% [-12.2..+87.5] |
| top-20 equal weight held | -16.8% | 0.23 | -91.8% | -53.5% | 100% | +19.8% [-44.6..+88.1] |
| top-20 EW only in UP phase | +20.4% | 0.65 | -48.3% | +116.3% | 29% | +28.2% [-4.4..+62.5] |
| BTC only in UP phase | +0.5% | 0.18 | -61.9% | +2.1% | 29% | +5.8% [-18.7..+31.0] |

| market phase | days | ensemble net ann. mean [90%] | exposure | BTC ann. mean | top-20 EW ann. mean |
|---|---:|---|---:|---:|---:|
| UP | 436 | +15.9% [-1.9..+35.3] | 15% | +53.0% | +136.0% |
| MIXED | 549 | -3.4% [-10.7..+3.9] | 7% | +37.1% | -48.0% |
| DOWN | 532 | +0.1% [-2.9..+3.0] | 3% | +24.0% | -5.6% |

## AFTER publication (2025-04-01 .. 2026-09-30)

| series | CAGR | Sharpe | max drawdown | total | mean exposure | ann. mean [90%] |
|---|---:|---:|---:|---:|---:|---|
| ensemble net | -1.5% | -0.29 | -9.0% | -2.3% | 6% | -1.4% [-8.1..+5.3] |
| ensemble at 0.05%/side | -1.3% | -0.25 | -8.8% | -2.0% | 6% | -1.2% [-7.9..+5.5] |
| ensemble gross | -0.9% | -0.16 | -8.4% | -1.3% | 6% | -0.8% [-7.4..+6.0] |
| BTC buy & hold | -3.4% | 0.13 | -53.0% | -4.8% | 100% | +5.5% [-51.7..+60.4] |
| top-20 equal weight held | -41.7% | -0.44 | -76.7% | -53.5% | 100% | -30.1% [-116.1..+60.4] |
| top-20 EW only in UP phase | -3.8% | -0.02 | -23.2% | -5.6% | 15% | -0.6% [-31.6..+31.0] |
| BTC only in UP phase | -0.1% | 0.05 | -13.9% | -0.1% | 15% | +0.6% [-12.3..+14.3] |

| market phase | days | ensemble net ann. mean [90%] | exposure | BTC ann. mean | top-20 EW ann. mean |
|---|---:|---|---:|---:|---:|
| UP | 84 | +8.1% [-14.2..+29.7] | 15% | +19.9% | +9.9% |
| MIXED | 156 | -1.8% [-15.7..+10.1] | 9% | +38.7% | +0.4% |
| DOWN | 279 | -4.3% [-8.0..-1.7] | 3% | -17.4% | -59.0% |

