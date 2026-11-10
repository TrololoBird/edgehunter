# Audit 13 — Cascade / Squeeze Reversal

Status: cascade playbook separated from Wyckoff and audited as a shadow/research method.

## Sources and formal rules

* [CME open-interest context](https://www.cmegroup.com/education/lessons/open-interest): liquidation/open-interest data is context about participation, not a complete reversal rule.
* [Cascade code's cited research context](https://arxiv.org/abs/2203.10813): crypto intraday reversals after large shocks are an empirical phenomenon, not a canonical discretionary entry system.
* Wyckoff secondary-test principle is documented in [StockCharts](https://chartschool.stockcharts.com/table-of-contents/market-analysis/wyckoff-analysis-articles/the-wyckoff-method-a-tutorial): a climax itself is not the confirmed entry; a later lower-volume test confirms supply/demand.

## Code comparison

`strategies/cascade.py:63-109` requires a price anomaly plus dominant forced liquidation, measures a >= configured ATR
leg and records climax-volume context. `:124-162` creates a 15m leg, a 5m trigger zone and retracement/mean targets.
The cascade setup is configured shadow/research-only and does not claim a canonical source-defined rule set.

## Confirmed architecture violation and fix

`ExhaustionStrategy` previously used `name = 'wyckoff'`, merging liquidation-cascade reversals with Wyckoff SPRING/UTAD
cards and their bias/regime/confirmation/statistics gates. It now uses `name = 'cascade'`; config, bias, reversal flow,
journal/statistics and legacy Wyckoff config expansion were updated. Historical regression evidence (the test suite was later removed):
`tests/test_cascade_method_separation.py` asserts separate strategy objects.

## Residual doubts

No authoritative source specifies the project's anomaly, liquidation dominance, ATR, or target thresholds. The method
must remain explicitly shadow/research until those rules are independently registered and validated.
