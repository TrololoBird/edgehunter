#!/bin/sh
# fourth wave (weekend): the period BEFORE the main window as an independent check of every result, plus maker
# entries. Pre-registered in research/prereg/weekend_prior_period.md
cd "$(dirname "$0")"
export PIERCE_MODEL=models/overshoot_pre.json
while [ ! -f logs/queue3.done ]; do sleep 300; done
W=3
.venv/bin/python research_vol.py --workers $W --window 2023-10-01,2024-10-01,2025-03-31 > logs/q4_vol.log 2>&1
.venv/bin/python research_xsec.py --workers $W --window 2023-10-01,2024-10-01,2025-03-31 > logs/q4_xsec.log 2>&1
cp research/classic_eng43.md research/classic_eng43_main.md 2>/dev/null
.venv/bin/python research_classic.py --months 18 --end 2025-03-31 --holdout 6 --workers $W > logs/q4_classic.log 2>&1
cp research/classic_eng43.md research/classic_eng43_2023.md 2>/dev/null
.venv/bin/python research_cards.py --months 18 --end 2025-03-31 --holdout 6 --what all --workers 4 \
  --out research/cards_eng43_2023.md --rows research_cards_eng43_2023.parquet \
  --samples research_samples_eng43_2023.parquet > logs/q4_cards.log 2>&1
.venv/bin/python research_maniac.py --months 18 --end 2025-03-31 --holdout 6 --limit 0 --workers 4 \
  --out research/maniac_eng43_2023.md --rows research_maniac_eng43_2023.parquet > logs/q4_maniac.log 2>&1
RESEARCH_ENTRY=maker .venv/bin/python research_cards.py --months 18 --end 2026-09-30 --holdout 6 --what all \
  --entry maker --workers 4 --out research/cards_eng43_maker.md --rows research_cards_eng43_maker.parquet \
  --samples research_samples_eng43_maker.parquet > logs/q4_maker.log 2>&1
echo done > logs/queue4.done
