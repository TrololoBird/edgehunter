#!/bin/sh
# eng-43 validation + ML plan runs, one after another (the cloud container has 4 cores)
cd "$(dirname "$0")"
export PIERCE_MODEL=models/overshoot_pre.json
while pgrep -f "python research_vol.py" >/dev/null; do sleep 60; done
.venv/bin/python research_xsec.py --workers 3 > logs/xsec.log 2>&1
.venv/bin/python research_classic.py --months 18 --end 2026-09-30 --holdout 6 --workers 3 > logs/classic.log 2>&1
while pgrep -f "python research_cards.py" >/dev/null; do sleep 60; done
.venv/bin/python research_maniac.py --months 18 --end 2026-09-30 --holdout 6 --limit 0 --workers 4 \
  --out research/maniac_eng43.md --rows research_maniac_eng43.parquet > logs/maniac.log 2>&1
.venv/bin/python pretrain.py --months 18 --workers 4 --rate 40000000 > logs/pretrain.log 2>&1
.venv/bin/python ml_eval.py > research/ml_eval_eng43.txt 2>&1
.venv/bin/python null_audit.py ml > logs/null_ml.log 2>&1
.venv/bin/python research_regimes.py > logs/regimes.log 2>&1
echo done > logs/queue.done
