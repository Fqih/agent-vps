#!/usr/bin/env bash
# One-time VPS hardening + services. Run on the VPS: bash ~/hermes_automation/setup-vps.sh
set -euo pipefail
cd ~/hermes_automation

echo "== 1/5 Tailscale"
if ! command -v tailscale >/dev/null; then
    curl -fsSL https://tailscale.com/install.sh | sh
fi
sudo tailscale up --hostname=agent-vps        # prints a login URL the first time
tailscale ip -4

echo "== 2/5 Expose 9router to the tailnet only"
sudo tailscale serve --bg --tcp 20128 tcp://127.0.0.1:20128

echo "== 3/5 Bind docker ports to localhost (docker bypasses ufw otherwise)"
cd ~/9router
cp docker-compose.yml docker-compose.yml.bak-tailscale
sed -i -e 's#"20128:20128"#"127.0.0.1:20128:20128"#' -e 's#"8787:8787"#"127.0.0.1:8787:8787"#' docker-compose.yml
docker compose up -d
cd ~/hermes_automation

echo "== 4/5 Firewall"
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow in on tailscale0
sudo ufw --force enable

echo "== 5/5 Services"
sudo install -m 644 infobot.service hermes-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now infobot.service
if grep -qE '^TELEGRAM_BOT_TOKEN=' ~/.hermes/.env && grep -qE '^TELEGRAM_ALLOWED_USERS=' ~/.hermes/.env; then
    sudo systemctl enable --now hermes-gateway.service
else
    echo "SKIP hermes-gateway: add TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USERS to ~/.hermes/.env first"
fi

echo "== Done"
sudo ufw status verbose | head -20
ss -tlnp | grep -E ':(20128|8787|9090) '
systemctl --no-pager --lines=0 status infobot hermes-gateway | grep -E '●|Active'
