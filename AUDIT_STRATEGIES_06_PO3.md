# Audit 06 — PO3 / Power of Three

Status: executable detector and plan audited; one missing displacement condition fixed and tested.

## Sources and formal rules

* [ICT Power of Three / AMD reference](https://www.ictkillzone.com/ict-power-of-three): Asian accumulation, London Judas sweep against the daily direction, displacement/FVG and distribution toward opposing liquidity.
* [Inner Circle Traders Asian session reference](https://www.theinnercircletraders.com/ict-asian-session/): Asian range is accumulation and London takes an Asian extreme before the real delivery.
* [Alternative implementation](https://thetrademethod.com/setups/silver-bullet.html): the same ICT execution convention uses a declared session window, displacement, FVG CE limit, structural stop and draw-on-liquidity target.

Formal rule: complete Asian range (20:00–00:00 New York), London 02:00–05:00 New York, raid the Asian side opposite the trade, then a displacement/MSS bar with a first FVG; enter CE, stop beyond raid extreme, TP1 opposite Asian side and later draw on liquidity; daily/weekly bias is mandatory.

## Code comparison

* `strategies/po3.py:27-36` converts the New York window with DST-aware `ZoneInfo`.
* `strategies/po3.py:47-98` requires 48 Asian 5m bars, detects the opposite-side raid, searches a prior swing and creates an FVG/CE.
* `strategies/po3.py:107-158` enforces bias, CE touch entry, Judas-extreme stop and Asian-side TP1.

## Confirmed violation and fix

The detector's displacement condition at `strategies/po3.py:75` previously required only a directional candle body,
despite the documented/source rule requiring a displacement body at least half the candle range. A tiny directional
body could therefore qualify as the MSS/distribution transition and create a PO3 card, changing the setup from a
displacement-confirmed reversal into any FVG after a weak candle.

Added `displacement_bar()` and require `directional body >= 0.5 * range`. Historical regression test (the test suite was later removed):
`tests/test_po3_method.py::test_po3_requires_half_range_displacement_body`.

## Residual doubts

1. The exact 20:00–00:00 and 02:00–05:00 windows are common ICT implementations; ICT's video material is not a formal
   machine-readable specification.
2. Swing selection and the exact three-candle FVG construction remain project operationalisations.
3. Execution, partial fills, bias refresh and target management still require the shared lifecycle pass.
