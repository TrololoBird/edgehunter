# Edwards–Magee trendline break

Класс: `TrendlineStrategy`. [Код](../../../strategies/maniac_strategies.py#L197). Commit `f386ec3`, 2026-10-16.

[Источники по ID](../STRATEGY_SOURCES.md) · [Общий путь исполнения](../STRATEGY_COMMON.md) · [Параметры](../STRATEGY_PARAMETERS.md) · [Индекс](../STRATEGIES.md)

Setup: `TL EM UP`, `TL EM DOWN`.

## Источники и эталон

E1: проверен Brandt, цитирующий E&M. 3% decisive close и volume increase upside реально присутствуют. Цитируемый third test — не просто «двазакрытия»; автоматического 1h+15m trading robot источник не задаёт.

## Данные и таймфреймы

Detector1h, окно tl_lookback400, минимум tl_min_span40+10 баров; последние два 2/2 high или low дают линию. Pivots и предшествующие closes построены без двух breakout bars. Математическая линейная интерполяция корректна.

## Формулы, условия и параметры

Для UP нужны falling highs, DOWN rising lows; два close за линией на 3% оттекущейцены и первый close-breakout ранее не случился. Upside volume первого breakoutbar>20barmean; downside не требует — соответствует асимметрии в источнике. Последние два pivots не обеспечивают геометрическую значимость всех возможных трендовых линий. 2/2,2closes,20barmean — дополнительные квантификации.

## Фактические входы, подтверждения и выходы

Затем отдельное ожидание retest и 15m shift. Стоп last3/3 1h pivot/last40extreme с measuredpierce; targets HTF liquidity map. В sig фиксируется значение диагонали при detector event; plan ждёт возврат к этому **горизонтальному** price, не пересчитывает будущую диагональ на время retest.

## Противоречия и неподтверждённые приписывания

Docstring обещает restinglimit/согласованный flow, но close-shift и flow лишь записывается. Параметры tl_pivot, tl_min_touches, tl_touch_atr, tl_touch_gap и многие другие не используются текущим detector; реально прочитаны tl_lookback/tl_min_span. Перенос 3% из акции на hourlycrypto не подтверждён E1.

## Вердикт

Некоторые classic penetration ideas перенесены верно, но получилась своя двухэтапная стратегия. Нельзя приписывать E&M retest на фиксированной цене и 15mMSS.
