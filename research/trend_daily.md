# Candidate replacement strategies on daily candles (478 coins with a spot pair, 2023-10-13 .. 2026-09-27)

Per-trade returns net of 0.20% per position change (taker fee + slippage); funding NOT included (a week's long at +0.01% / 8h pays ~0.21%). 'vs mean' = minus the equal-weight universe mean over the same days (market-neutral view). [90%] = bootstrap over weeks. Universe per day: $10M average volume over the 30 days before, delisted coins included.

| strategy | half | weeks | trades | mean net per trade [90%] | vs universe mean [90%] | long share |
|---|---|---:|---:|---|---|---:|
| TSMOM 28d, hold 7d | older | 73 | 14981 | +1.27% [-0.33..+2.97] | -0.19% [-0.37..-0.01] | 44% |
| TSMOM 28d, hold 7d | newer | 77 | 12771 | -0.05% [-1.29..+1.18] | -0.22% [-0.47..+0.05] | 44% |
| XSMOM top/bottom 10%, hold 7d | older | 73 | 3053 | +0.00% [-0.58..+0.65] | +0.00% [-0.58..+0.65] | 50% |
| XSMOM top/bottom 10%, hold 7d | newer | 77 | 2624 | -0.42% [-1.19..+0.34] | -0.42% [-1.19..+0.34] | 50% |
| TREND EMA20/50, daily | older | 73 | 67301 | +0.19% [-0.07..+0.45] | +0.01% [-0.02..+0.05] | 39% |
| TREND EMA20/50, daily | newer | 78 | 37440 | -0.07% [-0.25..+0.11] | -0.07% [-0.11..-0.02] | 39% |

TREND is measured per coin-day of holding (the next day's return, costs only on position changes): its 'per trade' is per day held, not comparable in size to the 7-day holds above.
