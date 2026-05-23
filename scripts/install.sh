#!/usr/bin/env bash
# One-shot installer for KBAI Hermes Agent
# Usage: curl -fsSL <url>/install.sh | bash
# Or:    curl -fsSL <url>/install.sh | DOMAIN=your-vps-ip bash

set -euo pipefail

BRANCH="claude/exciting-dirac-1j88g"
REPO="ravellerh/kbai"
RAW="https://raw.githubusercontent.com/${REPO}/${BRANCH}"
INSTALL_DIR="/opt/kbai"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}[kbai]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
die()  { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }
sep()  { echo -e "${CYAN}──────────────────────────────────────────${NC}"; }

[[ $EUID -ne 0 ]] && die "Run as root or with sudo."

sep
log "Downloading KBAI Hermes Agent files..."
sep

mkdir -p \
    "${INSTALL_DIR}/nginx" \
    "${INSTALL_DIR}/systemd" \
    "${INSTALL_DIR}/scripts"

download() {
    local path="$1"
    curl -fsSL "${RAW}/${path}" -o "${INSTALL_DIR}/${path}"
}

download "docker-compose.yml"
download "docker-compose.gpu.yml"
download ".env.example"
download "nginx/kbai-hermes.conf.template"
download "systemd/kbai-hermes.service"
download "scripts/setup.sh"
download "scripts/pull-model.sh"
chmod +x "${INSTALL_DIR}/scripts/setup.sh" "${INSTALL_DIR}/scripts/pull-model.sh"

log "Files downloaded to ${INSTALL_DIR}"

# Run setup from INSTALL_DIR so REPO_DIR resolves correctly
export DOMAIN="${DOMAIN:-}"
exec bash "${INSTALL_DIR}/scripts/setup.sh"
