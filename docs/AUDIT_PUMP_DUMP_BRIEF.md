# edgehunter - pump / dump strategies: brief for an external auditor

Snapshot: 2026-10-24 ~19:45 UTC, deployed commit `935c7f3` (logic_version `eng-155`+, code up to eng-160b).
Bot: Python 3.14, asyncio + uvloop, ccxt. Market data: Binance USDT-M futures (+ spot, Bybit, OKX, Bitget, Hyperliquid,
Coinbase for the ~110-coin universe). Execution: BingX demo account (prices converted Binance -> BingX by a ratio).
Every code excerpt in Appendix A is extracted automatically from the deployed files (line numbers included).

Project rules the auditor should know (the owner's):
- No backtests / offline optimisation as a decision tool. Decisions come from code review, primary sources and the
  LIVE journal (`signals.db`, `demo_trades.db`). Archive research exists (research/pumps*.md) and is cited as context.
- The whole codebase is AI-written: comments and "by design" never excuse a bug.
- New filters go in as SHADOW vetoes first (journaled, not blocking); promoted only on live evidence.
- A strategy losing trade after trade = an obvious bug to find now (not "wait for more data", not "switch it off").
- Every strategy is ON (data collection); results are judged per strategy / per setup on live outcomes (`card_r`).

---------------------------------------------------------------------------------------------------------------------

## 1. Map of the pump / dump code

| Piece | File | What it does |
|---|---|---|
| PUMP START detector | strategies/pump.py `pump_start` | +15m move >= max(3%, 4 x 15m sigma), RVOL >= 5 (24h MEDIAN when known), OI 5m > 0, spot (small caps: futures) taker flow > 0, fresh 24h high |
| DUMP START detector | strategies/pump.py `dump_start` | mirror: -15m, OI 5m > 0 (new shorts), taker flow < 0, fresh 24h low. Our extension (the screener has no standalone dump start) |
| PUMP TOP | strategies/pump.py `pump_top` | buying climax: 15m candle at the high of a >= 10% / 4h pump, upper wick >= 50% of range, volume >= 2x; entry on 5m shift down |
| DUMP BOUNCE SHORT | strategies/pump.py `dump_bounce` | 1h: dump >= 15% below the 6h high on >= 3x volume, exhaustion, 38.2-61.8% bounce, 1h close below previous low -> short. The only archive rule positive in both halves (research/pumps*.md) |
| Plans | strategies/pump.py `*Strategy.plan` | stop beyond the ignition (+ measured pierce), targets = measured move (1x, 1.618x) and 1h+ zones, `min_rr` 1.0, `confirm_only` (enter at the signal close or never) |
| Universe hook | strategies/loopside.py `_pumps` | every final minute per coin: cheap 15m gate, then detectors; activation log; features |
| Small caps (outside the universe) | smallcap.py `SmallCapWatch` | eng-158: one dynamic Binance 1m-kline connection for every perpetual >= $3M/24h outside the universe; 240-min ring; REST 15m vol + 5m OI on a gate hit; cards + demo |
| Features | strategies/pd_features.py | eng-159..160b: 288 x 5m median baselines, volume / range clusters, move3/6/12, 2h breakout, EMA20, pullback, quiet window, phases (ACTIVATION / ACTIVE / LATE / SPIKE_FAIL / NONE), trades ratio, price vs 12h MA, vs BTC (difference and beta residual), H_n / ATR5 |
| Enrichment at signal time | scanner.py `_pd_enrich`, `_btc_m5` | one REST call (290 x 5m) per PUMP/DUMP START; BTC 5m cached 5 min |
| Shadow vetoes | strategies/pump.py `context_veto` | `pd_late`, `pd_spike_fail` (config.shadow_vetoes) - journaled, not blocking |
| Retest variant | signal_book.py `_retest_variants` | eng-160: `variant_retest` - H_n +- 0.25 ATR(5m), 5m close back beyond H_n within 2h; plan's stop / targets; journal only; all cards watched (no survivorship) |
| Rush orders | flow.py `RushBook` | eng-89: same-ms same-side multi-level aggTrade sweeps per second; `rush_*` in every universe signal (proxy, see 6.3) |
| Hard veto | signal_book.py update (~line 454) | `event_risk`: no LONG on coins Binance tagged for monitoring / delisting - blocked 19 PUMP STARTs since 17.10 |
| Management | signal_book.py `_trail`, executor.py `on_partial`, `exit_parts` | eng-155: stop to break-even + 0.15% after +1R, 50% out at +1R (open trades too) |
| Portfolio | config `crowd_max` 6 | eng-156: max 6 open trades per direction (Turtles' closely-correlated limit) |

## 2. Signal lifecycle (one PUMP START, universe coin)

```
final 1m candle -> loopside._pumps(symbol)
  activation log update (5m ACTIVATION, source rule)                      [pd_features.ActivationLog]
  base15 gate: close / close 15 min ago - 1 >= pump_start_min_pct (3%)    [cheap, by time not index]
  vol_15m = sqrt(mean(r^2)) of the last 96 x 15m returns
  tier0['rvol_1m_med'] = last minute quote / (median(96 x 15m qv) / 15)
  pump_start(minutes, tier0, vol_15m, now, h1)  -> setup dict | None
  found.update(pd_features.features(minutes, m15, +1))   # ring-based first pass
  found['pd_activation_lead_s'] = activation lead
scanner._detect_setups -> sig = dict(md.tier0) + setup (includes rush_* , oi, cvd ...)
scanner._perform_scan:  await _pd_enrich(symbol, sig)      # REST 290 x 5m: source baselines + extras + H_n
SignalBook.update -> vetoes (veto_reason, context_veto -> shadow pd_late / pd_spike_fail, event_risk, disabled ...)
  card created (status BIAS) -> _advance: plan (PumpStartStrategy.plan) -> confirm entry at the current price
  entry_levels -> low_rr if R:R to TP1 < min_rr 1.0 -> card EXPIRED (confirm_only) else ENTRY
  journal: setup row, entry row (vetoed or live), card row; demo executor opens on BingX for live entries
  _retest_variants watches the card 2h for variant_retest (journal only)
trade: _trail each minute (BE + partial at +1R, PARTIAL / RESTOP events -> executor), exit by stop / targets / TTL
```

Small cap: identical from the signal on; detection runs in smallcap.py on its own 1m stream; the card's price /
minutes come from the watch via Scanner._price_of / _minute_candles fallbacks; no 15m frame (PlanInput.atr falls back
to sig['atr_15m'] = 1h ATR(14)/2).

## 3. Exact rules and numbers

### 3.1 PUMP START / DUMP START (detector)
- move15 = close(t) / close(t-15m) - 1 (both minutes must exist; a gap -> no signal)
- |move15| >= max(pump_start_min_pct = 0.03, pump_start_z = 4.0 x vol_15m)
- RVOL: `rvol_1m_med` (last minute quote / 24h-median minute) if available, else Tier-0 `rvol_1m` (vs 24h MEAN) >= 5.0
- OI: oi_change_5m > 0 for both (pump: new longs+shorts while price rises; dump: new positions while it falls)
- flow: spot_cvd_5m > 0 (pump) / < 0 (dump). Universe = Binance spot taker delta + aggregated venues; small caps =
  Binance FUTURES taker delta of the last 5 minutes (flagged `flow_src = futures`)
- fresh 24h extreme: last high > max(highs of the previous 24h excluding the last 15m) (h1 candles + minutes)
- once per coin per hour bucket of the anchor (pump) / per direction (dump)

### 3.2 Plan geometry (PumpStart / DumpStart)
- entry: `confirm` at the current price when the card is processed (seconds after the signal minute closes)
- stop: beyond the ignition extreme (pump: lowest low of the last 16 minutes; dump: highest high) + measured pierce
  pad (pierce model per level kind, capped in ATR), floor = 1 ATR (geometry.stop_levels / stop_floor)
- targets: measured move from the close (close +- move, +- 1.618 move) and 1h+ zones (htf_zones), select_targets
- min_rr 1.0 to TP1 (R:R ~1 by construction: eng-71); costs in cost_r; low_rr -> card EXPIRED, journaled
- TTL: pump_ttl = (3600, 3600, 12h); trade managed by stop / targets / BE+partial

### 3.3 Features journaled per PUMP/DUMP START (columns)
rvol_1m_med, pd_base_n, pd_vol_ratio_5m, pd_vol_cluster, pd_range_ratio, pd_range_cluster, pd_move3, pd_move6,
pd_move12, pd_green4, pd_green6, pd_breakout, pd_above_ema20, pd_ema20_slope, pd_pullback, pd_quiet, pd_late,
pd_spike_fail, pd_phase, pd_activation_lead_s, pd_trades_ratio_5m, pd_price_vs_ma12h, pd_vs_btc, pd_btc_beta,
pd_vs_btc_resid, pd_hn, pd_atr5, smallcap, flow_src, + the universe's rush_n_10s / rush_n_30s / rush_net_30s /
rush_usd_30s / rush_z_30s, oi_change_5m, spot_cvd_5m, and ~150 context columns (regime, bias, dvol, funding ...).

Source thresholds (aleks-ent/pump-dump-crypto-screener PUMP_DETECTION_RULES.md, read in full 24.10): volume >= 3 / 5 /
10 x median, cluster >= 2 of 4; range >= 2 (3) x median, cluster >= 2 of 4; move3 >= 2%, move6 >= 4%; breakout close
> 24-bar high x 1.003; pullback <= 0.30 (0.20), > 0.50 no longer active; ACTIVATION vol >= 3, range >= 1.5,
move3 > 0, close > EMA20 or breakout; LATE move12 >= 12% & vol >= 10 & range >= 4; SPIKE one candle >= 5% retraced
> 70% within 2. Baselines: medians of the PREVIOUS 288 x 5m candles.

### 3.4 Risk / execution
- 1R per trade, size recomputed at BingX's price; leverage 2-5x; stops `stopLossPrice` reduceOnly, workingType MARK_PRICE
- chase_limit for plans without targets (eng-147); R:R re-checked at BingX price for plans with targets
- eng-155: BE + 0.15% after +1R for every plan without its own trail; 50% out at +1R (tp0 order for new trades;
  PARTIAL event -> market reduce for older ones; keeps half of the ORIGINAL size)
- crowd_max 6 per direction; daily loss / trade-count limits off; demo_off_setups empty

## 4. Live evidence so far (journal, 17.10-24.10)
- PUMP START: 157 setups vetoed `disabled` (before eng-157) + 19 vetoed `event_risk`; 0 live entries yet.
- PUMP TOP: 85 setups `disabled`; DUMP START: new (eng-157, 24.10 18:45), none yet.
- DUMP BOUNCE SHORT: 8 setups in the universe + 7 outside (journal only before eng-158); live card results across
  versions: -1.05R, +0.66R, +0.35R, -0.23R (4 trades).
- Archive (research/pumps.md, 478 coins 2023-10..2026-08, pre-registered): small-cap pumps revert (78-82% back to 50%
  before a new extreme); FADE of pumps negative; DIP-BUY / dump bounce the only cells beating geometry in both halves;
  holdout 2021-2023 (research/pumps_holdout.md) did NOT confirm DIP-BUY for pumps.
- See data/pump_signals.csv and logs/ in the bundle.

## 5. Known gaps / open questions for the auditor
1. Entry timing: PUMP START enters seconds after the 15m move is already >= 3% and >= 4 sigma. Is that the "start" or
   already the late part (the research's lead-time question)? Measure with pd_activation_lead_s and MFE/MAE.
2. R:R by construction ~1 (stop spans the ignition, TP1 = measured move) + min_rr 1.0 -> many low_rr expiries
   (the 19 event_risk / 157 disabled before tell nothing yet). Is the stop placement right for momentum ignition?
3. DUMP START is our mirror. Literature treats dumps mostly as distribution after a pump / liquidation cascades;
   OI rising + taker selling is the chosen confirmation - is that sound?
4. Small caps: no spot, no books, futures-only flow, ATR from 1h/2, 10-min re-attach after restarts.
5. Rush orders are a narrower proxy than La Morgia (aggTrade merges same-price fills; see 6.3); no 5/15/25-s windows.
6. LATE / SPIKE_FAIL are shadow only; PUMP TOP / FADE logic vs research (fading pumps lost on the archive).
7. event_risk blocks PUMP START longs on monitored coins - correct for pumps (those coins pump hardest)?
8. BE after +1R and partials are the owner's choice; sources are split (MAE/MFE write-ups find BE at +1R often lowers
   expectancy). Is the implementation correct (Appendix A: _trail, on_partial)?
9. variant_retest: H_n = edge of 24 x 5m before the last 3 bars; retest band 0.25 ATR(5m); the plan's stop kept.

## 6. Nuances
6.1 No lookahead: baselines use previous candles only; REST klines filtered by closeTime < now; the current 5m candle
    never in its own base; card entry at a live price after the signal minute closed.
6.2 Mean vs median: the Tier-0 rvol (24h mean) still exists for other strategies; PUMP/DUMP START use the median one
    when the 15m history has >= 48 candles.
6.3 RushBook counts one taker order that hit >= 2 price levels (several aggTrades with the same T and side). Binance
    aggTrade already merges one taker's fills at one price, so single-level market orders are not counted; the paper
    groups raw @trade prints in the same ms. Neither is an exact market-order count (no parent id publicly).
6.4 pd_trades_ratio_5m is closed-candle only; base median >= 20 trades else not computed.
6.5 Small caps' ACTIVATION base = 24h mean minute (no 15m history before a check); detection uses the median.
6.6 The Binance liquidation stream (forceOrder) carries at most one order per symbol per second -> undercount;
    liquidations are context only.
6.7 OI history endpoint: 5m resolution, ~30 days only.

## 7. Bundle contents
- docs/: this brief, PUMP_DUMP_DETECTOR.md, PLAN_eng156.md, HISTORY_recent.md (eng-150..160b)
- code/: full sources (pump.py, pd_features.py, smallcap.py, loopside.py, scanner.py, signal_book.py, geometry.py,
  executor.py, flow.py, config.py, journal.py, levels.py, base.py, indicators.py, zones.py)
- research/: pumps.md, pumps_by_size.md, pumps_holdout.md (archive, context only)
- data/: pump_signals.csv (every pump-strategy row since 17.10 with pd_* features), demo_trades_pump.csv
- logs/: pump / small-cap / PD-features lines since 23.10, Health sample

---------------------------------------------------------------------------------------------------------------------

## Appendix A - code excerpts (auto-extracted from the deployed files)

### strategies/pump.py:30-65 `pump_start`

```python
def pump_start(minutes: Sequence[Sequence[float]], m: Dict, vol_15m: Optional[float], now_ms: int,
               h1: Sequence[Sequence[float]] = ()) -> Optional[Dict]:
    """minutes: final 1m candles; m: the coin's Tier-0 metrics; vol_15m: std of 15m returns; h1: the closed 1h candles
    (eng-132: the 24h high comes from them - the 1m history holds only ~10h, so every 10h-old high looked 'fresh')."""
    cfg = CONFIG.strategies
    if len(minutes) < 120 or not vol_15m:
        return None
    last = minutes[-1]
    # by time, not by index (eng-74: after a feed gap minutes[-16] is older than 15 minutes - a false '+x% in 15m')
    from strategies.oi_build import _close_at
    base = next((c for c in minutes if c[0] == int(last[0]) - 15 * MINUTE_MS), None)
    if base is None or _close_at(minutes, int(last[0]) - 15 * MINUTE_MS) is None:
        return None
    move = last[4] / base[4] - 1
    if move < max(cfg.pump_start_min_pct, cfg.pump_start_z * vol_15m):
        return None
    # eng-159: the 24h MEDIAN minute when the caller has it (pd_features), the 24h mean (Tier-0) otherwise
    if (m.get('rvol_1m_med') or m.get('rvol_1m') or 0) < cfg.pump_start_rvol:
        return None
    if (m.get('oi_change_5m') or 0) <= 0 or (m.get('spot_cvd_5m') or 0) <= 0:
        return None
    cut = minutes[-15][0]
    # closed hours starting before the minutes' first candle (the hour holding it too) + the minutes themselves (before the last 15m): a full 24h window
    first_min = minutes[0][0]
    day = [c[2] for c in h1 if now_ms - 86_400_000 - MINUTE_MS <= c[0] and c[0] < first_min]
    day += [c[2] for c in minutes if c[0] >= now_ms - 86_400_000 - MINUTE_MS and c[0] < cut]
    if day and last[2] <= max(day):
        return None                                   # not a fresh 24h high: a recovery inside the range
    quiet = minutes[-60:-15]
    low = min(c[3] for c in minutes[-16:])
    return {'setup': 'PUMP START', 'direction': 1,
            'setup_note': f"+{move:.1%} in 15m ({move / vol_15m:.1f}x the 15m volatility), RVOL {m.get('rvol_1m', 0):.1f}, "
                          f"OI rising, spot buying, a fresh 24h high",
            'anchor_level': max(c[2] for c in quiet) if quiet else base[4], 'anchor_extreme': low,
            'anchor_label': 'ignition', 'anchor_ts': int(base[0]), 'anchor_close': last[4],
            'pump_low': low, 'pump_move': move, 'event_ts': int(last[0]) + MINUTE_MS}
```

### strategies/pump.py:68-102 `dump_start`

```python
def dump_start(minutes: Sequence[Sequence[float]], m: Dict, vol_15m: Optional[float], now_ms: int,
               h1: Sequence[Sequence[float]] = ()) -> Optional[Dict]:
    """eng-157 (the owner: we look for the start of dumps as well as pumps): PUMP START mirrored - the last 15 minutes
    fell >= pump_start_z x the coin's 15m volatility and >= pump_start_min_pct on >= pump_start_rvol x the usual volume,
    open interest rising (new shorts, not long liquidation only) and spot taker selling, at a fresh 24h low."""
    cfg = CONFIG.strategies
    if len(minutes) < 120 or not vol_15m:
        return None
    last = minutes[-1]
    from strategies.oi_build import _close_at
    base = next((c for c in minutes if c[0] == int(last[0]) - 15 * MINUTE_MS), None)
    if base is None or _close_at(minutes, int(last[0]) - 15 * MINUTE_MS) is None:
        return None
    move = last[4] / base[4] - 1
    if -move < max(cfg.pump_start_min_pct, cfg.pump_start_z * vol_15m):
        return None
    # eng-159: the 24h MEDIAN minute when the caller has it (pd_features), the 24h mean (Tier-0) otherwise
    if (m.get('rvol_1m_med') or m.get('rvol_1m') or 0) < cfg.pump_start_rvol:
        return None
    if (m.get('oi_change_5m') or 0) <= 0 or (m.get('spot_cvd_5m') or 0) >= 0:
        return None
    cut = minutes[-15][0]
    first_min = minutes[0][0]
    day = [c[3] for c in h1 if now_ms - 86_400_000 - MINUTE_MS <= c[0] and c[0] < first_min]
    day += [c[3] for c in minutes if c[0] >= now_ms - 86_400_000 - MINUTE_MS and c[0] < cut]
    if day and last[3] >= min(day):
        return None                                   # not a fresh 24h low: a drop inside the range
    quiet = minutes[-60:-15]
    high = max(c[2] for c in minutes[-16:])
    return {'setup': 'DUMP START', 'direction': -1,
            'setup_note': f"{move:.1%} in 15m ({-move / vol_15m:.1f}x the 15m volatility), RVOL {m.get('rvol_1m', 0):.1f}, "
                          f"OI rising, spot selling, a fresh 24h low",
            'anchor_level': min(c[3] for c in quiet) if quiet else base[4], 'anchor_extreme': high,
            'anchor_label': 'dump ignition', 'anchor_ts': int(base[0]), 'anchor_close': last[4],
            'dump_high': high, 'pump_move': move, 'event_ts': int(last[0]) + MINUTE_MS}
```

### strategies/pump.py:105-128 `pump_top`

```python
def pump_top(minutes: Sequence[Sequence[float]], m: Dict, now_ms: int) -> Optional[Dict]:
    """The climax 15m candle that just closed after a pump of >= pump_top_min_pct within 4h."""
    cfg = CONFIG.strategies
    bars = resample(minutes, 15, now_ms)
    if len(bars) < 21:
        return None
    last = bars[-1]
    window = bars[-16:]
    low = min(b[3] for b in window)
    hi = max(b[2] for b in window)
    if last[2] < hi or hi / low - 1 < cfg.pump_top_min_pct:
        return None                                   # the climax must be the high of the pump
    span = last[2] - last[3]
    upper = last[2] - max(last[1], last[4])
    avg_vol = sum(b[5] for b in bars[-21:-1]) / 20
    if span <= 0 or upper < 0.5 * span or not avg_vol or last[5] < 2 * avg_vol:
        return None
    oi_falling = (m.get('oi_change_5m') or 0) < 0
    return {'setup': 'PUMP TOP', 'direction': -1,
            'setup_note': f"buying climax after +{hi / low - 1:.0%} in 4h: 15m upper wick {upper / span:.0%} of the "
                          f"candle on {last[5] / avg_vol:.1f}x volume{', OI falling' if oi_falling else ''}; "
                          f"entry on the 5m shift down",
            'anchor_level': hi, 'anchor_extreme': hi, 'anchor_label': 'pump high', 'anchor_ts': int(window[0][0]),
            'anchor_close': last[4], 'pump_low': low, 'pump_high': hi, 'event_ts': int(last[0]) + QUARTER_MS}
```

### strategies/pump.py:134-213 `dump_bounce`

```python
def dump_bounce(h1: Sequence[Sequence[float]], now_ms: int) -> Optional[Dict]:
    """
    eng-55, the rule of research_pumps.py (DIP-BUY mirrored for a dump; the only pump / dump rule positive in every
    period 2021-2026: +0.14R on 156 trades Apr-Sep 2026, 900 perpetuals). On CLOSED 1h candles [ts, o, h, l, c, vol]:
    - DUMP at hour t: close >= dump_min_move below the highest high of the last 6 hours, and the hours since that high
      traded >= dump_vol_x x the average hour of the week before; one dump per 48h.
    - its low: the lowest low until the first close above the previous hour's high (exhaustion), within 24h; no
      exhaustion, no signal (audit A18).
    - the bounce, from the exhaustion hour on: price retraces to 38.2% of the dump (from the low toward the 6h high) within 24h, not beyond 61.8%,
      then a 1h close below the previous hour's low -> short at market now (the research entered at the next open).
    - stop above the bounce's high + 0.25 ATR(1h); TP1 the dump's low. dump_ext (the 1.618 extension) is journaled
      in the signal only: the plan has no TP2 of its own (audit A18; the owner decides whether it becomes one).
    Fires only when the trigger is the candle that just closed.
    """
    cfg = CONFIG.strategies
    n = len(h1)
    if n < 190:
        return None
    h = [c[2] for c in h1]
    lo = [c[3] for c in h1]
    cl = [c[4] for c in h1]
    v = [c[5] for c in h1]
    last_event = -10 ** 9
    found = None
    for t in range(max(175, n - 75), n - 1):
        if t - last_event < 48:
            continue
        k0 = max(range(t - 5, t + 1), key=lambda k: h[k])
        base = h[k0]
        if not cl[t] or base / cl[t] - 1 < cfg.dump_min_move:
            continue
        week = v[t - 168 - 5:t - 5 + 1]
        vol7 = sum(week) / len(week) if week else 0.0
        if not vol7 or sum(v[k0:t + 1]) < cfg.dump_vol_x * (t + 1 - k0) * vol7:
            continue
        last_event = t
        if t < n - 26:
            continue                                  # too old to be still bouncing
        # review V12: research_pumps.atr1h - the 14 hours BEFORE the dump hour (the dump bar's own range left out)
        # owner 2026-10-18: Wilder's ATR14 (the bot's one ATR) of the candles up to the hour before the dump
        from levels import wilder_of
        trs = [max(h[k], cl[k - 1]) - min(lo[k], cl[k - 1]) for k in range(max(1, t - 200), t)]
        atr = wilder_of(trs, 14) or (sum(trs) / len(trs) if trs else 0.0)
        # audit R05 / N26: a causal automaton - the dump's low is FIXED at the exhaustion close (the first close above
        # the previous hour's high) and the bounce is searched only from that hour on; a dump not exhausted yet has
        # no low and no trade (searching from t+1 placed earlier touches against a low found later)
        peak, ex = lo[t], None
        for k in range(t + 1, min(n, t + 25)):
            peak = min(peak, lo[k])
            if cl[k] > h[k - 1]:
                ex = k
                break
        if ex is None:
            continue
        size = base - peak
        if ex is None or size <= 0:
            continue
        lo_r, hi_r = peak + 0.382 * size, peak + 0.618 * size
        touched, pull = False, None
        for k in range(ex, min(n, t + 25)):
            if not touched:
                if h[k] >= lo_r:
                    touched, pull = True, h[k]
                continue
            pull = max(pull, h[k])
            if pull > hi_r:
                break
            if cl[k] < lo[k - 1]:
                if k == n - 1:
                    stop = pull + 0.25 * atr
                    found = {'setup': 'DUMP BOUNCE SHORT', 'direction': -1,
                             'setup_note': f"1h dump -{base / cl[t] - 1:.0%} from the 6h high {base:.6g} on "
                                           f"{sum(v[k0:t + 1]) / ((t + 1 - k0) * vol7):.1f}x volume; the bounce reached "
                                           f"{(pull - peak) / size:.0%} of it and closed below the previous low",
                             'anchor_level': cl[k], 'anchor_extreme': stop, 'anchor_label': 'dump bounce',
                             'anchor_ts': int(h1[t][0]), 'anchor_close': cl[k], 'dump_low': peak, 'dump_high': base,
                             'dump_stop': stop, 'dump_ext': base - 1.618 * size,
                             'event_ts': int(h1[k][0]) + 3_600_000}
                break
    return found
```

### strategies/pump.py:216-242 `DumpBounceStrategy`

```python
class DumpBounceStrategy(Strategy):
    """The short of the first bounce after a dump (eng-55): at market on the trigger close, stop above the bounce,
    TP1 the dump's low (research_pumps.py); the 1.618 extension (sig dump_ext) is not a target of the plan."""
    name = 'pump'
    anchor_type = 'level'
    setups = {'DUMP BOUNCE SHORT': -1}
    min_rr = 0.0                     # the research rule has no ratio filter: TP1 is the dump's low wherever it is
    ttl_key = 'pump_ttl'

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('anchor_ts'), 'dump') if x.sig.get('dump_low') is not None else None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        from strategies.maniac_strategies import _confirm_plan
        sig = x.sig
        if sig.get('dump_low') is None:
            return None
        # audit: the research's exits - TP1 the dump's low, TP2 its 1.618 extension (dump_ext was computed, never
        # used) and its own stop 0.25 ATR above the bounce, not widened / moved by the shared floor (own_stop)
        exit = {'stop': ['price', sig['dump_stop']], 'stop_src': 'above the bounce + 0.25 ATR(1h)',
                'tp': ['level', sig['dump_low'], 0.0, None], 'tp_src': "the dump's low", 'atr': x.atr,
                'tp2': ['level', sig.get('dump_ext') or sig['dump_low'], 0.0, None], 'own_targets': True,
                'own_stop': True}
        plan = _confirm_plan(x, self.name, '1h', exit, 'first bounce after a dump, 1h close below the previous low')
        if plan and not plan.get('skip'):
            plan['key'] = (sig['anchor_ts'], 'dump')
        return plan
```

### strategies/pump.py:245-290 `PumpStartStrategy`

```python
class PumpStartStrategy(Strategy):
    name = 'pump'
    anchor_type = 'level'
    setups = {'PUMP START': 1}
    # eng-71: the stop spans the ignition and TP1 is its measured move - R:R ~1 by construction, the global 2 vetoed
    # every PUMP START (ORCA / NIGHT 0.5-1.0); the owner's method has no ratio rule (as the other sources: 1)
    min_rr = 1.0
    ttl_key = 'pump_ttl'
    uses_minutes = True
    default_tf = '15m'

    def context_veto(self, sig: Dict, direction: int) -> Optional[str]:
        # eng-159: the detector's phases (strategies.pd_features) - shadow vetoes, journaled, judged live
        from signal_book import shadow_veto
        if sig.get('pd_spike_fail'):
            shadow_veto(sig, 'pd_spike_fail')
        return 'pd_late' if sig.get('pd_late') else None

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('anchor_ts'), 'start') if x.sig.get('pump_low') is not None else None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig = x.sig
        atr = x.atr or sig.get('atr_15m')     # eng-158: a small cap has no 15m frame - the watch's ATR
        if sig.get('pump_low') is None or not atr:
            return None
        close = sig['anchor_close']
        zones = merge(list(x.raw_levels or []), atr, symbol=x.symbol)
        move = close - sig['pump_low']
        fillers = (close + move, close + 1.618 * move)
        # eng-69: the stop spans the whole ignition, so the targets cannot be the nearest 15m swing / FVG (live eng-60:
        # TP1 at 0.56 of the risk, every entry low_rr) - the measured move and 1h+ zones only
        targets, sources = select_targets(htf_zones(zones, '1h'), close, 1, max(atr, x.tf_atr.get('1h') or 0.0),
                                          'extension', fillers, 'measured move')
        anchor = {'type': 'level', 'tf': '15m', 'level': sig['anchor_level'], 'label': 'pump ignition',
                  'extreme': sig['pump_low'], 'ts': sig['anchor_ts']}
        plan = base_plan(x, self.name, anchor, '15m', entry='confirm', confirm_only=True,
                         zone_lo=close - 0.25 * atr, zone_hi=close + 0.25 * atr, zone_src='momentum ignition',
                         missable=False, stop_ref=sig['pump_low'],
                         exit={'stop': ['ref', 0.0], 'tp': ['map', 0.0], 'atr': atr,
                               'stop_src': 'below the ignition'},
                         intent='extension', fillers=fillers, fill_label='measured move', targets=targets,
                         target_src=sources, zones=zones, key=(sig['anchor_ts'], 'start'))
        plan['target_tf'] = '1h'                     # eng-69: targets from 1h+ zones (see above)
        # eng-91: no averaging into a loser (was add_half: one more unit at half the way to the stop)
        return plan
```

### strategies/pump.py:293-335 `DumpStartStrategy`

```python
class DumpStartStrategy(Strategy):
    """eng-157: PumpStartStrategy mirrored for the start of a dump (short at the confirmation, stop above the ignition,
    the measured move down and 1h+ zones as targets)."""
    name = 'pump'
    anchor_type = 'level'
    setups = {'DUMP START': -1}
    min_rr = 1.0
    ttl_key = 'pump_ttl'
    uses_minutes = True
    default_tf = '15m'

    def context_veto(self, sig: Dict, direction: int) -> Optional[str]:
        # eng-159: the detector's phases (strategies.pd_features) - shadow vetoes, journaled, judged live
        from signal_book import shadow_veto
        if sig.get('pd_spike_fail'):
            shadow_veto(sig, 'pd_spike_fail')
        return 'pd_late' if sig.get('pd_late') else None

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('anchor_ts'), 'dstart') if x.sig.get('dump_high') is not None else None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig = x.sig
        atr = x.atr or sig.get('atr_15m')     # eng-158: a small cap has no 15m frame - the watch's ATR
        if sig.get('dump_high') is None or not atr:
            return None
        close = sig['anchor_close']
        zones = merge(list(x.raw_levels or []), atr, symbol=x.symbol)
        move = sig['dump_high'] - close
        fillers = (close - move, close - 1.618 * move)
        targets, sources = select_targets(htf_zones(zones, '1h'), close, -1, max(atr, x.tf_atr.get('1h') or 0.0),
                                          'extension', fillers, 'measured move')
        anchor = {'type': 'level', 'tf': '15m', 'level': sig['anchor_level'], 'label': 'dump ignition',
                  'extreme': sig['dump_high'], 'ts': sig['anchor_ts']}
        plan = base_plan(x, self.name, anchor, '15m', entry='confirm', confirm_only=True,
                         zone_lo=close - 0.25 * atr, zone_hi=close + 0.25 * atr, zone_src='momentum ignition (dump)',
                         missable=False, stop_ref=sig['dump_high'],
                         exit={'stop': ['ref', 0.0], 'tp': ['map', 0.0], 'atr': atr,
                               'stop_src': 'above the ignition'},
                         intent='extension', fillers=fillers, fill_label='measured move', targets=targets,
                         target_src=sources, zones=zones, key=(sig['anchor_ts'], 'dstart'))
        plan['target_tf'] = '1h'
        return plan
```

### strategies/pump.py:338-367 `PumpTopStrategy`

```python
class PumpTopStrategy(Strategy):
    name = 'pump'
    anchor_type = 'level'
    setups = {'PUMP TOP': -1}
    ttl_key = 'pump_ttl'
    uses_minutes = True
    default_tf = '15m'

    def gate_key(self, x: PlanInput) -> Optional[tuple]:
        return (x.sig.get('anchor_ts'), 'top') if x.sig.get('pump_high') is not None else None

    def plan(self, x: PlanInput) -> Optional[Dict]:
        sig, atr = x.sig, x.atr
        if sig.get('pump_high') is None or not atr:
            return None
        hi, lo = sig['pump_high'], sig['pump_low']
        leg = hi - lo
        retraces = tuple(hi - r * leg for r in (0.382, 0.5, 0.618))
        zones = merge(list(x.raw_levels or []), atr, symbol=x.symbol)
        targets, sources = select_targets(zones, sig['anchor_close'], -1, atr, 'mean', retraces, 'retrace')
        anchor = {'type': 'level', 'tf': '15m', 'level': hi, 'label': 'pump high', 'extreme': hi,
                  'ts': sig['anchor_ts']}
        # the shift down is looked for in the climax's upper part: from the high to its 0.236 retracement
        zone = (hi - 0.236 * leg, hi)
        plan = base_plan(x, self.name, anchor, '15m', entry='pullback', zone_lo=zone[0], zone_hi=zone[1],
                         zone_src='buying climax (5m shift down)', invalid=hi, fix_invalid=False, missable=True,
                         stop_ref=hi, intent='mean', fillers=retraces, fill_label='retrace', targets=targets,
                         target_src=sources, zones=zones, key=(sig['anchor_ts'], 'top'))
        # eng-91: no averaging into a loser (was add_half)
        return plan
```

### strategies/pd_features.py:24-40 `bars_5m`

```python
def bars_5m(minutes: Sequence[Sequence[float]]) -> List[List[float]]:
    """Final 1m candles -> complete 5m bars [ts, o, h, l, c, quote_vol, taker_buy_quote] (a bucket missing a minute is
    dropped - a hole beats a false bar)."""
    out: List[List[float]] = []
    count: List[int] = []
    for c in minutes:
        start = int(c[0]) // FIVE_MS * FIVE_MS
        if out and out[-1][0] == start:
            b = out[-1]
            b[2], b[3], b[4] = max(b[2], c[2]), min(b[3], c[3]), c[4]
            b[5] += c[5]
            b[6] += c[6] if len(c) > 6 else 0.0
            count[-1] += 1
        else:
            out.append([start, c[1], c[2], c[3], c[4], c[5], c[6] if len(c) > 6 else 0.0])
            count.append(1)
    return [b for b, n in zip(out, count) if n == 5]
```

### strategies/pd_features.py:43-49 `volume_base_1m`

```python
def volume_base_1m(m15: Sequence[Sequence[float]]) -> Optional[float]:
    """The 24h MEDIAN quote volume of a minute: median of the last 96 closed 15m candles / 15."""
    vols = [float(b[5]) for b in list(m15)[-96:] if len(b) > 5 and b[5] is not None]
    if len(vols) < 48:
        return None
    med = median(vols)
    return med / 15 if med > 0 else None
```

### strategies/pd_features.py:59-164 `features`

```python
def features(minutes: Sequence[Sequence[float]], m15: Sequence[Sequence[float]], direction: int,
             m5: Optional[Sequence[Sequence[float]]] = None) -> Dict:
    """pd_* features at the last final minute, for a move in `direction` (+1 pump, -1 dump).

    m5: closed 5m candles of the last 24h+ (REST, the source's 288-candle baselines); without it the 5m bars of the 1m
    ring are the base (pd_base_n says how many)."""
    out: Dict = {}
    ring = bars_5m(minutes)
    if m5:
        hist = [list(b[:7]) if len(b) >= 7 else list(b[:6]) + [0.0] for b in m5]
        cut = ring[0][0] if ring else float('inf')
        bars = [b for b in hist if b[0] < cut] + ring
    else:
        bars = ring
    if len(bars) < 13:
        return out
    last = bars[-1]
    prev = bars[-289:-1]
    out['pd_base_n'] = len(prev)
    # baselines: medians of the PREVIOUS candles only (the source: 288 x 5m, the current one excluded)
    vols = [b[5] for b in prev if b[5] is not None]
    base5 = median(vols) if len(vols) >= 12 else None
    if not base5:
        b1 = volume_base_1m(m15)
        base5 = b1 * 5 if b1 else None
    if base5 and minutes:
        out['rvol_1m_med'] = float(minutes[-1][5]) / (base5 / 5)
    rngs = [(b[2] - b[3]) / b[4] for b in prev if b[4]]
    med_rng = median(rngs) if len(rngs) >= 12 else None
    def vr(b):
        return b[5] / base5 if base5 else None
    def rr(b):
        return (b[2] - b[3]) / b[4] / med_rng if med_rng and b[4] else None
    if base5:
        out['pd_vol_ratio_5m'] = vr(last)
        out['pd_vol_cluster'] = sum(1 for b in bars[-4:] if (vr(b) or 0) >= 3.0)          # source: >= 2 of 4
    if med_rng:
        out['pd_range_ratio'] = rr(last)
        out['pd_range_cluster'] = sum(1 for b in bars[-4:] if (rr(b) or 0) >= 2.0)        # source: >= 2 of 4
    out['pd_move3'] = last[4] / bars[-4][4] - 1 if bars[-4][4] else None
    out['pd_move6'] = last[4] / bars[-7][4] - 1 if bars[-7][4] else None
    # green (red for a dump) candles of the last 4 / 6 (source: >= 3 of 4, strong >= 5 of 6)
    out['pd_green4'] = sum(1 for b in bars[-4:] if direction * (b[4] - b[1]) > 0)
    out['pd_green6'] = sum(1 for b in bars[-6:] if direction * (b[4] - b[1]) > 0)
    loc = bars[-25:-1]
    if len(loc) >= 12:
        edge = max(b[2] for b in loc) if direction > 0 else min(b[3] for b in loc)
        out['pd_breakout'] = direction * (last[4] / edge - 1) if edge else None             # source: > 0.003
    # eng-160: H_n for the retest variant - the edge of the 2h range BEFORE the move (the 24 bars before the last 3:
    # the 15-minute move that fired the signal), so the level is the range the pump broke, not a bar of the pump
    pre = bars[-27:-3]
    if len(pre) >= 12:
        out['pd_hn'] = max(b[2] for b in pre) if direction > 0 else min(b[3] for b in pre)
    trs = [max(b[2] - b[3], abs(b[2] - a[4]), abs(b[3] - a[4])) for a, b in zip(bars[-15:-1], bars[-14:])]
    if len(trs) >= 10:
        out['pd_atr5'] = sum(trs) / len(trs)                                                # ATR(14) of 5m
    closes = [b[4] for b in bars]
    if len(closes) >= 26:
        e20 = _ema(closes, 20)
        out['pd_above_ema20'] = int(direction * (closes[-1] - e20[-1]) > 0)
        out['pd_ema20_slope'] = direction * (e20[-1] / e20[-7] - 1) if e20[-7] else None   # source: > 0
    # impulse start: the first of the last 12 candles with volume >= 3x, range >= 2x, closing in the direction;
    # pullback = (impulse extreme - close) / (extreme - start price) (source: <= 0.30 shallow, > 0.50 no longer active)
    if base5 and med_rng:
        win = bars[-12:]
        start = next((i for i, b in enumerate(win) if (vr(b) or 0) >= 3 and (rr(b) or 0) >= 2
                      and direction * (b[4] - b[1]) > 0), None)
        if start is not None:
            s0 = win[start][1]
            ext = max(b[2] for b in win[start:]) if direction > 0 else min(b[3] for b in win[start:])
            leg = direction * (ext - s0)
            out['pd_pullback'] = direction * (ext - last[4]) / leg if leg > 0 else None
            before = bars[:len(bars) - 12 + start]
            pre = before[-72:-24] if len(before) >= 48 else []
            if pre and med_rng:
                hi, lo = max(b[2] for b in pre), min(b[3] for b in pre)
                mid = (hi + lo) / 2
                out['pd_quiet'] = (hi - lo) / mid / med_rng if mid else None              # 24-72 candles before
    # LATE (source: 12 candles >= 12%, volume >= 10x, range >= 4x), mirrored for a dump
    if bars[-13][4]:
        move12 = direction * (last[4] / bars[-13][4] - 1)
        out['pd_move12'] = move12
        out['pd_late'] = int(move12 >= 0.12 and (out.get('pd_vol_ratio_5m') or 0) >= 10
                             and (out.get('pd_range_ratio') or 0) >= 4)
    # SPIKE (source: one candle >= 5%, more than 70% retraced within the next 2 candles), last 30 minutes
    fail = 0
    tail = bars[-8:]
    for i in range(len(tail) - 2):
        a = tail[i]
        jump = direction * (a[4] - a[1])
        if a[1] and jump / a[1] >= 0.05:
            back = max(direction * (a[4] - b[4]) for b in tail[i + 1:i + 3])
            if back > 0.7 * jump:
                fail = 1
    out['pd_spike_fail'] = fail
    # the source's ACTIVATION / ACTIVE on this candle (journaled; the card's own trigger is PUMP / DUMP START)
    act = ((out.get('pd_vol_ratio_5m') or 0) >= 3 and (out.get('pd_range_ratio') or 0) >= 1.5
           and direction * (out.get('pd_move3') or 0) > 0
           and (out.get('pd_above_ema20') or (out.get('pd_breakout') or 0) > 0.003))
    active = ((out.get('pd_vol_cluster') or 0) >= 2 and (out.get('pd_range_cluster') or 0) >= 2
              and (direction * (out.get('pd_move3') or 0) >= 0.02 or direction * (out.get('pd_move6') or 0) >= 0.04)
              and (out.get('pd_green4') or 0) >= 3 and (out.get('pd_pullback') if out.get('pd_pullback') is not None else 1) <= 0.30
              and out.get('pd_above_ema20') and (out.get('pd_ema20_slope') or 0) > 0)
    out['pd_phase'] = ('LATE' if out.get('pd_late') else 'SPIKE_FAIL' if fail else 'ACTIVE' if active
                       else 'ACTIVATION' if act else 'NONE')
    return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in out.items() if v is not None}
```

### strategies/pd_features.py:167-187 `activation`

```python
def activation(minutes: Sequence[Sequence[float]], base1: Optional[float], direction: int) -> bool:
    """The source's ACTIVATION on the last CLOSED 5m bar of the ring: volume >= 3x the median 5m volume, range >= 1.5x
    the median 5m range, close above the bar 3 back, and close beyond EMA20 or a breakout of the previous 24 bars."""
    if not base1 or len(minutes) < 60:
        return False
    if (int(minutes[-1][0]) + MINUTE_MS) % FIVE_MS:
        return False                                  # only when a 5m bar just closed
    bars = bars_5m(minutes)
    if len(bars) < 26:
        return False
    b = bars[-1]
    rngs = [(x[2] - x[3]) / x[4] for x in bars[:-1] if x[4]]
    med = median(rngs) if rngs else 0
    if not med or not b[4] or b[5] < 3 * base1 * 5 or (b[2] - b[3]) / b[4] < 1.5 * med:
        return False
    if direction * (b[4] - bars[-4][4]) <= 0:
        return False
    e20 = _ema([x[4] for x in bars], 20)[-1]
    loc = bars[-25:-1]
    edge = max(x[2] for x in loc) if direction > 0 else min(x[3] for x in loc)
    return direction * (b[4] - e20) > 0 or direction * (b[4] / edge - 1) > 0.003
```

### strategies/pd_features.py:190-231 `extras`

```python
def extras(m5_rest: Sequence[Sequence[float]], minutes: Sequence[Sequence[float]],
           btc_minutes: Sequence[Sequence[float]], direction: int,
           btc_m5: Optional[Sequence[Sequence[float]]] = None) -> Dict:
    """eng-159c, from the other sources of the owner's research (read 2026-10-24):
    - pd_trades_ratio_5m: trades of the last closed 5m candle / the median of the previous 288 (La Morgia et al. 2020,
      'The Doge of Wall Street' 2023: StdTrades / rush orders jump at the pump's start); REST kline field n;
    - pd_price_vs_ma12h: close vs the 12h moving average of the open (Kamps & Kleinberg 2018 / the 2025 thresholding
      detector: price against a 12h moving average), signed by the direction;
    - pd_vs_btc: the coin's 30-minute move minus BTC's (the BOCD detector of RaibekTussupbekov judges an alt against
      BTC/USDT), signed by the direction."""
    out: Dict = {}
    rows = [r for r in m5_rest if len(r) > 7]
    if len(rows) >= 50:
        trades = [r[7] for r in rows]
        base = median(trades[-289:-1])
        if base >= 20:                   # a near-dead coin's ratio is noise, not a signal (review eng-159c)
            out['pd_trades_ratio_5m'] = trades[-1] / base
        opens = [r[1] for r in rows[-145:-1]]
        ma = sum(opens) / len(opens) if opens else None
        last = minutes[-1][4] if minutes else rows[-1][4]
        if ma:
            out['pd_price_vs_ma12h'] = direction * (last / ma - 1)
    if btc_m5 and len(rows) >= 60:
        # the BOCD detector's idea closer: the coin's 30-minute return minus beta x BTC's, beta from the PREVIOUS 5m
        # returns only (aligned by candle time, up to 288), so a high-beta alt moving with BTC is no anomaly
        bmap = {int(r[0]): r[4] for r in btc_m5}
        pairs = [(a[4], b[4], bmap.get(int(a[0])), bmap.get(int(b[0]))) for a, b in zip(rows[:-1], rows[1:])]
        rets = [(c1 / c0 - 1, b1 / b0 - 1) for c0, c1, b0, b1 in pairs if c0 and b0 and b1]
        hist = rets[-289:-6]
        if len(hist) >= 48:
            mx = sum(x for _, x in hist) / len(hist)
            my = sum(y for y, _ in hist) / len(hist)
            var = sum((x - mx) ** 2 for _, x in hist)
            beta = sum((x - mx) * (y - my) for y, x in hist) / var if var else 0.0
            b6, b0_ = bmap.get(int(rows[-1][0])), bmap.get(int(rows[-7][0]))
            if b6 and b0_ and rows[-7][4]:
                out['pd_btc_beta'] = beta
                out['pd_vs_btc_resid'] = direction * ((rows[-1][4] / rows[-7][4] - 1) - beta * (b6 / b0_ - 1))
    coin, btc = bars_5m(minutes), bars_5m(btc_minutes)
    if len(coin) >= 7 and len(btc) >= 7 and coin[-7][4] and btc[-7][4]:
        out['pd_vs_btc'] = direction * ((coin[-1][4] / coin[-7][4] - 1) - (btc[-1][4] / btc[-7][4] - 1))
    return {k: round(v, 6) for k, v in out.items()}
```

### strategies/pd_features.py:234-256 `ActivationLog`

```python
class ActivationLog:
    """First ACTIVATION per (coin, direction) - the detector's lead time (journal pd_activation_lead_s)."""

    def __init__(self, keep_ms: int = 2 * 3_600_000):
        self.first: Dict[tuple, int] = {}
        self.keep_ms = keep_ms

    def update(self, symbol: str, minutes, base1: Optional[float]) -> None:
        if not minutes:
            return
        ts = int(minutes[-1][0])
        for d in (1, -1):
            key = (symbol, d)
            old = self.first.get(key)
            if old is not None and ts - old > self.keep_ms:
                self.first.pop(key, None)
                old = None
            if old is None and activation(minutes, base1, d):
                self.first[key] = ts

    def lead_s(self, symbol: str, direction: int, signal_ms: int) -> Optional[float]:
        ts = self.first.pop((symbol, direction), None)
        return (signal_ms - ts) / 1000 if ts is not None and ts <= signal_ms else None
```

### strategies/loopside.py:64-114 `_pumps`

```python
    def _pumps(self, symbol: str, md, now_ms: int) -> List[Dict]:
        """The pump's start (every final minute) and top (every 15m close), cheap gates first (strategies.pump)."""
        from strategies.pump import dump_start, pump_start, pump_top
        minute = md.minute_closed_until
        if not minute or self._pump_checked.get(symbol) == minute:
            return []
        self._pump_checked[symbol] = minute
        minutes = self.minutes_of(symbol)
        if len(minutes) < 120:
            self._skip(symbol, 'pump', len(minutes), 120)
            return []
        out = []
        cfg = CONFIG.strategies
        from strategies.oi_build import _close_at
        from strategies import pd_features as pdf
        m15 = list(self.m15_of(symbol))
        base1 = pdf.volume_base_1m(m15)
        self._pd_activation.update(symbol, minutes, base1)        # eng-159: lead time of the detector
        tier0 = dict(md.tier0 or {})
        if base1:
            tier0['rvol_1m_med'] = float(minutes[-1][5]) / base1
        base15 = _close_at(minutes, int(minutes[-1][0]) - 15 * 60_000)     # by time (eng-74), None across a gap
        if base15 and minutes[-1][4] / base15 - 1 >= cfg.pump_start_min_pct:
            closes = [c[4] for c in self.m15_of(symbol)[-97:]]
            rets = [b / a - 1 for a, b in zip(closes, closes[1:]) if a]
            vol = (sum(r * r for r in rets) / len(rets)) ** 0.5 if len(rets) > 20 else None
            found = pump_start(minutes, tier0, vol, now_ms, list(md.h1 or ()))
            if found and (symbol, found['anchor_ts'] // 3_600_000) not in self._pump_fired:
                self._pump_fired.add((symbol, found['anchor_ts'] // 3_600_000))
                found.update(pdf.features(minutes, m15, 1))
                found['pd_activation_lead_s'] = self._pd_activation.lead_s(symbol, 1, int(found['event_ts']))
                out.append(found)
        if base15 and 1 - minutes[-1][4] / base15 >= cfg.pump_start_min_pct:
            # eng-157: the start of a dump (strategies.pump.dump_start)
            closes = [c[4] for c in self.m15_of(symbol)[-97:]]
            rets = [b / a - 1 for a, b in zip(closes, closes[1:]) if a]
            vol = (sum(r * r for r in rets) / len(rets)) ** 0.5 if len(rets) > 20 else None
            found = dump_start(minutes, tier0, vol, now_ms, list(md.h1 or ()))
            if found and (symbol, 'dstart', found['anchor_ts'] // 3_600_000) not in self._pump_fired:
                self._pump_fired.add((symbol, 'dstart', found['anchor_ts'] // 3_600_000))
                found.update(pdf.features(minutes, m15, -1))
                found['pd_activation_lead_s'] = self._pd_activation.lead_s(symbol, -1, int(found['event_ts']))
                out.append(found)
        if (minute + 60_000) % 900_000 == 0:
            window = [c for c in minutes if c[0] >= minute - 4 * 3_600_000]
            if window and max(c[2] for c in window) / min(c[3] for c in window) - 1 >= cfg.pump_top_min_pct:
                found = pump_top(minutes, md.tier0 or {}, minute + 60_000)
                if found and (symbol, 'top', found['anchor_ts']) not in self._pump_fired:
                    self._pump_fired.add((symbol, 'top', found['anchor_ts']))
                    out.append(found)
        return out
```

### smallcap.py:44-224 `SmallCapWatch`

```python
class SmallCapWatch:
    def __init__(self, fetcher):
        self.fetcher = fetcher
        self.rings: Dict[str, Deque[tuple]] = {}
        self.forming: Dict[str, tuple] = {}
        self.by_id: Dict[str, str] = {}             # 'KATUSDT' -> 'KAT/USDT:USDT'
        self.qv24: Dict[str, float] = {}
        self.h1: Dict[str, List] = {}               # the wide watch's closed 1h candles
        self.pending: List[Tuple[str, Dict]] = []   # signals for the next scan
        self._fired: set = set()
        from strategies.pd_features import ActivationLog
        self._activation = ActivationLog()          # eng-159: lead time (base: the 24h mean minute - no 15m history here)
        self._stream = None
        self._seeding: set = set()
        self.detections = 0
        self.checks = 0

    # ------------------------------------------------------------------ feed

    @property
    def symbols(self) -> List[str]:
        return list(self.by_id.values())

    def has(self, symbol: str) -> bool:
        return symbol in self.rings

    def minutes(self, symbol: str) -> List[List[float]]:
        ring = self.rings.get(symbol)
        return [list(c) for c in ring] if ring else []

    def price(self, symbol: str) -> Optional[float]:
        f = self.forming.get(symbol)
        ring = self.rings.get(symbol)
        now = time.time() * 1000
        if f is not None and now - f[8] <= 60_000:
            return f[4]
        if ring and now - (ring[-1][0] + MINUTE_MS) <= 120_000:
            return ring[-1][4]
        return None

    def on_kline(self, data) -> None:
        sym = self.by_id.get(data.get('s'))
        k = data.get('k') or {}
        if sym is None or not k:
            return
        try:
            row = (int(k['t']), float(k['o']), float(k['h']), float(k['l']), float(k['c']), float(k['q']),
                   float(k['Q']), float(k['v']))
        except (KeyError, TypeError, ValueError):
            return
        if not k.get('x'):
            self.forming[sym] = row + (time.time() * 1000,)
            return
        ring = self.rings.setdefault(sym, deque(maxlen=CONFIG.strategies.smallcap_minutes))
        if ring and ring[-1][0] >= row[0]:
            if ring[-1][0] == row[0]:
                ring[-1] = row
            return
        ring.append(row)
        self.forming.pop(sym, None)
        qv = self.qv24.get(sym)
        self._activation.update(sym, ring, qv / 1440 if qv else None)
        if len(ring) >= 120:
            asyncio.get_event_loop().create_task(self._check(sym))

    # ------------------------------------------------------------------ the coin list (from the wide watch)

    async def set_coins(self, wanted: List[Tuple[str, str, float]], h1: Dict[str, List]) -> None:
        """wanted: (unified symbol, Binance id, 24h quote volume) of the perpetuals outside the universe."""
        from venues import BinanceStream
        self.h1 = h1
        new = {bid: sym for sym, bid, _ in wanted}
        self.qv24 = {sym: qv for sym, _, qv in wanted}
        for sym in set(self.rings) - set(new.values()):
            self.rings.pop(sym, None)
            self.forming.pop(sym, None)
        self.by_id = new
        if self._stream is None:
            self._stream = BinanceStream(_Sink(self), self.fetcher.symbol_map, 'futures', [], 'Binance small caps 1m')
            await self._stream.start(dynamic=True)
        await self._stream.set_dynamic([f"{bid.lower()}@kline_1m" for bid in new])
        for sym, bid, _ in wanted:
            if sym not in self.rings and sym not in self._seeding:
                self._seeding.add(sym)
                asyncio.get_event_loop().create_task(self._seed(sym, bid))

    async def _seed(self, sym: str, bid: str) -> None:
        try:
            k = await self.fetcher._rest_call(self.fetcher.futures_exchange, 'fapiPublicGetKlines',
                                              {'symbol': bid, 'interval': '1m', 'limit': CONFIG.strategies.smallcap_minutes},
                                              priority=2, weight=2)
            now = time.time() * 1000
            rows = [(int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[7]), float(x[10]),
                     float(x[5])) for x in k or [] if int(x[6]) < now]
            ring = self.rings.setdefault(sym, deque(maxlen=CONFIG.strategies.smallcap_minutes))
            have = {r[0] for r in ring}
            merged = sorted([r for r in rows if r[0] not in have] + list(ring))
            ring.clear()
            ring.extend(merged[-CONFIG.strategies.smallcap_minutes:])
        except Exception as e:
            logger.debug(f"small caps: seed {sym} failed: {e!r}")
        finally:
            self._seeding.discard(sym)

    # ------------------------------------------------------------------ detection

    def _atr_15m(self, sym: str) -> Optional[float]:
        h1 = self.h1.get(sym) or []
        if len(h1) < 15:
            return None
        trs = [max(b[2] - b[3], abs(b[2] - a[4]), abs(b[3] - a[4])) for a, b in zip(h1[-15:-1], h1[-14:])]
        return sum(trs) / len(trs) / 2 if trs else None

    async def _check(self, sym: str) -> None:
        cfg = CONFIG.strategies
        ring = self.rings.get(sym)
        if not ring:
            return
        last = ring[-1]
        base = next((c for c in reversed(ring) if c[0] == last[0] - 15 * MINUTE_MS), None)
        if base is None or not base[4]:
            return
        move = last[4] / base[4] - 1
        if abs(move) < cfg.pump_start_min_pct:
            return                                           # the cheap gate: nothing moves for most minutes
        key = (sym, int(base[0]) // 3_600_000, 1 if move > 0 else -1)
        if key in self._fired:
            return
        self.checks += 1
        try:
            from strategies.pump import dump_start, pump_start
            bid = next(b for b, s in self.by_id.items() if s == sym)
            k15 = await self.fetcher._rest_call(self.fetcher.futures_exchange, 'fapiPublicGetKlines',
                                                {'symbol': bid, 'interval': '15m', 'limit': 98}, priority=1, weight=1)
            closes = [float(x[4]) for x in k15 or []][:-1]
            m15 = [[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[7])] for x in (k15 or [])[:-1]]
            from strategies import pd_features as pdf
            base1 = pdf.volume_base_1m(m15)
            rets = [b / a - 1 for a, b in zip(closes, closes[1:]) if a]
            vol = (sum(r * r for r in rets) / len(rets)) ** 0.5 if len(rets) > 20 else None
            oi = await self.fetcher._rest_call(self.fetcher.futures_exchange, 'fapiDataGetOpenInterestHist',
                                               {'symbol': bid, 'period': '5m', 'limit': 2}, priority=1, weight=0)
            oi_vals = [float(x.get('sumOpenInterest') or 0) for x in oi or []]
            oi_change = oi_vals[-1] / oi_vals[0] - 1 if len(oi_vals) == 2 and oi_vals[0] else 0.0
            minutes = [list(c) for c in ring]
            now_ms = int(last[0]) + MINUTE_MS
            flow = sum(2 * c[6] - c[5] for c in minutes if c[0] + MINUTE_MS > now_ms - 300_000)
            avg_minute = (self.qv24.get(sym) or 0) / 1440
            rvol = last[5] / avg_minute if avg_minute else 0.0
            m = {'rvol_1m': rvol, 'oi_change_5m': oi_change, 'spot_cvd_5m': flow}
            if base1:
                m['rvol_1m_med'] = last[5] / base1       # eng-159: the 24h median minute
            h1 = self.h1.get(sym) or []
            found = (pump_start if move > 0 else dump_start)(minutes, m, vol, now_ms, h1)
            rvol = m.get('rvol_1m_med') or rvol
            logger.info(f"Small caps: {sym} {move:+.1%} in 15m - RVOL {rvol:.1f}, OI 5m {oi_change:+.2%}, futures flow "
                        f"{flow:+,.0f}, vol15 {vol or 0:.3%} -> {found['setup'] if found else 'no setup'}")
            if not found:
                return
            self._fired.add(key)
            atr = self._atr_15m(sym)
            if not atr:
                logger.info(f"Small caps: {sym} {found['setup']} skipped - no 1h history for the ATR")
                return
            self.detections += 1
            found.update(pdf.features(minutes, m15, found['direction']))
            found['pd_activation_lead_s'] = self._activation.lead_s(sym, found['direction'], int(found['event_ts']))
            sig = dict(found, is_setup=True, is_structured=False, is_tier_0_anomaly=False, active_phases=[],
                       long_score=0, short_score=0, alert_type='LONG' if found['direction'] > 0 else 'SHORT',
                       atr_15m=atr, volume_24h=self.qv24.get(sym), smallcap=True, flow_src='futures',
                       strategy='pump')
            self.pending.append((sym, sig))
        except Exception as e:
            logger.warning(f"Small caps: check {sym} failed: {e!r}")

    def drain(self) -> List[Tuple[str, Dict]]:
        out, self.pending = self.pending, []
        return out

    def health(self) -> str:
        return f"small caps {len(self.rings)} coins, {self.checks} checks, {self.detections} setups"
```

### scanner.py:1451-1465 `_btc_m5`

```python
    async def _btc_m5(self) -> List:
        """eng-160b: BTC's last 290 closed 5m candles for the beta residual (pd_vs_btc_resid), cached per 5 minutes."""
        now = time.time() * 1000
        cached = getattr(self, '_btc_m5_cache', None)
        if cached and now - cached[0] < 300_000:
            return cached[1]
        try:
            k = await self.fetcher._rest_call(self.fetcher.futures_exchange, 'fapiPublicGetKlines',
                                              {'symbol': 'BTCUSDT', 'interval': '5m', 'limit': 290}, priority=1, weight=2)
            rows = [[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4])] for x in k or [] if int(x[6]) < now]
            self._btc_m5_cache = (now, rows)
            return rows
        except Exception as e:
            logger.debug(f"BTC 5m for the beta residual: {e!r}")
            return []
```

### scanner.py:1467-1494 `_pd_enrich`

```python
    async def _pd_enrich(self, symbol: str, sig: Dict) -> None:
        """eng-159: the detector's features on the source's 24h baselines - the last 289 closed 5m candles (REST, once
        per PUMP / DUMP START) + the 1m ring; the activation lead time found by the detector is kept."""
        try:
            from strategies import pd_features as pdf
            bid = self.fetcher.futures_exchange.market(symbol)['id']
            k = await self.fetcher._rest_call(self.fetcher.futures_exchange, 'fapiPublicGetKlines',
                                              {'symbol': bid, 'interval': '5m', 'limit': 290}, priority=1, weight=2)
            now = time.time() * 1000
            m5 = [[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[7]), float(x[10]), float(x[8])]
                  for x in k or [] if int(x[6]) < now]
            lead = sig.get('pd_activation_lead_s')
            minutes = self._minute_candles(symbol)
            feats = pdf.features(minutes, [], int(sig['direction']), [r[:7] for r in m5])
            btc_m5 = await self._btc_m5()
            feats.update(pdf.extras(m5, minutes, self._minute_candles('BTC/USDT:USDT'), int(sig['direction']), btc_m5))
            if feats:
                sig.update(feats)
                sig['pd_activation_lead_s'] = lead
            logger.info(f"PD features {symbol} {sig['setup']}: phase {sig.get('pd_phase')}, vol x{sig.get('pd_vol_ratio_5m', 0):.1f} "
                        f"(cluster {sig.get('pd_vol_cluster')}), range x{sig.get('pd_range_ratio', 0):.1f} "
                        f"(cluster {sig.get('pd_range_cluster')}), move3 {sig.get('pd_move3', 0):+.1%}, "
                        f"breakout {sig.get('pd_breakout', 0):+.2%}, trades x{sig.get('pd_trades_ratio_5m', 0):.1f}, "
                        f"vs 12h MA {sig.get('pd_price_vs_ma12h', 0):+.1%}, vs BTC {sig.get('pd_vs_btc', 0):+.1%} "
                        f"(resid {sig.get('pd_vs_btc_resid', 0):+.1%}, beta {sig.get('pd_btc_beta', 0):.2f}), "
                        f"rush z {sig.get('rush_z_30s', 0):.1f}, base {sig.get('pd_base_n')} x 5m")
        except Exception as e:
            logger.warning(f"PD features {symbol}: {e!r}")
```

### scanner.py:1496-1502 `_minute_candles`

```python
    def _minute_candles(self, symbol: str):
        """FINAL futures 1m candles only: entry triggers are closes, and a running minute's close is just the live price."""
        md = self.market_data.get(symbol)
        if md is None:
            # eng-158: a small cap's card is fed by the small-cap watch
            return self.smallcap.minutes(symbol) if self.smallcap is not None else []
        return [c for c in list(md.minute_klines) if c[0] <= md.minute_closed_until]
```

### scanner.py:1506-1532 `_price_of`

```python
    def _price_of(self, symbol: str) -> Optional[float]:
        """
        Freshest futures price: the latest ticker sample or the 1m kline close, whichever is newer. None when both
        are older than PRICE_MAX_AGE_SEC, so a stalled stream never drives SL/TP decisions with a frozen price.
        """
        md = self.market_data.get(symbol)
        if md is None:
            return self.smallcap.price(symbol) if self.smallcap is not None else None    # eng-158
        now_ms = time.time() * 1000
        candidates = []
        if md.ticker_samples:
            ts, price, _ = md.ticker_samples[-1]
            candidates.append((ts, price))
        if md.minute_klines:
            candle = md.minute_klines[-1]
            # audit C03: the kline's price is dated by its last stream event; without one, a final candle by its close
            # and a forming one by its open (open + 60s made a stale forming candle 'now' and beat a newer trade)
            ev_open, ev_ms = getattr(md, 'kline_event', (0, 0.0))
            if ev_open == candle[0] and ev_ms:
                ts = min(now_ms, ev_ms)
            elif candle[0] <= getattr(md, 'minute_closed_until', 0):
                ts = min(now_ms, candle[0] + 60_000)
            else:
                ts = candle[0]
            candidates.append((ts, candle[4]))
        fresh = [(ts, p) for ts, p in candidates if p and now_ms - ts <= self.PRICE_MAX_AGE_SEC * 1000]
        return float(max(fresh)[1]) if fresh else None
```

### scanner.py:925-992 `wide_watch_loop`

```python
    async def wide_watch_loop(self):
        """
        eng-57: the universe holds 70 coins with complete data (a spot pair, >= 2 other venues, >= $10M): the biggest
        small-cap pumps / dumps (no spot pair, a fresh listing) were never seen. Once an hour (a few minutes after the
        close) the 1h candles of every other USDT perpetual >= wide_min_volume run the pump / dump monitor (dashboard)
        and the dump-bounce rule; its events are JOURNALED (vetoed 'outside_universe': no streams there, so no card /
        demo trade) - the forward test of the research rule on the whole market it was measured on.
        """
        from strategies.pump import MAJORS, dump_bounce
        cfg = CONFIG.strategies
        await asyncio.sleep(600)
        while self._running:
            started = time.time()
            try:
                rows = await self.fetcher._rest_call(self.fetcher.futures_exchange, 'fapiPublicGetTicker24hr',
                                                     priority=2, weight=40)
                by_id = getattr(self.fetcher.futures_exchange, 'markets_by_id', {}) or {}
                wanted = []
                qv: Dict[str, float] = {}
                for t in rows or []:
                    m = by_id.get(t.get('symbol'))
                    m = m[0] if isinstance(m, list) else m
                    if not m or not m.get('swap') or m.get('quote') != 'USDT' or m['symbol'] in self.market_data:
                        continue
                    if (m.get('info', {}).get('underlyingType') in CONFIG.exchange.excluded_underlying_types or
                            m.get('base') in CONFIG.exchange.excluded_bases or m.get('base') in MAJORS):
                        continue
                    if float(t.get('quoteVolume') or 0) >= cfg.wide_min_volume:
                        wanted.append((m['symbol'], t['symbol'], float(t.get('lastPrice') or 0)))
                        qv[m['symbol']] = float(t.get('quoteVolume') or 0)
                sem = asyncio.Semaphore(4)

                async def one(sym, bid, last):
                    async with sem:
                        try:
                            k = await self.fetcher._rest_call(self.fetcher.futures_exchange, 'fapiPublicGetKlines',
                                                              {'symbol': bid, 'interval': '1h', 'limit': 200},
                                                              priority=2, weight=2)
                        except Exception as e:
                            logger.debug(f"wide watch: 1h candles failed for {sym}: {e}")
                            return
                    now_ms = time.time() * 1000
                    h1 = [[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[7]), float(x[10])]
                          for x in k or [] if int(x[6]) < now_ms]
                    self.wide_h1[sym] = h1
                    found = dump_bounce(h1, int(now_ms)) if len(h1) >= 190 else None
                    if found and (sym, found['anchor_ts']) not in self._wide_fired:
                        self._wide_fired.add((sym, found['anchor_ts']))
                        sig = dict(found, is_setup=True, is_structured=False, is_tier_0_anomaly=False,
                                   active_phases=[], long_score=0, short_score=0, alert_type='SHORT',
                                   card_veto='outside_universe')
                        logger.info(f"Wide watch: {sym} {found['setup']} - {found['setup_note']} (journal only)")
                        await self.journal.arecord([(sym, sig)], {sym: last or h1[-1][4]})

                await asyncio.gather(*(one(*w) for w in wanted))
                if self.smallcap is not None:
                    # eng-158: the same coins on the live 1m watch (one dynamic Binance connection)
                    await self.smallcap.set_coins([(s, b, qv.get(s, 0.0)) for s, b, _ in wanted], self.wide_h1)
                for sym in [s for s in self.wide_h1 if s in self.market_data or s not in {w[0] for w in wanted}]:
                    self.wide_h1.pop(sym, None)
                logger.info(f"Wide watch: {len(wanted)} perpetuals outside the universe scanned in "
                            f"{time.time() - started:.0f}s")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"Wide watch failed: {e}")
            now = time.time()
            await asyncio.sleep(max(600.0, 3600 - now % 3600 + 240))
```

### signal_book.py:180-193 `shadow_veto`

```python
def shadow_veto(sig: Dict, reason: Optional[str]) -> Optional[str]:
    """eng-101: a reason in strategies.shadow_vetoes does not block - it is added to sig['shadow_veto'] and None is
    returned ('no_*' covers the detectors' required confirmations, not the structural no_data / no_leg ...)."""
    if not reason:
        return reason
    names = CONFIG.strategies.shadow_vetoes
    # eng-138: a missing entry CONFIRMATION (confirm.missing: 'no_<confirmation>', a required / journal-promoted one)
    # stays a filter in shadow as before; a setup's own required part (no_spring_test, po3_bias_required, ...) blocks
    conf = '<confirmations>' in names and reason.startswith('no_') and reason[3:] in confirm.required_names()
    if reason in names or conf or ('no_*' in names and reason.startswith('no_') and reason not in _REAL_NO):
        have = set(filter(None, (sig.get('shadow_veto') or '').split(',')))
        sig['shadow_veto'] = ','.join(sorted(have | {reason}))
        return None
    return reason
```

### signal_book.py:1352-1375 `_confirmation_entry`

```python
    def _confirmation_entry(self, s: TrackedSignal, price: float, now_ms: int,
                            confirm_of: Optional[ConfirmCheck]) -> Optional[TrackedSignal]:
        """
        Entry at the setup's confirmation (the closed candle that confirmed it), at the current price: taken when R:R
        to TP1 allows it, else the card waits in its zone for a trigger.
        """
        levels = entry_levels(s.plan, price, None, s.direction)
        if not levels or s.direction * (price - levels['sl']) <= 0:
            return None
        levels['zone_src'] = 'setup confirmation'
        levels['range_pos'] = range_position(s.plan.get('dealing_range'), levels['entry'], s.direction)
        anchor = s.plan.get('anchor') or {}
        # the confirming event: a breakout's candle, a reversed leg's end, else the anchor
        since = int(anchor.get('break_ts') or anchor.get('end_ts') or anchor.get('ts') or now_ms - 900_000)
        # a reversal's confirmation follows the reversed leg's end: that is its extreme
        extreme_ms = int(anchor['end_ts']) if anchor.get('end_ts') and s.mode in confirm.REVERSALS else None
        confirms = confirm_of(s.symbol, s.mode, s.direction, since, now_ms, extreme_ms) if confirm_of else {}
        # an entry AT the signal's close (VA80, AUCTION, BB W / M, cup): the method's own rule puts that close past
        # its level by design - journaled, not vetoed (review of eng-147)
        self._overshoot(s, levels['entry'], levels, block=False)
        reason = shadow_veto(s.sig, confirm.missing(s.mode, confirms))
        if reason is None and CONFIG.levels.veto_low_rr and levels.get('low_rr'):
            reason = 'low_rr'
        return self._enter(s, levels, now_ms, reason, confirms)
```

### signal_book.py:1560-1579 `_retest_variants`

```python
    def _retest_variants(self, candles_of, now_ms: int) -> None:
        """
        eng-160 (the owner, trade geometry scenario B): the retest entry of a PUMP / DUMP START journaled beside the live
        confirmation entry as 'variant_retest' (never traded). Every such card with a plan is watched - entered, vetoed
        low_rr or expired alike (a variant read only on entered cards would be survivorship) - for 2h of 5m bars after
        the signal: price comes back into H_n +- 0.25 ATR(5m) (H_n = the edge of the 2h range the move broke, pd_hn),
        and a 5m bar closes back beyond H_n -> entry at that close with the plan's own stop / targets. A close beyond
        H_n -+ 0.25 ATR on the wrong side breaks the structure: no retest entry.
        """
        for s in self.signals.values():
            if s.group_key in self.RETEST_SETUPS and s.plan and (s.sig or {}).get('pd_hn') \
                    and 'variant_retest' not in s.variants_done and id(s) not in self._retest_watch:
                self._retest_watch[id(s)] = s
        for key, s in list(self._retest_watch.items()):
            try:
                if self._retest_variant(s, candles_of, now_ms):
                    self._retest_watch.pop(key, None)
            except Exception as e:
                logger.warning(f"Retest variant {s.symbol} {s.group_key}: {e!r}")
                self._retest_watch.pop(key, None)
```

### signal_book.py:1581-1615 `_retest_variant`

```python
    def _retest_variant(self, s: 'TrackedSignal', candles_of, now_ms: int) -> bool:
        """True when this card's retest is settled (journaled, broken, stale or out of time)."""
        from strategies.pd_features import FIVE_MS, bars_5m
        sig, d = s.sig or {}, s.direction
        hn, atr = sig.get('pd_hn'), sig.get('pd_atr5')
        start = int(sig.get('event_ts') or 0)
        if not hn or not atr or not start or not candles_of:
            s.variants_done.append('variant_retest')
            return True
        bars = [b for b in bars_5m(list(candles_of(s.symbol))) if b[0] >= start // FIVE_MS * FIVE_MS + FIVE_MS]
        band = 0.25 * atr
        touched = False
        for i, b in enumerate(bars[:self.RETEST_BARS]):
            close_ms = int(b[0]) + FIVE_MS
            if d * (b[4] - (hn - d * band)) < 0:
                s.variants_done.append('variant_retest')          # closed through the zone: the breakout failed
                return True
            near = b[3] if d > 0 else b[2]
            if d * (near - (hn + d * band)) <= 0:
                touched = True
            if touched and d * (b[4] - hn) > 0:
                if now_ms - close_ms > FIVE_MS + 2 * MINUTE_MS:
                    s.variants_done.append('variant_retest')      # a stale bar (restart / gap): not journaled
                    return True
                levels = entry_levels(s.plan, float(b[4]), None, d)
                if levels and d * (levels['entry'] - levels['sl']) > 0:
                    levels['zone_src'] = f"retest of the 2h range edge {hn:.6g} +- 0.25 ATR(5m) (variant)"
                    self._variant(s, 'variant_retest', levels, close_ms)
                else:
                    s.variants_done.append('variant_retest')
                return True
        if len(bars) >= self.RETEST_BARS or now_ms - start > (self.RETEST_BARS + 2) * FIVE_MS:
            s.variants_done.append('variant_retest')              # no retest within 2h
            return True
        return False
```

### signal_book.py:1549-1555 `_variant`

```python
    def _variant(self, s: TrackedSignal, name: str, levels: Dict, now_ms: int, limit: bool = False):
        """eng-149: a shadow variant of the card journaled as a vetoed entry `name` (never traded), once per card."""
        s.variants_done.append(name)
        shadow = copy.copy(s)
        shadow.levels, shadow.entered_at, shadow.vetoed = levels, now_ms / 1000, name
        shadow.of_confirm, shadow.confirms, shadow.limit_variant = None, {}, limit
        self._extra.append(shadow)
```

### signal_book.py:753-847 `_trail`

```python
    def _trail(self, s: TrackedSignal, candles_of, hi: Optional[float] = None, lo: Optional[float] = None) -> None:
        """
        Stop management of an open trade, only ever toward the trade (a RESTOP event moves the demo's stop):
        - plan 'sar': Wilder's Parabolic SAR of the plan's bars (BB1 4h);
        - plan 'trail_pct': a % trail behind the best price;
        - plan 'be_after_r': break-even + costs after +R (globally off since eng-111; ORB sets it, eng-154);
        - the partial at +1R: off (partial_share 0 since eng-123);
        - plan 'trail_after_tp1' (half at TP1, then the EMA20 trail): off - _plan resets it while
          strategies.ema_trail_after_tp1 is False (eng-111); only band_exit plans keep it.
        """
        plan, lv, d = s.plan or {}, s.levels, s.direction
        sar = plan.get('sar')
        if sar and candles_of and lv.get('sl'):
            # eng-127, Bollinger's Method I: Wilder's Parabolic SAR of the plan's bars, stepped once per CLOSED bar
            # since the signal; the stop follows it (the SAR's own stop-and-reverse touch is the stop order)
            from strategies.maniac import parabolic_sar_step
            size = int(sar['tf_min']) * MINUTE_MS
            # audit A12: as of the minute being managed (s.managed_ms = its end): a bar that closes later must not
            # move the stop that minute is judged against
            asof = s.managed_ms or None
            minutes = [m for m in candles_of(s.symbol) if asof is None or m[0] + MINUTE_MS <= asof]
            if sar.pop('start_at_sl', False):
                # ORB: the SAR starts at the trade's final stop when that is farther than the plan's (a pool / the
                # min-stop floor) - the first bar must not take the buffer away
                sar['sar'] = min(sar['sar'], lv['sl']) if d > 0 else max(sar['sar'], lv['sl'])
            if minutes:
                done = (int(minutes[-1][0]) + MINUTE_MS) // size * size
                bars = [b for b in _resample(s.symbol, minutes, int(sar['tf_min']), done) if sar['last_ts'] < b[0] and b[0] + size <= done]
                for b in bars:
                    nxt, ep, af, stopped = parabolic_sar_step(sar['sar'], sar['ep'], sar['af'], d, b[2], b[3],
                                                              prev_hi=sar.get('prev_hi'), prev_lo=sar.get('prev_lo'))
                    sar.update(sar=nxt, ep=ep, af=af, last_ts=int(b[0]), prev_hi=float(b[2]), prev_lo=float(b[3]))
                    if stopped:
                        break
                if d * (sar['sar'] - lv['sl']) > 0:
                    lv['sl'] = sar['sar']
                    lv['sl_src'] = f"Parabolic SAR (AF {sar['af']:.2f})"
                    self.events.append((s, 'RESTOP'))
            return
        pct = plan.get('trail_pct')
        if pct and hi is not None and lo is not None and lv.get('sl'):
            # eng-88: a percentage trailing stop behind the best price since the entry (OI build), only toward the
            # trade; moved in steps of >= 0.25% of the price so the demo's stop is not re-placed every minute
            best = hi if d > 0 else lo
            prev = plan.get('trail_best')
            plan['trail_best'] = best if prev is None else (max(prev, best) if d > 0 else min(prev, best))
            new = plan['trail_best'] * (1 - d * pct)
            if d * (new - lv['sl']) > 0.0025 * plan['trail_best']:
                lv['sl'] = new
                lv['sl_src'] = f'trailing {pct:.0%} behind the best price'
                self.events.append((s, 'RESTOP'))
            return
        be_r = plan.get('be_after_r')
        if be_r is None and CONFIG.strategies.be_after_1r:
            be_r = 1.0          # eng-155: cards opened before the flag (restored from the state) get it too
        if hi is not None and lo is not None and lv.get('entry') and lv.get('sl'):
            risk = lv.get('risk0') or abs(lv['entry'] - lv['sl'])
            fav = (hi - lv['entry']) if d > 0 else (lv['entry'] - lo)
            # eng-105 (the owner's rule, independent of break-even since eng-111): the partial at +1R (the demo's tp0)
            if risk and fav >= CONFIG.executor.partial_r * risk and CONFIG.executor.partial_share \
                    and not plan.get('p1r_done') and not s.units and (plan.get('no_tp') or not lv.get('tp1') or
                                                                      d * (lv['tp1'] - lv['entry']) > risk * CONFIG.executor.partial_r):
                plan['p1r_done'] = True
                s.part_ms.setdefault('p1r', int(s.managed_ms or 0))
                self.events.append((s, 'PARTIAL'))     # eng-155: the demo takes the half if its tp0 has not
            if be_r and risk and fav >= be_r * risk:
                # eng-84: the stop to break-even + costs once price traded +be_r R its way (off by default, eng-111)
                be = lv['entry'] * (1 + d * BE_COST)
                if d * (be - lv['sl']) > 0:
                    lv['sl'] = be
                    lv['sl_src'] = f'break-even + costs after +{be_r:g}R'
                    self.events.append((s, 'RESTOP'))
            if not plan.get('trail_after_tp1'):
                return
        if not plan.get('trail_after_tp1') or s.best_target < 1 or not candles_of:
            return
        # eng-84: break-even INCLUDING the round trip's costs (fees + slippage), not the bare entry
        be = lv['entry'] * (1 + d * BE_COST)
        new = max(lv['sl'], be) if d > 0 else min(lv['sl'], be)
        tf = int((s.plan or {}).get('trigger_minutes') or 5)
        # as of the minute being managed (review of 6b771ba: the whole buffer let later bars move an earlier stop)
        asof = s.managed_ms or None
        minutes = [m for m in candles_of(s.symbol) if asof is None or m[0] + MINUTE_MS <= asof]
        bars = _resample(s.symbol, minutes, tf, minutes[-1][0] + MINUTE_MS) if minutes else []
        if len(bars) >= 20:
            alpha, ema = 2 / 21, bars[0][4]
            for b in bars[1:]:
                ema += alpha * (b[4] - ema)
            if d * (bars[-1][4] - ema) > 0:
                new = max(new, ema) if d > 0 else min(new, ema)
        step = 0.1 * (lv.get('risk0') or abs(lv['entry'] - lv['sl']))
        if d * (new - lv['sl']) > step or (d * (new - lv['sl']) > 0 and d * (lv['sl'] - lv['entry']) < 0):
            lv['sl'] = new
            lv['sl_src'] = 'trailing: entry / EMA20 after TP1'
            self.events.append((s, 'RESTOP'))
```

### executor.py:377-393 `exit_parts`

```python
    def exit_parts(self, ex, trade: Dict, qty: float, trail: bool, no_tp: bool):
        """eng-105: partial_share of the position at +partial_r R (trade['tp0']), the rest by tp_parts; the plain
        tp_parts when the plan's TP1 is already nearer than that (TP1 is the partial then)."""
        cfg = CONFIG.executor
        d, fill, sl = trade['direction'], trade.get('entry_fill'), trade.get('sl')
        if not cfg.partial_share or not fill or not sl or trade.get('units'):
            return self.tp_parts(ex, trade['symbol'], qty, trail, no_tp)
        p1r = fill + d * cfg.partial_r * abs(fill - sl)
        tp1 = trade.get('tp1')
        if not no_tp and tp1 and d * (tp1 - p1r) <= 0:
            return self.tp_parts(ex, trade['symbol'], qty, trail, no_tp)
        half = float(ex.amount_to_precision(trade['symbol'], qty * cfg.partial_share))
        if half <= 0:
            return self.tp_parts(ex, trade['symbol'], qty, trail, no_tp)
        trade['tp0'] = p1r
        rest = float(ex.amount_to_precision(trade['symbol'], qty - half))
        return [(0, half)] + list(self.tp_parts(ex, trade['symbol'], rest, trail, no_tp))
```

### executor.py:1146-1197 `on_partial`

```python
    async def on_partial(self, s) -> None:
        """eng-155: the card went +partial_r R - partial_share of the position out. A trade opened with its tp0 order
        (exit_parts) has usually given it already (the position is down to the rest: only marked); a trade opened
        before partials were on has none - its take-profits are cancelled, the half closed at market (it may be well
        past +1R by then) and the take-profits re-placed for the rest. The stop is never touched here."""
        cfg = CONFIG.executor
        if not self.enabled or not s.entered_at or not cfg.partial_share:
            return
        card_id = f"{s.symbol}|{s.group_key}|{int(s.entered_at)}"
        trade = self.open.get(card_id) or self.open.get(f"{s.symbol}|{s.group_key}|c{int(s.created)}")
        if trade is None or trade.get('partial_done') or trade.get('units') or not trade.get('qty'):
            return
        async with self._lock:
            if all(t is not trade for t in self.open.values()):
                return
            try:
                ex = await self._exchange()
                symbol, d, qty = trade['symbol'], trade['direction'], float(trade['qty'])
                rest_share = 1 - cfg.partial_share
                left = await self._position_qty(symbol)
                if 0 < left <= qty * (rest_share + 0.05):
                    done = 'already out by its tp0'
                elif left > 0:
                    for o in await ex.fetch_open_orders(symbol):
                        if not self._is_stop(o):
                            try:
                                await ex.cancel_order(o['id'], symbol)
                            except Exception as e:
                                errors.report('executor.on_partial', e, f"Demo partial {symbol}: cancel {o.get('id')}")
                    left = await self._position_qty(symbol)
                    if left <= qty * (rest_share + 0.05):
                        done = 'out by its tp0 meanwhile'
                    else:
                        # down to rest_share of the ORIGINAL size: a trade whose TP1 third already went out keeps
                        # its half, not 1/6 (live APE 2026-10-24: half of the original closed from 2/3 left)
                        half = float(ex.amount_to_precision(symbol, left - qty * rest_share))
                        if half > 0:
                            await ex.create_order(symbol, 'market', 'sell' if d > 0 else 'buy', half, None,
                                                  {'reduceOnly': True})
                        done = f"{half} closed at market"
                    rest = await self._position_qty(symbol)
                    if rest > 0:
                        await self._place_tps(trade, self.tp_parts(ex, symbol, rest, bool(trade.get('trail')),
                                                                   bool(trade.get('no_tp'))))
                else:
                    return
                trade['partial_done'] = 1
                with sqlite3.connect(self.db_path) as c:
                    c.execute("UPDATE demo_trades SET partial_done = 1 WHERE id = ?", (trade['id'],))
                logger.info(f"Demo PARTIAL {symbol}: {done}")
            except Exception as e:
                logger.warning(f"Demo partial {s.symbol}: {e!r}")
```

### executor.py:1111-1144 `on_restop`

```python
    async def on_restop(self, s) -> None:
        """eng-58: the card trailed its stop (after TP1: the entry, then the EMA20): the remaining position's stop is
        moved on BingX (its TP1 half is already out, so no take-profit is left to re-place)."""
        if not self.enabled or not s.entered_at:
            return
        card_id = f"{s.symbol}|{s.group_key}|{int(s.entered_at)}"
        # eng-84: a trade entered by a resting limit is keyed by the waiting card (c<created>) - it was never restopped
        trade = self.open.get(card_id) or self.open.get(f"{s.symbol}|{s.group_key}|c{int(s.created)}")
        if trade is None or (getattr(s, 'plan', None) or {}).get('no_stop'):
            return
        async with self._lock:
            # audit C01: the trade may have been closed while this task waited for the lock
            if all(t is not trade for t in self.open.values()):
                return
            try:
                symbol, d = trade['symbol'], trade['direction']
                left = await self._position_qty(symbol)
                if left <= 0:
                    return
                scale = float(trade.get('scale') or 0.0)
                if not scale and trade.get('entry_plan') and s.levels.get('entry'):
                    scale = float(trade['entry_plan']) / float(s.levels['entry'])
                    trade['scale'] = scale
                scale = scale or 1.0
                # eng-85: the new stop first, then the old stop(s) by id - the cancel-all first left the position naked
                # whenever the new stop failed, and took TP2 / TP3 of the thirds plans with it for good
                new = await self._place_stop(symbol, d, left, s.levels['sl'] * scale)
                await self._cancel_orders(symbol, keep=new.get('id'), stops_only=True)
                trade['sl'] = s.levels['sl'] * scale
                with sqlite3.connect(self.db_path) as c:     # the stop guard restores THIS stop after a restart
                    c.execute("UPDATE demo_trades SET sl = ? WHERE id = ?", (trade['sl'], trade['id']))
                logger.info(f"Demo RESTOP {symbol}: stop {s.levels['sl'] * scale:.6g} for {left}")
            except Exception as e:
                logger.warning(f"Demo restop {s.symbol}: {e!r}")
```

### strategies/geometry.py:557-599 `stop_levels`

```python
def stop_levels(plan: Dict, entry: float, extreme: Optional[float], direction: int) -> Tuple[float, str]:
    """
    The stop: beyond the strategy's reference (the anchor's extreme / the range middle / the trigger's swing) and a
    stop pool just behind it, then the ATR buffer, never closer than the stop floor.
    """
    cfg = CONFIG.levels
    atr = plan['atr']
    zones: List[Zone] = plan.get('zones') or []
    moved = False
    if plan.get('stop_mid') is not None:
        base, src = plan['stop_mid'], plan.get('stop_mid_src', 'range middle')
    else:
        # the farthest of the strategy's structural reference (a zone's edge, the anchor's extreme) and the deepest
        # wick that tested it since price came into the zone (the trigger's extreme)
        ref, label = plan.get('stop_ref'), plan.get('stop_ref_src') or 'beyond the swing'
        if ref is None or (extreme is not None and direction * (ref - extreme) > 0):
            if ref is not None:
                label = 'beyond the test wick'
            ref = extreme
        prot = plan.get('protected')
        if prot is not None and direction * (entry - prot) > 0 and (ref is None or direction * (ref - prot) > 0):
            # ICT: the stop beyond the swing that broke structure, not right behind an unswept pool
            ref, label = prot, 'beyond the protected swing (BOS)'
        base, src = stop_beyond(zones, ref, entry, direction, plan.get('leg_atr') or atr, label, plan.get('symbol'),
                                farthest=bool(plan.get('stop_farthest')))
        moved = ref is not None and base != ref
    kind = kind_at(zones, base) or kind_of_label(src, plan.get('tf', '15m'))
    measured = overshoot(plan.get('symbol'), kind, base)
    pad, how = zone_pad(plan, measured, moved)
    if pad is not None:
        # beyond the level by its measured pierce or the structure timeframe's ATR buffer, whichever is wider; a stop
        # so far that it does not pay is a wrong entry (low_rr), not a reason to move it closer
        stop, src = base - direction * pad, f"{src} + {how} {pad / base:.2%}"
    else:
        stop = base - direction * cfg.stop_buffer_atr * (plan.get('leg_atr') or atr)
    # the floor in the structure's own ATR too (a 1h / 4h leg's stop floored by the 15m ATR sat inside its noise)
    # eng-58: the volatility floor holds with the pierce model too (it was skipped whenever the model existed - i.e.
    # always - while the docs and levels.min_leg_atr assumed it; live eng-6: stops < 1 ATR hit on 8 of 10 entries)
    floor = stop_floor(max(atr, plan.get('leg_atr') or 0.0, plan.get('tf_atr') or 0.0), plan.get('recent_atr'))
    if direction * (entry - stop) < floor:
        stop = entry - direction * floor
        src = f"{src}, widened to the {cfg.min_stop_atr:g}x volatility floor"
    return stop, src
```

### flow.py:736-808 `RushBook`

```python
class RushBook:
    """
    eng-89, "rush orders" (La Morgia et al., arXiv 2005.06610: pump detection on Binance within seconds): one taker
    market order that ate several price levels prints as several aggTrades with the SAME trade time and side.
    A PROXY, narrower than the paper (review eng-160b): the paper groups raw trades of one side in the same ms; aggTrade
    already merges the fills of one taker at one price, so a market order filled at a single level is not counted here -
    only multi-level sweeps are. Neither is an exact market-order count (no parent order id in the public stream). Counted
    per second per coin in a one-hour ring (Binance futures only: its aggTrade carries the match time T). Journaled as
    features and as RUSH rows - data collection, no trading.
    """
    RING = 3600

    def __init__(self):
        self.counts: Dict[str, np.ndarray] = {}    # symbol -> [RING, 2 sides] rush orders per second
        self.usd: Dict[str, np.ndarray] = {}
        self.secs: Dict[str, np.ndarray] = {}      # the second each ring slot holds (stale slots are zeroed lazily)
        self._open: Dict[str, list] = {}           # symbol -> [T, side, levels, usd, last price]
        self.started = time.time()                 # the z-score needs a full hour of history (0 before: no RUSH rows)

    def on_trade(self, symbol: str, ts_ms: int, side: int, usd: float, price: float):
        g = self._open.get(symbol)
        if g is not None and g[0] == ts_ms and g[1] == side:
            g[3] += usd
            if price != g[4]:
                g[2], g[4] = g[2] + 1, price
            return
        if g is not None:
            self._close(symbol, g)
        self._open[symbol] = [ts_ms, side, 1, usd, price]

    def _close(self, symbol: str, g: list):
        if g[2] < 2:
            return                                  # one level: an ordinary fill, not a sweep
        if symbol not in self.counts:
            self.counts[symbol] = np.zeros((self.RING, 2))
            self.usd[symbol] = np.zeros((self.RING, 2))
            self.secs[symbol] = np.full(self.RING, -1, dtype=np.int64)
        sec = int(g[0] // 1000)
        k = sec % self.RING
        if self.secs[symbol][k] != sec:
            self.counts[symbol][k] = 0
            self.usd[symbol][k] = 0
            self.secs[symbol][k] = sec
        j = 0 if g[1] > 0 else 1
        self.counts[symbol][k, j] += 1
        self.usd[symbol][k, j] += g[3]

    def stats(self, symbol: str, now_ms: float) -> Dict[str, float]:
        """Rush orders in the last 10 / 30 s (count, net buy - sell count, USD) and the 30 s count's z-score against
        the coin's own previous hour (120 buckets of 30 s, zeros included)."""
        g = self._open.get(symbol)
        if g is not None and now_ms - g[0] > 1000:
            self._close(symbol, g)
            self._open.pop(symbol, None)
        counts = self.counts.get(symbol)
        if counts is None:
            return {'rush_n_10s': 0.0, 'rush_n_30s': 0.0, 'rush_net_30s': 0.0, 'rush_usd_30s': 0.0, 'rush_z_30s': 0.0}
        now = int(now_ms // 1000)
        age = now - self.secs[symbol]
        valid = (age >= 0) & (age < self.RING)
        c = np.where(valid[:, None], counts, 0.0)
        u = np.where(valid[:, None], self.usd[symbol], 0.0)
        last10, last30 = valid & (age < 10), valid & (age < 30)
        n10 = float(c[last10].sum())
        n30 = float(c[last30].sum())
        net30 = float(c[last30, 0].sum() - c[last30, 1].sum())
        usd30 = float(u[last30].sum())
        base = np.zeros(self.RING // 30)
        hist = valid & (age >= 30)
        np.add.at(base, (age[hist] // 30).clip(0, self.RING // 30 - 1), c[hist].sum(axis=1))
        base = base[1:]
        z = (n30 - base.mean()) / max(base.std(), 0.5) if now_ms / 1000 - self.started >= self.RING else 0.0
        return {'rush_n_10s': n10, 'rush_n_30s': n30, 'rush_net_30s': net30, 'rush_usd_30s': usd30, 'rush_z_30s': float(z)}
```

### signal_book.py:443-469 veto block in SignalBook.update

```python
        directional: List[Tuple[int, Dict]] = []
        for symbol, sig in signals:
            kind, group_key, direction = classify(sig)
            key = (symbol, group_key)
            strategy = strategy_of(group_key)
            if strategy is not None:
                self._recent_setups[(symbol, direction)] = now
                directional.append((direction, sig))
                sig.pop('shadow_veto', None)
                sig['card_veto'] = None
                reason = shadow_veto(sig, veto_reason(group_key, sig)) or shadow_veto(sig, strategy.context_veto(sig, direction))
                if reason is None and direction > 0 and sig.get('event_risk'):
                    # eng-53: no longs on a coin Binance tagged for monitoring / is delisting (documented -4..-34%)
                    reason = 'event_risk'
                if reason is None and not strategy.has_data(sig):
                    reason = 'no_data'
                if reason is None and (not strategy.enabled or group_key in CONFIG.strategies.disabled_setups):
                    reason = 'disabled'
                pool_of = getattr(self, 'pool_of', None)
                if reason is None and pool_of is not None and not pool_of(strategy.name, symbol):
                    reason = shadow_veto(sig, 'not_in_pool')
                if reason:
                    sig['card_veto'] = reason
                    self.vetoed.append((symbol, group_key, reason, sig))
                    continue
                # One open card per coin and direction: a setup relabelled on the live candle is the same idea
                same_side = [s for s in self.signals.values()
```

### config.py:774-783 `pump_start_min_pct`

```python
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
```

### config.py:831-840 `dump_min_move`

```python
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
```

### config.py:837-846 `wide_min_volume`

```python
    # below the previous low; stop above the bounce + 0.25 ATR(1h); TP1 the dump's low, TP2 the 1.618 extension
    dump_min_move: float = 0.15
    dump_vol_x: float = 3.0
    # eng-57 wide watch: perpetuals outside the universe above this 24h volume (pretraining's floor, research_pumps)
    wide_min_volume: float = 3_000_000
    # eng-158: live 1m watch of those perpetuals for PUMP START / DUMP START (smallcap.py): cards + demo like the universe
    smallcap_watch: bool = True
    smallcap_minutes: int = 240               # 1m ring per coin (PUMP START 120, the 5m layer 48 bars; ~9 MB / 150)
    # eng-127: OI build = Pring's rule (strategies/oi_build.py, shadow); the OI robots' thresholds are deleted
    oi_build_ttl: tuple = (900, 900, 4 * 3600)
```

### config.py:673-682 `shadow_vetoes: tuple`

```python
    # reasons that WOULD have vetoed it, so card_r of shadowed vs clean entries measures each rule on live trades.
    # Kept blocking: crowded, same_leg, low_rr, macro_event, event_risk, perp_led, killzone / session, disabled.
    # eng-156: 'against_bias' blocks again (SWEEP / SILVER BULLET against the weekly / daily bias, live eng-148..155:
    # 6 sweep entries, 1 win, -5.5R; Silver Bullet 3, -1.8R; ICT's top-down rule); 'against_trend' (1h) stays shadow
    shadow_vetoes: tuple = ('against_trend', 'pd_late', 'pd_spike_fail',     # eng-159: detector phases, shadow 'not_in_pool', 'h4_against', 'regime_flat',
                            'regime_trend', 'alts_vs_btc', 'profile', 'regime', 'no_confirmation',
                            # eng-138: the filters by name (was the pattern 'no_*', which also put a setup's own
                            # required parts - Wyckoff's spring test 'no_spring_test' - in shadow: springs without
                            # their test were traded)
                            'no_bias', 'no_supply', 'no_demand', 'no_orderflow', 'no_oi', 'no_level', 'no_htf_poi',
```

### config.py:804-813 `crowd_max: int`

```python
    # eng-146: 3 (was 6): alts correlate 0.8-0.9 in falls, so 6 positions at 1R were one ~5.6R bet; 3 caps the
    # cluster at ~3R per direction (policy, not fitted)
    # eng-156: 6 again - the Turtles' closely correlated markets limit (Faith, Original Turtle Rules: 4 / 6 / 10 / 12);
    # 28 trendline shorts were open at once on 2026-10-24, one ~28R bet on the market falling
    crowd_max: int = 6
    # eng-128: the data-mined layers (models/profiles.json, profiles_regime.json: research_optimize's filters, stops,
    # break-even, time stops, the 'regime_off' veto; models/exit_overlays.json: research_overlays' early exits and the
    # alts_with filter) have no source - fitted on the archive, several negative on their own validation: off
    optimized_profiles: bool = False
    time_after_tp1: float = 3.0
```

### config.py:793-802 `be_after_1r: bool`

```python
    structural_lifetimes: bool = True
    # eng-111: no source -> off (break-even after +1R; the EMA20 trail after TP1)
    # eng-155 (the owner, live: 18 trendline shorts at +1..+3R with their stops untouched): break-even + costs after +1R
    # for every plan again, open cards included (SignalBook._trail)
    be_after_1r: bool = True
    ema_trail_after_tp1: bool = False
    time_stop_bars: int = 24
    # eng-51: at most crowd_max OPEN trades in one direction across all strategies (the rest journaled vetoed
    # 'crowded'). The Turtles allowed 6 units in closely correlated markets (Faith, Original Turtle Rules); alts move
    # with BTC as one market - 12 Silver Bullet longs on 2026-10-02 were one bet. Turtle units counted by the
```

### config.py:1112-1121 `partial_share: float`

```python
    # eng-105: no resting limits - a touch of the zone only arms the entry; the trade opens at the CLOSE of
    # the trigger-timeframe candle that touched the zone and closed back on the trade's side of its line
    touch_confirm_close: bool = True
    partial_r: float = 1.0
    partial_share: float = 0.5       # eng-155 (the owner): half out at +1R again (off since eng-123); open trades too
    max_leverage: int = 5            # eng-84: 2-5x (the 3-5-7 rule); the risk is set by the stop, cross margin
    # eng-58, the account's day (prop firms: daily loss 1-5%, 2-3 trades a day, a pause after a streak). eng-125: the
    # numbers were picked inside those ranges, no source -> off (0); the risk per trade (1%, the Turtles' unit) stays
    daily_loss_r: float = 0.0
    max_trades_day: int = 0
```
