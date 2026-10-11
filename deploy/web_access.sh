#!/usr/bin/env bash
# The dashboard as a PUBLIC page over HTTPS (run as root after install.sh): bash deploy/web_access.sh
# The bot keeps listening on 127.0.0.1:8765; Caddy terminates HTTPS in front of it with a Let's Encrypt certificate
# for <ip>.sslip.io (a public DNS name that resolves to the IP itself - no domain needed). No login: anyone with the
# address sees the cards and the journal. Posting to Telegram (/api/briefing) and the internals (/api/debug) answer
# local requests only (webui._local), so the public cannot post to the channel.
set -euo pipefail

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

# HTTP/1.1 + 2 only: HTTP/3 needs UDP 443, which a VPN on the same server (amnezia-awg2) may already hold - caddy
# then failed to start at all
cat > /etc/caddy/Caddyfile <<EOF
{
	servers {
		protocols h1 h2
	}
}

$HOST {
	encode gzip
	reverse_proxy 127.0.0.1:8765
}
EOF

ufw allow 80/tcp      # Let's Encrypt's HTTP challenge and the redirect to HTTPS
ufw allow 443/tcp
systemctl enable caddy
systemctl restart caddy
echo "Dashboard: https://$HOST"
