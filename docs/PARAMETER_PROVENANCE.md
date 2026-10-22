# Provenance of the trade-shaping parameters (stage 0 of the external audit 2026-10-18)

Every rule that moves an entry, a stop, a target, a card's life, the size or a tolerance, with what actually supports
it. The whole project (code, comments, research notes) is AI-written: a comment saying "derived", "canonical" or
"proven", or an author's name, is a claim to check, not support. Statuses:

- **math** - follows from explicitly stated assumptions and units (checked here); the assumptions themselves may still be unproven.
- **exchange** - an exchange's / contract's published rule.
- **empirical** - reproduced on data with a checked execution model and a separate validation sample.
- **policy** - the owner's choice (a risk appetite), not a property of the market.
- **heuristic** - plausible, without sufficient support. Measure it in the journal before relying on it; do not
  replace it with another invented number.

Checked against the code of logic eng-143 (2026-10-18). "Measured" below means a number quoted in a comment; none of
those was re-run for this table, so none is promoted to **empirical**.

| Parameter (where) | Value | Purpose / units | Stated source | Check | Status |
|---|---|---|---|---|---|
| `levels.cost_guard` (geometry.finish_levels, system_levels) | 1.0 | veto when risk < k x round-trip cost (price units) | eng-108 "break-even formula" | False as a break-even condition: EV = p.W - (1-p).L - c can be positive with c > 1R (p 0.8, W 3R, c 1.2R: +1R). Text fixed (eng-142) | policy |
| `levels.min_rr_tp1` | 1.0 | min R:R to TP1 / blended, net of costs | eng-112 "p.R - (1-p) > 0" | Break-even R:R depends on p, unknown per setup; 1.0 is break-even only at p = 0.5 | heuristic |
| expectancy veto (geometry, `HIT_RATE`) | Wilson 95% upper | veto when thirds-model EV <= 0 at p upper | journal replay, 30 days | p is per target before the stop (descriptive); EV model = three thirds against a fixed stop - since eng-143 it vetoes only plans that exit that way, the rest is journaled `exp_model` / `exp_note`. Entries of one market move are correlated: the interval is optimistic | math (on its model) / heuristic (as a gate) |
| `fee_round_trip` (journal) | 0.001 | taker 0.05% x 2 | Binance USD-M taker fee, VIP 0 | Exchange schedule; BNB discount / VIP tiers differ | exchange |
| `slippage_bps`, `slippage_max_bps`, `slippage_impact_sigma`, `slippage_notional_usd` (levels.slippage_bps) | 5 / 25 bps, 0.04, $10k | entry + exit slippage, square-root impact by 24h volume | "square-root impact" | Functional form from the impact literature; the constants are not fitted to this bot's fills (demo fills exist but are not compared) | heuristic |
| `target_through_bps` | 2 bps | a limit TP counts only once traded through | "backtests that fill on a touch overstate" | Direction of the bias is right; 2 bps is not measured against queue position | heuristic |
| SL-first on a candle touching both (signal_book, levels.simulate) | - | ambiguity rule | conservative convention | A convention: biases results down, never up | policy |
| gap fill (signal_book._manage_trade) | next observed open | a stop / target crossed inside a minute hole | eng-142 | The price inside the hole is unknown; the next open is the first OBSERVED price, still an estimate (the hole is flagged `data_gaps`) | heuristic (flagged) |
| `stop_buffer_atr` | 0.3 ATR of the anchor TF | stop beyond structure | "0.1 sat where stops cluster (Osler)"; "47% of 0.1-ATR stops ... (history 2026-09)" | Osler documents clustering at round numbers, not a 0.3 ATR buffer; the 47% is an unreproduced comment | heuristic |
| `levels.min_rr_tp1_floor` (eng-147) | 1.0 | min R:R to TP1 when TP1 is a real level | owner; VPS journal eng-135..144: 8 entries < 1R, -4.74R | In-sample, n = 8; eng-86 had turned it off on laptop data (< 0.5R near 0) | policy |
| TP2 / TP3 '1R step' (geometry.finish_levels, eng-147) | +1R each | slots the map cannot fill (not the methods' own targets) | owner | No measurement; lifts the blended R:R of single-level plans | policy |
| `levels.moved_pad_atr` / `pierce_cap_atr` (geometry.capped_pad, eng-147) | 0.2 / 0.5 ATR (working tf) | pad past a stop_beyond pool / cap on the measured pierce | owner; journal stop widths | n = 52, no control; a deep raid of the pool itself can reach the moved stop | heuristic |
| `levels.max_trigger_overshoot_atr` (signal_book._overshoot, eng-147) | 0.6 ATR | veto a trigger close this far past the anchor level / zone edge | owner; journal: 11 entries > 0.6, -7.00R | In-sample, n = 11, threshold chosen on the same rows | heuristic |
| `executor.chase_limit_n` / `chase_limit_atr` (eng-147) | 0.5 N / 0.5 ATR | no demo open of a target-less plan after a run past the signal price | owner | No measurement | policy |
| crowd ranking (signal_book.crowd_rank, eng-147) | shadow vetoes, RVOL, min(rr_tp1, 2.5) | order of one pass's entries for crowd_max | owner | No measurement | policy |
| `min_stop_atr` | 1.0 x 15m ATR | stop floor | "8 of 10 live entries hit" | n = 10, no control | heuristic |
| `max_stop_atr` | 3.0 ATR | no trade with a farther stop | eng-91 | No source | heuristic |
| `continuation_zone` | 0.62-0.79 | pullback entry band of the leg | ICT OTE | ICT material names these ratios; no test that the band beats another | heuristic (author's rule) |
| `continuation_invalid` | 1.0 | card invalid beyond the leg start | ICT | Same | heuristic (author's rule) |
| `reversal_targets` | 0.382 / 0.5 / 0.618 | reversal TPs as leg fractions | Fibonacci practice | No test | heuristic |
| leg timeframe (levels.find_impulse) | 15m / 1h / 4h by >= 5 candles | the structure's TF, its ATR and trigger | Elder's "factor of five" | Elder's factor relates screens, not the classification of a leg; the >= 5 rule is ours. Since eng-142 a missing HTF ATR makes the card wait instead of reclassifying | heuristic |
| `min_leg_atr()` / `min_leg_move()` (levels) | min_stop_atr / 0.382; cost_guard x cost / 0.382 | smallest leg | eng-57 "derived" | The algebra holds (TP1 = 0.382 leg must cover the stop floor / the costs); its premises (min_stop_atr, cost_guard) are heuristic / policy | math on heuristic inputs |
| `require_displacement` + FVG on 3 consecutive candles (strategies.leg) | on | continuation needs a gap | ICT | A pattern definition; consecutiveness enforced since eng-142 | heuristic (author's rule) |
| `zones.min_strength` | 2.5 | a map zone counts as a target / obstacle | ours | Weights of level sources are unmeasured (CLAUDE.md says so) | heuristic |
| target reach `3 x ATR x sqrt(time_stop_bars x time_after_tp1)` (geometry.finish_levels) | 3 sd over 72 bars | drop map targets out of reach | "3 sd of a random walk" | ATR is a mean range, not a standard deviation; with `structural_lifetimes` the trade has no 72-bar clock. A filter, not a probability | heuristic |
| `overshoot(..., 'p90')` (geometry, models/overshoot.json) | per-kind p90 | stop beyond the typical pierce | fitted on the archive | Provenance of the JSON (sample, cutoff, out-of-sample check) not recorded with it | heuristic until its fit is documented |
| `BE_COST` (signal_book) | 0.0015 | break-even stop offset | "taker x 2 + ~0.05% slippage" | A cost estimate, not a guaranteed break-even; only used with `be_after_r` (off) | heuristic (inactive) |
| `be_after_r`, `ema_trail_after_tp1`, `partial_share` | off / False / 0 | trade management | eng-111 / eng-123: no source | Off by default; the thirds exit is what runs | policy |
| `structural_lifetimes` (cards end structurally, no clocks) | True | lifetimes | eng-108 owner's rule | Owner's choice | policy |
| `plan_wait_sec` | 180 s | wait for 1h history before a plan | ours | Since eng-142 a leg missing its ATR keeps waiting after it | heuristic |
| funding model (levels.funding_r, signal_book._cost_r) | the contract's interval, rate at entry or settled ledger | holding cost per part held | exchange funding rule | Per part until it left and per Turtle unit from its add time since eng-142; one rate for the hold in live (the replay uses settled rates) | exchange (form) / heuristic (one rate) |
| `risk.liq_stop_margin`, `maintenance_of` (webui.sizing_view) | 1.5 x stop, Bybit first tier | max isolated leverage shown to the trader | Bybit maintenance tiers | Estimate: isolated margin, tier 1, no account state; shown as such since eng-143 | exchange (tier) / heuristic (margin) |
| `risk_pct`, `executor.max_leverage` | 1%, 5x | demo sizing | owner | Risk appetite | policy |
| `outcome_life_h` | 72 h | journal relabel horizon | ours | Label horizon only, not a trading rule | policy |
| Turtles: 2N stop, +1 unit / 0.5N, 4 units, channel exits | - | breakout | Faith, "Way of the Turtle" / Original Turtle Rules | Rules match the published text (CLAUDE.md: not changed); their edge in crypto perps is not established | heuristic (author's rule) |
| Connors RSI(2), Crabel ORB, O'Neil cup-handle, Seiden 3:1, Dalton 80% | - | strategy rules | the authors' books | Implementations follow the summaries in the code; each author's result was on other markets / periods | heuristic (author's rule) |

## What this changes
- Nothing above is a reason to change a threshold now: the table marks what is a policy and what is an unproven
  heuristic; replacing one heuristic number with another proves nothing.
- The journal now records `exp_model` / `exp_note` (the thirds-model estimate, also when it only shadows) and
  `obstacle_r` / `obstacle_src` (the nearest strong zone before TP1), so the questions of the audit's section 7 - are
  entries behind a near obstacle weaker; do far author's targets pay - can be answered from live rows of one logic version.
- Research notes marked VOID stay void; a research result counts only with its data, code version, cutoff and a pass
  rule fixed before the run (CLAUDE.md).
