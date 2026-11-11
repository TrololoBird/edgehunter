# EdgeHunter Capability Matrix v1

Это матрица фактической готовности, а не список желаемых функций.

Статусы:

- VERIFIED — capability существует и имеет подтверждённый production path.
- PARTIAL — часть реализации есть, но end-to-end proof отсутствует.
- BROKEN — реализация или исторические данные нарушают контракт.
- NOT IMPLEMENTED — отсутствует единый инженерный контракт.

| Capability | Existing implementation | Status | Proof required |
|---|---|---|---|
| Venue/market ingestion | fetcher.py, venues.py, candle cache | PARTIAL | point-in-time and gap audit |
| Closed candle finality | local finality checks and tests | PARTIAL | all consumers and exchange closure semantics |
| OHLCV multi-timeframe data | MarketData and resampling | PARTIAL | as-of lineage |
| Order book/depth | depth.py, recorder.py | PARTIAL | sequence-gap and replay test |
| Trades/delta/CVD | flow.py and journal columns | PARTIAL | source lineage and feature consumers |
| OI/funding | fetcher.py, positioning.py | PARTIAL | freshness and timestamp contract |
| Actual liquidation events | liquidation streams/journal | PARTIAL | coverage by venue and event completeness |
| Estimated liquidation exposure | no single canonical contract | NOT IMPLEMENTED | explicit model/schema/source |
| Structural pools/EQH/EQL | zones.py | PARTIAL | source semantics and strength attribution |
| Pivot/SR zones | sr.py, zones.py | PARTIAL | lineage and no-forming-bar property tests |
| Pierce p50/p80 | pierce.py | PARTIAL | point-in-time calibration dataset |
| Higher-timeframe bias | briefing.py and scanner.py | PARTIAL | target definition and replay |
| Structure BOS/CHoCH/HH/HL | scattered strategy/level logic | PARTIAL | canonical Structure Engine |
| Wave hypotheses | no canonical Wave Engine | NOT IMPLEMENTED | confirmed/hypothesis/invalidated contract |
| Pattern recognition | scattered strategy modules | PARTIAL | no-repaint and alternative labeling |
| Scenario generation | briefing_chart.py | BROKEN/PARTIAL | unified execution and geometry contract |
| Alternative scenario | long/short pair and OCO logic | PARTIAL | explicit scenario graph/FSM |
| Limit execution simulation | new retest path | PARTIAL | queue/latency/fill sensitivity |
| Gross/net R:R | journal and briefing fields | PARTIAL | single formula contract |
| Macro calendar | macro_calendar.py, official_calendar.py | PARTIAL | immutable source/event provenance |
| News/evidence analysis | event_risk.py and external feeds | PARTIAL | source claims and confidence |
| Event studies | scripts/research only | PARTIAL | canonical target/horizon/calibration contract |
| Signal cards | SignalBook/strategies | VERIFIED/PARTIAL | end-to-end runtime provenance |
| Demo execution | executor.py/demo_trades.db | PARTIAL | reconciliation and fill audit |
| Briefing archive | data/briefings.jsonl | BROKEN/PARTIAL | schema migration and legacy isolation |
| Web analysis API | webui.py | VERIFIED/PARTIAL | snapshot coherence and stale semantics |
| Web dashboard | web/app.js | VERIFIED/PARTIAL | frontend security and freshness labels |
| Telegram publication | notifier.py/briefing formatter | PARTIAL | publication_id and evidence lineage |
| Statistical reporting | stats.py/journal.py | PARTIAL | dependency/censoring/OOS inference |
| Calibration engine | no unified engine | NOT IMPLEMENTED | target-specific calibration contract |
| Bitemporal data model | no universal model | NOT IMPLEMENTED | valid/transaction time schema |
| Immutable historical evidence | no universal model | NOT IMPLEMENTED | versioned corrections and replay |
| Monotonic degradation | local quality modules | PARTIAL | global publish gate |
| Reproducibility contract | partial provenance fields | PARTIAL | publication-to-raw-event replay |
| Security/rate limits | local guards and API controls | PARTIAL | complete endpoint/taint audit |
| Test suite | tests/ | VERIFIED | 81 tests in project environment |
| System acceptance suite | absent | NOT IMPLEMENTED | cross-module integration/replay suite |
