# Audit 05 — Sweep / Silver Bullet

Status: executable playbooks separated; targeted tests pass. No demo-PnL evidence used.

## Sources and formal rules

* [ICT Silver Bullet alternative implementation](https://thetrademethod.com/setups/silver-bullet.html): separate New York windows (03–04, 10–11, 14–15), displacement and FVG, with entry at the FVG consequent encroachment.
* [Official Bollinger-style ICT checklist alternative](https://backtestify.com/strategies/ict-silver-bullet): sweep first, later displacement/FVG in the same window, CE entry valid only during the window, draw-on-liquidity target.
* [ICT liquidity/displacement reference](https://liquiditysweeps.com/ict-displacement/): a sweep is only the setup; displacement breaks structure and leaves an FVG used for the retracement entry.

Formal distinction:

* **SWEEP**: 15m raid of an HTF pool, close back, HTF POI/context, lower-timeframe MSS + FVG retrace; stop beyond the raid/pool; target opposing liquidity.
* **SILVER BULLET**: time-window-specific 5m raid of the prior hour's liquidity, displacement/FVG in the same NY window, CE touch entry, raid-extreme stop, daily draw target and window-limited entry.

## Code comparison

* `strategies/level.py:111-249` implements the general HTF-pool sweep, adaptive pool stop, dealing-range context and FVG trigger.
* `strategies/silver_bullet.py:131-199` implements the 5m CE limit, raid-extreme stop, PDH/PDL target and `entry_until_ms`.

## Confirmed violation and fix

Both classes previously used `name = 'sweep'`. As a result the Silver Bullet inherited the general sweep's mode gates and
could enter shared sweep-only lifecycle paths (`signal_book.py` checks for `s.mode == 'sweep'`), despite its distinct
clock, trigger, target and stop rules. The registry now uses `sweep` and `silver_bullet` separately. Bias/regime,
OI/flow confirmations, reversal classification, pool rules, journal/statistics and legacy config aliases were updated.

Historical regression evidence (the test suite was later removed): `tests/test_sweep_method_separation.py` asserts distinct strategy objects; the alias test confirms an old
`enabled = ["sweep"]` configuration keeps both historical playbooks. `unknown_names()` and targeted tests are green.

## Residual doubts

1. ICT's public material is discretionary; exact pool age/depth and measured-pierce parameters remain project choices.
2. The general sweep's shadow POI/premium filters are not blocking gates; their final policy needs the shared filter audit.
3. Silver Bullet's source window is NY wall-clock time; timezone/DST and executor fill semantics require separate runtime
   verification.
