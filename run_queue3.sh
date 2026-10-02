#!/bin/sh
# third wave: replications of the earlier archive studies up to 2026-09 (new names, the originals stay)
cd "$(dirname "$0")"
export PIERCE_MODEL=models/overshoot_pre.json
while [ ! -f logs/queue2.done ]; do sleep 120; done
W=3
.venv/bin/python research_htf.py --workers $W --out research/htf_phases_rerun.md > logs/q3_htf.log 2>&1
.venv/bin/python research_level_triggers.py --workers $W --out research/level_triggers_rerun.md > logs/q3_lt.log 2>&1
.venv/bin/python research_pumps.py --workers $W --out research/pumps_rerun.md > logs/q3_pumps.log 2>&1
.venv/bin/python research_channels.py --workers $W --out research/channels_rerun.md > logs/q3_channels.log 2>&1
.venv/bin/python research_eqh.py --out research/eqh_rerun.md > logs/q3_eqh.log 2>&1
.venv/bin/python research_trend_daily.py --out research/trend_daily_rerun.md > logs/q3_trend.log 2>&1
.venv/bin/python research_ensemble.py --out research/ensemble_trend_rerun.md > logs/q3_ensemble.log 2>&1
.venv/bin/python research_positioning.py --out research/positioning_rerun.md > logs/q3_positioning.log 2>&1
echo done > logs/queue3.done
