#!/usr/bin/env bash
# Everything after install.sh in one go (run as root on the VPS):   bash /opt/pump/deploy/setup_server.sh
#  - the latest code of the checked-out branch, polars pinned to the version the bot was tested with
#  - the dashboard public over HTTPS (deploy/web_access.sh)
#  - config.local.toml: [web] open_browser = false; merged with config.from_laptop.toml when you copied it
#    (BingX demo keys, Telegram token / channel) - signals.db / demo_trades.db / scanner_state.json / models are used
#    as they are when present
#  - the service started (and restarted when it already ran)
set -euo pipefail
APP=/opt/pump
cd "$APP"

git config --global --add safe.directory "$APP"     # the tree belongs to the pump user
git pull --ff-only
sudo -u pump "$APP/.venv/bin/python" -m pip install -q "polars==1.44.2"

CFG="$APP/config.local.toml"
touch "$CFG"
if [ -f "$APP/config.from_laptop.toml" ]; then
  # the laptop's settings first; the server's [web] section is written below once
  grep -v '^open_browser' "$APP/config.from_laptop.toml" > "$CFG.new"
  mv "$CFG.new" "$CFG"
  rm "$APP/config.from_laptop.toml"
fi
if grep -q '^\[web\]' "$CFG"; then
  grep -q '^open_browser' "$CFG" || sed -i '/^\[web\]/a open_browser = false' "$CFG"
else
  printf '\n[web]\nopen_browser = false\n' >> "$CFG"
fi

bash "$APP/deploy/web_access.sh"

chown -R pump:pump "$APP"
systemctl restart pump-bot
sleep 20
systemctl --no-pager --lines=15 status pump-bot || true
echo
echo "Log: journalctl -u pump-bot -f   (Ctrl+C leaves the log, the bot keeps running)"
