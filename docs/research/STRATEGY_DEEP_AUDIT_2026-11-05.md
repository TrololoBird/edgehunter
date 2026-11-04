# Глубокий аудит trendline / pump / bollinger / breakout / continuation

Дата: 2026-11-05

## Правило решения

Стратегии не отключаются по этому отчёту. Изменение принимается только после
разделения по setup и направлению, cluster-weighted bootstrap, holdout-проверки
и сравнения с placebo. Цель исправления — улучшить out-of-sample R и сохранить
корректность исполнения.

## Выборка

Таблица из запроса содержит 59 сделок и `-32.69R`, то есть примерно `-0.55R`
на сделку. Она не совпадает с полной live demo-выборкой: за последние 7 дней
закрыто 148 trendline, 172 pump, 52 bollinger, 16 breakout и 2 continuation.
Следовательно, исходную таблицу нельзя смешивать с полной базой без восстановления
её SQL-фильтра, периода и logic version.

За последние 7 дней cluster-weighted средние по полной базе:

| family | closed | mean R | 4h clusters | mean cluster R |
|---|---:|---:|---:|---:|
| trendline | 148 | -0.42 | 47 | -0.32 |
| pump | 172 | -0.42 | 39 | -0.27 |
| bollinger | 52 | -0.37 | 16 | -0.15 |
| breakout | 16 | -0.40 | 10 | -0.39 |
| continuation | 2 | -0.47 | 2 | -0.47 |

## Направления и setup

| strategy / setup | direction | N | mean R | sum R | wins |
|---|---:|---:|---:|---:|---:|
| trendline | short | 154 | -0.24 | -37.18 | 64 |
| trendline | long | 76 | -0.77 | -58.60 | 15 |
| pump | short | 231 | -0.14 | -32.40 | 118 |
| pump | long | 58 | -0.12 | -6.80 | 29 |
| bollinger | short | 18 | +0.46 | +8.22 | 15 |
| bollinger | long | 64 | -0.64 | -40.94 | 16 |
| breakout | short | 22 | -0.25 | -5.58 | 8 |
| breakout | long | 14 | -0.94 | -13.23 | 0 |

Самые важные ветки для исправления:

- `TL TOUCH UP` long: 72 cards, `-0.89R` mean, 11 wins;
- `TL TOUCH DOWN` short: 127 cards, `-0.62R` mean, 37 wins;
- `DUMP START` short: 174 cards, `-0.42R` mean, 73 wins;
- `PUMP START` long: 44 cards, `-0.55R` mean, 15 wins;
- `BB W-BOTTOM` long: 41 cards, `-0.89R` mean, 5 wins;
- `BB3 BUY` long: 11 cards, `-0.95R` mean, 1 win;
- `BB1 UP` long: 10 cards, `-0.99R` mean, 0 wins;
- `BB1 DOWN` short: 21 cards, `-0.23R` mean, 8 wins.

Положительные контрольные ветки присутствуют внутри тех же семейств:

- Bollinger short: `+0.46R` mean;
- `BB M-TOP` short: положительный результат при малой выборке;
- `BB3 SELL` short: положительный результат при малой выборке.

Это указывает на directional/regime/entry problem, а не на необходимость
удалить целое семейство.

## Execution separation

В demo/card сравнении за текущий период разница небольшая:

- trendline: demo примерно на `+0.05R` относительно card;
- pump: примерно `-0.08R`;
- bollinger: примерно `+0.01R`;
- breakout: примерно `+0.07R`.

Основной ущерб находится в сигнале/направлении. Отдельно нужно считать
`NO_MARKET`, `PRICE_GAP`, `OVERLAP`, `NO_SLOT` и не смешивать их с реальными SL.

## Внешняя проверка методики

Внешние источники не доказывают прибыльность конкретной реализации, но задают
проверяемые механические ожидания:

- trendline/reversal требует подтверждения структуры, а не только касания линии:
  [Charles Schwab: chart patterns](https://www.schwab.com/learn/story/how-to-read-stock-charts-and-trading-patterns);
- breakout должен проверяться объёмом и подтверждением продолжения:
  [Charles Schwab: volume and trends](https://www.schwab.com/learn/story/ways-volume-can-help-confirm-trends);
- breakout без подтверждения подвержен false move:
  [Charles Schwab: day trading and breakout confirmation](https://international.schwab.com/story/introduction-to-pattern-day-trader-rules);
- резкие движения в тонких crypto-токенах имеют отдельный pump/dump и liquidity risk:
  [CFTC virtual-currency pump-and-dump advisory](https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/beware_virtual_currency_pump_dump.html).

## Следующие исправления

1. Ввести holdout-разрез по `setup × direction`, не меняя live logic.
2. Проверить для trendline подтверждение структуры, slope/age/touches и старший bias.
3. Для pump разделить `PUMP START`, `DUMP START`, `DUMP BOUNCE` и измерить latency/liquidity.
4. Для Bollinger сравнить W-bottom/M-top/BB3 по направлению, regime и band expansion.
5. Для breakout проверить close-through-level, volume confirmation, retest и distance to opposing zone.
6. Сравнить изменённые правила с placebo, затем только подготовить code patch.

## Реализованный кандидат `eng-170a`

В dev добавлено симметричное подтверждение reversal-входа:

- trendline third touch требует directional close тела touch-candle;
- Bollinger W/M и BB3 требуют reclaim средней полосы в сторону сделки;
- прежняя логика остаётся доступной в старых journal rows для holdout-сравнения.

Это candidate patch, а не окончательный verdict: перед дальнейшим rollout нужны
replay/holdout и сравнение cluster-weighted R с `eng-169l`.

