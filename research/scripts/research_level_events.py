"""
Level-event dataset (eng-57, step 1 of the level methodology rework; docs/AUDIT_parameters.md sections 9-11): EVERY
approach of price to EVERY level, with the context a trader reads at that moment, and what happened after - for real
levels and for placebo levels. Pre-registered here, before any result: the features and outcomes below are fixed;
step 2 (the analysis) tests them against the placebo with both halves and a false-discovery control.

Why: research_level_weights / research_confluence / research_level_mechanics found no hold beyond placebo, but they
took only the FIRST test, levels up to 1h / the previous day, outcomes on a 15m-ATR scale (a daily level's normal
pierce is ~0.9%) and placebos 0.3-1.5% away (inside a daily level's zone). Literature: Osler (2000, NY Fed) 60.8% vs
56.2% bounces at published levels; Chung & Bellotti (2021) bounce odds rise with previous bounces (memory).

LEVELS (each known only from its confirming candle; 15m candles from the Binance archive with taker-buy volume;
1h / 4h / 1d / 1w built from them):
  swing_<tf>     3 x 3 pivot highs / lows of 15m, 1h, 4h, 1d candles (as research_overshoot for 15m / 1h)
  equal          two 1h pivots of one side within 0.1%
  pdhl / pwhl    previous UTC day / week high and low
  round          round numbers (a tenth of the price's order of magnitude)
  fvg_<tf>       fair value gaps of 15m, 1h, 4h, 1d (near edge); ob_<tf> / breaker_<tf> of 1h, 4h, 1d
  poc / va / hvn / lvn   the UTC day's volume profile (zones.volume_profile)
  A level lives until it BREAKS (two consecutive 15m closes beyond it) or 30 days.
APPROACH: a 15m candle whose extreme comes within BAND = 0.25 x ATR(15m) of the level, after price had closed at least
1 ATR of the level's timeframe (capped at the 4h ATR) away on the level's side (the first approach needs the start beyond that distance).
Every approach is an event; `touch` = its number (1 = the first).

FEATURES (measured at the approach candle's open, i.e. from the candles before it):
  level   kind, tf, side (+1 resistance), touch, prior_bounces (earlier approaches of this level that ended front /
          wick / close1), age_h, width_atr (zone width / ATR of its tf; 0 for lines), origin_atr (the move that made
          the level: from the pivot / the gap's displacement over the next 3 candles of its tf, in its ATR),
          origin_vol (that move's volume / the average of 20 candles before it)
  approach  into_atr (net move toward the level over the last 20 candles of the level's tf, in its ATR; > 0 = trending
          into it), speed_atr (last 4 15m candles' move toward it / ATR15), run_atr (move toward it since the last
          15m pivot on the other side / ATR15), vol_ratio (volume of the last 4 15m candles / their 96-candle
          average), delta (taker-buy share of the last 4 15m candles - 0.5, signed: > 0 = buyers into a resistance)
  location  range_pos (price in the last 20 daily candles' range, 0 low .. 1 high), room_atr (distance to the nearest
          known 1h pivot on the bounce side beyond the level... i.e. the next opposite level, in ATR of the level's tf;
          capped at 50), ema_dev (close - EMA50 of 1h) / ATR1h
  market  trend_1d / trend_4h ((close - EMA20 of that tf) / its ATR), er_4h (Kaufman efficiency of the last 20 4h
          closes: 1 = straight trend, 0 = chop), vol_regime (ATR15 / its 30-day median), btc_1h (BTC's 1h return
          signed toward the level: > 0 = BTC also moving into it), hour (UTC)
  liquidity  swept (1 when the last 8 15m candles traded beyond a 15m pivot of the same side lying between the
          approach start and the level - a liquidity grab on the way in), oi_1h (OI change over the hour before,
          from the archive's 5-minute metrics; NaN without them)
OUTCOMES (from the approach candle; horizon H by the level's tf: 15m 4h, 1h 12h, 4h 24h, 1d 3 days, 1w 7 days):
  mech   front / wick / close1 / failed / break within 8 15m candles (research_level_mechanics)
  bounce trade  a limit at the band's near edge, stop beyond the level by its kind's measured p80 pierce (+ the zone
          width), targets 1 / 2 / 3 R: b1 / b2 / b3 = +1 target first, -1 stop first, 0 neither; b_mfe / b_mae in R
  break trade   a stop entry beyond the level by the p80 pierce, stop back at the band's near edge: k1 / k2 / k3,
          k_mfe / k_mae in R
PLACEBO: each level shifted 1-2 x its kind's p90 pierce (beyond its own zone), same side and time, same rules.

    python research_level_events.py --months 12 --limit 60 --workers 2
Writes data/level_events/<SYMBOL>.parquet (one row per approach; `placebo` 0 / 1).
"""
import os as _os, sys as _sys; _sys.path[:0] = [_os.path.dirname(_os.path.abspath(__file__)), _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..', '..'))]  # noqa: E401,E702 - bot modules + sibling scripts
import argparse
import json
import logging
import math
import os
import random
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List

import numpy as np

M15 = 900_000
HOUR = 3_600_000
DAY = 86_400_000
TF_MS = {'15m': M15, '1h': HOUR, '4h': 4 * HOUR, '1d': DAY, '1w': 7 * DAY}
H_BARS = {'15m': 16, '1h': 48, '4h': 96, '1d': 288, '1w': 672}       # horizon in 15m candles
BAND = 0.25
K = 8
LIFE = 30 * 96
OUT_DIR = os.path.join('data', 'level_events')


# ------------------------------------------------------------------------------------------------ data

def load_15m(arch, symbol: str, start: date, end: date) -> np.ndarray:
    """[ts, o, h, l, c, quote_vol, taker_buy_quote] 15m candles of the COMPLETE months in [start, end]."""
    months, _ = arch.periods(date(start.year, start.month, 1), end)
    out = []
    for m in months:
        data = arch._fetch(f"futures/um/monthly/klines/{symbol}/15m/{symbol}-15m-{m}.zip")
        if data is None:
            continue
        for r in arch._rows(data):
            try:
                ts = float(r[0])
            except ValueError:
                continue
            ts = ts / 1000.0 if ts > 1e14 else ts
            out.append((ts, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[7]), float(r[10])))
    if not out:
        return np.empty((0, 7))
    a = np.asarray(out, dtype=float)
    a = a[np.argsort(a[:, 0], kind='stable')]
    return a[np.concatenate(([True], np.diff(a[:, 0]) > 0))]


def resample(c15: np.ndarray, tf_ms: int) -> np.ndarray:
    """Complete candles of tf from 15m ones: [ts, o, h, l, c, v, buy]."""
    if tf_ms == M15:
        return c15
    per = tf_ms // M15
    key = (c15[:, 0] // tf_ms).astype(np.int64) if tf_ms < 7 * DAY else ((c15[:, 0] + 3 * DAY) // tf_ms).astype(np.int64)
    starts = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
    rows = []
    for a, b in zip(starts, list(starts[1:]) + [len(c15)]):
        if b - a == per:
            rows.append((c15[a, 0], c15[a, 1], c15[a:b, 2].max(), c15[a:b, 3].min(), c15[b - 1, 4],
                         c15[a:b, 5].sum(), c15[a:b, 6].sum()))
    return np.asarray(rows, dtype=float) if rows else np.empty((0, 7))


def atr_of(c: np.ndarray, n: int = 14) -> np.ndarray:
    if not len(c):
        return np.empty(0)
    h, l, cl = c[:, 2], c[:, 3], c[:, 4]
    prev = np.r_[cl[0], cl[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))
    return np.convolve(tr, np.ones(n) / n, mode='full')[:len(tr)]


def ema_of(x: np.ndarray, n: int) -> np.ndarray:
    out = np.empty_like(x)
    a = 2 / (n + 1)
    acc = x[0] if len(x) else 0.0
    for i, v in enumerate(x):
        acc = a * v + (1 - a) * acc
        out[i] = acc
    return out


def aligned(ts15: np.ndarray, c: np.ndarray, tf_ms: int, values: np.ndarray) -> np.ndarray:
    """values of the last tf candle CLOSED at each 15m candle's open (NaN before the first)."""
    if not len(c):
        return np.full(len(ts15), np.nan)
    closes = c[:, 0] + tf_ms
    idx = np.searchsorted(closes, ts15, side='right') - 1
    out = np.full(len(ts15), np.nan)
    ok = idx >= 0
    out[ok] = values[idx[ok]]
    return out


# ------------------------------------------------------------------------------------------------ levels

def pivots(h, l, k=3):
    out = []
    for i in range(k, len(h) - k):
        if h[i] == h[i - k:i + k + 1].max() and h[i] > h[i - k:i].max():
            out.append((i, h[i], 1))
        if l[i] == l[i - k:i + k + 1].min() and l[i] < l[i - k:i].min():
            out.append((i, l[i], -1))
    return out


def level_list(c15: np.ndarray, tfc: Dict[str, np.ndarray], atrs: Dict[str, np.ndarray]) -> List[dict]:
    """Every level as {known, price, side, kind, tf, width, origin_atr, origin_vol}."""
    from research_level_weights import fvg_levels, ob_levels
    out = []

    def origin(c, a, i, d):
        """The move away from candle i over the next 3 candles in its ATR and that move's volume ratio."""
        j = min(len(c) - 1, i + 3)
        if not a[i] > 0:
            return math.nan, math.nan
        move = (c[i, 2] - c[i + 1:j + 1, 3].min()) if d > 0 else (c[i + 1:j + 1, 2].max() - c[i, 3])
        base = c[max(0, i - 20):i, 5].mean() if i > 0 else math.nan
        return move / a[i], (c[i + 1:j + 1, 5].mean() / base) if base else math.nan

    for tf in ('15m', '1h', '4h', '1d'):
        c, a = tfc[tf], atrs[tf]
        if len(c) < 10:
            continue
        for i, p, s in pivots(c[:, 2], c[:, 3]):
            if i + 3 < len(c):
                om, ov = origin(c, a, i, s)
                out.append(dict(known=c[i + 3, 0] + TF_MS[tf], price=p, side=s, kind=f'swing_{tf}', tf=tf, width=0.0,
                                origin_atr=om, origin_vol=ov))
    c = tfc['1h']
    piv = pivots(c[:, 2], c[:, 3])
    last = {1: [], -1: []}
    for i, p, s in piv:
        for j, q in last[s][-10:]:
            if abs(p / q - 1) <= 0.001:
                out.append(dict(known=c[i + 3, 0] + HOUR if i + 3 < len(c) else c[-1, 0] + HOUR,
                                price=max(p, q) if s > 0 else min(p, q), side=s, kind='equal', tf='1h', width=0.0,
                                origin_atr=math.nan, origin_vol=math.nan))
                break
        last[s].append((i, p))
    for tf, kind in (('1d', 'pdhl'), ('1w', 'pwhl')):
        c = tfc[tf]
        for i in range(len(c)):
            k = c[i, 0] + TF_MS[tf]
            out.append(dict(known=k, price=c[i, 2], side=1, kind=kind, tf=tf, width=0.0, origin_atr=math.nan,
                            origin_vol=math.nan))
            out.append(dict(known=k, price=c[i, 3], side=-1, kind=kind, tf=tf, width=0.0, origin_atr=math.nan,
                            origin_vol=math.nan))
    d1 = tfc['1d']
    for i in range(len(d1)):
        close = d1[i, 4]
        step = 10 ** (math.floor(math.log10(close)) - 1)
        base = math.floor(close / step) * step
        for k in (-2, -1, 1, 2, 3):
            p = base + k * step
            out.append(dict(known=d1[i, 0] + DAY, price=p, side=1 if p > close else -1, kind='round', tf='1d',
                            width=0.0, origin_atr=math.nan, origin_vol=math.nan))
    for tf in ('15m', '1h', '4h', '1d'):
        c, a = tfc[tf], atrs[tf]
        if len(c) < 15:
            continue
        ts = c[:, 0]
        for known, price, side, _ in fvg_levels(c, TF_MS[tf], f'fvg_{tf}'):
            i = int(np.searchsorted(ts, known - TF_MS[tf])) - 1          # the gap's middle candle
            far = c[i - 1, 2] if side < 0 else c[i - 1, 3]
            width = abs(price - far) / a[i] if 0 <= i < len(a) and a[i] > 0 else math.nan
            disp = (c[i, 2] - c[i, 3]) / a[i] if 0 <= i < len(a) and a[i] > 0 else math.nan
            vol = c[i, 5] / c[max(0, i - 20):i, 5].mean() if i > 0 else math.nan
            out.append(dict(known=known, price=price, side=side, kind=f'fvg_{tf}', tf=tf, width=width,
                            origin_atr=disp, origin_vol=vol))
        if tf != '15m':
            for known, price, side, kind in ob_levels(c, TF_MS[tf]):
                kind = kind.replace('_1h', f'_{tf}')
                out.append(dict(known=known, price=price, side=side, kind=kind, tf=tf, width=math.nan,
                                origin_atr=math.nan, origin_vol=math.nan))
    from research_level_weights import profile_levels
    for known, price, side, kind in profile_levels(c15[:, :6]):
        out.append(dict(known=known, price=price, side=side, kind=kind, tf='1d', width=0.0, origin_atr=math.nan,
                        origin_vol=math.nan))
    return out


def pierce_of(kind: str, q: str) -> float:
    """The measured pierce (share of price) of the nearest measured kind (models/overshoot.json, global)."""
    model = getattr(pierce_of, 'model', None)
    if model is None:
        with open(os.path.join('models', 'overshoot.json'), encoding='utf-8') as f:
            model = pierce_of.model = json.load(f)['global']
    if kind in model:
        base = kind
    elif kind.endswith('15m'):
        base = 'swing_15m'
    elif kind.endswith('1h') or kind == 'equal':
        base = 'swing_1h'
    elif kind == 'round':
        base = 'round'
    else:
        base = 'pdhl'                     # 4h / daily / weekly levels and the day's profile
    return model[base][q] / 100


# ------------------------------------------------------------------------------------------------ events

def first_passage(h, l, start, end, d, entry, stop, targets):
    """Per target: +1 reached before the stop, -1 stop first (a candle touching both = stop), 0 neither by `end`."""
    res = [0] * len(targets)
    for j in range(start, end):
        stop_hit = (l[j] <= stop) if d > 0 else (h[j] >= stop)
        for t, tg in enumerate(targets):
            if res[t] == 0:
                hit = (h[j] >= tg) if d > 0 else (l[j] <= tg)
                if stop_hit:
                    res[t] = -1
                elif hit:
                    res[t] = 1
        if stop_hit or all(r != 0 for r in res):
            break
    return res


def mechanic(h, l, c, i, price, side, n):
    beyond = (lambda j: h[j] > price) if side > 0 else (lambda j: l[j] < price)
    cb = (lambda j: c[j] > price) if side > 0 else (lambda j: c[j] < price)
    end = min(n, i + K)
    if not any(beyond(j) for j in range(i, end)):
        return 'front'
    first = next((j for j in range(i, end) if cb(j)), None)
    if first is None:
        return 'wick'
    if first + 1 < n and cb(first + 1):
        back = next((j for j in range(first + 2, min(n, first + 2 + K)) if not cb(j)), None)
        return 'break' if back is None else 'failed'
    return 'close1'


def events_of(c15, levels, ctx, placebo: int, rnd: random.Random) -> List[dict]:
    ts, o, h, l, c, v, buy = (c15[:, k] for k in range(7))
    n = len(ts)
    atr15 = ctx['atr15']
    out = []
    for lv in levels:
        price, side, tf, kind = lv['price'], lv['side'], lv['tf'], lv['kind']
        if placebo:
            shift = rnd.uniform(1.0, 2.0) * pierce_of(kind, 'p90')
            price = price * (1 + side * shift) if rnd.random() < 0.5 else price * (1 - side * shift)
        i0 = int(np.searchsorted(ts, lv['known']))
        if i0 < 200 or i0 >= n - K - 2:
            continue
        tf_atr = ctx[f'atr_{tf}'][i0]
        if not tf_atr > 0 or not atr15[i0 - 1] > 0:
            continue
        end = min(n, i0 + LIFE)
        # 'away' = 1 ATR of the level's timeframe, capped at the 4h ATR (a daily ATR of ~4% would drop almost every
        # previous-day high, which sits closer than that)
        sep = min(tf_atr, ctx['atr_4h'][i0]) if ctx['atr_4h'][i0] > 0 else tf_atr
        if side * (price - c[i0 - 1]) <= sep:
            continue                                   # must start at least 1 ATR(tf) away on its side
        band = BAND * atr15[i0 - 1]
        ext = h[i0:end] if side > 0 else l[i0:end]
        near = np.flatnonzero(side * (price - ext) <= band) + i0      # candles reaching the band
        away = np.flatnonzero(side * (price - c[i0:end]) > sep) + i0     # closes back at least `sep` away
        width = lv['width'] if lv['width'] == lv['width'] else 0.0
        stop_ext = pierce_of(kind, 'p80') * price + width * tf_atr
        H = H_BARS.get(tf, 48)
        touch, bounces, pos = 0, 0, 0
        while pos < len(near):
            i = int(near[pos])
            if i >= n - K - 2:
                break
            touch += 1
            ev = features(c15, ctx, i, price, side, tf, kind, lv, tf_atr, band)
            mech = mechanic(h, l, c, i, price, side, n)
            # bounce: a limit at the band's near edge, stop beyond the level by the p80 pierce (+ the zone's width)
            entry = price - side * band
            stop = price + side * stop_ext
            risk = abs(stop - entry)
            d = -side
            b = first_passage(h, l, i, min(n, i + H), d, entry, stop, [entry + d * r * risk for r in (1, 2, 3)])                 if risk > 0 else [0, 0, 0]
            seg = slice(i, min(n, i + H))
            b_mfe = ((entry - l[seg].min()) if d < 0 else (h[seg].max() - entry)) / risk if risk else math.nan
            b_mae = ((h[seg].max() - entry) if d < 0 else (entry - l[seg].min())) / risk if risk else math.nan
            # break: a stop entry beyond the pierce, stop back at the band's near edge
            kentry = price + side * stop_ext
            kstop = price - side * band
            krisk = abs(kentry - kstop)
            win = (h[i:min(n, i + H)] >= kentry) if side > 0 else (l[i:min(n, i + H)] <= kentry)
            hit = np.flatnonzero(win)
            filled = i + int(hit[0]) if len(hit) else None
            if filled is not None and krisk > 0:
                kk = first_passage(h, l, filled + 1, min(n, filled + 1 + H), side, kentry, kstop,
                                   [kentry + side * r * krisk for r in (1, 2, 3)])
            else:
                kk = [math.nan] * 3
            ev.update(placebo=placebo, touch=touch, prior_bounces=bounces, mech=mech,
                      b1=b[0], b2=b[1], b3=b[2], b_mfe=b_mfe, b_mae=b_mae, b_risk_pct=risk / price,
                      k_filled=int(filled is not None), k1=kk[0], k2=kk[1], k3=kk[2])
            out.append(ev)
            if mech in ('front', 'wick', 'close1'):
                bounces += 1
            if mech == 'break':
                break                                  # two consecutive closes beyond: the level is gone
            # the next approach only after price closed at least 1 ATR(tf) away again
            j = int(np.searchsorted(away, i, side='right'))
            if j >= len(away):
                break
            pos = int(np.searchsorted(near, away[j], side='right'))
    return out


def features(c15, ctx, i, price, side, tf, kind, lv, tf_atr, band) -> dict:
    ts, h, l, c, v, buy = c15[:, 0], c15[:, 2], c15[:, 3], c15[:, 4], c15[:, 5], c15[:, 6]
    a15 = ctx['atr15'][i - 1]
    prev = c[i - 1]
    # toward the level = +side (a resistance above: moving up into it)
    tf_c = ctx[f'close20_{tf}'][i]
    into = side * (prev - tf_c) / tf_atr if tf_c == tf_c else math.nan
    speed = side * (prev - c[i - 5]) / a15
    piv_side = ctx['piv15_lo'] if side > 0 else ctx['piv15_hi']   # the last pivot on the other side
    pv = piv_side[i]
    run = side * (prev - pv) / a15 if pv == pv else math.nan
    vol = v[i - 4:i].sum() / 4 / ctx['vol96'][i] if ctx['vol96'][i] > 0 else math.nan
    dl = buy[i - 4:i].sum() / v[i - 4:i].sum() - 0.5 if v[i - 4:i].sum() > 0 else math.nan
    lo20, hi20 = ctx['lo20d'][i], ctx['hi20d'][i]
    rpos = (prev - lo20) / (hi20 - lo20) if hi20 > lo20 else math.nan
    # room: the nearest known 1h pivot beyond the bounce (below a resistance's approach / above a support's)
    piv_t, piv_p = ctx['piv1h_t'], ctx['piv1h_p']
    known = piv_t <= ts[i]
    if side > 0:
        cand = piv_p[known & (piv_p < price - band)]
        room = (price - cand.max()) / tf_atr if len(cand) else 50.0
    else:
        cand = piv_p[known & (piv_p > price + band)]
        room = (cand.min() - price) / tf_atr if len(cand) else 50.0
    swept = math.nan
    pv_same = (ctx['piv15_hi'] if side > 0 else ctx['piv15_lo'])[i - 8] if i >= 8 else math.nan
    if pv_same == pv_same:
        if side > 0:
            swept = int(pv_same < price and h[i - 8:i].max() > pv_same)
        else:
            swept = int(pv_same > price and l[i - 8:i].min() < pv_same)
    btc = ctx['btc_ret1h'][i]
    return dict(ts=ts[i], kind=kind, tf=tf, side=side, price=price, age_h=(ts[i] - lv['known']) / HOUR,
                width_atr=lv['width'], origin_atr=lv['origin_atr'], origin_vol=lv['origin_vol'],
                into_atr=into, speed_atr=speed, run_atr=run, vol_ratio=vol, delta=side * dl if dl == dl else math.nan,
                range_pos=rpos, room_atr=min(room, 50.0), ema_dev=(prev - ctx['ema50_1h'][i]) / ctx['atr_1h'][i]
                if ctx['atr_1h'][i] > 0 else math.nan,
                trend_1d=(prev - ctx['ema20_1d'][i]) / ctx['atr_1d'][i] if ctx['atr_1d'][i] > 0 else math.nan,
                trend_4h=(prev - ctx['ema20_4h'][i]) / ctx['atr_4h'][i] if ctx['atr_4h'][i] > 0 else math.nan,
                er_4h=ctx['er_4h'][i], vol_regime=a15 / ctx['atr15_med'][i] if ctx['atr15_med'][i] > 0 else math.nan,
                btc_1h=side * btc if btc == btc else math.nan, hour=int(ts[i] // HOUR % 24),
                swept=swept, oi_1h=ctx['oi_1h'][i])


def context(c15: np.ndarray, tfc, atrs, btc15: np.ndarray, oi: Dict[str, np.ndarray]) -> dict:
    ts = c15[:, 0]
    n = len(ts)
    a15 = atrs['15m']
    ctx = {'atr15': np.r_[np.nan, a15[:-1]]}       # the ATR of the candles BEFORE each one
    for tf in ('15m', '1h', '4h', '1d', '1w'):
        c, a = tfc[tf], atrs[tf]
        ctx[f'atr_{tf}'] = ctx['atr15'] if tf == '15m' else aligned(ts, c, TF_MS[tf], a)
        if len(c) > 20:
            # the close 20 candles of this tf ago (the net move into the level)
            ctx[f'close20_{tf}'] = aligned(ts, c, TF_MS[tf], np.r_[np.full(20, np.nan), c[:-20, 4]])
        else:
            ctx[f'close20_{tf}'] = np.full(n, np.nan)
    ctx['close20_15m'] = np.r_[np.full(21, np.nan), c15[:-21, 4]][:n] if n > 21 else np.full(n, np.nan)
    for tf, span, name in (('1h', 50, 'ema50_1h'), ('1d', 20, 'ema20_1d'), ('4h', 20, 'ema20_4h')):
        c = tfc[tf]
        ctx[name] = aligned(ts, c, TF_MS[tf], ema_of(c[:, 4], span)) if len(c) else np.full(n, np.nan)
    c4 = tfc['4h']
    if len(c4) > 21:
        net = np.abs(c4[20:, 4] - c4[:-20, 4])
        path = np.convolve(np.abs(np.diff(c4[:, 4])), np.ones(20), mode='valid')
        er = np.r_[np.full(20, np.nan), net / np.where(path > 0, path, np.nan)]
        ctx['er_4h'] = aligned(ts, c4, 4 * HOUR, er)
    else:
        ctx['er_4h'] = np.full(n, np.nan)
    d1 = tfc['1d']
    if len(d1) > 20:
        hi = np.array([d1[max(0, k - 19):k + 1, 2].max() for k in range(len(d1))])
        lo = np.array([d1[max(0, k - 19):k + 1, 3].min() for k in range(len(d1))])
        ctx['hi20d'], ctx['lo20d'] = aligned(ts, d1, DAY, hi), aligned(ts, d1, DAY, lo)
    else:
        ctx['hi20d'] = ctx['lo20d'] = np.full(n, np.nan)
    v = c15[:, 5]
    ctx['vol96'] = np.r_[np.full(96, np.nan), np.convolve(v, np.ones(96) / 96, mode='valid')[:-1]][:n]
    a = a15
    med = np.full(n, np.nan)
    for k in range(2880, n, 96):
        med[k:k + 96] = np.median(a[k - 2880:k])
    ctx['atr15_med'] = med
    # the last confirmed 15m pivot high / low at each candle (3 x 3: known 3 candles later)
    hi_p, lo_p = np.full(n, np.nan), np.full(n, np.nan)
    for i, p, s in pivots(c15[:, 2], c15[:, 3]):
        k = i + 4
        if k < n:
            (hi_p if s > 0 else lo_p)[k] = p
    for arr in (hi_p, lo_p):
        last = np.nan
        for k in range(n):
            if arr[k] == arr[k]:
                last = arr[k]
            arr[k] = last
    ctx['piv15_hi'], ctx['piv15_lo'] = hi_p, lo_p
    c1 = tfc['1h']
    pv = pivots(c1[:, 2], c1[:, 3])
    ctx['piv1h_t'] = np.array([c1[i + 3, 0] + HOUR if i + 3 < len(c1) else np.inf for i, _, _ in pv])
    ctx['piv1h_p'] = np.array([p for _, p, _ in pv])
    if len(btc15):
        bi = np.searchsorted(btc15[:, 0], ts) - 1
        ok = bi >= 4
        r = np.full(n, np.nan)
        r[ok] = btc15[bi[ok], 4] / btc15[bi[ok] - 4, 4] - 1
        ctx['btc_ret1h'] = r
    else:
        ctx['btc_ret1h'] = np.full(n, np.nan)
    if len(oi.get('ts', [])):
        oi_t, oi_v = oi['ts'], oi['oi']
        j = np.searchsorted(oi_t, ts) - 1
        j0 = np.searchsorted(oi_t, ts - HOUR) - 1
        r = np.full(n, np.nan)
        ok = (j >= 0) & (j0 >= 0)
        r[ok] = oi_v[j[ok]] / np.where(oi_v[j0[ok]] > 0, oi_v[j0[ok]], np.nan) - 1
        ctx['oi_1h'] = r
    else:
        ctx['oi_1h'] = np.full(n, np.nan)
    return ctx


def run_coin(job) -> Dict:
    symbol, start, end, with_oi = job
    import polars as pl
    if os.path.exists(os.path.join(OUT_DIR, f'{symbol}.parquet')):
        return {'symbol': symbol, 'rows': -1}          # done by an earlier (interrupted) run of the same options (main)
    from history import Archive
    arch = Archive(rate_bytes=4e6)
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    c15 = load_15m(arch, symbol, s, e)
    if len(c15) < 5000:
        return {'symbol': symbol, 'rows': 0}
    btc = load_15m(arch, 'BTCUSDT', s, e) if symbol != 'BTCUSDT' else c15
    try:
        oi = arch.metrics(symbol, s, e) if with_oi else {}
    except Exception as err:                       # an archive file that keeps failing: the coin without OI
        logging.warning(f"{symbol}: no OI metrics ({err})")
        oi = {}
    tfc = {tf: resample(c15, TF_MS[tf]) for tf in TF_MS}
    atrs = {tf: atr_of(tfc[tf]) for tf in TF_MS}
    ctx = context(c15, tfc, atrs, btc, oi)
    levels = level_list(c15, tfc, atrs)
    rnd = random.Random(sum(map(ord, symbol)))
    rows = events_of(c15, levels, ctx, 0, rnd) + events_of(c15, levels, ctx, 1, rnd)
    if not rows:
        return {'symbol': symbol, 'rows': 0}
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pl.DataFrame(rows, infer_schema_length=None).with_columns(pl.lit(symbol).alias('symbol'))
    df.write_parquet(os.path.join(OUT_DIR, f'{symbol}.parquet'))
    return {'symbol': symbol, 'rows': len(rows), 'real': sum(1 for r in rows if not r['placebo'])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--months', type=int, default=12)
    ap.add_argument('--limit', type=int, default=60)
    ap.add_argument('--workers', type=int, default=1)
    ap.add_argument('--min-volume', type=float, default=3e6)
    ap.add_argument('--no-oi', action='store_true')
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-7s | %(message)s', datefmt='%H:%M:%S')
    from history import Archive
    from pretrain import select_coins
    end = datetime.now(timezone.utc).date().replace(day=1) - timedelta(days=1)
    start = end - timedelta(days=30 * args.months)
    coins = select_coins(Archive(rate_bytes=4e7), start, end, args.min_volume)[:args.limit]
    jobs = [(f, start.isoformat(), end.isoformat(), not args.no_oi) for _, f, _, _ in coins]
    # audit R08: a resume only within the SAME options - the per-symbol files carry no dates / OI flag / code version,
    # so a run with other options must not reuse them (it moves them aside)
    import hashlib
    import json
    import shutil
    manifest = {'start': start.isoformat(), 'end': end.isoformat(), 'oi': not args.no_oi,
                'code': hashlib.sha256(open(__file__, 'rb').read()).hexdigest()[:16]}
    mpath = os.path.join(OUT_DIR, '_run.json')
    old = None
    if os.path.exists(mpath):
        with open(mpath, encoding='utf-8') as fh:
            old = json.load(fh)
    if os.path.isdir(OUT_DIR) and old != manifest and any(f.endswith('.parquet') for f in os.listdir(OUT_DIR)):
        stale = f"{OUT_DIR}_stale_{int(datetime.now(timezone.utc).timestamp())}"
        shutil.move(OUT_DIR, stale)
        logging.info(f"events: the cached rows were made with other options ({old}): moved to {stale}")
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(mpath, 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh)
    if args.workers > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(args.workers) as pool:
            for k, r in enumerate(pool.map(run_coin, jobs), 1):
                logging.info(f"events: {k}/{len(jobs)} {r['symbol']} {r['rows']} rows")
    else:
        for k, job in enumerate(jobs, 1):
            try:
                r = run_coin(job)
            except Exception as err:
                logging.warning(f"events: {job[0]} failed: {err}")
                continue
            logging.info(f"events: {k}/{len(jobs)} {r['symbol']} {r['rows']} rows")


if __name__ == '__main__':
    main()
