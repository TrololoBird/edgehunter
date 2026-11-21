# EdgeHunter v2 component inventory

This is an implementation inventory, not an endorsement of the old names or
documentation.  The status describes the v2 working contour after the
quarantine changes.

| Layer | Components | v2 status | Boundary |
|---|---|---|---|
| Entry/runtime | `main.py`, `scanner.py` | `ANALYTICS_ONLY` | Collects current observations; no admitted setup can create a card or order. |
| Exchange data | `fetcher.py`, `venues.py`, `flow.py`, `depth.py`, `raw_event_log.py` | `PARTIAL` | Existing adapters remain; freshness/coverage checks exist in places but the full `DataProvenance` contract is not yet wired to every field. |
| Data quality | `data_quality.py`, `core/data_provenance.py` | `PARTIAL` | Explicit fresh/stale/missing/invalid states and decision-safe provenance are available; adapter-wide integration is pending. |
| OHLCV/indicators | `indicators.py`, `levels.py` | `REVIEW_REQUIRED` | No strategy consumes them in v2. Formulas need a source/initialization/warm-up contract and causal tests before admission. |
| Levels/volume | `zones.py`, `sr.py`, `pierce.py`, `positioning.py` | `OBSERVATION_ONLY` | Candle-derived levels, modelled clusters and selected-account estimates are diagnostics, not forecasts, stops or fills. |
| Macro | `macro.py`, `macro_calendar.py`, `official_calendar.py` | `FAIL_CLOSED_PIT` | Current revised FRED rows are unavailable in strict mode; release/vintage ingestion remains to be implemented. |
| Flow/positioning | `flow.py`, `positioning.py`, `iceberg.py` | `OBSERVATION_ONLY` | No inference of participant intent, hidden order identity, total liquidation volume or market-wide positioning. |
| Regime/scoring | `scorer.py`, `core/regime.py`, `scenarios.py` | `QUARANTINED` | Legacy Wyckoff/phase/intent taxonomy is disabled; geometric probability is not used as a market probability. |
| Strategy router | `strategies/__init__.py`, `core/source_manifest.py` | `EMPTY` | `STRATEGIES`, `SETUPS` and verified records are empty. Configuration cannot activate legacy classes. |
| Legacy strategies | `strategies/*.py` | `FORENSIC_ONLY` | All registered legacy IDs are `REMOVE`; classes cannot create v2 cards. |
| Signal lifecycle | `signal_book.py`, `core/execution_contract.py` | `PARTIAL` | Legacy state container remains for read-only compatibility; v2 execution transitions are explicit and evidence-gated. |
| Execution | `executor.py`, `levels.py`, `core/execution_contract.py`, `core/execution_reconciler.py` | `DISABLED / CONTRACTED` | Environment-only credentials, source-gated registry and disabled config all prevent orders. Limit touch is unsupported without queue evidence; the reconciler accepts filled state only from evidence-bearing exchange events. |
| Journal | `journal.py`, `stats.py` | `V2_PROVENANCE` | Separate reference/estimated/actual prices, manifest metadata and clean DB path; legacy DBs are rejected. |
| ML/research | `ml.py`, `ml_eval.py`, `pretrain.py`, `replay.py`, `research/` | `QUARANTINED` | No old model/result warms v2. Historical OHLCV replay is not live-equivalent and its entry points are blocked. |
| Monitoring/UI | `webui.py`, `briefing.py`, `notifier.py` | `OBSERVATION_ONLY` | Legacy phase names are not rendered as verified classifications; no execution status is implied by a reference row. |
| Storage/deploy | `storage.py`, `config.py`, `config.local.toml`, `deploy/` | `PARTIAL` | v2 paths and disabled defaults are present; deployment secret rotation and testnet gate remain required. |

## Runtime dependency boundary

The current flow is intentionally limited to:

```text
exchange observations
        -> data quality / timestamps
        -> closed-bar mathematical features
        -> neutral observations and dashboard
        -> v2 journal with provenance
```

The following edges are blocked until a reviewed strategy exists:

```text
legacy detector -> setup/card
legacy phase score -> directional signal
historical replay -> v2 journal/model
reference or OHLC touch -> actual fill
online outcome -> new rule/promotion
configuration -> unverified strategy
```

## Required next implementation units

1. Extend `core/data_provenance.py` and the existing `data_contract.py` with one
   immutable observation envelope for venue, market, symbol,
   event/receive/availability times, units, sequence, completeness and raw
   hash.
2. `data_quality.py` integration: make every decision input carry the envelope
   and make stale/incomplete/unknown values fail closed.
3. `indicator_contracts.py`: source, formula, initialization, warm-up,
   timeframe and causality tests for each retained indicator.
4. `strategy_engine_v2.py`: only source-manifest-approved rule tables and no
   synthetic fills.
5. `execution_reconciler.py`: idempotent order/user-data state machine,
   restart recovery, protection and exchange reconciliation.
6. `journal_v2.py` migrations: actual fill, fee, funding settlement and
   unknown-status accounting without importing legacy rows.

