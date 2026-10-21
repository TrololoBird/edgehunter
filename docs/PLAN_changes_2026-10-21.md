# Планируемые изменения (ведётся с 2026-10-21)

Статусы: ЖДЁТ = нужно «да» владельца; ТЕСТ = ждёт облачного исследования; ГОТОВО = в master, не выкачено.

| # | Что | Статус | Где |
|---|-----|--------|-----|
| 1 | График: юниты Turtle, источник стопа, линия N-дн. выхода, маркеры по бару, дедуп подписей оси; снимок deque (fetcher/scanner) | ГОТОВО (9ec8407), выкатка ЖДЁТ | webui.py, web/app.js, web/style.css |
| 2 | Turtle: варианты A, B, C, D, D2, E, F1, F2/F2b, G, H на архиве; сначала сверить базы (-0.171R vs +1.11R) | ТЕСТ | research/TASK_turtle_variants.md |
| 3 | Выбор варианта Turtle по итогам п.2 (правила Turtle меняются только по решению владельца) | ЖДЁТ п.2 | signal_book.py, strategies/turtle.py |
| 4 | Закрытия ORPHAN при рестартах (10-18 04:47, 10-21 12:12-12:15): разобрать причину | ЖДЁТ «да» на разбор | executor.py, signal_book.py |
| 5 | Устаревшие docstrings: strategies/__init__.py (удалённые thirdeye/fib05/bomberman/oi_accum/smt), breakout.py (старый пробой вместо Turtle), ARCHITECTURE (BULL F/BEAR D, AUCTION как POC retest) | можно сразу (документация) | strategies/, docs/ARCHITECTURE.md |
| 6 | Проверить: демо торгует только стратегии с профилем (profiles.py) - но Turtle без профиля торговался | проверка | profiles.py, executor.py |
| 7 | ORB: стоп «середина диапазона» в описании класса vs противоположный уровень в детекторе | проверка | strategies/classic*.py |
| 8 | Живой срез Turtle-карточек по ликвидациям / RushBook / айсбергам / тегу Monitoring (описательно, n~25) | после п.2 | journal |
