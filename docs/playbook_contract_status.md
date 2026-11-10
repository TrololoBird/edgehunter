# Playbook contract migration status

The executable contract is selected through `strategies.entry_levels_for()`.
Each registered directional setup has a concrete owner method; the audit in
`tools/contract_audit.py` verifies this registry invariant and persists the
owner as `contract_id` / `contract_source` in journal entry and card rows.

The contract audit currently reports 40/40 independent entry contracts and no
`strategies.geometry` imports in the strategy package. Target discovery and
structural padding used by the migrated playbooks are local to their owning
modules. The audit remains a deployment gate so a future compatibility fallback
cannot be reintroduced silently.

Outcome horizons are stored at 15m, 1h, 3h, 4h, 6h, 8h, 12h, 24h, 2d, 3d,
and 7d. Only horizons through 8h run in the live evaluator; longer horizons
are available through the journal backfill entry point.
