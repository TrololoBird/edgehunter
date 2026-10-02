# G — cross-sectional ranking (pre-registered 2026-10-02, ONE attempt)

- Universe: every coin of select_coins on its eligible days (volume floor $3M, spot pair), 2025-04-03 .. 2026-09-30.
- Rebalance every 4h (00, 04, ... UTC). Target: the coin's next-4h return minus the universe MEAN of the same 4h.
- Features known at the rebalance: returns 1h / 4h / 24h / 7d, log realized variance 24h / 7d, Amihud illiquidity
  (mean |1h return| / quote volume over 24h), log quote volume 24h vs 7d, distance to the 7d high / low, the last
  funding rate (archive fundingRate files), hour of day.
- Model: LightGBM regressor on dev (the last 60 days of dev = early stopping); baselines: 24h momentum rank and 24h
  reversal rank (no fitting).
- Portfolio: equal-weight long the top decile, short the bottom decile, held 4h; cost = (fee_round_trip + 2 x the
  coin's levels.slippage_bps) x turnover (the share of names that changed).
- WORKS only if the LightGBM long-short net return per 4h is > 0 in dev AND holdout, the holdout 90% block-bootstrap
  interval (weekly blocks) is > 0, it beats both baselines on the holdout, and the deflated Sharpe with every trial in
  research/trials.csv counted is > 0.95. Otherwise the topic is closed in research-findings.

Disclosure: before the full run, a code smoke test on the 40 most liquid coins was run end to end (it printed dev and
holdout numbers: LightGBM net -0.59% per 4h in the holdout). The rule above was not changed after it.
