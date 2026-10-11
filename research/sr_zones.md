# Price-action S/R zones (sr.py) vs placebo prices (40 coins, 2025-10-05 .. 2026-09-30)

Rejection = a 15m close back on the level's side within 1h of the first candle beyond it. Placebo = the same level shifted 0.3-1.5% (same side, same time). OR = odds ratio real / placebo; [90%] by coin bootstrap. Pre-registered: a class holds price only if OR > 1 with the interval above 1 in both halves.

| class | tests | rejected | placebo | OR [90%] | older [90%] | newer [90%] | verdict |
|---|---:|---:|---:|---|---|---|---|
| sr | 101808 | 76.9% | 77.9% | 0.94 [0.92..0.96] | 0.95 [0.90..1.00] | 0.94 [0.91..0.96] | descriptive |
| sr_top | 32085 | 76.3% | 78.1% | 0.90 [0.87..0.93] | 0.89 [0.84..0.95] | 0.90 [0.87..0.93] | descriptive |
| sr_bot | 50503 | 77.6% | 77.7% | 1.00 [0.96..1.04] | 1.00 [0.91..1.12] | 1.00 [0.95..1.04] | descriptive |
| sr_flip | 41133 | 77.1% | 77.8% | 0.96 [0.93..1.00] | 0.91 [0.86..0.95] | 0.98 [0.94..1.02] | descriptive |
| sr_t3 | 69677 | 76.6% | 77.9% | 0.93 [0.91..0.95] | 0.92 [0.88..0.96] | 0.93 [0.90..0.95] | descriptive |
| sr_1d | 39240 | 76.2% | 78.2% | 0.89 [0.83..0.95] | 0.96 [0.86..1.07] | 0.88 [0.82..0.94] | descriptive |
