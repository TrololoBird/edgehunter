# Audit 10 — ORB

Status: executable ORB path reviewed; no hidden code violation fixed in this pass. The implementation is explicitly a
session variant, while canonical Crabel material describes multiple ORB variants.

## Sources and formal rules

* [Toby Crabel, Opening Range Breakout overview](https://tobycrabel.substack.com/p/opening-range-breakout-a-century): opening-range breakout, volatility-calibrated stretch, fixed holding/exit rule; the cited test uses no stop and holds to the next open.
* [Crabel ORB source article](https://nexusfi.com/attachments/72178d1335946495): opening-range/Stretch stop-order construction.
* [Alternative summary](https://tradelosstracker.com/library/book/141/extended): opposite opening-range protective stop and session/day holding rules.

## Code comparison

* `strategies/classic.py:306-345` builds session opening range and Crabel Stretch, entering on the first touch.
* `strategies/classic_strategies.py:35-91` uses the opposite level as stop, no target order, session close exit, and optional
  break-even after 1R/60 minutes.

## Finding

The bot's ORB is a named session variant (Asia/London/New York, asset-class sessions), not the canonical daily-open
variant. The VWAP and RVOL checks are shadow-only and do not alter entry. The break-even rule is explicit in code and
has a cited Crabel variant reference; it is therefore recorded as a variant rather than silently treated as canonical.

No PnL evidence was used and no unambiguous executable violation was found in this pass.

## Residual doubts

The exact session adaptation, crypto session boundaries, and break-even interpretation need a source-specific decision;
they must not be reported as literal universal Crabel rules.
