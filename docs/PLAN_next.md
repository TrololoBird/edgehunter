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
17. TODO logic_version: eng-155 still, though eng-156..161 changed vetoes (against_bias blocking, crowd_max), enabled
    setups (eng-157), detection (DUMP START, small caps, median RVOL), journaling (variant_retest). Bump to eng-161;
    keep_waiting_from eng-155 (waiting cards keep their veto-at-creation).
18. TODO EH-TRADE-002: `_trail` returns inside the SAR (BB1) and trail_pct branches BEFORE the +1R partial / BE block ->
    no PARTIAL for those cards; worse, new BB1 trades get the exchange tp0 (executor.exit_parts) while the card never
    books p1r_done -> journal R and demo R disagree. Move the partial block before the trail branches (BE stays off
    where a plan has its own trail).
19. TODO EH-DOC-003: stale text - signal_book._trail docstring ("BE globally off since eng-111", "partial off since
    eng-123"), config.py partial comment "Off since eng-123".
20. TODO EH-DEPLOY-001: deploy/install.sh USER_NAME=pump while the units run User=edgehunter -> a clean install cannot
    start the service. Set edgehunter.
21. TODO EH-DEPLOY-004: deploy/README.md says polars 1.44.2, setup_server.sh says "pinned", requirements.txt has
    polars>=2.0,<3 -> write the version actually installed on the VPS into a constraints file used by the installer.

Owner decisions (not bugs): public dashboard without auth (deploy/web_access.sh, documented); root README / LICENSE.
