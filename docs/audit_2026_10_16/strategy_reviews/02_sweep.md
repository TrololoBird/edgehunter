# Liquidity sweep / ICT2022

Класс: `SweepStrategy`. [Код](../../../strategies/level.py#L107). Commit `f386ec3`, 2026-10-16.

[Источники по ID](../STRATEGY_SOURCES.md) · [Общий путь исполнения](../STRATEGY_COMMON.md) · [Параметры](../STRATEGY_PARAMETERS.md) · [Индекс](../STRATEGIES.md)

Setup: `SWEEP LOW`, `SWEEP HIGH`.

## Источники и эталон

I2 (ограничен доступ к оригинальному видео); Osler-подобные исследования clustering stops подтверждают лишь возможность концентрации стопов, а не конкретную эту торговую систему. Не используется как доказательство её прибыльности.

## Данные и таймфреймы

Setup на закрытой 15m; pools собираются as-of перед баром из 1h+ swings, EQ, prevday/week, sessions; уже взятые pools удаляются. rank выбирает TF: swing→15m/trigger5m, session/EQ→1h/15m, day/week→4h/60m. Это собственная таблица, не выведенная из ICT.

## Формулы, условия и параметры

Вынесенный high/low + close обратно. Default depth0.1..1ATR только без pierce model; с моделью floor0 и max=p90 overshoot. RVOL минимум 0 (фильтр отключён), round pools запрещены, minage0. Pool significance rank и shallowest-tie — авторские. fvg_setup требует последнего 3-candle swing до raid и gap, а MSS допускает max(close middle,close third) за swing.

## Фактические входы, подтверждения и выходы

Sweep лишь arms FVG; затем entry через touch_confirm, не немедленный вход по raid. Bias/HTF POI/killzone/premium flags могут стать shadow. Защитные no_data/no_leg и геометрия реально блокируют. Стоп beyond sweep и общего protected/pool/pierce/floor; цели opposite liquidity, по трети, без фиксированного дневного гарантийного draw.

## Противоречия и неподтверждённые приписывания

Слова «на объёме», «обязательный bias/killzone» не описывают current defaults. Sweep-TF не определяется timeframe источника механически в классике. Формирование pool as-of — правильное решение; A04 по агрегации остаётся. Индексированное no_spring_test сюда не относится: нельзя объявить все no_* безусловно пропускающими.

## Вердикт

Кодификация raid→MSS/FVG существует, но контекст и исполнение изменены автором; соответствие всех обязательных исходных условий не доказано.
