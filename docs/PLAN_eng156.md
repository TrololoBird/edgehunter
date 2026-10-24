# eng-156 plan (2026-10-24): open items closed by decision

The owner asked me to decide the open items myself, using live data and web sources. Rule applied: a strategy that
loses trade after trade has a bug - fix it now, do not wait for more trades and do not just switch it off.

## Decisions

| # | Item | Decision | Status |
|---|---|---|---|
| 1 | SWEEP / SILVER BULLET against the weekly / daily bias (`against_bias`) | **Block** (out of `shadow_vetoes`) | eng-156 |
| 2 | SWEEP against the coin's 1h trend (`against_trend`) | Stays shadow | no change |
| 3 | `crowd_max` (open trades per direction) | **6** (was 0 = no limit) | eng-156 |
| 4 | Event-loop stalls: uncached `resample` in `signal_book` | **Cache** per (coin, tf), copies out | eng-156 |
| 5 | Wyckoff INVALID text "back inside the range past its middle" | **Fixed**: "beyond the spring low / upthrust high" | eng-156 |
| 6 | Break-even after +1R and half at +1R (eng-155) | Keep, measure on `logic_version` eng-155+ | no change |
| 7 | Continuation: 48 MISSED, 0 entries since 23.10 | Keep the OTE zone | no change |
| 8 | "Silent" strategies | connors trades (6 live entries); pump / oi_build off on purpose; cup_handle stopped by its history gate; wyckoff's cards are invalidated correctly | no bug |
| 9 | Journal books the +1R partial at exactly +1R (open trades closed at market above it) | Keep - one-off for the trades open at eng-155; new trades take tp0 at +1R | no change |
| 10 | Auto-mode `systemctl` soft-deny | The owner's security setting - not changed by me | - |

## Why

1. **against_bias blocks.** Live (eng-148..155, live entries with `card_r`): sweeps tagged `against_bias` 6 trades,
   1 win, -5.5R (-0.92R a trade); without it 16 trades, 12 wins, +8.0R. Silver Bullet against the bias 3 trades,
   -1.8R. That is the losing streak the owner's rule names. ICT's own model is top-down: the higher-timeframe bias
   gives the direction, the lower timeframe the entry; practitioner sources agree that in a strong trend a sweep
   tends to continue rather than reverse (no independent win-rate study exists - see sources).
2. **against_trend stays shadow.** Live: 2 entries, both won (+0.8R) - nothing to fix. The archive's
   `SWEEP HIGH [against_trend]` holdout (-0.453R, system - placebo -0.287R) was on the old logic; the LOW side was not
   different from placebo. Re-check once it has 10+ live entries.
3. **crowd_max 6.** 28 trendline shorts were open at once on 24.10 (one bet on the market falling, ~28R at stake).
   The Original Turtle Rules cap units at 4 single market / 6 closely correlated / 10 loosely correlated / 12 one
   direction; alts correlate 0.8-0.9 in sell-offs (closely correlated), so 6. Open trades are not closed - only new
   entries in a full direction wait (journaled `crowded`).
4. **resample cache.** Same key design as `fetcher._RESAMPLE_CACHE` (count, first / last minute, close bucket, digest
   of the last 180 minutes). Verified: identical bars for 5 / 15 / 60m, a revised minute invalidates, returned bars are
   independent copies; 1.3 ms -> 0.1 ms a call.
5. **Wyckoff text.** `invalid` of a Wyckoff card is the spring / upthrust extreme (`wyckoff_range.plan`), the message
   was the generic range one. Text only.
6. **BE + partial.** The owner's decision (eng-155). Sources are split: MAE/MFE write-ups find a mechanical +1R
   break-even often lowers expectancy (scratches cost more than avoided losers), others favour the risk-free rest. No
   controlled study either way, so it is measured live: compare eng-155+ `card_r` / demo `r` with eng-148..154.
7. **Continuation.** Its cards miss because price reaches the 1.272 extension before a 62-79% pullback (ICT's OTE).
   A MISSED card loses nothing, and no source gives a better zone (no reach-rate statistics published for OTE).
   Changing the zone would be an invented threshold.

## Rollout

1. Tests (264) pass; cache equivalence checked on synthetic minutes.
2. Commit eng-156, push, deploy, restart.
3. After restart: no Traceback / ERROR; `Event loop blocked` count vs the 30 min before (6 stalls, avg 1.28 s);
   new sweep cards with `against_bias` journaled as vetoed; no new entry while 6+ trades are open in one direction.
4. Re-check points: against_trend at 10+ live entries; eng-155 BE / partial results after ~30 closed trades.

## Sources

- ICT top-down / sweep context: https://dailypriceaction.com/blog/liquidity-sweep-reversals/ ,
  https://de.tradingview.com/script/GoeqO1ev-Sweep-Reverse-Liquidity-Sweep-Reversal-Strategy/
- Turtle unit limits: https://elitetrader.com/et/threads/original-turtle-rules-interpretation.266360/ ,
  https://www.mql5.com/en/articles/23448
- Correlation in stress: https://blofin.com/academy/education/trading/risk-of-ruin ,
  https://k33.com/research/archive/articles/a-very-correlated-crypto-market
- Break-even / partials: https://www.luxalgo.com/library/concept/breakeven-move-rules/ ,
  https://bearbulltraders.com/wp-content/uploads/2023/05/Fundamentals-of-Profit-Taking.pdf
- OTE definition (no reach statistics): https://www.luxalgo.com/library/concept/optimal-trade-entry.md
- Own data: research/ours_placebo_6m.md:44-50; signals.db / demo_trades.db (eng-148..155)
