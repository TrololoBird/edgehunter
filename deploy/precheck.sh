#!/bin/sh
# Pre-start gate (systemd ExecStartPre and before a manual restart): undefined names / syntax errors and a broken
# import of the scan path stop the start instead of a bot that fails in its scan loop (the oi_signal outage, eng-128).
set -e
cd "$(dirname "$0")/.."
PY=.venv/bin/python
# Runtime precheck must cover executable application code only. Audit snippets and
# offline research extracts are intentionally incomplete and are not importable
# production modules; linting them can block an otherwise valid service restart.
[ -x .venv/bin/ruff ] && .venv/bin/ruff check --no-cache --select F,E9 \
  --exclude .claude,research,'research_*.py',docs/evidence,docs/audit_2026_10_16_followup/checks,tests -q .
$PY -c "import scanner, executor, webui, briefing, strategies.detect" >/dev/null
$PY -m pip check
# mode tables naming a strategy nobody registers (a deleted strategy left behind) stop the start
$PY -c "import strategies, sys; u = strategies.unknown_names(); u and sys.exit(f'unknown strategy names: {u}')"
# Lettered releases are valid feature-gate versions, but live evidence must
# remain on one exact release (eng-169l and eng-169m are never interchangeable).
$PY - <<'PY'
from config import CONFIG
from core.versioning import version_key
v = CONFIG.journal.logic_version
if version_key(v) == (0, ''):
    raise SystemExit(f'invalid logic version: {v!r}')
if CONFIG.journal.verdict_since and version_key(CONFIG.journal.verdict_since) == (0, ''):
    raise SystemExit(f'invalid verdict_since version: {CONFIG.journal.verdict_since!r}')
PY
# Every enabled mode must be represented consistently in the registry, pool rules,
# bias/regime classification, OI expectation table and statistics nature table.
$PY - <<'PY'
from config import CONFIG
from strategies import STRATEGIES
from strategies import bias, confirm, regime
from stats import NATURE

enabled = set(CONFIG.strategies.enabled)
registry = set(STRATEGIES)
pools = {rule[0] for rule in CONFIG.pools.rules}
bias_modes = set(bias.TREND) | set(bias.WITH_BIAS) | set(bias.RANGE) | set(bias.EXEMPT)
regime_modes = set(regime.TREND_MODES) | set(regime.RANGE_MODES)
expected = {
    'registry': enabled - registry,
    'pools': enabled - pools,
    'bias': enabled - bias_modes,
    'regime': enabled - regime_modes,
    'confirm.OI_EXPECT': enabled - set(confirm.OI_EXPECT),
    'stats.NATURE': enabled - set(NATURE),
}
missing = {name: sorted(values) for name, values in expected.items() if values}
if missing:
    raise SystemExit(f'incomplete strategy tables: {missing}')
PY
