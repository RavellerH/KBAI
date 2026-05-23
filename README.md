# Self-hosted Hermes LLM on VPS

Run [NousResearch Hermes-3-Llama-3.1-8B](https://huggingface.co/NousResearch/Hermes-3-Llama-3.1-8B) on your own VPS with a chat UI and a protected REST API — no cloud subscriptions, no data leaving your server.

**Stack:** Ollama · Open WebUI · Nginx · Docker Compose · systemd

---

## Requirements

| Resource | Minimum | Recommended |
|---|---|---|
| RAM | 8 GB | 16 GB |
| Disk | 20 GB free | 40 GB free |
| OS | Ubuntu 22.04 / 24.04 | Ubuntu 24.04 LTS |
| CPU | 4 cores | 8+ cores |
| GPU | not required | NVIDIA (auto-detected) |

> **Model size:** Q4_K_M quantization — ~5.5 GB download, ~6 GB RAM at runtime.

---

## Quick Install

SSH into your VPS as root, then run:

```bash
git clone -b claude/exciting-dirac-1j88g https://github.com/ravellerh/kbai /opt/kbai
DOMAIN=your-ip-or-domain bash /opt/kbai/scripts/setup.sh
```

Replace `your-ip-or-domain` with your VPS public IP or a domain name pointing to it.

The script will:
1. Detect CPU or NVIDIA GPU
2. Install Docker, Nginx, and dependencies
3. Generate random API keys
4. Start Ollama + Open WebUI via Docker Compose
5. Configure Nginx reverse proxy
6. Pull the Hermes model (~5.5 GB)
7. Enable auto-start on boot via systemd

**When finished, the script prints your access URLs and API key — save them.**

---

## Manual Install (fallback)

Use this if `git clone` or the setup script fails partway through.

### 1. Fix any broken packages

```bash
apt-get install -y --fix-broken
dpkg --configure -a
```

### 2. Add swap (required if VPS has ≤ 8 GB RAM)

```bash
fallocate -l 4G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

### 3. Install base packages

```bash
apt-get update
apt-get install -y ca-certificates curl gnupg lsb-release nginx gettext-base openssl git
```

### 4. Install Docker

```bash
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | tee /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
systemctl enable --now docker
```

### 5. Configure and start

```bash
# Set your domain/IP
DOMAIN=your-ip-or-domain
HERMES_API_KEY=$(grep '^HERMES_API_KEY=' /opt/kbai/.env | cut -d= -f2)
export DOMAIN HERMES_API_KEY

# Nginx
envsubst '${DOMAIN} ${HERMES_API_KEY}' < /opt/kbai/nginx/kbai-hermes.conf.template \
  > /etc/nginx/sites-available/kbai-hermes
ln -sf /etc/nginx/sites-available/kbai-hermes /etc/nginx/sites-enabled/kbai-hermes
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# Systemd
cp /opt/kbai/systemd/kbai-hermes.service /etc/systemd/system/kbai-hermes.service
systemctl daemon-reload && systemctl enable kbai-hermes

# Start containers and pull model
cd /opt/kbai && docker compose up -d
sleep 15
bash /opt/kbai/scripts/pull-model.sh
```

---

## What You Get

| Endpoint | URL | Auth |
|---|---|---|
| Open WebUI (chat) | `http://your-domain/` | Login created on first visit |
| Ollama REST API | `http://your-domain/ollama/` | Bearer token |

The Bearer token is auto-generated during setup and saved to `/opt/kbai/.env`.

```bash
# View your API key at any time
grep HERMES_API_KEY /opt/kbai/.env
```

---

## API Usage Examples

### Generate (streaming)

```bash
curl http://your-domain/ollama/api/generate \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "hf.co/NousResearch/Hermes-3-Llama-3.1-8B-GGUF:Q4_K_M",
    "prompt": "Explain quantum entanglement in simple terms.",
    "stream": false
  }'
```

### Chat (OpenAI-compatible format)

```bash
curl http://your-domain/ollama/api/chat \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "hf.co/NousResearch/Hermes-3-Llama-3.1-8B-GGUF:Q4_K_M",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Hello!"}
    ]
  }'
```

### List available models

```bash
curl http://your-domain/ollama/api/tags \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

## TLS / HTTPS

After setup, add a free TLS certificate with Certbot. You need a domain name pointing to your VPS (not just an IP).

```bash
apt-get install -y certbot python3-certbot-nginx
certbot --nginx -d your-domain.com
```

Certbot automatically edits the Nginx config and sets up auto-renewal.

---

## Managing the Service

```bash
# Check status
systemctl status kbai-hermes

# Stop
systemctl stop kbai-hermes

# Start
systemctl start kbai-hermes

# View logs
docker logs kbai-ollama
docker logs kbai-open-webui

# Pull a different model
docker exec kbai-ollama ollama pull <model-name>

# List loaded models
docker exec kbai-ollama ollama list
```

---

## GPU Support (NVIDIA)

The setup script auto-detects an NVIDIA GPU. If you add a GPU after initial setup, reinstall the NVIDIA Container Toolkit and restart with the GPU compose override:

```bash
# Install toolkit
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor \
  -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
apt-get update && apt-get install -y nvidia-container-toolkit
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker

# Restart with GPU support
cd /opt/kbai
docker compose down
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

---

## File Structure

```
├── docker-compose.yml          # Ollama + Open WebUI services
├── docker-compose.gpu.yml      # NVIDIA GPU override
├── .env.example                # Environment template (copy → .env)
├── nginx/
│   └── kbai-hermes.conf.template   # Nginx reverse proxy config
├── systemd/
│   └── kbai-hermes.service         # Systemd unit for auto-start
└── scripts/
    ├── setup.sh                # Main installer
    ├── install.sh              # One-liner bootstrap (downloads setup.sh)
    └── pull-model.sh           # Pull Hermes model into Ollama
```

---

## Troubleshooting

**apt-get gets killed during install**
Add swap before running setup — see step 2 of the manual install above.

**`dpkg --configure -a` fails with dependency errors**
Run `apt-get install -y --fix-broken` first, then retry `dpkg --configure -a`.

**Nginx fails to start**
Check config syntax: `nginx -t`. Ensure port 80 is not already in use: `ss -tlnp | grep :80`.

**Ollama not responding**
Check container logs: `docker logs kbai-ollama`. It may still be loading — wait 30 seconds and retry.

**Model pull fails**
Ensure the container is running (`docker ps`) and you have enough disk space (`df -h`).
