#!/usr/bin/env bash
# One-time setup of the bot on a fresh Ubuntu 24.04 VPS (run as root). Idempotent: safe to run again.
#   curl -O .../install.sh   (or copy the repo first)   then:   bash deploy/install.sh
set -euo pipefail

APP=/opt/pump
USER_NAME=pump

# 1. system packages, time sync (signed exchange requests need an exact clock), a 2 GB swap file
apt-get update
apt-get install -y git curl ca-certificates build-essential chrony ufw
systemctl enable --now chrony
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q /swapfile /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# 2. a user without login rights that owns the bot
id -u "$USER_NAME" >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin "$USER_NAME"

# 3. the code (copy the repo to $APP before running this script, or clone it here)
mkdir -p "$APP"
chown -R "$USER_NAME":"$USER_NAME" "$APP"

# 4. Python 3.14 + the venv through uv (Ubuntu's python3 is older)
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
cd "$APP"
uv python install 3.14
sudo -u "$USER_NAME" bash -c "cd $APP && $(command -v uv) venv --python 3.14 .venv && .venv/bin/python -m ensurepip && .venv/bin/python -m pip install -r requirements.txt"

# 5. firewall: SSH only - the dashboard listens on 127.0.0.1 and is reached through an SSH tunnel
ufw allow OpenSSH
ufw --force enable

# 6. the service
cp "$APP/deploy/pump-bot.service" /etc/systemd/system/pump-bot.service
systemctl daemon-reload
systemctl enable pump-bot
echo
echo "Done. Put config.local.toml (the BingX demo keys, [web] open_browser = false) into $APP, then:"
echo "  systemctl start pump-bot && journalctl -u pump-bot -f"
