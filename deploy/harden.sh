#!/usr/bin/env bash
# Server hardening - the OWNER runs it (Claude does not change security settings):   bash /opt/pump/deploy/harden.sh
#  1. SSH: keys only (no password logins), root only with a key
#  2. fail2ban: bans an address after 5 failed SSH logins for 1 hour
#  3. unattended-upgrades: security updates installed automatically (no automatic reboot)
# BEFORE running: every device you log in from must have its key in /root/.ssh/authorized_keys
# (the laptop's id_ed25519 is there; a phone SSH app needs its own key added first), else you lock yourself out.
# The provider's web console still works if that happens.
set -euo pipefail

echo "Keys allowed for root:"
awk '{print "  " $1, substr($2, 1, 16) "...", $3}' /root/.ssh/authorized_keys
read -r -p "Every device you use is listed above? Type yes to continue: " ok
ok=$(printf '%s' "$ok" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
case "$ok" in yes|y|да|д) ;; *) echo "stopped (answer was: '$ok')"; exit 1 ;; esac

# 1. SSH keys only (a drop-in wins over sshd_config and over 50-cloud-init.conf by its name order)
cat > /etc/ssh/sshd_config.d/00-keys-only.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
EOF
sshd -t && systemctl reload ssh

# 2. fail2ban for sshd
apt-get update -q
DEBIAN_FRONTEND=noninteractive apt-get install -y -q fail2ban unattended-upgrades
cat > /etc/fail2ban/jail.d/sshd.local <<'EOF'
[sshd]
enabled = true
# a minimized Ubuntu has no /var/log/auth.log (rsyslog absent): read sshd from the systemd journal
backend = systemd
maxretry = 5
findtime = 10m
bantime = 1h
EOF
systemctl enable --now fail2ban
systemctl restart fail2ban

# 3. security updates only, never an automatic reboot (the bot runs here)
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
sed -i 's|^//\?\s*Unattended-Upgrade::Automatic-Reboot .*|Unattended-Upgrade::Automatic-Reboot "false";|' /etc/apt/apt.conf.d/50unattended-upgrades
systemctl enable --now unattended-upgrades

echo
sshd -T | grep -E '^(passwordauthentication|permitrootlogin|kbdinteractiveauthentication)'
fail2ban-client status sshd | head -5
echo "Done. Test a NEW ssh login from another terminal before closing this one."
