# Plan after the audit (2026-10-01)

Each item: why, what exactly, how it is checked, sources. Order = dependencies (machine first, the archive run needs
memory; zones and SMT change the logic, so they go in BEFORE the archive run, or the run measures an old logic again).

## 1. Free the machine (prerequisite)
Why: ~500 MB free of 6 GB; below ~400 MB Windows pages and the loop stalls 1-6 s regardless of the code; the archive
run and the P(edge) rebuild cannot run next to the bot.
- [x] 1.1 (claude 1.36 GB, python 1.28 GB incl. an automatic pretrain.py 320 MB, chrome 0.7 GB) Measure what uses RAM (processes by working set).
- [ ] 1.2 Owner closes what is not needed (browser tabs, second Claude windows).
- [x] 1.3 (instead: automatic pretraining off until item 5, shadow IsolationForest worker off - config.local.toml; the flow rings are ~60 MB, not worth it) Bot: shorter flow rings for the 1h-history venues where the 1h window is not read (measure first which
      windows are read: 5m Tier-0, 1h perp-led / confirmations).
- [ ] 1.4 Check: free RAM >= 1.5 GB with the bot running; no "Event loop blocked" for 30 min.

## 2. Zones from price action, not +-ATR (logic change, before the archive run)
Why: classic S/R zones are drawn from the candles AT the level - body close ("acceptance") to wick extreme ("probe"),
"the whole region where price fought" (BabyPips / FXStreet / TradingStrategyGuides); an ICT order block is the
candle's body (or full range) with its 50% "mean threshold". "Level +- k x ATR" is an indicator-author convention
(TradingView ATR-zone scripts), not a method. The bot uses ATR for: merge_atr 0.3 (levels merged into a zone),
zone_half_atr 0.25 (pullback zone around a level), sweep_zone_atr 0.25, breakout_zone_atr 0.25, auction +-0.25 ATR.
- [x] 2.1 RawLevel carries its candle: for a swing the pivot candle's body edge and wick extreme; for equal highs /
      lows the span of the touching candles' bodies / wicks; PDH/PDL / sessions: the extreme candle's body-to-wick.
- [x] 2.2 (merge tolerance = the kind's p50 pierce) Zone = union of its levels' body-to-wick spans (merging by overlap, not by 0.3 ATR); strength unchanged.
- [x] 2.3 (EMA20 point: p50 pierce of a swing) Pullback zone (trend / momentum) = the support zone's own span, not level +- 0.25 ATR.
- [x] 2.4 sweep / breakout done; auction's engine keeps its own +-0.25 ATR retest band (the author's system) - Sweep entry area = wick to the sweep candle's body (already close); breakout retest = the breakout candle's
      body-to-edge; auction = the POC's value area (VAL-VAH of the consolidation), not +-0.25 ATR.
- [x] 2.5 ATR stays only where nothing is measured (fillers when the map is empty).
- [x] 2.6 (checked on SOL / BTC / ETH 1h charts: zones = the bodies-to-wicks of the extreme candles; a chaining bug that merged half the chart into one zone fixed in 72827d1; widths now 0.1-2.4%) Check: tests pass; on the live chart the zones match the candles at the levels (owner's eye on 5 coins).

## 3. SMT only on correlated pairs (logic change, before the archive run)
Why: SMT needs a tight correlation - normally > 0.7 (BTC/ETH ~0.85; BTC/SOL, ETH/SOL usable; BTC vs DOGE is "not an
SMT pair") - TradingFinder / Bitsgap / Quantum Algo. The bot picks the better of BTC / ETH but never checks the level.
- [x] 3.1 (+ a signal needs SMT or QM: without a pair it passed as a plain sweep) Correlation of 15m returns over the last 200 candles >= 0.7 or the coin gets no SMT signal (journaled
      vetoed='low_correlation').
- [x] 3.2 BTC / ETH / SOL (never the coin itself) Candidates: BTC, ETH, SOL (and the coin's own sector leader once sectors.py maps it).
- [x] 3.3 'smt pairs x/y' in the Health line Check: the share of coins with an SMT pair, logged once an hour.

## 4. Archive validation of the CURRENT logic (after 1-3)
Why: every archive number (cards, placebo, exits) was measured before today's changes (structural stops, measured
pierce, R:R 2, confirmations, source-aligned strategies). The old placebo run (eng-10 logic) finished 01:31.
- [x] 4.1 prep: PIERCE_MODEL env + research_overshoot.py --model-out; at run time: research_overshoot.py --end <replay start> --model-out models/overshoot_pre.json, then PIERCE_MODEL=models/overshoot_pre.json for the replays.
      Was: research_cards.py already updated (new detectors, fvg / touch triggers, confirmations, single touch).
      Remaining: the pierce model must not see the future - in the replay use the older-half p80 (or the global
      one), not the 12-month file.
- [ ] 4.2 Smoke run: 1 coin, 1 month; the report's rows look sane.
- [ ] 4.3 Full run: 6 months, 2 holdout months, 100 coins, placebo, 2 workers (~6-8 h, at night).
- [ ] 4.4 research_maniac.py the same for the ported systems.
- [ ] 4.5 Pre-registered verdict (written before the run): a class works only if R > 0 on development AND holdout,
      the holdout 90% interval > 0 and "system - placebo" on holdout > 0.
- [ ] 4.6 Report research/validation_eng26.md; decisions per class.

## 5. P(edge) rebuild (after 4: both do not fit in memory)
- [ ] 5.1 pretrain.py on the current logic (it refuses the eng-7 file already); ml_eval.py on the result.
- [ ] 5.2 Stays shadow unless out-of-sample AUC and the top-decile Edge beat the base rate (as before: 0.53).

## 6. Live report after 7 days (runs by itself; the report on day 7)
- [ ] 6.1 Per strategy: entries, R net (journal replay) vs the BingX demo fills - do they agree?
- [ ] 6.2 Anomaly labels and icebergs: the "Эффект" column on a second market (not the falling 27-30 Sep one).
- [ ] 6.3 Confirmations (min 1) and R:R 2: vetoed entries' replay vs taken ones.
- [ ] 6.4 Live-verdict rule (CLAUDE.md) for every strategy with >= 30 independent 4h clusters.

## 7. Owner decisions (not code)
- [ ] 7.1 On-chain exchange flows (CryptoQuant / Whale Alert): paid; decide whether they are worth it.
- [ ] 7.2 VPS / a second machine if item 1 does not free enough RAM.

Sources: BabyPips forum "wick or body", FXStreet Learning Center (support / resistance), TradingStrategyGuides
"Drawing support and resistance", ATAS / TradingFinder (ICT order blocks, mean threshold), TradingView ATR-zone
scripts (the ATR convention), TradingFinder / Bitsgap / Quantum Algo (SMT correlation > 0.7).

## Done 2026-10-01 night (eng-28)
- [x] worker-path test (tests/test_runtime.py::test_build_maps_worker_path_returns_a_context)
- [x] auction: touch band = p50 pierce of a 1h level, stop pad = p80 (was 0.25 / 0.35 ATR)
- [x] sweep: no ATR minimum depth with the pierce model (any trade beyond the pool, volume + close back filter)
- [x] confirmations: a venue counts only if its ring covers the window; no reading -> None, never a false 0
- [x] trigger: ICT MSS = break of the last 2/2 swing before the extreme (fallback: the 5-candle high / low)
- [~] alt-spot seed at start: impossible - Bybit's REST klines carry no taker split
