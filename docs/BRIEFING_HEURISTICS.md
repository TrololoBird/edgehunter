# Briefing analysis: parameters without a primary source (eng-169)

Every number below was chosen by the (AI-written) code or by an internal review, not taken from a cited source or
calibrated on data. They are kept until a measurement on the published briefings (scripts/acceptance_briefing.py,
scripts/trace_briefing.py, scripts/variants_briefing.py) supports or replaces them. Audits #8-#10 listed them.

| Where | Parameter | Value | Note |
|---|---|---|---|
| sr.pivots | fractal width | 2 bars each side | Williams' 5-bar fractal (a source for the shape, not for its value as S/R) |
| sr.pivots | reaction window / threshold | 10 bars / >= 1 ATR14 | a fresh pivot (window incomplete) is marked `fresh` |
| sr.zones | lookback | 1h 10d, 4h 45d, 1d 120d | heuristic |
| sr.zones | cluster tolerance / max width | 0.6 / 1.5 x ATR(1h) | heuristic; greedy from the lowest pivot |
| sr.zones | timeframe weights | 1h 1, 4h 2, 1d 4 | heuristic |
| sr.zones | age half-life | 30 days, all timeframes | decay with age is supported (Chung & Bellotti), the value is not |
| sr.zones | volume factor / react bonus | 0.75 + 0.25 min(vol, 3); x (1 + 0.15 min(react, 5)) | heuristic |
| sr.zones | rejection bonus / chop penalty | + 0.5 min(holds, 5); x 0.65 if breaks > holds (>= 3 approaches) | heuristic |
| key_zones | map-level band, 'рядом' radius | +- 0.15 / 0.6 x ATR(1h) | heuristic |
| key_zones | ladder 'same place' gap, span | max(tol, 1.5 ATR(1h)); +- 5 ATR(1d) | the span is a display limit |
| pierce / key_zones | tol / pad | p50 <= 0.5 ATR(1h); 0.5..1 ATR(1h) around p80 | measured quantiles, heuristic clamps; 4h / 1d zones use swing_1h (no own statistics) |
| plan | position-in-zone thresholds | long 0.65 / 0.40, short 0.35 / 0.60, edge trade if width >= 1.5 ATR(1h) | heuristic |
| plan | targets above the history high | + 1 ATR(1d) steps | extrapolation, labelled |
| session_bias | fast background | 4h EMA20 + its 12h slope + 24h return | heuristic; measured: no clear edge either way |
| conf_tf | 4h vs 1h | 4h for zones of 4h+ pivots / higher map levels (acceptance only) | supported by the acceptance measurement (eng-168z1) |
| scoring | horizon | 72 h | heuristic |
| execution_model_v1 | partial / costs | 50% at +1R, BE + costs; fee 0.1% round trip + 2 x 5 bps | the bot's rule; funding not included |
| sweep shadow | ICT sweep | 0.05..0.8 ATR beyond, close past the middle, wick >= 40%, stop max(0.25 ATR, 0.25 range) | audit #10's definition, shadow only |
