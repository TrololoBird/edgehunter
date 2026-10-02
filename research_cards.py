"""
Historical replay of the bot's CARDS (not the 4h horizon of a setup): SWEEP and BREAKOUT events detected on the
Binance archive by the live detectors, planned by the live strategies (strategy.plan: zone, invalidation, targets by
intent, stop), walked minute by minute through the shared lifecycle (WATCH -> ZONE -> structure-shift trigger on
closed trigger-timeframe candles -> entry_levels / low R:R veto / breakout's required OI confirmation -> INVALID /
MISSED / EXPIRED) and every entry replayed like the journal does (levels.simulate: fill at the open of the first full
minute after the entry + slippage, stop exits slipped, targets traded through, funding netted), net of the round-trip
fee in R (stats.net_r).

What differs from the live bot (so the numbers are an estimate, not the live result):
- level maps without book walls / liquidity bands / Hyperliquid / observed liquidations (not in the archive);
- the perp-led veto of breakouts is not applied (it needs the multi-venue flows); the sweep's 'against_trend' veto is
  applied AND the vetoed events are replayed too (flag `vetoed`), so the veto itself is tested;
- prices are 1m candle extremes (the live bot checks the last price every few seconds);
- one open card per coin and direction (the live rule); the market crowd, regimes and P(edge) do not matter here.

Run: .venv\\Scripts\\python research_cards.py [--months 6] [--workers 3] [--limit N] [--out research/cards_6m.md]
Uses the pretraining cache (history_cache/); the coins and their eligible days as pretrain.select_coins picks them.
"""
import argparse
import logging
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

import numpy as np
import polars as pl

from config import CONFIG

logger = logging.getLogger('research_cards')

MINUTE_MS = 60_000
QUARTER_MS = 900_000
HOUR_MS = 3_600_000
H4_MS = 4 * HOUR_MS
STREAM_COLS = [0, 1, 2, 3, 4, 6, 7]          # [t, o, h, l, c, quote, taker buy quote]


# Entry execution of the replay: 'market' (the journal's manual fill: the next full minute's open + slippage, taker
# fees) or 'maker' (a resting limit at the trigger's close, filled only if price trades back through it within
# MAKER_WAIT_MIN minutes). Set with --entry (an environment variable, so the worker processes see it).
ENTRY_MODE = os.environ.get('RESEARCH_ENTRY', 'market')
MAKER_WAIT_MIN = 5
MAKER_FEE, TAKER_FEE = 0.0002, 0.0005        # Binance USD-M VIP0


def _net_r(r: Optional[float], entry: float, sl: float, fee: Optional[float] = None) -> Optional[float]:
    if r is None or not entry or entry == sl:
        return r
    return r - (CONFIG.journal.fee_round_trip if fee is None else fee) * entry / abs(entry - sl)


def _oi_change(oi_ts: np.ndarray, oi_v: np.ndarray, since: float, until: float) -> Optional[float]:
    """Relative OI change between the first sample at / after since and the last at / before until (confirm.oi_change)."""
    a = int(np.searchsorted(oi_ts, since, side='left'))
    b = int(np.searchsorted(oi_ts, until, side='right')) - 1
    if b <= a or oi_ts[b] - oi_ts[a] < 5 * MINUTE_MS or not oi_v[a]:
        return None
    return float(oi_v[b] / oi_v[a] - 1)


def make_placebo(m_ts: np.ndarray, key: str):
    """
    The placebo trade's entry: the SAME time of day on a random other day within +-7 days (away from the window's
    edges). A uniform random time compared session-bound setups (ORB, Silver Bullet, kill zones) with hours of other
    volatility - the null-world audit (null_audit.py) showed ORB beating such a placebo on data without structure.
    """
    rng = np.random.default_rng(sum(map(ord, key)))
    shifts = [d for d in range(-7, 8) if d]

    def pick(entered_ms: float):
        for _ in range(10):
            t = (entered_ms + shifts[int(rng.integers(len(shifts)))] * 86_400_000) // MINUTE_MS * MINUTE_MS
            if m_ts[0] + 3 * 86_400_000 < t < m_ts[-1] - 3 * 86_400_000:
                return t
        return None
    return pick


def replay_coin(job: tuple) -> List[Dict]:
    key, fut_id, spot_id, start_iso, end_iso, days_ok, what = job
    out: List[Dict] = []
    samples: List[Dict] = []
    if what in ('events', 'all'):
        rows, smp = replay_events(job)
        out += rows
        samples += smp
    if what in ('phases', 'all'):
        rows, smp = replay_phases(job)
        out += rows
        samples += smp
    return out, samples


def replay_events(job: tuple) -> List[Dict]:
    key, fut_id, spot_id, start_iso, end_iso, days_ok, _ = job
    from history import Archive
    from indicators import compute_indicators_batch
    from levels import ltf_trigger, resample, simulate
    from strategies.geometry import entry_levels
    from pretrain import _asof, _bucket, _raw_frame
    from strategies import strategy_of
    from strategies.base import PlanInput
    from strategies.level import sweep_at_close
    from strategies.wyckoff_range import wyckoff_events
    from strategies.structure import Context, coin_trend, pools_before, recent_atr
    from zones import build_raw, merge

    days_ok = set(days_ok)
    start, end = date.fromisoformat(start_iso), date.fromisoformat(end_iso)
    archive = Archive(rate_bytes=4e7)
    fut = archive.klines_1m('futures', fut_id, start, end)
    if len(fut) < 1440 * 10:
        return [], []
    spot = archive.klines_1m('spot', spot_id, start, end) if spot_id else np.empty((0, 8))
    btc = fut if fut_id == 'BTCUSDT' else archive.klines_1m('futures', 'BTCUSDT', start, end)
    met = archive.metrics(fut_id, start, end)
    fund = archive.funding(fut_id, start, end)
    c15 = _bucket(fut, QUARTER_MS)
    oi15 = {int((t - 1) // QUARTER_MS * QUARTER_MS): float(v) for t, v in zip(met['ts'], met['oi']) if int(t) % QUARTER_MS == 0 and v}
    fut_all = compute_indicators_batch({key: _raw_frame(c15, oi15)}, {key: (0.0, 0.0)})
    atr_by_ts = {int(t): a for t, a in zip(fut_all['timestamp'].to_list(), fut_all['atr'].to_list())}
    m_ts = fut[:, 0]
    placebo = make_placebo(m_ts, key)
    minutes_all = fut[:, STREAM_COLS]
    h1 = _bucket(fut, HOUR_MS)
    h1_list = [[r[0], r[1], r[2], r[3], r[4], r[6], r[7]] for r in h1]
    h1_close = h1[:, 0] + HOUR_MS if len(h1) else np.empty(0)
    c5 = _bucket(fut, 5 * MINUTE_MS)
    c5_list = [[r[0], r[1], r[2], r[3], r[4], r[6], r[7]] for r in c5]
    c5_close = c5[:, 0] + 5 * MINUTE_MS if len(c5) else np.empty(0)
    c15_list = [[r[0], r[1], r[2], r[3], r[4], r[6], r[7]] for r in c15]
    oi_ts, oi_v = np.asarray(met['ts']), np.asarray(met['oi'])
    oi_hour = [(int(t), float(v)) for t, v in zip(oi_ts, oi_v) if int(t) % HOUR_MS == 0 and v]
    oi_hour_ts = np.asarray([t for t, _ in oi_hour]) if oi_hour else np.empty(0)
    qv15 = c15[:, 6]
    prev20 = np.r_[np.nan, np.convolve(qv15, np.ones(20), 'full')[:len(qv15)][:-1]] / 20
    sweep_possible = ~(prev20 > 0) | (qv15 >= CONFIG.strategies.sweep_min_rvol * prev20)
    features = feature_builder(fut, spot, _bucket(btc, QUARTER_MS), fut_all, oi_ts, oi_v, fund, h1_list)
    samples: List[Dict] = []

    out: List[Dict] = []
    busy_until = {1: 0.0, -1: 0.0}
    for q in range(98, len(c15_list)):
        last_open = int(c15_list[q][0])
        cut = last_open + QUARTER_MS
        if cut // 86_400_000 not in days_ok:
            continue
        atr = atr_by_ts.get(last_open)
        if not atr or atr != atr:
            continue
        window = c15_list[q - 98:q + 1]
        h = int(np.searchsorted(h1_close, cut, side='right'))
        h1_long = h1_list[max(0, h - 520):h]
        h1_window = h1_long[-200:]
        trend = coin_trend(h1_window)
        events = []
        if cut % HOUR_MS == 0:
            # (the breakout is the Turtles' daily system since eng-32: research_turtle.py)
            events.extend(wyckoff_events(h1_long))
        if sweep_possible[q]:
            events.append(sweep_at_close(window, pools_before(window, h1_window, atr, last_open), atr, trend))
        for event in [e for e in events if e]:
            d = event['direction']
            now_ms = cut + 5_000
            if now_ms < busy_until[d]:
                continue                                  # one open card per coin and direction
            strategy = strategy_of(event['setup'])
            sig = dict(event, coin_trend=trend, has_spot=True)
            vetoed = strategy.context_veto(sig, d)
            part = window[-CONFIG.timeframe.rest_lookback_candles:]
            j = int(np.searchsorted(oi_hour_ts, now_ms, side='right')) if len(oi_hour_ts) else 0
            k5 = int(np.searchsorted(c5_close, now_ms, side='right'))
            raw = build_raw(part, h1_window, oi_hour[max(0, j - 200):j], [], atr, now_ms,
                            candles_4d=c5_list[max(0, k5 - 4 * 288):k5])
            ctx = Context(atr=atr, recent_atr=recent_atr(part), cut_ms=cut, zones=merge(raw, atr), pools=[], trend=trend)
            closed = int(np.searchsorted(m_ts, now_ms - MINUTE_MS, side='right'))
            minutes_now = minutes_all[max(0, closed - 240):closed].tolist()
            df = fut_all.slice(max(0, q - 98), 99)
            plan = strategy.plan(PlanInput(key, d, event['setup'], sig, df, minutes_now, raw, h1_window, ctx, None))
            row = {'symbol': key, 'ts_ms': now_ms, 'setup': event['setup'], 'strategy': strategy.name, 'direction': d,
                   'vetoed': vetoed or '', 'status': 'NO_PLAN', 'vetoed_triggers': 0, 'veto_log': '', 'r_tp1': None, 'r_tp2': None,
                   'r_be': None, 'rr_tp1': None, 'risk_pct': None, 'outcome': None, 'hold_min': None,
                   'vx_reason': '', 'vx_r_tp1': None, 'vx_r_tp2': None, 'vx_rr_tp1': None,
                   'pl_r_tp1': None, 'pl_r_tp2': None}
            if plan is None or not plan.get('targets'):
                out.append(row)
                continue
            finished_ms = _lifecycle(plan, strategy, d, row, now_ms, m_ts, minutes_all, fut, fund, oi_ts, oi_v,
                                     entry_levels, ltf_trigger, resample, simulate, _asof,
                                     features=features, samples=samples, placebo=placebo,
                                     spot_minutes=spot[:, STREAM_COLS] if len(spot) else None)
            if not vetoed:
                busy_until[d] = finished_ms
            out.append(row)
    return out, samples


def replay_phases(job: tuple) -> List[Dict]:
    """
    The phase setups the bot makes cards of (trend: BULL F / BEAR D; wyckoff: BULL A / B / E, BEAR C): scored by the
    live PhaseScorer on closed 15m candles (spot structure, futures OI / flow), classified, vetoed like the bot
    (perp-led when crowded, the trend strategy's tide), planned and walked like the event cards; the plan is re-made at
    every 15m close until the entry (live it follows the chart), a continuation's plan frozen in its zone.
    """
    key, fut_id, spot_id, start_iso, end_iso, days_ok, _ = job
    from history import Archive
    from indicators import compute_indicators_batch
    from journal import classify, veto_reason
    from levels import ltf_trigger, pullback_volume_ok, resample, simulate
    from pretrain import _asof, _bucket, _raw_frame
    from scorer import PhaseScorer
    from strategies import strategy_of
    from strategies.base import PlanInput
    from strategies.geometry import entry_levels
    from strategies.structure import Context, coin_trend, recent_atr
    from zones import build_raw, merge

    days_ok = set(days_ok)
    start, end = date.fromisoformat(start_iso), date.fromisoformat(end_iso)
    archive = Archive(rate_bytes=4e7)
    fut = archive.klines_1m('futures', fut_id, start, end)
    spot = archive.klines_1m('spot', spot_id, start, end) if spot_id else np.empty((0, 8))
    if len(fut) < 1440 * 10 or len(spot) == 0:
        return [], []
    btc = fut if fut_id == 'BTCUSDT' else archive.klines_1m('futures', 'BTCUSDT', start, end)
    met = archive.metrics(fut_id, start, end)
    fund = archive.funding(fut_id, start, end)
    c15 = _bucket(fut, QUARTER_MS)
    oi15 = {int((t - 1) // QUARTER_MS * QUARTER_MS): float(v) for t, v in zip(met['ts'], met['oi']) if int(t) % QUARTER_MS == 0 and v}
    fut_all = compute_indicators_batch({key: _raw_frame(c15, oi15)}, {key: (0.0, 0.0)})
    spot_all = compute_indicators_batch({key: _raw_frame(_bucket(spot, QUARTER_MS), None)}, {key: (0.0, 0.0)})
    if len(fund):
        for name in ('fut', 'spot'):
            frame = fut_all if name == 'fut' else spot_all
            rates = [(_asof(fund[:, 0], fund[:, 1], t + QUARTER_MS) or 0.0) for t in frame['timestamp'].to_list()]
            frame = frame.with_columns(pl.Series('funding_rate', rates), pl.Series('predicted_funding', rates))
            if name == 'fut':
                fut_all = frame
            else:
                spot_all = frame
    scorer = PhaseScorer()
    scored = scorer.calculate_scores(spot_all, fut_all, None, None).sort('timestamp')
    fut_ts = fut_all['timestamp'].to_numpy()
    m_ts = fut[:, 0]
    placebo = make_placebo(m_ts, key)
    minutes_all = fut[:, STREAM_COLS]
    h1 = _bucket(fut, HOUR_MS)
    h1_list = [[r[0], r[1], r[2], r[3], r[4], r[6], r[7]] for r in h1]
    h1_close = h1[:, 0] + HOUR_MS if len(h1) else np.empty(0)
    c5 = _bucket(fut, 5 * MINUTE_MS)
    c5_list = [[r[0], r[1], r[2], r[3], r[4], r[6], r[7]] for r in c5]
    c5_close = c5[:, 0] + 5 * MINUTE_MS if len(c5) else np.empty(0)
    c15_list = [[r[0], r[1], r[2], r[3], r[4], r[6], r[7]] for r in c15]
    c15_close = c15[:, 0] + QUARTER_MS
    btc15 = _bucket(btc, QUARTER_MS)
    btc_close_ts, btc_close = btc15[:, 0] + QUARTER_MS, btc15[:, 4]
    oi_ts, oi_v = np.asarray(met['ts']), np.asarray(met['oi'])
    oi_hour = [(int(t), float(v)) for t, v in zip(oi_ts, oi_v) if int(t) % HOUR_MS == 0 and v]
    oi_hour_ts = np.asarray([t for t, _ in oi_hour]) if oi_hour else np.empty(0)
    features = feature_builder(fut, spot, btc15, fut_all, oi_ts, oi_v, fund, h1_list)
    samples: List[Dict] = []

    def inputs(t_ms: float):
        """(df of closed 15m candles, 1h candles, raw levels, context) as the bot had them at t_ms."""
        q = int(np.searchsorted(fut_ts + QUARTER_MS, t_ms, side='right'))
        df = fut_all.slice(max(0, q - CONFIG.timeframe.rest_lookback_candles), min(q, CONFIG.timeframe.rest_lookback_candles))
        k = int(np.searchsorted(c15_close, t_ms, side='right'))
        part = c15_list[max(0, k - CONFIG.timeframe.rest_lookback_candles):k]
        h = int(np.searchsorted(h1_close, t_ms, side='right'))
        h1w = h1_list[max(0, h - 200):h]
        atr = df['atr'][-1] if df.height else None
        if not atr or atr != atr or not part:
            return None
        j = int(np.searchsorted(oi_hour_ts, t_ms, side='right')) if len(oi_hour_ts) else 0
        k5 = int(np.searchsorted(c5_close, t_ms, side='right'))
        raw = build_raw(part, h1w, oi_hour[max(0, j - 200):j], [], atr, t_ms, candles_4d=c5_list[max(0, k5 - 4 * 288):k5])
        ctx = Context(atr=atr, recent_atr=recent_atr(part), cut_ms=int(t_ms), zones=merge(raw, atr), pools=[],
                      trend=coin_trend(h1w))
        return df, h1w, raw, ctx

    # ---- candidates: phase setups at each closed 15m candle, Tier-0 impulses (momentum) at qualifying minutes
    candidates = []
    for row in scored.iter_rows(named=True):
        close_ms = row['timestamp'] + QUARTER_MS
        if close_ms // 86_400_000 not in days_ok:
            continue
        row.update({c: 0.0 for c in ('rvol_1m', 'price_z', 'oi_z', 'whale_net_5m', 'liq_long_5m', 'liq_short_5m')})
        row.update(is_tier_0_anomaly=False, rule_anomaly=False, liq_cascade=False)
        sig = scorer.signal_from_row(row)
        if not sig or not sig.get('is_structured'):
            continue
        _, group_key, d = classify(sig)
        if strategy_of(group_key) is not None and d:
            candidates.append((close_ms + 5_000, sig, group_key, d))
    candidates += _impulses(key, fut, spot, met, fut_all, scored, h1_list, days_ok, scorer, classify)
    candidates.sort(key=lambda c: c[0])

    out: List[Dict] = []
    busy_until = {1: 0.0, -1: 0.0}
    for now_ms, sig, group_key, d in candidates:
        strategy = strategy_of(group_key)
        if now_ms < busy_until[d]:
            continue
        x = inputs(now_ms)
        if x is None:
            continue
        df, h1w, raw, ctx = x
        b = int(np.searchsorted(btc_close_ts, now_ms, side='right')) - 1
        sig.update(coin_trend=ctx.trend, has_spot=True,
                   btc_1h=float(btc_close[b] / btc_close[b - 4] - 1) if b >= 4 else None)
        vetoed = veto_reason(group_key, sig) or strategy.context_veto(sig, d)
        k = int(np.searchsorted(m_ts, now_ms - MINUTE_MS, side='right'))
        plan = strategy.plan(PlanInput(key, d, group_key, sig, df, minutes_all[max(0, k - 240):k].tolist(), raw, h1w,
                                       ctx, None))
        rec = {'symbol': key, 'ts_ms': now_ms, 'setup': group_key, 'strategy': strategy.name, 'direction': d,
               'vetoed': vetoed or '', 'status': 'NO_PLAN', 'vetoed_triggers': 0, 'veto_log': '', 'r_tp1': None,
               'r_tp2': None, 'r_be': None, 'rr_tp1': None, 'risk_pct': None, 'outcome': None, 'hold_min': None,
               'vx_reason': '', 'vx_r_tp1': None, 'vx_r_tp2': None, 'vx_rr_tp1': None,
                   'pl_r_tp1': None, 'pl_r_tp2': None}
        if plan is None or plan.get('skip') or not plan.get('targets'):
            if plan and plan.get('skip'):
                rec['status'] = f"NO_PLAN ({plan['skip']})"
            out.append(rec)
            continue
        reached = plan.get('reached')

        def replan(t_ms, strategy=strategy, d=d, group_key=group_key, sig=sig, reached=reached):
            y = inputs(t_ms)
            if y is None:
                return None
            df2, h1w2, raw2, ctx2 = y
            kk = int(np.searchsorted(m_ts, t_ms - MINUTE_MS, side='right'))
            p2 = strategy.plan(PlanInput(key, d, group_key, sig, df2, minutes_all[max(0, kk - 240):kk].tolist(), raw2,
                                         h1w2, ctx2, reached))
            return None if p2 is None or p2.get('skip') else p2

        spring_minute = sig.get('fut_candle_minute_usd')

        def spring_test(levels, zone_since, trigger_ms, group_key=group_key, spring_minute=spring_minute):
            if group_key != 'BULL B':
                return None
            a = int(np.searchsorted(m_ts, zone_since, side='left'))
            b2 = int(np.searchsorted(m_ts, trigger_ms, side='left'))
            ok = pullback_volume_ok(minutes_all[a:b2].tolist(), int(zone_since), int(trigger_ms), spring_minute or 0.0)
            return None if ok else 'no_spring_test'

        finished = _lifecycle(plan, strategy, d, rec, now_ms, m_ts, minutes_all, fut, fund, oi_ts, oi_v,
                              entry_levels, ltf_trigger, resample, simulate, _asof, replan=replan, extra_veto=spring_test,
                              features=features, samples=samples, placebo=placebo)
        if not vetoed:
            busy_until[d] = finished
        out.append(rec)
    return out, samples


def _impulses(key, fut, spot, met, fut_all, scored, h1_list, days_ok, scorer, classify) -> list:
    """
    IMPULSE UP / DOWN setups (momentum) as the live Tier-0 loop finds them: every minute whose 5m move or 1m volume
    could qualify is probed at its close with calculate_tier0_metrics (the coin's 15m return / OI std, the time-of-day
    profile, the average minute of the last 24h, OI from the 5-minute metrics), then flagged and classified like live.
    """
    from indicators import calculate_tier0_metrics, minute_delta, seasonal_factors, seasonal_scale
    from collections import deque
    t0 = CONFIG.tier0
    m_ts = fut[:, 0]
    closes = fut[:, 4]
    qv_cum = np.concatenate(([0.0], np.cumsum(fut[:, 6])))
    with np.errstate(divide='ignore', invalid='ignore'):
        ch5 = np.abs(closes[5:] / closes[:-5] - 1)
    probe = np.flatnonzero(ch5 > t0.price_change_5m_threshold) + 5
    if not len(probe):
        return []
    s_ts = spot[:, 0] if len(spot) else np.empty(0)
    oi_pts = [(float(t), float(v)) for t, v in zip(met['ts'], met['oi']) if v]
    oi_ts = np.asarray([p[0] for p in oi_pts]) if oi_pts else np.empty(0)
    ind = fut_all.select('timestamp', 'ret_std', 'oi_std').to_numpy()
    h1_close = np.asarray([c[0] + HOUR_MS for c in h1_list]) if h1_list else np.empty(0)
    seasons: Dict[int, Optional[Dict]] = {}
    scored_ts = scored['timestamp'].to_numpy()
    out = []
    last_family_ms = 0.0
    for i in probe:
        now_ms = float(m_ts[i]) + MINUTE_MS
        if now_ms // 86_400_000 not in days_ok or now_ms - last_family_ms < CONFIG.journal.cooldown_sec * 1000:
            continue
        j = int(np.searchsorted(m_ts, now_ms - MINUTE_MS, side='right'))
        minutes = deque(fut[max(0, j - 30):j][:, STREAM_COLS].tolist(), maxlen=240)
        ticker = deque(((k[0] + 59_999, k[4], 0.0) for k in fut[max(0, j - 10):j].tolist()), maxlen=400)
        k = int(np.searchsorted(oi_ts, now_ms, side='right')) if len(oi_ts) else 0
        oi = deque(oi_pts[max(0, k - 13):k], maxlen=64)
        n = min(j, 1440)
        avg_minute = (qv_cum[j] - qv_cum[j - n]) / max(1, n) if n else 0.0
        q = int(np.searchsorted(ind[:, 0], now_ms - QUARTER_MS, side='right')) - 1
        ret_std = ind[q, 1] if q >= 0 and ind[q, 1] == ind[q, 1] else None
        oi_std = ind[q, 2] if q >= 0 and ind[q, 2] == ind[q, 2] else None
        day = int(now_ms) // 86_400_000
        if day not in seasons:
            h = int(np.searchsorted(h1_close, day * 86_400_000, side='right'))
            seasons[day] = seasonal_factors(h1_list[max(0, h - 672):h])
        if ret_std:
            ret_std *= seasonal_scale(seasons[day], now_ms, 'ret')
        avg_minute *= seasonal_scale(seasons[day], now_ms, 'vol')
        m = calculate_tier0_metrics(ticker, oi, minutes, now_ms, ret_std=ret_std, oi_std=oi_std, avg_minute_usd=avg_minute)
        m['futures_cvd_5m'] = minute_delta(minutes, now_ms)
        if len(s_ts):
            js = int(np.searchsorted(s_ts, now_ms - MINUTE_MS, side='right'))
            m['spot_cvd_5m'] = minute_delta(spot[max(0, js - 6):js][:, STREAM_COLS].tolist(), now_ms)
        qs = int(np.searchsorted(scored_ts, now_ms - QUARTER_MS, side='right')) - 1
        if qs < 0:
            continue
        full = scored.row(qs, named=True)
        full.update(m)
        flag = scorer.flag_tier_0_anomaly(pl.DataFrame([{'symbol': key, **{c: v for c, v in m.items()
                                                                           if isinstance(v, (int, float))}}]))
        if not flag['is_tier_0_anomaly'][0]:
            continue
        full.update(is_tier_0_anomaly=True, rule_anomaly=True, liq_cascade=False, whale_net_5m=0.0)
        sig = scorer.signal_from_row(full)
        if not sig:
            continue
        sig['spot_cvd_5m'] = m.get('spot_cvd_5m', 0.0)
        sig['futures_cvd_5m'] = m['futures_cvd_5m']
        _, group_key, d = classify(sig)
        if group_key in ('IMPULSE UP', 'IMPULSE DOWN') and d:
            out.append((now_ms, sig, group_key, d))
            last_family_ms = now_ms
    return out


EXIT_RULES = ('tp1', 'tp2', 'be05_tp1', 'be05_tp2', 'be1r_tp2', 'trail1r', 'time60', 'time240', 'fix1r', 'fix2r',
              'fix3r', 'wide2x')


def exit_variants(bars: np.ndarray, d: int, sl: float, tp1: float, tp2: float) -> Dict[str, float]:
    """
    Gross result (fraction of price, before costs) of pre-registered exit rules for ONE entry on the same path of 1m
    candles [t, o, h, l, c] after it (filled at the first candle's open). A stop and a target in one candle: the stop
    first; a target fills once traded 2 bps through; breakeven / trailing stops act from the candle after they arm;
    unfinished trades close at the last candle's close (8h). Rules: tp1 / tp2 (stop or target), be05_* (stop to the
    entry once price went +0.5%), be1r_tp2 (... once +1R), trail1r (after +1R a stop trailing 1R behind the best
    price, no target), time60 / time240 (tp1, closed at market after 60 / 240 min), fixN r (target at N stop
    distances), wide2x (stop and TP1 distances doubled).
    """
    b = np.asarray(bars, dtype=float)
    n = len(b)
    if n < 2:
        return {}
    hi = b[:, 2] * d if d > 0 else -b[:, 3]
    lo = b[:, 3] * d if d > 0 else -b[:, 2]
    close = b[:, 4] * d
    e, s, t1, t2 = b[0, 1] * d, sl * d, tp1 * d, tp2 * d
    risk = e - s
    if risk <= 0 or t1 <= e:
        return {}
    buf = 2e-4 * abs(b[0, 1])
    unit = abs(b[0, 1])

    def first(mask: np.ndarray) -> int:
        idx = np.flatnonzero(mask)
        return int(idx[0]) if len(idx) else -1

    def bracket(stop: float, target: float, start: int = 0, end: int = n) -> float:
        """Exit price of a stop / target bracket over candles [start, end), else the close of the last one."""
        if start >= end:
            return close[end - 1]
        i_s = first(lo[start:end] <= stop)
        i_t = first(hi[start:end] >= target + buf) if np.isfinite(target) else -1
        if i_s >= 0 and (i_t < 0 or i_s <= i_t):
            return stop
        if i_t >= 0:
            return target
        return close[end - 1]

    def armed(threshold: float, target: float) -> float:
        """Stop to the entry once price reached threshold (from the next candle), exit at target."""
        a = first(hi >= threshold)
        if a < 0:
            return bracket(s, target)
        before = bracket(s, target, 0, a + 1)
        i_s, i_t = first(lo[:a + 1] <= s), first(hi[:a + 1] >= target + buf)
        if i_s >= 0 or i_t >= 0:
            return before
        return bracket(e, target, a + 1, n)

    def trailing() -> float:
        a = first(hi >= e + risk)
        if a < 0:
            return bracket(s, np.inf)
        i_s = first(lo[:a + 1] <= s)
        if i_s >= 0:
            return s
        best = np.maximum.accumulate(hi[a:])
        stops = np.maximum(best[:-1] - risk, e)            # the stop of candle j is set by the best up to j-1
        hit = first(lo[a + 1:] <= stops)
        return stops[hit] if hit >= 0 else close[-1]

    exits = {
        'tp1': bracket(s, t1), 'tp2': bracket(s, t2),
        'be05_tp1': armed(e + 0.005 * unit, t1), 'be05_tp2': armed(e + 0.005 * unit, t2),
        'be1r_tp2': armed(e + risk, t2), 'trail1r': trailing(),
        'time60': bracket(s, t1, 0, min(n, 60)), 'time240': bracket(s, t1, 0, min(n, 240)),
        'fix1r': bracket(s, e + risk), 'fix2r': bracket(s, e + 2 * risk), 'fix3r': bracket(s, e + 3 * risk),
        'wide2x': bracket(e - 2 * risk, e + 2 * (t1 - e)),
    }
    return {k: float((v - e) / unit) for k, v in exits.items()}

TF_RANK = {'5m': 1, '15m': 2, '1h': 3, '4h': 4}


def feature_builder(fut: np.ndarray, spot: np.ndarray, btc15: np.ndarray, fut_all: pl.DataFrame, oi_ts: np.ndarray,
                    oi_v: np.ndarray, fund: np.ndarray, h1_list: list):
    """
    Features of a potential trade at its entry time, from data the live bot has at that moment (futures 1m klines of
    the last 4h, the 15m frame, spot 1m klines of the last hour, OI of the last hour, funding, BTC's 15m closes, the
    coin's 1h candles). Directional readings are multiplied by the trade's direction. For the meta-labeling model
    (research_meta.py): which of a strategy's trades are worth taking.
    """
    from levels import atr_of
    from strategies.structure import coin_trend
    m_ts = fut[:, 0]
    s_ts = spot[:, 0] if len(spot) else np.empty(0)
    ind = fut_all.select('timestamp', 'atr', 'adx').to_numpy()
    btc_ts, btc_c = (btc15[:, 0] + QUARTER_MS, btc15[:, 4]) if len(btc15) else (np.empty(0), np.empty(0))
    h1_close = np.asarray([c[0] + HOUR_MS for c in h1_list]) if h1_list else np.empty(0)

    def flow(arr, a, b):
        qv = arr[a:b, 6].sum()
        return float((2 * arr[a:b, 7].sum() - qv) / qv) if qv > 0 else 0.0

    def build(t_ms: float, d: int, levels: Dict, plan: Dict, start_ms: float, vetoed_before: int) -> Dict:
        j = int(np.searchsorted(m_ts, t_ms - MINUTE_MS, side='right'))
        if j < 1441:
            return {}
        price = float(fut[j - 1, 4])
        closes = fut[j - 61:j, 4]
        lr = np.diff(np.log(closes))
        q = int(np.searchsorted(ind[:, 0] + QUARTER_MS, t_ms, side='right')) - 1
        atr15 = float(ind[q, 1]) if q >= 0 and ind[q, 1] == ind[q, 1] else None
        adx = float(ind[q, 2]) if q >= 0 and ind[q, 2] == ind[q, 2] else None
        day_qv = fut[j - 1440:j, 6].sum()
        lo24, hi24 = float(fut[j - 1440:j, 3].min()), float(fut[j - 1440:j, 2].max())
        pos = (price - lo24) / (hi24 - lo24) if hi24 > lo24 else 0.5
        h = int(np.searchsorted(h1_close, t_ms, side='right'))
        h1w = h1_list[max(0, h - 200):h]
        closes_1h = [c[4] for c in h1w]
        ema = None
        if len(closes_1h) >= 40:
            ema = closes_1h[0]
            for c in closes_1h[1:]:
                ema += 2 / 21 * (c - ema)
        atr1h = atr_of([list(c[:5]) for c in h1w]) if h1w else None
        b = int(np.searchsorted(btc_ts, t_ms, side='right')) - 1
        risk = abs(levels['entry'] - levels['sl'])
        hour = int(t_ms) // HOUR_MS % 24
        out = {
            'rr_tp1': levels['rr_tp1'], 'risk_pct': risk / levels['entry'],
            'risk_atr': risk / atr15 if atr15 else None,
            'tp1_atr': abs(levels['tp1'] - levels['entry']) / atr15 if atr15 else None,
            'tf_rank': TF_RANK.get(plan.get('tf'), 2), 'entry_confirm': 1.0 if plan.get('entry') == 'confirm' else 0.0,
            'wait_min': (t_ms - start_ms) / MINUTE_MS, 'vetoed_before': float(vetoed_before),
            'ret_1h_dir': d * (price / fut[j - 61, 4] - 1), 'ret_4h_dir': d * (price / fut[j - 241, 4] - 1),
            'ret_24h_dir': d * (price / fut[j - 1441, 4] - 1),
            'rv_1h_atr': float(lr.std() * price / atr15) if atr15 and len(lr) > 10 else None,
            'rvol_15m': float(fut[j - 15:j, 6].sum() / (day_qv / 96)) if day_qv > 0 else None,
            'flow_15m_dir': d * flow(fut, j - 15, j), 'flow_1h_dir': d * flow(fut, j - 60, j),
            'adx': adx, 'pos_24h_dir': pos if d > 0 else 1 - pos,
            'hour_sin': float(np.sin(2 * np.pi * hour / 24)), 'hour_cos': float(np.cos(2 * np.pi * hour / 24)),
            'weekend': 1.0 if (int(t_ms) // 86_400_000 + 3) % 7 >= 5 else 0.0,
            'coin_trend_dir': float(d * coin_trend(h1w)) if h1w else 0.0,
            'ema20_1h_atr_dir': d * (price - ema) / atr1h if ema and atr1h else None,
            'btc_1h_dir': d * float(btc_c[b] / btc_c[b - 4] - 1) if b >= 4 else None,
            'btc_4h_dir': d * float(btc_c[b] / btc_c[b - 16] - 1) if b >= 16 else None,
        }
        oi = _oi_change(oi_ts, oi_v, t_ms - HOUR_MS, t_ms)
        out['oi_1h'] = oi
        out['oi_1h_dir'] = d * oi if oi is not None else None
        if len(fund):
            from pretrain import _asof
            rate = _asof(fund[:, 0], fund[:, 1], t_ms)
            out['funding_dir'] = d * rate * 1e4 if rate is not None else None
        if len(s_ts):
            js = int(np.searchsorted(s_ts, t_ms - MINUTE_MS, side='right'))
            out['spot_flow_1h_dir'] = d * flow(spot, max(0, js - 60), js) if js > 60 else None
        return out

    return build

def _lifecycle(plan, strategy, d, row, start_ms, m_ts, minutes_all, fut, fund, oi_ts, oi_v,
               entry_levels, ltf_trigger, resample, simulate, _asof, replan=None, extra_veto=None,
               features=None, samples=None, placebo=None, spot_minutes=None) -> float:
    """
    Walk the card minute by minute from start_ms; fills `row`; returns when the card finished (ms). `replan(t_ms)`:
    the strategy's plan as of a 15m close (the live plan follows the chart until the entry; a continuation's plan is
    frozen in its zone), None while the plan does not exist. `extra_veto(levels, zone_since, trigger_ms)`: a
    strategy-specific trigger veto (the spring's test).
    """
    watch_ttl, zone_ttl, trade_ttl = strategy.ttls(plan['tf'])
    fixed_invalid = plan.get('invalid') if plan.get('fix_invalid') else None
    invalid, tp1 = plan.get('invalid'), plan['targets'][0]
    required_oi = strategy.name == 'breakout'
    interval = plan['trigger_minutes'] * MINUTE_MS

    def veto(levels, until_ms, extreme_ms=None) -> Optional[str]:
        # the live order: required / minimum confirmations (strategies/confirm.py), then the R:R minimum
        from strategies import confirm
        a = int(np.searchsorted(m_ts, until_ms - 2 * HOUR_MS, side='left'))
        b = int(np.searchsorted(m_ts, until_ms, side='left'))
        mins = minutes_all[a:b].tolist()
        spot = None
        if spot_minutes is not None and len(spot_minutes):
            s_ts = spot_minutes[:, 0]
            spot = spot_minutes[int(np.searchsorted(s_ts, until_ms - 2 * HOUR_MS)):int(np.searchsorted(s_ts, until_ms))].tolist()
        oi = _oi_change(oi_ts, oi_v, until_ms - HOUR_MS, until_ms)
        confirms = confirm.evaluate(strategy.name, d, mins, spot, oi, until_ms - HOUR_MS, until_ms,
                                    int(extreme_ms) if extreme_ms else None, None)
        reason = confirm.missing(strategy.name, confirms)
        if reason:
            return reason
        if CONFIG.levels.veto_low_rr and levels.get('low_rr'):
            return 'low_rr'
        return None

    def trade(levels, entered_ms) -> Optional[Dict]:
        """The journal's replay of an entry: net R at TP1 / TP2 / breakeven variant, or None without 8h of data."""
        first = -(-int(entered_ms) // MINUTE_MS) * MINUTE_MS          # the journal's first full minute after entry
        a = int(np.searchsorted(m_ts, first, side='left'))
        candles = fut[a:a + trade_ttl // 60].tolist()
        if len(candles) < trade_ttl // 60:
            return None
        rate = _asof(fund[:, 0], fund[:, 1], entered_ms) if len(fund) else None
        bars = [[c[0], c[1], c[2], c[3], c[4]] for c in candles]
        fee = None
        if ENTRY_MODE == 'maker':
            # a resting limit at the trigger's close: filled only when price trades back through it within
            # MAKER_WAIT_MIN minutes (the fills are the trades price went against: adverse selection included);
            # maker fee on the entry, no entry slippage, a taker fee on the exit (conservative: TPs could rest too)
            limit = levels['entry']
            k = next((i for i, c in enumerate(bars[:MAKER_WAIT_MIN])
                      if (c[3] < limit * (1 - 1e-4) if d > 0 else c[2] > limit * (1 + 1e-4))), None)
            if k is None:
                return {'filled': False, 'outcome': 'NOT_FILLED', 'rr_tp1': levels['rr_tp1'],
                        'risk_pct': abs(levels['entry'] - levels['sl']) / levels['entry'],
                        'r_tp1': None, 'r_tp2': None, 'r_be': None}
            res = simulate(levels, d, bars[k:], use_fill=False, funding_8h=rate)
            fee = MAKER_FEE + TAKER_FEE
        else:
            res = simulate(levels, d, bars, use_fill=True, funding_8h=rate)
            res['variants'] = exit_variants(bars, d, levels['sl'], levels['tp1'], levels['tp2'])
        out = {'filled': bool(res.get('filled')), 'outcome': res.get('outcome'), 'rr_tp1': levels['rr_tp1'],
               'risk_pct': abs(levels['entry'] - levels['sl']) / levels['entry']}
        entry = res.get('entry_fill') or levels['entry']
        for col in ('r_tp1', 'r_tp2', 'r_be'):
            out[col] = _net_r(res.get(col), entry, levels['sl'], fee) if out['filled'] else None
        out['variants'] = res.get('variants') or {}
        return out

    def sample(levels, entered_ms, res, reason):
        """A training example for the meta-labeling model: the trade's features at entry and its net R."""
        if samples is None or features is None or not res or not res['filled']:
            return
        f = features(entered_ms, d, levels, plan, start_ms, row['vetoed_triggers'] - (1 if reason else 0))
        if not f:
            return
        samples.append({'symbol': row['symbol'], 'ts_ms': int(entered_ms), 'setup': row['setup'],
                        'strategy': row['strategy'], 'direction': d, 'card_veto': row['vetoed'],
                        'trigger_veto': reason or '', 'r_tp1': res['r_tp1'], 'r_tp2': res['r_tp2'],
                        'r_be': res['r_be'], **{f"x_{k}": v for k, v in res.get('variants', {}).items()}, **f})

    def enter(levels, entered_ms) -> float:
        res = trade(levels, entered_ms)
        sample(levels, entered_ms, res, None)
        if placebo is not None and res is not None and res['filled']:
            # the same trade (direction, stop / target distances in %) at a random time of the same coin: the
            # result a system's timing must beat
            fake_ms = placebo(entered_ms)
            if fake_ms is not None:
                k = int(np.searchsorted(m_ts, fake_ms - MINUTE_MS, side='right'))
                if k > 0:
                    p0 = float(fut[k - 1, 4])
                    e0 = levels['entry']
                    fake = dict(levels, entry=p0, **{key: p0 * levels[key] / e0 for key in ('sl', 'tp1', 'tp2', 'tp3')})
                    pres = trade(fake, fake_ms)
                    if pres and pres['filled']:
                        row['pl_r_tp1'], row['pl_r_tp2'] = pres['r_tp1'], pres['r_tp2']
        if res is None:
            row['status'] = 'NO_DATA'
            return entered_ms
        row.update(status='ENTRY' if res['filled'] else 'SKIPPED', outcome=res['outcome'], rr_tp1=res['rr_tp1'],
                   risk_pct=res['risk_pct'], r_tp1=res['r_tp1'], r_tp2=res['r_tp2'], r_be=res['r_be'],
                   hold_min=(entered_ms - start_ms) / MINUTE_MS)
        return entered_ms + trade_ttl * 1000

    def vetoed_trade(levels, entered_ms, reason):
        """What the FIRST vetoed trigger would have given if taken (tests the veto itself)."""
        if row.get('vx_reason'):
            return
        res = trade(levels, entered_ms)
        if res and res['filled']:
            row.update(vx_reason=reason, vx_r_tp1=res['r_tp1'], vx_r_tp2=res['r_tp2'], vx_rr_tp1=res['rr_tp1'])
            sample(levels, entered_ms, res, reason)

    j = int(np.searchsorted(m_ts, start_ms - MINUTE_MS, side='right'))
    if plan['entry'] == 'confirm' and j > 0:
        price = float(fut[j - 1, 4])
        levels = entry_levels(plan, price, None, d)
        if levels and d * (price - levels['sl']) > 0:
            reason = veto(levels, start_ms)
            if reason is None:
                return enter(levels, start_ms)
            row['vetoed_triggers'] += 1
            row['veto_log'] += reason + ' '
            vetoed_trade(levels, start_ms, reason)
        if plan.get('confirm_only'):
            row['status'] = 'EXPIRED'                     # the system enters at its signal's close or not at all
            return start_ms
    status, zone_since = 'WATCH', None
    close_tf = (plan.get('invalid_close_min') or 0) * MINUTE_MS
    kind = plan.get('trigger', 'shift')
    from strategies.maniac import ifvg_trigger, in_session, pinbar_trigger
    from strategies.ict import fvg_trigger, touch_trigger
    near_edge = plan['zone_hi'] if d > 0 else plan['zone_lo']
    horizon = start_ms + (watch_ttl + zone_ttl) * 1000 + HOUR_MS
    current = plan
    while j < len(m_ts) and m_ts[j] < horizon:
        t_close = float(m_ts[j]) + MINUTE_MS
        high, low, close = float(fut[j, 2]), float(fut[j, 3]), float(fut[j, 4])
        against, favour = (low, high) if d > 0 else (high, low)
        if replan is not None and int(m_ts[j]) % QUARTER_MS == 0 and not (strategy.frozen_in_zone and status == 'ZONE'):
            current = replan(float(m_ts[j]))
            if current is not None and current.get('targets'):
                plan = current
                invalid = fixed_invalid if fixed_invalid is not None else plan.get('invalid')
                tp1 = plan['targets'][0]
                near_edge = plan['zone_hi'] if d > 0 else plan['zone_lo']
                interval = plan['trigger_minutes'] * MINUTE_MS
            else:
                current = None
        if current is None:
            # no plan (the leg stopped qualifying): the card waits, and expires after the waiting lifetime
            if t_close - start_ms > watch_ttl * 1000:
                row['status'] = 'EXPIRED'
                return t_close
            j += 1
            continue
        if invalid is not None and close_tf:
            # INVALID on a CLOSE of the system's timeframe beyond (a wick through is allowed)
            if int(t_close) % close_tf == 0 and d * (close - invalid) <= 0:
                row['status'] = 'INVALID'
                return t_close
        elif invalid is not None and d * (against - invalid) <= 0:
            row['status'] = 'INVALID'
            return t_close
        if plan.get('missable') and d * (favour - tp1) >= 0:
            row['status'] = 'MISSED'
            return t_close
        if plan.get('reset') is not None and status == 'ZONE' and d * (favour - plan['reset']) > 0:
            status, zone_since = 'WATCH', None       # the leg extended without a trigger: re-measured
        if status != 'ZONE' and d * (against - near_edge) <= 0:
            status, zone_since = 'ZONE', float(m_ts[j])
        if status == 'ZONE':
            a = int(np.searchsorted(m_ts, zone_since - (4 * CONFIG.levels.ltf_break_lookback + 2) * interval, side="left"))
            if kind == 'ifvg':
                a = int(np.searchsorted(m_ts, int(plan['trigger_from_ms']) - 45 * interval, side='left'))
            ltf = resample(minutes_all[a:j + 1].tolist(), plan['trigger_minutes'], t_close)
            if kind == 'fvg':
                trigger = fvg_trigger(ltf, d, int(zone_since), interval)
            elif kind == 'touch':
                trigger = touch_trigger(ltf, d, int(zone_since), interval, plan['zone_lo'], plan['zone_hi'])
            elif kind == 'pinbar':
                trigger = pinbar_trigger(ltf, d, int(zone_since), interval, plan['zone_lo'], plan['zone_hi'])
            elif kind == 'ifvg':
                trigger = ifvg_trigger(ltf, d, int(plan['trigger_from_ms']), int(zone_since), interval)
            else:
                trigger = ltf_trigger(ltf, d, int(zone_since), interval)
            if trigger:
                if t_close - trigger['time'] > interval + 2 * MINUTE_MS:
                    zone_since = trigger['time']
                else:
                    levels = entry_levels(plan, trigger['entry'], trigger['extreme'], d)
                    if levels and d * (close - levels['sl']) > 0:
                        reason = extra_veto(levels, zone_since, trigger['time']) if extra_veto else None
                        if reason is None and plan.get('session') and not in_session(trigger['time'], tuple(plan['session'])):
                            reason = 'off_session'
                        reason = reason or veto(levels, trigger['time'], trigger.get('extreme_time'))
                        if reason is None:
                            return enter(levels, t_close + 5_000)
                        row['vetoed_triggers'] += 1
                        row['veto_log'] += reason + ' '
                        vetoed_trade(levels, t_close + 5_000, reason)
                        zone_since = trigger['time']
                        if plan.get('single_touch'):
                            row['status'] = 'EXPIRED'         # Seiden: the first touch was the zone's only chance
                            return t_close
            if t_close - zone_since > zone_ttl * 1000:
                row['status'] = 'EXPIRED'
                return t_close
        elif t_close - start_ms > watch_ttl * 1000:
            row['status'] = 'EXPIRED'
            return t_close
        j += 1
    row['status'] = 'EXPIRED'
    return float(m_ts[j - 1]) + MINUTE_MS if j else start_ms


def _block_ci(values: np.ndarray, blocks: np.ndarray, seed: int = 7):
    from research_edges import block_stats
    return block_stats(values, blocks, seed)


def report(df: pl.DataFrame, start: date, end: date) -> str:
    from research_edges import bh
    lines = [f"# Historical card replay (logic {CONFIG.journal.logic_version})", '',
             f"Window {start} .. {end}, {df['symbol'].n_unique()} coins, {len(df)} cards. R = result in stop units of an "
             f"entry replayed like the journal (fill at the next full minute's open + {CONFIG.levels.slippage_bps:g} bps, "
             f"stop exits slipped, targets traded {CONFIG.levels.target_through_bps:g} bps through, funding), NET of the "
             f"{CONFIG.journal.fee_round_trip * 100:.2f}% round-trip fee. R TP1 = everything exits at TP1 (or the stop / "
             f"the 8h mark); R TP2 likewise at TP2; R BE = stop to breakeven once TP1 traded, exit at TP2. [90%] = block "
             f"bootstrap over 4h x direction blocks; q = Benjamini-Hochberg over the rows of the table.", '',
             '| Setup | vetoed | cards | entries | invalid | missed | expired | avg R:R | win TP1 | R TP1 [90%] | q | R TP2 | R BE | median risk |',
             '|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|']
    groups = df.group_by(['setup', 'vetoed'], maintain_order=True).agg(pl.len().alias('n')).sort(['setup', 'vetoed'])
    stats = []
    for setup, vetoed, n in groups.iter_rows():
        g = df.filter((pl.col('setup') == setup) & (pl.col('vetoed') == vetoed))
        e = g.filter(pl.col('status') == 'ENTRY')
        counts = {s: g.filter(pl.col('status') == s).height for s in ('INVALID', 'MISSED', 'EXPIRED')}
        if e.height >= 10:
            r1 = e['r_tp1'].to_numpy().astype(float)
            blocks = (e['ts_ms'].to_numpy() // H4_MS) * 2 + (e['direction'].to_numpy() > 0)
            mean, lo, hi, p, k = _block_ci(r1, blocks)
        else:
            mean = lo = hi = p = float('nan')
        stats.append((setup, vetoed, n, e, counts, mean, lo, hi, p))
    qs = bh([s[-1] for s in stats])
    f = lambda v, d=2: '—' if v is None or v != v else f"{v:+.{d}f}"  # noqa: E731
    for (setup, vetoed, n, e, counts, mean, lo, hi, p), q in zip(stats, qs):
        win = float((e['r_tp1'] > 0).mean()) if e.height else float('nan')
        lines.append(
            f"| {setup} | {vetoed or '—'} | {n} | {e.height} | {counts['INVALID']} | {counts['MISSED']} | {counts['EXPIRED']} | "
            f"{f(e['rr_tp1'].mean() if e.height else None)} | {'—' if win != win else f'{win:.0%}'} | "
            f"{f(mean, 3)} [{f(lo, 3)}..{f(hi, 3)}] | {'—' if q != q else f'{q:.3f}'} | "
            f"{f(e['r_tp2'].mean() if e.height else None, 3)} | {f(e['r_be'].mean() if e.height else None, 3)} | "
            f"{'—' if not e.height else f'{e['risk_pct'].median() * 100:.2f}%'} |")
    lines += ['', '## What the vetoed triggers would have given (the first vetoed trigger of each card, taken anyway)', '',
              '| Setup | card veto | trigger veto | trades | avg R:R | win TP1 | R TP1 [90%] | q | R TP2 |',
              '|---|---|---|---:|---:|---:|---|---:|---:|']
    vx = df.filter(pl.col('vx_reason') != '')
    vstats = []
    for (setup, vetoed, reason), g in sorted(vx.group_by(['setup', 'vetoed', 'vx_reason']), key=lambda kv: kv[0]):
        r1 = g['vx_r_tp1'].to_numpy().astype(float)
        blocks = (g['ts_ms'].to_numpy() // H4_MS) * 2 + (g['direction'].to_numpy() > 0)
        stat = _block_ci(r1, blocks) if g.height >= 10 else (float('nan'),) * 5
        vstats.append((setup, vetoed, reason, g, stat))
    vq = bh([st[3] for *_, st in vstats])
    for (setup, vetoed, reason, g, (mean, lo, hi, p, k)), q in zip(vstats, vq):
        win = float((g['vx_r_tp1'] > 0).mean())
        lines.append(f"| {setup} | {vetoed or '—'} | {reason} | {g.height} | {f(g['vx_rr_tp1'].mean())} | {win:.0%} | "
                     f"{f(mean, 3)} [{f(lo, 3)}..{f(hi, 3)}] | {'—' if q != q else f'{q:.3f}'} | {f(g['vx_r_tp2'].mean(), 3)} |")
    return '\n'.join(lines) + '\n'


def main():
    cfg = CONFIG.pretrain
    parser = argparse.ArgumentParser()
    parser.add_argument('--months', type=int, default=cfg.months)
    parser.add_argument('--min-volume', type=float, default=cfg.min_volume_usd)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--end', default=None, help='last day of the window (YYYY-MM-DD; default yesterday): an '
                        'earlier window is a holdout for decisions made on the recent one')
    parser.add_argument('--out', default=os.path.join('research', 'cards_6m.md'))
    parser.add_argument('--rows', default='research_cards.parquet')
    parser.add_argument('--samples', default='research_samples.parquet',
                        help='every taken and first vetoed trade with its entry features (research_meta.py)')
    parser.add_argument('--entry', choices=('market', 'maker'), default='market',
                        help='entry execution: the journal\'s market fill, or a resting limit at the trigger (maker fee)')
    parser.add_argument('--holdout', type=int, default=0,
                        help='> 0: the report splits the window into development and the last N months (holdout), '
                             'with the placebo comparison (research_maniac.report)')
    parser.add_argument('--what', choices=('events', 'phases', 'all'), default='events',
                        help='events: SWEEP / BREAKOUT; phases: trend / wyckoff phase setups')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-7s | %(message)s', datefmt='%H:%M:%S')
    from history import Archive
    from pretrain import select_coins
    end = date.fromisoformat(args.end) if args.end else datetime.now(timezone.utc).date() - timedelta(days=1)
    start = end - timedelta(days=30 * args.months)
    coins = select_coins(Archive(rate_bytes=4e7), start, end, args.min_volume)
    if args.limit:
        coins = coins[:args.limit]
    os.environ['RESEARCH_ENTRY'] = args.entry           # the worker processes read ENTRY_MODE at import
    jobs = [(k, f, s, start.isoformat(), end.isoformat(), days, args.what) for k, f, s, days in coins]
    rows: List[Dict] = []
    samples: List[Dict] = []
    started = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(replay_coin, job): job[0] for job in jobs}
        for n, fut in enumerate(as_completed(futures), 1):
            try:
                coin_rows, coin_samples = fut.result()
                rows += coin_rows
                samples += coin_samples
            except Exception as e:
                logger.warning(f"cards: {futures[fut]} failed ({type(e).__name__} {e})")
            if n % 25 == 0 or n == len(jobs):
                logger.info(f"cards: {n}/{len(jobs)} coins in {time.time() - started:.0f}s ({len(rows)} cards)")
    df = pl.DataFrame(rows, infer_schema_length=None)
    df.write_parquet(args.rows)
    if samples:
        pl.DataFrame(samples, infer_schema_length=None).write_parquet(args.samples)
        logger.info(f"cards: {len(samples)} trade samples with features -> {args.samples}")
    if args.holdout:
        from research_maniac import report as split_report
        text = split_report(df, start, end, end - timedelta(days=30 * args.holdout), title='our classes')
    else:
        text = report(df, start, end)
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print(text)


if __name__ == '__main__':
    main()
