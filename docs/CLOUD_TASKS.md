# Cloud tasks (2026-10-06, after eng-72)

Three jobs that need the Binance archive and many cores, not the live bot. The owner runs the bot on a Windows laptop;
a cloud session cannot run it or read its journal (`signals.db`, `demo_trades.db` stay local).

## 0. Prompt to start the cloud session (paste as is)

> Clone the repo, read `CLAUDE.md` (especially eng-59 .. eng-72 at its end) and `docs/CLOUD_TASKS.md`, then do
> Task 1, then Task 3, then Task 2 exactly as written there. Commit and push each step's report as soon as it is done
> (small files only). Do not change the bot's signal logic; report bugs you find with file:line and a proposed fix.
> Pre-registered rules are not changed after seeing results. Reply in Russian with a short summary per task.

## 1. Setup

```bash
git clone <repo> pump && cd pump
python3.14 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests -q                 # must pass (70)
nproc; free -g                                      # plan the parallelism: ~1.5 GB RAM per replay worker
```
- Binance REST is geo-blocked in the cloud (HTTP 451): everything here reads `data.binance.vision` through
  `history.Archive` (cached under `history_cache/`, never commit it) - no REST calls are needed.
- Work on `master`; commit `research/*.md`, `research/*.parquet` < 20 MB, scripts. Never `data/`, `history_cache/`.
- Before each commit: `.venv/bin/python -m ruff check --select F <changed files>` and `pytest tests -q`.
- Long jobs in the background with logs (`nohup ... > logs/x.log 2>&1 &`); check progress from the logs.

## Task 1 - replay of the CURRENT logic (first; everything else depends on it)

Why: eng-67 .. eng-71 changed the geometry (stop floor and targets in the structure timeframe's ATR, the stop beyond
the structure by max(pierce, 1.5 ATR of its timeframe), daily / weekly swings and the previous month / 52-week
extremes in the map, square-root slippage, Bollinger's stop buffer, VA80 traversed, PUMP START R:R 1). None of it is
measured on history; the last replay (`research/replay_summary.parquet` in the repo)
is eng-59: there trendline / pump / breakout entries beat placebo entries at 2 ATR but the geometry ate it
(trendline stops at 0.7 1h-ATR, pump TP1 closer than its stop), and bollinger / market_profile / connors entries did
not beat placebo at all (`research/entry_edge.md`, `research/geometry_audit.md`).

1.1 Smoke test (minutes): `.venv/bin/python replay.py --days 3 --coins 5 --out data/replay/smoke` - must finish
    without errors and write `group_00/{cards,entries}.parquet`.

1.2 The replay, 120 coins x 24 months, 24 groups of 5 coins (one SignalBook each). One process works through the
    groups one after another (~50 s per replayed day per group on a laptop core: 24 x 730 days is ~10 days on ONE
    core), so run N processes on the SAME --out with `--shard k/N` (each takes the groups whose index % N == k; every
    process makes the same coin selection; a finished group is skipped on a rerun, so a crash is resumed by rerunning):
```bash
mkdir -p logs; N=12      # <= cores and <= RAM / 1.5 GB
for k in $(seq 0 $((N-1))); do
  nohup .venv/bin/python replay.py --months 24 --coins 120 --group 5 --rate 5e6 --out data/replay/eng72 --shard $k/$N > logs/replay_eng72_$k.log 2>&1 &
done
tail -f logs/replay_eng72_0.log      # "<date>: N cards, M entries / vetoes, Xs" per replayed day
```
    The archive cache (`history_cache/`) is shared; `--rate` caps each process's download speed (bytes/s).

1.3 Summaries:
```bash
.venv/bin/python research/scripts/research_replay_report.py --run data/replay/eng72 --out research/replay_eng72.md
.venv/bin/python research/scripts/research_replay_summary.py data/replay/eng72 research/replay_summary_eng72.parquet
```

1.4 The audits of eng-59 on the new summary (env vars select the input / the report name):
```bash
export REPLAY_SUMMARY=research/replay_summary_eng72.parquet REPORT_SUFFIX=_eng72
.venv/bin/python research/scripts/research_entry_edge.py        # -> research/entry_edge_eng72.md  (entries vs placebo)
.venv/bin/python research/scripts/research_geometry_audit.py    # -> research/geometry_audit_eng72.md (stop / TP1 in 1h ATR, R:R, cost R)
.venv/bin/python research/scripts/research_bias.py              # -> research/bias_eng72.md (the HTF gate by month and side)
```

1.5 Report `research/eng72_vs_eng59.md` (Russian summary at the top), per strategy, eng-59 vs eng-72:
    - stop distance in ATR of the strategy's timeframe (median), share of stops < 1 ATR, TP1 / stop ratio,
      round-trip cost in R;
    - full-trade final R (the card's own exit, `final_r` / `card_r`, NOT the 8h `r_tp1`), mean and 90% cluster
      bootstrap interval (4h clusters), by month and by side; number of trades (a verdict needs >= 100);
    - entries vs placebo: P(+1R before -1R), P(+2R before -1R);
    - which vetoes now reject what (`vetoed` counts and the replayed R of the rejected entries next to the passed).
    Methodology (eng-66): full-trade outcomes, by month and side, placebo baseline, walk-forward (no single split),
    PBO / CSCV wherever something was selected.

1.6 Only if 1.5 shows that some strategy's entries keep their edge through the new geometry: run
    `docs/CLOUD_OPTIMIZE.md` steps 2-5 on `research/replay_summary_eng72.parquet` (OPT_PREFIX=research/optimize_eng72,
    profiles to `models/profiles_eng72.json`). Otherwise stop and report.

## Task 2 - order book and order flow on the archive (the live-only confirmations)

Why: the heat map, walls, liquidity bands, book imbalance, pulled vs filled and the footprint (`depth.py`, `flow.py`,
`strategies/confirm.py`) are measured live only - a verdict takes weeks. The archive has:
`data.binance.vision/data/futures/um/daily/bookDepth/<SYM>/` (cumulative depth and notional at +-1..5% of the price,
~every minute), `.../bookTicker/` (best bid / ask), `.../aggTrades/` (every trade, taker side). Check what exists per
coin / date first (`history.Archive` lists S3 prefixes; add `bookDepth` / `aggTrades` readers to `history.py`, cached
like the klines).

Pre-register first: write `research/scripts/research_book_flow.py` with the rules below in its docstring, commit it, THEN run it.
1. Inputs: every passed entry of Task 1 (`vetoed` null) + 10 placebo entries per entry (same coin, same side, same
   hour of day, random other days within +-120 days).
2. Features at the entry time (no look-ahead: only data with timestamps <= the entry):
   - book imbalance at 1% and at 2% (bookDepth bid vs ask notional) - the trade's side heavier = "with";
   - the opposite side's depth change over the previous 30 min within 2% (a wall eaten or pulled; bookDepth);
   - taker delta since the setup's extreme / over the last 15 min, in units of the coin's average minute (aggTrades);
   - footprint: stacked imbalance >= 3:1 over 3 price buckets of 5 bps and absorption (a 1m delta >= p90 of the hour
     against the trade with a range <= 0.2 ATR), as `flow.Footprint` / `fetcher.orderflow_confirm` define them;
   - spread at the entry (bookTicker), in bps.
3. Outcome: the full-trade final R of the replayed card (placebo: the same plan geometry replayed from the placebo
   time, `levels.simulate`).
4. Test per strategy x feature: mean final R with vs without the feature, minus the same difference on the placebo
   entries; 90% cluster-bootstrap interval (4h clusters); Benjamini-Hochberg over all cells at q 0.10; a cell needs
   >= 30 clusters on each side of the split. Report by month as well (a feature that helps in one month only is noise).
5. Scope: start with the 30 most liquid coins x the last 6 months (aggTrades is hundreds of GB for 120 x 24); report
   effect sizes and intervals; extend only promising cells.
6. Output `research/book_flow_archive.md` (Russian summary on top). A feature that passes is PROPOSED as a required
   confirmation (`CONFIG.orderflow.required_confirmations`); the owner decides - do not change the config.

## Task 3 - indicator formulas against TA-Lib (small, can run while Task 1 replays)

`.venv/bin/pip install polars-talib` (bundles TA-Lib). On 20 coins' 15m and 1h archive candles compare the bot's
implementations with TA-Lib on the same input:
- `indicators.py` (compute_indicators_batch: EMA, RSI, ATR, Bollinger, ADX / DI, MFI, OBV ...),
- `strategies/ind_panel.py` (the entry panel: EMA 20/50/200, RSI, MACD, ADX/DI, stochastic, %B, band width, MFI,
  OBV, CCI),
- `strategies/bias.py` (EMA50 / EMA20 weekly, ADX on 4h).
Intended differences (do not report as bugs): ATR is a simple 14-candle mean of true ranges (not Wilder's RMA),
Bollinger uses the population std (ddof=0), and warm-up rows. Report every other mismatch > 1e-6 relative in
`research/talib_check.md`: indicator, file:line, our value vs TA-Lib, the cause, the proposed fix. Do not change the
bot.

## Not to do (decided 2026-10-06)
Coinalyze liquidation history (1500-2000 intraday points: too short), Glassnode / CryptoQuant / news / whale feeds
(days-scale or unproven), a new backtest engine (nautilus / vectorbt: the replay runs the live code), Playwright cards.

## When done
Push; the owner pulls on the laptop. New profiles go under new names (`models/profiles_eng72.json`) - the owner swaps
them in. Every finding that needs a code change in the bot goes into the report as a list (file:line, why, fix).
