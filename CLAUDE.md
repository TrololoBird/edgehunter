# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An asyncio crypto market-microstructure scanner ("Microstructure Scanner") for a **manual** trader. Universe: up to 150 Binance USD-M perpetuals with **complete data** (`fetcher.select_universe`: a Binance spot pair, >= 2 other futures venues, listed >= 9 days, spread <= 10 bp, >= $10M 24h volume, most liquid first; the market baseline for Edge still covers every USDT perpetual via REST mark prices); Bybit, OKX, Hyperliquid, Bitget (futures) and Coinbase (spot) enrich it with trades, liquidations, OI and funding. It flags raw Tier-0 anomalies and turns directional events into cards of **strategies, each with its own anchor, entry and targets** (`strategies/`): Wyckoff reversals and trend continuations from six 15m phases (A Accumulation, B Spring, C Distribution, D Breakdown, E Capitulation, F Markup), the Tier-0 momentum impulse, liquidity sweeps of higher-timeframe pools, liquidation-cascade exhaustion, absorption at a level and breakouts with initiative. Zones / stops / targets come from a per-coin level map (support / resistance, liquidity pools, estimated and real liquidations, volume profile, walls, order-book liquidity bands, VWAP, Fibonacci). Everything is journaled in SQLite and shown in a browser dashboard with an order-book heatmap. Levels are mechanical rules measured by the journal (`stats.py`), never advice; phase weights, detector thresholds, level-source weights and Fibonacci ratios are unproven hypotheses, which is why every filter, family and target source is journaled.

## Commands

```bash
py -3.14 -m venv .venv && .venv\Scripts\python -m pip install -r requirements.txt   # Python 3.14
.venv\Scripts\python main.py                  # bot + browser dashboard http://127.0.0.1:8765 (console = log; scanner.log, rotated 10 MB x 5)
.venv\Scripts\python main.py --no-web         # log only
.venv\Scripts\python stats.py --days 7 --last 20   # outcome statistics (current logic version; --all-versions for all)
.venv\Scripts\python pretrain.py --months 6       # pretrain regimes + P(edge) on the Binance public archive (bot stopped or low --rate)
.venv\Scripts\python -m pytest tests -q       # offline checks of formulas / parsers (recorded WS samples in tests/fixtures)
```

**Verify behaviour with live runs, not by adding tests.** Offline tests only catch formula/parsing slips; stream behaviour (bandwidth, lag, disconnects, exchange quirks) only shows live. Run `main.py` (or `--no-web`) for 5-10 minutes and read the `Health:` line logged every minute (Tier-0 / scan / heavy-pass time, cpu, memory, per-venue messages/s and KB/s, lag, DOWN venues) and the WARNING lines. Don't add tests unless a live run exposed a concrete bug; ask first.

Optional `config.local.toml` next to `config.py` overrides any `CONFIG` value (`[section] key = value`, type-checked at start-up), e.g. `[notify] enabled = true` with your own `telegram_token` / `telegram_chat_id`.

Start-up: ~30s to load instrument lists of all venues, then streams start; the 15m candle history loads in the background (~55s for 300 symbols) and a symbol joins scoring once its history is in (`MarketData.baseline_ready`). Tier-0 warms up for 5 min (no signals / journal rows before). Open cards and whale-size histograms are restored from `scanner_state.json`.

## Architecture

`main.py → scanner.Scanner → fetcher.DataFetcher (+ venues.*Stream, flow, depth, symbols, ratelimit) → indicators → scorer / strategies (detect, structure) → signal_book (+ strategies, levels, zones, positioning) → webui / journal / notifier`; `watchdog.LoopWatchdog` watches the event loop, `storage.atomic_write` writes state files. All tunables are frozen dataclasses in `config.py` reached through the global `CONFIG`.

### Data layer
- **Bandwidth is the binding constraint, not CPU.** Measured live: one socket to Binance carries ~40-70 KB/s; beyond that its send buffer fills, data lags 5-20s and the server drops the connection. So: Binance streams are only `@kline_1m` (spot + futures), `@aggTrade` for every futures symbol, `!forceOrder@arr`, and `@depth20@500ms` for ≤40 hot symbols; each group is split over several sockets (`subs_per_connection` 60-120). Never subscribe whole-market arrays (`!markPrice@arr@1s`, `!miniTicker@arr` ~100 KB/s): funding / mark / index come from REST `premiumIndex` every 30s, 24h volumes from REST `ticker/24hr` every 5 min, the last price from aggTrades. Watch the per-venue KB/s in the Health line when adding streams.
- **15m candles are built from closed 1m candles** (`MarketData._add_closed_minute`): exactly Binance's 15m candle (verified live against REST), without a second kline stream. A bucket that started mid-candle or missed minutes is **not final**: it sits in the frame but `MarketData.incomplete` keeps scoring on the history before it until the REST candle replaces it (`request_backfill(need_ts)` retries until REST publishes that candle; afterwards only complete stream candles newer than the snapshot are re-applied). Scoring such a candle gave wrong phases / spot-perp flows after every start and stream gap (measured: all REST mismatches of journaled setups).
- **WebSocket transport: picows** (`venues.VenueStream`): frames are handled in the data callback. With aiohttp one message was consumed per event-loop iteration and the busiest socket fell behind. Protocol pings only when a socket is idle (`idle_timeout`); app-level pings where a venue needs them (Bybit JSON ping, OKX/Bitget text `ping`); reconnect backoff resets only after data flowed. `use_aiofastnet=False` (its OpenSSL DLL lookup fails on some builds; `_import_picows` silences its stderr print).
- **Binance USD-M routing (2026 split)**: klines / aggTrade / forceOrder on `wss://fstream.binance.com/market/stream`, order books on `/public/stream`; unrouted legacy URLs connect but push nothing.
- **Other venues** (`venues.py`): Bybit `publicTrade` + `allLiquidation` (complete liquidations); OKX `trades` (sizes × `ctVal`), `open-interest`, `funding-rate`, `liquidation-orders`; Hyperliquid `activeAssetCtx` for all mapped coins, `trades` for up to 150 mapped coins (dynamic); Bitget `trade`; Coinbase `market_trades` (spot; its `side` is the MAKER side). Bybit / Bitget OI and funding come from one bulk REST ticker call each every 30s (their ticker streams pushed ~2700 msgs/s). Taker side: Binance `m=true` = sell; Bybit `S`, OKX/Bitget `side` = taker; Hyperliquid `B` = buy.
- **Verified live against the venues' REST (2026-09-26)**: per-minute volume and taker side 1:1 on Binance / Bybit / OKX / Bitget / Coinbase, OI and 8h funding per venue, volume profile (15m candles match 1m within a bucket; the 4-day profile uses 5m, 1h put the POC 3% off), OKX liquidations (count, USD, side), Binance whale sweeps rebuilt from aggTrades. `/api/debug?symbol=` exposes the per-coin internals for such checks. Bitget funding comes from `current-fund-rate` (387 contracts settle every 4h).
- **Universe selection** (`fetch_candidates` -> `select_universe`, at start-up and hourly): candidates = every perpetual above the volume floor; the venues' instrument lists are loaded first and kept (`SymbolMap._rows`), so each candidate's venue coverage is known before it joins (`SymbolMap.coverage`) and a coin that joins later is mapped to its venues too (before, only the start-up universe was ever mapped). The freed bandwidth goes to data per coin: 40 order books (6 sockets), Hyperliquid trades for up to 150 coins, positioning every 5 min for every coin. Strategies declare the data they cannot be judged without (`Strategy.requires`: trend / momentum / breakout need a spot market, else vetoed `no_data`).
- **Symbol mapping** (`symbols.SymbolMap`): the key of every coin is its Binance futures ccxt symbol (`1000PEPE/USDT:USDT`). Other venues map by base coin with unit multipliers (`1000PEPE`, `kPEPE`, `1MBABYDOGE`); everything is aggregated in USD notional (`price × size × contract_value`). Every mapping is price-checked at start-up against one bulk ticker call per venue (`SymbolMap.verify_prices`, before anything is subscribed); a per-coin price >10% off Binance means a different token under the same ticker and the mapping is dropped (QNT, BB on OKX, EDGE on Coinbase). Market lists and tickers are loaded with synchronous ccxt in worker threads (`_load_markets_off_loop`, `load_venues`): parsing thousands of markets on the loop blocked it ~2s. ccxt market lists of other venues are discarded after mapping (they held ~500 MB).
- **Weekly trend of every coin** (`DataFetcher._weekly_candles_loop`: 60 weekly candles, weight 1, after each weekly close and for joining coins): `MarketData.w1_ref` = EMA20 of the closed weekly closes and the weekly return std (`strategies.structure.weekly_ref`); `trend_w` = the price's distance from it in weekly std, `breadth_w` = the universe's share above it (`Scanner._update_market_state`). Context only (journal, P(edge) × direction, stats splits, pretraining from REST weekly candles): tested on 120 coins' full daily history (2026-09-27), the weekly / monthly EMA is no level of its own — touches, crosses, retests and the big moves after them match parallel lines EMA × 0.8..1.2 once volatility and run-up are matched; what differs is the trend they happen in. Never a level source or veto until the journal proves it.
- **1h candles of every coin** (`DataFetcher._hourly_candles_loop`, `MarketData.h1`: 200 candles ≈ 8 days, weight 2, a minute after each hour, after the 15m history): the pools of previous day / week / sessions, 1h swings and the coins' trends exist for all 300 coins (~600 weight / hour). Card coins additionally load `load_htf` (1h OI history for the liquidation estimate, 4 days of 5m for the volume profile).
- **Restart-safe inputs**: at start-up (and when a coin joins) each coin's stream histories are seeded from REST: the last hour of 5m `openInterestHist` (`MarketData.seed_oi`, 13 points), 4h of futures and 1h of spot 1m klines plus the futures closes as price samples (`MarketData.seed_minutes`: a streamed candle wins), so OI changes, flows, RVOL, absorption, triggers and entry confirmations have their inputs right after a restart — before, the first hour after every start had no 1h OI reading and no spot / divergence history. **OI** it is then polled by `_oi_loop` with 8 requests in flight at evenly spread slots (sequential polling took ~2 min per pass over this link and left the 5m OI change at 0).
- **REST** (`ratelimit.RestGate`): every Binance REST call goes through `DataFetcher._rest_call`: a proactive weight budget (reads `X-MBX-USED-WEIGHT-1M`, stays under 70% of the limit, lower priorities get a smaller share: 0 candles/backfill, 1 OI/tickers, 2 journal outcomes/positioning) plus a shared pause on 429/418 (`banned until`, `Retry-After`). Futures klines use limit 99 (weight 1). OI: Binance has no OI stream; `_oi_loop` polls each symbol once a minute, spread evenly. `openInterestHist` timestamps are period END times.

- **Data recorder** (`recorder.py`, `CONFIG.recorder`, eng-8): the live-only data the public archive lacks goes to Parquet under `data/recorder/<flow|depth|deriv>/date=YYYY-MM-DD/` (minute files merged into `HH.parquet` after the hour): per second x venue x coin taker buy / sell and liquidation USD (the FlowStore rings), every 500-level book of the hot coins as 0.1% bands to 5% per side + live top-20 metrics, per minute x venue OI (coins, USD) / mark / funding. The loop only slices the finished minute (numpy); frames and writes run in the level-map worker process. ~270 MB a day. Purpose: test microstructure as a FILTER for 1h-4h trades later (a manual entry is seconds late for tick signals).

### Positioning (`positioning.py`, card coins only; context and levels, never a trigger)
- Long/short ratios: Binance global accounts / top accounts / top positions, Bybit and OKX account ratios (5m): card coins every 5 min, every other universe coin every 30 min (`positioning_universe_sec`), concurrently within the /futures/data budget (OKX one request at a time: 5 / 2s); a coin keeps its last ratios until new ones arrive. `hl_net_usd` is 0 when no tracked account holds a coin listed on Hyperliquid.
- Hyperliquid large accounts: the 300 most active accounts by monthly volume with >= $100k equity, picked from the public leaderboard (~40 MB, downloaded once a day at a capped 1 MB/s: unthrottled it saturated the link and the streams lagged 38s; cached in `hl_accounts.json`); their positions every 5 min. Real liquidation prices become `liq_hl` levels, net long/short is context (`hl_net_usd` journaled).
- Coinbase premium (Coinbase USD vs Binance spot, relative to the universe median: the raw value carries the USDT/USD basis) from the live trades, else from one REST call a minute for the universe's products (`_coinbase_prices_loop`); OKX liquidations are refilled from REST after a restart.
- Journal columns `ls_global`, `ls_top`, `hl_net_usd`, `cb_premium`; stats.py splits Edge by crowd, HL accounts vs the signal, premium.

### Order flow (`flow.py`, `depth.py`)
- `FlowStore`: numpy ring buffers per venue × symbol × second (taker buy / sell USD, long / short liquidation USD, counts). O(1) writes; `snapshot()` computes all windows for all symbols at once (the 1h window is cached 30s). Binance `forceOrder` is sampled (≤1 per symbol per second); Bybit's feed is complete.
- Whales = **sweeps**: prints of one side with the same trade time or within 300ms are merged (`SweepTracker`) before sizing. Whale size per coin = rolling p99.5 of its sweep sizes (log-histogram decayed hourly), floored by liquidity tier ($500k top 2, $100k top 30, $25k rest). Algo clusters: ≥5 notable same-side sweeps within 60s summing to a whale.
- `Footprint`: bid×ask USD per price bucket per minute, only for cards in ZONE. `DataFetcher.orderflow_confirm` = stacked diagonal imbalance ≥3:1 over 3 levels, or absorption (a 1m delta ≥ p90 of the hour AGAINST the trade with a range ≤0.2 ATR).
- Order books (`DepthBook`): live top 20 levels (`@depth20@500ms`: spread, walls counted only after standing 10s — spoofing) plus a 500-level REST snapshot per hot symbol every 60s (`_deep_books_loop`, weight 10, only for books with a live stream: `DepthBook.active`): on small-tick coins the top 20 levels cover far less than ±0.5%, so band depth / imbalance and sweep-vs-depth use the deeper book. Partial-book streams push only on change: a book is stale after 60s without updates.
- **Heatmap**: every 500-level snapshot is bucketed on a fixed per-coin price grid (0.1% of price, ±5% around the mid, compact `array`s, ~2h kept, also after the coin leaves the hot set) and drawn behind the candles in the coin panel (`/api/coin` → `heatmap`). A bucket holding ≥4× the snapshot's median bucket in ≥80% of the last 30 min of snapshots is a **liquidity band** (`DepthBook.liquidity_bands`, bids below / asks above the price): a level source `book` of its own (resting size that stayed, not a flashed wall). Only ≤40 hot coins have books (bandwidth).

### Signals
- **Strategies** (`strategies/`; `STRATEGIES`, `SETUPS` = setup name → strategy and direction, `strategy_of`). Each class of market event has its own **anchor** (a leg, a level or a range), entry, invalidation, stop reference and **target intent**; only the stop floor, R:R, the card lifecycle and the journal are shared (`strategies/geometry.py`, `signal_book.py`). Fibonacci exists only where a real leg exists. Timeframe rule: events are detected on any data (ticks, 1m), the structure is never finer than 15m, the entry never finer than 5m and 3-6× finer than the structure (Elder's factor of ~5: 15m → 5m, 1h → 15m, 4h → 1h, `levels.TRIGGER_MINUTES`). `CONFIG.strategies.enabled` turns a strategy's cards off (still journaled, `vetoed='disabled'`).
  - **Current registry (eng-43; the history of each change is in the eng-NN notes at the end)** - one methodology =
    one strategy name, several playbooks may share it:
    - `continuation` (BULL F / BEAR D: Bollinger method I out of a squeeze; IMPULSE UP / DOWN: Tier-0) - ICT OTE
      pullback 0.62-0.79 of a leg with displacement, Elder's tide ~5x the leg, invalid beyond the leg's start, targets
      the trend-based extension 1.0 / 1.2 / 1.272 / 1.618 from the pullback.
    - `sweep` (SWEEP LOW / HIGH; SILVER BULLET LONG / SHORT) - ICT: weekly / daily bias, the raid into a 1h+ PD array,
      discount / premium, entry at the FVG's CE on 5m, targets the draw on liquidity; SMT and the kill zone are
      confirmations.
    - `wyckoff` (SPRING / UTAD of a 1h range with the test; FLUSH / SQUEEZE REVERSAL = the climax's secondary test).
    - `breakout` - the Turtles (daily System 1 / 2, 2N stop, units + pyramid, N-day channel exit).
    - `supply_demand` - Seiden: 4h zones, 1h touch, the curve, R:R 3.
    - `market_profile` (AUCTION LONG / SHORT POC retest; VA80 LONG / SHORT Dalton's 80% rule).
    - `trendline` (1h lines, Edwards & Magee), `bollinger` (W-bottom / M-top, the measured move), `orb` (Crabel),
      `connors` (daily RSI(2)), `cup_handle` (O'Neil, 1h / 4h), `pump` (PUMP START / PUMP TOP, the owner's, with 1:1
      averaging).
    - The 15m phase scores (A-F) are still computed and journaled as structured rows; only D / F feed `continuation`.
    - Deleted (eng-35): Third Eye, Bomberman, OI accumulation, fib 0.5, the standalone SMT / absorption setups, the 15m
      phase reversals (BULL A / B / E, BEAR C). The paragraphs below that still name them describe the history.
  - Minimum legs follow from the stop rule and R:R ≥ 1: a reversal's first retracement target is 0.382 of its leg, so under ~3 ATR it cannot pay even from the extreme.
  - Detection: `strategies.structure.build_maps` (worker PROCESS, after each 15m close: level maps, pools, the coin's 1h trend, volatility, the closed candle's sweep / breakout events, fired once while it is the latest candle, up to 15 min: a feed gap delays the REST replacement by minutes; fired events persist in scanner_state.json) and `strategies.detect.LiveDetector` (loop: releases those events once, absorption on each new final 1m candle, cascades). Journal rows `kind='setup'` with the detector's note in `reason`.
- **Tier 0** (`Scanner.tier0_loop`, every 2s): `indicators.calculate_tier0_metrics` + FlowStore / WhaleBook / deriv snapshots. Anomaly (`PhaseScorer.flag_tier_0_anomaly`): RVOL_1m > 5 on a ≥$25k minute (ignored in the first 45s after each quarter-hour: algo bursts); |price 5m| > 1% AND |z| ≥ 4 of the coin's typical 5m move (std of 15m changes / √3), or > 2% while volatility is unknown; same for OI (0.8%); net whale sweeps ≥ 3 whale sizes; algo cluster; liquidation cascade (≥$50k and ≥1 average minute in 5m); ONE-VENUE (≥80% of the 5m net flow from one venue). Held 60s (hysteresis).
- **Phases** are scored only on **closed** 15m candles (`scorer.score_closed`). The heavy Polars pass (`compute_indicators_batch` + scoring, `.over('symbol')`, in `asyncio.to_thread`) runs only when a candle closed or history changed (signature = finalized_until + `history_version`); every scan the light pass (`signals_from_rows`) joins the cached rows with live Tier-0 metrics. Only finalized candles are merged into the frames; card plans get the live candle from `MarketData.live_candle`. Spot frames drive price/CVD (futures for futures-only listings), futures columns are as-of joined. Phases: A squeeze + tight range with sellers absorbed + OI building; B Wyckoff spring (shallow sweep of an established SIDEWAYS range — net move over the 20 candles ≤ half their span, `spring_max_drift`: a channel down also fit "range ≤ 6 ATR" and those springs went the signal's way within 15m 27% of the time — closed back inside on net selling); C new high on net selling (+ funding crowding, + spot selling at the high); D close below lower BB, sellers ≥60%, OI +0.5%/1h; E volume climax after a decline of ≥ 3 standard deviations of the coin's 15m returns × √10 (floor 1%) with an OI flush of ≥ 2 OI standard deviations × √4 (floor 0.5%): per-coin volatility, not a fixed 3% for BTC and small caps alike (+ spot absorbing, + long liquidations); F close above the upper BB, buyers ≥60%, OI +0.5%/1h, funding below the extreme. Long = A+B+E+F, short = C+D (`scorer.LONG_PHASES` / `SHORT_PHASES`), alert at 3, ties are no signal.
- **Spot vs perp**: `perp_led` = perp net flow over 1h drives the move while spot disagrees or is < 25% of it (multi-venue aggregate once 20 candles were accumulated live). Perp-led IMPULSE UP/DOWN, BEAR D and BULL F are **vetoed**: not a card, journaled with `vetoed='perp_led'`, shown in Forming with ✗.
- **Impulses** (`journal.classify`): directional only with OI ≥ +0.3%/5m and agreeing perp flow; observed liquidations decide SHORT SQUEEZE / LONG FLUSH; else IMPULSE UNCONFIRMED. Other labels: LIQ CASCADE, WHALES BUY/SELL, ALGO BUY/SELL, OI SURGE/FLUSH, ONE-VENUE, ABSORPTION, VOLUME SPIKE (one row per coin and family).
- **Level map** (`zones.py`, full map cached per card coin by `Scanner.levels_loop`, else the quick map of the 15m candles; rebuilt on a new 15m candle / new 1h history / every 15 min): intact swing highs/lows (15m and 1h), equal highs/lows not swept (stop pools), previous day / week and current day high-low, the last completed sessions' highs / lows, volume profile (POC, VAH/VAL, HVN of 4d 5m (1h only until the 5m history loaded) and 24h 15m), **estimated** liquidation clusters (1h OI increases IN COINS split by taker share over 10/25/50/100x, removed when price crosses them: a model, not data; OI in USD read every rally as new positions), observed liquidations (`MarketData.liq_events`), persistent book walls (live), order-book liquidity bands (heatmap, live), day VWAP; plans add the leg's Fibonacci levels, VWAP anchored at the leg start and a range's far side. Levels merge into zones by their body-to-wick spans (gap = the kind's p50 pierce, `zones.merge`; 0.3 ATR only without the pierce model); strength = sum of `CONFIG.zones.weights` (confluence; `liq_est` 0.5 until the forward test proves it).
- **Shared lifecycle and geometry** (`signal_book.py`, `strategies/geometry.py`): the leg (`levels.find_impulse`): its end = furthest point of the move on the last 12h of 15m candles, its start searched back over 15m and then 1h history until price was last beyond the end; timeframe by duration (≤12h 15m, ≤48h 1h, else 4h), checked in its own ATR (≥3 ATR, ≥1.5%); waiting TTLs of leg strategies scale ×2 / ×4. A plan's zone is where the trigger is looked for; a plan with entry `confirm` is entered at once at the confirmation when R:R to TP1 ≥ `min_rr_tp1` (vetoed `low_rr` otherwise, the card then waits in its zone). INVALID beyond the plan's invalidation (fixed at the card's start when the extreme was known at the confirmation — a reversal is not re-measured from a new extreme: live, 38 of 52 "missed" reversals were failed springs whose old low became TP1 after a re-measure); MISSED when TP1 (fixed beyond the furthest price reached since the anchor) is reached before an entry. Targets by intent (`select_targets`): TP1 / TP2 = the nearest of the primary or strong (≥ 2.5) zones and the anchor's own objectives (Fibonacci / measured moves), ≥ 1 ATR apart — by distance: with the objectives only filling empty slots a breakout got a week-old 1h low 35% away as TP1 (R:R 19.8); TP3 prefers the intent's primary kind; 1-ATR steps (`ATR step`) fill what is left. R:R is net of the execution cost (`geometry.cost_of`: the round-trip taker fee + the slippage of the market entry and of the stop exit, `levels.slippage_bps` each; `entry_levels`, `cap_for_rr`). **Stop = structure + volatility buffer** (eng-6): beyond the farthest of the strategy's structural reference (continuations: the edge of the support zone the entry comes from when it is a price-action zone — `zones.STRUCTURE_KINDS`: swings, equal highs / lows, previous day / week / sessions, range edges, round numbers, book bands; VWAP / profile / Fibonacci have no 'broken here' edge; reversals / sweeps / absorption: the anchor's extreme) and the deepest wick that tested it since price came into the zone (the trigger's extreme), pushed beyond a stop pool just behind it, then the measured pierce of the level's kind beyond (`pierce.py`, eng-11+; `stop_buffer_atr` only without the model) (0.1 sat where stops cluster — Osler — and inside the 0.1-1.0 ATR pierce the bot itself calls a sweep; history: 47% of 15m-swing stops at 0.1 ATR were followed by the +2 ATR move), never closer than `min_stop_atr` × max(ATR14, ATR of the last hour) (live, stops < 1 ATR were hit on 8 of 10 entries, and ATR14 lagged a waking market by 26%); `sl_src` says which (`beyond the zone (...)`, `beyond the test wick`, `beyond <pool>`). Each target / stop / zone carries its source label (journaled). Entry trigger = structure shift on FINAL candles only (`_minute_candles` returns 1m klines up to `minute_closed_until`) on the plan's trigger timeframe with agreeing taker flow of the candles AFTER the extreme (the selling into a low is what was absorbed there); a break that closed more than one trigger candle ago is skipped. A spring needs its "test" (pullback 1m futures volume ≤ 0.6 × the spring candle's FUTURES minute, `fut_candle_minute_usd`: the scored row is the spot candle for coins with a spot pair); every entry carries its **confirmations** (`strategies/confirm.py`, journaled as `confirms` / `conf_n`, shown on the cards): `flow` (futures taker delta since the extreme), `spot` (spot taker delta: real buying, not only leverage), `oi` (OI over the last hour: rising for trend / momentum / breakout — new positions behind the move; falling for sweep / exhaustion — stops and liquidations flushed), `orderflow` (stacked footprint imbalance, absorption, or for reversals a CVD divergence at the extreme); `n/a` where a reading cannot exist (no spot pair; OI for Wyckoff / absorption), None only on a REST failure (logged, never a veto). Required: by rule `breakout:oi` (`CONFIG.orderflow.required_confirmations`, as D / F / directional impulses already need OI), plus any the journal promotes (`journal.refresh_confirm_stats`, hourly: a strategy's entries without it have ≥ 30 15m-clusters and a 90% interval of the 4h Edge below 0); a negative required one vetoes the entry `no_<name>` (journaled, the card keeps waiting). The order-flow check alone as a fixed veto rejected 37 of 52 triggers live and 9 of 11 cards then reached TP1 without an entry, so it is required only once proven. A setup without an anchor is not a card (vetoed `no_leg`), nor one whose anchor already had a finished card (`same_leg`); a strategy's context policy vetoes with its reason (journaled); a new card closes the open card of the opposite direction when its structure timeframe is the same or higher (`TF_RANK`); every setup carries its market crowd (coins with a same-direction setup within 5 min, `CONFIG.market`) and its context (`mkt_1h` / `mkt_4h` universe median, `btc_1h`, the coin's 1h `coin_trend`, `vol_ratio` = last hour's ATR / ATR14) for the journal, stats and P(edge) — no limit on the number of cards. Lifecycle BIAS → WATCH → ZONE → ENTRY → TP1/2/3 / SL / INVALID / MISSED / EXPIRED / CLOSED; one open card per coin and direction.

### Machine learning (`ml.py`: scikit-learn, river)
The market regime changes, so nothing is fitted once on the past: models start from a pretrained state and keep learning live.
- **Pretraining** (`pretrain.py` + `history.py`, run before the bot; result `pretrained.pkl`, downloads cached in `history_cache/`): the archive's USDT perpetuals with a spot pair on the days they passed $3M average daily volume (judged from the 30 days before, delisted coins included), 6 months of the Binance public archive (1m klines futures + spot, 5-minute `metrics` = OI and long-short ratios, funding). Per coin (worker processes) the live code produces the journal rows the bot would have written: 15m candles from 1m, `compute_indicators_batch` + `PhaseScorer.calculate_scores` (OI attached as live, funding from its history per candle), `calculate_tier0_metrics` at each close and on every minute that could qualify (rule-based Tier-0 anomalies / impulses), `build_context` on every closed candle (sweeps / breakouts), `classify`, the journal cooldown, `SignalJournal._base_row`; the main process adds the market context (median moves, BTC, regimes, market crowd) and the label (4h return vs the median of every coin), and trains P(edge) in time order. Not in the archive, learned live only: liquidations, books, other venues, Hyperliquid, Coinbase, whale sweeps, the IsolationForest verdict. The journal starts P(edge) from it (`SuccessModel.load_pretrained`; an error drift returns to the pretrained model, not to an empty one); the scanner puts the pretrained regime candles under the live ones (`regime_history` = 20000 candles). **Automatic**: `Scanner.pretrain_loop` re-runs `pretrain.py` in a background process (below-normal priority, 1 worker, 300 KB/s; `pretrain.lock` holds its PID, one run at a time, it survives bot restarts) when `pretrained.pkl` is missing, older than 7 days or of another `logic_version`, and hot-reloads the result (P(edge) restarts from it and replays the live journal, the regime history gets the new months). Old cache files beyond the window are pruned. `pretrain_rows.parquet` keeps every labelled row with its features and the online model's prediction before learning it: `ml_eval.py` evaluates P(edge) on it (prequential; purged walk-forward base rate vs logistic vs LightGBM with uniqueness weights; Edge of the top-ranked rows).
- **Anomalies** (`AnomalyModel`, IsolationForest, fitted and scored in a separate worker PROCESS: in a thread scikit-learn held the GIL and stalled the event loop for 1-2s at every burst): each coin's Tier-0 vector (log RVOL, |price z|, |OI z|, whale sweeps, liquidations / average minute, algo cluster, one-venue share, perp and spot flow / average minute) is sampled every 30s; the forest is refitted hourly on the last 3h of the whole universe (first fit after ~15 min, 3000 samples) and a coin is anomalous when it is among the 0.1% most unusual (`anomaly_quantile`). Once fitted it decides (`ml_ready`), the seven rules only label the event (`t0_*` columns, `rule_anomaly`; ML-only events are `UNUSUAL`). Measured live: ~540 rule onsets/h -> ~36/h, each a multi-factor event. `ml_state.pkl` keeps the last model (any age: it scores until the refit) and the timestamped training window (samples inside `anomaly_window_sec` survive a restart; an old model is refitted as soon as the window holds `anomaly_min_samples`, right after a short restart); **delete it whenever a feature's meaning changes** (a model fitted on broken OI flags every OI move).
- **Regimes** (`RegimeModel`, GaussianMixture, k=4): market-wide features per closed 15m candle (BTC 1h move / volatility, breadth, median funding / OI change / RVOL; NaN / null rows dropped), refitted once a day (`regime_refit_sec`; between refits the model only labels new candles: a refit every 15 min changed what a name meant - 8 names for 4 clusters in the journal), history pretrained months + live, pretraining labels each week with a model fitted on the past only (`labels_walk_forward`); clusters are named from their centers (`up·volatile`, `flat·quiet`, ...). Rows carry `regime`; `journal.REGIME_STATS` (hourly) mutes a setup in a regime once its Edge there is proven negative over >= 30 independent 4h blocks with the false discovery rate controlled over the whole setup x regime grid (`journal.proven_negative`: block-bootstrap p-values + Benjamini-Hochberg, `rule_fdr` 0.10; the same rule promotes confirmations) (`vetoed='regime'`).
- **P(edge)** (`SuccessModel`, river logistic regression + ADWIN; whale / price z / OI z / book imbalance also enter multiplied by the signal's direction, a linear model cannot learn the sign interaction itself): learns online from every directional journal row when its 4h label arrives (label = beat the universe median), replays the journal at start, resets on error drift. Shadow only: stored as `p_edge`, shown on cards after 300 rows; stats.py splits Edge by it.

### Per-strategy coin pools (`pools.py`, `sectors.py`, `CONFIG.pools`)
- Each strategy trades only its own pool (<= `size` coins by 24h volume), rebuilt hourly (`Scanner.pools_loop`): the rule per strategy (coin class by 24h volume rank: major / large <= 30 / mid <= 80 / small; sectors to exclude, from CoinGecko categories cached daily in models/sectors.json; minimum 1h volatility) minus the coins where the strategy's journaled entries of the last 90 days average <= -0.3R over >= 8 entries. Outside the pool a setup is journaled with vetoed='not_in_pool'. Measured on the archive before building it: walk-forward monthly (the 15 best / worst coins of the previous 6 months per strategy), the WORST coins stayed the worst (level triggers -0.39R / -0.29R vs -0.10R / -0.03R for the rest) while the best were only slightly better than the rest and still negative; no sector has triggers beating geometry (meme the worst in 2025-26, -0.16R). So the automatic part is the exclusion; the class / sector / volatility rules default to 'all' until a strategy's split proves otherwise.

### Journal and stats
- `journal.py`: SQLite in WAL mode, all writes through `asyncio.to_thread` (the a* methods) under a lock. One row per (symbol, event family) per 30 min (stronger readings still logged); entries are `ENTRY <setup>` rows with levels; every row stores `logic_version` (bump it when signal logic changes; now `eng-29` (eng-29: see "Methods aligned with their sources, classic methods added"; eng-21: R:R >= 2 for every entry incl. the ported systems, at least one positive confirmation; eng-20 forced liquidations are no whales; eng-19 extdata.py, Bybit spot; eng-18 cold start seeded; eng-17: OI accumulation only when takers bought; measured pierce beyond the ported systems' own stop references; see "Live-first rework eng-8 .. eng-16"); eng-10 all strategies make cards again (Live verdict); eng-9 BULL E disabled; eng-8 honest stop exits (a candle that opens beyond the stop fills at its open), slippage by liquidity, `oi_accum` in coins; eng-7 the audit fixes below; eng-6 introduced the structural stop), the veto reason and order-flow / multi-venue features. The `universe` table stores the mark price of every USDT perpetual (not only the streamed universe; stocks / pre-IPO excluded) every 15 min: the market baseline. The `liquidations` table keeps every live liquidation of every venue (flushed each scan) and `liq_levels` snapshots the liquidation levels of each card coin's map (`liq_est` estimates, `liq_hl` real Hyperliquid account prices) whenever the full map is rebuilt: a forward test of the liquidation model (the map drops a cluster once price crosses it, so comparing the live map with past liquidations is biased by construction: measured 2% of liquidated USD in bands covering 6% of the range, meaningless). `evaluate_loop` fills 15m/1h/4h returns and 4h MFE/MAE from 1m klines (one request per row covers all due horizons; a horizon is due only once the window's last 1m candle has closed, `horizon_due_ms`; SL is a touch of a candle's high / low, a TP counts once price traded `target_through_bps` (2) through it); entries are replayed by `levels.simulate` over the trade's whole life (the 8h horizon = `trade_ttl_sec`; a 4h replay marked longer trades to their 4h close) with a **manual fill** (next minute's open + slippage) and stop exits at the stop or, on a gap, at the candle's open, plus slippage (`levels.slippage_bps`: 5 bps at >= $500M 24h volume, x sqrt($500M / volume) below, capped at 25 bps; the planner's `geometry.cost_of` and the archive research still use the flat 5 bps), `SKIPPED` if the fill is already beyond the stop. Every finished card is a `kind='card'` row `<STATUS> <setup>` with its `reason` (e.g. which vetoes skipped its triggers), so the outcome loop shows what price did after a MISSED / EXPIRED card; entries store `tp*_src` / `sl_src` / `zone_src`, every row its `strategy`, entry / card rows the plan's `anchor` (JSON), directional rows the context (`mkt_1h`, `mkt_4h`, `btc_1h`, `coin_trend`, `vol_ratio`, `market_crowd`, the coin's 24h futures volume `volume_24h`); the replay also stores `r_be` (the same trade with the stop at breakeven once TP1 traded, exited at TP2 — compared, not live).
- `stats.py`: Edge = return in the signal's direction minus the median return of the **whole universe** over the same window (snapshots; falls back to the median of logged coins), with 90% **cluster** bootstrap intervals (signals of one direction whose 4h outcome windows overlap ride one market move: 4h blocks are resampled together, `stats.cluster_of`; the journal's automatic rules use the same blocks); win rates and R net of the 0.1% round-trip fee; an Edge-by-feature table (strategy, coin 24h volume, market 1h vs the signal, the coin's 1h trend vs the signal, volatility state, vetoed vs passed, perp-led, liquidations, multi-venue, quarter-hour, order-flow confirmation); TP1 hit rate by level source; finished cards by status with the move afterwards.

### Dashboard / notifications
- `webui.py` + `web/` (plain HTML/JS, TradingView lightweight-charts from jsdelivr): aiohttp server inside the bot on 127.0.0.1:8765, opened in the browser at start. `/ws` pushes the full state after every scan (`build_state`); `/api/coin` = 1h (4 days) / 15m / 5m candles + level map (the card's plan when there is one) + 48h of the coin's journal, answered from memory at once (the 1h / 5m history loads in the background, `load_htf_background`, and the page asks again; coins outside the universe get REST candles at priority 0); a card opens on the chart of its structure timeframe (1h for 1h / 4h legs, 5m for 5m anchors); the waiting tab shows each card's anchor (a leg, a level, a range) and its entry timeframe; the order-book heatmap is drawn behind the candles on a canvas (toggle «стакан»); `/api/history`, `/api/anomaly_stats` read the journal through their own read-only SQLite connection (edge = against the universe median); `/api/stats` renders `stats.report` to HTML. Every setup shows its strategy (hover: its mechanics). Tabs: in trade, waiting (zone / targets with sources, vetoed triggers and why), finished (card outcomes with reason and what price did afterwards; entries incl. vetoed), anomalies (live, per-label follow-through, history), forming / vetoed, stats, health. Click a row for the coin panel (chart with zones, card levels and journal markers).
- `notifier.py`: optional (off by default) Windows balloon / Telegram on ZONE, ENTRY, TP, SL; fire-and-forget tasks.

### Audit eng-4 (2026-09-27, web-checked against research; see git history)
- Venue OI is aggregated in COINS (USD / the venue's mark): in USD, "OI rising" on a rally held without a single new position, so the breakout's OI confirmation read the price itself. Unknown aggregates are None (not 0) until a venue has the window's history; Binance's seeded hour is in the aggregate from the start.
- P(edge) features: every directional reading enters × the signal's direction (funding of all venues, long/short ratios Binance / Bybit / OKX (log), Hyperliquid net, Coinbase premium, which side was liquidated) plus hour-of-day (sin / cos) and weekend; the level map's `liq_hit` (liquidations that already happened) is a level, not a pool.
- Journal eng-4 columns: `ret_8h`, `agg_funding_8h`, `ls_bybit`, `ls_okx`, `hour_utc`, `weekend`, `liq_on_wick` (swept-side liquidations of all venues on the sweep candle), `oi_change_sweep`; stats splits by session, weekend, pullback zone (map level vs Fibonacci only), sweep-wick liquidations, funding vs the signal. The market baseline is snapshotted every 5 min.
- Known, journaled but not acted on until the data proves them (audit): trend filter for continuations (`coin 1h trend vs the signal` split), the perp-led veto (perps normally lead spot in price discovery: it stays, under test), per-coin OI z-scores for D / F / impulses, time-of-day normalization of Tier-0 RVOL / z, multi-venue delta for absorption, reaction-time decay of entries.

### Classic alignment eng-5 (2026-09-27: web research, the tool combines classic methods, it does not invent new ones)
- **Elder's tide** for the pullback continuations (trend, momentum; `LegContinuation.context_veto`, `against_tide`): not against the coin's 1h trend (EMA20 slope) and BTC not >= 0.5% against over the last hour. Breakouts take no trend filter (Turtle / Bollinger method I).
- **Pullback zones** (superseded in eng-29 by ICT's OTE 0.62-0.79 with displacement, invalid beyond the leg's start) 0.382-0.618 of the leg (deeper = trend failure); the zone is a real map level inside the band, else the EMA20 of the leg's timeframe (Raschke's Holy Grail), else no card (`no_level`, kept per card in `SignalBook._skip_reason`). Fibonacci-only zones are gone (no edge in the ratios themselves).
- **Perp-led veto only when leverage is crowded** (`journal.crowded`: funding >= +0.03% / 8h for longs, <= -0.01% for shorts, or a Coinbase discount >= 0.05% for longs, with OI +0.5% / 1h): perps lead spot in price discovery, crowded leverage is the documented risk (BIS WP 1087).
- **Anomalies are decided by the classic rules** (`CONFIG.ml.anomaly_decides = False`); the IsolationForest is journaled in shadow (`ml_score`, `ml_anomaly`).
- **Relative volume / volatility at time**: `indicators.seasonal_factors` (4 weeks of 1h candles, refreshed daily by `DataFetcher._seasonal_loop`; the same profile per day in pretraining) scales Tier-0's average minute and return std to the hour of day and weekend (`seasonal_scale`); measured on SOL: 13-16 UTC ~1.8-1.9x the mean hour, weekends ~0.72x.
- **OI in the coin's own z-scores**: directional impulses need OI z >= 2 (floor 0.15%), phases D / F OI over 1h >= 1.5 OI std x sqrt(4) (floor 0.3%); fixed thresholds only while the coin's OI volatility is unknown.
- **ADX14** (Wilder) journaled with a stats split (>= 30 trending).

### Audit eng-7 (2026-09-28, cloud session: code audit + fixes verified offline; see HANDOFF.md for the device steps)
- **Pretraining look-ahead removed**: `pretrain.tier0_at` used the archive minute that opened at the scan time with its WHOLE volume / taker flow (live sees seconds of it): on SOL Jul-Sep 2026 the median `rvol_1m` of rows at a 15m close was 1.69 with the leak, 0.67 without. Only minutes closed by the scan are used now; anomaly probes run at the minute's close. The row cache carries the logic version; a `pretrained.pkl` of another `logic_version` is not used for P(edge) (the regime history stays) and `Scanner._pretrain_due` rebuilds it.
- `zones.estimated_liquidations` takes OI in coins (`sumOpenInterest`); sizes are USD at the last close.
- The spring test compares futures with futures (`fut_candle_minute_usd`, scorer `FUTURES_COLUMNS`); BULL B's "range high" comes from the futures frame (the spot row's `prior_range_high` is 1000x off for 1000PEPE-type contracts).
- Equal highs / lows are "swept" by any candle after the group's latest swing (`RawLevel.ts`), not only the last 12; a failing level map is logged by the worker instead of dropped silently.
- Bollinger bands use the population standard deviation (ddof=0, Bollinger's definition). ATR stays a simple 14-candle mean of true ranges (not Wilder's RMA): the thresholds were measured with it.
- Replay: a target fills once traded `CONFIG.levels.target_through_bps` through it (a touch overstated limit fills).
- Cards show sizing (`webui.sizing_view`, `CONFIG.risk`): stop %, the highest isolated leverage whose liquidation stays 1.5x the stop distance away, the funding the position pays / receives per 8h, and with `[risk] account_usd` set the notional / margin for `risk_pct` of the account. Information, never an order.
- **Pretraining picks its coins from the past** (`pretrain.select_coins`): every USDT perpetual in the archive's S3 listing (`history.Archive.list_symbols`, delisted ones included) with a Binance spot pair (the live universe requires one; tokenized stocks / pre-IPO have none), and a coin's rows count only on days it passed the volume floor judged from the 30 days BEFORE (`eligible_days`, archive daily candles) and was listed >= 9 days. Before, today's exchange list and 24h volume picked the coins (survivorship, look-ahead). Weekly closes for `trend_w` come from the archive's daily candles (the REST API is geo-blocked in the cloud). The label's universe baseline is a 5m grid (`_forward_median`): minute rows were up to 15 min off.
- `stats.py`: `Edge β 4h` (the baseline x the coin's beta from 7 days of hourly snapshot returns before the signal's day, Blume-adjusted, `BetaEstimator`) and Benjamini-Hochberg q-values (`bootstrap_p`, `bh_q`) in the setup table and the feature splits.
- Replay nets funding out of each exit's R (`levels.funding_r`: the rate at the signal x the 8h settlements held through; 4h-settling coins pay about twice that).
- **Edge is measured against the universe MEAN, not the median** (`journal.universe_return`, `stats.UniverseBaseline`, the dashboard, `research_edges.py`, `ml_eval.py`): on 6 months of 363 coins the average coin beat the median by +0.108% per 4h with NO signal (right-skewed returns; the same in every volatility tercile), so Edge against the median gave every long ~+0.11% and every short ~-0.11% - including the journal's automatic regime mutes / confirmation promotions, which therefore leaned to muting shorts. The P(edge) label stays 'beat the median' (balanced 50/50). Against the mean, no archive-testable setup has a significant 4h Edge (all q >= 0.17; the best, BULL F, +0.10% [+0.03..+0.17], is below the ~0.20% round-trip cost): `research/edges_6m.md`. P(edge) out of sample: AUC 0.53, log-loss skill +0.3%, the top-ranked rows do not have a larger Edge (`research/ml_eval_6m.txt`) - shadow only, as before.
- **Archive research results** (card replays, exit rules, meta-labeling, higher timeframes, positioning, EQH / EQL, channels, pumps, the scenario card's probability model): the `research-findings` skill. Bottom line: no archive-testable setup, exit rule or model has an edge net of costs; gross R of the cards is ~0. `sweep` / `breakout` and the phase / momentum setups in `disabled_setups` are off for that reason. Load the skill before proposing or judging any strategy, filter, exit rule or model.
- `scenarios.py` (scenario card on every coin panel) shows the random-walk geometric probability and the measured trigger rates, information only; `pumps.py` shows live small-cap pumps / dumps with each rule's measured verdict (details in the skill).
- **Live verdict (eng-10, 2026-09-30)**: every strategy makes cards again (the archive cannot replay the live-only confirmations, liquidations, books and other venues, and a disabled strategy never produced a card, so it was never measured live); archive losers carry `archive_negative` (the «архив −» mark). Pre-registered, not to be changed after the fact: a strategy is judged once its passed entries (`vetoed` NULL, logic_version >= eng-10) span >= 30 independent 4h clusters: KEEP if mean net R > 0 and the 90% cluster-bootstrap interval's lower bound > -0.05R; otherwise its code is DELETED (detector, strategy class, config, tests). The same for the `conf_n` split (eng-6 live, 2.5 days: 0 confirmations -0.44R on 67 entries .. 4 of 4 +0.16R on 11): a confirmation count becomes a required filter only if it passes the same rule.
- `tests/test_audit.py`: regression checks of these bugs; a freqtrade-style truncation test shows indicators and phase scores do not look ahead.
- Not changed (decisions for the owner): the "phase" letters are not Wyckoff's phases (B = a phase-C spring, E = a phase-A selling climax, F = phase-E markup; renaming changes journal keys); ATR stays a simple mean.

### Live-first rework eng-8 .. eng-16 (2026-09-30)
- **Replay honesty (eng-8)**: a stop is filled at the candle's open when it gapped through (`levels.stop_fill`); slippage grows as liquidity falls (`levels.slippage_bps`: 5 bps at >= $500M 24h volume, x sqrt($500M / volume), cap 25 bps; the planner's `geometry.cost_of` and the archive scripts keep 5 bps); `oi_accum` reads OI in coins; every entry journals the raw 1h OI change (`confirms._oi_1h`).
- **Every strategy makes cards again (eng-10)**: a disabled strategy never produced a card, so its entries, confirmations and live-only inputs were never measured. Archive losers carry `archive_negative` («архив −»); the pre-registered **Live verdict** rule (Journal and stats) keeps or deletes each strategy.
- **Stops from structure, not ATR constants (eng-11 .. eng-15)**: the ported systems' fixed % / ATR exits (Third Eye's 1% stop sat inside one 15m candle on SUI) are replaced by the map: the stop beyond the nearest structure (`geometry.structure_stop`), targets at the next levels; the fixed rule only without references. The buffer beyond a level is MEASURED (`research_overshoot.py` -> `models/overshoot.json`, `research/overshoot.md`: p80 of how far price pierces a level of that kind on that coin before a 15m close back within 1h; 80 coins x 12 months, stable across halves 82-83%; swing 15m 0.63%, 1h 0.77%, equal 0.61%, previous day 0.92%, round 1.36%; per coin 0.15-1.40%) - no minimum / maximum in ATR: a stop that does not pay is `low_rr`, and the card shows why («стоп далеко»: stop %, TP1 %, the entry's distance from the zone edge, `veto_notes`). Stops are no longer pushed beyond ESTIMATED liquidations (live eng-6: the widest stops, -0.16R, 0 of 22 stopped trades reached TP1). ICT (`strategies/ict.py`): the stop beyond the protected swing (the last pivot that broke structure); premium / discount journaled as `range_pos` (0 = the cheapest end of the 48h range for the direction) with a stats split.
- **Methods aligned with their sources (eng-16)**: Wyckoff spring / UTAD of a 1h trading range after a trend's stop (`strategies/wyckoff_range.py`, setups SPRING / UTAD; entry on the test), the 15m B / C scores off (`legacy_wyckoff_bc`), BULL E (buying the climax) journaled without a card, honest names for A / C / F / D on the dashboard; sweep entry = retrace into the post-sweep displacement FVG (`trigger='fvg'`); breakout = the Turtles' 20-day Donchian on 1h with an acceptance close (`breakout_donchian`; the 15m `breakout_at_close` stays for pretraining / research); auction POC from 15m candles; smt in ICT's kill zones 02-05 / 07-10 NY with the more correlated of BTC / ETH (`structure.pick_correlate`); supply / demand = Seiden's base (1-6 boring candles), a limit at the proximal line, first touch only (`trigger='touch'`, `single_touch`).
- **Data recorder** and **BingX demo execution** (`executor.py`, VST sandbox forced, every ENTRY card at 1% of a $10k base capped at $4k notional, stop + three reduce-only targets, results in `demo_trades.db`; the key in config.local.toml).

## Notes
- Python 3.14 in `.venv`: `asyncio.run(..., loop_factory=winloop.new_event_loop)` (event-loop policies are deprecated). `main.loop_exception_handler` turns aiohttp's orphaned DNS failures (shielded resolver tasks whose caller already timed out) into one WARNING line. `gc.freeze()` after the baselines and after every 1h-candle pass (never `gc.collect()` on the loop): full collections over millions of candle lists paused the loop 1-3s. Stalls with low CPU are usually the machine paging (6 GB, Claude + Chrome): check free RAM before blaming code. Logging is configured only in `main.py`'s `__main__`, so importing it never writes `scanner.log`.
- Logging levels: a feed that drops and reconnects at once is INFO (public gateways restart); repeated connections without data are WARNING. `watchdog.LoopWatchdog` samples the main thread's stack when the loop stalls > 1s and logs where it was (plus gc pauses): no guessing about lag. CPU work that took ~1s on the loop was removed from it: IsolationForest in a worker process, the 15m frame split per symbol once per heavy pass, card plans cached until their inputs change (only leg plans follow the live 15m candle's high / low; a phase setup's leg gate is cached per plan key), FlowStore windows summed as contiguous ring slices (fancy indexing copied ~90 MB per 1h refresh), frames cut before an incomplete candle cached (after every start all ~600 frames have one until REST replaces it), the new candles of all ~600 frames at a 15m close appended in a worker thread (`Scanner._merge_frames`, 1.6s on the loop), level maps in a worker process, each venue's 5m flow summed once per Tier-0 pass. py-spy (`--threads`) showed the stall mechanism: pure-Python worker threads take the GIL in 5ms slices, so 2-3 of them cut the loop's share and a 0.3s Tier-0 pass became 1-4s.
- Start-up keeps the coins of restored open cards in the universe (they had no data and broke the hot-symbol update); the hot set only takes coins with data.
- Robustness: backfills retry with backoff (0/5/15/45/120/300s) and re-apply stream-finalized candles; `_price_of` ignores prices older than 60s; a listing younger than 24h averages its volume over its listed minutes; the universe is re-selected hourly (`universe_loop`; coins with open cards stay until they finish); hot-symbol subscriptions (order books, Hyperliquid trades) keep a 60s minimum age and 300s hold. Ctrl+C: repeats within 3s are ignored, a later repeat force-exits after restoring the terminal.
- Tokenized stocks and pre-IPO contracts are excluded by Binance's `underlyingType` (`CONFIG.exchange.excluded_underlying_types`).

## Working with the owner
- The owner is a manual crypto trader; talk to them in Russian. Challenge their ideas with data and web sources instead of agreeing; they ask for that explicitly.
- Implement all planned changes across every related module first, then lint + `pytest` once, then one graceful bot restart; never restart mid-change (it mixes code versions in the live evaluation window).
- Verify with live runs (`scanner.log` Health line, the journal, the dashboard), not by generating tests; add a test only for a concrete bug a live run exposed, and ask first.
- Pretraining on the Binance public archive (`pretrain.py`) is wanted; judge models out of sample (purged walk-forward, `ml_eval.py`).
- Hypotheses about levels / indicators are tested against placebo controls matched on volatility and trend before they touch signal logic (the weekly-EMA study, 2026-09-27: no level of its own, the trend it sits in is what matters).
- The bot runs on the owner's Windows machine (winloop, local `signals.db`, `history_cache/`, ~6 GB RAM): a cloud session cannot run it or read its journal. Restart there: start `.venv\Scripts\python.exe main.py` from PowerShell (own console); stop gracefully by attaching to the child interpreter's console and sending Ctrl+C (FreeConsole → AttachConsole(pid) → SetConsoleCtrlHandler(None, True) → GenerateConsoleCtrlEvent(0, 0)); check exactly one instance listens on :8765.

### Methods aligned with their sources, classic methods added (eng-29, 2026-10-01)
- Continuations (trend / momentum) by ICT's optimal trade entry: the leg must show displacement (a fair value gap,
  `strategies.leg.displacement`, else `no_displacement`), the zone is 0.62-0.79 of the leg (`continuation_zone`), invalid
  beyond the leg's start (`continuation_invalid` 1.0). Tests pin the old 0.382-0.618 / 0.786 (conftest).
- Confirmations add `vsa` (`strategies/vsa.py`, Tom Williams: no supply / stopping volume / reverse upthrust for longs,
  no demand / buying climax / upthrust for shorts, on 5m bars since the extreme) and the order-flow kind
  `finished_auction` (`flow.Footprint.finished_auction`: no taker sells at the footprint's low / buys at its high).
- Volume profile adds LVN levels (`lvn`, weight 0.5: valleys <= `lvn_ratio` x the nodes on both sides). The map adds ICT zones (`zones.imbalances`): open fair value gaps (`fvg`, gap >= 0.1 of the displacement candle, the unfilled part) and unmitigated order blocks (`ob`, structural: the last opposite candle before a break with an FVG) of 15m (1 day) and 1h (8 days).
- Targets: empty TP slots take the nearest map zone of ANY strength before an ATR step (`geometry.map_fill`); the ported systems take TP2 / TP3 from the map too (were always TP1 + 1 / 2 ATR: TP2 / TP3 were ATR steps on 18 / 21 of 35 entries).
- New classic strategies (`strategies/classic.py`, cards `classic_strategies.py`, entry at the signal's close):
  `value_area` VA80 LONG / SHORT (Dalton's 80% rule on the UTC day's value area, 30m periods), `orb` ORB UP / DOWN
  (Crabel's 30m range after the US equity open, first 15m close beyond it within 2.5h, stop at the range's other side,
  NR4 / NR7 noted), `connors` RSI2 LONG / SHORT (DAILY RSI(2) < 10 above the 200-day SMA / > 90 below, target the 5-day SMA; daily candles by `fetcher._daily_candles_loop`, checked loop-side `Scanner._connors_daily`).
- `macro_calendar.py`: entries 30 min before .. 60 min after CPI / FOMC are vetoed `macro_event` (dates for 2026 only).
- Pinned coins (`CONFIG.exchange.pinned_bases`: BTC ETH XAU XRP SOL SUI BNB DOGE HYPE): always in the universe and in
  every strategy's pool, bypassing the volume / spot / venue / commodity exclusions; the rest of each pool is picked by
  the method's order (`PoolsConfig.rules`: volume / volatility / alts) - a hypothesis, the journal exclusion still applies.

### Measurement tools (eng-29)
- `stats.py` prints `vetoes_table` (every veto reason's rejected entries replayed next to the passed ones: a filter
  stays only if what it rejects does worse) and `demo_table` (BingX demo R next to the journal R of the same card;
  `EARLY_CLOSE` = REZ / GRT / NMR closed 2026-10-01 while their cards were open, not results). Freeze the signal logic
  for 7 days after a version bump before judging anything (eng-26 .. eng-29 changed within one day).
- Robustness (eng-29): a dead worker process (killed when RAM runs out) no longer breaks its pool for good - the maps
  and anomaly pools are recreated (`_broken`), the failing pass is skipped (live 2026-09-30 23:28: Tier-0 raised
  BrokenProcessPool every 2s until a restart). The demo trades one card per coin (BingX one-way mode nets orders of a
  coin into one position): a second card on a held coin is recorded `OVERLAP`. Lint before a restart:
  `ruff check --select F` and `pylint --disable=all --enable=E0601,E0602,E0606` (both would have caught this
  session's two outages).

### The ported systems answer to classic methodology (eng-30, the owner's rule 2026-10-01)
crypto_maniac's repositories are SAMPLES: where a sample contradicts classic technical analysis or the method's own
source, the source wins. Changed: `csi` (a close beyond BB(40, 1.5) read as a reversal contradicts Bollinger; the
"candle sentiment index" is his invention) -> `bollinger` BB W-BOTTOM / BB M-TOP (Bollinger's method III: the first
test closes outside the band, the retest holds inside, entry on the close beyond the middle peak, stop beyond the
retest, target the opposite band); `thirdeye` on the classic parameters (Lambert's CCI(20) +-100, Hosoda's Ichimoku
9 / 26 / 52 displaced 26 with the conversion over the base line and the lagging span, Wilder's ADX(14) >= 20; his fitted
RSI / NATR / BB-width bands dropped); `trendline` targets from the map (Edwards & Magee), not the line's first anchor.
Kept as consistent with their sources: supply / demand (Seiden), auction (Market Profile POC), SMT (ICT), fib 0.5
(Fibonacci retracement), Bomberman (Appel's MACD signal cross with a trend filter; the QML is a retail SMC condition),
OI accumulation (derivatives, not chart TA).
- eng-31 (our own strategies against their sources): phases D / F need the break out of a squeeze
  (`squeezed_recently`: Bollinger's method I - a tag of a wide band is no signal); `exhaustion` enters on Wyckoff's
  secondary test (the pullback's minute volume <= `spring_test_volume_ratio` x the climax's, else `no_spring_test`) - the
  climax itself is not bought, as BULL E; BULL A (buying a squeeze before it breaks: against Bollinger, no Wyckoff
  phase) is journaled without a card (`disabled_setups`). Checked and kept: momentum / trend pullbacks (ICT OTE),
  SPRING / UTAD (Pruden / Weis), sweep (ICT), absorption (order flow), VA80 (Dalton), ORB (Crabel), RSI(2) (Connors).
  Open, the owner's decision: `breakout` is the Turtles' 20-day channel but not their trade (they enter on the touch,
  stop 2N = 2 x the 20-day ATR, exit on the 10-day opposite breakout; ours enters on an accepted 1h close with a
  structure stop and map targets).
- eng-32: `breakout` = the Turtles' systems in full (`strategies/turtle.py`, the owner's decision): daily candles; N = the
  20-day exponential true range; System 1 on the touch of the 20-day high / low unless the last S1 breakout won, System 2
  (55 days) as its fail-safe; entered at once (`Scanner._turtle_breakout`, once per coin / direction / day); stop 2N; no
  profit target (`exit['tp'] = ['trail']`: 100 / 200 / 300 R placeholders) - the card closes on the 10-day (S1) / 20-day
  (S2) opposite channel (`SignalBook._manage_trade`, `trail_days`, `daily_of`); no volume / flow / OI / spot / perp-led /
  confirmation filters (`orderflow.confirm_exempt`); trade lifetime 90 days; the demo places no take-profits. Not done:
  pyramiding (+1 unit per 1/2 N up to 4) and unit sizing (1% of equity per N). The journal's 8h replay marks these
  trades to the horizon; the card row and the demo hold the real result.
- eng-34: Turtle pyramiding and units (+1 unit every 1/2 N up to 4 per coin, at most 12 units per direction overall -
  `unit_limit`; all units' stop moved to 2N from the newest; `TrackedSignal.units`, R = the sum of the units in
  first-unit risk; the demo sizes a unit at 1% of the account per N and adds / re-stops on the card's ADD event).
  ICT zones on every timeframe the bot holds - 15m, 1h, 4h (from 1h) and the daily (`MarketData.d1`, sent to the maps
  worker): open FVGs, unmitigated order blocks and breakers (failed OBs), kinds `fvg_<tf>` / `ob_<tf>` / `breaker_<tf>`
  weighted by timeframe (15m FVG 0.5 .. daily OB 3.0; order blocks / breakers are structure for stops). ICT's daily
  bias (`daily_bias`: yesterday's close beyond the day before's high / low) vetoes sweeps and SMT against it
  (`against_bias`; with no bias the 1h trend as before), journaled. Supply / demand zones on 1h with the 15m touch
  (Seiden: zones on the higher timeframe). The coin panel's heatmap is backed by the recorder's depth files (4 days,
  10-minute steps, `recorder.heat_history`): it showed only the ~4h held in memory.

### Ten methodologies (eng-35, the owner's decision 2026-10-01)
One methodology = one strategy name (`strategies.SETUPS` -> name; `strategy_of` -> the playbook's object, several
playbooks may share a name): `continuation` (BULL F / BEAR D + IMPULSE UP / DOWN: one ICT-OTE pullback trade, two
impulse detectors), `wyckoff` (the climax's secondary test FLUSH / SQUEEZE REVERSAL + SPRING / UTAD), `sweep` (ICT;
SMT divergence `smt` and the kill zone `killzone` are its confirmations, `structure.smt_divergence`), `breakout`
(Turtles), `supply_demand` (Seiden), `market_profile` (AUCTION + VA80), `trendline`, `bollinger`, `orb`, `connors`.
Deleted: the invented systems (Third Eye, Bomberman, OI accumulation, the 15m phase reversal BULL A / B / E, BEAR C -
the phases are still scored and journaled as structured rows, no cards), `fib05` (a duplicate of the continuation),
the standalone `smt` and `absorption` setups (now confirmations). Higher timeframes: own 4h candles (200, every 4h,
`MarketData.h4`) and the weekly ones (`MarketData.w1`) go to the maps worker - FVG / OB / breaker zones on 4h, daily
and weekly (`fvg_1w` 3.5, `ob_1w` 4.0), the day / week open (`open`); ICT's top-down bias: `weekly_bias` first, else
`daily_bias`, vetoes sweeps against it (`against_bias`). `research_maniac.py` still calls the deleted
`oi_accumulation` (archive tool, not the bot).
- eng-36: ICT additions - the sweep's FVG entry rests at the gap's consequent encroachment (CE, 50%; `ict.fvg_trigger`);
  balanced price ranges (`zones.balanced_ranges`, `bpr_1h` 1.5 / `bpr_4h` 2.5: overlapping bearish + bullish FVGs within
  20 candles, kept until closed through); the Silver Bullet (`strategies/silver_bullet.py`, setups SILVER BULLET LONG /
  SHORT of the `sweep` strategy: 03-04, 10-11, 14-15 New York, the raid of the previous hour's high / low, a 5m FVG
  with displacement, a limit at its CE, stop beyond the raid, target the hour's opposite side; loop-side
  `Scanner._silver_bullet`). Cards carry their `logic_version`; at a start every card of an older logic is closed
  (entered: CLOSED at market, journaled; waiting: EXPIRED) - an eng-7 card kept trading beside eng-35 ones.
- eng-37 (timeframes by their sources, before any data collection - the owner's rule): Elder's tide ~5x the leg
  (`continuation`: 15m leg -> the 1h trend, 1h -> 4h `trend_4h`, 4h -> daily `trend_1d`, else `against_tide`); ICT's
  three layers for `sweep` (the raid must run into a 1h+ PD array - OB / FVG / BPR / breaker, else `no_htf_poi`; longs
  only in the discount half of the 48h dealing range, shorts in the premium, else `premium` / `discount`; TP by the
  `draw_liquidity` intent: previous day / week / sessions, equal highs / lows, daily swings); Seiden: supply / demand
  zones of 4h candles with the 1h touch and his curve (`curve_pos` in the 20-day daily range: demand only in the lower
  half, else `curve`); Wyckoff's spring / UTAD vetoed `against_htf` when the daily trend and the weekly bias both oppose
  it; trendlines of 1h candles with the stop on 15m pivots (Edwards & Magee); a `htf_zone` confirmation on every entry
  (the price inside a 4h / daily / weekly zone: ICT / Seiden's nesting). Card rows journal `card_r` (the lifecycle's own
  exit, units) - `stats.card_results_table`; `research_turtle.py` replays the Turtles on daily archive candles.
  Lighter data for the laptop: universe 70 (`max_pairs`), 25 order books, Hyperliquid trades for 70 coins.
- eng-39: `pump` strategy (`strategies/pump.py`, the owner's): PUMP START long (+15m >= max(3%, 4 x the coin's 15m
  volatility), RVOL >= 5, OI rising, spot buying, a fresh 24h high; market entry, stop below the ignition, targets map
  / measured moves) and PUMP TOP short (a buying climax 15m candle - upper wick >= half, volume >= 2x - after >= 10% in
  4h, the 5m shift down, stop above the high, targets the 0.382 / 0.5 / 0.618 retracements); averaging 1:1 (`add_half`:
  one more unit at half the way to the stop, the stop kept, R summed over the units; the demo adds and re-places the
  stop and take-profits). Loop-side `Scanner._pumps`.
- eng-40: R:R from each method's source (`Strategy.min_rr` -> `plan['min_rr']`, `geometry._min_rr`; None = the global
  `min_rr_tp1` 2): supply / demand 3 (Seiden), cup with handle 1, Bollinger W/M,
  Market Profile, ORB, Silver Bullet 1 (their targets are references, no ratio rule), Connors 0 (no stop / ratio rule).
  (cup with handle: min R:R 1, stop the nearer of the handle low and 8% below the entry - O'Neil) `cup_handle` (`strategies/cup_handle.py`, CUP HANDLE long on 1h / 4h: O'Neil's rules - prior +30%, U cup 12-50%
  deep with rims within 5%, a handle in the upper half <= 12% on lower volume, the close above the pivot on >= 1.4x
  volume; stop below the handle, target the cup's depth from the pivot - Bulkowski).
- eng-41: one R:R path for every plan (`geometry.finish_levels`): level targets sit in front of their level by the
  kind's p50 pierce; R:R is judged on level targets only (`is_synthetic`: ATR steps, 'x R', placeholders; ATR steps
  count only where the map holds nothing beyond the entry - price discovery); a third with no level beyond exits at
  the last level (the demo places no order in empty space); the deciding R:R is the BLENDED one of the three thirds;
  risk >= 5x the execution cost; with >= 30 replayed decisions of a strategy in 30 days (`journal.refresh_hit_rates` ->
  `geometry.HIT_RATE`) the check is the expectancy p x R:R1 - (1 - p) > 0 instead of the minimum R:R. Journal
  `rr_blend` / `rr_reason`. The pump's averaging plan risks 1.5 units: the demo sizes each unit to 1/1.5 of the risk.
  `cap_for_rr` takes the method's minimum. Stop buffers of the sweep invalidation / the cascade estimate and the
  confirm-at-close zone are the measured pierce (were 0.3 / 0.25 ATR). The auction lost its '2.5 R' fallback target.
  Kept as ATR (scale, not price levels): the 1-ATR spacing between targets, detectors' significance thresholds
  (Seiden's 2-ATR departure, trendline tolerances, the auction's bins), the Turtles' N, the fallbacks used only
  without the pierce model.
- eng-42: continuation targets are the TREND-BASED Fibonacci extension (Carney / Pesavento's ABC, TradingView's
  Trend-Based Fib Extension, the owner's screenshots): the impulse A -> B projected from the pullback's extreme C at
  1.0 / 1.2 / 1.272 / 1.618 (was the 2-point extension from A); labelled 'ext k', '+ <zone>' when a 4h / daily /
  weekly zone sits within the pierce of it. The card view carries the grid (`webui.fib_view`) and the chart draws it
  (toggle «фибо»): the dashed legs A -> B -> C, the retracements with the OTE band 0.62-0.79 (gold), the extensions
  (green); with the grid on, only strong map zones are drawn. ICT zones / LVN / opens have legend colours by family.
- eng-43 (no signal change): an entered card of an older logic keeps its trade to the end under its own levels (only
  waiting ones expire at a start; card rows carry the card's own `logic_version`) - closing every trade at each
  version bump left the demo with almost no finished trades. `deploy/` holds the VPS setup (systemd unit, install
  script, README in Russian): Railway / Render do not fit (US servers - Binance answers 451; ephemeral disk; ~0.5 GB).
- eng-44: the entry log / notification crashed on a target-less (Turtle) entry (`rr_tp1` None formatted as a number:
  the scan stopped before the demo order - AAVE 04:33); the cost guard is risk >= 3x the execution cost (5x vetoed
  ordinary 2% stops); the `vsa` confirmation reads only the extreme's 5m bar and the three after it (positive on 13 of
  16 entries before).
- eng-45 (execution on BingX, the owner's main venue): the demo carries every level of the Binance plan to BingX by
  the CURRENT price ratio (the contract scale x the basis between the venues), judges the entry at BingX's own ask
  (long) / bid (short) - skipped `PRICE_GAP` when that price is beyond the stop, beyond TP1, or the blended R:R there
  falls below the method's minimum - and journals the basis (`demo_trades.basis`). Measured 2026-10-02 on VST: basis
  -0.14% .. +0.09%, but the demo's spread reached 3.3% (1000PEPE) / ~0.4% (ALICE, MEGA).
- eng-46: resting BingX limit entries for the touch plans (Seiden's proximal line, the Silver Bullet's CE: plans with
  `trigger='touch'`): every waiting card gets a limit on BingX at its line carried over by the current price ratio,
  sized from the plan's stop (`DemoExecutor.sync_limits`, every 30s from the scan); a filled limit becomes a trade with
  its stop and take-profits (`check_limits`, each minute); the card's Binance touch never enters at market - if BingX
  did not fill within `executor.limit_wait_min` (15) the limit is cancelled and recorded `NOT_FILLED`; a card ending
  without an entry cancels it. One trade or resting limit per coin (BingX nets a coin into one position). Resting limits
  persist in `demo_pending.json`. Limit entries take no confirmation check (the methods enter at the line - Seiden),
  the R:R is checked at the line when the limit is placed.
- eng-47 (time exits, the owner's request): `Strategy.time_exit` - 'bars' (default): a trade without TP1 within
  `time_stop_bars` (24) bars of its structure timeframe is closed (15m 6h, 1h 24h, 4h 4 days, >= 4h), after TP1 the
  rest runs `time_after_tp1` (3) x longer; 'fixed' = the method's own exit with ttls()[2] as a cap (Turtles, Connors,
  cup, Seiden, Silver Bullet); 'session' = VA80 out at the UTC day's close (Dalton), ORB at 16:00 New York (Crabel).
  The flat 12h clock closed ALICE / MOVE on the way to TP2 / TP3 and held dead trades. Also: `card_r` = the thirds as
  traded (`SignalBook._exit_r`; it marked the whole position at the last price), demo risk / R from BingX's fill,
  lost limit fills closed (`LATE_FILL`, `UNTRACKED` safety net every 5 min).
- eng-48 (the owner's request): pools by the methods' sources (`PoolsConfig.rules`: Connors major / large, ORB and
  market_profile up to mid, pump mid / small, the rest all; pinned coins in every pool); Connors exits on the first
  daily close beyond the CURRENT SMA5 (`plan['connors_exit']`, TP placeholders like the Turtles, no demo TPs); an
  opposite setup of another strategy no longer closes a 'fixed' / 'session' method trade or a trade past TP1;
  `CONFIG.levels.min_rr_tp1_floor` 0.25 (TP1's own net R:R, methods with min_rr > 0); entry rows journal `reason`
  (detector note + trigger).
- eng-49: the Silver Bullet takes ICT's context as the sweep (`context_veto`: weekly / daily bias, else the 1h trend;
  longs only from the discount half of the 48h dealing range, shorts from the premium); at most `crowd_max` (3) entries
  of one strategy in one direction per `crowd_window_sec` (1h) - vetoed `crowded`, Turtles exempt - and the demo's
  resting limits obey the same cap (12 Silver Bullet longs at 10:30 NY 2026-10-02 into a -3.4% BTC move).
- eng-50: ORB is Crabel's trade - stop at the range's other side, no profit target (`tp ['trail']`, `plan['no_tp']`:
  no demo take-profits), out at 16:00 New York (session exit); its map target had killed 38 of 49 plans on
  2026-10-03 (a break into price discovery has no level beyond). A system plan without a target / valid stop is
  journaled `no_target` (was mislabelled `no_leg`).
- eng-51 (checked against sources, web 2026-10-03; LuxAlgo-type vendor pages not counted as independent): Bollinger
  W / M target = the opposite band (Bollinger / StockCharts; eng-40's measured move was ours); cup TP1 = half the cup
  height (Bulkowski: met ~76%, full height ~50%) and TP2 the full height; Connors out on day 10 without the SMA5 exit;
  ICT dealing range = the last 1h swing-low -> swing-high leg (`ict.dealing_range`, the 48h window only as fallback);
  invented thresholds off: `min_rr_tp1_floor` 0, pools of orb / market_profile / pump back to 'all' (Connors' liquid
  large caps kept); the crowd limit = at most `crowd_max` (6) OPEN trades in one direction across strategies (the
  Turtles' closely-correlated limit), Turtles excluded; one plan flag `no_tp` (Turtles, Connors, ORB) for "no
  take-profit orders"; their 100 / 200 / 300 R placeholders are journaled as NULL targets (`levels.simulate` treats a
  NULL target as unreachable). Still hypotheses, no source for the numbers: the time stop's 24 bars / x3, cost guard
  3x, limit wait 15 min, ORB anchored to the US equity open (crypto ORB sources use 00:00 UTC).
- eng-52 (Compass review, `research/compass_check.md`, `research_compass.py`): journal features `prem_1h` / `prem_z`
  (mark vs index premium, 24h history `MarketData.premium_hist`), `funding_1h` (hourly funding mode), `oi_vol`,
  `er_1h` / `chop_1h` (Kaufman ER, Choppiness), `rs_btc_z` (24h return net of BTC x beta); `journal.crowded` also
  reads the 1h premium beyond Binance's neutral band (+0.06% / -0.04%: the funding is exactly 0.01% on 57% of our
  rows); demo stops trigger on the MARK price (`workingType`); Connors' pool back to all coins (crypto reversal is a
  small-coin effect); stats.py `reversal_test_table` (Mahadzva's reversal-vs-continuation test on our setups).
- eng-53 (Compass "7 phases" review): `event_risk.py` - Binance's Monitoring Tag (spot product tags) and scheduled
  perpetual delistings (futures exchangeInfo deliveryDate), hourly; longs on such coins vetoed `event_risk`; journal
  features `event_risk`, `near52` (price / 52-week closing high; daily candles now 370), `vol_rank`, `liq_proxy`
  (OI falling with price over 5m). Not done: the pump detector vs naive baselines (only 22 PUMP START rows yet).
- eng-54: the cost guard (risk >= 3x the execution cost) also applies to target-less plans (Turtles, Connors, ORB:
  the `trail` branch of `geometry.system_levels` skipped it) - ETH's ORB of 2026-10-03 had a 0.10% stop on a 0.15%
  range and lost -2.2R in the demo.
- eng-55 (the audit's plan, docs/PLAN_after_audit.md; every rule checked against its source by web search 2026-10-04;
  the owner lifted the freeze): ORB = Crabel's book rule - stop orders at the day's (00:00 UTC) open +- the Stretch
  (10-day SMA of min(H - O, O - L)), entered on the touch loop-side (`Scanner._orb_touch`), the other level the stop,
  out at the UTC day's close (the 30-minute US-open range + 15m close of eng-29..54 was not his rule); Bollinger W / M
  needs Accumulation / Distribution NOT confirming the retest (method III compares tags with A/D; rule 6 "tags are not
  signals") and exits at the LIVE opposite band (`SignalBook.band_of`, no TP orders); Seiden's leg-out candle body >
  half its range (OTA's "exciting" candle); Wyckoff's range from phase A EVENTS (SC -> AR -> ST, `_phase_a`; the
  20-candle sideways window was ours), the test also needs a narrower spread (`levels.pullback_spread_ok`), TP adds the
  point-and-figure count (box = a tenth of the range, 3-box reversal: our box); Connors' 2% stop -> a catastrophic stop
  3 daily ATR away labelled as our deviation (he uses none); Turtles at most 6 units per direction (Faith: closely
  correlated markets) and the demo unit shrunk so 4 units fit the notional cap; PUMP TOP journaled without a card
  (the archive's fade, negative in every period); new `DUMP BOUNCE SHORT` (pump strategy, `strategies.pump.dump_bounce`,
  the research rule positive in every period 2021-2026, small caps only). stats.py: `verdict_table` - the two-level
  verdict (SUSPEND at >= 30 clusters with the 90% lower bound < -0.05R; DEPRECATE only at >= 200 clusters - MinTRL of
  a +0.1R edge - with the upper bound < 0), PSR / DSR (N = logic version x strategy cells: an upper bound, ONC not
  computed) / MinTRL; `demo_gap_table` (entry and stop slippage of the demo vs the plan). Checked and kept as the
  sources define them: trendlines already trade the break (two closes beyond the line), VA80 on the UTC day, the Silver
  Bullet's New York windows (ICT applies them to every market).
- eng-56: `oi_signal` (OI SIGNAL LONG / SHORT, strategies/oi_signal.py, `Scanner._oi_signal`): a LIVE TEST of
  cryptomillion's "OI [15m]" alerts (teletype; a commercial channel with no published evidence): 15m OI >= +3% and
  price >= 2% with the 15m futures taker delta and the 1h OI / price agreeing; OI rising while price and CVD fall =
  the short. Thresholds ours (they publish none). Entered at market, stop beyond the 15 minutes' extreme, map targets.
  Also eng-55 fixes: entered trades keep their plan in scanner_state.json (lost on every restart: Turtle channel
  exit / pyramid, Connors' SMA5 exit, no_tp placeholders shown as negative TPs), the demo's BingX ratio rebuilt after
  a restart, ORB keeps the day's state per coin (15m candles rebuilt each minute stalled the loop), QuickEdit off
  before the first console write.
- eng-57 (checked against ICT by web search 2026-10-04; ICT's own definition is only in his videos, so the common
  ground of several independent write-ups): an order block's displacement must close beyond the last CONFIRMED swing
  (ICT's 3-candle swing: the middle candle's high above both neighbours', confirmed by the block's candle), not the highest high / lowest low of the
  ten candles before it; the rest already matched (the last opposite candle, an FVG in the displacement, the zone open
  -> wick, the breaker on a close through the far side). joshyattridge/smart-money-concepts was compared on 20 coins x
  499 1h candles: FVG detection identical; its order block (the lowest candle between swing and break, any colour, no
  FVG) departs from ICT more than ours, so it is not adopted. Also: `Scanner.wide_watch_loop` (every perpetual outside
  the universe >= $3M: the pump / dump monitor «·вне» and DUMP BOUNCE SHORT journaled `outside_universe`, no card),
  stats.py `robustness_table` (tail / coin / halves / cost-to-zero, PBO by CSCV) and the Harvey-Liu haircut in the
  verdict, journal `weis_ratio` (Weis wave into SPRING / UTAD), the demo's reduce-only limit close on BingX's price
  band (102202).
  eng-57 fixes found by the error audit: trendline never fired in the journal's whole history (`tl_flat_deg` 7.5, his
  15m bot's cut, excluded every 1h line gentler than 0.13 ATR a candle - all lines spanning 40+ candles; now 0) and
  its 'map' target read an empty list (also oi_signal's: `geometry.exit_target` reads the map at the entry); the demo
  signs every private BingX call with recvWindow 60s (ccxt's signer sent none: BingX's 5s default vs ~11s VST round
  trips = 'timestamp is invalid').
  Parameter audit (docs/AUDIT_parameters.md, 2026-10-04): 42 config values no module read were deleted (the removed
  systems' te_* / csi_* / oi_* robot / fib05 / bomberman, the standalone SMT / absorption, the 15m breakout, a few
  infrastructure leftovers); the duplicate `metrics.funding_crowded` merged into `orderflow.crowded_funding_long`;
  the Holy Grail needs ADX > 30 AND rising (`adx_prev`, Raschke). The ported robots' values were checked against their
  repos (trendline_bot, supply_demand-v4, auction_theory_in_code): all match; they ran on 15m, ours on 1h / 4h.
  First-commit values rechecked (docs/AUDIT_parameters.md section 9): the Bollinger squeeze is BandWidth at its
  ~6-month low = 125 bars (`bbw_squeeze_lookback`, was 50); session pools use the exchanges' local hours with daylight
  saving (`sweep_sessions` = Tokyo 09-18, London 08-17, New York 08-17 local; were fixed UTC 0-8 / 7-16 / 13-21).
  Formulas / data instead of hand-set numbers (eng-57, docs/AUDIT_parameters.md section 10): the minimum leg is
  derived (`levels.min_leg_atr` = min_stop_atr / 0.382, `min_leg_move` = cost_guard x round-trip cost / 0.382); the
  liquidation estimate uses the tracked Hyperliquid accounts' real notional-weighted leverage (models/leverage_mix.json,
  positioning) and each contract's maintenance margin / max leverage from Bybit's public risk limits
  (models/maintenance.json, daily); equal highs / lows are within the coin's measured p50 pierce; the whale size is the
  coin's own p99.5 sweep (USD floors only during the cold start); the regime count is chosen by BIC (2..6);
  research_level_weights.py: swings / equal / previous-day / round levels hold price LESS often than placebo prices
  (odds ratio 0.79-0.86) and alike -> their weights are all 1.0; entry replays journal `tp1_min` for a measured time stop.
  Extended (research/level_weights.md): FVG 15m / 1h (OR 0.83 / 0.90), order blocks 1h (0.94), breakers 1h (0.83) hold
  price no better than placebo, the day's volume profile POC / VA / HVN / LVN exactly like it (0.98-1.02) -> those
  weights are 1.0 too; the 4h / daily / weekly ICT scaling, vwap, fib, range, book, liquidations stay unmeasured.
- eng-58 (the full audit, docs/AUDIT_full.md; the practice review, docs/STRATEGY_PRACTICE.md): result honesty - the
  card's R (`card_r`, the verdict's input) is NET of fees, slippage by liquidity and funding (`SignalBook._cost_r`)
  and a stop gapped through fills at the candle's open (`exit_fill`); trades are managed on the final 1m candles'
  extremes since `managed_ms` (targets 2 bps through, the stop first in a candle - as the journal's replay; the scan
  price missed every wick); resting limits (Seiden, ICT CE / OTE, trendline retest, PO3) are replayed at their price
  (`limit_entry`); the 1 ATR stop floor applies with the pierce model too; the waiting zone's end prices costs by
  liquidity; `min_confirmations` 0 (one of five ~50/50 readings passed ~95%); the verdict / robustness run over the
  version family since `journal.verdict_since` (eng-55) with older gross card R netted (`stats.card_r_net`). ICT by
  its practice: the sweep's MSS is a close beyond the swing the raid came from (`ict.fvg_setup`), which ARMS a resting
  limit at the gap's CE (`TrackedSignal.armed`: the plan becomes a touch plan the demo places); continuation needs a
  leg that broke structure (`no_bos`) and enters on a limit at the OTE zone's near edge; sweep / continuation enter
  only in the London / New York kill zones (`killzone`; their demo limits rest only there); the Silver Bullet needs
  the MSS and targets the previous day's high / low; new `po3` (ICT Power of Three / Judas swing, strategies/po3.py);
  ICT pools major / large / mid. Others by their sources: trendline enters on the retest (a limit at the broken line),
  supply / demand vetoes against the daily trend (`big_picture`), the cup with handle runs on daily candles (35+ day
  bases, 12-33% deep), Connors RSI(2) 5 / 95 without a 10-day exit, VA80 on the TPO value area, the liquidation
  climax needs a prior trend (`no_prior_trend`) with a 15m structure. System: one direction per coin a day
  (`against_day`, the Turtles exempt); continuation / oi_signal take half at TP1 and trail the rest (entry, then the
  entry timeframe's EMA20; RESTOP moves the demo's stop); the demo stops trading for the day at -3R, after 6 trades,
  and pauses 4h after 3 losses in a row (`executor.risk_limit`). Dead code removed: fib05 / SMT detectors, the
  pinbar / ifvg triggers' branches, WhaleConfig. Not done: pretraining that replays the 13 strategies (meta-labeling
  needs it) - a separate project.
- eng-59 (the rest of the 13-item plan + the pool audit): the replaced rules are journaled as vetoed entries of the
  same card for the comparison (`SignalBook._shadow_entry`: `weak_mss` = the old sweep trigger before the new MSS armed
  the card, `variant_shift` = the old 5m-shift market entry beside the resting limit of continuation / an armed sweep);
  an ICT card in its zone expires when its kill zone ends (`session_end`); altcoins' sweep / continuation / PO3 trade
  with BTC's ICT bias (`against_btc`, journal `btc_bias`); fix: the Silver Bullet (strategy `sweep`) was vetoed
  `killzone` in two of its three windows (`ict_gated`). Pools: a coin's class is its rank among ALL Binance USDT
  perpetuals (`fetcher.market_volumes`; within the 70-coin universe 'mid <= 80' meant every coin); a coin leaves a
  strategy's pool only when its entries are proven negative (`journal.proven_negative`, 4h blocks + BH, `min_blocks`
  8; was mean <= -0.3R over 8 entries); stats split `method nature x coin state` (Dreiss' Choppiness) and `BTC bias`.
  `research_pools.py` (pre-registered): Turtles / Connors trades on the daily archive by coin attributes (market volume
  rank, ATR %, Choppiness, ER, beta / corr to BTC) -> research/pools.md.
- eng-59 B9 (archive replay of the live lifecycle): the loop-side detectors moved from scanner.Scanner to
  `strategies/loopside.py` (`LoopDetectors`: pump, Silver Bullet, PO3, Turtles, ORB, OI signal, dump bounce, Connors)
  so `replay.py` runs the same code: the live `SignalBook` stepped once a minute over the Binance archive (1m futures /
  spot, 5-minute OI metrics, funding, daily candles), fed by `build_maps` (maps + 15m-close events), `LiveDetector`,
  `LoopDetectors`, the scorer's phases / Tier-0, confirmations from Binance's own 1m flows / OI; every entry (passed and
  vetoed) also replayed by `levels.simulate`; outputs data/replay/<run>/group_NN/{cards,entries}.parquet (groups of
  `--group` coins share one book). Not in the archive: liquidations (no cascade setups), books, other venues,
  Hyperliquid, footprint. `research_replay_report.py` -> research/replay.md (cards' net R, exits by nature, vetoes).
- eng-60 (local eng-56 + this note's changes, merged with origin's eng-57..59 on 2026-10-05): the map
  holds each completed UTC day's naked POC (Dalton's virgin POC: `zones.day_poc` from 5 days of 5m candles of every
  universe coin, once a day by `fetcher._day_pocs_loop`, ~700 weight; naked = no 1h candle after that day traded
  through it, `zones.naked_daily_pocs`); AUCTION's target falls back to the next map POC (naked daily / 4d / 24h) when the engine's own 1h POCs hold
  none ahead (was `no_target`), min R:R 1.5 kept. Also (no signal change): `errors.report` - no exception handler
  swallows a failure (WARNING throttled per source, counts in the Health line); `memreport` - a 'Memory MB' line every
  10 min (process classes by VirtualQuery + the bot's structures), `tools/vmmap.py <pid>` the same from outside;
  `MIMALLOC_PURGE_DELAY=0` (polars' mimalloc kept freed blocks); FlowStore rows = max_pairs + 40 (was 320); the
  BingX demo session staggers connection attempts (a dead VST address cost 21s per new connection -> 'timestamp is
  invalid'; demo leverage now sent with side BOTH - it was never set; a BingX stop filling before our close is
  EXCHANGE, not a failed close); winloop's 'write() when UVStream is closing' is a counted WARNING; journal warm-up vectorized (numpy) + index universe(symbol, ts_ms, price). Never combine winloop with
  tracemalloc (create_server hangs).
  Merge fixes (research/replay_missing.md, the cloud replay's diagnosis of eng-58/59): ORB takes the day's open from
  the day's first minute itself (`loopside._orb_touch`: at 00:01 UTC the minutes before the last one were empty and
  the day stayed 'open unknown'); the maps get the whole daily history (`_map_job`: 60 daily candles never reached
  the daily cup's 120); `minute_klines` holds 600 minutes (PO3 reads the Asian range 20:00-00:00 New York from
  02:00-05:00 NY: 240 minutes held at most 21 of its 48 5m bars). eng-57's recvWindow-60s sign wrapper on BingX was
  dropped (the cause was the dead address; BingX documents 5000 ms as the maximum); the demo close handles both an
  exchange stop that filled first (101290 -> EXCHANGE) and the price band (102202 -> reduce-only limit). Futures
  klines REST weight by Binance's table (1 / 2 / 5 / 10).
- eng-61 (2026-10-05, the owner: "find why and fix everything"):
  Confirmations: `orderflow` was structurally absent for the systems entering at their signal's close (footprint and
  the absorption ATR existed only for cards waiting in a zone: ORB 4 positive of 88 entries, Bollinger 4 / 83, pump
  0 / 19) - the footprint now runs for every universe coin (5 bps price buckets, last 30 min; an older extreme reads
  the flow into the entry) and absorption takes a 15m ATR estimate from the 1m candles; `vsa` needed 20 5m bars
  before the extreme inside a 3h window (never positive for extremes older than 80 min: ORB median 273, VA80 300)
  and its no supply / no demand counted anywhere in a pullback (continuation 40 of 41 positive) - now the whole 10h
  buffer, the last four closed bars when the extreme is older, and no supply / demand only as a TEST near the
  window's low / high (Williams): 20% positive at random points. Every entry journals `_ind` (strategies/ind_panel.py:
  EMA 20/50/200, RSI, MACD, ADX/DI, stochastic, %B, band width, MFI, OBV, CCI, ATR rank, RVOL as 20 directional
  rules on 15m and 1h) and `_book` (the local book's imbalance, pulled / filled within 1% over 5 min, a $50k order's
  impact). research_indicator_confirms.py (pre-registered; research/indicator_confirms.md): 208 strategy x rule x
  timeframe cells on the archive replay, 0 pass BH q 0.10 - no classic indicator turns an entry set positive.
  Order books rebuilt (depth.py): a local book per hot coin from the @depth@500ms diff stream + a 1000-level snapshot
  with Binance's sequence rules (the 500-level REST snapshots every 60s covered BTC +-0.07%, ETH +-0.2%); every
  decrease split into filled (aggTrades at the price) / pulled; heat snapshots of the whole book every 30s; walls
  stand 30s within +-2%; bands drop when their pull turnover is > 3x the side's median; `slippage_bps` walks the
  book. 'book' left zones.STRUCTURE_KINDS (no stop on pullable orders) and weighs 1.0; the chart's density lines
  are the bot's bands (the looser second definition and the dead `LiveDetector.levels_of` were removed).
- eng-62 (2026-10-05, the owner: adapt the classic methods to crypto futures by search and test them on the demo):
  research_optimize.py simulates every replayed entry (16 550, 40 coins x 12 months, 5m paths) under 524 position
  management variants (target 1-3R / the plan's TP1 / none, breakeven after +1R, a 2-3 x 1h-ATR chandelier trail,
  a third (research: half) at +1R, time stop 4-72h, stop 1.0 / 1.5 x) and selects per strategy filters (none, one or
  a pair of 53: indicator rules, coin class, session, weekend, BTC's trend, ATR rank, the bot's veto) on the first 8
  months; the last 4 months are the validation (research/optimize.md, research/optimize_robust.md: a profile also
  stable in both training halves). Validated: only the Turtles (their own exits +0.36R on 108 validation cards; the
  profile coin:large + 3R / breakeven +0.52R on 21). models/profiles.json: every other strategy's best profile as a
  `candidate` for the demo (validation pump +0.29R / 11, sweep +0.02 / 18, the rest negative) -
  strategies/profiles.py applies the filters at the entry (`vetoed='profile'`) and the position management
  (SignalBook._profile_manage: breakeven / trail with RESTOP to the demo; the profile's time stop in _time_exit).
  Confirmations carry `_btc_slope` / `_atr_1h` for it.
- eng-63 (2026-10-05): regime switch (research_optimize_regime.py, pre-registered): BTC 4h ADX >= 25 trend / range x
  ATR above / below its 125-candle median -> trend_hv / trend_lv / range_hv / range_lv (strategies/profiles.regime_labels,
  the same function live via fetcher `_regime` from BTC's h4). Per strategy x regime one filter at most, positive in
  both training halves, validated once: ON breakout trend_hv (+0.42R [+0.18] on 105 - not applied live, the Turtles keep
  their own exits), pump trend_lv / range_hv / range_lv and supply_demand trend_hv (1-11 validation trades: candidates).
  Continuation failed in every regime (decay, not a regime artifact). models/profiles_regime.json: a strategy listed
  there trades only in its ON regimes (`vetoed='regime_off'`), with that regime's profile; others keep
  models/profiles.json. replay.py switches the profiles off (it measures the methods' own plans). Profile filters are
  skipped (logged) when the indicator panel is missing. docs/CLOUD_OPTIMIZE.md: the 120 coins x 24 months job
  (research_replay_summary.py, OPT_TRAIN_MONTHS / OPT_PREFIX / OPT_PROFILES).
- eng-64 (2026-10-05, web-checked: the OI price/OI quadrants - Bookmap, Traders Log; Trader Dale's level + order-flow
  timing): `oi` is a confirmation of every method by its type (strategies/confirm.OI_EXPECT: breaks / continuations /
  pump / OI signal / trendline / cup expect OI rising - new positions; fades - Bollinger W/M, market_profile, Seiden,
  Connors, sweep, wyckoff - expect it falling: the move faded was positions closing); journaled, required only when
  proven. The order-flow entry in the zone (`SignalBook._flow_entry`, Dale: absorption / imbalance / finished auction
  at the level + the delta since the zone's extreme turned the trade's way, + OI as the type expects) is journaled as
  a vetoed entry `flow_entry` of the same card (once per card, only in a scan where the method's own trigger did not
  enter) so the journal compares the two entries. Hot set: free order-book slots go to coins with a setup in the last
  3h, then the pinned coins (the close-entry systems had no synced book at their entry; 13 of 25 slots were used).
- eng-65 (2026-10-05): research_overlays.py (pre-registered; research/overlays.md): early exits over the method's own
  plan - noprog_H (no +0.3R within H hours), struct (a 15m close at -0.5R), btc_K (BTC K% against within 15 min,
  altcoins) - and the alts-vs-BTC filter (the universe's median 4h return beat BTC's the trade's way). Adopted (train
  lower bound > 0 and validation > 0), all small (+0.01..+0.16R; no strategy turns positive): connors struct + alts_with,
  trendline noprog_2, market_profile btc_0.7, sweep / supply_demand noprog_4+btc_1.0 (models/exit_overlays.json;
  SignalBook._overlay_exit at each final 1m close, CLOSED at the close; the filter vetoes `alts_vs_btc`). They apply to
  the method's own plan only, so the candidate profiles that FAILED validation left models/profiles.json (bollinger,
  trendline, market_profile, continuation, connors). research_htf_filter.py (the owner's "the higher timeframe
  decides"; research/htf_filter.md): the coin's daily / 4h / weekly trend and 4h trend-vs-range change no strategy's
  mean R (0 of ~50 cells kept); continuation's entries run AGAINST the daily trend ~90% of the time (its tide is the
  1h / 4h). BTC / USDT dominance (CoinGecko /global, 5 min) journaled as `_dom`; market state carries `btc_4h`.
- eng-66 (2026-10-05, the owner: "the higher timeframe always comes first"; web-checked: Elder's triple screen, ICT
  top-down bias, Weinstein / Shannon stages, time-series momentum, range trading): strategies/bias.py - per coin and
  for BTC the tide = the momentum blend (sign mean of the 30 / 90 / 365-day returns) + the daily trend (close vs EMA50
  and its 5-day slope) for intraday methods, + the weekly (close vs EMA20) for daily methods (Connors, cup); the 4h is
  the WAVE (a pullback against the tide is the entry); 'range' = no daily trend and 4h ADX < 25; else 'conflict'.
  Gate (SignalBook._enter): no altcoin trade against BTC's bias (`btc_bias`), none in a conflict (`htf_conflict`),
  trend / with-bias methods only the tide's way, range methods (market_profile, bollinger, wyckoff) in a range both
  ways (target capped at the 20-day range middle) and in a trend only its way (`htf_bias`); the Turtles and trendline
  (a broken line signals a change of trend) are exempt. Journaled `_bias` (coin, btc, components). research_bias.py
  (the rule fixed by the sources; the card's full final_r, by month and side; research/bias.md): the allowed trades
  lose less in most strategies (+0.01..+0.24R) but no strategy passes the pre-registered bar; the gate removes ~70% of
  the (losing) trades. Methodology fixes (the owner's audit): full-trade outcomes instead of the 8h r_tp1, results by
  month / side, fixed source rules instead of searches where possible; research_htf_filter's 8h verdict is void.
- eng-67 (2026-10-05, the owner caught it; web-checked: "use the ATR of the timeframe the setup is on" - QuantVPS,
  ChartingPark; Seiden-style zones: the stop 1-2 ATR of the zone's timeframe beyond its distal line): the stop floor
  (`geometry.stop_floor`) used the 15m ATR for every plan, also for 1h / 4h / daily structures (SOL: ATR 15m 0.44%,
  4h 0.98%, 1d 4.2%) - a 4h zone's stop could sit inside 4h noise. `PlanInput.tf_atr` (Scanner._tf_atrs: ATR14 of the
  closed 1h / 4h / daily candles), `plan['tf_atr']` = the plan's own timeframe's ATR, and both floors take the max of
  the 15m ATR, the leg's and the structure timeframe's. The measured pierce beyond a level (per level kind) is
  unchanged. research_entry_edge.py / research_geometry_audit.py (research/entry_edge.md, geometry_audit.md): on the
  eng-59 replay the bollinger / market_profile / connors entries do not beat placebo entries even without our stop /
  targets; trendline / pump / breakout entries do at 2 ATR (trendline's stops sat at 0.7 1h-ATR, 77% inside an hour's
  range; pump's TP1 was closer than its stop, R:R 0.63) - a replay on the current code is the cloud job's step 1.
- eng-68 (2026-10-05, the owner: "and the take-profit - also on the lower timeframes? then the R:R is cut"): yes - TP1
  was the nearest strong / primary zone of the WHOLE map (15m swings / FVG / OB included), spaced and filled by the 15m
  ATR. Now `geometry.htf_zones`: a plan of timeframe tf targets only zones of tf and higher (zones whose kinds all
  carry a lower timeframe suffix are dropped; untimed kinds - previous day / week, sessions, profile, round, VWAP -
  stay); the planned targets that sit on such lower-timeframe zones are dropped at the entry (`_ltf_prices`) and the
  slots refilled from the allowed zones; the spacing / ATR steps use max(15m ATR, the leg's, the structure
  timeframe's ATR) - entry_levels, system_levels, exit_target's map branch.
- eng-69 (2026-10-05, the owner: "stops beyond the zone with a 3-5% margin"): the buffer beyond a stop's structure is
  max(the measured pierce, `levels.zone_buffer_atr` (1.5) x the ATR of the structure's own timeframe)
  (`geometry.zone_pad`: stop_levels, the systems' 'ref' stops and the ICT protected-swing stop); `sl_src` names which.
  Also `structure_stop` (the systems' fixed % / ATR stops replaced by the map) takes the same buffer; PUMP START targets
  the measured move and 1h+ zones only (`plan['target_tf']`, honoured by every `htf_zones` call): its stop spans the
  whole ignition, the nearest 15m zone gave TP1 at 0.56 of the risk (all 7 eng-60 entries `low_rr`).
  Map fixes (the owner compared BTC with an analyst's weekly levels): the dashboard drew its own map from the card-only
  1h history - for a coin without a card no 1h / 4h / daily / weekly level, no previous day / week (`Scanner._build_levels`
  now returns the map the plans use); the quick map rebuilds when the 1h / 4h / daily / weekly / day-POC histories arrive
  (they load after the first quick map: for up to 15 min after every start the plans had only 15m levels); a failing
  map in the worker reaches scanner.log (`errors.report('scanner.maps')`, was the console only); `/api/debug` shows the
  histories' sizes and the map's kinds.
- Briefings / watch alerts (2026-10-05, the owner: BTC, ETH, gold and oil lead the alts; the session opens move them):
  `briefing.py` posts to the owner's Telegram channel (Notifier.post, HTML; token / channel from config.local.toml or
  the environment's TELEGRAM_BOT_TOKEN / TELEGRAM_CHANNEL_ID; `notify.enabled` now on, toasts off): briefings before
  the Tokyo / London / New York opens (02:30 / 09:30 / 16:00 MSK, `CONFIG.briefing`) per watched coin (BTC ETH XAU CL
  SOL XRP: bias components, 1h+ zones of the plans' map with what holding / losing means, base / alternative
  scenario), dominance, breadth, the day's US releases (CPI / FOMC dated, NFP / ISM / claims by their publication rule);
  a 23:30 recap (zones tested / broken, scenario met); alerts: a 1h close beyond / a sweep of a briefing zone, a 15m
  shock >= 4 sd and 1.2% with the breadth and the session, a BTC / ETH / XAU / CL bias change, the demo's fills /
  exits, anomalies of the watched coins, venues down / component errors / the demo's risk stop; card events add
  CLOSED / RESTOP / INVALID / ADD. `/api/briefing` (?kind=recap, ?send=1) shows the text. Oil = Binance's CLUSDT
  (WTI, pinned). research_sessions.py -> research/sessions_leaders.md: the opens' moves vs other times and whether a
  leader's move comes before the alts' (lagged correlation, next-15m / 60m continuation).
  The briefing is sent as pictures (`briefing_chart.py`, matplotlib; the owner's reference layout): a 4h chart (10 days; the 1h was unreadable against daily / weekly zones) with the window's extremes, the scenarios' paths and the
  named zones (global / resistance / local resistance, the zone price sits in, next / key / global support: per side
  the three strongest 1h+ zones >= 0.4 daily ATR apart, ties to the higher timeframe's level), price tags with the
  distance, the long (acceptance above the zone -> the resistances, stop below the next support; price discovery =
  half-daily-ATR steps, labelled) and the short (reaction at the nearest resistance) with entry / 3 targets / stop /
  condition; the scenario's % is the driftless random-walk chance of TP1 before the stop, labelled - not a forecast.
  The demo's daily loss / trade count / losing-streak stops are off in config.local.toml (the owner: the demo measures).
- eng-70 (2026-10-05, the owner: "where 15m / 1h / 4h hold no level, the daily / weekly do"; web: the prior period's
  extremes and major swings carry the large S/R): the map adds intact daily (fractal 3) and weekly (fractal 2) swings
  (`swing_1d` 2.5, `swing_1w` 3.0), the previous month's high / low (`pmhl` 2.5), the month's open, the 52-week high /
  low (`year` 3.0) - `zones.htf_swings`, structure kinds (stops), pierce as swing_1h / pdhl. Briefing card: the watched
  zone's role follows the price at the post (role reversal: inside = reaction zone, above = support with the long on
  its retest, below = resistance with the short on its retest); long = 1h close above the zone + retest (or the retest
  once above), stop below the zone; short = 1h close below + retest (or the retest once below), stop above it; targets
  the resistances' / supports' near edges ahead of the price; zones of 15m / 1h swings / equal highs only are skipped.
- eng-71 (2026-10-06, the owner: "check every 'not a card' for geometry errors"): (1) slippage by the square-root
  impact law (Toth et al. 2011): half spread 1 bp + 0.5 x 4% x sqrt($10k / 24h volume), cap 25 bps
  (`levels.slippage_bps`; was 5 x sqrt($500M / V) - no order size, 25 bps a side on a $20M coin, ~5x too high, every
  plan's cost / low_rr inflated); (2) Bollinger W / M stop beyond the retest by the pierce / zone buffer with the 1 ATR
  floor (`exit['pad']` in the trail branch of system_levels: BTC's stop sat 0.08% away and the cost guard vetoed it);
  (3) VA80 skips a value area already traversed (< 0.3 of its width left to the far edge: TP1 0.06-0.15% away);
  (4) PUMP START min R:R 1 (stop = the ignition, TP1 = its measured move: R:R ~1 by construction, 2 vetoed all).
- eng-72 (2026-10-06): `fetcher._external_loop` - ForexFactory's week calendar hourly (`macro_calendar.LIVE`, USD high /
  medium; HIGH-impact events join the entry blackout beside the dated CPI / FOMC - NFP / PCE / GDP / minutes were
  missing; the briefing lists the real events instead of the publication rules) and Deribit every 5 min (DVOL of BTC /
  ETH -> the day's priced move DVOL / sqrt(365); every 30 min the option OI by strike of the two nearest expiries,
  `fetcher.options`): briefing context only. The funding interval was already handled (`_funding_info` normalises every
  rate to 8h), so R needs no change there.
- eng-73 (2026-10-07, the review of the 2026-10-06 run): session methods (ORB, VA80) exit only at the session's end
  (the 12h cap fired first for every trade entered in the UTC day's first half); a time exit that fell due while the
  bot had no data is marked at the close of the minute it was due (`_time_exit` returns the due time); a map zone
  beyond 3 sd of a random walk over time_stop_bars x time_after_tp1 bars of the structure ATR is no target for R:R
  (`finish_levels`, '(beyond reach)': FET AUCTION's 52-week-high TP2 gave blended R:R 28; the anchor's own objectives
  stay); a vetoed trigger repeated scan after scan is journaled once (`TrackedSignal.last_veto`: 261 PO3 rows of 2
  cards); universe snapshots only from REST marks < 2 min old (13h of frozen marks during the outage, deleted from the
  journal); the demo recovers results whose exit fill was not listed at the close (`_refinalize`) and names a frozen
  VST quote; Telegram falls back to plain text on an HTML parse error; `_btc_bias` 0 = known neutral.
- eng-74 (2026-10-08, the review of the briefings, web-checked against Murphy / Bulkowski / Osler (NY Fed) / ICT
  write-ups / Elder / Moskowitz-Ooi-Pedersen): `zones.merge` - a level wider than `zones.max_merge_atr` (6) x the
  merge's ATR is a zone of its own that absorbs nothing, and a merged zone is at most that wide (a 6.5k daily breaker
  chained BTC's 86.5-93k into one zone; a hypothesis to be measured); the briefing (`briefing.key_zones`) keeps whole
  zones (no 0.3-daily-ATR trim, a zone around the price is shown - the wide ones as context), supports below the
  price and resistances above it, each zone with `tol` (p50 pierce: retest / acceptance tolerance) and `pad` (stop
  buffer: p80 pierce, >= 1.5 1h ATR); `briefing_chart.plan` = one source for the card, the text, the alerts and the
  evening scoring (inside a zone: 1h close beyond + retest; between zones: the nearest support's / resistance's
  retest), targets only real zones (ATR steps only above the history's high), percentages from the entry, 'шанс TP1
  по расстоянию' instead of 'Вероятность', the higher timeframe labelled 'Фон (недели)', 24h extremes with the minute
  candles, XAU's history spliced with PAXGUSDT before its listing (12.2025), year levels of younger contracts named
  'NNNd'; the 23:30 recap scores every saved briefing scenario (fill / TP1 / stop / acceptance without a retest);
  anomalies of a watched coin within 5 min go out as one message with the zone and the scenarios' state; a waiting
  card whose TP1 is already behind the price is not a card (`tp1_passed`), the exhaustion's test zone narrower than
  the p50 pierce is `no_room`; the dashboard's universe baseline loads only the page's window (the whole table, 1.2M
  rows rebuilt every 10 min, was the memory growth); the demo closes card-driven exits with a reduce-only limit at
  the touch first (market after 15 s) and journals the card's exit price (`exit_ref`). Not changed (the Turtles'
  rules): units are added during liquidation cascades.
  eng-74 also (NEAR OI SIGNAL LONG 2026-10-07 22:07 UTC, entered on data Binance's own OI history contradicts): the
  OI signal and the pump detector measure their 15m / 1h windows by TIME (`oi_signal._close_at`: the candle that
  opened exactly then; a missing minute = no signal) and an OI change needs a sample within 3 minutes of the window's
  start (after a RAM-paging feed gap `minutes[-16]` and the last old OI sample were far older: '+5.56% / OI +4.68% in
  15m' where the mark moved +1.7% and OI was flat); the reach check covers every target on a map zone of ANY kind
  (Hyperliquid liquidation prices +76% / +100% had no pierce model and made a 0.31 R:R a blended 8.9). The briefing
  lists the edges of a wide zone around the price as levels (targets).
  eng-74 also (the briefing zones checked against the candles, 2026-10-08): the week's open is the open of the candle
  that opened AT the week's start (the first 15m candle held was taken - the 15m history is shorter than a week: ETH
  2 690 for 2 725.71); PDH / PDL / PWH / PWL come from the daily candles when the 1h history does not cover the whole
  period (200 1h candles ~8 days: ETH's PWL read 2 645 for 2 634); `strategies.structure.liquidity_pools` still builds
  its PW pools from the 1h candles only. The briefing's zones use only significant levels (`briefing._significant`:
  daily / weekly swings, PDH/PDL/PWH/PWL, the completed sessions' ranges (ICT: London runs Asia's liquidity), week /
  month open, PMH/PML, the year's extremes, 4h+ FVG / OB / breaker / BPR, naked daily POCs, the 4-day profile), each
  at most half a daily ATR thick from its price, merged zones at most half a daily ATR wide (a convention, no source
  for the number). Excluded as unproven / intraday: VWAP (no evidence beyond its use as an execution benchmark),
  the rolling 24h profile, 15m / 1h swings, equal highs / lows, round numbers (Osler's FX order data supports them,
  our crypto archive does not: research/level_weights.md, OR 0.79-0.86).
  eng-74 also: the map holds the previous completed UTC day's POC / VAH / VAL (`zones.day_poc` now returns
  (day, POC, VAH, VAL) from the 5m candles; `naked_daily_pocs` adds 'POC PD' / 'VAH PD' / 'VAL PD' - Dalton's
  reference value area; the briefing shows them); the sweep's liquidity pools take the previous day / week from the
  daily candles when the 1h history does not cover them (`structure.liquidity_pools(..., d1)`, closed days only).
  eng-74 also (the 09:30 card of 2026-10-08): overlapping briefing zones are merged (up to a daily ATR wide - the
  half-ATR cap had drawn BTC's 81 857-82 500 inside 81 511-82 414); a scenario whose TP1 is closer than its stop
  (R:R < 1) is not shown - the card says why (a long 51 under the next resistance; a short's TP1 -0.3% for a +1.6%
  stop whose 'chance' read 82%); 'у верха / у низа зоны' when the price is only within the zone's tolerance; close
  zones' labels pushed apart.
  eng-74 also (the cards checked against the range / break-and-retest playbooks): inside a zone the card takes per
  side the better of the breakout (1h close beyond + retest, the stop beyond the whole zone) and the zone's edge
  (range trading: buy the support edge / sell the resistance edge, the first target the opposite boundary, the stop
  beyond the edge) - after the merge every coin's price sat inside a daily-ATR-wide zone and all six breakout
  scenarios were R:R < 1; overlapping zones too wide to merge are split at the middle of their overlap. The R:R >= 1
  floor has no source (Tharp: the needed R:R follows the win rate, (1 - p) / p + costs) - the evening scoring of the
  saved briefings is what will measure p.
  eng-74 also: a briefing stop that falls inside another zone moves beyond that zone's far edge + its pad (a test of
  the next zone would take it - Osler; BTC's short stop 84 087 inside 83 577-84 273 -> 84 873); the REACTION that
  enters every briefing scenario is defined (`Briefing.reaction`): a closed 1h candle that traded into the entry
  range and closed back beyond its far edge, a candle of the trade's colour (the confirmation candle of the
  break-and-retest / range playbooks) - the card's condition says so, the evening scoring enters at that candle's
  close (was: any touch), and a live alert '✅ реакция ... сценарий включён' posts the entry, stop, targets and R:R.
  eng-74 also - the briefing card on the 1h structure (the owner's reference card, Binance data): 1h swings, equal
  highs / lows, 1h FVG / OB / breaker / BPR and the day's extremes join the higher levels; zones ~1 1h-ATR thick
  (merged <= 1.5), 3 resistances / 2 supports, the 1h chart of 3 days, a 'what it is' line per zone
  (`briefing.describe`); a level wider than a 1h ATR becomes its edges + (ICT zones) its middle (CE / mean threshold) -
  capped from one side BTC's daily FVG vanished; tolerance <= 0.5 and stop buffer 0.5..1.0 1h ATR (the pierce model's
  global figures put gold's stop 3 ATR away; sources: 0.3-1.0 ATR); a stop is pushed beyond ONE adjacent zone only;
  overlapping zones inside one another are absorbed, never inverted; inside a zone the scenarios also include the
  bounce at the nearest support / the fade at the nearest resistance; `/api/briefing_card?symbol=` renders a card
  locally without posting it.
  eng-74 also: only the ICT zones (FVG / OB / breaker / BPR) wider than a 1h ATR become edges + CE; a swing or a
  previous-period extreme stays a band of a 1h ATR from its wick (was split too: 'минимум вчера (верх)'); the
  anomaly alert names the liquidated side and its sum ('каскад: ликвидации лонгов $xM' - was 'распродажа / откуп')
  and the zone in words, 'в зоне' / 'у зоны' by where the events were; the zone alerts carry the zone's description.
- eng-75 (2026-10-08, the owner: "you don't understand what support and resistance are and what forms them"; web:
  Fidelity / Investing.com / Capital.com / Dukascopy / Wealthsimple / FTMO): `sr.py` - S/R zones from where price
  TURNED: clusters of 1h / 4h / daily fractal pivots that moved >= 1 ATR of their timeframe away, the band the
  pivots' wicks, strength = sum of tf weight x reaction x volume x recency + 0.5 per later rejection (a candle that
  came from outside, wicked in and closed back out; consecutive ones = one episode), flip = swing highs AND lows in
  one cluster. The briefing's zones are these (`briefing.key_zones`); the map's constructs (PDH, FVG, VAL, opens,
  sessions) only name a zone they coincide with ('здесь же'). `research_sr.py` (VOID - the owner, 2026-10-08: wrong method - a 15m close back within 1h at the exact edge, no +- band in the zone's own timeframe ATR, no horizon by timeframe, no reaction size, placebos landing in other zones; the same holds for research/level_weights.md; redo before any conclusion) (research/sr_zones.md,
  40 coins x 12 months): NO class holds price better than placebo prices - all zones OR 0.94 [0.92..0.96], the
  strongest third 0.90, >= 3 touches 0.93, with a daily pivot 0.89, the same in both halves - the stronger the level
  the more often it breaks (Osler: stops beyond it accelerate the break). The card says so; the fade / bounce
  scenarios have no measured edge. Open: a pre-registered break-follow-through test (after a 15m close beyond a
  zone, a 1 ATR continuation more often than beyond a placebo?) before the breakout scenario is trusted.
