# Audit 09 — Market Profile / Auction

Status: VA80 and failed-auction playbooks separated; targeted tests pass.

## Sources and formal rules

* [Dalton 80% rule summary](https://ohlcv.io/posts/peering-into-daily-bars/): open outside prior value, two consecutive 30-minute periods back inside, rotate toward the far value edge, session exit.
* [Shadow Trader explanation](https://www.shadowtrader.com/glossary/eighty-percent-rule/): same two-period acceptance rule and far-edge objective.
* [Auction-market failed-auction reference](https://www.trader-dale.com/wp-content/uploads/2018/08/VOLUME-PROFILE-The-insiders-guide-to-trading-FINAL-VERSION-3.6.2021.pdf): failed auction is a rejected probe beyond value; stop belongs beyond the probe and the rotation objective is the opposite value side.

## Code comparison

* `strategies/classic_strategies.py:11-32` implements VA80 entry, far-edge target, edge stop and session exit.
* `strategies/maniac_strategies.py:160-180` implements failed-auction re-entry, probe stop, opposite-value target and session exit.

## Confirmed violation and fix

Both classes previously used `name = 'market_profile'`, causing unrelated detector/entry/stop semantics to share mode
gates, OI/confirmation policy, pools and statistics. They now use `value_area` and `auction` respectively. Bias, regime,
confirmations, pools, statistics, and legacy `market_profile` config aliases were updated. Historical regression evidence (the test suite was later removed):
`tests/test_market_profile_method_separation.py` asserts distinct strategy objects; config alias tests preserve old files.

## Residual doubts

Crypto has no centralized session open and the bot maps sessions to UTC/profile periods. The exact TPO/value construction,
failed-auction acceptance and partial-fill behavior require the remaining execution audit.
