# eng-43 archive validation — pre-registration (written before any run, 2026-10-02)

- Verdict rule (from CLOUD_RETRAIN.md, unchanged): a strategy WORKS only if mean net R > 0 in development AND holdout,
  the holdout 90% cluster-bootstrap interval > 0, and system − placebo in the holdout > 0.
- Windows: research_cards / research_maniac: `--end 2026-09-30 --months 18 --holdout 6` → development
  2025-04-03 … 2026-04-03, holdout 2026-04-03 … 2026-09-30 (the scripts count 30-day months; 2 days off the brief).
- research_turtle: its own daily windows (`--start 2023-10-01 --holdout 2025-10-01 --end 2026-09-30`): a 20/55-day
  system needs years; deviation from the common split is deliberate.
- Pierce model: `models/overshoot_pre.json` from 12 months ending 2026-03-31, used via PIERCE_MODEL in every replay.
- Coins: ALL archive coins passing `select_coins` (owner's request 2026-10-02: as many coins as possible), not 100.
