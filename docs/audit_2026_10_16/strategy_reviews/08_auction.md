# Failed auction / AMT

Класс: `AuctionStrategy`. [Код](../../../strategies/maniac_strategies.py#L130). Commit `f386ec3`, 2026-10-16.

[Источники по ID](../STRATEGY_SOURCES.md) · [Общий путь исполнения](../STRATEGY_COMMON.md) · [Параметры](../STRATEGY_PARAMETERS.md) · [Индекс](../STRATEGIES.md)

Setup: `AUCTION LONG`, `AUCTION SHORT`.

## Источники и эталон

Dalton TPO convention проверена в предыдущем A01; происхождение точного алгоритма «два 30m close beyond=acceptance, один 30m return=oppositeedge» в доступном авторском материале не установлено. Это следует честно назвать нашей formalization of AMT.

## Данные и таймфреймы

Одноимённая сессия предыдущего буднего дня по локальному календарю, current session open INSIDE its VA,15m data grouped pairs into30m. >=80% прошлых 15m bars считается достаточным, даже при пропущенных сегментах. Выход сессии хранится в signal.

## Формулы, условия и параметры

TPO вычисляется неверно (A01): вес свечи делится на количество строк и 15m периоды не объединены в 30m. Проверка acceptance закрытиями — не эквивалент TPO времени у цены. Исторические два close outside в любой части сессии запрещают модель целиком. Probe extreme берётся по всей сессии, может быть не тем probe, что породил последний return.

## Фактические входы, подтверждения и выходы

Entry current price после return30m, stop beyondprobe+pierce/floor; target farVA, repeated own targets (вся позиция там), session exit. Докстринг `_confirm_plan` «at the close» не гарантирует fill по historicalclose; price_of берётся на скане. MinRR1 — наша политика, не доказанный Dalton bound.

## Противоречия и неподтверждённые приписывания

Ядро исходного profile неверно, поэтому входы и цели не сравнимы с классическим TPO. Название failed auction не доказывает источник всех правил. Нельзя обещать 80% likelihood; это иной setup, чем VA80. Обязательного отдельного подтверждения объёмом при defaults нет.

## Вердикт

Не считать проверенной реализацией AMT: профиль требует исправления, точные event rules — обоснования и явной спецификации.
