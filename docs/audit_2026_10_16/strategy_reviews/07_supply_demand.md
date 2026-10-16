# Seiden / OTA supply-demand

Класс: `SupplyDemandStrategy`. [Код](../../../strategies/maniac_strategies.py#L57). Commit `f386ec3`, 2026-10-16.

[Источники по ID](../STRATEGY_SOURCES.md) · [Общий путь исполнения](../STRATEGY_COMMON.md) · [Параметры](../STRATEGY_PARAMETERS.md) · [Индекс](../STRATEGIES.md)

Setup: `SD DEMAND`, `SD SUPPLY`.

## Источники и эталон

D1/D2 — статьи SamSeiden; D3 — SamEvans/OTA. Они подтверждают качественную механику зон и profit zone. Полный worksheet 8/10 и точные числовые score-формулы в этих статьях не раскрыты. D2 отдельно подтверждает количественный минимум 3:1 для исходного отхода от уровня и смысл profit zone до T1.

## Данные и таймфреймы

Зоны 4h из native h4, detector работает при>=40bars и >=10 найденных баз. Base=последовательность boring bars, departure=последовательность exciting, новый уровень появляется после первого не-exciting close. Такой алгоритм подтверждения не равен исчерпывающему DBR/RBR/RBD/DBD.

## Формулы, условия и параметры

Boring body<=50%range, exciting>50%; strength терцили ATR-speed, time<=median base length. Freshness+2 безусловно новая зона; RR+2 присваивается до проверки. Big picture=daily trend1+нижняя/верхняя половина rolling20day range1, arrival=отсутствие 2/2 противоположного 1h swing. Все эти квантификации — наши, не формулы Seiden.

## Фактические входы, подтверждения и выходы

План touch на 1h, с default touch_confirm_close вход после подтверждения 1h close. Stop distal+pierce и 1ATRfloor. Targets противоположные зоны; sd_opposing называет fresh отсутствие close beyond distal, а не отсутствие прежних touches. Score<8 реально блокирует. Источник profit-zone имеет смысл до ближайшей opposing zone, не до среднего трёх выходов.

## Противоречия и неподтверждённые приписывания

S05: реальный план score10 проходит при TP1≈0.26R и blended≈3.42R, несмотря на собственное обещание «не менее 3:1 profit zone». RR3 применяется к blended; floorTP1=0. Политика confirmation для всех score8–10 тоже не совпадает с таблицей «9–10limit/8confirm». Это не повод угадывать прибыльность модели.

## Вердикт

Авторская числовая операционализация OTA с подтверждённым противоречием RR-контракта; качественное сходство есть, точная классика не доказана.
