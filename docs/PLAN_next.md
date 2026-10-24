# Fix / change plan after eng-160b (2026-10-24 20:35 UTC)

Status legend: CHECKED = verified against code / live data today; TODO = to do; INVESTIGATE = cause unknown yet.

## Verified today - no action
- External report #4 (strategies that did not trade): all 5 proposed fixes rejected - files do not exist, SWEEP LOW's
  market_down is a shadow veto (signal_book.py:2073), tp1_passed drops a card whose TP1 is already behind the price
  (signal_book.py:1045), OTA's profit zone needs the opposing zone, OTE entry after TP1 = chasing.
- TL TOUCH DOWN 7 losses in a row (16:00-20:01): one correlated short bet (4 entries at 17:00), BTC -1.2% to 16:00 then
  +0.9%; not a construction bug. crowd_max 6 (eng-156) caps such clusters now.
- Memory 836 -> 1590 MB after a restart = warm-up (steady state before eng-158 was 1.8-2.0 GB); small-cap attach +266 MB.
- mfe_r / mae_r empty on fresh entries = filled at the 4h horizon (journal.py ~1319), not a bug.

## Priority 1 - correctness / data
1. DONE eng-161 (diag + REST refill): `1m gaps dropped` grows ~45 / hour (RESAMPLE_QUALITY): 1m buckets with missing minutes are dropped ->
   holes in 5m / 15m bars used by triggers, pd_features, variant_retest. Find which coins / streams lose minutes
   (log the symbol on a drop), patch from REST if needed.
2. DONE eng-161: small caps re-attach in ~10 min after every restart (wide watch sleeps 600 s and rescans 120 coins): attach
   the last known list at start-up (persist it), seed rings at once.
3. DONE eng-161: small caps: the "no setup" log does not say WHICH condition failed (e.g. TA -4.5%, RVOL 38 -> no setup) - log
   the failing gate (move / rvol / oi / flow / 24h extreme).

## Priority 2 - strategy logic to check in code
4. INVESTIGATE SD SUPPLY: 360 setups, 0 live, 166 'no opposing supply / demand zone'. The rule is source-consistent, but
   check `maniac.sd_opposing`: are opposing zones found (fresh 4h zones only? within what distance? tested zones
   excluded?) - 0 of 360 suggests the search is too narrow.
5. INVESTIGATE Silver Bullet tp1_passed 53 of 241: why TP1 (PDH / PDL) is already behind price when the setup fires -
   late emission, or TP1 picked as a liquidity the displacement already took.
6. INVESTIGATE BB M-TOP low_rr 89 of 120: target selection vs Bollinger's own exit (band_exit vs map targets).
7. INVESTIGATE Turtles unit_limit 40: confirm units are counted only on open, non-finished cards (restored cards?).
8. TODO event_risk blocks PUMP START longs (19 since 17.10) on Binance-monitored coins - those are the coins that pump;
   owner's rule is data first -> make event_risk a SHADOW veto for PUMP START only (journaled, measured).
9. WATCH PUMP / DUMP START geometry: R:R ~1 by construction + min_rr 1.0 -> expect many low_rr expiries; decide after
   the first live signals (journal low_rr share, variant_retest results).

## Priority 3 - measurement points (no code)
10. eng-153: MISSED of SWEEP (was 109/113 'no 60m trigger') - compare after 24h.
11. eng-154: ORB break-even on the first trade that reaches +1R.
12. eng-155: BE + partial results vs eng-148..154 after ~30 closed trades.
13. eng-156: against_bias blocks (sweep / SB) - count and outcome of what it blocked (shadow copies not kept - note).
14. eng-157..160: first PUMP / DUMP START, pd_phase distribution, variant_retest vs live entry.

## Backlog
15. Exact rush-order count from raw @trade (paper's same-ms grouping) for the universe - extra stream per coin, memory
    cost; only if the proxy shows value.
16. Continuation OTE (0 entries): kept by decision (no source for another zone); revisit with live MISSED data.

## External audits batch 2026-10-24 21:00 (4 reports) - verified

Rejected (checked against the tree):
- "deep-research-report" (generic): Polymarket - 0 matches in the repo; "no tests / no CI" - tests/ has 23 files,
  .github/workflows/ci.yml exists; file names (main/strategy/data_pipeline/execution.py roles) invented.
- "2-deep-research-report": the same report already rejected (sweep.py / trendline.py / open_range.py do not exist).
- "deep-research-report (1)" (literature Q&A): no code action; agrees with the shadow-first policy (no evidence for
  funding as a contrarian signal, round numbers, OB / FVG fill rates, ICT OTE).

Confirmed (EDGEHUNTER_AUDIT_PRELIMINARY) -> to implement:
17. DONE eng-162: logic_version: eng-155 still, though eng-156..161 changed vetoes (against_bias blocking, crowd_max), enabled
    setups (eng-157), detection (DUMP START, small caps, median RVOL), journaling (variant_retest). Bump to eng-161;
    keep_waiting_from eng-155 (waiting cards keep their veto-at-creation).
18. DONE eng-162: EH-TRADE-002: `_trail` returns inside the SAR (BB1) and trail_pct branches BEFORE the +1R partial / BE block ->
    no PARTIAL for those cards; worse, new BB1 trades get the exchange tp0 (executor.exit_parts) while the card never
    books p1r_done -> journal R and demo R disagree. Move the partial block before the trail branches (BE stays off
    where a plan has its own trail).
19. DONE eng-162: EH-DOC-003: stale text - signal_book._trail docstring ("BE globally off since eng-111", "partial off since
    eng-123"), config.py partial comment "Off since eng-123".
20. DONE eng-162: EH-DEPLOY-001: deploy/install.sh USER_NAME=pump while the units run User=edgehunter -> a clean install cannot
    start the service. Set edgehunter.
21. DONE eng-162: EH-DEPLOY-004: deploy/README.md says polars 1.44.2, setup_server.sh says "pinned", requirements.txt has
    polars>=2.0,<3 -> write the version actually installed on the VPS into a constraints file used by the installer.

Owner decisions (not bugs): public dashboard without auth (deploy/web_access.sh, documented); root README / LICENSE.

## External audit "Independent Quantitative Microstructure..." (F-01..F-14) - verified 2026-10-24 21:20

Confirmed -> to implement:
22. DONE eng-163: F-01 PUMP / DUMP START R:R < 1 by construction (TP1 = measured move, stop = 16-min extreme + pad >= 1 ATR): our own
    offline check gave rr_tp1 0.94 -> low_rr expiry. Fix: TP1 at least the risk span (close +- max(move, |close - stop|)).
23. DONE eng-163: F-02 5m features lag 1-4 min on signals that fire mid-5m-bucket (the last COMPLETE 5m bar is the pre-ignition one):
    add a rolling bar of the last 5 closed 1m candles as the evaluated bar.
24. DONE eng-163: F-03 DUMP START requires OI 5m > 0 - a long-liquidation cascade cuts OI, so the main dump mechanism is rejected and
    only late short builds pass. Fix: drop the hard OI gate for dumps, journal pd_dump_oi_regime (long_flush / short_build).
25. DONE eng-163: F-06 (part) BTC 5m cache lives 300 s from fetch, not per 5m bucket -> the latest bar is missing and pd_vs_btc_resid is
    None; invalidate on the 5m boundary. (Alignment itself is by openTime already - that part of F-06 is wrong.)
26. DONE eng-163: F-08 (part) variant_retest journals a retest after TP1 was already hit -> cancel when TP1 trades before the zone touch.
    (A retest below the plan stop is already skipped, not corrupted - that part is wrong.)
27. DONE eng-163: F-09 small-cap ACTIVATION base = 24h mean (detection uses median) - known; use the median of the 1m ring.
28. DONE eng-163: F-12 event_risk on PUMP START -> shadow (same as item 8).
29. DONE eng-163: F-13 RushBook: use aggTrade ids (l - f + 1) so single-level multi-maker sweeps count; new journal column.
30. DONE eng-163: smallcap._check repeats REST every minute while |move15| >= 3% when no setup fires -> per-coin cooldown 5 min.
Rejected: F-04 memory (steady state was 1.8-2.0 GB before small caps; seeding goes through the REST limiter),
F-05 restop leaves position naked (on_restop places the new stop BEFORE cancelling the old, executor.py ~1135),
F-07 sign errors (features use direction: pd_late, spike_fail, green, breakout, EMA, ma12h are signed; only the raw
pd_move3/6 columns are unsigned by design), F-10 (24h extreme uses h1 + minutes before the last 15 min, not 15m REST),
F-11 (fixed in eng-161). Optional later: VPIN / impact ratio / BOCD features, PUMP TOP OI shadow veto (F-14).

## External audit "Independent Quantitative Audit ... (48h strategies)" - verified 2026-10-24 21:40

Note: my brief to this auditor mislabelled the 16 market_down entry vetoes as TL TOUCH DOWN - the journal shows they are
TL TOUCH UP (longs). _market_down returns False for every short (signal_book.py: `if s.direction <= 0`).

Confirmed / source-backed -> to implement:
31. DONE eng-164: ORB: Crabel's own exit rule - "stops should be moved to break even within one hour after entry" (Day Trading with
    Short Term Price Patterns, 1990): after 60 min in profit -> stop to break-even + costs (in addition to eng-154's +1R).
32. DONE eng-164: SD: when no opposing zone exists, use Seiden's "initial profit margin" (the departure leg's extreme before price
    returned to the zone) as the target instead of vetoing (the opposing zone stays the target when it exists).
33. NOT DONE (see HISTORY eng-164): Silver Bullet tp1_passed (47 short, 6 long in 48h): when PDL / PDH is already behind price at the setup, the draw on
    liquidity advances to the next untaken pool (PWL / PWH, multi-day swing) - extends item 5.
34. DONE eng-164: Cascade (FLUSH / SQUEEZE): no_prior_trend is a hard plan skip (188 / 48h) - make it a shadow tag per the shadow-first
    rule (no_room stays: it means no zone wide enough for the R:R, i.e. no plan).
35. BB M-TOP / W-BOTTOM targets vs Bollinger's opposite band - check with item 6.

Rejected (checked in code):
- market_down vetoing shorts: impossible (see note); unit_limit "counts other strategies": it sums `units` of open cards,
  which only unit systems (the Turtles) carry; 6 = Faith's closely-correlated cap, chosen on purpose for alts (eng-51/156).
- CCXT 499-bar fetchOHLCV starving history: the bot uses raw /fapi/v1/klines with explicit limits (daily 1400); coins
  failing connors (202 daily) / breakout (60 daily) gates are young listings.
- reclaim_entry "blocking gate": it is an alternative shadow ENTRY journaled beside the card, not a confirmation gate.
- Continuation re-anchor: the plan already follows a continuing impulse until the entry (signal_book _advance).
- Wyckoff "60-minute TTL": invented - SPRING / UTAD cards end structurally (structural_lifetimes); "60m" is the trigger tf.
- XAU / XAG / BZ in ORB: the intended ORB universe (eng-93: majors, gold, silver, oil).
- Connors shorts live / OI BUILD cancelling live cards: shorts stay shadow (book trades longs); 0 OI BUILD cancellations
  since the restart (81 OI BUILD cards) - recheck after 24h.

## Review notes 2026-10-24 22:00
36. CHECKED Turtle rules vs Faith (strategies/turtle.py: N = 20-day EMA of TR, S1 20-day skipped after a winner, S2 55-day,
    2N stop, 10 / 20-day exits, +1 unit per 0.5N, 4 units / coin) - match; unit counting extracted
    (SignalBook._direction_units) and tested (tests/test_eng164.py) with the ORB one-hour break-even and the small-cap
    failing-gate log.
37. INVESTIGATE small-cap flow window: APR +17.9% in 15m on RVOL 83 and OI +2% was rejected 'taker flow against the move' -
    the flow is the last 5 minutes only (selling after the spike). Compare with the flow over the 15-minute move.
