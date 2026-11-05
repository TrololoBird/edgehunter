# Edge Hunter — список задач

Обновлено: 2026-11-05

Последнее техническое обновление: 2026-11-06. Release 1/2 изменения опубликованы до `44b2be4`; replay smoke и 14d replay завершаются без падения, но доступный archive cache пропускает BTC/ETH/SOL из-за недостаточной истории. Acceptance replay остаётся открытым до пополнения архива.

## Статус

- [x] Этап 1A внедрён и выложен в production.
- [x] После рестарта precheck прошёл.
- [x] `369` offline-тестов проходят.
- [x] Production-сервис активен, crash-loop после выкладки не обнаружен.
- [ ] Длительное наблюдение памяти и SQLite FD в течение 6–12 часов.
- [ ] Этап 1B: безопасная переработка конкурентности executor.
- [x] Инфраструктурный аудит: проверить расхождения Git, effective systemd и runtime; длительное наблюдение остаётся открытым.
- [ ] Инфраструктурный аудит: внедрить supervisor задач и общий shutdown deadline; общий supervisor остаётся открытым.
- [x] Инфраструктурный аудит: закрывать process pools после завершения потребителей.
- [x] Инфраструктурный аудит: single-flight для `_context_task`.
- [ ] Инфраструктурный аудит: унифицировать connect/read/total/shutdown timeouts; production urllib paths переведены, archive/research paths остаются отдельным длинным контуром.
- [ ] Проверить wall-clock/monotonic для всех TTL, rate-limit и длительностей; rate-limit закрыт, остальные интервалы открыты.
- [x] Проверить атомарность runtime JSON/cache-записей; append-only JSONL остаются отдельным исследованием.
- [ ] Проверить quality/age/error-контракты после broad `except Exception`.
- [ ] Проверить event-loop stalls по live Health и watchdog stack samples.
- [ ] Проверить реальное владение SQLite FD и WAL readers.
- [ ] Проверить process-pool RSS, BrokenProcessPool и порядок shutdown; порядок закрытия исправлен, live RSS/BrokenProcessPool измерения открыты.
- [ ] Проверить websocket reconnect, backoff, ping и cancellation; cancellation/deadline исправлены, live reconnect evidence открыто.
- [ ] Проверить retry/idempotency для внешних REST операций.
- [ ] Проверить разницу dev/effective production конфигурации.

## Этап 1B — executor и исполнение

### Подготовка

- [x] Зафиксировать baseline: RSS, Private_Dirty, SwapPss, `memory.events`, SQLite FD, Health; evidence сохранён, длительная серия открыта.
- [ ] Проверить все пути чтения/изменения `self.open`, `self.pending`, `_unknown_coins` и `_finalized`.
- [ ] Проверить все сетевые пути `_place_stop`, `_place_tps`, `_cancel_orders`, `_cancel_targets`, `_close`, `_finalize`.

### Состояние входа

- [x] Добавить реестр `_inflight` с символом, карточкой, направлением, clientOrderId и фазой.
- [x] Ввести фазы `RESERVED`, `ORDER_SENT`, `FILLED`, `STOP_PENDING`, `PROTECTED`, `REGISTERED`, `UNKNOWN`.
- [x] Сохранять минимальную запись сделки после подтверждения fill до дальнейшего сопровождения.
- [x] Обработать `asyncio.CancelledError` во время create order и постановки стопа.
- [x] Блокировать монету до завершения reconcile для неизвестного результата.

### Блокировки

- [ ] Ввести короткий state lock без `await` внутри критической секции.
- [x] Ввести per-coin lock для сетевых операций одной монеты.
- [ ] Не допустить превышения портфельных, кластерных и TPSL-лимитов через `_inflight`.
- [ ] Убрать 69-секундное ожидание `on_add()` из-под глобального state lock.
- [ ] Перевести `check_limits`, `on_target`, `on_partial`, `on_add` и `close_untracked` на новые границы блокировок.

### Reconcile и ордера

- [ ] Учитывать `_inflight` в `close_untracked()` и reconciliation.
- [ ] Разделить восстановление позиции, стопа и виртуальных TP.
- [ ] Отменять TP только по подтверждённым идентификаторам, не по косвенному типу ордера.
- [ ] Проверить восстановление после таймаута BingX и неоднозначного ответа API.
- [ ] Сохранить корректное пирамидирование Turtles и разрешить доборы юнитов.

## Проверки перед выкладкой 1B

- [ ] Отмена до отправки ордера не создаёт UNKNOWN.
- [ ] Отмена во время create order создаёт UNKNOWN и блокирует монету.
- [ ] Отмена во время постановки стопа не теряет позицию.
- [ ] Отмена после постановки стопа оставляет сделку в `open` и SQLite.
- [ ] Медленный `on_add()` по BTC не блокирует вход по ETH.
- [ ] Два одновременных входа соблюдают cluster/max-trades лимиты.
- [ ] Доборы 2–4 юнитов Turtles не блокируются как OVERLAP.
- [ ] Все 369 текущих тестов проходят.
- [ ] Ruff и precheck проходят.

## Отложено

- [ ] Изменение торговой логики и геометрии Turtles.
- [ ] Массовое сокращение семейств стратегий.
- [ ] Новые process pools.
- [ ] Переписывание архитектуры на отдельные сервисные слои.
- [ ] Изменение параметров риска без отдельного исследования и согласования.
