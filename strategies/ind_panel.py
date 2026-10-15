"""
Classic indicator panel of one coin at one moment (strategies.confirm journals it on every entry as `_ind`; the archive
study research_indicator_confirms.py uses the same functions): EMA 20 / 50 / 200 and the EMA50 slope (Murphy, Elder),
RSI 14 (Wilder), MACD 12 / 26 / 9 (Appel), ADX 14 with +DI / -DI (Wilder), stochastic 14 / 3 (Lane), Bollinger %B and
band width (Bollinger), MFI 14 (Quong & Soudack), OBV (Granville), CCI 20 (Lambert), ATR rank, relative volume.
`rules(ind, d)` turns them into booleans "the indicator agrees with a trade in direction d"; which of them CONFIRM an
entry is decided by research/indicator_confirms.md (pre-registered), not by this module.
"""
import numpy as np


def ema(x: np.ndarray, n: int) -> np.ndarray:
    """EMA seeded with the SMA of the first n values (TA-Lib / Appel; NaN before). Seeding with x[0] left EMA200 on the
    panel's 499 candles up to 0.4% off (research/talib_check.md). Shorter than n: seeded with x[0] (best effort)."""
    x = np.asarray(x, dtype=float)
    a = 2.0 / (n + 1)
    if len(x) < n:
        out = np.empty_like(x)
        if len(x):
            out[0] = x[0]
            for i in range(1, len(x)):
                out[i] = a * x[i] + (1 - a) * out[i - 1]
        return out
    out = np.full_like(x, np.nan)
    finite = np.flatnonzero(np.isfinite(x))
    s = int(finite[0]) if len(finite) else len(x)        # leading NaNs (an EMA of an EMA, e.g. MACD's signal)
    if len(x) - s < n:
        return out
    out[s + n - 1] = x[s:s + n].mean()
    for i in range(s + n, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def rma(x: np.ndarray, n: int) -> np.ndarray:
    """Wilder's smoothing (RSI, ADX, ATR as their authors define them)."""
    out = np.full_like(x, np.nan)
    if len(x) < n:
        return out
    out[n - 1] = np.nanmean(x[:n])
    for i in range(n, len(x)):
        out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out


def sma(x: np.ndarray, n: int) -> np.ndarray:
    c = np.cumsum(np.insert(x, 0, 0.0))
    out = np.full_like(x, np.nan)
    out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def rolling_std(x: np.ndarray, n: int) -> np.ndarray:
    m = sma(x, n)
    m2 = sma(x * x, n)
    return np.sqrt(np.maximum(m2 - m * m, 0.0))


def rolling_max(x, n):
    from numpy.lib.stride_tricks import sliding_window_view
    out = np.full_like(x, np.nan)
    out[n - 1:] = sliding_window_view(x, n).max(axis=1)
    return out


def rolling_min(x, n):
    from numpy.lib.stride_tricks import sliding_window_view
    out = np.full_like(x, np.nan)
    out[n - 1:] = sliding_window_view(x, n).min(axis=1)
    return out


def pct_rank(x: np.ndarray, n: int) -> np.ndarray:
    """Share of the last n values below the current one."""
    from numpy.lib.stride_tricks import sliding_window_view
    out = np.full_like(x, np.nan)
    if len(x) >= n:
        w = sliding_window_view(x, n)
        out[n - 1:] = (w < w[:, -1:]).mean(axis=1)
    return out


def indicators(k: np.ndarray) -> dict:
    """k: [open_ms, o, h, l, c, quote_volume]. Arrays aligned with k (value at candle i uses candles <= i)."""
    h, l, c, v = k[:, 2], k[:, 3], k[:, 4], k[:, 5]
    prev_c = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(abs(h - prev_c), abs(l - prev_c)))
    up, dn = h - np.concatenate(([h[0]], h[:-1])), np.concatenate(([l[0]], l[:-1])) - l
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr = rma(tr, 14)
    pdi = 100 * rma(plus_dm, 14) / atr
    mdi = 100 * rma(minus_dm, 14) / atr
    dx = 100 * abs(pdi - mdi) / np.maximum(pdi + mdi, 1e-12)
    adx = rma(np.nan_to_num(dx), 14)
    delta = np.diff(c, prepend=c[0])
    rs = rma(np.maximum(delta, 0), 14) / np.maximum(rma(np.maximum(-delta, 0), 14), 1e-12)
    rsi = 100 - 100 / (1 + rs)
    macd = ema(c, 12) - ema(c, 26)
    hist = macd - ema(macd, 9)
    lo14, hi14 = rolling_min(l, 14), rolling_max(h, 14)
    k_raw = 100 * (c - lo14) / np.maximum(hi14 - lo14, 1e-12)
    stoch_k = sma(np.nan_to_num(k_raw, nan=50.0), 3)
    stoch_d = sma(np.nan_to_num(stoch_k, nan=50.0), 3)
    mid, sd = sma(c, 20), rolling_std(c, 20)
    pctb = (c - (mid - 2 * sd)) / np.maximum(4 * sd, 1e-12)
    bbw = 4 * sd / np.maximum(mid, 1e-12)
    tp = (h + l + c) / 3
    mf = tp * v
    # Quong & Soudack / TA-Lib: an unchanged typical price is neither positive nor negative flow (it was negative)
    tp_diff = np.diff(tp, prepend=tp[0])
    tp_diff[np.abs(tp_diff) <= 1e-12 * np.abs(tp)] = 0.0      # (h + l + c) / 3 rounding noise of equal prices
    pos, neg = sma(np.where(tp_diff > 0, mf, 0.0), 14), sma(np.where(tp_diff < 0, mf, 0.0), 14)
    mfi = 100 - 100 / (1 + pos / np.maximum(neg, 1e-12))
    obv = np.cumsum(np.sign(delta) * v)
    # Lambert: the mean deviation of the window's typical prices from the CURRENT window's mean (each deviation from
    # its own window's mean read cci_extreme differently in 11% of cases - research/talib_check.md)
    tp_sma = sma(tp, 20)
    mean_dev = np.full_like(tp, np.nan)
    if len(tp) >= 20:
        from numpy.lib.stride_tricks import sliding_window_view
        mean_dev[19:] = np.abs(sliding_window_view(tp, 20) - tp_sma[19:, None]).mean(axis=1)
    cci = (tp - tp_sma) / np.maximum(0.015 * mean_dev, 1e-12)
    e20, e50, e200 = ema(c, 20), ema(c, 50), ema(c, 200)
    return dict(c=c, l=l, h=h, v=v, e20=e20, e50=e50, e200=e200, rsi=rsi, hist=hist, adx=adx, pdi=pdi, mdi=mdi,
                stoch_k=stoch_k, stoch_d=stoch_d, pctb=pctb, bbw_rank=pct_rank(bbw, 125), mfi=mfi, obv=obv,
                cci=cci, atr_rank=pct_rank(atr, 125), rvol=v / np.maximum(sma(v, 20), 1e-12))


def lag(x: np.ndarray, n: int) -> np.ndarray:
    return np.concatenate((np.full(n, np.nan), x[:-n]))


def any_last(x: np.ndarray, n: int) -> np.ndarray:
    """True when x was True on any of the last n candles."""
    out = x.copy()
    for j in range(1, n):
        out = out | np.concatenate((np.zeros(j, bool), x[:-j]))
    return out


def rules(ind: dict, d: int) -> dict:
    """Each classic confirmation as a boolean array for direction d (+1 long / -1 short)."""
    c, rsi, hist = ind['c'], ind['rsi'], ind['hist']
    long = d > 0
    sgn = 1 if long else -1
    e50_slope = ind['e50'] - lag(ind['e50'], 10)
    lo14, hi14 = rolling_min(ind['l'], 14), rolling_max(ind['h'], 14)
    prev_lo, prev_hi = lag(rolling_min(ind['l'], 14), 14), lag(rolling_max(ind['h'], 14), 14)
    rsi_prev_lo = lag(rolling_min(np.nan_to_num(rsi, nan=50), 14), 14)
    rsi_prev_hi = lag(rolling_max(np.nan_to_num(rsi, nan=50), 14), 14)
    rsi_lo, rsi_hi = rolling_min(np.nan_to_num(rsi, nan=50), 14), rolling_max(np.nan_to_num(rsi, nan=50), 14)
    k, dd = ind['stoch_k'], ind['stoch_d']
    cross_up = (k > dd) & (lag(k, 1) <= lag(dd, 1))
    cross_dn = (k < dd) & (lag(k, 1) >= lag(dd, 1))
    obv_slope = ind['obv'] - lag(ind['obv'], 10)
    return {
        # trend (Murphy, Elder): the trade is with the trend
        'ema200_side': sgn * (c - ind['e200']) > 0,
        'ema_stack': (c > ind['e50']) & (ind['e50'] > ind['e200']) if long else (c < ind['e50']) & (ind['e50'] < ind['e200']),
        'ema50_slope': sgn * e50_slope > 0,
        'ema20_side': sgn * (c - ind['e20']) > 0,
        'adx_trend': (ind['adx'] > 25) & (sgn * (ind['pdi'] - ind['mdi']) > 0),
        # momentum (Appel, Wilder): momentum agrees
        'macd_hist': sgn * hist > 0,
        'macd_turn': sgn * (hist - lag(hist, 1)) > 0,
        'rsi_50': sgn * (rsi - 50) > 0,
        # reversal / exhaustion (Wilder, Lane, Lambert, Bollinger, Quong & Soudack): the other side is stretched
        'rsi_extreme': any_last(rsi < 30, 3) if long else any_last(rsi > 70, 3),
        'rsi_divergence': (lo14 < prev_lo) & (rsi_lo > rsi_prev_lo) if long else (hi14 > prev_hi) & (rsi_hi < rsi_prev_hi),
        'stoch_cross': any_last(cross_up & (k < 20), 3) if long else any_last(cross_dn & (k > 80), 3),
        'bb_outside': any_last(ind['pctb'] < 0, 3) if long else any_last(ind['pctb'] > 1, 3),
        'mfi_extreme': any_last(ind['mfi'] < 20, 3) if long else any_last(ind['mfi'] > 80, 3),
        'cci_extreme': any_last(ind['cci'] < -100, 3) if long else any_last(ind['cci'] > 100, 3),
        'adx_range': ind['adx'] < 20,
        # volume (Granville, Quong & Soudack)
        'rvol_1_5': ind['rvol'] >= 1.5,
        'obv_slope': sgn * obv_slope > 0,
        'mfi_50': sgn * (ind['mfi'] - 50) > 0,
        # volatility state (Bollinger squeeze, ATR)
        'squeeze': ind['bbw_rank'] < 0.2,
        'atr_high': ind['atr_rank'] > 0.5,
    }



_IND_CACHE: dict = {}          # (key, last candle ts, count) -> indicators(): one computation per closed candle


def panel(candles, direction: int, key=None) -> dict:
    """{rule: bool} on the LAST of `candles` ([ts, o, h, l, c, quote_volume, ...], closed, oldest first); {} with
    fewer than 250 candles (EMA 200 needs its warm-up). With a key (symbol, timeframe) the indicator arrays are cached
    until the next candle closes: every card of a coin asked for them again (watchdog: 2s loop stalls in rolling_min)."""
    if len(candles) < 250:
        return {}
    ck = (key, candles[-1][0], len(candles)) if key is not None else None
    ind = _IND_CACHE.get(ck) if ck is not None else None
    if ind is None:
        k = np.asarray([row[:6] for row in candles], dtype=np.float64)
        ind = indicators(k)
        if ck is not None:
            if len(_IND_CACHE) > 600:                       # ~150 coins x 2 timeframes x 2 candles
                _IND_CACHE.clear()
            _IND_CACHE[ck] = ind
    out = {}
    for name, arr in rules(ind, direction).items():
        value = np.asarray(arr)[-1]
        out[name] = bool(value) if value == value else None       # NaN -> None
    return out
