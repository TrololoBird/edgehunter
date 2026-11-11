# EdgeHunter — независимая инвентаризация v1

Статус: рабочий документ этапа 1. Это инвентаризация фактической реализации, а не целевая архитектура и не утверждение торговой эффективности.

Дата проверки: 2026-11-11. Проверяемая директория: /opt/edgehunter.
Git commit на начало проверки: 697580de095d1108dc30e98821ad8261d857e434.

Рабочее дерево содержит незакоммиченные изменения в briefing.py, briefing_chart.py, web/app.js, web/index.html, main.py, README.md, deploy/edgehunter-bot.service и models/official_calendar.json. Для итогового аудита commit, diff и runtime digest должны сохраняться отдельно.

## Статусы

- VERIFIED — поведение подтверждено исходниками и воспроизводимой проверкой.
- PARTIALLY_VERIFIED — часть цепочки подтверждена, но отсутствует runtime/data/replay evidence.
- BROKEN — обнаружено противоречие, ошибка типов, нарушение контракта или failing check.
- UNUSED — код существует, но не входит в production-путь.
- NOT_IMPLEMENTED — требуемая функция отсутствует как единый контракт.

## Runtime и проверки

| Объект | Статус | Факт |
|---|---|---|
| Рабочий каталог | VERIFIED | /opt/edgehunter |
| Systemd unit | VERIFIED | edgehunter-bot, WorkingDirectory=/opt/edgehunter |
| Python compile | VERIFIED | ключевые production-модули компилируются |
| Precheck | VERIFIED | deploy/precheck.sh проходит |
| Штатный тестовый запуск | VERIFIED | PYTHONPATH=. .venv/bin/python -m pytest -q: 81 passed |
| Системный pytest без окружения | BROKEN | imports не находятся без PYTHONPATH и .venv |
| Runtime/source identity | PARTIALLY_VERIFIED | есть provenance-модуль, но deployment должен сравнивать digest процесса и дерева |

## Данные

### data/briefings.jsonl

Проверено 904 записи:

- b169a: 565;
- b168y: 12;
- rules_v отсутствует: 327;
- silent=true: 628.

Историческая выборка неоднородна. Legacy записи без rules_v нельзя автоматически считать текущей версией.

В старых записях rr_ok встречается и как строка "False"/"True", и как boolean. Проверка value is False классифицирует только настоящий boolean.

Статус: BROKEN для исторической типовой целостности; новые записи должны проходить строгую схему.

### signals.db

Основные таблицы:

- signals: 76224;
- universe: 5657222;
- liquidations: 1203540;
- liq_levels: 4447292;
- history_skips: 22557.

logic_version:

- eng-169l: 67814;
- eng-169m: 4817;
- eng-170a: 3593.

Схема содержит OI, funding, spot/perpetual delta, CVD, ликвидации, depth imbalance, gross/net R:R, cost model, geometry errors, source commit и implementation hash. Наличие колонок не доказывает, что каждое поле используется в downstream-решении.

Статус: PARTIALLY_VERIFIED.

### demo_trades.db

Отдельный demo/execution-контур. Его результаты нельзя автоматически смешивать с briefing outcomes: это разные state machines и модели входа.

Статус: PARTIALLY_VERIFIED.

## Production-путь

fetcher и venue streams → scanner.market_data → scorer/SignalBook/strategies → journal/signals.db → webui WebSocket.

Параллельный briefing-путь:

market_data → Briefing.analyze → key_zones, _bias_of, session_bias, briefing_chart.plan → /api/analysis и /api/pinned → Web/Telegram.

Signal pipeline и briefing pipeline используют общие данные, но не являются одной математической моделью.

## Инвентаризация ключевых модулей

| Модуль | Роль | Статус |
|---|---|---|
| main.py | запуск процесса и event loop | VERIFIED |
| config.py | dataclass-конфигурация и overrides | VERIFIED |
| fetcher.py | venue adapters, свечи, OI, funding | PARTIALLY_VERIFIED |
| scanner.py | оркестрация сканирования и market state | PARTIALLY_VERIFIED |
| depth.py | локальные order books и depth bands | PARTIALLY_VERIFIED |
| flow.py | trades, delta, liquidation-related flow | PARTIALLY_VERIFIED |
| positioning.py | ratios и positioning | VERIFIED |
| zones.py | RawLevel и источники уровней | PARTIALLY_VERIFIED |
| sr.py | pivot clustering и zones | PARTIALLY_VERIFIED |
| levels.py | ATR, resampling, fills, slippage, profiles | PARTIALLY_VERIFIED |
| pierce.py | overshoot/p50/p80 | PARTIALLY_VERIFIED |
| briefing.py | analysis, archive, outcomes | BROKEN/PARTIALLY_VERIFIED |
| briefing_chart.py | scenario plan и PNG card | BROKEN/PARTIALLY_VERIFIED |
| journal.py | SQLite schema и signal outcomes | PARTIALLY_VERIFIED |
| signal_book.py | tracked cards, strategies, exits | PARTIALLY_VERIFIED |
| executor.py | demo/live execution и reconciliation | PARTIALLY_VERIFIED |
| macro_calendar.py | macro calendar | PARTIALLY_VERIFIED |
| official_calendar.py | official calendar parsing/merge | PARTIALLY_VERIFIED |
| event_risk.py | listings/news/event risk | PARTIALLY_VERIFIED |
| ml.py | anomaly/regime/success/trade models | PARTIALLY_VERIFIED |
| stats.py | journal reports | PARTIALLY_VERIFIED |
| webui.py | HTTP/WebSocket/API | VERIFIED/PARTIALLY_VERIFIED |
| web/app.js | dashboard rendering | PARTIALLY_VERIFIED |
| notifier.py | Telegram publisher | PARTIALLY_VERIFIED |
| raw_event_log.py | raw event persistence | PARTIALLY_VERIFIED |
| recorder.py | flow/depth/derivatives recorder | PARTIALLY_VERIFIED |
| core/provenance.py | source commit/dirty/implementation digest | VERIFIED |
| quality_contract.py | feature-quality state | VERIFIED/PARTIALLY_VERIFIED |
| data_quality.py | freshness/stale quality | VERIFIED/PARTIALLY_VERIFIED |
| tests | unit/component/regression | VERIFIED |

## Архитектурные разрывы

### Bitemporal data foundation

В проекте есть timestamps свечей, событий, получения и вычисления, но нет обязательного сквозного объекта valid_time + transaction_time + decision_as_of + snapshot_id.

Статус: NOT_IMPLEMENTED как общий контракт.

### Evidence lineage

Есть source labels, rules_v, logic_version, source_commit и implementation_hash, но нет обязательной цепочки publication → scenario → evidence → feature → snapshot → raw events → runtime hash.

Статус: NOT_IMPLEMENTED.

### Calibration target contract

В проекте одновременно существуют TP1/stop outcomes, signal labels, P(edge), anomaly effects, demo outcomes и scenario outcomes. Они не сведены к общей декларации target, horizon, population и censoring.

Статус: NOT_IMPLEMENTED.

### Monotonic degradation

Отдельные компоненты умеют отмечать stale/not-ready/error, но нет единого правила: ухудшение качества не может повышать confidence и должно уменьшать доступность выводов.

Статус: PARTIALLY_VERIFIED.

### Scenario/order/fill/trade

Старая briefing-модель связывала сценарий, synthetic fill и исход слишком тесно. Limit-on-retest улучшает причинность, но требует отдельного execution ledger и replay.

Статус: PARTIALLY_VERIFIED.

### Historical immutability

Есть архивы и JSONL, но нет общего immutable event-version contract для исправленных свечей, календарей, внешних источников и derived evidence.

Статус: NOT_IMPLEMENTED.

## Что нельзя переносить в Master Specification без изменений

Нельзя фиксировать как целевые контракты:

- старое p как probability;
- strength как probability;
- OHLC touch как гарантированный limit fill;
- rr_ok без typed schema;
- missing rules_v как текущую версию;
- 72-hour outcomes без зависимости и censoring model;
- scenario outcome как trading performance;
- macro narrative без source/event provenance;
- estimated liquidation exposure как actual positions;
- WebSocket и REST как один атомарный snapshot;
- публикацию без immutable evidence lineage.

## Покрытие тестами

Текущие тесты покрывают:

- minute finality;
- candle resume;
- venue/component resilience;
- entry/risk contract;
- cost serialization;
- invalid target geometry;
- execution gates;
- exchange errors;
- stop confirmation/readback;
- restored positions.

Не покрыты как единый acceptance suite:

- bitemporal lineage;
- immutable historical evidence;
- scenario-to-publication reproducibility;
- snapshot identity между модулями;
- monotonic degradation;
- calibration target contract;
- queue-aware limit execution;
- dependent-outcome inference.

## Следующие задачи этапа 1

1. Построить production import/call graph.
2. Провести SQLite schema и migration audit.
3. Провести JSONL schema/type audit.
4. Проследить timestamps и as-of ограничения.
5. Проследить data-quality gates до Web и Telegram.
6. Проверить publication lineage.
7. Выполнить малый deterministic replay.
8. Выделить UNUSED и NOT_IMPLEMENTED.
9. Создать defect registry с минимальными воспроизводимыми примерами.
10. Только после этого зафиксировать Master Technical Specification v2.0.

Цель этапа 1 — доказать, что EdgeHunter фактически умеет делать сейчас. Целевая архитектура, новые FSM и новые аналитические функции фиксируются только после завершения этой инвентаризации.


## Function-level status correction

Статус модуля не является статусом всех его функций. Для следующей итерации используется функция/контрактная гранулярность.

| Function / contract | Status | Evidence or gap |
|---|---|---|
| Briefing.analyze() | PARTIALLY_VERIFIED | JSON shape and calculations readable; full point-in-time replay pending |
| Briefing.key_zones() | PARTIALLY_VERIFIED | zone path traced; all source lineage and historical as-of pending |
| Briefing._bias_of() | PARTIALLY_VERIFIED | higher-timeframe calculation exists; target/validation contract pending |
| Briefing.session_bias() | VERIFIED/PARTIAL | deterministic display context; not a calibrated predictive model |
| Briefing.outcomes() | BROKEN/PARTIAL | legacy types, version cohorts and execution semantics require migration/replay |
| Briefing.outcomes_total() | BROKEN/PARTIAL | aggregation inherits legacy schema and cohort/dependence issues |
| Briefing._save() | BROKEN/PARTIAL | writes legacy and current shapes; strict schema/normalization required |
| briefing_chart.plan() | BROKEN/PARTIAL | geometry/cost/fill contracts changed; paired replay required |
| Briefing.reaction() | PARTIAL | candle predicate exists; not equivalent to full natural-language scenario |
| Briefing.entry_ms() | PARTIAL | timing is defined by scenario scorer; realistic limit-fill evidence pending |
| sr.zones() | PARTIAL | clustering exists; input finality and lineage properties pending |
| zones.build_raw() | PARTIAL | many level families exist; source semantics and no-repaint proof pending |
| pierce.overshoot() | PARTIAL | p50/p80 lookup exists; point-in-time calibration pending |
| Scanner._tf_atrs() | VERIFIED/PARTIAL | closed-bar filter exists locally; cross-module consistency pending |
| Scanner._market_context() | VERIFIED | header uses short-horizon market context; UI period semantics must remain explicit |
| webui.build_state() | VERIFIED/PARTIAL | WebSocket state produced; runtime snapshot identity pending |
| WebUI._analysis_of() | VERIFIED/PARTIAL | cache/inflight controls exist; freshness contract pending |
| WebUI._pinned() | VERIFIED/PARTIAL | pinned analysis path exists; cohort/outcome semantics pending |
| Notifier.post()/post_photo() | PARTIAL | Telegram publishing exists; publication evidence identity absent |
| core.provenance.implementation_provenance() | VERIFIED/PARTIAL | digest generation exists; deployment enforcement pending |
| data_quality.quality() | VERIFIED/PARTIAL | local freshness decision exists; monotonic downstream policy pending |
| quality_contract.entry_quality() | VERIFIED/PARTIAL | quality state exists; no universal publication gate |
| journal.Journal._ensure_schema() | PARTIAL | schema migration path exists; immutable migration audit pending |
| journal.Journal.write() | PARTIAL | rich fields are persisted; source/evidence lineage not universal |
| executor.DemoExecutor state transitions | PARTIAL | execution/reconciliation logic exists; end-to-end replay pending |

## Baseline artifacts

The current audit baseline is stored under docs/audit_baseline/:

- BASELINE.txt — timestamp, HEAD, dirty status, runtime identity, Python and dependency hashes;
- working-tree.diff — unstaged working-tree changes;
- index.diff — staged changes;
- untracked.txt — untracked files;
- MANIFEST.sha256 — hashes of baseline artifacts.

The baseline must be captured again after any restart or code change.
