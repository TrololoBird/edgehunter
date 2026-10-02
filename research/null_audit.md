# Null-world audit (6 coins, 2026-07-02 .. 2026-09-30, hours shuffled within each week)

Expected on a world without structure: gross R ~ 0, net R ~ -cost, no setup above its placebo.

## research_cards (card replay)

| Setup | entries | mean R TP1 | placebo |
|---|---:|---:|---:|
| SWEEP HIGH | 5 | +0.016 | -0.222 |

## research_classic

| Setup | trades | mean | placebo |
|---|---:|---:|---:|
| ORB DOWN | 177 | -0.276 | -0.430 |
| ORB UP | 156 | -0.387 | -0.682 |
| PUMP START | 22 | +0.259 | +0.096 |
| PUMP TOP | 2 | +0.762 | -0.648 |
| RSI2 LONG | 5 | +1.005 | +5.099 |
| RSI2 SHORT | 18 | +0.404 | -0.447 |
| VA80 LONG | 49 | -0.228 | -0.131 |
| VA80 SHORT | 63 | -0.197 | -0.436 |

# Null-world audit of ml_eval (labels shuffled within each week)

Expected: AUC ~ 0.5, log-loss skill <= 0, PBO ~ 0.5, top 20% ~ all rows.

```

4. CPCV (6 groups, 2 test; 5 paths, 200000 newest rows)
   split (0, 1): train 129682, test 66666
   split (0, 2): train 126512, test 66667
   split (0, 3): train 126799, test 66666
   split (0, 4): train 126776, test 66666
   split (0, 5): train 129655, test 66667
   split (1, 2): train 129848, test 66667
   split (1, 3): train 126033, test 66666
   split (1, 4): train 126010, test 66666
   split (1, 5): train 128889, test 66667
   split (2, 3): train 130113, test 66667
   split (2, 4): train 126722, test 66667
   split (2, 5): train 129601, test 66668
   split (3, 4): train 130111, test 66666
   split (3, 5): train 129888, test 66667
   split (4, 5): train 133001, test 66667
   variant                  AUC median [min..max]   log-loss skill median   top-20% Edge - all (median)
   logistic C=0.01          0.501 [0.498..0.504]   -0.000%   -0.031%
   logistic C=0.05          0.500 [0.498..0.504]   -0.005%   -0.030%
   logistic C=0.5           0.500 [0.498..0.504]   -0.012%   -0.040%
   LightGBM leaves=7        0.503 [0.500..0.505]   -0.013%   -0.005%
   LightGBM leaves=15       0.503 [0.500..0.505]   -0.021%   -0.001%
   PBO over 5 variants + 'all rows' (15 weeks): 0.15  (> 0.5: the in-sample winner is worse than the median out of sample)
   best variant LightGBM leaves=15: weekly top-20% Edge +0.029% vs all rows +0.012%; deflated Sharpe 0.09 with 154 trials counted
```

