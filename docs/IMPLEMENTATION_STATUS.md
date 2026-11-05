# Modernization implementation status

This change implements the verifiable foundation of the modernization plan.

## Implemented

- dependency constraint is resolvable (`ccxt==4.5.90`);
- README, explicit license notice and claims register;
- security workflow with dependency and Bandit scans;
- immutable action references and deployment `pip check`;
- explicit `FRESH/DEGRADED/STALE/MISSING/INVALID` data-quality states;
- opt-in append-only gzip JSONL capture of raw WebSocket frames;
- opt-in capture of CCXT REST results and errors without storing credentials;
- evidence tests for the quality contract and raw-event integrity.

## Deliberately not enabled

No new trading filter, stop rule, level-clustering rule, ML calibration, or
room-to-run veto is enabled by this change. Those are market hypotheses and
require the raw journal, an independent validator, and forward observations.
