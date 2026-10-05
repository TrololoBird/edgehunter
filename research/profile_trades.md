# OHLC volume profile vs the trades' profile (12 coins x 10 days)

**Summary (cloud run 2026-10-05, 12 coins x 10 days, aggTrades reference).** Median POC error of the 15m and 5m OHLC profiles is exactly 1.0 bucket (1/4 ATR), 1m 1.0 too (VAH / VAL 0 on 1m) - the rule needs > 1 bucket for 15m / 5m: **the live profile STAYS** on its candles. Tails differ: p90 POC error 9 buckets on 15m, 6.1 on 5m, 4 on 1m.

Rules: the docstring of `research_profile_trades.py`. Bucket = 1/4.0 ATR(15m).

| candles | level | days | median error (ATR) | median (buckets) | p90 (buckets) |
|---|---|---:|---:|---:|---:|
| 1m | poc | 120 | 0.250 | 1.0 | 4.0 |
| 1m | vah | 120 | 0.000 | 0.0 | 2.0 |
| 1m | val | 120 | 0.000 | 0.0 | 2.0 |
| 5m | poc | 120 | 0.250 | 1.0 | 6.1 |
| 5m | vah | 120 | 0.250 | 1.0 | 4.0 |
| 5m | val | 120 | 0.250 | 1.0 | 4.0 |
| 15m | poc | 120 | 0.250 | 1.0 | 9.0 |
| 15m | vah | 120 | 0.250 | 1.0 | 4.1 |
| 15m | val | 120 | 0.250 | 1.0 | 4.0 |
