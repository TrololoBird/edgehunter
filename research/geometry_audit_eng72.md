# Entry vs geometry (research_geometry_audit.py)

## Part 1: geometry of the passed entries (ATR = the coin's 1h ATR14 at the entry)

```
shape: (11, 7)
┌────────────────┬───────┬──────────────┬─────────────┬─────────────┬──────────┬────────────┐
│ strategy       ┆ n     ┆ stop_ATR_med ┆ stops_<1ATR ┆ tp1_ATR_med ┆ rr_med   ┆ cost_R_med │
│ ---            ┆ ---   ┆ ---          ┆ ---         ┆ ---         ┆ ---      ┆ ---        │
│ str            ┆ u32   ┆ f64          ┆ f64         ┆ f64         ┆ f64      ┆ f64        │
╞════════════════╪═══════╪══════════════╪═════════════╪═════════════╪══════════╪════════════╡
│ orb            ┆ 48030 ┆ 2.4          ┆ 0.036498    ┆ null        ┆ null     ┆ 0.129791   │
│ bollinger      ┆ 36758 ┆ 1.139942     ┆ 0.342837    ┆ null        ┆ null     ┆ 0.245426   │
│ market_profile ┆ 12438 ┆ 1.089598     ┆ 0.423943    ┆ 1.897524    ┆ 1.755046 ┆ 0.2285     │
│ pump           ┆ 1752  ┆ 2.509002     ┆ 0.010274    ┆ 1.684703    ┆ 0.722393 ┆ 0.070978   │
│ breakout       ┆ 1733  ┆ 10.498019    ┆ 0.0         ┆ null        ┆ null     ┆ 0.025646   │
│ connors        ┆ 1222  ┆ 12.347204    ┆ 0.0         ┆ null        ┆ null     ┆ 0.018413   │
│ sweep          ┆ 688   ┆ 1.381074     ┆ 0.218023    ┆ 3.233062    ┆ 2.285897 ┆ 0.207316   │
│ trendline      ┆ 557   ┆ 0.664636     ┆ 0.791741    ┆ 2.619462    ┆ 3.925198 ┆ 0.338752   │
│ wyckoff        ┆ 20    ┆ 2.380167     ┆ 0.0         ┆ 1.674801    ┆ 0.707526 ┆ 0.090506   │
│ supply_demand  ┆ 20    ┆ 1.639978     ┆ 0.05        ┆ 4.836519    ┆ 2.783145 ┆ 0.134544   │
│ continuation   ┆ 16    ┆ 1.335605     ┆ 0.1875      ┆ 1.079081    ┆ 1.071313 ┆ 0.131528   │
└────────────────┴───────┴──────────────┴─────────────┴─────────────┴──────────┴────────────┘

shape: (20, 4)
┌────────────────┬─────────────────────────────────┬───────┬───────────┐
│ strategy       ┆ sl_src                          ┆ n     ┆ stop_ATR  │
│ ---            ┆ ---                             ┆ ---   ┆ ---       │
│ str            ┆ str                             ┆ u32   ┆ f64       │
╞════════════════╪═════════════════════════════════╪═══════╪═══════════╡
│ bollinger      ┆ beyond the W / M retest + meas… ┆ 36758 ┆ 1.139942  │
│ breakout       ┆ 2N from the breakout (Turtles)  ┆ 1733  ┆ 10.498019 │
│ connors        ┆ catastrophic stop 3 daily ATR … ┆ 1222  ┆ 12.347204 │
│ market_profile ┆ beyond the value area edge + m… ┆ 5956  ┆ 0.86507   │
│ market_profile ┆ beyond the POC test + measured… ┆ 1580  ┆ 1.528795  │
│ market_profile ┆ beyond the POC test + measured… ┆ 566   ┆ 0.998875  │
│ market_profile ┆ beyond breaker 4h bear · break… ┆ 30    ┆ 1.309621  │
│ orb            ┆ the opposite open +- Stretch l… ┆ 48030 ┆ 2.4       │
│ pump           ┆ below the ignition + measured … ┆ 451   ┆ 2.517946  │
│ pump           ┆ above the bounce + 0.25 ATR(1h… ┆ 179   ┆ 1.481684  │
│ pump           ┆ below the ignition + measured … ┆ 158   ┆ 2.357358  │
│ pump           ┆ below the ignition + measured … ┆ 155   ┆ 2.455546  │
│ pump           ┆ below the ignition + measured … ┆ 100   ┆ 2.563657  │
│ pump           ┆ below the ignition + measured … ┆ 64    ┆ 2.613589  │
│ pump           ┆ below the ignition + measured … ┆ 46    ┆ 2.642006  │
│ sweep          ┆ beyond the raid's extreme + me… ┆ 202   ┆ 1.080373  │
│ sweep          ┆ beyond the swing + measured pi… ┆ 44    ┆ 1.552103  │
│ sweep          ┆ beyond the protected swing (BO… ┆ 30    ┆ 1.725889  │
│ trendline      ┆ 15m structure beyond the line,… ┆ 338   ┆ 0.573722  │
│ trendline      ┆ 15m structure beyond the line   ┆ 219   ┆ 0.926856  │
└────────────────┴─────────────────────────────────┴───────┴───────────┘
```

## Part 2: the entry without our stop / targets, vs placebo (same coin, side, hour; other days)

```
shape: (22, 10)
┌────────────────┬─────────┬────────┬───────────┬───┬───────────────┬───────────────┬───────────────┬───────────────┐
│ strategy       ┆ kind    ┆ n      ┆ r1h_ATR   ┆ … ┆ p_+1ATR_first ┆ p_-1ATR_first ┆ p_+2ATR_first ┆ p_-2ATR_first │
│ ---            ┆ ---     ┆ ---    ┆ ---       ┆   ┆ ---           ┆ ---           ┆ ---           ┆ ---           │
│ str            ┆ str     ┆ u32    ┆ f64       ┆   ┆ f64           ┆ f64           ┆ f64           ┆ f64           │
╞════════════════╪═════════╪════════╪═══════════╪═══╪═══════════════╪═══════════════╪═══════════════╪═══════════════╡
│ bollinger      ┆ ours    ┆ 36758  ┆ -0.019719 ┆ … ┆ 0.488737      ┆ 0.505795      ┆ 0.425023      ┆ 0.439523      │
│ bollinger      ┆ placebo ┆ 328313 ┆ NaN       ┆ … ┆ 0.492119      ┆ 0.502859      ┆ 0.430534      ┆ 0.440863      │
│ breakout       ┆ ours    ┆ 1733   ┆ 0.24625   ┆ … ┆ 0.534334      ┆ 0.465666      ┆ 0.508367      ┆ 0.450087      │
│ breakout       ┆ placebo ┆ 15493  ┆ NaN       ┆ … ┆ 0.497644      ┆ 0.49745       ┆ 0.434712      ┆ 0.432453      │
│ connors        ┆ ours    ┆ 1222   ┆ 0.024746  ┆ … ┆ 0.492635      ┆ 0.503273      ┆ 0.36252       ┆ 0.481997      │
│ connors        ┆ placebo ┆ 11268  ┆ NaN       ┆ … ┆ 0.507366      ┆ 0.486599      ┆ 0.433617      ┆ 0.422258      │
│ continuation   ┆ ours    ┆ 16     ┆ 0.174013  ┆ … ┆ 0.75          ┆ 0.25          ┆ 0.375         ┆ 0.3125        │
│ continuation   ┆ placebo ┆ 133    ┆ -0.054091 ┆ … ┆ 0.443609      ┆ 0.548872      ┆ 0.413534      ┆ 0.503759      │
│ market_profile ┆ ours    ┆ 12438  ┆ -0.007304 ┆ … ┆ 0.480865      ┆ 0.512301      ┆ 0.402557      ┆ 0.434957      │
│ market_profile ┆ placebo ┆ 112076 ┆ NaN       ┆ … ┆ 0.493433      ┆ 0.501017      ┆ 0.426791      ┆ 0.440692      │
│ orb            ┆ ours    ┆ 48030  ┆ -0.021122 ┆ … ┆ 0.483802      ┆ 0.512534      ┆ 0.44212       ┆ 0.452988      │
│ orb            ┆ placebo ┆ 431161 ┆ NaN       ┆ … ┆ 0.492255      ┆ 0.501374      ┆ 0.428         ┆ 0.435109      │
│ pump           ┆ ours    ┆ 1752   ┆ 0.062966  ┆ … ┆ 0.452626      ┆ 0.539954      ┆ 0.425799      ┆ 0.493721      │
│ pump           ┆ placebo ┆ 15563  ┆ NaN       ┆ … ┆ 0.476772      ┆ 0.517702      ┆ 0.417593      ┆ 0.451198      │
│ supply_demand  ┆ ours    ┆ 20     ┆ 0.080725  ┆ … ┆ 0.65          ┆ 0.35          ┆ 0.65          ┆ 0.2           │
│ supply_demand  ┆ placebo ┆ 179    ┆ -0.00843  ┆ … ┆ 0.469274      ┆ 0.530726      ┆ 0.47486       ┆ 0.418994      │
│ sweep          ┆ ours    ┆ 688    ┆ 0.039774  ┆ … ┆ 0.484012      ┆ 0.510174      ┆ 0.443314      ┆ 0.444767      │
│ sweep          ┆ placebo ┆ 6215   ┆ NaN       ┆ … ┆ 0.494127      ┆ 0.500724      ┆ 0.437973      ┆ 0.44473       │
│ trendline      ┆ ours    ┆ 557    ┆ 0.0467    ┆ … ┆ 0.508079      ┆ 0.48833       ┆ 0.473968      ┆ 0.412926      │
│ trendline      ┆ placebo ┆ 4935   ┆ NaN       ┆ … ┆ 0.488551      ┆ 0.506383      ┆ 0.423708      ┆ 0.448227      │
│ wyckoff        ┆ ours    ┆ 20     ┆ -0.049573 ┆ … ┆ 0.5           ┆ 0.5           ┆ 0.4           ┆ 0.4           │
│ wyckoff        ┆ placebo ┆ 186    ┆ 0.047177  ┆ … ┆ 0.516129      ┆ 0.467742      ┆ 0.435484      ┆ 0.403226      │
└────────────────┴─────────┴────────┴───────────┴───┴───────────────┴───────────────┴───────────────┴───────────────┘
```
