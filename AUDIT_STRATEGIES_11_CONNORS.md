# Audit 11 — Connors RSI(2)

Status: executable scope narrowed to the published long RSI2X rule; non-published variants no longer create executable
strategy cards.

## Sources and formal rules

* [StockCharts RSI(2) strategy](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2): above 200-day SMA, RSI(2) extreme, exit on first close above 5-day SMA.
* [Alternative implementation](https://cleartape.ai/strategies/rsi-2-strategy): same daily trend filter, RSI(2) oversold entry and SMA5 close exit.

## Code comparison

`strategies/classic.py:369-418` computes daily Wilder RSI(2), SMA200 and SMA5. The `first='orig'` path implements the
published long condition (`c > sma200 and r < connors_rsi_low`) and records SMA5 exit. The regular path implements a
cross-back variant; mirrored short variants are also generated.

## Confirmed violation and fix

`ConnorsStrategy` previously registered four setups (`RSI2 LONG/SHORT`, `RSI2X LONG/SHORT`) under one executable
method, although the source rule audited here is the long RSI2X system. This made cross-back and mirrored-short variants
trade under the published Connors name. The registry now exposes only `RSI2X LONG`; the alternatives remain callable for
research but cannot create executable cards. Historical regression evidence (the test suite was later removed): `tests/test_connors_method.py` asserts the three variants are
not registered.

The plan keeps Connors' no-stop/SMA5 exit semantics (`classic_strategies.py:103-124`); the ATR field is measurement only.

## Residual doubts

The source commonly uses RSI<5 or <10 variants; the project parameter 5 is explicit. Asset-universe and crypto-vs-stock
adaptation are not canonical Connors rules and remain separate assumptions.
