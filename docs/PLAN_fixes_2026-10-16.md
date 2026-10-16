# Plan of changes after the 24h trade review (2026-10-16)

Source: review of the 24h of BingX demo trades (15.10 00:22 .. 16.10 00:22 UTC), the journal and scanner.log.
Each item: what was seen (verified / hypothesis), the change, who decides. Nothing here is implemented yet.

## Stage 1 - executor and labels (no signal logic; owner's yes, one restart)
1. **Non-crypto contracts.** BingX rejects XAU / XAG / CL with 101414 (one-way mode, verified 3x in 24h). Change:
   the executor skips symbols with a non-crypto underlying, journaled as NO_MARKET 'non-crypto on BingX'.
2. **Reconcile false flat.** 15.10 10:04 HYPE / UNI / XPL were marked EXCHANGE without exit fills, still open on
   BingX, then closed at market as UNTRACKED at 10:05 (verified in the log; cause hypothesis: a stale empty
   position read). Change: reconcile marks EXCHANGE only after 3 flat reads (as `_close` does since eng-132) AND
   no exit fill found -> otherwise keep tracked; UNTRACKED never duplicates a row the same minute.
3. **Exit price of MARSCOIN BB W-BOTTOM** (id 85): exit_avg 0.07906 never traded (market 0.0707-0.0758 at the stop).
   Needs the BingX fills (fetch_my_trades): the owner runs the read-only command (credentials are not readable from
   this session). Fix `_exit_fills` / `_finalize` only if the fills show the cause.
4. **Slippage columns.** Journal R vs demo R differ by up to 0.58R (ETH). Add `entry_slip_bp`, `exit_slip_bp` to
   demo_trades (fill vs plan / exit_ref) and a line in /trades.

Checked, no change needed: the 2.5-2.8% "BingX price" refusals (ETH, JTO) were the VST demo quote lagging Binance
(Binance 2359 = plan, VST 2424): the 2% guard worked. Turtle UNI / XPL risk $190-203 = 2 units (pyramid). PHA without
an exchange stop = Connors by design. depth_imb empty for 83% = books only for hot coins. Event-loop stalls after
eng-133: same rate as before, old code paths (flow.stats, ind_panel, profiles getmtime, ssl).

## Stage 2 - data and process (owner's yes for the process rule)
5. Logic version cadence: at most one signal-logic change a week (8 versions in 4 days left 41 finished cards).
6. `docs/DATA_COVERAGE.md`: null share of each journal column per version / kind, which features are usable.
7. Check p_edge (93% null), hl_net_usd (36%), cb_premium (32%), okx_book_imb (59%): by design or a feed gap.

## Stage 3 - signal logic: research first, pass rule agreed before the run, then the owner's yes
8. **Silver Bullet target.** TP1 5-14R with ~1.5-3% stops; 3 demo trades, 0 targets reached (time / stop exits).
   Test on the archive: draw on liquidity capped at N daily ATR vs as is.
9. **Correlated entries.** 3 ORB DOWN within 20 min, 2 SB in the same minute = 2 bets. The cluster-cap counterfactual
   is already in the eng-133 cloud study: decide after its report.
10. **Entries against the method's own rules.** Shadow filters (eng-101) let entries through that the method's source
    forbids (AIOT SB: no bias, not in a pool, conf_n 0; G / ONE SB: against daily / weekly / 4h). Report per strategy:
    source rule / code check / shadow only, with card_r of shadowed vs clean on the journal + the eng-133 archive
    tags. Bollinger W / M has no trend check at all (MARSCOIN long with 4h / 1d trend -1).
    Live journal now: 41 cards (clean -0.25R n=23, shadowed +0.21R n=18) - too few for any decision.
11. SOPH pump short: rr_tp1 0.33 allowed (min_rr 0 by the research rule) - keep, list in the report.

## Monitoring
12. 16.10 07:30 UTC first Farside timer run, etf_flow_* in the journal after 08:00.
13. The eng-133 cloud study report.
