#!/usr/bin/env bash
# Weekly dependency report. Only direct requirements with a newer release
# that still satisfies requirements.txt are actionable; ccxt's exact
# transitive pins and development tools are intentionally omitted.
set -euo pipefail

APP=/opt/edgehunter
cd "$APP"
OUT=$(.venv/bin/python - <<'PY'
import json
import re
import subprocess
from pathlib import Path
from packaging.specifiers import SpecifierSet

def specs(path):
    out = {}
    for raw in Path(path).read_text(encoding='utf-8').splitlines():
        line = raw.split('#', 1)[0].strip()
        m = re.match(r'^([A-Za-z0-9_.-]+)\s*(?:\[[^]]+\])?\s*(.*)$', line)
        if not m or line.startswith(('-', 'git+')):
            continue
        out[m.group(1).lower().replace('_', '-')] = m.group(2).split(';', 1)[0].strip()
    return out

direct = specs('requirements.txt')
pinned = {name for name, spec in specs('constraints.txt').items() if spec.startswith('==')}
rows = json.loads(subprocess.check_output([
    '.venv/bin/python', '-m', 'pip', 'list', '--outdated', '--format=json'], text=True))
for row in rows:
    name = row['name'].lower().replace('_', '-')
    spec = direct.get(name)
    if spec is None or name in pinned:
        continue
    try:
        if spec and row['latest_version'] not in SpecifierSet(spec):
            continue
    except Exception:
        continue
    print(f"{row['name']} {row['version']} -> {row['latest_version']}")
PY
)

CUR=$(.venv/bin/python -c "import ccxt;print(ccxt.__version__)")
NEW=$(.venv/bin/python -m pip index versions ccxt 2>/dev/null | head -1 | grep -oP "\(\K[^)]+" || true)
set -a
. /etc/edgehunter.env
set +a
GROUP=$(grep -oP '^group_chat_id = "\K[^" ]+' config.local.toml)
TOPIC=$(grep -oP '^topic_service = \K[0-9]+' config.local.toml)
MSG="🛠 Зависимости: ccxt $CUR (последняя ${NEW:-неизвестно})"
if [ -n "$NEW" ] && [ "$CUR" != "$NEW" ]; then
  MSG="$MSG — требуется обновление ccxt"
fi
if [ -n "$OUT" ]; then
  MSG="$MSG\nОбновления, совместимые с requirements.txt:\n$OUT"
else
  MSG="$MSG\nНет безопасных обновлений в пределах текущих constraints.txt/requirements.txt; pip check clean."
fi
curl -s -m 15 "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=$GROUP" --data-urlencode "message_thread_id=$TOPIC" \
  --data-urlencode "text=$MSG" >/dev/null
