"""
Task 3 of docs/CLOUD_TASKS.md: the bot's indicator formulas against TA-Lib on the same input.

Inputs: 20 of the most liquid USDT perpetuals, 15m and 1h futures candles of the Binance archive (2026-04 .. 2026-09),
4h / daily / weekly built from the 1h / daily archive candles for strategies/bias.py.
For every coin x timeframe, 150 end points evenly spread over the series; at each end point both implementations get
the SAME window - the length the bot feeds them live:
  - indicators.compute_indicators_batch: 99 candles (CONFIG rest_lookback_candles, the live 15m frame) and 499;
  - strategies/ind_panel.indicators: 499 candles (long_history_candles, fetcher.indicator_panel);
  - strategies/bias: 4h ADX on 200 candles (h1_candles / 4h), daily EMA50 on 370, weekly EMA20 on 60.
The last row's value is compared (relative difference |ours - talib| / max(|talib|, 1e-12)).
Intended differences (docs/CLOUD_TASKS.md, not bugs): ATR = simple 14-candle mean of true ranges in indicators.py,
Bollinger population std, warm-up rows. They are checked against their intended definition instead (SMA(TRANGE, 14),
BBANDS with population std = TA-Lib's own).
Also: how often the entry panel's boolean rules (strategies/ind_panel.rules) change when the TA-Lib value is used.
Output: research/talib_check.md. Changes nothing in the bot.
"""
import os
from datetime import date

import numpy as np
import polars as pl
import talib

from history import Archive
from indicators import compute_indicators_batch
from strategies import bias as htf
from strategies.ind_panel import indicators as panel_ind, rules

COINS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT', '1000PEPEUSDT', 'SUIUSDT', 'BNBUSDT', 'ADAUSDT',
         'LINKUSDT', 'AVAXUSDT', 'LTCUSDT', 'WLDUSDT', 'AAVEUSDT', 'NEARUSDT', 'UNIUSDT', 'XLMUSDT', 'BCHUSDT',
         'DOTUSDT', 'ARBUSDT']
START, END = date(2026, 4, 1), date(2026, 9, 30)
N_ENDS = 150


def rel(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = np.isfinite(a) & np.isfinite(b)
    return np.abs(a[ok] - b[ok]) / np.maximum(np.abs(b[ok]), 1e-12), int((~ok).sum())


def frame(k):
    n = len(k)
    return pl.DataFrame({'timestamp': k[:, 0].astype(np.int64), 'open': k[:, 1], 'high': k[:, 2], 'low': k[:, 3],
                         'close': k[:, 4], 'volume': k[:, 5] / k[:, 4], 'quote_volume': k[:, 5],
                         'taker_delta': np.zeros(n), 'open_interest': np.ones(n)})


def talib_set(k):
    h, l, c, v = k[:, 2], k[:, 3], k[:, 4], k[:, 5]
    up, mid, lo = talib.BBANDS(c, 20, 2, 2, 0)
    macd, sig, hist = talib.MACD(c, 12, 26, 9)
    sk, sd = talib.STOCH(h, l, c, 14, 3, 0, 3, 0)
    return dict(e20=talib.EMA(c, 20), e50=talib.EMA(c, 50), e200=talib.EMA(c, 200), rsi=talib.RSI(c, 14), hist=hist,
                adx=talib.ADX(h, l, c, 14), pdi=talib.PLUS_DI(h, l, c, 14), mdi=talib.MINUS_DI(h, l, c, 14),
                atr_wilder=talib.ATR(h, l, c, 14), atr_sma=talib.SMA(talib.TRANGE(h, l, c), 14),
                stoch_k=sk, stoch_d=sd, pctb=(c - lo) / (up - lo), bb_upper=up, bb_lower=lo,
                mfi=talib.MFI(h, l, c, v, 14), obv=talib.OBV(c, v), cci=talib.CCI(h, l, c, 20))


def main():
    arch = Archive(rate_bytes=2e7)
    res = {}            # (module, indicator, window) -> list of rel diffs
    nan_mismatch = {}
    flips = {}          # rule -> [changed, total]

    def add(key, ours, ref):
        d, bad = rel(ours, ref)
        res.setdefault(key, []).extend(d.tolist())
        nan_mismatch[key] = nan_mismatch.get(key, 0) + bad

    for sym in COINS:
        for tf in ('15m', '1h'):
            k = arch.klines_ohlc('futures', sym, tf, START, END)
            if len(k) < 600:
                print(sym, tf, 'short', len(k))
                continue
            ends = np.linspace(500, len(k), N_ENDS).astype(int)
            for e in ends:
                # ind_panel, 499 candles
                w = k[e - 499:e]
                ours, ref = panel_ind(w), talib_set(w)
                for name in ('e20', 'e50', 'e200', 'rsi', 'hist', 'adx', 'pdi', 'mdi', 'stoch_k', 'stoch_d', 'pctb',
                             'mfi', 'cci'):
                    add(('ind_panel', name, tf, 499), ours[name][-1:], ref[name][-1:])
                # obv: the rules read only its 10-candle slope
                add(('ind_panel', 'obv_slope10', tf, 499), [ours['obv'][-1] - ours['obv'][-11]],
                    [ref['obv'][-1] - ref['obv'][-11]])
                # boolean rules with the TA-Lib values substituted
                sub = dict(ours)
                for name in ('e20', 'e50', 'e200', 'rsi', 'hist', 'adx', 'pdi', 'mdi', 'stoch_k', 'stoch_d', 'pctb',
                             'mfi', 'cci', 'obv'):
                    sub[name] = ref[name]
                for d in (1, -1):
                    a, b = rules(ours, d), rules(sub, d)
                    for rname in a:
                        x, y = np.asarray(a[rname])[-1], np.asarray(b[rname])[-1]
                        f = flips.setdefault(rname, [0, 0])
                        f[0] += int(bool(x) != bool(y))
                        f[1] += 1
                # indicators.py on the live 15m frame length (99) and on 499
                for L in (99, 499):
                    w = k[e - L:e]
                    out = compute_indicators_batch({'X': frame(w)}, {})
                    ref = talib_set(w)
                    add(('indicators', 'adx', tf, L), out['adx'].to_numpy()[-1:], ref['adx'][-1:])
                    add(('indicators', 'atr (vs SMA(TRANGE,14))', tf, L), out['atr'].to_numpy()[-1:], ref['atr_sma'][-1:])
                    add(('indicators', 'bb_upper', tf, L), out['bb_upper'].to_numpy()[-1:], ref['bb_upper'][-1:])
                    add(('indicators', 'bb_lower', tf, L), out['bb_lower'].to_numpy()[-1:], ref['bb_lower'][-1:])
        # strategies/bias.py: 4h ADX (200 candles of 4h from 1h), daily EMA50 (370), weekly EMA20 (60)
        h1 = arch.klines_ohlc('futures', sym, '1h', date(2025, 10, 1), END)
        t4 = (h1[:, 0] // 14_400_000).astype(np.int64)
        _, first = np.unique(t4, return_index=True)
        h4 = np.array([[h1[a, 0], h1[a, 1], h1[a:b, 2].max(), h1[a:b, 3].min(), h1[b - 1, 4], h1[a:b, 5].sum()]
                       for a, b in zip(first, list(first[1:]) + [len(h1)]) if b - a == 4])
        for e in np.linspace(200, len(h4), 60).astype(int):
            w = h4[e - 200:e]
            add(('bias', 'adx4 (_adx)', '4h', 200), [htf._adx(w)], talib.ADX(w[:, 2], w[:, 3], w[:, 4], 14)[-1:])
        d1 = arch.klines_ohlc('futures', sym, '1d', date(2024, 6, 1), END)
        for e in np.linspace(370, len(d1), 30).astype(int):
            c = d1[e - 370:e, 4]
            add(('bias', 'ema50 daily (ind_panel.ema)', '1d', 370), htf.ema(c, 50)[-1:], talib.EMA(c, 50)[-1:])
        # weekly: 60 weekly closes (the live w1), EMA20
        wk = d1[:, 4][6::7]
        for e in np.linspace(60, len(wk), 10).astype(int):
            c = wk[e - 60:e]
            if len(c) == 60:
                add(('bias', 'ema20 weekly (ind_panel.ema)', '1w', 60), htf.ema(c, 20)[-1:], talib.EMA(c, 20)[-1:])
        print(sym, 'done', flush=True)

    rows = []
    for key, d in sorted(res.items()):
        d = np.asarray(d)
        rows.append((*key, len(d), float(np.median(d)) if len(d) else np.nan, float(np.percentile(d, 95)) if len(d) else np.nan,
                     float(d.max()) if len(d) else np.nan, float((d > 1e-6).mean()) if len(d) else np.nan, nan_mismatch[key]))
    out = ['# Indicator formulas vs TA-Lib (Task 3)', '',
           f'TA-Lib {talib.__version__} (python `ta-lib` wheel; polars-talib bundles the same C library). '
           f'{len(COINS)} coins, futures archive {START} .. {END}, {N_ENDS} end points per coin x timeframe; both '
           'implementations get the same window, the last value is compared. Generated by `research_talib_check.py`.', '',
           '| module | indicator | tf | window | n | median rel | p95 rel | max rel | share > 1e-6 | NaN on one side |',
           '|---|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        out.append(f'| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]:.2e} | {r[6]:.2e} | {r[7]:.2e} | {r[8]:.1%} | {r[9]} |')
    out += ['', '## Entry-panel rules flipped by the TA-Lib values (last candle, both directions, 15m + 1h)', '',
            '| rule | changed | of | share |', '|---|---:|---:|---:|']
    for rname, (a, b) in sorted(flips.items(), key=lambda x: -x[1][0]):
        out.append(f'| {rname} | {a} | {b} | {a / max(b, 1):.1%} |')
    path = os.path.join('research', 'talib_check_data.md')
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(out) + '\n')
    print('\n'.join(out))


if __name__ == '__main__':
    main()
