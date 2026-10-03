#!/bin/sh
# Confirmation study (2026-10-03, the owner: "do everything the archive allows"): research_cards / research_maniac in
# --confirm record mode on both windows, then research_confirms.py. IDEMPOTENT like run_all.sh (markers in logs/done,
# per-coin results in research_cache/). The disk allowance holds one window of 1m klines: the prior window first
# (on disk), then its 1m files are deleted and the main window is downloaded again.
# Start: setsid nohup ./run_confirms.sh >> logs/run_confirms.out 2>&1 < /dev/null &
cd "$(dirname "$0")"
mkdir -p logs/done
export PIERCE_MODEL=models/overshoot_pre.json
step() {
  name=$1; shift
  [ -f "logs/done/$name" ] && return 0
  echo "$(date -u +%FT%TZ) start $name"
  if "$@" > "logs/$name.log" 2>&1; then touch "logs/done/$name"; echo "$(date -u +%FT%TZ) done $name"
  else echo "$(date -u +%FT%TZ) FAILED $name (exit $?)"; fi
}
P=.venv/bin/python
E=2025-03-31
step rec_cards_2023  $P research_cards.py --months 18 --end $E --holdout 6 --what all --workers 4 --confirm record --out research/cards_rec_2023.md --rows research_cards_rec_2023.parquet --samples research_samples_rec_2023.parquet
step rec_maniac_2023 $P research_maniac.py --months 18 --end $E --holdout 6 --limit 0 --workers 4 --confirm record --out research/maniac_rec_2023.md --rows research_maniac_rec_2023.parquet
step confirms_2023   $P research_confirms.py --rows research_cards_rec_2023.parquet research_maniac_rec_2023.parquet --split 2024-10-02 --title "prior window 2023-10 .. 2025-03" --out research/confirms_2023.md
if [ -f logs/done/confirms_2023 ] && [ ! -f logs/done/drop_1m_2023 ]; then
  for y in 2023-10 2023-11 2023-12 2024-01 2024-02 2024-03 2024-04 2024-05 2024-06 2024-07 2024-08 2024-09 2024-10 2024-11 2024-12 2025-01 2025-02 2025-03; do
    find history_cache/futures/um/monthly/klines history_cache/spot/monthly/klines -path "*/1m/*-1m-$y.zip" -delete 2>/dev/null
  done
  touch logs/done/drop_1m_2023; echo "$(date -u +%FT%TZ) prior-window 1m files deleted"
fi
M="--months 18 --end 2026-09-30 --holdout 6"
step rec_cards_main  $P research_cards.py $M --what all --workers 4 --confirm record --out research/cards_rec_main.md --rows research_cards_rec_main.parquet --samples research_samples_rec_main.parquet
step rec_maniac_main $P research_maniac.py $M --limit 0 --workers 4 --confirm record --out research/maniac_rec_main.md --rows research_maniac_rec_main.parquet
step confirms_main   $P research_confirms.py --rows research_cards_rec_main.parquet research_maniac_rec_main.parquet --split 2026-04-03 --title "main window 2025-04 .. 2026-09" --out research/confirms_main.md
echo "$(date -u +%FT%TZ) all confirm steps attempted"
