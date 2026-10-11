#!/usr/bin/env bash
# The dashboard from outside, over HTTPS with a login (run as root after install.sh):
#   bash deploy/web_access.sh <login>          (asks for the password)
# The bot keeps listening on 127.0.0.1:8765; Caddy terminates HTTPS in front of it with a Let's Encrypt certificate
# for <ip>.sslip.io (a public DNS name that resolves to the IP itself - no domain needed) and asks for the login.
# Without the login anyone could read the cards, the journal and trigger /api/briefing?send=1 (a Telegram post).
set -euo pipefail

LOGIN="${1:?usage: bash deploy/web_access.sh <login>}"
read -r -s -p "Password for $LOGIN: " PASS; echo
[ ${#PASS} -ge 10 ] || { echo "Use at least 10 characters"; exit 1; }

IP="$(curl --proto '=https' -s4 https://api.ipify.org)"
HOST="${IP//./-}.sslip.io"

# Caddy from its official repository
if ! command -v caddy >/dev/null; then
  apt-get install -y debian-keyring debian-archive-keyring apt-transport-https gnupg
  curl --proto '=https' --tlsv1.2 -sSfL -o /tmp/caddy.gpg.key https://dl.cloudsmith.io/public/caddy/stable/gpg.key
  gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg /tmp/caddy.gpg.key
  curl --proto '=https' --tlsv1.2 -sSfL -o /etc/apt/sources.list.d/caddy-stable.list \
    https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt
  apt-get update
  apt-get install -y caddy
fi

HASH="$(caddy hash-password --plaintext "$PASS")"
cat > /etc/caddy/Caddyfile <<EOF
$HOST {
	basic_auth {
		$LOGIN $HASH
	}
	reverse_proxy 127.0.0.1:8765
}
EOF

ufw allow 80/tcp      # Let's Encrypt's HTTP challenge and the redirect to HTTPS
ufw allow 443/tcp
systemctl enable caddy
systemctl restart caddy
echo
echo "Dashboard: https://$HOST  (login $LOGIN). The certificate is issued within a minute of the first start."
