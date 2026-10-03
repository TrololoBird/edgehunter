#!/bin/sh
# Every cloud run of the eng-43 validation and the ML plan, in order. IDEMPOTENT: a step whose marker exists is
# skipped, and the long per-coin replays resume from research_cache/ - the container restarted twice on 2026-10-02
# and killed every process. Start (or restart) with:  setsid nohup ./run_all.sh > logs/run_all.out 2>&1 < /dev/null &
cd "$(dirname "$0")"
mkdir -p logs/done
export PIERCE_MODEL=models/overshoot_pre.json
step() {  # step NAME COMMAND...
  name=$1; shift
  [ -f "logs/done/$name" ] && return 0
  echo "$(date -u +%FT%TZ) start $name"
  if "$@" > "logs/$name.log" 2>&1; then touch "logs/done/$name"; echo "$(date -u +%FT%TZ) done $name"
  else echo "$(date -u +%FT%TZ) FAILED $name (exit $?)"; fi
}
P=.venv/bin/python
M="--months 18 --end 2026-09-30 --holdout 6"
step cards     $P research_cards.py $M --what all --workers 4 --out research/cards_eng43.md --rows research_cards_eng43.parquet --samples research_samples_eng43.parquet
step classic   $P research_classic.py $M --workers 4
[ -f logs/done/classic ] && cp research/classic_eng43.md research/classic_eng43_main.md
step maniac    $P research_maniac.py $M --limit 0 --workers 4 --out research/maniac_eng43.md --rows research_maniac_eng43.parquet
step vol_eval2 $P research_vol.py --from-rows
step pretrain  $P pretrain.py --months 18 --workers 4 --rate 40000000
step ml_eval   sh -c "$P ml_eval.py > research/ml_eval_eng43.txt"
step null_ml   $P null_audit.py ml
step regimes   $P research_regimes.py --source current
step null30    $P null_audit.py archive --coins 30 --months 6
step meta      $P research_meta.py --samples research_samples_eng43.parquet --out research/meta_eng43.md
step exits     $P research_exits.py --samples research_samples_eng43.parquet --out research/exits_eng43.md
step vol_2023  $P research_vol.py --workers 4 --window 2023-10-01,2024-10-01,2025-03-31
step xsec_2023 $P research_xsec.py --workers 4 --window 2023-10-01,2024-10-01,2025-03-31
step classic_2023 $P research_classic.py --months 18 --end 2025-03-31 --holdout 6 --workers 4
[ -f logs/done/classic_2023 ] && cp research/classic_eng43.md research/classic_eng43_2023.md && cp research/classic_eng43_main.md research/classic_eng43.md
step cards_2023 $P research_cards.py --months 18 --end 2025-03-31 --holdout 6 --what all --workers 4 --out research/cards_eng43_2023.md --rows research_cards_eng43_2023.parquet --samples research_samples_eng43_2023.parquet
step maniac_2023 $P research_maniac.py --months 18 --end 2025-03-31 --holdout 6 --limit 0 --workers 4 --out research/maniac_eng43_2023.md --rows research_maniac_eng43_2023.parquet
# step maker (dropped 2026-10-03: the disk allowance; needs the main window 1m data, deleted)     env RESEARCH_ENTRY=maker $P research_cards.py $M --what all --entry maker --workers 4 --out research/cards_eng43_maker.md --rows research_cards_eng43_maker.parquet --samples research_samples_eng43_maker.parquet
step scenarios $P train_scenarios.py --months 18 --workers 4 --out research/scenario_model_eng43.md
step htf       $P research_htf.py --workers 4 --out research/htf_phases_rerun.md
step lt        $P research_level_triggers.py --workers 4 --out research/level_triggers_rerun.md
step pumps     $P research_pumps.py --workers 4 --out research/pumps_rerun.md
step channels  $P research_channels.py --workers 4 --out research/channels_rerun.md
step eqh       $P research_eqh.py --out research/eqh_rerun.md
step trend     $P research_trend_daily.py --out research/trend_daily_rerun.md
step ensemble  $P research_ensemble.py --out research/ensemble_trend_rerun.md
step positioning $P research_positioning.py --out research/positioning_rerun.md
echo "$(date -u +%FT%TZ) all steps attempted"
