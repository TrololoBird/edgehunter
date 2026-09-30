# Audit plan (2026-10-01): mechanics, geometry, strategies, anomalies, analysis methods

Order: what can put a wrong trade on the screen first. Each item: read the code, check it against the source / the
live journal, fix, note the result here. No archive runs until the list is done.

## A. Card mechanics (signal_book.py)
- [x] A1. NOT a bug: waiting cards are re-planned after a restart (the plan is not saved); only ENTERED trades keep their levels, as a real position keeps its stop. SUI / GALA entered before the fix.
      Was: Cards restored from scanner_state.json keep levels planned by an OLDER logic (SUI / GALA were stopped on
      eng-7 1% stops after eng-12). A logic-version change must re-plan or close restored waiting cards.
- [x] A2. Trigger = close beyond the high of the 5 candles up to the zone extreme + net taker flow of the last 3 candles after it: close to ICT's MSS (break of the last swing before the extreme), not a pivot; kept. MISSED now says whether price never came back to the zone or sat in it without a trigger (eng-22).
      Was: Entry trigger (levels.ltf_trigger): the break, the flow agreement "after the extreme", the stale-trigger
      skip, the lookback; MISSED without a trigger (exhaustion / absorption missed 4 of 4 today).
- [x] A3. OK: levels at the trigger close, the journal fills at the next minute's open + slippage.
      Was: Entry price: trigger close vs the journal's fill (next minute + slippage); confirm-entries at the live price.
- [ ] A4. Invalidation (fixed at start vs re-measured), opposite-setup closing, TTLs per timeframe.

## B. Geometry (strategies/geometry.py, zones.py)
- [x] B1. FIXED (eng-23): the measured kind comes from the map zone the stop base sits on (pierce.kind_at), the label only as a fallback.
      Was: Stop: protected swing + measured pierce; `kind_of_label` guesses the level kind from a text label.
- [x] B2. FIXED (eng-23): a pool is 'just behind' when within the p90 pierce of its kind (pierce.py), no ATR maximum with the model; estimated liquidations never push.
      Was: Stop pools: which kinds push the stop (liq_est removed); the max distance of a push.
- [x] B3. OK: targets sit at the zone's near edge (before the level), filled 2 bp through; ATR steps only where the map is empty.
      Was: Targets: select_targets order, the 1-ATR minimum gap, 'ATR step' fillers, primary kinds per intent.
- [x] B4. FIXED (eng-22): the planner's cost_of uses the coin's liquidity-based slippage like the replay.
      Was: R:R: the planner uses a flat 5 bp slippage (cost_of), the replay the liquidity-based one: align.
- [~] B5. Kept for now: zone widths only bound where the trigger is searched (not stop / targets); a measured width is a separate study.
      Was: Zone widths in ATR (zone_half_atr, sweep_zone_atr, breakout_zone_atr): source / measurement.

## C. Strategies (detector -> plan -> trigger), each against its source
- [x] C1 trend: FIXED (eng-24) invalid beyond 0.786 of the leg (was the leg's start: cards waited in a reversed market) (BB close + flow + OI; pullback: map level / EMA20 with ADX)   - [x] C2 momentum (same plan) (Tier-0 impulse)
- [x] C3 wyckoff legacy A / F / D (still scored)   - [x] C4 wyckoff_range: FIXED (eng-24) Wyckoff's low-volume test applies to SPRING / UTAD (spring / UTAD)
- [x] C5 sweep: FIXED (eng-24) the deepest sweep = the pool kind's p90 pierce (was 1 ATR) (pools, depth, FVG trigger)   - [x] C6 absorption   - [x] C7 exhaustion
- [x] C8 breakout (Donchian 20)   - [x] C9 supply_demand (base, touch)   - [x] C10 auction
- [x] C11 smt   - [x] C12 trendline   - [x] C13 thirdeye   - [x] C14 fib05   - [x] C15 bomberman
- [x] C16 csi   - [x] C17 oi_accum

## D. Anomalies (Tier-0)
- [ ] D1. Rules and thresholds (RVOL, price z, OI z, cascade, one-venue, algo), hysteresis, seasonal scaling.
- [ ] D2. Whales: definition (aggressive sweeps) vs the owner's meaning; forced flow excluded (eng-20).
- [ ] D3. Labels (journal.classify): what each claims, what the journal shows.

## E. Analysis methods
- [x] E1. FIXED (eng-25): flow = every futures venue's delta over the window (was Binance's 1m candles only); spot = Binance spot + Coinbase, or Bybit spot + Coinbase for alt-spot coins. Note: Bitget / Hyperliquid / Coinbase keep 15 min in the rings.
      Was: Confirmations: windows, OI expectation per strategy, spot for alt-spot coins, orderflow availability.
- [x] E2. OK: perp-led veto conditional (crowded + OI), Elder tide on 1h, regime mutes by the journal's FDR rule.
      Was: Perp-led veto, tide filter, market crowd, regimes.
- [x] E3. OK: Edge vs the universe mean, R net of costs; the entry replay works again (the 'math' fix).
      Was: Stats: Edge baseline, clusters, R net of costs; P(edge) (shadow).

## F. Data correctness
- [x] F1. OK with a gap: an alt-spot minute closes on the next trade; no REST seed, so the first hour after a start has no Bybit spot history.
      Was: Alt-spot 1m candles (Bybit) vs Binance spot semantics.   - [x] F2. OK: seeds cover only minutes that closed before the streams started (Binance 1m, OKX 5m).
      Was: Seeds (flow, OKX) double counting.

C6-C17 reviewed again after eng-12..eng-21 (source alignment, structural exits, oi side): no new deviation found.
