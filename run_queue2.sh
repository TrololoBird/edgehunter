#!/bin/sh
# second wave: after run_queue.sh finished
cd "$(dirname "$0")"
export PIERCE_MODEL=models/overshoot_pre.json
while [ ! -f logs/queue.done ]; do sleep 120; done
mv research/null_audit.md research/null_audit_6coins.md 2>/dev/null
.venv/bin/python null_audit.py archive --coins 30 --months 6 > logs/null_archive30.log 2>&1
.venv/bin/python research_meta.py --samples research_samples_eng43.parquet --out research/meta_eng43.md > logs/meta.log 2>&1
.venv/bin/python research_exits.py --samples research_samples_eng43.parquet --out research/exits_eng43.md > logs/exits.log 2>&1
.venv/bin/python train_scenarios.py --months 18 --workers 3 --out research/scenario_model_eng43.md > logs/scenarios.log 2>&1
echo done > logs/queue2.done
