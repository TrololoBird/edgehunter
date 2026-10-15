#!/bin/sh
# Pre-start gate (systemd ExecStartPre and before a manual restart): undefined names / syntax errors and a broken
# import of the scan path stop the start instead of a bot that fails in its scan loop (the oi_signal outage, eng-128).
set -e
cd "$(dirname "$0")/.."
PY=.venv/bin/python
[ -x .venv/bin/ruff ] && .venv/bin/ruff check --select F,E9 --exclude .claude,research,'research_*.py' -q .
$PY -c "import scanner, executor, webui, briefing, strategies.detect" >/dev/null
