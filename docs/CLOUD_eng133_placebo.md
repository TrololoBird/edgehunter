# Cloud task: entries vs placebo, shadow tags and macro features (eng-133, 2026-10-15)

Pre-registered: `research/PROTOCOL_entries_vs_placebo_eng133.md` (pass rule, placebo, statistics, the implementation
decisions). It is NOT changed after seeing results. Script: `research/scripts/research_entries_placebo_eng133.py`
(smoke-tested on the VPS: 3 coins / 12 days, no crash). Signal logic is not touched: `replay.py` only writes extra columns.

## Prompt to start the cloud session (paste as is)

> Clone the repo, read `CLAUDE.md`, `docs/CLOUD_eng133_placebo.md` and `research/PROTOCOL_entries_vs_placebo_eng133.md`,
> then run the task exactly as written. Do not change the bot's signal logic or the protocol; report bugs with file:line.
> Commit and push the report (small files only). Reply in Russian with a short summary.

## Steps
```bash
git clone <repo> pump && cd pump
python3.14 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests -q                       # must pass (75)
nproc; free -g                                            # ~1.5 GB RAM per replay worker
# 1. replay of the current logic (eng-133), 60 coins x 6 months, 24 shards (reduce to nproc)
mkdir -p logs
for k in $(seq 0 23); do nohup .venv/bin/python replay.py --months 6 --coins 60 --group 5 --shard $k/24 \
    --out data/replay/eng133 > logs/replay_$k.log 2>&1 & done; wait
# 2. the study (placebo simulations are ~100x the replay's: use all cores)
.venv/bin/python research/scripts/research_entries_placebo_eng133.py --run data/replay/eng133 --placebos 100 \
    --seed 133 --boot 5000 --workers $(nproc) --etf-file research/etf_flows_2026-10-15.json \
    --out research/entries_placebo_eng133.md
```
- Binance REST is geo-blocked in the cloud: everything reads `data.binance.vision` (`history.Archive`), cache under
  `history_cache/` (never commit). The macro step downloads the CBOE VIX CSV, alternative.me Fear & Greed and FRED
  DTWEXBGS into `data/macro_cache/`; a source that fails prints "unavailable" and its feature is reported as no
  verdict - say so in the summary, do not substitute another source. The Binance TradFi perpetuals (XAU / CL / SPY / QQQ)
  come from the archive (listed 2026-04 for CL / SPY / QQQ: the dev half is mostly empty for them).
- The ETF flows come from the committed snapshot `research/etf_flows_2026-10-15.json` (Farside, final-revised values: a
  mild look-ahead, the protocol says so; an ETF verdict needs the live journal columns `etf_flow_*` to confirm).
- Commit `research/entries_placebo_eng133.md` and the `*_placebo.parquet` next to it if < 20 MB. Never `data/`.
- Report: every family and feature with n / means / intervals / q, the passing and the failing alike; the PASS rule is
  the protocol's, applied mechanically; the descriptive blocks are not conclusions. Do not tune anything afterwards.
