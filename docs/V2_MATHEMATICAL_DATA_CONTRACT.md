# EdgeHunter v2 mathematical and data contract

This contract is the gate for future implementation.  A formula is not
approved merely because an indicator has a familiar name.  Every retained
calculation must record its source, units, initialization, warm-up, closed-bar
availability and missing-value behavior.

## Data envelope

Every observation must carry:

| Field | Requirement |
|---|---|
| `venue` / `market` / `symbol` | Exact source market, such as Binance spot or USD-M perpetual. |
| `event_ts_ms` | Exchange event or candle open time; never substituted with receive time. |
| `received_ts_ms` | Local receive time. |
| `available_ts_ms` | Earliest time the value was usable by the process. |
| `source` / `sequence` | Endpoint/stream and sequence where the source provides one. |
| `units` | Quote/base/contracts/rate and conversion factor. |
| `state` | Observed, stale, missing, incomplete, invalid or unknown. |
| `raw_hash` | Hash of the immutable raw record or batch. |

Only `observed` values with a valid event timestamp and complete coverage may
enter a decision path. Missing values remain unknown; they are never replaced
with zero.

## Indicator record

Each indicator implementation must specify:

1. exact formula and source;
2. input units and timeframe;
3. initialization and warm-up length;
4. whether the value is available only after a closed bar;
5. handling of gaps, duplicates, out-of-order rows and NaN;
6. the causal test proving no future row is read;
7. numerical behavior for zero denominators and constant series.

The first accepted mathematical primitives are ordinary OHLCV aggregation,
True Range/ATR, EMA/SMA/RMA, RSI, volatility and correlation.  Their presence
does not authorize a strategy or a threshold.  ADX, MACD, stochastic,
Bollinger, VWAP and volume profile remain `REVIEW_REQUIRED` until the same
contract and tests are present.

## Source manifest for named methods

The following URLs are the sources that may be used for a future rule review;
they do not approve the old implementation:

| Name | Primary/official source used for review | v2 decision |
|---|---|---|
| Wilder ATR/RMA | [TA-Lib ATR reference](https://ta-lib.github.io/ta-doc/indicator/ATR.htm) and Wilder, *New Concepts in Technical Trading Systems* | Indicator calculation only; no strategy approved. |
| Bollinger Bands | [Bollinger official methods](https://bollingerbands.us/help-methods.php) | Old mixed Method I/III classes removed. |
| Connors RSI(2) | [StockCharts RSI(2)](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2) | Old class removed pending source-matched implementation. |
| Turtle Trading | [Original Turtle rules](https://oxfordstrat.com/coasdfASD32/uploads/2016/01/turtle-rules.pdf) | Old incomplete breakout removed. |
| Crabel ORB | [Crabel opening-range discussion](https://tobycrabel.substack.com/p/opening-range-breakout-a-century) | Old ORB removed; no exact implementation approved. |
| Wyckoff | [StockCharts tutorial](https://chartschool.stockcharts.com/table-of-contents/market-analysis/wyckoff-analysis-articles/the-wyckoff-method-a-tutorial), [schematics](https://www.wyckoffanalytics.com/wp-content/uploads/2019/08/WyckoffSchematics-VisualTemplatesForMarketTimingDecisions.pdf) | Old A–F classifier and numeric Spring rules removed. |
| ICT, Seiden, Dalton, O’Neil, Bulkowski | No exact primary fragment for the old complete rules was established | Old attributions removed; no substitute method invented. |

## Market observations versus interpretations

The working data model must keep four separate types:

1. **Observed**: trades, candles, OI, funding, mark/index, book updates and
   public force-order messages.
2. **Feature**: a deterministic calculation over observations.
3. **Interpretation**: a hypothesis with an evidence limit.
4. **Signal**: a source-backed rule that consumes named features.

Examples of prohibited direct substitutions:

- OI increase → new longs or new shorts;
- OI decrease → liquidation or short covering;
- force-order stream → total market liquidations;
- CVD/delta → accumulation/distribution intent;
- selected-account liquidation estimate → guaranteed future execution;
- candle-volume spread → time-at-price profile;
- BTC return → complete market-regime classification;
- geometric barrier probability → empirical trade probability.

## Execution semantics

`reference_price`, `estimated_fill` and `actual_fill` are different fields.

- A closed-candle close is a reference price unless an exchange event proves a
  fill.
- An OHLC touch is insufficient for a limit fill because queue position,
  traded volume and order lifetime are unknown.
- An ambiguous bar that touches both barriers is `UNKNOWN`, not a chosen
  favorable order.
- Fees, spread, impact, funding settlement and partial fills are measured or
  explicitly marked unavailable; they are not silently inferred as actual P/L.

## Statistical semantics

Every reported interval or probability must state its unit of observation,
dependence structure, selection rule, horizon and whether it is descriptive,
confidence-based or posterior.  Wilson, Beta posterior, bootstrap, PSR, DSR,
PBO and calibration code cannot be used as evidence until the data split,
effective sample size, multiple testing and temporal leakage controls are
documented and tested.

