# Инфраструктурный аудит Edge Hunter

Дата: 2026-11-03

Цель: проверить инфраструктуру по фактическому коду и конфигурации, не принимая комментарии и старые аудиты как доказательство.

## Подтверждённые расхождения

### INF-01 — документация о MemoryHigh не соответствует effective unit

В `deploy/edgehunter-bot.service` указано `MemoryHigh=2G`, но production drop-in `/etc/systemd/system/edgehunter-bot.service.d/memory.conf` переопределяет его на `3G`. Текущее effective значение подтверждено через `systemctl show`. Любые выводы по порогу должны ссылаться на effective unit, а не только на файл в Git.

### INF-02 — precheck проверяет весь репозиторий, включая evidence и тестовые артефакты (**исправлено**)

`deploy/precheck.sh` запускает Ruff по `.`. Поэтому сохранённые Python-выдержки аудита и тестовые заготовки становятся причиной отказа старта, даже если production-модули исправны. Это уже проявилось при deploy: сервис не стартовал до удаления таких файлов из production-коммита. Исправлено в текущем инфраструктурном изменении: runtime gate исключает `docs/evidence`, offline audit checks, `research*` и `tests`; тесты остаются отдельной dev/CI-проверкой.

### INF-03 — часть SQLite-соединений намеренно долгоживущая, а часть readers живёт дольше запроса

`journal.SignalJournal.conn` — постоянное соединение. `webui.JournalReader._conn()` создаёт read-only соединение на запрос и закрывает его в вызывающих методах; это нужно проверять по каждому пути, а не считать количество FD доказательством утечки. После текущего рестарта production наблюдались 3 FD `signals.db`, 1 WAL и 1 SHM: это не равно 3 утечкам без сопоставления с потоками journal/webui.

### INF-04 — комментарии всё ещё утверждают periodic gc.freeze после удаления вызовов (**исправлено**)

В `main.py` сохранился комментарий о том, что история `gc.freeze()`d fetcher'ом, хотя вызовы были удалены из `fetcher.py`. Это создавало ложную модель эксплуатации. Комментарий заменён и теперь явно фиксирует отсутствие `gc.freeze()` в fetcher.

### INF-05 — background tasks не имеют единого владельца (**частично исправлено**)

`Scanner` хранит собственные `_tasks` и `_background`, `DataFetcher` — `_tasks` и `_background_tasks`, `Notifier` — собственные fire-and-forget tasks. Ранее `smallcap`, `webui` и book snapshots в `fetcher` создавали задачи вне shutdown-реестров. Теперь эти задачи зарегистрированы у владельцев; retry task `Notifier` также дожидается отмены. Общий реестр для всех компонентов и единая политика ошибок остаются отдельной задачей.

## Гипотезы, требующие измерения

- Рост `memory.current` после стабилизационного рестарта может быть native allocator/Polars, а не Python GC; текущая лёгкая метрика не разделяет владельцев.
- Один event loop обслуживает websocket callbacks, scanner loops, REST tasks и webui; комментарии о GIL не доказывают конкретный источник задержки без task latency и queue depth.
- ProcessPool ML/maps создаются лениво и используют `spawn`; нужно измерить RSS каждого worker и поведение при `BrokenProcessPool`, а не судить по parent RSS.
- `Notifier` сохраняет outbox, но порядок и backoff сообщений нужно проверять по фактическим `card/event/seq`, включая закрытие во время 429.

## Подтверждённые проблемы жизненного цикла

### INF-06 — сетевые await выполняются под глобальным executor lock

AST-проверка показывает `await` внутри `async with self._lock` в `on_entry`, `check_limits`, `on_target`, `on_partial`, `on_add`, `on_finish` и `reconcile_loop`. Блокировка действительно охватывает REST, sleeps и обработку закрытия. Снятие блокировки требует резерва состояния, иначе `close_untracked` увидит биржевую позицию до регистрации в `self.open`.

### INF-07 — shutdown не имеет общего deadline для всех задач (**исправлено**)

`Scanner.stop()` ранее отменял задачи и ждал `asyncio.gather(*tasks)` без timeout. Теперь внешний cleanup-контур в `main.py` ограничен 75 секундами, что оставляет запас до systemd `TimeoutStopSec=90`; локальные таймауты `DataFetcher.stop()` сохраняются.

### INF-08 — process pools закрываются до отмены потребителей (**исправлено**)

`Scanner.stop()` ранее закрывал anomaly/maps pools до отмены задач, которые могут ждать `run_in_executor`. Это создавало гонку штатного shutdown с `BrokenProcessPool` и отменёнными futures. Теперь pools закрываются после отмены и ожидания scanner-задач.

### INF-09 — задача контекста может быть заменена без отмены предыдущей

`_context_task` получает новый `asyncio.create_task()` в нескольких местах. Старый task перед заменой не отменяется и не ожидается. При медленном обновлении возможны параллельные записи общего mutable контекста и лишняя нагрузка.

### INF-10 — fire-and-forget задачи имеют разные политики ошибок

`Scanner._background_task()` регистрирует задачу, но не задаёт единый обработчик результата; `Notifier.send()`, `webui` и `smallcap` создают собственные задачи. Исключения и cancellation не имеют единого owner/name/метрики, поэтому часть отказов может быть замечена только как unhandled-task warning.

### INF-11 — сетевые timeout-контракты не унифицированы

Вызовы используют 15, 20, 30 и 900 секунд, а часть timeout задаётся внешним `wait_for`. Нет единого разделения `connect/read/total`, retry и shutdown timeout. 900-секундный Hyperliquid download особенно плохо согласуется с остановкой systemd за 90 секунд.

## Приоритет следующего исследования

1. Снять 30–60 минут task/queue/FD/memory telemetry без тяжёлого object-walk.
2. Построить таблицу владельцев всех asyncio tasks и их shutdown-пути.
3. Проверить долгоживущие SQLite connections по `/proc/<pid>/fd` и месту создания.
4. Сопоставить effective systemd settings с Git-файлами.
5. Исправить stale-комментарии и precheck-политику отдельным инфраструктурным коммитом.
6. Только после этого продолжать executor Stage 1B.

## Что не считается доказательством

## Дополнительные findings

## Production-срез после рестарта

На текущем PID 2497: `NRestarts=0`, `MemoryHigh=3G` (effective drop-in), RSS около 1.5 GiB, `memory.current` около 2.44 GiB, swap около 8 KiB, `memory.events.high=0`, `oom_kill=0`. Это подтверждает отсутствие текущего OOM, но не доказывает отсутствие долгосрочного наклона.

Health за последний период показывает повторяющиеся event-loop stalls до 1.5 секунды. Стеки указывают на `signal_book._input/_card_gate`, `levels.resample`, `strategies.loopside` и `ind_panel.rolling_min`. Значит, после исправления кэша остаётся синхронная CPU-нагрузка в основном loop; утверждение, что все задержки устранены кэшированием, неверно.

В том же периоде `scan` обычно 0.2–0.5 секунды, но отдельные проходы достигают 1–2.3 секунды. `memory.current` заметно выше Health RSS, поэтому для оценки утечки нужно отдельно учитывать native/cache/cgroup working set.

### INF-12 — проблема Telegram фактически сохраняется

В `notifier._post()` lock удерживается во время HTTP retry, а `await asyncio.sleep(min(wait, 60.0) + 0.5)` выполняется внутри lock. При 429 с `retry_after > 60` значение обрезается, а приоритетные сообщения ждут `PRIORITY_LOCK_WAIT_SEC` и получают `ConnectionError`.

### INF-13 — wall-clock используется для интервалов

`ratelimit.BanState.wait`, REST-бюджет, TTL неизвестного входа и другие интервалы используют `time.time()`. NTP-коррекция может сократить или продлить ожидание. Для длительностей нужен `time.monotonic()`.

### INF-14 — локальные cache-файлы пишутся неодинаково

`macro.py` пишет JSON напрямую через `open(..., 'w')` и `json.dump`, а `official_calendar.py` использует собственный временный файл вместо общего durable helper. При OOM или kill cache может стать обрезанным.

### INF-15 — broad catches могут скрывать неполноту данных

В `fetcher`, `extdata`, `positioning`, `strategies` и `executor` многочисленные `except Exception` логируют ошибку и продолжают цикл. Без обязательных полей age/coverage/error отказ источника превращается в обычный `None` или stale-значение.

- комментарий в коде без telemetry;
- число `memory.events.high` без `memory.current`, PSI и временной шкалы;
- число FD без владельца соединения;
- успешный импорт модуля как доказательство корректного shutdown;
- offline replay, если он использует другую версию данных, геометрии или execution model.

## Проверка инфраструктурного исправления

Изменения ограничены `deploy/precheck.sh`, `main.py`, `scanner.py`, `smallcap.py`, `webui.py`, `fetcher.py`, `notifier.py` и этой документацией; production unit и runtime не изменялись. Проверки: `sh -n deploy/precheck.sh`, Ruff gate по production-коду, импорт стартового пути, проверка неизвестных стратегий, Pylint E0601/E0602/E0606 и `357 passed` (`pytest tests -q`; часть старых audit-заготовок была удалена удалённым cleanup-коммитом).

Read-only snapshot текущего процесса после проверки: `MainPID=2497`, `NRestarts=0`, `MemoryHigh=3G`, `MemoryCurrent=2,208,137,216`, RSS `1,330,632 kB`, swap `280,208 kB`, `memory.events.high=0`, `oom_kill=0`, 34 threads. Для `signals.db` видны 3 основных FD (`db`, `-wal`, `-shm`) и 3 read-only FD; read-only ownership требует отдельного сопоставления с callers и не считается утечкой по одному числу.
