# B1 — realized-volatility forecast (pre-registered 2026-10-02, before any run)

- Target: realized variance of the NEXT 1h and 4h = sum of squared 1m log returns of the futures, at every hour close
  of every coin on its eligible days (volume floor, select_coins).
- Window: 2025-04-03 .. 2026-09-30. Development before 2026-04-01 (the last 60 days of it = early-stopping
  validation for LightGBM only); HOLDOUT 2026-04-01 .. 2026-09-30, looked at once.
- Forecasts compared (all fitted on development only, pooled over coins):
  1. ATR14 of 15m candles (the bot's stop unit) -> log RV = a + b log(ATR14/close)^2;
  2. max(ATR14, ATR of the last hour) (the bot's `min_stop_atr` base), same calibration;
  3. HAR-RV (Corsi 2009): log RV_next = a + b1 log RV_1h + b2 log RV_4h + b3 log RV_24h + b4 log RV_7d (OLS);
  4. LightGBM on HAR lags + hour of day / weekend + BTC's HAR lags + the universe median RV + |returns| 1h/4h/24h +
     log volume vs its 7-day mean + distance to the 24h high / low.
- Loss: QLIKE on variance (RV/F - log(RV/F) - 1, F = exp(log forecast + half the residual variance of development)),
  plus MSE of log RV. Diebold-Mariano on the hourly cross-coin mean loss differential, Newey-West with 24 lags.
- ACCEPT LightGBM if, on the holdout, QLIKE is >= 5% lower than HAR-RV for BOTH horizons and DM p < 0.05;
  else HAR-RV is the forecast if it beats both ATR baselines by >= 5% QLIKE with DM p < 0.05; else keep ATR.
- KILL: nothing beats ATR14 -> the stop unit stays as it is and B5 is cancelled.
- Counts as 4 variants x 2 horizons in research/trials.csv.
