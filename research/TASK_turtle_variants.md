# Cloud task: Turtle variants (pre-registered 2026-10-21, approved by the owner before the run)

Base: `research/scripts/research_turtle.py` (daily archive replay, the current rules). Extend it; do not change the bot.

## Step 0 - reconcile the two baselines (before any variant)
`research/turtle.md` (60 coins, holdout 2025-10..2026-09): **-0.171R / trade**. The card replay (`research/replay.md`,
40 coins, 2025-10..2026-09): **+1.11R / card**. Same period, opposite sign. Find why (coin set, costs, S1 skip, entry
price, pyramid, R definition, exit) and report it. If the cause is a bug in either script, fix it and state which
baseline is valid. The variants run only on the reconciled baseline.

## Data and execution model
- Binance USD-M archive, top 100 coins by volume, 2023-10-01 .. 2026-09-30; development < 2025-10-01 <= holdout.
- Intraday order from **1m candles** (pyramid adds, stops, exits within a day; stop first when a minute touches both).
- Costs: fee round trip + 5 bp slippage per unit and per re-entry; funding at the archive's 8h rates.
- R = risk of ONE unit (2N at entry). N = Wilder 20-day, fixed at entry.

## Variants (vs the base = current rules: 1/2 N adds from the previous fill, up to 4, all stops 2N from the newest)
- **A** one unit, no adds.
- **B** at most one add per closed 4h candle: after a 4h close, if price >= last fill + 1/2 N, add exactly ONE unit at
  the price then; the next step is measured from that fill; never several units at once.
- **C** Whipsaw (Faith 2003): stop 1/2 N per unit, stops of earlier units never moved, a stopped unit re-enters when
  price reaches its original entry again; at most 2 re-entries per unit; costs on every re-entry.
- **D(K)**, K = 3 and 6: at most K open Turtle positions per direction; `turtle_max_direction_units` = 4K. Signals are
  collected per **1h window**, ranked at the window's close by Strength20 = d * (P - Close_{t-20d}) / N, the top ones
  taken until K is full (entry at the window close price - no look-ahead). Also report D(K) with arrival order (first
  come) to separate the cap from the ranking.
- **D2(K)** = D(K) plus at most 2 open positions per sector (`sectors.py`, CoinGecko; Faith's limit for closely
  correlated markets). Ranking as D.
- **E** trend filter (Faith 2007): longs only when EMA25 > EMA350 of daily closes, shorts only when below. The archive
  is loaded from 2022-09 for the warm-up; a coin with < 350 days of history has no E reading and is reported apart
  (n, mean R) - not silently dropped. Not replaced by SMA200: that would test another rule.
- **F1** exit = the tighter of the 10-day (S2: 20-day) channel and peak - 3N (peak = the best price since the first
  unit, closed 1h candles).
- **F2** once price reached +2N from the first unit, all stops to the first unit's entry (0R) - only when the 1h
  candle that reached it has taker-buy share < 0.48 (the kline's taker_buy_quote / quote_volume). F2b: the same
  without the taker condition, to separate the two.
- **G** no pyramid add on a spike: an add is skipped when, over the 15 minutes before it, Binance OI (archive
  `metrics`, 5m sum_open_interest) did not rise AND the spot taker delta (spot 1m klines) is <= 0. Coins without a
  spot pair: the add stays allowed (reported apart).
- **H** listing age: no entry when the perpetual is < 60 days old (onboardDate).

## Pass rule (fixed before the run)
- A, B, C (same cards as the base): paired per-card difference dR = R_var - R_base. PASS if mean dR > 0 in BOTH halves
  (development and holdout) AND the 90% interval of mean dR, block bootstrap by 4h clusters of entry time, is > 0.
- D, E (cards removed): the unit is the **4h cluster**: sum of R per cluster, var minus base, same both-halves + 90%
  interval rule. Reported, not part of the rule: mean R per card, portfolio max drawdown in R, the worst cluster.
- 13 variants are tested: report each one's interval also at 1 - 0.10/13 (Bonferroni) beside the 90% one; a pass
  that holds only at 90% is marked 'weak'.
- Diagnostics (no rule): MFE / MAE in N and R of every base card, how many reached +1R / +2N, and how much of the
  peak each card gave back.
- Several variants passing: the one with the larger holdout lower bound. Nothing passing = the base stays.
- A PASS is a proposal only; the owner decides on the bot change (the Turtles' rules are not changed otherwise).

## Not testable on the archive (live journal only, no conclusion here)
Liquidation flow, RushBook, book_eaten, icebergs, walls, footprint (no history), the Monitoring tag (no dated
history of the tag). These stay in the live journal; a slice of the live Turtle cards by these readings is
descriptive (n is ~25) and never a pass.

## Report
`research/turtle_variants.md`: step 0 finding, a table per variant (n, mean R dev / holdout, dR with interval, PASS /
FAIL), the 10 worst clusters of the base and what each variant did on them. Keep the scripts in `research/scripts/`.
