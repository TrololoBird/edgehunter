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

# Null-world audit (30 coins, 2026-04-03 .. 2026-09-30, hours shuffled within each week)

Expected on a world without structure: gross R ~ 0, net R ~ -cost, no setup above its placebo.

## research_cards (card replay)

| Setup | entries | mean R TP1 | placebo | system - placebo [90%] |
|---|---:|---:|---:|---|
| BULL F | 1 | +0.064 | +0.358 | — |
| SPRING | 1 | -1.077 | +1.470 | — |
| SWEEP HIGH | 56 | +0.048 | -0.181 | +0.229 [-0.072..+0.554] |
| SWEEP LOW | 95 | -0.073 | -0.159 | +0.086 [-0.099..+0.286] |
| UTAD | 2 | -1.071 | -1.044 | — |

## research_classic

| Setup | trades | mean | placebo | system - placebo [90%] |
|---|---:|---:|---:|---|
| ORB DOWN | 1834 | -0.491 | -0.437 | -0.054 [-0.195..+0.095] |
| ORB UP | 2129 | -0.310 | -0.363 | +0.053 [-0.126..+0.230] |
| PUMP START | 335 | -0.026 | +0.036 | -0.062 [-0.175..+0.053] |
| PUMP TOP | 108 | -0.158 | -0.158 | -0.000 [-0.216..+0.201] |
| RSI2 LONG | 45 | +1.126 | -1.243 | +2.369 [-6.844..+8.161] |
| RSI2 SHORT | 192 | +0.260 | -3.861 | +4.120 [+2.906..+5.417] |
| VA80 LONG | 650 | -0.152 | -0.148 | -0.004 [-0.096..+0.085] |
| VA80 SHORT | 772 | -0.131 | -0.167 | +0.037 [-0.066..+0.141] |

