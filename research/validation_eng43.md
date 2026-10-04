# eng-43 archive validation (2026-10-03 12:20 UTC: every queued run finished)

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
| market_profile: AUCTION LONG / SHORT | 681 / 156, 325 / 165 | -0.04 / -0.04 | -0.04 / -0.03 | +0.18 / +0.31 (crosses 0) | does not work |
| bollinger: BB M-TOP / W-BOTTOM | 48255 / 15306, 43762 / 12021 | -0.05 / -0.11 | -0.056 [-0.08..-0.03] / -0.111 [-0.15..-0.08] | +0.03 / -0.03 | does not work (significantly negative, q <= 0.004) |
| cup_handle: CUP HANDLE | 605 / 177 | -0.208 | +0.022 [-0.16..+0.22] | -0.518 [-0.74..-0.29] | does not work (far below placebo) |
| supply_demand: SD DEMAND / SUPPLY | 60 / 30, 12 / 2 | -0.14 / -1.31 | -0.08 / — | +0.17 (crosses 0) | does not work / too few |
| trendline: TRENDLINE UP / DOWN | 0 / 0 (687 + 159 cards, all NO_PLAN) | — | — | — | NOT MEASURED - a LIVE signal-logic bug (below) |

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
| B1 volatility forecast (425 coins; lags floored after review) | holdout QLIKE: LightGBM -5.2% (1h) / -0.2% (4h) vs HAR-RV; HAR-RV 14-23% better than ATR14 / max(ATR14, ATR 1h) | HAR-RV (pre-registered rule, unchanged in all three evaluations); prior period queued |
| G cross-sectional ranking (422 coins) | LightGBM gross +0.16% / 4h holdout, net -0.34%, DSR 0 | does not work - closed |
| B1 prior-period check 2023-10 .. 2025-03 (research/vol_b1_2023.md) | holdout QLIKE 1h: HAR 0.378 vs ATR14 0.269 (HAR worse; DM p 0.49 - a few outlier hours dominate the mean), 4h: HAR 0.230 vs ATR14 0.255 (+11%, p 0.09); MSE of log RV: HAR better than ATR14 in BOTH periods and horizons (0.31 vs 0.40, 0.32 vs 0.40); LightGBM best on every metric but never significant | by the pre-registered prior-period rule the QLIKE result is PERIOD-SPECIFIC: B1's "HAR beats ATR" is downgraded to "HAR beats ATR in log-MSE, not robustly in QLIKE"; no change to the stop unit on this evidence |
| Cards prior-period check (research/cards_eng43_2023.md, 359 coins) | SPRING dev -0.37R / holdout -0.54R (22 / 14 entries); SWEEP LOW holdout -0.29R [-0.40..-0.17], below placebo; SWEEP HIGH -0.08R; BULL F -0.36 / -0.15R | SPRING's main-window +0.36R does NOT repeat: period-specific (prior-period rule); nothing works in either period |
| Maniac prior-period check (research/maniac_eng43_2023.md, 351 coins) | AUCTION LONG holdout -0.51R (q 0.03); BB W-BOTTOM -0.07R; BB M-TOP -0.02R; CUP HANDLE -0.11R; SD DEMAND +0.53R [-0.20..+1.33] on 21 entries (main window: -0.08R); trendline again all NO_PLAN | nothing passes in either period |
| Scenario probability model, 18 months (research/scenario_model_eng43.md) | Brier skill vs the random-walk geometry -6.8% | NOT passed - the card keeps the geometric probability (models/scenario_prob.pkl NOT replaced) |
| Re-runs of the earlier studies to 2026-09 (*_rerun.md: HTF phases, level triggers, pumps, channels, EQH, daily trend, ensemble, positioning) | HTF: no cell positive with q <= 0.10 on the dev half; positioning: the most negative funding-level decile again underperforms in both halves (-0.42% / -0.63% per 24h vs the universe) - the same descriptive pattern whose pre-registered short holdout failed after costs (research/funding_holdout.md); the others as in research-findings | no change to the earlier conclusions |
| Classic prior-period check (research/classic_eng43_2023.md) | no VA80 / ORB / pump holdout interval above 0; RSI2 holdout +0.4% / +1.2% with intervals across 0 (placebo comparison invalid, as above) | consistent: does not work |
| G prior-period check (research/xsec_g_2023.md) | LightGBM gross +0.02% / 4h holdout, net -0.33%; momentum / reversal net -0.34% / -0.26% | does not work in either period - closed |
| C sticky HMM regimes (49k market candles, 18 months) | runs 7.2 vs 5.8 candles (GMM); neither separates the 4h Edge beyond +-0.03%; HMM uses 10 names vs 7 | keep GMM (no gain worth a logic change) |
| P(edge) retrain (18 months) + ml_eval | CPCV: AUC 0.539 (LightGBM) / 0.534 (logistic), top-20% Edge +0.047% over all rows, PBO 0.28, deflated Sharpe 0.76 (154 trials) | real but tiny ranking signal, far below the ~0.20% cost: stays SHADOW |
| Null-world ML audit (labels shuffled) | AUC 0.500-0.503, log-loss skill <= 0, DSR 0.09 | the ML pipeline does not invent signal (passes) |
| Null-world audit, 30 coins x 6 months (hours shuffled within weeks) | every card / classic setup: system - placebo intervals cross 0 (sweeps +0.23 / +0.09 n.s.); only RSI2 "beats" its placebo (+2.4 / +4.1%), the known unfair duration-matched placebo | the replay pipelines do not invent an edge (passes); RSI2's placebo comparison is invalid by design |
| Exit rules on the eng-43 samples (research/exits_eng43.md) | no strategy x exit rule chosen on development stays > 0 on the holdout (ALL be05_tp1 -0.28% market / -0.15% limit) | exits cannot make the entries pay |
| Meta-labeling on the eng-43 samples (research/meta_eng43.md) | the selected trades: -0.057R [-0.071..-0.045]; wyckoff predicted > 0 +0.167R on 44 trades (noise by the rule) | NOT PASSED - not shipped |

## Live signal-logic bug found (NOT fixed here: the brief forbids signal-logic changes in this session)
`TrendlineStrategy.plan` (strategies/maniac_strategies.py:161) asks for `'tp': ['map', 1.0]`, but `_confirm_plan` builds the
plan with `targets=[]`; `geometry.exit_target` reads the map targets from `plan['targets']`, finds none and returns None,
`system_levels` returns None and the plan is dropped (verified: `exit_target({'tp': ['map', 1.0]}, {'targets': [],
'target_src': []}, 100.0, 1.0, 1)` -> `(None, '', True)`; all 846 replayed trendline cards are NO_PLAN). Introduced by
eng-30 (58ad9f7). The live bot shares the code (signal_book -> strategy.plan): no trendline card can have been made since
eng-30. ORB (strategies/classic_strategies.py:40) uses the same `['map', 1.0]` through `_confirm_plan` and is probably dead
live too (research_classic replays ORB with its own exits, so the ORB verdict above is unaffected). Minimal fix: fill
`targets` / `target_src` in `_confirm_plan` with `select_targets(...)` as supply / demand does, then re-run the trendline
replay.

## Bugs found and fixed during the validation (all in research code, none in the signal logic)
research_turtle (illiquid days, N ~ 0: +-1e9 R), placebo time of day (all replay scripts), research_anomaly score sign,
HMM stable names, null-world alignment and daily candles, research_classic pump volatility index, research_vol zero-RV
lags, drift table thread safety, research_cache (pickle / path), queue pgrep self-match, container reclaimed when the
session idles (runs restarted by run_all.sh + a watcher).

## Confirmation study (2026-10-04; research_confirms.py, pre-registered in its docstring)

The archive replay now records every entry's confirmations as the live bot computes them (flow, spot, oi, CVD
divergence, vsa, htf_zone, SMT, kill zone; conf_n) with the 4h / daily / weekly context, the SPRING / UTAD test and the
maniac context vetoes; `--confirm record` enters every trigger so the minimum-confirmation rule is measured, not applied.

| window | entries passed the context vetoes | base R dev / holdout | splits passing the rule |
|---|---:|---|---|
| prior 2023-10 .. 2025-03 (research/confirms_2023.md) | 166 291 | -0.056 / -0.049 | none |
| main 2025-04 .. 2026-09 (research/confirms_main.md) | 151 455 | -0.080 / -0.073 | none |

- No single confirmation and no conf_n >= k threshold selects better trades in development AND holds in the holdout,
  in either window. conf_n >= 1 (the live minimum) cannot be tested: almost every trigger already has `flow`.
- Pattern seen in both windows: more confirmations look better in development (conf_n >= 4 / 5: +0.05..+0.06 R) and
  worse in the holdout (-0.08..-0.10 R); `vsa` flips sign (+0.03 R dev, -0.18 R holdout, prior window).
- `continuation` main-window holdout +0.145 R [+0.01..+0.28] on 119 entries, but -0.04 R in its development half and
  negative in both halves of the prior window: one positive sample out of four, not a pass.
- trendline (first test since the eng-44 fix): dev -0.05 R / holdout +0.02 R on 79 / 33 entries, intervals around 0.
- Not testable on the archive (live journal only): footprint order flow, multi-venue flows / perp-led, liquidations,
  books, Hyperliquid, Coinbase.
