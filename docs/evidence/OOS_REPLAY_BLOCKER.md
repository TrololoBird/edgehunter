# OOS replay evidence status

The contract and registry checks pass, but the available replay archive does
not currently provide a complete OOS portfolio run:

- `replay.py --days 1 --coins 1` produced a manifest with `coins: []` for
  2026-10-31.
- A 30-day, one-coin replay did not produce a result within the controlled
  observation window and was stopped to avoid excess load.
- Live `signals.db` contains separate eng-169l/eng-169m partitions and current
  eng-169m entry/card outcomes; those are forward evidence, not a substitute
  for an archived OOS replay.

No historical evidence was rewritten or relabeled as eng-169m.
