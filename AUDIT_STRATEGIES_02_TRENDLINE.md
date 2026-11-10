# Audit 02 — Trendline

Status: executable detector/plan/registry audited. The two playbooks are now separated; source-specific geometry is
documented below. No demo-PnL result was used as proof of a violation.

## Sources and formal rules

* [Edwards & Magee, *Technical Analysis of Stock Trends* (summary of the original text)](https://tradelosstracker.com/library/book/255-technical-analysis-of-stock-trends-8th-edition-bassetti/extended): a line is tentative through two reaction points; a third valid contact gives confirmation.
* [The Right Trader — trendline break](https://therighttrader.com/learn/trend-analysis/trendline-break): a decisive close beyond the line is the break; a later return and rejection is a separate retest entry, with reclaim invalidating the break.
* [The Right Trader — trendline retest](https://therighttrader.com/learn/trend-analysis/trendline-retest): a touch before a break is an ordinary test; a retest requires the prior break and role reversal.

Formal playbooks used for this audit:

* **TL EM**: two falling highs (resistance) or rising lows (support), no intervening close through the line; two decisive closes beyond it (the project parameter is 3% of line price), then wait for a retest and lower-timeframe confirmation. Stop beyond the last structure pivot; targets are the next mapped levels.
* **TL TOUCH**: two reaction points define a line, price leaves the line, then the first third touch reaches the line band and closes on the trendline side with a directional body/rejection. Entry is that close; stop beyond the far side of the band plus measured pierce; target is the next mapped level.

## Code comparison

* Detector: `strategies/maniac.py:303-330` constructs a line from the last two pivots and rejects closes through it; `:333-381` requires two closes at least `pct` beyond the line and a volume check for upside breaks.
* Third touch: `strategies/maniac.py:384-431` requires leaving the band after the second point, a new touch, body/rejection, slope and band limits.
* TL EM plan: `strategies/maniac_strategies.py:249-282` retests the same sloped line, uses a 15m shift trigger with flow, and stops beyond a confirmed 1h pivot.
* TL TOUCH plan: `strategies/maniac_strategies.py:237-248` enters on the confirmed touch close and uses the band edge plus measured pierce.

## Confirmed violation and fix

Before this change, `TL EM UP/DOWN` and `TL TOUCH UP/DOWN` shared `TrendlineStrategy.name == "trendline"`. The
common executable gates therefore treated a breakout/retest and a pre-break third-touch continuation as one method:
the same pool, bias/regime mode, OI/confirmation mode, and statistics class. This violates the requirement that
different methodologies not be merged and makes source-to-code evidence ambiguous.

The registry now instantiates `TrendlineBreakStrategy(name='trendline_break')` and
`TrendlineTouchStrategy(name='trendline_touch')`, each with only its own setups. Config pools, bias exemptions,
confirmation expectations, overshoot exemptions, and journal/statistics mappings were updated. The common line math
is shared as implementation, while the method identity and gates are separate.

Historical regression coverage (the test suite was later removed): `tests/test_trendline_method_separation.py` asserts separate names and strategy objects;
`tests/test_eng169h.py` verifies the flow confirmation lookup uses the touch mode explicitly.

## Residual doubts

1. The 3% decisive-penetration threshold and 1h/15m timeframe choice are project parameters; Edwards & Magee do not
   prescribe these crypto values. They must remain labelled as implementation parameters.
2. The public sources describe discretionary confirmation; the executable shift/flow rule is an operationalisation,
   not a verbatim source rule.
3. Full stop/target execution and partial-fill audit for Trendline remains part of the shared lifecycle pass.
