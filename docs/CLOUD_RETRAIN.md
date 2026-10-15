# Full retraining in a cloud session (eng-59)

The bot runs on the owner's Windows laptop; this file is for a CLOUD session that rebuilds every model and archive
study from the Binance public archive (data.binance.vision). Binance's REST API may be geo-blocked in the cloud; the
archive is not. The live journal (`signals.db`) and the demo (`demo_trades.db`) are NOT in the repo and not needed.

## Rules
- Work on `master`; commit and push results as each job finishes (small files only: `models/*.json`, `research/*.md`,
  pickles < 20 MB). Never commit `history_cache/` or `data/`.
- Every study's decision rule is pre-registered in its script's docstring. Do not change a rule after seeing results.
  A bug in a script may be fixed (note it in the report); `ruff check --select F` and `python -m pytest tests -q` stay
  green. Do not change the bot's signal logic (signal_book.py, strategies/*, config values) - the owner decides that
  from the reports.
- Python 3.14: `python3.14 -m venv .venv && .venv/bin/pip install -r requirements.txt` (`uv python install 3.14` if
  missing; winloop is Windows-only and skipped).
- Use the machine's cores: minute-level jobs need ~1.5 GB RAM per worker. Long jobs run in the background; keep going
  until all are done.

## 1. Models the bot loads (commit the outputs)
| # | Command | Output |
|---|---|---|
| 1 | `pretrain.py --months 12 --workers <N> --rate 2e7` | `pretrained.pkl` (P(edge) start + regime history; the bot also rebuilds it itself weekly - commit only if < 20 MB) and `pretrain_rows.parquet` (keep, not committed) |
| 2 | `ml_eval.py` | research/ml_eval_12m.txt (P(edge) out of sample) |
| 3 | `research/scripts/research_overshoot.py --months 12 --limit 120 --workers <N>` | models/overshoot.json (stop buffers beyond levels) + research/overshoot.md |
| 4 | `research/scripts/research_level_weights.py --months 12 --limit 100 --workers <N>` | models/level_weights.json + research/level_weights.md |
| 5 | `research/scripts/research_regimes_hmm.py` (after 1: reads pretrained.pkl) | research/regimes_hmm.md |

`models/scenario_prob.pkl` has no trainer in the repo (built once by hand); leave it as is and say so in the summary.

## 2. Archive studies (docs/CLOUD_RESEARCH.md, jobs 1-8)
Run all eight jobs of `docs/CLOUD_RESEARCH.md` (level events + factors, the B9 replay `replay.py` + report, pools,
Connors, daily methods, ATR / volume bars, trade-based profile, meta-labeling on the replay - `research/scripts/research_meta_replay.py`
is to be written there, its rule in the docstring before running). Note: research/level_factors.md (59 coins x 12
months) was already produced on the laptop; rebuild with `--limit 100` only if time allows.

## 3. Summary
`research/CLOUD_SUMMARY.md` in Russian: one table - job -> verdict by its pre-registered rule -> key numbers -> what
it means for the bot; the models rebuilt (old vs new numbers for overshoot.json / level_weights.json); bugs fixed in
scripts; what could not run and why. Commit, push to master.

On the laptop afterwards: `git pull`, then a graceful bot restart (CLAUDE.md, Working with the owner) to load the new
models.
