# Meta-labeling on the archive replay (job 8)

**Summary.** 5936 passed replay entries; strategies judged (>= 300 entries): 3; USEFUL by the pre-registered rule: none. Below 300 entries (not judged): connors (213), continuation (16), pump (96), supply_demand (5), sweep (140), trendline (84).

Run `data/replay/run12m`; rule and method: the docstring of `research_meta_replay.py`. Label r_tp1 > 0; purged monthly walk-forward (8h trade life + 1-day embargo); net R = r_tp1 (journal replay, net of fees and slippage).

| strategy | passed entries | OOS rows | AUC LightGBM | AUC logistic | log-loss GBM / base | older: all / top⅓ (n) | newer: all / top⅓ (n) | newer top⅓ 90% (days) | verdict |
|---|---:|---:|---:|---:|---|---|---|---|---|
| bollinger | 3109 | 2329 | 0.519 | 0.526 | 0.6750 / 0.6392 | -0.097 / -0.023 (484) | -0.228 / -0.126 (351) | [-0.275..+0.017] | NOT USEFUL |
| breakout | 359 | 243 | 0.449 | 0.552 | 0.7857 / 0.6821 | -0.010 / +0.076 (14) | +0.014 / -0.111 (34) | [-0.185..-0.038] | NOT USEFUL |
| market_profile | 1914 | 1462 | 0.545 | 0.528 | 0.7275 / 0.6801 | -0.086 / -0.106 (111) | -0.247 / -0.254 (92) | [-0.391..-0.117] | NOT USEFUL |
