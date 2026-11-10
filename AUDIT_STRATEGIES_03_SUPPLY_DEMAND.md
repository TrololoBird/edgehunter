# Audit 03 — Supply / Demand

Status: executable detector and plan audited; one non-source warm-up gate removed and covered by a regression test.

## Sources and formal rules

* [FXStreet / Online Trading Academy — Will that Demand Hold or Break?](https://www.fxstreet.com/amp/education/lesson-from-the-pros-stocks-201504280000): Seiden's odds enhancers include the strength and speed of departure, freshness, time at the level, higher-timeframe curve/trend, arrival and the profit margin to opposing supply/demand.
* [Sam Seiden teaching archive](https://www.faratrade.ir/wp-content/uploads/2020/08/5-years-of-sam-seiden-supply-and-demand-teaching-1.pdf): a fresh zone has not been revisited; the profit zone is the distance to the opposing fresh level.
* [DT Academy — supply and demand](https://www.thedtterminal.com/academy/supply-and-demand): a clean short base, fast departure, freshness and higher-timeframe alignment are quality factors; no minimum count of historical zones is required.

Formal implementation contract used here: identify a short base and an impulsive departure on the 4h structure; keep the
first fresh return; confirm on the lower timeframe; stop beyond the distal edge; target the nearest opposing fresh zone;
reject when the profit margin cannot satisfy the method's 3:1 rule. The code's numerical thresholds are project
parameters because Seiden's public material is discretionary.

## Code comparison

* `strategies/maniac.py:163-214` identifies boring base candles, a directional departure and the distal/proximal zone.
* `strategies/maniac.py:217-259` emits only when the departure has just confirmed and scores speed/time.
* `strategies/maniac_strategies.py:61-150` applies freshness, curve/trend, arrival, opposing-zone target, proximal-entry
  3:1 check, distal stop and 4h zone / lower-timeframe touch confirmation.

## Confirmed violation and fix

`sd_zone_events` previously returned no signal until `len(zones) >= 10` (`strategies/maniac.py:230-232`). This is an
arbitrary historical warm-up condition absent from the source methodology. It changes the strategy by suppressing a
valid first fresh zone (and any symbol with fewer than ten prior departures), while the source scores the current zone
on its own observable odds enhancers. The detector now accepts any non-empty set of causal zones; quantile/median
statistics naturally collapse to the available sample when history is short.

Historical regression evidence (the test suite was later removed): `tests/test_supply_demand_method.py::test_supply_demand_does_not_require_ten_unrelated_historical_zones`
constructs one valid fresh zone and verifies that the detector emits `SD DEMAND`. The Supply/Demand causal tests also
remain green.

## Residual doubts

1. The 0.5 body/range definition, 4h timeframe, 3:1 RR and score weights are operational choices; they are not all
   stated as fixed numbers in the public Seiden sources.
2. `sd_opposing` uses the code's zone history to determine freshness; exchange-specific wick semantics and partial fills
   still need review in the shared execution audit.
3. No PnL or demo result was used to justify the fix.
