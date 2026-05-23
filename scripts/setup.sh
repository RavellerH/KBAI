#!/usr/bin/env bash
# setup.sh — Installs and configures the KBAI Hermes Agent on Ubuntu/Debian VPS
# Installs: Docker, Docker Compose plugin, Nginx, systemd service
#
# Non-interactive usage (no prompts):
#   curl -fsSL https://raw.githubusercontent.com/ravellerh/kbai/claude/exciting-dirac-1j88g/scripts/install.sh | bash
#
# Or with DOMAIN pre-set:
#   DOMAIN=your-vps-ip bash setup.sh

set -euo pipefail

INSTALL_DIR="/opt/kbai"
# When run via curl/pipe, BASH_SOURCE[0] is empty — fall back to INSTALL_DIR
_src="${BASH_SOURCE[0]:-}"
if [[ -n "$_src" && "$_src" != "bash" ]]; then
    REPO_DIR="$(cd "$(dirname "$_src")/.." && pwd)"
else
    REPO_DIR="${INSTALL_DIR}"
fi

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}[kbai]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
die()  { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }
sep()  { echo -e "${CYAN}──────────────────────────────────────────${NC}"; }

# ── Root check ────────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && die "Run as root or with sudo."

# ── OS check ──────────────────────────────────────────────────────────────────
. /etc/os-release 2>/dev/null || true
[[ "${ID:-}" == "ubuntu" || "${ID:-}" == "debian" ]] || \
    warn "This script is tested on Ubuntu/Debian. Proceeding anyway."

sep
log "KBAI Hermes Agent — Setup"
sep

# ── Detect GPU ────────────────────────────────────────────────────────────────
HAS_GPU=false
GPU_INFO=""
if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
    HAS_GPU=true
    GPU_INFO=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
    log "NVIDIA GPU detected: ${GPU_INFO}"
else
    warn "No NVIDIA GPU detected — will run in CPU mode (Q4_K_M quantized model)."
    warn "Minimum recommended RAM: 8 GB (16 GB preferred)."
fi

# ── Load or create .env ───────────────────────────────────────────────────────
ENV_FILE="${INSTALL_DIR}/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
    [[ ! -f "${REPO_DIR}/.env.example" ]] && die ".env.example not found in ${REPO_DIR}"
    mkdir -p "${INSTALL_DIR}"
    cp "${REPO_DIR}/.env.example" "${ENV_FILE}"

    # Auto-generate secrets
    WEBUI_SECRET=$(openssl rand -hex 32)
    API_KEY=$(openssl rand -hex 24)
    sed -i "s|^WEBUI_SECRET_KEY=.*|WEBUI_SECRET_KEY=${WEBUI_SECRET}|" "${ENV_FILE}"
    sed -i "s|^HERMES_API_KEY=.*|HERMES_API_KEY=${API_KEY}|" "${ENV_FILE}"

    warn ".env created at ${ENV_FILE} with generated secrets."

    # Use DOMAIN env var if set, otherwise prompt
    if [[ -n "${DOMAIN:-}" ]]; then
        DOMAIN_INPUT="${DOMAIN}"
        log "Using DOMAIN from environment: ${DOMAIN_INPUT}"
    else
        echo ""
        read -rp "Enter your VPS public IP or domain name: " DOMAIN_INPUT
        [[ -z "${DOMAIN_INPUT}" ]] && die "DOMAIN cannot be empty."
    fi
    sed -i "s|^DOMAIN=.*|DOMAIN=${DOMAIN_INPUT}|" "${ENV_FILE}"
    log "DOMAIN set to: ${DOMAIN_INPUT}"
fi

# shellcheck source=/dev/null
source "${ENV_FILE}"
[[ "${DOMAIN:-}" == "your-vps-ip-or-domain.example.com" ]] && \
    die "Set a real DOMAIN value in ${ENV_FILE} before running setup."

sep
log "Installing system packages..."

# ── apt prerequisites ─────────────────────────────────────────────────────────
apt-get update -qq
apt-get install -y -qq \
    ca-certificates curl gnupg lsb-release nginx gettext-base openssl

# ── Docker ────────────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    log "Installing Docker..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        | tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable --now docker
else
    log "Docker already installed: $(docker --version)"
fi

# ── NVIDIA Container Toolkit (GPU only) ──────────────────────────────────────
if [[ "${HAS_GPU}" == "true" ]]; then
    if ! dpkg -l | grep -q nvidia-container-toolkit 2>/dev/null; then
        log "Installing NVIDIA Container Toolkit..."
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
            | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
        curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
            | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
            | tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
        apt-get update -qq
        apt-get install -y -qq nvidia-container-toolkit
        nvidia-ctk runtime configure --runtime=docker
        systemctl restart docker
    else
        log "NVIDIA Container Toolkit already installed."
    fi
fi

# ── Copy project files to INSTALL_DIR ─────────────────────────────────────────
sep
log "Copying project to ${INSTALL_DIR}..."
rsync -a --exclude='.git' --exclude='.env' "${REPO_DIR}/" "${INSTALL_DIR}/"
# .env was already placed there; don't overwrite it

# ── Nginx ─────────────────────────────────────────────────────────────────────
sep
log "Configuring Nginx..."
NGINX_CONF="/etc/nginx/sites-available/kbai-hermes"
NGINX_TEMPLATE="${INSTALL_DIR}/nginx/kbai-hermes.conf.template"

# map_hash_bucket_size must live in the http context, separate from the site config
echo 'map_hash_bucket_size 128;' > /etc/nginx/conf.d/map-hash.conf

export DOMAIN HERMES_API_KEY
envsubst '${DOMAIN} ${HERMES_API_KEY}' < "${NGINX_TEMPLATE}" > "${NGINX_CONF}"

ln -sf "${NGINX_CONF}" /etc/nginx/sites-enabled/kbai-hermes
rm -f /etc/nginx/sites-enabled/default   # remove default placeholder

# AnythingLLM on port 3002
NGINX_ALLM_CONF="/etc/nginx/sites-available/kbai-anythingllm"
envsubst '${DOMAIN}' < "${INSTALL_DIR}/nginx/kbai-anythingllm.conf.template" > "${NGINX_ALLM_CONF}"
ln -sf "${NGINX_ALLM_CONF}" /etc/nginx/sites-enabled/kbai-anythingllm

nginx -t && systemctl reload nginx
log "Nginx configured for domain: ${DOMAIN}"

# ── Systemd service ───────────────────────────────────────────────────────────
sep
log "Installing systemd service..."
cp "${INSTALL_DIR}/systemd/kbai-hermes.service" /etc/systemd/system/kbai-hermes.service
systemctl daemon-reload
systemctl enable kbai-hermes

# ── Start services ────────────────────────────────────────────────────────────
sep
log "Starting Docker Compose services..."
cd "${INSTALL_DIR}"
if [[ "${HAS_GPU}" == "true" ]]; then
    docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
else
    docker compose up -d
fi

log "Waiting for Ollama to be ready..."
for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:11434/api/tags &>/dev/null; then
        break
    fi
    sleep 2
done

# ── Pull Hermes model ─────────────────────────────────────────────────────────
sep
log "Pulling Hermes-3-Llama-3.1-8B (Q4_K_M, ~5.5 GB)..."
bash "${INSTALL_DIR}/scripts/pull-model.sh"

# ── Done ──────────────────────────────────────────────────────────────────────
sep
API_KEY_VALUE=$(grep '^HERMES_API_KEY=' "${ENV_FILE}" | cut -d= -f2)
log "Setup complete!"
echo ""
echo -e "  Open WebUI:      ${CYAN}http://${DOMAIN}/${NC}"
echo -e "  AnythingLLM RAG: ${CYAN}http://${DOMAIN}:3002/${NC}"
echo -e "  Ollama API:      ${CYAN}http://${DOMAIN}/ollama/${NC}"
echo -e "  API key:         ${YELLOW}${API_KEY_VALUE}${NC}"
echo ""
echo -e "  Example API call:"
echo -e "  ${CYAN}curl http://${DOMAIN}/ollama/api/generate \\"
echo -e "    -H 'Authorization: Bearer ${API_KEY_VALUE}' \\"
echo -e "    -d '{\"model\":\"hf.co/NousResearch/Hermes-3-Llama-3.1-8B-GGUF:Q4_K_M\",\"prompt\":\"Hello\"}' ${NC}"
echo ""
warn "Credentials are stored in: ${ENV_FILE}"
warn "To add TLS, run: certbot --nginx -d ${DOMAIN}"
sep
