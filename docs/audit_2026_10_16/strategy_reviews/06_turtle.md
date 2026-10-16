# Turtle System1 / System2

Класс: `BreakoutStrategy`. [Код](../../../strategies/breakout.py#L91). Commit `f386ec3`, 2026-10-16.

[Источники по ID](../STRATEGY_SOURCES.md) · [Общий путь исполнения](../STRATEGY_COMMON.md) · [Параметры](../STRATEGY_PARAMETERS.md) · [Индекс](../STRATEGIES.md)

Setup: `BREAKOUT UP`, `BREAKOUT DOWN`.

## Источники и эталон

T1: проверены главы Position Sizing, Entries, Stops, Exits. T2 — дополнительная сверка реализации. Точное соответствие оценивалось по фактическому detector→plan→executor.

## Данные и таймфреймы

Daily CLOSED history>=60, канал 20/55 excluding running day. Новый final1m high/low определяет crossing; защита от уже случившегося today crossing использует 15m+1m. Это задержанный minute-based detection, не tick execution original.

## Формулы, условия и параметры

TR=max(H−L,|H−prevC|,|L−prevC|), N seeded20TR then(19N+TR)/20: соответствует. S1 historical filter использует ns[i], включающий TR самого дня пробоя, и mark-to-market ещё открытой гипотетической позиции: это не буквальная исходная классификация breakout loss. 0.5N add и максимум 4units соответствуют; глобальный cap6 трактует все coins как closely-correlated, собственное допущение.

## Фактические входы, подтверждения и выходы

Событие по минутному high/low, вход по current market. S02: stop=breakoutlevel−2N, не actualentry−2N. При level100,N5,entry110 effectiveSL90=4N, оригинал 2N. A08: канал 10/20 проверяется scan price и пропускает wick-cross. Adds только по текущей цене скана, не всем пропущенным ступеням внутри минут. A10 искажает unit result. Volume/OI/spot не обязательны — правильно.

## Противоречия и неподтверждённые приписывания

Sizing теперь 1% account на полное SL-distance, не original1% perN; comment eng91 признаёт изменение. `turtle_unit_risk=.01` нигде не читается. Стопы прежних units уравниваются с новым, тогда как источник оговаривает gap/slippage cases. Перенос с традиционных futures на crypto и notional cap также меняют систему.

## Вердикт

Наиболее чёткий первоисточник, но не точная Turtle-replica: существенны цена отсчёта 2N, intraminute exits и исторический winner-filter; sizing изменён осознанно.
