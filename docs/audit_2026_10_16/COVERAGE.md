# Покрытие проверки

База: `f386ec3b9e34131ff45b1e65721a7fe3f48542e2`. Все 293 исходных tracked-файла учтены, SHA256 совпадает с началом аудита. Торговый код не изменён. Базовые применимые проверки выполнены для каждого файла; глубина ручной проверки различается. Наличие строки в этом перечне **не означает**, что каждая строка файла прошла ручной семантический анализ.

- `manual`: ручной первый проход (включая все 28 файлов strategies), плюс применимые статические проверки.
- `targeted`: прицельная проверка опасных путей, контрактов и связей между модулями, плюс статика; не построчный аудит всего модуля.
- `structural`: полный синтаксический/статический проход и индекс функций/опасных выражений; нет заявления о полном ручном анализе логики.
- `documentary`: формат, версии, утверждения и выборочная сверка с текущим кодом/первоисточниками. Старые числовые исследования не пересчитаны.
- `test`: существующие тесты запущены в двух версиях Python.
- `artifact`: JSON/Parquet/NPZ разобраны; PKL разобраны без исполнения. Схемы/null/nonfinite — в file_checks.json. NaN исследовательских статистик при пустых подгруппах не объявлены повреждением данных.
- `vendor`: синтаксис и точное совпадение поставляемой библиотеки с опубликованной версией; внутренний алгоритм чужой библиотеки не аудировался.

Это завершённый набор локальных проверок, а не сертификация проекта. Не выполнены: live-сверка аккаунта/логов/VPS, исполнение ордеров, длительный replay всех исследований и проверка доходности. Для них здесь нет соответствующих данных; они не подменены выдуманным PASS. Неподтверждённые гипотезы перечислены отдельно в REPORT.md.

Категории: artifact=18, documentary=111, manual=52, structural=54, targeted=48, test=9, vendor=1.

| Файл | Глубина | Формат/статика |
|---|---|---|
| `.claude/agents/planner.md` | documentary | UTF-8 PASS |
| `.claude/agents/reviewer.md` | documentary | UTF-8 PASS |
| `.claude/settings.json` | artifact | JSON PASS |
| `.claude/skills/research-findings/SKILL.md` | documentary | UTF-8 PASS |
| `.gitattributes` | structural | UTF-8 PASS |
| `.github/workflows/ci.yml` | manual | UTF-8 PASS |
| `.gitignore` | structural | UTF-8 PASS |
| `AUDIT_PLAN.md` | documentary | UTF-8 PASS |
| `CLAUDE.md` | documentary | UTF-8 PASS |
| `CLOUD_RETRAIN.md` | documentary | UTF-8 PASS |
| `HANDOFF.md` | documentary | UTF-8 PASS |
| `PLAN_NEXT.md` | documentary | UTF-8 PASS |
| `briefing.py` | targeted | Python AST PASS |
| `briefing_chart.py` | targeted | Python AST PASS |
| `config.py` | targeted | Python AST PASS |
| `deploy/README.md` | documentary | UTF-8 PASS |
| `deploy/harden.sh` | targeted | UTF-8 PASS |
| `deploy/install.sh` | targeted | UTF-8 PASS |
| `deploy/mark_dup_untracked.py` | targeted | Python AST PASS |
| `deploy/precheck.sh` | manual | UTF-8 PASS |
| `deploy/pump-bot.service` | targeted | UTF-8 PASS |
| `deploy/pump-farside.service` | targeted | UTF-8 PASS |
| `deploy/pump-farside.timer` | targeted | UTF-8 PASS |
| `deploy/setup_server.sh` | targeted | UTF-8 PASS |
| `deploy/web_access.sh` | targeted | UTF-8 PASS |
| `depth.py` | targeted | Python AST PASS |
| `docs/ARCHITECTURE.md` | documentary | UTF-8 PASS |
| `docs/AUDIT_full.md` | documentary | UTF-8 PASS |
| `docs/AUDIT_parameters.md` | documentary | UTF-8 PASS |
| `docs/AUDIT_round2.md` | documentary | UTF-8 PASS |
| `docs/AUDIT_round3.md` | documentary | UTF-8 PASS |
| `docs/AUDIT_strategies.md` | documentary | UTF-8 PASS |
| `docs/CLOUD_OPTIMIZE.md` | documentary | UTF-8 PASS |
| `docs/CLOUD_RESEARCH.md` | documentary | UTF-8 PASS |
| `docs/CLOUD_RETRAIN.md` | documentary | UTF-8 PASS |
| `docs/CLOUD_TASKS.md` | documentary | UTF-8 PASS |
| `docs/CLOUD_eng133_placebo.md` | documentary | UTF-8 PASS |
| `docs/DATA_COVERAGE.md` | documentary | UTF-8 PASS |
| `docs/HANDOFF_2026-10-12_exits.md` | documentary | UTF-8 PASS |
| `docs/HANDOFF_eng75.md` | documentary | UTF-8 PASS |
| `docs/HISTORY.md` | documentary | UTF-8 PASS |
| `docs/PLAN_after_audit.md` | documentary | UTF-8 PASS |
| `docs/PLAN_fixes_2026-10-16.md` | documentary | UTF-8 PASS |
| `docs/PLAN_server_eng76.md` | documentary | UTF-8 PASS |
| `docs/STRATEGY_PRACTICE.md` | documentary | UTF-8 PASS |
| `errors.py` | manual | Python AST PASS |
| `event_risk.py` | targeted | Python AST PASS |
| `executor.py` | manual | Python AST PASS |
| `extdata.py` | manual | Python AST PASS |
| `fetcher.py` | targeted | Python AST PASS |
| `flow.py` | targeted | Python AST PASS |
| `history.py` | manual | Python AST PASS |
| `iceberg.py` | manual | Python AST PASS |
| `indicators.py` | manual | Python AST PASS |
| `journal.py` | targeted | Python AST PASS |
| `levels.py` | manual | Python AST PASS |
| `macro.py` | manual | Python AST PASS |
| `macro_calendar.py` | manual | Python AST PASS |
| `main.py` | targeted | Python AST PASS |
| `memreport.py` | targeted | Python AST PASS |
| `ml.py` | targeted | Python AST PASS |
| `ml_eval.py` | targeted | Python AST PASS |
| `models/exit_overlays.json` | artifact | JSON PASS |
| `models/htf_filters.json` | artifact | JSON PASS |
| `models/level_weights.json` | artifact | JSON PASS |
| `models/overshoot.json` | artifact | JSON PASS |
| `models/pretrained.eng-7.pkl` | artifact | Pickle opcode parse PASS, NOT executed |
| `models/profiles.json` | artifact | JSON PASS |
| `models/profiles_regime.json` | artifact | JSON PASS |
| `models/scenario_prob.pkl` | artifact | Pickle opcode parse PASS, NOT executed |
| `netstate.py` | manual | Python AST PASS |
| `notifier.py` | targeted | Python AST PASS |
| `pierce.py` | manual | Python AST PASS |
| `pools.py` | manual | Python AST PASS |
| `positioning.py` | manual | Python AST PASS |
| `pretrain.py` | targeted | Python AST PASS |
| `pumps.py` | manual | Python AST PASS |
| `ratelimit.py` | manual | Python AST PASS |
| `recorder.py` | targeted | Python AST PASS |
| `replay.py` | targeted | Python AST PASS |
| `requirements-dev.txt` | documentary | UTF-8 PASS |
| `requirements.txt` | documentary | UTF-8 PASS |
| `research/CLOUD_SUMMARY.md` | documentary | UTF-8 PASS |
| `research/PROTOCOL_entries_vs_placebo_eng133.md` | documentary | UTF-8 PASS |
| `research/adaptive_params.md` | documentary | UTF-8 PASS |
| `research/algo_whales.md` | documentary | UTF-8 PASS |
| `research/atr_volbars.md` | documentary | UTF-8 PASS |
| `research/bb1_windows.md` | documentary | UTF-8 PASS |
| `research/bias.md` | documentary | UTF-8 PASS |
| `research/bias_eng72.md` | documentary | UTF-8 PASS |
| `research/book_flow_archive.md` | documentary | UTF-8 PASS |
| `research/cards_12m.md` | documentary | UTF-8 PASS |
| `research/cards_6m.md` | documentary | UTF-8 PASS |
| `research/cards_fixed_12m.md` | documentary | UTF-8 PASS |
| `research/cards_holdout.md` | documentary | UTF-8 PASS |
| `research/channels.md` | documentary | UTF-8 PASS |
| `research/compass_check.md` | documentary | UTF-8 PASS |
| `research/confluence.md` | documentary | UTF-8 PASS |
| `research/connors_crypto.md` | documentary | UTF-8 PASS |
| `research/daily_methods.md` | documentary | UTF-8 PASS |
| `research/demo_gap.md` | documentary | UTF-8 PASS |
| `research/edges_12m.md` | documentary | UTF-8 PASS |
| `research/edges_6m.md` | documentary | UTF-8 PASS |
| `research/eng72_vs_eng59.md` | documentary | UTF-8 PASS |
| `research/ensemble_trend.md` | documentary | UTF-8 PASS |
| `research/entry_edge.md` | documentary | UTF-8 PASS |
| `research/entry_edge_eng72.md` | documentary | UTF-8 PASS |
| `research/eqh.md` | documentary | UTF-8 PASS |
| `research/etf_flows_2026-10-15.json` | artifact | JSON PASS |
| `research/exit_bt/audit.py` | structural | Python AST PASS |
| `research/exit_bt/audit_ict.py` | structural | Python AST PASS |
| `research/exit_bt/bt.py` | structural | Python AST PASS |
| `research/exit_bt/charts.py` | structural | Python AST PASS |
| `research/exit_bt/demo_be.py` | structural | Python AST PASS |
| `research/exit_bt/fetch.py` | structural | Python AST PASS |
| `research/exit_bt/fetch5.py` | structural | Python AST PASS |
| `research/exit_bt/majors.py` | structural | Python AST PASS |
| `research/exit_bt/report.md` | documentary | UTF-8 PASS |
| `research/exit_bt/report_audit_bb.md` | documentary | UTF-8 PASS |
| `research/exit_bt/report_audit_bb_va_rsi2_wyckoff_c0.002.md` | documentary | UTF-8 PASS |
| `research/exit_bt/report_audit_bb_va_rsi2_wyckoff_c0.md` | documentary | UTF-8 PASS |
| `research/exit_bt/report_audit_ict.md` | documentary | UTF-8 PASS |
| `research/exit_bt/report_audit_rsi2.md` | documentary | UTF-8 PASS |
| `research/exit_bt/report_audit_va.md` | documentary | UTF-8 PASS |
| `research/exit_bt/report_audit_wyckoff.md` | documentary | UTF-8 PASS |
| `research/exit_bt/report_demo_be.md` | documentary | UTF-8 PASS |
| `research/exit_bt/report_majors.md` | documentary | UTF-8 PASS |
| `research/exit_bt/report_sessions.md` | documentary | UTF-8 PASS |
| `research/exit_bt/report_tf.md` | documentary | UTF-8 PASS |
| `research/exit_bt/report_wide.md` | documentary | UTF-8 PASS |
| `research/exit_bt/sessions.py` | structural | Python AST PASS |
| `research/exit_bt/tf.py` | structural | Python AST PASS |
| `research/exit_bt/wide.py` | structural | Python AST PASS |
| `research/exits_12m.md` | documentary | UTF-8 PASS |
| `research/exits_all_12m.md` | documentary | UTF-8 PASS |
| `research/funding_holdout.md` | documentary | UTF-8 PASS |
| `research/geometry_audit.md` | documentary | UTF-8 PASS |
| `research/geometry_audit_eng72.md` | documentary | UTF-8 PASS |
| `research/htf_filter.md` | documentary | UTF-8 PASS |
| `research/htf_phases.md` | documentary | UTF-8 PASS |
| `research/indicator_confirms.md` | documentary | UTF-8 PASS |
| `research/indicator_confirms.parquet` | artifact | Parquet full decode PASS |
| `research/level_factors.md` | documentary | UTF-8 PASS |
| `research/level_mechanics.md` | documentary | UTF-8 PASS |
| `research/level_triggers.md` | documentary | UTF-8 PASS |
| `research/level_weights.md` | documentary | UTF-8 PASS |
| `research/maker_12m.md` | documentary | UTF-8 PASS |
| `research/meta_12m.md` | documentary | UTF-8 PASS |
| `research/meta_replay.md` | documentary | UTF-8 PASS |
| `research/ml_eval_12m.txt` | documentary | UTF-8 PASS |
| `research/ml_eval_6m.txt` | documentary | UTF-8 PASS |
| `research/optimize.md` | documentary | UTF-8 PASS |
| `research/optimize.parquet` | artifact | Parquet full decode PASS |
| `research/optimize_matrix.npz` | artifact | NPZ PASS (allow_pickle=False) |
| `research/optimize_regime.md` | documentary | UTF-8 PASS |
| `research/optimize_robust.md` | documentary | UTF-8 PASS |
| `research/optimize_robust_picks.json` | artifact | JSON PASS |
| `research/ours_placebo_6m.md` | documentary | UTF-8 PASS |
| `research/overlays.md` | documentary | UTF-8 PASS |
| `research/overshoot.md` | documentary | UTF-8 PASS |
| `research/phases_6m.md` | documentary | UTF-8 PASS |
| `research/pools.md` | documentary | UTF-8 PASS |
| `research/positioning.md` | documentary | UTF-8 PASS |
| `research/profile_trades.md` | documentary | UTF-8 PASS |
| `research/pumps.md` | documentary | UTF-8 PASS |
| `research/pumps_by_size.md` | documentary | UTF-8 PASS |
| `research/pumps_holdout.md` | documentary | UTF-8 PASS |
| `research/regimes_hmm.md` | documentary | UTF-8 PASS |
| `research/replay.md` | documentary | UTF-8 PASS |
| `research/replay_eng72.md` | documentary | UTF-8 PASS |
| `research/replay_missing.md` | documentary | UTF-8 PASS |
| `research/replay_summary.parquet` | artifact | Parquet full decode PASS |
| `research/replay_summary_eng59.parquet` | artifact | Parquet full decode PASS |
| `research/replay_summary_eng72.parquet` | artifact | Parquet full decode PASS |
| `research/scenario_model.md` | documentary | UTF-8 PASS |
| `research/scripts/research_adaptive.py` | structural | Python AST PASS |
| `research/scripts/research_algo_whales.py` | structural | Python AST PASS |
| `research/scripts/research_atr_volbars.py` | structural | Python AST PASS |
| `research/scripts/research_bb1_windows.py` | structural | Python AST PASS |
| `research/scripts/research_bias.py` | structural | Python AST PASS |
| `research/scripts/research_book_flow.py` | structural | Python AST PASS |
| `research/scripts/research_cards.py` | structural | Python AST PASS |
| `research/scripts/research_channels.py` | structural | Python AST PASS |
| `research/scripts/research_compass.py` | structural | Python AST PASS |
| `research/scripts/research_confluence.py` | structural | Python AST PASS |
| `research/scripts/research_connors.py` | structural | Python AST PASS |
| `research/scripts/research_daily_methods.py` | structural | Python AST PASS |
| `research/scripts/research_edges.py` | structural | Python AST PASS |
| `research/scripts/research_eng72_vs_eng59.py` | structural | Python AST PASS |
| `research/scripts/research_ensemble.py` | structural | Python AST PASS |
| `research/scripts/research_entries_placebo_eng133.py` | targeted | Python AST PASS |
| `research/scripts/research_entry_edge.py` | structural | Python AST PASS |
| `research/scripts/research_eqh.py` | structural | Python AST PASS |
| `research/scripts/research_exits.py` | structural | Python AST PASS |
| `research/scripts/research_fetch5m.py` | structural | Python AST PASS |
| `research/scripts/research_funding.py` | structural | Python AST PASS |
| `research/scripts/research_geometry_audit.py` | structural | Python AST PASS |
| `research/scripts/research_htf.py` | targeted | Python AST PASS |
| `research/scripts/research_htf_filter.py` | structural | Python AST PASS |
| `research/scripts/research_indicator_confirms.py` | targeted | Python AST PASS |
| `research/scripts/research_level_events.py` | structural | Python AST PASS |
| `research/scripts/research_level_factors.py` | structural | Python AST PASS |
| `research/scripts/research_level_mechanics.py` | targeted | Python AST PASS |
| `research/scripts/research_level_triggers.py` | structural | Python AST PASS |
| `research/scripts/research_level_weights.py` | structural | Python AST PASS |
| `research/scripts/research_maniac.py` | structural | Python AST PASS |
| `research/scripts/research_meta.py` | structural | Python AST PASS |
| `research/scripts/research_meta_replay.py` | targeted | Python AST PASS |
| `research/scripts/research_optimize.py` | targeted | Python AST PASS |
| `research/scripts/research_optimize_regime.py` | structural | Python AST PASS |
| `research/scripts/research_optimize_robust.py` | targeted | Python AST PASS |
| `research/scripts/research_overlays.py` | structural | Python AST PASS |
| `research/scripts/research_overshoot.py` | structural | Python AST PASS |
| `research/scripts/research_pools.py` | structural | Python AST PASS |
| `research/scripts/research_positioning.py` | structural | Python AST PASS |
| `research/scripts/research_profile_trades.py` | structural | Python AST PASS |
| `research/scripts/research_pumps.py` | structural | Python AST PASS |
| `research/scripts/research_regimes_hmm.py` | structural | Python AST PASS |
| `research/scripts/research_replay_report.py` | targeted | Python AST PASS |
| `research/scripts/research_replay_summary.py` | targeted | Python AST PASS |
| `research/scripts/research_sessions.py` | structural | Python AST PASS |
| `research/scripts/research_sr.py` | structural | Python AST PASS |
| `research/scripts/research_talib_check.py` | targeted | Python AST PASS |
| `research/scripts/research_tier0.py` | structural | Python AST PASS |
| `research/scripts/research_trend_daily.py` | structural | Python AST PASS |
| `research/scripts/research_turtle.py` | targeted | Python AST PASS |
| `research/sessions_leaders.md` | documentary | UTF-8 PASS |
| `research/sr_zones.md` | documentary | UTF-8 PASS |
| `research/talib_check.md` | documentary | UTF-8 PASS |
| `research/talib_check_data.md` | documentary | UTF-8 PASS |
| `research/tier0_thresholds.md` | documentary | UTF-8 PASS |
| `research/trend_daily.md` | documentary | UTF-8 PASS |
| `research/turtle.md` | documentary | UTF-8 PASS |
| `ruff.toml` | manual | UTF-8 PASS |
| `scanner.py` | targeted | Python AST PASS |
| `scenarios.py` | targeted | Python AST PASS |
| `scorer.py` | targeted | Python AST PASS |
| `sectors.py` | manual | Python AST PASS |
| `signal_book.py` | targeted | Python AST PASS |
| `sr.py` | manual | Python AST PASS |
| `stats.py` | targeted | Python AST PASS |
| `storage.py` | manual | Python AST PASS |
| `strategies/__init__.py` | manual | Python AST PASS |
| `strategies/base.py` | manual | Python AST PASS |
| `strategies/bias.py` | manual | Python AST PASS |
| `strategies/breakout.py` | manual | Python AST PASS |
| `strategies/cascade.py` | manual | Python AST PASS |
| `strategies/classic.py` | manual | Python AST PASS |
| `strategies/classic_strategies.py` | manual | Python AST PASS |
| `strategies/confirm.py` | manual | Python AST PASS |
| `strategies/cup_handle.py` | manual | Python AST PASS |
| `strategies/detect.py` | manual | Python AST PASS |
| `strategies/geometry.py` | manual | Python AST PASS |
| `strategies/ict.py` | manual | Python AST PASS |
| `strategies/ind_panel.py` | manual | Python AST PASS |
| `strategies/leg.py` | manual | Python AST PASS |
| `strategies/level.py` | manual | Python AST PASS |
| `strategies/loopside.py` | manual | Python AST PASS |
| `strategies/maniac.py` | manual | Python AST PASS |
| `strategies/maniac_strategies.py` | manual | Python AST PASS |
| `strategies/oi_build.py` | manual | Python AST PASS |
| `strategies/po3.py` | manual | Python AST PASS |
| `strategies/profiles.py` | manual | Python AST PASS |
| `strategies/pump.py` | manual | Python AST PASS |
| `strategies/regime.py` | manual | Python AST PASS |
| `strategies/silver_bullet.py` | manual | Python AST PASS |
| `strategies/structure.py` | manual | Python AST PASS |
| `strategies/turtle.py` | manual | Python AST PASS |
| `strategies/vsa.py` | manual | Python AST PASS |
| `strategies/wyckoff_range.py` | manual | Python AST PASS |
| `symbols.py` | manual | Python AST PASS |
| `tests/conftest.py` | test | Python AST PASS |
| `tests/fixtures/ws_samples.json` | artifact | JSON PASS |
| `tests/test_audit.py` | test | Python AST PASS |
| `tests/test_flow.py` | test | Python AST PASS |
| `tests/test_infra.py` | test | Python AST PASS |
| `tests/test_levels.py` | test | Python AST PASS |
| `tests/test_runtime.py` | test | Python AST PASS |
| `tests/test_scorer.py` | test | Python AST PASS |
| `tests/test_signal_book.py` | test | Python AST PASS |
| `tests/test_venues.py` | test | Python AST PASS |
| `tools/coinglass_heatmap.py` | targeted | Python AST PASS |
| `tools/farside_flows.py` | targeted | Python AST PASS |
| `tools/vmmap.py` | targeted | Python AST PASS |
| `train_scenarios.py` | structural | Python AST PASS |
| `venues.py` | manual | Python AST PASS |
| `watchdog.py` | manual | Python AST PASS |
| `web/app.js` | targeted | UTF-8 PASS |
| `web/index.html` | targeted | UTF-8 PASS |
| `web/lightweight-charts.5.0.8.js` | vendor | UTF-8 PASS |
| `web/style.css` | targeted | UTF-8 PASS |
| `webui.py` | targeted | Python AST PASS |
| `zones.py` | targeted | Python AST PASS |
