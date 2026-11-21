# Legacy artifact quarantine

Effective 2026-11-17, the following are forensic material only:

- the pre-v2 SQLite journals (`data/*.db` except a newly created v2 path);
- `pretrained.pkl`, scenario models, profile files and their manifests;
- `research/`, `research/exit_bt/`, `replay.py` and `pretrain.py` outputs;
- old scanner state files and pending-order files;
- legacy strategy modules under `strategies/`.

They must not be migrated, warm-started, used for pool selection, used for
parameter selection, or used to establish a hit rate, expectancy, calibration
or risk limit.  The v2 journal refuses to open a non-empty database without a
matching `journal_meta` source/execution manifest.  The v2 strategy registry is
empty until a primary-source contract and causal tests are reviewed.

The quarantine does not assert that every legacy implementation is mathematically
wrong.  It says that none has an approved provenance and therefore none is
eligible to create a signal or order in the new working contour.

The old executor diagnostic order probe is disabled in v2.  It is not a
shortcut around the strategy and testnet gates.

## Re-enable gate

An artifact may be considered only in a separate forensic process that records:

1. immutable path and SHA-256;
2. source commit and dirty state;
3. feature/schema and execution-model versions;
4. a primary-source manifest for every retained rule;
5. an explicit decision that does not reuse the artifact for v2 training or
   trading.

