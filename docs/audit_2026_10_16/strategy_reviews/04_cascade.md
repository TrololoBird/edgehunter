# Liquidation exhaustion / climax test

Класс: `ExhaustionStrategy`. [Код](../../../strategies/cascade.py#L112). Commit `f386ec3`, 2026-10-16.

[Источники по ID](../STRATEGY_SOURCES.md) · [Общий путь исполнения](../STRATEGY_COMMON.md) · [Параметры](../STRATEGY_PARAMETERS.md) · [Индекс](../STRATEGIES.md)

Setup: `FLUSH REVERSAL`, `SQUEEZE REVERSAL`.

## Источники и эталон

W1 задаёт смысл climax/secondary test. M2 — исследование intraday reversal, не правила liquidation-стратегии. Нельзя выводить из его abstract готовый tradeable cascade model или универсальное «исследований не существует».

## Данные и таймфреймы

Событие на 1m/5m metrics, реальная наблюдённая liquidation side, start из предшествующих 30 мин, leg extreme следует новым минутам. Структура в плане 15m, trigger5m. Это собственное масштабирование, не Wyckoff4h PhaseA.

## Формулы, условия и параметры

Tier0 price_anomaly (floor+z) и доминирующая liquidation side; minimum leg derived от costs/volatility. Наличие большего long-liquidation notional на падении даёт long candidate, но не определяет, что продажи исчерпаны. Prior trend — сравнение close25-й 1h свечи и start; retraces38.2/50/61.8, zone<=23.6% с RRcap и минимумширины.

## Фактические входы, подтверждения и выходы

В текущей _enter всегда cascade_shadow: реальные карточки-входы/демо не разрешаются. В теневом пути ждёт 5m shift и меньший average volume теста; отдельный narrow-spread test для FLUSH/SQUEEZE не вызывается. Цели mean/map/VWAP и собственные Fib.

## Противоречия и неподтверждённые приписывания

Называть такое событие полноценным Wyckoff SC нельзя: PhaseA range/AR/ST не установлен этим detector. S01 искажает VWAP-цель. Меньший объём теста — проверяемое чтение W1, но усреднение минуты и Fib-константы собственные. Shadow-статус — сознательная политика, не отключение «правильной классики».

## Вердикт

Экспериментальная теневая гипотеза на мотивах Wyckoff; первоисточник не подтверждает конкретные entry/exit formulas.
