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
random time shifted by +-12 h .. 7 days; same exit rules and costs.

## Statistics
- Unit = a 4h time bucket (all entries of all coins in the bucket averaged), then block bootstrap over days. >= 30 independent buckets
  per family, else "no verdict".
- Per family (setup) and per shadow tag / macro feature bucket: mean net R, mean minus placebo mean, 90% bootstrap interval.
- Multiple testing: Benjamini-Hochberg over all tested families + tag/feature buckets, FDR <= 0.05.

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

## Reported either way
All families and features with n, means, intervals, q; the ones that fail are listed too. No threshold is tuned after seeing results.
