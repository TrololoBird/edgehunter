# Logic history eng-4 .. eng-76 (moved from CLAUDE.md on 2026-10-12, unchanged)

Each note: what changed, why, what was measured. The newest notes are at the end.

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
- **Edge is measured against the universe MEAN, not the median** (`journal.universe_return`, `stats.UniverseBaseline`, the dashboard, `research/scripts/research_edges.py`, `ml_eval.py`): on 6 months of 363 coins the average coin beat the median by +0.108% per 4h with NO signal (right-skewed returns; the same in every volatility tercile), so Edge against the median gave every long ~+0.11% and every short ~-0.11% - including the journal's automatic regime mutes / confirmation promotions, which therefore leaned to muting shorts. The P(edge) label stays 'beat the median' (balanced 50/50). Against the mean, no archive-testable setup has a significant 4h Edge (all q >= 0.17; the best, BULL F, +0.10% [+0.03..+0.17], is below the ~0.20% round-trip cost): `research/edges_6m.md`. P(edge) out of sample: AUC 0.53, log-loss skill +0.3%, the top-ranked rows do not have a larger Edge (`research/ml_eval_6m.txt`) - shadow only, as before.
- **Archive research results** (card replays, exit rules, meta-labeling, higher timeframes, positioning, EQH / EQL, channels, pumps, the scenario card's probability model): the `research-findings` skill. Bottom line: no archive-testable setup, exit rule or model has an edge net of costs; gross R of the cards is ~0. `sweep` / `breakout` and the phase / momentum setups in `disabled_setups` are off for that reason. Load the skill before proposing or judging any strategy, filter, exit rule or model.
- `scenarios.py` (scenario card on every coin panel) shows the random-walk geometric probability and the measured trigger rates, information only; `pumps.py` shows live small-cap pumps / dumps with each rule's measured verdict (details in the skill).
- **Live verdict (eng-10, 2026-09-30)**: every strategy makes cards again (the archive cannot replay the live-only confirmations, liquidations, books and other venues, and a disabled strategy never produced a card, so it was never measured live); archive losers carry `archive_negative` (the «архив −» mark). Pre-registered, not to be changed after the fact: a strategy is judged once its passed entries (`vetoed` NULL, logic_version >= eng-10) span >= 30 independent 4h clusters: KEEP if mean net R > 0 and the 90% cluster-bootstrap interval's lower bound > -0.05R; otherwise its code is DELETED (detector, strategy class, config, tests). The same for the `conf_n` split (eng-6 live, 2.5 days: 0 confirmations -0.44R on 67 entries .. 4 of 4 +0.16R on 11): a confirmation count becomes a required filter only if it passes the same rule.
- `tests/test_audit.py`: regression checks of these bugs; a freqtrade-style truncation test shows indicators and phase scores do not look ahead.
- Not changed (decisions for the owner): the "phase" letters are not Wyckoff's phases (B = a phase-C spring, E = a phase-A selling climax, F = phase-E markup; renaming changes journal keys); ATR stays a simple mean.

### Live-first rework eng-8 .. eng-16 (2026-09-30)
- **Replay honesty (eng-8)**: a stop is filled at the candle's open when it gapped through (`levels.stop_fill`); slippage grows as liquidity falls (`levels.slippage_bps`: 5 bps at >= $500M 24h volume, x sqrt($500M / volume), cap 25 bps; the planner's `geometry.cost_of` and the archive scripts keep 5 bps); `oi_accum` reads OI in coins; every entry journals the raw 1h OI change (`confirms._oi_1h`).
- **Every strategy makes cards again (eng-10)**: a disabled strategy never produced a card, so its entries, confirmations and live-only inputs were never measured. Archive losers carry `archive_negative` («архив −»); the pre-registered **Live verdict** rule (Journal and stats) keeps or deletes each strategy.
- **Stops from structure, not ATR constants (eng-11 .. eng-15)**: the ported systems' fixed % / ATR exits (Third Eye's 1% stop sat inside one 15m candle on SUI) are replaced by the map: the stop beyond the nearest structure (`geometry.structure_stop`), targets at the next levels; the fixed rule only without references. The buffer beyond a level is MEASURED (`research/scripts/research_overshoot.py` -> `models/overshoot.json`, `research/overshoot.md`: p80 of how far price pierces a level of that kind on that coin before a 15m close back within 1h; 80 coins x 12 months, stable across halves 82-83%; swing 15m 0.63%, 1h 0.77%, equal 0.61%, previous day 0.92%, round 1.36%; per coin 0.15-1.40%) - no minimum / maximum in ATR: a stop that does not pay is `low_rr`, and the card shows why («стоп далеко»: stop %, TP1 %, the entry's distance from the zone edge, `veto_notes`). Stops are no longer pushed beyond ESTIMATED liquidations (live eng-6: the widest stops, -0.16R, 0 of 22 stopped trades reached TP1). ICT (`strategies/ict.py`): the stop beyond the protected swing (the last pivot that broke structure); premium / discount journaled as `range_pos` (0 = the cheapest end of the 48h range for the direction) with a stats split.
- **Methods aligned with their sources (eng-16)**: Wyckoff spring / UTAD of a 1h trading range after a trend's stop (`strategies/wyckoff_range.py`, setups SPRING / UTAD; entry on the test), the 15m B / C scores off (`legacy_wyckoff_bc`), BULL E (buying the climax) journaled without a card, honest names for A / C / F / D on the dashboard; sweep entry = retrace into the post-sweep displacement FVG (`trigger='fvg'`); breakout = the Turtles' 20-day Donchian on 1h with an acceptance close (`breakout_donchian`; the 15m `breakout_at_close` stays for pretraining / research); auction POC from 15m candles; smt in ICT's kill zones 02-05 / 07-10 NY with the more correlated of BTC / ETH (`structure.pick_correlate`); supply / demand = Seiden's base (1-6 boring candles), a limit at the proximal line, first touch only (`trigger='touch'`, `single_touch`).
- **Data recorder** and **BingX demo execution** (`executor.py`, VST sandbox forced, every ENTRY card at 1% of a $10k base capped at $4k notional, stop + three reduce-only targets, results in `demo_trades.db`; the key in config.local.toml).

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
`daily_bias`, vetoes sweeps against it (`against_bias`). `research/scripts/research_maniac.py` still calls the deleted
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
  exit, units) - `stats.card_results_table`; `research/scripts/research_turtle.py` replays the Turtles on daily archive candles.
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
- eng-52 (Compass review, `research/compass_check.md`, `research/scripts/research_compass.py`): journal features `prem_1h` / `prem_z`
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
  research/scripts/research_level_weights.py: swings / equal / previous-day / round levels hold price LESS often than placebo prices
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
  `research/scripts/research_pools.py` (pre-registered): Turtles / Connors trades on the daily archive by coin attributes (market volume
  rank, ATR %, Choppiness, ER, beta / corr to BTC) -> research/pools.md.
- eng-59 B9 (archive replay of the live lifecycle): the loop-side detectors moved from scanner.Scanner to
  `strategies/loopside.py` (`LoopDetectors`: pump, Silver Bullet, PO3, Turtles, ORB, OI signal, dump bounce, Connors)
  so `replay.py` runs the same code: the live `SignalBook` stepped once a minute over the Binance archive (1m futures /
  spot, 5-minute OI metrics, funding, daily candles), fed by `build_maps` (maps + 15m-close events), `LiveDetector`,
  `LoopDetectors`, the scorer's phases / Tier-0, confirmations from Binance's own 1m flows / OI; every entry (passed and
  vetoed) also replayed by `levels.simulate`; outputs data/replay/<run>/group_NN/{cards,entries}.parquet (groups of
  `--group` coins share one book). Not in the archive: liquidations (no cascade setups), books, other venues,
  Hyperliquid, footprint. `research/scripts/research_replay_report.py` -> research/replay.md (cards' net R, exits by nature, vetoes).
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
  impact). research/scripts/research_indicator_confirms.py (pre-registered; research/indicator_confirms.md): 208 strategy x rule x
  timeframe cells on the archive replay, 0 pass BH q 0.10 - no classic indicator turns an entry set positive.
  Order books rebuilt (depth.py): a local book per hot coin from the @depth@500ms diff stream + a 1000-level snapshot
  with Binance's sequence rules (the 500-level REST snapshots every 60s covered BTC +-0.07%, ETH +-0.2%); every
  decrease split into filled (aggTrades at the price) / pulled; heat snapshots of the whole book every 30s; walls
  stand 30s within +-2%; bands drop when their pull turnover is > 3x the side's median; `slippage_bps` walks the
  book. 'book' left zones.STRUCTURE_KINDS (no stop on pullable orders) and weighs 1.0; the chart's density lines
  are the bot's bands (the looser second definition and the dead `LiveDetector.levels_of` were removed).
- eng-62 (2026-10-05, the owner: adapt the classic methods to crypto futures by search and test them on the demo):
  research/scripts/research_optimize.py simulates every replayed entry (16 550, 40 coins x 12 months, 5m paths) under 524 position
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
- eng-63 (2026-10-05): regime switch (research/scripts/research_optimize_regime.py, pre-registered): BTC 4h ADX >= 25 trend / range x
  ATR above / below its 125-candle median -> trend_hv / trend_lv / range_hv / range_lv (strategies/profiles.regime_labels,
  the same function live via fetcher `_regime` from BTC's h4). Per strategy x regime one filter at most, positive in
  both training halves, validated once: ON breakout trend_hv (+0.42R [+0.18] on 105 - not applied live, the Turtles keep
  their own exits), pump trend_lv / range_hv / range_lv and supply_demand trend_hv (1-11 validation trades: candidates).
  Continuation failed in every regime (decay, not a regime artifact). models/profiles_regime.json: a strategy listed
  there trades only in its ON regimes (`vetoed='regime_off'`), with that regime's profile; others keep
  models/profiles.json. replay.py switches the profiles off (it measures the methods' own plans). Profile filters are
  skipped (logged) when the indicator panel is missing. docs/CLOUD_OPTIMIZE.md: the 120 coins x 24 months job
  (research/scripts/research_replay_summary.py, OPT_TRAIN_MONTHS / OPT_PREFIX / OPT_PROFILES).
- eng-64 (2026-10-05, web-checked: the OI price/OI quadrants - Bookmap, Traders Log; Trader Dale's level + order-flow
  timing): `oi` is a confirmation of every method by its type (strategies/confirm.OI_EXPECT: breaks / continuations /
  pump / OI signal / trendline / cup expect OI rising - new positions; fades - Bollinger W/M, market_profile, Seiden,
  Connors, sweep, wyckoff - expect it falling: the move faded was positions closing); journaled, required only when
  proven. The order-flow entry in the zone (`SignalBook._flow_entry`, Dale: absorption / imbalance / finished auction
  at the level + the delta since the zone's extreme turned the trade's way, + OI as the type expects) is journaled as
  a vetoed entry `flow_entry` of the same card (once per card, only in a scan where the method's own trigger did not
  enter) so the journal compares the two entries. Hot set: free order-book slots go to coins with a setup in the last
  3h, then the pinned coins (the close-entry systems had no synced book at their entry; 13 of 25 slots were used).
- eng-65 (2026-10-05): research/scripts/research_overlays.py (pre-registered; research/overlays.md): early exits over the method's own
  plan - noprog_H (no +0.3R within H hours), struct (a 15m close at -0.5R), btc_K (BTC K% against within 15 min,
  altcoins) - and the alts-vs-BTC filter (the universe's median 4h return beat BTC's the trade's way). Adopted (train
  lower bound > 0 and validation > 0), all small (+0.01..+0.16R; no strategy turns positive): connors struct + alts_with,
  trendline noprog_2, market_profile btc_0.7, sweep / supply_demand noprog_4+btc_1.0 (models/exit_overlays.json;
  SignalBook._overlay_exit at each final 1m close, CLOSED at the close; the filter vetoes `alts_vs_btc`). They apply to
  the method's own plan only, so the candidate profiles that FAILED validation left models/profiles.json (bollinger,
  trendline, market_profile, continuation, connors). research/scripts/research_htf_filter.py (the owner's "the higher timeframe
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
  (a broken line signals a change of trend) are exempt. Journaled `_bias` (coin, btc, components). research/scripts/research_bias.py
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
  unchanged. research/scripts/research_entry_edge.py / research/scripts/research_geometry_audit.py (research/entry_edge.md, geometry_audit.md): on the
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
  (WTI, pinned). research/scripts/research_sessions.py -> research/sessions_leaders.md: the opens' moves vs other times and whether a
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
  sessions) only name a zone they coincide with ('здесь же'). `research/scripts/research_sr.py` (VOID - the owner, 2026-10-08: wrong method - a 15m close back within 1h at the exact edge, no +- band in the zone's own timeframe ATR, no horizon by timeframe, no reaction size, placebos landing in other zones; the same holds for research/level_weights.md; redo before any conclusion) (research/sr_zones.md,
  40 coins x 12 months): NO class holds price better than placebo prices - all zones OR 0.94 [0.92..0.96], the
  strongest third 0.90, >= 3 touches 0.93, with a daily pivot 0.89, the same in both halves - the stronger the level
  the more often it breaks (Osler: stops beyond it accelerate the break). The card says so; the fade / bounce
  scenarios have no measured edge. Open: a pre-registered break-follow-through test (after a 15m close beyond a
  zone, a 1 ATR continuation more often than beyond a placebo?) before the breakout scenario is trusted.
- eng-76 (merge 2026-10-12: the cloud session's "eng-73" of 2026-10-11, renamed - the local eng-73..75 are other changes; the cloud audit's fixes, research/talib_check.md / eng72_vs_eng59.md): indicators match TA-Lib -
  CCI's mean deviation from the CURRENT window's mean (Lambert; cci_extreme read differently in 11% of cases), MFI
  without flow on an unchanged typical price (Quong & Soudack), `ind_panel.ema` seeded with the SMA of its first n
  values (EMA200 was up to 0.4% off on 499 candles; also bias' weekly EMA20 / daily EMA50), the 15m frame's ADX with
  Wilder's / TA-Lib's seeding (`indicators.py`; on the live 99-candle frame it was up to 7% off - the Holy Grail's
  ADX > 30). replay.py now gives the SignalBook the plans' own-timeframe ATR (`tf_atr_of`, as Scanner._tf_atrs): the
  eng-72 replay ran without it, so eng-67 / eng-69's stop floors / zone buffers / target spacing in the 1h / 4h /
  daily ATR were not applied there (e.g. trendline's stops at 0.66 1h ATR) - the eng-72 numbers understate the new
  geometry and are re-measured on eng-76. deploy/install.sh: uv and Python 3.14 outside root's home (the pump user
  could not read /root: the venv step failed).
  Also: /api/briefing_card is local only too. research/sr_zones.md and research/level_weights.md are VOID (see eng-75).
- eng-76 follow-ups (2026-10-12, the VPS move; no signal-logic change): polars 2.0 (the two joins whose row order the
  code reads keep `maintain_order='left'`: fetcher's OI join, scorer.score_closed's `.last()`), requirements.txt with
  upper bounds + requirements-dev.txt (ccxt pins uvloop / orjson / multidict / certifi exactly); Telegram forum
  group with topics (notifier topics briefing / signals / alerts / demo / service; service only to the group, the
  rest also to the channel); the dashboard over wss behind Caddy (h1/h2: a VPN holds UDP 443); files the bot
  rewrites out of git; the briefing no longer prints the void "zones hold no better than random" verdict; the dead
  BingX `recvWindow` option removed (ccxt's sign never sent it); CLAUDE.md cut to the core, details moved to
  docs/ARCHITECTURE.md and this file.
- eng-77 (2026-10-12, checked against Curtis Faith's "The Original Turtle Trading Rules", PDF text): the Turtles'
  channel exit fires when price goes BEYOND the 10 / 20-day low / high (was: on touching it); a pyramid unit is booked
  at the price it was added at (Faith: the 1/2 N interval runs from the previous unit's actual fill - after a slipped
  add the next one is further out; was the theoretical previous unit + 1/2 N). Checked and kept: N = (19 x PDN + TR)
  / 20 seeded with the 20-day mean TR, stops 2N from the newest unit, exits intraday, S1 skip after a winning S1
  breakout, 1/2 N spacing (Faith; Covel's book says 1 N). Bollinger W / M (entry on the close beyond the middle peak
  = StockCharts / CFI, the opposite band as target), Connors (close beyond SMA5 = StockCharts), ORB / VA80 session
  exits checked against secondary sources: unchanged.
- eng-78 (2026-10-12, the timeframe audit): the Turtles and Connors carry their structure timeframe '1d' (daily
  channels / daily RSI(2) + SMA5; were '4h': their own-timeframe ATR for the stop floor was the 4h one - the 2N / 3
  daily-ATR stops were above both, so no stop moved); the dashboard's scenario card gets the daily candles of every
  coin (md.d1) when the card-coin history (htf_1d) is absent - 21 of 73 coins had no scenario because their 8-day 1h
  window held no level above the price; the chart shows only zones of its own timeframe and higher (as
  geometry.htf_zones), daily / weekly cards open on 1h candles. Checked and kept: ORB / VA80 stay '15m' (their
  structure is the day, but a '1d' plan would floor the stop at a daily ATR - against Crabel's opposite level),
  Bollinger W / M 15m with its 15m band exit, TTL_FACTOR has no '1d' (every daily method has its own ttl_key).
- eng-79 (2026-10-12, the timeframe audit on the laptop journal's eng-67+ entries): (1) `geometry._zone_rank` - a
  zone qualifies for a plan of timeframe tf when ONE of its levels is of tf or higher; untimed kinds are all-timeframe
  only when they are daily-or-longer references (pdhl, pmhl, year, open, range, poc, va); intraday untimed kinds
  (vwap, round, book, liq_est / liq_hit / liq_hl, equal, hvn, lvn, wall) rank as 15m. Before, any untimed kind made a
  zone valid everywhere: "FVG 15m bear · VWAP day · 15m high · OB 15m bear" was TP1 of a 4h SD DEMAND (CRV), 13 such
  targets in 2 days (AUCTION 1h, SD 4h, SPRING 1h, DUMP BOUNCE 1h). Open: the 'poc' / 'va' kinds also carry the
  rolling 24h profile (labels 'POC 24h' / 'VAH 24h') - one kind for daily and intraday profiles. (2) trendline: the
  stop beyond the last confirmed 1h pivot (the line's own timeframe) + 0.1 x ATR(1h); was 15m pivots + 0.1 x ATR(15m)
  (the cloud replay: median 0.66 1h ATR, 79% inside an hour's range). (3) The chart draws zones as boxes from the candle
  that made them (Zone.ts = the earliest level's candle) and hides zones below its timeframe by the same rank.
- eng-80 (2026-10-12, the book / flow / liquidation audit against the venues' docs): the local book's sync matched
  Binance's procedure (buffer, u < lastUpdateId dropped, U <= lastUpdateId <= u, pu chain); but the 1000-level REST
  snapshot covers only ~+-0.07% of BTC and the book beyond it knows only levels that CHANGED since the sync, so a large
  resting order far from the price - what walls / bands look for - never appeared: heat snapshots, walls and bands now
  use only the snapshot's covered range (`cov_lo` .. `cov_hi`, sent to the page as heatmap.cov), and a book whose mid
  left that range is re-synced (at most every 5 min). Liquidation sides re-checked: Binance forceOrder S = the
  liquidation ORDER side (SELL = a long closed; the feed is the latest liquidation per symbol per second - Binance
  undercounts), Bybit allLiquidation S = the POSITION side (Buy = a long liquidated, complete), OKX posSide long = a
  long liquidated: all three as coded. Dashboard: the 1h chart groups closed 15m candles into hours until the 1h
  history arrives after a start.
- eng-81 (2026-10-12, the VPS link: ~180 MB/s, 33 ms to Binance - the laptop's ~70 KB/s per socket had cut the
  whole-market streams): `!markPrice@arr@1s` (mark / index / funding of every contract each second; the premium
  history keeps its 30s spacing) and `!miniTicker@arr` (every 24h volume) are streams again (`CONFIG.ws.market_arrays`),
  the REST premiumIndex / ticker loop runs only while they are quiet (> 15 s); order books for 60 hot coins (VPS
  config). Dashboard: a new coin starts from an empty auto-scaled chart (the previous coin's price range stayed: TAO
  ~300 -> NEAR / ETH candles off-screen); the chart draws at most 4 zones of strength >= 2 per side within the candles'
  range (+50%), «все уровни» for up to 12 incl. weak ones; the 2 largest densities per side; no automatic window
  Fibonacci grid (only the continuation card's own); box labels never overlap.
- eng-82 (2026-10-12): ORB (Crabel: buy / sell STOP orders resting at the day's open +- Stretch - his rule
  re-checked against secondary sources of the 1990 book) checks the touch on the live trade price each scan, not only
  at a final minute's close: INJ entered 0.97% beyond its level on a 2.8% stop (the minute-close detection was up to a
  minute late on an RVOL-11 impulse). The demo's resting BingX stop-entry (TRIGGER_MARKET) was verified on VST but is
  not wired in yet (two per coin a day, the gates evaluated before the touch, adopting the fill into the card).
  research/scripts/research_algo_whales.py (pre-registered; research/algo_whales.md, the laptop journal: 3.3k ALGO / 1k WHALES
  anomalies): the coin's return from the event's price minus the mean of every coin, vs the same coin and hour on a
  random other day - no label continues or reverses in both halves (ALGO BUY 4h -0.47% [-0.86..-0.09] overall, not in
  the newer half); the raw "reversal after 4h" was the market's own move.
- FREEZE (the owner, 2026-10-12): no signal-logic change and no bot restart until Wednesday 2026-10-14 13:00 MSK
  (10:00 UTC), except a fix of a crash that loses data or demo orders; ideas go to docs/PLAN_server_eng76.md.
- eng-129 (2026-10-15, the owner's P0 + P1 order): demo executor - the stop rests until the position is flat (_close
  cancelled everything first and left it naked when the close failed / hit 102202), a 5-min stop guard re-places a
  missing stop (or closes when the price is beyond it), trailed stops persisted, _refinalize bounded by the close time
  (it mixed the next trades' exits in), risk_usd = stop distance + costs (R = -1 at the stop, was -1.1..-1.3), the
  fill price from fetch_order when the reply has none, one fill lookup under the lock (was up to 20s), day limits
  >= 1e5 treated as off (LIMIT 1000000 per entry), UNTRACKED USD in the daily summary, Telegram alerts on NO_STOP /
  LATE_FILL / UNTRACKED / a failed close. Signals: 'no plan' expiries journal the strategy's reason; sweeps no longer
  take round numbers as the pool (sweep_round_pools, 39 of 77 INVALIDs eng-125..128). Not changed: the sweep's CE
  entry - its MISSED cards were IN the zone, the FVG trigger did not form before TP1.
- eng-130 (2026-10-15, the owner's order after the source check of every strategy's target): supply_demand targets
  the opposing fresh 4h supply / demand zone's proximal line (Seiden: "the distance between our supply and target
  (T1: Demand)"; was the map's opposite liquidity - breakers, equal lows, the day open), no opposing zone = no trade
  (maniac.sd_opposing); cup_handle TP1 = breakout + 61% of the right-lip depth (Bulkowski's measure rule as his site
  gives it now, 913 bullish cups; was half the height 'met 76%'), TP2 the full depth (strategies.cup_target_share);
  po3 / Silver Bullet: no source target ahead (the Asian range's other side / the day's draw) = no trade (was the
  map's nearest liquidity).
- eng-131 (2026-10-15): a card without a plan expires only once its coin's data is in (15m frame, 1h / 4h / daily ATR,
  1m candles) and the book has run 10 minutes (SignalBook._plan_data_ready); before, every restart expired 14-59
  restored cards within 5 minutes as 'no plan' (51 at 13:40 on 15.10) - they had no history yet, not no setup. A coin
  whose data never comes expires at its watch TTL.
- eng-132 (2026-10-15, the owner's release plan; decisions delegated to the session): 
  A, demo safety: a position is flat only after two empty reads (reconcile passes a minute apart, then a 2s re-read
  before cancel_all) - one glitchy fetch_positions at 10:04 took the stops of HYPE / UNI / XPL and close_untracked
  then booked the same positions again as UNTRACKED (ids 110-112 = 55-57, $49 twice; deploy/mark_dup_untracked.py marks
  them, usd_without_r skips them); a position found within 15 min of its finalize goes back to tracking instead of
  being dumped; TradFi contracts (XAU / XAG / CL / BZ: BingX 101414) are NO_MARKET; finish_levels sorts the targets
  after the pierce pull. B, data: PUMP START's 24h high from the 1h history (the 1m history holds ~10h: every 10h-old
  high looked 'fresh'); the cup is skipped, not measured on a cut window, when the history before the left rim is
  shorter than 2x the cup; every history gate that stops a strategy writes history_skips (once a coin / strategy / day);
  the Binance venue status carries liq_sampled (forceOrder = at most one liquidation a second). B2 NOT done: 125 is
  Bollinger's six months of DAILY bars and he gives no intraday rule; comparing a 15m / 4h width with the daily
  minimum makes every bar a squeeze. D, analytics: the replay's slippage takes the symbol's measured book slippage
  (levels.simulate / fill_price, replay, stats.card_r_net); the card table shows stops out in profit (Trail) and R per
  unit. D2 / D3 (expectancy by thirds, p over OPEN entries) change the entry veto, not just the reports: left for a
  pre-registered study.
- eng-134 (2026-10-16, owner's go on external data; logic_version unchanged, shadow only): `kimchi_prem` - Upbit KRW
  premium % over the Binance futures price (Upbit's own KRW-USDT as the FX; NULL when the coin's last Upbit trade is
  > 3 min old or |prem| > 30%: KRW-EDGE is another coin than EDGEUSDT); `us_session` stats its calendar file once a
  minute (getmtime per card showed in watchdog stalls); `tools/coinglass_heatmap.py` - research downloader of
  CoinGlass's keyless order-book heatmap (undocumented endpoint, never a live input). CoinGecko: `/global` and sectors
  were already used; keyless offers nothing else needed.
- eng-136 (2026-10-16, branch fix/audit-2026-10-16, NOT deployed: needs the owner's yes) - fixes of the audit
  docs/audit_2026_10_16 (follow-up: docs/audit_2026_10_16_followup/FOLLOWUP.md, before / after in checks/):
  A06 a demo close is final only when the exit ORDERS' filled amounts (fetch_order) cover the position, never a partial
  result after 6h; S01/A16 candles carry base volume at index 7, VWAP = sum(quote)/sum(base), MFI / OBV on base;
  A04 resample returns complete buckets only; A03 SAR two-bar clamp; A12 SAR as of the managed minute; A08 Turtle
  channel / Bollinger band exits on every 1m candle; A10 the recorded exit fill for every open unit; A13 one card per
  coin / direction within a scan; A15 demo API newest 5000 rows, excluded reasons as stats; S10 no TP on no_tp plans;
  A02 Silver Bullet / PO3 search past a direction already fired; A18 dump bounce only after an exhaustion close (the
  eng-55 research measured the old rule: its +0.14R does not cover the new one); S04 spring test spread scaled by the
  spring's timeframe; S05 Seiden's 3:1 on TP1; S06 Bollinger's min_rr after the stop's padding; S11 the P&F count is a
  filler. keep_waiting_from eng-136 (detection / plans changed).
  Review of 6b771ba: a demo exit is priced and its fees taken from each exit ORDER (fetch_order: status closed,
  executedQty, avgPrice, commission), never from a fill list that may be partial; the 1m exit loop judges each minute
  on the Turtle channel / Bollinger band / EMA trail known at that minute (live and a batch after a restart decide the
  same); levels.resample_min_coverage 0.8: an inner bucket with minutes missing is kept only with its first and last
  minute and >= 80% of minutes, else dropped (counted on the Health line).
- eng-135 (2026-10-16, owner: "decide yourself, implement, update the UI"): exchange announcements in `event_risk.py`,
  keyless, every 2 minutes. Binance CMS catalogue 161 "Binance Will Delist A, B on <date>" (spot delisting; Alpha /
  Margin removals ignored) and Upbit "거래지원 종료" (delisting) / "유의 종목 지정" (warning list) now feed
  `event_risk`, so the eng-53 long veto covers them: Binance until the day after the delisting date, an Upbit delisting
  until its removal date (>= 14 days), an Upbit warning 14 days unless "유의 종목 지정 해제" lifts it; the veto is kept
  apart from the newest announcement (a later listing never clears it); Upbit's first_listed_at (edits move listed_at). Before, only the Monitoring Tag and the perpetual's deliveryDate did (the spot delisting of EPIC /
  QUICK on 2026-10-14 had no flag). Listings (Binance catalogue 48 "Will List", Upbit "KRW 마켓 ... 추가") are journal
  only: `news` / `news_age_h` (shadow; studies RockawayX / The TIE / Klein Labs: a listing effect fades in 1-2 days, often
  reverses) - a `pump` trigger from them needs a pre-registered archive test. Only bases of Binance USDT perpetuals;
  Upbit tickers may name another coin (a false veto costs a card). Dashboard: an "анонсы" item in the header (48h, ⚠ =
  longs vetoed) and the announcement / veto line in the coin drawer. Token unlocks: no free source (DefiLlama
  emissions 402, Tokenomist paid). logic_version eng-135; keep_waiting_from unchanged: the veto is checked at the
  trigger, so a waiting card is judged by the new rule anyway.
  Same release, dashboard: the BingX demo summary follows the period picker (it summed every trade since 11.10:
  -30.5R of which -35.4R came from 11-13.10, before the executor fixes of eng-129; since 14.10 +4.9R on 10 trades);
  the zone tooltip is absolute again (`#chart > div {position: relative}` outranked `.zone-tip`, the shown tip took
  layout space and the chart jumped under the cursor).

- **eng-139 (2026-10-17, audit Pump_Core_Audit_eng138 C01-C18)**: executor - add / restop re-check the trade under the
  lock (C01), an unreadable position after a timed-out entry is UNKNOWN with an alert, never "not opened" (C02), R:R to
  TP1 gated by the method's minimum before the blended check (C05); `_price_of` dates a kline by its stream event (C03);
  the entry minute's high / low come from its own trades only (C04); the time exit is checked per candle, so a later
  stop no longer outlives it (C07); a stop and a Turtle channel hit in one candle: the nearer one first (C06); Binance
  OI recorded natively (C08); `bars_4h` keeps taker / base volume (C09); MFI = typical price x base volume (C10);
  order-book drops queue per level (C11); the journal rejects a window with missing minutes (C12); hit rates keyed by
  `setup_key` - this re-activates the negative-expectancy veto, which was dead before (C13); fib extensions from the
  leg's start (C14); briefing scores signed R and skips scenarios already past TP1 (C15); pretrain buckets only full
  groups (C16); replay rank unknown in a restricted universe (C17); hot-symbol slots evicted by priority (C18).
- **eng-140 (2026-10-18, independent recheck of eng-139)**: a coin stays closed to new entries (market and limit) for 15 min
  after an entry whose outcome is UNKNOWN (C02); `hours_from` keeps the 15m candles' base volume (C09); the 1m outcome window
  must start exactly at the next full minute (C12); the entry-minute test also counts the Turtles' channel / Bollinger band
  as exit levels, a touched minute is 'ambiguous' (EXTRA_2); stats shows Ambig / Mean R low (EXTRA_1); demo rows with an
  unconfirmed entry fill are marked as estimates, also after a restart and after `_refinalize` (EXTRA_3).

**eng-140 (data-to-signal audit D01-D15, 2026-10-18)** - the same version as the recheck fixes above. D01/D11: venue OI / funding
keep the exchange's event time (older-than-stored updates ignored) and the native OI unit (`native_oi`). D02: a depth book
is fresh only if its event time is young too. D03: Hyperliquid positions - a refresh where every request failed keeps
the last snapshot (with its real age); readers ignore a snapshot older than 6 refresh periods. D04/D14: the context
signature carries the last h1/h4/d1/w1 timestamps; BB Method I / Supply-Demand / Cup & Handle run on "a new bar since the last
pass" (`structure.new_bar`), not only at `cut % period == 0`. D06: `zones.imbalances` skips FVGs across missing candles. D05:
`Zone.parts` keeps (kind, price, lo, hi, swept) of every merged level; `htf_zones` trims a zone to the edges of the levels
that qualify for the plan's timeframe. D07: `join_asof` tolerance 2 candles (a stale futures column becomes null). D08: `rvol_1m` /
`minute_usd` use the wall-clock minute (a kline opened 90s ago is not the current minute). D09/D12: liquidity targets are
the swing's extreme (the wick), and a swing a later wick took (`RawLevel.swept`) is no untaken pool. D10: a minute of an
already finalized 15m bucket is not re-added. D13: a venue's flow ring counts for a confirmation only if it was recording
since the window began (`first_sec`). D15: 4h candles keep the base volume (8th field). Not measured live yet.

**eng-140 (external-source recheck E01-E08)**: E01 Value Area: two equal neighbouring TPO rows enter together (Sierra). E02: observed-liquidation
levels made mostly of Bybit / OKX events (bankruptcy price) are labelled "(bankruptcy px)". E03: the ORB VWAP veto uses quote / base. E04: `s1_state`
- a day through the 2N stop AND a profitable channel exit (no opening gap past the stop) is 'ambiguous', which blocks the next S1. E05/E06:
one RSI convention (flat = 50, no absolute floor: scale-invariant) and TA-Lib's ADX seed (`ind_panel.adx_talib`) shared by the panel and `regime.adx`
(26.08, was 23.79). E07: Bybit both-sides OI fallback halved. E08: the ORB contract is the closed minute (documented; the tick args stay unread).
Review notes: `htf_zones` trimming also moves the structure stops of 1h+ plans to the qualifying levels' edges; liquidity targets sit exactly on the
swing's extreme (no buffer rule yet); `_ltf_prices` knows both prices of a zone. A stale HL snapshot reads as no positions (0), not unknown.

**eng-141 (business trading-logic audit B01-B11, H01, F01)**: B01 `executor.on_add` confirms the add by the exchange's own position (size and
average price before/after, a client id, a lost reply resolved by the position, partial fills recorded as filled); B02 `_dedupe_stops` compares the
stops' total quantity with the actual position and re-places the stop when it covers less. B03: a waiting card ends MISSED when a final 1m high/low
reached TP1 since the last check (`SignalBook._tp1_since`, `tp_ms`; only cards of eng-141+). B04: `fetch_candidates` skips markets with
`active=False` or `info.status != TRADING`. B05: trading messages (`Notifier.send`) take the send lock before briefings (bounded 20s wait), failed
deliveries (5xx / 429 / network) go to `notify_outbox.json` and are retried for 15 min, a late one carries a "delivered late" note; the outbox
survives a restart (`Notifier.resume`). B06: NFP 2026-11-06 added; `macro_calendar.coverage` puts "macro veto degraded" into the Health line when the weekly
feed is lost/stale (6h) or the hand list ended. B07/B08 are conventions, documented only: Turtle units have their own budget (not one portfolio limit);
BingX stops trigger on MARK_PRICE while the card judges Binance trades, so the two can end at different minutes. B09: missing 1m candles inside a trade
are bridged by a candle with the certain range (last close -> next open), so a stop between them is taken. B10: a `no_stop` plan (Connors) is announced
as "стопа нет", `sl` is only the R unit. B11: `VenueFlow.gaps` records stretches of >45s without any write; a confirmation window crossing one (or ending
more than 45s after the last write) does not count that venue. H01: `Scanner.stop` also cancels `_context_task` and the background tasks. F01: the
UNKNOWN-entry coin hold survives a restart (`demo_unknown.json`). Not done: per-coin continuity (gaps are per venue), F07 (the ADD fallback price
is the Binance price; only used when the position gives no average). Not measured live yet.

## eng-141b (web analysis; no signal-logic change)
- New tab "Аналитика": the pinned coins (`CONFIG.exchange.pinned_bases` in the universe) always, plus a ticker box for any
  Binance USDT perpetual (`/api/pinned`, `/api/analysis`). `Briefing.analyze` is pure (restores `context`, posts nothing):
  zones (`key_zones` with a `src` override), higher-timeframe bias, the briefing plan's long / short scenarios with R:R and
  a mechanical checklist (bias, R:R, entry distance in 1h ATR, macro, the bot's own cards). A coin outside the universe is
  light: REST candles only (`fetcher.light_candles`, cached 5 min, <= 12 loads a minute, `1000`-prefixed names resolved),
  labelled "только свечи". The verdict is a rule list, not advice.
- `Briefing.outcomes` tallies the saved briefings' scenarios (TP1 / stop / open / cancelled / no entry) per watched coin;
  `_score_record` is the shared scorer. Week sample (60 briefings, BTC/ETH/XAU): long 4 TP1 / 10 stops, short 6 TP1 / 0 stops
  in a bearish week - too small and correlated for any rule change.
- Silent briefing records for every pinned coin (`_save`, `silent: true`; posts still BTC/ETH/XAU), `snapshot_outcomes` at the 23:30 recap -> data/briefing_outcomes.jsonl (14-day tally per coin), `outcomes_total` on the analysis tab.
- Loop stalls (319 'Event loop blocked' in 24 h, 1-3 s, victims: polars/numpy calls waiting for the GIL): the panel prewarm thread ran the pure-Python minute->15m/1h `resample` for each direction every 20 s; now cached per (coin, tf, minute ring, bucket) in `fetcher._RESAMPLE_CACHE`. Same results.

## eng-142 (external audit 2026-10-18 "edgehunter recommendations eng141"; branch eng-142-audit)
Base: the live tree's uncommitted audit-2026-10-18 fixes (commit d021a9e, running since the 18.10 17:57 restart) + the report's items:
- P0 gap fill: eng-141's B09 bridge candle (last close -> next open as a made-up bar) is removed. Reproduced: long entry 100 / SL 99,
  close 100, hole, next open 95 -> filled 99; now 95 (the first observed price). A level between the two ends lies beyond the next open,
  so the real minute catches it; the hole stays flagged (`plan['data_gaps']`, "[data gap ...]" in the finish reason).
- P1 leg timeframe: `find_impulse` no longer re-measures a 1h / 4h leg as a 15m one (15m ATR, 5m trigger) when the higher-timeframe ATR
  is missing - it returns None (no plan, the card waits). Reproduced on a 7.5h leg: no 1h -> 15m / 5m / ATR 1, 1h -> 1h / 15m / ATR 2.
  Tests now feed the fixture's 1h candles (`conftest.h1_of`); the lifecycle tests use 15m trigger bars (the fixture leg is 6h = 1h).
- P1 displacement / BOS: three rows count only as three consecutive candles of the leg's timeframe (`leg._adjacent`). Reproduced:
  timestamps [0, 15m, 45m] passed as an FVG.
- P1 outbox: a card event carries card / event / seq; a retry drops an ENTRY whose trade is no longer open or whose price no longer pays
  the plan's minimum R:R to TP1 (`Scanner._entry_still_actionable`), and a RESTOP superseded by a newer event of the card.
- P1/P2 funding: charged per part of the position until it left (`TrackedSignal.part_ms` tp1 / tp2 / p1r, `SignalBook._parts_held`),
  each Turtle unit from its own add time and at its own price (was: the whole position to the last exit, every unit from the entry).
- cost_guard: the config text no longer calls it "the break-even formula" (a policy cap; costs > 1R can still have positive expectancy).
Not done (proposals, separate changes): the TP1 hit-rate veto as expectancy (P1 #5), obstacles / horizon diagnostics (P2 #7), sizing /
leverage assumptions in the UI (P2 #8), the stage-0 parameter-provenance table.

## eng-143 (the rest of the external audit 2026-10-18)
- P1 #5: the expectancy veto (`HIT_RATE`, the three-thirds model against a fixed stop) vetoes only plans that exit in thirds; a plan with
  half + trail, the +1R partial, the averaging add, Turtle units or no targets gets the estimate journaled (`exp_model`, `exp_note`
  "shadow: ...") but is not vetoed by it. `refresh_hit_rates` documents p as a descriptive per-target rate (correlated entries: the
  interval is optimistic). `coin_results` uses `card_r` only - the replay's all-out-at-TP1 `r_tp1` is no longer substituted for a
  missing result.
- P2 #7: `geometry.obstacle_before` - the nearest strong map zone between the entry and TP1, journaled (`obstacle_r` in R, `obstacle_src`)
  and named in the ENTRY message. Diagnostic only; targets and the reach filter unchanged.
- P2 #8: `webui.sizing_view` uses the geometry's costs (`cost_of` with the coin's volume and symbol); `max_leverage` is None when no
  leverage keeps the liquidation beyond the stop under the model (was floored to 1x), and the assumptions are shown.
- Stage 0: `docs/PARAMETER_PROVENANCE.md`.

## eng-128 (2026-10-15, 445fa83, recorded late)
- The data-mined profiles (eng-63) off: `config.optimized_profiles=False`, signal_book drops them (no source behind
  the mined cut-offs).

## eng-144 (2026-10-21) - the restart / audit package
- State: `scanner_state.json` is never written before it was loaded (a stop during start-up wrote an empty book over
  it, the demo then closed 11 positions as ORPHAN); a failed read keeps the file (`.bad` copy) and disables saving and
  orphan closes for that run.
- Demo: a position without a card is no longer closed at market - it ends on its BingX stop / targets (ORPHAN 30 trades
  -9.2R on 11-21.10). Connors gets a catastrophe stop 3 R units away (the SMA5 exit unchanged).
- Restored cards waiting for history expire by their watch TTL counted from the start-up (112 SWEEP cards expired in
  three restart bursts).
- OI BUILD off (5387 cards in 2.5 days, no entry, cancelled 105 SWEEP cards as the opposite setup).
- Turtle / Connors cards count and are capped by `crowd_max` (crowded signals -0.22R vs clean +0.01R; Turtle -11.6R).
- `leg.broke_structure`: no swing in reach is no break of structure (was True).
- Stats: the new logic_version separates every journal / demo statistic from the eng-143 rows.

## eng-145 (2026-10-22) - market-down gate, ORB on Parabolic SAR, demo off for losing families; docstring audit
Owner's order, from the live journal only (no archive research):
- `SignalBook._market_down`: no LONG entry while BTC and the universe median are both down over 4h AND 24h
  (`market_state` gains `mkt_1d` / `btc_1d`); a blocking reason `market_down`, not a shadow veto. The Turtles and
  Connors are exempt (their rules take no market filter).
- ORB: the fixed session-close exit replaced by Wilder's Parabolic SAR of 15m bars (`plan['sar']`, AF 0.02 step,
  start at the opening range's far side); `time_exit = 'fixed'` = no clock.
- `executor.demo_off_setups`: Bollinger (W / M, BB3), Market Profile (VA80, AUCTION), the Turtles' BREAKOUT and BB1
  keep their cards and journal but stop trading on the demo account.
- Docstrings / comments checked against the code (they described removed logic: resting limits instead of touch ->
  close, break-even / partials that are off since eng-111 / eng-123, 3R caps removed in eng-110); dead code deleted:
  `level.absorption_at`, `classic.orb_event`, `breakout.breakout_donchian`, the unreachable `['map', 1.0]` TP1
  branches of PO3 / Silver Bullet.

## eng-146 (2026-10-22) - fresh statistics; ORB back to the session close; 24h market gate; cluster cap 3
- The owner: old statistics are reset (the new logic_version starts the count); focus on the logic.
- ORB: the eng-145 Parabolic SAR exit reverted to Crabel's session-close exit (external research: Crabel's rules
  exit on the session; the SAR was ours, fitted to 35 trades).
- market_down: a long is blocked when BTC's and the universe median's 24h moves are both < 0 (eng-145 also
  required both 4h moves < 0, so every 4h bounce inside a falling day let longs through). Turtles / Connors exempt.
- crowd_max 6 -> 3 per direction: alts correlate 0.8-0.9 in falls, 6 positions at 1R were one ~5.6R bet (policy).

## eng-147 (2026-10-22) - stop / target geometry, blocking sweep filters, swept levels, honest MFE, chase cap, crowd ranking
Retrospective on the VPS journal eng-135..144 (52 entries, -11.42R, true MFE / MAE recomputed from Binance 1m klines).
The owner's decisions:
- Stop: past `stop_beyond`'s pool only +0.2 ATR (`levels.moved_pad_atr`), else the measured pierce capped at 0.5 ATR
  of the working timeframe (`pierce_cap_atr`; `geometry.capped_pad`, also the sweep stop).
- `trigger_overshoot` (blocking): the trigger close > 0.6 ATR past the zone's trade-side edge (11 entries, -7.00R);
  ORB / Turtles exempt. `zone_edge` / `trigger_over_atr` journaled.
- `min_rr_tp1_floor` 0 -> 1.0 (8 entries with TP1 < 1R: -4.74R). Fewer than 3 map targets: TP2 / TP3 are projected
  +1R past the previous one ('1R step', synthetic) instead of repeating the last level.
- SWEEP LOW / HIGH: against the bias / trend (`sweep_against_bias` / `sweep_against_trend`), premium / discount and
  `sweep_no_htf_poi` block (6 of 9 sweeps, -4.64R). Silver Bullet unchanged.
- Swept levels: PDH/PDL, PWH/PWL traded through since (today / this week) and PMH/PML through this month carry
  `swept`; zones whose pool / liquidity parts are all swept (incl. 1h+ swings flagged since audit D09) are skipped
  by `stop_beyond` and the liquidity targets. Methods with their own targets (own_targets / no_atr_steps) keep
  repeating them, no +1R steps.
  (The 365-day high / low cannot be swept inside its own window.)
- Journal: `mfe_r` / `mae_r` over 4h from the entry in R, direction-aware (`mfe_4h` stays raw).
- Executor `chase_limit`: a plan without targets is not opened when BingX ran > 0.5 N (Turtles) / 0.5 ATR past the
  signal price (`close_reason` CHASE_LIMIT).
- crowd_max: one pass's entries are held and entered best first: fewer shadow vetoes, higher 15-minute RVOL, then
  min(rr_tp1, 2.5) (2.0 without a TP1).
- VA80 / ORB notes: "out at the session's close" (the SAR text was stale).
Dropped on data: Bollinger W window / bridge, the VA80 stop, break-even after TP1.

## eng-148 (2026-10-23) - eng-147's unproven blocks back to shadow, no demo limits, stage-0 diagnostics
The plan: docs/PLAN_eng148.md (owner's yes to stages 0-3 on the VPS, one restart). Evidence: 9174 vetoed entries of
eng-135..144 lost -0.26R vs -0.22R entered; vetoed TP1 >= 1R lost MORE (-0.46R) than TP1 < 1R (-0.21R); the sweep
filters cut 1170 entries at -0.24R (cut and kept lose alike); the 0.6 ATR overshoot threshold was set in sample.
- Demo policy (the owner): `crowd_max = 0` (no direction limit; the pass's ranking is journaled as `crowd_pos`),
  `executor.cluster_entry_sec = 0`, `executor.demo_off_setups = ()`. Kept: one trade per coin (BingX netting) and the
  Turtles' own unit limits (their rules are not changed). Pump averaging into a loser is already gone (eng-91).
- Sweep: against_bias / against_trend / no_htf_poi / premium / discount are shadow vetoes again (as eng-107).
- `levels.min_rr_tp1_floor = 0` (the method's own minimums stay: Seiden 3:1, min_rr_on_tp1); `strat_class` journaled
  (trend / structure / mean_reversion) for a later floor by class.
- trigger_overshoot: journal-only (`trigger_over_atr`, `rr_trigger` net of costs, `cost_r`); the residual R:R at the
  trigger price is low_rr's own check (entry_levels at the trigger close), no separate veto.
- market_down: a shadow veto for reversal longs (SWEEP LOW, SILVER BULLET LONG, SPRING, FLUSH REVERSAL, SD DEMAND,
  VA80 / AUCTION LONG, BB W-BOTTOM), still blocking for impulse / breakout / trend longs.
- Journal (entry rows): `mfe_life_r` / `mae_life_r` (to the stop or the window's end), `mfe_n10_r` / `mae_n10_r`
  (10 15m bars), `post_stop_mfe_r` (15 15m bars after a stop), shadow time stop `time_stop` / `time_stop_r`
  (8 15m bars with MFE < 0.4R), `optimistic_fill` (a limit the first hour only touched); on the 8h window of every entry, relabelled over the life.
- stats.py: "eng-148 splits" - net R @TP1 weighted 1 / c_t over 15m x direction clusters, cluster-bootstrap p and BH q,
  by class / UTC hour / weekend / volume / crowd top 3 / time stop / limit fill / TP1 R:R.
Not in this batch (need new detectors or the archive): the ICT limit / 50-50 split, the two-contour stop, sweep
re-entry, ORB NR4/NR7, Wyckoff ST/BUEC, regime routing, BTC/ETH SMT, the BTC-EMA50 market_down variant, stage 4.

## eng-149 (2026-10-23) - the rest of plan eng-148 stages 0-3 as journal-only shadow (logic_version stays eng-148)
Trading is unchanged (no new veto, no demo change), so the evaluation window of eng-148 is kept. Every variant is a
vetoed entry row `variant_*` of the same card (never traded; journal dedup per card + reason) or a journal column.
- 3.1 ICT: on an armed sweep (MSS + FVG) resting limits at the CE (`variant_ce_limit`) and the gap's near edge
  (`variant_fvg_edge`), filled on the touch (`limit_entry` = 1), the stop set before the touch (no touch-bar wick),
  the row from the touch bar's open; stats reads the 50/50 split (edge + CE, one stop). stats pairs every variant with
  the card's own entry; p of the paired difference.
- 3.2 two contours: `two_stop_r` = out at the first UTC 15m close beyond the stop or the touch of stop + 0.7 ATR
  (`atr_entry`), vs `base_stop_r` = the plain stop, both to TP1 / 8h.
- 3.4 sweep second test: `retest_r` - back to the entry after >= 0.5R away with no 15m close beyond the zone's far edge
  (`zone_far`: the FVG's far side), the same stop / TP1.
- 3.5 ORB: `nr4` / `nr7` / `inside_day` on every row. The shadow 13:30 UTC open was dropped after review: as a card it
  took the (symbol, ORB UP/DOWN) key and its 30-min cooldown blocked live ORBs; 00:00 UTC is the Asia session already
  (Tokyo 09:00). It needs a journal path outside cards. `hold8_r` = no-target systems held 8h, stop on the touch.
- 3.6 Wyckoff: `variant_st_stop` - the same entry with the stop beyond the TEST's extreme + 0.25 ATR (heuristic pad),
  only where tighter than the live stop.
- 3.7 / 0.4 regime: `atr_ratio` (1h ATR14 / its 100h mean), `vol_regime` climax >= 1.8 / compression <= 0.7 / trend
  (ER14 >= 0.4) / range - heuristic cuts, a split, not a rule.
- 3.8 `smt_majors` (BTC vs ETH new 24h low / high on closed 1h: +1 / -1 / 0). 2.4 `btc_below_ema50_4h`,
  `liq_cascade_2h` (2h long liquidations / their 2h mean over the 22h before), `mkt_down_alt` (either; cascade >= 3).
- 0.3 stats.py funnel by strategy; variants table on the same cards; the new labels in the eng-148 splits.
- All shadow exits on the first 8h of every entry (no survivor bias from the life relabel). rs_btc (0.7) existed.
Left by design: stage 4 (each item its own yes after 100+ cluster-independent trades), stage 5 (cloud).

## eng-150 (2026-10-23) - plan eng-148 stage 4 live (the owner's order, before the 100-trade threshold)
- 4.1: a sweep / Silver Bullet with no weekly / daily bias is blocked (`sweep_no_htf_bias`; no 1h-trend substitute);
  `against_bias` stays shadow.
- 4.2: premium / discount on the swept pool's timeframe range (PW -> 1d, PD / day -> 4h, else 1h), still shadow;
  journal `range_tf`, `range_pos_tf`, `range_pos_1h`.
- 4.3: `zones.stop_beyond` takes the NEAREST pool behind the invalidation (was the farthest); sweeps journal `sl_old`
  (the old rule) and `zone_moved` / `zone_move_atr` (a pool < 1 structure ATR beyond the extreme; journal-only: the
  fvg trigger never reads the zone, moving it would only have widened the stop - review).
- 4.5: a false pierce of an intact swing / PDH-PDL-PWH-PWL adds a '(pierce)' pool at its extreme; a 1h swing closed
  through with price still beyond is a `flip_1h` S/R level.
- 4.6: zones made only of `liq_est` are never targets, map fills, supports or structure stops.
- 4.7: the +1R TP2 / TP3 step repeats the previous target when a map zone stands in its path. Wyckoff / Seiden keep
  their own objectives (owner).
- 4.10: TL TOUCH UP / DOWN - the third touch of a two-swing 1h line within +-0.3 ATR, entry at the touch close, stop
  beyond the band + the measured pierce; the E&M break stays; cup_handle stays 1d only.
- Shadow: Crabel ORB from a fixed 13:30 UTC open journaled as `variant_orb_open` without a card (same as the live NY
  ORB until the US switches to EST on 2026-11-01).

## eng-151 (2026-10-23) - fixes of eng-150 after the external audit (the owner's order; eng-150 was never live)
- 4.1: `sweep_no_htf_bias` in `strategies.shadow_vetoes` (sweep + Silver Bullet): a context veto blocks before the
  entry and its row has no outcome (eng-148: no_prior_trend 506 / po3_* 217 rows, r_tp1 on none), and blocking the
  neutral bias while against_bias trades was not monotonic.
- 4.7: a 1R step that meets an opposing zone >= `levels.opposing_min_gap_r` (0.3R, heuristic) past the previous
  target stops at the zone's near edge (source 'before <zone>'); closer than that the previous target repeats.
- 4.3 shadow: `variant_pool2` - when `zone_moved` (an untaken pool < 1 ATR beyond the sweep's extreme), a resting
  limit at that pool's liquidity on the touch with the plan's stop rule from it; stats.py pairs it with the card's own
  entry. The external audit's hard block (no trigger before the second pool) was not adopted untested.
- `liq_cascade_2h` from 5m buckets of the universe's long liquidations (`DataFetcher.liq_long_5m`, ~25h): the per-coin
  deque (maxlen 2000) overflowed on ETH (2145 / 24h) and BTC (1998); None until 24h of buckets after a restart.
- replay: `book.h4_of` (4.2's 4h range). Version eng-151 (not 'eng-150.1': version_no parses an integer).
- Review fixes: the 1R step's target sits 0.01R before the zone and the next target repeats it; variant_pool2 is
  read before a card ends INVALID (the second raid runs through the invalidation; after a live entry it is not
  journaled - a limit); the liq coverage guard counts from the first live event (OKX backfill is older); replay h4
  closed candles only; against_trend still journaled when the bias veto is in shadow.
  On INVALID the pool-2 touch is searched on the 1m candles since the zone. Not covered: a second raid after a live
  entry or after the card ended - variant_pool2 compares only touches before the card's end.

## eng-167 (2026-10-25, remaining review items closed)
- Executor (trade-geometry review, sections 11 / 17): leverage cut until BingX's isolated liquidation estimate
  (entry x (1 -+ 1/lev)) lies beyond the stop with a 20% margin (Turtle 2N stops of 10-46% at 5x were liquidation-first);
  demo_trades journals slip_bps (entry fill vs the decision quote), latency_ms (card entry -> order), leverage.
- htf_bias blocks LONGS (live 13 days: longs against the coin's bearish top-down bias 9 of 9 lost, -1.0R; shorts tagged
  htf_bias +1.06R on 16 - the bias lags a falling market, so shorts stay shadow).
- Small caps: the flow gate uses the taker flow over the same 15 minutes as the move (`flow_15m`; the last 5 minutes
  caught the selling after the spike: APR +17.9% / RVOL 83 rejected); REST seeding limited to 8 at once.
- Journal-only features: pd_vpin (VPIN of the 1m ring), pd_impact_ratio (last 5m price impact vs its 288-bar median);
  PUMP TOP shadow veto pt_squeeze (OI rising with spot buying, audit F-14).
- Not changed (owner's decisions): daily loss limit / pause after stops (off), public dashboard, README / LICENSE,
  strategy modes (detect / paper / small / paused). Measurement items need live data (PLAN_next 10-14, 38).

## eng-166 (2026-10-24, why sweep cards miss TP1 without an entry)
- Live 15:12-22:00 (after eng-153): MISSED share of closed sweep cards ROSE (37% -> 52%); of 54 MISSED, 52 never armed
  (no structure shift + FVG on the trigger timeframe), 2 armed without a CE fill. On real Binance 15m data 29 of 39
  MISSED cards had TP1 AT OR BEFORE the swing the raid came from - the level ict.fvg_setup's shift must close beyond:
  price reached TP1 before an entry could exist, by construction.
- Fix: the sweep plan draws its targets from beyond that swing (`ict.raid_swing`, shared with fvg_setup, on the plan's
  trigger timeframe); `mss_level` journaled. eng-153's 60m -> 15m change did not address this (the reason only changed
  from 'no 60m trigger' to 'no 15m trigger').
- keep_waiting_from eng-165 (missed in eng-165: the not_in_pool veto changed).

## eng-165 (2026-10-24, the owner's order on live data)
- `not_in_pool` blocks (was a shadow veto): live entries tagged with it -0.20R a trade vs +0.01R without (50 / 64
  entries, 8h replay, 13 days).
- Bug (mine, eng-159): an inline comment inserted into the shadow_vetoes line commented out its rest, so not_in_pool,
  h4_against and regime_flat silently BLOCKED from 2026-10-24 19:10 (71 entries vetoed not_in_pool; 0 by the other two).
  h4_against / regime_flat back in shadow; the tuple now has one item group per line.

## eng-164 (2026-10-24, plan items 31 / 32 / 34 + an eng-163 bug)
- Bug (eng-163): smallcap._check reused the name `last` for the cooldown dict, so the next line read last[0] from a dict
  (KeyError(0) on every small-cap check after a cooldown) - renamed.
- ORB: Crabel's own rule (Day Trading with Short Term Price Patterns, 1990: "In general stops should be moved to break
  even within one hour after entry") - after 60 min, a trade whose last minute is fully beyond break-even gets
  break-even + costs (`plan['be_after_min']`), beside the +1R rule.
- SD: no fresh opposing zone -> Seiden's "initial profit margin" (the departure's extreme, `sd_departure_extreme`) is
  the target instead of 'no opposing supply / demand zone' (166 SD SUPPLY + 29 DEMAND skipped in 48h).
- Cascade no_prior_trend: a shadow tag instead of a hard plan skip (188 / 48h).
- Not done: Silver Bullet DOL advance (item 33) - tp1_passed means price already went beyond the target before the card
  existed (the idea played out); only a third-party glossary names the PWH / PWL advance.

## eng-163 (2026-10-24, microstructure audit items 22-30, verified)
- F-01 PUMP / DUMP START TP1 at least the risk span (`pump._span_targets`, `_risk_span`: |close - extreme| + 0.25 ATR,
  >= min_stop_atr x ATR): the bare measured move gave R:R < 1 by construction (a synthetic START now enters, was low_rr).
- F-02 pd_features evaluate a rolling bar of the last 5 closed minutes when the last complete 5m bar is stale
  (`pd_rolling_bar` = 1).
- F-03 DUMP START has no OI gate (long-liquidation cascades cut OI); `pd_dump_oi_regime` long_flush / short_build.
- F-06 BTC 5m cache refreshed per 5m bucket. F-08 variant_retest cancelled when TP1 trades before the zone touch.
- F-09 small-cap ACTIVATION base = median minute of the ring. F-12 event_risk on PUMP START = shadow tag.
- F-13 RushBook counts same-ms taker groups with >= 2 raw fills (aggTrade l - f + 1), `rush_fill_n_30s`; the multi-level
  `rush_*` columns unchanged.
- smallcap: one REST check per coin per 5 minutes; failing-gate log no longer cites OI for dumps.

## eng-162 (2026-10-24, external audit EDGEHUNTER_AUDIT_PRELIMINARY, confirmed findings)
- EH-LOGIC-001: logic_version eng-155 -> eng-162 (eng-156..161 changed vetoes, enabled setups, detection and journaling
  under the old label); keep_waiting_from eng-162 (by its own rule: detection / vetoes changed).
- EH-TRADE-002: the +1R partial is its own step (`SignalBook._partial_1r`) run before the SAR / % trail branches, which
  return early - BB1 / trail_pct cards booked no PARTIAL although the executor placed tp0 for new trades (journal R vs
  demo R disagreed). Break-even stays off where a plan has its own trail.
- EH-DOC-003: _trail docstring and the partial_share comment describe the current behaviour.
- EH-DEPLOY-001: deploy/install.sh USER_NAME=edgehunter (the units run User=edgehunter; a clean install could not start).
- EH-DEPLOY-004: constraints.txt (polars 2.0.0, ccxt 4.5.85, numpy, uvloop, orjson, picows, aiohttp as on the VPS) used by
  install.sh / setup_server.sh; README no longer says polars 1.44.2.

## eng-161 (2026-10-24, PLAN_next priority 1)
- 1m holes: `DataFetcher.minute_holes` / `patch_minute_holes` + `Scanner._minute_hole_pass` (each Health minute): the
  closed futures minutes missing in a universe coin's buffer (a stream reconnect left them for good - seed_minutes ran
  only at start-up / join; levels.resample then dropped the 5m / 15m bars: '1m gaps dropped' ~45 / h) are listed per
  coin (log "Minute holes: N coins, M minutes ... worst: ...") and refilled from REST, <= 15 coins a pass, one refill
  per coin per 10 minutes.
- Small caps attach at start-up (`SmallCapWatch.restore` from smallcap_coins.json, saved on every hourly list) instead
  of ~10 min later; a coin without 1h history loads it on its first check.
- Small-cap "no setup" log names the failing gate (move vs 4 x vol15, RVOL, OI 5m, taker flow, fresh 24h extreme).

## eng-160b (2026-10-24, external review of eng-159c)
- `pd_vs_btc_resid` + `pd_btc_beta`: the coin's 30-minute return minus beta x BTC's, beta from the previous 5m returns
  only (up to 288, aligned by candle time; BTC 5m cached per 5 min) - closer to the BOCD detector's alt-vs-BTC model
  than the plain difference `pd_vs_btc` (both journaled, judged apart).
- `pd_trades_ratio_5m` only when the 24h median is >= 20 trades a 5m candle (a near-dead coin's ratio is noise). It is a
  closed-candle context feature; the second-scale reading stays the rush-order proxy.
- RushBook documented as a proxy: aggTrade merges one taker's fills at one price, so only multi-level sweeps count
  (the paper groups raw same-ms trades). Columns kept as rush_* for journal continuity.
- Not done on purpose: the reviewer's offline ablation (the owner: no backtests) - the live journal holds every feature
  per card, and the comparison is made on live outcomes.

## eng-160 (2026-10-24, the owner: trade geometry scenario B as a shadow variant)
- `variant_retest` for PUMP START / DUMP START (SignalBook._retest_variants): every such card with a plan is watched -
  entered, vetoed (low_rr) or expired alike, so the variant has no survivorship - for 24 x 5m after the signal.
  Price back into H_n +- 0.25 ATR(5m), then a 5m close back beyond H_n -> entry at that close, the plan's own stop and
  targets, journaled as a vetoed entry 'variant_retest' (never traded). A close beyond H_n -+ 0.25 ATR on the wrong
  side = the breakout failed, no variant; a stale bar (restart) is skipped.
- H_n (`pd_hn`) = the edge of the 24 x 5m range before the signal's 15-minute move (not a bar of the move itself);
  `pd_atr5` = ATR(14) of 5m. Both journaled.

## eng-159c (2026-10-24, the remaining sources of the owner's research read)
- New journaled features at a PUMP / DUMP START (`pd_features.extras`, Scanner._pd_enrich): `pd_trades_ratio_5m`
  (La Morgia 2020 / Doge of Wall Street 2023: trade counts jump at the start), `pd_price_vs_ma12h` (Kamps &
  Kleinberg 2018, the 2025 thresholding detector), `pd_vs_btc` (RaibekTussupbekov's BOCD vs BTC). Rush orders
  (same-ms multi-level sweeps) were already in the bot (flow.RushOrders, rush_* columns) and reach these signals.
- Not implementable with our data: Telegram / NLP target prediction (Xu & Livshits, Hu et al., Bolz et al.,
  Nghiem et al.), 30-s random forests on historical P&D labels (Fantazzini & Xiao, La Morgia - needs labeled events),
  market-cap / developer-activity factors (Charfeddine & Mahrous, Victor & Hagemann), sub-second cross-venue impact
  (Albers et al.), L2 add / cancel for small caps (no books there).
- CORRECTION (external review, re-checked 2026-10-24): Tsuchiya 2021 (Digital Finance, doi 10.1007/s42521-021-00034-6),
  Schmalz 2026 (SSRN 7227998, preprint) and Kitvanitphasu et al. 2026 (RIBAF 81, doi 10.1016/j.ribaf.2025.103163)
  DO exist - my "not found / likely invented" was wrong. None gives a rule usable here (exchange-level P&D success;
  OFI on Binance.US BTC that flipped sign across 7 / 9 / 17 days; VPIN and BTC jumps).

## eng-159b (2026-10-24, checked against the source: aleks-ent PUMP_DETECTION_RULES.md, read in full)
- Baselines now as the source: medians of the PREVIOUS 288 closed 5m candles (REST, one call per PUMP / DUMP START,
  `Scanner._pd_enrich`), not the 4h ring / 15m approximation (`pd_base_n` journaled).
- Added the source's features: range cluster (>= 2x among the last 4), green / red count of 4 / 6, close vs EMA20 and
  its 6-bar slope, the pullback from the impulse (start = first of the last 12 bars with volume >= 3x, range >= 2x),
  the quiet window 24-72 candles before the impulse start.
- Phases as the source: ACTIVATION (5m: vol >= 3x, range >= 1.5x, move3 > 0, close beyond EMA20 or a breakout),
  ACTIVE (both clusters, move3 >= 2% or move6 >= 4%, 3 of 4 in the direction, pullback <= 0.30, EMA20 side + slope),
  LATE, SPIKE_FAIL (> 70%), else NONE. The ACTIVATION lead-time log runs on closed 5m bars.
- The source has no standalone dump start (dumps = distribution after a pump): DUMP START is our mirror, kept.

## eng-159 (2026-10-24, the owner: implement docs/PUMP_DUMP_DETECTOR.md)
- `strategies/pd_features.py`: 24h MEDIAN volume baselines (96 closed 15m candles), the 5m layer from the final 1m
  candles (volume ratio + cluster >= 3x of the last 4, range_ratio vs the ring's median 5m range, move3 / move6 /
  move12, 2h breakout, 2-6h quiet), phases LATE / SPIKE_FAIL, ACTIVATION log (lead time).
- PUMP START / DUMP START gate on the median-based RVOL (`rvol_1m_med`) when available, the Tier-0 mean otherwise.
- LATE and SPIKE_FAIL are shadow vetoes (`pd_late`, `pd_spike_fail`): journaled, not blocking - data first.
- Journal columns: rvol_1m_med, pd_vol_ratio_5m, pd_vol_cluster, pd_range_ratio, pd_move3 / 6 / 12, pd_breakout,
  pd_quiet, pd_late, pd_spike_fail, pd_phase, pd_activation_lead_s, smallcap, flow_src.
- Small caps: ring 240 minutes; their ACTIVATION base is the 24h mean minute (no 15m history before a check).

## eng-158 (2026-10-24, the owner: catch pump / dump starts in the small caps too - KAT -44%, WET -46% were missed)
- `smallcap.py` SmallCapWatch: the wide watch's perpetuals (outside the universe, >= wide_min_volume) on ONE dynamic
  Binance futures connection of 1m klines (no universe stream restart); a 180-minute ring per coin (~7 MB / 150).
  Each final minute: |15m move| >= pump_start_min_pct gates; then REST 15m volatility + 5m OI change, and
  PUMP START / DUMP START decide. A hit is a normal setup signal -> card, journal, demo (BingX).
- Small-cap inputs: futures taker flow instead of spot (`flow_src` 'futures'), rvol = minute / (24h volume / 1440),
  ATR = 1h ATR(14) / 2 (`sig['atr_15m']`, used by PlanInput.atr when there is no 15m frame).
- Scanner: `_price_of` / `_minute_candles` fall back to the watch for coins outside the universe; the card's first plan
  does not wait for a 15m frame when `sig['smallcap']`. Health line: "small caps N coins, checks, setups".
- After a restart the watch re-attaches with the wide watch (~10 min); a small-cap trade keeps its exchange stop.

## eng-157 (2026-10-24, the owner's order: every strategy on, collect the data; pumps AND dumps)
- `strategies.disabled_setups` emptied: BULL E, BULL A, PUMP TOP, PUMP START, OI BUILD LONG / SHORT produce cards and
  journal again (demo_off_setups was already empty).
- DUMP START (new, strategies/pump.py): PUMP START mirrored - 15m fall >= max(pump_start_min_pct, pump_start_z x 15m
  vol) on RVOL >= pump_start_rvol, OI rising (new shorts) and spot selling, at a fresh 24h low; short at the
  confirmation, stop above the ignition, measured-move / 1h+ zone targets. Wired in loopside._pumps.
- Known side effect (eng-144): OI BUILD made 5387 cards in 2.5 days and its opposite cards cancelled 105 SWEEP cards.
- cup_handle stays behind its history gate (not enough 1h / 4h history yet) - not a switch.

## eng-156 (2026-10-24, decided by me on the owner's order; plan + sources: docs/PLAN_eng156.md)
- `against_bias` blocks again (SWEEP / SILVER BULLET against the weekly / daily bias; live 6 sweep entries, 1 win,
  -5.5R); `against_trend` stays shadow.
- `crowd_max` 6 (Turtles' closely correlated limit; 28 trendline shorts were open at once).
- signal_book `_resample`: cached per (coin, tf), copies out (loop stalls under _try_entry / _trail).
- Wyckoff INVALID text names the spring low / upthrust high (was the generic range text).
- eng-155b: on_partial keeps half of the ORIGINAL size (APE past its TP1 third was closed down to 1/6).

## eng-155 logic_version bump (2026-10-24, follow-up)
- `logic_version` eng-152 -> eng-155: eng-153 / 154 / 155 went live 15:12-16:41 UTC without it, so their rows until
  this bump are labelled eng-152 (stats per version mix them). `keep_waiting_from` stays eng-152 (HIT_RATE floor,
  waiting cards of 15:12+ carry the old label). Online P(edge) / confirm stats restart from the new version's rows.
- `strategies/level.py`: `sl_old` = `invalid` (the second identical farthest-pool `stop_beyond` call removed).
- `main.py`: the BytesIO `BufferError` at gc finalization (harmless, 3.13+ reports it; RhysU/jobserver#444) is one
  INFO line an hour; uvloop 0.22.1's `asyncio.iscoroutinefunction` DeprecationWarning filtered by its text
  (fixed in uvloop 0.23.0, but ccxt 4.5.90 still pins 0.22.1).

## eng-155 (2026-10-24, the owner: protect the profit - 18 trendline shorts at +1..+3R had their stops untouched)
- `strategies.be_after_1r` True: the stop to break-even + costs after +1R for every plan (off since eng-111); cards
  restored without the flag get it too (`_trail`). SAR / % trail plans keep their own trail.
- `executor.partial_share` 0.5: half out at +1R (off since eng-123). New trades: the tp0 order (exit_parts). Open
  trades: the card's +1R raises PARTIAL -> `executor.on_partial` (take-profits cancelled, the half at market, the
  take-profits re-placed for the rest, `partial_done` on the row; skipped when tp0 already took it).
- The thirds expectancy veto no longer applies (the exit is not three thirds any more) - by its own rule.

## eng-154 (2026-10-24, the owner: a losing streak is a bug to fix, not a sample to wait for)
- ORB: the stop to break-even + costs after +1R (`plan['be_after_r'] = 1.0`); still out at the session's close.
  Live eng-148: 8 of 10 ORB cards lost, 4 in a row; XAG / XAU / BNB / XRP traded +0.6..+1.1R and closed
  -0.1..-0.7R at the close (no stop management since eng-146 reverted the SAR, be_after_1r off since eng-111).
- signal_book._trail docstring: ORB no longer listed under the SAR (removed in eng-146).

## eng-153 (2026-10-24, external audit #3, confirmed findings only)
- SWEEP plan timeframe capped at 1h (`sweep_tf`): the raid is a 15m candle, its trigger is now at most 15m. The day /
  previous day / week pools had a 4h plan with a 60m trigger: live eng-152, 109 of 113 MISSED cards were
  "no 60m trigger" while TP1 came in 15-90 min. `pool_rank` unchanged (dealing range tf, best pool choice).
- Journal: flow_entry / reclaim_entry / weak_mss (shadow, never traded) are rows of their own like `variant_*`;
  they took the card's one veto slot and the method's own later veto was silently dropped.
- Rejected from the audit: dropping the protected-swing stop for sweep (it only applies beyond the extreme, never
  inside), uvloop upgrade (0.22.1 still warns, ccxt pins it), flow_entry "85% win" (replayed, TP1 at 0.03-0.4R).

## eng-152 (2026-10-24, the owner's order after the external audit)
- Plan 4.3 back to shadow for SWEEP LOW / HIGH: invalidation and entry stop beyond the farthest pool
  (`plan['stop_farthest']`, the eng-148 rule); the nearest-pool invalidation journaled as `sl_near`.
- Why (live eng-151, 3.6h): 41 of 44 INVALID sweep cards had the nearest-pool stop, median life 16 min vs 135;
  26 of the 41 were invalidated by a price that never reached the old stop; 0 own sweep entries.
- Not a full return to eng-148: pierce pools (4.5) stay live. Silver Bullet unchanged (entry stop still nearest -
  owner's call). `variant_pool2` rows not comparable with eng-151. `sl_old` == invalid now.
- Includes d69bb88 (variant_pool2 enters at the pool's own untaken price).

## eng-168 (25.10) — htf_bias audit
- The eng-167 block of longs on the htf_bias tag removed: untagged longs lost almost as much (−0.77R on 80 vs −1.0R on 9) in a 13-day falling market, which is the side's beta, not the filter. htf_bias is a shadow tag for both sides again.
- Bug: the shadow tags of an entry attempt survived into later attempts of a waiting card (sig is replaced only while the setup re-appears), so a stale htf_bias tag could block a long that was by then with the trend and mislabel journal rows. `SignalBook._new_attempt` resets to the setup-time tags at the start of each attempt.
- Journaling only (the audit: the eng-168 sample would not be clean otherwise): WITH_BIAS setups (sweep, connors, supply_demand) in a 'range' bias get their own shadow tag `htf_range` instead of `htf_bias`; the htf_bias / htf_range / htf_conflict and h4_against tags are written even when an earlier filter (crowded, market_down, sd_score...) already vetoed the entry - no censoring by the filter order for these tags.
- SD investigation (item 1 of the deferred list): no search bug - 'no opposing zone' is 0 since eng-164 (the departure-extreme target); the remaining causes are Seiden's min_rr 3 at the first touch (low_rr kills the single-touch card; would-be EV of the low_rr entries -0.40R on 91, the rule protects) and waiting cards expired at restarts by keep_waiting_from bumps (26 of 40 SD cards since eng-164). keep_waiting_from stays eng-167 in eng-168.
- Recorded, not applied (measurement first): a faster tide (EMA20 d1, TSM 7/14/30, Kaufman ER), unconditional collection of all filter reasons (censoring by order), cluster-based sample rules, unused gate() btc_bias/is_btc. Journal `daily_bias` is ICT's prior-day close vs range (scanner.py), not bias.d1 - hence its mismatch with the veto.
- Bug (Silver Bullet tp1_passed, deferred item 3): the tp1_passed drop and the MISSED end compared the price with `plan['targets'][0]` - the nearest map pool from select_targets - while a system with its own level target (Silver Bullet / PO3: exit['tp'] = ['level', PDH / PDL, ...]) takes TP1 there (geometry.exit_target). 64 of 123 Silver Bullet tp1_passed setups were dropped with the draw still ahead of the price; the other 59 had the draw already taken (ICT: target reached before the retrace - a correct cancel). `signal_book.card_tp1` returns the system's level target, else targets[0].
- BB W-BOTTOM "22 of 22 stops": 16 are eng-76/82 entries with tp1 NULL (pre-eng-85; the 8h replay cannot book a TP) - excluded from measurements; since eng-88 8 trades, 4 of the 6 stops one 4h close (16.10 08:00). Detector checked on Binance candles: a_ is the LAST close outside the band (4-8 bars), the retest low above the first in 7 / 8, A/D compared as a difference (cumulative offset cancels). Backlog: the 1.5 ATR 4h stop pad doubles Bollinger's stop on volatile coins (PONS 8.7% -> 17.6%).
- not_in_pool back in shadow (owner, 25.10: the difference is noise; the clean sample needs the full flow); bias.gate's unused btc_bias / is_btc arguments removed.
