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
import random
import sqlite3
import statistics
import threading
import time
from typing import Dict, List, Optional, Tuple

from config import CONFIG
from levels import simulate
from strategies import confirm
from scorer import LONG_PHASES, SHORT_PHASES


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
    is not used; its regime history (market features only) stays valid.
    """
    return bool(state) and state.get('logic_version') == CONFIG.journal.logic_version


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
"""

# Columns added after the first release; created on old databases by _migrate()
EXTRA_COLUMNS = {
    'whale_net_5m': 'REAL',
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
    'strategy': 'TEXT', 'anchor': 'TEXT', 'mkt_1h': 'REAL', 'mkt_4h': 'REAL', 'btc_1h': 'REAL', 'coin_trend': 'INTEGER',
    'vol_ratio': 'REAL', 'r_be': 'REAL',
    # eng-2: the coin's 24h futures quote volume (liquidity: patterns on thin coins are one order's work)
    'volume_24h': 'REAL',
    # eng-4: the 8h horizon (entries replayed over the trade's life), the other venues' funding and long/short
    # ratios, time of day, the sweep candle's liquidations / OI change
    'ret_8h': 'REAL', 'agg_funding_8h': 'REAL', 'ls_bybit': 'REAL', 'ls_okx': 'REAL', 'hour_utc': 'INTEGER',
    'weekend': 'INTEGER', 'liq_on_wick': 'REAL', 'oi_change_sweep': 'REAL', 'adx': 'REAL',
    # eng-3: entry confirmations (strategies/confirm.py, JSON {name: true / false / null | order-flow kind}) and how
    # many were positive
    'confirms': 'TEXT', 'conf_n': 'INTEGER',
    # the coin's weekly trend (distance from its weekly EMA in weekly standard deviations) and the universe's share
    # above its weekly EMA: context, never a filter (the weekly EMA tested as no level of its own, 2026-09-27)
    'trend_w': 'REAL', 'breadth_w': 'REAL',
    # ICT premium / discount: the entry's place in the 48h dealing range for its direction (0 = cheapest end)
    'range_pos': 'REAL',
    # extdata.py: Deribit BTC DVOL and its 1h change, BTC options put / call OI; the next-funding spread across
    # Binance / Bybit / Hyperliquid (8h-equivalent); OKX / Bybit book imbalance within 0.5%
    'dvol_btc': 'REAL', 'dvol_chg_1h': 'REAL', 'pc_oi_btc': 'REAL', 'funding_spread': 'REAL',
    'okx_book_imb': 'REAL', 'bybit_book_imb': 'REAL',
    # iceberg.py: hidden limit orders refilled at one price over the last 5 minutes (bid - ask USD, count)
    'iceberg_net_5m': 'REAL', 'iceberg_n_5m': 'REAL', 'daily_bias': 'REAL', 'weekly_bias': 'REAL', 'card_r': 'REAL',
    'units': 'REAL', 'trend_4h': 'REAL', 'trend_1d': 'REAL', 'rr_blend': 'REAL', 'rr_reason': 'TEXT',
}

FEATURE_KEYS = {
    # journal column: signal key
    'price_z': 'price_z', 'oi_z': 'oi_z', 'spot_delta_1h': 'spot_delta_1h', 'perp_delta_1h': 'perp_delta_1h',
    'spot_cvd_5m': 'spot_cvd_5m', 'futures_cvd_5m': 'futures_cvd_5m', 'agg_cvd_5m': 'agg_cvd_5m',
    'agg_oi_change_5m': 'agg_oi_change_5m', 'top_venue': 'top_venue', 'top_venue_share': 'top_venue_share',
    'liq_long_5m': 'liq_long_5m', 'liq_short_5m': 'liq_short_5m', 'depth_imb': 'depth_imb', 'top_ratio': 'top_ratio',
    'basis': 'basis', 'ml_score': 'ml_score', 'regime': 'regime',
    'ls_global': 'ls_global', 'ls_top': 'ls_top', 'hl_net_usd': 'hl_net_usd', 'cb_premium': 'cb_premium',
    'market_crowd': 'market_crowd', 'mkt_1h': 'mkt_1h', 'mkt_4h': 'mkt_4h', 'btc_1h': 'btc_1h',
    'coin_trend': 'coin_trend', 'vol_ratio': 'vol_ratio', 'volume_24h': 'volume_24h',
    'agg_funding_8h': 'agg_funding_8h', 'ls_bybit': 'ls_bybit', 'ls_okx': 'ls_okx', 'hour_utc': 'hour_utc',
    'weekend': 'weekend', 'liq_on_wick': 'liq_on_wick', 'oi_change_sweep': 'oi_change_sweep', 'adx': 'adx',
    'trend_w': 'trend_w', 'breadth_w': 'breadth_w',
    'dvol_btc': 'dvol_btc', 'dvol_chg_1h': 'dvol_chg_1h', 'pc_oi_btc': 'pc_oi_btc', 'funding_spread': 'funding_spread',
    'okx_book_imb': 'okx_book_imb', 'bybit_book_imb': 'bybit_book_imb',
    'iceberg_net_5m': 'iceberg_net_5m', 'iceberg_n_5m': 'iceberg_n_5m', 'daily_bias': 'daily_bias', 'weekly_bias': 'weekly_bias',
    'trend_4h': 'trend_4h', 'trend_1d': 'trend_1d',
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
    rng = random.Random(seed)
    stats: Dict[tuple, Tuple[int, float]] = {}
    for key, blocks_by_id in groups.items():
        blocks = list(blocks_by_id.values())
        n = len(blocks)
        if n < min_blocks:
            stats[key] = (n, 1.0)
            continue
        draws = 2000
        at_or_above = sum(statistics.fmean([v for _ in range(n) for v in blocks[rng.randrange(n)]]) >= 0
                          for _ in range(draws))
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
    return abs(z) >= t0.price_z_threshold or (z == 0 and abs(px) > 2 * t0.price_change_5m_threshold)


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
    if direction > 0:
        premium = sig.get('cb_premium')
        return (funding is not None and funding >= cfg.crowded_funding_long) or \
            (premium is not None and premium <= -cfg.crowded_cb_discount)
    return funding is not None and funding <= cfg.crowded_funding_short


def perp_flow_5m(sig: Dict) -> float:
    """5m perp taker flow: all futures venues when several report, else Binance."""
    if (sig.get('venues_active') or 0) >= 2 and sig.get('agg_cvd_5m'):
        return sig['agg_cvd_5m']
    return sig.get('futures_cvd_5m') or sig.get('futures_cvd') or 0.0


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
        # OI rising in the coin's own terms (z of its 5m OI change) above a small floor; the fixed threshold only
        # while its OI volatility is unknown
        oi_z = sig.get('oi_z', 0.0) or 0.0
        oi_confirms = (oi >= t0.impulse_oi_floor and oi_z >= t0.impulse_oi_z) if oi_z else oi >= t0.impulse_oi_min
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
        self._snapshot_cache: Dict[int, Dict[str, float]] = {}
        self.success = None
        if CONFIG.ml.success_enabled:
            try:
                from ml import SuccessModel
                self.success = SuccessModel()
            except Exception as e:
                logger.warning(f"P(edge) model unavailable: {e}")
            pretrained = load_pretrained()
            if pretrained and pretrained.get('success') and not pretrained_current(pretrained):
                logger.warning(f"Pretrained P(edge) is of logic {pretrained.get('logic_version')}, not "
                               f"{CONFIG.journal.logic_version}: not used until pretrain.py runs again")
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
        columns = list(rows[0])
        self.conn.executemany(
            f"INSERT INTO signals ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
            [tuple(r[c] for c in columns) for r in rows],
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
        with self._lock:
            for symbol, sig in signals:
                price = prices.get(symbol)
                if not price:
                    continue
                kind, group_key, direction = classify(sig)
                family, rank = event_family(group_key)
                last_ts, last_rank = self._last_logged.get((symbol, family), (0, -1))
                if now_ms - last_ts < cooldown_ms and rank <= last_rank:
                    continue
                self._last_logged[(symbol, family)] = (now_ms, rank)
                row = self._base_row(now_ms, symbol, kind, group_key, direction, price, sig)
                # card_veto: the setup did not become a card (no qualifying leg, its leg already played)
                row['vetoed'] = veto_reason(group_key, sig) or sig.get('card_veto')
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
        row.update({'entry': lv['entry'], 'sl': lv['sl'], 'tp1': lv['tp1'], 'tp2': lv['tp2'], 'tp3': lv['tp3'],
                    'rr_tp1': lv.get('rr_tp1'), 'low_rr': int(bool(lv.get('low_rr'))),
                    'rr_blend': lv.get('rr_blend'), 'rr_reason': lv.get('rr_reason'),
                    'vetoed': getattr(tracked, 'vetoed', None), 'of_confirm': getattr(tracked, 'of_confirm', None),
                    'confirms': json.dumps(getattr(tracked, 'confirms', None) or {}),
                    'conf_n': sum(1 for k, v in (getattr(tracked, 'confirms', None) or {}).items()
                                  if not k.startswith('_') and confirm.positive(v)),
                    'perp_led': 0, 'p_edge': tracked.sig.get('p_edge'),
                    'tp1_src': lv.get('tp1_src'), 'tp2_src': lv.get('tp2_src'), 'tp3_src': lv.get('tp3_src'),
                    'range_pos': lv.get('range_pos'),
                    'sl_src': lv.get('sl_src'), 'zone_src': lv.get('zone_src') or (tracked.plan or {}).get('zone_src'),
                    'setup_ts_ms': int(tracked.created * 1000), 'strategy': tracked.mode,
                    'anchor': _anchor_json(tracked.plan)})
        with self._lock:
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
                    'card_r': tracked.final_r, 'units': float(len(getattr(tracked, 'units', None) or [])) or None})
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
            if not self._snapshot_times or self._snapshot_times[-1] < ts_ms + minutes * 60_000:
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
                    self._snapshot_cache[t] = dict(self.conn.execute("SELECT symbol, price FROM universe WHERE ts_ms = ?", (t,)))
                    if len(self._snapshot_cache) > 400:
                        self._snapshot_cache.pop(next(iter(self._snapshot_cache)))
                snaps.append(self._snapshot_cache[t])
        a, b = snaps
        changes = [b[s] / a[s] - 1 for s in a if s in b and a[s]]
        if len(changes) < 20:
            return None
        return statistics.median(changes) if stat == 'median' else statistics.fmean(changes)

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
        import bisect
        import statistics
        since = int((time.time() - days * 86_400) * 1000)
        with self._lock:
            uni = self.conn.execute("SELECT ts_ms, symbol, price FROM universe WHERE ts_ms >= ? ORDER BY ts_ms",
                                    (since,)).fetchall()
            rows = self.conn.execute("SELECT group_key, symbol, ret_4h FROM signals WHERE kind = 'anomaly' AND "
                                     "ret_4h IS NOT NULL AND ts_ms >= ?", (since,)).fetchall()
        norm = lambda s: s.replace('/USDT:USDT', 'USDT').replace('/', '')
        series: Dict[str, list] = {}
        for t, s, p in uni:
            series.setdefault(norm(s), []).append((t, p))
        usual: Dict[str, float] = {}
        for s, v in series.items():
            ts = [x[0] for x in v]
            moves = []
            for t, p in v:
                j = bisect.bisect_left(ts, t + 4 * 3_600_000)
                if j < len(v) and abs(ts[j] - t - 4 * 3_600_000) <= 600_000 and p:
                    moves.append(abs(v[j][1] / p - 1))
            if len(moves) > 20:
                usual[s] = statistics.mean(moves)
        ratios: Dict[str, list] = {}
        for label, s, r4 in rows:
            base = usual.get(norm(s))
            if base:
                ratios.setdefault(label, []).append(abs(r4) / base)
        ANOMALY_EFFECT.clear()
        ANOMALY_EFFECT.update({k: (statistics.median(v), len(v)) for k, v in ratios.items() if len(v) >= 25})
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

    def refresh_drift(self, days: float = 3.0) -> int:
        """
        Feature drift of P(edge) (ML_PLAN.md H2): PSI of the last `days` of directional rows' model features against
        the reference distributions in models/cards/p_edge.json (written by pretrain.py) -> model_cards.DRIFT.
        """
        import model_cards
        from ml import SuccessModel
        card = model_cards.load_card('p_edge')
        if not card or not card.get('features'):
            return 0
        since = int((time.time() - days * 86400) * 1000)
        with self._lock:
            self.conn.row_factory = sqlite3.Row
            try:
                rows = self.conn.execute(
                    "SELECT * FROM signals WHERE kind NOT IN ('entry', 'card') AND direction != 0 AND ts_ms >= ? "
                    "ORDER BY ts_ms DESC LIMIT 3000", (since,)).fetchall()      # bounded: the features loop holds the GIL
            finally:
                self.conn.row_factory = None
        drift = model_cards.drift_of(card, [SuccessModel.features(r) for r in rows])
        model_cards.set_drift(drift)
        worst = model_cards.worst_drift()
        if worst and worst[1] > 0.25:
            logger.info(f"Drift: P(edge) feature {worst[0]} PSI {worst[1]:.2f} vs its training rows (> 0.25: a "
                        f"population the model was not trained on)")
        return len(drift)

    def refresh_hit_rates(self) -> int:
        """
        p(TP1 before the stop) per strategy from the replayed entries of the last 30 days (passed and vetoed: the
        replay is the same), >= 30 decided ones (TP1 / TP2 / TP3 vs SL) -> strategies.geometry.HIT_RATE, which turns
        the entry check from a fixed R:R into the expectancy p x R:R1 - (1 - p).
        """
        from strategies import geometry
        since = int((time.time() - 30 * 86400) * 1000)
        with self._lock:
            rows = self.conn.execute(
                "SELECT strategy, outcome FROM signals WHERE kind = 'entry' AND ts_ms >= ? AND outcome IN "
                "('TP1', 'TP2', 'TP3', 'SL') AND strategy IS NOT NULL", (since,)).fetchall()
        counts: Dict[str, List[int]] = {}
        for strategy, outcome in rows:
            c = counts.setdefault(strategy, [0, 0])
            c[0 if outcome == 'SL' else 1] += 1
        rates = {s: (hit / (hit + sl), hit + sl) for s, (sl, hit) in counts.items() if hit + sl >= 30}
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

    def coin_results(self, since_ms: int) -> List[Tuple[str, str, int, float]]:
        """(strategy, symbol, entries, mean net R to TP1) of the replayed, non-vetoed entries since `since_ms`."""
        with self._lock:
            return self.conn.execute(
                "SELECT strategy, symbol, COUNT(*), AVG(r_tp1) FROM signals WHERE kind = 'entry' AND r_tp1 IS NOT NULL "
                "AND (vetoed IS NULL OR vetoed = '') AND strategy IS NOT NULL AND ts_ms >= ? GROUP BY strategy, symbol",
                (since_ms,)).fetchall()

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
                f"SELECT id, ts_ms, symbol, price, direction, entry, sl, tp1, tp2, tp3, {rets}, kind, funding_8h FROM signals "
                f"WHERE eval_failed = 0 AND ({pending}) ORDER BY ts_ms LIMIT ?",
                (*[due[label] for label in HORIZONS], limit),
            )
            columns = [c[0] for c in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    async def evaluate_loop(self, fetcher):
        """Fill in outcomes as horizons come due (also catches up on signals from previous runs)."""
        last_regime_stats = 0.0
        while True:
            try:
                await self._evaluate_pass(fetcher)
                if time.time() - last_regime_stats >= 3600:
                    last_regime_stats = time.time()
                    await asyncio.to_thread(self.refresh_regime_stats)
                    await asyncio.to_thread(self.refresh_confirm_stats)
                    await asyncio.to_thread(self.refresh_anomaly_effects)
                    await asyncio.to_thread(self.refresh_drift)
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
        updates = {f'ret_{label}': float(window[-1][4]) / price - 1}
        if label == '4h':
            updates['mfe_4h'] = max(float(k[2]) for k in window) / price - 1
            updates['mae_4h'] = min(float(k[3]) for k in window) / price - 1
        if label == '8h' and row.get('entry') is not None and row.get('direction') and row.get('kind') == 'entry':
            # Entry rows: replay SL / TP on the 1m candles of the trade's whole life, filled like a human would
            updates.update(simulate(row, row['direction'], window, use_fill=True, funding_8h=row.get('funding_8h')))
        sets = ', '.join(f"{col} = ?" for col in updates)
        with self._lock:
            self.conn.execute(f"UPDATE signals SET {sets} WHERE id = ?", (*updates.values(), signal_id))
            self.conn.commit()
        if label == '4h' and self.success is not None and row.get('direction') and row.get('kind') not in ('entry', 'card'):
            self._learn(signal_id)

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
