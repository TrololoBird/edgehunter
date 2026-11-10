# Audit 07 — OI Build

Status: executable detector reviewed; no unambiguous source violation was found beyond an explicitly documented
robust-statistics operationalisation. The setup remains journal/shadow-only by configuration.

## Sources and formal rules

* [CME open-interest primer](https://www.cmegroup.com/education/lessons/open-interest): OI is a participation/trend-strength input and must be interpreted with price, not as a directional position count.
* [ICE volume/OI reference](https://download.dataservices.theice.com/products/marketq/help/charts/chart_studies/available_chart_studies/voi.htm): rising price plus rising OI is a strength confirmation; falling price plus rising OI is bearish confirmation.

The project’s Pring-style rule is: 1h price direction and positive 1h OI change materially above the coin’s own recent baseline, with a BTC-relative move filter; stop beyond the hour extreme and target opposing liquidity.

## Code comparison

`strategies/oi_build.py:62-112` requires fresh OI data, computes 1h changes, applies a robust median/MAD two-sigma threshold,
requires price to exceed its usual 1h move and outperform BTC in normalized units, then emits an OI BUILD signal.
`strategies/oi_build.py:115-133` uses a 15m confirmation plan, hour-extreme stop and map targets.

## Finding

The docstring’s historical wording says “above the mean”, while executable code intentionally uses median + 2 MAD
(`oi_build.py:74-80`). This is a documented robustness choice, not a hidden implementation mismatch: it materially
changes sensitivity and must be treated as a separate operational variant, not claimed as literal Pring. The setup is
also disabled from demo execution (`config.py:1199-1201`), so no PnL was used as evidence.

No code change was made because replacing the robust baseline with a mean would be an unvalidated methodology change.
Existing tests `tests/test_infra.py::test_oi_build_pring_rule` and `tests/test_eng169i.py` cover the causal OI/price/BTC
requirements.

## Residual doubts

The public sources do not prescribe the 2-MAD threshold, 3-day baseline, BTC normalization, or crypto 5m sampling.
Those parameters require a separately named variant and future out-of-sample validation before enabling execution.
