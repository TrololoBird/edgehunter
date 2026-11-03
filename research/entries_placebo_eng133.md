# Entries vs placebo, shadow tags and macro features (eng-133 protocol)

Run `data/replay/eng133`; 2170 entries with a placebo (2292 usable, 1087 dev / 1083 holdout after the purge), split 2026-07-01; K = 100 copies, seed 133, 5000 bootstrap draws, block = 12 buckets (48 h); lifetime lag for Newey-West = 12.

## Families (net R at TP1 with the replay's exits; real minus placebo; 90% intervals)

| Setup | part | n | buckets | mean R [90%] | placebo mean | P90 placebo | real - placebo [90%] | q (holdout) | verdict |
|---|---|---:|---:|---|---:|---:|---|---:|---|
| AUCTION LONG | dev | — | < 30 | — | — | — | — | — |  |
| AUCTION LONG | holdout | — | < 30 | — | — | — | — | — | no verdict (< 30 buckets) |
| AUCTION SHORT | dev | — | < 30 | — | — | — | — | — |  |
| AUCTION SHORT | holdout | — | < 30 | — | — | — | — | — | no verdict (< 30 buckets) |
| BB M-TOP | dev | 111 | 75 | -0.121 [-0.204..-0.069] | -0.054 | +0.010 | -0.067 [-0.142..+0.008] |  |  |
| BB M-TOP | holdout | 115 | 73 | -0.075 [-0.136..+0.005] | -0.036 | +0.036 | -0.039 [-0.132..+0.047] | 1.000 | no evidence |
| BB W-BOTTOM | dev | 66 | 38 | -0.032 [-0.127..+0.088] | -0.050 | +0.068 | +0.018 [-0.049..+0.131] |  |  |
| BB W-BOTTOM | holdout | 85 | 56 | +0.045 [-0.003..+0.112] | -0.047 | +0.028 | +0.092 [+0.046..+0.182] | 0.092 | no evidence |
| BB1 DOWN | dev | 44 | 30 | -0.015 [-0.130..+0.018] | -0.102 | -0.040 | +0.087 [-0.046..+0.115] |  |  |
| BB1 DOWN | holdout | 64 | 47 | -0.015 [-0.097..+0.046] | -0.056 | -0.004 | +0.041 [-0.042..+0.100] | 0.958 | no evidence |
| BB1 UP | dev | 45 | 34 | -0.089 [-0.120..+0.027] | +0.000 | +0.073 | -0.089 [-0.142..+0.043] |  |  |
| BB1 UP | holdout | 57 | 47 | +0.041 [-0.099..+0.220] | -0.041 | +0.045 | +0.082 [-0.073..+0.272] | 0.912 | no evidence |
| BREAKOUT DOWN | dev | 75 | 55 | -0.027 [-0.059..-0.002] | -0.027 | -0.001 | +0.000 [-0.037..+0.021] |  |  |
| BREAKOUT DOWN | holdout | 48 | 38 | -0.037 [-0.052..-0.016] | -0.033 | -0.011 | -0.003 [-0.021..+0.030] | 1.000 | no evidence |
| BREAKOUT UP | dev | 84 | 70 | -0.023 [-0.115..+0.069] | -0.014 | +0.017 | -0.010 [-0.100..+0.076] |  |  |
| BREAKOUT UP | holdout | 88 | 71 | +0.112 [+0.037..+0.245] | -0.010 | +0.017 | +0.121 [+0.046..+0.257] | 0.249 | no evidence |
| DUMP BOUNCE SHORT | dev | — | < 30 | — | — | — | — | — |  |
| DUMP BOUNCE SHORT | holdout | — | < 30 | — | — | — | — | — | no verdict (< 30 buckets) |
| IMPULSE UP | dev | — | < 30 | — | — | — | — | — |  |
| IMPULSE UP | holdout | — | < 30 | — | — | — | — | — | no verdict (< 30 buckets) |
| ORB DOWN | dev | 192 | 85 | -0.192 [-0.268..-0.107] | -0.043 | +0.065 | -0.149 [-0.244..-0.052] |  |  |
| ORB DOWN | holdout | 196 | 98 | -0.182 [-0.339..-0.016] | -0.120 | -0.034 | -0.062 [-0.208..+0.101] | 1.000 | no evidence |
| ORB UP | dev | 210 | 102 | -0.279 [-0.407..-0.147] | -0.122 | -0.039 | -0.157 [-0.301..-0.003] |  |  |
| ORB UP | holdout | 155 | 82 | +0.134 [-0.112..+0.451] | -0.082 | +0.017 | +0.216 [-0.036..+0.540] | 0.580 | no evidence |
| RSI2 LONG | dev | — | < 30 | — | — | — | — | — |  |
| RSI2 LONG | holdout | — | < 30 | — | — | — | — | — | no verdict (< 30 buckets) |
| RSI2 SHORT | dev | — | < 30 | — | — | — | — | — |  |
| RSI2 SHORT | holdout | — | < 30 | — | — | — | — | — | no verdict (< 30 buckets) |
| SD DEMAND | dev | — | < 30 | — | — | — | — | — |  |
| SD DEMAND | holdout | — | < 30 | — | — | — | — | — | no verdict (< 30 buckets) |
| SD SUPPLY | dev | — | < 30 | — | — | — | — | — |  |
| SD SUPPLY | holdout | — | < 30 | — | — | — | — | — | no verdict (< 30 buckets) |
| SILVER BULLET LONG | dev | 60 | 45 | -0.112 [-0.264..+0.103] | -0.108 | +0.111 | -0.004 [-0.146..+0.209] |  |  |
| SILVER BULLET LONG | holdout | 53 | 44 | +0.072 [-0.316..+0.167] | -0.080 | +0.119 | +0.153 [-0.232..+0.267] | 1.000 | no evidence |
| SILVER BULLET SHORT | dev | 47 | 43 | -0.189 [-0.395..-0.065] | -0.117 | +0.086 | -0.072 [-0.300..+0.029] |  |  |
| SILVER BULLET SHORT | holdout | 73 | 54 | -0.204 [-0.390..-0.076] | -0.104 | +0.064 | -0.099 [-0.282..+0.026] | 1.000 | no evidence |
| SWEEP HIGH | dev | — | < 30 | — | — | — | — | — |  |
| SWEEP HIGH | holdout | — | < 30 | — | — | — | — | — | no verdict (< 30 buckets) |
| SWEEP LOW | dev | — | < 30 | — | — | — | — | — |  |
| SWEEP LOW | holdout | — | < 30 | — | — | — | — | — | no verdict (< 30 buckets) |
| TL EM DOWN | dev | — | < 30 | — | — | — | — | — |  |
| TL EM DOWN | holdout | — | < 30 | — | — | — | — | — | no verdict (< 30 buckets) |
| TL EM UP | dev | — | < 30 | — | — | — | — | — |  |
| TL EM UP | holdout | — | < 30 | — | — | — | — | — | no verdict (< 30 buckets) |
| VA80 LONG | dev | — | < 30 | — | — | — | — | — |  |
| VA80 LONG | holdout | — | < 30 | — | — | — | — | — | no verdict (< 30 buckets) |
| VA80 SHORT | dev | — | < 30 | — | — | — | — | — |  |
| VA80 SHORT | holdout | — | < 30 | — | — | — | — | — | no verdict (< 30 buckets) |

## Shadow tags (entries with the tag minus entries without; real net R)

| tag | part | with | without | diff [90%] | q (holdout) | verdict |
|---|---|---:|---:|---|---:|---|
| against_bias | dev | -0.080 | -0.118 | +0.039 [-0.113..+0.265] |  |  |
| against_bias | holdout | +0.100 | -0.047 | +0.147 [-0.114..+0.482] | 1.000 | no evidence |
| against_day | dev | — | — | — |  |  |
| against_day | holdout | — | — | — | 1.000 | no verdict (< 30 buckets) |
| against_trend | dev | — | — | — |  |  |
| against_trend | holdout | — | — | — | 1.000 | no verdict (< 30 buckets) |
| against_vwap | dev | — | — | — |  |  |
| against_vwap | holdout | — | — | — | 1.000 | no verdict (< 30 buckets) |
| discount | dev | — | — | — |  |  |
| discount | holdout | — | — | — | 1.000 | no verdict (< 30 buckets) |
| killzone | dev | — | — | — |  |  |
| killzone | holdout | — | — | — | 1.000 | no verdict (< 30 buckets) |
| low_rvol | dev | -0.247 | -0.109 | -0.137 [-0.246..+0.009] |  |  |
| low_rvol | holdout | -0.033 | -0.026 | -0.007 [-0.235..+0.258] | 1.000 | no evidence |
| no_htf_poi | dev | — | — | — |  |  |
| no_htf_poi | holdout | — | — | — | 1.000 | no verdict (< 30 buckets) |
| premium | dev | — | — | — |  |  |
| premium | holdout | — | — | — | 1.000 | no verdict (< 30 buckets) |

## Macro features (top tercile minus bottom tercile of the dev-half bounds; real net R)

| feature | bounds (dev terciles) | part | top | bottom | diff [90%] | q (holdout) | verdict |
|---|---|---|---:|---:|---|---:|---|
| xau_chg_1h | -0.116 / 0.101 | dev | -0.231 | -0.180 | -0.051 [-0.157..+0.064] |  |  |
| xau_chg_1h | -0.116 / 0.101 | holdout | +0.062 | -0.040 | +0.102 [-0.071..+0.282] | 1.000 | no evidence |
| xau_chg_24h | -0.688 / 0.305 | dev | -0.171 | -0.205 | +0.034 [-0.046..+0.148] |  |  |
| xau_chg_24h | -0.688 / 0.305 | holdout | -0.003 | -0.035 | +0.032 [-0.106..+0.180] | 1.000 | no evidence |
| oil_chg_1h | -0.202 / 0.24 | dev | -0.115 | -0.189 | +0.074 [-0.042..+0.194] |  |  |
| oil_chg_1h | -0.202 / 0.24 | holdout | -0.046 | -0.083 | +0.037 [-0.132..+0.215] | 1.000 | no evidence |
| oil_chg_24h | -1.74 / 1.05 | dev | -0.162 | -0.136 | -0.026 [-0.134..+0.066] |  |  |
| oil_chg_24h | -1.74 / 1.05 | holdout | -0.001 | +0.018 | -0.019 [-0.190..+0.148] | 1.000 | no evidence |
| spy_chg_1h | -0.0537 / 0.101 | dev | -0.119 | -0.419 | +0.299 [+0.141..+0.405] |  |  |
| spy_chg_1h | -0.0537 / 0.101 | holdout | +0.033 | +0.039 | -0.006 [-0.353..+0.253] | 1.000 | no evidence |
| spy_chg_24h | -0.0558 / 0.428 | dev | -0.168 | -0.300 | +0.132 [-0.016..+0.456] |  |  |
| spy_chg_24h | -0.0558 / 0.428 | holdout | — | — | — | 1.000 | no verdict (< 30 buckets) |
| qqq_chg_1h | -0.0657 / 0.137 | dev | -0.029 | -0.272 | +0.243 [+0.027..+0.406] |  |  |
| qqq_chg_1h | -0.0657 / 0.137 | holdout | -0.049 | -0.030 | -0.019 [-0.361..+0.127] | 1.000 | no evidence |
| qqq_chg_24h | -0.00194 / 0.823 | dev | -0.134 | -0.324 | +0.190 [+0.068..+0.539] |  |  |
| qqq_chg_24h | -0.00194 / 0.823 | holdout | — | — | — | 1.000 | no verdict (< 30 buckets) |
| vix_prev | 17.3 / 18.7 | dev | -0.141 | -0.108 | -0.034 [-0.123..+0.088] |  |  |
| vix_prev | 17.3 / 18.7 | holdout | — | — | — | 1.000 | no verdict (< 30 buckets) |
| fng | 17 / 28 | dev | -0.154 | -0.104 | -0.050 [-0.166..+0.033] |  |  |
| fng | 17 / 28 | holdout | — | — | — | 1.000 | no verdict (< 30 buckets) |
| etf_flow_1d | -146 / 11.8 | dev | -0.125 | -0.076 | -0.049 [-0.131..+0.055] |  |  |
| etf_flow_1d | -146 / 11.8 | holdout | -0.018 | +0.009 | -0.027 [-0.161..+0.075] | 1.000 | no evidence |
| etf_flow_3d | -387 / 31.3 | dev | -0.128 | -0.106 | -0.022 [-0.103..+0.065] |  |  |
| etf_flow_3d | -387 / 31.3 | holdout | -0.080 | -0.029 | -0.051 [—..—] | 1.000 | no evidence |
| dxy_chg_1d | — | — | — | — | — | — | no verdict (too few values) |

## Descriptive: horizon profile (no stop, no target; mark-to-market net R and MFE in R at 4 / 8 / 12 / 24 bars of the setup's timeframe; first 10 placebo copies)

| who | horizon (bars) | n | net R mean | MFE p25 | MFE p50 | MFE p75 |
|---|---:|---:|---:|---:|---:|---:|
| real | 4 | 2254 | -0.022 | +0.126 | +0.295 | +0.628 |
| real | 8 | 2254 | +0.027 | +0.172 | +0.405 | +0.869 |
| real | 12 | 2254 | +0.015 | +0.203 | +0.483 | +1.035 |
| real | 24 | 2239 | +0.007 | +0.284 | +0.672 | +1.432 |
| placebo | 4 | 18706 | -0.049 | +0.106 | +0.241 | +0.498 |
| placebo | 8 | 18704 | -0.036 | +0.156 | +0.347 | +0.735 |
| placebo | 12 | 18696 | -0.021 | +0.194 | +0.434 | +0.921 |
| placebo | 24 | 18588 | -0.070 | +0.274 | +0.626 | +1.284 |

## Descriptive: structural exit (BB W-BOTTOM / M-TOP: first touch of the SMA20; VA80 / AUCTION: POC not in the replay output, not computed)

- real_struct: n = 257, mean net R = -0.045
- placebo_struct: n = 2277, mean net R = -0.012

## Descriptive: counterfactual Cluster Cap (<= 2 cards of one side per 4h window, top by rr_tp1; NOT for production)

- without cap: n = 2170, mean = -0.064, total = -138.9, max drawdown = 173.8 R
- with cap: n = 1577, mean = -0.084, total = -132.6, max drawdown = 151.0 R

## Descriptive: measured correlation (pairwise mean of the replayed coins' 1h log returns) and N_eff

- mean pairwise correlation of 1h returns across 60 coins: rho = —
- same-side entries per 4h window: mean 2.02, p90 4, max 13; N_eff at the mean N = nan

## Counts

- placebo copies per entry: mean 55.3; entries without any placebo: 0; entries with < 100: 1237

## Notes from the cloud run (2026-10-16; added after the run, the numbers above are untouched)

- PASS rule applied mechanically: **no family, tag or feature passes**; every tested row is "no evidence" or "no verdict".
- Untested (no TP1 / too few buckets): Turtles, Connors (RSI2), band exits and every family marked "< 30 buckets".
- DXY (FRED DTWEXBGS) unavailable in the cloud ("Remote end closed connection"): no verdict, no substitute used.
- VIX / Fear & Greed: holdout "< 30 buckets" in a tercile - possibly the holdout's values all fall in the middle tercile of
  the dev bounds; not investigated.
- Placebo copies per entry: mean 55.3 of 100 (1237 entries below 100) - the matching (trend sign + ATR tercile, 3-14 d
  window) leaves fewer candidates than planned; the P90-of-placebo threshold is therefore noisier than designed.
- Script issues seen (not fixed, protocol frozen): the measured rho came out as "—"/NaN (numpy divide-by-zero warnings in
  the correlation step, likely a constant / empty return series); etf_flow_3d holdout interval "—" (`Mean of empty slice`,
  research_entries_placebo_eng133.py:295).
- Caveats from docs/CLOUD_eng133_placebo.md apply: one 8 h trade window for every timeframe (not the live lifecycle);
  revised ETF flows (mild look-ahead); placebo entry one minute earlier than a real one.
- Run: Python 3.14.6, 4 cores / 15 GB, 24 shards run 4 at a time (the container restarted twice; finished shards kept,
  interrupted ones re-run from scratch), `--workers 4`.
