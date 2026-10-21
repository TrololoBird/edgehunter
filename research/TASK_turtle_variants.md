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
- **E** trend filter (Faith 2007): longs only when EMA25 > EMA350 of daily closes, shorts only when below.

## Pass rule (fixed before the run)
- A, B, C (same cards as the base): paired per-card difference dR = R_var - R_base. PASS if mean dR > 0 in BOTH halves
  (development and holdout) AND the 90% interval of mean dR, block bootstrap by 4h clusters of entry time, is > 0.
- D, E (cards removed): the unit is the **4h cluster**: sum of R per cluster, var minus base, same both-halves + 90%
  interval rule. Reported, not part of the rule: mean R per card, portfolio max drawdown in R, the worst cluster.
- Several variants passing: the one with the larger holdout lower bound. Nothing passing = the base stays.
- A PASS is a proposal only; the owner decides on the bot change (the Turtles' rules are not changed otherwise).

## Report
`research/turtle_variants.md`: step 0 finding, a table per variant (n, mean R dev / holdout, dR with interval, PASS /
FAIL), the 10 worst clusters of the base and what each variant did on them. Keep the scripts in `research/scripts/`.
