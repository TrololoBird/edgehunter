# EdgeHunter v2: strategy candidates compatible with the data contract

Status: **candidate list only** (2026-11-18).

No item in this document is enabled. `STRATEGIES`, `SETUPS` and
`VERIFIED_SOURCE_RECORDS` remain empty. A candidate becomes a working strategy
only after a new source-faithful implementation, causal tests, data-quality
tests and an evidence-based execution contract are approved.

There is no `custom`, `adapted` or `author heuristic` category. If a rule is
not present in the cited source, it is excluded from the implementation.

## What the current bot can provide

The current data layer can collect, subject to the still-incomplete provenance
integration:

- closed 1m candles and derived 15m/1h/4h/daily candles;
- OHLCV, ATR-style volatility, moving averages and RSI-style calculations;
- trades/aggregate trades, OI, funding, mark/index and local order-book
  observations;
- an executor that is currently disabled and an evidence-gated reconciliation
  contract.

The current system cannot safely claim historical queue position, guaranteed
limit fills, complete market liquidations, participant side or live-equivalent
historical execution. Therefore the shortlist uses closed candles and
market/stop execution only. Limit-touch, FVG/OTE and order-identity rules are
excluded.

## Shortlist

| ID | Candidate | Primary source | Data fit | Execution fit | Status |
|---|---|---|---|---|---|
| CAND-001 | Turtle/Donchian breakout | [Original Turtle rules](https://oxfordstrat.com/coasdfASD32/uploads/2016/01/turtle-rules.pdf) | Closed daily or explicitly selected source timeframe bars, channel breakout, N/ATR and position-unit inputs | Stop/market order with exchange acknowledgement and fill reconciliation | Candidate for a new implementation; old `breakout` is removed |
| CAND-002 | Connors RSI(2) | [Published RSI(2) rule set](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2) | Closed daily OHLC, RSI(2), the source trend filter and source-defined exit | Market order on the source-defined decision boundary; actual fill must be separate from candle close | Candidate for a new implementation; old `connors` is removed |
| CAND-003 | Bollinger volatility-breakout method | [Bollinger official methods](https://bollingerbands.us/help-methods.php) | Closed OHLCV, bands and the exact source-defined squeeze/breakout conditions | Market/stop execution only unless a separate queue model is proven | Candidate for source review; old Bollinger classes are removed |

These are feasibility candidates, not claims that the strategies work on
crypto. Their original material was not written as proof of performance on
Binance perpetuals. Transfer to crypto requires a new, predeclared evaluation
on data not used to choose parameters.

## Strategies versus observable event detectors

There were no ML strategies in the old registry. ML, regime labels and
scenario probabilities are analytical components; their old decision use is
quarantined and they are not counted as strategies in this inventory.

### ICT/SMC

ICT/SMC is not being denied as a subject of analysis. The bot can compute
separately defined, closed-bar observations such as a swing break, a
sweep/reclaim or an imbalance location. The old `sweep`, `silver_bullet` and
`po3` contracts are removed because their complete rules, timing and execution
assumptions were not source-verified. A candle touching an FVG/CE is not
evidence that a resting limit order filled. No ICT/SMC label is admitted as a
strategy until a primary source fragment and a complete causal rule table are
recorded.

### Extreme impulses and full retracements

Large moves of 100% or 300% and subsequent partial or full retracements are
observable market events. They do not require an assumption that an organised
group manipulated the market. The old `pump_start`, `pump_top`, `dump_start`
and `dump_bounce` classes are removed as trading strategies because their
thresholds, labels and fills were not source-verified.

A future data-only event monitor may record, without calling it a
manipulation:

- `UP_IMPULSE` / `DOWN_IMPULSE` — a specified return over closed bars;
- `RETRACE` — return toward the impulse origin;
- `FULL_RETRACE` — return through the defined impulse origin;
- continuation, consolidation or reversal as separate outcome labels.

The existing data layer can enrich these events with POC/VAH/VAL, merged
zones, equal pools, FVG locations, estimated and observed liquidation levels,
taker flow, sweeps, whale-size clusters, OI, funding and local order-book
observations. Those inputs can be used to define and test impulse-start,
climax, retracement, reclaim and continuation signals. They still must not
infer participant intent from price alone, guarantee that an order was
absorbed, or automatically short every large rise.

These are data-supported research candidates, not enabled strategies. A
trading contract requires explicit causal rules, a predeclared evaluation and
the same evidence-gated execution requirements as the source-backed queue.

## Data-supported signal families under review

The following families are not claims that the old classes were correct. They
record what the current data layer can evaluate without inventing missing
market information:

| ID | Signal family | Existing inputs | Current status |
|---|---|---|---|
| SIG-001 | Impulse start / climax / full retracement | Closed bars, return and range expansion, volume, taker flow, sweeps, OI/funding, POC/zones, liquidation observations | Research candidate; no organised-manipulation label and no fixed threshold is approved |
| SIG-002 | Liquidity sweep / reclaim / displacement | Equal pools, PDH/PDL/PWH/PWL, FVG/structure locations, closed-bar reclaim, flow and liquidation context | Research candidate; old ICT/SMC classes are not admitted as source-faithful strategies |
| SIG-003 | POC and zone acceptance/rejection | POC/VAH/VAL buckets, merged zones, VWAP, prior-session references and closed-bar response | Research candidate; current candle-volume POC is descriptive, not a full time-at-price profile |
| SIG-004 | Liquidation-flow reaction | Observed force-order events, long/short liquidation flow, OI change, price acceleration and liquidation-map estimates | Research candidate; observed streams are incomplete and estimates are not guaranteed future orders |

For `SIG-001`, a complete return through the measured impulse origin is a
price-defined `FULL_RETRACE`. The word `absorption` is reserved for a
separately specified flow condition; it is not inferred merely because a pump
was retraced.

## Source-faithful implementation requirements

### CAND-001 — Turtle/Donchian

The implementation must reproduce the selected published Turtle system's
breakout, volatility unit, stop, sizing, pyramiding and exit rules. The old
`breakout` class is not reusable: it mixed a local card lifecycle and touch
assumptions with a partial Turtle label.

Required before admission:

1. identify the exact system and timeframe from the source;
2. implement the source's `N`/unit and stop semantics without silently
   substituting a different ATR window;
3. model stop/market orders with exchange evidence;
4. test breakouts, gaps, duplicate triggers, missing bars and partial fills.

### CAND-002 — Connors RSI(2)

The implementation must use only the source-defined RSI, trend condition,
entry and exit. The source is an equity rule set; crypto use is a new test
question, not an assumption of equivalence.

The old class is not reusable because it combined multiple variants, a
mirrored short rule, local SMA/ATR conventions and an executor catastrophe
stop that are not all part of the cited rule set.

### CAND-003 — Bollinger method

The implementation must first select one exact official method. It may not
add OI, funding, CVD, Wyckoff phase, market-regime or liquidity conditions and
still call them Bollinger rules. Any added condition would require a separate
source and a separate strategy contract.

## Explicitly excluded from the shortlist

| Legacy family | Decision | Reason |
|---|---|---|
| ICT/SMC, Silver Bullet, PO3, OTE, FVG/CE | Exclude | No exact source-backed contract for the old rules; limit touch is not a fill |
| Wyckoff phase/scoring | Exclude | Existing A–F taxonomy does not match the published accumulation/distribution phases |
| Dalton/Market Profile/value area | Exclude | Existing candle-volume approximation is not a source-matched time-at-price implementation |
| Sam Seiden supply/demand | Exclude | Zone score, 3:1 rule and touch fill have no verified primary rule |
| Legacy pump/dump trading classes | Exclude as strategies; event monitoring remains possible | A large price move and a retracement are real observations, but do not prove organised manipulation; the old thresholds and fills are not source-verified |
| OI build, liquidation cascade, short squeeze | Exclude | OI and sampled force-order data do not identify participant side or complete liquidation volume |
| Iceberg/absorption/order-flow intent | Exclude | Public aggregate L2/trade data lack order identity and do not establish intent |
| ML/regime/scenario probability | Not strategies; old decision use excluded | These are analytical components, not source-backed trading rules; no ML strategy existed in the registry |

## Admission gate

For a candidate to enter `core/source_manifest.py` and the runtime registry,
the review must record:

1. primary URL and exact rule fragment;
2. complete rule table with timing and units;
3. source-faithful implementation hash and version;
4. closed-bar and availability-time contract;
5. market/stop execution assumptions and exchange-event reconciliation;
6. causal, missing-data, gap, duplicate and ambiguity tests;
7. a frozen out-of-sample evaluation plan.

Until that gate passes, the correct runtime state is analytics-only.
