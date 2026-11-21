# EdgeHunter v2 remediation and rebuild plan

This plan is the working change record for the independent audit. It does not
claim that the old strategies worked and it does not reuse old results. The
old databases, models, research outputs and reports are forensic artifacts only.

## Current safety boundary

Implemented in the working tree:

- the strategy router is source-gated and currently empty;
- the default strategy allow-list, pool selection, ML models and executor are
  disabled;
- v2 journal/state/model paths are separate from legacy paths;
- local exchange credentials were removed from `config.local.toml`; executor
  access remains disabled and credentials are read only from the environment;
- the legacy executor CLI order probe is disabled; it cannot bypass the
  source-gated/testnet boundary;
- limit/FVG/OTE historical fills return `UNSUPPORTED_LIMIT_MODEL` instead of
  treating a candle touch as an execution;
- reference price, estimated replay fill and actual exchange fill have separate
  journal fields;
- `core/execution_reconciler.py` defines idempotent exchange-event evidence;
  a reference price or a terminal/no-fill response cannot become a fill;
- universe baselines use only snapshots at or before the signal/label time;
- lead-flow correlation pairs minute k with the next complete return;
- the old phase scorer is disabled and fails closed if manually re-enabled;
- price/OI and flow labels describe observations rather than asserting new
  positions, liquidation, accumulation or distribution.

## Phase 0 — quarantine and inventory

1. Keep legacy files and databases read-only for provenance investigation.
2. Do not migrate old rows, labels, hit rates, expectancy, models or signal
   state into v2.
3. Record SHA-256, source commit, schema version and data-source manifest for
   every future artifact.
4. Rotate any credential that was ever present in the checkout or logs.
5. Add a deployment check that refuses to start with executor enabled unless a
   separate reviewed testnet profile and environment credentials are present.

## Phase 1 — independent component audit

For each module reconstruct the call graph from imports and calls, then mark:

- observed data and units;
- calculated feature and formula;
- interpretation and its evidence limit;
- signal/decision and source record;
- execution assumption;
- state/storage side effects.

The audit order is data acquisition, time alignment, levels, strategies,
scoring, statistics/ML, execution, risk, storage and monitoring. A defect is
not closed by a docstring or a test that reproduces the old behavior.

## Phase 2 — source approval

Use `docs/STRATEGY_SOURCE_MANIFEST_V2.md` and
`core/source_manifest.py`. No strategy reaches the router without a primary
source and an exact rule fragment. A published indicator (for example Wilder
ATR or Bollinger Bands) does not validate an unrelated entry, threshold or
fill rule.

The current feasibility queue is listed in
`docs/V2_STRATEGY_CANDIDATES.md`; it contains no enabled strategy.

Initial decision: all legacy strategies are `REMOVE`; `KEEP` is empty and no
`FIX` implementation has been admitted yet.

## Phase 3 — data and mathematical foundation

### Data contracts

Create a versioned record for every input containing:

- venue, market type and symbol;
- event timestamp and receive timestamp;
- source endpoint/stream and sequence number when available;
- units and conversion factor;
- freshness and completeness status;
- as-of/availability timestamp for released data;
- immutable raw-record hash.

Fail closed for stale or incomplete data on a decision path. A missing stream
is `unknown`, not zero and not a passed confirmation.

### Mathematical contracts

For each retained indicator document the formula, initialization, warm-up,
timeframe, closed-bar rule, units, missing-value behavior and causality test.
The first pass covers OHLCV aggregation, True Range/ATR/RMA, EMA/SMA/RSI,
volatility and correlation. No undocumented coefficients or thresholds are
introduced.

### Historical data

Use Binance public archive only as historical market data, not as a complete
replay of live state. Store raw files immutably with download time, checksum
and archive URL. Point-in-time macro features require ALFRED vintages or a
release-event table; current FRED CSV revisions cannot be used as historical
knowledge.

## Phase 4 — market analytics

Split every output into:

1. `observed`: trade, kline, OI, funding, mark/index, book or force-order data;
2. `feature`: a stated calculation over observed data;
3. `interpretation`: a hypothesis with evidence limits;
4. `signal`: a source-backed rule that explicitly consumes the feature.

Examples required by the contract:

- OI/volume is an OI-to-volume ratio, not leverage;
- price/OI cells describe open-contract expansion/contraction, not new longs,
  new shorts, liquidation or short squeeze;
- CVD/delta is aggressive-flow imbalance, not proof of absorption or intent;
- Binance force-order streams are partial observations, not total market
  liquidation volume;
- aggregate L2 levels have no order identity and cannot identify an iceberg;
- estimated liquidation clusters and Hyperliquid account prices are model or
  platform observations, not guaranteed future execution levels.

## Phase 5 — verified strategy engine

Implement one strategy at a time from the source manifest. Each strategy gets:

- `strategy_id` and immutable `strategy_version`;
- source manifest hash;
- closed-bar/as-of input contract;
- entry and invalidation rules;
- stop and target rules from the source;
- an explicit market/limit/stop execution model;
- causal unit tests from published examples and ambiguous cases.

Any rule not in the source is removed, not renamed or justified as a custom
method. Until the first strategy passes this gate, v2 is analytics-only.

## Phase 6 — execution and risk

Implement the state machine:

`SIGNAL → VALIDATED → ORDER_SUBMITTED → ACKNOWLEDGED → PARTIAL_FILL →
FILLED → PROTECTED → PARTIAL_EXIT → CLOSED → RECONCILED`.

Store reference, estimated and actual prices separately. A limit order needs
queue/market-volume evidence; OHLC touch alone produces an unknown/unsupported
status. Every exchange fill is reconciled from user-data events, and an
unreadable acknowledgement blocks new orders for the affected symbol/account.
The in-memory reconciler is a contract until it is wired to the adapter and
restart journal; it is not evidence that live execution is ready.

Risk gates cover spread, depth, fees, funding, slippage, margin, leverage,
correlated exposure, stale data and kill switch. No real trading is enabled by
this repository change.

## Phase 7 — new journal and monitoring

The v2 journal starts at runtime zero and stores source/data/execution
provenance on each row. Legacy results cannot warm-start v2 ML or determine a
pool, veto, promotion, parameter or threshold. ML remains disabled until a
new, predeclared task has enough independent observations and an OOS protocol.

## Phase 8 — acceptance gate

Before any testnet/demo:

- all mathematical unit tests pass;
- causal tests prove no future candle, future snapshot or revised value enters
  a feature at decision time;
- data-quality tests cover missing, stale, duplicate, reordered and partial
  streams;
- source manifest and strategy tests pass;
- state transitions are idempotent and restart-safe;
- duplicate orders are prevented;
- exchange reconciliation and protection recovery are tested;
- limit/ambiguous OHLC cases remain unknown rather than filled;
- credentials are absent from source and logs;
- executor is disabled unless an explicit testnet gate is satisfied.

This gate says only that the software and data contracts are technically
ready. It says nothing about profitability or statistical edge.

## File-level work queue

| Area | Files | Action |
|---|---|---|
| strategy registry | `strategies/__init__.py`, `core/source_manifest.py` | quarantine legacy classes; admit only source records |
| configuration | `config.py`, `config.local.toml` | v2 paths, disabled executor/ML/pools, no secrets |
| journal | `journal.py`, `stats.py` | new provenance fields, past-only snapshots, no adaptive promotions |
| execution model | `levels.py`, `executor.py`, `signal_book.py` | no synthetic limit fills; separate price semantics |
| scoring | `scorer.py` | disable unverified phase taxonomy; raw feature observations only |
| flow | `flow.py` | causal next-minute alignment |
| macro | `macro.py`, future `macro_pit.py` | require release/vintage availability; no current-CSV replay |
| data quality | `data_contract.py`, `data_quality.py`, `fetcher.py` | source/timestamp/sequence/completeness contract |
| storage | new v2 DB and state paths | clean start; legacy read-only archive |
| documentation | this plan and source manifest | every later change linked to a primary source |

