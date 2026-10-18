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
    max_pairs: int = 70           # pinned + the strategies' pools (was 150: the laptop's RAM / CPU / link)
    min_24h_quote_volume_usd: float = 10_000_000
    require_spot: bool = True
    min_futures_venues: int = 2          # of Bybit, OKX, Bitget, Hyperliquid
    min_listing_days: int = 9
    # eng-99 (the owner): small caps - $1-10M 24h volume, the most liquid smallcap_max of them, outside the complete-data
    # rule (no spot / other venues needed; listed >= min_listing_days, spread <= smallcap_max_spread). Only the
    # smallcap_strategies trade them (pools.allows); the demo risks smallcap_risk_mult of the usual risk on them
    smallcap_min_volume_usd: float = 1_000_000
    smallcap_max: int = 60
    smallcap_max_spread: float = 0.0
    smallcap_strategies: tuple = ('oi_build',)
    smallcap_risk_mult: float = 1.0       # eng-112: no source for halving - removed
    # eng-100: the market regime is BTC's 7-day return over its closed daily candles (time-series momentum is strongest
    # at the daily / weekly horizon in crypto - Liu & Tsyvinski, RFS 2021; altcoins carry beta > 1 to BTC): a trade
    # against the regime risks regime_against_mult of the usual risk. Replaces the 'btc_bias' / 'against_btc' vetoes.
    # The TradFi contracts (gold, silver, oil) are not BTC's market: exempt
    regime_days: int = 7
    regime_against_mult: float = 1.0      # eng-112: the sources size by volatility (Moskowitz-Ooi-Pedersen), not x0.5 against BTC - removed
    regime_exempt_bases: tuple = ('XAU', 'XAG', 'XPT', 'XPD', 'CL', 'BZ', 'COPPER')
    # eng-126: 0 = off - the spread is inside the measured book slippage (levels.BOOK_SLIP), priced into every R:R;
    # the 10 / 30 bp caps had no source
    max_spread: float = 0.0
    # Binance exchangeInfo `underlyingType` values to skip: tokenized stocks (US/HK/KR/CN) and pre-IPO shares.
    # They sit flat outside their exchange's trading hours and trip squeeze/flat-price phases.
    excluded_underlying_types: tuple = ('EQUITY', 'HK_EQUITY', 'KR_EQUITY', 'CN_EQUITY', 'PREMARKET', 'COMMODITY')
    # Tokenized gold / silver trade the metal, not crypto flows (PAXG / XAUT were flagged 'whales' on metal hedges)
    excluded_bases: tuple = ('PAXG', 'XAUT', 'XAU', 'XAG', 'XPT', 'XPD')
    # Pinned coins (the owner's, 2026-10-01): always in the universe and in EVERY strategy's pool, whatever the volume,
    # spot pair, venue count or the exclusions above say (XAU = Binance's gold TradFi perpetual: no spot pair, so the
    # strategies that require spot veto it 'no_data'). BNB / DOGE / HYPE added: the largest perpetual volumes after them
    pinned_bases: tuple = ('BTC', 'ETH', 'XAU', 'CL', 'XRP', 'SOL', 'SUI', 'BNB', 'DOGE', 'HYPE', 'XAG', 'BZ')
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
    rvol_anomaly_threshold: float = 4.0
    # Bollinger's squeeze: BandWidth at its lowest of ~6 months = 125 bars of the chart's timeframe (was 50, no source)
    bbw_squeeze_lookback: int = 125
    squeeze_recent: int = 12          # Bollinger method I: the squeeze within the last 12 15m candles (3h)
    # Squeeze = Bollinger width at most this multiple of its bbw_squeeze_lookback minimum
    bbw_squeeze_tolerance: float = 1.05
    oi_change_window: int = 12
    # Short OI window (15m candles) for the price/OI matrix checks in phases D and E: 4 = 1h
    oi_short_window: int = 4
    # Funding normalized to an 8h-equivalent rate (0.001 = 0.1%); Binance's neutral rate is +0.01% per 8h.
    # Extreme funding: from +0.1% (longs) / below -0.05% (shorts). Crowded = orderflow.crowded_funding_* (one place).
    # Ours: the neutral is Binance's +0.01%; the extremes are not symmetric around it (+0.09 / -0.06) - no source
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
    price_change_5m_threshold: float = 0.0   # eng-123: the 1% floor was ours - the measured z >= 6 alone
    # measured on the live journal (research/tier0_thresholds.md): an effect beyond the coin's usual 4h move only from
    # |z| >= 6 (was 4)
    price_z_threshold: float = 6.0
    oi_z_threshold: float = 6.0
    # the rules that flag an anomaly (the rest are journaled features): rvol / whales / venue measured x1.0
    flag_rules: tuple = ('price', 'oi', 'cluster', 'liq')
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
    tier2_min_age_sec: int = 60
    # Algos fire at :00/:15/:30/:45 (quarter-hour bursts, +30% volume): an RVOL-only trigger is ignored this long
    # after each quarter-hour boundary
    quarter_boundary_ignore_sec: int = 45
    # eng-89: RUSH rows (journal only): a 30 s burst of rush orders of at least rush_min_n and z >= rush_z against the
    # coin's previous hour, once per coin / side per rush_cooldown_sec
    rush_min_n: int = 5
    rush_z: float = 10.0          # eng-98: 6 logged ~90 rows an hour, 81% of them z 6-10 (the liquid coins' background)
    rush_cooldown_sec: int = 600


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
    # USD sizes by 24h-volume rank used ONLY until a coin has min_samples sweeps (eng-57; were floors under the measured
    # p99.5 - hand-set numbers overriding the coin's own distribution): top floor_top_n_1 coins, top floor_top_n_2, rest
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
    # $10-200k in 5 minutes measured x0.90 (nothing), >= $200k x1.20 (research/tier0_thresholds.md; was $50k)
    cascade_min_usd: float = 200_000


@dataclass(frozen=True)
class DepthConfig:
    """
    Local order books (Binance <sym>@depth@500ms diff stream + a 1000-level snapshot, depth.py) of the hot symbols
    only: open cards and active anomalies. Measured 2026-10-05: ~4.3 KB/s per book (depth20 was ~2 KB/s).
    """
    max_symbols: int = 25          # (was 40: the laptop; pinned + open cards first)
    # Sockets the books are spread over (one socket carries ~40-70 KB/s)
    sockets: int = 6
    band_pcts: tuple = (0.005, 0.01)
    # A wall: a single level >= wall_multiple x the median level notional within +-wall_range_pct, counted after it
    # stood wall_min_age_sec (book depth refills within 5-10s of a trade: a 10s-old level said little)
    wall_multiple: float = 5.0
    wall_range_pct: float = 0.02
    wall_min_age_sec: float = 30.0
    # eng-105: a wall is no market maker's quote at the touch (2026-10-14: BTC's 'bid wall' sat $12 under the mid, the
    # top levels are always the largest) - at least wall_min_dist_pct from the mid and outside the best wall_skip_levels
    wall_min_dist_pct: float = 0.0015
    wall_skip_levels: int = 10
    # Diff streams push on change: a book is stale after this long without an event
    stale_sec: int = 60
    # Heatmap: the whole local book within +-heat_range_pct, bucketed by heat_bucket_pct of price, every
    # heat_snapshot_sec, heat_snapshots kept (2h); a bucket is a liquidity band when it held >= heat_band_multiple x the
    # snapshot's median bucket in >= heat_band_presence of the snapshots of heat_band_window_sec (at least
    # heat_band_min_snapshots) and was not mostly pulled (depth._bands)
    heat_bucket_pct: float = 0.001
    heat_range_pct: float = 0.05
    heat_snapshot_sec: float = 30.0
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
    # Binance's funding formula: F = 0.01% while the premium is within [-0.04%, +0.06%] (eng-52)
    crowded_premium_long: float = 0.0006
    crowded_premium_short: float = 0.0004
    crowded_oi_1h: float = 0.005
    # Footprint price bucket as a share of the 15m ATR, diagonal imbalance ratio and consecutive levels
    # footprint price bucket of every coin: 5 bps (~0.05 x the 15m ATR of a mid-volatility coin)
    footprint_bucket_pct: float = 0.0005
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
    required_confirmations: tuple = ()
    # strategies whose source has no confirmation rule: min_confirmations does not apply (the Turtles: eng-31)
    confirm_exempt: tuple = ('breakout',)
    # A confirmation becomes required for a strategy once its entries WITHOUT it have >= promote_min_clusters
    # independent results (15m clusters) and a 90% interval of the 4h Edge entirely below 0 (journal, hourly)
    promote_confirmations: bool = True
    promote_min_clusters: int = 30
    # an entry needs at least this many positive confirmations (flow / spot / oi / orderflow); 0 = off
    # eng-58: 0 (was 1) - one positive of five ~50/50 readings passes ~95% of entries: a filter in name only, set from
    # one bucket (0 of 4: -0.44R on 67 entries). Confirmations stay journaled; vetoes_table / features_table judge them
    min_confirmations: int = 0


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
    # the MOST clusters tried: the number is chosen by BIC over 2 .. this (eng-57; was a fixed 4)
    regime_clusters: int = 6
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
    rule_fdr: float = 0.05           # eng-125: Benjamini & Hochberg (1995) use q = 0.05; 0.10 had no source
    # P(edge): shown on cards once trained on this many labelled rows; shadow mode (never filters)
    success_enabled: bool = True
    success_min_trained: int = 300


@dataclass(frozen=True)
class LevelsConfig:
    """Two-timeframe model (levels.py): 15m impulse + Fibonacci context, 5m structure-shift entry. Rules, not advice."""
    # HTF impulse: largest leg of the last N 15m candles, >= impulse_min_atr ATR and >= impulse_min_candles long
    htf_lookback_candles: int = 48          # 12h: where the leg's END is searched
    # The leg's START is searched back over 1h history up to this far (a move of hours / days is measured whole)
    leg_lookback_hours: int = 96
    # eng-57: derived, not chosen - a reversal's first target is 0.382 of its leg and must pay >= 1 R over the stop
    # floor (min_stop_atr): leg >= min_stop_atr / 0.382 = 2.62 ATR (was the rounded 3.0). levels.min_leg_atr()
    impulse_min_atr: float = 0.0
    impulse_min_candles: int = 4            # 1h
    # ... and at least this big in price: at night ATR shrinks and a 0.5% drift can measure 7 ATR
    # eng-57: derived (levels.min_leg_move): the first target, 0.382 of the leg, must cover cost_guard x the round-trip
    # cost (fees + 2 x slippage at the reference liquidity, 0.2%): 3 x 0.2% / 0.382 = 1.57% (was the rounded 1.5%)
    impulse_min_move: float = 0.0
    # the risk must be at least this many round-trip costs (geometry; was a literal 3 in two places). Ours, eng-44:
    # 5x vetoed ordinary 2% stops; a source-less rule - the costs eat 1/3 of 1 R at the limit
    # eng-108 (the owner: no invented numbers): 1 = the break-even formula - the risk must at least cover one round trip of
    # costs (below it the costs exceed the risk); the 3 was source-less
    cost_guard: float = 1.0
    # Continuation: look for the trigger once the pullback reaches this retracement zone of the impulse
    # The pullback band of a continuation: 0.382-0.618 of the leg (a deeper retrace is a trend failure, not an entry);
    # the zone is a real map level inside it, else the EMA20 of the leg's timeframe (Raschke's "Holy Grail"
    # pullback); no level and no EMA20 inside: no card ('no_level'). Automated tests found no edge in Fibonacci
    # ratios themselves (ESWA 2021): a Fibonacci-only zone was a line with nothing behind it.
    continuation_zone: tuple = (0.62, 0.79)        # ICT OTE (was Raschke / Fibonacci 0.382-0.618)
    # a continuation card is INVALID once the pullback retraces deeper than this share of the leg (was the leg's start)
    continuation_invalid: float = 1.0              # ICT: beyond the impulse's start (was 0.786)
    # eng-112: the event-study window (10 min before .. 45 min after; Lund University FOMC study; Volmex 2024: BTC
    # volatility rises into CPI / FOMC and falls after) - was an invented 30 / 60
    macro_before_min: int = 10
    macro_after_min: int = 45
    # eng-100: this many minutes before a high-impact US release an open intraday trade in profit has its
    # stop at break-even + costs, one flat / in loss is closed at market (stops are run both ways in the first minutes);
    # the multi-day systems (Turtles, Connors) keep theirs
    macro_guard_min: int = 0         # eng-123: the open-trade guard has no source - off (the entry window stays)
    # audit (ICT OTE Primer 10:45-14:46, 37:49-38:03): the first take profit at the PRIOR HIGH (the impulse's end, 1.0
    # of the leg A->B from A), then the -27% / -62% extensions of that leg (1.272 / 1.618 from A); was C + k x leg from
    # the pullback (low 100 / high 120 / C 104.2: TP1 124.2 instead of 120) and an extra 1.2 no source names
    continuation_targets: tuple = (1.0, 1.272, 1.618)
    # Reversal: price must still be within this retracement of the reversed leg's end (accumulation: a bit wider)
    reversal_zone_max: float = 0.236
    # must stay below the first reversal target (0.382), or there is no room left for the trade
    reversal_targets: tuple = (0.382, 0.5, 0.618)
    # LTF trigger on ltf_minutes candles built from the 1m stream (15m -> 5m keeps the 3-5x step between timeframes
    # and leaves a human time to act): close beyond the high/low of the last ltf_break_lookback candles up to the
    # zone extreme, with net taker flow of the last ltf_flow_candles candles after that extreme in the trade's direction
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
    # eng-91: no trade whose stop is farther than this from the entry (the Turtles / Connors exempt; geometry.stop_too_far)
    # eng-108: removed (0 = off) - an invented 10%; the size is set by the stop, so a stop-out loses 1 R whatever its width
    max_stop_pct: float = 0.0
    # eng-69: the stop sits beyond its structure by max(measured pierce, this x ATR of the structure timeframe)
    # eng-113 (eng-69: "beyond the zone with a 3-5% margin" - on altcoins' 4h zones ~1.5 ATR of the
    # zone's timeframe): the stop sits beyond its structure by max(measured pierce, this x the structure tf's ATR)
    zone_buffer_atr: float = 0.0     # eng-123: the sources: 'slightly beyond the distal line', no size - the measured pierce
    # Entries with R:R to TP1 below this are LOW RR: with veto_low_rr they are journaled as vetoed entries
    # (vetoed='low_rr') and the card keeps waiting, so the screen only shows entries worth taking by hand
    # 2:1, the practitioners' minimum for intraday trades (breakeven win rate 33% before costs); was 1.0
    # eng-112: the formula, not the practitioners' 2: a positive expectancy p x R:R - (1 - p) > 0; with no measured p
    # (geometry.HIT_RATE) p = 0.5 -> R:R > 1 net of costs. A method's own minimum from its source stays (Strategy.min_rr)
    min_rr_tp1: float = 1.0
    veto_low_rr: bool = True
    # Manual execution: the journal replays entries filled this long after the trigger, plus slippage
    fill_delay_sec: int = 30
    slippage_bps: float = 5.0
    # Slippage grows as liquidity falls (square-root impact): slippage_bps x sqrt(slippage_ref_volume / 24h volume),
    # between slippage_bps and slippage_max_bps. A hypothesis, not a measurement: 5 bps for BTC and a $10M coin alike
    # understated the cost of the small ones (spreads up to 10 bps, thin books in cascades)
    slippage_ref_volume: float = 500e6
    slippage_max_bps: float = 25.0
    # eng-71: the square-root impact law (Toth et al. 2011, Almgren): half the spread + Y x daily sigma x sqrt(Q / V)
    # for an order of Q USD in a market trading V USD a day (Y ~ 0.5-1, sigma ~ 4% for crypto) - the old 5 x
    # sqrt($500M / V) ignored the order size and put a $10k order on a $20M coin at 25 bps a side (true ~5 bps),
    # inflating every plan's cost (low_rr / cost guard). Used where the 24h volume is known.
    slippage_notional_usd: float = 10_000.0
    slippage_half_spread_bps: float = 1.0
    slippage_impact_sigma: float = 0.04
    # A target (a resting limit order) counts as filled in the journal's replay only once price traded this far
    # THROUGH it: a touch fills only part of the queue (backtests that fill limits on a touch overstate the result)
    target_through_bps: float = 2.0
    # Spring "test": average 1m volume of the pullback <= this share of the spring candle's average minute
    spring_test_volume_ratio: float = 1.0    # eng-119: the source's 'lower volume' (the 0.6 was ours)
    # eng-55 Wyckoff's test also NARROWS the spread (StockCharts Wyckoff tutorial, tradingwyckoff: ranges 40-70%
    # smaller than the spring's): the pullback's average 15m range <= this x the spring candle's range scaled to 15m
    spring_test_spread_ratio: float = 0.6
    # audit A04, the data-quality policy of a bucket INSIDE a 1m history with minutes missing (a stream reconnect;
    # the 1m buffer is not backfilled): kept only when its first and last minute are there (open / close exact) and
    # >= this share of its minutes is (high / low / volume at most understated by the gap); otherwise dropped and
    # counted (levels.RESAMPLE_QUALITY). A partial LEADING bucket is always dropped
    resample_min_coverage: float = 0.8
    # Lifetimes: waiting for the pullback, waiting for the trigger inside the zone, managing the trade
    watch_ttl_sec: int = 6 * 3600
    # A new card waits this long for the coin's 1h history / level map before its first plan is taken anyway
    plan_wait_sec: int = 180
    zone_ttl_sec: int = 3 * 3600
    trade_ttl_sec: int = 8 * 3600
    # eng-48: the first third must earn at least this net R:R at TP1 (methods with a minimum R:R > 0): a blend let
    # TP1s 0.1-0.3% away pass on a TP3 13% away (BCH VA80 0.09, VIRTUAL -0.10 on 2026-10-02)
    # eng-86: off again. eng-85's 1.0 was reasoned, not measured: the laptop journal (30.09-11.10, 961 closed entries) had
    # rr_tp1 < 0.5 near zero (+0.07R) and >= 1.5 at -0.6..-0.74R - the floor kept the worse buckets
    min_rr_tp1_floor: float = 0.0
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
    swing_width_15m: int = 2         # eng-123: Bill Williams' 2/2 fractal (3 was ours)
    swing_width_1h: int = 2
    # Equal highs / lows (stop pools): >= 2 swings within this many ATR of each other
    equal_tolerance_atr: float = 0.15
    # Volume profile: price buckets per ATR, value area share, HVN = bucket volume >= this multiple of the median
    profile_buckets_per_atr: float = 4.0
    value_area: float = 0.7
    hvn_ratio: float = 2.0
    lvn_ratio: float = 0.6           # LVN: a profile valley <= this x the nodes on both sides
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
    # eng-74: a merged zone is at most this many ATR (the merge's ATR, 15m for the maps) wide, and a single level wider
    # than that (a big daily candle's order block / breaker: BTC's 83 786-90 320) is a zone of its own that absorbs
    # nothing - chaining through it made one zone of 86.5-93k and the briefing's trim then deleted it. A hypothesis
    # (no classic source gives a number; Murphy: zones, not prices) - to be measured like research_level_weights.py
    max_merge_atr: float = 6.0
    # Source weights; a zone's strength is the sum of its sources
    # liq_est 0.5 (was 1.5): the estimated liquidation model is unproven (forward test 2026-10-01: x1.37 the
    # liquidations of jittered placebo levels over 14h, within noise) - it may label a zone, not make one strong
    # eng-57 (research/level_weights.md, 60 coins x 12 months, placebo levels 0.3-1.5% away): swings 15m / 1h, equal
    # highs / lows, previous day high / low and round numbers all hold price LESS often than a random price nearby
    # (odds ratio 0.78-0.87, both halves) and alike - so they weigh the same, 1.0 (were 1.0 / 1.5 / 2.0 / 2.0 / 1.0,
    # set by hand). Extended: FVG 15m / 1h (0.83 / 0.90), order blocks 1h (0.94) and breakers 1h (0.83) hold worse
    # than random too, the day's volume profile POC / VA / HVN / LVN exactly like random (0.98-1.02) -> all 1.0 (were
    # 0.5-1.5). ob_15m / breaker_15m set to 1.0 with them. Still unmeasured hand-set values: the 4h / daily / weekly
    # ICT zones, vwap, fib, range, book, wall, liquidations, opens, htf, swing_1d, bpr.
    weights: tuple = (('swing_1h', 1.0), ('swing_15m', 1.0), ('equal', 1.0), ('pdhl', 1.0), ('poc', 1.0),
                      ('va', 1.0), ('hvn', 1.0), ('liq_est', 0.5), ('liq_hit', 1.0), ('wall', 1.0),
                      ('vwap', 1.0), ('fib', 0.5), ('range', 1.5), ('liq_hl', 2.0), ('book', 1.0), ('round', 1.0),
                      ('swing_1d', 2.5), ('htf', 2.5), ('lvn', 1.0),
                      # eng-70: weekly swings, the previous month's / 52-week extremes (unmeasured, as swing_1d)
                      ('swing_1w', 3.0), ('pmhl', 2.5), ('year', 3.0),
                      # ICT zones: 15m / 1h measured (no hold beyond random, weight 1); the 4h / daily / weekly
                      # scaling is an UNMEASURED hypothesis (research/level_weights.md covers 15m / 1h only)
                      ('fvg_15m', 1.0), ('fvg_1h', 1.0), ('fvg_4h', 1.5), ('fvg_1d', 2.5),
                      ('ob_15m', 1.0), ('ob_1h', 1.0), ('ob_4h', 2.0), ('ob_1d', 3.0),
                      ('breaker_15m', 1.0), ('breaker_1h', 1.0), ('breaker_4h', 2.0), ('breaker_1d', 3.0),
                      ('fvg_1w', 3.5), ('ob_1w', 4.0), ('breaker_1w', 4.0), ('open', 1.0),
                      ('bpr_1h', 1.5), ('bpr_4h', 2.5))
    # Round-number levels / pools within this many ATR of price (zones.round_levels)
    round_span_atr: float = 3.0
    # Targets: a zone must be at least this strong to be an obstacle (TP1/TP2); TP3 prefers pools / liquidations
    min_strength: float = 2.5
    min_target_atr: float = 0.0      # eng-121: no 1-ATR spacing of ours - the R:R formula judges a near target
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
    the strategy's journaled entries of the last lookback_days are proven negative (eng-59: block bootstrap + BH) (walk-
    forward on the archive: the worst coins of the last 6 months stayed the worst the next month, -0.39R vs -0.10R;
    picking the best ones did not help), capped at `size` coins by 24h volume. Setups outside the pool are journaled
    with vetoed='not_in_pool'.
    """
    enabled: bool = True
    # every universe coin (70) minus the ones a strategy's journal proved losing: the per-method top-20 (eng-29) was a
    # guess, and it vetoed the setups of the coins that moved (live 2026-10-01: MEGA's M-top, JASMY's breakout and
    # sweep 'not_in_pool'); on the archive only the EXCLUSION of the worst coins helped, picking the 'best' did not
    size: int = 999
    refresh_sec: int = 3600
    lookback_days: int = 90
    # eng-59: a coin is excluded once its entries are PROVEN negative over >= min_blocks 4h blocks (block bootstrap
    # + Benjamini-Hochberg at CONFIG.ml.rule_fdr, journal.proven_negative); was mean <= -0.3R over 8 entries
    min_blocks: int = 8
    # (strategy, classes 'major,large,mid,small' or 'all', sectors to exclude (sectors.py names), min ATR(1h) in %)
    # (+ the order the rest is picked in: 'volume' / 'volatility' / 'alts', see pools.Pools.rebuild). The pinned coins
    # (CONFIG.exchange.pinned_bases) are in every pool on top of `size`. A hypothesis per method, not a measurement:
    # the journal's per-coin exclusion still applies to the rest.
    # eng-48, by the methods' sources: Connors' mean reversion was built on liquid indices / large caps (major,
    # large); Crabel's ORB and Dalton's profile need a session with real volume (up to mid); pumps are a small-cap
    # event (mid, small); the Turtles diversified over everything; the rest name no asset class
    # eng-58: ICT's models (sweep / Silver Bullet, continuation, PO3) on liquid coins only - in crypto they are applied
    # to BTC / ETH and liquid majors; thin books turn every wick into a 'raid'
    rules: tuple = (('continuation', 'major,large,mid', '', 0.0, 'volatility'), ('breakout', 'all', '', 0.0, 'volatility'),
                    ('orb', 'all', '', 0.0, 'volume'), ('trendline', 'all', '', 0.0, 'volatility'),
                    ('market_profile', 'all', '', 0.0, 'volume'),
                    ('connors', 'all', '', 0.0, 'volume'),
                    ('bollinger', 'all', '', 0.0, 'volume'), ('wyckoff', 'all', '', 0.0, 'volume'),
                    ('sweep', 'major,large,mid', '', 0.0, 'volume'), ('supply_demand', 'all', '', 0.0, 'volume'),
                    ('pump', 'all', '', 0.0, 'volatility'), ('cup_handle', 'all', '', 0.0, 'volume'),
                    ('po3', 'major,large,mid', '', 0.0, 'volume'))


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
    enabled: tuple = ('continuation', 'wyckoff', 'sweep', 'breakout', 'supply_demand', 'market_profile',
                      'trendline', 'bollinger', 'orb', 'connors', 'pump', 'cup_handle', 'po3', 'oi_build')
    # BULL E buys the selling climax: Wyckoff reads the climax as the START of a trading range and buys later (the
    # spring's test: wyckoff_range); journaled, no card
    # BULL A (squeeze + tight range + OI) buys a squeeze BEFORE it breaks: Bollinger waits for the break (the direction
    # is unknown, a head fake comes first) and it is no Wyckoff phase - journaled, no card (eng-30, classic rule)
    # eng-55 PUMP TOP: a short against the pump at its first turn - the archive's FADE (-0.08R on 560 trades
    # Apr-Sep 2026, -0.19R on 60%+ pumps, negative in every period and split): journaled, no card
    # eng-83 ORB UP / DOWN: Crabel's ORB lost net of costs on 14 months of Binance 15m / 5m (research/exit_bt):
    # the bot's daily-open variant -0.07R on 9.4k holdout trades (43 coins), no exit rule fixed it (breakeven,
    # chandelier 3/6 ATR, 2R target, partials, 8h); session opens (Asia / London / NY, 15-120m ranges, Stretch or wide
    # 0.5-1 daily ATR stops) negative after 0.20% too; the only gross edge (majors, London / NY) is 0.05-0.1% a trade,
    # below the costs: journaled, no card
    # eng-88: OI SIGNAL LONG and PUMP START off - after the signal the coin lagged the market by 0.8% at 15 minutes and
    # 1.5-2.4% at 1-2h, in rising and falling markets alike (minute marks 11-13.10), and lost on the demo
    # eng-101, shadow mode: filters / detector confirmations with no proven effect on either journal (server
    # 11-14.10, laptop 30.09-11.10) no longer block - the entry is taken and journaled with shadow_veto = the
    # reasons that WOULD have vetoed it, so card_r of shadowed vs clean entries measures each rule on live trades.
    # Kept blocking: crowded, same_leg, low_rr, macro_event, event_risk, perp_led, killzone / session, disabled.
    shadow_vetoes: tuple = ('against_bias', 'against_trend', 'not_in_pool', 'h4_against', 'regime_flat',
                            'regime_trend', 'alts_vs_btc', 'profile', 'regime', 'no_confirmation',
                            # eng-138: the filters by name (was the pattern 'no_*', which also put a setup's own
                            # required parts - Wyckoff's spring test 'no_spring_test' - in shadow: springs without
                            # their test were traded)
                            'no_bias', 'no_supply', 'no_demand', 'no_orderflow', 'no_oi', 'no_level', 'no_htf_poi',
                            '<confirmations>',     # every missing entry confirmation (confirm.required_names)
                            'htf_bias', 'htf_conflict', 'rg_breakout_in_range', 'rg_countertrend',
                            'killzone', 'no_htf_poi', 'premium', 'discount', 'perp_led', 'low_rvol', 'against_vwap', 'btc_against', 'against_htf', 'against_day')
    disabled_setups: tuple = ('BULL E', 'BULL A', 'PUMP TOP', 'PUMP START',
                             # eng-127: the setups switched off in eng-109 for invented thresholds are rewritten from
                             # their sources or deleted - Seiden's odds enhancers (SD), the failed auction (AUCTION),
                             # Bollinger's Method I (BB1, replaces BULL F / BEAR D), Connors without a stop at 1x,
                             # the Turtles as written; Pring's OI rule and the cascades in shadow; the ATR-line bot
                             # and the OI robots deleted
                             )
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
    recent_atr_candles: int = 14     # eng-121: = Wilder's ATR14 (the 4-candle 'recent ATR' was ours)
    # Liquidity sweep (ICT / SMC: pools of the higher timeframes, swept by a 15m candle, entry on 5m). Pools: intact
    # 1h swings of the last sweep_swing_hours, equal highs / lows, previous day / week high-low, the day's high-low
    # and the last completed sessions (UTC hours), each at least sweep_pool_min_age_sec old and not traded through
    # since it formed. The sweep: a closed 15m candle pierces a pool by sweep_min_depth_atr-sweep_max_depth_atr and
    # closes back beyond it on >= sweep_min_rvol x the average 15m volume. Against the coin's 1h trend it is vetoed
    # ('against_trend'): live, sweeps of highs in a rising market lost -0.35R a trade, sweeps of lows +0.36R
    sweep_swing_hours: int = 100_000  # eng-121: every intact swing of the 1h history (a pool lives until traded through; 72h was ours)
    sweep_pool_min_age_sec: int = 0          # eng-108: removed (invented 1h); the pool only has to exist before the sweep
    # round numbers as the swept pool: 39 of 77 sweep INVALIDs (eng-125..128) were 'beyond the extreme at round N'; the
    # round-number study found clustering at round prices but no reliable return after them (Urquhart 2017, Economics
    # Letters 159) - rounds stay on the level map (targets / stops), not as the pool a sweep reverses from
    sweep_round_pools: bool = False
    # Bulkowski's measure rule for the cup with handle: the share of the right-lip-to-valley depth added to the breakout
    # (his 'percentage meeting price target', bullish cups in a bull market: 61% of 913, thepatternsite.com/cup.html)
    cup_target_share: float = 0.61
    sweep_min_depth_atr: float = 0.1
    sweep_max_depth_atr: float = 1.0
    sweep_min_rvol: float = 0.0              # eng-108: removed (invented; the sources' sweep has no volume rule) - journaled
    # the exchanges' local hours, daylight saving included (forex session tables; eng-57: were fixed UTC 0-8 / 7-16 / 13-21)
    sweep_sessions: tuple = (('Asia', 'Asia/Tokyo', 9, 18), ('London', 'Europe/London', 8, 17),
                             ('New York', 'America/New_York', 8, 17))
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
    # Liquidation exhaustion (cascades overshoot mechanically; revert once the forced flow stops): a cascade
    # (liquidations.cascade_*) of longs on a drop / shorts on a rally; the leg runs from the extreme of the
    # exhaustion_pre_minutes before it to the cascade's extreme (following price until the entry), >= 3 ATR (a
    # reversal's first target 0.382 of the leg must pay 1R over the >= 1 ATR stop); entry: a 5m structure shift
    exhaustion_pre_minutes: int = 30
    exhaustion_min_leg_atr: float = 0.0          # eng-57: derived, levels.min_leg_atr() (was 3.0)
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
    breakout_ttl: tuple = (3600, 3600, 90 * 86400)   # Turtles: entered at once, out on the trailing channel
    # ---- crypto_maniac's systems (github.com/roman-boop; strategies/maniac.py): his parameters as he ships them.
    # Longer histories they need: 15m / 1h candles of every coin (fetcher._hourly_candles_loop, limit 499 = weight 2)
    long_history_candles: int = 499
    # eng-127: supply / demand by Seiden / OTA's odds enhancers (strategies/maniac.sd_zone_events), no thresholds
    sd_ttl: tuple = (7 * 86400, 86400, 3 * 86400)   # 4h zones (Seiden: 4h or higher) live a week
    # classic methods (strategies/classic.py): entered at the signal's close; the trade lives a session
    classic_ttl: tuple = (3600, 3600, 12 * 3600)
    silver_bullet_ttl: tuple = (3600, 3600, 4 * 3600)
    po3_ttl: tuple = (3 * 3600, 3 * 3600, 12 * 3600)   # eng-58: the London window, the trade into New York
    # pumps (strategies/pump.py): the start = +15m >= max(min %, z x the coin's 15m volatility) on RVOL, OI and spot
    # buying at a fresh 24h high; the top = a buying climax after >= pump_top_min_pct within 4h
    pump_start_min_pct: float = 0.03
    pump_start_z: float = 4.0
    pump_start_rvol: float = 5.0
    pump_top_min_pct: float = 0.10
    pump_ttl: tuple = (3600, 3600, 12 * 3600)
    cup_ttl: tuple = (86400, 86400, 60 * 86400)     # eng-58: daily bases; O'Neil holds breakouts for weeks
    # daily RSI(2): out at the SMA5 (Connors); eng-58: no 10-day exit (no source found for it) - a 60-day safety cap
    connors_ttl: tuple = (3600, 3600, 60 * 86400)
    # Time exits (eng-47; Strategy.time_exit): a trade that has not reached TP1 within time_stop_bars bars of its
    # structure timeframe failed to work (Kaufman / Le Beau's time stop: 15m 6h, 1h 24h, 4h 4 days, at least
    # time_stop_min_sec); once TP1 traded the rest may run time_after_tp1 x as long. A flat 12h clock closed working
    # trades on the way to TP2 / TP3 (ALICE, MOVE 2026-10-02) and kept dead ones open for hours.
    # eng-108 (the owner: no invented numbers): cards and trades end STRUCTURALLY - a waiting card by its invalidation,
    # TP1 traded before an entry, its session / kill zone end or no plan; a trade by its stop, targets, break-even /
    # trail and the method's exit. The watch / zone / trade clocks and the time stop below are then unused
    structural_lifetimes: bool = True
    # eng-111: no source -> off (break-even after +1R; the EMA20 trail after TP1)
    be_after_1r: bool = False
    ema_trail_after_tp1: bool = False
    time_stop_bars: int = 24
    # eng-51: at most crowd_max OPEN trades in one direction across all strategies (the rest journaled vetoed
    # 'crowded'). The Turtles allowed 6 units in closely correlated markets (Faith, Original Turtle Rules); alts move
    # with BTC as one market - 12 Silver Bullet longs on 2026-10-02 were one bet. Turtle units counted by the
    # Turtles' own 12-unit limit, not here
    crowd_max: int = 6
    # eng-128: the data-mined layers (models/profiles.json, profiles_regime.json: research_optimize's filters, stops,
    # break-even, time stops, the 'regime_off' veto; models/exit_overlays.json: research_overlays' early exits and the
    # alts_with filter) have no source - fitted on the archive, several negative on their own validation: off
    optimized_profiles: bool = False
    time_after_tp1: float = 3.0
    time_stop_min_sec: int = 4 * 3600
    # The Turtles' units (strategies/turtle.py): +1 unit every turtle_add_n x N in favour, at most turtle_max_units per
    # coin and turtle_max_direction_units in one direction overall; a unit is turtle_unit_risk of the account per N
    # (1%: the 2N stop risks 2%). eng-55: 6 = the Turtles' limit for CLOSELY correlated markets (Faith: 4 per market,
    # 6 closely / 10 loosely correlated, 12 per direction) - altcoins move with BTC at 0.6-0.9, one cluster
    turtle_add_n: float = 0.5
    turtle_max_units: int = 4
    turtle_max_direction_units: int = 6
    turtle_unit_risk: float = 0.01
    # eng-55 Crabel's ORB as his book defines it (Oxfordstrat; Crabel's pattern definitions): stop orders at the day's
    # open +- the Stretch (the 10-day SMA of min(High - Open, Open - Low) of the daily candles); the first one hit is
    # the trade, the other its stop; out at the session's (UTC day's) close. Crypto's daily candle opens 00:00 UTC.
    orb_stretch_days: int = 10
    # eng-93, the owner (2026-10-12/14: "ORB is a stock strategy - only the majors"; "the majors, gold, silver, oil,
    # split by sessions"): the session ORB trades only these, each session's open (strategies.classic.ORB_SESSIONS)
    orb_bases: tuple = ('BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'XAU', 'XAG', 'CL', 'BZ')
    # Connors' RSI(2) levels (eng-58: 5 / 95, his original rule; 10 / 90 is a later variant)
    connors_rsi_low: float = 5.0
    connors_rsi_high: float = 95.0
    # eng-55: Connors uses no stop. A perpetual with leverage needs one for the margin: a CATASTROPHIC stop this many
    # daily ATR(20) away, journaled as our deviation (it is not part of his exit)
    # eng-55 dump bounce (research/pumps*.md, positive in every period 2021-2026): a DUMP = close >= dump_min_move
    # below the 6h high on >= 3x the hour's volume of the week before; short the first 38.2-61.8% bounce on a 1h close
    # below the previous low; stop above the bounce + 0.25 ATR(1h); TP1 the dump's low, TP2 the 1.618 extension
    dump_min_move: float = 0.15
    dump_vol_x: float = 3.0
    # eng-57 wide watch: perpetuals outside the universe above this 24h volume (pretraining's floor, research_pumps)
    wide_min_volume: float = 3_000_000
    # eng-127: OI build = Pring's rule (strategies/oi_build.py, shadow); the OI robots' thresholds are deleted
    oi_build_ttl: tuple = (900, 900, 4 * 3600)
    # ICT optimal trade entry for the continuations (trend / momentum): the pullback into 0.62-0.79 of a leg that left
    # a fair value gap (displacement); invalid beyond the leg's start (ICT: "past the 100% level")
    require_displacement: bool = True
    # eng-127: AUCTION = the failed auction (strategies/classic.failed_auction_event); the ported engine is deleted
    # lllll SMT / Quasimodo (15m main + 5m entry): the correlate is BTC (ETH for BTC itself); require_if_available;
    # the 5m inversion FVG within 8 main bars; entries only 02:00-10:00 New York (his session; () = any time)
    smt_main_bars: int = 500
    smt_with_trend_only: bool = False
    smt_ref_window: int = 60
    smt_ifvg_min_atr: float = 0.03
    smt_ifvg_search_back: int = 40
    # ICT kill zones (New York time): London open 02:00-05:00 and New York open 07:00-10:00 (not one 02-10 window)
    smt_session: tuple = ('America/New_York', '02:00', '05:00', '07:00', '10:00')
    # SMT only against a pair at least this correlated (15m returns, 200 candles): the method's precondition
    smt_min_correlation: float = 0.7
    # trendline_bot (15m, sloped lines only)
    tl_lookback: int = 400
    tl_pivot: int = 3
    tl_min_span: int = 40
    tl_min_touches: int = 3
    tl_touch_atr: float = 0.25
    tl_touch_gap: int = 5
    tl_violation_atr: float = 0.10
    tl_max_dist_atr: float = 3.0
    # eng-57: 0 (was 7.5, his 15m bot's cut): on 1h a line spanning 40+ candles is gentler than 0.13 ATR a candle, so
    # 7.5 degrees left no line at all - 0 events on 20 coins x 250 hours, 9 without it. Steep lines stay out (tl_max_deg)
    tl_flat_deg: float = 0.0
    tl_min_pivot_touches: int = 3
    tl_pivot_tol_atr: float = 0.20
    tl_max_deg: float = 35.0
    tl_last_touch_age: int = 40
    tl_confirm_atr: float = 0.15
    tl_min_body_atr: float = 0.35
    tl_max_depth_atr: float = 1.2
    tl_close_pos_max: float = 0.40
    trendline_ttl: tuple = (24 * 3600, 24 * 3600, 48 * 3600)   # 1h lines; eng-58: a day for the retest
    bollinger_ttl: tuple = (4 * 3600, 4 * 3600, 3 * 86400)   # eng-84: W / M on 4h - the trade lives days


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
    ping_interval: int = 20
    # eng-81: Binance's whole-market arrays (!markPrice@arr@1s, !miniTicker@arr) as streams - off on a thin link
    market_arrays: bool = True


@dataclass(frozen=True)
class VenuesConfig:
    """
    Extra exchanges that enrich the Binance universe (trades -> aggregated CVD / sweeps, liquidations, OI, funding).
    The universe itself stays the Binance USD-M top list; other venues are mapped onto it by base coin.
    """
    enabled: tuple = ('bybit', 'okx', 'hyperliquid', 'bitget', 'coinbase', 'bybit_spot')
    # Hyperliquid allows 1000 subscriptions: asset contexts for every coin, trades only for this many hot coins
    hyperliquid_trades_max: int = 70   # = the universe (max_pairs)
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
    enabled: bool = True
    toast: bool = False
    telegram_token: str = ""
    telegram_chat_id: str = ""
    # A forum supergroup next to the channel (2026-10-12): every message also goes to its topic's thread there;
    # 'service' messages (feeds down, component errors) go ONLY to the group. Empty group id = channel only.
    group_chat_id: str = ""
    topic_briefing: int = 0       # briefings, cards, recap, macro reminders
    topic_signals: int = 0        # card events: ENTRY / TP / SL / CLOSED / RESTOP / ADD
    topic_alerts: int = 0         # zone reactions / breaks, 15m shocks, bias changes, anomalies
    topic_demo: int = 0           # BingX demo fills / exits / risk stop
    topic_service: int = 0        # feeds down, component errors
    # the owner: no 'in the zone, waiting for the trigger' messages - only what happened to a trade
    events: tuple = ('ENTRY', 'TP', 'SL', 'CLOSED', 'RESTOP', 'ADD')
    # the owner's token / channel from the environment (TELEGRAM_BOT_TOKEN / TELEGRAM_CHANNEL_ID) when these are empty


@dataclass(frozen=True)
class BriefingConfig:
    """Telegram briefings / watch alerts (briefing.py) for the coins that lead the market (the owner, 2026-10-05)."""
    enabled: bool = True
    coins: tuple = ('BTC', 'ETH', 'XAU')          # the owner 2026-10-07: forecasts only for these three
    # (HH:MM Moscow, title): before the Tokyo (03:00 MSK), London (10:00 MSK) and New York cash (16:30 MSK) opens + recap
    schedule: tuple = (('02:30', 'Сводка перед Азией'), ('09:30', 'Сводка перед Лондоном'),
                       ('16:00', 'Сводка перед Нью-Йорком'), ('23:30', 'recap'))
    span_atr_1d: float = 5.0           # zones within this many daily ATRs of the price (3 resistances / 2 supports)
    shock_z: float = 4.0               # a 15m move of >= this x the coin's typical 15m move ...
    shock_min_pct: float = 0.012       # ... and >= 1.2%


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
    logic_version: str = "eng-141"
    # eng-87: WAITING cards of this logic version or later survive a restart under a newer logic_version (relabelled to
    # it): a bump that changes only trade management / execution / the journal no longer expires them (51 waiting cards
    # expired by the bumps of 11-13.10, 108 in the laptop journal). Raise it to the new logic_version whenever a bump
    # changes how a card is detected, planned or vetoed
    keep_waiting_from: str = "eng-139"
    # eng-58: strategies are judged over every logic version from this one on (57 versions in 8 days left no version
    # with 30 clusters: the verdict waited forever); card_r of rows before eng-58 was gross - stats.card_r_net nets it
    verdict_since: str = "eng-55"
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
    # the bot re-runs pretrain.py by itself (stale / other logic version); off while the logic is still changing
    auto: bool = True
    auto_refresh_days: int = 7
    auto_workers: int = 1
    auto_bytes_per_sec: float = 300_000
    lock_path: str = 'pretrain.lock'
    log_path: str = 'pretrain.log'


@dataclass(frozen=True)
class IcebergConfig:
    # iceberg.py: executed at one price >= multiple x the largest size ever shown there, >= min_usd, within window_sec
    # of the level's last execution, while nothing traded through it
    window_sec: int = 120
    multiple: float = 3.0
    min_usd: float = 50_000
    min_refills: int = 2           # book snapshots showing the level again after it was hit (a real refill)


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
    limit_wait_min: int = 15      # a touch plan's BingX limit kept this long after Binance's touch (eng-46)
    # eng-105: partial profit at +1R for every trade - partial_share of the position out at +partial_r R
    # (an exchange take-profit order, it fills between scans too); the rest keeps its stop (break-even + costs after
    # +1R) and the method's exit. Skipped where the plan's TP1 is already nearer than +1R (TP1 is the partial then).
    # eng-105: no resting limits - a touch of the zone only arms the entry; the trade opens at the CLOSE of
    # the trigger-timeframe candle that touched the zone and closed back on the trade's side of its line
    touch_confirm_close: bool = True
    partial_r: float = 1.0
    partial_share: float = 0.0       # eng-123: no study for half at +1R (practitioners' advice only) - off
    max_leverage: int = 5            # eng-84: 2-5x (the 3-5-7 rule); the risk is set by the stop, cross margin
    # eng-58, the account's day (prop firms: daily loss 1-5%, 2-3 trades a day, a pause after a streak). eng-125: the
    # numbers were picked inside those ranges, no source -> off (0); the risk per trade (1%, the Turtles' unit) stays
    daily_loss_r: float = 0.0
    max_trades_day: int = 0
    pause_losses: int = 0
    pause_hours: float = 0.0
    # audit-80: opt-in guards (0 = off, the owner's eng-125 decision stands until set in config.local.toml)
    strategy_kill_r: float = 0.0      # no new trades of a strategy whose last strategy_kill_n closed trades sum <= -this R
    strategy_kill_n: int = 30
    day_alert_r: float = 0.0          # a Telegram alert (not a block) once the UTC day's closed trades lost this many R
    daily_summary: bool = True        # per-strategy R of yesterday's demo trades to the demo topic at 00:05 UTC


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
    briefing: BriefingConfig = field(default_factory=BriefingConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    ml: MLConfig = field(default_factory=MLConfig)
    pretrain: PretrainConfig = field(default_factory=PretrainConfig)
    recorder: RecorderConfig = field(default_factory=RecorderConfig)
    executor: ExecutorConfig = field(default_factory=ExecutorConfig)
    iceberg: IcebergConfig = field(default_factory=IcebergConfig)


# EDGEHUNTER_CONFIG (legacy PUMP_CONFIG) points at another overrides file (a dev / test run beside the live bot, its own ports and switches)
LOCAL_CONFIG_PATH = os.environ.get('EDGEHUNTER_CONFIG') or os.environ.get('PUMP_CONFIG') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.local.toml')


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
