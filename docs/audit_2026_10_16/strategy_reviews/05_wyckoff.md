# Wyckoff spring / UTAD

Класс: `WyckoffRangeStrategy`. [Код](../../../strategies/wyckoff_range.py#L200). Commit `f386ec3`, 2026-10-16.

[Источники по ID](../STRATEGY_SOURCES.md) · [Общий путь исполнения](../STRATEGY_COMMON.md) · [Параметры](../STRATEGY_PARAMETERS.md) · [Индекс](../STRATEGIES.md)

Setup: `SPRING`, `UTAD`.

## Источники и эталон

W1 и V1: опубликованные материалы школы/автора VSA. Не буквальная механическая спецификация всей книги Wyckoff/Pruden/Weis.

## Данные и таймфреймы

Действительно 4h bars из 1h history, не 1h из module docstring. `_phase_a` ищет SC/BC→AR→ST до последнего бара; последний бар spring/UTAD. Range основан на событиях, не фиксированном пятичасовом окне.

## Формулы, условия и параметры

Climax=одновременно maxvolume и minlow/maxhigh от 2/2 pivot; AR=абсолютный последующий extreme; ST=последующий extreme на меньшем volume. Это наши proxies: классика не требует, чтобы climax всегда был абсолютным максимумом объёма. PhaseB достаточность не измеряется. Spring=wick beyond + close back, half-wick/30% уже удалены. P&F=close-only columns×(rangeheight/10)×3, Weis reversal=3boxes: box-size и линия count — авторские решения.

## Фактические входы, подтверждения и выходы

Test zone extreme↔edge, вход через shift на TF ниже; для 4h trigger60m, не 15m из docstring. Volume-test реально может veto, не проходит через shadow_veto. Дополнительный spread-test сравнивает 15m диапазоны с 4h spring. Стоп structural+pierce/floor, цели rangefar/P&F, остальные фильтры часто shadow.

## Противоречия и неподтверждённые приписывания

S04: spread comparison делит spring на 2, что соответствовало 1h→15m, а detector уже 4h (при собственной sqrt(time) модели нужно 4). S11: pnf_target есть в первичном плане, но не в fillers; при совпадении с LTF-ценой он удаляется при входе. В воспроизведённом плане цели 110/140/140 превращаются в три выхода около 109.669; P&F 140 теряется. Фраза «Wyckoff покупает только test, никогда spring» чрезмерно категорична: школа различает варианты spring. P&F арифметика не доказывает правильный выбор count line.

## Вердикт

Структурный proxy Wyckoff с собственным P&F и неверно согласованным spread-TF. Эквивалентность полному классическому процессу не подтверждена.
