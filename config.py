"""
All tunables, as frozen dataclasses reached through the global CONFIG.

Local overrides: an optional `config.local.toml` next to this file replaces individual values without code edits,
e.g.

    [tier0]
    rvol_1m_threshold = 6.0

    [notify]
    enabled = true
    telegram_token = "..."
    telegram_chat_id = "..."

Unknown sections/keys or values of the wrong type are rejected at start-up (load_overrides).
"""
import dataclasses
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExchangeConfig:
    exchange_id: str = "binance"
    quote_currency: str = "USDT"
    # The universe is the set of coins with COMPLETE data, not the top by volume (fetcher.select_universe): every
    # coin has a Binance spot pair (spot vs perp, the spot confirmation), >= min_futures_venues other futures venues
    # (aggregated OI / liquidations / flows), enough history for its higher-timeframe pools (1h candles 8 days), a
    # tradable spread; the most liquid of them up to max_pairs. The top 300 by volume had no spot on a third of the
    # coins and no book / positioning on most, and saturated the link (Binance ~190 KB/s, stalls). The market
    # baseline for Edge still uses every USDT perpetual (REST mark prices, no streams).
    max_pairs: int = 150
    min_24h_quote_volume_usd: float = 10_000_000
    require_spot: bool = True
    min_futures_venues: int = 2          # of Bybit, OKX, Bitget, Hyperliquid
    min_listing_days: int = 9
    max_spread: float = 0.001            # bid-ask spread / mid at the selection (10 bp)
    # Binance exchangeInfo `underlyingType` values to skip: tokenized stocks (US/HK/KR/CN) and pre-IPO shares.
    # They sit flat outside their exchange's trading hours and trip squeeze/flat-price phases.
    excluded_underlying_types: tuple = ('EQUITY', 'HK_EQUITY', 'KR_EQUITY', 'CN_EQUITY', 'PREMARKET', 'COMMODITY')
    # Tokenized gold / silver trade the metal, not crypto flows (PAXG / XAUT were flagged 'whales' on metal hedges)
    excluded_bases: tuple = ('PAXG', 'XAUT', 'XAU', 'XAG', 'XPT', 'XPD')
    # The universe (top max_pairs by 24h volume) is re-selected this often: new listings join, dropped coins leave
    universe_refresh_sec: int = 3600


@dataclass(frozen=True)
class TimeframeConfig:
    # 99, not 100: Binance futures klines cost weight 1 below limit=100 and 2 from 100
    rest_lookback_candles: int = 99
    rest_timeframe: str = "15m"
    scan_interval_sec: int = 10
    bulk_funding_interval_sec: int = 30
    oi_update_interval_sec: int = 60


@dataclass(frozen=True)
class MetricsConfig:
    rvol_window: int = 50
    rvol_micro_burst_threshold: float = 1.5
    rvol_anomaly_threshold: float = 4.0
    bbw_squeeze_lookback: int = 50
    # Squeeze = Bollinger width at most this multiple of its bbw_squeeze_lookback minimum
    bbw_squeeze_tolerance: float = 1.05
    oi_change_window: int = 12
    # Short OI window (15m candles) for the price/OI matrix checks in phases D and E: 4 = 1h
    oi_short_window: int = 4
    # Funding normalized to an 8h-equivalent rate (0.001 = 0.1%); Binance's neutral rate is +0.01% per 8h.
    # Crowded longs from +0.03% (3x neutral), extreme from +0.1%; shorts are crowded below -0.05%
    funding_crowded: float = 0.0003
    funding_extreme_positive: float = 0.001
    funding_extreme_negative: float = -0.0005
    # Phase D: candle taker delta / candle quote volume below this (-0.2 = taker sells >= 60% of the candle)
    dump_delta_ratio: float = -0.2
    # Phase A: the price_flat_window range (max high - min low) within this many ATRs counts as a tight range, and
    # net taker SELLING of at least this share of its volume (0.1 = sellers took 55%) that fails to push price out
    # of it counts as sells absorbed by resting bids
    flat_range_atr: float = 3.0
    accumulation_flow_min: float = 0.1
    # Phase C: net taker flow over cvd_divergence_lookback at the new high must be below this (-0.05 = buyers <= 47.5%)
    distribution_flow_max: float = -0.05
    # Phase B (Wyckoff spring): the prior spring_lookback candles must form a trading range no wider than this many
    # ATRs, and the sweep below its low must be shallow (at most spring_max_depth_atr ATRs) before closing back inside
    spring_range_atr: float = 6.0
    # The 15m "B spring / C distribution" scores (5-hour windows, C without a range): off, replaced by the 1h Wyckoff
    # range events (strategies/wyckoff_range.py)
    legacy_wyckoff_bc: bool = False
    spring_max_depth_atr: float = 1.0
    # ... and it must be sideways: the net close-to-close move over the lookback at most this share of its high-low
    # span (a 6-ATR channel down also fits "range <= 6 ATR"; live, springs scored in such declines went the signal's
    # way within 15m only 27% of the time)
    spring_max_drift: float = 0.5
    # Phase E: OI change over oi_short_window below this = forced long liquidation, after a decline over
    # price_flat_window of at least capitulation_min_drop, confirmed by buyers >= 55% of the candle
    capitulation_oi_drop: float = -0.02
    capitulation_min_drop: float = 0.03
    # ... measured in the coin's own volatility once known: the decline over price_flat_window >= this many standard
    # deviations of 15m returns x sqrt(window), the OI drop over oi_short_window >= this many OI standard deviations
    capitulation_drop_z: float = 3.0
    capitulation_oi_z: float = 2.0
    capitulation_drop_floor: float = 0.01
    capitulation_oi_floor: float = 0.005
    capitulation_confirm_flow: float = 0.1
    # Phase D: OI must grow at least this much over oi_short_window (new shorts, not noise)
    dump_oi_min: float = 0.005
    trend_oi_z: float = 1.5
    trend_oi_floor: float = 0.003
    # Phase F (markup breakout, the mirror of D): candle delta ratio above this (+0.2 = taker buys >= 60%), OI up at
    # least dump_oi_min over oi_short_window, funding below funding_extreme_positive (longs not crowded yet)
    markup_delta_ratio: float = 0.2
    cvd_divergence_lookback: int = 20
    price_flat_window: int = 10
    local_high_window: int = 50
    spring_lookback: int = 20
    # Spot vs perp flow over this many 15m candles (4 = 1h)
    spot_perp_window: int = 4


@dataclass(frozen=True)
class ScoringConfig:
    accumulation_weight: int = 1
    cvd_rising_weight: int = 2
    oi_rising_flat_price_weight: int = 1
    # 3 = a fully met spring reaches alert_threshold on its own
    spring_weight: int = 3
    distribution_divergence_weight: int = 2
    funding_extreme_weight: int = 1
    dump_oi_rising_weight: int = 3
    distribution_crowded_weight: int = 1
    dump_cvd_drop_weight: int = 2
    capitulation_rvol_weight: int = 2
    capitulation_funding_weight: int = 1
    capitulation_delta_flip_weight: int = 2
    # +1 to C / E when spot and perp flow confirm the reversal read (spot-led selling at a high, spot absorbing a flush)
    spot_perp_confirm_weight: int = 1
    # +1 to E when long liquidations spiked (forced selling, the capitulation itself)
    liquidation_weight: int = 1
    alert_threshold: int = 3
    micro_burst_rvol: float = 1.5
    # Hot symbols (order book) also include structured setups: Score >= tier2_min_score AND RVOL_1m > micro_burst_rvol
    tier2_min_score: int = 3


@dataclass(frozen=True)
class Tier0Config:
    """Raw impulse detection that ignores phases/Score. Any single condition flags an anomaly."""
    # 5x the average minute, and only on a minute that traded at least rvol_min_minute_usd: on thin coins a 3x
    # minute is routine noise (in a 7h run it fired on 258 of 300 coins with no edge over the market)
    rvol_1m_threshold: float = 5.0
    rvol_min_minute_usd: float = 25_000
    # 5m price / OI moves: an anomaly needs BOTH the absolute floor and a z-score of the coin's own typical 5m move
    # (std of 15m changes over ~24h / sqrt(3)); 2% in 5m is noise for a memecoin and an event for BTC
    oi_change_5m_threshold: float = 0.008
    price_change_5m_threshold: float = 0.01
    price_z_threshold: float = 4.0
    oi_z_threshold: float = 4.0
    window_sec: int = 300
    # No signals / journal rows this long after a start: the 5m flow windows are seeded from REST 1m klines (Binance),
    # so a minute is enough for the streams to connect (was window_sec = 5 minutes)
    warmup_sec: int = 60
    check_interval_sec: float = 2.0
    # Keep hot-symbol (order book) subscriptions this long after the last trigger
    tier2_hold_sec: int = 300
    # A 5m price impulse is directional only if OI rose at least this much (new positions) and futures CVD agrees
    impulse_oi_min: float = 0.003
    impulse_oi_z: float = 2.0
    impulse_oi_floor: float = 0.0015
    # Net whale flow over 5m, in units of the symbol's whale size, that counts as an anomaly
    whale_net_units: float = 3.0
    # |Px 5m| below this with an RVOL spike = absorption (volume hits resting orders, price doesn't move)
    absorption_max_move: float = 0.005
    # Anomalies stay on screen this long after their last trigger
    display_hold_sec: int = 600
    # Hysteresis: a symbol stays anomalous this long after its last trigger (RVOL hovering at the threshold
    # otherwise flips the flag every 2s check)
    anomaly_hold_sec: int = 60
    # Hot-symbol eviction: only subscriptions not triggered for this long, and at least this old, can be evicted
    tier2_evict_idle_sec: int = 120
    tier2_min_age_sec: int = 60
    # Algos fire at :00/:15/:30/:45 (quarter-hour bursts, +30% volume): an RVOL-only trigger is ignored this long
    # after each quarter-hour boundary
    quarter_boundary_ignore_sec: int = 45


@dataclass(frozen=True)
class SweepConfig:
    """
    Whale detection on taker sweeps: prints of one side with the same trade time (one taker order walking several
    price levels, the Aggr technique) or within sweep_merge_ms are merged before sizing. The whale size per coin is
    the rolling `percentile` of its sweep sizes (log-histogram decayed hourly), never below the liquidity-tier floor.
    """
    sweep_merge_ms: int = 300
    percentile: float = 0.995
    min_samples: int = 300
    hist_decay_per_hour: float = 0.97
    # USD floors by 24h-volume rank: top floor_top_n_1 coins, top floor_top_n_2, the rest
    floor_top_n_1: int = 2
    floor_top_usd_1: float = 500_000
    floor_top_n_2: int = 30
    floor_top_usd_2: float = 100_000
    floor_rest_usd: float = 25_000
    # Algo cluster (TWAP-like): >= cluster_min_count notable (>= cluster_percentile) sweeps of one side within
    # cluster_window_sec, summing to at least one whale size
    cluster_percentile: float = 0.99
    cluster_window_sec: int = 60
    cluster_min_count: int = 8
    # ... summing to at least this many whale sizes, with this share of the notable sweeps on one side
    cluster_min_whales: float = 2.0
    cluster_side_share: float = 0.8
    window_sec: int = 900
    # a sweep with forced flow of its side (liquidations) >= this share of its size is not a whale's decision
    forced_share: float = 0.5


@dataclass(frozen=True)
class LiquidationConfig:
    """Liquidations (Binance !forceOrder@arr is SAMPLED: at most one per symbol per second; Bybit/OKX add more)."""
    window_sec: int = 300
    # A liquidation cascade: liquidations over window_sec >= this share of the coin's average minute volume
    # and at least cascade_min_usd
    cascade_avg_minute_share: float = 1.0
    cascade_min_usd: float = 50_000


@dataclass(frozen=True)
class DepthConfig:
    """Order book (Binance <sym>@depth20@500ms) for hot symbols only: open cards and active anomalies."""
    # 40 with the data-complete universe (~150 coins instead of 300 freed ~half of the trade / kline bandwidth)
    max_symbols: int = 40
    # Sockets the order books are spread over (~1.5 KB / 500ms per book; one socket carries ~40-70 KB/s)
    sockets: int = 6
    band_pcts: tuple = (0.005, 0.01)
    # A level is a wall at >= wall_multiple x the median level notional of the book, counted only after it has
    # stood wall_min_age_sec (spoofed walls are pulled within seconds)
    wall_multiple: float = 5.0
    wall_min_age_sec: float = 10.0
    # Partial-book streams push only on change: a book is stale only after this long without an update
    stale_sec: int = 60
    # REST 500-level snapshots of the hot symbols (weight 10 each) for band depth; used while this fresh
    # 40 books x weight 10 every 60s = 400 weight / min (every 30s it was 800 of the ~1680 budget)
    deep_interval_sec: int = 60
    deep_max_age_sec: int = 150
    # Heatmap: every 500-level snapshot is bucketed by price (heat_bucket_pct of price) and kept heat_snapshots deep
    # (2h at 30s); a bucket is a liquidity band when it held >= heat_band_multiple x the snapshot's median bucket in
    # >= heat_band_presence of the snapshots of the last heat_band_window_sec (at least heat_band_min_snapshots):
    # resting size that stayed, not a flashed wall
    heat_bucket_pct: float = 0.001
    # Only buckets within this share of price around the mid are kept (memory: ~100 floats per snapshot)
    heat_range_pct: float = 0.05
    heat_snapshots: int = 240
    heat_band_window_sec: int = 1800
    heat_band_multiple: float = 4.0
    heat_band_presence: float = 0.8
    heat_band_min_snapshots: int = 20
    heat_band_max_per_side: int = 3


@dataclass(frozen=True)
class OrderflowConfig:
    """Spot-vs-perp veto and footprint / absorption confirmation of entries."""
    # Perp-led: 1h spot and perp flows disagree in sign, or spot net flow < this share of the perp net flow
    perp_led_spot_share: float = 0.25
    veto_perp_led: bool = True
    # "Crowded" (journal.crowded): funding >= +0.03% / 8h for longs (<= -0.01% for shorts) or a Coinbase discount
    # >= 0.05% for longs, with OI +0.5% over the last hour
    crowded_funding_long: float = 0.0003
    crowded_funding_short: float = -0.0001
    crowded_cb_discount: float = 0.0005
    crowded_oi_1h: float = 0.005
    # Footprint price bucket as a share of the 15m ATR, diagonal imbalance ratio and consecutive levels
    footprint_bucket_atr: float = 0.05
    imbalance_ratio: float = 3.0
    stacked_levels: int = 3
    # Absorption: a 1m delta >= this percentile of the last hour's |delta| with the minute's range <= max_move ATR
    absorption_percentile: float = 0.9
    absorption_max_move_atr: float = 0.2
    # True: entries without absorption / stacked imbalance on the trade side are vetoed (still journaled).
    # False: the order-flow confirmation is recorded and shown, and required only once the journal proves entries
    # without it lose (promote_confirmations). Measured live on 2026-09-26 as a fixed veto it rejected 37 of 52
    # triggers and 9 of 11 cards then ran to TP1 without an entry.
    require_orderflow_confirm: bool = False
    # CVD divergence at a reversal's extreme: the previous swing is looked for this far back
    divergence_lookback_min: int = 60
    # Entry confirmations required by rule ('<strategy>:<confirmation>', strategies/confirm.py): a breakout needs
    # rising OI (new positions behind it), as the D / F phases and directional impulses already do
    required_confirmations: tuple = ('breakout:oi',)
    # A confirmation becomes required for a strategy once its entries WITHOUT it have >= promote_min_clusters
    # independent results (15m clusters) and a 90% interval of the 4h Edge entirely below 0 (journal, hourly)
    promote_confirmations: bool = True
    promote_min_clusters: int = 30
    # an entry needs at least this many positive confirmations (flow / spot / oi / orderflow); 0 = off
    min_confirmations: int = 1


@dataclass(frozen=True)
class MLConfig:
    """ml.py: IsolationForest anomalies, GaussianMixture regimes, river P(edge) (see its docstring)."""
    # Anomalies: fit on the last anomaly_window_sec of universe feature vectors sampled every
    # anomaly_sample_every_sec, refit hourly; a coin is anomalous when its vector is among the anomaly_quantile
    # most unusual of the training window. Until the first fit (and with anomaly_enabled=false) the rules decide.
    anomaly_enabled: bool = True
    # The classic rules (RVOL at time of day, z-scores, OI, whales, liquidations, one venue) decide anomalies; the
    # IsolationForest is only journaled: no evidence it beats rules / robust z on 9 interpretable features
    # (ADBench: no universally best detector), and live its "most unusual" events moved no more than the rules'
    anomaly_decides: bool = False
    anomaly_quantile: float = 0.001
    anomaly_window_sec: int = 3 * 3600
    anomaly_sample_every_sec: int = 30
    anomaly_fit_every_sec: int = 3600
    # ~15 min of samples with the ~100-coin universe (IsolationForest draws 256 per tree)
    anomaly_min_samples: int = 3000
    # Vectors of the first minutes are not sampled for training: 5m windows and OI changes are still filling up
    anomaly_skip_first_sec: int = 360
    # Regimes: Gaussian mixture on market-wide features of closed 15m candles (history persisted, ~31 days)
    regime_enabled: bool = True
    regime_clusters: int = 4
    # ~7 months of 15m candles: the pretrained months (pretrain.py) plus the live ones
    regime_history: int = 20_000
    regime_min_history: int = 60
    regime_refit_sec: int = 86_400
    # Mute a setup in the current regime once its journal Edge there has >= regime_veto_min_n results and the
    # upper end of its 90% interval is below 0 (journaled with vetoed='regime')
    regime_veto: bool = True
    regime_veto_min_n: int = 30
    # False discovery rate of the journal's automatic rules (regime mutes, promoted confirmations): Benjamini-
    # Hochberg over all the groups tested at once
    rule_fdr: float = 0.10
    # P(edge): shown on cards once trained on this many labelled rows; shadow mode (never filters)
    success_enabled: bool = True
    success_min_trained: int = 300


@dataclass(frozen=True)
class WhaleConfig:
    """Kept for compatibility (display window); sizing moved to SweepConfig."""
    min_usd: float = 25_000
    avg_minute_share: float = 0.25
    window_sec: int = 900


@dataclass(frozen=True)
class LevelsConfig:
    """Two-timeframe model (levels.py): 15m impulse + Fibonacci context, 5m structure-shift entry. Rules, not advice."""
    # HTF impulse: largest leg of the last N 15m candles, >= impulse_min_atr ATR and >= impulse_min_candles long
    htf_lookback_candles: int = 48          # 12h: where the leg's END is searched
    # The leg's START is searched back over 1h history up to this far (a move of hours / days is measured whole)
    leg_lookback_hours: int = 96
    impulse_min_atr: float = 3.0
    impulse_min_candles: int = 4            # 1h
    # ... and at least this big in price: at night ATR shrinks and a 0.5% drift can measure 7 ATR
    impulse_min_move: float = 0.015
    # Continuation: look for the trigger once the pullback reaches this retracement zone of the impulse
    # The pullback band of a continuation: 0.382-0.618 of the leg (a deeper retrace is a trend failure, not an entry);
    # the zone is a real map level inside it, else the EMA20 of the leg's timeframe (Raschke's "Holy Grail"
    # pullback); no level and no EMA20 inside: no card ('no_level'). Automated tests found no edge in Fibonacci
    # ratios themselves (ESWA 2021): a Fibonacci-only zone was a line with nothing behind it.
    continuation_zone: tuple = (0.382, 0.618)
    continuation_targets: tuple = (1.0, 1.272, 1.618)
    # Reversal: price must still be within this retracement of the reversed leg's end (accumulation: a bit wider)
    reversal_zone_max: float = 0.236
    # must stay below the first reversal target (0.382), or there is no room left for the trade
    accumulation_zone_max: float = 0.3
    reversal_targets: tuple = (0.382, 0.5, 0.618)
    # LTF trigger on ltf_minutes candles built from the 1m stream (15m -> 5m keeps the 3-5x step between timeframes
    # and leaves a human time to act): close beyond the high/low of the last ltf_break_lookback candles up to the
    # zone extreme, with net taker flow of the last ltf_flow_candles candles after that extreme in the trade's direction
    ltf_minutes: int = 5
    ltf_break_lookback: int = 5
    ltf_flow_candles: int = 3
    # Stop = structure + a volatility buffer (hybrid): beyond the farthest of the structural zone the entry comes from
    # (its wick-defined edge), the deepest wick that tested it and a stop pool right behind, then by this many ATRs of
    # the anchor's timeframe. 0.1 sat where stops cluster (Osler, NY Fed SR150) and inside the 0.1-1.0 ATR pierce this
    # bot itself calls a sweep: 47% of 15m-swing stops at 0.1 ATR were followed by the +2 ATR move (history, 2026-09)
    stop_buffer_atr: float = 0.3
    # ... and never closer than this many 15m ATRs to the entry: live, stops < 1 ATR (the low of 2-3 5m candles)
    # were hit on 8 of 10 entries while their paper R:R read 9-23
    min_stop_atr: float = 1.0
    # Entries with R:R to TP1 below this are LOW RR: with veto_low_rr they are journaled as vetoed entries
    # (vetoed='low_rr') and the card keeps waiting, so the screen only shows entries worth taking by hand
    # 2:1, the practitioners' minimum for intraday trades (breakeven win rate 33% before costs); was 1.0
    min_rr_tp1: float = 2.0
    veto_low_rr: bool = True
    # Manual execution: the journal replays entries filled this long after the trigger, plus slippage
    fill_delay_sec: int = 30
    slippage_bps: float = 5.0
    # Slippage grows as liquidity falls (square-root impact): slippage_bps x sqrt(slippage_ref_volume / 24h volume),
    # between slippage_bps and slippage_max_bps. A hypothesis, not a measurement: 5 bps for BTC and a $10M coin alike
    # understated the cost of the small ones (spreads up to 10 bps, thin books in cascades)
    slippage_ref_volume: float = 500e6
    slippage_max_bps: float = 25.0
    # A target (a resting limit order) counts as filled in the journal's replay only once price traded this far
    # THROUGH it: a touch fills only part of the queue (backtests that fill limits on a touch overstate the result)
    target_through_bps: float = 2.0
    # Spring "test": average 1m volume of the pullback <= this share of the spring candle's average minute
    spring_test_volume_ratio: float = 0.6
    # Lifetimes: waiting for the pullback, waiting for the trigger inside the zone, managing the trade
    watch_ttl_sec: int = 6 * 3600
    # A new card waits this long for the coin's 1h history / level map before its first plan is taken anyway
    plan_wait_sec: int = 180
    zone_ttl_sec: int = 3 * 3600
    trade_ttl_sec: int = 8 * 3600
    # Finished signals stay on screen this long
    finished_display_sec: int = 1800


@dataclass(frozen=True)
class ZonesConfig:
    """
    Level map (zones.py): support / resistance, liquidity pools, estimated liquidation clusters, volume profile,
    order-book walls, VWAP and Fibonacci levels, merged into zones weighted by confluence. Built only for coins
    with cards. The weights are hypotheses; the journal stores which sources each target came from.
    """
    refresh_sec: int = 900
    # 1h candles / 1h OI history per card coin (limit 99 weighs 1; openInterestHist has its own 1000/5min limit)
    htf_refresh_sec: int = 3600
    htf_candles: int = 99
    # Swing points: a high/low with this many lower highs / higher lows on each side
    swing_width_15m: int = 3
    swing_width_1h: int = 2
    # Equal highs / lows (stop pools): >= 2 swings within this many ATR of each other
    equal_tolerance_atr: float = 0.15
    # Volume profile: price buckets per ATR, value area share, HVN = bucket volume >= this multiple of the median
    profile_buckets_per_atr: float = 4.0
    value_area: float = 0.7
    hvn_ratio: float = 2.0
    # Liquidation estimate: leverage tiers and the share of new OI assumed at each; maintenance margin share
    liq_leverages: tuple = (10, 25, 50, 100)
    liq_leverage_weights: tuple = (0.3, 0.35, 0.25, 0.1)
    liq_maintenance: float = 0.005
    # Clusters are summed in buckets of this share of price (at least ATR/2); a cluster is a level when it holds at
    # least liq_min_oi_share of the coin's current OI, the largest liq_max_per_side per side
    liq_bucket: float = 0.004
    liq_min_oi_share: float = 0.003
    liq_max_per_side: int = 6
    # Observed liquidations: a price bucket with at least this USD in 24h is a swept pool
    liq_observed_min_usd: float = 250_000
    # Levels closer than this many ATR merge into one zone
    merge_atr: float = 0.3
    # Source weights; a zone's strength is the sum of its sources
    weights: tuple = (('swing_1h', 1.5), ('swing_15m', 1.0), ('equal', 2.0), ('pdhl', 2.0), ('poc', 1.5),
                      ('va', 1.0), ('hvn', 1.0), ('liq_est', 1.5), ('liq_hit', 1.0), ('wall', 1.0),
                      ('vwap', 1.0), ('fib', 0.5), ('range', 1.5), ('liq_hl', 2.0), ('book', 1.5), ('round', 1.0),
                      ('swing_1d', 2.5), ('htf', 2.5))
    # Round-number levels / pools within this many ATR of price (zones.round_levels)
    round_span_atr: float = 3.0
    # Targets: a zone must be at least this strong to be an obstacle (TP1/TP2); TP3 prefers pools / liquidations
    min_strength: float = 2.5
    min_target_atr: float = 1.0
    # Stop: beyond an equal-high/low pool or liquidation cluster within this many ATR behind the invalidation
    stop_pool_atr: float = 0.6
    max_stop_atr: float = 3.0
    # Continuation zone: strongest support inside the Fibonacci zone, +- this many ATR
    zone_half_atr: float = 0.25


@dataclass(frozen=True)
class PositioningConfig:
    """Other traders' positioning (positioning.py): long/short ratios, Hyperliquid large accounts."""
    # Hyperliquid: the most active accounts by monthly volume with at least this equity
    hl_accounts: int = 300
    hl_min_account_usd: float = 100_000
    hl_accounts_refresh_sec: int = 24 * 3600
    # The leaderboard file is ~40 MB: downloaded at this capped rate so the market streams keep their bandwidth
    hl_download_bytes_per_sec: int = 1_000_000
    hl_positions_refresh_sec: int = 300
    # info requests weigh 2 of 1200 per minute: stay far below
    hl_requests_per_min: int = 240
    # A liquidation bucket of the tracked accounts becomes a level from this size
    hl_min_level_usd: float = 250_000
    hl_accounts_path: str = "hl_accounts.json"
    # Coinbase premium: its USD price vs Binance spot (USDT), only when both traded within this many seconds
    coinbase_max_age_sec: int = 60


@dataclass(frozen=True)
class PoolsConfig:
    """
    Per-strategy coin pools (pools.py): each strategy trades only its own coins, refreshed hourly. A pool = the
    universe filtered by the strategy's rule (coin classes by 24h volume rank: major = BTC ETH SOL XRP BNB, large =
    rank <= 30, mid = rank <= 80, small = the rest; sectors to exclude; minimum 1h volatility), minus the coins where
    the strategy's journaled entries of the last lookback_days average <= exclude_below_r over >= min_entries (walk-
    forward on the archive: the worst coins of the last 6 months stayed the worst the next month, -0.39R vs -0.10R;
    picking the best ones did not help), capped at `size` coins by 24h volume. Setups outside the pool are journaled
    with vetoed='not_in_pool'.
    """
    enabled: bool = True
    size: int = 20
    refresh_sec: int = 3600
    lookback_days: int = 90
    min_entries: int = 8
    exclude_below_r: float = -0.3
    # (strategy, classes 'major,large,mid,small' or 'all', sectors to exclude (sectors.py names), min ATR(1h) in %)
    rules: tuple = (('trend', 'all', '', 0.0), ('momentum', 'all', '', 0.0), ('wyckoff', 'all', '', 0.0),
                    ('absorption', 'all', '', 0.0), ('exhaustion', 'all', '', 0.0), ('sweep', 'all', '', 0.0),
                    ('breakout', 'all', '', 0.0))
    # strategies without a rule (crypto_maniac's systems) run on every coin of the universe; a coin whose journaled
    # entries of a strategy lose (exclude_below_r) is still excluded from it: see pools.Pools.allows


@dataclass(frozen=True)
class StrategiesConfig:
    """
    Strategies (strategies/): each has its own anchor (a leg, a level or a range), entry, stop and target intent;
    only the stop floor, the R:R check, the card lifecycle and the journal are shared. Timeframe rule: events are
    detected on any data (ticks, 1m), the structure is never finer than 15m, the entry never finer than 5m, and the
    entry timeframe is 3-6x finer than the structure (Elder's factor of ~5): 15m -> 5m, 1h -> 15m, 4h -> 1h. Sizes are
    in 15m ATRs; lifetimes are (waiting, trigger in the zone, open trade) seconds.
    """
    # Every strategy produces cards again (eng-10, the owner's decision 2026-09-30): the archive replay cannot see the
    # live-only inputs (confirmations from spot / other venues / footprint, liquidations, books), and a disabled
    # strategy produced no card, so no entry, no confirmations and no replay were ever measured live. Setups that lost
    # on the archive are marked on their cards (`archive_negative`) and judged by the live journal with the rule in
    # CLAUDE.md ("Live verdict"): kept or deleted from the code.
    enabled: tuple = ('trend', 'momentum', 'wyckoff', 'wyckoff_range', 'sweep', 'absorption', 'exhaustion', 'breakout',
                      'supply_demand', 'auction', 'smt', 'trendline', 'thirdeye', 'fib05', 'bomberman', 'csi',
                      'oi_accum')
    # BULL E buys the selling climax: Wyckoff reads the climax as the START of a trading range and buys later (the
    # spring's test: wyckoff_range); journaled, no card
    disabled_setups: tuple = ('BULL E',)
    # Raschke's Holy Grail: the EMA20 pullback only when ADX(14) > this (the source's rule; no map level in the zone)
    holy_grail_adx: float = 30.0
    # Lost net of costs on the archive card replay (research-findings skill: cards_6m / phases_6m / cards_fixed_12m):
    # a warning on the card, not a filter
    # (SWEEP / BREAKOUT were rewritten to their sources in eng-16: the archive has not replayed the new logic)
    archive_negative: tuple = ('BULL A', 'BULL B', 'BEAR C', 'BULL E', 'BULL F', 'BEAR D', 'IMPULSE UP')
    # 1h candles of every coin (fetcher._hourly_candles_loop): ~8 days for the weekly / daily / session pools
    h1_candles: int = 200
    h1_refresh_sec: int = 3600
    # Events of a closed 15m candle (sweeps, breakouts) fire while it is the coin's latest candle: after a feed gap its
    # REST replacement arrives minutes late (live, a 3-minute limit lost every event of a disturbed close); each event
    # fires once, the fired ones are kept in scanner_state.json across restarts, and the entry is priced now (R:R)
    close_event_max_age_sec: int = 900
    # Elder's tide (trend / momentum pullbacks): vetoed 'against_tide' when BTC moved at least this much against the
    # trade over the last hour, or the coin's 1h trend points the other way
    tide_btc_against: float = 0.005
    # The coin's own trend (1h): close vs EMA(trend_ema) and the EMA's slope over trend_slope_bars bars
    trend_ema: int = 20
    trend_slope_bars: int = 4
    # The coin's weekly trend (context only, journaled as trend_w / breadth_w): distance of the price from the EMA of
    # the last trend_w_ema CLOSED weekly closes in standard deviations of the weekly log returns over the same weeks.
    # Tested 2026-09-27 on 120 coins' full daily history: the weekly EMA is no level of its own (touches / crosses
    # behave like parallel lines EMA x 0.8..1.2), the trend a touch happens in is what differs
    trend_w_ema: int = 20
    # Stop floor = levels.min_stop_atr x max(ATR14, ATR of the last recent_atr_candles 15m candles): ATR14 lags a
    # waking market (live: the last hour's ATR was 26% above ATR14 when the stops were hit)
    recent_atr_candles: int = 4
    # Liquidity sweep (ICT / SMC: pools of the higher timeframes, swept by a 15m candle, entry on 5m). Pools: intact
    # 1h swings of the last sweep_swing_hours, equal highs / lows, previous day / week high-low, the day's high-low
    # and the last completed sessions (UTC hours), each at least sweep_pool_min_age_sec old and not traded through
    # since it formed. The sweep: a closed 15m candle pierces a pool by sweep_min_depth_atr-sweep_max_depth_atr and
    # closes back beyond it on >= sweep_min_rvol x the average 15m volume. Against the coin's 1h trend it is vetoed
    # ('against_trend'): live, sweeps of highs in a rising market lost -0.35R a trade, sweeps of lows +0.36R
    sweep_swing_hours: int = 72
    sweep_pool_min_age_sec: int = 3600
    sweep_min_depth_atr: float = 0.1
    sweep_max_depth_atr: float = 1.0
    sweep_min_rvol: float = 1.0
    sweep_sessions: tuple = (('Asia', 0, 8), ('London', 7, 16), ('New York', 13, 21))
    sweep_zone_atr: float = 0.25
    sweep_ttl: tuple = (2 * 3600, 2 * 3600, 8 * 3600)
    # Absorption at a level (order flow: the level is the setup, absorption the confirmation): a closed 1m candle with
    # taker delta >= the hour's orderflow.absorption_percentile against the level, volume >= absorption_min_rvol x the
    # average minute and a range <= orderflow.absorption_max_move_atr, its extreme within absorption_level_atr of a
    # higher-timeframe pool, a map zone of strength >= absorption_min_strength or a book liquidity band, after a move of
    # >= absorption_min_move_atr into it over the last hour (room to revert). Entry: a 5m structure shift
    absorption_min_rvol: float = 3.0
    absorption_level_atr: float = 0.3
    absorption_min_strength: float = 2.0
    absorption_min_move_atr: float = 1.5
    absorption_zone_atr: float = 0.25
    absorption_ttl: tuple = (60 * 60, 60 * 60, 6 * 3600)
    # Liquidation exhaustion (cascades overshoot mechanically; revert once the forced flow stops): a cascade
    # (liquidations.cascade_*) of longs on a drop / shorts on a rally; the leg runs from the extreme of the
    # exhaustion_pre_minutes before it to the cascade's extreme (following price until the entry), >= 3 ATR (a
    # reversal's first target 0.382 of the leg must pay 1R over the >= 1 ATR stop); entry: a 5m structure shift
    exhaustion_pre_minutes: int = 30
    exhaustion_min_leg_atr: float = 3.0
    exhaustion_ttl: tuple = (60 * 60, 60 * 60, 6 * 3600)
    # Breakout with initiative (60-70% of crypto breakouts fail: confirm by the close, volume and acceptance): the range
    # of the breakout_range_candles 15m candles before the breakout candle, breakout_min_width_atr-breakout_max_width_atr
    # wide; the breakout candle closes beyond it on >= breakout_min_rvol x the range's average volume with taker flow
    # on its side, and the next 15m candle closes beyond it too (acceptance) -> entry at that close; stop at the range
    # middle (>= the stop floor), INVALID back inside past the middle; targets: map, then measured moves in units of
    # max(range height, breakout_min_move_atr)
    breakout_range_candles: int = 8
    breakout_min_width_atr: float = 0.8
    breakout_max_width_atr: float = 3.0
    breakout_min_rvol: float = 1.5
    breakout_measured_moves: tuple = (1.0, 1.618, 2.618)
    breakout_min_move_atr: float = 1.5
    breakout_zone_atr: float = 0.25
    breakout_ttl: tuple = (2 * 3600, 2 * 3600, 8 * 3600)
    # ---- crypto_maniac's systems (github.com/roman-boop; strategies/maniac.py): his parameters as he ships them.
    # Longer histories they need: 15m / 1h candles of every coin (fetcher._hourly_candles_loop, limit 499 = weight 2)
    long_history_candles: int = 499
    # supply_demand-v4: ATR(20) of the bars before the source candle, 6 bars of approach, the departure confirmed
    # within 4 bars by a close 2 ATR beyond, zone height <= 1.2 ATR, score >= 3.5
    sd_atr_period: int = 20
    sd_prior_bars: int = 6
    sd_lookahead: int = 4
    sd_min_move_atr: float = 2.0
    sd_max_zone_atr: float = 1.2
    sd_min_score: float = 3.5
    sd_ttl: tuple = (24 * 3600, 4 * 3600, 8 * 3600)
    # auction_theory_in_code (1h): consolidation windows, POC concentration, impulse, retest reaction, targets
    auction_atr_period: int = 14
    auction_windows: tuple = (24, 48, 96)
    auction_max_range_atr: float = 6.0
    auction_max_range_pct: float = 0.10
    auction_max_net_ratio: float = 0.35
    auction_bin_atr: float = 0.20
    auction_min_concentration: float = 2.5
    auction_strong_concentration: float = 2.8
    auction_poc_edge: float = 0.15
    auction_candidate_stale: int = 8
    auction_impulse_mult: float = 1.0
    auction_impulse_horizon: int = 12
    auction_touch_atr: float = 0.25
    auction_reaction_atr: float = 0.15
    auction_invalidation_atr: float = 0.90
    auction_reaction_window: int = 3
    auction_max_touches: int = 2
    auction_level_ttl: int = 1500
    auction_max_crosses: int = 6
    auction_level_cooldown: int = 5
    auction_local_window: int = 30
    auction_max_levels: int = 50
    auction_min_rr: float = 1.5
    auction_fallback_rr: float = 2.5
    auction_stop_pad_atr: float = 0.35
    auction_min_risk_atr: float = 0.15
    auction_ttl: tuple = (3600, 3600, 48 * 3600)
    # lllll SMT / Quasimodo (15m main + 5m entry): the correlate is BTC (ETH for BTC itself); require_if_available;
    # the 5m inversion FVG within 8 main bars; entries only 02:00-10:00 New York (his session; () = any time)
    smt_main_bars: int = 500
    smt_with_trend_only: bool = False
    smt_ref_window: int = 60
    smt_ifvg_min_atr: float = 0.03
    smt_ifvg_search_back: int = 40
    smt_sl_buffer_atr: float = 0.1
    smt_min_rr: float = 2.0
    smt_fallback_rr: float = 2.5
    # ICT kill zones (New York time): London open 02:00-05:00 and New York open 07:00-10:00 (not one 02-10 window)
    smt_session: tuple = ('America/New_York', '02:00', '05:00', '07:00', '10:00')
    smt_ttl: tuple = (9 * 900, 9 * 900, 8 * 3600)
    # trendline_bot (15m, sloped lines only)
    tl_lookback: int = 400
    tl_pivot: int = 3
    tl_min_span: int = 40
    tl_min_touches: int = 3
    tl_touch_atr: float = 0.25
    tl_touch_gap: int = 5
    tl_violation_atr: float = 0.10
    tl_max_dist_atr: float = 3.0
    tl_flat_deg: float = 7.5
    tl_min_pivot_touches: int = 3
    tl_pivot_tol_atr: float = 0.20
    tl_max_deg: float = 35.0
    tl_last_touch_age: int = 40
    tl_confirm_atr: float = 0.15
    tl_min_body_atr: float = 0.35
    tl_max_depth_atr: float = 1.2
    tl_close_pos_max: float = 0.40
    tl_min_rr: float = 1.0
    trendline_ttl: tuple = (900, 900, 24 * 3600)
    # thirdeye_strategy_algo (1h): CCI length, fixed SL / TP from his realtime.py
    te_cci_length: int = 25
    te_sl_pct: float = 0.01
    te_tp_pct: float = 0.05
    thirdeye_ttl: tuple = (3600, 3600, 72 * 3600)
    # fibonachi_trading_system (1h)
    fib05_ttl: tuple = (3600, 3600, 72 * 3600)
    # bomberman_bot (1h)
    bomberman_ttl: tuple = (3600, 3600, 48 * 3600)
    # bollinger_bands-with-clusters v6 (15m): BB(40, 1.5), RSI(96), CSI clusters, SL 0.4%, out after 3 bars
    csi_bb_period: int = 40
    csi_bb_std: float = 1.5
    csi_rsi_period: int = 96
    csi_rsi: float = 60.0
    csi_min_cluster: int = 3
    csi_bull_quant: float = 0.78
    csi_bear_quant: float = 0.22
    csi_sl_pct: float = 0.004
    csi_ttl: tuple = (900, 900, 3 * 900)
    # oi_trading_robot v7.4 (long only): OI +5% / 1h, price growth <= 0.5 x OI growth, OI 24h > price 24h; his
    # defaults SL 2%, TP 4% / 6%, a 3h cooldown per coin, the 15m structure filter off
    oi_1h_threshold: float = 5.0
    oi_price_ratio: float = 0.5
    oi_sl_pct: float = 0.02
    oi_tp_pcts: tuple = (0.04, 0.06)
    oi_cooldown_sec: int = 3 * 3600
    oi_structure_filter: bool = False
    oi_accum_ttl: tuple = (900, 900, 24 * 3600)


@dataclass(frozen=True)
class MarketConfig:
    """
    Market crowd of a setup: how many coins produced a directional setup of the same direction within
    cluster_window_sec (live: BTC swept a 15m high and six alts "swept" theirs in the same 5m candle - one market move,
    the alts' setups are its beta). Every confirmed setup stays a card (no limit on their number: the journal and the
    ML models learn from all of them); the crowd is journaled (`market_crowd`) and learned as a feature, stats.py
    splits Edge by it (>= cluster_min = a market move).
    """
    cluster_min: int = 5
    cluster_window_sec: int = 300


@dataclass(frozen=True)
class WebConfig:
    """Browser dashboard (webui.py), bound to localhost only."""
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8765
    open_browser: bool = True


@dataclass(frozen=True)
class RestConfig:
    """REST pacing. Binance futures: 2400 weight/min per IP, spot: 6000/min."""
    # Futures klines (limit 99) weigh 1 and openInterestHist 0, so 15 parallel symbols stay far below the limit
    baseline_concurrency: int = 40
    baseline_delay_sec: float = 0.05
    max_retries: int = 3
    # Proactive budget: stay below this share of the weight limit (read from X-MBX-USED-WEIGHT-1M); lower priorities
    # get a smaller share (priority 0 = candles/backfill, 1 = OI polling, 2 = journal outcomes / positioning ratios)
    budget_share: float = 0.7
    priority_shares: tuple = (1.0, 0.8, 0.55)
    futures_weight_limit: int = 2400
    spot_weight_limit: int = 6000
    # Top-trader position ratio (own limit 1000 requests / 5 min shared by all /futures/data endpoints)
    positioning_budget_per_5m: int = 500
    positioning_cache_sec: int = 300
    # Every other universe coin (journal features of all rows): ~150 coins x 3 calls = 450 per pass
    positioning_universe_sec: int = 300


@dataclass(frozen=True)
class WSConfig:
    max_concurrent_trades: int = 40
    reconnect_delay: float = 5.0
    max_reconnect_attempts: int = 10
    ping_interval: int = 20


@dataclass(frozen=True)
class VenuesConfig:
    """
    Extra exchanges that enrich the Binance universe (trades -> aggregated CVD / sweeps, liquidations, OI, funding).
    The universe itself stays the Binance USD-M top list; other venues are mapped onto it by base coin.
    """
    enabled: tuple = ('bybit', 'okx', 'hyperliquid', 'bitget', 'coinbase', 'bybit_spot')
    # Hyperliquid allows 1000 subscriptions: asset contexts for every coin, trades only for this many hot coins
    hyperliquid_trades_max: int = 150
    # Bitget: at most this many channels per connection (their recommendation is < 50)
    bitget_channels_per_connection: int = 45
    # Mapping sanity: a coin is dropped for a venue when its price differs from Binance by more than this
    max_price_deviation: float = 0.1
    # Per-second flow history: long for the big venues (1h windows), short for the rest
    flow_history_sec: int = 3600
    flow_history_short_sec: int = 900
    # Aggregated 15m flow columns are used by scoring once this many candles were accumulated live
    agg_min_candles: int = 20
    # ONE-VENUE anomaly: this share of the 5m net flow came from one venue while it moved the price
    one_venue_share: float = 0.8
    one_venue_min_usd: float = 250_000


@dataclass(frozen=True)
class RiskConfig:
    """
    Position sizing shown on an entered card (webui.sizing_view): information for the manual trader, never an order.
    - max leverage: the isolated-margin liquidation (about 1/L - maintenance away from the entry) stays at least
      liq_stop_margin x the stop distance away, so a gap through the stop is not a liquidation;
    - position size: only with account_usd > 0 (config.local.toml [risk]); notional so that the stop loses risk_pct of
      the account including the round-trip execution cost.
    """
    account_usd: float = 0.0
    risk_pct: float = 1.0
    liq_stop_margin: float = 1.5


@dataclass(frozen=True)
class NotifyConfig:
    """Optional notifications for a manual trader away from the screen (off by default)."""
    enabled: bool = False
    toast: bool = True
    telegram_token: str = ""
    telegram_chat_id: str = ""
    events: tuple = ('ENTRY', 'TP', 'SL', 'ZONE')


@dataclass(frozen=True)
class LoggingConfig:
    file: str = "scanner.log"
    max_bytes: int = 10 * 1024 * 1024
    backups: int = 5


@dataclass(frozen=True)
class JournalConfig:
    """Signal journal (journal.py) and outcome tracking."""
    db_path: str = "signals.db"
    # Same symbol + same setup is logged again only after this long
    cooldown_sec: int = 1800
    eval_interval_sec: int = 60
    # Rows evaluated per pass; one 1m-kline request fills every due horizon of a row (weight <= 2 each)
    max_evals_per_pass: int = 60
    # Stored with every row; stats.py compares only rows produced by the same signal logic
    logic_version: str = "eng-23"
    # Prices of the whole universe are snapshotted this often: the market baseline for Edge
    # 5 min: the nearest snapshot is at most 2.5 min off the signal's window (with 15 min the 15m-horizon Edge
    # baseline could be offset by ~7.5 min at each end)
    universe_snapshot_sec: int = 300
    # Round-trip trading cost used by stats.py for net R / returns (taker 0.05% per side)
    fee_round_trip: float = 0.001
    # Open cards / sweep histograms survive restarts here
    state_path: str = "scanner_state.json"


@dataclass(frozen=True)
class PretrainConfig:
    """pretrain.py: models trained on the Binance public archive before the bot starts (history.py)."""
    path: str = 'pretrained.pkl'
    # every labelled historical row with its P(edge) features and the prediction made BEFORE learning it
    dataset_path: str = 'pretrain_rows'      # a directory of parquet parts
    cache_dir: str = 'history_cache'
    months: int = 6
    min_volume_usd: float = 3_000_000       # every USDT perpetual above it (a larger sample than the live universe)
    workers: int = 3
    download_bytes_per_sec: float = 1_000_000
    # The bot re-runs pretrain.py by itself (a background process at below-normal priority, one worker: the machine
    # has little free memory) when pretrained.pkl is missing or older than this, and reloads the models when done
    auto_refresh_days: int = 7
    auto_workers: int = 1
    auto_bytes_per_sec: float = 300_000
    lock_path: str = 'pretrain.lock'
    log_path: str = 'pretrain.log'


@dataclass(frozen=True)
class ExecutorConfig:
    # BingX DEMO trading of every card that reaches ENTRY (executor.py; sandbox forced, never a real balance). Turned on
    # by an api_key / api_secret in config.local.toml ([executor], a trade-only key)
    enabled: bool = True
    api_key: str = ""
    api_secret: str = ""
    risk_pct: float = 1.0           # the stop costs this share of account_usd
    # Sizing base, not the demo balance: the demo holds ~330k VST, and 1% of that exceeded BingX's per-symbol position
    # limits (5-10k USDT on XRP / TRX at 20x). R is what is compared, so the base only has to be tradable
    account_usd: float = 10_000.0
    max_notional_usd: float = 4_000.0
    max_leverage: int = 20


@dataclass(frozen=True)
class RecorderConfig:
    # Live-only data (per-second flow of all venues, 500-level books, per-venue OI / funding) to Parquet: recorder.py
    enabled: bool = True
    root: str = os.path.join('data', 'recorder')
    # the disk filled up on 2026-09-30 (state saves failed): keep this many days, never write below this much free
    keep_days: int = 30
    min_free_gb: float = 5.0


@dataclass
class AppConfig:
    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)
    timeframe: TimeframeConfig = field(default_factory=TimeframeConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    ws: WSConfig = field(default_factory=WSConfig)
    tier0: Tier0Config = field(default_factory=Tier0Config)
    rest: RestConfig = field(default_factory=RestConfig)
    journal: JournalConfig = field(default_factory=JournalConfig)
    whales: WhaleConfig = field(default_factory=WhaleConfig)
    sweeps: SweepConfig = field(default_factory=SweepConfig)
    liquidations: LiquidationConfig = field(default_factory=LiquidationConfig)
    depth: DepthConfig = field(default_factory=DepthConfig)
    orderflow: OrderflowConfig = field(default_factory=OrderflowConfig)
    levels: LevelsConfig = field(default_factory=LevelsConfig)
    zones: ZonesConfig = field(default_factory=ZonesConfig)
    strategies: StrategiesConfig = field(default_factory=StrategiesConfig)
    pools: PoolsConfig = field(default_factory=PoolsConfig)
    market: MarketConfig = field(default_factory=MarketConfig)
    web: WebConfig = field(default_factory=WebConfig)
    positioning: PositioningConfig = field(default_factory=PositioningConfig)
    venues: VenuesConfig = field(default_factory=VenuesConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    ml: MLConfig = field(default_factory=MLConfig)
    pretrain: PretrainConfig = field(default_factory=PretrainConfig)
    recorder: RecorderConfig = field(default_factory=RecorderConfig)
    executor: ExecutorConfig = field(default_factory=ExecutorConfig)


LOCAL_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.local.toml')


def _coerce(section: str, key: str, current: Any, value: Any) -> Any:
    """Type-check one override against the default's type (lists become tuples, ints are accepted for floats)."""
    if isinstance(current, bool):
        if not isinstance(value, bool):
            raise ValueError(f"[{section}] {key}: expected true/false, got {value!r}")
        return value
    if isinstance(current, tuple):
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"[{section}] {key}: expected a list, got {value!r}")
        return tuple(value)
    if isinstance(current, float):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"[{section}] {key}: expected a number, got {value!r}")
        return float(value)
    if isinstance(current, int):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"[{section}] {key}: expected an integer, got {value!r}")
        return value
    if isinstance(current, str):
        if not isinstance(value, str):
            raise ValueError(f"[{section}] {key}: expected a string, got {value!r}")
        return value
    raise ValueError(f"[{section}] {key}: cannot be overridden")


def apply_overrides(config: AppConfig, overrides: Dict[str, Dict[str, Any]]) -> AppConfig:
    """Return `config` with `overrides` ({section: {key: value}}) applied; raises ValueError on unknown/wrong input."""
    for section, values in overrides.items():
        if not hasattr(config, section) or not isinstance(values, dict):
            raise ValueError(f"Unknown config section [{section}]")
        current = getattr(config, section)
        names = {f.name for f in dataclasses.fields(current)}
        changes = {}
        for key, value in values.items():
            if key not in names:
                raise ValueError(f"Unknown config key [{section}] {key}")
            changes[key] = _coerce(section, key, getattr(current, key), value)
        setattr(config, section, dataclasses.replace(current, **changes))
    return config


def load_overrides(config: AppConfig, path: str = LOCAL_CONFIG_PATH) -> AppConfig:
    if not os.path.exists(path):
        return config
    import tomllib
    with open(path, 'rb') as f:
        overrides = tomllib.load(f)
    apply_overrides(config, overrides)
    logger.info(f"Config overrides loaded from {path}: {', '.join(f'[{s}]' for s in overrides)}")
    return config


CONFIG = load_overrides(AppConfig())
