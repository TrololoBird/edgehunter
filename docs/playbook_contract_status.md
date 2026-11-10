# Playbook contract migration status

The executable contract is selected through `strategies.entry_levels_for()`.
Each registered directional setup has a concrete owner method; the audit in
`tools/contract_audit.py` verifies this registry invariant and persists the
owner as `contract_id` / `contract_source` in journal entry and card rows.

The remaining migration boundary is plan construction: several detectors still
use `strategies.geometry` for map target discovery or structural padding. Those
imports are reported by the audit and must be removed before deployment. This
document intentionally records that boundary instead of presenting the
compatibility result as a completed strategy migration.

Outcome horizons are stored at 15m, 1h, 3h, 4h, 6h, 8h, 12h, 24h, 2d, 3d,
and 7d. Only horizons through 8h run in the live evaluator; longer horizons
are available through the journal backfill entry point.
