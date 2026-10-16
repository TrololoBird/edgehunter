# Bollinger W-bottom / M-top и MethodIII

Класс: `BollingerStrategy`. [Код](../../../strategies/maniac_strategies.py#L240). Commit `f386ec3`, 2026-10-16.

[Источники по ID](../STRATEGY_SOURCES.md) · [Общий путь исполнения](../STRATEGY_COMMON.md) · [Параметры](../STRATEGY_PARAMETERS.md) · [Индекс](../STRATEGIES.md)

Setup: `BB W-BOTTOM`, `BB M-TOP`, `BB3 BUY`, `BB3 SELL`.

## Источники и эталон

B1/B2/B3/B4: различены W/M-pattern и MethodIII alert→confirmation. Для формул имеется авторское подтверждение, для half-at-band+EMA20LTF — нет. Нельзя объединять эти playbook в «один полностью канонический MethodIII».

## Данные и таймфреймы

Оба detector на закрытых 4h. W/M требует>=60bars; первые outside-search с 20-го бара до конца всей переданной истории. BB3 требует>=45bars, alert lookback5; формальное «5bars жизни alert» — наше.

## Формулы, условия и параметры

SMA20±2populationσ и %b=(C−lower)/(upper−lower) соответствуют B1. W/M: последний outside-close, middlepeak, retest с inside-close, A/D выше/ниже, первый break middlepeak. BB3:21barII со знаком, bandtag, strongbar>=50%body,outerthird,range>=median20; последний набор прямо наш. II/A-D используют quotevolume вместо количества актива: классическое volume-подтверждение изменено.

## Фактические входы, подтверждения и выходы

W/M входит current price, стоп retest+pierce/1ATRfloor, half по band at signal, остаток live opposite band и EMA trail. BB3 помечается bb3_shadow. A12: SAR/EMA backlog chronology в общем manager. При текущих flags W/M сохраняет свой trail_after_tp1 из-за band_exit (общее отключение его не снимает).

## Противоречия и неподтверждённые приписывания

S06: после расширения стопа класс.min_rr1 не перепроверяется для trail-path: реальный план проходит при RR1≈0.36. Называть исходное соотношение reward>risk гарантией после floor нельзя. Данные 4h верны для live band; replay15m неверен(A11). Введённый 4h timeframe — наша адаптация, не обязательное правило всех Bollinger systems.

## Вердикт

Формула полос и общая структура patterns подтверждены; параметры confirmation, quote-volume и управление — варианты. Есть воспроизведённый RR-баг; BB3 остаётся теневым.

## Две отдельные версии

| Версия | Условия | Допуск |
|---|---|---|
| W/M | Два экстремума, outside/inside, A/D, пробой промежуточного экстремума | Активна; half TP1 и band/EMA exit |
| BB3 | Alert у полосы + II21 + подтверждающая сильная свеча | Только `bb3_shadow`; не смешивать статистику с W/M |
