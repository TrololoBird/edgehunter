# Demo trades in USDT: actual vs break-even (+costs) and re-entry

```
id  symbol         setup              base / peak / BE at +0.5%, re-entry x0 | BE at +0.5%, re-entry x2 | BE at +1.0%, re-entry x0 | BE at +1.0%, re-entry x2 | BE at +2.0%, re-entry x0 | BE at +2.0%, re-entry x2
 12 SOLUSDT        BB W-BOTTOM        база     +0.0  пик    +12.9     -4.0     -4.0     -4.0     -4.0     -4.0     -4.0
 13 ZECUSDT        BB W-BOTTOM        база    +59.2  пик    +72.2    +55.2    +55.2    +55.2    +55.2    +55.2    +55.2
 14 WLDUSDT        BB W-BOTTOM        база    +38.0  пик    +65.9     -0.0    +10.7     -0.0    +20.2    +33.9    +33.9
 15 TIAUSDT        BB W-BOTTOM        база    +14.7  пик    +31.1     -0.0     -1.1    +10.6    +10.6    +10.6    +10.6
 16 ADAUSDT        BB W-BOTTOM        база    -13.5  пик     -3.2    -57.4    -57.4    -57.4    -57.4    -57.4    -57.4
 17 OGNUSDT        BB W-BOTTOM        база    +13.1  пик    +25.7     +9.1     +9.1     +9.1     +9.1     +9.1     +9.1
 18 GRASSUSDT      BREAKOUT UP        база   -383.9  пик   +147.4     -0.0     -0.0     -0.0     -0.0     -0.0   -476.1
 19 LTCUSDT        BB W-BOTTOM        база     +0.9  пик    +11.8     -3.1     -3.1     -3.1     -3.1     -3.1     -3.1
 20 WUSDT          ORB UP             база   -111.9  пик  +1245.6     -0.0     -0.0     -0.0     -0.0     -0.0     -0.0
 21 PLUMEUSDT      BREAKOUT UP        база    -74.1  пик    +39.5     -1.4     -1.4     -0.0    -84.6     -0.0    -80.6
 22 ETHUSDT        ORB UP             база    -45.3  пик    -14.5    -49.3    -49.3    -49.3    -49.3    -49.3    -49.3
 23 INJUSDT        ORB UP             база    -40.2  пик   +118.2     -0.0     -0.0     -0.0     -0.0     -0.0   -131.8
 24 NEARUSDT       BREAKOUT UP        база   -129.0  пик    +14.3     -0.5   -132.7     -0.5   -132.7   -128.9   -128.9
 25 TAOUSDT        BB M-TOP           база    -79.4  пик    +42.9     +0.0    -92.0     +0.0    -92.0    -78.6    -78.6
 26 WIFUSDT        BB M-TOP           база    -72.6  пик    +10.8    -69.5    -69.5    -69.5    -69.5    -69.5    -69.5
 28 TIAUSDT        ORB UP             база   -138.3  пик    +62.2     -0.0     -0.0     -0.0     -0.0     -0.0   -114.9
 29 IOUSDT         BREAKOUT UP        база   -113.8  пик    +85.5     -0.0     -0.0     -0.0     -0.0     -0.0     -0.0
 31 PONSUSDT       BB M-TOP           база    -53.6  пик    +38.7     +0.0    -67.4    -57.5    -57.5    -57.5    -57.5
 32 SOLUSDT        PO3 SHORT          база    -21.6  пик     +5.6    -25.6    -25.6    -25.6    -25.6    -25.6    -25.6
 33 DOGEUSDT       PO3 SHORT          база    -13.6  пик     -0.0    -17.6    -17.6    -17.6    -17.6    -17.6    -17.6
 34 ETHUSDT        SILVER BULLET SHORT база    -20.2  пик     +9.6    -24.2    -24.2    -24.2    -24.2    -24.2    -24.2
 37 1000SHIBUSDT   BB W-BOTTOM        база    -38.4  пик     +1.5    -38.3    -38.3    -38.3    -38.3    -38.3    -38.3
 38 MARSCOINUSDT   ORB DOWN           база   +112.2  пик   +129.2     +0.0     +0.0   +112.3   +112.3   +112.3   +112.3
 39 AZTECUSDT      BB W-BOTTOM        база   -116.2  пик    +29.1     -0.0     -0.0   -119.9   -119.9   -119.9   -119.9
 40 SXTUSDT        OI SIGNAL LONG     база   -114.7  пик     +4.5   -113.4   -113.4   -113.4   -113.4   -113.4   -113.4
 41 ENAUSDT        BB W-BOTTOM        база   -110.9  пик     -2.1   -101.8   -101.8   -101.8   -101.8   -101.8   -101.8
 44 OPUSDT         AUCTION LONG       база    -27.6  пик    -10.3    -93.3    -93.3    -93.3    -93.3    -93.3    -93.3
 45 SKYUSDT        AUCTION LONG       база    -21.0  пик    +73.8     -0.0    -41.3     -0.0    -29.8    -21.0    -21.0
 46 ONEUSDT        BB W-BOTTOM        база    +38.5  пик   +113.7    +34.5    +34.5    +34.5    +34.5    +34.5    +34.5
 47 CFXUSDT        BB W-BOTTOM        база    -43.6  пик    +90.7     -0.0     -0.0     -0.0    -69.2     -0.0    -61.1
 48 HBARUSDT       BB W-BOTTOM        база    -66.9  пик     -3.1    -51.0    -51.0    -51.0    -51.0    -51.0    -51.0
 49 ACEUSDT        BB W-BOTTOM        база   -146.7  пик    -22.9   -105.1   -105.1   -105.1   -105.1   -105.1   -105.1
 52 OGNUSDT        OI SIGNAL LONG     база    +17.4  пик    +75.9     -7.4    -25.0     -0.0     -0.0     -0.0     -0.0
 53 ZECUSDT        AUCTION LONG       база   -109.5  пик    +15.4   -103.0   -103.0   -103.0   -103.0   -103.0   -103.0
 54 SOLUSDT        BB W-BOTTOM        база    -78.0  пик    +16.7    -73.1    -73.1    -73.1    -73.1    -73.1    -73.1
 55 HYPEUSDT       BREAKOUT DOWN      база     -0.6  пик     +4.7     -0.6     -0.6     -0.6     -0.6     -0.6     -0.6
```

**Total actual: -1891.3 USDT**

- BE at +0.5%, re-entry x0: -840.7 USDT (+1050.6 vs actual)
- BE at +0.5%, re-entry x2: -1181.7 USDT (+709.5 vs actual)
- BE at +1.0%, re-entry x0: -886.4 USDT (+1004.8 vs actual)
- BE at +1.0%, re-entry x2: -1274.1 USDT (+617.2 vs actual)
- BE at +2.0%, re-entry x0: -1080.4 USDT (+810.8 vs actual)
- BE at +2.0%, re-entry x2: -1945.0 USDT (-53.8 vs actual)
