# EdgeHunter documentation truth audit — 2026-11-17

## Scope and snapshot

This is a truth audit of the supplied AST extraction and the current `/opt/edgehunter` checkout. It is not a docstring rewrite and it does not change executable code.

- Git branch: `codex/edgehunter-stabilization`
- Git HEAD: `3835b909b7707a76e74e7a97731b3e7fed63c3d0`
- `all_docstrings.md` SHA-256: `65ee73741c730fcc074a6db9ec5288a167f7350286d03c224064418535256e41`
- Python files parsed independently: **139**
- AST docstrings independently counted: **1160**
- Parse errors: **0**
- Manual semantic records in batches 1–7 plus Party 9 subset and Parties 10–13: **349**
- Full per-record inventory: [`DOCTRUTH_LEDGER_2026-11-17.jsonl`](DOCTRUTH_LEDGER_2026-11-17.jsonl)

The ledger deliberately keeps unreviewed records as `UNVERIFIED` or `PROVENANCE_UNVERIFIED`; an inventory is not evidence. Only the records listed in the manual batches below have semantic verdicts.

Each JSONL record preserves the complete docstring, raw claim fragments, a bounded implementation excerpt, source coordinates, risk flags, evidence pointers, and (where available) external-source URLs. For records outside the manual batches, these fields are collection aids only and do not imply verification.

### Truth-audit rule (effective for this report)

`status`/`truth_status` is the conservative verdict about the claim in the docstring. `implementation_status` preserves the earlier code-local review and is not a truth verdict. A `CONFIRMED` or `CONFIRMED_LIMITED` implementation match therefore does **not** establish that a scientific, statistical, market, or methodological assertion is true. A positive truth status is retained only where the listed independent primary source supports the narrow proposition; source existence alone does not validate transfer to EdgeHunter.

## Status counts

| Status | Records |
|---|---:|
| `CONFIRMED_LIMITED` | 9 |
| `HYPOTHESIS_AS_FACT` | 1 |
| `IMPLEMENTATION_GAP` | 5 |
| `MISATTRIBUTED` | 16 |
| `OVERSTATED_SCOPE` | 107 |
| `PROVENANCE_UNVERIFIED` | 201 |
| `STALE` | 4 |
| `UNVERIFIED` | 817 |

Status semantics used in the truth ledger: `CONFIRMED`/`CONFIRMED_LIMITED` require a narrow independent-source proposition, not merely a code match; `OVERSTATED_SCOPE` = a source or principle exists but the docstring generalizes it; `MISATTRIBUTED` = a source is credited beyond what was checked; `HYPOTHESIS_AS_FACT` = model output is presented as an observed fact; `IMPLEMENTATION_GAP` = prose and current call path disagree (a code contradiction, not scientific confirmation); `STALE` = contradicted by the current checkout; `PROVENANCE_UNVERIFIED` = owner/audit/eng provenance is not established by the available record; `UNVERIFIED` = no sufficient independent evidence was established.

For comparison, the preserved implementation-review counts are: {'CONFIRMED': 18, 'CONFIRMED_LIMITED': 63, 'HYPOTHESIS_AS_FACT': 1, 'IMPLEMENTATION_GAP': 5, 'MISATTRIBUTED': 16, 'OVERSTATED_SCOPE': 107, 'PROVENANCE_UNVERIFIED': 201, 'STALE': 4, 'UNVERIFIED': 745}. Those counts describe source-local matching only and must not be read as truth confirmations.

Risk flags are overlapping: provenance 276, measurements/statistics 162, attributions 111, venue/API 199, mathematics 83.

## Manual batches 1–7 plus Party 9 subset and Parties 10–13: findings

### 1. `liq_est` is a synthetic model, not reconstructed market positions

`zones.py:486-544` describes a model from hourly OI changes, HLC3, a symmetric long/short allocation, a leverage mix, taker-buy share, maintenance margin, and proportional shrinkage. The docstring’s “estimated/model” qualifier is a useful qualification, but it is not independent evidence that the model is well calibrated. The stronger interpretation “real liquidation clusters” is not supported by the available inputs. The maintenance artifact is sourced from Bybit risk limits, while Binance’s current account API documents a signed `/fapi/v1/leverageBracket` endpoint with Binance-specific `maintMarginRatio` fields. [Bybit risk-limit docs](https://bybit-exchange.github.io/docs/v5/market/risk-limit) and [Binance leverage-bracket docs](https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Notional-and-Leverage-Brackets) support the venue-mismatch finding.

**Verdict:** `HYPOTHESIS_AS_FACT` for any wording that treats `liq_est` as observed Binance liquidity. The model qualifier itself remains `UNVERIFIED` as a truth claim until an independent calibration/identification study exists.

### 2. Hyperliquid values are real for queried accounts, not a Binance-wide sample

`positioning.py:174-207` is about `clearinghouseState`; the official Hyperliquid response specification lists fields such as `liquidationPx`, `positionValue`, `szi`, and leverage. The docstring’s broader “other traders” interpretation still lacks a population argument: the account set is selected from a separate monthly-volume leaderboard and used as a proxy. [Hyperliquid API docs](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals) confirm the field definitions, but do not establish that the chosen accounts represent Binance.

**Verdict:** `OVERSTATED_SCOPE` for market-wide/Binance representativeness. The existence of the individual fields is source-confirmed; that does not validate the EdgeHunter inference.

### 3. Volume Profile is OHLCV approximation

`zones.py:392-465` describes a construction that divides each candle’s quote volume equally among every high-low bucket and explicitly notes the lack of tick data. That identifies the claimed approximation; it does not independently validate POC, VAH/VAL, HVN or LVN as market profile measurements. They are outputs of the chosen discretization and expansion/smoothing rules, not exchange-native trade-at-price volume.

**Verdict:** `UNVERIFIED` as a truth claim about profile validity; implementation review `CONFIRMED_LIMITED`. Public wording should say `OHLCV-based approximated volume profile`.

### 4. Pierce documentation is stale and not reproducible from this checkout

`pierce.py:1-5` says “80 coins x 12 months.” The saved report says 260 coins, 2025-10-05..2026-09-30, and `models/overshoot.json` contains 260 coin rows. Git history shows the research script was later removed (`5258329`). The pooled coverage numbers can be quoted as a dated aggregate result; they do not prove per-coin stability.

**Verdict:** `STALE` for the docstring; the pooled report is `UNVERIFIED_REPRODUCIBILITY` without the removed script and inputs.

### 5. Scenario percentage and EV gate use different assumptions

`briefing_chart.py:156` calls `scenario_gate(0.5, ...)`, while `briefing_chart.py:162` separately reports the driftless expression `risk/(risk+reward)`. `core/quant_gate.py` correctly computes EV/break-even for the supplied `p_base`; it cannot turn 0.5 into an empirical probability.

**Verdict:** `IMPLEMENTATION_GAP`: formulas are valid within their assumptions, but the two outputs are not one calibrated probability model.

### 6. Osler is a valid source with a narrower scope

Osler’s primary report says the data are stop-loss/take-profit orders at a large FX dealing bank and examines three currency pairs. It supports clustering around round numbers in that FX sample. It does not validate the exact Binance/crypto stop placement or EdgeHunter’s `tol`, `pad`, P50/P80 thresholds.

**Verdict:** `OVERSTATED_SCOPE` when used as direct Binance evidence; `CONFIRMED_LIMITED` for the FX finding. [NY Fed SR 125](https://fraser.stlouisfed.org/docs/publications/frbnysr/frbny_sr125.pdf) and [NY Fed SR 150](https://www.newyorkfed.org/research/staff_reports/sr150.html) are the primary sources.

### 7. Spoofing, resiliency, OFI, and absorption are separate claims

The `depth.py` module docstring treats cancellation without a matched trade as a spoofing signature. CFTC/CME Rule 575 makes intent at order entry part of the definition; a cancellation-like observation cannot establish that intent. Fabre & Challet’s paper is a real primary source, but its 31% result is a model output for large orders in a specified crypto dataset and period, not a Binance-wide prevalence estimate. [CFTC/CME Rule 575 guidance](https://www.cftc.gov/sites/default/files/filings/orgrules/19/04/rule041119cmedcm001.pdf) and [Fabre & Challet](https://arxiv.org/abs/2504.15908) support those narrower statements.

The same docstring attributes a 5–10 second refill rule to Xu et al. The paper studies Chinese stock data and reports return to sample average within 20 best-limit updates, not a universal time threshold for crypto. Cont, Kukanov & Stoikov find a short-interval linear OFI/price relation in 50 NYSE stocks with slope inverse to depth; that does not support the categorical sentence that resting depth cannot matter over an hours horizon. [Xu et al.](https://arxiv.org/abs/1602.00731) and [Cont, Kukanov & Stoikov](https://arxiv.org/abs/1011.6402) are therefore scope-limited references.

Finally, execution, replenishment/resiliency, and absorption are not interchangeable observations. The EdgeHunter candle/delta rule is an absorption-like operational proxy; it does not identify passive fills, replenishment, or trader intent.

**Verdict:** `OVERSTATED_SCOPE` for the module-level claims; the 31% transfer to Binance remains unverified.

### 8. Binance force-order feed: exact sampling is now source-confirmed

The current official Binance USDⓈ-M documentation states that `!forceOrder@arr` updates at 1000 ms and, for each symbol, pushes only the latest liquidation order in that interval; no stream is pushed when no liquidation occurs. Bybit’s official `allLiquidation` page documents a separate 500 ms stream. These are venue-specific feed semantics and establish a lower-bound/sample interpretation, not a complete liquidation history across the market. [Binance force-order stream](https://developers.binance.info/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Mini-Tickers-Stream), [Bybit all-liquidation stream](https://bybit-exchange.github.io/docs/v5/websocket/public/all-liquidation)

**Verdict:** `CONFIRMED_LIMITED` for the Binance sampling statement; no completeness claim is confirmed.

### 9. Aggregate trades and sweep grouping

Binance’s USDⓈ-M specification says aggregate trades combine market trades that fill within 100 ms with the same price and taking side. It does not say that records at several prices with the same timestamp are guaranteed to be one parent taker order. The `SweepConfig` and `flow.py` module descriptions can therefore define a grouping heuristic, but “one taker order walking several levels” is too strong without parent-order identifiers. [Binance USDⓈ-M market-data specification](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data)

**Verdict:** `OVERSTATED_SCOPE` for parent-order identity; `UNVERIFIED` for any claim that the grouping is a validated whale detector.

### 10. Configuration claims in the same Party 2 slice

The `ZonesConfig` wording is an inventory and already calls its weights hypotheses; no independent evidence here establishes confluence or predictive value. `PositioningConfig` names real classes of public data, but Binance ratios have a defined account/position population and Hyperliquid values concern selected queried accounts, not all traders. `VenuesConfig` describes a normalization layer, not a complete or directly comparable multi-exchange market census.

The `PoolsConfig` paragraph is the most evidentially loaded of these entries. Benjamini–Hochberg is a genuine FDR procedure, but the source paper does not validate the project’s “proven negative” label or the reported −0.39R/−0.10R walk-forward result. The block-bootstrap construction, tested family, and eng-59 provenance need the original dataset and analysis record. The result is therefore `UNVERIFIED`.

`StrategiesConfig` has a narrower Elder basis: Elder’s primary material supports an approximate factor of five between related timeframes and a higher-timeframe strategic screen, but the EdgeHunter 3–6 range and mappings are project policy. `RiskConfig` has the same source-scope issue: exchange liquidation formulas use mark price, maintenance tiers, fees and other terms; `1/L − maintenance` is a rough screen without a documented error bound. [Elder excerpt](https://catalogimages.wiley.com/images/db/pdf/9780470181676.excerpt.pdf), [Bybit liquidation formula](https://www.bybit.com/en/help-center/article/UTA-Trading-Rules-Liquidation-Process), [Benjamini–Hochberg](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x)

**Verdicts:** `UNVERIFIED` for the confluence and internal pool-result assertions; `OVERSTATED_SCOPE`/`MISATTRIBUTED` for venue-population, venue-mapping, Elder, and simplified liquidation-formula scope.

### 11. Party 3: market factors, positioning, statistics, risk, and ML

`ZonesConfig` is explicit that its weights are hypotheses. That is the correct qualification. The remaining issue is dependence: several inputs can encode the same price history or volume state, so coincident signals are not independent votes. Cont–Kukanov–Stoikov study order-flow/depth price impact, not confluence scores; Harvey–Liu–Zhu show why searching many factor combinations creates false-discovery pressure. [Cont–Kukanov–Stoikov](https://arxiv.org/abs/1011.6402), [Harvey–Liu–Zhu](https://doi.org/10.1093/rfs/hhv059)

`PositioningConfig` names real data classes, but the populations differ. Binance’s official market-data documentation defines specific long/short account and position populations; Hyperliquid fields concern queried accounts. Dunbar–Owusu-Amoako and Smales study other positioning datasets and therefore provide contextual evidence, not validation of Binance top-trader ratios or the selected Hyperliquid sample. [Binance market-data docs](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data), [Dunbar–Owusu-Amoako](https://doi.org/10.1016/j.jbef.2023.100812), [Smales](https://doi.org/10.1002/fut.22332)

For `PoolsConfig`, Künsch supports block bootstrap for dependent stationary observations under conditions; Benjamini–Hochberg controls FDR under its assumptions, while Benjamini–Yekutieli addresses broader dependence. These method papers do not support EdgeHunter’s internal `eng-59` values, the “proven negative” label, or the claim that selected worst coins remain worst next month. [Künsch](https://doi.org/10.1214/aos/1176347265), [Benjamini–Hochberg](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x), [Benjamini–Yekutieli](https://doi.org/10.1214/aos/1013699998)

Elder’s factor-of-five idea is a real source attribution, but the 3–6 range and the listed crypto timeframe pairs are EdgeHunter policy. The liquidation-distance expression is an approximation: official Binance and Bybit formulas include mark price, maintenance tier, fees and other terms, so no exact safety guarantee follows without a venue-specific derivation and error bound. [Elder excerpt](https://catalogimages.wiley.com/images/db/pdf/9780470181676.excerpt.pdf), [Binance liquidation formula](https://www.binance.com/en/support/faq/detail/b3c689c1f50a44cabb3a84e663b81d93?hl=en), [Bybit liquidation formula](https://www.bybit.com/en/help-center/article/UTA-Trading-Rules-Liquidation-Process)

For ML, Isolation Forest, Gaussian-mixture/EM methods and streaming drift tools are legitimate algorithm families. Their existence does not establish anomaly-to-edge validity, regime semantics or calibrated `P(edge)`. Calibration is a separate empirical property; a model score is not a verified probability without temporal holdout, leakage controls and calibration evaluation. [Isolation Forest](https://doi.org/10.1109/ICDM.2008.17), [EM](https://doi.org/10.1111/j.2517-6161.1977.tb01600.x), [River ADWIN](https://github.com/online-ml/river/blob/main/river/drift/adwin.py), [probability calibration study](https://doi.org/10.1145/1102351.1102430)

**Verdicts:** confluence `UNVERIFIED`; positioning `OVERSTATED_SCOPE`; pool statistics and persistence `UNVERIFIED`; Elder attribution `MISATTRIBUTED`; liquidation distance `OVERSTATED_SCOPE`; ML module `OVERSTATED_SCOPE` and `P(edge)` validation `UNVERIFIED`.

### 12. Batch A: core contracts and execution boundary

The ledger also contains a code-local review of the core snapshot, data-validity, freshness, provenance, versioning, regime, and demo-execution docstrings. The checks confirm several narrow implementation facts (for example, `MarketSnapshot` rejects candles at or after `asof_ms`, `SystemValidityGate` raises for its listed missing inputs, `credentials()` reads only the two environment variables, and the BingX connector forces sandbox mode). They do not prove that every live path uses the shared replay API, that all data are fresh, that a model is scientifically valid, or that owner/policy language is authentic.

Two direct contract limits are recorded as `IMPLEMENTATION_GAP`: `MarketSnapshot` validates candle timestamps but contains no event collection, so “every candle/event” is broader than the type’s enforcement; and `executor.py` says credentials live in `config.local.toml` while the current `credentials()` implementation reads only environment variables. The remaining contract verdicts are intentionally limited to what is visible in the relevant source and call sites.

### 13. Model artifacts and statistical runtime

The current scenario model is not an accepted live model: `models/scenario_prob.pkl.manifest.json` carries `quarantine: true`, `source_dirty: 1`, and a legacy logic marker. `scenarios.load_model()` rejects that manifest, so the live probability path falls back to the geometric baseline. The historical report in `research/scenario_model.md` is useful as a dated observation, but its trainer was removed and its inputs/results are not reproducible from this checkout.

The same distinction appears in `ml.py` and `pretrain.py`. The live scanner’s `_score_anomalies()` is an explicit no-op, despite the module docstring describing IsolationForest as a replacement for Tier-0 rules. The pretrainer writes `success_generator='legacy-phases-v1'`, while `journal.pretrained_current()` requires `live-loopside-v1`; the current code therefore does not establish that this legacy artifact is a valid live model. `ml_eval.py` also names a dataset absent from the checkout. These are runtime/provenance gaps, not evidence that the underlying algorithms are mathematically invalid.

One stale implementation explanation was isolated in `stats.version_no`: it still describes the old `int('169e')` failure, while the shared parser now returns the numeric family `169`.

### 14. Strategy-method scope

The strategy batch distinguishes implementation from attribution. `ict.fvg_setup` is a concrete local FVG/MSS/CE rule, but its exact lookbacks and thresholds are not established as canonical ICT. The classic, Wyckoff, crypto-maniac, VSA, PO3, cascade, and cup-and-handle modules likewise contain explicit project adaptations; their names and cited authors do not validate the numeric rules or expected edge. The Turtle module implements the documented daily-channel mechanics locally, but full rulebook fidelity still requires a source-by-source comparison.

The statistical helpers expose one structural mismatch beyond provenance: `stats.cluster_of()` uses `floor(ts / 4h)` buckets, while its docstring says clusters represent overlapping 4-hour outcome windows. A fixed bucket is only a proxy for interval overlap, so confidence intervals built from it need a narrower description or an interval-based clustering implementation. The bootstrap, BH, PSR, deflated-Sharpe, haircut, and CSCV routines are present as deterministic calculations; their output still depends on assumptions, trial definitions, and data artifacts that are not validated by the function body.

Configuration review found the same distinction at the boundary: `LiquidationConfig` repeats the unversioned one-per-second feed claim, `MLConfig` exposes an IsolationForest while the live anomaly hook is disabled, and `StrategiesConfig` presents the Elder timeframe factor as if it were an enforced source rule. These are recorded in the ledger with source-local evidence and limited corrections.

The flow/geometry batch confirms the local transport and replay mechanics while keeping their market interpretation narrow. `FlowStore.quality()` can establish configured feed coverage and gaps; it cannot establish that a zero means no trading. `RushBook` explicitly lacks parent-order identity, and footprint/VPin-style metrics are diagnostics. `levels.simulate()` is a deterministic replay model with stated tie/fill assumptions, not an exchange execution audit.

### 15. Briefing archive, scoring, and dashboard boundaries

The briefing layer now writes scenario snapshots to `data/briefings.jsonl` and scores them under a rules-version filter and a fixed 72-hour horizon. The old `_save` docstring still says posts existed only in Telegram and could not be scored; that statement is stale. The scorer and `execution_model_v1` implement deterministic candle-replay conventions, including partial-hour handling, conservative stop/target ties, and mark-to-market unresolved records. Those mechanics do not establish real fills or predictive validity.

`key_zones` combines the saved overshoot quantiles with local trimming, caps, and merging. Its Murphy/Bulkowski/Osler wording therefore remains broader than the evidence: the external concepts do not validate the exact EdgeHunter parameters. The dashboard binds through `CONFIG.web.host` and defaults to `127.0.0.1`; “localhost only” is not an invariant when configuration or a public proxy changes that boundary. `sizing_view` correctly labels its Bybit first-tier maintenance calculation as an estimate.

### 16. Level and venue primitives

The lower-level review confirms the implementation boundaries behind the earlier findings. `zones.leverage_mix()` and `positioning._write_leverage_mix()` use a tracked Hyperliquid sample or a configured fallback; `zones.maintenance_of()` reads a Bybit-generated artifact or a constant, not Binance risk brackets. Daily POC, equal-level tolerance, balanced ranges, and zone merging are deterministic local operations, while their Dalton/ICT/classic labels do not establish source fidelity or market edge. `positioning.hl_levels()` returns bucketed levels for current tracked accounts and drops stale snapshots. Binance book snapshot sequencing and pruning are implemented, but they describe a bounded local book with resync assumptions, not complete market depth.

### 17. Journal statistics and classic contracts

The journal review confirms the arithmetic of Beta/Wilson intervals, block bootstrap plus BH filtering, conservative minute-bar replay, and multi-venue flow fallbacks. The phrase `proven_negative` is still a policy label conditional on its block construction, null, draw count, and tested family; it does not prove a population edge is negative. Similarly, `crowded` is a thresholded funding/premium/OI proxy. Classic strategy classes implement local ORB, value-area, and RSI(2) contracts with explicit risk overlays; their Dalton/Crabel/Connors names do not make those contracts literal source implementations. The confirmation module records measurable windows, but spot persistence, OI direction, and VSA/order-flow interpretations remain hypotheses until supported by dated validation data.

### 18. Briefing range, chart, and calendar corrections

The local `conf_tf`, `level_map`, `positioning_line`, and `_history_high` mechanics match their narrow descriptions. `session_bias` is a 4h EMA20/24h-return context tag; its 1–3 day horizon is not a validated forecast. `_bias_line` contains an unsupported “11 of 14 falling sessions” claim without a reproducible session list or current `research_bias.py`. `_extremes_24h` omits the leading partial hour when the current time is inside an hour, so it cannot guarantee an exact rolling 24-hour range.

`briefing_chart.py` has three stale interface claims: the module text says about three days of 1h candles, while `BARS=60` draws 4h candles; it says six zones while the label list has seven; and the visible card prints fee-adjusted break-even `p_breakeven`, not the driftless `rw_prob` described in the module text. The current render path is recorded separately from those stale claims.

The `key_zones`/`plan` use of P50/P80 is also narrower than the prose suggests. The overshoot report conditions on rejections that returned; it measures penetration depth within that selected outcome class. It does not estimate retest success, acceptance, level survival, or an optimal stop buffer. The current use as `tol` and `pad` is an engineering heuristic pending a separate decision/outcome study.

The calendar path is layered: `macro_today()` uses official events and the fresh weekly feed when available, then publication rules as a fallback. The fallback cannot know rescheduled releases, and `macro_today()` itself does not enforce official source freshness. `official_calendar` has explicit source freshness/coverage checks, while the older `macro_calendar` module heading still describes the pre-official hand-list architecture.

### 19. Bias attribution and trendline exemption

`strategies/bias.py` computes a valid local feature set: simple 30/90/365-day return signs, weekly EMA20, daily/4h EMA50 slopes, and ADX14. That is not the Moskowitz–Ooi–Pedersen futures methodology or a complete Elder Triple Screen. The top-down and Elder language is therefore recorded as `OVERSTATED_SCOPE`/`MISATTRIBUTED`; the cited academic paper supports a narrower time-series-momentum concept, not this crypto feature blend. [Moskowitz, Ooi & Pedersen](https://doi.org/10.1093/rfs/hhq150)

The trendline exemption is implemented, but the cited report has only 10 allowed versus 68 blocked trades and the research script is absent from the current checkout. Its sign is suggestive but not independently reproducible or sufficient to establish the policy.

### 20. Party 4: event risk, listings, delistings and external data

`event_risk.py:1` has a real Keyrock source, but the source’s 90%/16,000+/30-day result is a commercial, sample-specific observation. Animoca’s separate public summary uses a different sample and reports a different conditional effect, so neither result establishes a universal bearish unlock filter. RockawayX covers Binance, Bybit and MEXC rather than Upbit; The Tie reports a broader listing sample; CoinSight’s Upbit figures are descriptive post-announcement returns. Spot delisting, futures delivery and Upbit termination are distinct events, so a fixed long veto needs its own calibration. DefiLlama’s current API documentation places the emissions endpoints in the paid Pro API, while the phrase “no free calendar” still needs to distinguish public pages and free endpoints. [Keyrock](https://keyrock.com/from-locked-to-liquidity-what-16000-token-unlocks-teach-us/), [Animoca Brands Research](https://www.smartkarma.com/insights/the-impact-of-token-unlock-events-on-cryptocurrency-prices-an-empirical-analysis), [RockawayX](https://www.rockawayx.com/insights/bullish-or-bearish-what-really-happens-when-tokens-list-on-a-cex), [DefiLlama Pro API](https://api-docs.defillama.com/llms-pro.txt)

`extdata.py:1` is partly source-correct and partly over-interpreted. DVOL is a 30-day annualised implied-volatility index, but it is not direction or crash probability. Put/call OI describes option inventory, not net delta. Hyperliquid’s `predictedFundings` endpoint is real but venue intervals and timestamps must be normalized; Bybit’s 50-level orderbook is a selected depth; and Deribit public OI has been eight hours delayed since 2026-11-10. The ETF D+1 08:00 rule is an operational cutoff, not a universal provider timestamp. [Deribit DVOL](https://insights.deribit.com/exchange-updates/dvol-deribit-implied-volatility-index/), [Deribit OI publication change](https://support.deribit.com/hc/en-us/articles/40275495462301-10-November-2026), [Hyperliquid predicted funding](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals)

**Verdicts:** `event_risk.py` module and Upbit veto `OVERSTATED_SCOPE`; external-data module `OVERSTATED_SCOPE`; `us_session` `CONFIRMED_LIMITED`; dominance interpretation `UNVERIFIED`.

### 21. Party 5: order flow, VPIN, footprint and large orders

The VPIN paper defines a toxicity metric, but the EdgeHunter calculation is an adaptation and not a calibrated probability of informed trading. Andersen and Bondarenko’s critique shows that predictive claims depend on volume, volatility and trade classification. A maximum one-hour correlation does not prove venue leadership. [Easley, López de Prado & O’Hara](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1695596&rec=1&srcabs=1748633), [Andersen & Bondarenko](https://doi.org/10.1016/j.finmar.2013.05.005)

La Morgia et al. study organized pump-and-dump detection, not parent-order reconstruction from Binance aggTrades. RushBook is therefore a project heuristic even though its docstring discloses the missing parent-order ID. Finished-auction side conventions are supported by footprint references, but the local share threshold and reversal interpretation remain heuristics. The `absorption_in` condition is a candle/delta proxy; it does not prove passive execution or replenishment. The `mean 1m range × sqrt(15)` value is a range proxy, not Wilder ATR(15m), whose true range includes the previous close and uses smoothing. [La Morgia et al.](https://arxiv.org/abs/2005.06610), [TradingView footprint guide](https://www.tradingview.com/support/solutions/43000726164-volume-footprint-charts-a-complete-guide/), [Wilder volatility](https://download.esignal.com/products/workstation/help/charts/studies/wilders_volatility.htm)

**Verdicts:** VPIN/lead venue `OVERSTATED_SCOPE`; RushBook `OVERSTATED_SCOPE`; finished-auction convention `CONFIRMED_LIMITED`; absorption and sqrt-time ATR `OVERSTATED_SCOPE`.

### 22. Party 6: iceberg, seasonality, intervals, and journal statistics

All records `DOC-0314` through `DOC-0362` now carry the Party-6 review scope. The specific findings below cover the substantive scientific, statistical and microstructural claims; the remaining operational or provenance entries are explicitly retained as `UNVERIFIED`/`PROVENANCE_UNVERIFIED`, not treated as verified merely because their code-local wording is readable.

The iceberg source is real and narrowly supports the definition of a partially disclosed order that replenishes after execution; repeated replenishment can help market participants discover it. It does not make a same-price refill in 500 ms L2 snapshots proof of one hidden order. Independent orders can replace one another at the same price, snapshots can miss intervening changes, and the public feed has no parent-order identifier. The EdgeHunter result is therefore an `iceberg-like replenishment` candidate, not verified hidden volume or “whale accumulation.” [Iceberg research](https://onlinelibrary.wiley.com/doi/full/10.1111/jfir.12414)

The seasonality attribution is directionally valid but narrower than the docstring. Andersen–Bollerslev and Boudt–Croux–Laurent support intraday periodicity and the value of accounting for it; Hansen–Kim–Kimbrough separately document recurring crypto volatility and volume patterns. EdgeHunter’s four-week UTC-hour medians, weekend ratios, clipping, and trailing-24h scaling are an adaptation, not a literal implementation of those estimators. The sqrt-time volatility normalization has the usual independent/stationary-increment assumptions and is only a proxy when applied to clustered, jump-prone crypto series. [Andersen–Bollerslev](https://doi.org/10.1016/S0927-5398(97)00004-2), [Boudt–Croux–Laurent](https://doi.org/10.1016/j.jempfin.2010.11.005), [crypto periodicity](https://arxiv.org/abs/2109.12142), [Common intraday periodicity](https://cris.maastrichtuniversity.nl/en/publications/common-intraday-periodicity-2/)

Wilson’s score interval and the Beta–Binomial posterior are mathematically legitimate for their respective models. Wilson’s 95% upper bound is not a correction for clustered trades, selection, or multiple testing; a Beta posterior also depends on the prior and likelihood and is not a frequentist confidence bound. The ledger consequently retains positive truth status only for these narrow definitions, not for their use as calibrated trading probabilities. [Wilson (1927)](https://doi.org/10.1080/01621459.1927.10502953), [Beta–Binomial conjugacy](https://openacttextdev.github.io/LDA_Ed2/ChBayes.html)

`P(edge)` and the online-learning claims remain scope-limited. Updating after a recorded exit is a necessary temporal-order rule, but calibration requires a defined event/horizon, point-in-time features, temporal holdout, leakage controls and reliability checks. A model marker or a score of 0.78 is not evidence that the event occurs 78% of the time. [Calibration study](https://doi.org/10.1145/1102351.1102430), [Bailey et al. on backtest overfitting](https://escholarship.org/uc/item/4w1110bb)

The journal’s `proven_negative`, `independent 4h blocks`, and confirmation-promotion language is too strong. Künsch supports block bootstrap for dependent stationary observations under conditions; BH controls FDR only under its dependence assumptions, with BY addressing a broader class. Four-hour bucket IDs do not establish independence, a rejected null does not prove a negative population mean, and a negative result without a confirmation does not prove that requiring it improves Edge. The direct comparison is `Edge_with − Edge_without` on comparable, untouched data. [Künsch block bootstrap](https://doi.org/10.1214/aos/1176347265), [Benjamini–Hochberg](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x), [Benjamini–Yekutieli](https://doi.org/10.1214/aos/1013699998)

MFE/MAE and the same-minute SL-first rule have narrower meanings: MFE/MAE are excursion summaries, post-stop movement is not evidence of a stop raid, and SL-first is a conservative replay convention rather than observed intraminute execution. The `0.11%` universe statistic and `x1.0/x1.4` anomaly ratios are local descriptive claims without independent sample artifacts. Shadow exits with `0.7 ATR` and retest are exploratory hypotheses, not source-backed optimal rules.

**Verdicts:** iceberg detection, seasonality transfer, sqrt-time volatility, `P(edge)`, post-stop raid, shadow exits, “proven negative”, independent blocks, anomaly-effect interpretation, and confirmation promotion are `OVERSTATED_SCOPE` or `UNVERIFIED`; Wilson and Beta definitions are `CONFIRMED_LIMITED` only for their narrow mathematical statements; the remaining empirical values stay unverified.

### 23. Party 7: Fibonacci, Wilder/Wyckoff, execution, and macro point-in-time data

All records `DOC-0374` through `DOC-0407` carry the Party-7 review scope. The Fibonacci arithmetic is valid as geometry: if a target is fixed at 0.382 of a leg and the stop floor is fixed, `min_stop_atr / 0.382` follows algebraically. The Fibonacci sequence or the ratios 0.382/0.618 do not prove that price reacts at those levels or that the resulting filter has positive expectancy. Empirical work has not established Fibonacci retracement as a universal standalone rule. [Marshall, Young & Rose](https://doi.org/10.1016/j.jbankfin.2005.08.001), [Fibonacci retracement study](https://doi.org/10.1016/j.eswa.2021.115893)

Wilder attribution is narrower and defensible: the seeded mean followed by `y += (x-y)/n` is the RMA/Wilder smoothing recurrence, and ATR uses smoothed true ranges. The owner decision and the reported 25–40% difference between competing measures are project provenance/measurement claims, not universal properties. [TA-Lib RMA](https://ta-lib.org/functions/rma.html)

The 2/2 swing, opposite extreme, duration buckets, and Fibonacci leg map are EdgeHunter operational definitions. They should not be presented as canonical Dow/Elliott impulse structure. Wyckoff Stock Market Institute does support lower volume and narrower spread as quality characteristics of a spring test, while the configured ratios, minute-volume proxy, and sqrt-time spread conversion remain project heuristics. [Wyckoff test of springs](https://wyckoffsmi.com/test-of-springs/)

The execution functions are replay models. Binance documents that stop orders may trigger from Last or Mark Price, that a stop-market order becomes a market order, and that execution can differ from the trigger during volatility. Funding intervals are contract-specific and can change from the default eight-hour schedule. Therefore fixed slippage, first-full-minute fills, same-candle SL-first, and one-rate-per-hold funding are assumptions, not exchange execution facts. [Binance stop orders](https://www.binance.com/en/support/faq/detail/360036351051), [Binance funding](https://www.binance.com/en/support/faq/detail/360033525031)

The FRED/ALFRED point-in-time distinction is confirmed: FRED’s current view is not the historical information set, while real-time periods, vintages, and initial-release output are available through ALFRED/FRED services. The exact DTWEXBGS, DCOILBRENTEU, and DGS10 availability delays still need per-series release calendars and cannot be inferred from observation dates. [FRED versus ALFRED](https://fred.stlouisfed.org/docs/api/fred/fred_vs_alfred.html), [Real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html), [FRED observations/vintages](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)

Official BLS, ISM, and Federal Reserve calendars are legitimate primary schedule sources. They do not prove that a future entry is final, or that a CPI/FOMC event will widen spreads, run stops both ways, or determine the move instead of a setup. `live_ok` also needs clearer state separation: no event found, source missing, official schedule incomplete, and new entries blocked are different conditions. [BLS iCalendar](https://www.bls.gov/help/hlpiCAL.htm), [ISM release calendar](https://www.ismworld.org/supply-management-news-and-reports/reports/rob-report-calendar), [FOMC calendar](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)

**Verdicts:** Wilder recurrence, point-in-time availability, and official calendar source identity are `CONFIRMED_LIMITED`; Fibonacci effectiveness, impulse-leg attribution, Wyckoff numeric thresholds, execution/funding formulas, fixed macro delays, macro price-effect language, and fail-open/fail-closed terminology are `OVERSTATED_SCOPE` or `UNVERIFIED`.

### 24. Party 9 subset included in the submission: overshoot, pool selection, and Hyperliquid positioning

The submitted follow-up records `DOC-0473`, `DOC-0478`, and `DOC-0482`–`DOC-0492` were reviewed under an explicit Party-9 subset scope; this does not imply that the skipped Party 8 is complete. `official_calendar.py` is source-correct in naming BLS, ISM, and Federal Reserve schedules, with the scheduled/unconfirmed distinction retained.

The overshoot documentation is stale where it says “80 coins × 12 months”; the saved model/report describe a later 260-coin window. Even with a half-sample comparison, pooled conditional rejection quantiles do not establish future stop-buffer stability. Pool selection from journal outcomes is a data-snooping/selection problem unless the selected universe is frozen and evaluated on untouched point-in-time data. [FRED/ALFRED point-in-time guidance](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html), [Bailey et al.](https://escholarship.org/uc/item/4w1110bb)

Hyperliquid’s public `clearinghouseState` can expose `szi`, leverage, `positionValue`, and platform-provided `liquidationPx` for a queried address. That does not identify all accounts of one owner, all large traders, or a representative Binance sample. The selected-account leverage mix and `liq_hl` buckets are platform-reported snapshots/estimates for the chosen accounts, not guaranteed future liquidation executions or a market-wide map. [Hyperliquid Info API](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals)

**Verdicts:** official calendar source identity `CONFIRMED_LIMITED`; stale overshoot text `STALE`; pool selection, market-wide Hyperliquid claims, leverage extrapolation, and “real” liquidation-level wording `OVERSTATED_SCOPE`; remaining operational records stay `UNVERIFIED` or `PROVENANCE_UNVERIFIED`.

### 25. Party 10: historical pretraining, archive scope, and pump candidates

The pretraining docstrings describe a useful research task, but the phrase “the journal rows the bot would have written” exceeds what the archive can establish. Binance’s public archive contains historical klines, trades and related files, with daily/monthly publication rules and a documented correction/update process. That makes it a source of historical market data, not an immutable point-in-time copy of every live information set. Historical file availability, retrieval time and later correction time must be recorded separately from the candle’s event time. [Binance public-data README](https://github.com/binance/binance-public-data/blob/master/README.md)

The missing inputs listed by the docstring are material: there is no complete historical order book, liquidation stream, other-venue flow, Hyperliquid account state, Coinbase premium, whale-sweep identity or historical live IsolationForest verdict in the cited archive. The strongest defensible description is “historical approximation using the available archive feature set.” Rebuilding complete candles from one copy of every constituent minute is a conservative aggregation convention; it does not prove that the underlying archive is complete, immutable, or equivalent to the live event stream.

The point-in-time universe language is directionally correct but narrower than “all historical Binance USDT perpetuals.” A spot-pair requirement changes the population, and carried-forward eligibility after too few daily observations is a stale-policy state rather than a fresh 30-day liquidity confirmation. The ledger therefore records the universe and live-equivalence claims as `OVERSTATED_SCOPE`, while keeping the minute-bucket rule source-limited.

The `P(edge)` target is also a different object from trade profitability. The documented label is relative: `R_asset > R_median(universe)` over the stated horizon. A coin can beat a negative median while still losing money. The reported `~0.11%` mean-minus-median result is a local statistic whose value depends on universe composition, dates, weighting and dependence; it is not a market constant or a net-return probability. The label should be named `beat_median_universe` and kept separate from `P(trade)` after costs.

The pump module’s 15%/6h/3x rule is a price-volume candidate detector. The primary pump-and-dump studies use additional evidence such as coordinated communications, event structure or wallet-level behavior: Xu and Livshits analyze 412 Telegram events, Hamrick et al. analyze Discord/Telegram event samples and popularity differences, and Li, Shin and Wang use wallet-level and quasi-experimental evidence. Those sources support the existence of coordinated manipulation research; they do not turn EdgeHunter’s thresholds, Fibonacci pullback or 1.618 target into a detector of proven manipulation or a validated trading edge. [Xu and Livshits](https://www.usenix.org/system/files/sec19-xu-jiahua_0.pdf), [Hamrick et al.](https://par.nsf.gov/servlets/purl/10251729), [Li, Shin and Wang](https://doi.org/10.1017/S0022109025000201)

The internal `+0.17R`, `+0.16R`, `+0.36R` and `+0.34R` figures remain project results. The current inventory does not provide an independent dataset, pre-registration record, random-walk specification, confidence interval, or untouched forward holdout sufficient to promote them to external evidence. “Untouched” and “pre-registered” should be retained only when the time of rule freeze and the complete analysis protocol are documented.

**Verdicts:** historical live-signal reconstruction, immutable point-in-time archive, carried-forward eligibility, and pump-and-dump interpretation are `OVERSTATED_SCOPE`; the concrete mean/median and R figures remain `UNVERIFIED`; Wilder ATR naming in the pump helper is only a narrow indicator-definition claim.

### 26. Party 11: replay, strategy-audit scope, and execution counterfactuals

`replay.py` is more accurately a historical lifecycle approximation. Closed one-minute candles cannot recover the live order-book state, liquidation events, other-venue flows, sub-minute detector timing or actual queue conditions. The docstring’s own missing-data list is evidence for this limitation; it is not a basis for calling the output a live-equivalent card lifecycle. [Binance public-data README](https://github.com/binance/binance-public-data/blob/master/README.md), [OHLC intrabar ambiguity](https://arxiv.org/abs/1412.5558)

The `research/exit_bt/audit.py` record is a detector-plus-simplified-exit study. Because it omits vetoes, confirmations and LTF triggers, its result is not a full Strategy audit. The ICT audit adds another model assumption: when a 5m bar touches the FVG CE, it assumes a resting limit fill. OHLC contact does not reveal queue position, partial execution, cancellation, or the order of intrabar trades. A queue-aware study is needed before “filled” can describe an observed execution. [Limit-order queue-position study](https://ora.ox.ac.uk/objects/uuid%3A0ab2bc82-2098-406b-b962-c6134402a0a4/files/m76ce75d22bc144a6cf57d2df85b67cba)

The ORB/Turtle backtest’s stop-first and next-bar trailing rules are defensible conservative conventions for ambiguous OHLC bars. The fixed 0.20% round-trip cost is a scenario parameter, not the realized cost of every symbol, size and liquidity regime; fees, spread, impact, funding and partial fills vary. The demo BE/re-entry record is a counterfactual comparison of an actual baseline with a simulated alternative. It cannot establish what would have happened under real execution, and the “owner’s proposal” wording remains `PROVENANCE_UNVERIFIED` without a primary decision record.

**Verdicts:** live-lifecycle replay, full Strategy audit, CE-touch-as-fill, universal 0.20% cost and executed BE/re-entry interpretation are `OVERSTATED_SCOPE`; stop-first and next-bar trailing remain bounded replay conventions; owner/proposal language requires separate provenance evidence.

### 27. Party 12: market regime, BTC context, scenario probabilities, and ICT/phase labels

The statement that one market factor explains “about half” of all coin moves is not a verifiable fact until the factor, horizon, universe and statistic are specified. Crypto factor research identifies common market, size and momentum factors, while Bitcoin-to-altcoin spillover estimates vary across assets and bull/bear regimes. These findings support a market-context feature, not a universal BTC `R² = 0.5` rule. [Common crypto risk factors](https://www.sciencedirect.com/science/article/pii/S026499931931020X), [Bitcoin-to-altcoin spillovers](https://www.mdpi.com/1911-8074/16/1/41)

The BTC momentum and weekly/daily prior-high/low rule are operational filters. Calling the latter “ICT bias” does not establish that the exact rule is canonical ICT, nor that it is optimal. A prior-high/low close, market-structure shift, liquidity sweep and higher-timeframe bias are related but non-equivalent concepts. The eng-59/eng-100/eng-149 references remain provenance tokens unless the primary decision records are attached.

`OI / 24h volume` is not leverage. CME defines volume as contracts traded and open interest as contracts remaining open; their ratio is a relative activity/open-interest feature and does not reveal a participant’s equity, margin or position leverage. Likewise, `R_coin − beta·R_BTC`, standardized by residual volatility, is a factor-adjusted residual. Its interpretation depends on beta window and regime; it is not causal or absolute strength. [CME open interest](https://www.cmegroup.com/education/lessons/open-interest)

The scenario formula `d_down / (d_up + d_down)` is a valid infinite-horizon hitting probability for a driftless symmetric random walk/Brownian idealization. It is a geometric benchmark, not a forecast of a crypto path. Drift, discrete sampling, changing levels and a finite horizon require a different first-passage model. The claim that the alternative model is walk-forward and calibrated requires frozen point-in-time features, non-overlapping or dependence-aware labels, out-of-sample predictions, baseline comparison and reliability results. [MIT Brownian crossing notes](https://www.bssve.in/StudyMaterials/MF002.pdf), [probability calibration study](https://doi.org/10.1145/1102351.1102430)

Returning `None` for a bar that touches both scenario boundaries is a defensible conservative OHLC convention, but removing those bars changes the target to a conditional label. The excluded fraction and its dependence on volatility, barrier distance and timeframe must be reported. The scenario ladder’s swings, equal levels, prior periods, profile and round numbers are feature sources; their confluence is not independent evidence, and `merge_atr`/`min_strength` remain project parameters.

The PhaseScorer docstring correctly calls its weights hypotheses, but its semantic labels are stronger than the aggregate inputs allow. Price/OI combinations show expansion or contraction of open exposure, not uniquely new longs, new shorts or long liquidation. CVD divergence and flat price can be absorption-like, but do not identify a passive buyer. Spot/perp flow separation is useful context; “spot-led is sturdier” is an empirical hypothesis requiring matched event results. The OR-based Tier-0 anomaly detector also needs joint false-positive and overlap measurements.

Phase A, C, D, E and F should be named `accumulation-like`, `distribution candidate`, `breakdown candidate`, `capitulation candidate` and `markup/momentum candidate` unless direct evidence supports the stronger event. The Wyckoff source supports the spring concept and the importance of supply/test behavior, but not EdgeHunter’s exact 20-candle, ATR, close-location and delta thresholds. Bollinger’s official Method I material supports the volatility-breakout idea, not the added OI/funding/delta filters. [Wyckoff spring tests](https://wyckoffsmi.com/test-of-springs/), [Bollinger Method I](https://bollingerbands.us/help-methods.php)

Closed-candle scoring prevents one narrow class of in-progress-bar changes. It does not by itself prove pipeline-wide absence of look-ahead: MTF joins, pivot confirmation, funding/OI availability, archive vintages and publication delays need separate point-in-time checks. The sampled Binance force-order stream can support observed liquidation messages with feed limitations; OI/volume/price patterns alone remain indirect proxies. [Binance force-order stream](https://developers.binance.info/docs/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Mini-Tickers-Stream)

**Verdicts:** BTC “half the market” and `OI/volume = leverage` are `OVERSTATED_SCOPE`; the exact ICT label is `MISATTRIBUTED` with unresolved provenance; geometric first-touch probability is a valid benchmark but the calibrated-model claim is `OVERSTATED_SCOPE`/`UNVERIFIED`; phase names carry a `MISATTRIBUTED` Wyckoff attribution, while price/OI direction, absorption, spot-led reliability, numeric rules and Bollinger extensions remain `OVERSTATED_SCOPE`; closed-candle scoring is only a local look-ahead safeguard.

### 28. Repeat review: corrections to the Party-12 interpretation

The second primary-source pass narrows several earlier statements. The factor papers cited for `scanner.py:_update_market_state` construct market/size/momentum factors; they do not report a universal BTC explanatory share of 50%. A separate high-frequency study describes Bitcoin’s explanatory power as weak, while the IMF’s approximately 80% result is a latent common crypto factor for a specified seven-token panel. None of these results can be converted into the EdgeHunter sentence without a per-asset regression, explicit `R²` aggregation and a dated sample. [Liu–Tsyvinski–Wu](https://www.nber.org/system/files/working_papers/w25882/w25882.pdf), [Liu–Liang–Cui](https://www.sciencedirect.com/science/article/pii/S026499931931020X), [Liu–Marsh–Mazza–Petitjean](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3389152), [IMF crypto factor](https://www.imf.org/-/media/files/publications/wp/2023/english/wpiea2023163-print-pdf.pdf)

The terminology correction for `OI / 24h volume` is final: it is an OI-to-volume or relative-open-interest ratio, not leverage. CME’s definitions distinguish contracts traded from contracts still open; neither field supplies account equity, margin or notional exposure. The BTC residual is a valid factor-adjusted construction only after its beta window, update schedule and stability are specified. [CME open interest](https://www.cmegroup.com/education/lessons/open-interest), [CME futures guide](https://www.cmegroup.com/content/dam/cmegroup/education/files/a-traders-guide-to-futures.pdf)

The `BTC ICT bias` label is now recorded as `MISATTRIBUTED`: closing beyond the previous high/low is a generic higher-timeframe breakout filter. The audit found no primary passage establishing this exact weekly/daily rule as ICT’s complete bias methodology; its origin also remains unverified. A source-backed ICT attribution would need to distinguish sweep, displacement and market-structure shift from a simple breakout.

The strongest correction concerns the six-label phase taxonomy. Wyckoff accumulation and distribution schematics use phases A–E. In accumulation, Phase A stops the prior downtrend, Phase B builds cause, Phase C tests remaining supply and may contain a Spring, Phase D shows demand control, and Phase E is the markup outside the range. Distribution is a separate mirrored schematic; `dump` and `capitulation` are not additional canonical phases. The EdgeHunter sequence `A accumulation / B Spring / C distribution / D dump / E capitulation / F markup` therefore misattributes a project classifier to Wyckoff. [StockCharts Wyckoff tutorial](https://chartschool.stockcharts.com/table-of-contents/market-analysis/wyckoff-analysis-articles/the-wyckoff-method-a-tutorial), [Wyckoff Analytics schematics](https://www.wyckoffanalytics.com/wp-content/uploads/2019/08/WyckoffSchematics-VisualTemplatesForMarketTimingDecisions.pdf)

The Spring concept itself remains legitimate, but the EdgeHunter 20-candle range, ATR penetration, upper-30%-close and negative-taker-delta requirements have no demonstrated Wyckoff provenance. CVD/absorption observations remain compatible with several mechanisms and do not identify accumulation or distribution. Likewise, the price/OI matrix establishes only changing open exposure; it cannot identify new longs, new shorts, short covering or long liquidation without additional position-level evidence.

Spot-led versus perp-led reliability is also not source-settled. Price-discovery studies report spot leadership, bidirectional feedback, and futures leadership in different samples and periods, so “spot-led is sturdier” and “perp-led fades more often” require an EdgeHunter event study with a defined fade horizon. [Baur–Dimpfl](https://onlinelibrary.wiley.com/doi/full/10.1002/fut.22004), [Cevik et al.](https://doi.org/10.1007/s10479-022-04971-2), [Frino et al.](https://onlinelibrary.wiley.com/doi/10.1002/fut.22560)

**Updated verdicts:** `scanner.py:_btc_bias` and the six Wyckoff-labelled phase records are `MISATTRIBUTED`; `OI/volume = leverage` remains `OVERSTATED_SCOPE` with a definitive terminology correction; the BTC 50% figure remains unsupported; price/OI, CVD, spot/perp, and phase-event interpretations remain hypotheses or candidates until direct, point-in-time validation is supplied. The geometric first-touch formula remains a valid mathematical benchmark and is not itself a hallucinated formula.

### 29. Party 13: signal lifecycle, execution models, variants, and owner/audit claims

The shared `signal_book` lifecycle is a software representation, not a proof that Turtle, ORB, ICT, Wyckoff and mean-reversion strategies share one trading methodology. “No limit on cards” should be read as no explicit application-level cap, with runtime, storage and exchange limits still present. The journal’s context fields also do not prove that values were available at signal time or used by ML.

The Silver Bullet windows are conventionally stated in New York local time, so DST handling through `America/New_York` is required. Their existence does not prove universal kill-zone exclusivity for every sweep/continuation model; public timing tables also differ in broader kill-zone boundaries. The ledger treats the window table as a bounded convention and the exclusivity claim as `OVERSTATED_SCOPE`.

The owner/audit statements in `signal_book.py` are not accepted as development history. The claims about eng-147 ranking, eng-169g’s 31 closures/~45 cards, “which entry is stronger”, the 2026-10-05 order-flow quote, the 2026-10-14 comparison and eng-59’s old rule require primary messages, issue/PR records, immutable journal extracts or reproducible audit outputs. Their presence in a docstring is not evidence of owner consent or of the stated numbers.

Parabolic SAR is a real Wilder indicator and Fidelity documents its acceleration factor and whipsaw risk. That does not validate EdgeHunter’s partial-at-1R, break-even, EMA20 or chandelier ordering. The `optimized profile` label likewise requires a frozen search protocol, trial accounting, costs/funding, walk-forward and untouched-period results; a simulator or JSON artifact is not proof of optimization. [Fidelity Parabolic SAR](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/PSAR), [Bailey et al.](https://escholarship.org/uc/item/4w1110bb)

Net R accounting by partial-exit time is a plausible accounting design, but the VVV +2.62R/+1.5R and −1.08R examples remain unverified without fills, partial quantities, fee tiers, funding settlements and a recomputation. The 0.6 ATR overshoot is explicitly in-sample and journal-only, so it is exploratory rather than independently validated.

The most material execution issue is `_confirmation_entry`: a closed confirmation candle’s close is a historical reference, not a guaranteed fill after the signal is detected. A live-equivalent study must model the next available quote/trade or use actual fills. Likewise, CE, near-edge and second-raid “filled on touch” records are counterfactual limit-fill assumptions; OHLC contact does not disclose queue position, available volume, partial fill or cancellation. [OHLC intrabar ambiguity](https://arxiv.org/abs/1412.5558), [queue-position study](https://ora.ox.ac.uk/objects/uuid%3A0ab2bc82-2098-406b-b962-c6134402a0a4/files/m76ce75d22bc144a6cf57d2df85b67cba)

The Wyckoff Secondary Test concept is real, but a stop beyond the test extreme plus 0.25 ATR is project parameterization. Reclaim, retest, flow-entry and one-direction-per-day rules are similarly project policies or counterfactual hypotheses; their owner comparisons and ICT justifications remain unverified. The Turtle correlated-market principle is real, but a cross-strategy count of open crypto trades is not a correlation-adjusted portfolio-risk measure. [StockCharts Wyckoff tutorial](https://chartschool.stockcharts.com/table-of-contents/market-analysis/wyckoff-analysis-articles/the-wyckoff-method-a-tutorial), [Turtle rules transcription](https://oxfordstrat.com/coasdfASD32/uploads/2016/01/turtle-rules.pdf)

The macro guard is a risk-management policy, not a consequence of the existence of macro announcements. The `ambiguous, not judged` entry-minute rule is a sound limitation for OHLC replay, but the A02 provenance still needs its primary audit record. Binance trade archives can provide trade-level sequence information where available; they do not automatically recover queue-level fills. [Binance public-data repository](https://github.com/binance/binance-public-data)

**Verdicts:** lifecycle universality and resource “no limit” are `OVERSTATED_SCOPE`; owner/audit quotations and historical counts are `PROVENANCE_UNVERIFIED`; ICT exclusivity, optimized exits, macro guard and Turtle transfer are `OVERSTATED_SCOPE`; the confirmation-close execution and touch-fill variants are `OVERSTATED_SCOPE`; the old-rule and ICT/day-bias attributions are `MISATTRIBUTED` or `PROVENANCE_UNVERIFIED`; the in-sample 0.6 ATR claim remains explicitly exploratory.

## Provenance and owner claims

The ledger marks **201** records containing owner/audit/eng-style provenance tokens as `PROVENANCE_UNVERIFIED` unless they were part of the manual batch. A matching Git commit proves that a change was committed; it does not prove that the owner approved every explanation later inserted into a docstring. For example, `eng-70`, `eng-168x`, `eng-168y`, and `eng-169` have matching commits in the current history, while `eng-74` and `eng-75` have no exact matching commit subject in the current refs. Commit authors and co-author lines are evidence about repository history, not independent validation of the market claim.

## What remains open

These manual batches are **not** a claim that all 1160 docstrings have been semantically verified. The remaining records are individually addressable in the ledger, with full source text and coordinates, but remain unverified until their implementation, primary sources, research inputs, and provenance are checked. No code or docstring was modified by this audit.
