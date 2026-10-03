# Compass review claims checked on our data
Generated 2026-10-03 21:57. Journal: signals.db; candles: Binance USD-M REST.

## 1. Binance funding sits at exactly 0.01% most of the time
- journal rows with a funding reading: 4949; exactly 0.0100%: 57.1%; > +0.03%: 1.6%; < -0.01%: 10.1%
- Claim: CONFIRMED if most readings are exactly 0.01% (the funding is uninformative inside the band).

## 2. Binance forceOrder stream: <= 1 order per symbol per second (a lower bound of liquidations)
- max Binance events for one symbol in one second: 3
- binance: 41415 events, $198.7M
- bybit: 19861 events, $59.8M
- okx: 15278 events, $58.5M
- Claim: CONFIRMED if the max is 1 and Binance shows far fewer events than Bybit (complete feed).

## 3. Intraday seasonality: volume and volatility yes, returns no; weekend volume ~30% lower
- 24 coins x 90 days of 1h candles
- volume, max / min hour: 2.29x (peak 14 UTC, low 23 UTC)
- range, max / min hour: 1.65x
- hourly mean returns with |t| > 2: 17 of 24 (00h t=+7.5, 01h t=-3.9, 02h t=+3.1, 04h t=+4.1, 07h t=-4.5, 08h t=+5.1, 10h t=+4.8, 11h t=+6.4, 12h t=+3.0, 13h t=+3.4, 14h t=-2.9, 15h t=+3.7, 16h t=+7.8, 18h t=-5.3, 20h t=+2.9, 22h t=-3.4, 23h t=+4.8); ~1.2 expected by chance (pooled coins are correlated, so t is overstated)
- 21-23 UTC mean return: -0.006% per hour vs all hours +0.025%
- weekend volume vs weekdays: -21%

## 4. Alt correlation with BTC rises on down days
- median correlation with BTC: BTC-down days 0.57, BTC-up days 0.49
- median beta: down days 1.27, up days 1.12

## 5. Taker flow explains the SAME interval's move, predicts the next one much less
- 2706 anomaly rows: corr(5m taker delta, same 5m move) +0.06; corr(5m delta, next 15m) -0.03; next 1h +nan

## 6. Price x OI quadrants vs the next 4h (anomaly rows, raw returns)
- price down / OI down: n 570, next 4h -0.54% (t -3.0), up 42%
- price down / OI up: n 359, next 4h +0.23% (t +1.0), up 53%
- price up / OI down: n 288, next 4h -0.55% (t -1.6), up 41%
- price up / OI up: n 531, next 4h -0.84% (t -3.5), up 39%

## 7. Swept level -> continuation, not reversal (Mahadzva, FX)
- SWEEP LOW: n 378, 4h in the reversal direction -0.05% (t -0.2), right side 47%
- SWEEP HIGH: n 433, 4h in the reversal direction +0.75% (t +3.3), right side 65%
- SILVER BULLET LONG: n 81, 4h in the reversal direction -1.62% (t -5.1), right side 31%
- SILVER BULLET SHORT: n 20, 4h in the reversal direction +2.18% (t +3.8), right side 85%
- SPRING: n 8, 4h in the reversal direction -1.52% (t -3.5), right side 12%
- UTAD: n 12, 4h in the reversal direction +0.35% (t +0.3), right side 67%
- FLUSH REVERSAL: n 7, 4h in the reversal direction +3.53% (t +2.1), right side 86%
- SQUEEZE REVERSAL: n 16, 4h in the reversal direction +1.63% (t +2.4), right side 75%
- Archive (research/cards_6m.md, 202k cards): sweep low -0.27R, sweep high -0.06R as reversal trades.

## 8. Claims already tested by our archive studies (research-findings)
- "Levels / EQH-EQL / S-R zones attract and reject price": hit rates at the random-walk rate (eqh.md, level_triggers.md, scenario_model.md) -> consistent with the review's "folklore / medium as a map".
- "TSMOM 1-4 weeks works in crypto": daily TSMOM / XSMOM did NOT replicate 2023-10..2026-09 (trend_daily.md) -> the review's [Empirical+] is not confirmed on recent Binance perps.
- "Funding / positioning predicts returns": only the funding level passed in-sample, its holdout failed (funding_holdout.md) -> weaker than the review states.
- "Pumps retrace": small-cap pumps come back to 50% of the move before a new high in 73-82% (pumps.md) -> consistent; the 30-minute round trip is about organised spot P&Ds, not measured here.
- "Meta-labeling is the way to use SMC": our meta-model AUC 0.63 still selected losing trades (-0.10R, meta_12m.md).

## Corrections (the pooled t-stats above overstate: coins move together, the period trended down)
- Hourly returns with one equal-weight cross-coin value per day (t over 90 days): |t| > 2 in 3 of 24 hours
  (00h +2.6, 11h +2.1, 16h +2.6; ~1.2 expected by chance) -> return seasonality weak, as the review says. The
  21-23 UTC effect (Quantpedia) is absent: -0.006% / hour, t -0.1.
- Reversal setups net of the same-time journal baseline (+-30 min): SWEEP LOW +0.50% (61% right), SWEEP HIGH +0.15%,
  SILVER BULLET LONG -0.16%, BB W-BOTTOM -0.32% (36%), BB M-TOP -0.09%, but only 3-17 independent 4h blocks each:
  no reading (reversal or continuation) is supported yet. Mahadzva's continuation result is NOT reproduced and NOT
  refuted on this journal; the raw section 7 numbers were the market's drift (shorts right, longs wrong).
- Section 6 (price x OI): every quadrant is negative because the period fell; the classic "price up + OI up = healthy
  trend" was the WORST after anomalies (-0.84%, 39% up) - after a spike, new leverage faded. Correlated rows: a
  pointer, not a result.
- Section 5: the 5m taker delta of anomaly rows barely tracks even its own 5m move (+0.06): anomaly rows are a biased
  sample (spikes); OFI / TFI needs the recorder's per-second flow, not the journal.
