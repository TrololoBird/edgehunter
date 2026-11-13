# EdgeHunter forensic implementation status

This report uses the readable checkout at `/opt/edgehunter`, the running systemd service, read-only SQLite queries, and runtime health output. The damaged archive is `ARCHIVE_ONLY` context and is not used for line-level claims.

## Provenance classes

- `FACT_CODE` is supported by the current readable source.
- `FACT_RUNTIME` is supported by the running process, systemd, logs, or `/api/health`.
- `FACT_DATA` is supported by read-only SQLite, JSON, or Parquet inspection.
- `HYPOTHESIS` needs an experiment.
- `ARCHIVE_ONLY` is visible only in the damaged archive.
- `UNVERIFIED` lacks sufficient evidence.

## Current implementation facts

| Claim | Provenance | Evidence | Confidence |
|---|---|---|---|
| Runtime provenance is persisted on signal and demo rows | `FACT_CODE` | `core/provenance.py`, `journal.py` `FEATURE_SCHEMA_VERSION`, `executor.py` provenance fields | high |
| Dirty checkout can be refused before service start | `FACT_CODE` | `deploy/precheck.sh`, `deploy/edgehunter-bot.service` | high |
| SignalBook, live limit execution, and replay share `StrategyEngine` geometry and causal snapshots | `FACT_CODE` | `core/strategy_engine.py`, `signal_book.py`, `executor.py`, `replay.py` | high |
| Replay resolves simultaneous stop and target touches stop-first | `FACT_CODE` | `levels.py:simulate`, `tests/test_regressions.py` | high |
| Entry execution has durable `(card_id, execution_phase)` idempotency claims | `FACT_CODE` and `FACT_DATA` | `executor.py`, SQLite `execution_intents` table | high |
| Missing exchange credentials fail closed | `FACT_CODE` | `executor.py:credentials` | high |
| Backfill jobs expose queued/running/verified/failed lifecycle and reasons | `FACT_CODE` | `fetcher.py`, `scanner.py` health payload | high |
| Depth reports sequence gaps, resyncs, and buffer drops | `FACT_CODE` | `depth.py`, `DepthBook.diagnostics()` | high |
| Iceberg features become NULL when L2 coverage is absent or stale | `FACT_CODE` | `iceberg.py`, journal `iceberg_reason` feature | high |
| Legacy model artifacts are quarantined and never auto-loaded | `FACT_CODE` and `FACT_DATA` | `models/*.manifest.json`, `scenarios.py`, `tools/model_audit.py` | high |
| `p_edge` and `p_trade` are shadow-only | `FACT_CODE` and `FACT_RUNTIME` | `journal.py` model status, `/api/health` | high |
| Briefing calculates cost-aware `EV_net` and displays `NO TRADE` for non-positive EV | `FACT_CODE` | `core/quant_gate.py`, `briefing.py`, `briefing_chart.py`, `web/app.js` | high |

## Current runtime snapshot

The latest observed `/api/health` response reported `ok=true`, RSS below 1 GB after restart, no backfill jobs active, no pool worker failures, no sequence gaps, and zero OKX seed errors. The exact current values are available from the local endpoint and are intentionally not copied into this file because they change continuously.

The service is running from a clean committed checkout. The verification commands are:

```text
EDGEHUNTER_REQUIRE_CLEAN=1 bash deploy/precheck.sh
.venv/bin/python -m pytest tests -q
.venv/bin/ruff check .
.venv/bin/pyright --project pyrightconfig.json
.venv/bin/python tools/demo_reconcile.py --db demo_trades.db --state scanner_state.json
.venv/bin/python tools/model_audit.py --root .
```

## Outstanding findings

| Finding | Provenance | Evidence | Required disposition |
|---|---|---|---|
| Ten open legacy demo rows have `protection_state=INVALID_GEOMETRY` | `FACT_DATA` and `FACT_RUNTIME` | `tools/demo_reconcile.py`, `demo_trades.db`, executor startup alerts | Operator must reconcile exchange-side protection and decide the position outcome. No automatic price reconstruction is justified by the stored row. |
| The scenario probability and `pretrained.eng-7` artifacts are quarantined | `FACT_DATA` | `tools/model_audit.py`, manifest sidecars | Retrain from a current feature schema and generate a signed manifest before promotion. |
| `p_edge` and `p_trade` have no active promotion gate | `FACT_CODE` | `journal.py` model mode is `shadow` | Require independent OOS evidence and an explicit logic-versioned promotion decision. |
| Six of the currently tracked depth books were synced in the latest snapshot | `FACT_RUNTIME` | `/api/health.depth_diagnostics` | Investigate coverage policy if a strategy requires every hot book. Missing coverage is now represented as unknown. |
| Legacy rows whose cards are absent from persisted scanner state are reported as reconciliation attention | `FACT_DATA` | `tools/demo_reconcile.py` | Resolve against exchange state before deleting or closing ledger rows. |

## Safe external-audit package

The following can be provided after removing host-specific paths and runtime identifiers.

- Committed source revision and implementation hash.
- `pyproject.toml`, `pyrightconfig.json`, CI workflows, and test results.
- Redacted `/api/health` snapshots with symbols and account identifiers removed.
- SQLite schema and aggregate counts, without credentials or order identifiers that expose account context.
- Synthetic fixtures for geometry, replay stop-first behavior, depth sequencing, backfill verification, iceberg coverage, model quarantine, and virtual TP sizing.
- Model manifests and SHA-256 values. The quarantined pickle payloads should remain withheld unless the auditor specifically needs offline artifact inspection.

No API keys, secrets, IP addresses, account identifiers, raw order credentials, or live exchange mutation commands belong in the external package.

## Completion status

The P0 protections, provenance controls, causal replay contract, memory stress harness, backfill telemetry, model quarantine, depth/iceberg data-quality contracts, CI static checks, and briefing EV gate are implemented and verified. The full expanded plan remains open while legacy demo positions require operator reconciliation and while no current model artifact has passed provenance and out-of-sample promotion gates.
