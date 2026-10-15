# Pre-registered protocol: live entries vs placebo, and the shadow filters / macro features (written 2026-10-15 BEFORE the run)

Question: do the live entry classes (logic eng-132, signal logic unchanged by eng-133) beat a placebo of the same trade, and does any
shadow tag or macro feature separate winners from losers? Nothing here changes the bot; a pass is a hypothesis for the owner, not a rule.

## Data and replay
- `replay.py` (live lifecycle stepped over the Binance archive), 6 months ending the last full month, coins by the usual
  `select_coins`, as many as memory allows (>= 20); development = first 3 months, HOLDOUT = last 3 months; the rule is
  applied to both halves separately. Costs as `research/ours_placebo_6m.md` (net R, next minute's open + slippage, fees, funding).
- Run on the VPS under `systemd-run --scope -p MemoryMax=1G -p CPUWeight=20 nice -n 19` so that an out-of-memory kills the replay, never the bot.

## Placebo
Same coin, the SAME direction, the same stop / target distance (ATR units of the setup's timeframe), 100 copies per real entry at a
random time shifted by +-3 d .. 14 d, excluding +-48 h around the real trade (so the placebo never sits in the real move itself), drawn only from copies whose 4h-trend sign and ATR(14) percentile (terciles) match the real entry's; same exit rules and costs.

## Statistics
- Unit = a 4h time bucket (all entries of all coins in the bucket averaged), then a MOVING-BLOCK bootstrap with blocks of 48 h (>= the p90 trade lifetime, since neighbouring 4h buckets share one market move) - or Newey-West with lag = p90 lifetime in buckets; the stricter interval counts. >= 30 independent buckets
  per family, else "no verdict".
- Per family (setup) and per shadow tag / macro feature bucket: mean net R, mean minus placebo mean, 90% bootstrap interval.
- Multiple testing: Benjamini-Hochberg over all tested families + tag/feature buckets, FDR <= 0.05.

- Stop/target are ATR(14) multiples measured at the PLACEBO's own entry (same gross R:R), never the real trade's % distance.
- Purge: a 48 h buffer between the halves; trades opened in the first half and closed in the second are dropped.

## Descriptive extras (reported, NOT pass-rule items, nothing is tuned from them)
- Horizon profile: Real vs Placebo net R and MFE quantiles (25/50/75%, in R) at fixed horizons 4 / 8 / 12 / 24 bars of the setup's timeframe, with the stops and targets untouched.
- Structural exit, one per family, fixed now: BB W-BOTTOM / M-TOP = touch of SMA20; VA80 / AUCTION = POC.
- Counterfactual Cluster Cap (<= 2 cards of one side per 4h window, top by R:R_net): the R curve with and without. Not for production; any use needs the owner's yes.
- Measured pairwise correlation of the entries' 1h returns in the same 4h window (the N_eff = N / (1 + (N-1) rho) figure must come from our data, not from an assumed rho 0.8).
- XAU / CL features are treated as missing on Saturday, Sunday, Friday after 21:00 UTC and Sunday before 22:00 UTC (CME closed); SPY / QQQ only inside the NYSE regular session.

## Pass rule ("entries work" / "the filter or feature matters")
ALL of: mean net R > 0.05 in BOTH halves; mean R above the placebo's 90th percentile in both halves; BH-adjusted q <= 0.05 on the
holdout; the sign of the effect equal in both halves. Features additionally: the bucket difference (top vs bottom tercile of the
feature) has the same sign in both halves and q <= 0.05 on the holdout. Anything else = no evidence.

## Macro features (look-ahead rules)
- ETF net flow of day D is usable from D+1 08:00 UTC (`etf_flows.json`, history from 2024-01-11 by `tools/farside_flows.py --history`);
  a Friday value stays the last known one until Tuesday 08:00 UTC.
- VIX: the previous session's close only. Fear & Greed: the day's value from 00:00 UTC of that day.
- XAU / oil / SPY / QQQ (Binance TradFi perpetuals, klines from listing): 1h / 24h changes of CLOSED 1h candles (live: c[-2]/c[-3] and c[-2]/c[-26], the replay must do the same); CL / SPY / QQQ listed 2026-04, earlier = missing; SPY / QQQ features only when the NYSE
  regular session is open (`us_calendar.json`, XNYS); otherwise the feature is treated as missing, never as a BTC copy.
- Daily DXY: FRED DTWEXBGS (broad index, NOT ICE DXY), previous day's value.

- ETF caveat: Farside revises a day after the first print and the live bot reads the file at 07:30 / 13:30 UTC, while the archive holds the
  final value; the retro test therefore uses revised numbers (mild look-ahead); an ETF verdict needs the live journal columns to confirm it.
- Placebo matching on trend/volatility: the same coin and the same stop/target in ATR units are matched; a same-sign 4h-trend condition is
  added to the placebo draw (copies whose trend_4h sign differs from the real entry's are discarded).

## Clarifications fixed before the run (2026-10-15, no data seen)
- "Placebo's 90th percentile" = the 90th percentile of the distribution of the placebo MEAN net R over the 100 copy-sets (copy k of every real entry forms set k), per half.
- q = one-sided p of (real mean - placebo mean) from the 48 h moving-block bootstrap (the stricter of it and Newey-West), then Benjamini-Hochberg.
- Feature terciles: the bounds are computed on the development half and applied unchanged to the holdout.
- Live journal: XAU / CL are logged always; the CME-closed mask is applied at analysis time from the timestamp; SPY / QQQ by the `us_session` column.

## Implementation decisions fixed before the run (2026-10-15; script `research/scripts/research_entries_placebo_eng133.py`, seed 133)
- ATR(14) = simple mean of 14 true ranges of the closed bars of the setup's timeframe, computed from the 1m archive for the real entry and every placebo alike; the placebo candidates are the timeframe bars inside the 3..14 d window (either side, >48 h from the real trade), uniform, at most 100 without replacement (fewer = `placebo_n` < 100 is reported); the ATR/price terciles are per coin and timeframe over the replayed period; the placebo's entry price = the close of the 1m candle before its decision time, its funding = the real entry's.
- The bucket sequence for the bootstrap = the sorted non-empty 4h buckets, block = max(12, 0.9 x trade lifetime in buckets); the p-value of a family = max(one-sided block-bootstrap p, Newey-West p); tag / feature contrasts use the two-sided version of the same p.
- Horizon profile = net R and MFE with no stop and no target (mark at the horizon), 10 placebo copies per entry. Structural exit: BB W-BOTTOM / M-TOP only (SMA20 touch, original stop); VA80 / AUCTION need the POC, which the replay does not write: not computed.
- Run size: 60 coins, `--group 5`, 24 shards, then `--placebos 100 --boot 5000`. Extra macro feature: broad dollar index 1-day change (FRED DTWEXBGS).

## Reported either way
All families and features with n, means, intervals, q; the ones that fail are listed too. No threshold is tuned after seeing results.
