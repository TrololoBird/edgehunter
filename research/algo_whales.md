# ALGO / WHALES anomalies vs the market and a placebo (research_algo_whales.py)

Signed excess return = the coin's return minus the mean of every coin, + = the label's way. Placebo = the same coin and hour on a random day 1-7 days away. Interval = 90% bootstrap of 4h clusters of the difference real - placebo. Pre-registered: CONTINUATION / REVERSAL only if the interval excludes 0 in both halves.

| label | h | n | mean real | mean placebo | diff [90%] | older half | newer half | verdict |
|---|---:|---:|---:|---:|---|---|---|---|
| ALGO BUY | 1h | 1218 | +0.041% | -0.048% | +0.089% [-0.092..+0.274] | [-0.079..+0.347] | [-0.196..+0.310] | no effect |
| ALGO BUY | 4h | 1132 | -0.238% | +0.231% | -0.469% [-0.858..-0.092] | [-0.951..-0.077] | [-0.943..+0.108] | no effect |
| ALGO SELL | 1h | 1800 | -0.034% | +0.082% | -0.116% [-0.249..+0.022] | [-0.256..+0.038] | [-0.310..+0.034] | no effect |
| ALGO SELL | 4h | 1527 | +0.034% | -0.215% | +0.249% [-0.118..+0.678] | [-0.394..+0.488] | [-0.043..+0.863] | no effect |
| WHALES BUY | 1h | 402 | +0.071% | -0.101% | +0.172% [-0.004..+0.470] | [-0.098..+0.241] | [+0.029..+1.462] | no effect |
| WHALES BUY | 4h | 401 | -0.021% | -0.140% | +0.119% [-0.374..+0.858] | [-0.574..+0.299] | [-0.467..+3.970] | no effect |
| WHALES SELL | 1h | 568 | -0.134% | +0.066% | -0.200% [-0.384..-0.042] | [-0.550..-0.103] | [-0.262..+0.306] | no effect |
| WHALES SELL | 4h | 582 | +0.088% | +0.215% | -0.127% [-0.639..+0.201] | [-0.869..+0.296] | [-0.521..+0.292] | no effect |
