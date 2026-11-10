# Audit 12 — Cup-and-Handle

Status: executable detector reviewed; existing shape/stop regressions pass. No new unambiguous violation fixed in this pass.

## Sources and formal rules

* [AAII cup-and-handle explanation](https://www.aaii.com/journal/article/the-cup-with-handle-pattern): rounded cup, right rim/handle, breakout above pivot with substantial volume.
* [O'Neil guideline summary](https://finabase.io/learn/technical-analysis/cup-and-handle): 7–65 week cup, 12–33% depth, upper-half handle and drying volume.

## Code comparison

`strategies/cup_handle.py:25-95` enforces prior advance, 49–455 daily candles, 12–33% depth, rounded bottom, 7–56-day
upper-half handle, lower handle volume, pivot breakout, 1.4× volume and a 5% chase limit. The plan at `:98-120`
uses handle/8% stop and measured targets.

Regression coverage already verifies V-shaped cups are rejected, U-shaped cups accepted, and stop loss is not widened
beyond the 8% method limit.

## Residual doubts

The 24/7 crypto calendar conversion (7–65 stock weeks to 49–455 candles), 1.4× volume threshold and Bulkowski 61%
target share are project operationalisations; they must not be presented as universal O'Neil rules.
