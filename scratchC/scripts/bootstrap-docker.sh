#!/usr/bin/env bash
#
# One-time bootstrap for a fresh Ubuntu VM.
# Installs Docker (Engine + Compose plugin), adds you to the docker group,
# and opens firewall ports 22 / 80 / 443.
#
# Usage:
#   sudo bash scripts/bootstrap-docker.sh
#
# You only need to run this ONCE per VM. All apps share this Docker install.

set -euo pipefail

BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${BLUE}▸${NC} $*"; }
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}!${NC} $*"; }

if [[ $EUID -ne 0 ]]; then
    echo "Run as root: sudo bash $0"
    exit 1
fi

# ── Docker ────────────────────────────────────────────────
if command -v docker &>/dev/null && docker compose version &>/dev/null; then
    ok "Docker and compose already installed: $(docker --version)"
else
    log "Installing Docker via official convenience script..."
    curl -fsSL https://get.docker.com | sh
    ok "Docker installed: $(docker --version)"
fi

systemctl enable --now docker >/dev/null
ok "Docker daemon is running."

# ── Add the invoking user to the docker group ─────────────
if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]]; then
    if id -nG "$SUDO_USER" | tr ' ' '\n' | grep -qx docker; then
        ok "User $SUDO_USER is already in the docker group."
    else
        usermod -aG docker "$SUDO_USER"
        warn "Added $SUDO_USER to the docker group."
        warn "You must log out and back in (or run: newgrp docker) for this to take effect."
    fi
fi

# ── Firewall ──────────────────────────────────────────────
if ! command -v ufw &>/dev/null; then
    log "Installing UFW..."
    apt-get update -qq
    apt-get install -y -qq ufw
fi

ufw allow 22/tcp   comment 'SSH'   >/dev/null
ufw allow 80/tcp   comment 'HTTP'  >/dev/null
ufw allow 443/tcp  comment 'HTTPS' >/dev/null
ufw allow 443/udp  comment 'HTTP/3'>/dev/null

if ! ufw status | grep -q "Status: active"; then
    ufw --force enable >/dev/null
    ok "UFW enabled with 22/80/443 open."
else
    ok "UFW already active with 22/80/443 open."
fi

echo
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Bootstrap complete.${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo
echo "  Next steps:"
echo "    1. Log out and back in  (so your user picks up the docker group)"
echo "    2. git clone <your repo>"
echo "    3. cd <repo> && cp .env.example .env && nano .env"
echo "    4. docker compose up -d"
echo
echo "  Also make sure:"
echo "    - Your DNS points at this VM's public IP"
echo "    - Azure NSG allows inbound TCP 80 and 443"
echo
