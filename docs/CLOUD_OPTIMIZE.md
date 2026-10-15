# Cloud job: strategy optimization on a large replay (eng-62, 2026-10-05)

Goal (the owner's): adapt the classic methods to crypto futures - filters, coin classes, market regimes, position
management - until they are positive, and send the positive ones to the BingX demo. On the laptop
(40 coins x 12 months) only the Turtles held on the untouched months; the rest overfit (train +0.3..+1.1R ->
validation -0.2..-1.0R) because 750k configurations were searched over ~16k entries. This job repeats the search on
**120 coins x 24 months** so that a configuration has to hold across far more data.

Read `CLAUDE.md` (eng-61 / eng-62 at its end) and `research/optimize.md`, `research/optimize_robust.md`,
`research/optimize_regime.md` first.

## Rules
- Work on `master`; commit and push results as each step finishes (small files only: `research/*.md`,
  `research/*.parquet` < 20 MB, `models/profiles*.json`). Never commit `history_cache/` or `data/`.
- The selection rules are pre-registered in the docstrings of `research/scripts/research_optimize.py`, `research/scripts/research_optimize_robust.py`,
  `research/scripts/research_optimize_regime.py`. Do not change a rule after seeing results; a bug may be fixed (say so in the report).
- Do not change the bot's signal logic. The outputs ARE the bot's profiles: `models/profiles.json` /
  `models/profiles_regime.json` are read live (strategies/profiles.py) - write the new ones under a new name (step 5)
  and let the owner swap them.
- `ruff check --select F <files>` and `python -m pytest tests -q` stay green.
- Python 3.14: `python3.14 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
- Use the machine's cores; minute-level jobs need ~1.5 GB RAM per worker. Long jobs in the background.

## Steps

1. **Replay 120 coins x 24 months** (the live card lifecycle on the archive; `replay.py` runs the methods' OWN plans -
   the optimized profiles are switched off inside it). Split the top 120 by volume in groups of 5 and run groups in
   parallel, one output dir per process:
   ```bash
   .venv/bin/python replay.py --months 24 --coins 120 --group 5 --rate 5e6 --out data/replay/run24m
   # or in parallel: --symbols A,B,C,D,E --out data/replay/run24m/g01  (one per group)
   .venv/bin/python research/scripts/research_replay_report.py --run data/replay/run24m --out research/replay_24m.md
   .venv/bin/python research/scripts/research_replay_summary.py data/replay/run24m research/replay_summary_24m.parquet
   ```
   Commit `research/replay_24m.md` (and the summary parquet if < 20 MB, else keep it local and note its size).

2. **Optimization** (5m paths per entry x 524 position-management variants x filters; 16 months train / 8 validation):
   ```bash
   OPT_TRAIN_MONTHS=16 .venv/bin/python research/scripts/research_optimize.py --replay research/replay_summary_24m.parquet \
       --rate 5e6 --out research/optimize_24m
   ```
   It writes `research/optimize_24m.md`, `.parquet` and `_matrix.npz` (the matrix stays local if > 20 MB).

3. **Robust pass** (a configuration positive in BOTH training halves):
   ```bash
   OPT_TRAIN_MONTHS=16 OPT_PREFIX=research/optimize_24m .venv/bin/python research/scripts/research_optimize_robust.py
   ```

4. **Regime switch** (BTC 4h ADX >= 25 trend / range x ATR above / below its median -> 4 regimes):
   ```bash
   OPT_TRAIN_MONTHS=16 OPT_PREFIX=research/optimize_24m OPT_PROFILES=models/profiles_regime_24m.json \
       .venv/bin/python research/scripts/research_optimize_regime.py
   ```

5. **Profiles for the owner**: from steps 2-4 write `models/profiles_24m.json` in the format of `models/profiles.json`
   (see its first entry): per strategy the best profile that was positive on the 8 validation months, `status`
   `validated` when its validation lower 90% bound > 0, else `candidate`; strategies with no positive profile are left
   out. The Turtles (`breakout`) keep their own exits unless a profile beats their own exits' validation result (report
   both numbers).

6. **Report** `research/CLOUD_OPTIMIZE_SUMMARY.md` (Russian, for the owner): per strategy - the best profile, train vs
   validation R, trades per month, verdict; which regimes; what changed against the laptop's 40 x 12 run; anything
   that did not work. Then push.

7. **Methodology of every study (the owner's audit, 2026-10-05)**: outcomes over the WHOLE trade (the card's `final_r`)
   and fixed horizons 8 / 24 / 72h side by side - never the 8h `r_tp1` alone for a daily rule; passed entries as the
   main sample (vetoed ones apart); rolling walk-forward (3 months train -> 1 month test, rolled monthly) instead of one
   split, with PBO by CSCV over the searched configurations; >= 100 trades for a verdict; results by month, by market
   phase (BTC up / down / flat) and by side. Coins picked by their volume AT the time (delisted ones included).
8. **Re-run on the 24-month replay**: `research/scripts/research_bias.py` (top-down bias, fixed rule), `research/scripts/research_overlays.py` (early
   exits), `research/scripts/research_htf_filter.py` (replace its 8h `r_tp1` by the card's `final_r`), each with the summary path of
   step 1; report them in the summary.
