# eng-43 archive validation (INTERIM, 2026-10-02 19:40 UTC)

Pre-registered rule (research/validation_eng43_prereg.md, CLOUD_RETRAIN.md): a strategy WORKS only if its mean net R is
> 0 in development AND holdout, the holdout 90% cluster-bootstrap interval is > 0, and system - placebo in the holdout
is > 0. Window 2025-04 .. 2026-09 (holdout from 2026-04-03), all 422 coins with a spot pair above the $3M floor,
pierce model fitted before the holdout (models/overshoot_pre.json). Placebos: the same trade at the same time of day on
another day within +-7 days (fixed 2026-10-02 after the null-world audit). Still running: research_maniac (supply /
demand, auction, trendline, Bollinger W/M, cup with handle), the prior-period check 2023-10 .. 2025-03, pretrain +
ml_eval. Sources: research/cards_eng43.md, classic_eng43.md, turtle.md, vol_b1.md, xsec_g.md.

## Strategies

| Strategy / setup | entries dev / holdout | R dev | R holdout [90%] | system - placebo holdout [90%] | Verdict |
|---|---|---:|---|---|---|
| sweep: SWEEP LOW | 885 / 394 | -0.120 | -0.075 [-0.143..-0.007] | -0.012 [-0.100..+0.080] | does not work |
| sweep: SWEEP HIGH | 598 / 210 | -0.035 | +0.018 [-0.074..+0.113] | +0.089 [-0.041..+0.219] | does not work |
| sweep against the trend (vetoed live) | 1800+1174 / 753+375 | -0.17 / -0.03 | -0.10 / -0.13 | — | does not work (the veto is right) |
| wyckoff: SPRING | 39 / 16 | +0.024 | **+0.356 [+0.040..+0.650]** | +0.360 [-0.226..+0.810] | does not work by the rule (placebo interval crosses 0); 55 entries: too few - the closest candidate |
| wyckoff: UTAD | 4 / 7 | — | — | — | too few entries |
| continuation: BULL F | 21 / 9 | -0.534 | — | — | does not work |
| continuation: BEAR D | 8 / 3 | — | — | — | too few entries |
| continuation: IMPULSE UP | 83 / 24 | -0.186 | -0.053 [-0.383..+0.305] | -0.286 | does not work |
| continuation: IMPULSE DOWN | 29 / 7 | +0.058 | — | — | too few entries |
| breakout (Turtles, daily, 459 coins, 2023-10 .. 2026-09) | 6650 / 1977 | -0.240 | -0.200 [-0.658..+0.185] | placebo -0.064 | does not work |
| market_profile: VA80 LONG / SHORT | 18739 / 6992, 17916 / 4908 | -0.22 / -0.51 | -1.07 / -0.16 | +0.06 / +0.01 (n.s.) | does not work |
| orb: ORB UP / DOWN | ~48k / ~16k each | -0.51 / -0.49 | -0.34 / -0.94 | +0.04 / -0.02 (n.s.) | does not work |
| connors: RSI2 LONG / SHORT (net %, no stop) | 494 / 233, 3197 / 1139 | +1.39% / +0.06% | -0.90% / -0.95% | (see note) | does not work (holdout mean < 0) |
| pump: PUMP START (without the live OI / spot conditions) | 14244 / 4636 | -0.068 | -0.079 [-0.113..-0.046] | -0.040 [-0.074..-0.005] | does not work (worse than placebo) |
| pump: PUMP TOP (5m shift entry) | 4430 / 1538 | -0.141 | -0.182 [-0.228..-0.139] | -0.076 [-0.141..-0.014] | does not work (worse than placebo) |
| supply_demand, auction, trendline, bollinger, cup_handle | running | | | | pending |

Notes
- Entries are few for the continuation and Wyckoff setups because the archive replay applies the live gates (displacement,
  OTE zone, tide, test volume, low_rr); the card counts are in research/cards_eng43.md.
- RSI2: the placebo holds the same DURATION, while the system exits on its own path-dependent rule (the first close
  beyond the SMA5) - "system - placebo" (+3..+5%) is therefore not a fair comparison and is not used. The verdict
  rests on the holdout mean (< 0). Shorts without a stop lost up to -565% on squeezes (BICO, ALPACA, SYN).
- Pump strategies lack their live OI / spot conditions in the archive (treated as passed): a live-only test remains.

## ML / models

| Item | Result | Decision |
|---|---|---|
| B1 volatility forecast (425 coins) | holdout QLIKE: LightGBM -7.3% (1h) / -0.4% (4h) vs HAR-RV; HAR-RV +15..20% better than ATR14 | HAR-RV (pre-registered rule); prior period queued |
| G cross-sectional ranking (422 coins) | LightGBM gross +0.16% / 4h holdout, net -0.34%, DSR 0 | does not work - closed |
| C sticky HMM regimes | runs 10.8 vs 7.2 candles (GMM) on eng-7 history | Edge split pending pretrain |
| P(edge) retrain + ml_eval (CPCV, PBO, DSR) | queued | pending |
| Null-world audit (6 coins) | found the placebo time-of-day bias; 30-coin run queued | pending |

## Bugs found and fixed during the validation (all in research code, none in the signal logic)
research_turtle (illiquid days, N ~ 0: +-1e9 R), placebo time of day (all replay scripts), research_anomaly score sign,
HMM stable names, null-world alignment and daily candles, research_classic pump volatility index, research_vol zero-RV
lags, drift table thread safety, research_cache (pickle / path), queue pgrep self-match, container reclaimed when the
session idles (runs restarted by run_all.sh + a watcher).
