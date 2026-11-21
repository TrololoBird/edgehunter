# EdgeHunter v2 defect remediation register

This register maps the independent pre-rebuild findings to the current v2
boundary.  `FIXED` means the defect is prevented or corrected in the active
path.  `QUARANTINED` means the old path is still present for forensic reading
but cannot create a v2 signal, label, model or order.  `PARTIAL` means the
active safety boundary is improved but a replacement contract is still
required.  `REMAINING` means no claim of completion is made.

The old implementation and its historical results are not evidence for v2.
The strategy registry is intentionally empty until a primary source, exact
rule fragment, causal tests and an execution contract are approved.

## Findings

| ID | Status | Current action | Remaining work / source |
|---|---|---|---|
| DEF-SEC-001 | FIXED / REMAINING | Checkout credentials were removed from the local override and the executor reads environment variables only. | Rotate any credential that was ever exposed outside the checkout; no source URL applies. |
| DEF-SEC-002 | FIXED | Config-file fallback is not used; missing environment credentials disable execution. | Add deployment secret scanning and a testnet-only gate before any enablement. |
| DEF-ML-001 | QUARANTINED | Live anomaly/regime/success/trade ML flags are disabled; old model hooks cannot make a v2 decision. | Define a new task and OOS protocol before reintroducing ML. |
| DEF-ML-002 | QUARANTINED | Legacy warm-start paths are outside the v2 journal/model paths. | No warm start or model migration is allowed; build a new dataset only after a reviewed task. |
| DEF-FLOW-001 | FIXED | Lead-flow correlation uses minute `k` as predictor and the next complete return as target. | Add causal/data-quality tests for every venue adapter. Source: [Cont, Kukanov & Stoikov](https://arxiv.org/abs/1011.6402). |
| DEF-MKT-001 | QUARANTINED | Price/OI labels now describe expansion/contraction and do not assert new longs, new shorts, covering or liquidation; phase scoring is disabled. | Keep intent claims out unless position-side data exists. Source: [CME open interest](https://www.cmegroup.com/market-data/volume-open-interest/about.html). |
| DEF-MKT-002 | QUARANTINED | CVD/delta outputs are observation fields; accumulation/distribution phase scoring cannot run. | If used later, specify order-book evidence and an independently validated interpretation. Source: [Cont et al.](https://arxiv.org/abs/1011.6402). |
| DEF-MKT-003 | PARTIAL | Iceberg wording is reduced to aggregate replenishment-like L2 behavior without order identity; old detector is not source-gated into v2. | Keep sequence/coverage metadata and never infer one hidden order. Source: [Binance diff-depth stream](https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md#diff-depth-stream). |
| DEF-MKT-004 | PARTIAL | Force-order records are labelled partial public observations and no longer mean total market liquidation volume. | Add explicit stream coverage/freshness in the data contract. Sources: [Binance derivatives API](https://developers.binance.com/en/docs/derivatives/usds-margined-futures/user-data-streams). |
| DEF-DATA-001 | PARTIAL | Settled funding and next-estimate funding are stored separately; replay no longer charges an unobserved future settlement. | Propagate funding kind/settlement timestamp through every venue aggregate. Sources: [mark price](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price), [funding history](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History). |
| DEF-POS-001 | FIXED | Hyperliquid fields and liquidation levels are explicitly restricted to selected tracked accounts and platform estimates. | Preserve account-selection and freshness metadata. Source: [Hyperliquid info API](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint). |
| DEF-ZONE-001 | PARTIAL | Volume Profile documentation now states that candle-volume spreading is an OHLC approximation, not time-at-price or Dalton Market Profile. | Do not use it as a source-backed level until tick/price-volume data and a source contract exist. |
| DEF-ZONE-002 | FIXED | Estimated liquidation clusters are marked as model outputs and cannot be treated as observed liquidation levels or directional evidence. | Keep them diagnostic only unless independently sourced and validated. |
| DEF-MACRO-001 | PARTIAL | Strict mode refuses current revised FRED rows without release/vintage timestamps. | Implement a release-event/ALFRED vintage store before historical macro decisions. Source: [ALFRED](https://alfred.stlouisfed.org/). |
| DEF-PRE-001 | QUARANTINED | `pretrain.py` and `replay.py` refuse to run with the empty v2 registry; old outputs are archive-only. | No live-equivalent historical replay is planned for v2. Source: [Binance public data](https://github.com/binance/binance-public-data). |
| DEF-EXEC-001 | PARTIAL | Reference price, estimated replay fill and actual exchange fill have separate fields; no source-gated strategy can reach execution. `core/execution_reconciler.py` now rejects fill states without exchange evidence and deduplicates user-data events. | Wire the reconciler into the live adapter, add restart recovery and finish signal-to-order timestamps before testnet. |
| DEF-EXEC-002 | FIXED | OHLC/limit touch returns `UNSUPPORTED_LIMIT_MODEL`; it is not recorded as a full fill. | Add queue/market-volume evidence if a limit strategy is ever admitted. |
| DEF-EXEC-003 | PARTIAL | v2 rows mark reference-only outcomes and do not populate actual exchange fills from replay; `record_entry` rejects an unregistered strategy. | Rebuild all PnL/MFE/MAE calculations around actual fills or explicit unknown status. |
| DEF-EXEC-004 | PARTIAL | Unobserved future funding is removed from replay; model slippage remains clearly estimated. | Add venue-specific fee, spread, impact and funding observations to the execution contract. |
| DEF-STAT-001 | QUARANTINED | Adaptive hit-rate gates and legacy geometry promotions cannot run with the empty registry. | No online promotion is allowed in v2 without frozen OOS data and a predeclared protocol. |
| DEF-STAT-002 | QUARANTINED | Confirmation promotion is disabled and requires a source-gated strategy. | Any future comparison must be matched, OOS and multiplicity-controlled. |
| DEF-STAT-003 | FIXED | Anomaly effect denominator uses the documented median rather than a mean. | Add a regression test for the statistic definition. |
| DEF-STAT-004 | FIXED | Universe baselines select only snapshots at or before the target timestamp. | Add missing/stale snapshot tests for the data contract. |
| DEF-STAT-005 | QUARANTINED | Legacy DSR/PBO/threshold-selection reports are not used by v2 and ML is disabled. | Reimplement statistical evaluation only for a new, frozen task with independent OOS data. Source: [Bailey et al.](https://escholarship.org/uc/item/1jv4851f). |
| DEF-ATTR-ORB-001 | REMOVE | Legacy ORB classes are not registered; the source manifest marks them `REMOVE`. | A future ORB must match a primary Crabel rule exactly. Source checked: [Crabel](https://tobycrabel.substack.com/p/opening-range-breakout-a-century). |
| DEF-ATTR-DALTON-001 | REMOVE | Value-area/auction classes and Dalton labels are quarantined; no exact primary rule was established for the old implementation. | Do not retain the attribution without a primary source fragment. |
| DEF-ATTR-CONNORS-001 | REMOVE | RSI(2) legacy class is not registered because its variants/exits exceed the checked published rule. | Reimplement only from the published rule set if independently approved. Source: [StockCharts RSI(2)](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2). |
| DEF-ATTR-TURTLE-001 | REMOVE | Legacy breakout class is not a complete Turtle implementation and is not registered. | A future implementation must include the source-defined entry, unit, stop, pyramiding and portfolio rules. Source: [Turtle rules](https://oxfordstrat.com/coasdfASD32/uploads/2016/01/turtle-rules.pdf). |
| DEF-ATTR-WYCKOFF-001 | REMOVE | The invented A–F phase taxonomy is not admitted and phase scoring is disabled. | Do not use Wyckoff names for the old classifier. Sources: [tutorial](https://chartschool.stockcharts.com/table-of-contents/market-analysis/wyckoff-analysis-articles/the-wyckoff-method-a-tutorial), [schematics](https://www.wyckoffanalytics.com/wp-content/uploads/2019/08/WyckoffSchematics-VisualTemplatesForMarketTimingDecisions.pdf). |
| DEF-ATTR-WYCKOFF-002 | REMOVE | Numeric spring constraints are not attributed to Wyckoff and the old strategy is not registered. | Any future Spring implementation needs source-matched structure and separately justified parameters. |
| DEF-ATTR-SEIDEN-001 | REMOVE | Supply/demand score, 3:1 and touch-fill rules have no verified primary source and are not registered. | No Seiden attribution remains in the v2 strategy manifest. |
| DEF-ATTR-BOLL-001 | REMOVE | The old Method I/III classes mixed Bollinger terminology with unsourced OI/delta/funding conditions and are not registered. | A future implementation must separate official band rules from any separately sourced signal. Source: [Bollinger methods](https://bollingerbands.us/help-methods.php). |
| DEF-ATTR-CUP-001 | REMOVE | Cup/handle numeric algorithm is not source-verified and is not registered. | Do not preserve O’Neil/Bulkowski attribution without an exact primary rule. |
| DEF-ICT-001 | REMOVE | ICT/OTE/Silver Bullet classes mix terms with unverified conditions and execution assumptions; none is registered. | No ICT attribution is allowed without an exact primary rule and execution contract. |

## Open work before a technical demo

1. Integrate `DataProvenance` into every exchange adapter, including sequence,
   freshness, completeness and raw-record hashes.
2. Complete ALFRED/release-event ingestion and reject unavailable vintages.
3. Finish the funding-kind/settlement-time contract across Binance, Bybit and
   Bitget aggregates.
4. Replace the legacy signal-book execution paths with the explicit execution
   lifecycle and exchange user-data reconciliation.
5. Add mathematical and causal tests for every indicator admitted to v2.
6. Add a separate testnet profile and kill-switch/restart/reconciliation gate.
7. Admit no strategy until its source manifest, rule table, negative cases and
   execution model pass review.

Until these items are closed, the repository is an analytics-only safety
boundary, not a deployable trading system and not evidence of profitability.
