# Audit 04 — Bollinger

Status: executable playbooks separated; no demo-PnL evidence used.

## Sources and formal rules

* [John Bollinger — official rules](https://www.bollingerbands.com/bollinger-band-rules): a band tag is not a signal; closes outside the bands are initially continuation signals; BandWidth identifies the Squeeze; W/M patterns require confirmation.
* [Official Method descriptions](https://bollingerbands.us/help-methods.php): Method I is volatility breakout; Method III is reversal using band contacts and an independent volume indicator (Accumulation/Distribution or Intraday Intensity).
* [Official screening rules](https://bollingerbands.us/help-screening.php): W bottom requires the first low outside the lower band, the second low inside, and a confirming break; Squeeze is a 125-period BandWidth low.
* [StockCharts Bollinger reference](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/bollinger-bands): independent reference for W-bottom/M-top confirmation.

## Rule-to-code comparison

* **W/M**: `strategies/maniac.py:577-659` uses BB(20,2), first outside close, inside retest, A/D relation and close beyond the intervening peak; `strategies/maniac_strategies.py:300-329` uses signal-close entry, retest stop, opposite live band target and band exit.
* **Method III alert**: `strategies/maniac.py:512-574` uses band tag + Intraday Intensity and a strong confirming bar; its stop is the alert-to-confirmation extreme and target is the opposite band.
* **Method I**: `strategies/maniac.py:456-509` uses a recent 125-bar BandWidth low and first outside close with Intraday Intensity; `strategies/maniac_strategies.py:332-354` exits with Wilder SAR and has no fixed target.

## Confirmed violation and fix

Before this change, BB1 was registered as `breakout`, the same executable mode as Turtle BREAKOUT, while W/M and BB3
shared `bollinger`. This caused unrelated entry, exit, timeframe and confirmation rules to share mode-level gates,
pool/statistics classes, and management exemptions. The registry now exposes:

* `bollinger_wm` — `BB W-BOTTOM`, `BB M-TOP`;
* `bollinger_method3` — `BB3 BUY`, `BB3 SELL`;
* `bollinger_method1` — `BB1 UP`, `BB1 DOWN`.

Bias, regime, OI expectation, management/overshoot gates, pools, journal/statistics mappings and legacy config aliases
were updated. Regression tests in `tests/test_bollinger_method_separation.py` assert distinct strategy objects; config
tests ensure old `bollinger`/`breakout` overrides expand to the former playbooks.

## Residual doubts

1. The project applies official daily/125-period concepts to 4h crypto bars; the source permits multiple timeframes but
   does not prescribe this exact crypto mapping.
2. The W/M target as the moving opposite band and the Method III strong-bar range threshold are implementation choices;
   they are not fully specified in the public text.
3. Shared execution/partial-fill behavior still requires the later lifecycle audit.
