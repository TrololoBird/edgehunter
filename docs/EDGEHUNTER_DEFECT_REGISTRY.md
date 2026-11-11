# EdgeHunter Defect Registry v1

Статус: начальная версия независимого аудита.

Каждая запись должна содержать: defect_id, location, exact function/contract, evidence, reproduction, impact, severity, current state, required fix, regression test.

| ID | Location | Function/contract | Evidence | Status | Severity |
|---|---|---|---|---|---|
| D-001 | briefing.py / JSONL | rr_ok serialization and classification | Historical records contain both string and boolean representations; classifier uses identity check | VERIFIED | P0 |
| D-002 | briefing.py | rules_v cohort isolation | Archive contains b169a, b168y and missing rules_v; current code uses a newer rules version | VERIFIED | P0 |
| D-003 | briefing.py | outcome model | Scenario, order intent and fill are historically coupled; new limit-on-retest needs replay evidence | VERIFIED/PARTIAL | P0 |
| D-004 | briefing_chart.py | gross/net R:R contract | plan and display historically used different bases/cost semantics | VERIFIED/PARTIAL | P0 |
| D-005 | briefing.py / sr.py | as-of candle propagation | zone construction requires explicit closed-bar input; all downstream consumers are not yet proven | VERIFIED/PARTIAL | P0 |
| D-006 | briefing.py / web/app.js | outcome horizon contract | OUTCOME_HOURS and UI wording historically diverged | VERIFIED | P1 |
| D-007 | zones.py / sr.py | tfs lineage | label and structural tfs must be traced through RawLevel, cluster and merge | OPEN | P1 |
| D-008 | pierce.py | point-in-time calibration | p50/p80 source window and calibration timestamp not yet proven for every record | OPEN | P1 |
| D-009 | webui.py / web/app.js | snapshot coherence | WebSocket live state and cached REST analysis have different freshness semantics | VERIFIED/PARTIAL | P1 |
| D-010 | all publication paths | evidence lineage | no universal publication → scenario → evidence → snapshot contract | VERIFIED | P0 |
| D-011 | all historical stores | immutable evidence | no universal versioned correction model for source events and derived evidence | VERIFIED | P0 |
| D-012 | quality propagation | monotonic degradation | component quality states exist but no global publication gate is proven | VERIFIED/PARTIAL | P0 |
| D-013 | test invocation | environment contract | system pytest fails imports; project venv + PYTHONPATH passes | VERIFIED | P1 |
| D-014 | runtime deployment | source/runtime identity | process started before current working-tree changes; disk and memory can diverge | VERIFIED | P0 |
| D-015 | statistics | dependent outcomes | overlapping scenario windows require episode/block inference; no universal contract yet | OPEN | P1 |
| D-016 | API/UI | untrusted HTML sinks | interpolated values are rendered through HTML templates; full taint review pending | OPEN | P1 |

Статус OPEN означает, что вопрос сформулирован и локализован, но воспроизводящий артефакт ещё не зафиксирован.
