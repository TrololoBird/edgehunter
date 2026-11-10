# Audit 08 — Breakout / Continuation

Status: one confirmed continuation-exit mismatch fixed; Turtle and continuation code otherwise matched their declared
source rules in the inspected executable paths.

## Sources and formal rules

* [Original Turtle rules summary](https://www.tradingblox.com/originalturtles/): System 1/2 Donchian entry on breakout, 2N stop, pyramiding and opposite-channel exit.
* [ICT OTE alternative reference](https://www.luxalgo.com/blog/ict-optimal-trade-entry-ote-explained/): retracement into 0.62–0.79 of a displacement leg, structural invalidation beyond the leg origin and extension/liquidity targets.

## Code comparison

* `strategies/breakout.py:70-102` uses Turtle channel touch, 2N stop and opposite-channel trailing exit.
* `strategies/leg.py:127-180` requires own-timeframe BOS and FVG displacement, Elder tide, 0.62–0.79 OTE, touch-close entry,
  origin stop and extension targets.

## Confirmed violation and fix

The continuation plan set `trail_after_tp1=True` at `strategies/leg.py:175`, while the executable strategy contract and
its own rules specify thirds at extension targets with no post-TP1 trail. This changed the exit and partial-management
semantics. The flag was removed. Historical regression evidence (the test suite was later removed): `tests/test_levels.py::test_impulse_plan_continuation_and_reversal` now asserts
that the plan has no post-TP1 trail; the test passes.

## Residual doubts

Turtle stop-order gap fills and continuation target selection through the shared level map still need the common execution
audit. No demo-PnL result was used to establish the violation.
