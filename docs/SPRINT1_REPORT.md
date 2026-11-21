# Edgehunter — Implementation Sprint 1

Date: 2026-11-19  
Scope: data integrity and market-data reliability. No commit was created.

## Protected working state

- HEAD: `3835b909b7707a76e74e7a97731b3e7fed63c3d0`
- Branch: `codex/edgehunter-stabilization`
- The checkout already contained a broad user diff and untracked audit/remediation artifacts. The original protected snapshot is preserved under `/tmp/edgehunter-sprint1-prestate/`; at this turn, HEAD, branch, `git status`, the full binary diff, and pre-edit copies of files changed here were saved under `/tmp/edgehunter-sprint1-baseline/`.
- Existing modifications were preserved. No reset, checkout, clean, stash, or commit was run.
- No file named `MASTER FINDINGS REGISTER` or `MASTER_FINDINGS.json` existed. The prior records were `docs/EDGEHUNTER_DEFECT_REGISTRY.md` and `docs/V2_DEFECT_REMEDIATION_REGISTER_2026-11-17.md`. Both were left unchanged; their IDs, evidence/action text and statuses were imported into the new cumulative master.

## Fixes

| Finding | Root cause | Change and old → new behavior | Compatibility / check |
|---|---|---|---|
| `SPR1-DATA-001` | Binance OI response was treated as current when received; value was not validated before freshness. | `DataFetcher.fetch_open_interest` validates positive finite OI and the exchange `time` before updating quality. It returns OI and exchange milliseconds; `_oi_loop` records the measurement at exchange time. Local receive time is kept separately in `oi_received_at`. Seed rows receive the same finite/positive checks. Old: receive time and malformed numeric values could refresh OI. New: invalid payload returns no sample and cannot refresh; stale exchange timestamp remains stale. | Repository search found `_oi_loop` as the only caller of `fetch_open_interest`; sample tuple shape remains `(timestamp_ms, oi)`. `oi_last_updated` stays seconds, now exchange time. Tested zero, negative, NaN and absent timestamp. |
| `SPR1-DATA-002` | REST book code considered successful JSON/HTTP sufficient and refreshed quality after it. | `ExternalData._json` raises on non-success HTTP. `_okx_book` and `_bybit_book` require a successful business code and valid two-sided, sorted, non-crossed levels with finite positive prices/sizes. `book_status` records transport, API, valid-content and age-derived freshness separately. Invalid content takes the existing error path and cannot mark quality fresh. Old: HTTP 200 with error/empty/malformed body could refresh. New: each stage has a distinct result. | Existing quality key remains `('book', symbol)` and existing `*_book_imb` fields remain. Regression checks cover API code, malformed levels and freshness expiry. No live REST request was made. |
| `SPR1-HEALTH-001` | UI treated absence of `connected` as success; a configured stream with a known zero count and no prior messages was also left `UNKNOWN`. | `DataFetcher.venue_status` emits `CONNECTED`, `DISCONNECTED`, `NOT_CONFIGURED`, `STALE` or `UNKNOWN`; absent/invalid connection data remains `UNKNOWN`, scanner aggregation treats unknown/stale/disconnected as unhealthy, and UI displays state text. Old: missing field appeared healthy. New: absent data is unknown. The separately discovered known-zero classification defect is recorded as `SPR1-HEALTH-002`. | Existing numeric `connected` is retained. UI continues to consume `venues`; unknown status reaches `/api/health` as unhealthy. Verified the missing-field backend case and JavaScript syntax; the known-zero case is verified separately under `SPR1-HEALTH-002`. |
| `SPR1-HEALTH-002` | A configured stream with known `connected=0` and no prior messages was left `UNKNOWN`. | Known zero becomes `DISCONNECTED`; missing or invalid connection information remains `UNKNOWN`. Binance stream groups apply the same aggregation rule. | `connected` remains numeric when known and is `null` when unavailable; existing UI and `/api/health` consume the shared explicit state. Verified known-zero and missing-field boundary tests. |
| `SPR1-FLOW-001` | REST minute/5-minute taker aggregates were written into second-level event-flow buffers and were indistinguishable from prints. Candle delta and stream flow were also combined without a source label. | Binance/OKX REST aggregate seeds remain available in candle history but are no longer inserted as trade prints. Legacy `FlowStore.seed_minute` calls go into a separately tagged observation buffer. The mixed spot field stays; separate candle-delta/event-flow fields and a source descriptor identify its inputs. `cvd_divergence` now documents that it uses candle aggregates. Old: REST aggregates could be treated as event prints by CVD/whale consumers. New: only stream events reach event-flow and whale rings; candle-based calculations are identified as OHLCV aggregates. | No public API field was silently removed or renamed. Regression check proves a seed does not change CVD or event-flow freshness. |
| `SPR1-FLOW-002` | Active venue count required non-zero net; old top share described net participation using a denominator that could hide gross activity. | `FlowStore.snapshot` keeps `venues_active`, `top_venue`, `top_venue_share` and `top_venue_net` with their prior definitions and adds explicitly named gross/net totals, active counts and gross top-venue concentration. UI wording now uses gross concentration. Old: balanced buy/sell venue looked inactive. New: gross activity counts it while net activity remains separately visible. | Existing scanner fields retain their prior meaning; new fields are added to the state API. Regression test uses equal buys and sells. |
| `SPR1-MKT-001` | Binance liquidation notional could fall back from executed `z` to original `q`, event status was unchecked, and sweep suppression summed liquidation flow across venues. | `normalize_binance_liquidation` accepts only FILLED events with valid time/side, positive average execution price and positive finite executed quantity; notional is `ap*z`. Sweep correlation filters liquidation flow to the sweep's venue and existing short time interval. Public feed wording now says partial observations. Old: original order size or another exchange's liquidation could distort notional/suppress a sweep. New: only matching executed observations are used. | Existing `liq_events` tuples/API preserved. Regression tests cover status, quantity and venue isolation. `DEF-MKT-004` stays PARTIAL because quantitative per-stream coverage instrumentation remains open. |

## Changed files

- Runtime: `fetcher.py`, `flow.py`, `extdata.py`, `scanner.py`, `strategies/confirm.py`, `webui.py`, `web/app.js`
- Regression checks: `tests/test_regressions.py`
- Documentation: `docs/ARCHITECTURE.md`, `docs/HISTORY.md`
- Audit registry: `docs/MASTER_FINDINGS_REGISTER.md`, `docs/MASTER_FINDINGS.json`

The sprint-only patch is `docs/evidence/EDGEHUNTER_SPRINT1.patch`; the ZIP carries the report, register, targeted test output, sprint patch, existing pre-change status/diff evidence and pre-change copies. The complete current tracked diff from HEAD is also preserved outside the repository at `/tmp/edgehunter-sprint1-baseline/final.diff`.

## Verification

- `.venv/bin/python -m py_compile fetcher.py flow.py extdata.py scanner.py webui.py depth.py venues.py strategies/confirm.py tests/test_regressions.py` — passed.
- `.venv/bin/python -m pytest -q tests/test_regressions.py -k 'open_interest_uses_exchange_timestamp or cross_venue_gross_activity or rest_minute_seed or liquidation_attribution or other_venue_liquidations or binance_liquidation_uses_filled or rest_book_validation or rest_book_status or missing_websocket_connection or configured_websocket_with_zero'` — 10 passed.
- `node --check web/app.js` — passed.
- No market simulation, replay, backtest, live REST request, order, or trade was run.

## Remaining limitations

- `DEF-MKT-004` remains PARTIAL: stream coverage and freshness are not quantified independently for every liquidation venue, and public liquidation events are not a complete market tape.
- Related imported findings remain unchanged: `D-012` (no proven global quality/publication gate), `D-009` (REST cache and WebSocket snapshot freshness differ), and `DEF-DATA-001` (funding kind/settlement-time normalization is incomplete across venue aggregates).
- Book quality is currently symbol-level across configured REST venues rather than a separate quality record per venue. Any invalid configured response conservatively prevents a fresh symbol-level verdict.
- Historical REST OHLCV candles remain useful for warm-up and candle-based indicators. They carry interval aggregates, not exact trade timestamps. `spot_cvd_5m` remains a compatibility field whose mixed inputs are now identified; consumers that need only event flow should use the explicit event-flow field.
- The full pre-existing project test suite was not run; only sprint-specific regressions and syntax checks were run.

## New findings

Seven Sprint 1 findings are registered as `SPR1-DATA-001`, `SPR1-DATA-002`, `SPR1-HEALTH-001`, `SPR1-HEALTH-002`, `SPR1-FLOW-001`, `SPR1-FLOW-002`, and `SPR1-MKT-001`. All are marked RESOLVED only after the listed targeted checks. Historical findings retain their original IDs/statuses and source wording in the master JSON; other OPEN/PARTIAL records remain open as imported.
