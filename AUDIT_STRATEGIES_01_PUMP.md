# Audit 01 — DUMP START / DUMP BOUNCE / PUMP TOP

Status: executable-code audit completed for the first group; no demo-PnL evidence was used. The remaining
methodological uncertainty is the owner's proprietary pump thresholds, which have no independent canonical rule set.

## Sources and formal rules

* [StockCharts — The Wyckoff Method](https://chartschool.stockcharts.com/table-of-contents/market-analysis/wyckoff-analysis-articles/the-wyckoff-method-a-tutorial): a buying climax is followed by an automatic reaction and a secondary test; a top is confirmed when supply outweighs demand on the test, with decreasing spread/volume near resistance.
* [Wyckoff Stock Market Institute glossary](https://wyckoffstockmarketinstitute.com/Archives/Wyckoff_selling_tests_1.pdf): an upthrust must react promptly after the failed move above resistance; the reaction is the confirmation.
* [IEEE — Cryptocurrency Pump and Dump Schemes](https://ieeexplore.ieee.org/document/8955594/): crypto pump/dump events are characterized by coordinated price and volume shocks; this supports event detection, but does not define a universal entry/stop/target system.
* Repository research (`research/pumps.md`, `research/pumps_holdout.md`): the project's only measured rule is the small-cap first 38.2–61.8% bounce after a dump, short on a 1h close below the previous hour's low; this is an alternative implementation, not an authoritative Wyckoff rule.

## Rule-to-code comparison

| Setup | Executable rule | Entry / stop / target / exit | Result |
|---|---|---|---|
| DUMP START | `strategies/pump.py:70-109`: 15m fall, RVOL, negative taker flow, fresh 24h low; no OI requirement | `strategies/pump.py:354-360`: confirmation entry, stop above ignition, measured/map targets | The code is a proprietary momentum detector. It must not be labelled as Wyckoff or merged with the fade setups. No canonical source supplies these exact thresholds. |
| DUMP BOUNCE | `strategies/pump.py:141-220`: 1h dump from 6h high, weekly-volume shock, exhaustion close, 38.2–61.8% bounce, close below prior low | stop above bounce + 0.25 ATR; TP1 dump low; TP2 1.618 extension (`strategies/pump.py:258-264`) | Matches the repository's pre-registered alternative implementation. It is distinct from DUMP START. |
| PUMP TOP | `strategies/pump.py:112-135`: 15m high/wick/2× volume after a 4h move; entry plan waits for a 5m shift (`strategies/pump.py:395-398`) | stop reference pump high; retracement/map targets | The 5m shift is a prompt reaction, but the detector itself does not establish an AR/ST sequence. Therefore this is a short-after-climax playbook, not a fully confirmed Wyckoff distribution top. |

## Confirmed violation and fix

Before this change all four setups returned `Strategy.name == "pump"` (`strategies/pump.py`), so the shared executable
gates treated them as one method: bias (`strategies/bias.py`), regime (`strategies/regime.py`), OI expectation and
confirmation policy (`strategies/confirm.py`), pool selection (`config.py`), lifecycle overshoot exemptions
(`signal_book.py`), and journal/statistics classing. That changes the meaning of the methods: e.g. a PUMP TOP fade
was classified with the same trend/OI/pool mode as PUMP START, and DUMP BOUNCE could inherit momentum gates.

The four classes now have independent names: `pump_start`, `dump_start`, `pump_top`, and `dump_bounce`. All shared
gates and configuration entries were updated, and legacy `pump` rows remain readable only where historical reports
need them. The setup registry now returns four distinct strategy objects.

Historical regression coverage (the test suite was later removed): `tests/test_pump_method_separation.py` checks distinct names and objects; `tests/test_eng169h.py`
checks that the PUMP TOP flow/absorption requirement applies only to `pump_top`, not PUMP START.

## Residual doubts

1. PUMP TOP still uses a proprietary 15m climax plus 5m shift rather than a complete Wyckoff AR/ST sequence. The
   source explicitly distinguishes a prompt upthrust reaction from a confirmed distribution top; this code should be
   treated as a separate short-after-climax model until a source-specific AR/ST rule is selected and tested.
2. DUMP START thresholds (3%, 4σ, RVOL 5, spot/perp flow) are repository parameters, not rules established by the
   cited academic sources. They are documented as such and are not evidence of a canonical methodology match.
3. Full execution/partial-fill/version-gate audit for these setups remains pending in the later lifecycle pass.
