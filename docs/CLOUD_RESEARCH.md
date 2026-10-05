# Archive research in the cloud (eng-59)

Every job below reads only the Binance public archive (data.binance.vision, cached in `history_cache/`) and the code
of this branch. The bot, its journal (`signals.db`) and the demo (`demo_trades.db`) stay on the owner's machine and are
NOT needed. Binance's REST API is geo-blocked in the cloud; the archive is not.

Rules (from CLAUDE.md, apply here too):
- Every study's decision rule is fixed in its docstring BEFORE the run. Do not change a rule after seeing a number;
  if a rule looks wrong, say so in the report and keep the pre-registered result.
- Report the results honestly, negative ones included. No changes to the bot's signal logic in this session: the
  results go to `research/*.md`, the owner decides.
- Lint before committing: `ruff check --select F <files>`; offline tests `python -m pytest tests -q` must stay green.

## Setup

```bash
python3.14 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest tests -q
```

Use as many workers as the machine allows (`nproc`, RAM ~1.5 GB per worker for the minute-level jobs).

## Jobs, in order

1. **Level events dataset** (step 1 of the level rework), then **step 2**:
   ```bash
   .venv/bin/python research_level_events.py --months 12 --limit 100 --workers <N>
   .venv/bin/python research_level_factors.py            # -> research/level_factors.md
   ```
   (The owner's machine built 48 of 60 coins; rebuild all here - same code, deterministic.)
2. **B9 archive replay of the live card lifecycle** - the main job:
   ```bash
   .venv/bin/python replay.py --months 12 --coins 40 --group 5 --out data/replay/run12m
   .venv/bin/python research_replay_report.py --run data/replay/run12m --out research/replay.md
   ```
   Groups are independent: run several `replay.py` processes in parallel with disjoint `--symbols` lists (the top 40
   by volume split in groups of 5; one output dir per process under `data/replay/run12m/`), then one report over all.
   Commit `research/replay.md`; also write `research/replay_summary.parquet` (cards + entries concatenated, without the
   `f_*` feature columns) if it is under ~20 MB.
3. **Pools** (coin attributes vs method): `research_pools.py` -> research/pools.md
4. **Connors 5/95 re-run** (plan 2.7): `research_connors.py` -> research/connors_crypto.md
5. **Daily methods** (ORB + NR4/NR7, cup with handle in weekly ATRs; plan 2.1, 2.2, 2.10):
   `research_daily_methods.py` -> research/daily_methods.md
6. **ATR RMA vs SMA, volume bars** (plan 3.5, 3.7): `research_atr_volbars.py --coins 40` -> research/atr_volbars.md
7. **Volume profile from trades** (plan 3.6): `research_profile_trades.py --coins 12 --days 10`
   -> research/profile_trades.md
8. **Meta-labeling on the replay** (B9's purpose): with the replay's `entries.parquet` (passed entries, `f_*` features,
   `r_tp1`), a purged walk-forward by month (embargo 1 day) of LightGBM vs a logistic regression vs the base rate on
   `r_tp1 > 0`, per strategy with >= 300 entries; report AUC, and the mean net R of the top-ranked third vs all, both
   halves. Pre-register in the script's docstring: the meta-model is useful only if the top third beats all entries in
   both halves with the newer half's 90% interval (bootstrap of days) above 0. Script: `research_meta_replay.py`.

## Output

Commit each `research/*.md` (and the new script for job 8) to this branch as it finishes, with a one-paragraph
summary per study at the top of its file. A final `research/CLOUD_SUMMARY.md`: one table - study, verdict per its
pre-registered rule, the key numbers, what it means for the bot (in Russian; the owner reads it).
