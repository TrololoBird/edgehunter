# Собрание Python-докстрок EdgeHunter

Сгенерировано из AST текущего дерева проекта. Включены только настоящие docstring-литералы: первый строковый оператор модуля, класса, функции или async-функции.

- Корень: `/opt/edgehunter`
- Python-файлов проверено: **139**
- Докстрок найдено: **1160**
- Ошибок разбора: **0**

## Докстроки

### `briefing.py`

#### 1. `_read_jsonl` — function — `briefing.py:67`

```text
Read valid JSONL records while tolerating a truncated final write.
```

#### 2. `to_4h` — function — `briefing.py:88`

```text
eng-168y: closed 1h bars [ts, o, h, l, c] -> the complete 4h bars (UTC 4h boundaries) they make.
```

#### 3. `conf_tf` — function — `briefing.py:102-104`

```text
eng-168y (the owner: analysis is not the bot's strategies): the candle that confirms a close beyond a zone
    follows the zone's own timeframe - 4h for a zone of 4h / 1d / 1w pivots or a higher map level (previous day / week /
    month extremes, the value area), 1h for an intraday one (1h pivots, today's extremes, sessions).
```

#### 4. `_significant` — function — `briefing.py:134`

```text
A level a briefing zone may stand on (key_zones).
```

#### 5. `describe` — function — `briefing.py:163`

```text
'What it is' for a zone: its levels in words, the highest timeframes first, at most three.
```

#### 6. `_label_rank` — function — `briefing.py:177`

```text
Higher timeframes first: weekly / previous week, daily / previous day, 4h, 1h, sessions / profile, 15m.
```

#### 7. `macro_today` — function — `briefing.py:187-189`

```text
Today's (MSK) US releases: the calendar's dated CPI / FOMC plus the regular ones by their publication rule
    (NFP the first Friday 08:30 NY, ISM manufacturing the first business day 10:00, ISM services the third business
    day 10:00, jobless claims every Thursday 08:30) - rules, not a published calendar: holidays / shutdowns move them.
```

#### 8. `Briefing._load_slots` — function — `briefing.py:243-244`

```text
The schedule slots already sent (owner 2026-10-18: a restart inside a slot's 10 minutes sent the 10-15 02:30
        briefing twice - the set lived in memory only).
```

#### 9. `Briefing._splice` — function — `briefing.py:313`

```text
The proxy's candles before the contract's first one, scaled to it at the overlap, then the contract's.
```

#### 10. `Briefing.session_bias` — function — `briefing.py:369-372`

```text
eng-168l (audit #3): the fast background of the next 1-3 days beside the weekly one (which read 'bull' in 11 of
        14 falling sessions): +1 when the last closed 4h is above its EMA20, the EMA20 rose over 3 candles (12h) and the
        24h return is positive; -1 mirrored; 0 else. A display / checklist context, not a trading filter; the periods
        are this module's choice (no source).
```

#### 11. `Briefing.level_map` — function — `briefing.py:392-395`

```text
eng-168x (the owner: the briefing is analysis and possible scenarios): the levels as an if-then map - for the
        nearest resistance / support (and the zone price is in) what a 1h close beyond it opens (the next zone), plus ONE
        base view: with the fast 1-3 day background up 'while above S, a test of R first', down mirrored, neutral = the
        range between them. Conditions only, no probability claimed.
```

#### 12. `Briefing.positioning_line` — function — `briefing.py:423-424`

```text
eng-168w: the crowd beside the levels - the Binance share of accounts long (global long / short ratio) and the
        open interest change over the last hour. Context only: no rule reads it.
```

#### 13. `Briefing._bias_line` — function — `briefing.py:442-443`

```text
The higher timeframe as BACKGROUND (Elder's tide: a filter of direction over weeks, not the session's
        forecast - it said 'bull' for BTC / ETH / SOL through 11 of 14 falling sessions, 2026-10-05..07).
```

#### 14. `Briefing._extremes_24h` — function — `briefing.py:458-459`

```text
24h high / low: the closed 1h candles + the final 1m candles after the last of them (the 1h candles load
        a minute after the hour).
```

#### 15. `Briefing._history_high` — function — `briefing.py:471`

```text
The highest high of the daily / weekly history held (price discovery above it), with its depth in days.
```

#### 16. `Briefing.key_zones` — function — `briefing.py:484-492`

```text

        The 1h+ zones of the plans' map around the price (eng-74, the 2026-10-07 review): whole zones, never trimmed
        (a trim to 0.3 daily ATR cut ETH's daily breaker 2 475-2 615 to 2 593-2 615, deleted the daily FVG 2 484-2 562
        inside it and every level above BTC's 87 177); a zone containing the price is shown, not dropped; supports are
        BELOW the price and resistances ABOVE it (they were counted from the watched zone: ETH's 'support' sat above
        the price). Each zone carries `tol` (the measured p50 pierce: a retest / acceptance within it counts - Murphy:
        zones, not prices; Bulkowski: what matters is the close beyond) and `pad` (the stop buffer beyond it: the
        measured p80 pierce, at least zone_buffer_atr x the 1h ATR - Osler: stops cluster just beyond a level).
        
```

#### 17. `Briefing.key_zones.ladder` — function — `briefing.py:655-658`

```text
Outward from the PRICE, NEAREST first (a target is the next level price meets - the strongest zone of a
            daily-ATR window skipped BTC's 82 500 daily low and ETH's 2 475 edge for weaker or farther ones); the next
            pick must lie beyond the previous one by more than their pierce (closer = one place); a zone of
            15m / 1h levels only was already dropped above.
```

#### 18. `Briefing.coin_text` — function — `briefing.py:701-702`

```text
The coin's zones and the two scenarios of the card (briefing_chart.plan: one source for the text, the
        picture, the watch alerts and the evening scoring).
```

#### 19. `Briefing.light_src` — function — `briefing.py:736-737`

```text
A coin outside the universe, from REST candles only (rows [ts, o, h, l, c, ...]): the same shape key_zones /
        htf_bias read. No flows, liquidations or level map - the zones are the swing clusters of sr.zones alone.
```

#### 20. `Briefing.analyze` — function — `briefing.py:750-752`

```text
The web analysis of one coin (pinned or typed in): zones, higher-timeframe bias, the long / short scenarios
        of briefing_chart.plan with their R:R and a mechanical checklist per side. Pure: the watched state (context,
        zones, scenario) is restored, nothing is posted. A rule list, not advice.
```

#### 21. `Briefing.cards` — function — `briefing.py:883`

```text
The briefing as pictures: (PNG, caption) per watched coin, the first caption carries the market / macro.
```

#### 22. `Briefing._save` — function — `briefing.py:930-931`

```text
Each briefing's forecast per coin (bias, zones, scenario) to data/briefings.jsonl: the posts lived only in
        Telegram, so nothing could be scored afterwards (2026-10-07 review).
```

#### 23. `Briefing._publication_intent` — function — `briefing.py:979`

```text
Persist an idempotent publication intent before external delivery.
```

#### 24. `Briefing._reconcile_publication` — function — `briefing.py:1000`

```text
Check the just-sent slot against delivery and archive identities.
```

#### 25. `Briefing.outcomes_total` — function — `briefing.py:1011`

```text
The tally over every pinned coin (long / short x outcome class) for the analysis page's header.
```

#### 26. `Briefing.snapshot_outcomes` — function — `briefing.py:1021-1022`

```text
The evening tally of the last 14 days per coin to data/briefing_outcomes.jsonl (one line a day): the trend of
        the plan rules' results over time, kept apart from the Telegram recaps.
```

#### 27. `Briefing.reaction` — function — `briefing.py:1039-1042`

```text
The REACTION that enters a briefing scenario (eng-74; the cards said 'реакция' / 'отказ' and the scoring
        filled on a mere touch): a closed 1h candle that traded into the entry range and closed back beyond its far
        edge in the trade's direction, as a candle of that colour - the confirmation candle of the break-and-retest /
        range playbooks (a wick into the level, the close back out).
```

#### 28. `Briefing.score_detail` — function — `briefing.py:1062-1064`

```text
score_scenario's (text, resolved_ms, r). eng-168m: resolved_ms = the close of the candle that ended it (TP1 /
        stop / cancelled / missed), None while undecided; r = the result in R (TP1 R, -1), and for an entered scenario
        still undecided the mark-to-market R at the last candle's close (an 'expired open' trade is not dropped).
```

#### 29. `Briefing._score_today` — function — `briefing.py:1131`

```text
Today's saved briefings of the coin (data/briefings.jsonl), each scenario scored on the closed 1h candles.
```

#### 30. `Briefing._resolved_today` — function — `briefing.py:1150-1152`

```text
eng-168m (audit #3): the published scenarios of the previous days (within OUTCOME_HOURS) whose outcome came
        TODAY (MSK): TP1 / stop / cancelled / missed on a candle closed today, or the horizon ended today with the trade
        still open (marked to market). The recap scored only today's posts.
```

#### 31. `Briefing.exec_detail` — function — `briefing.py:1181-1187`

```text
eng-168r (audit #6): two measures of an ENTERED scenario, kept apart.
        Scenario (the forecast): whether TP1 / TP2 / the stop traded after the entry, MFE / MAE in R of price from the
        entry, hours to the first of TP1 / stop. Execution (execution_model_v1, the bot's own rule): 50% out at +1R,
        the rest's stop to break-even + costs, the rest out at TP2 (TP1 when there is no TP2 beyond +1R) or that stop;
        costs = journal.fee_round_trip + 2 x levels.slippage_bps (base) on the whole position, funding NOT included. One 1h candle
        touching a stop and a target: the order is unknown - the stop is taken (conservative) and the outcome is marked
        ambiguous. Undecided at the end of `after` (the 72h horizon): marked to market at the last close.
```

#### 32. `Briefing.sweep_variant` — function — `briefing.py:1252-1259`

```text
eng-168w / eng-169 (audit #10, the ICT liquidity sweep as defined there), a SHADOW entry measured beside the
        scenario's own - nothing is posted or traded on it. The pool is the scenario zone's FAR edge (a cluster of swing
        extremes / a map level: resting stops beyond it). A closed 1h candle:
          - trades beyond that edge by 0.05..0.8 ATR(1h) (deeper = a run, not a sweep);
          - closes back beyond the zone's MIDDLE (displacement), with the rejecting wick >= 40% of its range;
        entry at its close, stop beyond its extreme by max(0.25 ATR(1h), 0.25 x its range), the scenario's targets,
        R:R >= 1 from the close. Old records without the zone / ATR fall back to the entry range and its width.
        Scored with exec_detail (execution_model_v1). None = no such candle within the bars.
```

#### 33. `Briefing._post_minutes` — function — `briefing.py:1291-1292`

```text
eng-168y: the 1m candles of the post's hour after the post, from Binance REST when the bot's ~10h minute
        ring no longer holds them (the recap at 23:30 scored the 02:30 / 09:30 posts without their hour). Cached.
```

#### 34. `Briefing._score_record` — function — `briefing.py:1314-1316`

```text
One saved briefing record against the closed 1h candles after its post: ([(name, result, tag)], ambiguous).
        audit N22: only prices AFTER the post. The hour holding the post is scored on its 1m candles after the post's
        minute; without them that hour is left out and said so (its OHLC may be before the post).
```

#### 35. `Briefing.human_outcome` — function — `briefing.py:1363`

```text
eng-168y: the scorer's status in words for the recap.
```

#### 36. `Briefing.outcomes` — function — `briefing.py:1403-1404`

```text
The saved briefings' scenarios scored on the closed candles (each against its own MSK day, as the recap):
        counts by scenario side and outcome class. A tally of what the plan rules did, not a verdict on them.
```

#### 37. `Briefing.check_levels` — function — `briefing.py:1521`

```text
Acceptance / rejection of the briefing zones on each newly closed 1h candle.
```

#### 38. `Briefing.check_shock` — function — `briefing.py:1601`

```text
A watched coin's 15m move >= shock_z x its typical 15m move (and >= shock_min_pct), with the breadth.
```

#### 39. `Briefing._zone_note` — function — `briefing.py:1709`

```text
Which briefing zone the events happened at, within its tolerance.
```

#### 40. `Briefing._scenario_note` — function — `briefing.py:1720`

```text
What the price now means for the briefing's two scenarios: which one is armed / where it is cancelled.
```

### `briefing_chart.py`

#### 41. `<module>` — module — `briefing_chart.py:1-20`

```text

The briefing card as a picture, laid out as the owner's reference (an analyst's BingX card, 2026-10-05):

  header   big price (green / red by the day), "<SYMBOL> · 1h · за сутки +x%", 24h high / low and the 1h ATR at the
           right; the timeframe tabs 1м 15м 1ч 4ч 1д with 1ч selected
  chart    ~3 days of 1h candles in the left ~60% of the width (room on the right), dates under it; six horizontal
           zones - ГЛОБАЛЬНОЕ СОПРОТИВЛЕНИЕ / СОПРОТИВЛЕНИЕ / ЛОКАЛЬНОЕ СОПРОТИВЛЕНИЕ / ЗОНА ПОДДЕРЖКИ / РЕАКЦИЯ /
           СЛЕДУЮЩАЯ ПОДДЕРЖКА / КЛЮЧЕВАЯ ПОДДЕРЖКА - each a tinted band with its name and role on the left, "lo – hi"
           in the middle and a coloured tag at the right with its upper edge and the distance in %; the price as a
           dashed line with a dark tag "price / HH:MM UTC"; the LONG tag (пробой и закрепление) near the top, the
           SHORT tag (пробой поддержки) near the bottom
  boxes    ЛОНГ (только после подтверждения): entry just above the watched zone after acceptance, targets at the three
           resistances' upper edges, stop below the next support's upper edge, condition "пробой и ретест зоны X";
           ШОРТ (при подтверждении): entry in the local resistance (отскок / реакция), targets the watched zone's low
           and the supports' upper edges, stop above the second resistance, condition "сигнал на разворот в зоне"
  footer   "СЕЙЧАС ЦЕНА ВНУТРИ ЗОНЫ lo – hi. ЖДЁМ ПОДТВЕРЖДЕНИЯ." / "Входить в середине диапазона не рекомендуется."

The % in the scenario tags is NOT the analyst's unexplained "probability": it is the driftless random-walk chance that
TP1 trades before the stop from the entry (stop distance / (stop + TP1 distance)), marked with * and explained.

```

#### 42. `plan` — function — `briefing_chart.py:57-67`

```text

    The two scenarios of the card (eng-74, the 2026-10-07 review):
    - price INSIDE a zone: long = a 1h close above it + a retest, short = a 1h close below it + a retest;
    - price BETWEEN zones: long = the retest of the nearest support from above with a reaction, short = the retest of
      the nearest resistance from below with a rejection;
    a retest / close counts within the zone's measured pierce (`tol`: Murphy - zones, not prices; Bulkowski - the
    close beyond decides, not an exact touch); the stop beyond the WHOLE zone + `pad` (the p80 pierce clamped to 0.5-1 ATR(1h) -
    Osler: stops cluster just beyond levels; was a quarter of the zone / 0.1%: ETH's stop sat 6 dollars below the
    edge); targets are real zones' near edges only - ATR steps only above the highest high of the history held
    (`ath`, price discovery), labelled; percentages from the ENTRY.
    
```

#### 43. `plan.touch` — function — `briefing_chart.py:85`

```text
eng-169a: the trigger edge (zone edge + tol); 'касание X' when price is still beyond it, else 'цена уже у зоны'.
```

#### 44. `plan.push_stop` — function — `briefing_chart.py:122-123`

```text
A stop inside another zone goes beyond that zone's far edge + its pad (Osler: stops cluster just beyond a
        level - BTC's short stop 84 087 sat inside the resistance 83 577-84 273).
```

#### 45. `plan.bounce` — function — `briefing_chart.py:166`

```text
Long from the nearest support below: its test + a bullish 1h reaction candle.
```

#### 46. `plan.fade` — function — `briefing_chart.py:175`

```text
Short from the nearest resistance above: its test + a bearish 1h reaction candle (the reference card).
```

#### 47. `render` — function — `briefing_chart.py:254-255`

```text
`candles`: 4h candles drawn on the chart; `atr_1h`: the drawn timeframe's ATR (4h); `candles_1h` for the 24h
    change / high / low.
```

### `config.py`

#### 48. `<module>` — module — `config.py:1-16`

```text

All tunables, as frozen dataclasses reached through the global CONFIG.

Local overrides: an optional `config.local.toml` next to this file replaces individual values without code edits,
e.g.

    [tier0]
    rvol_1m_threshold = 6.0

    [notify]
    enabled = true
    telegram_token = "..."
    telegram_chat_id = "..."

Unknown sections/keys or values of the wrong type are rejected at start-up (load_overrides).

```

#### 49. `Tier0Config` — class — `config.py:187`

```text
Raw impulse detection that ignores phases/Score. Any single condition flags an anomaly.
```

#### 50. `SweepConfig` — class — `config.py:236-240`

```text

    Whale detection on taker sweeps: prints of one side with the same trade time (one taker order walking several
    price levels, the Aggr technique) or within sweep_merge_ms are merged before sizing. The whale size per coin is
    the rolling `percentile` of its sweep sizes (log-histogram decayed hourly), never below the liquidity-tier floor.
    
```

#### 51. `LiquidationConfig` — class — `config.py:267`

```text
Liquidations (Binance !forceOrder@arr is SAMPLED: at most one per symbol per second; Bybit/OKX add more).
```

#### 52. `DepthConfig` — class — `config.py:278-281`

```text

    Local order books (Binance <sym>@depth@500ms diff stream + a 1000-level snapshot, depth.py) of the hot symbols
    only: open cards and active anomalies. Measured 2026-10-05: ~4.3 KB/s per book (depth20 was ~2 KB/s).
    
```

#### 53. `OrderflowConfig` — class — `config.py:319`

```text
Spot-vs-perp veto and footprint / absorption confirmation of entries.
```

#### 54. `MLConfig` — class — `config.py:364`

```text
ml.py: IsolationForest anomalies, GaussianMixture regimes, river P(edge) (see its docstring).
```

#### 55. `LevelsConfig` — class — `config.py:413`

```text
Two-timeframe model (levels.py): 15m impulse + Fibonacci context, 5m structure-shift entry. Rules, not advice.
```

#### 56. `ZonesConfig` — class — `config.py:542-546`

```text

    Level map (zones.py): support / resistance, liquidity pools, estimated liquidation clusters, volume profile,
    order-book walls, VWAP and Fibonacci levels, merged into zones weighted by confluence. Built only for coins
    with cards. The weights are hypotheses; the journal stores which sources each target came from.
    
```

#### 57. `PositioningConfig` — class — `config.py:616`

```text
Other traders' positioning (positioning.py): long/short ratios, Hyperliquid large accounts.
```

#### 58. `PoolsConfig` — class — `config.py:635-643`

```text

    Per-strategy coin pools (pools.py): each strategy trades only its own coins, refreshed hourly. A pool = the
    universe filtered by the strategy's rule (coin classes by 24h volume rank: major = BTC ETH SOL XRP BNB, large =
    rank <= 30, mid = rank <= 80, small = the rest; sectors to exclude; minimum 1h volatility), minus the coins where
    the strategy's journaled entries of the last lookback_days are proven negative (eng-59: block bootstrap + BH) (walk-
    forward on the archive: the worst coins of the last 6 months stayed the worst the next month, -0.39R vs -0.10R;
    picking the best ones did not help), capped at `size` coins by 24h volume. Setups outside the pool are journaled
    with vetoed='not_in_pool'.
    
```

#### 59. `StrategiesConfig` — class — `config.py:681-687`

```text

    Strategies (strategies/): each has its own anchor (a leg, a level or a range), entry, stop and target intent;
    only the stop floor, the R:R check, the card lifecycle and the journal are shared. Timeframe rule: events are
    detected on any data (ticks, 1m), the structure is never finer than 15m, the entry never finer than 5m, and the
    entry timeframe is 3-6x finer than the structure (Elder's factor of ~5): 15m -> 5m, 1h -> 15m, 4h -> 1h. Sizes are
    in 15m ATRs; lifetimes are (waiting, trigger in the zone, open trade) seconds.
    
```

#### 60. `MarketConfig` — class — `config.py:962-968`

```text

    Market crowd of a setup: how many coins produced a directional setup of the same direction within
    cluster_window_sec (live: BTC swept a 15m high and six alts "swept" theirs in the same 5m candle - one market move,
    the alts' setups are its beta). Every confirmed setup stays a card (no limit on their number: the journal and the
    ML models learn from all of them); the crowd is journaled (`market_crowd`) and learned as a feature, stats.py
    splits Edge by it (>= cluster_min = a market move).
    
```

#### 61. `WebConfig` — class — `config.py:975`

```text
Browser dashboard (webui.py), bound to localhost only.
```

#### 62. `RestConfig` — class — `config.py:984`

```text
REST pacing. Binance futures: 2400 weight/min per IP, spot: 6000/min.
```

#### 63. `VenuesConfig` — class — `config.py:1018-1021`

```text

    Extra exchanges that enrich the Binance universe (trades -> aggregated CVD / sweeps, liquidations, OI, funding).
    The universe itself stays the Binance USD-M top list; other venues are mapped onto it by base coin.
    
```

#### 64. `RiskConfig` — class — `config.py:1041-1047`

```text

    Position sizing shown on an entered card (webui.sizing_view): information for the manual trader, never an order.
    - max leverage: the isolated-margin liquidation (about 1/L - maintenance away from the entry) stays at least
      liq_stop_margin x the stop distance away, so a gap through the stop is not a liquidation;
    - position size: only with account_usd > 0 (config.local.toml [risk]); notional so that the stop loses risk_pct of
      the account including the round-trip execution cost.
    
```

#### 65. `NotifyConfig` — class — `config.py:1055`

```text
Optional notifications for a manual trader away from the screen (off by default).
```

#### 66. `BriefingConfig` — class — `config.py:1075`

```text
Telegram briefings / watch alerts (briefing.py) for the coins that lead the market (the owner, 2026-10-05).
```

#### 67. `JournalConfig` — class — `config.py:1098`

```text
Signal journal (journal.py) and outcome tracking.
```

#### 68. `PretrainConfig` — class — `config.py:1136`

```text
pretrain.py: models trained on the Binance public archive before the bot starts (history.py).
```

#### 69. `_coerce` — function — `config.py:1301`

```text
Type-check one override against the default's type (lists become tuples, ints are accepted for floats).
```

#### 70. `apply_overrides` — function — `config.py:1331`

```text
Return `config` with `overrides` ({section: {key: value}}) applied; raises ValueError on unknown/wrong input.
```

### `core/__init__.py`

#### 71. `<module>` — module — `core/__init__.py:1`

```text
Small dependency-free shared functions used by live and research code.
```

### `core/model_provenance.py`

#### 72. `<module>` — module — `core/model_provenance.py:1-6`

```text
Signed-by-provenance metadata for offline model artifacts.

The model itself remains a legacy pickle for reproducibility, but production
loads it only when the adjacent manifest describes the exact artifact and the
feature/logic contract currently running.

```

### `core/provenance.py`

#### 73. `<module>` — module — `core/provenance.py:1-7`

```text
Immutable process provenance captured once at import time.

The service must be able to distinguish rows written by the code loaded in a
running process from later edits made on disk.  Deployment may provide the
values explicitly; the git fallback is only for local runs and never blocks
startup when the checkout metadata is unavailable.

```

### `core/quant_gate.py`

#### 74. `<module>` — module — `core/quant_gate.py:1`

```text
Small, explicit cost-aware gates shared by briefing and scenario analytics.
```

#### 75. `scenario_gate` — function — `core/quant_gate.py:9-14`

```text
Return net EV and the fee-adjusted break-even probability.

    ``reward`` and ``risk`` are positive price distances before costs; cost is
    the round-trip price cost. A missing base probability is reported but does
    not silently become a trade approval.
    
```

### `core/regime.py`

#### 76. `<module>` — module — `core/regime.py:1-4`

```text
Deterministic market regime labels for analytics only.

This module deliberately has no ML dependency and never vetoes a signal.

```

### `core/strategy_engine.py`

#### 77. `<module>` — module — `core/strategy_engine.py:1`

```text
Shared, as-of-bounded strategy and replay execution contract.
```

#### 78. `MarketSnapshot` — class — `core/strategy_engine.py:11`

```text
Immutable market view. Every candle/event must be known at ``asof_ms``.
```

#### 79. `StrategyEngine` — class — `core/strategy_engine.py:34`

```text
Single geometry and replay API shared by live cards and archive replay.
```

### `core/versioning.py`

#### 80. `<module>` — module — `core/versioning.py:1`

```text
Comparable EdgeHunter logic-version helpers.
```

#### 81. `version_no` — function — `core/versioning.py:13`

```text
Return the numeric family while accepting lettered releases (eng-169l/m).
```

#### 82. `same_version` — function — `core/versioning.py:17`

```text
Exact release equality for journal/statistics partitions.
```

### `data_contract.py`

#### 83. `<module>` — module — `data_contract.py:1`

```text
Fail-closed validity checks for production briefing inputs.
```

#### 84. `SystemValidityError` — class — `data_contract.py:7`

```text
P0: required production input is absent or incomplete.
```

#### 85. `SystemValidityGate` — class — `data_contract.py:16`

```text
Fail-closed gate. No partial/degraded production calculation is allowed.
```

### `data_quality.py`

#### 86. `<module>` — module — `data_quality.py:1`

```text
Small, dependency-free data freshness contract shared by fetcher and scanners.
```

### `deploy/mark_dup_untracked.py`

#### 87. `<module>` — module — `deploy/mark_dup_untracked.py:1-2`

```text
eng-132 one-off: UNTRACKED rows 110-112 (2026-10-15 10:04) re-booked the same positions as the EXCHANGE rows 55-57
(identical USD result): mark them so the summaries do not count the $49 twice. Idempotent; run once at the restart.
```

### `depth.py`

#### 88. `<module>` — module — `depth.py:1-31`

```text

Order books of the hot symbols, built the way Binance documents a local book ("How to manage a local order book
correctly"): the <sym>@depth@500ms diff stream, buffered until a 1000-level REST snapshot arrives, events with
u < lastUpdateId dropped, the first applied one spanning lastUpdateId, then every event's `pu` must equal the
previous `u` (else the book is re-synced from a new snapshot). Each event carries absolute quantities: 0 removes a
level. Within a minute of streaming the book reaches far beyond the 1000 levels of the snapshot (any level that
changes is sent): 2026-10-05 the 500-level snapshots of the old design covered BTC only +-0.07% (less than one 0.1%
heat bucket) and ETH +-0.2%.

COVERAGE (eng-80): the REST snapshot holds 1000 levels per side (BTC ~+-0.07%); beyond it the local book knows only
the levels that CHANGED since the sync - a large order that just rests far from the price never appears, which is
exactly what walls / bands look for. So heat snapshots, walls and bands use only the price range the last snapshot
covered (`cov_lo` .. `cov_hi`), and a book whose mid left that range is re-synced (at most every 5 minutes)
from a fresh snapshot (Binance's guidance: keep the book to the depth you actually hold).

Every decrease of a level is split into FILLED (taker trades at that price on that side, from the aggTrade stream,
within ATTRIBUTION_MS) and PULLED (cancelled): liquidity that disappears without trades is the spoofing signature
(~31% of large crypto orders could spoof, arXiv 2504.15908); liquidity that is traded into and stays / refills is
absorption. Additions are counted as ADDED. Per heat bucket and minute: [added, pulled, filled] of each side.

Heatmap (as Bookmap draws it): a snapshot of the whole local book within +-heat_range_pct every heat_snapshot_sec,
bucketed by heat_bucket_pct of price on a grid fixed per coin. Walls: single levels >= wall_multiple x the median
level notional within +-wall_range_pct that stood wall_min_age_sec (book depth refills within 5-10s after a trade -
arXiv 1602.00731 - so a 10s-old order said little). Liquidity bands: heat buckets that held heat_band_multiple x the
snapshot's median bucket in >= heat_band_presence of the snapshots of heat_band_window_sec AND were not mostly
pulled (pulled USD over the window < the band's average resting USD, or fills >= half of the pulls).

What the book is used for is decided elsewhere and measured: depth is context, sweep sizing and the slippage of an
entry; bands / walls are not support or resistance by themselves (no study shows resting depth holds price on an
hours horizon; order-flow imbalance explains price over seconds - Cont, Kukanov & Stoikov 2014).

```

#### 89. `BookState` — class — `depth.py:47`

```text
One coin's local book and everything derived from it.
```

#### 90. `DepthBook.start` — function — `depth.py:117`

```text
A hot coin's diff stream was subscribed: buffer its events until the snapshot arrives.
```

#### 91. `DepthBook.drop` — function — `depth.py:122`

```text
The stream was unsubscribed: the book stops (heat history and bands are kept for the page).
```

#### 92. `DepthBook.active` — function — `depth.py:134`

```text
Coins with a synced live book.
```

#### 93. `DepthBook.wanting_snapshot` — function — `depth.py:138`

```text
Coins whose stream runs but whose book needs a (new) REST snapshot.
```

#### 94. `DepthBook.set_snapshot` — function — `depth.py:163`

```text
REST /fapi/v1/depth (limit 1000): the book from lastUpdateId, then the buffered events.
```

#### 95. `DepthBook.on_trade` — function — `depth.py:194`

```text
aggTrade: a taker SELL executes against the bids at `price`, a taker BUY against the asks.
```

#### 96. `DepthBook._prune` — function — `depth.py:373-380`

```text
Bound changed-depth levels that are outside the actionable window.

        Binance diff streams can report a level after the initial snapshot has
        moved far away.  Those levels are useful only while they are near the
        current market; retaining every changed price makes the Python dicts
        grow with uptime.  Keep the nearest configured levels as a second
        bound, so a thin book cannot be emptied by the percentage filter.
        
```

#### 97. `DepthBook.top` — function — `depth.py:456`

```text
The best n levels per side (iceberg tracking reads the near book as the old depth20 stream gave it).
```

#### 98. `DepthBook.liquidity_bands` — function — `depth.py:465`

```text
Persistent, not-mostly-pulled liquidity bands: [(price, side +1 bid / -1 ask, average USD)].
```

#### 99. `DepthBook.heatmap` — function — `depth.py:476-477`

```text
The coin's heatmap for the page: grid step, per snapshot [epoch ms, [[price, USD +bid / -ask], ...]], and per
        minute the pulled / filled USD per bucket [[minute ms, [[price, bid pulled, bid filled, ask pulled, ask filled]]]].
```

#### 100. `DepthBook.metrics` — function — `depth.py:491-492`

```text
Spread, depth within the configured bands (USD per side), imbalance, the nearest persistent walls, and
        the last 5 minutes' pulled / filled USD within 1% per side.
```

#### 101. `DepthBook.diagnostics` — function — `depth.py:538`

```text
Aggregate sequence/resync counters for health and external diagnostics.
```

#### 102. `DepthBook.wall_history` — function — `depth.py:549`

```text
eng-105: the walls that ended recently and how: broken / eaten (filled) / pulled (cancelled) / faded.
```

#### 103. `DepthBook.sweep_vs_depth` — function — `depth.py:558`

```text
A taker sweep's size relative to the visible liquidity it hits within `band` (> 1 = it ate the book).
```

#### 104. `DepthBook.slippage_bps` — function — `depth.py:573-574`

```text
Average price impact (bps from the touch) of a market order of `usd` walking the live book; None without
        a fresh book or when the book within reach is thinner than the order.
```

### `docs/audit_2026_10_16_followup/checks/a06.py`

#### 105. `<module>` — module — `docs/audit_2026_10_16_followup/checks/a06.py:1`

```text
A06 before / after: temporary SQLite, the exchange calls faked (no network). Run from the tree root.
```

### `docs/audit_2026_10_16_followup/checks/book.py`

#### 106. `<module>` — module — `docs/audit_2026_10_16_followup/checks/book.py:1-2`

```text
A03 / A08 / A10 / A12 / A13 / A15 / S10 before / after. Run: python checks/book.py <repo root>.
Offline: temporary SQLite only, no network, no exchange.
```

### `docs/audit_2026_10_16_followup/checks/review.py`

#### 107. `<module>` — module — `docs/audit_2026_10_16_followup/checks/review.py:1-2`

```text
Reviewer findings 1/2: an inner 1m gap keeps its bucket; the pullback test sees its first partial 15m bar.
Usage: python review.py <repo>
```

### `docs/audit_2026_10_16_followup/checks/review2.py`

#### 108. `<module>` — module — `docs/audit_2026_10_16_followup/checks/review2.py:1-11`

```text
Counterexamples of the independent review of 6b771ba. Usage: python review2.py <repo> (no network, temp SQLite).

1. A06: an order filled in full, its fills listed only in part -> the exit price / fees must come from the order.
2. Prefix invariance of the 1m exit loop: the same minutes managed one hour at a time (live) and in one batch whose
   buffers already hold LATER bars / days (a restart, a stall) must decide the same exit at the same minute.
3. A04: an inner bucket with minutes missing, by the explicit quality policy.
4. FVG across a dropped bucket.

`python review2.py <repo> check` asserts the expected (fixed) results: every mismatch is printed as FAIL and the
script exits 1 - a printed wrong result is not a pass. Without `check` it only prints (the 'before' run on 6b771ba).

```

#### 109. `expect` — function — `docs/audit_2026_10_16_followup/checks/review2.py:28`

```text
want: the expected value, or a callable(got) -> bool. Recorded only in check mode.
```

#### 110. `manage` — function — `docs/audit_2026_10_16_followup/checks/review2.py:108`

```text
(live: an hour of minutes at a time, every buffer cut at that time; batch: one call, buffers hold it all)
```

### `docs/audit_2026_10_16_followup/checks/s01_a16_a04.py`

#### 111. `<module>` — module — `docs/audit_2026_10_16_followup/checks/s01_a16_a04.py:1-2`

```text
S01 (VWAP), A16 (MFI / OBV volume), A04 (incomplete buckets): before / after.
Run: python checks/s01_a16_a04.py <repo root>. Offline, no network / DB.
```

### `docs/audit_2026_10_16_followup/checks/strat.py`

#### 112. `<module>` — module — `docs/audit_2026_10_16_followup/checks/strat.py:1`

```text
A02 / A18 / S04 / S05 / S06 / S11 before / after. Run: python checks/strat.py <repo root>. Offline.
```

### `errors.py`

#### 113. `<module>` — module — `errors.py:1-6`

```text
Visible failures: no exception handler may swallow an error or a missing input silently.

`report(source, exc, detail)` logs a WARNING for the first failure of a source and then at most once per
`WARN_EVERY_SEC` with the number of failures since (per-symbol REST failures would otherwise flood the log), and counts
every failure for the Health line (`health_text`).

```

#### 114. `health_text` — function — `errors.py:40`

```text
'errors: src N, ...' of the failures since the last call ('' when none), then resets the minute's counts.
```

#### 115. `alert_text` — function — `errors.py:48`

```text
'src N, ...' of the failures since the previous call ('' when none): for the Telegram alert, not the Health line.
```

### `event_risk.py`

#### 116. `<module>` — module — `event_risk.py:1-18`

```text

Event risk from Binance's own public data (eng-53; Compass "7 phases" review: scheduled / announced events are the
best-documented driver of dumps):
- the Monitoring Tag (Binance's delisting watch list): the spot product list carries tags['Monitoring'] - live after
  a tag, AVA -4.9%, SCR -7.5%, NFP -12%, WAN -34% within minutes / an hour (BeInCrypto, cryptorank);
- a scheduled delisting of the perpetual: futures exchangeInfo sets the contract's deliveryDate to the removal time
  (an ordinary perpetual carries 2100-12-25) - after Binance's delisting announcement of 2026-04-09: FUN -27.9%,
  MDT -22.8%, FIO -20.5% within minutes.
eng-135: exchange announcements, keyless, polled every 2 minutes (the tags / exchangeInfo stay hourly):
- Binance CMS delisting catalogue (161): "Binance Will Delist A, B on <date>" = a spot delisting - longs vetoed until
  the day after it (a futures delisting shows in deliveryDate above; Alpha / Margin removals are not a coin delisting);
- Binance new listings (48): "Binance Will List X (X)" - journal only ('news');
- Upbit trade notices: "... KRW 마켓 디지털 자산 추가" a KRW listing (journal only: listing effects fade in 1-2 days,
  RockawayX / The TIE), "거래지원 종료" an Upbit delisting and "유의 종목 지정" its warning list - longs vetoed 14 days.
  Upbit tickers can name another coin than Binance's (KRW-EDGE != EDGEUSDT): a false veto only costs a card.
Token unlocks (Keyrock: 90% of 16,000+ unlocks pressure the price for 30 days) need an external calendar: no free one
(DefiLlama emissions answer 402, Tokenomist is a paid API). A failed read keeps the last known state.

```

#### 117. `parse_binance` — function — `event_risk.py:44`

```text
(base, kind, ts, risk_until) of one Binance CMS title; only bases of known perpetuals.
```

#### 118. `parse_upbit` — function — `event_risk.py:61-63`

```text
Titles: "X(X) KRW 마켓 디지털 자산 추가", "... KRW, USDT 마켓 디지털 자산 추가", "신규 거래지원 안내 (KRW, BTC
    마켓)" = a KRW listing; "거래지원 종료" a delisting (vetoed until the removal date in "(11/16 15:00)" or 14 days,
    whichever is later); "유의 종목 지정" the warning list (14 days), "... 해제" lifts it ('upbit_unwarn', no risk).
```

#### 119. `EventRisk.refresh` — function — `event_risk.py:111`

```text
Blocking (run in a thread): both sources; each keeps its last state when its read fails.
```

#### 120. `EventRisk.refresh_news` — function — `event_risk.py:142`

```text
Blocking (run in a thread): Binance delisting / listing catalogues and Upbit trade notices.
```

#### 121. `EventRisk.view` — function — `event_risk.py:191`

```text
The page: every kept announcement, newest first.
```

### `executor.py`

#### 122. `<module>` — module — `executor.py:1-17`

```text

Demo execution on BingX (virtual VST, `open-api-vst`): an eligible card that reaches ENTRY is sent there unless a
configured demo gate (for example `demo_off_setups`, market/basis checks or an exchange constraint) rejects it. Its
result is recorded next to the journal's replay. DEMO ONLY: sandbox mode is forced and cannot be switched off from the
config. Never an order on a real balance.

- ENTRY: a market order sized so the stop costs `risk_pct` of the demo balance (capped by `max_leverage`), then a
  reduce-only stop-market at the card's SL and three reduce-only take-profits (thirds) at TP1 / TP2 / TP3.
- The card finishes (SL / TP3 / CLOSED / INVALID / EXPIRED / MISSED after an entry): open orders are cancelled and
  whatever is left of the position is closed at market.
- Every minute the open demo trades are reconciled: a position the exchange closed (stop / last target) is finalized.
- Each trade is a row of `demo_trades.db` (fills, fees, realized USD, R against the planned stop).

The API key is the owner's (config.local.toml, `[executor] api_key / api_secret`), a trade-only key.
    python executor.py --check           markets, balance, position mode
    python executor.py --test BTC/USDT:USDT    open and close the minimum size (checks order handling)

```

#### 123. `EntryUnknown` — class — `executor.py:78`

```text
audit C02: a market entry whose outcome could not be read back (lost reply + unreadable exchange).
```

#### 124. `EntryNotFilled` — class — `executor.py:82`

```text
The exchange gave a terminal, zero-fill result; no trade row may be created.
```

#### 125. `_finite` — function — `executor.py:86`

```text
x as a finite float, else None (None, '', non-numeric, NaN, +-inf): an exchange field never raises here.
```

#### 126. `_positive` — function — `executor.py:95`

```text
x as a finite float > 0, else None.
```

#### 127. `_coin` — function — `executor.py:101`

```text
The coin of a ccxt symbol, its unit multiplier dropped (audit N05: the shared parser, not '.replace(1000)').
```

#### 128. `basis_reject` — function — `executor.py:107`

```text
eng-169e: the skip reason when BingX's price is off Binance's by more than executor.max_entry_basis, else None.
```

#### 129. `credentials` — function — `executor.py:115-120`

```text
(key, secret) from the service environment only.

    A missing/cleared EnvironmentFile must disable exchange access. Falling
    back to credentials kept in the checkout could silently keep trading after
    an operator attempted an emergency stop.
    
```

#### 130. `DemoExecutor._market_of` — async function — `executor.py:308-312`

```text

        The same contract on BingX, price-checked (a ticker can be a different token there), and the price scale
        BingX's contract has against Binance's: 1000FLOKI on Binance is FLOKI on BingX (scale 1/1000), and the other way.
        Returns (BingX symbol, scale) or (None, reason).
        
```

#### 131. `DemoExecutor._coin_lock` — function — `executor.py:357`

```text
Serialize exchange mutations for one netted exchange coin.
```

#### 132. `DemoExecutor._claim_execution` — function — `executor.py:403`

```text
Persist an idempotency claim before the first exchange mutation.
```

#### 133. `DemoExecutor.regime_mult` — function — `executor.py:534-535`

```text
eng-100: regime_against_mult when the trade runs against BTC's 7-day momentum (the market regime), else 1;
        the TradFi contracts (gold, silver, oil) are exempt.
```

#### 134. `DemoExecutor._place_stop` — async function — `executor.py:548-551`

```text
eng-169j: BingX caps an account at 200 TP / SL orders (110206; 26.10: 69 stops + 131 targets, 30 new trades
        closed at market without a stop). A stop outranks a far target: one TP3 order of a trade still holding all
        three is cancelled and the stop retried (up to twice) - that trade's card closes the last third at market on its TP3
        (on_finish), the same exit.
```

#### 135. `DemoExecutor._stop_fields` — function — `executor.py:567`

```text
Extract the venue stop identity/price from both ccxt and BingX raw order shapes.
```

#### 136. `DemoExecutor._record_stop` — function — `executor.py:579-583`

```text
Persist the actual exchange stop as soon as the create/edit call succeeds.

        A protected position without this ledger identity cannot be rebound safely after a restart.  The old limit-fill
        path placed the order but discarded its response, which left exactly that gap for AT/USDT:USDT.
        
```

#### 137. `DemoExecutor._is_plain_tp3` — function — `executor.py:601-604`

```text
eng-172: a coin with only TWO resting targets gives up the farther one only when it is the TRADE'S OWN TP3 of
        a thirds plan that this module does not close virtually (no virt: on_target never sees it, so no target is
        taken twice) - the card's TP3 closes that third at market (on_finish), as for the three-target coins. A
        trailing plan's TP1 half, a tp0 + TP1 pair or a virtual trade is never cancelled here.
```

#### 138. `DemoExecutor._free_tp_slot` — async function — `executor.py:615-616`

```text
Cancel the farthest take-profit of one coin that has three (eng-172: or two, see _is_plain_tp3) resting - its
        TP3; True if one was cancelled.
```

#### 139. `DemoExecutor._ensure_sl_slot` — async function — `executor.py:642-646`

```text
eng-170 (the owner): a stop always has its slot. Before an entry: with fewer than tpsl_reserve free TP / SL
        slots, far TP3s are cancelled one by one (_free_tp_slot); nothing left to cancel -> the reason the coin is not
        opened (was: the entry filled, the stop failed with 110206, the position was closed at market - NO_STOP).
        A WARNING (10 min apart) from tpsl_warn orders. An unreadable order list lets the entry through: _place_stop
        still frees a slot on 110206.
```

#### 140. `DemoExecutor._cancel_orders` — async function — `executor.py:681-682`

```text
eng-85: cancel a coin's resting orders one by one (all but `keep`; only the stops with stops_only), never the
        blanket cancel-all before the replacement stands: the position is never left without a stop.
```

#### 141. `DemoExecutor._place_tps` — async function — `executor.py:693-697`

```text
The take-profits; a failure leaves the trade tracked with its stop (eng-85: an exception here used to drop
        a stopped position out of self.open, and close_untracked then dumped it at market as UNTRACKED).
        eng-171 (virtual_tps): only the first `on_exchange` parts rest on BingX (tp0 - or TP1 when the trade has no
        tp0; none after the partial), so a position holds its stop + one target (200 TP / SL orders cap, 110206); the
        rest are market reduceOnly exits on the card's TP1 / TP2 events (on_target, `_left_fraction`).
```

#### 142. `DemoExecutor.tp_parts` — function — `executor.py:739-740`

```text
(target index, amount) of the take-profit orders: thirds at TP1-3; eng-58 trailing plans (continuation,
        pump) half at TP1 and the rest on the card's trailing stop (RESTOP); target-less plans none.
```

#### 143. `DemoExecutor.exit_parts` — function — `executor.py:749-750`

```text
eng-105: partial_share of the position at +partial_r R (trade['tp0']), the rest by tp_parts; the plain
        tp_parts when the plan's TP1 is already nearer than that (TP1 is the partial then).
```

#### 144. `DemoExecutor.risk_limit` — function — `executor.py:767-772`

```text

        eng-58, the account's day (prop firms: a daily loss limit of 1-5%, 2-3 trades a day, a pause after a losing
        streak): no new demo trade once the UTC day's closed trades lost daily_loss_r R, after max_trades_day trades
        were opened today, or within pause_hours after pause_losses stops in a row. The numbers are ours, inside the
        prop firms' ranges. Cards and the journal are not limited (they measure the signals).
        
```

#### 145. `DemoExecutor.entry_gate` — function — `executor.py:807`

```text
Apply the shared demo eligibility field, then the optional per-direction cluster limit.
```

#### 146. `DemoExecutor._record_skip` — function — `executor.py:819`

```text
Keep non-trades out of the execution ledger while preserving auditability.
```

#### 147. `DemoExecutor.cluster_hit` — function — `executor.py:831-832`

```text
The coin of a demo entry in direction d within cluster_entry_sec: a filled trade, or a resting limit placed /
        entered in the window (it fills without asking again), else None.
```

#### 148. `DemoExecutor._chase` — function — `executor.py:850`

```text
eng-147: why the BingX price ran too far past the signal price for a plan without targets, else None.
```

#### 149. `DemoExecutor._actual_fill_geometry` — function — `executor.py:863-868`

```text
Validate the exchange fill against the card's *actual* entry geometry.

        The quote used to decide a card is not a fill.  This check is deliberately independent of the requested
        order price and is run after both market and resting-limit fills.  It returns ``(reason, risk, fee)``;
        ``reason`` is None only when the position can be managed by the recorded stop/targets.
        
```

#### 150. `DemoExecutor._close_invalid_fill` — async function — `executor.py:944-950`

```text
Quarantine a confirmed but unusable fill and flatten it immediately.

        The position already exists at this point, so this is an emergency
        reduce-only close rather than an entry veto.  Keep geometry breaches
        separate from slippage-induced R:R breaches in the ledger and exit
        reason so strategy expectancy does not absorb execution damage.
        
```

#### 151. `DemoExecutor.is_limit_plan` — function — `executor.py:1256-1260`

```text

        Plans whose source enters with a resting limit at a price known in advance (trigger 'touch'). eng-58: ICT's
        limits (sweep CE, continuation OTE) rest only inside the London / New York kill zones - outside them the card
        would veto the fill ('killzone'), so the limit is cancelled there (the setup lives within its session).
        
```

#### 152. `DemoExecutor.sync_limits` — async function — `executor.py:1272-1276`

```text

        Every waiting touch card gets a limit order on BingX at its entry line (carried over by the current price
        ratio); a card that ended without an entry gets it cancelled. A zone Binance touched but BingX did not is then
        simply not filled - the trade is the venue's, not Binance's.
        
```

#### 153. `DemoExecutor.check_limits` — async function — `executor.py:1460-1461`

```text
A filled limit becomes a trade (stop + take-profits placed); one the card entered on Binance but BingX did
        not fill within limit_wait_min is cancelled and recorded NOT_FILLED.
```

#### 154. `DemoExecutor._confirmed_order_fill` — async function — `executor.py:1511`

```text
Return an exchange-derived ``(average, amount)``; never use the requested limit as a fill price.
```

#### 155. `DemoExecutor._limit_trade` — function — `executor.py:1540`

```text
The demo row of a filled limit, written before its exits are placed (a failure there still leaves it).
```

#### 156. `DemoExecutor._release_unknown` — async function — `executor.py:1625-1627`

```text
audit T03: a coin held for an entry of unknown outcome is released only once the outcome is resolved - no
        position and no open order of that coin on BingX, read after the minimum hold (a late fill / a resting order can
        still land). The hold was a 900 s timer: a new entry went in without ever confirming the old one.
```

#### 157. `DemoExecutor._restore_db_ownership` — async function — `executor.py:1649-1656`

```text
Rebind exchange positions to an open ledger row after a runtime restart.

        The in-memory card book is intentionally ephemeral.  A single active
        row for the same venue symbol and direction is enough to recover the
        owner; ambiguous rows are left for the normal untracked guard instead
        of being guessed.  ``card_id`` and ``client_order_id`` remain on the
        restored row for later reconciliation.
        
```

#### 158. `DemoExecutor.close_untracked` — async function — `executor.py:1693-1697`

```text
Close only positions with no recoverable ledger owner.

        A missing in-memory card after restart is not proof that the exchange
        position is чужая: active rows are rebound from SQLite first.
        
```

#### 159. `DemoExecutor._dedupe_stops` — async function — `executor.py:1778-1783`

```text
eng-98: one stop per open trade on BingX. Before eng-85 a failed / repeated restop could leave an older stop
        resting beside the live one (live HYPE 14.10: 12 @ 91.47 beside 24 @ 89.72) - it would later cut a new position
        of the coin. The stop nearest the trade's own stop stays, the others are cancelled.
        The guard the other way: an open position with NO stop (a cancel that went through while its replacement
        failed, a close that failed after the take-profits went) gets its stop back at the trade's level, or is closed
        at market when the price is already beyond it.
```

#### 160. `DemoExecutor._left_fraction` — function — `executor.py:1839-1841`

```text
eng-171: the share of the trade's size that stays open once target k is done (thirds of what is left after
        the partial; half at TP1 for the trailing plans). The quantity is derived from the position itself, so a
        repeated or late call (restart, lost event, an exchange tp0 that fired) never closes more than planned.
```

#### 161. `DemoExecutor._cancel_targets` — async function — `executor.py:1848`

```text
Every resting order of the coin except its stops (a virtual exit subsumes the exchange tp0 / TP1).
```

#### 162. `DemoExecutor.on_target` — async function — `executor.py:1858-1859`

```text
eng-171: the card reached TP1 / TP2 (Binance prices, signal_book): the virtual take-profits of a trade
        (virt) are market reduceOnly exits down to `_left_fraction`. Idempotent per target (tp_done, in the db).
```

#### 163. `DemoExecutor.sync_targets` — async function — `executor.py:1903-1904`

```text
eng-171: cards that passed TP1 / TP2 while the bot was down (restart) or whose event was lost: the missed
        virtual exit is made now, not at the next target. No REST call unless a trade really lags.
```

#### 164. `DemoExecutor.on_restop` — async function — `executor.py:1910-1911`

```text
eng-58: the card trailed its stop (after TP1: the entry, then the EMA20): the remaining position's stop is
        moved on BingX (its TP1 half is already out, so no take-profit is left to re-place).
```

#### 165. `DemoExecutor.on_partial` — async function — `executor.py:1995-1998`

```text
eng-155: the card went +partial_r R - partial_share of the position out. A trade opened with its tp0 order
        (exit_parts) has usually given it already (the position is down to the rest: only marked); a trade opened
        before partials were on has none - its take-profits are cancelled, the half closed at market (it may be well
        past +1R by then) and the take-profits re-placed for the rest. The stop is never touched here.
```

#### 166. `DemoExecutor.on_add` — async function — `executor.py:2055`

```text
A Turtle unit added on the card: the same quantity again at market, the stop of the whole position moved.
```

#### 167. `DemoExecutor.strategy_killed` — function — `executor.py:2192-2193`

```text
audit-80, opt-in: a strategy whose last strategy_kill_n closed demo trades sum to <= -strategy_kill_r R
        opens no new demo trade (its cards and the journal go on, so it can earn its way back on paper).
```

#### 168. `DemoExecutor.day_summary` — function — `executor.py:2211`

```text
(strategy, trades, wins, sum R, avg slippage bps) of the trades closed in [day0, day0 + 1 day).
```

#### 169. `DemoExecutor.usd_without_r` — function — `executor.py:2222-2223`

```text
(trades, USD) closed in the day with a dollar result but no R (UNTRACKED: no planned stop) - they fell out
        of every R sum (11 rows, -12.54 USD by 15.10).
```

#### 170. `DemoExecutor._call` — async function — `executor.py:2231-2236`

```text
Read-only ccxt call with bounded total timeout and exponential retry.

        Mutating order calls stay outside this helper so a lost response is
        resolved by clientOrderId/position reconciliation instead of replaying
        an order blindly.
        
```

#### 171. `DemoExecutor._position_of` — async function — `executor.py:2249-2250`

```text
(size, average entry price) of the coin's position on the side d, (0, None) when there is none / unreadable.
        strict: an unreadable position raises instead (audit C02: an API error is no proof of a flat coin).
```

#### 172. `DemoExecutor._resolve_unknown_entry` — async function — `executor.py:2263-2267`

```text
audit N03 / C02: a market entry whose reply was lost (timeout / network). The coin was free before the order
        (one position per coin, one-way mode), so the position read decides: a position found becomes the trade
        (protected by the caller); 'not filled' needs three SUCCESSFUL empty reads, the third >= 14s after the order (BingX's position snapshot lags a few seconds); the waits stay short since the lock is held. When the exchange stays unreadable the
        outcome is UNKNOWN: EntryUnknown is raised (the caller records it and alerts; close_untracked closes a position
        that turns up later). Never retried blindly (a second order would double the position).
```

#### 173. `DemoExecutor._set_exit_ref` — function — `executor.py:2292-2293`

```text
The card's own exit price (Binance) next to the demo's fill: the demo lost ~0.15R a trade to the journal,
        almost all on the card-driven market closes (eng-74) - measured, not guessed.
```

#### 174. `DemoExecutor._close` — async function — `executor.py:2298-2302`

```text

        Out of the trade. The stop rests until the position is flat: only the take-profits (and an older closing limit)
        go first, the stop is cancelled after the position is 0. The cancel-all first left the position without a stop
        whenever the close then failed (any error but 101290 / 102202 raised past it; 102202 left a bare limit).
        
```

#### 175. `DemoExecutor._exit_kind` — async function — `executor.py:2400-2401`

```text
eng-170: 'SL' / 'TP' by the type of the last reduce-only order BingX filled on the coin since the entry
        (STOP_MARKET / TAKE_PROFIT_MARKET); None for a plain market close or an unreadable list.
```

#### 176. `DemoExecutor._finalize` — async function — `executor.py:2420-2425`

```text

        Realized result: OUR quantity x (the exit price - the entry fill), minus taker fees on both sides. The fills'
        prices are right but ccxt's BingX swap fills report the amount in another unit than the position (live REZ:
        33,333,333 for 333,333 coins), so the quantity each exit closed is its ORDER's filled amount (_exit_summary),
        and right after a close the exit fill may not be listed yet (retried).
        
```

#### 177. `DemoExecutor._funding_paid` — async function — `executor.py:2489`

```text
Sum of BingX's FUNDING_FEE ledger entries of the coin in [since, until] (USDT, signed), None unreadable.
```

#### 178. `DemoExecutor._exit_fills` — function — `executor.py:2501-2505`

```text
eng-91: only exit-side fills after this trade's entry (the 1s margin covers BingX's clock; the 5s fetch
        margin let the previous trade's exit on the same coin in) and not after its close (+2 min for a fill listed
        late): _refinalize retried for 3 days and took the NEXT trades' exits on the coin into this one's result; the +2 min
        ends before the next trade on the coin opened (_refinalize passes its opened_ms - 14s; with this 1s margin, 15s:
        its entry fill is on the same side when it is the opposite direction).
```

#### 179. `DemoExecutor._exit_summary` — async function — `executor.py:2510-2515`

```text
(exit price, quantity closed, exit fees in USDT) of the listed exit fills' ORDERS, all three from each order
        itself (fetch_order): filled = executedQty in the position's unit, average = avgPrice over ALL its fills,
        fee = commission over all its fills. The fills only name the orders: a fill list missing part of an order no
        longer prices the whole order at the listed part (review of 6b771ba). Not proven -> (None, 0, None): a fill
        without an order id, an order not readable, still working (open: more fills may come), without filled /
        average, or without a reported fee (audit A06: no estimated result).
```

#### 180. `DemoExecutor._next_entry_cutoff` — function — `executor.py:2549-2552`

```text
audit N01: where the next trade on the coin begins. Its entry order's own fill time when the row carries the
        order id (exact: this trade's exit is never cut); for older rows without it, the row's opened_ms - 14s (a
        limit's opened_ms is when check_limits SAW the fill, a market entry's after fetch_order's retries) - that
        margin can drop an exit made in the last 15s before the next entry, which is why the id is stored now.
```

#### 181. `DemoExecutor._fees` — function — `executor.py:2564-2565`

```text
The entry side at the configured taker rate (an estimate: the entry order's commission is not stored),
        the exit side as BingX charged it on the exit orders (_exit_summary).
```

#### 182. `DemoExecutor._refinalize` — async function — `executor.py:2569-2570`

```text
Closed trades whose exit fill was not listed at the close (1000PEPE 2026-10-06 11:07, the link failing):
        their result from BingX's fills, retried for 3 days.
```

#### 183. `DemoExecutor.reconcile_loop` — async function — `executor.py:2620`

```text
Finalize demo trades the exchange closed on its own (stop / last target).
```

#### 184. `DemoExecutor._set_basis` — function — `executor.py:2738`

```text
BingX vs Binance at the entry (journaled: the venue gap the demo trades through).
```

### `extdata.py`

#### 185. `<module>` — module — `extdata.py:1-21`

```text

Public data beyond the streams (verified live 2026-09-30), all REST, light on bandwidth; context for the journal /
stats / P(edge), never a trigger until the journal proves one:

- Deribit (no other source has options): the DVOL implied-volatility index of BTC / ETH (hourly candles) and the
  put / call open-interest ratio of each one's options (get_book_summary_by_currency) -> market_state
  `dvol_btc`, `dvol_chg_1h`, `pc_oi_btc`; a DVOL jump is logged as a market anomaly.
- Hyperliquid `predictedFundings`: the NEXT funding of Binance, Bybit and Hyperliquid for every coin in one call ->
  per coin `funding_spread` (max - min of the venues' 8h-equivalent rates): crowding on one venue.
- OKX `rubik/stat/taker-volume` (5m taker buy / sell of each coin's contracts): the OKX flow windows are seeded at
  start-up for the minutes before the streams (Binance's are seeded from its 1m klines).
- eng-133 (shadow features, journaled, never a filter): Binance TradFi perpetuals (gold, WTI oil, SPY, QQQ) 1h / 24h
  changes, the US cash-session flag, the previous day's CBOE VIX close, the Fear & Greed index and the spot-ETF net
  flow (tools/farside_flows.py writes etf_flows.json; a day D is visible from D+1 08:00 UTC: no look-ahead).
- Order books of OKX (`market/books`, 50 levels) and Bybit (`market/orderbook`, 50) for the hot coins every 60s ->
  per coin `okx_book_imb` / `bybit_book_imb`: (bid - ask) / (bid + ask) within 0.5% of the mid (Binance has its own).
- eng-134 (shadow, journaled, never a filter): Upbit's KRW tickers (all markets in one keyless call, every 60s) ->
  per coin `kimchi_prem` % = the KRW price / Upbit's own KRW-USDT / the Binance futures price - 1 (no FX source
  needed), computed at the card; NULL when the snapshot or the coin's last Upbit trade is older than 3 min, the coin
  is not on Upbit, or |premium| > 30% (a ticker shared by two different coins).

```

#### 186. `okx_taker_rows` — function — `extdata.py:61-66`

```text
Normalize OKX Rubik taker-volume rows to (timestamp_ms, sell, buy).

    The endpoint returns strings and has historically returned both millisecond
    and second timestamps in fixtures. Invalid rows are discarded by the
    caller's counter instead of being interpreted as zero flow.
    
```

#### 187. `okx_completed_bucket` — function — `extdata.py:90`

```text
Return a 5m bucket start for either OKX timestamp convention.
```

#### 188. `us_session` — function — `extdata.py:99-101`

```text
1 = the NYSE regular session (09:30-16:00 New York, 13:00 on early closes) is open, 0 = closed. The holidays and
    early closes come from us_calendar.json (tools/farside_flows.py writes it from exchange_calendars: pandas stays out
    of the bot); without the file the weekday and the hours alone decide.
```

#### 189. `etf_flows_visible` — function — `extdata.py:121`

```text
(last visible day's net flow, sum of the last 3 visible days) in USD m; a day D counts from D+1 08:00 UTC.
```

#### 190. `ExternalData.macro_loop` — async function — `extdata.py:178`

```text
TradFi perpetuals every 5 min; VIX / Fear & Greed / ETF file every 30 min. Journal context only.
```

#### 191. `ExternalData._upbit_ticker_chunk` — async function — `extdata.py:253`

```text
Fetch one ticker batch, isolating a stale/delisted code without dropping all KRW prices.
```

#### 192. `ExternalData.kimchi` — function — `extdata.py:313`

```text
Upbit premium % of a coin over its Binance futures price; None when stale / not listed.
```

#### 193. `ExternalData.seed_okx_flow` — async function — `extdata.py:390`

```text
Once, after the streams started: 5m OKX taker volume of the 15 minutes before them into the flow windows.
```

### `fetcher.py`

#### 194. `MarketData.alt_spot_trade` — function — `fetcher.py:164`

```text
A Bybit spot trade into the current minute; a new minute closes the last one into spot_minute_klines.
```

#### 195. `MarketData.record_ticker` — function — `fetcher.py:193`

```text
ticker: {'last', 'quoteVolume'} (ccxt shape: the REST 24h tickers every few minutes).
```

#### 196. `MarketData.record_price` — function — `fetcher.py:204`

```text
Last futures trade price, one sample per second (Tier-0 5m price change).
```

#### 197. `MarketData.seed_minutes` — function — `fetcher.py:220-224`

```text

        Closed 1m candles from REST merged over the streamed ones (REST is the closed authoritative value): flows, RVOL, absorption,
        the entry trigger and its confirmations work right after a start instead of after an hour of streaming.
        The futures closes also seed the price samples of Tier-0's 5m price change.
        
```

#### 198. `MarketData.seed_oi` — function — `fetcher.py:244`

```text
Older OI samples (REST history) merged under the live ones: the 5m OI change is known right after start.
```

#### 199. `MarketData._add_closed_minute` — function — `fetcher.py:319-323`

```text

        Build the 15m candle from closed 1m candles (open of the first, high / low extremes, close of the last,
        summed quote and taker-buy volume): exactly the exchange's 15m candle, without a second kline stream per
        symbol (the 15m stream pushed as often as the 1m one and doubled the bandwidth).
        
```

#### 200. `MarketData._replace_closed_bucket` — function — `fetcher.py:354`

```text
Rebuild a 15m aggregate after a late correction to an already closed minute.
```

#### 201. `MarketData.live_candle` — function — `fetcher.py:401`

```text
The in-progress 15m candle: the closed minutes of the bucket plus the live minute.
```

#### 202. `MarketData.drain_kline_rows` — function — `fetcher.py:414`

```text
Finalized candles since the last scan, then (optionally) the in-progress one.
```

#### 203. `MarketData.closed_until` — function — `fetcher.py:424`

```text
Open time of the newest finalized candle of the base market (spot when listed, else futures).
```

#### 204. `_pct_change` — function — `fetcher.py:444`

```text
Change of the last sample vs the first one at least ~window old (time-ordered samples, bisect lookup).
```

#### 205. `_top_strikes` — function — `fetcher.py:463-464`

```text
The strikes holding the most option open interest (in coins) over the two nearest Deribit expiries:
    [(strike, oi, calls share, expiry 'DDMMMYY')].
```

#### 206. `DataFetcher` — class — `fetcher.py:489-497`

```text

    Binance REST (ccxt, through RestGate) for candle history, OI and journal outcomes; own WebSocket clients
    (venues.py) for everything live:
    - Binance spot + futures klines (15m, 1m), futures aggTrade for every symbol (CVD, sweeps / whales,
      footprint), !forceOrder@arr (liquidations), !markPrice@arr@1s (funding, mark, basis), !miniTicker@arr
      (price + 24h volume, Tier-0) and <sym>@depth20@500ms for hot symbols (dynamic);
    - Bybit / OKX / Hyperliquid / Bitget futures and Coinbase spot: trades, liquidations, OI and funding mapped
      onto the Binance universe (symbols.SymbolMap), aggregated in flow.FlowStore.
    
```

#### 207. `DataFetcher.liq_bucket` — function — `fetcher.py:502`

```text
eng-151: one long liquidation into its 5m bucket (stale buckets pruned at each new bucket).
```

#### 208. `DataFetcher._load_markets_off_loop` — async function — `fetcher.py:623-626`

```text

        ccxt parses market lists (thousands of dicts) synchronously; on the event loop that blocked everything for
        ~2s at start. A synchronous ccxt instance loads them in a worker thread and the async one receives the result.
        
```

#### 209. `DataFetcher.load_venues` — async function — `fetcher.py:645-649`

```text

        Instrument lists and last prices of the other venues, loaded and parsed in worker threads (synchronous ccxt:
        parsing thousands of markets on the event loop blocked it); failures only disable that venue. Mappings
        whose price shows a different token under the same ticker are dropped before anything is subscribed.
        
```

#### 210. `DataFetcher._rest_call` — async function — `fetcher.py:700`

```text
Every REST call: proactive weight budget per priority, shared pause on 429/418 (ratelimit.RestGate).
```

#### 211. `DataFetcher._refresh_funding_info` — async function — `fetcher.py:723`

```text
Funding interval per symbol (/fapi/v1/fundingInfo lists only non-default ones; default is 8h).
```

#### 212. `DataFetcher._oi_loop` — async function — `fetcher.py:769-773`

```text

        Binance has no OI stream: poll every symbol once per oi_update_interval_sec, each at its own evenly spread
        slot, with a few requests in flight. Sequential polling took ~0.4s per request over this link, so one pass
        over 300 symbols took ~2 minutes and the 5m OI change often found no baseline sample.
        
```

#### 213. `DataFetcher._record_venue_oi` — function — `fetcher.py:808-809`

```text
native: the venue's own contract count when known (Binance) - audit C08: native rebuilt as USD (x last) /
        mark turned a constant OI into native x last / mark, a false change whenever last and mark moved apart.
```

#### 214. `DataFetcher._binance_rest_tickers_loop` — async function — `fetcher.py:818-821`

```text

        Funding / mark / index for every contract (premiumIndex, weight 10) every 30s and the 24h volumes (weight 40)
        every 5 min: the same numbers the whole-market streams pushed every second, at a tiny share of the bandwidth.
        
```

#### 215. `DataFetcher._bulk_deriv_loop` — async function — `fetcher.py:877-880`

```text

        OI and funding of every Bybit / Bitget contract in one public REST call per venue every 30s (2 requests a
        minute, far below their limits), instead of ticker streams pushing thousands of messages a second.
        
```

#### 216. `DataFetcher._coinbase_prices_loop` — async function — `fetcher.py:902-905`

```text

        Last prices of every Coinbase spot product in one public call a minute: the Coinbase premium of a coin whose
        live trades are older than coinbase_max_age_sec (thin USD books trade minutes apart) comes from it.
        
```

#### 217. `DataFetcher.deriv_snapshot` — function — `fetcher.py:975-980`

```text

        Aggregated positioning across venues: OI change over 5m / 1h (each venue's % change weighted by its current
        OI in USD, so unit and contract-size differences cancel), OI-weighted 8h funding, venues reporting.
        Cached per coin for DERIV_CACHE_MS: the inputs update every 10-60s, and recomputing all venues' windows
        for 300 coins on every 2s Tier-0 pass was a tenth of the event loop's busy time (profiled).
        
```

#### 218. `DataFetcher.fetch_top_symbols` — async function — `fetcher.py:1028`

```text
The universe: the candidates' data-complete subset (fetch_candidates -> select_universe).
```

#### 219. `DataFetcher.fetch_candidates` — async function — `fetcher.py:1032-1035`

```text

        USD-M perpetuals above the volume floor, most liquid first; refreshes the reference prices (the other venues'
        mapping check), the spreads (bookTicker, weight 5) and the ids of every USDT perpetual (market baseline).
        
```

#### 220. `DataFetcher._book_too_thin` — function — `fetcher.py:1101-1102`

```text
The 20 levels of the book do not hold one max_notional order (its slippage is unmeasurable); a thin but
        measurable book stays - its slippage goes into the costs (levels.BOOK_SLIP) and the R:R decides.
```

#### 221. `DataFetcher._refresh_book_slippage` — async function — `fetcher.py:1106-1112`

```text

        eng-124: the tradable universe needs order-book depth AT THE POSITION SIZE, not only volume / spread (CoinAPI,
        tradable universe): per candidate the slippage of a market order of executor.max_notional_usd walked through
        the REST book (20 levels, weight 2), worst side, in bps -> self.book_slip and levels.BOOK_SLIP, the floor of the
        coin's slippage in the costs (R:R, sizing). select_universe drops only a coin whose 20 levels do not hold the
        order. Unknown (no book / failed call) passes, as an unknown spread does.
        
```

#### 222. `DataFetcher.select_universe` — function — `fetcher.py:1151-1155`

```text

        The most liquid candidates with complete data (CONFIG.exchange): a Binance spot pair, enough other futures
        venues, enough history, a tradable spread; at most max_pairs. Venue coverage comes from every venue's
        instrument list (SymbolMap.coverage), so it is known for coins that are not in the universe yet.
        
```

#### 223. `DataFetcher._to_spot_symbol` — function — `fetcher.py:1229`

```text
Convert futures symbol (BTC/USDT:USDT) to spot symbol (BTC/USDT).
```

#### 224. `DataFetcher._normalize_1000x_symbol` — function — `fetcher.py:1235`

```text
Normalize 1000x futures symbol to spot equivalent, e.g. 1000PEPE/USDT:USDT -> PEPE/USDT.
```

#### 225. `DataFetcher.needs_alt_spot` — function — `fetcher.py:1241`

```text
A universe coin whose spot market is Bybit's (no Binance spot pair): its Bybit spot trades are streamed.
```

#### 226. `DataFetcher._spot_symbol_for` — function — `fetcher.py:1246`

```text
Spot pair for a futures symbol: same name, else the un-prefixed 1000x name (1000PEPE -> PEPE).
```

#### 227. `DataFetcher.get_volume_multiplier` — function — `fetcher.py:1254`

```text
The contract's coin multiplier: 1000 for 1000PEPE, 1e4 for 10000WEN, 1e6 for 1000000MOG / 1MBABYDOGE, else 1.
```

#### 228. `DataFetcher.fetch_minute_klines` — async function — `fetcher.py:1280-1284`

```text

        `count` futures 1m klines starting with the first full minute after start_ms (journal outcomes), so the
        signal's own minute never leaks into the outcome. None when the request failed (retry later), [] when the
        exchange has no data.
        
```

#### 229. `DataFetcher.minute_holes` — function — `fetcher.py:1298-1299`

```text
eng-161: the missing closed minutes inside a 1m buffer (after its first minute, within the last `window`
        minutes up to closed_until) - the holes levels.resample drops 5m / 15m bars for ('1m gaps dropped').
```

#### 230. `DataFetcher.patch_minute_holes` — async function — `fetcher.py:1309-1310`

```text
eng-161: refill the futures 1m holes of a universe coin from REST (a stream reconnect leaves them for good:
        seed_minutes ran only at start-up / join). Returns the minutes still missing afterwards.
```

#### 231. `DataFetcher._seed_minutes` — async function — `fetcher.py:1345`

```text
The streams' 1m history (futures 4h, spot 1h) from REST at start-up / when a coin joins (MarketData.seed_minutes).
```

#### 232. `DataFetcher._seed_oi` — async function — `fetcher.py:1365-1369`

```text

        The last day of 5m OI history (289 points, weight 0): Tier-0's 5m OI change and the entries' 1h OI
        confirmation work from the start (with 3 points every confirmation of the first hour had no OI reading), and
        the OI robot's 24h OI growth (MarketData.oi_5m).
        
```

#### 233. `DataFetcher.load_htf_background` — function — `fetcher.py:1397`

```text
load_htf without waiting for it (at most one request set per coin in flight).
```

#### 234. `DataFetcher.load_htf` — async function — `fetcher.py:1405-1408`

```text

        1h klines (~4 days) and 1h open-interest history of one card coin for the level map (zones.py), refreshed at
        most every zones.htf_refresh_sec. Klines weigh 1 (limit < 100), openInterestHist 0 (own 1000 / 5 min limit).
        
```

#### 235. `DataFetcher.chart_candles` — async function — `fetcher.py:1447`

```text
15m and 5m candles of any futures symbol for the web chart (coins no longer in the universe).
```

#### 236. `DataFetcher.light_candles` — async function — `fetcher.py:1467-1468`

```text
1h / 4h / daily / weekly candles of any listed USDT perpetual for the web analysis (a coin outside the
        universe), cached 5 min: [ts, o, h, l, c, quote volume] rows and the last price.
```

#### 237. `DataFetcher._closed_only` — function — `fetcher.py:1501-1504`

```text

        Drop the in-progress candle (and one that closed < 3s ago, which REST may still be completing): frames hold
        closed candles only; a partial REST row taken for a closed one gave candles with a few seconds of volume.
        
```

#### 238. `DataFetcher._load_frame` — async function — `fetcher.py:1509`

```text
REST candles (closed only) for one market as RAW_SCHEMA plus the open time of the newest one.
```

#### 239. `DataFetcher.create_market_data` — function — `fetcher.py:1532`

```text
Empty MarketData per symbol so streams can start before the REST history arrives.
```

#### 240. `DataFetcher.apply_universe` — function — `fetcher.py:1539-1542`

```text

        Switch to a new universe: new symbols get MarketData, dropped ones are removed unless listed in `keep`
        (open cards finish on the old data). Returns (added, removed); the caller restarts streams and loads history.
        
```

#### 241. `DataFetcher._hourly_candles_loop` — async function — `fetcher.py:1562-1566`

```text

        1h candles (limit 200 = ~8 days, weight 2) of every universe coin, refreshed a minute after each hour: the
        pools of previous day / week / sessions and the coins' trends must exist for all 300 coins, not only for card
        coins (~600 weight per hour against a ~1400 / minute budget). Waits for the 15m history first (priority).
        
```

#### 242. `DataFetcher._h4_candles_loop` — async function — `fetcher.py:1616`

```text
200 closed 4h candles of every universe coin (limit 200, weight 2) after each 4h close and for joining coins.
```

#### 243. `DataFetcher._daily_candles_loop` — async function — `fetcher.py:1650-1653`

```text

        Up to 1500 daily candles of every universe coin (weight 10) once per UTC day, a minute after the daily close,
        and for coins that join: Connors' RSI(2) system reads daily closes (~240 weight a day).
        
```

#### 244. `DataFetcher._dominance_loop` — async function — `fetcher.py:1704-1708`

```text

        BTC and USDT dominance (CoinGecko /global, free, no key) every 5 minutes: rising together = risk-off, falling
        together = money into altcoins (practice, not a measured rule: journaled as `_dom` on every entry until the
        journal can judge it; the archive has no dominance history).
        
```

#### 245. `DataFetcher._external_loop` — async function — `fetcher.py:1743-1750`

```text

        eng-72, public sources off the Binance REST budget (urllib in a thread; the funding interval is already handled:
        _funding_info normalises every rate to 8h):
        - ForexFactory's week calendar hourly (macro_calendar.LIVE: USD high / medium events; the high ones join the
          entry blackout, the briefing lists them);
        - Deribit every 5 min: DVOL (30-day implied volatility) of BTC / ETH, and every 30 min the option open interest
          by strike of the nearest expiries (self.options: context for the briefing - unproven as levels).
        
```

#### 246. `DataFetcher.htf_bias` — function — `fetcher.py:1808-1809`

```text
The top-down bias of the coin and of BTC (strategies/bias.py) from their closed daily / 4h / weekly candles:
        {'coin': {...}, 'btc': {...}, 'range_mid': the coin's 20-day range middle}.
```

#### 247. `DataFetcher.dominance_reading` — function — `fetcher.py:1846`

```text
{btc_d, usdt_d, btc_d_1h, usdt_d_1h, btc_d_4h, usdt_d_4h} (changes in percentage points) or None.
```

#### 248. `DataFetcher._day_pocs_loop` — async function — `fetcher.py:1859-1862`

```text

        Each universe coin's POCs of its last 4 completed UTC days, from 5 days of 5m candles (limit 1440, weight 10),
        once per UTC day a few minutes after the close and for coins that join (~700 weight a day).
        
```

#### 249. `DataFetcher._weekly_candles_loop` — async function — `fetcher.py:1897-1900`

```text

        Weekly candles of every universe coin (limit 60, weight 1): the weekly trend reference (weekly_ref), loaded
        once per weekly candle (Monday 00:00 UTC) and for coins that join; hourly check, ~150 weight a week.
        
```

#### 250. `DataFetcher._seasonal_loop` — async function — `fetcher.py:1935-1939`

```text

        Each coin's time-of-day volume / volatility profile from its last 4 weeks of 1h candles (limit 672, weight 5),
        once a day after the 15m history (indicators.seasonal_factors): Tier-0's RVOL and z-scores compare a minute
        with the same hour instead of the flat 24h average. New coins get theirs on the next pass.
        
```

#### 251. `DataFetcher.fetch_rest_baselines` — async function — `fetcher.py:1964-1968`

```text

        Background cold start: fill candle history symbol by symbol (highest volume first) with bounded
        concurrency plus a fixed delay; the RestGate budget keeps the burst below Binance's weight limit.
        Streams and Tier-0 already run meanwhile; a symbol joins phase scoring once its history is in.
        
```

#### 252. `DataFetcher.request_backfill` — function — `fetcher.py:2011-2014`

```text

        Re-download a symbol's candles after a stream gap (reconnect, missed candle close); `need_ts` = open time of
        a candle the snapshot must contain (REST publishes a closed candle a few seconds late: retry until it does).
        
```

#### 253. `DataFetcher._klines_to_df` — function — `fetcher.py:2116`

```text
Binance kline rows -> RAW_SCHEMA (base volume in the instrument's own units).
```

#### 254. `DataFetcher._attach_oi_history` — function — `fetcher.py:2133`

```text
Put OI snapshots onto candles: openInterestHist timestamps are period END times, so 12:15:00 closes the 12:00 candle.
```

#### 255. `DataFetcher._binance_plans` — function — `fetcher.py:2164`

```text
(market, name, raw stream names, streams per socket) of the static Binance groups; fills _binance_keys.
```

#### 256. `DataFetcher.restart_streams` — async function — `fetcher.py:2216-2217`

```text
After a universe change: every static stream moves to the new symbol set by diff (audit-80: the sockets
        stay up; only a group that did not exist yet is started).
```

#### 257. `DataFetcher.track_from` — function — `fetcher.py:2237-2238`

```text
Start collecting the Binance futures trades of `symbol` from `since_ms` (a card's entry) to the end of its
        minute (the trades kept, so a query's interval is exact - audit C04).
```

#### 258. `DataFetcher.tracked_of` — function — `fetcher.py:2256-2258`

```text
The trades of `symbol` in [since_ms, until_ms): {'hi', 'lo'} (None when no trade), 'pending' while no
        trade at / after until_ms arrived yet, None when not tracked or a trade was lost. audit C04: a trade at /
        after until_ms closes the observation but is not part of the interval.
```

#### 259. `DataFetcher.maintain` — function — `fetcher.py:2460`

```text
Periodic housekeeping from the Tier-0 loop: close finished sweeps, decay whale histograms.
```

#### 260. `DataFetcher.set_hot` — async function — `fetcher.py:2472`

```text
Order books (Binance) and Hyperliquid trades for the hot symbols only.
```

#### 261. `DataFetcher._book_sync_loop` — async function — `fetcher.py:2501-2505`

```text

        Local books of the hot symbols (depth.py): a 1000-level REST snapshot (weight 20) for every book whose diff
        stream is buffering - at its start and after a sequence gap. The snapshot is taken a second after the first
        buffered event (Binance: buffer first, then fetch, so the snapshot overlaps the buffered events).
        
```

#### 262. `DataFetcher.set_footprint` — function — `fetcher.py:2538-2544`

```text

        Footprint accumulation for EVERY universe coin (the last Footprint.KEEP_MINUTES), bucketed by
        `footprint_bucket_pct` of price (one fixed bucket per coin: a size change would mix two grids). Before
        (2026-10-05) only cards waiting in a zone had one, so the systems entering at their signal's close (ORB,
        Bollinger, VA80, pump, OI signal: 14 positive order-flow readings in 217 entries) were never judged by it.
        `zone`: symbol -> the card's 15m ATR, kept for the absorption test.
        
```

#### 263. `DataFetcher.orderflow_confirm` — function — `fetcher.py:2556-2560`

```text

        Order-flow confirmation of an entry in the zone: 'imbalance' (stacked diagonal imbalances on the trade side
        in the footprint) or 'absorption' (a heavy 1m delta AGAINST the trade that barely moved price: the
        aggressive side was absorbed by resting orders). None when neither happened.
        
```

#### 264. `DataFetcher._warn_no_oi` — function — `fetcher.py:2573-2575`

```text
No OI reading for a confirmation: once per coin per 30 minutes (it was logged on every 10 s evaluation of an
        open card), with what the samples looked like - oi_change() needs two samples >= 5 minutes apart inside the
        hour and the newest one <= 3 minutes old.
```

#### 265. `DataFetcher.confirmations` — function — `fetcher.py:2590`

```text
Entry confirmations (strategies.confirm): flow, spot, OI, order flow at the extreme.
```

#### 266. `DataFetcher.confirmations.venue_delta` — function — `fetcher.py:2614`

```text
Net taker USD of the venues whose ring covers the window; None when none does (no reading, not 0).
```

#### 267. `DataFetcher.profile_context` — function — `fetcher.py:2667-2668`

```text
For the optimized profiles (strategies/profiles.py), as research_optimize.py measured them: BTC's 1h EMA50
        slope over 10 closed hours and the coin's Wilder ATR14, using bars closed by until_ms.
```

#### 268. `DataFetcher.indicator_panel` — function — `fetcher.py:2689-2690`

```text
{'15m': {rule: bool}, '1h': {...}} on the candles closed by until_ms: the 499-candle REST histories
        (refreshed hourly) extended by the 1m stream's closed buckets since.
```

### `flow.py`

#### 269. `<module>` — module — `flow.py:1-11`

```text

Order flow state shared by every venue, kept as fixed-size numpy ring buffers instead of per-trade Python objects.

- FlowStore: per venue, per symbol, per epoch second: taker buy USD, taker sell USD, long / short liquidation USD
  and the trade count. Writing is O(1) in the hot path; window sums (60s .. 1h) are computed for all symbols at once.
- SweepTracker: merges prints of one taker (same side, same trade time or within sweep_merge_ms) into one sweep
  before sizing, so an order that walks several price levels counts as one big order (the Aggr technique).
- WhaleBook: per-symbol log-histogram of sweep sizes (decayed hourly) -> whale size = rolling percentile, floored
  by liquidity tier; keeps whale sweeps and notable sweeps for algo-cluster (TWAP-like) detection.
- Footprint: bid x ask volume per price bucket per minute for the few symbols waiting for an entry.

```

#### 270. `VenueFlow` — class — `flow.py:33-38`

```text

    Ring buffer of one venue: data[second % H, field, symbol_row]. Second-major: advancing one second zeroes ~5 KB
    of contiguous memory and a window sum reads one contiguous block. The symbol-major layout it replaced touched
    ~1600 pages per venue every second (one per row and field), kept the whole buffer hot and stalled the loop
    whenever the machine had paged it out.
    
```

#### 271. `VenueFlow.covers` — function — `flow.py:64-65`

```text
Audit B11: [a, b) lies after the ring started and crosses no recorded transport gap; with `row` (audit V06)
        also after this venue's first print of that coin.
```

#### 272. `VenueFlow.advance` — function — `flow.py:76`

```text
Move the head to `sec`, zeroing the slots of the seconds skipped since the last write.
```

#### 273. `VenueFlow._span_sum` — function — `flow.py:113-117`

```text

        Per-row sum over seconds [start_sec, end_sec) as at most two contiguous slices of the ring (views, no copy).
        Fancy indexing copied the whole window first: ~90 MB per refresh of the 1h window over all venues, which
        blocked the event loop for about a second.
        
```

#### 274. `VenueFlow.window` — function — `flow.py:125`

```text
Per-row sum over the last `seconds` seconds up to now_sec (inclusive).
```

#### 275. `VenueFlow.row_range_sum` — function — `flow.py:131-132`

```text
One row's sum over [start_sec, end_sec): the whole-matrix range_sum then one row cost ~1s on the loop per
        call (the whale forced-flow check ran it on every sweep).
```

#### 276. `VenueFlow.range_sum` — function — `flow.py:145`

```text
Per-row sum over [start_sec, end_sec) (seconds still inside the buffer only).
```

#### 277. `FlowStore.seed_minute` — function — `flow.py:210-211`

```text
A closed minute from REST (a kline's taker buy / total quote volume) at its middle second: the 5m windows
        are valid right after a start instead of 5 minutes later. Only minutes before the streams started.
```

#### 278. `FlowStore.liquidation` — function — `flow.py:233`

```text
side_liquidated: +1 a long position was liquidated (a forced sell), -1 a short (a forced buy).
```

#### 279. `FlowStore.symbol_range` — function — `flow.py:273`

```text
One field summed over [start_sec, end_sec) across every venue for one symbol (seconds still buffered).
```

#### 280. `FlowStore.snapshot` — function — `flow.py:295-299`

```text

        Per symbol, the live order-flow metrics used by Tier-0, scoring and the dashboard:
        cvd_<w> (Binance futures), agg_cvd_<w> (all futures venues), agg_spot_cvd_5m (spot venues),
        liq_long_5m / liq_short_5m (all venues, USD), venue shares of the 5m gross flow.
        
```

#### 281. `FlowStore.quality` — function — `flow.py:336-342`

```text
Return a real coverage verdict for a symbol's futures flow window.

        ``snapshot`` intentionally emits zero-valued metric keys for every registered symbol.  Key presence therefore
        cannot mean that a venue actually delivered data.  This method checks the ring-buffer start, per-symbol first
        print, transport gaps and the freshness bound for the requested window.  Binance must be covered when it is
        configured; otherwise at least half of the configured futures venues must be live.
        
```

#### 282. `FlowStore.micro_features` — function — `flow.py:358-366`

```text

        eng-59 journal features (context only, no rule uses them):
        - vpin: Easley, Lopez de Prado & O'Hara (2012) volume-synchronized probability of informed trading - the last
          hour's futures taker volume of all venues cut into `buckets` equal-volume buckets, mean |buy - sell| / bucket
          volume (exact taker sides, so no bulk classification);
        - vol_entropy: Shannon entropy of the hour's per-minute volume / ln(60): 1 = spread evenly, low = bursts;
        - lead_venue / lead_corr: the futures venue whose per-minute net taker flow best predicts the NEXT minute's
          Binance return over the hour (correlation; who moves first). `minutes`: final futures 1m candles.
        
```

#### 283. `SweepTracker` — class — `flow.py:469`

```text
Per venue and symbol, the sweep being built; emits finished sweeps to `on_sweep`.
```

#### 284. `SweepTracker.flush` — function — `flow.py:491`

```text
Emit sweeps whose merge window has passed (no newer print arrived to close them).
```

#### 285. `WhaleBook.set_ranks` — function — `flow.py:525`

```text
Liquidity-tier floors from the 24h-volume rank (index 0 = most liquid).
```

#### 286. `WhaleBook.thresholds` — function — `flow.py:547`

```text
(whale size, notable size or None while unknown) in USD for the symbol.
```

#### 287. `WhaleBook.maintain` — function — `flow.py:578`

```text
Hourly decay of the size histograms; call from a periodic loop.
```

#### 288. `WhaleBook.flow` — function — `flow.py:591`

```text
Whale sweeps over the window: buy / sell USD, counts, largest, most levels eaten by one sweep.
```

#### 289. `WhaleBook.net_units` — function — `flow.py:604`

```text
Net whale flow over the window in units of the symbol's whale size (3.0 = three whales net buying).
```

#### 290. `WhaleBook.cluster` — function — `flow.py:610`

```text
+1 / -1 when an algo cluster (many notable same-side sweeps summing to a whale) is running, else 0.
```

#### 291. `Footprint` — class — `flow.py:653`

```text
Bid x ask USD per price bucket per minute, only for symbols explicitly enabled (cards waiting for an entry).
```

#### 292. `Footprint.merged` — function — `flow.py:687`

```text
Bucket -> [buy USD, sell USD] summed over the minutes in [since_ms, until_ms).
```

#### 293. `Footprint.stacked_imbalance` — function — `flow.py:699-702`

```text

        Longest run of consecutive diagonal imbalances in the trade's direction: for longs, taker buys at a level
        >= imbalance_ratio x taker sells one bucket lower (initiative buying lifting offers); mirrored for shorts.
        
```

#### 294. `Footprint.finished_auction` — function — `flow.py:707-713`

```text

        A finished auction at the extreme (footprint convention, ATAS Bid/Ask: the Ask column = market BUYS, the Bid
        column = market SELLS). audit N10: a finished low has a zero ASK - at the window's lowest price (almost) no
        taker BOUGHT, the sellers met no buyers below and the auction ran out there; a finished high has a zero BID
        (no taker sells at the high). The old check read the opposite sides. `share`: the limit of that side as a
        share of the price bucket's volume.
        
```

#### 295. `minute_atr_15m` — function — `flow.py:727-728`

```text
A 15m ATR estimate from the last hour's closed 1m candles (mean 1m range x sqrt(15)) for coins without a zone
    card's ATR; None with fewer than 20 minutes.
```

#### 296. `absorption_in` — function — `flow.py:737-742`

```text

    Absorption against the trade in [since_ms, until_ms): a closed 1m candle whose taker delta is >= the
    absorption_percentile of the last hour's |delta|, AGAINST the trade (sellers for a long), while its range stayed
    <= absorption_max_move_atr x ATR: the aggressive side hit resting orders and could not move price.
    Candles are [open_time, open, high, low, close, quote_volume, taker_buy_quote].
    
```

#### 297. `RushBook` — class — `flow.py:782-790`

```text

    eng-89, "rush orders" (La Morgia et al., arXiv 2005.06610: pump detection on Binance within seconds): one taker
    market order that ate several price levels prints as several aggTrades with the SAME trade time and side.
    A PROXY, narrower than the paper (review eng-160b): the paper groups raw trades of one side in the same ms; aggTrade
    already merges the fills of one taker at one price, so a market order filled at a single level is not counted here -
    only multi-level sweeps are. Neither is an exact market-order count (no parent order id in the public stream). Counted
    per second per coin in a one-hour ring (Binance futures only: its aggTrade carries the match time T). Journaled as
    features and as RUSH rows - data collection, no trading.
    
```

#### 298. `RushBook.stats` — function — `flow.py:846-847`

```text
Rush orders in the last 10 / 30 s (count, net buy - sell count, USD) and the 30 s count's z-score against
        the coin's own previous hour (120 buckets of 30 s, zeros included).
```

### `history.py`

#### 299. `<module>` — module — `history.py:1-11`

```text

Historical market data from Binance's public archive (data.binance.vision) for pretraining (pretrain.py):
1m klines of USD-M futures and spot (quote volume + taker buy quote: the same fields as the live streams), the
5-minute `metrics` (open interest, top-trader / global long-short ratios) and funding rates.

Files are cached under CONFIG.pretrain.cache_dir (a second run downloads nothing), downloaded at a capped rate
(the link also carries the live streams: an uncapped download made them lag before, see positioning.py) and
retried on network errors; a 404 is "no data for that period" (not listed yet), not an error.
Liquidations, order books, the other venues, Hyperliquid and Coinbase have no public archive: models learn those
features live only.

```

#### 300. `RateLimiter` — class — `history.py:38`

```text
Caps the average download rate (bytes / s) across all requests of the process.
```

#### 301. `Archive._fetch` — function — `history.py:64`

```text
The zip at `path` (cached); None when the archive has no such file.
```

#### 302. `Archive._recent` — function — `history.py:119`

```text
Does the archive file's period (YYYY-MM-DD / YYYY-MM in its name) end within the last 10 days?
```

#### 303. `Archive.periods` — function — `history.py:146`

```text
Complete months as monthly files ('YYYY-MM'), the rest of the range as daily files ('YYYY-MM-DD').
```

#### 304. `Archive.klines_1m` — function — `history.py:162-165`

```text

        1m klines as float64 [open_time_ms, open, high, low, close, volume, quote_volume, taker_buy_quote], sorted,
        de-duplicated. `market`: 'futures' (USD-M) or 'spot'.
        
```

#### 305. `Archive.metrics` — function — `history.py:189-192`

```text

        5-minute metrics: 'ts' (snapshot time ms), 'oi' (open interest, base units), 'oi_usd', 'top_pos' (top
        traders' long/short position ratio), 'top_acc' (top accounts), 'global' (all accounts).
        
```

#### 306. `Archive.funding` — function — `history.py:212`

```text
Funding settlements [calc_time_ms, rate normalized to 8h (raw=True: the rate paid at that settlement)].
```

#### 307. `Archive.klines_1d` — function — `history.py:233-236`

```text

        Daily klines [open_time_ms, close, quote_volume] of the COMPLETE months in [start, end] (monthly files only:
        the running month has only daily files, and a daily 1d file per coin and day is thousands of requests).
        
```

#### 308. `Archive.klines_ohlc` — function — `history.py:255-258`

```text

        Klines [open_time_ms, open, high, low, close, quote_volume] of `interval` (e.g. '1h') over the COMPLETE months
        in [start, end] (monthly files only, like `klines_1d`).
        
```

#### 309. `Archive.list_symbols` — function — `history.py:276-279`

```text

        Every symbol the archive has monthly klines for, INCLUDING delisted ones (the S3 listing of data.binance.vision,
        paginated; cached for a day): pretraining picks its coins from the past, not from today's exchange.
        
```

#### 310. `_is_zip` — function — `history.py:316`

```text
A complete zip archive (its central directory at the end is intact).
```

#### 311. `_utc_ms` — function — `history.py:325`

```text
'2026-09-25 01:30:00' (UTC) -> epoch ms.
```

### `history_coverage.py`

#### 312. `<module>` — module — `history_coverage.py:1`

```text
Deterministic coverage of closed candles; never infer readiness from a loading flag.
```

#### 313. `coverage` — function — `history_coverage.py:11-16`

```text
Report depth, freshness and real gaps without synthesizing candles.

    Rows use exchange OHLCV order and opening timestamps in milliseconds.
    Freshness is measured against the last expected closed candle, allowing
    the configured publication grace after its close.
    
```

### `iceberg.py`

#### 314. `<module>` — module — `iceberg.py:1-11`

```text

Iceberg detection: how a whale really accumulates (resting limit orders refilled at one price), not the aggressive
market sweeps the old "whales" counted (measured x1.0: those were liquidations, stops and chasers).

For the hot coins with a live Binance book (depth20 @500ms): at one price level of one side, the volume EXECUTED
against it (aggTrades whose taker hit that side at that price) exceeds `multiple` x the largest size ever VISIBLE there
while the level held (no trade through it), and is at least `min_usd`. A bid iceberg = a hidden buyer absorbing sells
("whale buying"), an ask iceberg the hidden seller. Journaled as features (`iceberg_net_5m`: bid - ask iceberg USD over
5 minutes, `iceberg_n_5m`) and logged; measured before anything trades on it.
Sources: Bookmap's iceberg tracker, the usual definition (executed > displayed at a level that refills).

```

#### 315. `IcebergDetector` — class — `iceberg.py:41-47`

```text

    Bids and asks are kept apart so a trade only touches its own side: scanning every tracked level on every aggTrade
    stalled the event loop on ETH / BTC (live 2026-10-01, watchdog: iceberg.on_trade). A level must REFILL - be shown
    again in >= `min_refills` book snapshots after trades hit it - before it counts: depth20 arrives every 500 ms, so
    "executed > the largest size ever shown" alone fired on every busy ETH level where new orders simply arrived
    between two snapshots (112 of 157 events on ETH, "$61k executed vs $212 shown").
    
```

#### 316. `IcebergDetector.on_book` — function — `iceberg.py:63`

```text
Largest size seen at each price of the live book (USD); a level traded against and shown again = a refill.
```

#### 317. `IcebergDetector.on_trade` — function — `iceberg.py:102`

```text
A taker SELL hits the bid side at `price` (and breaks every bid above it), a taker BUY the asks.
```

### `indicators.py`

#### 318. `_over` — function — `indicators.py:39`

```text
Window expressions run per symbol, so one Polars pass covers every symbol.
```

#### 319. `compute_indicators_batch` — function — `indicators.py:44-50`

```text

    Derive every indicator the scorer needs for many symbols at once: the raw frames (RAW_SCHEMA, including the
    live in-progress last row) are stacked with a 'symbol' column and each rolling/shift/cumulative expression runs
    `.over('symbol')`. One query over ~30k rows replaces hundreds of tiny per-symbol queries (~20x faster).
    No global drop_nulls(): new listings with short history keep their rows and nulls are handled per expression.
    `funding` maps symbol -> (funding_rate, predicted_funding), both 8h-normalized.
    
```

#### 320. `compute_indicators` — function — `indicators.py:161`

```text
Single-symbol convenience wrapper around compute_indicators_batch (keeps a constant 'symbol' column).
```

#### 321. `merge_live_candle` — function — `indicators.py:168-172`

```text

    Replace (same candle) or append (new candle) a kline row; keeps the last rest_lookback_candles rows.
    Returns (frame, needs_backfill): backfill when a candle is skipped or the previous candle was never
    finalized (e.g. stream reconnect, or a candle closed between the REST download and the first WS update).
    
```

#### 322. `_base_sample` — function — `indicators.py:224`

```text
First sample at or after since_ms (samples are time-ordered): bisect instead of a linear scan.
```

#### 323. `calculate_tier0_metrics` — function — `indicators.py:240-249`

```text

    Core Tier-0 raw impulse metrics from in-memory stream data (no REST, no Polars); the order-flow columns are
    filled in by the scanner from FlowStore / WhaleBook.

    rvol_1m: quote volume of the last 60 seconds from the futures 1m kline stream (the current minute plus the
    not-yet-elapsed share of the previous one) divided by the average minute of the last 24h.
    whale_net_5m: net whale flow over the window in units of the symbol's whale size (legacy input: whale_trades
    as (ts_ms, signed usd, ...) records; the scanner overrides it with WhaleBook.net_units).
    price_z / oi_z: the 5m change divided by the coin's typical 5m change (15m std / sqrt(3)); 0 when unknown.
    
```

#### 324. `seasonal_factors` — function — `indicators.py:311-317`

```text

    The coin's intraday periodicity from ~4 weeks of 1h candles [ts, o, h, l, c, quote_vol, ...]: per UTC hour the
    median quote volume and the median |1h return| of weekdays, each divided by its mean over the 24 hours, and the
    weekend / weekday ratio of both. Relative volume and volatility then compare a minute with the same time of day
    ("relative volume at time"; Andersen-Bollerslev periodicity): against a flat 24h average, the US open produced
    false anomalies and quiet hours / weekends hid real ones (Boudt, Croux & Laurent 2011; crypto: arXiv 2109.12142).
    
```

#### 325. `seasonal_scale` — function — `indicators.py:356-360`

```text

    Expected level now relative to the trailing 24h average it scales (kind 'vol' for volume, 'ret' for volatility):
    the hour's factor x the weekend ratio, over the weekend share of the last 24 hours (the average already
    contains them). 1.0 without a profile.
    
```

#### 326. `minute_delta` — function — `indicators.py:372`

```text
Net taker flow (USD) of 1m klines [t, o, h, l, c, quote, taker_buy_quote] overlapping the last window.
```

### `journal.py`

#### 327. `<module>` — module — `journal.py:1-10`

```text

Signal journal: every new signal is stored in SQLite with the market state at that moment, and a background
loop later fills in what the price actually did (15m / 1h / 4h returns, 4h max favorable/adverse move) from
Binance 1m futures klines. `stats.py` turns the table into per-setup statistics.

Writes never block the event loop: the connection runs in WAL mode and every call from async code goes through
asyncio.to_thread (the a* methods), serialized by a lock. Every 15 minutes the prices of the whole universe are
stored (`universe` table): stats.py measures Edge against that real market baseline instead of the median of
the coins that happened to produce signals.

```

#### 328. `wilson_upper` — function — `journal.py:46`

```text
The upper end of the 95% Wilson score interval of a proportion (hits of n).
```

#### 329. `shrinkage_upper` — function — `journal.py:56`

```text
Upper posterior probability with an explicit Beta prior.
```

#### 330. `load_pretrained` — function — `journal.py:76`

```text
The models pretrain.py built from the public archive (None when it was not run).
```

#### 331. `pretrained_current` — function — `journal.py:99-104`

```text

    The pretrained P(edge) was built by the current signal logic. A model of an older logic_version learned rows the
    bot no longer writes (eng-7: rows of older versions saw up to 55s of the future in their Tier-0 inputs), so it
    is not used. The live-loopside-v1 generator marker is also required; legacy or untagged P(edge)
    cannot pass on logic_version alone. Regime history is handled separately.
    
```

#### 332. `_policy_text` — function — `journal.py:117`

```text
Store lifecycle policy values as SQLite-safe text, including structured exit specs.
```

#### 333. `strategy_class` — function — `journal.py:155`

```text
eng-148 (audit 3 / 31): the exit class a strategy belongs to, journaled for a later TP1 floor by class.
```

#### 334. `excursions` — function — `journal.py:160-162`

```text
eng-148 (stage 0): the trade's MFE / MAE in R up to its stop (or the window's end), over the first 10 15m bars
    (when the window covers them), and the best move in the 15 15m bars after the stop
    (post_stop_mfe_r: how often the stop was a raid that then went the trade's way). The 1m window starts at the entry.
```

#### 335. `_to_tp1` — function — `journal.py:205-206`

```text
The R of a trade from minute `start`: the stop's touch first (-1, the conservative order inside a minute), else
    TP1's touch (+R:R), else out at the window's last close.
```

#### 336. `_shadow_exits` — function — `journal.py:217-224`

```text

    eng-149 (plan eng-148 stage 3; journal only, before costs, to TP1 or the 8h window's end):
    - two_stop_r (audit 14): two contours - out at the close of the first 15m bar (UTC-aligned) that CLOSED beyond the
      stop, or at the touch of a far stop 0.7 ATR (the plan's working ATR, atr_entry) beyond it; base_stop_r = the
      same trade with the plain stop on the touch, on the same window (the pair to compare);
    - retest_r (audit 15; sweeps with a zone_far): the second test of the entry after the price left it by >= 0.5R
      with no 15m close beyond the zone's far edge before it - the same stop / TP1 from that re-entry.
    
```

#### 337. `_zone_far` — function — `journal.py:267`

```text
eng-149: the far edge of a sweep's entry zone (the FVG's far side once armed, else the zone's), None elsewhere.
```

#### 338. `horizon_due_ms` — function — `journal.py:278`

```text
Epoch ms from which the `minutes` horizon of a row logged at ts_ms can be evaluated.
```

#### 339. `proven_negative` — function — `journal.py:507-511`

```text

    For each group (4h blocks of Edge values): a block-bootstrap p-value of "the mean Edge is >= 0"; the groups
    proven negative with the Benjamini-Hochberg false discovery rate q over all groups tested (a setup x regime
    grid is dozens of tests at once: without the correction some mutes are chance).
    
```

#### 340. `price_anomaly` — function — `journal.py:539`

```text
Same rule as PhaseScorer.flag_tier_0_anomaly for the 5m price move (floor + the coin's own z-score).
```

#### 341. `crowded` — function — `journal.py:557-561`

```text

    Leverage crowded on the trade's side with positions still building: funding (all venues, else Binance) at or
    beyond the crowding level for that side, or (longs) US spot at a discount (Coinbase premium), AND OI rising
    over the last hour.
    
```

#### 342. `present` — function — `journal.py:582-583`

```text
audit N12: the first value that was OBSERVED (not None / NaN) - a measured 0 is a value, not a missing one
    (`a or b` replaced a cancelled-out aggregate flow of 0 by Binance's one-venue flow).
```

#### 343. `perp_flow_5m` — function — `journal.py:591`

```text
5m perp taker flow: all futures venues when several report, else Binance.
```

#### 344. `classify` — function — `journal.py:605-608`

```text

    (kind, group_key, direction) for a scorer signal: 'setup' = a detected setup (strategies.detect / structure), 'structured'
    = the 15m phases, 'anomaly' = a Tier-0 reading.
    
```

#### 345. `veto_reason` — function — `journal.py:668-672`

```text

    Why a directional setup is not shown as a card (it is still journaled with this reason, so stats.py can
    compare vetoed and passed signals): a continuation (D, F, a breakout, an impulse) driven by the perp side while
    spot disagrees.
    
```

#### 346. `event_family` — function — `journal.py:707-710`

```text

    (family, rank) of a setup label. A higher rank is a stronger reading of the same event (a confirmed impulse
    over an unconfirmed one, a fully met phase over a partial one) and is logged even inside the cooldown.
    
```

#### 347. `SignalJournal.record` — function — `journal.py:897-900`

```text

        Store signals not logged for the same (symbol, event family) within the cooldown, unless the new label is a
        stronger reading of the event (higher rank). Returns rows added.
        
```

#### 348. `SignalJournal.record_entry` — function — `journal.py:936-940`

```text

        An entry triggered by the LTF model (signal_book.TrackedSignal): its own row 'ENTRY <setup>' with the levels,
        so stats.py replays exactly what the dashboard showed, from the entry moment. Vetoed entries (no order-flow
        confirmation) are stored too, with the reason.
        
```

#### 349. `SignalJournal.record_card` — function — `journal.py:1012-1015`

```text

        A finished card (MISSED / EXPIRED / INVALID / TP3 / SL / CLOSED): 'card' row '<STATUS> <setup>' at the finish
        price, with the reason; the outcome loop then fills what price did in the card's direction afterwards.
        
```

#### 350. `SignalJournal.record_rush` — function — `journal.py:1091`

```text
eng-89: a RUSH BUY / RUSH SELL row (kind 'rush'): data collection, evaluated by the ret_* horizons.
```

#### 351. `SignalJournal.snapshot_universe` — function — `journal.py:1099`

```text
Store the price of every universe coin (at most once per universe_snapshot_sec).
```

#### 352. `SignalJournal.record_history_skips` — function — `journal.py:1114`

```text
[(symbol, strategy, held, needed)] of the strategies a history gate stopped; once a day per coin and strategy.
```

#### 353. `SignalJournal.record_liquidations` — function — `journal.py:1133`

```text
Live liquidations [(symbol, ts_ms, price, usd, side, venue)].
```

#### 354. `SignalJournal.record_liq_levels` — function — `journal.py:1142`

```text
A snapshot of a coin's liquidation levels [(kind, price, side, usd)] and the price at the time.
```

#### 355. `SignalJournal.universe_return` — function — `journal.py:1160-1165`

```text

        Return of the whole universe between the snapshots nearest ts and ts + minutes (<= 20 min away): the MEAN
        (Edge: an equal-weight universe has zero mean excess, while coins beat the median by ~0.11% per 4h on average -
        right-skewed returns - so Edge against the median favoured every long and penalised every short) or the
        'median' (the P(edge) label: a balanced 'beat the median coin').
        
```

#### 356. `SignalJournal.warm_start` — function — `journal.py:1214`

```text
Replay every labelled directional row into the P(edge) model (state = the journal itself).
```

#### 357. `SignalJournal._learn_trade` — function — `journal.py:1257`

```text
eng-174: a closed trade teaches P(trade) now - at its real exit, never before (the label is its result).
```

#### 358. `SignalJournal.warm_start_trades` — function — `journal.py:1267`

```text
Replay the closed trades of trade_history_days in exit order (rows before eng-174: the card row's time).
```

#### 359. `SignalJournal.refresh_anomaly_effects` — function — `journal.py:1286-1290`

```text

        Each anomaly label's effect, measured against the coin itself: the median of |4h move after the label| /
        the coin's usual |4h move| (its universe snapshots over the same days). x1.0 = the label adds nothing to the
        coin's normal volatility (live 2026-09-27..30: whales, absorption, one-venue, cascades ~x1.0; impulses x1.4).
        
```

#### 360. `SignalJournal.refresh_regime_stats` — function — `journal.py:1332-1336`

```text

        4h Edge per (setup, regime) for journal.veto_reason: a (setup, regime) is muted once its Edge is proven
        negative over >= regime_veto_min_n independent 4h blocks, with the false discovery rate controlled over the
        whole grid (proven_negative).
        
```

#### 361. `SignalJournal.refresh_hit_rates` — function — `journal.py:1355-1362`

```text

        p(TP1 before the stop) per SETUP (audit C09) from the replayed entries of the last 30 days (passed and vetoed: the
        replay is the same), decided ones (TP1 / TP2 / TP3 vs SL) -> strategies.geometry.HIT_RATE (p, n, p_upper). A
        DESCRIPTIVE rate of reaching each target before the stop (audit 2026-10-18 P1 #5): the entry check turns it into
        the expectancy of the three-thirds exit only, vetoing a plan that exits that way when even the upper end of the
        95% Wilson interval does not pay; it is not the expectancy of the whole exit policy (trail, partials, time
        exits), and entries of one market move are not independent draws, so the interval is optimistic.
        
```

#### 362. `SignalJournal.refresh_confirm_stats` — function — `journal.py:1403-1408`

```text

        Promote a confirmation to required for a strategy (strategies.confirm.PROMOTED) once the strategy's entries
        WITHOUT it have a negative Edge proven over >= promote_min_clusters independent 4h blocks, with the false
        discovery rate controlled over every (strategy, confirmation) tested (proven_negative). Only entries of the
        current logic version count.
        
```

#### 363. `SignalJournal.coin_results` — function — `journal.py:1433-1437`

```text
(strategy, symbol, ts_ms, direction, net R) of every non-vetoed entry since `since_ms` of the logic family
        judged now (CONFIG.journal.verdict_since on): the trade's own result (card_r, on the entry row since eng-86) only.
        audit 2026-10-18 P1 #5: the replay's R to TP1 (r_tp1) is another trade - all out at TP1 - and is no longer
        substituted for a missing card_r (an open trade or a row before eng-86 is left out, not given a model result);
        no coin is excluded on the results of a logic that no longer runs.
```

#### 364. `SignalJournal.summary` — function — `journal.py:1448`

```text
(signals logged, signals with a 4h outcome).
```

#### 365. `SignalJournal._pending` — function — `journal.py:1473`

```text
Oldest rows with at least one horizon due and not filled yet.
```

#### 366. `SignalJournal.maintenance` — function — `journal.py:1493-1494`

```text
Daily: fold the WAL back into the database (it grew to 7 MB between automatic checkpoints) and let SQLite
        refresh its planner statistics. No VACUUM: it rewrites the 100 MB file under the lock.
```

#### 367. `SignalJournal.evaluate_loop` — async function — `journal.py:1500`

```text
Fill in outcomes as horizons come due (also catches up on signals from previous runs).
```

#### 368. `SignalJournal._evaluate_pass` — async function — `journal.py:1523-1526`

```text

        Oldest-first across all horizons (so no horizon starves), one request per row: the 1m klines of the longest
        due horizon also cover the shorter ones.
        
```

#### 369. `SignalJournal.backfill_outcomes_once` — async function — `journal.py:1540`

```text
Evaluate all configured horizons once for an offline backfill job.
```

#### 370. `SignalJournal._replay` — function — `journal.py:1593`

```text
SL / TP of an entry row replayed on its 1m candles, filled like a human would.
```

#### 371. `SignalJournal._pending_life` — function — `journal.py:1604-1605`

```text
Entry rows whose provisional 8h outcome can still change (OPEN / TP1 / TP2; SL and TP3 are final) and
        whose full replay window (journal.outcome_life_h) has closed.
```

#### 372. `SignalJournal._evaluate_life_pass` — async function — `journal.py:1620`

```text
Relabel entries over the trade's real life (audit #21): 1500-minute pages of 1m klines.
```

#### 373. `SignalJournal._learn` — function — `journal.py:1661`

```text
Feed a freshly labelled directional row to the online P(edge) model.
```

### `levels.py`

#### 374. `<module>` — module — `levels.py:1-13`

```text

Price primitives of the strategies (strategies/): the leg (find_impulse: its end on the last 12h of 15m candles, its
start searched back over 15m and then 1h history until price was last beyond the end, its timeframe by duration 15m /
1h / 4h and checked in that timeframe's ATR), Fibonacci / retracement of a leg, the leg's own levels (fib, anchored
VWAP), resampling 1m candles, the structure-shift trigger on closed lower-timeframe candles, the spring's volume test,
and the journal's replay of an entry on 1m candles (simulate: manual fill, SL first on a tie; r_be = the same trade with
the stop moved to the entry once TP1 traded, exited at TP2).

LTF trigger (market structure shift): after the extreme made inside the zone, a candle closes beyond the highest high
(lowest low for shorts) of the `ltf_break_lookback` candles up to that extreme, while net taker flow of the last
`ltf_flow_candles` candles after the extreme agrees (the selling into a low is what was absorbed there, not a vote
against the shift).

```

#### 375. `min_leg_atr` — function — `levels.py:34-36`

```text
The smallest leg (in ATR) a reversal can be traded from: its first target, the leg's first retracement level
    (levels.reversal_targets[0], 0.382), must pay at least 1 R over the stop floor (levels.min_stop_atr):
    leg >= min_stop_atr / 0.382. A config value > 0 overrides the formula.
```

#### 376. `min_leg_move` — function — `levels.py:42-43`

```text
The smallest leg as a share of price: its 0.382 target must cover cost_guard round-trip costs (fees + the
    slippage of the entry and the stop exit at the reference liquidity). A config value > 0 overrides the formula.
```

#### 377. `wilder_of` — function — `levels.py:50-51`

```text
Wilder's smoothing (RMA) of a series at its last value: seeded with the mean of the first `period` values, then
    y += (x - y) / period (Wilder 1978, TA-Lib). None with fewer than `period` values.
```

#### 378. `atr_of` — function — `levels.py:61-63`

```text
THE bot's ATR (owner 2026-10-18: one formula everywhere): Wilder's ATR(period) - the RMA of the true ranges of
    [ts, o, h, l, c, ...] candles over all of them given (was the simple mean of the last `period`: after a spike the
    two differed by 25-40%, the detectors and the stops measured one candle with different rulers).
```

#### 379. `resample_htf` — function — `levels.py:71`

```text
1h candles -> complete `hours` candles on the UTC grid, without missing or repeated hours.
```

#### 380. `_extend_start` — function — `levels.py:87-90`

```text

    Walk back over candles [ts, o, h, l, c] older than the leg start (newest first): the move began after the last
    candle that traded beyond the leg's end; its start is the most extreme opposite price after that candle.
    
```

#### 381. `find_impulse` — function — `levels.py:109-116`

```text

    eng-122, the leg from STRUCTURE (no windows of ours): its END is the last confirmed 2/2 swing high (low for a
    down leg) of the 15m frame; its START is the most extreme opposite price between that end and the last candle
    (15m, then the older 1h history) that traded beyond the end - the move began after it. Its timeframe by duration
    (15m below 5h, 1h below 20h, else 4h) and its ATR in that timeframe; it qualifies by the derived minimum leg
    (levels.min_leg_atr / min_leg_move). Returns {'start', 'end', 'size', 'candles', 'atr', 'atr_15m', 'tf',
    'trigger_minutes', 'start_ts', 'end_ts'} or None.
    
```

#### 382. `_qualify` — function — `levels.py:184`

```text
find_impulse's timeframe / ATR / minimum-leg qualification of one start (eng-168f split).
```

#### 383. `retracement_of` — function — `levels.py:204`

```text
How much of the leg is given back at `price`: 0 = at the leg's end, 1 = back at its start.
```

#### 384. `fib_price` — function — `levels.py:210`

```text
Retracement level `ratio` of the leg (0 = end, 1 = start); negative ratios lie beyond the end.
```

#### 385. `_leg_levels` — function — `levels.py:216`

```text
Card-specific levels: the leg's Fibonacci levels, a range's far side, VWAP anchored at the leg's start.
```

#### 386. `reached_after` — function — `levels.py:232-236`

```text

    Furthest price in the trade's direction (+1: highest) reached after a reversed leg's end, from candles
    [ts, o, h, l, c, ...]: the end candle's close (its high may have printed before its low) and the full range of
    every later candle.
    
```

#### 387. `resample` — function — `levels.py:252-262`

```text

    1m candles [open_time, open, high, low, close, quote_vol, taker_buy_quote, base_vol] -> `minutes` candles
    aligned to epoch multiples of `minutes`. Only buckets that have closed by `now_ms` are returned (all of them when
    None). Data quality (audit A04): a partial FIRST bucket (a history starting mid-bucket) is dropped; an inner
    bucket with minutes missing is kept only when its first and last minute are present and its coverage is >=
    CONFIG.levels.resample_min_coverage, else dropped (a hole beats a false bar; dropping every gapped bucket left
    holes for one lost minute). Counts in RESAMPLE_QUALITY. base_vol (coins) is NaN when any minute lacks it (a row
    of the old 7-column format): never estimated from quote. complete=False keeps partial buckets (the chart's
    forming bar only, never a signal input).
    audit C04: a repeated minute counts once (the last copy); missing minutes are never interpolated.
    
```

#### 388. `ltf_trigger` — function — `levels.py:308-313`

```text

    Market structure shift on closed LTF candles [open_time, open, high, low, close, quote_vol, taker_buy_quote].
    Zone candles are those still open at or after `since_ms` (the minute price entered the zone). Returns
    {'entry', 'extreme', 'time', 'extreme_time'} for the first trigger, else None.  ``body_confirmations`` keeps the
    legacy one-close trigger at 1; Prizrak structural plans pass 2 so a wick / one noisy close is not a PP.
    
```

#### 389. `pullback_volume_ok` — function — `levels.py:366-371`

```text

    Wyckoff "test" of a spring: the pullback after the spring trades on lower volume (supply dried up). The average
    1m quote volume in [since_ms, until_ms) must be <= spring_test_volume_ratio x the spring candle's average minute.
    audit C08: None when it cannot be observed (no reference / no pullback minutes) - an unobserved test is not a
    passed one.
    
```

#### 390. `pullback_spread_ok` — function — `levels.py:385-390`

```text

    eng-55: Wyckoff's test also NARROWS the spread (StockCharts Wyckoff tutorial; tradingwyckoff: test ranges 40-70%
    smaller than the spring's). The pullback's 15m candles average a range <= spring_test_spread_ratio x the spring
    candle's range scaled to 15m by sqrt(time) - audit: sqrt(spring_minutes / 15), i.e. / 4 for the 4h spring the
    detector runs on (the old / 2 was the 1h case). None when it cannot be observed (audit C08).
    
```

#### 391. `window_coverage_ok` — function — `levels.py:409-413`

```text
Whether a candle window contains every expected open without a transport gap.

    The first bucket may start part-way through an interval (the caller's event time), but missing inner opens are
    never interpreted as zero volume.  Duplicate timestamps count once, matching ``resample``'s correction policy.
    
```

#### 392. `slippage_bps` — function — `levels.py:437-438`

```text
Slippage of one market order in bps: the base for liquid coins, more for thin ones (CONFIG.levels); with the
    symbol, never below its measured book slippage (eng-124: the volume model priced 84 of 195 coins' books too cheap).
```

#### 393. `stop_fill` — function — `levels.py:454`

```text
A stop is a market order: it fills at the stop, or at the open when the candle gapped through it, plus slippage.
```

#### 394. `fill_price` — function — `levels.py:461-464`

```text

    Price a human gets: the open of the first 1m candle after the trigger (the journal fetches candles from the
    first full minute after the entry, i.e. ~fill_delay_sec later) plus slippage against the trade.
    
```

#### 395. `funding_r` — function — `levels.py:476-482`

```text

    Funding the position pays over (t0, t1] in R: the rate per settlement x the settlements crossed x entry / risk.
    Longs pay a positive rate. audit C12: the contract's OWN interval (interval_h: 8 / 4 / 1 h, settlements at its
    multiples from 00 UTC) - a 4h contract held 01:00-05:00 settled at 04:00 and paid; the 8h grid counted none. The
    rate is the 8h-normalized one (fetcher), so one settlement of an h-hour contract is rate x h / 8. Still a model:
    one rate for the whole hold, not the actual settled rates (those are the exchange's ledger - executor).
    
```

#### 396. `simulate` — function — `levels.py:493-501`

```text

    Replay 1m candles [open_time, open, high, low, close, ...] after an entry. With use_fill the trade is entered at
    fill_price (manual execution) and R is measured from there; otherwise at levels['entry'] (the trigger close).
    SL and TPs are checked candle by candle; if one candle touches both SL and a TP, SL counts first (conservative); a
    target counts only once price traded target_through_bps THROUGH it (a limit order is not filled by a touch).
    With funding_8h (the rate at the signal) each exit's R is net of the funding settlements it was held through.
    Returns the furthest target reached before the stop and the R result of exiting fully at TP1 / TP2
    (unfinished trades are marked to the last close). A fill already beyond the stop is 'SKIPPED' (not traded).
    
```

### `macro.py`

#### 397. `<module>` — module — `macro.py:1-12`

```text

Macro context from FRED (St. Louis Fed; public CSV, no key): US 10-year Treasury yield (DGS10), the broad trade-
weighted dollar index (DTWEXBGS) and Brent crude (DCOILBRENTEU). audit N06: a value is used only from its RELEASE
(available_ms, a conservative calendar per series), not from the day after its observation date: H.10 (DTWEXBGS) is
published weekly on the following Monday 16:15 ET, EIA's Brent spot with up to a week's delay, H.15 (DGS10) the next
business day. FRED's current CSV is not a point-in-time vintage either (revisions are in it): for a strict history use
ALFRED vintages - until then the training features are labelled approximate.

Features: the 5-trading-day change of each series as of the previous day (yield in basis points, dollar and Brent in
%). Context for the scenario card and a candidate input of its probability model (`train_scenarios.py --macro`);
not a signal by itself.

```

#### 398. `available_ms` — function — `macro.py:33`

```text
audit N06: when an observation dated obs_day_ms (UTC day start) is public, conservatively.
```

#### 399. `fetch` — function — `macro.py:48`

```text
[(day start ms, value)] of a FRED series; '.' (holidays) skipped.
```

#### 400. `Macro.refresh` — function — `macro.py:70`

```text
Download (or read the cache when it is fresh); True when every series is present.
```

#### 401. `Macro.snapshot` — function — `macro.py:106`

```text
Last known levels + 5-day changes (for the dashboard).
```

### `macro_calendar.py`

#### 402. `<module>` — module — `macro_calendar.py:1-7`

```text

Scheduled US macro releases that move crypto at a known minute (FOMC statement 14:00 New York, CPI 08:30 New York):
an entry from `before_min` before to `after_min` after a release is journaled with vetoed='macro_event' (the spread
widens, stops are run both ways in the first minutes; the event, not the setup, decides the move). The dates are
published a year ahead: FOMC (federalreserve.gov, 2026 schedule), CPI (bls.gov/schedule/news_release/cpi.htm).
Add the next year's dates when they are published; a date list that ran out simply vetoes nothing.

```

#### 403. `_sources` — function — `macro_calendar.py:64-65`

```text
eng-168t: every blocking release - the official schedules first (official_calendar), the hand list, the live
    week's High events. A release present in several sources blocks once in practice (same minute windows).
```

#### 404. `blackout` — function — `macro_calendar.py:71`

```text
The release whose window `now_ms` falls in, else None.
```

#### 405. `upcoming` — function — `macro_calendar.py:80`

```text
eng-100: (time, name) of the next high-impact release within `within_ms` from now, else None.
```

#### 406. `live_ok` — function — `macro_calendar.py:90-93`

```text
eng-168s / eng-168t (audit #6, fail-closed): every blocking category (CPI, NFP, PPI, FOMC, ISM M / S) is
    covered - by its official schedule (fresh and reaching official_calendar.COVER_DAYS ahead) or, for the uncovered
    ones, by a fresh ForexFactory week. Otherwise a release may sit on a new entry unseen: new entries /
    recommendations wait; open positions are managed.
```

#### 407. `coverage` — function — `macro_calendar.py:99-101`

```text
Audit B06: why the macro veto may be blind right now, else None. The veto fails open (no source = no window), so
    the degraded state must at least be visible: the weekly feed lost / stale, or the hand list of CPI / FOMC / NFP
    already past its last date.
```

### `main.py`

#### 408. `<module>` — module — `main.py:2-14`

```text

EdgeHunter crypto market analysis and signal system (Binance USD-M perpetuals).

- Phases on 15m candles (scorer.py): long = A accumulation / B spring / E capitulation, short = C distribution /
  D breakdown; Tier-0 raw anomalies every 2s (RVOL 1m, OI 5m, price 5m, whale flow).
- Trade model (levels.py + zones.py): the 15m leg gives the context, the coin's level map (support / resistance,
  liquidity pools, liquidation clusters, volume profile, Fibonacci) the zone, stop and targets; the entry is a 5m
  structure shift, confirmed by order flow (flow.py); Binance + Bybit / OKX / Hyperliquid / Bitget / Coinbase
  streams (venues.py).
- Journal (journal.py) records every setup, entry and finished card; `python stats.py` shows how they played out.
- Browser dashboard (webui.py) on http://127.0.0.1:8765; the console shows the log.
Ctrl+C stops gracefully (press again after 3s to force).

```

#### 409. `setup_logging` — function — `main.py:45-49`

```text

    Console + a size-rotated scanner.log (a long run never grows the file without bound), written by a listener
    THREAD: the loop only queues records. A console write blocks while the window has a selection or conhost is
    paged out (measured: the loop stalled 2s inside StreamHandler.emit).
    
```

#### 410. `fast_loop_factory` — function — `main.py:66-70`

```text

    uvloop has no Windows build; winloop (uvloop-compatible) is used when installed, else the default loop.
    Returned as an asyncio.run(loop_factory=...) factory (event loop policies are deprecated since Python 3.14).
    Never combine winloop with tracemalloc: create_server never returns while tracemalloc is tracing (2026-10-05).
    
```

#### 411. `GracefulExit` — class — `main.py:87-90`

```text

    First Ctrl+C / SIGTERM / SIGBREAK starts a graceful shutdown. Repeats within FORCE_EXIT_AFTER_SEC are ignored
    (key auto-repeat, terminals that deliver Ctrl+C twice); a later repeat forces the exit.
    
```

#### 412. `ConsoleQuickEdit` — class — `main.py:112-116`

```text

    Windows console QuickEdit: a mouse click starts a text selection that PAUSES every write to the console, so
    the scanner's event loop blocked on its next log line and the whole bot froze until Enter / Esc.
    Disabled for this console while the bot runs, restored on exit.
    
```

#### 413. `loop_exception_handler` — function — `main.py:149-153`

```text

    aiohttp resolves DNS in a shielded task: when the caller already gave up (its timeout), a later DNS failure
    of that task has no awaiter and asyncio logged it as an ERROR with a traceback. The request itself was already
    retried by its caller; a network outage is logged once per event as a WARNING line.
    
```

#### 414. `unraisable_hook` — function — `main.py:171-178`

```text

    'Exception ignored while finalizing file <_io.BytesIO>: BufferError: Existing exports of data' (~10-40 a day, a
    5-line traceback at a random line - wherever the gc happened to run): a BytesIO collected in one reference cycle
    with a memoryview of its buffer (multiprocessing pickles to BytesIO.getbuffer()); the gc finalizes the BytesIO
    first and its close() refuses while the view exists. Both were garbage already - nothing is lost. Python 3.13+
    reports it (IOBase's finalizer stopped swallowing close() errors; RhysU/jobserver#444). One INFO line an hour
    with the count; everything else goes to Python's own hook.
    
```

#### 415. `keep_awake` — function — `main.py:192-196`

```text

    Keep Windows from sleeping while the bot runs (the display may still turn off): on 2026-10-05 the laptop slept
    11:05 -> 12:44 and the bot saw nothing for 1h39m. ES_CONTINUOUS | ES_SYSTEM_REQUIRED, cleared at exit. A closed lid
    or a manual sleep still wins.
    
```

### `memory_guard.py`

#### 416. `<module>` — module — `memory_guard.py:1`

```text
Cheap cgroup-v2 memory pressure checks; never walks Python objects.
```

### `memreport.py`

#### 417. `<module>` — module — `memreport.py:1-10`

```text

Where the bot's memory sits, cheap enough for the live loop (tracemalloc / objgraph walk every object and froze it:
2026-10-05, 72s stalls at 1.8 GB).

- `process_breakdown()`: this process's committed memory by region class (Windows VirtualQuery, the VMMap view):
  pymalloc arenas (1 MB blocks = Python objects), large private blocks (numpy / polars buffers, allocator segments),
  images (DLL code). tools/vmmap.py prints the same for another process from outside.
- `structures(fetcher, scanner)`: sizes of the bot's own containers, polars `estimated_size`, numpy `nbytes`, Python
  containers estimated from a sample of their elements; `MarketData` fields summed over all coins.

```

#### 418. `linux_memory_status` — function — `memreport.py:29`

```text
Cheap process/host memory snapshot; never walks Python objects.
```

#### 419. `regions` — function — `memreport.py:68`

```text
({allocation base: committed private bytes}, image bytes, mapped bytes) of a process (0 = this one).
```

#### 420. `process_breakdown` — function — `memreport.py:98`

```text
MB by class: private, arenas (pymalloc 1 MB blocks), small (< 1 MB), mid (1-8 MB), large (>= 8 MB), image.
```

#### 421. `_linux_breakdown` — function — `memreport.py:120-126`

```text

    The same view from /proc/<pid>/smaps (0 = this process): MB resident + swapped by class. `private` = anonymous
    writable memory, split into `heap` (brk), `small` (< 1 MB), `mid` (1-8 MB), `large` (>= 8 MB) by the size of the
    mapping; `swap` = the part of it that is swapped out; `image` = file-backed mappings. The kernel merges adjacent
    anonymous mappings, so a block of several allocator segments reads as one `large`; pymalloc arenas cannot be told
    apart (no `arenas` key).
    
```

#### 422. `approx_size` — function — `memreport.py:167`

```text
Bytes held by obj: exact for polars / numpy / array, estimated from a sample for Python containers.
```

#### 423. `_sample_size` — function — `memreport.py:202`

```text
40 elements at the top, fewer deeper: a sample of a sample stays bounded (40 x 10 x 3 x 3 x 3 calls).
```

#### 424. `structures` — function — `memreport.py:216-220`

```text

    [(name, MB)] largest first: MarketData fields summed over coins, then every attribute of the fetcher / scanner.
    One `seen` set across all of them: an object shared by several owners (the markets, symbol maps, the fetcher
    itself) is counted once, for the first owner.
    
```

### `ml.py`

#### 425. `<module>` — module — `ml.py:1-18`

```text

Machine learning that adapts to the current market instead of fixed thresholds fitted to the past.

1. AnomalyModel (scikit-learn IsolationForest): Tier-0 anomalies as an UNUSUAL COMBINATION of a coin's live
   features (RVOL, price / OI z-scores, whale sweeps, liquidations, flow intensity, one-venue share, algo
   clusters), refitted every hour on the last hours of the whole universe. It replaces the OR of seven fixed
   thresholds (which flagged ~1000 onsets an hour, most of them noise) once it has been fitted; until then the
   rules decide. No labels needed.
2. RegimeModel (scikit-learn GaussianMixture): the market regime from market-wide features of every closed 15m
   candle (BTC 1h move and volatility, breadth, median funding / OI change / RVOL). Clusters are named from their
   centers ('up·volatile', 'flat·quiet', ...). Every journal row carries the regime; stats.py splits Edge by it
   and journal.veto_reason mutes a setup whose Edge in the current regime is proven negative.
3. SuccessModel (River when available; a small compatibility model on Python 3.10): online logistic regression +
   drift detection for P(4h Edge > 0) of a directional signal from journal features. It learns from every labelled row
   as it comes in (and replays the journal after a restart), and starts over when error rates drift.
   Shadow mode: stored in the journal and shown on cards once trained, never used as a filter until stats.py
   proves it separates winners from losers.

```

#### 426. `_worker_fit` — function — `ml.py:48`

```text
(worker process) Fit, keep the model for scoring, return it pickled with its threshold.
```

#### 427. `_worker_load` — function — `ml.py:59`

```text
(worker process) Install a model restored from ml_state.pkl.
```

#### 428. `_worker_score` — function — `ml.py:67`

```text
(worker process) score_samples of the current vectors (lower = more unusual).
```

#### 429. `AnomalyModel.ascore` — async function — `ml.py:109`

```text
Scores computed in the worker process; None before the first fit.
```

#### 430. `AnomalyModel.afit` — async function — `ml.py:127`

```text
Fit in the worker process on the sampled window; the old model keeps scoring until the new one is in.
```

#### 431. `AnomalyModel.vector` — function — `ml.py:151`

```text
Scale-free features of one coin: z-scores, multiples of the coin's own average minute, shares.
```

#### 432. `AnomalyModel.observe` — function — `ml.py:173`

```text
Sample the universe's feature vectors into the training window (every anomaly_sample_every_sec).
```

#### 433. `AnomalyModel.window` — function — `ml.py:179`

```text
The training samples of the last anomaly_window_sec.
```

#### 434. `AnomalyModel.fit` — function — `ml.py:191`

```text
Blocking in-process fit (offline use / tests); the live scanner uses afit (worker process).
```

#### 435. `AnomalyModel.score` — function — `ml.py:206`

```text
score_samples of the current vectors (lower = more unusual), None before the first fit.
```

#### 436. `AnomalyModel.load_state` — function — `ml.py:220-224`

```text

        The last model (any age: it scores until the refit replaces it, rules alone were the gap) and the training
        samples still inside the window; a model older than anomaly_fit_every_sec is refitted as soon as the window
        holds anomaly_min_samples (due()), i.e. right after the start when the downtime was short.
        
```

#### 437. `RegimeModel.market_features` — function — `ml.py:253`

```text
Market-wide features per closed 15m candle from the heavy pass's futures indicator frame.
```

#### 438. `RegimeModel.update` — function — `ml.py:276`

```text
Merge the latest market features, refit the mixture (cheap) and label the newest candle.
```

#### 439. `RegimeModel._label_newest` — function — `ml.py:289`

```text
The current model's regime of the newest candle (between the daily refits).
```

#### 440. `RegimeModel._fit_bic` — function — `ml.py:297-298`

```text
The Gaussian mixture with the lowest BIC over k = 2 .. regime_clusters (eng-57: the number of regimes is
        chosen by the data - Schwarz's criterion - instead of a fixed 4).
```

#### 441. `RegimeModel.refit` — function — `ml.py:310`

```text
Fit the mixture on the whole history (pretrained months + live candles) and label its newest candle.
```

#### 442. `RegimeModel.labels_walk_forward` — function — `ml.py:325-328`

```text

        Regime of every history candle as known at its time: each step is labelled by a mixture fitted only on the
        candles before it (pretraining must not label the past with a model that has seen the future).
        
```

#### 443. `RegimeModel.label_history` — function — `ml.py:351`

```text
The fitted model's regime of every candle in the history (pretraining labels its journal rows with it).
```

#### 444. `RegimeModel._name` — function — `ml.py:360`

```text
Name a cluster from its standardized center: direction from BTC 1h move + breadth, then volatility.
```

#### 445. `_CompatOnlineModel` — class — `ml.py:380`

```text
Small dependency-free online logistic model for the Python 3.10 fallback.
```

#### 446. `_CompatDrift` — class — `ml.py:405`

```text
ADWIN-shaped bounded error monitor used only when River cannot be imported.
```

#### 447. `SuccessModel` — class — `ml.py:422`

```text
Online logistic regression on journal features, reset on drift (ADWIN over its 0/1 errors).
```

#### 448. `SuccessModel.features` — function — `ml.py:449`

```text
Features from a journal row (dict or sqlite3.Row): the same columns live and on replay.
```

#### 449. `SuccessModel.state` — function — `ml.py:549`

```text
The picklable model (pretrain.py saves it; the lock is not part of it).
```

#### 450. `SuccessModel.load_pretrained` — function — `ml.py:554`

```text
Start from the pretrained model; live rows keep training it, an error drift returns to it.
```

#### 451. `TradeModel` — class — `ml.py:583-589`

```text

    eng-174 P(trade): meta-label of the trades actually taken. Features of the ENTRY row (journaled at the entry, so
    nothing of the trade's life leaks in; the 'card' row's snapshot is refreshed while the card lives), label = the
    trade's result after costs (trade_label), learned when the card closes (its real exit, not entry + 4h).
    Few rows (~40 trades a day): a drift is acted on only after trade_drift_min_rows trades since the last reset, and
    the reset refits on the last trade_refit_rows trades (no archive prior to return to).
    
```

#### 452. `trade_label` — function — `ml.py:627`

```text
Positive = the trade made money after costs, by the pessimistic R (card_r_low; card_r on rows before it).
```

#### 453. `label_of` — function — `ml.py:634`

```text
Positive = the 4h return in the signal's direction beat the universe median over the same window.
```

### `ml_eval.py`

#### 454. `<module>` — module — `ml_eval.py:1-18`

```text

Evaluation of the P(edge) model on the pretraining dataset (pretrain_rows.parquet: every labelled historical row
with its features and the online model's prediction made BEFORE it learned that row).

1. Prequential (test-then-train) quality of the online logistic regression as it ran (river, pretrain.py).
2. Purged walk-forward comparison (time folds; training rows whose 4h label window reaches into the test fold are
   dropped, plus a 4h embargo): base rate vs logistic regression vs LightGBM, rows weighted by their uniqueness
   (1 / the number of labels overlapping their 4h window: signals of one market move are not independent).
3. What it gives the trader: Edge 4h of the rows the model ranks highest vs all rows.

4. --trades (eng-174): P(trade) on the closed trades of the journal - ENTRY-row features, label card_r_low > 0,
   purging and uniqueness on each trade's real [entry, exit] interval, isotonic calibration fitted on earlier
   folds only, R of the top-ranked trades and the Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014) of the best
   threshold and of each strategy against the pool. Run: .venv/bin/python ml_eval.py --trades --db signals.db

Metrics: log-loss and Brier skill against the base rate (a model that does not beat "always the base rate" has
no information), AUC (ranking), calibration by probability decile. Run: .venv\Scripts\python ml_eval.py

```

#### 455. `uniqueness` — function — `ml_eval.py:57`

```text
1 / the number of rows whose 4h label window overlaps this row's (all coins: one market move = one event).
```

#### 456. `interval_uniqueness` — function — `ml_eval.py:194`

```text
AFML average uniqueness over each label's REAL interval [entry, exit]: the mean of 1 / concurrency inside it.
```

#### 457. `deflated_sharpe` — function — `ml_eval.py:208-211`

```text

    Bailey & Lopez de Prado (2014): P(true Sharpe > 0) of the best of M tried variants, per-trade Sharpe of r, the
    expected maximum SR0 of M null trials from the variance of the trials' Sharpes. Returns (SR, SR0, DSR).
    
```

#### 458. `load_trades` — function — `ml_eval.py:231`

```text
Closed taken trades: ENTRY row features (frozen at the entry), label, entry time, real exit time.
```

### `netstate.py`

#### 459. `<module>` — module — `netstate.py:1-7`

```text

Machine-wide network state: one WARNING when the network goes down, one INFO when it is back.

Measured (2026-09-28..30): the machine lost DNS for ~15h in 8 outages; every stream reconnect, REST poll and
aiohttp's background resolver logged its own WARNING - 13k lines that buried everything else. While the network is
down every further failure of any source is logged at DEBUG; the first data that arrives ends the outage.

```

#### 460. `NetworkState.failed` — function — `netstate.py:40-43`

```text

        A request / connection of `source` failed. True when it was handled here (a DNS failure, or any network
        error during an outage): the caller then logs nothing itself.
        
```

#### 461. `NetworkState.ok` — function — `netstate.py:59`

```text
Data arrived: ends an outage.
```

### `notifier.py`

#### 462. `<module>` — module — `notifier.py:1-10`

```text

Optional notifications for a manual trader away from the screen (CONFIG.notify, off by default).

- Windows balloon notification through PowerShell (System.Windows.Forms, no extra packages).
- Telegram: the bot token / chat id of config.local.toml, else the environment's TELEGRAM_BOT_TOKEN /
  TELEGRAM_CHANNEL_ID (the owner's channel). `post` sends briefings / watch alerts (briefing.py) as HTML.
  Every message has a topic (briefing / signals / alerts / demo / service): it goes to the channel (except
  'service') and, when notify.group_chat_id is set, to that topic's thread of the forum group.
Sending runs in background tasks with a timeout, so a slow network never blocks the scan loop.

```

#### 463. `Notifier.resume` — function — `notifier.py:83`

```text
Start the retry task for messages left in the outbox by a previous run.
```

#### 464. `Notifier._stale` — function — `notifier.py:123`

```text
Why a queued card event is no longer an instruction (None: deliver it).
```

#### 465. `Notifier._log_sent` — function — `notifier.py:139`

```text
Every Telegram send attempt with its full text (data/tg_sent.db), so alerts can be reviewed afterwards.
```

#### 466. `Notifier._redact` — function — `notifier.py:160`

```text
An error's repr without the bot token (aiohttp errors can carry the request URL /bot<token>/...).
```

#### 467. `Notifier._post` — async function — `notifier.py:165-170`

```text
POST to the Bot API; a 429 waits its retry_after and retries twice.

        The send lock protects one HTTP request at a time.  It is deliberately
        released before the retry delay so a rate-limited message cannot block
        priority alerts (or shutdown) for up to a minute.
        
```

#### 468. `Notifier.send` — function — `notifier.py:222-223`

```text
Fire-and-forget; `event` is matched against notify.events (ENTRY, TP, SL, ZONE); `card` identifies the card
        for the outbox's staleness check.
```

#### 469. `Notifier._targets` — function — `notifier.py:268`

```text
(chat id, thread id or None) of every destination of a message of this topic.
```

#### 470. `Notifier.post` — function — `notifier.py:277`

```text
A briefing / watch alert (HTML), Telegram only; long texts are split at blank lines.
```

#### 471. `Notifier.post_photo` — function — `notifier.py:303`

```text
A briefing card (PNG) with an HTML caption (<= 1024 characters), Telegram only.
```

#### 472. `Notifier._telegram_to` — async function — `notifier.py:358-359`

```text
One message to one destination; True when Telegram took it. With `priority` (a trading instruction) a failed
        delivery (HTTP 5xx / 429 / a network error / a busy lock) goes to the outbox for the retry loop (audit B05).
```

### `official_calendar.py`

#### 473. `<module>` — module — `official_calendar.py:1-21`

```text

eng-168t (audit #6): the macro releases from their OFFICIAL schedules - the primary source of the entry blackout and of
the briefing's macro line; ForexFactory's weekly feed (macro_calendar.LIVE) stays the fallback / cross-check.

Sources (each fetched with a neutral User-Agent, cached in models/official_calendar.json):
- BLS iCalendar (https://www.bls.gov/schedule/news_release/bls.ics): CPI, Employment Situation (NFP), PPI; times in
  the feed's own zone (TZID=US-Eastern -> America/New_York);
- ISM release calendar (rob-report-calendar): the year's table of Manufacturing / Services PMI release days (holiday
  moves included), 10:00 a.m. ET;
- FOMC calendar (fomccalendars.htm): meeting dates; the policy statement at 2:00 p.m. ET on the meeting's last day and
  the press conference at 2:30 p.m. ET (two events, the statement is the blackout's anchor). Notation votes skipped.

Every event: {id, type, source, t (UTC ms), tz, title, status}. status 'scheduled' or 'unconfirmed' - an event a
previous fetch listed in the future and the new fetch no longer lists is KEPT as 'unconfirmed' (a partial response is
not a cancellation; a reschedule then blocks both times, the conservative side).

Coverage (completeness, not just reachability): a category is covered when its source was fetched successfully within
OFFICIAL_MAX_AGE_SEC AND that source's schedule reaches at least COVER_DAYS ahead (an empty / short schedule - ISM before
it posts next year's table - is NOT 'no events'). Uncovered categories fall back to the fresh ForexFactory week; with
neither, macro_calendar.live_ok() is False and new entries wait (fail-closed, eng-168s).

```

#### 474. `merge` — function — `official_calendar.py:129`

```text
The new list of `source` replaces its old events; an old FUTURE event the new list lacks stays 'unconfirmed'.
```

#### 475. `refresh` — function — `official_calendar.py:138-139`

```text
Fetch every source; a source that fails or parses to nothing keeps its previous events and its old fetched_at
    (it ages into 'stale'). Returns the new STATE (also written to the cache).
```

#### 476. `covered` — function — `official_calendar.py:183`

```text
The category's official source is fresh AND its schedule reaches COVER_DAYS ahead.
```

#### 477. `status_text` — function — `official_calendar.py:206`

```text
Why the official schedule is incomplete now, else None.
```

### `pierce.py`

#### 478. `<module>` — module — `pierce.py:1-6`

```text

How far price pierces a level before it turns back, measured (research_overshoot.py -> models/overshoot.json: per coin
and level kind the p50 / p80 / p90 of the depth of rejections, 80 coins x 12 months, stable across halves; the script was removed on
2026-10-22, the saved model stays). The stop
buffer beyond a level and the "just behind" distance of a stop pool come from here instead of ATR constants.

```

#### 479. `overshoot` — function — `pierce.py:36-37`

```text
The q-quantile pierce of this kind of level on this coin (its own figure with >= 20 rejections, else its liquidity
    group's, else all coins'), in price units; None without the model.
```

#### 480. `measured_kind` — function — `pierce.py:53`

```text
The measured kind of a map zone (its first kind that has one).
```

#### 481. `kind_of_label` — function — `pierce.py:61`

```text
The measured kind behind a pool / level text label (pools carry labels only).
```

### `pools.py`

#### 482. `<module>` — module — `pools.py:1-4`

```text

Per-strategy coin pools (CONFIG.pools): every strategy trades only its own coins. See PoolsConfig for the rule and
the measurement behind the automatic exclusion. Rebuilt hourly off the loop by Scanner.pools_loop.

```

#### 483. `Pools.allows` — function — `pools.py:40`

```text
True when pools are off, not built yet, or the coin is in the strategy's pool.
```

#### 484. `Pools.rebuild` — function — `pools.py:57-61`

```text

        entries: (strategy, symbol, ts_ms, direction, net R) of the journal's replayed, non-vetoed entries.
        market_volumes: the 24h quote volume of EVERY Binance USDT perpetual (eng-59): a coin's class is its rank in
        the whole market - ranked within the 70-coin universe, 'mid = rank <= 80' meant every coin.
        
```

#### 485. `Pools.view` — function — `pools.py:118`

```text
For the dashboard: each strategy's pool and the coins excluded by their journaled results.
```

### `positioning.py`

#### 486. `<module>` — module — `positioning.py:1-11`

```text

Positioning of other traders, from public data, for coins with open cards (context and level map, never a trigger):

- Long / short ratios: Binance global accounts, top-trader accounts and top-trader positions (/futures/data, own
  limit 1000 requests / 5 min shared with openInterestHist), Bybit account ratio, OKX account ratio (5m periods).
- Hyperliquid large accounts: the chain is public, so the real positions of big traders are known, with their
  liquidation prices. Accounts = the leaderboard's most active traders by monthly volume (the file is ~40 MB, so it is
  downloaded every `hl_accounts_refresh_sec` and cached in hl_accounts.json); positions of each account every
  `hl_positions_refresh_sec`. Their liquidation prices become 'liq_hl' levels (zones.py): real, not estimated.
- OKX liquidations (REST, the last 100 per contract): refill the observed-liquidation lists after a restart.

```

#### 487. `Positioning.refresh_ratios` — async function — `positioning.py:74-78`

```text

        Ratios of the given (due) symbols in order, concurrently, as many as the /futures/data budget allows this
        5 minutes (3 Binance calls per coin); the rest stay due for the next pass. A coin keeps its previous ratios
        until new ones arrive.
        
```

#### 488. `Positioning._pick_accounts` — function — `positioning.py:153`

```text
The most active traders: top by monthly volume among accounts with enough equity (vaults trade little).
```

#### 489. `Positioning._write_leverage_mix` — function — `positioning.py:222-227`

```text

        The leverage the tracked accounts really use, weighted by notional (eng-57): it replaces the guessed
        10 / 25 / 50 / 100x mix of the liquidation estimate (zones.leverage_mix). Leverages are rounded to whole x;
        bins under 1% of the notional are dropped. Large Hyperliquid accounts are a proxy for the market's leverage,
        not Binance's own (which publishes none).
        
```

#### 490. `Positioning._maintenance_loop` — async function — `positioning.py:251-255`

```text

        Each linear contract's lowest risk tier (maintenance margin, max leverage) from Bybit's public risk limits, once
        a day -> models/maintenance.json (zones.maintenance_of). Binance's own brackets need a signed request; a flat
        0.5% understated most altcoins (SUI 1%, small caps 1.5-2.5%).
        
```

#### 491. `Positioning.hl_current` — function — `positioning.py:298`

```text
audit D03: the snapshot is younger than 6 refresh periods (a stale snapshot is no current level).
```

#### 492. `Positioning.hl_levels` — function — `positioning.py:311`

```text
Liquidation prices of the tracked accounts, summed per price bucket: the 'liq_hl' levels of the map.
```

#### 493. `Positioning._okx_liquidations_backfill` — async function — `positioning.py:331`

```text
The last 100 filled liquidations of every mapped OKX contract (one pass at start, paced).
```

### `pretrain.py`

#### 494. `<module>` — module — `pretrain.py:1-24`

```text

Pretraining on the public Binance archive (history.py) BEFORE the bot starts; live, the models keep learning.

What is trained (everything the archive has the inputs for):
- the market regime model (ml.RegimeModel): the same market-wide features per closed 15m candle (BTC 1h move and
  volatility, breadth, median funding / 1h OI change / RVOL) over months of history instead of the last days;
- P(edge) (ml.SuccessModel): the journal rows the bot would have written - phase setups (A-F) scored by the same
  indicator / scorer code on 15m candles built from 1m klines (futures + spot, OI from the 5-minute metrics, funding
  from the funding history), liquidity sweeps and breakouts from the same detector (strategies.structure.build_context
  on each closed candle with its 8 days of 1h candles), Tier-0 anomalies / impulses from the same
  calculate_tier0_metrics + rules on every minute that could qualify - each with its context (market / BTC moves, the
  coin's 1h trend, volatility, 24h volume, long-short ratios, regime, market crowd), the journal's cooldown, and the
  label the live journal gives it (the 4h return in the signal's direction beat the median of every coin).

Not in the archive (the models learn them live only): liquidations, order books, the other venues' flows / OI,
Hyperliquid accounts, Coinbase, the IsolationForest verdict (Tier-0 rows here are the rule-based ones). Whale sizes
come from live sweeps (kept across restarts). The IsolationForest itself is not pretrained: it judges "unusual
compared with the last 3 hours", which history cannot tell (its window survives restarts, ml_state.pkl).

Run:  .venv\Scripts\python pretrain.py [--months 6] [--min-volume 3e6] [--workers 3] [--rate 1000000]
Downloads are cached (history_cache/); a re-run only computes. The result is pretrained.pkl; the bot loads it at
start (journal P(edge), scanner regimes) and keeps learning on top of it. Run it while the bot is stopped or with a
low --rate: the download shares the link with the live streams.

```

#### 495. `_spot_pair` — function — `pretrain.py:56`

```text
The Binance spot pair of a futures base (1000PEPE -> PEPEUSDT), else None.
```

#### 496. `eligible_days` — function — `pretrain.py:65-70`

```text

    Days (epoch day numbers) in [start, end] on which the coin would have passed the universe's volume floor and
    listing age, from PAST data only: the average daily quote volume of the 30 days before (over the days it traded,
    at least min_listing_days of them) >= min_volume. Days whose 30 days before hold fewer than 20 known daily candles
    (the running month has no monthly 1d file) keep the last decision.
    
```

#### 497. `select_coins` — function — `pretrain.py:89-96`

```text

    (journal key, futures id, spot id, eligible days) of every USDT perpetual the ARCHIVE has - delisted ones included
    - with a Binance spot pair (the live universe requires one: CONFIG.exchange.require_spot; tokenized stocks and
    pre-IPO contracts have none) that passed the volume floor on at least one day of the window, judged day by day from
    the 30 days before it. Today's exchange list and today's 24h volume picked the coins before: delisted coins were
    missing (survivorship) and a coin that became liquid last week counted for all months (look-ahead).
    Sorted by volume over the window.
    
```

#### 498. `_bucket` — function — `pretrain.py:124-126`

```text
1m rows [ts, o, h, l, c, v, qv, tbq] -> candles of `ms` (the last, possibly incomplete one dropped). audit C16:
    as live (levels.resample), only a group holding every one of its minutes once is a candle - a 5m bar of two minutes
    is not.
```

#### 499. `closed_minutes` — function — `pretrain.py:150-151`

```text
How many 1m candles (by open time) have CLOSED by now_ms: an archive minute holds its whole minute, the live
    scanner only the seconds already passed, so a running minute must not be read.
```

#### 500. `process_coin` — function — `pretrain.py:161-164`

```text

    One coin: download, build the live data structures from history, and produce the journal rows the bot would
    have written (without the cross-coin context, added in the main process) plus the market series.
    
```

#### 501. `process_coin.season_at` — function — `pretrain.py:238`

```text
The time-of-day profile as the bot would have had it: the 4 weeks of 1h candles before that day.
```

#### 502. `process_coin.tier0_at` — function — `pretrain.py:246`

```text
calculate_tier0_metrics exactly as the scanner calls it, on the history up to now_ms.
```

#### 503. `process_coin.weekly_at` — function — `pretrain.py:277`

```text
weekly_ref of the weeks CLOSED before now_ms (as the live bot has it after each weekly close).
```

#### 504. `process_coin.context_at` — function — `pretrain.py:284`

```text
The coin's own context (the market's is added in the main process).
```

#### 505. `_weekly_closes` — function — `pretrain.py:457-461`

```text

    [close time ms, close] of the futures' COMPLETE weekly candles (Monday 00:00 UTC weeks, like Binance's 1w) from the
    archive's daily candles since ~16 months before the window (weekly_ref needs 21 closed weeks). The archive is
    point-in-time and reachable where the REST API is not.
    
```

#### 506. `_sig_keys` — function — `pretrain.py:488`

```text
What the journal row, the veto and P(edge) read from a signal (journal._base_row / _features / veto_reason).
```

#### 507. `_small` — function — `pretrain.py:501`

```text
The fields of a signal the journal row / P(edge) read, not the whole scored frame row.
```

#### 508. `_forward_stats` — function — `pretrain.py:512-516`

```text

    (grid of candle open times, the median and the mean over coins of close[t + horizon] / close[t] - 1 from each
    candle's close). The median labels P(edge) (a balanced 'beat the median coin'); the mean is the Edge baseline:
    coins beat the median by ~0.11% per 4h on average (right-skewed returns), the mean has zero excess by construction.
    
```

#### 509. `_market_series` — function — `pretrain.py:537-541`

```text

    Per 15m candle (open time) on a regular grid: the median 1h / 4h move of every coin to that candle's close, BTC's
    1h move, and the median forward 4h move from that close (the label's universe baseline). Vectorized: a
    Python lookup per journal row over every coin took minutes per 10k rows.
    
```

#### 510. `run.baseline_at` — function — `pretrain.py:622`

```text
The universe's 4h move (median or mean) from the last 5m close at or before the signal.
```

#### 511. `prune_cache` — function — `pretrain.py:770`

```text
Delete cached archive files older than the training window (+1 month): the cache would grow forever.
```

### `pumps.py`

#### 512. `<module>` — module — `pumps.py:1-16`

```text

Live pump / dump monitor of small caps (the rules of `research_pumps.py`, on each coin's closed 1h candles).

A PUMP: the close >= 15% above the lowest low of the last 6 hours, the hours since that low traded >= 3x the average
hour of the week before (DUMP: the mirror). Small caps only (not among the 30 most traded coins by 24h volume).
After the event the monitor follows the first pullback / bounce: the 38.2-61.8% zone of the move, the trigger (a 1h
close beyond the previous candle's extreme after the zone was touched), stop beyond the pullback's extreme (+ 0.25
ATR1h), TP1 = the move's extreme, TP2 = its 1.618 extension.

Measured (research/pumps.md, research/pumps_holdout.md; hit rate vs the random-walk rate of the same trade):
- after a DUMP, short the first bounce: 2023-10..2026-08 +0.17R / +0.16R (older / newer half), the untouched
  2021-04..2023-09 +0.36R / +0.34R, TP1 hit 62-69% vs 45-57% geometry: the one pre-registered part that held;
- after a PUMP, buy the first pullback: +0.13R / +0.14R in 2023-26 but -0.04R / +0.13R in 2021-23 with the hit
  rate AT the geometry: not confirmed.
Information, never an order; samples are small (a few hundred trades per period).

```

#### 513. `_atr` — function — `pumps.py:33`

```text
Wilder's ATR(n) at candle t (levels.atr_of, the bot's one ATR) over up to 200 candles before it.
```

#### 514. `scan` — function — `pumps.py:39`

```text
The latest pump / dump of the last LOOKBACK closed 1h candles and the state of its first pullback.
```

#### 515. `monitor` — function — `pumps.py:102`

```text
Every small cap of the universe with a pump / dump in the last 48h (cached per coin by its last 1h candle).
```

#### 516. `monitor_wide` — function — `pumps.py:119-120`

```text
The same monitor on the perpetuals outside the universe (Scanner.wide_watch_loop, eng-57: small caps by
    construction - the majors are in the universe).
```

### `ratelimit.py`

#### 517. `<module>` — module — `ratelimit.py:1-11`

```text

Proactive REST rate limiting.

Every REST call goes through a RestGate. A gate does two things:
- it stays under a weight budget instead of waiting for a ban: after each call it reads the exchange's own counter
  (Binance `X-MBX-USED-WEIGHT-1M`, Bybit `X-Bapi-Limit-Status`), keeps a local estimate in between, and makes
  callers wait for the next minute when the budget for their priority is used up (priority 0 may use the whole
  budget, lower priorities a smaller share, so candle backfills never queue behind journal evaluation);
- on a 429 / 418 / 403 it pauses every caller of the gate (and of gates sharing its BanState) until the ban ends,
  parsed from `banned until <ms>` or `Retry-After`, with exponential backoff as a fallback.

```

#### 518. `BanState` — class — `ratelimit.py:32`

```text
Shared pause: one ban (per IP / API cluster) stops every gate that shares this object.
```

#### 519. `RestGate.call` — async function — `ratelimit.py:131`

```text
Run `exchange.<method>(*args, **kwargs)` within the budget; on 429/418 pause everyone and retry.
```

### `raw_event_log.py`

#### 520. `<module>` — module — `raw_event_log.py:1-7`

```text
Optional append-only raw event journal for independent validation.

The logger is disabled unless ``EDGEHUNTER_RAW_LOG_DIR`` is set. It stores one
gzip JSONL member per event, preserving the bytes received before parsing and
the local receive clocks. It deliberately has no dependency on the scanner's
signal or replay code.

```

#### 521. `RawEventLog.flush` — function — `raw_event_log.py:81`

```text
Wait for queued records (offline readers / orderly shutdown; never on the event loop).
```

#### 522. `RawEventLog.append_rest` — function — `raw_event_log.py:100`

```text
Record a REST response using the same append-only envelope.
```

### `recorder.py`

#### 523. `<module>` — module — `recorder.py:1-22`

```text

Data recorder: the live-only inputs the Binance public archive does not have, written to Parquet so they can be
tested offline later (as filters for 1h-4h trades, never as tick strategies: a manual entry is seconds late).

- flow:  per second x venue x coin, taker buy / sell USD, long / short liquidation USD, trade count (all six venues;
         the FlowStore ring buffers, so nothing new is streamed). Every Binance / Bybit / OKX liquidation event is
         already kept one by one in the journal's `liquidations` table.
- depth: once a minute, the latest 30s snapshot (CONFIG.depth.heat_snapshot_sec) of each hot coin's local book (kept
         from the diff stream; REST only on (re)sync, so Binance weight does not limit this): best bid / ask, and USD
         resting in 0.1% bands from the mid out to 5% per side (flat columns bid_00..bid_49 / ask_00..ask_49), plus
         the live metrics (spread, band depth / imbalance, persistent walls).
- walls: eng-170, every wall that ended (young ones too, unlike the dashboard's >= 30s list): first seen / ended
         (30s snapshot resolution), side, price, peak USD, multiple of the median level, filled / pulled USD, why.
- deriv: per minute x venue x coin, OI (coins and USD), mark, 8h funding (Bybit / OKX / Bitget / Hyperliquid OI is
         not in any public archive).

Layout: <root>/<kind>/date=YYYY-MM-DD/HHMM.parquet per minute, merged into HH.parquet once the hour is over.

The event loop only copies the finished minute out of the ring buffers (numpy slices, ~1 ms) and hands it to the
bot's worker PROCESS (the level-map pool); building frames and writing Parquet happen there, so disk I/O and
polars never hold the loop's GIL.

```

#### 524. `flow_minute` — function — `recorder.py:42-45`

```text

    The non-zero cells of one finished minute of every venue's ring buffer. Seconds after a venue's head
    (`last_sec`) are masked: their slots still hold data from one ring period ago.
    
```

#### 525. `depth_rows` — function — `recorder.py:73`

```text
Every 500-level snapshot newer than since_ts: raw levels (bucketed in the worker) + live top-20 metrics.
```

#### 526. `wall_rows` — function — `recorder.py:84`

```text
eng-170: the walls that ended after since_ts on every hot book.
```

#### 527. `write_minute` — function — `recorder.py:124-126`

```text
Worker process: one minute of each kind to its own file. Returns the rows written. `deriv_ts_ms`: when the
    derivatives were sampled (eng-102: they were stamped with the minute's START, ~90 s before the sample - an analysis
    joining marks / OI to signals by time saw 1.5 min of the future).
```

#### 528. `compact` — function — `recorder.py:184`

```text
Worker process: merge the minute files of every hour that ended before `before_sec` into HH.parquet.
```

#### 529. `prune` — function — `recorder.py:232`

```text
Delete day folders older than keep_days.
```

#### 530. `record_loop` — async function — `recorder.py:249-252`

```text

    Once a minute: the minute that ended >= 30s ago (venue lag) goes to the worker; hourly compaction there too.
    `executor_fn()` returns the worker pool (created lazily by the scanner); `running()` stops the loop.
    
```

#### 531. `heat_history` — function — `recorder.py:298-303`

```text

    The order-book heatmap of `symbol` from the recorded depth files (0.1% bands of every 500-level snapshot): the
    chart showed only the last ~4h held in memory (DepthBook.heat). One snapshot per `every_sec`, the bands put on a
    fixed price grid of `step` (the in-memory grid when given, else 0.1% of the median mid) -> {'step', 'snapshots':
    [[epoch ms, [[price, USD +bid / -ask], ...]], ...]}, the format of DepthBook.heatmap.
    
```

### `replay.py`

#### 532. `<module>` — module — `replay.py:1-19`

```text

B9 (eng-59): the archive replay of the LIVE card lifecycle for every strategy - the live SignalBook stepped minute by
minute over the Binance public archive, fed by the live detectors (strategies.structure.build_maps / build_context and
LiveDetector for the 15m-close events, strategies.loopside.LoopDetectors for the loop-side ones, the scorer's phases and
Tier-0 rules for the continuation), with the scanner's hooks rebuilt from history. Its output is what pretraining /
meta-labeling and the per-strategy archive studies (plan 2.3-2.9, 3.1) need: every card and every entry (passed and
vetoed) with the card's own net result (`final_r`, eng-58: fees, slippage by liquidity, funding).

What the archive cannot give (the live bot has it, the replay runs without - an estimate, not the live result):
- other venues' flows / OI / funding, liquidations (so no liquidation-cascade setups: FLUSH / SQUEEZE REVERSAL), order
  books (no walls / liquidity bands / book confirmations), Hyperliquid accounts, Coinbase premium, whale sweeps;
- confirmations are Binance-only (futures / spot taker delta from the 1m candles, OI from the 5-minute metrics, VSA,
  CVD divergence); the footprint order-flow reading does not exist;
- pools / the crowd limit / BTC's bias across coins hold only for the coins replayed together (one SignalBook);
- prices are final 1m candles (the live bot sees each trade); a scan runs once per minute (live: every few seconds).

Run:  .venv\Scripts\python replay.py --months 6 --coins 20 [--workers 1] [--days N for a smoke test]
Writes data/replay/<run>/cards.parquet and entries.parquet (resumable per coin group).

```

#### 533. `_bucket_list` — function — `replay.py:45`

```text
Complete candles of `ms` from 1m rows [ts, o, h, l, c, v, qv, tbq] as [ts, o, h, l, c, qv, tbq, v].
```

#### 534. `ArchiveCoin` — class — `replay.py:52-53`

```text
One coin's history and the MarketData stand-in the live detectors read (`d1`, `h1`, `h4`, `w1`, `tier0`,
    `oi_samples`, `minute_closed_until`, `quote_volume_24h`).
```

#### 535. `ArchiveCoin.minutes` — function — `replay.py:164-165`

```text
FINAL 1m futures candles in the stream format (the scanner's _minute_candles). audit R02: 600 as the live
        buffer (MarketData.minute_klines) - 240 left PO3 21 of its 24 required Asian 5m bars at 02:15 NY.
```

#### 536. `ArchiveCoin.frame` — function — `replay.py:179`

```text
The closed 15m futures frame with indicators (the scanner's frame part).
```

#### 537. `ArchiveCoin.compute_tier0` — function — `replay.py:188`

```text
calculate_tier0_metrics exactly as pretrain.tier0_at (only CLOSED minutes).
```

#### 538. `ArchiveCoin.live_15m` — function — `replay.py:223`

```text
The running 15m candle's open time / high / low (the plan key: leg plans follow it).
```

#### 539. `_weeks` — function — `replay.py:243`

```text
Binance weekly candles (Monday 00:00 UTC) from daily ones; the running week dropped.
```

#### 540. `Replay` — class — `replay.py:266`

```text
Several coins stepped together through one live SignalBook.
```

#### 541. `Replay._tf_atrs` — function — `replay.py:329`

```text
Scanner._tf_atrs on the archive: Wilder's ATR14 (levels.atr_of) of the closed 1h / 4h / daily candles.
```

#### 542. `Replay._band` — function — `replay.py:342-343`

```text
audit R03: the live exit's band (Scanner._opposite_band) - BB(20, 2) of the closed 4h candles built from
        the closed 1h ones known at asof_ms (the as-of rule of _manage_trade; now when None).
```

#### 543. `Replay._enrich` — function — `replay.py:355`

```text
The subset of Scanner._enrich the archive can rebuild (the rest stays None).
```

#### 544. `Replay._maps` — function — `replay.py:379`

```text
At a 15m close: every coin's quick map + context (build_maps, as the scanner's maps worker).
```

### `research/exit_bt/audit.py`

#### 545. `<module>` — module — `research/exit_bt/audit.py:1-16`

```text
Strategy audit: the bot's OWN detector functions (strategies/*.py, imported unchanged) called bar by bar on Binance
15m history (data/*.npy, 43 perps, 2025-08 .. 2026-10), each signal managed with the bot's exit plan in a simplified
form. Stop-first inside a bar (pessimistic); costs 0.20% round trip; R = initial risk; holdout from bt.SPLIT.

  BB W-BOTTOM / M-TOP   bollinger_wm_event(last 90 15m)   entry at the signal close; stop beyond the retest
                        (bb_stop, + 0.1 ATR pad); out when price reaches the live opposite band; 12h cap; the
                        plan's low_rr skip (band at the signal pays <= risk)
  VA80 LONG / SHORT     value_area_event(m15, cut)        entry at the close; stop the day's extreme; TP the far
                        value-area edge; out at the UTC day's close
  RSI2 LONG / SHORT     connors_event(daily)              entry at the daily close; out at the first close beyond
                        the SMA5; catastrophic stop 3 daily ATR; 60-day cap
  SPRING / UTAD         wyckoff_events(1h)                entry at the close; stop the spring / UTAD extreme; TP the
                        range's far side; 5-day cap
Not modelled: the bot's vetoes / confirmations / LTF triggers (they can only filter these signals).
Run: python -I audit.py [--setups bb,va,rsi2,wyckoff] [--symbols N]

```

#### 546. `agg` — function — `research/exit_bt/audit.py:32`

```text
15m rows -> k x 15m rows (ts, o, h, l, c, v), complete groups only, aligned to k*15m boundaries.
```

#### 547. `manage` — function — `research/exit_bt/audit.py:45`

```text
From bar i0 on: stop first, then target / live band. Returns (R net, exit index).
```

### `research/exit_bt/audit_ict.py`

#### 548. `<module>` — module — `research/exit_bt/audit_ict.py:1-7`

```text
ICT audit: the bot's own po3() and silver_bullet() (strategies/po3.py, silver_bullet.py, unchanged) on Binance 5m
history of the top-5 majors (data5/*.npy). Called at every 5m close inside their windows; one signal per window and
direction (the bot's gate). Plan as in the bot: a resting limit at the FVG's CE (filled if price returns to it while
the card waits: 3h PO3 / 1h SB), invalid if the extreme breaks first; stop the raid's extreme; target po3_target /
sb_target (first target); time cap 12h PO3 / 4h SB. Bias variants: none, and the daily bias = the last closed day
vs its SMA20 (a proxy of the bot's weekly / daily bias). Costs 0.07% (limit entry) and 0.20%.
Run: python -I audit_ict.py
```

### `research/exit_bt/bt.py`

#### 549. `<module>` — module — `research/exit_bt/bt.py:1-8`

```text
Exit-rule backtest for the bot's ORB (Crabel) and Turtle System 2 setups on Binance USDT-M 15m klines.

Entries are the bot's canon (strategies/classic.py stretch, strategies/turtle.py 55/20 channels, 2N, 0.5N adds);
only the exit / stop management varies. Intrabar order is unknown on 15m bars, so every bar checks the stop
FIRST (pessimistic), and trailing levels are updated from a bar only for the NEXT bar (no look-ahead).
Results are in R = the first unit's initial risk; costs 0.20% round trip per unit (taker 0.05% x2 + slippage).
Split: development = before SPLIT, holdout = after. Run: python bt.py

```

#### 550. `orb_trade` — function — `research/exit_bt/bt.py:61`

```text
Manage one ORB trade from bar i0 under rule r. Returns (R net, MFE R, exit index).
```

### `research/exit_bt/charts.py`

#### 551. `<module>` — module — `research/exit_bt/charts.py:1-3`

```text
Charts of the demo trades for a manual review: Binance 15m candles from 36h before the entry to 8h after the close,
the entry / stop / targets / exit, the 1h swing highs / lows of the 3 days before the entry (5-bar fractals) and the
previous day's high / low. 4 trades a picture. Run: python -I charts.py OUT_DIR
```

### `research/exit_bt/demo_be.py`

#### 552. `<module>` — module — `research/exit_bt/demo_be.py:1-6`

```text
The owner's proposal on the bot's REAL demo trades, in USDT: once price moves +X in the trade's favour, the stop
goes to break-even INCLUDING costs (entry +- fees + slippage); if that stop fills and price then crosses back beyond
the exit level in the trade's direction while the original trade would still be alive, re-enter at market (same qty,
original stop, same BE rule), at most `max_re` times. Baseline = the demo trade's actual USDT result.
Path: Binance 1m klines from the actual fill to the actual close (open trades: to now). Costs per side: taker 0.05% +
slippage 0.05% of notional. Stop first inside a minute (pessimistic). Run: python -I demo_be.py
```

#### 553. `sim` — function — `research/exit_bt/demo_be.py:27`

```text
USDT result with the BE + re-entry rule. trig = favourable move (fraction of price) that arms break-even.
```

### `research/exit_bt/fetch.py`

#### 554. `<module>` — module — `research/exit_bt/fetch.py:1`

```text
Download Binance USDT-M 15m klines from data.binance.vision (monthly + daily zips) into data/<SYM>.npy.
```

### `research/exit_bt/fetch5.py`

#### 555. `<module>` — module — `research/exit_bt/fetch5.py:1`

```text
Download Binance USDT-M 5m klines from data.binance.vision (monthly + daily zips) into data/<SYM>.npy.
```

### `research/exit_bt/majors.py`

#### 556. `<module>` — module — `research/exit_bt/majors.py:1`

```text
ORB on majors only (daily open, session range, session Stretch), net and gross of costs. Run: python -I majors.py
```

### `research/exit_bt/sessions.py`

#### 557. `<module>` — module — `research/exit_bt/sessions.py:1-4`

```text
Session-anchored ORB: range = first 30m (2 bars) after a session open, entry on a break of that range (buy stop at
range high / sell stop at range low), stop = the opposite side, exit at the session end. Also Crabel's Stretch from
the session open (open +- 10-session SMA of min(H-O, O-L)). DST: each date's own London / New York
offsets (zoneinfo). Run: python -I sessions.py
```

#### 558. `_utc_hm` — function — `research/exit_bt/sessions.py:14-15`

```text
audit N27: the local open h:m of the date d in `zone` as UTC (h, m) - the DST rules of THAT year (fixed
    Mar 9 / Nov 2 and Mar 30 / Oct 26 were 2025's dates: 2026-03-08 09:30 NY read 14:30 UTC instead of 13:30).
```

### `research/exit_bt/tf.py`

#### 559. `<module>` — module — `research/exit_bt/tf.py:1-3`

```text
Timeframe sensitivity of the session ORB on the top-5 majors: opening-range length (15/30/60/120m) x bar
resolution (5m vs 15m) x costs. Range = the first M minutes after the session open, entry on a break of it, stop = the
other side, out at the session end; stop-first inside a bar (pessimistic). Run: python -I tf.py
```

### `research/exit_bt/wide.py`

#### 560. `<module>` — module — `research/exit_bt/wide.py:1-3`

```text
Session ORB on top-5 majors with a WIDE risk: entry on the break of the first M-minute range (as tf.py), but the
stop = k x daily ATR(14) from the entry and a fixed target at T R; out at the session end otherwise. Costs in R shrink
by the wider stop. Pessimistic stop-first inside a bar. Run: python -I wide.py
```

### `scanner.py`

#### 561. `play_alert_sound` — function — `scanner.py:51`

```text
Play Windows system sound asynchronously (non-blocking).
```

#### 562. `_orb_shadow_row` — function — `scanner.py:65-66`

```text
eng-150: what journal.record_entry reads of a card, for the 13:30 UTC ORB variant (vetoed 'variant_orb_open',
    the stop the opposite Stretch level, no targets: the replay's hold8_r measures it).
```

#### 563. `make_entry_intent` — function — `scanner.py:78`

```text
Freeze the small mutable card fields before scheduling executor work.
```

#### 564. `_FrameLookup` — class — `scanner.py:92-97`

```text

    dict-like .get(symbol, include_live=False) for the tracked cards.  Closed 15m candles are the default; only a
    strategy that explicitly opts into ``follows_live_candle`` receives the in-progress OHLC.
    `parts` = the closed frame split per symbol once per heavy pass: filtering the whole universe's frame for every
    card on every scan blocked the event loop for over a second with ~40 cards.
    
```

#### 565. `_rr_text` — function — `scanner.py:125-126`

```text
R:R for a log line: to TP1 and blended, or 'none' (the Turtles have no target: rr_tp1 None crashed the entry's
    output and its demo order, live AAVE 2026-10-02 04:33).
```

#### 566. `_row8` — function — `scanner.py:134`

```text
A candle as exactly 8 floats [t, o, h, l, c, quote, taker buy quote, base], None / missing fields NaN.
```

#### 567. `Scanner` — class — `scanner.py:140-148`

```text

    Orchestration:
    - Tier-0 loop (every check_interval_sec): raw impulse metrics from the streams of every venue, anomaly flags
      with hysteresis, hot symbols (order books / Hyperliquid trades), footprints of cards in the zone;
    - scan loop (every scan_interval_sec): merge kline rows; the heavy Polars pass (indicators + phase scores of
      CLOSED 15m candles) only runs when a candle closed or history changed; the light pass every scan joins the
      cached scores with live Tier-0 metrics, feeds the signal book, journal, notifications and dashboard;
    - universe loop: re-selects the top symbols hourly; state loop: persists open cards / whale histograms.
    
```

#### 568. `Scanner._loopside_m15` — function — `scanner.py:251-253`

```text
The closed 15m candles of a symbol for the loop-side detectors (read-only for them). Every detector of every
        coin asked part_candles() to rebuild the whole list from the Polars frame (watchdog: 1-2 s loop stalls in
        part_candles): kept per frame object, a 15m close replaces the frame and with it the entry.
```

#### 569. `Scanner._volume_rank` — function — `scanner.py:263`

```text
The coin's rank by 24h quote volume among the scanned markets (1 = largest), refreshed once a minute.
```

#### 570. `Scanner._panel_prewarm_loop` — async function — `scanner.py:368-370`

```text
audit-80: the classic indicator panel of every coin with a live card, both directions, computed in a thread
        right after the 15m / 1h closes, so the confirmation asked on the loop finds it cached (strategies/ind_panel:
        rolling windows over 500 candles stalled the loop 1-2s at the closes).
```

#### 571. `Scanner._demo_report_loop` — async function — `scanner.py:383-384`

```text
audit-80: yesterday's demo trades per strategy to the demo topic at 00:05 UTC, and an alert (never a block)
        once today's closed trades lost CONFIG.executor.day_alert_r R.
```

#### 572. `Scanner.tier0_loop` — async function — `scanner.py:448`

```text
Fast loop: Tier-0 raw anomaly detection, hot-symbol subscriptions, footprints.
```

#### 573. `Scanner._tier0_metrics` — function — `scanner.py:462`

```text
Tier-0 metrics of every symbol: core (price / OI / RVOL) + order flow of all venues.
```

#### 574. `Scanner._journal_rush` — function — `scanner.py:514-516`

```text
eng-89: a burst of rush orders (30 s count >= rush_min_n and z >= rush_z against the coin's last hour) is
        journaled as a RUSH BUY / RUSH SELL row (kind 'rush': data only, never a card or an alert) - the journal's ret_*
        then show what followed the first seconds of an event.
```

#### 575. `Scanner._score_anomalies` — async function — `scanner.py:579`

```text
Compatibility hook: ML inference was removed from the live loop.
```

#### 576. `Scanner._update_hot` — async function — `scanner.py:583-587`

```text

        Hot symbols (order books, Hyperliquid trades): cards in a trade > in the zone > watching > anomalies /
        structured bursts, at most depth.max_symbols. A subscription younger than tier2_min_age_sec, or wanted within
        tier2_hold_sec, is kept so a slot is not re-subscribed and dropped every few seconds.
        
```

#### 577. `Scanner._merge_frames` — function — `scanner.py:660`

```text
Worker thread: append finalized candles to their frames -> [(frame, needs_backfill)].
```

#### 578. `Scanner._merge_rows` — async function — `scanner.py:671`

```text
Merge stream kline rows into the frames; returns closed-only frames, funding, closed_until, signature.
```

#### 579. `Scanner._accumulate_agg` — function — `scanner.py:738-742`

```text

        On each closed 15m futures candle, store its multi-venue futures net flow and extra-spot net flow. All
        symbols closing the same candle are computed in ONE vectorized pass (per-symbol passes copied the whole
        buffer 300 times and blocked the event loop for ~8s at every 15m close).
        
```

#### 580. `Scanner._drain_history_skips` — function — `scanner.py:921`

```text
eng-132: the strategies a history gate stopped (loop side and the maps worker's contexts) to the journal.
```

#### 581. `Scanner.blind_text` — function — `scanner.py:934-935`

```text
'pump 284 coins, ...': the strategies a history gate stopped on at least `min_coins` coins within the window
        (after a restart the 1h / 1d histories load for about an hour: those strategies see nothing until then).
```

#### 582. `Scanner._detect_setups` — function — `scanner.py:945`

```text
Detected setups of this scan as signals (the coin's live Tier-0 metrics + the setup's leg / note).
```

#### 583. `Scanner._opposite_band` — function — `scanner.py:978-980`

```text
BB(20, 2) of the closed 4h candles (eng-84: the W / M is read on 4h; was 15m): the upper band for a long,
        the lower for a short (Bollinger exit). The 4h candles are built from the coin's closed 1h candles; asof_ms:
        only the 4h candles closed by then (the 1m exit loop judges each minute on the band it could see).
```

#### 584. `Scanner.wide_watch_loop` — async function — `scanner.py:993-999`

```text

        eng-57: the universe holds 70 coins with complete data (a spot pair, >= 2 other venues, >= $10M): the biggest
        small-cap pumps / dumps (no spot pair, a fresh listing) were never seen. Once an hour (a few minutes after the
        close) the 1h candles of every other USDT perpetual >= wide_min_volume run the pump / dump monitor (dashboard)
        and the dump-bounce rule; its events are JOURNALED (vetoed 'outside_universe': no streams there, so no card /
        demo trade) - the forward test of the research rule on the whole market it was measured on.
        
```

#### 585. `Scanner._sweep_wick` — function — `scanner.py:1062-1065`

```text

        What happened on the sweep candle (journal features; stats decide whether they matter): liquidations of the
        swept side on every venue (the stops that ran are forced exits) and the Binance OI change across the candle.
        
```

#### 586. `Scanner._recorder_executor` — function — `scanner.py:1075`

```text
Dedicated process: recorder failures must not poison level-map computation.
```

#### 587. `Scanner._maps_executor` — function — `scanner.py:1089-1092`

```text

        One worker PROCESS for level maps (zones.build_raw + detector contexts, pure Python): in threads they held the
        GIL after every 15m close while ~300 maps were rebuilt, and the loop stalled 1-4s.
        
```

#### 588. `Scanner._map_job` — function — `scanner.py:1111-1114`

```text

        Inputs of one map, copied on the loop (the deques change under the loop; a copy is consistent); the 15m frame is
        sent as its few needed columns and turned into candles in the worker.
        
```

#### 589. `Scanner._correlates` — function — `scanner.py:1129`

```text
The SMT correlates' 15m histories (BTC for every coin, ETH for BTC): the long REST history + the frame.
```

#### 590. `Scanner._schedule_context_refresh` — async function — `scanner.py:1178`

```text
Replace a context refresh only after the previous writer has stopped.
```

#### 591. `Scanner._refresh_contexts` — async function — `scanner.py:1191`

```text
Quick level maps / sweep pools of every coin whose closed 15m candles changed (worker process).
```

#### 592. `Scanner._update_volatility` — function — `scanner.py:1231`

```text
Typical 15m price / OI moves from the heavy pass (Tier-0 z-scores).
```

#### 593. `Scanner._tf_atrs` — function — `scanner.py:1241`

```text
Wilder's ATR14 (levels.atr_of, the bot's one ATR) of the coin's closed 1h / 4h / daily candles.
```

#### 594. `Scanner._update_market_state` — function — `scanner.py:1254-1257`

```text

        The market every setup trades in (a feature, journaled and learned): the universe's median 15m-close move
        over the last 1h / 4h and BTC's last 1h - one market factor explains about half of all coins' moves.
        
```

#### 595. `Scanner._shadow_market` — function — `scanner.py:1291-1299`

```text

        eng-149 (plan eng-148, stages 2.4 / 3.8; journal only, no rule reads them):
        - btc_below_ema50_4h: BTC's last closed 4h close under the EMA50 of its 4h closes;
        - liq_cascade_2h: the universe's long liquidations of the last 2h over the 2h average of the 22h before
          (a falling-market cascade at >= 3, the heuristic of the plan's market_down variant);
        - mkt_down_alt: 1 when either holds - the shadow variant of market_down (BTC 4h EMA50 or a cascade);
        - smt_majors: ICT SMT between BTC and ETH on the last 24 closed 1h candles: +1 = one made a new low of the
          window and the other did not (bullish), -1 = the same at the highs, 0 = none.
        
```

#### 596. `Scanner._shadow_coin` — function — `scanner.py:1337-1343`

```text

        eng-149 (plan eng-148, stages 3.5 / 3.7 / 0.4; journal only): Crabel's narrow-range days on the last closed
        daily candle (nr4 / nr7: its range is the smallest of the last 4 / 7; inside_day: inside the day before), and
        the coin's volatility regime on closed 1h candles - atr_ratio = ATR(14) / the mean ATR(14) of the last 100
        hours, vol_regime = 'climax' (>= 1.8), 'compression' (<= 0.7), 'trend' (efficiency ratio of 14h >= 0.4)
        or 'range' (heuristic cuts, a label to split by, not a rule).
        
```

#### 597. `Scanner._positioning_features` — function — `scanner.py:1368-1374`

```text

        eng-52 journal features (Compass review; context only, no rule uses them except the premium in `crowded`):
        the mark-vs-index premium over the last hour and its z-score against 24h (Binance's funding is stuck at 0.01%
        inside the premium's neutral band), the 1h funding mode (Binance moves a contract to hourly funding after a
        capped settlement), OI / 24h volume (leverage), Kaufman's efficiency ratio and the Choppiness index of the
        last 14 hours, and the coin's 24h return net of BTC x beta in its own residual std (relative strength).
        
```

#### 598. `Scanner._btc_momentum` — function — `scanner.py:1421`

```text
eng-100: BTC's return over the last regime_days CLOSED daily candles (the market regime), None without them.
```

#### 599. `Scanner._btc_bias` — function — `scanner.py:1433-1436`

```text

        eng-59: BTC's ICT bias (weekly, else daily: the close beyond the previous candle's high / low), the direction
        altcoins' ICT models trade with (SignalBook._against_day: 'against_btc').
        
```

#### 600. `Scanner._enrich` — function — `scanner.py:1452`

```text
Live context that is not part of the scored row.
```

#### 601. `Scanner._coinbase_premium` — function — `scanner.py:1550-1553`

```text

        Coinbase USD price vs Binance spot (USDT): the live Coinbase trade when it is fresh, else Coinbase's last price
        from the bulk products call (at most two calls old); no value only for a coin not listed on Coinbase.
        
```

#### 602. `Scanner._minute_hole_pass` — async function — `scanner.py:1570-1576`

```text
Repair missing closed minutes, prioritising the worst symbols.

        The old fixed 15-symbol/10-minute cadence could not catch up after a
        reconnect wave across the universe.  The budget is configurable and
        the per-symbol retry interval is short enough to keep the queue moving
        while the REST gate still controls exchange weight.
        
```

#### 603. `Scanner._btc_m5` — async function — `scanner.py:1604`

```text
eng-160b: BTC's last 290 closed 5m candles for the beta residual (pd_vs_btc_resid), cached per 5 minutes.
```

#### 604. `Scanner._pd_enrich` — async function — `scanner.py:1620-1621`

```text
eng-159: the detector's features on the source's 24h baselines - the last 289 closed 5m candles (REST, once
        per PUMP / DUMP START) + the 1m ring; the activation lead time found by the detector is kept.
```

#### 605. `Scanner._minute_candles` — function — `scanner.py:1649`

```text
FINAL futures 1m candles only: entry triggers are closes, and a running minute's close is just the live price.
```

#### 606. `Scanner._price_of` — function — `scanner.py:1659-1662`

```text

        Freshest futures price: the latest ticker sample or the 1m kline close, whichever is newer. None when both
        are older than PRICE_MAX_AGE_SEC, so a stalled stream never drives SL/TP decisions with a frozen price.
        
```

#### 607. `Scanner._candles_15m` — function — `scanner.py:1689`

```text
Closed 15m futures candles [ts, o, h, l, c, quote_vol, taker_buy] and the latest ATR.
```

#### 608. `Scanner.levels_loop` — async function — `scanner.py:1715-1718`

```text

        Keep the level map of every coin with an open card: 1h history (REST, hourly), rebuilt in a worker thread
        when a 15m candle closed, the 1h history changed or refresh_sec passed.
        
```

#### 609. `Scanner._live_levels` — function — `scanner.py:1756`

```text
Order-book walls standing >= 10s (hot coins only) and Hyperliquid large accounts' liquidation prices.
```

#### 610. `Scanner._plan_key` — function — `scanner.py:1769-1772`

```text

        Everything a card's plan is computed from; the book recomputes the plan only when this changes. Items 1-3 are
        the live 15m candle (only leg plans follow it: signal_book.LIVE_KEY).
        
```

#### 611. `Scanner.coin_detail` — async function — `scanner.py:1794`

```text
One coin for the web page: candles, the level map (the card's plan when there is one), open cards.
```

#### 612. `Scanner._flow_series` — function — `scanner.py:1885-1886`

```text
[[open ms, open interest (base), futures taker delta USD, spot taker delta USD]] of the last 500 15m candles
        (the chart's OI / CVD panes; the page accumulates the deltas into CVD over the visible window).
```

#### 613. `Scanner.event_risk_loop` — async function — `scanner.py:1899-1900`

```text
Binance's Monitoring Tag and scheduled perpetual delistings (event_risk.py), hourly; the Binance / Upbit
        announcements (eng-135) every 2 minutes; all off the loop.
```

#### 614. `Scanner.pools_loop` — async function — `scanner.py:1915`

```text
Per-strategy coin pools (pools.py), rebuilt every CONFIG.pools.refresh_sec off the loop.
```

#### 615. `Scanner.macro_loop` — async function — `scanner.py:1935`

```text
FRED macro context (US10Y, dollar index, Brent) for the scenario card, refreshed every 6h off the loop.
```

#### 616. `Scanner.universe_loop` — async function — `scanner.py:1948`

```text
Re-select the universe hourly: new listings join, dropped coins leave (open cards finish first).
```

#### 617. `Scanner.positioning_loop` — async function — `scanner.py:1982-1985`

```text

        Long / short ratios (Binance, Bybit, OKX; context and journal features): coins with open cards every
        positioning_cache_sec, every other universe coin every positioning_universe_sec, cards first.
        
```

#### 618. `Scanner.state_loop` — async function — `scanner.py:2004`

```text
Every minute: persist state and log a health line (loop timings, per-venue message rates).
```

#### 619. `Scanner._market_context` — function — `scanner.py:2131`

```text
BTC / ETH price, 5m move and funding for the header.
```

#### 620. `Scanner._entry_still_actionable` — function — `scanner.py:2178-2179`

```text
The notifier's retry check of a queued ENTRY (audit 2026-10-18 P1): None while the trade is open and the price
        still pays the plan's minimum R:R to TP1 against its stop (strategies.geometry's rule); else why not.
```

#### 621. `Scanner._notify` — function — `scanner.py:2195-2196`

```text
Card events for Telegram / toasts in Russian (the owner, 2026-10-07: the English one-liner with internal
        confirmation keys and the no-target placeholders as TPs was unreadable).
```

### `scenario_snapshot.py`

#### 622. `<module>` — module — `scenario_snapshot.py:1`

```text
Immutable publication snapshot shared by briefing and outcome consumers.
```

### `scenarios.py`

#### 623. `<module>` — module — `scenarios.py:1-16`

```text

Two-sided level scenarios of one coin (the "scenario card"): the reaction zone the price is in, the next resistances
above and supports below on the 1h map, a LONG scenario (close above the reaction zone and a retest -> the
resistances above) and a SHORT scenario (a rejection at the first resistance -> the supports below), each with entry,
stop, three targets and R:R. Nothing is entered: the card says what would have to happen first.

The probability shown is P(the first resistance is reached before the first support), from a model trained on the
Binance archive with THE SAME level and feature code (`train_scenarios.py`, walk-forward, calibrated); without a
model file, or when the model did not beat the geometric baseline out of sample, the card shows the geometric
baseline of a driftless random walk, d_down / (d_up + d_down), labelled as such. Never a promise: a calibrated
frequency of similar past situations.

Levels (1h candles only, so live and training see the same inputs): intact 1h and 4h swings, equal highs / lows,
previous day / week and session highs / lows, the 8-day volume profile of the 1h candles, round numbers; merged at
`merge_atr` x ATR(1h); zones weaker than `min_strength` are skipped for the scenario ladder.

```

#### 624. `daily_from_1h` — function — `scenarios.py:70`

```text
UTC daily candles [ts, o, h, l, c, quote_vol] from complete days of 1h candles.
```

#### 625. `levels_htf` — function — `scenarios.py:85-88`

```text

    The higher-timeframe range: intact daily swings (90 days), the previous week's / month's high and low, the 30-day
    range high / low and the 30-day volume profile (POC / VAH / VAL / HVN of the 1h candles: the range's value area).
    
```

#### 626. `htf_context` — function — `scenarios.py:115`

```text
Weekly trend (EMA20 of weekly closes vs 4 weeks before) and the price's place in the 30-day range.
```

#### 627. `_trend` — function — `scenarios.py:144`

```text
EMA slope over the last 5 bars, in % of price.
```

#### 628. `ladder` — function — `scenarios.py:158`

```text
The reaction zone (holding or nearest to the price), up to 3 zones above and 2 below, >= 1 ATR apart.
```

#### 629. `load_model` — function — `scenarios.py:223`

```text
The trained model when it beat the geometric baseline out of sample (cached by file mtime).
```

#### 630. `build` — function — `scenarios.py:275-278`

```text

    The scenario card of one coin from its 1h candles (>= 50) and the live price. model: None = the saved model when it
    passed, False = the geometric baseline (training), a dict = that model.
    
```

#### 631. `label_first_touch` — function — `scenarios.py:332`

```text
1 if `up` is touched before `down` in the candles, 0 if `down` first, None if neither (or both in one bar).
```

### `scorer.py`

#### 632. `PhaseScorer` — class — `scorer.py:26-38`

```text

    Asymmetrical scoring of five market phases on CLOSED 15m candles, vectorized with pl.when().then().otherwise().
    Each condition adds points independently; long = A + B + E (bullish), short = C + D (bearish).

    The conditions follow the standard crypto order-flow reading:
    - price/OI matrix: price up + OI up = new longs (strong), price up + OI down = short covering (fades),
      price down + OI up = new shorts (strong), price down + OI down = long liquidation (exhaustion, near bottoms);
    - CVD: net taker selling absorbed while price is flat = accumulation, a new high on net taker selling =
      bearish divergence (distribution); spot-led flow is sturdier than perp-led flow;
    - funding: extreme positive = crowded longs, extreme negative = crowded shorts.
    The weights are hand-set hypotheses; the journal (stats.py) measures them live.
    All frames carry a 'symbol' column (see indicators.compute_indicators_batch), so one call scores every symbol.
    
```

#### 633. `PhaseScorer.calculate_scores` — function — `scorer.py:51-55`

```text

        Price/CVD structure comes from the spot frame (the futures frame for futures-only listings);
        OI, funding, RVOL and perp flow come from futures, as-of joined on (symbol, timestamp). `tier0` is one
        symbol's metrics (dict) or a frame with a 'symbol' column and TIER0_COLUMNS.
        
```

#### 634. `PhaseScorer._spot_perp` — function — `scorer.py:121-125`

```text

        Spot vs perp net flow over the last hour. Perp-led: the perp side drives the move while spot disagrees or
        barely participates (spot net flow < perp_led_spot_share of the perp net flow); such moves fade more often.
        The perp side uses the multi-venue aggregate once enough candles were accumulated (agg_ready).
        
```

#### 635. `PhaseScorer.flag_tier_0_anomaly` — function — `scorer.py:143-150`

```text

        Tier-0: raw impulse, independent of Score and phases. Any single condition is enough:
        - RVOL_1m above the threshold on a minute of real size, except in the first seconds after a quarter-hour
          boundary (algo bursts);
        - |price 5m| / |OI 5m| above BOTH the absolute floor and the coin's own z-score threshold;
        - net whale sweeps >= whale_net_units; an algo cluster; a liquidation cascade;
        - ONE-VENUE: most of the 5m net flow came from a single venue while several are active.
        
```

#### 636. `PhaseScorer._oi_building` — function — `scorer.py:197`

```text
OI rising over the last hour in the coin's own terms (z >= trend_oi_z of its 1h change, floor), else fixed.
```

#### 637. `PhaseScorer._score_phase_a_accumulation` — function — `scorer.py:208-214`

```text

        Phase A: accumulation (bullish) - a tight range where aggressive selling is absorbed by resting bids.
        - Bollinger width near its lookback minimum (squeeze) (+1)
        - Range over the window within flat_range_atr ATRs while taker SELLERS dominate its volume: the sells are
          absorbed, price does not break down (+2)
        - Futures OI growing over the same window while the range holds: positions built quietly (+1)
        
```

#### 638. `PhaseScorer._score_phase_b_spring` — function — `scorer.py:231-240`

```text

        Phase B: Wyckoff spring (bullish) - a shallow sweep below an established trading range that sellers could
        not hold.
        - The prior 20 candles form a range (high - low within spring_range_atr ATRs) that drifted sideways (net move
          <= spring_max_drift of that span), not a downtrend channel
        - The low pierces that range's low by at most spring_max_depth_atr ATRs and the candle closes back above it
        - Close in the top 30% of the candle on net taker selling: the sell stops were absorbed by bids
        Volume is not required: a quiet spring is the classic strong one; the LTF entry requires the Wyckoff "test"
        (a pullback on lower volume, levels.pullback_volume_ok).
        
```

#### 639. `PhaseScorer._score_phase_c_distribution` — function — `scorer.py:261-268`

```text

        Phase C: distribution / bull trap (bearish), all at a new 50-candle high.
        - Net taker flow over the last 20 candles clearly negative (buyers <= 47.5%): price up on selling =
          bearish CVD divergence, someone sells into strength (+2)
        - Funding above the extreme: longs pay heavily at the top (+1)
        - OI still rising with funding crowded (> orderflow.crowded_funding_long): leveraged longs piling in late (+1)
        - Spot net selling over the last hour at the high: the real (unleveraged) side distributes (+1)
        
```

#### 640. `PhaseScorer._score_phase_d_dump` — function — `scorer.py:290-298`

```text

        Phase D: breakdown continuation (bearish) - price down + OI up = new shorts with conviction.
        - Close below the lower Bollinger band out of a squeeze (Bollinger's method I)
        - Taker sells dominate the candle (delta_ratio < dump_delta_ratio)
        - OI up at least dump_oi_min over the short window (new shorts opening, not just longs closing)
        - Funding not already crowded short (squeeze risk)
        Falling price with collapsing OI is long liquidation, i.e. exhaustion; that belongs to phase E.
        A perp-led breakdown (spot not selling) is vetoed downstream (journal.veto_reason).
        
```

#### 641. `PhaseScorer._score_phase_e_capitulation` — function — `scorer.py:312-320`

```text

        Phase E: capitulation / selling climax (bullish reversal candidate).
        - Volume climax (RVOL > rvol_anomaly_threshold) after a real decline (>= capitulation_min_drop over the
          window), with OI dropping sharply over the short window: forced long liquidation (+2)
        - Funding below the negative extreme: shorts crowded after the flush (+1)
        - Reversal confirmation: long lower wick or buyers >= 55% of the candle (+2)
        - Spot net buying over the last hour: spot absorbs the perp flush (+1)
        - Long liquidations cascading (observed, not inferred from OI) (+1)
        
```

#### 642. `PhaseScorer._score_phase_f_markup` — function — `scorer.py:351-361`

```text

        Phase F: markup breakout continuation (bullish), the mirror of phase D - price up + OI up = new longs with
        conviction.
        - Close above the upper Bollinger band out of a squeeze (Bollinger's method I: the band break counts only after
          the bands narrowed to their lookback minimum; a tag of a wide band is not a signal)
        - Taker buys dominate the candle (delta_ratio > markup_delta_ratio)
        - OI up at least dump_oi_min over the short window (new longs opening, not just shorts covering)
        - Funding not already at the long extreme (a crowded top)
        Rising price with collapsing OI is a short squeeze, which fades; a perp-led breakout (spot not buying) is
        vetoed downstream (journal.veto_reason).
        
```

#### 643. `PhaseScorer.get_latest_signal` — function — `scorer.py:384`

```text
Signal from the last row of a single-symbol scored frame.
```

#### 644. `score_closed` — function — `scorer.py:500-504`

```text

    Score every symbol in one pass and return, per symbol, the scored row of its last CLOSED candle
    (timestamp <= closed_until[symbol], the base market's newest finalized candle). Structured phases are read
    only from closed candles: an in-progress 15m candle can still change its close, wick and delta.
    
```

#### 645. `signals_from_rows` — function — `scorer.py:518-521`

```text

    The per-scan light pass: cached closed-candle rows (structured scores) + fresh Tier-0 metrics -> signals.
    Symbols without candle history still get the Tier-0 check.
    
```

#### 646. `score_all_symbols` — function — `scorer.py:554`

```text
Heavy + light pass in one call (tools and tests). Without closed_until every symbol's last row counts.
```

### `scripts/acceptance_briefing.py`

#### 647. `<module>` — module — `scripts/acceptance_briefing.py:1-18`

```text

False acceptance of the published briefing zones (eng-168z1, audit #9) - a DESCRIPTIVE measurement of the zones the
briefings actually showed (frozen in data/briefings.jsonl), not of today's map and not a backtest of new rules.

Per published record (silent ones excluded) and zone: the first CONFIRMING close after the post - a close above the
zone's hi (up) or below its lo (down) on the confirmation timeframe - when price was NOT already beyond that edge at the
post. Counted twice, independently, on 1h and on 4h closes (the paired report), and once on the zone's own conf_tf when
the record has it (the policy report). After the confirming close, on the 1h closes that follow (the clock starts at
the confirming candle's CLOSE, for 1h and 4h alike), within N = 1 / 2 / 4 / 8 / 12 hours:
  inside  - a 1h close back between lo and hi;
  origin  - a 1h close back beyond the opposite edge (the side the move came from);
  retouch - a 1h candle's range back into the band (wick, the close may stay beyond).
F_N = events with that return within N h / confirmations with the full N h observed (younger ones are left out of the
denominator, not counted as held). One breakout of one zone posted in several briefings counts once (key: coin, zone
edges rounded to 0.1 ATR, direction, confirming candle).
Zone type: the timeframes of its pivots from the saved 'tfs' (new records) or parsed from its description '(1h/4h)'.
    PYTHONPATH=. .venv/bin/python scripts/acceptance_briefing.py [days=16]

```

### `scripts/diag_briefing.py`

#### 648. `<module>` — module — `scripts/diag_briefing.py:1-4`

```text
Diagnostic (eng-168u): every saved briefing scenario of the last 16 days replayed on Binance 1h - entered / TP1 /
stop, TP1 distance vs MFE / MAE in R, by scenario type and TP1 distance. Run from the bot directory:
    PYTHONPATH=. .venv/bin/python scripts/diag_briefing.py
A measurement of the rules as they ran, not a backtest of new ones.
```

### `scripts/trace_briefing.py`

#### 649. `<module>` — module — `scripts/trace_briefing.py:1-12`

```text

Trace of the entered briefing scenarios (eng-168v, audit #7): per scenario the real geometry after the reaction, the
excursions BEFORE the first stop vs over the whole 72h, the first outcome and its time, and the obstacles between the
entry and TP1 that existed at the post:
- ladder: the zones the briefing itself published (record['zones']) - by construction none should lie in between;
- raw:    the sr.zones clusters rebuilt from Binance candles closed BEFORE the post (the same call key_zones makes,
          before its span filter, merge and ladder) - a raw zone in between = an obstacle the ladder dropped or merged;
- pdhl:   the previous day / week high / low from the closed daily candles (the map's PDH / PDL / PWH / PWL; the other
          map levels - FVG / OB / POC - cannot be rebuilt offline and are not counted).
Writes data/trace_briefing.csv and prints a summary plus the N worst traces. A measurement of the rules as they ran.
    PYTHONPATH=. .venv/bin/python scripts/trace_briefing.py [days=16] [traces=5]

```

### `scripts/variants_briefing.py`

#### 650. `<module>` — module — `scripts/variants_briefing.py:1-15`

```text

Variants on the SAME entered briefing scenarios (eng-169 audit #10 check): every saved scenario of the last N days is
replayed with ONE rule changed at a time, scored with execution_model_v1 (Briefing.exec_detail: 50% at +1R, the rest at
break-even + costs to TP2, costs included) over the 72h horizon. A measurement of proposals on the scenarios the
briefings actually published - not a search for parameters.
  base      - as published: entry at the reaction candle's close, the scenario's stop and targets;
  tp_obst   - TP1 = the nearest obstacle beyond the entry by >= 1R: a raw sr.zones cluster rebuilt from candles before
              the post or PDH / PDL / PWH / PWL (audit: TP1 on the first real barrier), TP2 = the old TP1;
  stop_own  - stop at the scenario zone's far edge - 0.25 ATR(1h) (audit: no push_stop cascade, no big pad);
  retest    - after the reaction close, a limit at the zone's near edge (e1) within 6h, else no trade (audit: entry
              on the retest, not the reaction close);
  taker     - base, kept only when the reaction candle's taker-buy share agrees (>= 0.52 long, <= 0.48 short);
  react_4h  - the reaction looked for on complete 4h candles instead of 1h (the eng-168y policy for 4h zones).
    PYTHONPATH=. .venv/bin/python scripts/variants_briefing.py [days=16]

```

### `sectors.py`

#### 651. `<module>` — module — `sectors.py:1-5`

```text

Coin sectors from CoinGecko's public API (no key): a fixed list of broad categories; a coin listed in several gets
the first of them in CATEGORIES order, and a ticker shared by several tokens goes to the one with the biggest cap.
Cached for a day in models/sectors.json. Used by the per-strategy coin pools (`pools.py`) and the stats splits.

```

#### 652. `base_of` — function — `sectors.py:28`

```text
'1000PEPE/USDT:USDT' / '1000PEPEUSDT' -> 'PEPE' (unit multipliers dropped).
```

#### 653. `load` — function — `sectors.py:60`

```text
{base symbol: sector}; empty when CoinGecko is unreachable and there is no cache.
```

### `security.py`

#### 654. `<module>` — module — `security.py:1`

```text
Small fail-closed helpers for external URLs and local model artifacts.
```

#### 655. `safe_urlopen` — function — `security.py:13`

```text
Open only HTTPS resources with an explicit timeout.
```

#### 656. `safe_pickle_load` — function — `security.py:21`

```text
Load a model only from a regular, owner-only local file.
```

### `signal_book.py`

#### 657. `<module>` — module — `signal_book.py:1-34`

```text

Signal lifecycle and anomaly memory for the dashboard.

A directional setup belongs to a strategy (strategies/): the strategy turns it into a PLAN (its anchor - a leg, a
level or a range -, entry style, zone, invalidation, stop reference and targets by intent); this module runs the same
lifecycle for every plan:

    BIAS    the coin's history / level map is still loading (at most plan_wait_sec for 1h-dependent strategies), or
            the plan stopped existing later; a setup without an anchor never becomes a card (vetoed 'no_leg')
    WATCH   waiting for price to reach the plan's zone
    ZONE    price is in the zone: waiting for the structure-shift trigger on the plan's trigger timeframe
    ENTRY   entry / SL / TP set: at the confirmation (plan entry 'confirm') when R:R to TP1 allows it, else on the
            trigger in the zone
    TP1/TP2 targets reached, trade still managed;  final: TP3, SL, CLOSED (time / opposite setup), INVALID, MISSED,
            EXPIRED

Shared rules: INVALID beyond the plan's invalidation (fixed at the card's start when the extreme was known at the
confirmation); MISSED when TP1 (fixed beyond the furthest price reached since the anchor) is reached before an entry;
a continuation whose leg makes a new extreme goes back to waiting and is re-measured; a new card closes the open card
of the opposite direction when its structure timeframe is the same or higher; a card that finished blocks a new one
on the same anchor; every setup carries its market crowd (CONFIG.market) and context (trend, volatility) for the
journal / stats / ML - no limit on the number of cards.

Filters (each journaled with its reason instead of silently dropped, so stats.py can measure it):
- a perp-led continuation (spot disagrees) never becomes a card (journal.veto_reason);
- a strategy's context policy (a sweep against the coin's 1h trend: 'against_trend'), a disabled strategy;
- a spring's entry needs its "test": the pullback trades on lower volume than the spring candle;
- every entry carries its confirmations (strategies/confirm.py: taker flow, spot flow, OI, order flow at the
  extreme); a required one that is negative vetoes it ('no_oi', 'no_orderflow', ...: journaled as a vetoed entry,
  the card keeps waiting for the next trigger).

Statuses follow the futures price at each scan; the journal replays each entry on 1m candles with a manual fill.
Partial phases go to the watchlist; other Tier-0 anomalies are remembered for CONFIG.tier0.display_hold_sec.

```

#### 658. `ict_gated` — function — `signal_book.py:98-101`

```text

    ICT's sweep / continuation models trade inside the London / New York kill zones only (eng-58). The Silver Bullet
    shares the 'sweep' name but has its own windows (03-04, 10-11, 14-15 New York): eng-58 vetoed two of its three.
    
```

#### 659. `_frame_for` — function — `signal_book.py:130`

```text
Return a closed frame unless the owning strategy explicitly opts into the live candle.
```

#### 660. `htf_zone_at` — function — `signal_book.py:153-154`

```text
A zone of 4h or higher (order block / FVG / BPR / breaker of 4h, daily, weekly; daily swings; HTF range)
    contains the price.
```

#### 661. `_dur` — function — `signal_book.py:162`

```text
600 -> '10m', 7200 -> '2h' (reasons are parsed by the dashboard).
```

#### 662. `shadow_veto` — function — `signal_book.py:196-197`

```text
eng-101: a reason in strategies.shadow_vetoes does not block - it is added to sig['shadow_veto'] and None is
    returned ('no_*' covers the detectors' required confirmations, not the structural no_data / no_leg ...).
```

#### 663. `card_tp1` — function — `signal_book.py:212-215`

```text
eng-168: the TP1 the trade will actually take. A system with its own level target (exit['tp'] = ['level',
    price, ...], e.g. Silver Bullet's PDH / PDL) exits there (geometry.exit_target), while plan['targets'][0] is the
    nearest map pool from select_targets - checking tp1_passed / MISSED against that pool dropped 64 of 123 Silver
    Bullet setups whose draw was still ahead of the price.
```

#### 664. `plan_has_executable_exit` — function — `signal_book.py:223`

```text
A plan is tradable with either real targets or an explicitly named targetless exit manager.
```

#### 665. `crowd_rank` — function — `signal_book.py:235-236`

```text
eng-147 (the owner): the order in which one pass's entries take the crowd_max slots - fewer shadow vetoes, then
    the higher RVOL of the last 15 minutes (vs the 20 quarters before), then min(R:R to TP1, 2.5) (2.0 without a TP1).
```

#### 666. `version_no` — function — `signal_book.py:258-259`

```text
'eng-57' -> 57, 'eng-169e' -> 169 (a letter suffix marks a sub-release of the same number; 0 for anything else).
    eng-169e: int('169e') raised -> 0, so every card of eng-169e read as the oldest logic (the >= 137 / 141 rules off).
```

#### 667. `_exit_flags` — function — `signal_book.py:265-266`

```text
The exit-relevant plan fields of a trade saved without its plan (before eng-55), rebuilt from its signal and
    setup as the strategies set them at the entry.
```

#### 668. `TrackedSignal.r_now` — function — `signal_book.py:368`

```text
Current result in R (risk units) for an entered signal.
```

#### 669. `SignalBook.update` — function — `signal_book.py:457-463`

```text

        Feed one scan's signals. `frames.get(symbol, include_live=...)` returns the symbol's 15m futures frame with
        indicators (closed by default; live only for an opted-in strategy) and `candles_of(symbol)` its final 1m candles;
        `confirm_of(...)` reads an entry's confirmations
        (strategies.confirm). Returns (setups created, entries
        triggered this scan); vetoed entries are in the list too, with `.vetoed` set and no status change.
        
```

#### 670. `SignalBook._card_gate` — function — `signal_book.py:659-663`

```text

        Why a setup does not become a card: no anchor to build a plan on ('no_leg'), or a card on this anchor already
        finished ('same_leg': a setup keeps confirming on every candle, the idea was already played). A leg strategy
        without the coin's 1h history is decided by the first plan (1h / 4h legs need it).
        
```

#### 671. `SignalBook._plan_data_ready` — function — `signal_book.py:687-688`

```text
Can a missing plan be trusted: the book has run PLAN_GRACE_SEC and the coin has its 15m frame, its 1h / 4h /
        daily ATRs and final 1m candles (a plan built without them is None for want of data, not of a setup).
```

#### 672. `SignalBook._drop` — function — `signal_book.py:788`

```text
A card that turned out not to be one (no anchor / no room left): removed, shown in Forming as vetoed.
```

#### 673. `SignalBook._activate` — function — `signal_book.py:798-800`

```text
The card's first plan: fix its references (eng-169g: it no longer closes the opposite card - only its ENTRY
        does, _close_opposites; a plan alone closed open trades at market: 31 in 3 days, ~45 cards by the then
        journal-only OI BUILD).
```

#### 674. `SignalBook._close_opposites` — function — `signal_book.py:807-812`

```text

        eng-169g: an ENTRY (not a vetoed copy) closes the coin's opposite cards. A waiting card yields to an opposite
        entry of the same or a higher timeframe; an ENTERED trade only to one of a STRICTLY higher timeframe (the owner:
        "which entry is stronger" - a same-timeframe opposite signal is the same weight against a position already
        working, so it is journaled on the new card ('opposite_open'), the trade keeps its levels).
        
```

#### 675. `SignalBook._open_turtle_units` — function — `signal_book.py:865-869`

```text
Count units of real open Turtle positions only.

        ``units`` is also used by historical averaging/variant paths.  The portfolio cap is a Turtle
        contract, so waiting cards, finished cards and non-Turtle units must not consume it.
        
```

#### 676. `SignalBook._direction_units` — function — `signal_book.py:875`

```text
The open Turtle units already held in s's direction, excluding s itself.
```

#### 677. `SignalBook._partial_1r` — function — `signal_book.py:879-882`

```text
eng-105 / eng-155: partial_share of the position out once price traded +partial_r R (the demo's tp0, or a
        PARTIAL event -> executor.on_partial for trades opened without it); once per card, not for unit systems, not
        where the plan's TP1 is nearer than +partial_r R. eng-162: its own step, for the trailing plans too - the
        executor already placed tp0 for new SAR / % trail trades while the card never booked it (journal vs demo R).
```

#### 678. `SignalBook._trail` — function — `signal_book.py:896-906`

```text

        Stop management of an open trade, only ever toward the trade (a RESTOP event moves the demo's stop):
        - plan 'sar': Wilder's Parabolic SAR of the plan's bars (BB1 4h);
        - plan 'trail_pct': a % trail behind the best price;
        - the partial at +partial_r R (executor.partial_share of the position, eng-155): for EVERY plan, the trailing
          ones included, checked first (_partial_1r);
        - break-even + costs after +1R (strategies.be_after_1r, eng-155; a plan's own be_after_r wins) for the plans
          without their own trail (sar / trail_pct keep theirs);
        - plan 'trail_after_tp1' (half at TP1, then the EMA20 trail): off - _plan resets it while
          strategies.ema_trail_after_tp1 is False (eng-111); only band_exit plans keep it.
        
```

#### 679. `SignalBook._overlay_exit` — function — `signal_book.py:997-1001`

```text

        Early exits adopted by research_overlays.py (models/exit_overlays.json), checked at each final 1m candle's
        close: noprog_H - H hours in and the trade never traded +0.3R its way; struct - a 15m close at or below -0.5R;
        btc_K - altcoins: BTC moved K% against the trade over the last 15 minutes. Exit at the candle's close.
        
```

#### 680. `SignalBook._profile_manage` — function — `signal_book.py:1027-1029`

```text
An optimized profile's stop management on each final 1m candle (research_optimize.simulate): after +1R the
        stop to the entry (`be`) and / or an ATR chandelier `trail` x the 1h ATR behind the best price, only ever
        toward the trade; a RESTOP event moves the demo's stop.
```

#### 681. `SignalBook._funding_r` — function — `signal_book.py:1056`

```text
Funding in R of a whole position at `price` held over (t0, t1].
```

#### 682. `SignalBook._cost_r` — function — `signal_book.py:1069-1072`

```text
eng-58: the round trip's cost in R - fees, the slippage of the entry and of the exit (by the coin's
        liquidity, levels.slippage_bps) and the funding settlements held through - as the journal's replay nets it.
        audit 2026-10-18 D: `parts` = [(share, left at ms)] - each share pays funding only until it left (a third out
        at TP1 pays no later settlement); None = the whole position held to exit_ms.
```

#### 683. `SignalBook._exit_r` — function — `signal_book.py:1084-1088`

```text

        The card's realized R as it is traded: a third out at each target reached, the rest at the stop (SL) or at the
        last price (closed / expired). r_now marked the WHOLE position at the last price - a TP3 card read +2.62R where
        its thirds made +1.5R (VVV 2026-10-02), an SL after TP1 read -1.08R.
        
```

#### 684. `SignalBook._parts_held` — function — `signal_book.py:1129`

```text
The position's parts as _exit_r books them, each with the time it left (audit 2026-10-18 D).
```

#### 685. `SignalBook._advance` — function — `signal_book.py:1155`

```text
Move one signal along its lifecycle; returns the entry (possibly a vetoed copy) when a trigger fired.
```

#### 686. `SignalBook._new_attempt` — function — `signal_book.py:1351-1353`

```text
eng-168 (audit of htf_bias): the shadow tags of an entry attempt belong to THAT attempt. A card waits over
        many passes and its sig is replaced only while the setup re-appears, so a tag from an earlier attempt (a bias
        that has since changed) stayed and was journaled with the entry. The setup-time tags are the baseline.
```

#### 687. `SignalBook._invalid_since` — function — `signal_book.py:1460-1466`

```text

        Audit A01: the first final event beyond `invalid` since the last check (s.inv_ms; from the first whole minute
        after the card's creation): a 1m low / high through it (touch rule), or with `close_min` a close beyond it of
        a final `close_min` bar that closed after the card was created. Returns that price, None without one; moves
        s.inv_ms to the end of the last final minute seen. A re-planned (moving) invalidation is checked on the minutes
        since the last check only.
        
```

#### 688. `SignalBook._tp1_since` — function — `signal_book.py:1504-1507`

```text
Audit B03: the first final 1m high / low at TP1 since the last check (s.tp_ms; from the first whole minute after
        the card's creation) - a wick through TP1 between two scans ends the waiting card though the price is back.
        Only the minutes since the last check are read, with the plan of that moment (a moved TP1 is never applied to
        the older candles).
```

#### 689. `SignalBook._last_close` — function — `signal_book.py:1533`

```text
Close of the last FINAL candle of `minutes_tf` minutes (from the final 1m candles), None without data.
```

#### 690. `SignalBook._confirmation_entry` — function — `signal_book.py:1542-1545`

```text

        Entry at the immutable close of the setup's confirmation candle.  The current quote is only a safety check:
        it may invalidate a stale signal, but it must not redraw the levels or the journaled decision price.
        
```

#### 691. `SignalBook._overshoot` — function — `signal_book.py:1591-1597`

```text

        eng-147 measured how far a trigger close ran past the setup's level (the anchor's level for sweeps, else the
        zone's trade-side edge) in working-tf ATRs. eng-148 (audit: the 0.6 ATR threshold was chosen in sample): the
        ATR overshoot is journaled only; the residual R:R from the trigger price is low_rr's own check (entry_levels
        at the trigger close vs the method's min_rr), so nothing more blocks here.
        Journaled too: cost_r (the round-trip cost in R) and rr_trigger.
        
```

#### 692. `SignalBook._enter` — function — `signal_book.py:1620`

```text
Enter, or journal the entry that would have been taken with the veto reason (the card keeps waiting).
```

#### 693. `SignalBook._variant` — function — `signal_book.py:1818`

```text
eng-149: a shadow variant of the card journaled as a vetoed entry `name` (never traded), once per card.
```

#### 694. `SignalBook._retest_variants` — function — `signal_book.py:1830-1837`

```text

        eng-160 (the owner, trade geometry scenario B): the retest entry of a PUMP / DUMP START journaled beside the live
        confirmation entry as 'variant_retest' (never traded). Every such card with a plan is watched - entered, vetoed
        low_rr or expired alike (a variant read only on entered cards would be survivorship) - for 2h of 5m bars after
        the signal: price comes back into H_n +- 0.25 ATR(5m) (H_n = the edge of the 2h range the move broke, pd_hn),
        and a 5m bar closes back beyond H_n -> entry at that close with the plan's own stop / targets. A close beyond
        H_n -+ 0.25 ATR on the wrong side breaks the structure: no retest entry.
        
```

#### 695. `SignalBook._retest_variant` — function — `signal_book.py:1851`

```text
True when this card's retest is settled (journaled, broken, stale or out of time).
```

#### 696. `SignalBook._limit_variants` — function — `signal_book.py:1891-1896`

```text

        eng-149 (plan eng-148 stage 3.1, audit 13 / 34): once a sweep is armed (MSS + FVG), resting limits at the CE
        ('variant_ce_limit') and at the gap's near edge ('variant_fvg_edge'), filled on the touch at the limit price,
        the plan's own stop / targets - on the same armed cards as the live touch -> close entry, low_rr or not.
        stats.py reads the 50/50 split (edge + CE, one stop) from the pair.
        
```

#### 697. `SignalBook._pool2_on_invalid` — function — `signal_book.py:1920-1921`

```text
review eng-151: the second raid usually runs through the card's invalidation - the variant is read before
        the card ends INVALID, or only the touches that turned within the pad would be journaled (survivorship).
```

#### 698. `SignalBook._pool2_variant` — function — `signal_book.py:1932-1936`

```text

        eng-151 (external audit #2): when an untaken pool sits within zone_move_pool_atr beyond the sweep's extreme
        (plan['pool2']), a resting limit at that pool's liquidity, filled on the touch - the second raid - with the
        plan's stop rule from the pool and its targets, 'variant_pool2' (never traded), against the live entry.
        
```

#### 699. `SignalBook._st_stop_variant` — function — `signal_book.py:1953-1957`

```text

        eng-149 (plan eng-148 stage 3.6, audit 12): Wyckoff's entry on the secondary test with the stop beyond the
        TEST's extreme (+ 0.25 working ATR, a heuristic pad) instead of beyond the spring / climax - the same entry and
        targets, 'variant_st_stop', only where that stop is tighter than the live one.
        
```

#### 700. `SignalBook._shadow_entry` — function — `signal_book.py:1977-1983`

```text

        eng-59: the rule eng-58 replaced, journaled as a vetoed entry of the same card so the journal compares both on
        the same events (vetoes_table): 'weak_mss' = the old sweep trigger (a close beyond the high made after the
        raid, entry at the CE touch) while the new MSS has not armed the card; 'variant_shift' = the old market entry
        on the 5m structure shift beside the resting limit (continuation, an armed sweep). Inside the kill zone only,
        once per trigger.
        
```

#### 701. `SignalBook._flow_entry` — function — `signal_book.py:2011-2019`

```text

        The order-flow entry in the zone (2026-10-05, the owner: "we look for the best entry point in the zone"),
        journaled beside the method's own trigger on the same card (vetoed 'flow_entry', never traded) so the journal
        compares the two: once a minute while the card is in its zone, the confirmations since the zone was reached
        - an order-flow reading (absorption, stacked imbalance or a finished auction at the extreme), the taker
        delta since the zone's extreme turned the trade's way, and OI as the method's type expects (rising for
        breaks / continuations, falling for fades; 'n/a' where a method has no OI hypothesis). All three -> an
        entry at the price with the stop beyond the zone's extreme (the plan's own geometry), once per card.
        
```

#### 702. `SignalBook._reclaim_entry` — function — `signal_book.py:2049-2056`

```text

        eng-104, the reclaim entry of a liquidity sweep (the owner's comparison with a signal channel 2026-10-14: BTC /
        ETH sweeps of the day high found by the bot at 08:15 UTC were sold there at once, while our card waited for a
        lower-timeframe shift and expired with the kill zone): an entry at the price right after the sweep candle closed
        back inside, the stop beyond the sweep's extreme + the coin's measured pierce (the plan's own stop), the targets
        of the plan. Journaled beside the method's trigger as vetoed 'reclaim_entry' (never traded), once per card,
        only while the price is still within half the way from the swept level to the stop.
        
```

#### 703. `SignalBook._against_day` — function — `signal_book.py:2080-2084`

```text

        eng-58: one direction per coin a day (ICT trades the day's bias with every model; a long and a short of two
        strategies on one coin were one coin flip): the first entry of the UTC day sets it, an opposite entry is
        journaled 'against_day'. The Turtles (a multi-week system) are exempt.
        
```

#### 704. `SignalBook._entry_minute` — function — `signal_book.py:2096-2102`

```text

        Audit A02: the extremes of the entry minute AFTER the entry. (open, high, low) from the trades since the entry;
        the 1m candle's own when its range touched no stop / target / exit level (nothing to decide); None while the
        minute's trades are still arriving; False when the range touched a level and no complete trade record tells
        whether before or after the entry: 'ambiguous', not judged (no invented fill), the pessimistic stop R kept
        apart in r_low.
        
```

#### 705. `SignalBook._macro_guard` — function — `signal_book.py:2339-2341`

```text
eng-100: macro_guard_min before a high-impact US release (macro_calendar.upcoming) an intraday trade in profit
        gets its stop at break-even + costs, one flat or in loss is closed at market (True). Multi-day systems keep
        their exits.
```

#### 706. `SignalBook._market_up_veto` — function — `signal_book.py:2386`

```text
Return True only when the OI short must be blocked by a bullish regime.
```

#### 707. `SignalBook.crowded` — function — `signal_book.py:2397-2398`

```text
eng-51: crowd_max open trades in this direction across all strategies (Turtles' correlated-markets limit);
        `limit` = another count (eng-169f: the journal's crowd_tag with the cap itself off).
```

#### 708. `SignalBook.crowded_open` — function — `signal_book.py:2411`

```text
eng-168h: every open trade in this direction (the old crowd count) - journaled as a shadow tag only.
```

#### 709. `SignalBook._time_exit` — function — `signal_book.py:2416`

```text
Why the trade ends by time now (eng-47, Strategy.time_exit) and the time it fell due; (None, None) = it runs.
```

#### 710. `SignalBook.signals_view` — function — `signal_book.py:2459-2462`

```text

        Open signals by actionability - in a trade, in the zone, watching (closest to the zone first), direction
        only - followed by signals finished within finished_display_sec.
        
```

#### 711. `SignalBook.hot_symbols` — function — `signal_book.py:2484`

```text
Symbols that deserve order-book data, with a priority (0 = in a trade, 1 = in the zone, 2 = watching).
```

#### 712. `SignalBook.zone_symbols` — function — `signal_book.py:2494-2497`

```text

        Symbols waiting for an entry -> their 15m ATR (footprint bucket sizing). From the card's creation, not only
        once in the zone: a footprint started at the zone had seconds of data when the first trigger came.
        
```

#### 713. `SignalBook.state` — function — `signal_book.py:2504`

```text
Open cards and session counters (plans are recomputed from the frames after a restart).
```

### `signal_priority.py`

#### 714. `<module>` — module — `signal_priority.py:1`

```text
Deterministic portfolio-slot ordering and a short aggregation window.
```

### `smallcap.py`

#### 715. `<module>` — module — `smallcap.py:1-20`

```text

eng-158: live 1m watch of the small caps outside the universe for the start of pumps and dumps.

The universe holds ~70 data-complete coins; the biggest pumps / dumps happen in the coins outside it (no spot pair,
fresh listings, < 2 other venues). Until now those were read once an hour on 1h candles and journaled only
(Scanner.wide_watch_loop), so a -45% dump (KAT, WET 24.10) was seen an hour late and never traded.

Here every such perpetual (wide_min_volume, the wide watch's list) gets its Binance futures 1m kline stream on ONE
dynamic connection (no restart of the universe's streams when the list changes - eng-102). Per coin only a ring of
the last `smallcap_minutes` final minutes is kept (tuples, ~7 MB for 150 coins). On each final minute a cheap gate
(|15m move| >= pump_start_min_pct) runs first; only then the coin's 15m volatility and its OI change are fetched by
REST and PUMP START / DUMP START (strategies.pump) decide. A hit becomes an ordinary setup signal for the SignalBook:
the card, the journal and the demo trade follow the same rules as in the universe. The coin's minutes / price feed
the card through Scanner._minute_candles / _price_of while it is not in the universe.

Inputs that differ from the universe (no spot pair, no order books here):
- spot taker flow -> the FUTURES taker flow of the last 5 minutes (sig 'flow_src' = 'futures': journaled);
- rvol_1m -> the last minute's quote volume / (24h quote volume / 1440), the universe's own definition;
- the plan's ATR -> the 1h ATR(14) of the wide watch's 1h candles / 2 (a 15m ATR by the square-root rule).

```

#### 716. `_Sink` — class — `smallcap.py:34`

```text
BinanceStream's sink: only the 1m klines of the watched coins.
```

#### 717. `SmallCapWatch.restore` — async function — `smallcap.py:123-124`

```text
eng-161: attach the last known small-cap list at start-up (was: ~10 min later, after the wide watch's first
        hourly scan) - the rings are seeded by REST at once, the 1h candles load on a coin's first check.
```

#### 718. `SmallCapWatch.set_coins` — async function — `smallcap.py:137`

```text
wanted: (unified symbol, Binance id, 24h quote volume) of the perpetuals outside the universe.
```

#### 719. `SmallCapWatch._why_not` — function — `smallcap.py:291`

```text
eng-161: the first PUMP / DUMP START gate that failed (same order as strategies.pump.pump_start).
```

### `sqlsafe.py`

#### 720. `<module>` — module — `sqlsafe.py:1`

```text
Helpers for SQLite identifiers that cannot be supplied as parameters.
```

#### 721. `identifier` — function — `sqlsafe.py:9`

```text
Return a validated SQL identifier or fail closed.
```

### `sr.py`

#### 722. `<module>` — module — `sr.py:1-25`

```text

Support / resistance from where price actually turned (eng-75, the owner: "you don't understand what support and
resistance are and what forms them"; web-checked 2026-10-08: Fidelity, Investing.com, Capital.com, Dukascopy,
Wealthsimple, FTMO, Traders Agency).

What forms a level, by the sources:
- price reversed there: a swing high / low is where supply and demand changed hands (old highs resist, old lows
  support);
- memory: traders trapped at that price exit at breakeven when it returns, those who missed it buy / sell there -
  hence ROLE REVERSAL: a broken support resists from below, a broken resistance supports from above;
- strength: how many times price reacted there, how big the reaction was (size and duration), the volume on the
  touches, the timeframe (4h / daily / weekly outweigh 1h) and recency; touches alone are not enough (FTMO: a level
  tested too often may be weaker - orders rest behind it), the quality of the reaction counts.

So a zone here is a CLUSTER OF SWING PIVOTS of the 1h / 4h / daily candles, not a catalogue of constructs:
- pivots: fractal swings (the candle's high above `width` neighbours on both sides; lows mirrored), each with its
  reaction (the largest move away in the next `react_bars` candles, in that timeframe's ATR) and its volume
  (the candle's volume / the median of the 20 before);
- pivots within `tol` of each other (by price) form one zone, its band = the pivots' wicks (at most `max_width`);
- touches = pivots + the later 1h candles that wicked into the band and closed back out on the side they came
  from (rejections); flip = the cluster holds both swing highs and swing lows (the level changed role);
- strength = sum over the pivots of tf weight x (1 + reaction, capped) x volume factor x recency decay, plus half a
  point per rejection. The weights are hypotheses - research_sr.py measures whether these zones hold price better
  than placebo prices before anything trades on them.

```

#### 723. `pivots` — function — `sr.py:48`

```text
Confirmed fractal swings of [ts, o, h, l, c, v] candles (a pivot needs `width` closed candles after it).
```

#### 724. `zones` — function — `sr.py:77-80`

```text

    S/R zones from the pivots of the given timeframes ({'1h': [...], '4h': [...], '1d': [...]}), as of now_ms.
    tol: the price distance within which pivots are one place; max_width: the band's widest.
    
```

#### 725. `reaction_stats` — function — `sr.py:139-143`

```text
eng-168n: how price met the band [lo, hi] on the closed 1h candles AFTER its first pivot, the pivots' own bars
    (within one candle of their timeframe) left out. An approach starts on a candle that came from outside (the
    previous close beyond one edge) and traded into the band; it ends on the first close outside: back on the
    approach side = a rejection, beyond the far edge = a break (closes inside keep it open). max_pierce_atr: the deepest
    wick past the near edge on a rejection (max_pierce_on_rejection), in ATR14(1h).
```

### `stats.py`

#### 726. `<module>` — module — `stats.py:2-19`

```text

Statistics over the signal journal (signals.db): what the price did after each kind of signal.

    python stats.py                 # rows of the current signal logic (CONFIG.journal.logic_version)
    python stats.py --all-versions  # every row, including older logic
    python stats.py --days 7        # last 7 days
    python stats.py --last 30       # also list the 30 most recent signals with their outcomes

Returns are measured from the futures last price at the signal, in the signal's direction: for BEAR / IMPULSE
DOWN a falling price counts as a gain. "Net" figures subtract the round-trip fee (CONFIG.journal.fee_round_trip).

Market baseline: the MEAN return of the WHOLE universe over the same window (not the median: coins beat the median
by ~0.11% per 4h on average - right-skewed returns - which made every long look good and every short bad), from the price snapshots the
scanner stores every 15 minutes (older databases without snapshots fall back to the mean of the coins logged in
the same hour). "Edge" is a setup's return in its direction minus that baseline, so a falling market doesn't make
every short look good. [lo..hi] = 90% bootstrap interval of the mean: an interval that straddles 0 means the
sample cannot tell the setup from noise yet.

```

#### 727. `rotation_group` — function — `stats.py:48`

```text
Stable telemetry bucket for the structural rotation report.
```

#### 728. `cluster_of` — function — `stats.py:74-78`

```text

    Signals of one direction whose 4h outcome windows overlap ride the same market move (15 breakouts at one close,
    the next closes of the same move): one 4h block of one direction is one cluster, and the bootstrap resamples
    clusters (block bootstrap) - intervals of overlapping labels, not of independent rows.
    
```

#### 729. `bootstrap_ci` — function — `stats.py:84`

```text
90% percentile bootstrap interval of `stat`; with `clusters` (one key per value) whole clusters are resampled.
```

#### 730. `_block_means` — function — `stats.py:101-102`

```text
BOOTSTRAP resampled means of whole blocks, vectorized: a draw's mean = the drawn blocks' sum / their count
    (the Python loop took 24s of a 38s report over 90 days).
```

#### 731. `UniverseBaseline` — class — `stats.py:126`

```text
Mean return of every universe coin between the snapshots nearest t and t + horizon (see ret).
```

#### 732. `UniverseBaseline._at` — function — `stats.py:148`

```text
The snapshot nearest to ts (either side), within MAX_GAP_MS.
```

#### 733. `BetaEstimator` — class — `stats.py:168-173`

```text

    Each coin's beta to the universe mean from the snapshots of the 7 days BEFORE a signal (hourly returns, OLS,
    Blume-adjusted toward 1: 0.67 x beta + 0.33). Signals are picked on volatile coins (impulses, cascades), and a coin
    with beta 2 in a falling market "beats" the mean on a short without any skill: Edge beta = the return in the
    signal's direction minus beta x the mean. None (plain Edge) with fewer than 48 hourly points.
    
```

#### 734. `BetaEstimator.symbol_id` — function — `stats.py:205`

```text
'1000PEPE/USDT:USDT' -> '1000PEPEUSDT' (the snapshots store Binance ids).
```

#### 735. `bootstrap_p` — function — `stats.py:230`

```text
Two-sided block-bootstrap p-value of "the mean is 0" (whole clusters resampled, like bootstrap_ci).
```

#### 736. `bh_q` — function — `stats.py:243-244`

```text
Benjamini-Hochberg q-values of the p-values given (None stays None): the false discovery rate at which each
    result would be called significant when all of them are looked at together.
```

#### 737. `market_baseline` — function — `stats.py:257`

```text
Fallback: per horizon, the mean raw return of all rows logged in the same hour.
```

#### 738. `excess_pairs` — function — `stats.py:288`

```text
Excess returns and their clusters (cluster_of); beta: the baseline scaled by the coin's beta (BetaEstimator).
```

#### 739. `_is_benchmark_variant` — function — `stats.py:364`

```text
True for an explicit benchmark row or a legacy row identified by its reason.
```

#### 740. `net_r` — function — `stats.py:372`

```text
R result minus the round-trip fee expressed in R (fee x entry / risk).
```

#### 741. `levels_table` — function — `stats.py:384`

```text
Replay of every entry (ENTRY rows) per setup, filled like a human (next minute + slippage), fees included.
```

#### 742. `_family` — function — `stats.py:446`

```text
Strategy of a directional row ('ENTRY <setup>' rows too); None for anomaly labels without one.
```

#### 743. `features_table` — function — `stats.py:573`

```text
Edge 4h of directional rows split by each recorded feature: does the filter / context add anything?
```

#### 744. `source_kind` — function — `stats.py:616`

```text
The strongest source of a level label ('EQH×2 · PDH · fib 0.5' -> 'equal highs/lows').
```

#### 745. `sources_table` — function — `stats.py:627`

```text
How often TP1 was reached, per the source of TP1 (entry rows with a replay): which level kinds hold up?
```

#### 746. `reversal_test_table` — function — `stats.py:655-659`

```text

    Mahadzva's test (SSRN 2026, G10 FX: a swept level predicted CONTINUATION in 65 of 66 folds) on our journal: every
    reversal setup (passed or vetoed) with the move afterwards in the signal's direction. A negative mean = price
    continued the swept move: the reversal reading is wrong and the opposite side would have paid.
    
```

#### 747. `vetoes_table` — function — `stats.py:684-688`

```text

    Every filter judged by what it rejected: entries grouped by veto reason (passed = taken) with their replay - a
    filter earns its place only if the trades it vetoes do WORSE than the ones it lets through (R:R 2, the
    confirmation minimum, off-session, macro events ...). Per strategy too, where a strategy has both.
    
```

#### 748. `slices_table` — function — `stats.py:715-721`

```text

    eng-148 (stage 0): the replayed entries (net R @TP1, passed and vetoed alike) split by the journal's new fields and
    the audit's splits. Each row is weighted 1 / c_t (c_t = entries of the same 15m window and direction: one BTC
    move is one observation, not twenty), the p-value is the cluster bootstrap, q the Benjamini-Hochberg FDR over
    every split shown. Read-only diagnostics: a split decides nothing without the pre-registered pass rule
    (>= 100 clusters, p < 0.05, E[R] > 0 after costs, both halves).
    
```

#### 749. `_wmean` — function — `stats.py:785`

```text
The 1/c_t-weighted mean of (value, cluster) pairs, the number of clusters and the cluster-bootstrap p.
```

#### 750. `variants_table` — function — `stats.py:797-804`

```text

    eng-149 (plan eng-148 stage 3): each shadow variant against the card's OWN entry on the same cards (pairs), R
    before costs to TP1 / the 8h window, weighted 1/c_t (15m x direction); p = cluster bootstrap of the paired
    difference variant - own. The card's own entry = its live row or its own veto (not another shadow entry:
    flow_entry / reclaim_entry / weak_mss / variant_shift). FVG split 50/50 = half at the edge + half at the CE
    (0 when the CE was not reached) vs the CE limit alone, both on the cards whose edge was touched. Diagnostics only:
    the pre-registered pass rule decides (>= 100 clusters, p < 0.05, E[R] > 0 after costs, both halves).
    
```

#### 751. `funnel_table` — function — `stats.py:859-862`

```text

    eng-149 (plan eng-148 stage 0.3): where each strategy's cards fall out - cards by their finish (EXPIRED / MISSED /
    INVALID ... and the entered ones), entries passed vs vetoed and the top veto reasons (shadow variants left out).
    
```

#### 752. `card_results_table` — function — `stats.py:896-897`

```text
Entered cards by their OWN exit (card_r: the lifecycle's trailing channel / pyramided units / TTL close): the only
    result of the Turtles or Connors, whose trades outlive the 8h replay.
```

#### 753. `_moments` — function — `stats.py:943`

```text
Mean, sd, skewness, kurtosis (not excess) of xs.
```

#### 754. `psr` — function — `stats.py:955`

```text
Probabilistic Sharpe ratio (Bailey & Lopez de Prado 2012): P(true SR > sr0) given n observations.
```

#### 755. `min_trl` — function — `stats.py:963`

```text
Minimum track record length: observations for the observed SR to beat sr0 at `conf` (only if sr > sr0).
```

#### 756. `expected_max_sr` — function — `stats.py:971-972`

```text
The SR the best of `trials` independent zero-edge trials reaches by luck (Bailey & Lopez de Prado's deflated
    Sharpe threshold; the variance of an SR estimate under the null ~ 1 / n).
```

#### 757. `hl_haircut` — function — `stats.py:981-987`

```text

    Harvey & Liu (2015, "Backtesting", JPM): the Sharpe haircut for multiple testing - the t-stat of the per-cluster
    Sharpe (t = SR x sqrt(n)), its two-sided p-value Bonferroni-adjusted for `trials` (p x M, their most conservative
    rule), translated back to a Sharpe; haircut = 1 - SR_adj / SR (100% = nothing left once the trials are counted).
    Bonferroni is the strictest of their three (Bonferroni / Holm / BHY; they advocate BHY, which needs every trial's
    p-value - we have only the live cells'): an UPPER bound of the haircut.
    
```

#### 758. `pbo_cscv` — function — `stats.py:1000-1006`

```text

    Bailey, Borwein, Lopez de Prado & Zhu (2017): the probability of backtest overfitting by combinatorially symmetric
    cross-validation. `matrix` = T periods x N configurations (here: days x strategies, the day's summed R). The T rows
    are cut into `blocks` contiguous parts; for every half / half split the in-sample best configuration's
    out-of-sample relative rank w gives logit ln(w / (1 - w)); PBO = the share of splits with logit <= 0 (the IS winner
    at or below the OOS median). ~0.5 = choosing the best strategy is a coin flip.
    
```

#### 759. `robustness_table` — function — `stats.py:1028-1034`

```text

    Is a strategy's result a few lucky trades? (the crypto-backtest-audit checks, chrisamz/crypto-skills): total card R
    without the best trade / the best 5, without the best coin / the best 5 coins, the best trade's share of the total;
    the mean R of the first and second half by entry time; the first card per coin only; the extra round-trip cost
    (bps of price) that brings the total to 0 = sum R / sum(1 / risk in bps). Below the table: PBO of picking the best
    strategy (days x strategies, CSCV).
    
```

#### 760. `version_no` — function — `stats.py:1087-1088`

```text
'eng-57' -> 57, 'eng-169e' -> 169 (a letter suffix marks a sub-release of the same number; 0 for anything else).
    eng-169e: int('169e') raised -> 0, so every card of eng-169e read as the oldest logic (the >= 137 / 141 rules off).
```

#### 761. `card_r_net` — function — `stats.py:1094-1095`

```text
A card's R net of costs: rows from eng-58 on are net already (SignalBook._exit_r); older ones were gross - the
    round trip's fees and slippage (by the coin's 24h volume) are taken off here (funding / gaps not known for them).
```

#### 762. `effective_trials` — function — `stats.py:1108-1114`

```text

    eng-59 (plan 3.2): the effective number of independent trials behind the DSR - Lopez de Prado's ONC idea: the
    trials are the (logic version x strategy) cells; their mean-R series per 4h block are correlated (one strategy across
    versions is nearly the same bet), so they are clustered on the correlation distance sqrt((1 - rho) / 2) by k-means
    for k = 2 .. n - 1 and the k with the best silhouette t-stat (mean / std of the samples' silhouettes) is the
    effective N. Cells with < 10 blocks of results stay single trials. Returns (effective N, raw N).
    
```

#### 763. `verdict_table` — function — `stats.py:1158-1165`

```text

    eng-55: the two-level verdict per strategy (the owner's decision after the audit, written before results):
    SUSPEND (no demo, still journaled) at >= 30 independent 4h clusters when the 90% cluster interval's LOWER bound is
    below -0.05R; DEPRECATE (delete the code) only at >= 200 clusters (MinTRL of a +0.1R edge with skew 1.8 / kurtosis
    7.8) with the UPPER bound below 0. PSR = P(true mean R > 0) per cluster mean (skew / kurtosis aware); DSR = the
    same against the SR the best of N trials reaches by luck, N = the effective number of trials (eng-59:
    `effective_trials`, ONC-style clustering of the version x strategy cells; was the raw cell count, an upper bound).
    
```

#### 764. `demo_gap_table` — function — `stats.py:1214-1218`

```text

    eng-55 (audit 3.8 / 3.9): where the demo's R differs from the journal's - the entry slip (BingX fill vs the plan's
    entry, carried by the basis), the stop slip on SL exits (exit vs the stop: the mark-price trigger's delay shows
    here) and the share of skipped trades by reason.
    
```

#### 765. `demo_table` — function — `stats.py:1261-1266`

```text

    The BingX demo fills next to the same card's own result (eng-59, research/demo_gap.md: the journal's replay
    trades thirds to fixed targets over 8h while the card and the demo exit by the method - time stop, session, band,
    SMA5 - so `journal_r` was the wrong partner: half of the -0.32R gap was that). The card is the first finished card
    of the coin and direction after the demo's entry (`card_r`, netted by card_r_net).
    
```

#### 766. `cards_table` — function — `stats.py:1321`

```text
Finished cards by status: why they ended and what price did afterwards in the card's direction.
```

### `storage.py`

#### 767. `<module>` — module — `storage.py:1`

```text
Atomic file replacement with durable writes and Windows sharing retries.
```

#### 768. `atomic_write` — function — `storage.py:12-16`

```text
Flush a unique sibling tempfile, replace the target, then sync its POSIX directory.

    Concurrent writers publish complete files; the last successful replacement wins.
    A directory-sync failure is reported even though replacement may already have succeeded.
    
```

#### 769. `append_jsonl` — function — `storage.py:51-58`

```text
Append complete JSONL records with one flush/fsync per batch.

    Runtime JSONL files are sometimes inspected or generated by a root-owned
    maintenance job.  The service user owns the data directory, so it can
    replace such a file but cannot open it for append.  In that case publish
    one atomic copy containing the old records and this batch; the next write
    is then owned by the service user again.
    
```

### `strategies/__init__.py`

#### 770. `<module>` — module — `strategies/__init__.py:1-33`

```text

Strategies: each class of market event has its own anchor, entry, stop and target intent (see the modules). The
registry as it stands (eng-145; one methodology = one strategy name, several playbooks may share it):

    strategy        setups                                   module               entry / exit (summary)
    continuation    IMPULSE UP / DOWN (Tier-0)               leg.py               ICT OTE 0.62-0.79, touch -> close;
                                                                                  targets start + k x leg
    sweep           SWEEP LOW / HIGH                         level.py             raid of an HTF pool, 5m FVG CE
    silver_bullet   SILVER BULLET LONG / SHORT               silver_bullet.py     NY windows, FVG CE, TP1 PDH / PDL
    wyckoff         SPRING / UTAD                            wyckoff_range.py     1h range spring / upthrust + test
    cascade         FLUSH / SQUEEZE REVERSAL                 cascade.py           the climax's secondary test
    breakout        BREAKOUT UP / DOWN                       breakout.py          the Turtles (touch, 2N, channel exit)
                    BB1 UP / DOWN                            maniac_strategies    Bollinger method I (squeeze)
    supply_demand   SD DEMAND / SUPPLY                       maniac_strategies    Seiden 4h zones, 1h touch, R:R 3
    value_area      VA80 LONG / SHORT                        classic_strategies   Dalton's 80% rule by session
    auction         AUCTION LONG / SHORT                     maniac_strategies    the failed auction (eng-127)
    trendline_break TL EM UP / DOWN                          maniac_strategies    Edwards & Magee break/retest
    trendline_touch TL TOUCH UP / DOWN                       maniac_strategies    Edwards & Magee third-touch reaction
    bollinger_wm    BB W-BOTTOM / M-TOP                     maniac_strategies    Bollinger/Merrill W/M
    bollinger_method3 BB3 BUY / SELL                        maniac_strategies    Bollinger Method III alert/confirmation
    bollinger_method1 BB1 UP / DOWN                         maniac_strategies    Bollinger Method I squeeze breakout
    orb             ORB UP / DOWN                            classic_strategies   Crabel 5-min range +- Stretch, touch;
                                                                                  out on 15m Parabolic SAR (eng-145)
    connors         RSI2 / RSI2X LONG / SHORT                classic_strategies   daily RSI(2), out at the SMA5
    pump_start / dump_start / pump_top / dump_bounce         pump.py              separate pump playbooks
    cup_handle      CUP HANDLE                               cup_handle.py        O'Neil, 1h / 4h
    po3             PO3 LONG / SHORT                         po3.py               ICT power of three, Asian range
    oi_build        OI BUILD LONG / SHORT                    oi_build.py          demo-eligible; outcomes remain journaled

Registered setups remain queryable in the journal.  ``CONFIG.strategies.disabled_setups`` archives measured dead
branches before card creation; ``CONFIG.executor.demo_off_setups`` is the separate execution gate. Detection:
Tier-0 (impulse), structure.build_context (15m closes, worker process), loopside.py (1m / daily candles on the loop).

```

#### 771. `entry_levels_for` — function — `strategies/__init__.py:72`

```text
Dispatch level decisions through the owning playbook contract.
```

#### 772. `unknown_names` — function — `strategies/__init__.py:88-89`

```text
audit-80: strategy names in the mode tables (regime / bias / confirm) that no registered strategy carries - a
    deleted strategy's leftover (the oi_signal outage). deploy/precheck.sh prints them; cascade is a registered playbook.
```

### `strategies/base.py`

#### 773. `<module>` — module — `strategies/base.py:1-22`

```text

The strategy interface. A strategy turns a setup (a detected event or a scored phase) into a PLAN, a dict:

    strategy, direction, anchor {type 'leg' | 'level' | 'range', tf, text, ...}
    tf, trigger_minutes          structure timeframe and the entry trigger's (3-6x finer)
    atr, recent_atr, leg_atr     15m ATR14, the last hour's 15m ATR (stop floor), the anchor's own ATR (stop buffer)
    entry                        'confirm' (enter at the confirmation, else wait in the zone) | 'pullback'
    zone_lo, zone_hi, zone_src   where the trigger is looked for once price is there
    invalid                      price beyond which the idea is wrong (None: none before the entry)
    fix_invalid                  the invalid price is fixed when the card starts (an extreme known at the confirmation)
    reset                        continuation: price beyond it = the leg extended -> back to waiting, re-measured
    missable                     MISSED when TP1 is reached before an entry
    stop_ref / stop_mid          the stop goes beyond stop_ref (and the trigger's swing) or sits at stop_mid
    targets, target_src          fixed at the card's start beyond `reached` (retarget: re-measured from the entry)
    intent, fillers, fill_label  target intent and the anchor's own fillers (fib / measured moves)
    zones                        merged level map (stop pools, targets)
    key                          the anchor's identity: a finished card blocks a new one on the same anchor
    impulse                      the leg (leg anchors) for the retracement read of the zone

Lifecycle and journal transport are shared; trade decisions belong to each
playbook contract and are dispatched by the owning Strategy instance.

```

#### 774. `CardLevels` — class — `strategies/base.py:34`

```text
The executable level payload shared by lifecycle, executor and journal.
```

#### 775. `geometry_error` — function — `strategies/base.py:62-69`

```text
Return a stable error code for executable stop/target geometry.

    ``entry`` is the planned entry.  When ``entry_fill`` is supplied, the same
    stop and TP1 are checked against the exchange fill as well.  Keeping the
    code here makes the strategy, card and executor paths use one strict
    contract; callers can store the code as ``geometry_error`` instead of
    parsing a free form log message.
    
```

#### 776. `validate_card_levels` — function — `strategies/base.py:118`

```text
Fail-closed validation for executable stop/target geometry.
```

#### 777. `finalize_card_levels` — function — `strategies/base.py:123-128`

```text
Run every playbook contract through the shared risk/geometry evaluator.

    Playbooks are allowed to choose their structural reference and target intent, but they are not allowed to
    choose a private definition of risk.  The lazy import keeps the strategy module graph acyclic while making
    ``entry_levels_for`` the single decision point for all contracts.
    
```

#### 778. `PlanInput` — class — `strategies/base.py:194`

```text
Everything a plan is computed from.
```

#### 779. `Strategy.contract_id` — function — `strategies/base.py:260`

```text
Stable playbook identifier used to keep directions and variants separate.
```

#### 780. `Strategy.entry_levels` — function — `strategies/base.py:264-269`

```text
Return this playbook's executable trade contract.

        Every registered playbook must implement this method.  There is no
        An incomplete migration fails closed and is journaled as an
        unexecutable plan.
        
```

#### 781. `Strategy.session_end` — function — `strategies/base.py:273`

```text
Epoch seconds the method's session ends for a trade entered at entered_at ('session' methods).
```

#### 782. `Strategy.gate_key` — function — `strategies/base.py:280`

```text
The anchor's identity before a card exists (None: no anchor -> not a card, vetoed 'no_leg').
```

#### 783. `Strategy.context_veto` — function — `strategies/base.py:288`

```text
Why the market context forbids this setup (journaled as the veto), None = allowed.
```

#### 784. `base_plan` — function — `strategies/base.py:305`

```text
The fields every plan has; strategies add / override the rest.
```

### `strategies/bias.py`

#### 785. `<module>` — module — `strategies/bias.py:1-24`

```text

Top-down bias (HTF -> MTF -> LTF), the common ground of the sources (2026-10-05, the owner's rule "the higher
timeframe always comes first"; web-checked):
- Elder's triple screen: the long-term tide decides the side, the intermediate wave is a pullback AGAINST it (buy
  declines in an up tide), the short-term ripple times the entry; timeframes x5 apart.
- ICT top-down: monthly / weekly / daily / 4h give one bias - bullish = longs only, bearish = shorts only, neutral = no
  trade; an LTF setup against the HTF bias "is a trap, not a trade".
- Weinstein / Shannon: the higher timeframe's stage (base, markup, top, markdown) and its moving averages - longs in
  markup only.
- Time-series momentum (Moskowitz, Ooi & Pedersen 2012; crypto practice blends 1 / 3 / 12 months): the academic part.
- Ranges: mean reversion only inside a higher-timeframe range, from its edges, out at its middle.

State of one coin from its own candles (the last CLOSED ones):
- tsm: the sign mean of the 30 / 90 / 365-day returns (-1 .. +1), the momentum blend;
- w1: the weekly close vs the EMA20 of the weekly closes (+1 / -1);
- d1 / h4: +1 when the close is above the EMA50 and the EMA50 rose over 5 days / 6 candles, -1 mirrored, 0 else;
- adx4: ADX(14) of the 4h candles.
Bias:
- 'bull': tsm > 0 and the tide up - the daily trend for intraday methods (the 4h is their wave: a pullback against
  the tide is Elder's entry, not a veto), the weekly for daily methods (Connors, cup: the daily is their wave);
- 'bear': mirrored;
- 'range': d1 = 0 and adx4 < 25 (no daily trend, a non-trending 4h);
- 'conflict': anything else (the timeframes disagree: no trade - ICT's neutral).

```

#### 786. `state` — function — `strategies/bias.py:57-58`

```text
The coin's higher-timeframe state from closed daily / 4h / weekly candles ([ts, o, h, l, c, ...], oldest
    first); None without enough daily history.
```

#### 787. `bias_of` — function — `strategies/bias.py:79-81`

```text
The tide (Elder): the momentum blend and the daily trend for intraday methods - the 4h is their WAVE and may
    run against the tide (a pullback is the entry, not a veto); for daily methods the momentum blend and the week, the
    daily being their wave.
```

#### 788. `gate` — function — `strategies/bias.py:95-97`

```text
The veto reason of an entry against the top-down bias, None when allowed. audit C08: an unknown bias is
    'no_bias' (journaled - in shadow under 'no_*' while the bias's role in each source is unsettled), not a silent
    pass recorded as if the bias agreed.
```

#### 789. `range_mid` — function — `strategies/bias.py:122`

```text
The middle of the 20-day range (a range trade's objective: out at the middle).
```

#### 790. `closed` — function — `strategies/bias.py:134`

```text
The candles closed by now (the last one may be the forming one).
```

### `strategies/breakout.py`

#### 791. `<module>` — module — `strategies/breakout.py:1-8`

```text

Breakout strategies. The live card is the Turtles' channel breakout (BreakoutStrategy below; the events come from
strategies/turtle.py, eng-31): entry on the touch of the 20-day (System 1) / 55-day (System 2) channel, stop 2N, no
target, out on the opposite 10-day / 20-day channel.

breakout_at_close (the older 15m range breakout with volume, flow and acceptance) is kept only for pretrain.py's
archive events; it does not open cards.

```

#### 792. `breakout_at_close` — function — `strategies/breakout.py:19`

```text
The previous candle broke out of the range on volume and flow, the one that just closed held beyond it.
```

#### 793. `BreakoutStrategy` — class — `strategies/breakout.py:71-75`

```text

    The Turtles' breakout (strategies/turtle.py, eng-31): entered at once on the touch of the 20-day (System 1) / 55-day
    (System 2) channel, stop 2N, no target - the trade ends on the 10-day / 20-day opposite channel (SignalBook trails
    it, `trail_days`). No volume, flow, OI, spot or confirmation filter: the Turtles used none.
    
```

#### 794. `BreakoutStrategy.entry_levels` — function — `strategies/breakout.py:83-87`

```text
Turtle contract: 2N protective stop and channel exit, no profit targets.

        This deliberately does not call the shared geometry gates: the Turtle
        system sizes risk from its own N and exits on the opposite channel.
        
```

### `strategies/cascade.py`

#### 795. `<module>` — module — `strategies/cascade.py:1-19`

```text

Liquidation exhaustion (FLUSH REVERSAL / SQUEEZE REVERSAL) - eng-127: SHADOW only ('cascade_shadow'): "buy after a
cascade" is trader folklore (no tested rules); the adjacent evidence is intraday reversal after large price jumps
(Wen, Bouri, Xu, Zhao 2022) and overreaction after negative Bitcoin shocks. A cascade of forced liquidations overshoots mechanically
and price snaps back once the forced flow stops; the entry needs the extreme move AND a sign the flush is over.

Wyckoff (Pruden, Weis): a liquidation cascade is a selling / buying climax; the climax itself is not bought - the
trade comes on the SECONDARY TEST, a return toward the climax's extreme on lower volume (eng-30: the entry trigger
needs the pullback's average minute <= spring_test_volume_ratio x the climax's, like a spring's test).

eng-58: a selling climax ENDS a decline (Wyckoff's phase A): the close 24 1h candles before the cascade must be
beyond its start in the cascade's direction (above for a flush of longs), else 'no_prior_trend'; the structure is
15m (our timeframe rule), the entry 5m.

Anchor: a real leg - the cascade, from the extreme of the exhaustion_pre_minutes before it to its extreme. The extreme
keeps following price until the entry (nobody knows where a running cascade ends), so there is no fixed invalidation;
the card waits near the extreme for a 5m structure shift against the cascade. Targets: the mean (VWAP anchored at the
cascade's start, the map's VWAP / POC / nodes), the cascade's 0.382 / 0.5 / 0.618 retracements fill empty slots.

```

#### 796. `_cascade_targets` — function — `strategies/cascade.py:33`

```text
Cascade-specific retracement targets followed by mean/map levels.
```

#### 797. `_cascade_cap_for_rr` — function — `strategies/cascade.py:51`

```text
Cascade zone cap for its own 1R first-retracement rule.
```

#### 798. `cascade_leg` — function — `strategies/cascade.py:62`

```text
The cascade as a leg; its end follows new extremes of the final 1m candles.
```

#### 799. `CascadeTracker` — class — `strategies/cascade.py:79`

```text
Loop-side detector state: a running cascade per coin, fired once its leg is big enough.
```

#### 800. `ExhaustionStrategy.entry_levels` — function — `strategies/cascade.py:150`

```text
Cascade contract: climax extreme stop and retracement/mean targets.
```

### `strategies/classic.py`

#### 801. `<module>` — module — `strategies/classic.py:1-22`

```text

Classic published methods added as their authors define them (eng-29), on the session instruments only
(CONFIG.strategies.orb_bases: the majors, gold, silver, oil):

- value_area  Dalton's 80% rule by SESSION (eng-95; Dalton "Mind Over Markets"): the session (Asia / London / New York,
              weekdays) opens outside the previous same session's TPO value area (70% of time at price, eng-58),
              closes two consecutive 30-minute periods back inside it -> entry at the second period's close, target
              the far edge, out at the session's close (session_va_event, VA80). Beside it the failed auction
              (eng-127, failed_auction_event, AUCTION LONG / SHORT). Both run in the maps worker at 15m closes.
- orb         Toby Crabel's opening range breakout ("Playing the Opening Range Breakout", Stocks & Commodities): the
              range of a session's first 5 minutes, stop orders the Stretch (10-day SMA of min(High - Open,
              Open - Low)) beyond its high / low; the first level traded through is the entry (ON THE TOUCH, a stop
              order), the other level the stop; out at the session's close (eng-146; eng-145's 15m
              Parabolic SAR exit reverted). Checked
              loop-side on every final minute (session_orb via strategies.loopside.LoopDetectors).
- connors     Larry Connors' RSI(2) on DAILY candles, with the trend (close above / below the 200-day SMA): RSI2X = his
              original rule (a close with RSI(2) < 5, buy on the close; the mirrored short is shadow), RSI2 = the
              cross-back (eng-84: RSI(2) comes back out of the extreme, the close still beyond the SMA5). Out on the
              first daily close beyond the current SMA5. He uses no stop: the R unit is 1 daily ATR, position at 1x,
              and the executor keeps a catastrophe stop 3 R units away (eng-144, our deviation). Checked loop-side
              after each daily close (strategies.loopside.LoopDetectors._connors_daily).

```

#### 802. `value_area` — function — `strategies/classic.py:38-41`

```text
(VAL, POC, VAH) of the candles' volume spread evenly over each candle's range, else None. tpo: Market Profile's
    TPO value area (Dalton - eng-58): the candles are merged into 30-minute brackets and every price row a bracket
    visited gets ONE mark (audit C03: a wide candle's single unit was spread thinly over its rows, so a few narrow
    bars at one price made a 70% 'profile' there).
```

#### 803. `_complete_quarters` — function — `strategies/classic.py:116-120`

```text
Exact session-relative 15m grid, including sessions opening off the UTC quarter.

    The old ``start % 15m`` guard silently disabled the COMEX 08:20 ET XAU/XAG session.  Callers use
    ``_session_quarters`` to align the available closed 15m bars to the session origin before this strict check.
    
```

#### 804. `_session_quarters` — function — `strategies/classic.py:125-130`

```text
Aggregate closed 15m rows into a session-relative grid.

    Binance's standard 15m candles are UTC aligned, while COMEX opens at :20.  A bar's midpoint identifies the
    session-relative bucket; every bucket must have a source bar, otherwise the result is rejected as incomplete.
    This preserves a deterministic partial-edge convention without inventing candles across a data gap.
    
```

#### 805. `value_area_event` — function — `strategies/classic.py:155`

```text
Dalton's 80% rule at the close of a 30-minute period (`cut` = close time of the last 15m candle).
```

#### 806. `stretch` — function — `strategies/classic.py:196`

```text
Crabel's Stretch: the SMA of the last `days` closed days' min(High - Open, Open - Low).
```

#### 807. `narrow_range` — function — `strategies/classic.py:203`

```text
Crabel's NR-n: the last closed day's range the smallest of the last n days (None without the history).
```

#### 808. `orb_sessions` — function — `strategies/classic.py:223`

```text
(name, open_ms, close_ms) of the sessions running at now_ms for the coin (weekdays only).
```

#### 809. `previous_session` — function — `strategies/classic.py:248`

```text
(open_ms, close_ms) of the same session on the previous weekday (local calendar).
```

#### 810. `session_va_event` — function — `strategies/classic.py:266-270`

```text

    eng-95, Dalton's 80% rule by session (as on a stock exchange: yesterday's regular session's value area, today's
    open of the same session): the session opened outside the previous same session's TPO value area and closed two
    consecutive 30-minute periods (counted from the session's open) back inside it -> the far edge; out at the close.
    
```

#### 811. `failed_auction_event` — function — `strategies/classic.py:310-317`

```text

    eng-127, the failed auction (Steidlmayer / Dalton, auction market theory): the session OPENED INSIDE the previous
    same session's TPO value area, probed beyond one edge and did not find acceptance there - acceptance = two
    consecutive 30-minute periods closing beyond (the TPO convention of the 80% rule) - then a 30-minute period closed
    back inside: "price re-enters a previously accepted value range ... the market will auction to the opposite end"
    -> the far edge; the stop beyond the probe's extreme; out at the session's close. (The opening outside value is
    the 80% rule, session_va_event.)
    
```

#### 812. `session_orb` — function — `strategies/classic.py:363-370`

```text
Crabel's ORB on a running session. audit: Crabel, "Playing the Opening Range Breakout" Part 8 (Stocks &
    Commodities, p. 36) - the opening range of the first minutes (30 seconds to 5 minutes; 5 here), a buy stop the
    Stretch (the 10-day SMA of min(High - Open, Open - Low)) above its high and a sell stop the Stretch below its low;
    the first level TRADED through is the entry (a stop order fills on the touch, at the level or a gap's open), the
    other one the stop. Was: the session's open +- Stretch and a 5m CLOSE beyond (eng-105), another reference and
    moment. `minutes`: final 1m candles; the break is read on them (a minute late at most, the level is the price).
    audit E08: the contract is the CLOSED minute - price_hi / price_lo (the live tick) are accepted for the caller's
    signature and deliberately not read: a stop-entry detected on a candle that closed is a minute late, not instant.
```

#### 813. `rsi` — function — `strategies/classic.py:407`

```text
Wilder's RSI of the last close.
```

#### 814. `connors_event` — function — `strategies/classic.py:424-428`

```text

    Connors on DAILY candles (his system; the 1h version of eng-29's first draft was another system): the day that
    closed with RSI(2) in the extreme (`first=True`: not already there the day before; `first='orig'`: the original
    close-in rule - he is in until the SMA5 exit, and a run of oversold days is one trade).
    
```

### `strategies/classic_strategies.py`

#### 815. `<module>` — module — `strategies/classic_strategies.py:1-4`

```text

Cards of the classic methods in strategies/classic.py: each enters at its signal's close (as its author does), with
its own stop and target where the method defines one; the lifecycle, R:R rule and journal are shared.

```

#### 816. `ValueAreaStrategy` — class — `strategies/classic_strategies.py:16`

```text
Dalton's 80% rule: target the value area's far edge, stop beyond the edge price re-entered through.
```

#### 817. `OrbStrategy` — class — `strategies/classic_strategies.py:76-78`

```text
eng-93: the session opening range breakout (strategies.classic.session_orb) on the majors, gold, silver and
    oil: the first break of the Asia / London / New York session's first 30 minutes, the stop at the range's middle,
    TP1 the range's width projected, out at that session's close (was Crabel's open +- Stretch on the UTC day).
```

#### 818. `OrbStrategy.entry_levels` — function — `strategies/classic_strategies.py:87`

```text
Crabel ORB contract: opposite range level is the stop; session close is the exit.
```

#### 819. `ConnorsStrategy` — class — `strategies/classic_strategies.py:153`

```text
Connors' RSI(2): out at the SMA5 with an explicit 2 daily-ATR catastrophe stop.
```

#### 820. `ConnorsStrategy.entry_levels` — function — `strategies/classic_strategies.py:163`

```text
Connors contract: the SMA5 is the method exit and the 2 daily-ATR stop is real protection.
```

### `strategies/confirm.py`

#### 821. `<module>` — module — `strategies/confirm.py:1-28`

```text

Entry confirmations: independent evidence, measured at the entry, that the market backs the trade. The trigger itself
(a structure shift with agreeing taker flow, an accepted breakout, a confirmed phase) is the entry; these are the
readings order-flow traders check before taking it, each recorded for every entry (journal `confirms`):

- flow       futures taker delta since the extreme (at most the last hour) agrees with the trade;
- spot       spot taker delta over the same window agrees: real buying / selling of the coin, not only leverage
             (spot-led moves hold, perp-led ones get squeezed); 'n/a' for a coin without a spot pair;
- oi         open interest over the last hour (OI-weighted across venues when >= 2 report, else Binance): RISING for
             continuations (trend, momentum, breakout: new positions back the move - price and OI together), FALLING
             for sweeps and cascade exhaustion (the stops / liquidations were flushed); 'n/a' for Wyckoff (its phases
             score OI themselves) and absorption (absorbed market orders open positions on both sides);
- orderflow  at the extreme: stacked footprint imbalances, absorption (a heavy 1m delta against the trade that barely
             moved price), a finished auction (the footprint's extreme price traded only by the side that was pushing:
             nobody left to trade there, ATAS / Market Profile) or, for reversals, a CVD divergence (price made a new
             extreme beyond the previous swing, cumulative delta did not: the aggressive side is exhausted); False
             when none of them happened;
- vsa        Volume Spread Analysis on the 5m bars since the extreme (strategies/vsa.py, Tom Williams): no supply /
             stopping volume / reverse upthrust for longs, no demand / buying climax / upthrust for shorts.

Keys starting with '_' are metadata ('_window' = [since, until, extreme] ms, set by fetcher.confirmations), not readings.
Values: True / False, the order-flow kind (a string = present), NA ('n/a') where the reading cannot exist for this
coin / strategy. The inputs (1m candles of futures and spot, OI) are seeded from REST at start-up, so a reading is
never missing after a restart; if one still is (a REST failure), it is None and never vetoes.
Which confirmations an entry needs: CONFIG.orderflow.required_confirmations (by rule: a breakout needs rising OI,
like the D / F phases and directional impulses) plus those PROMOTED by the journal once entries without them show a
negative Edge (journal.refresh_confirm_stats). The rest are recorded and shown until stats.py proves them.

```

#### 822. `positive` — function — `strategies/confirm.py:54`

```text
A confirmation that is present (True or an order-flow kind), not 'n/a' / False / None.
```

#### 823. `required` — function — `strategies/confirm.py:59`

```text
Confirmations an entry of `strategy` needs.
```

#### 824. `required_names` — function — `strategies/confirm.py:69`

```text
Every confirmation name some strategy may require (configured, order flow, journal-promoted).
```

#### 825. `missing` — function — `strategies/confirm.py:91`

```text
The veto reason of the first required confirmation that is negative ('no_<name>').
```

#### 826. `delta` — function — `strategies/confirm.py:114`

```text
Taker delta (buy - sell quote) of the 1m candles opened in [since_ms, until_ms); 0 without trades.
```

#### 827. `covered_delta` — function — `strategies/confirm.py:119-122`

```text
eng-169d (audit P2: missing data is not a negative reading): the taker delta of [since_ms, until_ms) when the 1m
    candles cover it - at least one candle in the window and the last one opened at most 3 minutes before until_ms
    (the oi_change rule); None otherwise. delta() of a stalled / empty stream was 0 -> 'flow' / 'spot' False, journaled
    as an absent confirmation, counted by the promotion of required confirmations and by min_confirmations.
```

#### 828. `oi_change` — function — `strategies/confirm.py:130-133`

```text

    Relative OI change from the first sample at / after since_ms to the last at / before until_ms (a listing younger
    than the window: over its available history, at least 5 minutes). None without two such samples.
    
```

#### 829. `cvd_divergence` — function — `strategies/confirm.py:142-146`

```text

    Price made its extreme beyond the previous swing of the lookback while cumulative delta did not (long: a lower
    low on a higher CVD low). The previous swing = the most extreme candle closing at least 5 minutes before the
    extreme's candle. False when there is no such swing (nothing to diverge from).
    
```

#### 830. `evaluate` — function — `strategies/confirm.py:168-171`

```text

    All confirmations of one entry (see the module docstring). `spot_minutes` None = the coin has no spot pair;
    `oi` = the relative OI change over the last hour.
    
```

### `strategies/cup_handle.py`

#### 831. `<module>` — module — `strategies/cup_handle.py:1-13`

```text

Cup with handle (William O'Neil, "How to Make Money in Stocks"; statistics: Thomas Bulkowski, "Encyclopedia of Chart
Patterns"), on DAILY candles at the UTC day's close (eng-58; was 1h / 4h):

- a prior advance of >= 30% into the left rim (the lowest low of the 2x cup-length before it to the rim);
- the cup: 12-33% deep (O'Neil; eng-58, was up to 50%), 49..420 daily candles (7 .. 60 calendar weeks in the retained 898-bar window);
- the handle after the right rim: 7 .. 56 calendar days, drifting in the cup's UPPER half and no deeper than 12% of the
  rim, on lower volume than the cup's;
- the entry: the first close above the handle's high (the pivot) on >= 1.4x the average volume (O'Neil: +40-50%).
- stop below the handle's low; TP1 the pivot + 61% of the depth, TP2 + the full depth (Bulkowski's measure rule); O'Neil's own rule
  (cut losses at 7-8%, take 20-25%) is an exit rule, not an entry filter: the stop is the nearer of the handle's low
  and 8% below the entry, the minimum R:R to the measured target is 1.

```

#### 832. `cup_handle` — function — `strategies/cup_handle.py:32`

```text
The breakout of a cup with handle on the candle that just closed ([ts, o, h, l, c, quote_vol]), else None.
```

#### 833. `CupHandleStrategy` — class — `strategies/cup_handle.py:108`

```text
O'Neil's cup with handle: entry at the breakout close, stop below the handle, target the measured move.
```

#### 834. `CupHandleStrategy.entry_levels` — function — `strategies/cup_handle.py:116`

```text
O'Neil/Bulkowski contract: 8%/handle stop and measured cup targets.
```

### `strategies/detect.py`

#### 835. `<module>` — module — `strategies/detect.py:1-8`

```text

Loop-side detection of the event strategies. The coins' contexts (structure.Context) arrive from the maps worker
after each 15m close carrying that candle's events (sweeps, accepted breakouts); every scan this class
- releases those events once (a context rebuilt for the same candle does not fire it again),
- checks absorption on each new final 1m candle at the coin's significant levels,
- follows liquidation cascades until their leg is big enough (cascade.CascadeTracker).
It returns setup dicts that the scanner turns into signals (the coin's live Tier-0 metrics + the setup's anchor).

```

#### 836. `LiveDetector.state` — function — `strategies/detect.py:41`

```text
Fired close events [(symbol, setup, event_ts, fired_at)] of the last day (kept across restarts).
```

#### 837. `LiveDetector.wants` — function — `strategies/detect.py:56`

```text
Anything to look at this scan: pending close events, a new final minute, a running / new cascade.
```

#### 838. `LiveDetector.scan` — function — `strategies/detect.py:68`

```text
`minutes`: FINAL 1m futures candles [open_time, o, h, l, c, quote_vol, taker_buy_quote].
```

### `strategies/geometry.py`

#### 839. `<module>` — module — `strategies/geometry.py:1-13`

```text

Geometry shared by every strategy: the stop floor, the stop pushed beyond a stop pool, targets picked from the coin's
level map by the strategy's INTENT, the entry levels and R:R, and the R:R cap of a waiting zone.

Target intents (the strategy says what it trades toward; Fibonacci only where a real leg exists):
- 'extension'          continuation: strong zones beyond the leg's end, the leg's extensions fill empty slots;
- 'opposite_liquidity' a sweep: the nearest resting-stop pools on the other side first;
- 'mean'               absorption / exhaustion / climaxes: VWAP, POC, value area, volume nodes first;
- 'range'              a trading range's far side first;
- 'measured'           a breakout: strong zones beyond the edge, measured moves of the range fill empty slots.
A target is always >= zones.min_target_atr beyond its reference (and beyond the previous target); slots still empty are
1-ATR steps ('ATR step'), never copies of one level.

```

#### 840. `cost_of` — function — `strategies/geometry.py:25-31`

```text

    (volume_24h: the coin's; the slippage then grows as liquidity falls, levels.slippage_bps - the same model the
    journal's replay fills with, so an entry that passes R:R here is not a loser there by construction)
    Execution cost of a round trip in price units: the taker fees (0.05% a side at Binance VIP0) plus the slippage of
    a market entry and of a stop exit (levels.slippage_bps each). Fees alone made a 1-ATR stop on a quiet coin look
    ~0.3R cheaper than it trades.
    
```

#### 841. `stop_pierce` — function — `strategies/geometry.py:40-44`

```text

    eng-124: no source names the pierce quantile of a stop's buffer (p50 / p80 / p90) - the stop's level kind and its
    three measured quantiles (% of price) are journaled with each entry; with the row's sl / mae_4h / mfe_4h they show
    which buffer the stopped trades would have survived, to choose the quantile on live trades.
    
```

#### 842. `kind_at` — function — `strategies/geometry.py:58`

```text
The measured kind of the map zone a stop base sits on (the zone's own kinds, not its text label).
```

#### 843. `kind_of_label` — function — `strategies/geometry.py:68`

```text
The level kind behind a stop's source label (for its measured buffer).
```

#### 844. `stop_too_far` — function — `strategies/geometry.py:80-82`

```text
eng-91: a stop farther than levels.max_stop_pct from the entry is no trade (the 1.5 ATR(4h) pad of a coin whose 4h
    ATR a pump inflated put W's stop 48% away, PONS' 18% - live). Systems whose wide stop IS the method (the Turtles' 2N,
    Connors) are exempt.
```

#### 845. `stop_floor` — function — `strategies/geometry.py:91`

```text
Minimum stop distance: min_stop_atr x the larger of ATR14 and the last hour's ATR (ATR14 lags a waking market).
```

#### 846. `_target_in_zones` — function — `strategies/geometry.py:100`

```text
Whether a persisted target is actually represented by an allowed timeframe zone.
```

#### 847. `_kind_rank` — function — `strategies/geometry.py:120`

```text
One level kind's timeframe rank (see _zone_rank); None = valid on every timeframe.
```

#### 848. `_zone_rank` — function — `strategies/geometry.py:130-133`

```text
The highest timeframe rank among the zone's kinds (swing_15m, fvg_1h, ob_4h ...); None = valid on every
    timeframe (it holds a daily-or-longer untimed reference: previous day / week / month, the year, an open, a completed
    day's profile, a range); intraday untimed kinds (VWAP, round, book, liquidations, equal highs / lows, profile nodes)
    rank as 15m. A plan may target the zone when this rank >= its own timeframe's.
```

#### 849. `_trim` — function — `strategies/geometry.py:144-145`

```text
audit D05: the zone as a plan of timeframe rank `rank` sees it - the edges of its own levels only. A lower
    timeframe's level merged into a 1h swing's zone moved the 1h target (130.1 -> 129.9, R:R 3.01 -> 2.99).
```

#### 850. `htf_zones` — function — `strategies/geometry.py:157-159`

```text
The zones a plan of timeframe `tf` may target: its own timeframe and higher (2026-10-05, the owner: a 1h / 4h
    trade's TP1 was the nearest 15m swing / FVG, cutting the R:R of a stop now sized in the structure's ATR). A merged
    zone is cut back to the edges of the levels that qualify.
```

#### 851. `map_fill` — function — `strategies/geometry.py:175-179`

```text

    Fill the empty target slots (up to 3) with the nearest map zones beyond the last target, ANY strength (a single
    swing, a session high, an FVG, an order block): a level on the chart before an ATR step (the steps sat in empty
    space while levels stood right there, 2026-10-01: TP2 / TP3 were ATR steps on 18 / 21 of 35 entries).
    
```

#### 852. `is_synthetic` — function — `strategies/geometry.py:193`

```text
A target that is no price level: an ATR step, an R multiple, a placeholder ('none: ...').
```

#### 853. `setup_key` — function — `strategies/geometry.py:207`

```text
HIT_RATE's key: the setup without the journal's 'ENTRY ' prefix (audit C13).
```

#### 854. `finish_levels` — function — `strategies/geometry.py:214-229`

```text

    Entry / stop / three targets and the R:R checks, the same for every path (eng-41):
    - a LEVEL target sits in front of its level by the level kind's typical pierce (p50): price often turns before
      the level, and the replay counts a target only once traded through it - the old target on the level overstated
      R:R by about that pierce;
    - R:R is measured on the level targets only (an ATR step / an R multiple / a placeholder passes any threshold by
      construction - SMT's '2.5 R' targets: 2 of 44 reached); ATR steps count where the map holds nothing beyond the
      entry at all (price discovery - the owner's rule);
    - the R:R that decides is the BLENDED one of the actual exit (a third at each target; a missing level slot exits
      at the last level);
    - risk must be >= cost_guard x the round-trip execution cost (audit F09: the text said 3x / 'a third of the
      risk'; the rule is CONFIG.levels.cost_guard, 1 since eng-108 - the risk at least pays one round trip)
    - with a journal-measured p(TP_k before the stop) for the setup the entry must have a positive expectancy of its
      three thirds, sum_k (p_k x R:R_k - (1 - p_k)) / 3 at the upper ends of the shrinkage intervals; the method's
      minimum R:R (Strategy.min_rr, else the global one) holds as well.
    
```

#### 855. `obstacle_before` — function — `strategies/geometry.py:430-432`

```text
audit 2026-10-18 P2 #7, a diagnostic (journaled, never a filter): the nearest strong map zone the price meets
    between the entry and TP1 - (its near edge in R from the entry, its label). A method's own objective (a range's far
    side, an extension) skips the map on purpose; this shows what stands in the way, not that the target is wrong.
```

#### 856. `_cost_reason` — function — `strategies/geometry.py:444`

```text
The cost guard's veto as the rule actually stands (CONFIG.levels.cost_guard x the round-trip cost).
```

#### 857. `_min_rr` — function — `strategies/geometry.py:450`

```text
The plan's minimum R:R to TP1: its method's own (Strategy.min_rr, from the source) else the global rule.
```

#### 858. `_liq_price` — function — `strategies/geometry.py:459-460`

```text
The nearest untaken liquidity extreme of the zone in the trade's direction (its levels' own prices: a swing's
    wick, not the body edge the S/R zone starts from); the zone's near edge when it carries no liquidity part.
```

#### 859. `select_targets` — function — `strategies/geometry.py:470-473`

```text

    Up to three targets beyond `ref` in the trade's direction by the strategy's intent; `first` forces a primary
    objective (a range's far side) into the candidates. Returns (prices, labels).
    
```

#### 860. `zone_pad` — function — `strategies/geometry.py:571-573`

```text
The buffer beyond the stop's structure: the larger of the measured pierce of the level and
    zone_buffer_atr x the ATR of the structure's own timeframe (Seiden-style: 1-2 ATR of the zone's timeframe beyond
    its distal line; the owner: beyond the zone with a 3-5% margin - on alts' 4h that is ~1.5 ATR). eng-69.
```

#### 861. `capped_pad` — function — `strategies/geometry.py:587-589`

```text
eng-147: the buffer beyond a stop's structure. Moved past a pool / swing by stop_beyond: only moved_pad_atr x
    the working ATR (the stop sits at the pool's far edge; a deep raid of the pool itself can still reach it). Else the measured pierce, capped at pierce_cap_atr x
    the working ATR.
```

#### 862. `stop_levels` — function — `strategies/geometry.py:601-604`

```text

    The stop: beyond the strategy's reference (the anchor's extreme / the range middle / the trigger's swing) and a
    stop pool just behind it, then the ATR buffer, never closer than the stop floor.
    
```

#### 863. `exit_stop` — function — `strategies/geometry.py:646`

```text
A system's own stop rule (plan['exit']['stop']): ['pct', f] / ['atr', k] / ['ref', pad ATR] / ['price', p].
```

#### 864. `exit_target` — function — `strategies/geometry.py:661-665`

```text

    A system's own first target (plan['exit']['tp']): ['pct', f] / ['rr', r] / ['level', price, min R:R, fallback R]
    (the level when it pays min R:R, else the system skips - `low` True; no level -> fallback R) / ['map', min R:R]
    (the map's TP1). Returns (price, label, below the system's minimum R:R).
    
```

#### 865. `structure_stop` — function — `strategies/geometry.py:704-709`

```text

    Stop beyond the nearest price-action structure on the stop side (swings, equal highs / lows, previous day / week /
    sessions, range edges, round numbers, book bands) that leaves at least `floor` of risk, pushed beyond a stop pool
    right behind it, plus the ATR buffer. None when no such structure lies within max_stop_atr ATR (price discovery:
    then the fixed rule is all there is).
    
```

#### 866. `clear_pool` — function — `strategies/geometry.py:744-747`

```text
eng-84: a system's fixed-price stop (AUCTION's test, a trendline pivot, Connors' 3 ATR) went straight to the
    exchange, never checked against the map: SKY's sat 0.24% beyond the 1h low - inside that pool's usual pierce, and
    the raid of the low took it (liquidated longs printed below). A resting-stop pool between the stop and the entry
    whose usual pierce (p90) reaches the stop moves the stop beyond the pool's pierce.
```

#### 867. `system_levels` — function — `strategies/geometry.py:768-774`

```text

    Entry / stop / targets of the ported systems (strategies/maniac.py). Their own structural exits (beyond the sweep,
    the impulse's start, a level) are kept. Their FIXED exits (a % or ATR stop, a % or R target) ignore the map: a 1%
    stop on SUI (15m ATR 1.35%) sat inside one candle's noise and was taken before the move (live, 2026-09-30). Those
    are replaced by the map: the stop beyond the nearest structure, the targets at the next levels; the fixed rule is
    only the fallback where the map has nothing (price discovery).
    
```

#### 868. `_ext_label` — function — `strategies/geometry.py:932`

```text
'ext 1.272' for an extension target, '+ <zone>' when a 4h / daily / weekly zone sits within the pierce of it.
```

#### 869. `entry_levels` — function — `strategies/geometry.py:947`

```text
Entry / stop / targets for an entry at `entry` (targets behind the entry are dropped, refilled beyond it).
```

#### 870. `cap_for_rr` — function — `strategies/geometry.py:1022-1025`

```text

    The furthest entry (from the extreme toward TP1) that still pays min_rr_tp1 (net of fees) to TP1 with the stop at `stop_est`
    or the stop floor, whichever is wider: a waiting zone ends there.
    
```

### `strategies/ict.py`

#### 871. `<module>` — module — `strategies/ict.py:1-11`

```text

ICT / SMC readings of a plan (hypotheses, measured by the journal - never proven edges; Osler's NY Fed SR150 backs only
the stop clustering beyond round numbers / levels):

- protected swing: the last 15m pivot on the stop side that produced a break of structure (a later close beyond the
  opposite pivot before it). While it holds, the idea holds: the stop goes beyond it, not right behind an obvious
  unswept pool (equal lows, the day's low: the stops a raid takes before the move).
- premium / discount: where the entry sits in the dealing range (the last 48 1h candles' high - low), for the trade's
  direction: 0 = the cheapest end (a long at the range low), 1 = the dearest. ICT buys only in discount (< 0.5).
  Journaled as `range_pos`, split in stats.py; a filter only if the journal proves it.

```

#### 872. `protected_swing` — function — `strategies/ict.py:21`

```text
The price of the protected swing (the most recent one), None without a break of structure in the window.
```

#### 873. `dealing_range` — function — `strategies/ict.py:41-45`

```text

    ICT's dealing range (eng-51): the leg between the latest significant swing low and swing high (1h pivots with k
    candles on each side), equilibrium at its 50%. Was the 48h high / low window - a time box is not ICT's definition.
    Falls back to the window while the 1h history holds no pivot pair.
    
```

#### 874. `range_position` — function — `strategies/ict.py:70`

```text
0 = the cheapest end of the dealing range for this direction, 1 = the dearest (clipped).
```

#### 875. `fvg_trigger` — function — `strategies/ict.py:80-85`

```text

    ICT entry after a liquidity sweep: displacement (a candle with a body >= half its range in the trade's direction)
    that leaves a fair value gap (long: low[i] > high[i-2]) and shifts structure (a close beyond the highest high /
    lowest low since the sweep, before the displacement); the entry is the first later candle that retraces into the
    gap and closes without closing through it. A close through the gap kills it; the next displacement is searched.
    
```

#### 876. `_contiguous` — function — `strategies/ict.py:131`

```text
The run of time-contiguous bars ending at the last one (a gap / MSS across a hole is no structure).
```

#### 877. `raid_swing` — function — `strategies/ict.py:139-140`

```text
The swing the raid came from: the last 3-candle pivot high (long; low for a short) of the bars before the sweep
    at `since_ms` (up to 48 bars back) - the level fvg_setup's structure shift must close beyond. None without one.
```

#### 878. `fvg_setup` — function — `strategies/ict.py:154-160`

```text

    ICT's 2022 model after a liquidity sweep at `since_ms` (eng-58): a displacement candle (body >= half its range, in
    the trade's direction) that CLOSES BEYOND THE SWING THE RAID CAME FROM - the last 3-candle swing high (long; low
    for a short) of the bars before the sweep, the market structure shift - and leaves a fair value gap. Returns the
    gap and its consequent encroachment (CE, 50%) for a resting limit; the entry is that limit's fill (touch_trigger),
    not a later candle's close. eng-36..57 took any close above the highest high SINCE the sweep as the shift.
    
```

#### 879. `touch_trigger` — function — `strategies/ict.py:203-206`

```text

    Sam Seiden's entry: a resting limit at the fresh zone's PROXIMAL line, filled by the first candle that trades into
    it (at the open if it gapped past the line); the extreme is that candle's wick.
    
```

#### 880. `touch_confirm` — function — `strategies/ict.py:220-225`

```text

    eng-105, the owner: the touch confirmed by a CLOSE - the first closed trigger candle (since the zone was reached)
    that traded into the zone and closed back beyond its proximal line on the trade's side (a long: low <= zone_hi and
    close > zone_hi; a 'zone' of one price - a CE - the same with that price). The entry is that close; the extreme
    is the lowest low (highest high) since the zone was reached. A close through the zone's far side is no entry.
    
```

### `strategies/ind_panel.py`

#### 881. `<module>` — module — `strategies/ind_panel.py:1-8`

```text

Classic indicator panel of one coin at one moment (strategies.confirm journals it on every entry as `_ind`; the archive
study research_indicator_confirms.py uses the same functions): EMA 20 / 50 / 200 and the EMA50 slope (Murphy, Elder),
RSI 14 (Wilder), MACD 12 / 26 / 9 (Appel), ADX 14 with +DI / -DI (Wilder), stochastic 14 / 3 (Lane), Bollinger %B and
band width (Bollinger), MFI 14 (Quong & Soudack), OBV (Granville), CCI 20 (Lambert), ATR rank, relative volume.
`rules(ind, d)` turns them into booleans "the indicator agrees with a trade in direction d"; which of them CONFIRM an
entry is decided by research/indicator_confirms.md (pre-registered), not by this module.

```

#### 882. `ema` — function — `strategies/ind_panel.py:13-14`

```text
EMA seeded with the SMA of the first n values (TA-Lib / Appel; NaN before). Seeding with x[0] left EMA200 on the
    panel's 499 candles up to 0.4% off (research/talib_check.md). Shorter than n: seeded with x[0] (best effort).
```

#### 883. `rma` — function — `strategies/ind_panel.py:36`

```text
Wilder's smoothing (RSI, ADX, ATR as their authors define them).
```

#### 884. `rolling_std` — function — `strategies/ind_panel.py:57-58`

```text
Population std of each n-window from the deviations from its own mean (audit F01: sqrt(E[x^2] - E[x]^2)
    cancelled catastrophically at large prices - std 10.5 for 0.0009, false zeros at 1e8).
```

#### 885. `sma_valid` — function — `strategies/ind_panel.py:95`

```text
Simple moving average only when every value in the window is finite.
```

#### 886. `pct_rank` — function — `strategies/ind_panel.py:110`

```text
Share of the last n values below the current one.
```

#### 887. `adx_talib` — function — `strategies/ind_panel.py:120-122`

```text
(+DI, -DI, ADX) aligned with the bars, TA-Lib's ADX (unstable period 0): Wilder sums seeded with the first n-1
    true ranges / directional moves, the first ADX the mean of n DX values (audit E06: strategies.regime used another
    seed and zero-filled the early DX, 23.8 vs 26.1 at the threshold 25).
```

#### 888. `indicators` — function — `strategies/ind_panel.py:152-154`

```text
k: [open_ms, o, h, l, c, quote_volume(, taker_buy_quote, base_volume)]. Arrays aligned with k (value at
    candle i uses candles <= i). MFI (Quong & Soudack) and OBV (Granville) weight by the traded AMOUNT: base_volume
    (audit A16: typical x quote weighted price twice, 80 instead of 66.7); without it MFI falls back to the quote volume.
```

#### 889. `any_last` — function — `strategies/ind_panel.py:214`

```text
True when x was True on any of the last n candles.
```

#### 890. `rules` — function — `strategies/ind_panel.py:222`

```text
Each classic confirmation as a boolean array for direction d (+1 long / -1 short).
```

#### 891. `content_digest` — function — `strategies/ind_panel.py:274`

```text
A cheap fingerprint of candles' OHLCV (cache keys: a revised candle keeps its timestamp and the count).
```

#### 892. `panel` — function — `strategies/ind_panel.py:279-281`

```text
{rule: bool} on the LAST of `candles` ([ts, o, h, l, c, quote_volume, ...], closed, oldest first); {} with
    fewer than 250 candles (EMA 200 needs its warm-up). With a key (symbol, timeframe) the indicator arrays are cached
    until the next candle closes: every card of a coin asked for them again (watchdog: 2s loop stalls in rolling_min).
```

### `strategies/leg.py`

#### 893. `<module>` — module — `strategies/leg.py:1-16`

```text

Leg strategies: a real leg (levels.find_impulse: its end on the last 12h of 15m candles, its start searched back over
15m and 1h history; its timeframe by duration 15m / 1h / 4h, the entry 3-6x finer).

continuation (IMPULSE UP / DOWN from Tier-0; BULL F / BEAR D removed in eng-127 - Bollinger's Method I is BB1) by
ICT's optimal trade entry:
- the leg must BREAK STRUCTURE (its end beyond the last 3-candle swing in the 48 candles before its start; no swing =
  no trade) with displacement (a fair value gap inside it), both on the leg's own timeframe;
- Elder's tide ~5x the leg's timeframe (15m -> 1h trend, 1h -> 4h, 4h -> daily) not against the trade (plan());
- the zone = the OTE band itself (CONFIG.levels.continuation_zone, 0.62-0.79 of the leg);
- trigger 'touch': with executor.touch_confirm_close the entry is the CLOSE of the trigger candle that touched the
  zone and closed back on the trade's side (no resting limit);
- the stop beyond the leg's start (the 100% level); the card is invalid at continuation_invalid;
- targets the leg's extensions measured from its START: start + k x leg (CONFIG.levels.continuation_targets), then
  the map. No partial / trail after TP1 (off since eng-111): the position exits in thirds at the targets.

```

#### 894. `_continuation_targets` — function — `strategies/leg.py:34`

```text
Continuation-owned OTE target ordering: leg extensions, then map levels.
```

#### 895. `_closed_df` — function — `strategies/leg.py:57`

```text
Drop an in-progress 15m row while retaining all rows in replay/closed-frame callers.
```

#### 896. `_ema_of_tf` — function — `strategies/leg.py:66`

```text
The EMA of the leg's own timeframe: 15m from the frame, 1h from the 1h candles, 4h = 4 x span on 1h.
```

#### 897. `_to_4h` — function — `strategies/leg.py:81`

```text
1h candles [ts, o, h, l, c, vol] grouped into the 4h candles they make (UTC 4h boundaries).
```

#### 898. `_adjacent` — function — `strategies/leg.py:98-99`

```text
Three rows are three consecutive candles of the timeframe (audit 2026-10-18: a hole between rows is missing data,
    not a gap / swing the market made).
```

#### 899. `broke_structure` — function — `strategies/leg.py:105-106`

```text
ICT: the impulse must break structure - its end beyond the last 3-candle swing high (up; low down) formed in the
    48 candles before the leg's start (a swing high below the start does not count for an up leg).
```

#### 900. `displacement` — function — `strategies/leg.py:122-125`

```text

    ICT's displacement: the leg left a fair value gap in its direction - three candles inside the leg where the first's
    high is below the third's low (up; mirrored down): price moved too fast for the other side to trade there.
    
```

#### 901. `LegContinuation.entry_levels` — function — `strategies/leg.py:142`

```text
ICT OTE contract: impulse-start invalidation and measured extensions.
```

#### 902. `LegContinuation.context_veto` — function — `strategies/leg.py:157-160`

```text

        BTC not moving hard against the trade over the last hour (tide_btc_against) - a shadow veto ('btc_against').
        The coin's own tide (Elder, ~5x the leg's timeframe) is checked in plan(), not here.
        
```

#### 903. `MomentumStrategy` — class — `strategies/leg.py:224`

```text
The impulse detected by Tier-0 (5m move + OI + flow); the same pullback trade (eng-35: one strategy).
```

### `strategies/level.py`

#### 904. `<module>` — module — `strategies/level.py:1-14`

```text

Level strategies: the anchor is a price level and the extreme made at it, not a leg (no Fibonacci).

- sweep (SWEEP LOW / SWEEP HIGH): a closed 15m candle pierces a higher-timeframe resting-stop pool (structure.py) -
  at most the pool kind's measured pierce p90 (no minimum with the pierce model) - and closes back beyond it on
  volume. Bias: the weekly bias, else the daily, else the coin's trend (context_veto: 'against_bias' /
  'against_trend'). A raid outside a 1h+ POI ('no_htf_poi') and an entry in premium / discount of the dealing range
  ('premium' / 'discount') are SHADOW vetoes again (eng-148: eng-147 had made them blocking; audit 33: the cut and the
  kept entries lost alike, journaled until a pre-registered test decides).
- the entry (trigger 'fvg', ICT's 2022 model, eng-58): a displacement that breaks the swing the raid came from and
  leaves a gap arms the gap's CE (ict.fvg_setup); with executor.touch_confirm_close the trade opens at the CLOSE of
  the trigger candle that touched the CE and closed back on the trade's side (no resting limit).
- stop beyond the wick (and a pool behind it) + the measured pierce; targets: the draw on liquidity.

```

#### 905. `_contract_pad` — function — `strategies/level.py:26`

```text
Sweep-specific stop padding; kept local so geometry cannot decide the raid stop.
```

#### 906. `_sweep_targets` — function — `strategies/level.py:38`

```text
Sweep-only draw selection: nearest map zones beyond MSS, then ATR discovery steps.
```

#### 907. `reached_since` — function — `strategies/level.py:64`

```text
Furthest price in the trade's direction from `start` over the final 1m candles since `since_ms`.
```

#### 908. `pool_rank` — function — `strategies/level.py:77`

```text
Significance of a pool by its label: previous week > previous day / day > sessions, equal levels, round > 1h swing.
```

#### 909. `sweep_tf` — function — `strategies/level.py:88-89`

```text
eng-84: the plan timeframe of a sweep by the swept pool: a 1h swing -> 15m (5m trigger), sessions / equal
    levels / rounds / the day / previous day / week -> 1h (15m trigger).
```

#### 910. `sweep_at_close` — function — `strategies/level.py:98`

```text
The candle that just closed took a pool and closed back beyond it on volume -> the sweep event.
```

#### 911. `SweepStrategy.entry_levels` — function — `strategies/level.py:164`

```text
ICT sweep contract: raid extreme stop and opposite-liquidity targets.
```

### `strategies/loopside.py`

#### 912. `<module>` — module — `strategies/loopside.py:1-8`

```text

Loop-side setup detectors (eng-59, B9): the strategies the scanner checks on the final 1m candles / daily candles of
each coin rather than in the maps worker - the pump start / top, the Silver Bullet, PO3, the Turtles' touch, Crabel's
ORB, the OI signal, the dump bounce, Connors' RSI(2). Moved out of scanner.Scanner so the archive replay
(replay.py) runs the SAME code as the live bot. `md` is the coin's MarketData (or the replay's stand-in with the same
fields: d1, h1, tier0, oi_samples, minute_closed_until); `minutes_of(symbol)` returns the FINAL 1m futures candles,
`m15_of(symbol)` the closed 15m candles [ts, o, h, l, c, quote_vol, taker_buy].

```

#### 913. `LoopDetectors._skip` — function — `strategies/loopside.py:46`

```text
One skip_log row per coin and strategy until the log is drained (replay never drains: no unbounded growth).
```

#### 914. `LoopDetectors.scan` — function — `strategies/loopside.py:52`

```text
Every loop-side setup of the coin this scan (in the scanner's order).
```

#### 915. `LoopDetectors._pumps` — function — `strategies/loopside.py:65`

```text
The pump's start (every final minute) and top (every 15m close), cheap gates first (strategies.pump).
```

#### 916. `LoopDetectors._silver_bullet` — function — `strategies/loopside.py:117-118`

```text
ICT's Silver Bullet (strategies.silver_bullet), only inside its New York windows, once per window and
        direction per coin, on each new final 5m bar.
```

#### 917. `LoopDetectors._po3` — function — `strategies/loopside.py:146-147`

```text
ICT's Power of Three / Judas swing (strategies.po3) in the London kill zone, on each new final 5m bar, once
        per coin, day and direction.
```

#### 918. `LoopDetectors._turtle_breakout` — function — `strategies/loopside.py:169-170`

```text
The Turtles' channel breakout on the touch (strategies.turtle), checked on each new final minute, once per
        coin, direction and day.
```

#### 919. `LoopDetectors._orb_touch` — function — `strategies/loopside.py:207-209`

```text
eng-93: the session ORB (strategies.classic.session_orb) on the majors, gold, silver and oil only: the first
        break of the Asia / London / New York opening range, on the final minute or the live trade price (Crabel's
        entries are stop orders resting at the levels - eng-82).
```

#### 920. `LoopDetectors._oi_build` — function — `strategies/loopside.py:236`

```text
eng-127, Pring's OI rule in shadow (strategies.oi_build): at 5m closes, once per coin per hour.
```

#### 921. `LoopDetectors._dump_bounce` — function — `strategies/loopside.py:264`

```text
The short of the first bounce after a dump (strategies.pump.dump_bounce) on each closed 1h candle.
```

#### 922. `LoopDetectors._connors_daily` — function — `strategies/loopside.py:286`

```text
Connors' RSI(2) on the coin's daily candles, once per closed day (fresh within the day's first 2 hours).
```

### `strategies/maniac.py`

#### 923. `<module>` — module — `strategies/maniac.py:1-25`

```text

Detectors of crypto_maniac's trading systems (github.com/roman-boop), ported rule for rule onto our candles
[open_time, open, high, low, close, quote_volume, taker_buy_quote]. Each fires on the candle that just closed (the
maps worker runs them after every 15m close; the 1h systems when an hour closed), so an event fires once.

    system (his repo)                    tf        event                                    entry / exit (his)
    supply_demand-v4                     15m / 5m  a demand / supply zone confirmed         5m pinbar retest, stop beyond
                                                                                             the pinbar and the zone
    auction_theory_in_code               1h        POC retest reacted (auction_engine.py)   at the close, naked POC / 2.5R
    lllll (SMT / Quasimodo)              15m / 5m  2-candle sweep of an external pool       5m inversion FVG, opposite
                                                   + SMT vs BTC (ETH for BTC) or QM          pool (>= 2R) else 2.5R
    trendline_bot                        15m       2 closes beyond a sloped line            at the close, first anchor
    thirdeye_strategy_algo               1h        CCI(25) crossing +-98 + Ichimoku, EMA200, at the close, SL 1% TP 5%
                                                   ADX / RSI / NATR / BBW filters
    fibonachi_trading_system             1h        a candle pierces the impulse's 0.5 and    at the close, stop beyond
                                                   closes back                               the impulse, its extreme
    bomberman_bot                        1h        MACD cross + EMA100 side + QML + BBW      at the close, 1.5 ATR / 2R
    bollinger_bands-with-clusters        15m       close beyond BB(40, 1.5) in a CSI         at the close, SL 0.4%,
                                                   cluster of the same side + RSI(96)        out after 3 bars
    oi_trading_robot v7.4                1m/5m OI  OI +5%/1h, price <= half of it, OI 24h    long, ATR stop / targets
                                                   above price 24h, 15m higher lows          (strategies/maniac_oi)

Fixes of his code (the ideas as written, not the slips): Third Eye's realtime filters `(~use_x or cond)` are always
true in Python (~True == -2), so his live bot traded the CCI cross alone - here the filters apply as in his backtest.

```

#### 924. `wilder` — function — `strategies/maniac.py:48-50`

```text
RMA / Wilder smoothing, seeded with the mean of the first n values as Wilder / TA-Lib (owner 2026-10-18: one
    ATR everywhere - this was seeded with the first value, a different number than the panel's / geometry's for
    hundreds of bars). Before the seed: the running mean of the values so far (no NaN for the callers' indexing).
```

#### 925. `_base_volume` — function — `strategies/maniac.py:88`

```text
audit: the bars' BASE volume (quote volume / typical price) for the volume indicators (Intraday Intensity).
```

#### 926. `is_bull_pinbar` — function — `strategies/maniac.py:128-129`

```text
His rejection candle (supply_demand-v4 is_bullish_pinbar_df): body <= 35% of the range, a bullish close, the
    lower wick >= 55% of the range and >= 2x the upper wick.
```

#### 927. `in_session` — function — `strategies/maniac.py:146-147`

```text
Inside any of the session's [start, end) windows of the day in its time zone: (tz, start, end[, start, end...])
    (DST handled; windows across midnight too).
```

#### 928. `_boring` — function — `strategies/maniac.py:164`

```text
OTA / Seiden: a base ("boring") candle - its body at most half its range.
```

#### 929. `_exciting` — function — `strategies/maniac.py:169`

```text
A leg-out ("exciting") candle of the side: body more than half its range, closing in the side's direction.
```

#### 930. `_sd_bases` — function — `strategies/maniac.py:174-179`

```text

    Every base of the history and its departure: a run of boring candles followed by a run of exciting candles of
    one side. Demand: distal = the lowest low of the base, proximal = its highest body; supply mirrored. The departure
    ends at the first candle that is not exciting (its close confirms the zone). `speed` = the departure's move beyond
    the proximal line per candle, in ATR(14) (Seiden: "how quickly they leave"); `n_base` = the base's candles.
    
```

#### 931. `sd_zone_events` — function — `strategies/maniac.py:218-229`

```text

    eng-127, Sam Seiden / Online Trading Academy's odds enhancers ("5 years of Sam Seiden supply and demand
    teaching": Strength of the move max 2, Time at level max 1, Freshness max 2, Reward / Risk max 2, Big picture
    max 2, Arrival max 1; 9-10 limit order, 8 confirmation entry, below that no trade). The zones CONFIRMED by the
    candle that just closed; the history-relative scores are fixed here, the rest at the entry
    (SupplyDemandStrategy / SignalBook):
      strength  the departure speed ranked among this coin's departures (Seiden: "the more quickly they move, the
                more out of balance"): upper third 2, middle 1, lower 0;
      time      the base's candles at most the coin's median (Seiden: "few candles ... be very careful about coming up
                with a specific number") 1, else 0.
    Replaces the ported supply_demand-v4 thresholds (0.55 ATR body, 2 ATR within 4 bars, 1.2 ATR height, score 3.5).
    
```

#### 932. `sd_opposing` — function — `strategies/maniac.py:263-271`

```text

    Seiden's target: the OPPOSING zone - for a demand trade the nearest fresh supply zone above (its proximal line,
    the lowest body of its base), for a supply trade the nearest fresh demand zone below (its proximal line, the highest
    body); "the distance between our supply and target (T1: Demand) represents our potential profit zone" (FXStreet,
    'Lessons from the pros', 2014). review V10: fresh = price has not traded back INTO it (a high / low reaching
    its proximal line) since it was confirmed - closes alone missed a wick into the zone. Up to `n`
    [price, label] pairs, nearest first. Was the map's opposite liquidity (old highs / lows, equal levels, sessions),
    which is not his target.
    
```

#### 933. `_em_line` — function — `strategies/maniac.py:304-308`

```text

    eng-122, Edwards & Magee's trendline: drawn through the two LAST reaction points (2/2 swings) - a down trendline
    (resistance) through two falling tops, an up trendline (support) through two rising bottoms - and valid while no
    close went beyond it between them and since (no parameters of a bot).
    
```

#### 934. `trendline_em_event` — function — `strategies/maniac.py:335-341`

```text

    eng-107, the trendline break as Edwards & Magee define a DECISIVE penetration ("Technical Analysis of Stock Trends",
    via Peter Brandt): a CLOSE beyond the line by about 3% of the price (eng-109: their 3%; Brandt's 1-2% is his own
    suggestion for commodities / forex), confirmed by time (two closes beyond) and by volume (the breaking bar's volume
    above the 20-bar average - their volume test; the exact wording of the book was not found). The same line as
    the ATR-line bot (deleted in eng-127).
    
```

#### 935. `trendline_touch_event` — function — `strategies/maniac.py:386-391`

```text

    eng-150 (plan 4.10), Edwards & Magee: a line through the two last reaction points is confirmed by its THIRD touch.
    The touch = the latest closed candle reached the band line +/- tl_band_atr x ATR14 and closed on the line's side
    (no close beyond the line since its first point, _em_line); only the first touch after the second point.
    The entry is that candle's close, with the line (support -> long, resistance -> short).
    
```

#### 936. `parabolic_sar_step` — function — `strategies/maniac.py:437-442`

```text

    One bar of Wilder's Parabolic SAR (New Concepts in Technical Trading Systems, 1978: AF 0.02, +0.02 per new extreme,
    at most 0.20) for a position of side d: (new sar, ep, af, stopped). The bar is first checked against the current
    SAR (a touch stops the position), then the SAR for the next bar is computed. prev_hi / prev_lo: the PREVIOUS
    bar's extremes - Wilder (and TA-Lib's SAR) keep the SAR outside the last TWO bars' range (audit A03).
    
```

#### 937. `bb_method1_event` — function — `strategies/maniac.py:457-470`

```text

    eng-127, Bollinger's Method I - volatility breakout (Bollinger on Bollinger Bands, ch. 15-16): "await a Squeeze, then
    go with the expansion".
    - BB(20, 2); BandWidth = (upper - lower) / middle; the Squeeze = BandWidth at its lowest of the last 125 bars
      (his "six-month low" is 125 bars of the DAILY chart; applying 125 bars to other timeframes is our assumption,
      measured in research/bb1_windows.md);
    - the signal: the FIRST close outside a band after the last Squeeze bar (no close outside since it), confirmed
      by the volume indicator he pairs with the bands - Bostian's Intraday Intensity % (21) > 0 for a close above
      the upper band, < 0 below the lower;
    - the head fake is handled by the exit he names: Wilder's Parabolic SAR (0.02 / 0.20), its first value the
      extreme against the trade of the 20 bars of the band (the prior range), trailed bar by bar (SignalBook).
    No target (an expansion is ridden until the SAR stops it). Replaces BULL F / BEAR D (phase scores with our delta /
    OI floors and an ICT pullback entry).
    
```

#### 938. `bb_method3_event` — function — `strategies/maniac.py:513-525`

```text

    eng-106, Bollinger Method III exactly as John Bollinger's Method III manual (bollingerbands.com, 2021) states it:
    "A tag of the lower Bollinger Band while Intraday Intensity is positive will create a buy alert ... a tag of the
    upper Bollinger Band while Intraday Intensity is negative will generate a sell/short alert. These are alerts rather
    than signals ... wait for a strong up bar after a buy alert, or a strong down bar following a short alert".
    - BB(20, 2); Intraday Intensity (Bostian) normalized over 21 bars: sum((2C - H - L) / (H - L) x V) / sum(V);
    - the alert: a bar whose low tagged the lower band (high the upper) with II% > 0 (< 0), within the last 5 bars;
    - the confirmation, on the bar that just closed (the first after the alert): a strong bar in the trade's way -
      body >= half its range, close in the outer third, range >= the median range of the last 20 bars (ours: the
      manual gives no number);
    - stop beyond the extreme since the alert, the first target the opposite band (the manual names neither: ours, as
      the W / M). Journaled in shadow (SignalBook: 'bb3_shadow') beside the W / M.
    
```

#### 939. `bollinger_wm_event` — function — `strategies/maniac.py:578-586`

```text

    John Bollinger's reversal method ("Bollinger on Bollinger Bands", 2001, method III; W / M patterns after Arthur
    Merrill): a band tag is NOT a signal by itself. W-bottom: a low that closed BELOW the lower band (%b < 0), a rally,
    a retest low whose close stays INSIDE the band (%b >= 0, the price low may be lower), then the first close above the
    rally's high between them -> long at that close; stop below the retest low; out at the OPPOSITE BAND as it moves
    (Bollinger; eng-51 / 55), A/D must not confirm the retest.
    M-top mirrored. BB(20, 2), within the last 30 15m candles. (Replaces crypto_maniac's CSI system: a close beyond
    BB(40, 1.5) read as a reversal contradicts Bollinger's own rule, and its "candle sentiment index" is his invention.)
    
```

#### 940. `ifvg_trigger` — function — `strategies/maniac.py:666-671`

```text

    lllll find_first_inversion on the entry timeframe: for a buy the FIRST bearish FVG (high[i] < low[i-2]) formed
    from 40 bars before the pierce on is inverted by a close ABOVE its top (a sell mirrored); FVGs smaller than 0.03
    ATR are noise. Only an inversion closing at or after `scan_from_ms` counts. Entry at that close; the extreme is
    the deepest price since the pierce.
    
```

#### 941. `pinbar_trigger` — function — `strategies/maniac.py:708-709`

```text
supply_demand-v4: the first closed entry-timeframe candle since `since_ms` that is a pinbar retesting the zone
    (its wick into the zone, the close inside it or at most 25% of the zone's height beyond the near edge).
```

### `strategies/maniac_strategies.py`

#### 942. `<module>` — module — `strategies/maniac_strategies.py:1-6`

```text

Cards of crypto_maniac's systems (detectors: strategies/maniac.py, classic.py). Each keeps its author's entry
and exit: the entry at the signal's close (confirm_only: skipped, not re-timed, when his rule rejects it) or a
retest trigger (the trendline: 'shift', a structure shift with agreeing flow in the retest area), his stop and his
target; the lifecycle, journal and stats are ours. Also the failed auction (AuctionStrategy, Dalton).

```

#### 943. `_maniac_map_targets` — function — `strategies/maniac_strategies.py:25-29`

```text
Local map target selection for the trendline playbooks.

    Prizrak's target contract is explicit here: a 1h trendline may not use a 15m swing/FVG as TP1.  The shared
    geometry layer already applies this rule; this local selector now does the same before choosing its first level.
    
```

#### 944. `_finish` — function — `strategies/maniac_strategies.py:48`

```text
The card's targets as they stand at the estimated entry (the entry recomputes them at its own price).
```

#### 945. `_confirm_plan` — function — `strategies/maniac_strategies.py:68`

```text
A system entering at its signal's close: a narrow zone around that close, no waiting.
```

#### 946. `SupplyDemandStrategy` — class — `strategies/maniac_strategies.py:110-122`

```text

    eng-127, Seiden / OTA's odds enhancers (strategies/maniac.sd_zone_events): a 4h zone, its first return; the entry
    at the close of the candle that touched the zone and closed back (the confirmation entry - Seiden's score 8; the
    bot takes no resting limits), the stop beyond the distal line, the target the opposite liquidity at >= 3:1 (his
    profit margin). The score (max 10) is completed here and the entry vetoed below 8 ('sd_score'):
      strength 0-2, time 0-1    from the detector (the coin's own history);
      freshness 2               the first return only (a second would be 1, a third 0: not traded);
      reward / risk 2           min_rr 3 (his "at least 3:1") - below it there is no trade at all;
      big picture 0-2           1 for the daily trend with the trade (coin_trend of the daily closes), 1 for the
                                zone on the right side of the curve (the lower half of the 20-day range for demand);
      arrival 0-1               1 when no opposite swing (a 2/2 fractal of 1h) formed on the way back to the zone
                                (Seiden: "we don't want new resistance levels before we buy").
    
```

#### 947. `SupplyDemandStrategy.entry_levels` — function — `strategies/maniac_strategies.py:131`

```text
Seiden supply/demand contract: distal zone stop and opposing fresh-zone target.
```

#### 948. `AuctionStrategy` — class — `strategies/maniac_strategies.py:231-233`

```text
eng-127, the failed auction (strategies/classic.failed_auction_event): in at the close of the 30-minute period
    back inside value, the stop beyond the probe's extreme, the target the value area's opposite end, out at the
    session's close. Replaces the ported auction_theory_in_code POC retest (its 0.35 ATR / 1.5 R / 2.5 R numbers).
```

#### 949. `structural_stop` — function — `strategies/maniac_strategies.py:267-268`

```text
trendline_bot structural_stop: the last confirmed 5m pivot (3 / 3) beyond the entry, else the extreme of the
    last 40 5m bars, + a 0.1 ATR(5m) pad.
```

#### 950. `_pivot_stop` — function — `strategies/maniac_strategies.py:288`

```text
The last confirmed pivot (3 / 3) of `bars` beyond the entry, else the extreme of the last 40 bars, + pad.
```

#### 951. `TrendlineStrategy` — class — `strategies/maniac_strategies.py:307-309`

```text
Edwards & Magee trendline break on 1h lines: two closes beyond the line, then the retest - a 15m structure
    shift with agreeing taker flow between the broken line and its measured pierce (trigger 'shift', eng-84; no
    resting limit), the stop beyond the last confirmed 1h pivot, targets the next 1h+ levels of the map.
```

#### 952. `TrendlineBreakStrategy` — class — `strategies/maniac_strategies.py:370`

```text
Edwards–Magee break/retest playbook kept separate from the third-touch playbook.
```

#### 953. `TrendlineTouchStrategy` — class — `strategies/maniac_strategies.py:385`

```text
Third-touch trendline reaction playbook; it is not a breakout/retest signal.
```

#### 954. `BollingerStrategy` — class — `strategies/maniac_strategies.py:402-403`

```text
Bollinger's W-bottom / M-top (method III): entry at the close beyond the middle peak, the stop beyond the retest,
    the first target the opposite band (then the map).
```

#### 955. `_padded_bollinger_stop` — function — `strategies/maniac_strategies.py:434`

```text
Apply the same measured-pierce / volatility-floor contract as geometry.system_levels' trail branch.
```

#### 956. `BollingerSqueezeStrategy` — class — `strategies/maniac_strategies.py:500-501`

```text
eng-127, Bollinger's Method I (strategies/maniac.bb_method1_event): in at the close of the first band close after
    a Squeeze, out on Wilder's Parabolic SAR of the 4h bars (SignalBook._trail), no target.
```

#### 957. `BollingerSqueezeStrategy.entry_levels` — function — `strategies/maniac_strategies.py:509`

```text
Bollinger Method I contract: SAR protective stop, no fixed target.
```

### `strategies/oi_build.py`

#### 958. `<module>` — module — `strategies/oi_build.py:1-13`

```text

OI build (eng-127): Martin Pring's open-interest rules (as summarized from his writing) - "prices rising and open
interest increasing at a rate faster than its average = bullish", prices falling with open interest rising faster
than its average = bearish (new positions behind the move). A formula without our thresholds:

- at each 5m close, the 1h OI change (Binance, the 5-minute OI series of the last day) is above the MEAN of the
  day's 1h OI changes and above zero, and the 1h price change has the trade's sign;
- in at that close, the stop beyond the hour's extreme + the measured pierce, targets the opposite liquidity on the map.

No study shows OI changes predict crypto perpetual returns (and Binance's reported OI is known to be misquoted at
times, arXiv 2310.14973), so the setup is journaled in SHADOW only ('oi_shadow': SignalBook) until its own rows show
an edge. Replaces the OI robots of eng-56 / eng-88 (cryptomillion's OI [15m] alert and our +5% / VWAP / ER floors).

```

#### 959. `_oi_targets` — function — `strategies/oi_build.py:29-35`

```text
OI-build-owned opposite-liquidity targets with a cost-aware first target floor.

    OI's raw level map often contains a near micro-level immediately in front of the entry.  It is
    still a valid map observation, but it is not a usable TP1 when the net reward is below one unit
    of the actual stop risk.  Skip those levels before writing the contract targets so the shared
    geometry layer sees the first structural level that can pay the trade's round-trip cost.
    
```

#### 960. `_oi_change` — function — `strategies/oi_build.py:68-70`

```text
The OI change over `minutes`, None without a sample within 3 minutes of that time (eng-74: the last sample
    before it was taken whatever its age - after a feed gap NEAR's '15m' and '1h' changes were both +4.68% against an
    OI that Binance's own history shows flat, and the trade entered on it).
```

#### 961. `_close_at` — function — `strategies/oi_build.py:81`

```text
The close of the 1m candle that opened at ts_ms (a gap there -> None: no move measured across a hole).
```

#### 962. `_abs_move_1h` — function — `strategies/oi_build.py:91`

```text
The coin's usual 1h move: the mean |close / close 4 bars back - 1| over the last `bars` closed 15m candles.
```

#### 963. `oi_build` — function — `strategies/oi_build.py:99-107`

```text
minutes: final 1m candles; oi_5m: (ts_ms, OI) one sample per 5 minutes over the last day; oi_samples: the live
    OI samples (the journal's oi_chg_60m reads the same series); m15: closed 15m candles; btc_*: BTC's, None for BTC.

    eng-169i: Pring's "faster than its average" as a material move, not any tick above the mean (26.10: entries on OI
    +0.11% at a mean of +0.11%, price +0.04%; 18 longs in 2h, 15 stopped, all on BTC's +0.87% hour):
    - OI: the 1h change >= 2 robust sigmas above the day's 1h changes (median + 2 x 1.4826 MAD), and > 0;
    - price: the 1h move >= the coin's usual 1h move (mean |1h change| over 3 days of 15m candles);
    - the coin's own move: its 1h move in units of its usual move beats BTC's in BTC's units by >= 1 (a beta 2 alt
      on a BTC hour moves 2x BTC in % but not in its own units).
```

#### 964. `OiBuildStrategy.entry_levels` — function — `strategies/oi_build.py:171`

```text
Pring OI-build contract: hour extreme stop and opposite-liquidity targets.
```

### `strategies/pd_features.py`

#### 965. `<module>` — module — `strategies/pd_features.py:1-16`

```text

eng-159: the pump / dump detector's feature layer (docs/PUMP_DUMP_DETECTOR.md), from the owner's research.

Every feature is the coin against its OWN history:
- volume baselines are 24h MEDIANS (the closed 15m candles of the last 24h: a single spike no longer inflates the base
  the way the 24h mean did); per 1m = median15 / 15, per 5m = median15 / 3;
- the 5m layer is built from the final 1m candles: volume ratio and the cluster (5m bars >= 3x among the last 4),
  range_ratio (the bar's % range / the median of the 5m bars in the ring), move3 / move6 (15 / 30 minutes), the 2h
  breakout (close beyond the previous 24 x 5m extreme), the quiet period before (2-6h range vs its median);
- phases: LATE (move over 12 x 5m >= 12% with volume >= 10x and range >= 4x - the screener's late pump: seen, too late)
  and SPIKE_FAIL (a 5m bar >= 5% retraced >= 70% within the next 2 bars - a false start in the last 30 minutes).
Thresholds come from aleks-ent/pump-dump-crypto-screener PUMP_DETECTION_RULES.md (read at the source 2026-10-24;
heuristics, not measured); the 288-candle 5m baselines are fetched by REST when a PUMP / DUMP START fires: the features are
journaled (pd_* columns) and LATE / SPIKE_FAIL are SHADOW vetoes (strategies.shadow_vetoes) until the live journal
shows what they are worth.

```

#### 966. `bars_5m` — function — `strategies/pd_features.py:25-26`

```text
Final 1m candles -> complete 5m bars [ts, o, h, l, c, quote_vol, taker_buy_quote] (a bucket missing a minute is
    dropped - a hole beats a false bar).
```

#### 967. `volume_base_1m` — function — `strategies/pd_features.py:44`

```text
The 24h MEDIAN quote volume of a minute: median of the last 96 closed 15m candles / 15.
```

#### 968. `features` — function — `strategies/pd_features.py:61-64`

```text
pd_* features at the last final minute, for a move in `direction` (+1 pump, -1 dump).

    m5: closed 5m candles of the last 24h+ (REST, the source's 288-candle baselines); without it the 5m bars of the 1m
    ring are the base (pd_base_n says how many).
```

#### 969. `activation` — function — `strategies/pd_features.py:181-182`

```text
The source's ACTIVATION on the last CLOSED 5m bar of the ring: volume >= 3x the median 5m volume, range >= 1.5x
    the median 5m range, close above the bar 3 back, and close beyond EMA20 or a breakout of the previous 24 bars.
```

#### 970. `extras` — function — `strategies/pd_features.py:206-212`

```text
eng-159c, from the other sources of the owner's research (read 2026-10-24):
    - pd_trades_ratio_5m: trades of the last closed 5m candle / the median of the previous 288 (La Morgia et al. 2020,
      'The Doge of Wall Street' 2023: StdTrades / rush orders jump at the pump's start); REST kline field n;
    - pd_price_vs_ma12h: close vs the 12h moving average of the open (Kamps & Kleinberg 2018 / the 2025 thresholding
      detector: price against a 12h moving average), signed by the direction;
    - pd_vs_btc: the coin's 30-minute move minus BTC's (the BOCD detector of RaibekTussupbekov judges an alt against
      BTC/USDT), signed by the direction.
```

#### 971. `ActivationLog` — class — `strategies/pd_features.py:273`

```text
First ACTIVATION per (coin, direction) - the detector's lead time (journal pd_activation_lead_s).
```

### `strategies/po3.py`

#### 972. `<module>` — module — `strategies/po3.py:1-17`

```text

ICT's Power of Three / Judas swing (eng-58; innercircletrader.net, theinnercircletraders.com, ictkillzone.com - ICT
publishes it only in videos, so the rule is the common ground of several write-ups): a day unfolds as
accumulation (the Asian range), manipulation (a false move at the London open beyond one side of that range against
the day's bias - the Judas swing, which takes the stops there) and distribution (the true move the other way).

- the Asian range: the high / low of 20:00-00:00 New York time (ICT's Asian range);
- the window: the London kill zone, 02:00-05:00 New York time;
- the Judas swing: a 5m bar inside the window trades beyond the Asian range's side OPPOSITE the trade (below the low
  for a long);
- the market structure shift: a displacement bar (body >= half its range) closes beyond the last 3-bar swing the raid
  came from and leaves the first fair value gap after the raid;
- the trade: a resting limit at the gap's CE, the stop beyond the raid's extreme (+ the measured pierce), targets the
  Asian range's other side, then the day's draw (the previous day's high / low);
- the day's bias is REQUIRED (weekly, else daily): without it there is no Judas swing to read ('no_bias').
Detected loop-side on the final 1m candles built into 5m bars (strategies.loopside.LoopDetectors._po3), once per coin, day and direction.

```

#### 973. `_complete_grid` — function — `strategies/po3.py:30`

```text
Strictly contiguous closed bars for a session window.
```

#### 974. `displacement_bar` — function — `strategies/po3.py:38`

```text
ICT displacement confirmation: directional body must occupy at least half of the candle range.
```

#### 975. `london_window` — function — `strategies/po3.py:44`

```text
(window start, window end, Asian range start, Asian range end) in epoch ms when `ts_ms` is in 02:00-05:00 NY.
```

#### 976. `po3` — function — `strategies/po3.py:59-61`

```text
bars5: final 5m bars [open_time, o, h, l, c, ...] from the Asian range's start on.
    skip: directions already fired this window - searched past (audit A02: the first LONG kept coming back and hid a
    later SHORT of the same window).
```

#### 977. `_po3_targets` — function — `strategies/po3.py:126`

```text
PO3-owned draw selection: Asian range target, then its own draw/fillers.
```

#### 978. `Po3Strategy.entry_levels` — function — `strategies/po3.py:158`

```text
ICT PO3 contract: Judas extreme stop and Asian-range draw targets.
```

### `strategies/prizrak.py`

#### 979. `<module>` — module — `strategies/prizrak.py:1-6`

```text
Small, deterministic primitives for the Prizrak Trade structural contract.

The helpers deliberately do not place orders or choose a strategy.  They make the four observable rules explicit so
that a playbook can opt in without re-implementing wick/body, freshness, target-timeframe, or trap logic in several
modules.  Candle rows are ``[open_time, open, high, low, close, ...]`` and must be closed bars.

```

#### 980. `full_body_beyond` — function — `strategies/prizrak.py:21-25`

```text
True when the *whole* candle body closed beyond ``level`` in ``direction``.

    A wick alone is intentionally not a break.  Requiring the open and close on the same side is the probe/PP
    distinction from the course and prevents one-minute spikes from invalidating a higher-timeframe level.
    
```

#### 981. `body_break_confirmed` — function — `strategies/prizrak.py:34`

```text
Return whether the last ``confirmations`` closed bodies all broke ``level``.
```

#### 982. `body_break_since` — function — `strategies/prizrak.py:43`

```text
First close time of a confirmed full-body break after ``since_ms``; ``None`` if not confirmed.
```

#### 983. `classify_interaction` — function — `strategies/prizrak.py:54-58`

```text
Classify the latest level interaction as ``probe``, ``pp_break`` or ``none``.

    ``probe`` means a wick crossed the level but the next one or two closed bodies returned to the original side.  It is
    a valid level reaction, not an invalidation.  ``pp_break`` requires full-body acceptance for the configured count.
    
```

#### 984. `trap_detected` — function — `strategies/prizrak.py:72`

```text
A confirmed full-body break against the position, used to arm a BE exit on the retest.
```

#### 985. `target_timeframe_allowed` — function — `strategies/prizrak.py:77`

```text
A target may be on the entry timeframe or a higher one, never on an LTF.
```

#### 986. `accumulation_poc` — function — `strategies/prizrak.py:84-89`

```text
Build a POC only for a compact base with four boundary contacts and a later body exit.

    This is intentionally a pure candidate builder.  ``base_lo``/``base_hi`` come from a strategy's detected base;
    volume is distributed over price buckets exactly as the existing profile code does.  The returned ``fresh`` flag is
    true for the first post-exit touch and is meant to be persisted by the caller after a reaction.
    
```

### `strategies/profiles.py`

#### 987. `<module>` — module — `strategies/profiles.py:1-10`

```text

Optimized strategy profiles (research_optimize.py -> models/profiles.json; the research scripts were removed on
2026-10-22 and the profiles are off since eng-128 - CONFIG note): per strategy the entry FILTERS and the
POSITION MANAGEMENT that made it positive on the archive replay's untouched validation months. The live bot applies a
profile's filters to every entry of that strategy (`masks` computes them exactly as the research did) and the demo
trades only strategies with a profile.

profiles.json: {strategy: {"filters": ["1h:adx_trend", "coin:small", ...], "pm": {"target": "2", "be": true,
"trail": 3, "half": false, "hours": 24, "stop": 1.5}, "train": {...}, "validation": {...}}}

```

#### 988. `masks` — function — `strategies/profiles.py:39`

```text
The research's filter flags of one entry. `ind`: {'15m': {rule: bool}, '1h': {...}} (fetcher.indicator_panel).
```

#### 989. `failed` — function — `strategies/profiles.py:55`

```text
The profile's filters this entry does not meet ([] = it passes or the strategy has no profile).
```

#### 990. `apply_pm` — function — `strategies/profiles.py:63-65`

```text
The profile's stop and targets on an entry's levels (in place): the stop at `stop` x the plan's distance, the
    targets at `target` R (all three: the whole position), the plan's TP1 (all three), or none (no take-profit
    orders: the trail / breakeven / time stop exit). Returns the levels.
```

#### 991. `select` — function — `strategies/profiles.py:115-116`

```text
(profile, veto): the regime's profile when the strategy has regime profiles (veto 'regime_off' in a regime
    without one), else its plain profile (models/profiles.json), else (None, None).
```

#### 992. `btc_regime` — function — `strategies/profiles.py:130-131`

```text
The regime of BTC's last closed 4h candle ([ts, o, h, l, c, ...], oldest first); cached per last candle (the
    Python RMA loop ran for every confirmation: watchdog stalls in regime_labels).
```

#### 993. `regime_labels` — function — `strategies/profiles.py:144`

```text
Regime of each 4h candle of k ([open_ms, o, h, l, c]), as strategies/profiles.regime does live.
```

#### 994. `exit_overlays` — function — `strategies/profiles.py:180-181`

```text
The early-exit overlays adopted for this strategy and base ('plan' = the method's own plan, 'profile' = its
    optimized profile): e.g. ['noprog_4', 'btc_1.0'] from 'noprog_4+btc_1.0'; [] when none passed the rule.
```

#### 995. `overlay_filters` — function — `strategies/profiles.py:194-195`

```text
Entry filters adopted with the overlays (research_overlays.py) for the method's own plan: e.g. ['alts_with']
    (the median 4h return of the universe beat BTC's in the trade's direction).
```

### `strategies/pump.py`

#### 996. `<module>` — module — `strategies/pump.py:1-18`

```text

Pumps (the owner's strategy, eng-39), built from published pieces, not invented thresholds:

- PUMP START (long): momentum ignition - a range expansion out of quiet trading (Crabel's volatility breakout / the
  start of Wyckoff's markup) confirmed by participation: the last 15 minutes rose >= `pump_start_z` x the coin's own
  15m volatility and >= `pump_start_min_pct`, on >= `pump_start_rvol` x the usual volume, with open interest rising
  (new positions, not short covering) and spot taker buying (not a perp-only squeeze), price at a fresh 24h high.
  Entry at market; stop below the low of the ignition (the quiet range the move left) + the measured pierce; targets
  from the map (fillers in the move's own size).
- PUMP TOP (short): the end of a pump - Wyckoff's buying climax / VSA's upthrust after a move of >= `pump_top_min_pct`
  within 4h: a 15m candle at the high with a wick >= half its range on >= 2x the average volume (the climax), then the
  5m structure shift down; open interest falling or the CVD diverging confirms. Stop above the pump's high + the
  measured pierce; targets the pump's 0.382 / 0.5 / 0.618 retracements (the mean of the leg) and the map.
- Averaging 1:1 (the owner's rule): one more unit of the same size at half the way from the entry to the stop; the stop
  stays; R is the sum of both units in the first unit's risk (SignalBook `add_at`).
Archive note (research/pumps_by_size.md): fading pumps of 60%+ was the worst setup (-0.19R); this short waits for the
climax and the shift, it is not a fade of the rise itself. Both are journaled and judged like every strategy.

```

#### 997. `_pump_targets` — function — `strategies/pump.py:30`

```text
Pump-specific target ordering: own measured move/retrace, then map levels.
```

#### 998. `_pump_htf_zones` — function — `strategies/pump.py:48`

```text
Pump target map: retain 1h+ structure and untimed session levels.
```

#### 999. `pump_start` — function — `strategies/pump.py:61-62`

```text
minutes: final 1m candles; m: the coin's Tier-0 metrics; vol_15m: std of 15m returns; h1: the closed 1h candles
    (eng-132: the 24h high comes from them - the 1m history holds only ~10h, so every 10h-old high looked 'fresh').
```

#### 1000. `dump_start` — function — `strategies/pump.py:102-104`

```text
eng-157 (the owner: we look for the start of dumps as well as pumps): PUMP START mirrored - the last 15 minutes
    fell >= pump_start_z x the coin's 15m volatility and >= pump_start_min_pct on >= pump_start_rvol x the usual volume,
    open interest rising (new shorts, not long liquidation only) and spot taker selling, at a fresh 24h low.
```

#### 1001. `pump_top` — function — `strategies/pump.py:144`

```text
The climax 15m candle that just closed after a pump of >= pump_top_min_pct within 4h.
```

#### 1002. `dump_bounce` — function — `strategies/pump.py:173-185`

```text

    eng-55, the rule of research_pumps.py (DIP-BUY mirrored for a dump; the only pump / dump rule positive in every
    period 2021-2026: +0.14R on 156 trades Apr-Sep 2026, 900 perpetuals). On CLOSED 1h candles [ts, o, h, l, c, vol]:
    - DUMP at hour t: close >= dump_min_move below the highest high of the last 6 hours, and the hours since that high
      traded >= dump_vol_x x the average hour of the week before; one dump per 48h.
    - its low: the lowest low until the first close above the previous hour's high (exhaustion), within 24h; no
      exhaustion, no signal (audit A18).
    - the bounce, from the exhaustion hour on: price retraces to 38.2% of the dump (from the low toward the 6h high) within 24h, not beyond 61.8%,
      then a 1h close below the previous hour's low -> short at market now (the research entered at the next open).
    - stop above the bounce's high + 0.25 ATR(1h); TP1 the dump's low. dump_ext (the 1.618 extension) is journaled
      in the signal only: the plan has no TP2 of its own (audit A18; the owner decides whether it becomes one).
    Fires only when the trigger is the candle that just closed.
    
```

#### 1003. `_span_targets` — function — `strategies/pump.py:255-257`

```text
eng-163 (audit F-01): TP1 at least the risk span - the stop sits beyond the 16-minute ignition extreme plus a pad
    floored at min_stop_atr x ATR, so a TP1 at the bare measured move gave R:R < 1 by construction (every card low_rr).
    Targets nearer than the span are replaced by close +- span / 1.618 span (kept in order, duplicates allowed).
```

#### 1004. `_risk_span` — function — `strategies/pump.py:268`

```text
The stop distance the plan will get (extreme + 0.25 ATR pad, at least min_stop_atr x ATR), or the move.
```

#### 1005. `DumpBounceStrategy` — class — `strategies/pump.py:273-274`

```text
The short of the first bounce after a dump (eng-55): at market on the trigger close, stop above the bounce,
    TP1 the dump's low (research_pumps.py); the 1.618 extension (sig dump_ext) is not a target of the plan.
```

#### 1006. `DumpBounceStrategy.entry_levels` — function — `strategies/pump.py:282`

```text
Dump-bounce contract: fixed bounce stop and dump low/extension targets.
```

#### 1007. `PumpStartStrategy.entry_levels` — function — `strategies/pump.py:334`

```text
Pump ignition contract: stop below ignition and measured/map targets.
```

#### 1008. `DumpStartStrategy` — class — `strategies/pump.py:395-396`

```text
eng-157: PumpStartStrategy mirrored for the start of a dump (short at the confirmation, stop above the ignition,
    the measured move down and 1h+ zones as targets).
```

#### 1009. `DumpStartStrategy.entry_levels` — function — `strategies/pump.py:406`

```text
Dump ignition contract: stop above ignition and measured/map targets.
```

#### 1010. `PumpTopStrategy.entry_levels` — function — `strategies/pump.py:471`

```text
Buying-climax contract: stop above the pump high and retracement targets.
```

### `strategies/regime.py`

#### 1011. `<module>` — module — `strategies/regime.py:1-18`

```text

eng-104: ONE market regime per coin on the horizon of the trades (hours), replacing the eight scattered "trends"
(1h EMA20, daily EMA50 + 30/90/365-day momentum, weekly EMA, 4h ADX, ICT daily / weekly closes ...). The daily /
weekly reads lagged by weeks: 2026-10-14 BTC was 'bull' by them while it fell for a week inside an 8.6% 20-day range.

- direction of a timeframe (1h, 4h): market structure - the last two confirmed swing highs AND lows (fractal 2) both
  higher (+1) / both lower (-1) - agreeing with the EMA20 slope over 4 bars; else 0;
- the range: the high / low of the last 20 CLOSED days; `pos` = where the price sits in it (0 low .. 1 high);
- regime:
  'trend_up' / 'trend_down': 1h and 4h point the same way AND (ADX(14) of 4h >= 25 or the last 4h close is outside
  the 20-day range - the breakout already happened);
  'range': ADX(4h) < 25 and the price inside the 20-day range;
  'mixed': anything else.

Shadow use (SignalBook._enter): a trend / breakout setup in a range pointing at the range's near edge
('rg_breakout_in_range': buying the top / selling the bottom of a range), any setup against a trend
('rg_countertrend'). Journaled in `regime2` and shadow_veto, nothing is blocked until the journal shows it.

```

#### 1012. `direction` — function — `strategies/regime.py:39`

```text
+1 / -1 / 0 of closed bars [ts, o, h, l, c, ...]: swing structure confirmed by the EMA20 slope.
```

#### 1013. `state` — function — `strategies/regime.py:67`

```text
The coin's regime from CLOSED 1h / 4h / daily bars and the current price; None without the history.
```

#### 1014. `verdict` — function — `strategies/regime.py:86`

```text
The shadow veto of a setup in this regime, None when it fits (or the regime is unknown / mixed).
```

#### 1015. `label` — function — `strategies/regime.py:98`

```text
A compact journal text: 'range pos 0.40 adx 23.6 h1 -1 h4 -1'.
```

### `strategies/silver_bullet.py`

#### 1016. `<module>` — module — `strategies/silver_bullet.py:1-16`

```text

ICT's Silver Bullet: a one-hour window of the New York day (03:00-04:00, 10:00-11:00, 14:00-15:00 NY time) in which
price raids nearby liquidity, shifts structure and displaces the other way, leaving a fair value gap; the trade is
the retrace into that gap, entered at its consequent encroachment (CE, the gap's 50%), the stop beyond the raid's
extreme, the target the DRAW ON LIQUIDITY of the day (eng-58: the previous day's high / low in the trade's
direction; none ahead of the entry -> no trade). Detected loop-side on the final 1m candles built into 5m bars
(strategies.loopside.LoopDetectors._silver_bullet).

- liquidity (eng-106): the hour BEFORE the window plus the Asia (20:00-00:00 NY) and London (02:00-05:00 NY) session
  highs / lows - the nearest one beyond the window's open is the pool;
- the raid: a 5m bar inside the window trades beyond it;
- the market structure shift (eng-58, ICT): the displacement closes beyond the last 3-candle swing the raid came from;
- the displacement: a 5m bar with a body >= half its range in the other direction that leaves the FIRST FVG after
  the raid (bullish: the first bar's high < the third bar's low) inside the window;
- one setup per coin, window and direction.

```

#### 1017. `_complete_grid` — function — `strategies/silver_bullet.py:28`

```text
Require every expected closed bar in a session window; gaps are unknown, not zero volume.
```

#### 1018. `_complete_pool` — function — `strategies/silver_bullet.py:36`

```text
Session pools may use the 5m stream or the 15m long-history fallback, both with strict coverage.
```

#### 1019. `window_of` — function — `strategies/silver_bullet.py:44`

```text
The window's start (epoch ms) when `ts_ms` falls inside one, else None.
```

#### 1020. `silver_bullet` — function — `strategies/silver_bullet.py:54-56`

```text
bars5: final 5m bars [open_time, o, h, l, c, ...] covering at least the hour before the window.
    skip: directions already fired this window - searched past (audit A02: the first LONG kept coming back and hid a
    later SHORT of the same window).
```

#### 1021. `_silver_bullet_targets` — function — `strategies/silver_bullet.py:149`

```text
Silver Bullet draw ordering: daily liquidity first, then higher map levels.
```

#### 1022. `SilverBulletStrategy` — class — `strategies/silver_bullet.py:166-168`

```text
The Silver Bullet playbook of the ICT liquidity strategy: the FVG's CE (first touch, 5m; with
    executor.touch_confirm_close the entry is the close of the touching candle), stop beyond the raid's extreme +
    the measured pierce, TP1 the day's draw on liquidity (PDH / PDL) ahead of the entry, else no trade.
```

#### 1023. `SilverBulletStrategy.entry_levels` — function — `strategies/silver_bullet.py:179`

```text
ICT Silver Bullet contract: CE entry, raid-extreme stop, draw-on-liquidity targets.
```

### `strategies/structure.py`

#### 1024. `<module>` — module — `strategies/structure.py:1-11`

```text

A coin's market structure for the strategies, rebuilt after every closed 15m candle in the maps worker PROCESS
(pure Python: in threads it held the GIL and stalled the event loop):

- the level map (zones.build_raw on the 15m candles and the coin's 1h history) merged into zones;
- resting-stop pools of the higher timeframes with the time each formed: intact 1h swings, equal highs / lows,
  previous day / week, the day's extremes, the last completed sessions - minus those price traded through since;
- the coin's own 1h trend (close vs EMA and its slope) and its volatility state (last hour's ATR vs ATR14);
- the events of the candle that just closed (a sweep of a pool, a breakout accepted), detected here so the loop
  never scans 300 coins' candles.

```

#### 1025. `coin_trend` — function — `strategies/structure.py:54`

```text
+1 when the last close is above a rising EMA, -1 below a falling one, else 0.
```

#### 1026. `weekly_ref` — function — `strategies/structure.py:72-75`

```text

    (EMA(trend_w_ema) of CLOSED weekly closes, std of their weekly log returns over the same number of weeks), or None
    with fewer weeks than the EMA's period (a young listing has no weekly trend yet).
    
```

#### 1027. `trend_w_of` — function — `strategies/structure.py:92`

```text
The price's distance from the weekly EMA in weekly standard deviations (+ above, - below).
```

#### 1028. `_swings_with_ts` — function — `strategies/structure.py:100`

```text
Intact fractal swings (no later CLOSE beyond) with the time the fractal completed.
```

#### 1029. `liquidity_pools` — function — `strategies/structure.py:123-127`

```text

    Resting-stop pools as of `now_ms` from closed 1h candles plus the 15m candles of the running hour: intact 1h swings
    of the last sweep_swing_hours, equal highs / lows among them, previous day / week, the day's extremes and the last
    completed sessions; a pool price traded through after it formed is taken and dropped.
    
```

#### 1030. `pools_before` — function — `strategies/structure.py:169`

```text
The pools as they stood when the candle opening at `at_ms` started.
```

#### 1031. `merge_candles` — function — `strategies/structure.py:178`

```text
A long history (REST, refreshed hourly) with the newer closed candles on top, only bars closed by `cut_ms`.
```

#### 1032. `hours_from` — function — `strategies/structure.py:185`

```text
Closed 1h candles up to `cut_ms`; an hour REST has not published yet is built from its four 15m candles.
```

#### 1033. `bars_4h` — function — `strategies/structure.py:203-205`

```text
eng-84: complete 4h candles [ts, o, h, l, c, quote_vol, taker_buy, base_vol] built from the closed 1h candles up
    to `cut` (the 4h REST loop lags the close; the hour's own candles are already merged in `hours_from`). audit C09:
    the base volume (field 7) is summed, NaN when any hour lacks it (the reader then falls back to quote / HLC3).
```

#### 1034. `new_bar` — function — `strategies/structure.py:243-246`

```text
audit D04 / D14: True once for the bar of `period` that closed at the latest boundary <= cut, whenever its
    candle has arrived (the 4h / daily REST loops publish minutes after the boundary - gating on `cut % period == 0`
    ran the detector on the old history at the boundary and never again). A bar already handled is not re-run;
    a boundary older than the stored one (a restarted replay) resets it.
```

#### 1035. `maniac_events` — function — `strategies/structure.py:263`

```text
crypto_maniac's systems on the candle that just closed (15m), and on the hour when one closed (1h).
```

#### 1036. `smt_divergence` — function — `strategies/structure.py:338-342`

```text

    ICT's SMT divergence at a sweep: the coin took its pool (a new low since the pool formed, for SWEEP LOW) while the
    correlated market's candle of the sweep did NOT go below the correlate's own low of that window. None without a
    correlate or a window.
    
```

#### 1037. `part_candles` — function — `strategies/structure.py:404-405`

```text
A symbol's closed 15m frame (Polars) -> candles [ts, o, h, l, c, quote_vol, taker_buy, base_vol] and its latest
    ATR (base_vol NaN where the frame has none: never estimated from quote).
```

#### 1038. `pick_correlate` — function — `strategies/structure.py:419-422`

```text

    SMT needs a CLOSELY correlated pair (ICT: ES / NQ): of BTC and ETH, the one whose 15m returns correlate more with
    the coin's over the last 200 candles (BTC <-> ETH for the two themselves).
    
```

#### 1039. `build_maps` — function — `strategies/structure.py:452-458`

```text

    Worker PROCESS: level maps and contexts of many coins. A job is (symbol, the closed 15m frame (PART_COLUMNS),
    1h candles (8 days, every coin), card 1h candles (with OI), 1h OI, liquidation events, now ms, 4-day 5m candles,
    with_context, the long 15m / 1h histories (numpy, crypto_maniac's systems)) -> {symbol: (raw levels, Context or
    None)}. The frame is turned into candles here: ~300 conversions after every close held the event loop ~2s.
    `corr`: the SMT correlates' long 15m histories {'BTC': ..., 'ETH': ...} (BTC for every coin, ETH for BTC).
    
```

### `strategies/turtle.py`

#### 1040. `<module>` — module — `strategies/turtle.py:1-15`

```text

The Turtles' breakout systems as the original rules define them (Curtis Faith, "Way of the Turtle", 2007; "The
Original Turtle Trading Rules"), on DAILY candles (fetcher._daily_candles_loop), checked loop-side every final minute
(strategies.loopside.LoopDetectors._turtle_breakout):

- N = the 20-day exponential average of the true range: N = (19 x previous N + TR) / 20, seeded by the 20-day mean.
- System 1: a trade the moment price exceeds the high (low) of the previous 20 days by a tick - intraday, on the touch,
  not on a close. Skipped when the LAST System 1 breakout (either direction, traded or not) would have been a winner.
- System 2 (the fail-safe of a skipped System 1): the 55-day breakout, taken whatever the last one did.
- Stop: 2N from the entry. No profit target: System 1 exits on the 10-day low (a long) / high (a short), System 2 on
  the 20-day one (Scanner / SignalBook trail the exit, `trail_days`).
- Pyramiding (eng-34, SignalBook): +1 unit every 1/2 N from the previous unit's ACTUAL price (Faith), up to
  turtle_max_units; the stop of all units moves to 2N from the newest one. R stays the first unit's risk (2N), so a
  full pyramid stopped out loses ~2-2.5R. Not here: unit sizing (1% of equity per N).

```

#### 1041. `n_series` — function — `strategies/turtle.py:26`

```text
Turtle N per day (aligned with d1; None before 21 days).
```

#### 1042. `s1_state` — function — `strategies/turtle.py:40-51`

```text

    Replays System 1 over the daily history (one hypothetical position at a time, either direction).
    Returns (state of the most recent S1 breakout, result of the last COMPLETED one before it):
      'none'      - no S1 breakout in the history,
      'open'      - its hypothetical trade is still open (no result yet),
      'ambiguous' - its entry day also traded through the 2N stop: daily OHLC cannot tell which came first (open or
                    closed, the result is unknown),
      'win' / 'loss' - completed (a long that exited above its entry is a win).
    audit: the N of a hypothetical entry is the one known BEFORE its day (ns[i - 1]); an open trade is never marked at
    the last close. eng-137 (audit A04): the open ambiguous breakout was reported as the PREVIOUS completed result (or
    none), which let a new S1 in while its own result was unknown.
    
```

#### 1043. `s1_blocked` — function — `strategies/turtle.py:99-100`

```text
S1 is skipped after a winner and whenever the last breakout's result is unknown (unknown is no permission); an
    open unambiguous hypothetical trade has no result yet - the last completed one decides. S2 is never blocked.
```

#### 1044. `turtle_breakout` — function — `strategies/turtle.py:108-114`

```text

    The breakout the live minute made against the CLOSED daily candles `d1` ([open_time, o, h, l, c, quote_vol]):
    System 1 (20 days, unless the last S1 breakout was a winner) or System 2 (55 days). None without one.
    `before_hi` / `before_lo`: today's extremes BEFORE this minute - the Turtles enter on the touch, so a level
    already crossed earlier today is no entry now (live eng-32: started mid-day, the bot entered MOVR 26% above a
    55-day high crossed hours before).
    
```

#### 1045. `trail_level` — function — `strategies/turtle.py:157`

```text
The exit channel: the lowest low (a long) / highest high (a short) of the last `days` closed days.
```

### `strategies/vsa.py`

#### 1046. `<module>` — module — `strategies/vsa.py:1-13`

```text

Volume Spread Analysis (Tom Williams, "Master the Markets"; Wyckoff's effort vs result): every bar read by its volume,
its spread (high - low) and where it closed within the spread, against the bars before it.

For an entry the question is whether the bars since the extreme show the other side giving up:
- long:  NO SUPPLY / TEST (a down bar with a narrow spread on volume below the two bars before: nobody sells),
         STOPPING VOLUME (a down bar on >= 2x the average volume that closes in its upper half: buyers absorbed the
         selling), SPRING-like bars count as tests;
- short: NO DEMAND (an up bar, narrow spread, volume below the two before), UPTHRUST (a new high closing in its lower
         third on volume above the two before), BUYING CLIMAX (an up bar on >= 2x volume closing in its lower half).
Bars against the trade with these signs of the OTHER side (no demand at a long, stopping volume at a short) make the
reading negative. Returns the sign's name (positive), False (an opposing sign or none) - a confirmation `vsa`.

```

#### 1047. `close_location` — function — `strategies/vsa.py:20`

```text
0 = closed at the low, 1 = at the high (0.5 for a bar without range).
```

#### 1048. `signs` — function — `strategies/vsa.py:26`

```text
VSA signs of bar i (needs AVG_BARS before it). Bars: [ts, o, h, l, c, volume, ...].
```

#### 1049. `confirm` — function — `strategies/vsa.py:66`

```text
The last VSA sign since `since_ms` (bars opened at / after it): its name when it backs the trade, else False.
```

### `strategies/wyckoff_range.py`

#### 1050. `<module>` — module — `strategies/wyckoff_range.py:1-22`

```text

Wyckoff springs and upthrusts after distribution (UTAD) as Wyckoff defines them (Pruden, "The Three Skills of Top
Trading"; Weis, "Trades About to Happen"): events of an established TRADING RANGE that followed a trend's stop, on 1h.

- The range is defined by Wyckoff's phase A EVENTS, not a bar count (eng-55; StockCharts' Wyckoff tutorial, Wyckoff
  Analytics): the selling climax (SC: a wide 1h candle on climactic volume at a new 2-day low after a decline) sets
  the range low, the automatic rally (AR: the high of the rebound after it) the range high, the secondary test (ST:
  back toward the SC on LESS volume, holding above its low) completes phase A. The decline it stopped: the close 48h
  before the SC above the AR's high. Distribution mirrored (BC -> AR -> ST, UTAD). The quantification of "climactic"
  (volume >= 2x and range >= 1.5x the 20 candles before) is ours: Wyckoff describes it, he gives no number.
- SPRING (phase C): the 1h candle that just closed traded below the SC low and closed back inside, its lower wick >=
  half the candle, the pierce <= 30% of the range height, after the ST and with the range unbroken (no close beyond
  either edge since the ST). UTAD mirrored at the AR / BC high.
- The trade (Wyckoff buys the test, not the spring): a pullback toward the spring's area on less volume AND a narrower
  spread (SignalBook: pullback_volume_ok / pullback_spread_ok); the entry on the 15m structure shift there; the stop
  beyond the spring's low; targets: the range's far side, the point-and-figure count of the range (Wyckoff's cause ->
  effect: columns x box x 3 from the spring's low; box = a tenth of the range height, 3-box reversal - our box
  choice), then the map.

Replaces the 15m "BULL B / BEAR C" phase scores (a 5-hour window called a range; C was a CVD divergence at a new
high with no range at all). BULL E, the selling climax, is not bought: Wyckoff reads it as the range's start.

```

#### 1051. `_wyckoff_targets` — function — `strategies/wyckoff_range.py:33`

```text
Wyckoff-owned cause/effect target ordering: far range, P&F proxy, then map.
```

#### 1052. `_phase_a` — function — `strategies/wyckoff_range.py:55-65`

```text

    The latest SC -> AR -> ST (d = +1; BC -> AR -> ST for d = -1) before the last candle, with the range intact.
    eng-120, formulas from Wyckoff's definitions (no thresholds of ours):
    - the decline (rally) into the climax: from the last 2/2 swing high (low) that stands above (below) every price
      after it, down to the climax;
    - the selling climax (SC): the candle with the HIGHEST volume and the LOWEST low of that decline;
    - the automatic rally (AR): the highest high after the SC;
    - the secondary test (ST): the lowest low after the AR that holds above the SC's low on LESS volume than the SC;
    - the prior trend: the decline started above the AR (price came from above the range);
    searched over the whole history given (was: a week, a '2-day' low, a test within half the range - ours).
    
```

#### 1053. `pnf_count` — function — `strategies/wyckoff_range.py:118`

```text
Columns of a close-only point-and-figure chart (box size `box`, `reversal`-box reversal).
```

#### 1054. `weis_waves` — function — `strategies/wyckoff_range.py:141`

```text
Weis waves on closes: a wave runs until price closes `reversal` back from its extreme; (direction, volume).
```

#### 1055. `weis_ratio` — function — `strategies/wyckoff_range.py:159-161`

```text
Weis's effort into the spring (d = +1; the upthrust for -1): the volume of the last wave against the trade
    divided by the mean of the earlier waves against it since the climax. Below 1 = less effort into the test edge
    (supply drying up, Weis "Trades About to Happen"). Journaled (`weis_ratio`), not a filter.
```

#### 1056. `wyckoff_events` — function — `strategies/wyckoff_range.py:171-173`

```text
A spring / UTAD on the candle that just closed (h1[-1]) inside a phase-A range, else []. eng-84: run on 4h
    candles (the range of a trading range is read on 4h / daily, the 1h only times the entry - the owner's review of
    the live trades and the Wyckoff write-ups); `period_ms` / `tf` describe the candles given.
```

#### 1057. `WyckoffRangeStrategy.entry_levels` — function — `strategies/wyckoff_range.py:227`

```text
Wyckoff test contract: invalidate beyond spring/UTAD, target range effect.
```

#### 1058. `WyckoffRangeStrategy.context_veto` — function — `strategies/wyckoff_range.py:251-252`

```text
Wyckoff reads a 1h range inside the larger picture: no spring against a falling daily trend's weekly
        markdown, no UTAD against a rising one (both the daily trend and the weekly bias against the trade).
```

### `symbols.py`

#### 1059. `<module>` — module — `symbols.py:1-10`

```text

Canonical symbols across venues.

The key of every coin is its Binance USD-M futures ccxt symbol (e.g. '1000PEPE/USDT:USDT'), the same key MarketData
uses. Other venues are mapped by base coin: prefixes that scale the unit (1000PEPE, 10000..., 1M..., Hyperliquid's
kPEPE) are split into (coin, multiplier). Order-flow aggregation works in USD notional, which is invariant to the
unit (USD = price x size x contract_value; OKX sizes are contracts of ctVal coins), so multipliers only matter for
comparing prices. A mapping whose per-coin price deviates from Binance by more than venues.max_price_deviation is
dropped (two different tokens sharing a ticker).

```

#### 1060. `split_base` — function — `symbols.py:24`

```text
'1000PEPE' -> ('PEPE', 1000); '1MBABYDOGE' -> ('BABYDOGE', 1e6); Hyperliquid 'kPEPE' -> ('PEPE', 1000).
```

#### 1061. `SymbolMap.set_universe` — function — `symbols.py:66`

```text
binance_markets: canonical key -> its ccxt market (the current universe).
```

#### 1062. `SymbolMap.coverage` — function — `symbols.py:79`

```text
Venues each candidate key would be mapped to (pure: the live mapping is not touched).
```

#### 1063. `SymbolMap.add_venue` — function — `symbols.py:94-98`

```text

        Map a venue's ccxt markets onto the universe. Each market dict needs 'native', 'base' and optionally
        'contract_value' (see venues.load_venue_markets). One market per coin per venue: the one whose unit
        multiplier matches Binance's, else the plain (x1) one.
        
```

#### 1064. `SymbolMap.verify_prices` — function — `symbols.py:151-155`

```text

        Check every mapping of a venue against Binance before anything is subscribed (one bulk ticker call per venue):
        a per-coin price more than max_price_deviation away means a different token under the same ticker, and the
        mapping is dropped. Returns the dropped natives; the rest are marked verified.
        
```

#### 1065. `SymbolMap.check_price` — function — `symbols.py:170-173`

```text

        Compare the venue's per-coin price with Binance's; drop the mapping on a large deviation (two different
        tokens under one ticker). Returns True while the mapping is (still) valid.
        
```

### `task_supervisor.py`

#### 1066. `<module>` — module — `task_supervisor.py:1`

```text
Common task ownership helper for long-lived asyncio components.
```

### `tools/coinglass_heatmap.py`

#### 1067. `<module>` — module — `tools/coinglass_heatmap.py:1-11`

```text

eng-134 research tool, NOT part of the bot: CoinGlass's order-book liquidity heatmap (the site's internal endpoint
capi.coinglass.com, keyless; verified 2026-10-16). 100 points of resting book liquidity by price: interval 1d =
100 days, 1h = ~4 days. CoinGlass's official API needs a key; this endpoint is undocumented and may change or close
any day, and scraping may be against their terms - research snapshots only, never a live input. ~2.7 MB per BTC call.

    python tools/coinglass_heatmap.py ANIME BTC --interval 1h --out research/coinglass

Writes <out>/<SYMBOL>_<interval>_<YYYYmmddHHMM>.json: {"symbol", "interval", "size" (price step), "max",
"data": [[unix_s, [[price, liquidity], ...]], ...]} exactly as served.

```

### `tools/contract_audit.py`

#### 1068. `<module>` — module — `tools/contract_audit.py:1-7`

```text
Static audit of playbook contract ownership.

This is an evidence report, not a trading test.  Playbooks may still declare their structural intent in an
``entry_levels`` method, but the runtime dispatch in ``strategies.entry_levels_for`` sends every result through the
shared finalizer before it can reach the journal or executor.  The report therefore separates declaration methods from
independent risk decisions and keeps legacy fallback detection explicit.

```

### `tools/demo_reconcile.py`

#### 1069. `<module>` — module — `tools/demo_reconcile.py:2`

```text
Read-only reconciliation report for demo ledger and persisted scanner cards.
```

### `tools/farside_flows.py`

#### 1070. `<module>` — module — `tools/farside_flows.py:1-12`

```text

Daily job OUTSIDE the bot (systemd timer / cron, ~08:30 UTC): spot-ETF net flows from Farside and the NYSE calendar.

- etf_flows.json  {"YYYY-MM-DD": total net flow of all US spot BTC ETFs, USD m} - the extdata macro_loop reads it and
  shows a day D only from D+1 08:00 UTC (no look-ahead). Farside answers 403 to plain HTTP clients (Cloudflare TLS
  fingerprint); curl_cffi with a Chrome fingerprint gets the page. One request a day, the last 5 rows are re-read from
  the table every run (issuers revise the latest days).
- us_calendar.json  {"closed": [weekday holidays], "early": [13:00 ET closes]} for the next 400 days, from
  exchange_calendars (XNYS): the bot gets the NYSE session flag without importing pandas.

    python tools/farside_flows.py [--out-dir /opt/edgehunter] [--html saved_page.html]   # --html: parse a local file (no network)

```

#### 1071. `num` — function — `tools/farside_flows.py:25`

```text
Farside cells: '123.4', '(45.6)' = outflow, '-' = no data (the issuer has not reported yet), '0.0'.
```

#### 1072. `parse_flows` — function — `tools/farside_flows.py:66`

```text
{'YYYY-MM-DD': total net flow USD m} from Farside's HTML table; a day with no total yet is left out.
```

### `tools/funnel_reconciliation.py`

#### 1073. `<module>` — module — `tools/funnel_reconciliation.py:2`

```text
Build the auditable card -> execution -> closed funnel from journal/demo SQLite.
```

### `tools/memory_stress.py`

#### 1074. `<module>` — module — `tools/memory_stress.py:2`

```text
Bounded render stress check for the long-lived briefing worker.
```

### `tools/migrate_briefing_legacy.py`

#### 1075. `<module>` — module — `tools/migrate_briefing_legacy.py:1`

```text
One-time, reversible migration of pre-snapshot briefing records.
```

### `tools/ml_report.py`

#### 1076. `<module>` — module — `tools/ml_report.py:2-7`

```text
Evaluate the live ML fields without changing the trading journal.

The report is deliberately out of sample: rows are grouped by UTC day and
the thresholds are calculated from the preceding days only.  This prevents a
threshold chosen from the whole month from being presented as evidence.

```

### `tools/model_audit.py`

#### 1077. `<module>` — module — `tools/model_audit.py:2`

```text
Read-only audit of model artifacts and feature provenance; never unpickles legacy files.
```

### `tools/negative_forensics.py`

#### 1078. `<module>` — module — `tools/negative_forensics.py:2-7`

```text
Build a veto-aware negative-entry and demo-execution report.

The report deliberately keeps executable replay rows separate from shadow
benchmarks.  It is a small sqlite-only utility so it can run against the live
databases without importing the event loop or exchange client.

```

#### 1079. `in_scope` — function — `tools/negative_forensics.py:110`

```text
Apply the provenance slice without assuming either field is populated.
```

#### 1080. `stop_pierce_quantiles` — function — `tools/negative_forensics.py:132-137`

```text
Parse the stored p50/p80/p90 buffer percentages, if present.

    ``stop_pierce`` is a measured stop-buffer diagnostic (percentage of the
    stop price), not a realized post-stop excursion in ATR.  Keeping that
    distinction in the report prevents it being read as a causal price path.
    
```

### `tools/playbook_evidence_audit.py`

#### 1081. `<module>` — module — `tools/playbook_evidence_audit.py:1`

```text
Read-only evidence coverage report for the registered playbooks.
```

### `tools/reconcile_briefings.py`

#### 1082. `<module>` — module — `tools/reconcile_briefings.py:1`

```text
Fail-closed reconciliation for briefing publications and outcomes.
```

### `tools/replay_acceptance.py`

#### 1083. `<module>` — module — `tools/replay_acceptance.py:2`

```text
Cluster-weighted acceptance statistics for replay/funnel evidence.
```

#### 1084. `holm_bonferroni` — function — `tools/replay_acceptance.py:7`

```text
Return adjusted p-values in original order (step-down Holm).
```

### `tools/replay_preflight.py`

#### 1085. `<module>` — module — `tools/replay_preflight.py:2`

```text
Fail-fast check for sufficient replay history before expensive jobs.
```

### `tools/retention.py`

#### 1086. `<module>` — module — `tools/retention.py:2-8`

```text
Bound operational journal tables without making accidental destructive changes.

Default mode is read-only.  Applying retention requires both ``--apply`` and
``--backup``; the backup is created with SQLite's online backup API before the
first delete.  Deletes are batched so the writer never holds one long table
lock.

```

### `tools/runtime_sampler.py`

#### 1087. `<module>` — module — `tools/runtime_sampler.py:2`

```text
Low-overhead production sampler for the Release 1 acceptance window.
```

### `tools/strategy_audit.py`

#### 1088. `<module>` — module — `tools/strategy_audit.py:2`

```text
Export reproducible strategy/card/demo audit rows from the live SQLite databases.
```

### `tools/version_audit.py`

#### 1089. `<module>` — module — `tools/version_audit.py:1`

```text
Read-only audit for logic-version partitioning in a signals journal.
```

### `tools/version_debug_report.py`

#### 1090. `<module>` — module — `tools/version_debug_report.py:2-12`

```text
Compare logic versions and trace anomalies into later setups and outcomes.

This report deliberately keeps old versions in the comparison. ``stats.py`` uses
the active version by default for clean evaluation; this tool answers a different
question: what changed from the month of ``eng-169l`` to ``eng-169m`` and what
did each anomaly lead to afterwards?

Usage::

    python tools/version_debug_report.py --db signals.db --demo-db demo_trades.db

```

### `tools/vmmap.py`

#### 1091. `<module>` — module — `tools/vmmap.py:1-4`

```text
Committed memory of a running process by region class, read from outside (no injection, no slowdown).

    .venv\Scripts\python tools\vmmap.py <pid>      # e.g. the bot's interpreter (the larger of the two main.py)

```

### `venues.py`

#### 1092. `<module>` — module — `venues.py:1-18`

```text

Raw WebSocket clients for every venue, normalized to a few events delivered to a sink (DataFetcher):

    sink.on_trade(market, ts_ms, price, size, side, recv_ms)          side: +1 taker buy, -1 taker sell
    sink.on_liquidation(market, ts_ms, price, size, side_liq, recv_ms) side_liq: +1 long liquidated, -1 short
    sink.on_deriv(market, oi_usd=, funding_8h=, mark=, ts_ms=)          open interest (USD), 8h-equivalent funding
    sink.on_binance(market_type, stream, data, recv_ms)                 Binance's own streams (klines, depth, ...)

`market` is a symbols.VenueMarket (native id -> canonical key). Taker-side conventions differ per venue and are
handled here: Binance aggTrade m=true = taker SELL; Bybit `S` / OKX `side` / Bitget `side` = taker side;
Hyperliquid `B` = taker buy; Coinbase market_trades `side` is the MAKER side (inverted).

Transport: picows (Cython WebSocket client, frames handled in the data callback). Each VenueStream splits its
subscriptions over connections within the venue's limits, subscribes in paced batches, pings at the application
level where required, detects dead sockets with protocol pings when idle, and reconnects with backoff that only
resets once data flowed. A 'dynamic' connection supports runtime subscribe / unsubscribe
(Binance order books and Hyperliquid trades of hot symbols).

```

#### 1093. `_import_picows` — function — `venues.py:30-34`

```text

    picows imports aiofastnet, whose C code prints an OpenSSL DLL lookup error straight to stderr on some Python
    builds (it then falls back to the standard ssl module, which is what we use: use_aiofastnet=False). Silence that
    one print by pointing fd 2 at the null device during the import.
    
```

#### 1094. `ssl_context` — function — `venues.py:67-70`

```text

    One shared client SSL context: ws_connect built a new one per connection, and loading the Windows certificate
    stores (ssl.create_default_context) blocked the loop 1-1.5s at every reconnect wave.
    
```

#### 1095. `_Listener` — class — `venues.py:94-99`

```text

    picows callback: every frame is handled synchronously the moment its bytes arrive (no task switch per
    message), so a busy socket is drained at the speed data comes in. With aiohttp one message was consumed per
    event-loop iteration: the busiest Binance socket fell 5-15s behind at peaks and its pong queued behind the
    backlog, which made the heartbeat drop the connection (code 1006) every ~30s.
    
```

#### 1096. `VenueStream.subscriptions` — function — `venues.py:168`

```text
Static subscriptions for the current symbol map.
```

#### 1097. `VenueStream.update_static` — async function — `venues.py:224-227`

```text
audit-80: move the static connections to `new_subs` by diff - unsubscribe the dropped ones on the socket that
        holds them, subscribe the new ones where there is room (a new socket when none has) - instead of dropping every
        socket of the venue at each universe refresh (minutes of missing trades and a reconnect wave). False when the
        venue has no unsubscribe message (the caller restarts it).
```

#### 1098. `VenueStream.restart` — async function — `venues.py:268`

```text
Re-subscribe after the symbol map changed (universe refresh): by diff where the venue can unsubscribe.
```

#### 1099. `VenueStream._pinger` — async function — `venues.py:303`

```text
Application-level ping for venues that require it (protocol pings are handled by picows).
```

#### 1100. `VenueStream.set_dynamic` — async function — `venues.py:383`

```text
Make the dynamic connection subscribe exactly `wanted` (diffs are sent while connected).
```

#### 1101. `BinanceStream` — class — `venues.py:413`

```text
One Binance connection group: `streams` are raw stream names ('btcusdt@kline_15m', '!forceOrder@arr').
```

#### 1102. `_iso_ms` — function — `venues.py:688`

```text
'2026-09-26T11:36:31.632752Z' (up to nanoseconds) -> epoch ms.
```

#### 1103. `BybitSpotStream` — class — `venues.py:729-730`

```text
Bybit spot trades, only for the coins without a Binance spot pair (the sink decides): their spot flow and spot
    1m candles, so they join the universe with a spot market.
```

#### 1104. `venue_market_rows` — function — `venues.py:767`

```text
ccxt markets -> [{'native', 'base', 'contract_value'}] as SymbolMap.add_venue expects.
```

### `watchdog.py`

#### 1105. `<module>` — module — `watchdog.py:1-8`

```text

Event-loop watchdog: finds WHAT blocks the loop instead of only reporting that it was blocked.

A coroutine touches a heartbeat every 100ms; a daemon thread checks it. When the loop has not ticked for
`stall_sec`, the thread samples the main thread's stack (sys._current_frames) a few times during the stall and
logs the most frequent innermost frames of our code. Garbage-collection pauses are timed through gc.callbacks
(a full collection over hundreds of MB of live objects also stops the loop) and reported with the stall.

```

#### 1106. `exit_with_parent` — function — `watchdog.py:24-28`

```text

    ProcessPoolExecutor initializer: the worker ignores console Ctrl+C / Ctrl+Break and exits when the bot's process
    is gone. A bot killed without its
    shutdown (console closed, crash, Stop-Process) left its spawn workers running for days (5 orphans measured).
    
```

#### 1107. `free_ram_mb` — function — `watchdog.py:61-65`

```text

    Available physical memory (Windows). Stalls whose loop samples sit in C code (`main.py <module>`, ssl reads) with
    no busy thread are usually the machine paging the bot out (6 GB shared with Claude and Chrome; measured
    2026-09-30: ~800 MB free, 3-5k pages/s, the bot's working set trimmed to 197 of 580 MB): shown with each stall.
    
```

#### 1108. `LoopWatchdog.gc_text` — function — `watchdog.py:106`

```text
'gc g0 120x 0.4s (max 0.01), ...' since the last call, then reset.
```

#### 1109. `LoopWatchdog._sample` — function — `watchdog.py:155`

```text
The main thread's innermost own frames, and what the other busy threads are running (GIL holders).
```

### `webui.py`

#### 1110. `<module>` — module — `webui.py:1-16`

```text

Browser dashboard: an aiohttp server inside the bot, bound to localhost only.

- GET /            the page (web/index.html + app.js + style.css, no build step)
- GET /ws          full state as JSON after every scan (cards, forming / vetoed setups, anomalies, session, venues,
                   ML, market header)
- GET /api/coin    one coin: 1h / 15m / 5m candles, the level map (zones.py) or the card's plan, the order-book
                   heatmap (hot coins), journal rows of 48h
- GET /api/history finished cards / anomalies / entries of the last N hours with what price did afterwards, raw and
                   against the whole-universe mean (the journal's `universe` snapshots)
- GET /api/anomaly_stats  per anomaly label: count and the average move afterwards in its direction
- GET /api/stats   stats.py report rendered to HTML

Journal queries use their own read-only SQLite connection (WAL: readers never block the bot's writer) in a worker
thread. Nothing here is advice: the page shows mechanical rules and their measured results.

```

#### 1111. `_registry` — function — `webui.py:52`

```text
audit N33: setup -> its strategy and mode (on / shadow / off) from the code's registry, for the page's labels.
```

#### 1112. `explain` — function — `webui.py:76`

```text
Plain-language conditions behind a setup.
```

#### 1113. `context_parts` — function — `webui.py:111`

```text
Order-flow / positioning context shared by cards and tables.
```

#### 1114. `_num` — function — `webui.py:154`

```text
JSON-safe number (NaN / inf -> None).
```

#### 1115. `sizing_view` — function — `webui.py:193-200`

```text

    Sizing facts of an entry for a manual trader (CONFIG.risk): the stop distance, the highest isolated leverage whose
    liquidation stays liq_stop_margin x the stop distance away, the funding the position pays (+) or receives (-) per
    8h at the current rate, and, with an account size configured, the notional and margin for risk_pct of it.
    audit 2026-10-18 P2 #8: an ESTIMATE under stated assumptions (isolated margin, the contract's first Bybit maintenance
    tier, no account state): the costs are the geometry's own (cost_of with the coin's volume and symbol), and when no
    leverage keeps the liquidation beyond the stop under the model, max_leverage is None, not '1x is fine'.
    
```

#### 1116. `fib_view` — function — `webui.py:228-232`

```text

    The Fibonacci grid of a leg card for the chart: the impulse A -> B (with its times), the retracements 0.5 / 0.618
    / 0.705 / 0.786 (the OTE band 0.62-0.79), and after the entry the leg's extensions from A (1.0 / 1.2 / 1.272 /
    1.618), the same levels the plan targets; C (the pullback's extreme) is marked.
    
```

#### 1117. `_trail_exit` — function — `webui.py:250`

```text
The level the lifecycle exits a Turtle trade on (signal_book: the N-day low / high of closed days).
```

#### 1118. `card_view` — function — `webui.py:258`

```text
`daily`: the coin's closed daily candles, for the Turtles' N-day exit channel on the chart (coin view only).
```

#### 1119. `_demo_status` — function — `webui.py:314-316`

```text
card key (symbol|setup|entered_at) -> its newest BingX demo row: the page shows why a card in a trade has no
    position on BingX (no market, the coin held by another card, an error, closed by the exchange). Re-read every 30s
    (a ~100-row table).
```

#### 1120. `JournalReader` — class — `webui.py:388`

```text
Read-only journal access for the page (own connection, worker thread) with the universe baseline cached.
```

#### 1121. `JournalReader._universe` — function — `webui.py:403-404`

```text
The baseline from `since_ms` (minus a margin for the snapshot nearest a row's time) to now: only the
        window the page asks for, not the whole table (eng-74: the whole table was the bot's memory growth).
```

#### 1122. `WebUI.publish` — function — `webui.py:539`

```text
Called after every scan: serialize once, push to every open page (a slow page skips updates).
```

#### 1123. `WebUI._hours` — function — `webui.py:594-595`

```text
A query number within (0, cap] (eng-102: 'hours=abc' was a 500, 'days=1e9' a full-journal report on the
        public dashboard).
```

#### 1124. `WebUI._demo` — async function — `webui.py:612-613`

```text
The BingX demo trades for the page: the equity curve (closed trades in order), per-strategy totals with each
        one's daily R, and with ?symbol= that coin's trades for the chart's markers.
```

#### 1125. `WebUI._health` — async function — `webui.py:658`

```text
The last minute's Health reading as JSON; 'ok' false when it is older than 3 minutes or a venue is DOWN.
```

#### 1126. `WebUI._local` — function — `webui.py:722-723`

```text
A request from this machine itself, not through the public proxy (deploy/web_access.sh: Caddy adds
        X-Forwarded-For). The dashboard may be public; posting to Telegram and the internals are not.
```

#### 1127. `WebUI._cards_of` — function — `webui.py:727`

```text
The bot's live cards of a coin, as short rows for the analysis page.
```

#### 1128. `WebUI._analysis_of` — async function — `webui.py:736-738`

```text
Levels + a mechanical checklist of one coin (briefing.Briefing.analyze), cached 60 s. A coin outside the
        universe is analysed from REST candles only (no flows / liquidations / level map): cached, and at most
        12 such REST loads a minute (the dashboard is public).
```

#### 1129. `WebUI._pinned` — async function — `webui.py:813`

```text
The pinned coins' analysis, always (CONFIG.exchange.pinned_bases that are in the universe).
```

#### 1130. `WebUI._briefing_card` — async function — `webui.py:822`

```text
The briefing card of one coin as it would be sent now (PNG), for checking - nothing is posted (local only).
```

#### 1131. `WebUI._briefing` — async function — `webui.py:836-837`

```text
The briefing as it would be sent now (briefing.py), as text: ?send=1 also posts it to Telegram (local
        requests only: a public dashboard must not let anyone post to the owner's channel or render charts on demand).
```

#### 1132. `WebUI._debug` — async function — `webui.py:854`

```text
Internal state of one coin (verification against the exchanges' own REST numbers); local requests only.
```

### `zones.py`

#### 1133. `<module>` — module — `zones.py:1-26`

```text

Level map of one coin: where price is likely to stall or where stops / liquidations sit, from several independent
sources, merged into zones weighted by confluence. levels.py builds entry zones, stops and targets from it.

Sources (CONFIG.zones.weights):
- swing_15m / swing_1h: fractal highs and lows (a high with `width` lower highs on each side);
- equal: equal highs / lows (>= 2 swings within equal_tolerance_atr) that were not swept since: stop pools;
- pdhl: previous UTC day's / week's high and low, the current day's high / low and the last completed sessions'
  (Asia / London / New York, the exchanges' local hours in CONFIG.strategies.sweep_sessions) highs / lows: where stops rest;
- book: order-book liquidity that stayed (heatmap bands, depth.py);
- poc / va / hvn: volume profile of 5m candles over ~4 days and of 15m candles over ~24h, each candle's volume spread evenly over its
  range: point of control, value-area edges (CBOT method), high-volume nodes;
- liq_est: ESTIMATED liquidation clusters: every 1h OI increase at price P opened as many longs as shorts (each
  contract has both sides); each side is spread over leverage tiers, the aggressive (taker) side of the candle is
  assumed to use more leverage (its weight shifts towards the high tiers); a position at leverage L is liquidated around
  P * (1 -+ 1/L +- maintenance). OI decreases remove positions proportionally; clusters price already crossed are
  gone. A model (like the public liquidation heatmaps), not data;
- liq_hit: prices where liquidations were actually observed in the last 24h (a pool already swept);
- wall: persistent order-book walls (hot coins only, depth.py);
- liq_hl: REAL liquidation prices of large Hyperliquid accounts (positioning.py), summed per price bucket;
- vwap: VWAP of the current UTC day and VWAP anchored at the measured leg's start;
- fib / range: Fibonacci levels of a leg and a trading range's edges (added by the strategies' plans).

Everything is a hypothesis: the journal stores which sources each target and stop came from, and stats.py measures
how often each kind was reached.

```

#### 1134. `leverage_mix` — function — `zones.py:61`

```text
(leverage, share of notional) of real positions; the configured guess only until the first measurement.
```

#### 1135. `maintenance_of` — function — `zones.py:71`

```text
(maintenance margin rate, max leverage) of the contract's lowest risk tier; the configured rate without data.
```

#### 1136. `equal_tolerance` — function — `zones.py:80-81`

```text
Two swings are 'equal' when they differ by less than the typical pierce of an equal-high / low on this coin
    (p50, pierce.py: the measured overshoot); the ATR share only without the model.
```

#### 1137. `swings` — function — `zones.py:157-160`

```text

    Fractal swing highs / lows of [ts, o, h, l, c, ...] candles that are still intact: no later candle CLOSED beyond
    them (a broken swing is no longer where stops rest; wicks through it are sweeps and keep it alive).
    
```

#### 1138. `equal_pools` — function — `zones.py:207-209`

```text
Equal highs / lows: >= 2 swings within the tolerance, not traded through since the latest of them.
    `history` (1h candles): the sweep check of pools older than the 15m window (eng-102: a pair of 1h swings from 5 days
    ago, wicked through 3 days ago, read as an untouched EQH - the 15m candles hold ~2 days).
```

#### 1139. `round_levels` — function — `zones.py:246-250`

```text

    Round prices within `span` of `price`: multiples of a tenth of the price's order of magnitude (84,000 for BTC,
    3,100 for ETH, 0.23 for a 0.2345 coin). Stop-loss orders cluster just beyond round numbers and take-profits at
    them (Osler, NY Fed Staff Report 150): the stop pools a sweep takes, and levels price reacts to.
    
```

#### 1140. `session_windows` — function — `zones.py:259-263`

```text

    The last COMPLETED occurrence of each session before now: (name, start ms, end ms). Sessions are the exchanges'
    LOCAL hours (Tokyo 09-18, London 08-17, New York 08-17: 00-09 / 08-17 or 07-16 / 13-22 or 12-21 UTC with daylight
    saving - the forex session tables); eng-57, were fixed UTC hours that matched neither season.
    
```

#### 1141. `htf_swings` — function — `zones.py:283-285`

```text
eng-70 (the owner: "where the 15m / 1h / 4h hold no level, the daily / weekly do"): intact daily (fractal 3) and
    weekly (fractal 2) swing highs / lows, the previous calendar month's high / low and the month's open, the 52-week
    high / low (Murphy / Bulkowski: the prior period's extremes and major swings are where the large S/R sits).
```

#### 1142. `day_levels` — function — `zones.py:322-325`

```text

    Previous UTC day's and week's high / low, the current day's high / low (>= 3 candles) and the last completed
    sessions' highs / lows, from 1h candles. with_ts: also the time each level was complete [(RawLevel, formed ms)].
    
```

#### 1143. `mark_swept` — function — `zones.py:380`

```text
eng-147: flags `level` swept when any of `candles` wicked beyond it on its side.
```

#### 1144. `swept_zone` — function — `zones.py:387`

```text
eng-147: every part of `z` of one of `kinds` was swept (a zone with no such parts is not).
```

#### 1145. `volume_profile` — function — `zones.py:393-403`

```text

    Volume profile of [ts, o, h, l, c, quote_vol, ...] candles, each candle's quote volume spread evenly over its
    range (no tick data), so the candles must be short relative to the window: the 24h profile of 15m candles matched
    one built from 1m candles within one bucket, while 1h candles put a 4-day POC 3% off (the 4-day profile uses 5m).
    - POC: the bucket with the most volume;
    - value area (CBOT method): from the POC, repeatedly add the two buckets above or the two below, whichever pair
      holds more volume, until `value_area` of the volume is inside; VAH / VAL = the area's outer edges;
    - HVN: peaks of the 3-bucket smoothed profile (the highest within +-2 buckets) with >= hvn_ratio x the median;
    - LVN: valleys of it (the lowest within +-2 buckets) at <= lvn_ratio x the lower of the nodes on both sides
      (the highest on each side, each >= the median).
    
```

#### 1146. `accumulation_poc` — function — `zones.py:471-476`

```text
Return a Prizrak POC only after a four-touch base and a full-body exit from it.

    The profile arithmetic lives in ``strategies.prizrak`` so replay and live map builders share the same definition.
    This helper returns a normal ``RawLevel`` and therefore remains compatible with the existing merge/zone contract;
    callers decide whether the level is still fresh before allowing a limit entry.
    
```

#### 1147. `estimated_liquidations` — function — `zones.py:488-492`

```text

    Estimated liquidation clusters from 1h OI changes (see the module docstring). `oi_1h` is OI in COINS (contracts x
    contract size): OI in USD rises with the price alone and read every rally as new positions. Clusters are kept in
    coins; the sizes returned are USD at the last close.
    
```

#### 1148. `observed_liquidations` — function — `zones.py:551`

```text
Price buckets where >= liq_observed_min_usd was actually liquidated in the last 24h.
```

#### 1149. `vwap` — function — `zones.py:572-577`

```text
VWAP of [ts, o, h, l, c, quote_vol, taker, base_vol] candles opened at or after since_ms: sum(quote) /
    sum(base) - exact (every trade's price x quantity over the quantity; audit S01 / C02: quote-weighted typical
    prices weighted price twice). The base volume is the exchange's own (Binance's kline volume, the 8th field); a
    candle without it (None / NaN / older 7-column rows) falls back to quote / HLC3 - an approximation (one bar of
    trades at 100 and 200 reads 166.67, not 150), kept from the live branch so a coin without base volume keeps its
    VWAP level.
```

#### 1150. `imbalances` — function — `zones.py:598-611`

```text

    ICT's fair value gaps and order blocks still open on `candles` ([ts, o, h, l, c, ...]):
    - FVG (kind 'fvg'): three candles where the first's high < the third's low (bullish; mirrored bearish): the gap
      between them is the zone; the part price has not traded back through since is kept, a fully filled gap dropped;
    - order block (kind 'ob'): the last opposite candle before a displacement that broke structure - a down-close
      candle whose next three candles close above the last CONFIRMED swing high (ICT's 3-candle swing, confirmed by
      the block's candle: his break of structure is a swing, eng-57; was the highest high of the ten candles before)
      while leaving a bullish FVG (bearish mirrored); the zone runs from its body (open) to its wick (low); mitigated
      (traded back into) = dropped.
    - breaker (kind 'breaker'): an order block that FAILED - price later closed through its far side - flips: a broken
      bullish OB is resistance (ICT's breaker block), mirrored.
    Kinds carry the timeframe ('fvg_4h', 'ob_1d', 'breaker_1h'): a daily order block outweighs a 15m one
    (CONFIG.zones.weights). The `keep` nearest of each kind and side to the last close.
    
```

#### 1151. `balanced_ranges` — function — `zones.py:688-692`

```text

    ICT's balanced price range: a bearish FVG and a later bullish one (or the reverse) within 20 candles whose ranges
    overlap - price was delivered both ways through the same area, the overlap is a strong reaction zone. Kept while
    no later close went through it; the side by the later gap (a bullish one: support). Kind 'bpr_<tf>'.
    
```

#### 1152. `bars_of` — function — `zones.py:725`

```text
1h candles -> complete `hours` candles aligned to UTC multiples.
```

#### 1153. `day_poc` — function — `zones.py:740-742`

```text
[(day_ms, POC)] of each completed UTC day the 5m candles fully cover (Dalton's daily profile, volume at price:
    short candles - 1h ones put a POC percents off). The bucket = the candles' mean range x sqrt(3) (~a 15m ATR) /
    profile_buckets_per_atr, as the map's other profiles.
```

#### 1154. `naked_daily_pocs` — function — `zones.py:769-770`

```text
The completed days' POCs no candle after that day has traded through (`candles`: 1h, 8 days - a touch needs
    only the range): naked / virgin POCs (Dalton), an untested value reference. Kind 'poc' like the composites.
```

#### 1155. `build_raw` — function — `zones.py:797-800`

```text

    Card-independent levels of one coin (cached by the scanner; rebuilt on a new candle / new 1h history).
    `candles_4d`: 4 days of 5m candles for the 4-day volume profile (1h candles are too coarse for it).
    
```

#### 1156. `merge` — function — `zones.py:856-862`

```text

    Levels whose body-to-wick spans overlap - or lie closer than the typical pierce of their kind (p50, pierce.py:
    price treats them as one place) - become one zone spanning all of them (classic S/R zones: the region where
    price fought, body to wick; was: points within 0.3 ATR). Without the pierce model the old ATR tolerance applies.
    Strength = sum of source weights over distinct price events (eng-169e: one extreme in several kinds counts once, at
    its largest weight); one kind counted <= 2x.
    
```

#### 1157. `targets` — function — `zones.py:942-946`

```text

    Up to three targets beyond `entry`: TP1 / TP2 = the first zones strong enough to stall price (min_strength),
    TP3 = the next liquidity pool / liquidation cluster beyond TP2 (else the next strong zone). A target is the zone's
    near edge (price reaches it first). Returns [(price, label)].
    
```

#### 1158. `liq_only` — function — `zones.py:982`

```text
eng-150 (plan 4.6): a zone made of estimated liquidations only - confluence, never a target / anchor.
```

#### 1159. `stop_beyond` — function — `zones.py:989-995`

```text

    Stop base: the invalidation price, pushed beyond a stop pool / liquidation cluster that sits just behind it
    (within stop_pool_atr ATR), so a routine sweep of that pool does not take the stop, as long as the risk stays
    within max_stop_atr ATR. Returns (base price before the ATR buffer, label).
    eng-150 (plan 4.3): the NEAREST such pool, never one beyond the next pool (farthest=True = the old rule; eng-152: live
    again for the sweep strategy, plan['stop_farthest']).
    
```

#### 1160. `support_in` — function — `zones.py:1030`

```text
Strongest zone inside [lo, hi] (a pullback's support for longs / resistance for shorts).
```
