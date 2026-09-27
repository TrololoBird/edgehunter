import logging
import polars as pl
from typing import Dict, List, Optional, Tuple, Union
from config import CONFIG
from indicators import TIER0_COLUMNS

logger = logging.getLogger(__name__)

# Columns taken from the futures frame when a spot frame drives the price structure (renamed where both frames
# carry the column), funding is a per-symbol scalar already present on both frames
FUTURES_COLUMNS = {'oi_change_pct': 'oi_change_pct', 'oi_change_short': 'oi_change_short',
                   'oi_change_flat': 'oi_change_flat', 'rvol': 'rvol', 'oi_std': 'oi_std',
                   'delta_1h': 'fut_delta_1h', 'flow_1h': 'fut_flow_1h'}
# Per-symbol live extras joined onto the scored frame (scanner: aggregated multi-venue 15m flow)
EXTRA_COLUMNS = ('agg_fut_delta_1h', 'agg_spot_extra_1h', 'agg_ready')

PHASE_MAX = {'A': 4, 'B': 3, 'C': 5, 'D': 5, 'E': 7, 'F': 5}
# Phases per side: bullish A accumulation, B spring, E capitulation, F markup; bearish C distribution, D breakdown
LONG_PHASES, SHORT_PHASES = 'ABEF', 'CD'


class PhaseScorer:
    """
    Asymmetrical scoring of five market phases on CLOSED 15m candles, vectorized with pl.when().then().otherwise().
    Each condition adds points independently; long = A + B + E (bullish), short = C + D (bearish).

    The conditions follow the standard crypto order-flow reading:
    - price/OI matrix: price up + OI up = new longs (strong), price up + OI down = short covering (fades),
      price down + OI up = new shorts (strong), price down + OI down = long liquidation (exhaustion, near bottoms);
    - CVD: net taker selling absorbed while price is flat = accumulation, a new high on net taker selling =
      bearish divergence (distribution); spot-led flow is sturdier than perp-led flow;
    - funding: extreme positive = crowded longs, extreme negative = crowded shorts.
    The weights are hand-set hypotheses; the journal (stats.py) measures them live.
    All frames carry a 'symbol' column (see indicators.compute_indicators_batch), so one call scores every symbol.
    """

    def __init__(self):
        self.cfg = CONFIG.metrics
        self.sc = CONFIG.scoring

    def calculate_scores(
        self,
        spot_df: Optional[pl.DataFrame],
        futures_df: Optional[pl.DataFrame],
        tier0: Union[None, Dict[str, float], pl.DataFrame] = None,
        extras: Optional[pl.DataFrame] = None,
    ) -> pl.DataFrame:
        """
        Price/CVD structure comes from the spot frame (the futures frame for futures-only listings);
        OI, funding, RVOL and perp flow come from futures, as-of joined on (symbol, timestamp). `tier0` is one
        symbol's metrics (dict) or a frame with a 'symbol' column and TIER0_COLUMNS.
        """
        has_spot = spot_df is not None and not spot_df.is_empty()
        has_futures = futures_df is not None and not futures_df.is_empty()
        if not (has_spot or has_futures):
            return pl.DataFrame()

        fut_cols = {src: dst for src, dst in FUTURES_COLUMNS.items() if has_futures and src in futures_df.columns}
        if has_spot and has_futures:
            futures_only = futures_df.filter(~pl.col('symbol').is_in(spot_df['symbol'].unique().implode()))
            spot_base = spot_df.with_columns(pl.lit(True).alias('has_spot'))
            base = (pl.concat([spot_base, futures_only.with_columns(pl.lit(False).alias('has_spot'))], how='diagonal_relaxed')
                    if not futures_only.is_empty() else spot_base)
            # As-of join: the latest futures candle at or before each base candle, so a spot candle that opened a
            # moment before its futures twin (15m rollover, lagging stream) still gets OI / RVOL
            renamed = futures_df.select(['symbol', 'timestamp', *[pl.col(s).alias(d) for s, d in fut_cols.items()]])
            df = base.drop([d for d in fut_cols.values() if d in base.columns and d not in ('delta_1h', 'flow_1h')])
            df = df.join_asof(renamed, on='timestamp', by='symbol', strategy='backward', check_sortedness=False,
                              suffix='_fut')
        else:
            df = (spot_df if has_spot else futures_df).with_columns(pl.lit(has_spot).alias('has_spot'))
            if not has_spot:
                df = df.with_columns(pl.col('delta_1h').alias('fut_delta_1h'), pl.col('flow_1h').alias('fut_flow_1h'))

        needed = ['oi_change_pct', 'oi_change_short', 'oi_change_flat', 'rvol', 'fut_delta_1h', 'fut_flow_1h']
        missing = [c for c in needed if c not in df.columns]
        if missing:
            df = df.with_columns([pl.lit(0.0, dtype=pl.Float64).alias(c) for c in missing])

        df = self._join_live(df, tier0, extras)
        # Tier-0 flags first: phase E reads the liquidation-cascade flag
        df = self.flag_tier_0_anomaly(df)
        df = self._spot_perp(df)
        df = self._score_phase_a_accumulation(df)
        df = self._score_phase_b_spring(df)
        df = self._score_phase_c_distribution(df)
        df = self._score_phase_d_dump(df)
        df = self._score_phase_e_capitulation(df)
        df = self._score_phase_f_markup(df)
        return self._calculate_total_scores(df)

    @staticmethod
    def _join_live(df: pl.DataFrame, tier0, extras: Optional[pl.DataFrame]) -> pl.DataFrame:
        if isinstance(tier0, pl.DataFrame) and not tier0.is_empty():
            df = df.join(tier0, on='symbol', how='left', maintain_order='left')
        elif isinstance(tier0, dict) and tier0:
            # Tier-0 metrics are live scalars, broadcast onto every row like funding_rate
            df = df.with_columns([pl.lit(float(tier0.get(c, 0.0)), dtype=pl.Float64).alias(c) for c in TIER0_COLUMNS])
        if extras is not None and not extras.is_empty():
            df = df.join(extras, on='symbol', how='left', maintain_order='left')
        missing = [c for c in EXTRA_COLUMNS if c not in df.columns]
        if missing:
            df = df.with_columns([pl.lit(None, dtype=pl.Float64).alias(c) for c in missing])
        return df

    def _spot_perp(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Spot vs perp net flow over the last hour. Perp-led: the perp side drives the move while spot disagrees or
        barely participates (spot net flow < perp_led_spot_share of the perp net flow); such moves fade more often.
        The perp side uses the multi-venue aggregate once enough candles were accumulated (agg_ready).
        """
        share = CONFIG.orderflow.perp_led_spot_share
        agg = pl.col('agg_ready').fill_null(0) > 0
        # With the aggregate the spot side adds the other spot venues too, so both sides are on the same scale
        spot = (pl.when(pl.col('has_spot'))
                .then(pl.col('delta_1h') + pl.when(agg).then(pl.col('agg_spot_extra_1h').fill_null(0.0)).otherwise(0.0))
                .otherwise(None))
        perp = pl.when(agg).then(pl.col('agg_fut_delta_1h')).otherwise(pl.col('fut_delta_1h'))
        weak_spot = pl.col('spot_delta_1h').abs() < share * pl.col('perp_delta_1h').abs()
        df = df.with_columns(spot.alias('spot_delta_1h'), perp.alias('perp_delta_1h'))
        return df.with_columns(
            (pl.col('has_spot') & (pl.col('perp_delta_1h') > 0) & ((pl.col('spot_delta_1h') <= 0) | weak_spot))
            .fill_null(False).alias('perp_led_long'),
            (pl.col('has_spot') & (pl.col('perp_delta_1h') < 0) & ((pl.col('spot_delta_1h') >= 0) | weak_spot))
            .fill_null(False).alias('perp_led_short'),
        )

    def flag_tier_0_anomaly(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Tier-0: raw impulse, independent of Score and phases. Any single condition is enough:
        - RVOL_1m above the threshold on a minute of real size, except in the first seconds after a quarter-hour
          boundary (algo bursts);
        - |price 5m| / |OI 5m| above BOTH the absolute floor and the coin's own z-score threshold;
        - net whale sweeps >= whale_net_units; an algo cluster; a liquidation cascade;
        - ONE-VENUE: most of the 5m net flow came from a single venue while several are active.
        """
        t0 = CONFIG.tier0
        liq = CONFIG.liquidations
        venues = CONFIG.venues
        missing = [c for c in TIER0_COLUMNS if c not in df.columns]
        if missing:
            df = df.with_columns([pl.lit(0.0, dtype=pl.Float64).alias(c) for c in missing])
        df = df.with_columns([pl.col(c).fill_null(0.0) for c in TIER0_COLUMNS])

        rvol = ((pl.col('rvol_1m') > t0.rvol_1m_threshold) & (pl.col('minute_usd') >= t0.rvol_min_minute_usd) &
                (pl.col('sec_into_quarter') >= t0.quarter_boundary_ignore_sec))
        # z-scores are 0 while a coin's volatility is unknown (short history): then the absolute floor x2 decides
        price = (pl.col('price_change_5m').abs() > t0.price_change_5m_threshold) & (
            (pl.col('price_z').abs() >= t0.price_z_threshold) |
            ((pl.col('price_z') == 0) & (pl.col('price_change_5m').abs() > 2 * t0.price_change_5m_threshold)))
        oi = (pl.col('oi_change_5m').abs() > t0.oi_change_5m_threshold) & (
            (pl.col('oi_z').abs() >= t0.oi_z_threshold) |
            ((pl.col('oi_z') == 0) & (pl.col('oi_change_5m').abs() > 2 * t0.oi_change_5m_threshold)))
        liq_total = pl.col('liq_long_5m') + pl.col('liq_short_5m')
        cascade = (liq_total >= liq.cascade_min_usd) & (liq_total >= liq.cascade_avg_minute_share * pl.col('avg_minute_usd'))
        one_venue = ((pl.col('venues_active') >= 2) & (pl.col('top_venue_share') >= venues.one_venue_share) &
                     (pl.col('top_venue_net').abs() >= venues.one_venue_min_usd))
        whales = pl.col('whale_net_5m').abs() >= t0.whale_net_units
        cluster = pl.col('cluster') != 0
        rule = (rvol | price | oi | whales | cluster | cascade | one_venue).fill_null(False)
        # Once the IsolationForest is fitted it decides (an unusual COMBINATION of the coin's features); the
        # rules only label the event and serve as the fallback before the first fit
        ml = pl.col('ml_anomaly') > 0
        is_anomaly = pl.when(pl.col('ml_ready') > 0).then(ml).otherwise(rule).fill_null(False)
        return df.with_columns(
            is_anomaly.alias('is_tier_0_anomaly'), rule.alias('rule_anomaly'), cascade.fill_null(False).alias('liq_cascade'),
            # Which condition fired (logs / debugging): one boolean column per trigger
            *[c.fill_null(False).alias(f"t0_{name}") for name, c in (
                ('rvol', rvol), ('price', price), ('oi', oi), ('whales', whales), ('cluster', cluster),
                ('liq', cascade), ('venue', one_venue), ('ml', ml & (pl.col('ml_ready') > 0)))],
        )

    @staticmethod
    def _points(condition: pl.Expr, weight: int) -> pl.Expr:
        return pl.when(condition.fill_null(False)).then(weight).otherwise(0)

    def _score_phase_a_accumulation(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Phase A: accumulation (bullish) - a tight range where aggressive selling is absorbed by resting bids.
        - Bollinger width near its lookback minimum (squeeze) (+1)
        - Range over the window within flat_range_atr ATRs while taker SELLERS dominate its volume: the sells are
          absorbed, price does not break down (+2)
        - Futures OI growing over the same window while the range holds: positions built quietly (+1)
        """
        squeezed = pl.col('is_squeezed')
        tight = pl.col('flat_range') <= self.cfg.flat_range_atr * pl.col('atr')
        sells_absorbed = tight & (pl.col('flow_flat') <= -self.cfg.accumulation_flow_min)
        oi_building = tight & (pl.col('oi_change_flat') > 0)

        score = (
            self._points(squeezed, self.sc.accumulation_weight) +
            self._points(sells_absorbed, self.sc.cvd_rising_weight) +
            self._points(oi_building, self.sc.oi_rising_flat_price_weight)
        )
        return df.with_columns(
            score.alias('score_phase_a'),
            (squeezed & sells_absorbed & oi_building).fill_null(False).alias('phase_a_active'),
        )

    def _score_phase_b_spring(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Phase B: Wyckoff spring (bullish) - a shallow sweep below an established trading range that sellers could
        not hold.
        - The prior 20 candles form a range (high - low within spring_range_atr ATRs) that drifted sideways (net move
          <= spring_max_drift of that span), not a downtrend channel
        - The low pierces that range's low by at most spring_max_depth_atr ATRs and the candle closes back above it
        - Close in the top 30% of the candle on net taker selling: the sell stops were absorbed by bids
        Volume is not required: a quiet spring is the classic strong one; the LTF entry requires the Wyckoff "test"
        (a pullback on lower volume, levels.pullback_volume_ok).
        """
        atr = pl.col('atr')
        spring = (
            (pl.col('prior_range') <= self.cfg.spring_range_atr * atr) &
            (pl.col('prior_drift') <= self.cfg.spring_max_drift * pl.col('prior_range')) &
            pl.col('pierced_recent_low') &
            (pl.col('prior_low') - pl.col('low') <= self.cfg.spring_max_depth_atr * atr) &
            (pl.col('close') > pl.col('prior_low')) &
            pl.col('long_lower_wick') &
            (pl.col('delta_ratio') < 0)
        ).fill_null(False)
        return df.with_columns(
            self._points(spring, self.sc.spring_weight).alias('score_phase_b'),
            spring.alias('phase_b_active'),
        )

    def _score_phase_c_distribution(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Phase C: distribution / bull trap (bearish), all at a new 50-candle high.
        - Net taker flow over the last 20 candles clearly negative (buyers <= 47.5%): price up on selling =
          bearish CVD divergence, someone sells into strength (+2)
        - Funding above the extreme: longs pay heavily at the top (+1)
        - OI still rising with funding crowded (> funding_crowded): leveraged longs piling in late (+1)
        - Spot net selling over the last hour at the high: the real (unleveraged) side distributes (+1)
        """
        at_high = pl.col('is_local_high')
        divergence = at_high & (pl.col('flow_divergence') < self.cfg.distribution_flow_max)
        funding_extreme = at_high & (pl.col('predicted_funding') > self.cfg.funding_extreme_positive)
        crowded = at_high & (pl.col('oi_change_pct') > 0) & (pl.col('predicted_funding') > self.cfg.funding_crowded)
        spot_selling = at_high & pl.col('has_spot') & (pl.col('spot_delta_1h') < 0)

        score = (
            self._points(divergence, self.sc.distribution_divergence_weight) +
            self._points(funding_extreme, self.sc.funding_extreme_weight) +
            self._points(crowded, self.sc.distribution_crowded_weight) +
            self._points(spot_selling, self.sc.spot_perp_confirm_weight)
        )
        return df.with_columns(
            score.alias('score_phase_c'),
            divergence.fill_null(False).alias('phase_c_active'),
        )

    def _score_phase_d_dump(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Phase D: breakdown continuation (bearish) - price down + OI up = new shorts with conviction.
        - Close below the lower Bollinger band
        - Taker sells dominate the candle (delta_ratio < dump_delta_ratio)
        - OI up at least dump_oi_min over the short window (new shorts opening, not just longs closing)
        - Funding not already crowded short (squeeze risk)
        Falling price with collapsing OI is long liquidation, i.e. exhaustion; that belongs to phase E.
        A perp-led breakdown (spot not selling) is vetoed downstream (journal.veto_reason).
        """
        dump = (
            (pl.col('close') < pl.col('bb_lower')) &
            (pl.col('delta_ratio') < self.cfg.dump_delta_ratio) &
            (pl.col('oi_change_short') >= self.cfg.dump_oi_min) &
            (pl.col('predicted_funding') > self.cfg.funding_extreme_negative)
        ).fill_null(False)
        return df.with_columns(
            self._points(dump, self.sc.dump_oi_rising_weight + self.sc.dump_cvd_drop_weight).alias('score_phase_d'),
            dump.alias('phase_d_active'),
        )

    def _score_phase_e_capitulation(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Phase E: capitulation / selling climax (bullish reversal candidate).
        - Volume climax (RVOL > rvol_anomaly_threshold) after a real decline (>= capitulation_min_drop over the
          window), with OI dropping sharply over the short window: forced long liquidation (+2)
        - Funding below the negative extreme: shorts crowded after the flush (+1)
        - Reversal confirmation: long lower wick or buyers >= 55% of the candle (+2)
        - Spot net buying over the last hour: spot absorbs the perp flush (+1)
        - Long liquidations cascading (observed, not inferred from OI) (+1)
        """
        climax = (
            (pl.col('rvol') > self.cfg.rvol_anomaly_threshold) &
            (pl.col('price_change_flat') <= -self.cfg.capitulation_min_drop) &
            (pl.col('oi_change_short') < self.cfg.capitulation_oi_drop)
        )
        funding_negative = pl.col('predicted_funding') < self.cfg.funding_extreme_negative
        confirmation = climax & (pl.col('long_lower_wick') | (pl.col('delta_ratio') >= self.cfg.capitulation_confirm_flow))
        spot_absorbs = climax & pl.col('has_spot') & (pl.col('spot_delta_1h') > 0)
        long_liqs = climax & pl.col('liq_cascade') & (pl.col('liq_long_5m') > pl.col('liq_short_5m'))

        score = (
            self._points(climax, self.sc.capitulation_rvol_weight) +
            self._points(climax & funding_negative, self.sc.capitulation_funding_weight) +
            self._points(confirmation, self.sc.capitulation_delta_flip_weight) +
            self._points(spot_absorbs, self.sc.spot_perp_confirm_weight) +
            self._points(long_liqs, self.sc.liquidation_weight)
        )
        return df.with_columns(
            score.alias('score_phase_e'),
            confirmation.fill_null(False).alias('phase_e_active'),
        )

    def _score_phase_f_markup(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Phase F: markup breakout continuation (bullish), the mirror of phase D - price up + OI up = new longs with
        conviction.
        - Close above the upper Bollinger band
        - Taker buys dominate the candle (delta_ratio > markup_delta_ratio)
        - OI up at least dump_oi_min over the short window (new longs opening, not just shorts covering)
        - Funding not already at the long extreme (a crowded top)
        Rising price with collapsing OI is a short squeeze, which fades; a perp-led breakout (spot not buying) is
        vetoed downstream (journal.veto_reason).
        """
        markup = (
            (pl.col('close') > pl.col('bb_upper')) &
            (pl.col('delta_ratio') > self.cfg.markup_delta_ratio) &
            (pl.col('oi_change_short') >= self.cfg.dump_oi_min) &
            (pl.col('predicted_funding') < self.cfg.funding_extreme_positive)
        ).fill_null(False)
        return df.with_columns(
            self._points(markup, self.sc.dump_oi_rising_weight + self.sc.dump_cvd_drop_weight).alias('score_phase_f'),
            markup.alias('phase_f_active'),
        )

    def _calculate_total_scores(self, df: pl.DataFrame) -> pl.DataFrame:
        return df.with_columns(
            # Bullish phases: accumulation, spring, capitulation bottom
            (pl.col('score_phase_a') + pl.col('score_phase_b') + pl.col('score_phase_e') +
             pl.col('score_phase_f')).alias('total_long_score'),
            # Bearish phases: distribution, breakdown
            (pl.col('score_phase_c') + pl.col('score_phase_d')).alias('total_short_score'),
        )

    def get_latest_signal(self, scored_df: pl.DataFrame) -> Optional[Dict]:
        """Signal from the last row of a single-symbol scored frame."""
        if scored_df.is_empty():
            return None
        return self.signal_from_row(scored_df.row(-1, named=True))

    def signal_from_row(self, row: Dict) -> Optional[Dict]:
        long_score = row.get('total_long_score') or 0
        short_score = row.get('total_short_score') or 0
        threshold = self.sc.alert_threshold

        # Conflicting structure (equal bullish and bearish scores) is not a setup
        is_structured = max(long_score, short_score) >= threshold and long_score != short_score
        is_anomaly = bool(row.get('is_tier_0_anomaly'))
        if not (is_structured or is_anomaly):
            return None

        active_phases = [p for p in 'ABCDEF' if row.get(f'phase_{p.lower()}_active')]
        if is_structured and long_score > short_score:
            alert_type = 'LONG'
        elif is_structured:
            alert_type = 'SHORT'
        else:
            alert_type = 'ANOMALY'

        def num(key: str) -> float:
            value = row.get(key)
            return float(value) if value is not None else 0.0

        signal = {
            'long_score': long_score,
            'short_score': short_score,
            'alert_type': alert_type,
            'is_structured': is_structured,
            'is_tier_0_anomaly': is_anomaly,
            'active_phases': active_phases,
            'phase_a_score': row.get('score_phase_a') or 0,
            'phase_b_score': row.get('score_phase_b') or 0,
            'phase_c_score': row.get('score_phase_c') or 0,
            'phase_d_score': row.get('score_phase_d') or 0,
            'phase_e_score': row.get('score_phase_e') or 0,
            'phase_f_score': row.get('score_phase_f') or 0,
            'funding_rate': num('funding_rate'),
            'delta_ratio': num('delta_ratio'),
            # Context for explanations (15m candles)
            'candle_ts': row.get('timestamp'),
            'rvol_15m': num('rvol'),
            'flow_flat': num('flow_flat'),
            'flow_divergence': num('flow_divergence'),
            'oi_change_3h': num('oi_change_pct'),
            'oi_change_1h': num('oi_change_short'),
            'price_change_flat': num('price_change_flat'),
            'flat_range_atr': num('flat_range') / row['atr'] if row.get('atr') else 0.0,
            'oi_change_flat': num('oi_change_flat'),
            'is_squeezed': bool(row.get('is_squeezed')),
            'atr': num('atr'),
            'prior_range_high': num('prior_range_high'),
            'prior_low': num('prior_low'),
            'candle_minute_usd': num('candle_minute_usd'),
            'has_spot': bool(row.get('has_spot')),
            'spot_delta_1h': row.get('spot_delta_1h'),
            'perp_delta_1h': num('perp_delta_1h'),
            'perp_led_long': bool(row.get('perp_led_long')),
            'perp_led_short': bool(row.get('perp_led_short')),
            'liq_cascade': bool(row.get('liq_cascade')),
            'rule_anomaly': bool(row.get('rule_anomaly')),
            'agg_ready': bool(row.get('agg_ready')),
        }
        for c in TIER0_COLUMNS:
            signal[c] = num(c)
        return signal


def _tier0_frame(tier0: Dict[str, Dict[str, float]]) -> pl.DataFrame:
    symbols = list(tier0)
    return pl.DataFrame(
        {'symbol': symbols, **{c: [float((tier0[s] or {}).get(c, 0.0) or 0.0) for s in symbols] for c in TIER0_COLUMNS}},
        schema={'symbol': pl.String, **{c: pl.Float64 for c in TIER0_COLUMNS}},
    )


def _extras_frame(extras: Optional[Dict[str, Dict[str, float]]]) -> Optional[pl.DataFrame]:
    if not extras:
        return None
    symbols = list(extras)
    return pl.DataFrame(
        {'symbol': symbols, **{c: [extras[s].get(c) for s in symbols] for c in EXTRA_COLUMNS}},
        schema={'symbol': pl.String, **{c: pl.Float64 for c in EXTRA_COLUMNS}},
    )


def score_closed(
    spot_all: pl.DataFrame,
    futures_all: pl.DataFrame,
    tier0: Dict[str, Dict[str, float]],
    closed_until: Dict[str, int],
    extras: Optional[Dict[str, Dict[str, float]]] = None,
) -> Dict[str, Dict]:
    """
    Score every symbol in one pass and return, per symbol, the scored row of its last CLOSED candle
    (timestamp <= closed_until[symbol], the base market's newest finalized candle). Structured phases are read
    only from closed candles: an in-progress 15m candle can still change its close, wick and delta.
    """
    scorer = PhaseScorer()
    scored = scorer.calculate_scores(spot_all, futures_all, _tier0_frame(tier0), _extras_frame(extras))
    if scored.is_empty():
        return {}
    limits = pl.DataFrame({'symbol': list(closed_until), 'closed_until': list(closed_until.values())},
                          schema={'symbol': pl.String, 'closed_until': pl.Int64})
    closed = (scored.join(limits, on='symbol', how='inner')
              .filter(pl.col('timestamp') <= pl.col('closed_until'))
              .group_by('symbol', maintain_order=True).last())
    return {row['symbol']: row for row in closed.to_dicts()}


def signals_from_rows(rows: Dict[str, Dict], tier0: Dict[str, Dict[str, float]]) -> List[Tuple[str, Dict]]:
    """
    The per-scan light pass: cached closed-candle rows (structured scores) + fresh Tier-0 metrics -> signals.
    Symbols without candle history still get the Tier-0 check.
    """
    scorer = PhaseScorer()
    tier0_df = scorer.flag_tier_0_anomaly(_tier0_frame(tier0))
    flags = dict(zip(tier0_df['symbol'].to_list(), tier0_df['is_tier_0_anomaly'].to_list()))
    cascades = dict(zip(tier0_df['symbol'].to_list(), tier0_df['liq_cascade'].to_list()))
    rules = dict(zip(tier0_df['symbol'].to_list(), tier0_df['rule_anomaly'].to_list()))
    all_signals = []
    for symbol in set(rows) | set(tier0):
        row = dict(rows.get(symbol) or {})
        row.update({c: v for c, v in (tier0.get(symbol) or {}).items() if c in TIER0_COLUMNS})
        row['is_tier_0_anomaly'] = bool(flags.get(symbol))
        row['liq_cascade'] = bool(cascades.get(symbol)) or bool(row.get('liq_cascade'))
        row['rule_anomaly'] = bool(rules.get(symbol))
        signal = scorer.signal_from_row(row)
        if signal:
            signal['symbol'] = symbol
            all_signals.append((symbol, signal))

    # Structured signals first (by score), then raw anomalies (by size of the 5m move)
    all_signals.sort(key=lambda x: (
        x[1]['is_structured'],
        max(x[1]['long_score'], x[1]['short_score']),
        abs(x[1]['price_change_5m']),
    ), reverse=True)
    return all_signals


def score_all_symbols(
    spot_all: pl.DataFrame,
    futures_all: pl.DataFrame,
    tier0: Dict[str, Dict[str, float]],
    closed_until: Optional[Dict[str, int]] = None,
) -> List[Tuple[str, Dict]]:
    """Heavy + light pass in one call (tools and tests). Without closed_until every symbol's last row counts."""
    if closed_until is None:
        closed_until = {}
        for df in (futures_all, spot_all):
            if df is not None and not df.is_empty():
                for s, ts in df.group_by('symbol').agg(pl.col('timestamp').max()).iter_rows():
                    closed_until[s] = int(ts)
    rows = score_closed(spot_all, futures_all, tier0, closed_until)
    return signals_from_rows(rows, tier0)
