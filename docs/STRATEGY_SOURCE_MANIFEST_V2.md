# EdgeHunter v2 strategy source manifest

Status: **quarantine / no strategy enabled** (2026-11-17).

The old registry was generated from class names and comments. That is not
evidence that a published method was implemented. The v2 router therefore
starts with an empty `STRATEGIES`/`SETUPS` registry. A strategy can be admitted
only after its exact rules, source fragment, implementation version and tests
are recorded in `core/source_manifest.py`.

`KEEP` means the implementation matches the cited source. `FIX` means the
published method exists but a new implementation must be written and tested.
`REMOVE` means the old implementation is not permitted in the working
pipeline. There is no “custom”, “adapted”, or “author heuristic” status.

## Legacy decision table

| Strategy id | Primary source checked | Current implementation decision | Reason |
|---|---|---:|---|
| `continuation` | No one-to-one primary rule for the complete class was found | REMOVE | Mixed ICT/leg/Fibonacci/confirmation rules; no source-backed contract |
| `sweep` | No primary source for the complete implementation was found | REMOVE | Aggregate L2/touch model is not a published ICT execution rule |
| `silver_bullet` | No primary source with the complete implementation and fill rule was found | REMOVE | Time-window/FVG CE implementation is not verified |
| `wyckoff` | [Wyckoff method tutorial](https://chartschool.stockcharts.com/table-of-contents/market-analysis/wyckoff-analysis-articles/the-wyckoff-method-a-tutorial); [schematics](https://www.wyckoffanalytics.com/wp-content/uploads/2019/08/WyckoffSchematics-VisualTemplatesForMarketTimingDecisions.pdf) | REMOVE | Existing A–F phase mapping and numeric spring rules do not match the source |
| `cascade` | No primary source for the complete implementation was found | REMOVE | Liquidation/OI labels are indirect observations, not a verified method |
| `breakout` | [Original Turtle rules](https://oxfordstrat.com/coasdfASD32/uploads/2016/01/turtle-rules.pdf) | REMOVE | Current class is not a source-faithful Turtle implementation |
| `orb` | [Toby Crabel, Opening Range Breakout](https://tobycrabel.substack.com/p/opening-range-breakout-a-century) | REMOVE | Current range/stretch/session/fill contract is not verified against the source |
| `connors` | [StockCharts RSI(2)](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2) | REMOVE | Current variants, exits and short logic exceed the published rule set |
| `bollinger_method1` | [Bollinger official methods](https://bollingerbands.us/help-methods.php) | REMOVE | Extra OI/delta/funding conditions and execution are not Bollinger Method I |
| `bollinger_method3` | [Bollinger official methods](https://bollingerbands.us/help-methods.php) | REMOVE | Current confirmation contract is not source-verified |
| `bollinger_wm` | No primary source for this complete implementation was found | REMOVE | W/M and extra filters are not a verified Bollinger rule |
| `value_area` | No exact Dalton primary fragment for this implementation was found | REMOVE | Value-area/80% rule and session construction are not source-matched |
| `auction` | No exact Dalton primary fragment for this implementation was found | REMOVE | Failed-auction scoring is not source-matched |
| `supply_demand` | No primary Sam Seiden source for the score/fill contract was found | REMOVE | Zone score, 3:1 rule and touch fill are unsupported |
| `trendline_break` | No primary source for the complete implementation was found | REMOVE | Edwards/Magee attribution and numeric rules are unverified |
| `trendline_touch` | No primary source for the complete implementation was found | REMOVE | Third-touch parameters are unverified |
| `pump_start` | No primary source for the complete entry strategy was found | REMOVE | A large upward move is an observable event, not proof of organised manipulation; the old thresholds and fill contract are not verified |
| `dump_start` | No primary source for the complete entry strategy was found | REMOVE | A large downward move is an observable event, not proof of participant intent; the old thresholds and fill contract are not verified |
| `pump_top` | No primary source for the complete entry strategy was found | REMOVE | Retracement/reversal can be monitored as an event, but the old Fibonacci targets and fills are unsupported |
| `dump_bounce` | No primary source for the complete entry strategy was found | REMOVE | A bounce after a large move is observable, but the old entry, stop and execution contract is not source-verified |
| `cup_handle` | No exact O’Neil/Bulkowski primary algorithm for this implementation was found | REMOVE | Numeric pattern and entry rules are unverified |
| `po3` | No primary source for the complete implementation was found | REMOVE | ICT attribution and Asia-range execution are not one-to-one verified |
| `oi_build` | No primary source for a trading strategy was found | REMOVE | OI/price combinations cannot identify new longs/shorts |

The remaining names found in legacy comments—ICT/SMC, Sam Seiden supply and
demand, Dalton/Market Profile, Elder Triple Screen, O’Neil, Bulkowski and
Fibonacci retracement/extension—also have no approved v2 implementation. A
general book, indicator definition or pattern description does not establish
the old code's exact thresholds, lifecycle or execution model. Those labels
are not approved strategy implementations. Observable price-action events may
be specified and tested separately, but they must not be presented as the
original method or as proof of participant intent.

## What is allowed later

A future `FIX`/`KEEP` entry must include:

1. a primary/official URL;
2. a quoted or precisely located rule fragment;
3. a formal rule table (inputs, timing, entry, invalidation, exit);
4. an implementation hash and strategy version;
5. causal examples and negative/ambiguous cases;
6. tests derived directly from the source;
7. an explicit execution model. OHLC touch is never sufficient for a limit fill.

Until then, all legacy classes are read-only forensic material and cannot
produce cards, journal entries of type `entry`, or orders.

The feasible source-review queue is documented separately in
[`V2_STRATEGY_CANDIDATES.md`](V2_STRATEGY_CANDIDATES.md). It is a candidate
queue, not an approval list; the runtime registry remains empty until each
candidate passes the admission gate.
