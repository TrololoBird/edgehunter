# Candidate replacement strategies on daily candles (478 coins with a spot pair, 2023-10-18 .. 2026-10-02)

Per-trade returns net of 0.20% per position change (taker fee + slippage); funding NOT included (a week's long at +0.01% / 8h pays ~0.21%). 'vs mean' = minus the equal-weight universe mean over the same days (market-neutral view). [90%] = bootstrap over weeks. Universe per day: $10M average volume over the 30 days before, delisted coins included.

| strategy | half | weeks | trades | mean net per trade [90%] | vs universe mean [90%] | long share |
|---|---|---:|---:|---|---|---:|
| TSMOM 28d, hold 7d | older | 73 | 15029 | +1.10% [-0.62..+2.79] | -0.20% [-0.38..-0.02] | 44% |
| TSMOM 28d, hold 7d | newer | 76 | 12575 | +0.14% [-1.08..+1.35] | -0.22% [-0.49..+0.05] | 44% |
| XSMOM top/bottom 10%, hold 7d | older | 73 | 3063 | +0.00% [-0.59..+0.62] | +0.00% [-0.59..+0.62] | 50% |
| XSMOM top/bottom 10%, hold 7d | newer | 76 | 2584 | -0.38% [-1.17..+0.38] | -0.38% [-1.17..+0.38] | 50% |
| TREND EMA20/50, daily | older | 74 | 67929 | +0.22% [-0.03..+0.48] | +0.02% [-0.02..+0.06] | 39% |
| TREND EMA20/50, daily | newer | 77 | 37204 | -0.11% [-0.28..+0.07] | -0.07% [-0.12..-0.03] | 39% |

TREND is measured per coin-day of holding (the next day's return, costs only on position changes): its 'per trade' is per day held, not comparable in size to the 7-day holds above.
