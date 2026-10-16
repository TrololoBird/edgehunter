# Параметры: значение, происхождение, реальное чтение

Срез `f386ec3`, 2026-10-16. Все 155 значений из `CONFIG.levels`, `CONFIG.strategies`, `CONFIG.orderflow` и четырёх значимых executor-политик перечислены ниже. Секреты не извлекались. Это не перечень всех настроек exchange/сканера: каналы данных и их фактические ограничения разобраны в dossier и COMMON.

«Собственный выбор» не означает плохой параметр. Он означает отсутствие доказательства, что именно это число обязательно у заявленного автора. Авторский перенос на crypto/4h, отключённый guard и математическая ошибка различаются.

Ссылки чтения получены по AST-атрибутам и строковым `getattr` вне config/tests. Это кандидаты использования, включая legacy/research, а не доказательство достижимости live-пути. Непрямое чтение TTL по имени разобрано отдельно. Полный список ссылок — `strategy_parameter_refs.json`.

## levels

| Параметр | Default | Происхождение / смысл | Чтение в коде |
|---|---|---|---|
| `htf_lookback_candles` | `48` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | нет прямого AST-чтения |
| `leg_lookback_hours` | `96` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | нет прямого AST-чтения |
| `impulse_min_atr` | `0.0` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | [levels.py:38](../../levels.py#L38) |
| `impulse_min_candles` | `4` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | [levels.py:90](../../levels.py#L90) |
| `impulse_min_move` | `0.0` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | [levels.py:46](../../levels.py#L46) |
| `cost_guard` | `1.0` | Модель исполнения проекта: единицы bps/секунды/$ и ликвидность. Требует сверки с fills, не является правилом классика. | [levels.py:46](../../levels.py#L46), [strategies/geometry.py:245](../../strategies/geometry.py#L245), [strategies/geometry.py:577](../../strategies/geometry.py#L577) |
| `continuation_zone` | `[0.62,0.79]` | OTE-подобные 62–79%; полная авторская спецификация ICT не получена (I2). | [strategies/leg.py:112](../../strategies/leg.py#L112) |
| `continuation_invalid` | `1.0` | 100% импульса — структурная отмена собственного OTE-плана. | [strategies/leg.py:140](../../strategies/leg.py#L140) |
| `macro_before_min` | `10` | Операционная политика macro-event protection; не авторское правило паттерна. | [macro_calendar.py:56](../../macro_calendar.py#L56) |
| `macro_after_min` | `45` | Операционная политика macro-event protection; не авторское правило паттерна. | [macro_calendar.py:56](../../macro_calendar.py#L56) |
| `macro_guard_min` | `0` | Операционная политика macro-event protection; не авторское правило паттерна. | [signal_book.py:1446](../../signal_book.py#L1446), [signal_book.py:1449](../../signal_book.py#L1449) |
| `continuation_targets` | `[1.0,1.2,1.272,1.618]` | Авторская корзина extensions; 1.2 не точный Fibonacci ratio. Нет доказательства обязательности всей корзины ICT. | [levels.py:168](../../levels.py#L168), [strategies/geometry.py:703](../../strategies/geometry.py#L703), [strategies/geometry.py:709](../../strategies/geometry.py#L709) (+2) |
| `reversal_zone_max` | `0.236` | Собственная Fib-геометрия climax/pump; не формула Wyckoff или VSA из первоисточника. | [strategies/cascade.py:140](../../strategies/cascade.py#L140) |
| `reversal_targets` | `[0.382,0.5,0.618]` | Собственная Fib-геометрия climax/pump; не формула Wyckoff или VSA из первоисточника. | [levels.py:38](../../levels.py#L38), [levels.py:46](../../levels.py#L46), [strategies/cascade.py:138](../../strategies/cascade.py#L138) |
| `ltf_break_lookback` | `5` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | [research/scripts/research_cards.py:761](../../research/scripts/research_cards.py#L761) |
| `ltf_flow_candles` | `3` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | [levels.py:257](../../levels.py#L257) |
| `stop_buffer_atr` | `0.3` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | [strategies/cascade.py:136](../../strategies/cascade.py#L136), [strategies/geometry.py:416](../../strategies/geometry.py#L416), [strategies/geometry.py:508](../../strategies/geometry.py#L508) (+2) |
| `min_stop_atr` | `1.0` | Собственный native-ATR floor, может нарушить source-defined max loss и предварительный RR (S06/S07). | [levels.py:38](../../levels.py#L38), [strategies/geometry.py:91](../../strategies/geometry.py#L91), [strategies/geometry.py:423](../../strategies/geometry.py#L423) (+2) |
| `max_stop_pct` | `0.0` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | [strategies/geometry.py:82](../../strategies/geometry.py#L82) |
| `zone_buffer_atr` | `0.0` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | [strategies/geometry.py:376](../../strategies/geometry.py#L376), [strategies/geometry.py:504](../../strategies/geometry.py#L504) |
| `min_rr_tp1` | `1.0` | Собственная политика net RR, несмотря на имя применяется и к blended; см. S05/S06. | [executor.py:395](../../executor.py#L395), [strategies/geometry.py:277](../../strategies/geometry.py#L277), [strategies/geometry.py:752](../../strategies/geometry.py#L752) |
| `veto_low_rr` | `true` | Политика отказа при вычисленном low_rr; не исправляет неверно вычисленный или пропущенный guard. | [research/scripts/research_cards.py:619](../../research/scripts/research_cards.py#L619), [signal_book.py:1054](../../signal_book.py#L1054), [signal_book.py:1092](../../signal_book.py#L1092) |
| `fill_delay_sec` | `30` | Модель исполнения проекта: единицы bps/секунды/$ и ликвидность. Требует сверки с fills, не является правилом классика. | нет прямого AST-чтения |
| `slippage_bps` | `5.0` | Модель исполнения проекта: единицы bps/секунды/$ и ликвидность. Требует сверки с fills, не является правилом классика. | [fetcher.py:2253](../../fetcher.py#L2253), [levels.py:45](../../levels.py#L45), [levels.py:310](../../levels.py#L310) (+6) |
| `slippage_ref_volume` | `500000000.0` | Модель исполнения проекта: единицы bps/секунды/$ и ликвидность. Требует сверки с fills, не является правилом классика. | нет прямого AST-чтения |
| `slippage_max_bps` | `25.0` | Модель исполнения проекта: единицы bps/секунды/$ и ликвидность. Требует сверки с fills, не является правилом классика. | [levels.py:313](../../levels.py#L313) |
| `slippage_notional_usd` | `10000.0` | Модель исполнения проекта: единицы bps/секунды/$ и ликвидность. Требует сверки с fills, не является правилом классика. | [levels.py:312](../../levels.py#L312) |
| `slippage_half_spread_bps` | `1.0` | Модель исполнения проекта: единицы bps/секунды/$ и ликвидность. Требует сверки с fills, не является правилом классика. | [levels.py:313](../../levels.py#L313) |
| `slippage_impact_sigma` | `0.04` | Модель исполнения проекта: единицы bps/секунды/$ и ликвидность. Требует сверки с fills, не является правилом классика. | [levels.py:312](../../levels.py#L312) |
| `target_through_bps` | `2.0` | Модель исполнения проекта: единицы bps/секунды/$ и ликвидность. Требует сверки с fills, не является правилом классика. | [levels.py:381](../../levels.py#L381), [research/scripts/research_cards.py:815](../../research/scripts/research_cards.py#L815), [signal_book.py:1348](../../signal_book.py#L1348) |
| `spring_test_volume_ratio` | `1.0` | Смысл уменьшения объёма поддержан W1/V1; средние/точный коэффициент — квантификация проекта. | [levels.py:275](../../levels.py#L275) |
| `spring_test_spread_ratio` | `0.6` | 0.6 — наша квантификация сужения; делитель 2 не согласован с нынешним 4h spring (S04). | [levels.py:291](../../levels.py#L291) |
| `watch_ttl_sec` | `21600` | Собственный срок; обычный TTL подавлен structural_lifetimes=True, кроме собственных session/exit веток. | [signal_book.py:843](../../signal_book.py#L843), [signal_book.py:844](../../signal_book.py#L844), [strategies/base.py:133](../../strategies/base.py#L133) |
| `plan_wait_sec` | `180` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | [signal_book.py:849](../../signal_book.py#L849) |
| `zone_ttl_sec` | `10800` | Собственный срок; обычный TTL подавлен structural_lifetimes=True, кроме собственных session/exit веток. | [strategies/base.py:133](../../strategies/base.py#L133) |
| `trade_ttl_sec` | `28800` | Собственный срок; обычный TTL подавлен structural_lifetimes=True, кроме собственных session/exit веток. | [replay.py:469](../../replay.py#L469), [research/scripts/research_book_flow.py:244](../../research/scripts/research_book_flow.py#L244), [research/scripts/research_entries_placebo_eng133.py:195](../../research/scripts/research_entries_placebo_eng133.py#L195) (+3) |
| `min_rr_tp1_floor` | `0.0` | 0 отключает дополнительный floor ближайшей цели; из-за этого blend может пропустить слабый TP1. | [strategies/geometry.py:257](../../strategies/geometry.py#L257), [strategies/geometry.py:258](../../strategies/geometry.py#L258), [strategies/geometry.py:590](../../strategies/geometry.py#L590) |
| `finished_display_sec` | `1800` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | [signal_book.py:433](../../signal_book.py#L433), [signal_book.py:1532](../../signal_book.py#L1532) |

## strategies

| Параметр | Default | Происхождение / смысл | Чтение в коде |
|---|---|---|---|
| `enabled` | `["continuation","wyckoff","sweep","breakout","supply_demand","market_profile","trendline","bollinger","orb","connors","pump","cup_handle","po3","oi_build"]` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | [briefing.py:765](../../briefing.py#L765), [briefing.py:871](../../briefing.py#L871), [executor.py:61](../../executor.py#L61) (+23) |
| `shadow_vetoes` | `["against_bias","against_trend","not_in_pool","h4_against","regime_flat","regime_trend","alts_vs_btc","profile","regime","no_confirmation","no_*","htf_bias","htf_conflict","rg_breakout_in_range","rg_countertrend","killzone","no_htf_poi","premium","discount","perp_led","low_rvol","against_vwap","btc_against","against_htf","against_day"]` | Большинство контекстных отказов только тегируются. Inline callers иногда игнорируют hard-return; см. COMMON. | [signal_book.py:144](../../signal_book.py#L144), [signal_book.py:958](../../signal_book.py#L958) |
| `disabled_setups` | `["BULL E","BULL A","PUMP TOP","PUMP START"]` | PUMP START/TOP отключены; BULL A/E — старые имена вне реестра Strategy. | [signal_book.py:368](../../signal_book.py#L368) |
| `holy_grail_adx` | `30.0` | Наследие удалённых playbook; нет чтения текущими Strategy. | нет прямого AST-чтения |
| `archive_negative` | `["BULL A","BULL B","BEAR C","BULL E","BULL F","BEAR D","IMPULSE UP"]` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | [webui.py:338](../../webui.py#L338) |
| `h1_candles` | `200` | 200 часов: хватает некоторым 4h моделям минимально, не обеспечивает длинные контекстные окна. | [fetcher.py:1353](../../fetcher.py#L1353) |
| `h1_refresh_sec` | `3600` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | [fetcher.py:1329](../../fetcher.py#L1329) |
| `close_event_max_age_sec` | `900` | Допустимый возраст события — операционная политика; historical close не гарантирует fill. | [strategies/structure.py:324](../../strategies/structure.py#L324) |
| `tide_btc_against` | `0.005` | Собственная формализация trend/tide, не полная механическая спецификация Elder/ICT. | [strategies/leg.py:89](../../strategies/leg.py#L89) |
| `trend_ema` | `20` | Собственная формализация trend/tide, не полная механическая спецификация Elder/ICT. | [research/scripts/research_entries_placebo_eng133.py:69](../../research/scripts/research_entries_placebo_eng133.py#L69), [strategies/structure.py:54](../../strategies/structure.py#L54), [strategies/structure.py:56](../../strategies/structure.py#L56) |
| `trend_slope_bars` | `4` | Собственная формализация trend/tide, не полная механическая спецификация Elder/ICT. | [research/scripts/research_entries_placebo_eng133.py:69](../../research/scripts/research_entries_placebo_eng133.py#L69), [strategies/structure.py:54](../../strategies/structure.py#L54), [strategies/structure.py:60](../../strategies/structure.py#L60) |
| `trend_w_ema` | `20` | Собственная формализация trend/tide, не полная механическая спецификация Elder/ICT. | [fetcher.py:1638](../../fetcher.py#L1638), [strategies/structure.py:74](../../strategies/structure.py#L74) |
| `recent_atr_candles` | `14` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | [strategies/structure.py:46](../../strategies/structure.py#L46) |
| `sweep_swing_hours` | `100000` | 100000 фактически снимает короткое ограничение истории; реальная история всё равно конечна. | [strategies/structure.py:126](../../strategies/structure.py#L126) |
| `sweep_pool_min_age_sec` | `0` | 0: возраст pool дополнительно не ограничивается. | [strategies/level.py:72](../../strategies/level.py#L72) |
| `sweep_round_pools` | `false` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | [strategies/level.py:74](../../strategies/level.py#L74) |
| `cup_target_share` | `0.61` | 0.61 подтверждено текущим measure rule Bulkowski (K1); не выход O’Neil. | [strategies/cup_handle.py:79](../../strategies/cup_handle.py#L79), [strategies/cup_handle.py:107](../../strategies/cup_handle.py#L107) |
| `sweep_min_depth_atr` | `0.1` | Собственная глубина; при действующей pierce-модели fallback заменяется эмпирическим overshoot. | [strategies/level.py:69](../../strategies/level.py#L69) |
| `sweep_max_depth_atr` | `1.0` | Собственный предел; при pierce-модели используется её p90 вместо постоянной 1ATR. | [strategies/level.py:69](../../strategies/level.py#L69) |
| `sweep_min_rvol` | `0.0` | 0: обязательный повышенный RVOL отсутствует. | [pretrain.py:348](../../pretrain.py#L348), [research/scripts/research_cards.py:138](../../research/scripts/research_cards.py#L138), [strategies/level.py:67](../../strategies/level.py#L67) |
| `sweep_sessions` | `[["Asia","Asia/Tokyo",9,18],["London","Europe/London",8,17],["New York","America/New_York",8,17]]` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | [zones.py:229](../../zones.py#L229) |
| `sweep_ttl` | `[7200,7200,28800]` | Собственный срок; обычный TTL подавлен structural_lifetimes=True, кроме собственных session/exit веток. | нет прямого AST-чтения; используется ttl_key |
| `absorption_min_rvol` | `3.0` | Числовая квантификация absorption/flow проекта; наличие параметра не делает его обязательным фильтром всех Strategy. | [strategies/level.py:195](../../strategies/level.py#L195) |
| `absorption_level_atr` | `0.3` | Числовая квантификация absorption/flow проекта; наличие параметра не делает его обязательным фильтром всех Strategy. | [strategies/level.py:199](../../strategies/level.py#L199) |
| `absorption_min_strength` | `2.0` | Числовая квантификация absorption/flow проекта; наличие параметра не делает его обязательным фильтром всех Strategy. | нет прямого AST-чтения |
| `absorption_min_move_atr` | `1.5` | Числовая квантификация absorption/flow проекта; наличие параметра не делает его обязательным фильтром всех Strategy. | [strategies/level.py:205](../../strategies/level.py#L205) |
| `exhaustion_pre_minutes` | `30` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | [strategies/cascade.py:86](../../strategies/cascade.py#L86) |
| `exhaustion_min_leg_atr` | `0.0` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | [strategies/cascade.py:99](../../strategies/cascade.py#L99) |
| `exhaustion_ttl` | `[3600,3600,21600]` | Собственный срок; обычный TTL подавлен structural_lifetimes=True, кроме собственных session/exit веток. | [strategies/cascade.py:68](../../strategies/cascade.py#L68) |
| `breakout_range_candles` | `8` | Наследие прежнего intraday range breakout; текущие Turtle/BB1 используют собственные условия. | [strategies/breakout.py:23](../../strategies/breakout.py#L23) |
| `breakout_min_width_atr` | `0.8` | Наследие прежнего intraday range breakout; текущие Turtle/BB1 используют собственные условия. | [strategies/breakout.py:34](../../strategies/breakout.py#L34) |
| `breakout_max_width_atr` | `3.0` | Наследие прежнего intraday range breakout; текущие Turtle/BB1 используют собственные условия. | [strategies/breakout.py:34](../../strategies/breakout.py#L34) |
| `breakout_min_rvol` | `1.5` | Наследие прежнего intraday range breakout; текущие Turtle/BB1 используют собственные условия. | [strategies/breakout.py:44](../../strategies/breakout.py#L44) |
| `breakout_ttl` | `[3600,3600,7776000]` | Собственный срок; обычный TTL подавлен structural_lifetimes=True, кроме собственных session/exit веток. | нет прямого AST-чтения; используется ttl_key |
| `long_history_candles` | `499` | 499 — запрошенная глубина; не доказывает полноту session/calendar и daily Cup history. | [fetcher.py:1344](../../fetcher.py#L1344), [fetcher.py:1347](../../fetcher.py#L1347), [research/scripts/research_maniac.py:38](../../research/scripts/research_maniac.py#L38) |
| `sd_ttl` | `[604800,86400,259200]` | Собственный срок; обычный TTL подавлен structural_lifetimes=True, кроме собственных session/exit веток. | нет прямого AST-чтения; используется ttl_key |
| `classic_ttl` | `[3600,3600,43200]` | Собственный срок; обычный TTL подавлен structural_lifetimes=True, кроме собственных session/exit веток. | нет прямого AST-чтения; используется ttl_key |
| `silver_bullet_ttl` | `[3600,3600,14400]` | Собственный срок; обычный TTL подавлен structural_lifetimes=True, кроме собственных session/exit веток. | нет прямого AST-чтения; используется ttl_key |
| `po3_ttl` | `[10800,10800,43200]` | Собственный срок; обычный TTL подавлен structural_lifetimes=True, кроме собственных session/exit веток. | нет прямого AST-чтения; используется ttl_key |
| `pump_start_min_pct` | `0.03` | Авторский pump-порог; PUMP START/TOP сейчас disabled. Доказательства классической универсальности нет. | [strategies/loopside.py:72](../../strategies/loopside.py#L72), [strategies/pump.py:44](../../strategies/pump.py#L44) |
| `pump_start_z` | `4.0` | Авторский pump-порог; PUMP START/TOP сейчас disabled. Доказательства классической универсальности нет. | [strategies/pump.py:44](../../strategies/pump.py#L44) |
| `pump_start_rvol` | `5.0` | Авторский pump-порог; PUMP START/TOP сейчас disabled. Доказательства классической универсальности нет. | [strategies/pump.py:46](../../strategies/pump.py#L46) |
| `pump_top_min_pct` | `0.1` | Авторский pump-порог; PUMP START/TOP сейчас disabled. Доказательства классической универсальности нет. | [strategies/loopside.py:82](../../strategies/loopside.py#L82), [strategies/pump.py:77](../../strategies/pump.py#L77) |
| `pump_ttl` | `[3600,3600,43200]` | Собственный срок; обычный TTL подавлен structural_lifetimes=True, кроме собственных session/exit веток. | нет прямого AST-чтения; используется ttl_key |
| `cup_ttl` | `[86400,86400,5184000]` | Собственный срок; обычный TTL подавлен structural_lifetimes=True, кроме собственных session/exit веток. | нет прямого AST-чтения; используется ttl_key |
| `connors_ttl` | `[3600,3600,5184000]` | Собственный срок; обычный TTL подавлен structural_lifetimes=True, кроме собственных session/exit веток. | нет прямого AST-чтения; используется ttl_key |
| `structural_lifetimes` | `true` | Снимает обычные произвольные watch/zone/trade TTL. Session rules остаются только там, где переданы. | [signal_book.py:883](../../signal_book.py#L883), [signal_book.py:889](../../signal_book.py#L889), [signal_book.py:910](../../signal_book.py#L910) (+4) |
| `be_after_1r` | `false` | False: общий break-even после 1R отключён. | [signal_book.py:552](../../signal_book.py#L552) |
| `ema_trail_after_tp1` | `false` | False снимает trail_after_tp1 у большинства планов; исключение band_exit. Docstrings OTE устарели. | [signal_book.py:554](../../signal_book.py#L554), [signal_book.py:556](../../signal_book.py#L556) |
| `time_stop_bars` | `24` | Авторская политика времени/достижимости целей; действие зависит от structural_lifetimes и собственного выхода модели. | [signal_book.py:1506](../../signal_book.py#L1506), [signal_book.py:1508](../../signal_book.py#L1508), [strategies/geometry.py:225](../../strategies/geometry.py#L225) |
| `crowd_max` | `6` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | [executor.py:573](../../executor.py#L573), [signal_book.py:1469](../../signal_book.py#L1469) |
| `optimized_profiles` | `false` | False: текущая общая подмена настроек оптимизированными профилями отключена. | [signal_book.py:1145](../../signal_book.py#L1145), [signal_book.py:1149](../../signal_book.py#L1149), [signal_book.py:1206](../../signal_book.py#L1206) |
| `time_after_tp1` | `3.0` | Авторская политика времени/достижимости целей; действие зависит от structural_lifetimes и собственного выхода модели. | [signal_book.py:1509](../../signal_book.py#L1509), [strategies/geometry.py:225](../../strategies/geometry.py#L225) |
| `time_stop_min_sec` | `14400` | Авторская политика времени/достижимости целей; действие зависит от structural_lifetimes и собственного выхода модели. | [signal_book.py:1506](../../signal_book.py#L1506) |
| `turtle_add_n` | `0.5` | 0.5N подтверждено T1; проверять от предыдущего фактического fill. | [signal_book.py:1389](../../signal_book.py#L1389) |
| `turtle_max_units` | `4` | 4 units на рынок подтверждено T1. | [executor.py:438](../../executor.py#L438), [executor.py:440](../../executor.py#L440), [signal_book.py:1388](../../signal_book.py#L1388) |
| `turtle_max_direction_units` | `6` | 6 — исходный cap тесно коррелированных рынков, не полный направленный cap 12; все coins объединены по допущению. | [signal_book.py:1216](../../signal_book.py#L1216), [signal_book.py:1392](../../signal_book.py#L1392) |
| `turtle_unit_risk` | `0.01` | Число 1% на N соответствует T1, но параметр НЕ читается. В executor другое основание риска: 1% на весь стоп. | нет прямого AST-чтения |
| `orb_stretch_days` | `10` | 10 дней подтверждено Crabel O1. UTC daily для трёх разных сессий — адаптация. | [strategies/classic.py:139](../../strategies/classic.py#L139), [strategies/classic.py:325](../../strategies/classic.py#L325) |
| `orb_bases` | `["BTC","ETH","SOL","BNB","XRP","XAU","XAG","CL","BZ"]` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | [strategies/classic.py:429](../../strategies/classic.py#L429), [strategies/loopside.py:182](../../strategies/loopside.py#L182) |
| `connors_rsi_low` | `5.0` | 5 встречается в изложениях RSI2 (C3); у автора есть другие пороги (C1). Live использует выход из экстремума. | [strategies/classic.py:400](../../strategies/classic.py#L400), [strategies/classic.py:406](../../strategies/classic.py#L406), [strategies/classic.py:417](../../strategies/classic.py#L417) |
| `connors_rsi_high` | `95.0` | 95 — зеркальный вариант (C3), не единственный порог автора и не доказательство crypto short. | [strategies/classic.py:402](../../strategies/classic.py#L402), [strategies/classic.py:408](../../strategies/classic.py#L408), [strategies/classic.py:417](../../strategies/classic.py#L417) |
| `dump_min_move` | `0.15` | Авторский inverse drop base/current−1, не обычный %-decline. 15% означает −13.0435% (S09). | [strategies/pump.py:123](../../strategies/pump.py#L123) |
| `dump_vol_x` | `3.0` | Авторский порог research P1, внешней универсальной константой не является. | [strategies/pump.py:127](../../strategies/pump.py#L127) |
| `wide_min_volume` | `3000000` | Числовой/операционный выбор проекта. Подтверждения как обязательной константы первоисточника не найдено; роль раскрыта в соответствующем dossier/COMMON. | [scanner.py:867](../../scanner.py#L867) |
| `oi_build_ttl` | `[900,900,14400]` | Собственный срок; обычный TTL подавлен structural_lifetimes=True, кроме собственных session/exit веток. | нет прямого AST-чтения; используется ttl_key |
| `require_displacement` | `true` | Переключатель собственной геометрической FVG-проверки; её нельзя приравнять к любой авторской трактовке displacement. | [strategies/leg.py:105](../../strategies/leg.py#L105) |
| `smt_main_bars` | `500` | Наследие SMT/iFVG helpers; отдельной зарегистрированной SMT Strategy сейчас нет. Не считать самостоятельным live playbook. | нет прямого AST-чтения |
| `smt_with_trend_only` | `false` | Наследие SMT/iFVG helpers; отдельной зарегистрированной SMT Strategy сейчас нет. Не считать самостоятельным live playbook. | нет прямого AST-чтения |
| `smt_ref_window` | `60` | Наследие SMT/iFVG helpers; отдельной зарегистрированной SMT Strategy сейчас нет. Не считать самостоятельным live playbook. | нет прямого AST-чтения |
| `smt_ifvg_min_atr` | `0.03` | Наследие SMT/iFVG helpers; отдельной зарегистрированной SMT Strategy сейчас нет. Не считать самостоятельным live playbook. | [strategies/maniac.py:574](../../strategies/maniac.py#L574) |
| `smt_ifvg_search_back` | `40` | Наследие SMT/iFVG helpers; отдельной зарегистрированной SMT Strategy сейчас нет. Не считать самостоятельным live playbook. | [strategies/maniac.py:576](../../strategies/maniac.py#L576) |
| `smt_session` | `["America/New_York","02:00","05:00","07:00","10:00"]` | Наследие SMT/iFVG helpers; отдельной зарегистрированной SMT Strategy сейчас нет. Не считать самостоятельным live playbook. | [executor.py:527](../../executor.py#L527), [signal_book.py:74](../../signal_book.py#L74), [signal_book.py:956](../../signal_book.py#L956) (+4) |
| `smt_min_correlation` | `0.7` | Наследие SMT/iFVG helpers; отдельной зарегистрированной SMT Strategy сейчас нет. Не считать самостоятельным live playbook. | [strategies/structure.py:379](../../strategies/structure.py#L379) |
| `tl_lookback` | `400` | Окно поиска текущего E&M-proxy; собственное 400h ограничение, не правило книги. | [strategies/maniac.py:316](../../strategies/maniac.py#L316) |
| `tl_pivot` | `3` | Наследие прежнего trendline detector: текущий E&M путь читает tl_lookback/tl_min_span; этот порог им не управляет. | нет прямого AST-чтения |
| `tl_min_span` | `40` | Собственная минимальная длина линии 40h, не классическая обязательная константа. | [strategies/maniac.py:318](../../strategies/maniac.py#L318) |
| `tl_min_touches` | `3` | Наследие прежнего trendline detector: текущий E&M путь читает tl_lookback/tl_min_span; этот порог им не управляет. | нет прямого AST-чтения |
| `tl_touch_atr` | `0.25` | Наследие прежнего trendline detector: текущий E&M путь читает tl_lookback/tl_min_span; этот порог им не управляет. | нет прямого AST-чтения |
| `tl_touch_gap` | `5` | Наследие прежнего trendline detector: текущий E&M путь читает tl_lookback/tl_min_span; этот порог им не управляет. | нет прямого AST-чтения |
| `tl_violation_atr` | `0.1` | Наследие прежнего trendline detector: текущий E&M путь читает tl_lookback/tl_min_span; этот порог им не управляет. | нет прямого AST-чтения |
| `tl_max_dist_atr` | `3.0` | Наследие прежнего trendline detector: текущий E&M путь читает tl_lookback/tl_min_span; этот порог им не управляет. | нет прямого AST-чтения |
| `tl_flat_deg` | `0.0` | Наследие прежнего trendline detector: текущий E&M путь читает tl_lookback/tl_min_span; этот порог им не управляет. | нет прямого AST-чтения |
| `tl_min_pivot_touches` | `3` | Наследие прежнего trendline detector: текущий E&M путь читает tl_lookback/tl_min_span; этот порог им не управляет. | нет прямого AST-чтения |
| `tl_pivot_tol_atr` | `0.2` | Наследие прежнего trendline detector: текущий E&M путь читает tl_lookback/tl_min_span; этот порог им не управляет. | нет прямого AST-чтения |
| `tl_max_deg` | `35.0` | Наследие прежнего trendline detector: текущий E&M путь читает tl_lookback/tl_min_span; этот порог им не управляет. | нет прямого AST-чтения |
| `tl_last_touch_age` | `40` | Наследие прежнего trendline detector: текущий E&M путь читает tl_lookback/tl_min_span; этот порог им не управляет. | нет прямого AST-чтения |
| `tl_confirm_atr` | `0.15` | Наследие прежнего trendline detector: текущий E&M путь читает tl_lookback/tl_min_span; этот порог им не управляет. | нет прямого AST-чтения |
| `tl_min_body_atr` | `0.35` | Наследие прежнего trendline detector: текущий E&M путь читает tl_lookback/tl_min_span; этот порог им не управляет. | нет прямого AST-чтения |
| `tl_max_depth_atr` | `1.2` | Наследие прежнего trendline detector: текущий E&M путь читает tl_lookback/tl_min_span; этот порог им не управляет. | нет прямого AST-чтения |
| `tl_close_pos_max` | `0.4` | Наследие прежнего trendline detector: текущий E&M путь читает tl_lookback/tl_min_span; этот порог им не управляет. | нет прямого AST-чтения |
| `trendline_ttl` | `[86400,86400,172800]` | Собственный срок; обычный TTL подавлен structural_lifetimes=True, кроме собственных session/exit веток. | нет прямого AST-чтения; используется ttl_key |
| `bollinger_ttl` | `[14400,14400,259200]` | Собственный срок; обычный TTL подавлен structural_lifetimes=True, кроме собственных session/exit веток. | нет прямого AST-чтения; используется ttl_key |

## orderflow

| Параметр | Default | Происхождение / смысл | Чтение в коде |
|---|---|---|---|
| `perp_led_spot_share` | `0.25` | Собственный порог микроструктуры/данных. Проверять источник, единицы и hard/shadow путь; не классическая константа. | [journal.py:418](../../journal.py#L418), [scorer.py:116](../../scorer.py#L116) |
| `veto_perp_led` | `true` | Собственный порог микроструктуры/данных. Проверять источник, единицы и hard/shadow путь; не классическая константа. | [journal.py:409](../../journal.py#L409) |
| `crowded_funding_long` | `0.0003` | Собственный порог микроструктуры/данных. Проверять источник, единицы и hard/shadow путь; не классическая константа. | [journal.py:320](../../journal.py#L320), [scorer.py:262](../../scorer.py#L262) |
| `crowded_funding_short` | `-0.0001` | Собственный порог микроструктуры/данных. Проверять источник, единицы и hard/shadow путь; не классическая константа. | [journal.py:323](../../journal.py#L323) |
| `crowded_cb_discount` | `0.0005` | Собственный порог микроструктуры/данных. Проверять источник, единицы и hard/shadow путь; не классическая константа. | [journal.py:322](../../journal.py#L322) |
| `crowded_premium_long` | `0.0006` | Собственный порог микроструктуры/данных. Проверять источник, единицы и hard/shadow путь; не классическая константа. | [journal.py:321](../../journal.py#L321) |
| `crowded_premium_short` | `0.0004` | Собственный порог микроструктуры/данных. Проверять источник, единицы и hard/shadow путь; не классическая константа. | [journal.py:324](../../journal.py#L324) |
| `crowded_oi_1h` | `0.005` | Собственный порог микроструктуры/данных. Проверять источник, единицы и hard/shadow путь; не классическая константа. | [journal.py:313](../../journal.py#L313) |
| `footprint_bucket_pct` | `0.0005` | Собственный порог микроструктуры/данных. Проверять источник, единицы и hard/shadow путь; не классическая константа. | [fetcher.py:2161](../../fetcher.py#L2161) |
| `imbalance_ratio` | `3.0` | Собственный порог микроструктуры/данных. Проверять источник, единицы и hard/shadow путь; не классическая константа. | [flow.py:673](../../flow.py#L673) |
| `stacked_levels` | `3` | Собственный порог микроструктуры/данных. Проверять источник, единицы и hard/shadow путь; не классическая константа. | [fetcher.py:2171](../../fetcher.py#L2171), [research/scripts/research_book_flow.py:178](../../research/scripts/research_book_flow.py#L178) |
| `absorption_percentile` | `0.9` | Числовая квантификация absorption/flow проекта; наличие параметра не делает его обязательным фильтром всех Strategy. | [flow.py:662](../../flow.py#L662), [strategies/level.py:193](../../strategies/level.py#L193) |
| `absorption_max_move_atr` | `0.2` | Числовая квантификация absorption/flow проекта; наличие параметра не делает его обязательным фильтром всех Strategy. | [flow.py:667](../../flow.py#L667), [strategies/level.py:195](../../strategies/level.py#L195) |
| `require_orderflow_confirm` | `false` | False: обязательное flow-подтверждение отключено на уровне этого переключателя. | [strategies/confirm.py:57](../../strategies/confirm.py#L57) |
| `divergence_lookback_min` | `60` | Собственный порог микроструктуры/данных. Проверять источник, единицы и hard/shadow путь; не классическая константа. | [strategies/confirm.py:101](../../strategies/confirm.py#L101) |
| `required_confirmations` | `[]` | Пусто по умолчанию; PROMOTED может расширять. Отсутствия далее могут стать shadow. | [strategies/confirm.py:56](../../strategies/confirm.py#L56) |
| `confirm_exempt` | `["breakout"]` | breakout общее для Turtle и BB1; это техническая группировка двух различных моделей. | [strategies/confirm.py:71](../../strategies/confirm.py#L71) |
| `promote_confirmations` | `true` | Калибровочная политика проекта; не авторский источник. Финальный veto зависит от shadow-пути. | [journal.py:934](../../journal.py#L934) |
| `promote_min_clusters` | `30` | Собственный порог микроструктуры/данных. Проверять источник, единицы и hard/shadow путь; не классическая константа. | [journal.py:950](../../journal.py#L950) |
| `min_confirmations` | `0` | 0: минимальное количество default подтверждений не требуется. | [strategies/confirm.py:74](../../strategies/confirm.py#L74) |

## executor

| Параметр | Default | Происхождение / смысл | Чтение в коде |
|---|---|---|---|
| `touch_confirm_close` | `true` | True: касание + закрытие, затем текущая цена; это меняет resting-limit спецификацию. | [executor.py:520](../../executor.py#L520), [journal.py:609](../../journal.py#L609), [signal_book.py:1007](../../signal_book.py#L1007) |
| `partial_r` | `1.0` | Технический порог общего partial; при partial_share=0 не даёт частичного выхода. | [executor.py:313](../../executor.py#L313), [signal_book.py:675](../../signal_book.py#L675), [signal_book.py:677](../../signal_book.py#L677) (+2) |
| `partial_share` | `0.0` | 0: дополнительного общего partial нет; собственный half W/M сохраняется. | [executor.py:311](../../executor.py#L311), [executor.py:317](../../executor.py#L317), [signal_book.py:675](../../signal_book.py#L675) (+2) |
| `risk_pct` | `1.0` | 1% account на полный стоп, а не исходный Turtle 1% на N. Политика executor. | [executor.py:414](../../executor.py#L414), [executor.py:441](../../executor.py#L441), [executor.py:597](../../executor.py#L597) (+1) |

## Существенные числа вне CONFIG

Проверка только CONFIG пропустила бы основные правила detector. Следующие значения прочитаны непосредственно в исходниках; не все они вынесены в настройки.

| Метод | Числа/условия в коде | Основание и ограничение |
|---|---|---|
| OTE | 2/2 pivots, 5/20 часов для TF, 3-bar FVG | Квантификация проекта; оригинальный ICT целиком не получен |
| Sweep / SB / PO3 | 3-candle swing, 3-bar FVG, CE 50%, NY windows, покрытие sessions | Алгоритм проекта; геометрия gap верна, обязательность всего набора не доказана |
| Cascade | 30 минут до события, 25-й 1h close, Fib зоны | Гипотеза проекта по мотивам climax, не Wyckoff mechanical rule |
| Wyckoff | 2/2 pivot, box = range/10, reversal 3, multiplier 3 | P&F имеет классическую основу; box/count line и proxy фаз авторские |
| Turtle | 20/55 entry, 10/20 exit, N20, 2N | Подтверждено T1; цена отсчёта/исторический фильтр расходятся |
| Seiden | body 50%, ≥10 баз, терцили силы, медиана времени, curve 20 дней/половина, score≥8 | Числовая модель проекта; D1–D3 не подтверждают именно её |
| Auction / VA80 | 70% VA, 60 buckets, ≥80% покрытия, пары 15m, два close | TPO имеет первоисточник M0, но вес/период неверны; точные acceptance rules не доказаны |
| E&M trendline | 2/2 pivots, два close, 3%, volume mean20, stop pivot3/3 | E1 подтверждает идею decisive close и асимметрию объёма, не весь автомат |
| BB W/M / BB3 | SMA20/2σ, II21, alert5, strong body50%/outer third/median20 | Формулы полос и идея объёмного подтверждения имеют источник; точные триггеры смешаны с нашими |
| BB1 | 125×4h Squeeze, SAR0 extreme20, AF .02/.20 | 125×4h не исходные шесть месяцев; SAR clamp ошибочен |
| Connors | SMA200/SMA5, RSI2 history60, ATR20 | RSI/SMA корректны; cross-back и crypto sizing собственные |
| Pump start/top | 15m/1m RVOL, high24h, OI/CVD5m; 4h move, half wick, volume2×20 | Авторские эвристики; выключены, OI у top не hard filter |
| Dump | 6h/7d/48h/24h, .382–.618, .25ATR, ext1.618 | Внутренний research; live sequence/exit не эквивалентны |
| Cup | 35–325, 12–33%, prior30% за 2L, handle5–56/12%, volume1.4×50, chase5%, stop8% | Часть подтверждается школой O’Neil; календарь/форма/история/финальный стоп расходятся |
| OI | ≥26 samples, 12 интервалов, 55–65min, stale10min | Собственный hourly predictor; точная формула Pring не найдена |

Общий вывод «все параметры взяты из классики, своих порогов нет» опровергается этими чтениями. Для подробных условий, контекста и выходов см. [все dossier](STRATEGIES.md), [общий путь](STRATEGY_COMMON.md) и [источники](STRATEGY_SOURCES.md).
