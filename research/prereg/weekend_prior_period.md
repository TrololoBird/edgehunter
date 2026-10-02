# Prior-period check (pre-registered 2026-10-02, before any of these runs)

The main window is 2025-04 .. 2026-09 (holdout from 2026-04). Every result is re-run on the 18 months BEFORE it:
2023-10-01 .. 2025-03-31, its own holdout from 2024-10-01 (research_cards / maniac / classic: --end 2025-03-31
--months 18 --holdout 6; research_vol / research_xsec: --window 2023-10-01,2024-10-01,2025-03-31).
A strategy or model that WORKS on the main window must also have mean net R (or the model's metric) on the same side
of zero in this prior period; otherwise its main-window result is treated as period-specific. No parameter is chosen
on this period. research_classic's report path is fixed (classic_eng43.md): the queue copies it to
classic_eng43_2023.md right after the run.
