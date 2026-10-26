# Static audit eng-169 (2026-10-26): lookahead, levels, confirmations

No backtests were run. Each card: where, fact, evidence, status, fix / test.

## S1 - lookahead fields in training - NOT a defect
- ml.SuccessModel.features (ml.py): NUMERIC + direction-signed readings + confirms, all written at the signal. ret_4h only in
  label_of (the label). p_edge is journaled, no entry decision reads it.
- Data-mined layers (models/profiles*.json, exit_overlays.json) fitted on outcomes: off (strategies.optimized_profiles = False, eng-128).
- journal.refresh_confirm_stats uses ret_4h as the outcome of the promotion test (a label), with FDR control - not a feature.

## S2 - targets on levels measured no better than random - CONFIRMED methodology gap (not changed: owner decision)
- config.LevelsConfig.weights: swings 15m/1h, equal highs/lows, PDH/PDL, round, FVG/OB/breaker 15m/1h hold LESS often than a
  random nearby price (research/level_weights.md, odds 0.78-0.94); POC/VA/HVN/LVN = random. All weight 1.0 and SUMMED into a
  zone's strength; min_strength 2.5 makes a cluster of three such sources an obstacle / TP1.
- Higher-timeframe ICT weights 1.5-4.0, swing_1d/1w, htf, pmhl, year, liq_hl, range: hand-set, unmeasured.
- Live, last 3 days, 169 ENTRY lines: TP1 only on measured-not-better-than-random sources 11; TP1 including unmeasured hand-set
  sources 110; method / synthetic targets 48.
- Effect: a near "obstacle" that does not hold shortens TP1 and can veto entries as low_rr; the R:R shown rests on it.

## S3 - missing data read as a negative confirmation - CONFIRMED DEFECT, fixed eng-169d
- strategies/confirm.evaluate: 'flow' / 'spot' = direction x delta > 0; delta() of an empty / stalled 1m stream = 0 -> False.
  fetcher.confirmation: spot_usd = delta(Binance spot) + (Coinbase or 0) -> 0 when both are absent.
- False feeds min_confirmations, missing() of required confirmations and the journal's promotion of required confirmations.
- Fix: confirm.covered_delta (a candle in the window, the last one <= 3 min before the entry, as oi_change) -> None otherwise;
  fetcher passes None when neither Binance spot nor Coinbase covers the window. Test: tests/test_eng169d.py (2 of 4 fail before).
- Frequency in past entries: not measured.

## S4 - OI expectation vs mechanism - OPEN QUESTIONS (journaled only unless promoted)
- trendline: +1 (a "break / momentum" reading) for TL TOUCH, a rejection at the line - its mechanism is a fade.
- po3 (Judas swing reversal) has no OI expectation ('n/a') and no CVD divergence check, unlike sweep / wyckoff (REVERSALS).
- No live effect today: no required confirmations configured; promoted ones come only from a FDR-controlled journal test.

## S5 - one price event counted as several independent sources - METHODOLOGY GAP, demonstrated (not changed)
- zones.merge (zones.py): strength = sum of source weights, deduplicated only WITHIN one kind (<= 2x its weight). The docstring
  says exactly this, so the code matches its own spec: not an implementation defect, not a divergence from the documented rule.
- Different kinds built from the same candle (15m swing, 1h swing, equal lows, day low) all add: one low -> strength 4.0 >
  min_strength 2.5 (an obstacle / TP1 candidate). Live TP1 labels show it: "15m low · 1h low · EQL×2 · day low".
- RawLevel carries ts (the candle that made the level) for swings, so a per-event rule is implementable (variant C).
- Characterization test: tests/test_audit_zone_dependence.py (documents the current behaviour; must be updated on purpose if
  the rule changes).

## S6 - lookahead of the live level map (audit P0) - PASSED
- Every buffer build_raw reads holds CLOSED candles only: 15m from the closed frame (part_candles), 1h / 4h / 1d / 1w via
  fetcher._closed_only. The forming candle is added only to the page's chart (scanner `forming`), never to a plan.
- Fractals need `width` closed bars on the right (range(width, n - width)); OBs look at the three following closed
  candles; swept / mitigated / intact use the candles up to now. A level is therefore known when its last defining bar
  closed. Not checked here: research / replay scripts (their own time slicing).

## S7 - zones.merge invariants (audit P1) - PASSED, tests/test_audit_merge_invariance.py
- Input order: 20 shuffles of 60 mixed levels give identical zones (merge sorts by span first).
- Chain A-B-C: measured from the zone's FIRST level (eng-27), A-B merged, C separate.
- Width cap: a level wider than 6 ATR is its own zone and absorbs nothing.
- Added: a zone with one swept and one live pool is not swept (swept_zone is per kind set); ties of equal prices are
  deterministic; prices x 1000 with ATR x 1000 give the same zones x 1000 and the same strength; fetcher._closed_only keeps
  a candle only when the exchange's closeTime is > 3 s in the past (UTC ms, no time zone involved).
- Not applicable: re-merging merged zones (merge takes raw levels, never zones).
- Scope: these are properties shown on the tested inputs, not a proof for every input.
