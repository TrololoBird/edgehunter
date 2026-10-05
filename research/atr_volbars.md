# ATR: Wilder RMA vs simple mean; volume bars vs time bars (40 coins, 2026-07-01 .. 2026-09-30)

**Summary (cloud run 2026-10-05, 40 coins, 2026-07 .. 2026-09).** 3.5: Wilder's RMA vs the simple ATR14 on 15m: median ratio 1.022, 10-90% 0.873 .. 1.212 - the spread exceeds +-10%, so by the pre-registered rule **switch to RMA and recalibrate every ATR threshold** (the 1-ATR stop floor moves by > 10% on 42% of candles). 3.7: volume bars cut the hour-of-day seasonality from max/min 1.76 (time bars) to 1.29 - **passes the rule (< 1.3 and > 1.5), barely** (1.29 vs the 1.30 cut). Both are the owner's decision; nothing changed in the bot.

Rules: the docstring of `research_atr_volbars.py` (pre-registered).

## 3.5 ATR14 on 15m candles

- RMA / SMA: median 1.022, 10-90% 0.873 .. 1.212
- candles where the 1-ATR stop floor would move by > 10%: 42%
- verdict: switch to RMA and recalibrate

## 3.7 Hour-of-day seasonality of |return|

| hour UTC | time bars 15m | volume bars |
|---:|---:|---:|
| 0 | 0.3665% | 0.5035% |
| 1 | 0.3527% | 0.4777% |
| 2 | 0.3303% | 0.4762% |
| 3 | 0.2983% | 0.4717% |
| 4 | 0.2856% | 0.4915% |
| 5 | 0.3278% | 0.5159% |
| 6 | 0.2938% | 0.4617% |
| 7 | 0.2767% | 0.4256% |
| 8 | 0.3320% | 0.4200% |
| 9 | 0.3076% | 0.4010% |
| 10 | 0.2826% | 0.4596% |
| 11 | 0.2934% | 0.4232% |
| 12 | 0.3379% | 0.4100% |
| 13 | 0.4626% | 0.4419% |
| 14 | 0.4690% | 0.4217% |
| 15 | 0.4073% | 0.4000% |
| 16 | 0.3713% | 0.4219% |
| 17 | 0.3252% | 0.4341% |
| 18 | 0.3270% | 0.4627% |
| 19 | 0.3192% | 0.4432% |
| 20 | 0.2668% | 0.4719% |
| 21 | 0.2742% | 0.4982% |
| 22 | 0.2775% | 0.4386% |
| 23 | 0.2658% | 0.4518% |

- max/min: time bars 1.76, volume bars 1.29
- verdict: volume bars remove the seasonality
