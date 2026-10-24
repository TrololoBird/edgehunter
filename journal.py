"""
Signal journal: every new signal is stored in SQLite with the market state at that moment, and a background
loop later fills in what the price actually did (15m / 1h / 4h returns, 4h max favorable/adverse move) from
Binance 1m futures klines. `stats.py` turns the table into per-setup statistics.

Writes never block the event loop: the connection runs in WAL mode and every call from async code goes through
asyncio.to_thread (the a* methods), serialized by a lock. Every 15 minutes the prices of the whole universe are
stored (`universe` table): stats.py measures Edge against that real market baseline instead of the median of
the coins that happened to produce signals.
"""
import asyncio
import bisect
import json
import logging
import sqlite3
import threading

import numpy as np
import time
from typing import Dict, List, Optional, Tuple

from config import CONFIG
from levels import simulate
from strategies import confirm
from scorer import LONG_PHASES, SHORT_PHASES


def wilson_upper(hits: int, n: int, z: float = 1.96) -> float:
    """The upper end of the 95% Wilson score interval of a proportion (hits of n)."""
    if n <= 0:
        return 1.0
    p = hits / n
    centre = p + z * z / (2 * n)
    spread = z * ((p * (1 - p) + z * z / (4 * n)) / n) ** 0.5
    return min(1.0, (centre + spread) / (1 + z * z / n))


def _anchor_json(plan: Optional[Dict]) -> Optional[str]:
    anchor = (plan or {}).get('anchor')
    return json.dumps(anchor, separators=(',', ':'), default=float) if anchor else None


def load_pretrained() -> Optional[Dict]:
    """The models pretrain.py built from the public archive (None when it was not run)."""
    import os
    import pickle
    path = CONFIG.pretrain.path
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'rb') as fh:
            return pickle.load(fh)      # our own file, written by pretrain.py
    except Exception as e:
        logging.getLogger(__name__).warning(f"Pretrained models unreadable ({type(e).__name__} {e}); run pretrain.py again")
        return None


def pretrained_current(state: Optional[Dict]) -> bool:
    """
    The pretrained P(edge) was built by the current signal logic. A model of an older logic_version learned rows the
    bot no longer writes (eng-7: rows of older versions saw up to 55s of the future in their Tier-0 inputs), so it
    is not used. The live-loopside-v1 generator marker is also required; legacy or untagged P(edge)
    cannot pass on logic_version alone. Regime history is handled separately.
    """
    return (bool(state) and state.get('logic_version') == CONFIG.journal.logic_version
            and state.get('success_generator') == 'live-loopside-v1')


def _strategy_of(group_key: str) -> Optional[str]:
    from strategies import SETUPS
    key = group_key.split(' ', 1)[1] if group_key.split(' ', 1)[0] in ('ENTRY', 'SL', 'TP3', 'CLOSED', 'INVALID', 'MISSED', 'EXPIRED') else group_key
    entry = SETUPS.get(key)
    return entry[0] if entry else None

logger = logging.getLogger(__name__)

# Horizon label -> minutes after the signal
# 8h = a trade's lifetime (levels.trade_ttl_sec): entries are replayed over it (a 4h replay marked every longer trade
# to its 4h close)
HORIZONS = {'15m': 15, '1h': 60, '4h': 240, '8h': 480}
# Outcome windows start at the first FULL minute after the signal; a horizon is due once its last 1m candle has
# closed, i.e. up to one minute + this margin after ts + horizon. Evaluated earlier, the last candle was still
# running and its "close" was the live price (measured: 41 of 53 rows off by up to 0.2%).
CLOSE_MARGIN_MS = 5_000


STRATEGY_CLASS = {'breakout': 'trend', 'continuation': 'trend', 'orb': 'trend', 'cup_handle': 'trend',
                  'trendline': 'structure', 'sweep': 'structure', 'wyckoff': 'structure', 'supply_demand': 'structure',
                  'connors': 'mean_reversion', 'bollinger': 'mean_reversion', 'market_profile': 'mean_reversion',
                  'pump': 'mean_reversion', 'po3': 'structure', 'oi_build': 'trend'}


def strategy_class(mode: Optional[str]) -> Optional[str]:
    """eng-148 (audit 3 / 31): the exit class a strategy belongs to, journaled for a later TP1 floor by class."""
    return STRATEGY_CLASS.get(mode or '')


def excursions(row: Dict, window: List) -> Dict:
    """eng-148 (stage 0): the trade's MFE / MAE in R up to its stop (or the window's end), over the first 10 15m bars
    (when the window covers them), and the best move in the 15 15m bars after the stop
    (post_stop_mfe_r: how often the stop was a raid that then went the trade's way). The 1m window starts at the entry."""
    e, sl, d = row.get('entry'), row.get('sl'), row.get('direction')
    if not e or not sl or d not in (-1, 1) or d * (e - sl) <= 0 or not window:
        return {}
    risk = d * (e - sl)
    # 15m bars for every timeframe (review of eng-148: 4h-tf bars need days of minutes, only survivors had them)
    bar = 15

    def fav(k):
        return d * ((float(k[2]) if d > 0 else float(k[3])) - e) / risk

    def adv(k):
        return d * ((float(k[3]) if d > 0 else float(k[2])) - e) / risk

    stop_i = next((i for i, k in enumerate(window) if adv(k) <= -1), None)
    through = CONFIG.levels.target_through_bps / 1e4
    if row.get('limit_entry'):
        # a resting limit the first hour only touched (never traded through it) - the demo / replay fill is optimistic
        hit = any((float(k[3]) < e * (1 - through)) if d > 0 else (float(k[2]) > e * (1 + through)) for k in window[:60])
        opt = {'optimistic_fill': int(not hit)}
    else:
        opt = {}
    life = window[:stop_i + 1] if stop_i is not None else window
    out = {'mfe_life_r': max(fav(k) for k in life), 'mae_life_r': max(-1.0, min(adv(k) for k in life)), **opt}
    if len(window) >= 10 * bar:
        n10 = window[:10 * bar]
        out['mfe_n10_r'], out['mae_n10_r'] = max(fav(k) for k in n10), min(adv(k) for k in n10)
    if stop_i is not None and len(window) >= stop_i + 1 + 15 * bar:
        out['post_stop_mfe_r'] = max(fav(k) for k in window[stop_i + 1:stop_i + 1 + 15 * bar])
    # stage 3 shadow (audit 14): a time stop - out at the close of the 8th working bar when the trade has not made
    # 0.4R by then and was not stopped before; 1 = it would have fired, time_stop_r = the R of that exit (before costs)
    n8 = 8 * bar
    if len(window) >= n8 and (stop_i is None or stop_i >= n8):
        fired = max(fav(k) for k in window[:n8]) < 0.4
        out['time_stop'] = int(fired)
        if fired:
            out['time_stop_r'] = d * (float(window[n8 - 1][4]) - e) / risk
    # on the first 8h for every entry (the life relabel would give only the survivors a longer window)
    out.update(_shadow_exits(row, window[:480], e, row.get('sl'), d, risk))
    return out


def _to_tp1(window: List, start: int, e: float, sl: float, tp1: float, d: int, risk: float) -> float:
    """The R of a trade from minute `start`: the stop's touch first (-1, the conservative order inside a minute), else
    TP1's touch (+R:R), else out at the window's last close."""
    for k in window[start:]:
        lo, hi = float(k[3]), float(k[2])
        if (lo <= sl) if d > 0 else (hi >= sl):
            return -1.0
        if (hi >= tp1) if d > 0 else (lo <= tp1):
            return d * (tp1 - e) / risk
    return d * (float(window[-1][4]) - e) / risk


def _shadow_exits(row: Dict, window: List, e: float, sl: float, d: int, risk: float) -> Dict:
    """
    eng-149 (plan eng-148 stage 3; journal only, before costs, to TP1 or the 8h window's end):
    - two_stop_r (audit 14): two contours - out at the close of the first 15m bar (UTC-aligned) that CLOSED beyond the
      stop, or at the touch of a far stop 0.7 ATR (the plan's working ATR, atr_entry) beyond it; base_stop_r = the
      same trade with the plain stop on the touch, on the same window (the pair to compare);
    - retest_r (audit 15; sweeps with a zone_far): the second test of the entry after the price left it by >= 0.5R
      with no 15m close beyond the zone's far edge before it - the same stop / TP1 from that re-entry.
    """
    tp1, out = row.get('tp1'), {}
    if not tp1:
        # a system without a target (ORB, Turtles, Connors): held 8h with the stop on the touch (ORB opens compared)
        stop_i = next((i for i, k in enumerate(window) if ((float(k[3]) <= sl) if d > 0 else (float(k[2]) >= sl))), None)
        if stop_i is not None or len(window) >= 480:
            out['hold8_r'] = -1.0 if stop_i is not None else d * (float(window[-1][4]) - e) / risk
        return out
    if d * (tp1 - e) <= 0:
        return out
    out['base_stop_r'] = _to_tp1(window, 0, e, sl, tp1, d, risk)
    atr = row.get('atr_entry')
    if atr and atr > 0:
        far = sl - d * 0.7 * atr
        r = None
        for k in window:
            lo, hi, close = float(k[3]), float(k[2]), float(k[4])
            if (lo <= far) if d > 0 else (hi >= far):
                r = d * (far - e) / risk
                break
            if (hi >= tp1) if d > 0 else (lo <= tp1):
                r = d * (tp1 - e) / risk
                break
            if int(k[0]) % 900_000 == 840_000 and d * (close - sl) < 0:
                r = d * (close - e) / risk          # the 15m bar's close beyond the stop
                break
        out['two_stop_r'] = r if r is not None else d * (float(window[-1][4]) - e) / risk
    far_edge = row.get('zone_far')
    if far_edge:
        left = False
        for i, k in enumerate(window):
            lo, hi, close = float(k[3]), float(k[2]), float(k[4])
            if int(k[0]) % 900_000 == 840_000 and d * (close - far_edge) < 0:
                break                               # the zone's far edge broken by a 15m body: no second test
            if not left:
                left = d * ((hi if d > 0 else lo) - e) / risk >= 0.5
            elif (lo <= e) if d > 0 else (hi >= e):
                out['retest_r'] = _to_tp1(window, i, e, sl, tp1, d, risk)
                break
    return out


def _zone_far(tracked) -> Optional[float]:
    """eng-149: the far edge of a sweep's entry zone (the FVG's far side once armed, else the zone's), None elsewhere."""
    plan = tracked.plan or {}
    if tracked.mode != 'sweep':
        return None
    lo, hi = (plan.get('fvg') or [plan.get('zone_lo'), plan.get('zone_hi')])[:2]
    if lo is None or hi is None:
        return None
    return float(min(lo, hi) if tracked.direction > 0 else max(lo, hi))


def horizon_due_ms(ts_ms: int, minutes: int) -> int:
    """Epoch ms from which the `minutes` horizon of a row logged at ts_ms can be evaluated."""
    first_minute = -(-ts_ms // 60_000) * 60_000
    return first_minute + minutes * 60_000 + CLOSE_MARGIN_MS

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY,
    ts_ms INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    kind TEXT NOT NULL,            -- 'structured' | 'anomaly' | 'setup' | 'entry' | 'card'
    group_key TEXT NOT NULL,       -- e.g. 'BULL A', 'BULL a (partial)', 'BEAR D', 'IMPULSE UP', 'ENTRY BULL B'
    direction INTEGER NOT NULL,    -- +1 bullish, -1 bearish, 0 no direction
    price REAL NOT NULL,           -- futures last price at the signal
    long_score INTEGER, short_score INTEGER, phases TEXT, tier0 INTEGER, tier2 INTEGER,
    rvol_1m REAL, oi_change_5m REAL, price_change_5m REAL, delta_ratio REAL, funding_8h REAL,
    ret_15m REAL, ret_1h REAL, ret_4h REAL, mfe_4h REAL, mae_4h REAL,
    eval_failed INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(ts_ms);
CREATE INDEX IF NOT EXISTS idx_signals_group ON signals(group_key);
CREATE TABLE IF NOT EXISTS universe (
    ts_ms INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    price REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_universe_ts ON universe(ts_ms);
CREATE INDEX IF NOT EXISTS idx_universe_sym ON universe(symbol, ts_ms, price);
-- Every live liquidation of every venue (prices in Binance units) and snapshots of the liquidation LEVELS the level map
-- used (estimated clusters 'liq_est', real Hyperliquid account liquidation prices 'liq_hl'): a forward test of whether
-- liquidations happen where the map expects them once price gets there (the map drops crossed clusters, so only a
-- snapshot taken BEFORE price arrives can be checked)
CREATE TABLE IF NOT EXISTS liquidations (
    ts_ms INTEGER NOT NULL, symbol TEXT NOT NULL, price REAL NOT NULL, usd REAL NOT NULL, side INTEGER NOT NULL,
    venue TEXT
);
CREATE INDEX IF NOT EXISTS idx_liquidations ON liquidations(symbol, ts_ms);
CREATE TABLE IF NOT EXISTS liq_levels (
    ts_ms INTEGER NOT NULL, symbol TEXT NOT NULL, kind TEXT NOT NULL, price REAL NOT NULL, side INTEGER, usd REAL,
    ref_price REAL
);
CREATE INDEX IF NOT EXISTS idx_liq_levels ON liq_levels(symbol, ts_ms);
-- eng-132: a strategy that did not run on a coin for want of history ('skip: history N < M'), once a coin, strategy, day
CREATE TABLE IF NOT EXISTS history_skips (
    ts_ms INTEGER NOT NULL, symbol TEXT NOT NULL, strategy TEXT NOT NULL, held INTEGER NOT NULL, needed INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_skips ON history_skips(ts_ms);
"""

# Columns added after the first release; created on old databases by _migrate()
EXTRA_COLUMNS = {
    'whale_net_5m': 'REAL',
    # eng-87: a card that ended WITHOUT an entry (EXPIRED / MISSED): the entry / stop its plan had at the zone's line -
    # MISSED cards had no levels at all, so what was missed could not be measured in R
    'plan_entry': 'REAL', 'plan_sl': 'REAL',
    # eng-88: OI over 15 / 60 minutes; the 5m taker flow as a share of the 24h volume (futures net, spot net) - the
    # whale-alert channels' normalisation ("order size 5.49% of the 24h volume")
    'oi_chg_15m': 'REAL', 'oi_chg_60m': 'REAL', 'flow_pct_5m': 'REAL', 'spot_flow_pct_5m': 'REAL',
    # eng-89: rush orders (one taker order over several levels) in the last 10 / 30 s, net count, USD, z vs the last hour;
    # the 5m futures flow over the book's depth within 1% (signed)
    'rush_n_10s': 'REAL', 'rush_n_30s': 'REAL', 'rush_net_30s': 'REAL', 'rush_usd_30s': 'REAL', 'rush_z_30s': 'REAL',
    'flow_depth_5m': 'REAL',
    # eng-100: the market regime at the signal - BTC's 7-day return over closed daily candles
    'btc_mom_7d': 'REAL',
    # eng-101: the shadowed vetoes (strategies.shadow_vetoes) that would have blocked this row's setup / entry
    'shadow_veto': 'TEXT',
    # eng-104: the one regime (strategies/regime.py) at the entry: 'range pos 0.40 adx 23.6 h1 -1 h4 -1'
    'regime2': 'TEXT',
    # eng-108: the values of removed thresholds (sweep volume / depth / pool age), journaled to look at them later
    'sweep_rvol': 'REAL', 'sweep_depth_atr': 'REAL', 'pool_age_h': 'REAL',
    # eng-124: the stop's level kind and its measured pierce p50 / p80 / p90 (% of price): '<kind> 0.120/0.250/0.400'
    'stop_pierce': 'TEXT',
    # Signal-logic version that produced the row (NULL = before versioning)
    'logic_version': 'TEXT',
    # Levels of entry rows (levels.py) and their replay (levels.simulate)
    'entry': 'REAL', 'sl': 'REAL', 'tp1': 'REAL', 'tp2': 'REAL', 'tp3': 'REAL',
    'filled': 'INTEGER', 'outcome': 'TEXT', 'r_tp1': 'REAL', 'r_tp2': 'REAL',
    # mtf-4: manual fill, R:R, veto / confirmation reasons
    'entry_fill': 'REAL', 'rr_tp1': 'REAL', 'low_rr': 'INTEGER', 'vetoed': 'TEXT', 'of_confirm': 'TEXT',
    # mtf-4 features (order flow, multi-venue, positioning): stats.py splits Edge by them
    'price_z': 'REAL', 'oi_z': 'REAL', 'spot_delta_1h': 'REAL', 'perp_delta_1h': 'REAL', 'perp_led': 'INTEGER',
    'spot_cvd_5m': 'REAL', 'futures_cvd_5m': 'REAL', 'agg_cvd_5m': 'REAL', 'agg_oi_change_5m': 'REAL',
    'agg_ready': 'INTEGER', 'top_venue': 'TEXT', 'top_venue_share': 'REAL', 'liq_long_5m': 'REAL',
    'liq_short_5m': 'REAL', 'cluster': 'INTEGER', 'depth_imb': 'REAL', 'top_ratio': 'REAL', 'basis': 'REAL',
    'sec_into_candle': 'INTEGER',
    # ml.py: IsolationForest score, market regime, P(4h edge > 0) of the online model (shadow)
    'ml_score': 'REAL', 'regime': 'TEXT', 'p_edge': 'REAL',
    # mtf-5: level-map sources of the entry zone / targets / stop, card outcomes (kind='card') with their reason
    'zone_src': 'TEXT', 'tp1_src': 'TEXT', 'tp2_src': 'TEXT', 'tp3_src': 'TEXT', 'sl_src': 'TEXT', 'reason': 'TEXT',
    'setup_ts_ms': 'INTEGER',
    # positioning.py: Binance long/short accounts (global / top), Hyperliquid large accounts' net position, Coinbase premium
    'ls_global': 'REAL', 'ls_top': 'REAL', 'hl_net_usd': 'REAL', 'cb_premium': 'REAL', 'market_crowd': 'INTEGER',
    # eng-1: the strategy and its anchor (JSON), the market / coin context (universe median and BTC moves, the coin's
    # 1h trend, last hour's ATR / ATR14) and the replay with the stop at breakeven after TP1 (exit at TP2)
    'strategy': 'TEXT', 'anchor': 'TEXT', 'mkt_1h': 'REAL', 'mkt_4h': 'REAL', 'btc_1h': 'REAL', 'btc_4h': 'REAL', 'mkt_1d': 'REAL', 'btc_1d': 'REAL', 'coin_trend': 'INTEGER',
    'vol_ratio': 'REAL', 'r_be': 'REAL', 'outcome_h': 'INTEGER',
    # eng-2: the coin's 24h futures quote volume (liquidity: patterns on thin coins are one order's work)
    'volume_24h': 'REAL',
    # eng-4: the 8h horizon (entries replayed over the trade's life), the other venues' funding and long/short
    # ratios, time of day, the sweep candle's liquidations / OI change
    'ret_8h': 'REAL', 'agg_funding_8h': 'REAL', 'ls_bybit': 'REAL', 'ls_okx': 'REAL', 'hour_utc': 'INTEGER',
    'weekend': 'INTEGER', 'liq_on_wick': 'REAL', 'oi_change_sweep': 'REAL', 'adx': 'REAL',
    # eng-3: entry confirmations (strategies/confirm.py, JSON {name: true / false / null | order-flow kind}) and how
    # many were positive
    'confirms': 'TEXT', 'conf_n': 'INTEGER',
    # eng-137 (audit A02): how the rest of the entry minute was judged ('trades' / 'clean' / 'ambiguous') and the
    # pessimistic card R when that minute's range reached the stop with no trades to order it (= card_r otherwise)
    'entry_min': 'TEXT', 'card_r_low': 'REAL',
    # the coin's weekly trend (distance from its weekly EMA in weekly standard deviations) and the universe's share
    # above its weekly EMA: context, never a filter (the weekly EMA tested as no level of its own, 2026-09-27)
    'trend_w': 'REAL', 'breadth_w': 'REAL',
    # ICT premium / discount: the entry's place in the 48h dealing range for its direction (0 = cheapest end)
    'range_pos': 'REAL',
    # eng-147: the zone's trade-side edge at the trigger and how far the trigger close ran past it (working-tf ATRs);
    # the excursions over 4h from the ENTRY in R, signed by the direction (mfe_4h / mae_4h are raw highs / lows vs
    # the signal price, whatever the direction)
    'zone_edge': 'REAL', 'trigger_over_atr': 'REAL', 'mfe_r': 'REAL', 'mae_r': 'REAL',
    # eng-148 (stage 0): excursions in R over the trade's life (to the stop / the window's end), over 10 15m bars,
    # the best move in 15 15m bars AFTER a stop; the cost in R; the strategy class; the place
    # in the pass's crowd ranking (0 = best); the residual R:R from the trigger price; a limit fill the price only
    # touched (no trade through by a tick: optimistic on the demo)
    'mfe_life_r': 'REAL', 'mae_life_r': 'REAL', 'mfe_n10_r': 'REAL', 'mae_n10_r': 'REAL', 'post_stop_mfe_r': 'REAL',
    'cost_r': 'REAL', 'strat_class': 'TEXT', 'crowd_pos': 'INTEGER', 'rr_trigger': 'REAL', 'optimistic_fill': 'INTEGER',
    'time_stop': 'INTEGER', 'time_stop_r': 'REAL',
    # eng-149 (plan eng-148 stages 0.4 / 2.4 / 3.2 / 3.4 / 3.5 / 3.7 / 3.8; journal only): see scanner._shadow_market /
    # _shadow_coin and journal.excursions
    'btc_below_ema50_4h': 'INTEGER', 'liq_cascade_2h': 'REAL', 'mkt_down_alt': 'INTEGER', 'smt_majors': 'INTEGER',
    'nr4': 'INTEGER', 'nr7': 'INTEGER', 'inside_day': 'INTEGER', 'atr_ratio': 'REAL', 'vol_regime': 'TEXT',
    'range_tf': 'TEXT', 'range_pos_tf': 'REAL', 'range_pos_1h': 'REAL', 'zone_moved': 'TEXT', 'zone_move_atr': 'REAL', 'sl_old': 'REAL', 'sl_near': 'REAL',
    'atr_entry': 'REAL', 'zone_far': 'REAL', 'two_stop_r': 'REAL', 'base_stop_r': 'REAL', 'retest_r': 'REAL',
    'hold8_r': 'REAL',
    # extdata.py: Deribit BTC DVOL and its 1h change, BTC options put / call OI; the next-funding spread across
    # Binance / Bybit / Hyperliquid (8h-equivalent); OKX / Bybit book imbalance within 0.5%
    'dvol_btc': 'REAL', 'dvol_chg_1h': 'REAL', 'pc_oi_btc': 'REAL', 'funding_spread': 'REAL',
    'okx_book_imb': 'REAL', 'bybit_book_imb': 'REAL',
    # eng-134 shadow: Upbit KRW premium % over the Binance futures price (extdata.kimchi), journal only;
    # eng-135 shadow: the coin's newest Binance / Upbit announcement (event_risk.news_of) and its age in hours
    'kimchi_prem': 'REAL', 'news': 'TEXT', 'news_age_h': 'REAL',
    # iceberg.py: hidden limit orders refilled at one price over the last 5 minutes (bid - ask USD, count)
    'iceberg_net_5m': 'REAL', 'iceberg_n_5m': 'REAL', 'daily_bias': 'REAL', 'weekly_bias': 'REAL', 'btc_bias': 'REAL', 'vpin': 'REAL', 'vol_entropy': 'REAL', 'lead_venue': 'TEXT', 'lead_corr': 'REAL', 'card_r': 'REAL', 'card_id': 'TEXT', 'funding_hours': 'REAL',
    'prem_1h': 'REAL', 'prem_z': 'REAL', 'funding_1h': 'REAL', 'oi_vol': 'REAL', 'er_1h': 'REAL', 'chop_1h': 'REAL',
    'rs_btc_z': 'REAL', 'event_risk': 'TEXT', 'near52': 'REAL', 'vol_rank': 'REAL', 'liq_proxy': 'REAL',
    'units': 'REAL', 'best_tp': 'INTEGER', 'trend_4h': 'REAL', 'trend_1d': 'REAL', 'rr_blend': 'REAL', 'rr_reason': 'TEXT',
    'weis_ratio': 'REAL', 'tp1_min': 'REAL', 'limit_entry': 'INTEGER',
    # audit 2026-10-18: the thirds-model expectancy at the entry (exp_model, exp_note when it was only a shadow) and the
    # nearest opposing level before TP1 (obstacle_r in R from the entry, its source): diagnostics, never a filter
    'exp_model': 'REAL', 'exp_note': 'TEXT', 'obstacle_r': 'REAL', 'obstacle_src': 'TEXT',
    # eng-133 shadow features (extdata.macro_loop): TradFi perpetuals' changes %, NYSE session flag, previous VIX close,
    # Fear & Greed, spot-ETF net flow USD m (1 day / 3 days, visible from D+1 08:00 UTC): journal only, never a filter
    'xau_chg_1h': 'REAL', 'xau_chg_24h': 'REAL', 'oil_chg_1h': 'REAL', 'oil_chg_24h': 'REAL', 'spy_chg_1h': 'REAL', 'spy_chg_24h': 'REAL', 'qqq_chg_1h': 'REAL', 'qqq_chg_24h': 'REAL', 'us_session': 'REAL', 'vix_prev': 'REAL', 'fng': 'REAL', 'etf_flow_1d': 'REAL', 'etf_flow_3d': 'REAL',
}

FEATURE_KEYS = {
    # journal column: signal key
    'price_z': 'price_z', 'oi_z': 'oi_z', 'spot_delta_1h': 'spot_delta_1h', 'perp_delta_1h': 'perp_delta_1h',
    'spot_cvd_5m': 'spot_cvd_5m', 'futures_cvd_5m': 'futures_cvd_5m', 'agg_cvd_5m': 'agg_cvd_5m',
    'agg_oi_change_5m': 'agg_oi_change_5m', 'top_venue': 'top_venue', 'top_venue_share': 'top_venue_share',
    'liq_long_5m': 'liq_long_5m', 'liq_short_5m': 'liq_short_5m', 'depth_imb': 'depth_imb', 'top_ratio': 'top_ratio',
    'basis': 'basis', 'ml_score': 'ml_score', 'regime': 'regime',
    'ls_global': 'ls_global', 'ls_top': 'ls_top', 'hl_net_usd': 'hl_net_usd', 'cb_premium': 'cb_premium',
    'market_crowd': 'market_crowd', 'mkt_1h': 'mkt_1h', 'mkt_4h': 'mkt_4h', 'btc_1h': 'btc_1h', 'btc_4h': 'btc_4h', 'mkt_1d': 'mkt_1d', 'btc_1d': 'btc_1d',
    'coin_trend': 'coin_trend', 'vol_ratio': 'vol_ratio', 'volume_24h': 'volume_24h',
    'agg_funding_8h': 'agg_funding_8h', 'ls_bybit': 'ls_bybit', 'ls_okx': 'ls_okx', 'hour_utc': 'hour_utc',
    'weekend': 'weekend', 'liq_on_wick': 'liq_on_wick', 'oi_change_sweep': 'oi_change_sweep', 'adx': 'adx',
    'trend_w': 'trend_w', 'breadth_w': 'breadth_w',
    'dvol_btc': 'dvol_btc', 'dvol_chg_1h': 'dvol_chg_1h', 'pc_oi_btc': 'pc_oi_btc', 'funding_spread': 'funding_spread',
    'okx_book_imb': 'okx_book_imb', 'bybit_book_imb': 'bybit_book_imb', 'kimchi_prem': 'kimchi_prem', 'news': 'news', 'news_age_h': 'news_age_h',
    'iceberg_net_5m': 'iceberg_net_5m', 'iceberg_n_5m': 'iceberg_n_5m', 'daily_bias': 'daily_bias', 'weekly_bias': 'weekly_bias', 'btc_bias': 'btc_bias', 'vpin': 'vpin', 'vol_entropy': 'vol_entropy', 'lead_venue': 'lead_venue', 'lead_corr': 'lead_corr',
    'prem_1h': 'prem_1h', 'prem_z': 'prem_z', 'funding_1h': 'funding_1h', 'oi_vol': 'oi_vol', 'er_1h': 'er_1h',
    'chop_1h': 'chop_1h', 'rs_btc_z': 'rs_btc_z',
    'btc_below_ema50_4h': 'btc_below_ema50_4h', 'liq_cascade_2h': 'liq_cascade_2h', 'mkt_down_alt': 'mkt_down_alt',
    'smt_majors': 'smt_majors', 'nr4': 'nr4', 'nr7': 'nr7', 'inside_day': 'inside_day', 'atr_ratio': 'atr_ratio',
    'vol_regime': 'vol_regime', 'range_tf': 'range_tf', 'range_pos_tf': 'range_pos_tf', 'range_pos_1h': 'range_pos_1h', 'zone_moved': 'zone_moved',
    'zone_move_atr': 'zone_move_atr', 'sl_old': 'sl_old', 'sl_near': 'sl_near', 'event_risk': 'event_risk', 'near52': 'near52',
    'vol_rank': 'vol_rank', 'liq_proxy': 'liq_proxy',
    'trend_4h': 'trend_4h', 'trend_1d': 'trend_1d', 'weis_ratio': 'weis_ratio',
    'xau_chg_1h': 'xau_chg_1h', 'xau_chg_24h': 'xau_chg_24h', 'oil_chg_1h': 'oil_chg_1h', 'oil_chg_24h': 'oil_chg_24h', 'spy_chg_1h': 'spy_chg_1h', 'spy_chg_24h': 'spy_chg_24h', 'qqq_chg_1h': 'qqq_chg_1h', 'qqq_chg_24h': 'qqq_chg_24h', 'us_session': 'us_session', 'vix_prev': 'vix_prev', 'fng': 'fng', 'etf_flow_1d': 'etf_flow_1d', 'etf_flow_3d': 'etf_flow_3d',
}

# anomaly label -> (median |4h move| / the coin's usual |4h move|, n): refreshed hourly (refresh_anomaly_effects)
ANOMALY_EFFECT: Dict[str, tuple] = {}

# (setup, regime) -> (results, upper end of the 90% interval of its 4h Edge): refreshed hourly from the journal
REGIME_STATS: Dict[Tuple[str, str], Tuple[int, float]] = {}      # (setup, regime) -> (4h blocks, p of Edge >= 0)
REGIME_MUTED: set = set()                                          # (setup, regime) proven negative (BH-controlled)

# Rows whose 4h label windows overlap ride one market move: the automatic rules resample 4h blocks of one direction
BLOCK_MS = 4 * 3_600_000


def block_of(ts_ms: int, direction: int) -> tuple:
    return ts_ms // BLOCK_MS, direction


def proven_negative(groups: Dict[tuple, Dict[tuple, List[float]]], min_blocks: int, q: float,
                    seed: int) -> Tuple[Dict[tuple, Tuple[int, float]], set]:
    """
    For each group (4h blocks of Edge values): a block-bootstrap p-value of "the mean Edge is >= 0"; the groups
    proven negative with the Benjamini-Hochberg false discovery rate q over all groups tested (a setup x regime
    grid is dozens of tests at once: without the correction some mutes are chance).
    """
    rng = np.random.default_rng(seed)
    stats: Dict[tuple, Tuple[int, float]] = {}
    for key, blocks_by_id in groups.items():
        blocks = list(blocks_by_id.values())
        n = len(blocks)
        if n < min_blocks:
            stats[key] = (n, 1.0)
            continue
        draws = 2000
        # the mean of the pooled values of n resampled blocks = sum of their sums / sum of their sizes
        sums = np.array([sum(b) for b in blocks], dtype=float)
        sizes = np.array([len(b) for b in blocks], dtype=float)
        idx = rng.integers(0, n, size=(draws, n))
        at_or_above = int((sums[idx].sum(axis=1) / sizes[idx].sum(axis=1) >= 0).sum())
        stats[key] = (n, (at_or_above + 1) / (draws + 1))
    tested = sorted((p, key) for key, (n, p) in stats.items() if n >= min_blocks)
    m = len(tested)
    cutoff = 0
    for i, (p, _) in enumerate(tested, 1):
        if p <= q * i / m:
            cutoff = i
    return stats, {key for _, key in tested[:cutoff]}


# ---------------------------------------------------------------------- classification

def price_anomaly(sig: Dict) -> bool:
    """Same rule as PhaseScorer.flag_tier_0_anomaly for the 5m price move (floor + the coin's own z-score)."""
    t0 = CONFIG.tier0
    px, z = sig.get('price_change_5m', 0.0) or 0.0, sig.get('price_z', 0.0) or 0.0
    if abs(px) <= t0.price_change_5m_threshold:
        return False
    return abs(z) >= t0.price_z_threshold or (z == 0 and t0.price_change_5m_threshold > 0
                                              and abs(px) > 2 * t0.price_change_5m_threshold)


def oi_anomaly(sig: Dict) -> bool:
    t0 = CONFIG.tier0
    oi, z = sig.get('oi_change_5m', 0.0) or 0.0, sig.get('oi_z', 0.0) or 0.0
    if abs(oi) <= t0.oi_change_5m_threshold:
        return False
    return abs(z) >= t0.oi_z_threshold or (z == 0 and abs(oi) > 2 * t0.oi_change_5m_threshold)


def crowded(sig: Dict, direction: int) -> bool:
    """
    Leverage crowded on the trade's side with positions still building: funding (all venues, else Binance) at or
    beyond the crowding level for that side, or (longs) US spot at a discount (Coinbase premium), AND OI rising
    over the last hour.
    """
    cfg = CONFIG.orderflow
    funding = sig.get('agg_funding_8h')
    funding = sig.get('funding_rate') if funding is None else funding
    oi = sig.get('agg_oi_change_1h')
    oi = sig.get('oi_change_1h') if oi is None else oi
    if oi is None or oi < cfg.crowded_oi_1h:
        return False
    # eng-52: Binance's funding is exactly 0.01% while the premium index sits in [-0.04%, +0.06%] (its own formula),
    # so the 1h premium beyond that band is the crowding reading; the funding rule stays for the other venues
    prem = sig.get('prem_1h')
    if direction > 0:
        premium = sig.get('cb_premium')
        return (funding is not None and funding >= cfg.crowded_funding_long) or \
            (prem is not None and prem > cfg.crowded_premium_long) or \
            (premium is not None and premium <= -cfg.crowded_cb_discount)
    return (funding is not None and funding <= cfg.crowded_funding_short) or \
        (prem is not None and prem < -cfg.crowded_premium_short)


def present(*values):
    """audit N12: the first value that was OBSERVED (not None / NaN) - a measured 0 is a value, not a missing one
    (`a or b` replaced a cancelled-out aggregate flow of 0 by Binance's one-venue flow)."""
    for v in values:
        if v is not None and v == v:
            return v
    return None


def perp_flow_5m(sig: Dict) -> float:
    """5m perp taker flow: all futures venues when several report, else Binance."""
    if (sig.get('venues_active') or 0) >= 2 and present(sig.get('agg_cvd_5m')) is not None:
        return sig['agg_cvd_5m']
    v = present(sig.get('futures_cvd_5m'), sig.get('futures_cvd'))
    return 0.0 if v is None else v


def one_venue(sig: Dict) -> bool:
    v = CONFIG.venues
    return ((sig.get('venues_active') or 0) >= 2 and (sig.get('top_venue_share') or 0) >= v.one_venue_share
            and abs(sig.get('top_venue_net') or 0) >= v.one_venue_min_usd)


def classify(sig: Dict) -> Tuple[str, str, int]:
    """
    (kind, group_key, direction) for a scorer signal: 'setup' = a detected setup (strategies.detect / structure), 'structured'
    = the 15m phases, 'anomaly' = a Tier-0 reading.
    """
    if sig.get('is_setup'):
        return 'setup', sig['setup'], sig['direction']
    if sig.get('is_structured'):
        bull = sig['alert_type'] == 'LONG'
        side, direction = ('BULL', 1) if bull else ('BEAR', -1)
        side_phases = LONG_PHASES if bull else SHORT_PHASES
        scores = {p: sig.get(f'phase_{p.lower()}_score', 0) for p in side_phases}
        active = [p for p in sig.get('active_phases', []) if p in side_phases]
        if active:
            return 'structured', f"{side} {max(active, key=lambda p: scores[p])}", direction
        return 'structured', f"{side} {max(scores, key=scores.get).lower()} (partial)", direction

    t0 = CONFIG.tier0
    px = sig.get('price_change_5m', 0.0) or 0.0
    whales = sig.get('whale_net_5m', 0.0) or 0.0
    oi = sig.get('oi_change_5m', 0.0) or 0.0
    liq_long, liq_short = sig.get('liq_long_5m', 0.0) or 0.0, sig.get('liq_short_5m', 0.0) or 0.0
    cascade = bool(sig.get('liq_cascade'))
    if price_anomaly(sig):
        up = px > 0
        # Observed liquidations first, then the price/OI matrix: up on falling OI = shorts covering (fades);
        # down on falling OI = longs liquidated
        if cascade and up and liq_short > liq_long:
            return 'anomaly', 'SHORT SQUEEZE', 0
        if cascade and not up and liq_long > liq_short:
            return 'anomaly', 'LONG FLUSH', 0
        if oi < 0:
            return 'anomaly', 'SHORT SQUEEZE' if up else 'LONG FLUSH', 0
        # Directional only when both confirm: OI clearly rising (new positions, not just unknown/flat OI) and the
        # 5m futures taker flow on the same side as the move. Missing data = unconfirmed.
        cvd = perp_flow_5m(sig)
        oi_confirms = oi > 0        # eng-121: the price / OI matrix (OI rising = new positions); our floors / z removed
        flow_confirms = bool(cvd) and (cvd > 0) == up
        if oi_confirms and flow_confirms:
            return 'anomaly', 'IMPULSE UP' if up else 'IMPULSE DOWN', 1 if up else -1
        return 'anomaly', 'IMPULSE UNCONFIRMED', 0
    if cascade:
        return 'anomaly', 'LIQ CASCADE', 0
    # the algo cluster is what flags (CONFIG.tier0.flag_rules); net whale sweeps alone measured x1.0, so a cluster
    # names the event even when the sweeps also add up to whales
    cluster = sig.get('cluster', 0) or 0
    if cluster:
        return 'anomaly', 'ALGO BUY' if cluster > 0 else 'ALGO SELL', 1 if cluster > 0 else -1
    if abs(whales) >= t0.whale_net_units:
        return 'anomaly', 'WHALES BUY' if whales > 0 else 'WHALES SELL', 1 if whales > 0 else -1
    if oi_anomaly(sig):
        return 'anomaly', 'OI SURGE' if oi > 0 else 'OI FLUSH', 0
    if one_venue(sig):
        return 'anomaly', 'ONE-VENUE', 0
    if sig.get('rule_anomaly') is False:
        # Flagged by the IsolationForest only: an unusual combination, no single threshold crossed
        return 'anomaly', 'UNUSUAL', 0
    if abs(px) < t0.absorption_max_move:
        # Volume spike that doesn't move price: aggressive orders absorbed by resting liquidity
        return 'anomaly', 'ABSORPTION', 0
    return 'anomaly', 'VOLUME SPIKE', 0


def veto_reason(group_key: str, sig: Dict) -> Optional[str]:
    """
    Why a directional setup is not shown as a card (it is still journaled with this reason, so stats.py can
    compare vetoed and passed signals): a continuation (D, F, a breakout, an impulse) driven by the perp side while
    spot disagrees.
    """
    if CONFIG.orderflow.veto_perp_led and sig.get('has_spot'):
        # Perps lead spot in price discovery (a perp-led move is the normal case, and perp taker imbalance predicts
        # 4-12h continuation): the risk is CROWDED leverage (high funding / basis with OI building predicts
        # liquidations, BIS WP 1087). Vetoed only perp-led AND crowded AND OI rising; else journaled perp_led=1.
        direction = {'BEAR D': -1, 'BULL F': 1, 'IMPULSE UP': 1, 'IMPULSE DOWN': -1}.get(group_key)
        if direction is not None:
            if group_key.startswith('IMPULSE'):
                perp = perp_flow_5m(sig)
                spot = sig.get('spot_cvd_5m') or 0.0
                led = direction * perp > 0 and (direction * spot <= 0 or abs(spot) < CONFIG.orderflow.perp_led_spot_share * abs(perp))
            else:
                led = bool(sig.get('perp_led_long') if direction > 0 else sig.get('perp_led_short'))
            if led and crowded(sig, direction):
                return 'perp_led'
    # Proven negative in the current market regime (enough independent 4h blocks, BH-controlled: proven_negative)
    regime = sig.get('regime')
    if CONFIG.ml.regime_veto and regime and (group_key, regime) in REGIME_MUTED:
        return 'regime'
    return None


# Labels that describe the same underlying event: the live candle and the 5m windows can flip an event between
# them from one scan to the next, so cooldowns and on-screen rows are kept per (symbol, family)
_FAMILIES = {
    'IMPULSE UP': 'IMPULSE', 'IMPULSE DOWN': 'IMPULSE', 'IMPULSE UNCONFIRMED': 'IMPULSE',
    'SHORT SQUEEZE': 'IMPULSE', 'LONG FLUSH': 'IMPULSE', 'LIQ CASCADE': 'IMPULSE',
    'ABSORPTION': 'VOLUME', 'VOLUME SPIKE': 'VOLUME',
    'OI SURGE': 'OI', 'OI FLUSH': 'OI',
    'WHALES BUY': 'WHALES', 'WHALES SELL': 'WHALES', 'ALGO BUY': 'WHALES', 'ALGO SELL': 'WHALES',
    'ONE-VENUE': 'VENUE', 'UNUSUAL': 'ML',
}


def event_family(group_key: str) -> Tuple[str, int]:
    """
    (family, rank) of a setup label. A higher rank is a stronger reading of the same event (a confirmed impulse
    over an unconfirmed one, a fully met phase over a partial one) and is logged even inside the cooldown.
    """
    if group_key.startswith(('BULL ', 'BEAR ')):
        return group_key.split()[0], 0 if 'partial' in group_key else 1
    if group_key.startswith('ENTRY '):
        return group_key, 1
    return _FAMILIES.get(group_key, group_key), 1 if group_key in ('IMPULSE UP', 'IMPULSE DOWN', 'WHALES BUY', 'WHALES SELL') else 0


def _features(sig: Dict) -> Dict:
    out = {col: sig.get(key) for col, key in FEATURE_KEYS.items()}
    out['agg_ready'] = int(bool(sig.get('agg_ready')))
    out['cluster'] = int(sig.get('cluster') or 0)
    out['sec_into_candle'] = int(sig.get('sec_into_quarter') or 0)
    out['btc_mom_7d'] = sig.get('btc_mom_7d')
    out['shadow_veto'] = sig.get('shadow_veto')
    out['regime2'] = sig.get('regime2')
    for k in ('sweep_rvol', 'sweep_depth_atr', 'pool_age_h'):
        out[k] = sig.get(k)
    for col in ('oi_chg_15m', 'oi_chg_60m', 'rush_n_10s', 'rush_n_30s', 'rush_net_30s', 'rush_usd_30s', 'rush_z_30s',
                'flow_depth_5m'):
        v = sig.get(col)
        out[col] = None if v is None or v != v else float(v)
    vol = sig.get('volume_24h') or 0
    fut = present(sig.get('agg_cvd_5m'), sig.get('futures_cvd_5m'))
    out['flow_pct_5m'] = float(fut) / vol if vol and fut is not None else None
    out['spot_flow_pct_5m'] = float(sig['spot_cvd_5m']) / vol if vol and sig.get('spot_cvd_5m') is not None else None
    return out


# ---------------------------------------------------------------------- journal

class SignalJournal:
    def __init__(self, path: str = CONFIG.journal.db_path):
        self.path = path
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)
        self._migrate()
        # after _migrate: setup_ts_ms is a migrated column on old databases (the entry lookups of finalize / card_r)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_entry ON signals(symbol, group_key, setup_ts_ms) "
                          "WHERE kind = 'entry'")
        self.conn.commit()
        # (symbol, family) -> (last logged ts, its rank); seeded from the DB so restarts respect the cooldown
        cutoff = int((time.time() - CONFIG.journal.cooldown_sec) * 1000)
        self._last_logged: Dict[Tuple[str, str], Tuple[int, int]] = {}
        for symbol, group_key, ts in self.conn.execute(
            "SELECT symbol, group_key, ts_ms FROM signals WHERE ts_ms >= ? AND kind NOT IN ('entry', 'card') ORDER BY ts_ms", (cutoff,)
        ):
            family, rank = event_family(group_key)
            self._last_logged[(symbol, family)] = (ts, rank)
        self._last_snapshot = 0.0
        self._snapshot_times: List[int] = []
        self._snapshot_cache: Dict[int, np.ndarray] = {}
        self._snapshot_times_at = 0.0
        self._symbol_index: Dict[str, int] = {}
        self.success = None
        if CONFIG.ml.success_enabled:
            try:
                from ml import SuccessModel
                self.success = SuccessModel()
            except Exception as e:
                logger.warning(f"P(edge) model unavailable: {e}")
            pretrained = load_pretrained()
            if pretrained and pretrained.get('success') and not pretrained_current(pretrained):
                logger.warning("Pretrained P(edge) has incompatible logic or event generator: not loaded. "
                               "Legacy pretrain.py cannot supply live-loopside-v1 events.")
            elif self.success is not None and pretrained and pretrained.get('success'):
                self.success.load_pretrained(pretrained['success'])
                logger.info(f"P(edge) model: pretrained on {pretrained['rows']} historical rows of {pretrained['coins']} "
                            f"coins ({pretrained['start']} .. {pretrained['end']}); the journal replay continues it")

    def _migrate(self):
        existing = {row[1] for row in self.conn.execute("PRAGMA table_info(signals)")}
        for column, sql_type in EXTRA_COLUMNS.items():
            if column not in existing:
                self.conn.execute(f"ALTER TABLE signals ADD COLUMN {column} {sql_type}")

    def _insert(self, rows: List[Dict]):
        if not rows:
            return
        # audit N16: the union of the batch's columns, a row's missing field NULL - the first row's columns lost the
        # setups' reason after an anomaly row, and an anomaly after a setup failed the whole batch (KeyError: reason)
        columns = list(dict.fromkeys(c for r in rows for c in r))
        self.conn.executemany(
            f"INSERT INTO signals ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
            [tuple(r.get(c) for c in columns) for r in rows],
        )

    @staticmethod
    def _base_row(ts_ms: int, symbol: str, kind: str, group_key: str, direction: int, price: float, sig: Dict) -> Dict:
        row = {
            'ts_ms': ts_ms, 'symbol': symbol, 'kind': kind, 'group_key': group_key, 'direction': direction,
            'price': price, 'long_score': sig.get('long_score', 0), 'short_score': sig.get('short_score', 0),
            'phases': ','.join(sig.get('active_phases', [])), 'tier0': int(bool(sig.get('is_tier_0_anomaly'))),
            'tier2': int(bool(sig.get('tier2_active'))), 'rvol_1m': sig.get('rvol_1m', 0.0),
            'oi_change_5m': sig.get('oi_change_5m', 0.0), 'price_change_5m': sig.get('price_change_5m', 0.0),
            'delta_ratio': sig.get('delta_ratio', 0.0), 'funding_8h': sig.get('funding_rate', 0.0),
            'funding_hours': sig.get('funding_interval_h'),           # review V09: the contract's funding interval
            'whale_net_5m': sig.get('whale_net_5m', 0.0), 'logic_version': CONFIG.journal.logic_version,
        }
        row.update(_features(sig))
        return row

    def record(self, signals: List[Tuple[str, Dict]], prices: Dict[str, float]) -> int:
        """
        Store signals not logged for the same (symbol, event family) within the cooldown, unless the new label is a
        stronger reading of the event (higher rank). Returns rows added.
        """
        now_ms = int(time.time() * 1000)
        cooldown_ms = CONFIG.journal.cooldown_sec * 1000
        rows = []
        logged = {}
        with self._lock:
            for symbol, sig in signals:
                price = prices.get(symbol)
                if not price:
                    continue
                kind, group_key, direction = classify(sig)
                family, rank = event_family(group_key)
                last_ts, last_rank = logged.get((symbol, family)) or self._last_logged.get((symbol, family), (0, -1))
                if now_ms - last_ts < cooldown_ms and rank <= last_rank:
                    continue
                logged[(symbol, family)] = (now_ms, rank)
                row = self._base_row(now_ms, symbol, kind, group_key, direction, price, sig)
                # card_veto: the setup did not become a card (no qualifying leg, its leg already played)
                row['vetoed'] = sig.get('card_veto') if 'card_veto' in sig else veto_reason(group_key, sig)
                row['strategy'] = _strategy_of(group_key)
                if kind == 'setup':
                    row['reason'] = sig.get('setup_note')
                row['perp_led'] = int(bool(sig.get('perp_led_long') if direction > 0 else sig.get('perp_led_short')))
                row['p_edge'] = self.success.predict(row) if self.success is not None and direction else None
                sig['p_edge'] = row['p_edge']
                rows.append(row)
            if rows:
                self._insert(rows)
                self.conn.commit()
                # the cooldown only after the rows are saved: a failed batch is retried, not suppressed
                self._last_logged.update(logged)
        if rows:
            logger.info(f"Journal: logged {len(rows)} new signals")
        return len(rows)

    def record_entry(self, tracked) -> None:
        """
        An entry triggered by the LTF model (signal_book.TrackedSignal): its own row 'ENTRY <setup>' with the levels,
        so stats.py replays exactly what the dashboard showed, from the entry moment. Vetoed entries (no order-flow
        confirmation) are stored too, with the reason.
        """
        lv = tracked.levels
        row = self._base_row(int(tracked.entered_at * 1000), tracked.symbol, 'entry', f"ENTRY {tracked.group_key}",
                             tracked.direction, lv['entry'], tracked.sig)
        # systems without a profit target (Turtles, Connors, ORB) carry 100 / 200 / 300 R placeholders for the lifecycle:
        # journaled as NULL, not as prices (live ZRO ORB DOWN: TP1 -1.757) - eng-51
        no_tp = bool((tracked.plan or {}).get('no_tp'))
        row.update({'entry': lv['entry'], 'sl': lv['sl'], 'tp1': None if no_tp else lv['tp1'],
                    'tp2': None if no_tp else lv['tp2'], 'tp3': None if no_tp else lv['tp3'],
                    'rr_tp1': lv.get('rr_tp1'), 'low_rr': int(bool(lv.get('low_rr'))),
                    'rr_blend': lv.get('rr_blend'), 'rr_reason': lv.get('rr_reason'),
                    'exp_model': lv.get('exp_model'), 'exp_note': lv.get('exp_note'),
                    'obstacle_r': lv.get('obstacle_r'), 'obstacle_src': lv.get('obstacle_src'),
                    'vetoed': getattr(tracked, 'vetoed', None), 'of_confirm': getattr(tracked, 'of_confirm', None),
                    'confirms': json.dumps(getattr(tracked, 'confirms', None) or {}),
                    'conf_n': sum(1 for k, v in (getattr(tracked, 'confirms', None) or {}).items()
                                  if not k.startswith('_') and confirm.positive(v)),
                    'perp_led': 0, 'p_edge': tracked.sig.get('p_edge'),
                    'tp1_src': lv.get('tp1_src'), 'tp2_src': lv.get('tp2_src'), 'tp3_src': lv.get('tp3_src'),
                    'range_pos': lv.get('range_pos'),
                    'zone_edge': lv.get('zone_edge'), 'trigger_over_atr': lv.get('trigger_over_atr'),
                    'cost_r': lv.get('cost_r'), 'rr_trigger': lv.get('rr_trigger'),
                    # eng-149: the plan's working ATR (two-contour stop) and a sweep zone's far edge (second test)
                    'atr_entry': (tracked.plan or {}).get('tf_atr') or (tracked.plan or {}).get('atr'),
                    'zone_far': _zone_far(tracked),
                    'strat_class': strategy_class(tracked.mode), 'crowd_pos': tracked.sig.get('crowd_pos'),
                    # eng-58: a resting limit (Seiden's line, ICT's CE / OTE): the replay fills it at the entry price
                    'limit_entry': int(getattr(tracked, 'limit_variant', False) or
                                       ((tracked.plan or {}).get('trigger') == 'touch'
                                        and not CONFIG.executor.touch_confirm_close)),
                    'sl_src': lv.get('sl_src'), 'stop_pierce': lv.get('stop_pierce'), 'zone_src': lv.get('zone_src') or (tracked.plan or {}).get('zone_src'),
                    'setup_ts_ms': int(tracked.created * 1000), 'strategy': tracked.mode,
                    'anchor': _anchor_json(tracked.plan),
                    # eng-48: why it entered (the detector's note + the plan's trigger), was empty on entry rows
                    'reason': ' | '.join(str(x) for x in (tracked.sig.get('setup_note'),
                                                          (tracked.plan or {}).get('trigger'),
                                                          (tracked.plan or {}).get('entry_note')) if x) or None})
        with self._lock:
            if row['vetoed'] and self.conn.execute(
                    "SELECT 1 FROM signals WHERE kind = 'entry' AND symbol = ? AND group_key = ? AND setup_ts_ms = ? "
                    "AND (vetoed IS ? OR (COALESCE(vetoed, '') NOT LIKE 'variant_%' AND ? NOT LIKE 'variant_%')) "
                    "LIMIT 1",
                    (row['symbol'], row['group_key'], row['setup_ts_ms'], row['vetoed'], row['vetoed'])).fetchone():
                # eng-149: a shadow variant ('variant_*') is its own row beside the card's veto
                # eng-84: a vetoed trigger leaves the card waiting, and each later trigger of the same card was a new
                # row (live PO3 LONG: 27 'entries' = 3 setups, each a full replayed trade): one row per card
                return
            self._insert([row])
            self.conn.commit()
        logger.info(f"Journal: entry {tracked.symbol} {tracked.group_key} @ {lv['entry']:.6g}"
                    f"{' (vetoed: ' + row['vetoed'] + ')' if row['vetoed'] else ''}")

    def record_card(self, tracked) -> None:
        """
        A finished card (MISSED / EXPIRED / INVALID / TP3 / SL / CLOSED): 'card' row '<STATUS> <setup>' at the finish
        price, with the reason; the outcome loop then fills what price did in the card's direction afterwards.
        """
        price = tracked.finish_price or tracked.last_price
        if not price:
            return
        lv = tracked.levels or {}
        plan = tracked.plan or {}
        row = self._base_row(int((tracked.finished_at or time.time()) * 1000), tracked.symbol, 'card',
                             f"{tracked.status} {tracked.group_key}", tracked.direction, price, tracked.sig)
        # the card belongs to the logic that opened it (a trade kept across a version bump finishes under its version)
        if getattr(tracked, 'logic_version', None):
            row['logic_version'] = tracked.logic_version
        targets = plan.get('targets') or []
        sources = plan.get('target_src') or []
        notes = getattr(tracked, 'veto_notes', None) or []
        row.update({'reason': tracked.finish_reason + (f" | {notes[-1]}" if notes else ''), 'setup_ts_ms': int(tracked.created * 1000),
                    'strategy': tracked.mode, 'anchor': _anchor_json(tracked.plan),
                    'zone_src': plan.get('zone_src'), 'perp_led': 0,
                    'entry': lv.get('entry'), 'sl': lv.get('sl'),
                    'tp1': lv.get('tp1', targets[0] if targets else None),
                    'tp2': lv.get('tp2', targets[1] if len(targets) > 1 else None),
                    'tp3': lv.get('tp3', targets[2] if len(targets) > 2 else None),
                    'tp1_src': lv.get('tp1_src', sources[0] if sources else None),
                    'vetoed': ','.join(sorted(set(tracked.veto_log))) or None,
                    # the card's own result in R: the lifecycle's exit (a trailing channel, pyramided units) - the 8h
                    # replay cannot see a Turtle or Connors trade that lives for days
                    'card_r': tracked.final_r,
                    'entry_min': getattr(tracked, 'entry_min', None) or None,
                    'card_r_low': (min(tracked.r_low, tracked.final_r) if getattr(tracked, 'r_low', None) is not None
                                   and tracked.final_r is not None else tracked.final_r),
                    'units': float(len(getattr(tracked, 'units', None) or [])) or None,
                    # audit N24: the executor's own card id (symbol|setup|entered_at s) - the demo trade's exact card
                    'card_id': f"{tracked.symbol}|{tracked.group_key}|{int(tracked.entered_at)}" if tracked.entered_at else None,
                    # the furthest target the card reached (0 = none) - the TP1 / TP2 / TP3 hit rates of stats.py
                    'best_tp': int(tracked.best_target or 0) if tracked.entered_at else None})
        if not tracked.entered_at and plan.get('zone_lo') is not None and plan.get('zone_hi') is not None:
            try:
                from strategies.geometry import entry_levels
                line = plan['zone_hi'] if tracked.direction > 0 else plan['zone_lo']
                est = entry_levels(plan, line, None, tracked.direction)
                if est:
                    row.update(plan_entry=est['entry'], plan_sl=est['sl'])
                    if row.get('tp1') is None:
                        row['tp1'] = est['tp1']
            except Exception as e:
                logger.debug(f"Card plan levels {tracked.symbol}: {e!r}")
        with self._lock:
            self._insert([row])
            if tracked.entered_at and tracked.final_r is not None:
                # eng-86: the card's own exit on its ENTRY row too - a target-less method (band / session / channel exit)
                # left the entry row 'OPEN' / 'SL' only, and studies of entry rows saw card_r empty everywhere
                # eng-102: only the entry actually taken - the card's vetoed / shadow triggers (same setup_ts_ms) got
                # the trade's result and the veto studies read a later trade as the vetoed one's
                self.conn.execute("UPDATE signals SET card_r = ?, best_tp = ? WHERE kind = 'entry' AND symbol = ? AND "
                                  "group_key = ? AND setup_ts_ms = ? AND vetoed IS NULL",
                                  (tracked.final_r, row['best_tp'], tracked.symbol, f"ENTRY {tracked.group_key}",
                                   int(tracked.created * 1000)))
            self.conn.commit()

    def record_rush(self, symbol: str, direction: int, price: float, sig: Dict) -> None:
        """eng-89: a RUSH BUY / RUSH SELL row (kind 'rush'): data collection, evaluated by the ret_* horizons."""
        row = self._base_row(int(time.time() * 1000), symbol, 'rush', 'RUSH BUY' if direction > 0 else 'RUSH SELL',
                             direction, price, sig)
        with self._lock:
            self._insert([row])
            self.conn.commit()

    def snapshot_universe(self, prices: Dict[str, Optional[float]], now: Optional[float] = None) -> int:
        """Store the price of every universe coin (at most once per universe_snapshot_sec)."""
        now = now or time.time()
        if now - self._last_snapshot < CONFIG.journal.universe_snapshot_sec:
            return 0
        ts_ms = int(now * 1000)
        rows = [(ts_ms, s, float(p)) for s, p in prices.items() if p]
        if not rows:
            return 0    # no prices yet (right after a start): try again next scan, not in 15 min
        with self._lock:
            self.conn.executemany("INSERT INTO universe (ts_ms, symbol, price) VALUES (?, ?, ?)", rows)
            self.conn.commit()
        self._last_snapshot = now
        return len(rows)

    def record_history_skips(self, rows: List[Tuple]) -> None:
        """[(symbol, strategy, held, needed)] of the strategies a history gate stopped; once a day per coin and strategy."""
        now = int(time.time() * 1000)
        day = now // 86_400_000
        seen = self.__dict__.setdefault('_skip_seen', set())
        if len(seen) > 20_000:
            seen.clear()
        fresh = []
        for symbol, strategy, held, needed in rows:
            if (symbol, strategy, day) not in seen:
                seen.add((symbol, strategy, day))
                fresh.append((now, symbol, strategy, int(held), int(needed)))
        if not fresh:
            return
        with self._lock:
            self.conn.executemany("INSERT INTO history_skips (ts_ms, symbol, strategy, held, needed) VALUES (?, ?, ?, ?, ?)", fresh)
            self.conn.commit()
        logger.debug(f"skip: history shorter than needed for {len(fresh)} coin / strategy pairs")

    def record_liquidations(self, events: List[Tuple]) -> None:
        """Live liquidations [(symbol, ts_ms, price, usd, side, venue)]."""
        if not events:
            return
        rows = [(ts, sym, float(price), float(usd), int(side), venue) for sym, ts, price, usd, side, venue in events]
        with self._lock:
            self.conn.executemany("INSERT INTO liquidations (ts_ms, symbol, price, usd, side, venue) VALUES (?, ?, ?, ?, ?, ?)", rows)
            self.conn.commit()

    def record_liq_levels(self, ts_ms: int, symbol: str, ref_price: Optional[float], levels: List[Tuple]) -> None:
        """A snapshot of a coin's liquidation levels [(kind, price, side, usd)] and the price at the time."""
        if not levels:
            return
        rows = [(ts_ms, symbol, kind, float(price), side, usd, ref_price) for kind, price, side, usd in levels]
        with self._lock:
            self.conn.executemany("INSERT INTO liq_levels (ts_ms, symbol, kind, price, side, usd, ref_price) "
                                  "VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
            self.conn.commit()

    async def arecord_liquidations(self, events):
        return await asyncio.to_thread(self.record_liquidations, events)

    async def arecord_liq_levels(self, ts_ms, symbol, ref_price, levels):
        return await asyncio.to_thread(self.record_liq_levels, ts_ms, symbol, ref_price, levels)

    # ------------------------------------------------------------------ market baseline / ML

    def universe_return(self, ts_ms: int, minutes: int, stat: str = 'mean') -> Optional[float]:
        """
        Return of the whole universe between the snapshots nearest ts and ts + minutes (<= 20 min away): the MEAN
        (Edge: an equal-weight universe has zero mean excess, while coins beat the median by ~0.11% per 4h on average -
        right-skewed returns - so Edge against the median favoured every long and penalised every short) or the
        'median' (the P(edge) label: a balanced 'beat the median coin').
        """
        with self._lock:
            # reload the snapshot times when a later one is needed, at most once a minute (a label still in the
            # future reran a full DISTINCT scan of the table on every call)
            if not self._snapshot_times or (self._snapshot_times[-1] < ts_ms + minutes * 60_000
                                            and time.time() - self._snapshot_times_at > 60):
                self._snapshot_times_at = time.time()
                self._snapshot_times = [t for (t,) in self.conn.execute("SELECT DISTINCT ts_ms FROM universe ORDER BY ts_ms")]

            def nearest(t: int) -> Optional[int]:
                i = bisect.bisect_left(self._snapshot_times, t)
                near = [s for s in self._snapshot_times[max(0, i - 1):i + 1] if abs(s - t) <= 20 * 60_000]
                return min(near, key=lambda s: abs(s - t)) if near else None

            t0, t1 = nearest(ts_ms), nearest(ts_ms + minutes * 60_000)
            if t0 is None or t1 is None or t0 == t1:
                return None
            snaps = []
            for t in (t0, t1):
                if t not in self._snapshot_cache:
                    # a dense price vector over a shared symbol index (NaN = not in that snapshot)
                    pairs = self.conn.execute("SELECT symbol, price FROM universe WHERE ts_ms = ?", (t,)).fetchall()
                    for sym, _ in pairs:
                        self._symbol_index.setdefault(sym, len(self._symbol_index))
                    vec = np.full(len(self._symbol_index), np.nan)
                    vec[[self._symbol_index[sym] for sym, _ in pairs]] = [p if p else np.nan for _, p in pairs]
                    self._snapshot_cache[t] = vec
                    if len(self._snapshot_cache) > 400:
                        self._snapshot_cache.pop(next(iter(self._snapshot_cache)))
                snaps.append(self._snapshot_cache[t])
        a, b = snaps
        k = min(len(a), len(b))
        changes = b[:k] / a[:k] - 1
        changes = changes[np.isfinite(changes)]
        if len(changes) < 20:
            return None
        return float(np.median(changes) if stat == 'median' else changes.mean())

    def _labelled_rows(self, since_ms: int = 0) -> List[sqlite3.Row]:
        with self._lock:
            self.conn.row_factory = sqlite3.Row
            try:
                return self.conn.execute(
                    "SELECT * FROM signals WHERE kind NOT IN ('entry', 'card') AND direction != 0 AND ret_4h IS NOT NULL "
                    "AND logic_version = ? AND ts_ms >= ? ORDER BY ts_ms", (CONFIG.journal.logic_version, since_ms)).fetchall()
            finally:
                self.conn.row_factory = None

    def warm_start(self) -> int:
        """Replay every labelled directional row into the P(edge) model (state = the journal itself)."""
        if self.success is None:
            return 0
        from ml import label_of
        learned = 0
        for row in self._labelled_rows():
            label = label_of(row, self.universe_return(row['ts_ms'], 240, 'median'))
            if label is not None:
                self.success.learn(row, label)
                learned += 1
        if learned:
            logger.info(f"P(edge) model warmed up on {learned} journal rows ({self.success.drifts} drift resets)")
        return learned

    def refresh_anomaly_effects(self, days: float = 14.0) -> int:
        """
        Each anomaly label's effect, measured against the coin itself: the median of |4h move after the label| /
        the coin's usual |4h move| (its universe snapshots over the same days). x1.0 = the label adds nothing to the
        coin's normal volatility (live 2026-09-27..30: whales, absorption, one-venue, cascades ~x1.0; impulses x1.4).
        """
        since = int((time.time() - days * 86_400) * 1000)
        norm = lambda s: s.replace('/USDT:USDT', 'USDT').replace('/', '')
        with self._lock:
            rows = self.conn.execute("SELECT group_key, symbol, ret_4h FROM signals WHERE kind = 'anomaly' AND "
                                     "ret_4h IS NOT NULL AND ts_ms >= ?", (since,)).fetchall()
            # only the labelled coins' snapshots (the whole universe was ~800k rows, ~10s of Python per refresh)
            wanted = {norm(s) for _, s, _ in rows}
            names = [u for (u,) in self.conn.execute("SELECT DISTINCT symbol FROM universe WHERE ts_ms >= ?", (since,))
                     if norm(u) in wanted]
            uni = self.conn.execute(
                f"SELECT ts_ms, symbol, price FROM universe WHERE ts_ms >= ? AND symbol IN ({','.join('?' * len(names))})",
                (since, *names)).fetchall() if names else []
        usual: Dict[str, float] = {}
        if uni:
            syms = np.array([norm(s) for _, s, _ in uni])     # one series per coin however a snapshot spelled it
            ts_all = np.array([t for t, _, _ in uni], dtype=np.int64)
            px_all = np.array([p if p else np.nan for _, _, p in uni], dtype=float)
            order = np.lexsort((ts_all, syms))            # by symbol, then time
            syms, ts_all, px_all = syms[order], ts_all[order], px_all[order]
            names, starts = np.unique(syms, return_index=True)
            for name, lo, hi in zip(names, starts, list(starts[1:]) + [len(syms)]):
                ts, px = ts_all[lo:hi], px_all[lo:hi]
                target = ts + 4 * 3_600_000
                j = np.searchsorted(ts, target)
                ok = j < len(ts)
                jj = np.where(ok, j, 0)
                ok &= np.abs(ts[jj] - target) <= 600_000
                moves = np.abs(px[jj][ok] / px[ok] - 1)
                moves = moves[np.isfinite(moves)]
                if len(moves) > 20:
                    usual[str(name)] = float(moves.mean())
        ratios: Dict[str, list] = {}
        for label, s, r4 in rows:
            base = usual.get(norm(s))
            if base:
                ratios.setdefault(label, []).append(abs(r4) / base)
        ANOMALY_EFFECT.clear()
        ANOMALY_EFFECT.update({k: (float(np.median(v)), len(v)) for k, v in ratios.items() if len(v) >= 25})
        return len(ANOMALY_EFFECT)

    def refresh_regime_stats(self) -> int:
        """
        4h Edge per (setup, regime) for journal.veto_reason: a (setup, regime) is muted once its Edge is proven
        negative over >= regime_veto_min_n independent 4h blocks, with the false discovery rate controlled over the
        whole grid (proven_negative).
        """
        groups: Dict[Tuple[str, str], Dict[tuple, List[float]]] = {}
        for row in self._labelled_rows():
            if not row['regime']:
                continue
            base = self.universe_return(row['ts_ms'], 240)
            if base is not None:
                groups.setdefault((row['group_key'], row['regime']), {}).setdefault(
                    block_of(row['ts_ms'], row['direction']), []).append(row['direction'] * (row['ret_4h'] - base))
        stats, muted = proven_negative(groups, CONFIG.ml.regime_veto_min_n, CONFIG.ml.rule_fdr, seed=3)
        REGIME_STATS.clear()
        REGIME_STATS.update(stats)
        if muted != REGIME_MUTED:
            logger.info(f"Regime stats: muted in their regime: {sorted(muted)}")
        REGIME_MUTED.clear()
        REGIME_MUTED.update(muted)
        return len(stats)

    def refresh_hit_rates(self) -> int:
        """
        p(TP1 before the stop) per SETUP (audit C09) from the replayed entries of the last 30 days (passed and vetoed: the
        replay is the same), decided ones (TP1 / TP2 / TP3 vs SL) -> strategies.geometry.HIT_RATE (p, n, p_upper). A
        DESCRIPTIVE rate of reaching each target before the stop (audit 2026-10-18 P1 #5): the entry check turns it into
        the expectancy of the three-thirds exit only, vetoing a plan that exits that way when even the upper end of the
        95% Wilson interval does not pay; it is not the expectancy of the whole exit policy (trail, partials, time
        exits), and entries of one market move are not independent draws, so the interval is optimistic.
        """
        from strategies import geometry
        since = int((time.time() - 30 * 86400) * 1000)
        with self._lock:
            rows = self.conn.execute(
                "SELECT group_key, outcome, logic_version FROM signals WHERE kind = 'entry' AND ts_ms >= ? AND "
                "outcome IN ('TP1', 'TP2', 'TP3', 'SL') AND strategy IS NOT NULL AND tp1 IS NOT NULL AND "
                "COALESCE(vetoed, '') NOT IN ('low_rr', 'flow_entry', 'weak_mss', 'reclaim_entry', 'bb3_shadow', 'rsi2x_shadow', "
                "'tl_em_shadow', 'oi_shadow', 'cascade_shadow', 'rsi2_crossback_shadow', 'connors_short_shadow')",
                (since,)).fetchall()
        # audit 2026-10-18: not the entries vetoed 'low_rr' either - their TP1 sat too close to pay (79% hit of 4177 in
        # 30 days vs 29% of the traded ones), which put every setup's p far above what an entry the gate passes reaches
        # eng-102: only entries WITH a TP1 (a target-less system - Bollinger / ORB / breakout rows with tp1 NULL - only
        # ever ends 'SL' here: Bollinger measured p 0% and every entry was vetoed 'expectancy -1.00R') and of the
        # current logic (keep_waiting_from on: the older versions had other targets / stops); the shadow ALTERNATIVE
        # entries (flow_entry / weak_mss: never traded, TP1 at 0.03-0.4 R) made sweep's p 97%
        from signal_book import version_no
        floor = version_no(CONFIG.journal.keep_waiting_from)
        counts: Dict[str, List[int]] = {}
        for strategy, outcome, lv in rows:
            if version_no(lv) < floor:
                continue
            # audit C13: one key form for writer and reader (the plan asks by 'SWEEP LOW', the row is 'ENTRY SWEEP LOW')
            # [SL, reached TP1, reached TP2, reached TP3]: each third's own p(its target before the stop)
            c = counts.setdefault(geometry.setup_key(strategy), [0, 0, 0, 0])
            if outcome == 'SL':
                c[0] += 1
            else:
                for k in range(1, int(outcome[2]) + 1):
                    c[k] += 1
        # eng-124: no fixed n >= 30 (a 60% rate after 20-50 trades is anywhere in 35-85% / 46-74%): every strategy with
        # decided entries gets its rate AND the upper end of its 95% Wilson interval; the veto uses the upper end
        rates = {s: (h1 / (h1 + sl), h1 + sl, wilson_upper(h1, h1 + sl), wilson_upper(h2, h1 + sl),
                     wilson_upper(h3, h1 + sl)) for s, (sl, h1, h2, h3) in counts.items() if h1 + sl > 0}
        geometry.HIT_RATE.clear()
        geometry.HIT_RATE.update(rates)
        return len(rates)

    def refresh_confirm_stats(self) -> int:
        """
        Promote a confirmation to required for a strategy (strategies.confirm.PROMOTED) once the strategy's entries
        WITHOUT it have a negative Edge proven over >= promote_min_clusters independent 4h blocks, with the false
        discovery rate controlled over every (strategy, confirmation) tested (proven_negative). Only entries of the
        current logic version count.
        """
        if not CONFIG.orderflow.promote_confirmations:
            return 0
        with self._lock:
            rows = self.conn.execute(
                "SELECT ts_ms, direction, strategy, confirms, ret_4h FROM signals WHERE kind = 'entry' AND "
                "ret_4h IS NOT NULL AND confirms IS NOT NULL AND logic_version = ?",
                (CONFIG.journal.logic_version,)).fetchall()
        groups: Dict[Tuple[str, str], Dict[tuple, List[float]]] = {}
        for ts_ms, direction, strategy, confirms, ret in rows:
            base = self.universe_return(ts_ms, 240)
            if base is None or not strategy or not direction:
                continue
            for name, value in json.loads(confirms or '{}').items():
                if value is False:
                    groups.setdefault((strategy, name), {}).setdefault(block_of(ts_ms, direction), []).append(
                        direction * (ret - base))
        _, promoted = proven_negative(groups, CONFIG.orderflow.promote_min_clusters, CONFIG.ml.rule_fdr, seed=5)
        if promoted != confirm.PROMOTED:
            logger.info(f"Confirmations required by the journal: {sorted(promoted)}")
        confirm.PROMOTED.clear()
        confirm.PROMOTED.update(promoted)
        return len(promoted)

    def coin_results(self, since_ms: int) -> List[Tuple[str, str, int, int, float]]:
        """(strategy, symbol, ts_ms, direction, net R) of every non-vetoed entry since `since_ms` of the logic family
        judged now (CONFIG.journal.verdict_since on): the trade's own result (card_r, on the entry row since eng-86) only.
        audit 2026-10-18 P1 #5: the replay's R to TP1 (r_tp1) is another trade - all out at TP1 - and is no longer
        substituted for a missing card_r (an open trade or a row before eng-86 is left out, not given a model result);
        no coin is excluded on the results of a logic that no longer runs."""
        from stats import version_no
        floor = version_no(CONFIG.journal.verdict_since)
        with self._lock:
            rows = self.conn.execute(
                "SELECT strategy, symbol, ts_ms, direction, card_r, logic_version FROM signals "
                "WHERE kind = 'entry' AND card_r IS NOT NULL "
                "AND (vetoed IS NULL OR vetoed = '') AND strategy IS NOT NULL AND ts_ms >= ?", (since_ms,)).fetchall()
        return [r[:5] for r in rows if version_no(r[5]) >= floor]

    def summary(self) -> Tuple[int, int]:
        """(signals logged, signals with a 4h outcome)."""
        with self._lock:
            total, done = self.conn.execute("SELECT COUNT(*), COUNT(ret_4h) FROM signals").fetchone()
        return total, done

    # ------------------------------------------------------------------ async wrappers (never block the loop)

    async def arecord(self, signals, prices) -> int:
        return await asyncio.to_thread(self.record, signals, prices)

    async def arecord_entry(self, tracked):
        await asyncio.to_thread(self.record_entry, tracked)

    async def arecord_card(self, tracked):
        await asyncio.to_thread(self.record_card, tracked)

    async def asnapshot_universe(self, prices):
        return await asyncio.to_thread(self.snapshot_universe, prices)

    async def asummary(self) -> Tuple[int, int]:
        return await asyncio.to_thread(self.summary)

    # ------------------------------------------------------------------ outcomes

    def _pending(self, limit: int) -> List[Dict]:
        """Oldest rows with at least one horizon due and not filled yet."""
        now_ms = int(time.time() * 1000)
        # Conservative SQL bound (a whole extra minute); the exact check is horizon_due_ms in _evaluate_pass
        due = {label: now_ms - (minutes + 1) * 60_000 - CLOSE_MARGIN_MS for label, minutes in HORIZONS.items()}
        rets = ', '.join(f"ret_{label}" for label in HORIZONS)
        pending = ' OR '.join(f"(ret_{label} IS NULL AND ts_ms <= ?)" for label in HORIZONS)
        with self._lock:
            cursor = self.conn.execute(
                # eng-102: simulate reads limit_entry / volume_24h - without them every resting-limit entry was
                # replayed as a market fill (next minute's open + slippage) at the default liquidity's slippage
                f"SELECT id, ts_ms, symbol, price, direction, entry, sl, tp1, tp2, tp3, {rets}, kind, funding_8h, "
                f"funding_hours, limit_entry, volume_24h, anchor, atr_entry, zone_far FROM signals "
                f"WHERE eval_failed = 0 AND ({pending}) ORDER BY ts_ms LIMIT ?",
                (*[due[label] for label in HORIZONS], limit),
            )
            columns = [c[0] for c in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def maintenance(self) -> None:
        """Daily: fold the WAL back into the database (it grew to 7 MB between automatic checkpoints) and let SQLite
        refresh its planner statistics. No VACUUM: it rewrites the 100 MB file under the lock."""
        with self._lock:
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self.conn.execute("PRAGMA optimize")

    async def evaluate_loop(self, fetcher):
        """Fill in outcomes as horizons come due (also catches up on signals from previous runs)."""
        last_regime_stats, last_maintenance = 0.0, time.time()
        while True:
            try:
                await self._evaluate_pass(fetcher)
                await self._evaluate_life_pass(fetcher)
                if time.time() - last_maintenance >= 86_400:
                    last_maintenance = time.time()
                    await asyncio.to_thread(self.maintenance)
                if time.time() - last_regime_stats >= 3600:
                    last_regime_stats = time.time()
                    # audit N17: the measured p(TP1) follows the new outcomes (was computed once at the start)
                    await asyncio.to_thread(self.refresh_hit_rates)
                    await asyncio.to_thread(self.refresh_regime_stats)
                    await asyncio.to_thread(self.refresh_confirm_stats)
                    await asyncio.to_thread(self.refresh_anomaly_effects)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"Journal evaluation error: {e}")
            await asyncio.sleep(CONFIG.journal.eval_interval_sec)

    async def _evaluate_pass(self, fetcher):
        """
        Oldest-first across all horizons (so no horizon starves), one request per row: the 1m klines of the longest
        due horizon also cover the shorter ones.
        """
        now_ms = int(time.time() * 1000)
        for row in await asyncio.to_thread(self._pending, CONFIG.journal.max_evals_per_pass):
            due = [(label, minutes) for label, minutes in HORIZONS.items()
                   if row[f'ret_{label}'] is None and horizon_due_ms(row['ts_ms'], minutes) <= now_ms]
            if not due:
                continue
            longest = max(minutes for _, minutes in due)
            klines = await fetcher.fetch_minute_klines(row['symbol'], row['ts_ms'], longest)
            await asyncio.to_thread(self._store_outcomes, row, due, klines)
            await asyncio.sleep(0.05)

    def _store_outcomes(self, row: Dict, due: List[Tuple[str, int]], klines: Optional[List]):
        for label, minutes in due:
            self._store_outcome(row, label, minutes, klines)

    def _store_outcome(self, row: Dict, label: str, minutes: int, klines: Optional[List]):
        signal_id, ts_ms, price = row['id'], row['ts_ms'], row['price']
        if klines is None:
            return  # request failed (network, rate limit): retry on a later pass
        if len(klines) < minutes:
            # The exchange answered with too little data (e.g. delisted): give up once the horizon is well past
            if time.time() * 1000 - ts_ms > (minutes + 60) * 60_000:
                with self._lock:
                    self.conn.execute("UPDATE signals SET eval_failed = 1 WHERE id = ?", (signal_id,))
                    self.conn.commit()
            return
        window = klines[:minutes]
        if int(window[-1][0]) + 60_000 > time.time() * 1000 - 1_000:
            return  # the window's last candle has not closed yet: retry on a later pass
        t0 = int(window[0][0])
        if t0 != -(-ts_ms // 60_000) * 60_000 or any(int(k[0]) != t0 + i * 60_000 for i, k in enumerate(window)):
            # audit C12: a hole in the minutes made '15m' span 75 minutes - the horizon is a duration, not a row count.
            # An exchange gap does not heal: the row is given up, not labelled with a longer window
            with self._lock:
                self.conn.execute("UPDATE signals SET eval_failed = 1 WHERE id = ?", (signal_id,))
                self.conn.commit()
            logger.info(f"Journal: signal {signal_id} {label} not labelled: the 1m minutes have a gap")
            return
        updates = {f'ret_{label}': float(window[-1][4]) / price - 1}
        if label == '4h':
            updates['mfe_4h'] = max(float(k[2]) for k in window) / price - 1
            updates['mae_4h'] = min(float(k[3]) for k in window) / price - 1
            e, sl, d = row.get('entry'), row.get('sl'), row.get('direction')
            if e and sl and d in (-1, 1) and d * (e - sl) > 0:
                hi, lo = max(float(k[2]) for k in window), min(float(k[3]) for k in window)
                updates['mfe_r'] = d * ((hi if d > 0 else lo) - e) / (d * (e - sl))
                updates['mae_r'] = d * ((lo if d > 0 else hi) - e) / (d * (e - sl))
        if label == '8h' and row.get('entry') is not None and row.get('direction') and row.get('kind') == 'entry':
            # Entry rows: replay SL / TP on the 1m candles of the trade's whole life, filled like a human would
            updates.update(self._replay(row, window))
            updates.update(excursions(row, window))      # eng-148: every entry, stopped or not, on its 8h window
            updates['outcome_h'] = minutes // 60
        sets = ', '.join(f"{col} = ?" for col in updates)
        with self._lock:
            self.conn.execute(f"UPDATE signals SET {sets} WHERE id = ?", (*updates.values(), signal_id))
            self.conn.commit()
        if label == '4h' and self.success is not None and row.get('direction') and row.get('kind') not in ('entry', 'card', 'rush'):
            self._learn(signal_id)

    @staticmethod
    def _replay(row: Dict, window: List) -> Dict:
        """SL / TP of an entry row replayed on its 1m candles, filled like a human would."""
        updates = simulate(row, row['direction'], window, use_fill=True, funding_8h=row.get('funding_8h'),
                           funding_hours=row.get('funding_hours'))
        if row.get('tp1') is None and updates.get('outcome') in ('SL', 'OPEN'):
                # eng-84: a method without targets (Bollinger's band, Crabel's session close, the Turtles' channel) can
                # only read 'SL' / 'OPEN' here - its winners never showed (BB / ORB: 0 TP of 60). Its result is the
                # card's own exit (card rows, card_r); the entry row says so instead of counting as a stop-out
                updates['outcome'] = 'NO_TP' if updates['outcome'] == 'OPEN' else 'SL'
        return updates

    def _pending_life(self, limit: int) -> List[Dict]:
        """Entry rows whose provisional 8h outcome can still change (OPEN / TP1 / TP2; SL and TP3 are final) and
        whose full replay window (journal.outcome_life_h) has closed."""
        hours = CONFIG.journal.outcome_life_h
        due = int(time.time() * 1000) - (hours * 60 + 1) * 60_000 - CLOSE_MARGIN_MS
        since = int((time.time() - 35 * 86400) * 1000)      # HIT_RATE reads 30 days: older rows are not replayed again
        with self._lock:
            cursor = self.conn.execute(
                "SELECT id, ts_ms, symbol, price, direction, entry, sl, tp1, tp2, tp3, kind, funding_8h, funding_hours, "
                "limit_entry, volume_24h, anchor, atr_entry, zone_far FROM signals WHERE kind = 'entry' AND eval_failed = 0 AND entry IS NOT NULL "
                "AND direction IS NOT NULL AND outcome IN ('OPEN', 'TP1', 'TP2') AND COALESCE(outcome_h, 8) < ? "
                "AND ts_ms <= ? AND ts_ms >= ? ORDER BY ts_ms LIMIT ?", (hours, due, since, limit))
            columns = [c[0] for c in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    async def _evaluate_life_pass(self, fetcher):
        """Relabel entries over the trade's real life (audit #21): 1500-minute pages of 1m klines."""
        minutes = CONFIG.journal.outcome_life_h * 60
        done, failed = 0, 0
        for row in await asyncio.to_thread(self._pending_life, max(1, CONFIG.journal.max_evals_per_pass // 4)):
            klines: List = []
            while len(klines) < minutes:
                start = row['ts_ms'] if not klines else int(klines[-1][0]) + 1     # the next whole minute
                page = await fetcher.fetch_minute_klines(row['symbol'], start, min(1500, minutes - len(klines)))
                if page is None:
                    klines = None
                    break
                if not page:
                    break
                klines.extend(page)
                await asyncio.sleep(0.05)
            if klines is None:
                failed += 1
                continue                                   # request failed: retry on a later pass
            await asyncio.to_thread(self._store_life, row, klines, minutes)
            done += 1
        if done or failed:
            logger.info(f"Journal: {done} entries relabelled over {CONFIG.journal.outcome_life_h}h, {failed} failed")

    def _store_life(self, row: Dict, klines: List, minutes: int):
        window = klines[:minutes]
        t0 = -(-row['ts_ms'] // 60_000) * 60_000
        if not window or int(window[0][0]) != t0 or any(int(k[0]) != t0 + i * 60_000 for i, k in enumerate(window)):
            # a gap (or a delisting) in the minutes: the provisional 8h label stays, marked as final for this row
            updates = {'outcome_h': CONFIG.journal.outcome_life_h}
        else:
            updates = self._replay(row, window)
            updates.update(excursions(row, window))
            updates['outcome_h'] = len(window) // 60
            if len(window) < minutes:
                updates['outcome_h'] = CONFIG.journal.outcome_life_h     # the exchange has no more: as long as it gets
        sets = ', '.join(f"{col} = ?" for col in updates)
        with self._lock:
            self.conn.execute(f"UPDATE signals SET {sets} WHERE id = ?", (*updates.values(), row['id']))
            self.conn.commit()

    def _learn(self, signal_id: int):
        """Feed a freshly labelled directional row to the online P(edge) model."""
        from ml import label_of
        with self._lock:
            self.conn.row_factory = sqlite3.Row
            try:
                row = self.conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
            finally:
                self.conn.row_factory = None
        if row is None or row['kind'] in ('entry', 'card') or row['logic_version'] != CONFIG.journal.logic_version:
            return
        label = label_of(row, self.universe_return(row['ts_ms'], 240, 'median'))
        if label is not None:
            self.success.learn(row, label)

    def close(self):
        with self._lock:
            self.conn.close()
