# Cloud tasks (2026-10-06, after eng-72)

Three jobs that need the archive and many cores, not the live bot. Read `CLAUDE.md` (eng-61 .. eng-72 at its end) and
`docs/CLOUD_OPTIMIZE.md` (its Rules section applies here too: work on `master`, commit small results only, never
`history_cache/` / `data/`, pre-registered rules not changed after seeing results, ruff + pytest green). The cloud
cannot call Binance REST (HTTP 451); `data.binance.vision` (the archive), Deribit and DefiLlama are reachable.

## Task 1 - replay of the CURRENT logic (first; everything else depends on it)

eng-67 .. eng-71 changed the geometry (stop floor and targets in the structure timeframe's ATR, the stop beyond the
structure by max(pierce, 1.5 ATR of its timeframe), daily / weekly swings and the previous month / 52-week extremes in
the map, square-root slippage, Bollinger's stop buffer, VA80 traversed, PUMP START R:R 1). None of it is measured on
history; the last replay (`research/replay_summary.parquet`) is eng-59.

1. `docs/CLOUD_OPTIMIZE.md` step 1 with the current code: 120 coins x 24 months, groups of 5 in parallel
   (`replay.py` now reads BTC's minutes in every group - `_minutes_of`).
2. `research_replay_report.py` -> `research/replay_eng72.md`; `research_replay_summary.py` ->
   `research/replay_summary_eng72.parquet`.
3. The same audits as on eng-59, on the new summary (copy the scripts' outputs to `*_eng72.md`):
   `research_entry_edge.py` (entries vs placebo), `research_geometry_audit.py` (stop / TP1 in 1h ATR, R:R, cost in R),
   `research_bias.py` (the HTF gate by month and side). Report per strategy the change vs eng-59: stop distance in ATR
   of its timeframe, share of stops < 1 ATR, TP1 / stop ratio, full-trade final R (not the 8h r_tp1), by month.
4. Judge with the methodology of eng-66: full-trade outcomes, by month and side, >= 100 trades per verdict, placebo
   entries as the baseline, walk-forward (not one split), PBO / CSCV where a selection was made.
5. Then `docs/CLOUD_OPTIMIZE.md` steps 2-5 on this replay if, and only if, step 3 shows the geometry no longer eats
   the entries' edge (trendline / pump / breakout beat placebo at 2 ATR on eng-59).

## Task 2 - order book and order flow on the archive (the live-only confirmations)

The heat map, walls, liquidity bands, book imbalance, pulled vs filled and the footprint are journaled live only
(slowly: weeks for a verdict). The Binance archive holds what is needed to test them on history:
`data.binance.vision/data/futures/um/daily/bookDepth/<SYM>/` (depth in % bands around the price, ~minutely),
`.../bookTicker/` (best bid / ask), `.../aggTrades/` (every trade with the taker side).

Pre-register before looking (write the rules into the script's docstring, commit it, then run):
1. For every passed entry of Task 1's replay (and 10 placebo entries per entry: same coin / side / hour, other days),
   compute at the entry from the archive: book imbalance within 0.5% / 1% (bookDepth), the change of the opposite
   side's depth over the previous 30 min (a "wall" eaten or pulled), the taker delta since the setup's extreme
   (aggTrades), stacked imbalance / absorption as `flow.Footprint` defines them (aggTrades bucketed like the bot),
   spread (bookTicker).
2. Question per feature: do entries with the feature's "right" sign have a better full-trade final R than those
   without, by month, beating the same split on the placebo entries? BH-corrected over all strategy x feature cells
   (q 0.10), >= 30 independent 4h clusters per side of the split.
3. Output `research/book_flow_archive.md`; a feature is proposed as a required confirmation (CONFIG.orderflow
   .required_confirmations) only if it passes; the owner decides.
Cost: bookDepth / aggTrades are large (aggTrades of 120 coins x 24 months is hundreds of GB) - start with 30 coins x
6 months, report the effect sizes and their intervals, and extend only if they are promising.

## Task 3 - indicator formulas against TA-Lib (small)

`pip install polars-talib` (bundles TA-Lib). On 20 coins' 15m / 1h archive candles compare the bot's own
implementations (indicators.py, strategies/ind_panel.py, strategies/bias.py: EMA, RSI, MACD, ADX / DI, ATR, Bollinger,
stochastic, MFI, CCI, OBV) with TA-Lib's. Known intended differences (do not "fix"): ATR is a simple 14-candle mean
(not Wilder's RMA), Bollinger uses ddof=0. Report any other mismatch > 1e-6 relative in `research/talib_check.md`
with the formula and the line; do not change the bot - list the fixes for the owner.

## Not to do (decided 2026-10-06)
Coinalyze liquidation history (1500-2000 intraday points: too short), Glassnode / CryptoQuant / news / whale feeds
(days-scale or unproven), a new backtest engine (nautilus / vectorbt: the replay runs the live code).
