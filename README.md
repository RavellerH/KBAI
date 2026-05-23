# KBAI — Self-hosted Knowledge Base AI

A fully self-hosted, open-source AI stack for your personal knowledge base.
Run the **Hermes-3-Llama-3.1-8B** language model on your own VPS with a chat interface,
a RAG engine that can search your Obsidian notes and PDFs, and a protected REST API —
no cloud subscriptions required, no data leaving your server.

---

## What's Included

| Service | Purpose | Access |
|---|---|---|
| **Ollama** | Serves the Hermes LLM locally | Internal only |
| **Open WebUI** | Chat UI for the Hermes model | `http://your-ip/` |
| **AnythingLLM** | RAG — chat with your notes & PDFs | `http://your-ip:3002/` |
| **Nginx** | Reverse proxy + Bearer token API auth | Port 80 |
| **systemd** | Auto-start all services on boot | — |

**Model:** [NousResearch Hermes-3-Llama-3.1-8B](https://huggingface.co/NousResearch/Hermes-3-Llama-3.1-8B) — Q4_K_M quantization (~5.5 GB, runs on CPU)

---

## Architecture

```
                        ┌─────────────────────────────────┐
                        │         YOUR VPS                 │
                        │                                  │
  Browser / API  ──────▶│  Nginx (port 80)                │
                        │   ├── /         → Open WebUI    │
                        │   └── /ollama/  → Ollama API    │
                        │                                  │
  Browser        ──────▶│  Nginx (port 3002)              │
                        │   └── /        → AnythingLLM   │
                        │                                  │
                        │  Docker Compose                  │
                        │   ├── kbai-ollama      :11434   │
                        │   ├── kbai-open-webui  :3001    │
                        │   └── kbai-anythingllm :8081    │
                        └─────────────────────────────────┘
```

---

## Requirements

| Resource | Minimum | Recommended |
|---|---|---|
| RAM | 8 GB + 4 GB swap | 16 GB |
| Disk | 20 GB free | 40 GB free |
| OS | Ubuntu 22.04 / 24.04 | Ubuntu 24.04 LTS |
| CPU | 4 cores | 8+ cores |
| GPU | Not required | NVIDIA (auto-detected) |

> The Q4_K_M model uses ~5.5 GB RAM at runtime. A 4 GB swap file is strongly recommended on 8 GB VPS instances.

---

## Quick Install

SSH into your VPS as root, then run:

```bash
git clone -b claude/exciting-dirac-1j88g https://github.com/ravellerh/kbai /opt/kbai
DOMAIN=your-ip-or-domain bash /opt/kbai/scripts/setup.sh
```

Replace `your-ip-or-domain` with your VPS public IP or a domain name pointing to it.

The script will:
1. Add 4 GB swap (prevents OOM kills on 8 GB VPS)
2. Fix any broken dpkg state
3. Install Docker, Nginx, and all dependencies
4. Generate random API keys and secrets
5. Pull and start Ollama + Open WebUI + AnythingLLM
6. Configure Nginx reverse proxy with Bearer token auth
7. Enable auto-start on boot via systemd
8. Download the Hermes-3-Llama-3.1-8B model (~5.5 GB)

**When finished, the script prints your URLs and API key — save them.**

---

## Manual Install (fallback)

Use this if the setup script fails partway through.

### 1. Fix broken packages (if needed)

```bash
apt-get install -y --fix-broken
dpkg --configure -a
```

### 2. Add 4 GB swap

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

### 5. Start the stack

```bash
cd /opt/kbai

# Generate secrets
WEBUI_SECRET=$(openssl rand -hex 32)
API_KEY=$(openssl rand -hex 24)
DOMAIN=your-ip-or-domain

# Write .env
cat > /opt/kbai/.env <<EOF
DOMAIN=$DOMAIN
WEBUI_SECRET_KEY=$WEBUI_SECRET
HERMES_API_KEY=$API_KEY
EOF

# Nginx
echo 'map_hash_bucket_size 128;' > /etc/nginx/conf.d/map-hash.conf
export DOMAIN HERMES_API_KEY=$API_KEY
envsubst '${DOMAIN} ${HERMES_API_KEY}' < nginx/kbai-hermes.conf.template \
  > /etc/nginx/sites-available/kbai-hermes
envsubst '${DOMAIN}' < nginx/kbai-anythingllm.conf.template \
  > /etc/nginx/sites-available/kbai-anythingllm
ln -sf /etc/nginx/sites-available/kbai-hermes /etc/nginx/sites-enabled/kbai-hermes
ln -sf /etc/nginx/sites-available/kbai-anythingllm /etc/nginx/sites-enabled/kbai-anythingllm
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl start nginx && systemctl enable nginx

# Start containers
docker compose up -d

# Wait and pull models
sleep 20
docker exec kbai-ollama ollama pull hf.co/NousResearch/Hermes-3-Llama-3.1-8B-GGUF:Q4_K_M
docker exec kbai-ollama ollama pull nomic-embed-text
```

---

## Initial Setup

### Open WebUI (Chat with Hermes)

1. Open `http://your-ip/`
2. Create your admin account on first visit
3. The Hermes model is pre-loaded — start chatting

### AnythingLLM (RAG — Chat with your knowledge base)

1. Open `http://your-ip:3002/`
2. Create your admin account
3. Go to **Settings → LLM Provider**:
   - Provider: `Ollama`
   - Base URL: `http://kbai-ollama:11434`
   - Model: `hf.co/NousResearch/Hermes-3-Llama-3.1-8B-GGUF:Q4_K_M`
4. Go to **Settings → Embedding**:
   - Provider: `Ollama`
   - Base URL: `http://kbai-ollama:11434`
   - Model: `nomic-embed-text`
5. Create **Workspaces** for each domain (e.g. `AI Research`, `Crypto`, `Creative Writing`)
6. Upload your PDFs, Markdown notes, and documents into each workspace
7. Chat with your documents — AnythingLLM retrieves relevant context using RAG

---

## Ollama API

The Ollama REST API is exposed at `/ollama/` and requires a Bearer token.

```bash
# View your API key
grep HERMES_API_KEY /opt/kbai/.env
```

### Generate (single prompt)

```bash
curl http://your-domain/ollama/api/generate \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "hf.co/NousResearch/Hermes-3-Llama-3.1-8B-GGUF:Q4_K_M",
    "prompt": "Explain attention mechanisms in transformers.",
    "stream": false
  }'
```

### Chat (multi-turn)

```bash
curl http://your-domain/ollama/api/chat \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "hf.co/NousResearch/Hermes-3-Llama-3.1-8B-GGUF:Q4_K_M",
    "messages": [
      {"role": "system", "content": "You are a helpful research assistant."},
      {"role": "user", "content": "What is a transformer?"}
    ]
  }'
```

### List models

```bash
curl http://your-domain/ollama/api/tags \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

## Pulling Additional Models

```bash
# Pull any model from Ollama library or HuggingFace
docker exec kbai-ollama ollama pull mistral
docker exec kbai-ollama ollama pull llama3.2

# List all loaded models
docker exec kbai-ollama ollama list
```

---

## TLS / HTTPS

Requires a domain name (not just an IP) pointing to your VPS.

```bash
apt-get install -y certbot python3-certbot-nginx
certbot --nginx -d your-domain.com
```

Certbot automatically configures Nginx and sets up auto-renewal.

---

## Service Management

```bash
# Status of all containers
docker ps

# Restart everything
systemctl restart kbai-hermes

# Stop / start
systemctl stop kbai-hermes
systemctl start kbai-hermes

# View logs
docker logs kbai-ollama
docker logs kbai-open-webui
docker logs kbai-anythingllm

# Rebuild and restart a single service
cd /opt/kbai && docker compose up -d --force-recreate open-webui
```

---

## GPU Support (NVIDIA)

The setup script auto-detects an NVIDIA GPU. To add GPU support after initial install:

```bash
# Install NVIDIA Container Toolkit
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor \
  -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
apt-get update && apt-get install -y nvidia-container-toolkit
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker

# Restart Ollama with GPU support
cd /opt/kbai
docker compose down
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

---

## File Structure

```
├── docker-compose.yml               # Ollama + Open WebUI + AnythingLLM
├── docker-compose.gpu.yml           # NVIDIA GPU override
├── .env.example                     # Environment template (copy → .env)
├── nginx/
│   ├── kbai-hermes.conf.template    # Proxy config: Open WebUI + Ollama API
│   └── kbai-anythingllm.conf.template  # Proxy config: AnythingLLM on :3002
├── systemd/
│   └── kbai-hermes.service          # Systemd unit for auto-start
└── scripts/
    ├── setup.sh                     # Main installer
    ├── install.sh                   # Bootstrap (downloads setup.sh)
    └── pull-model.sh                # Pull Hermes model into Ollama
```

---

## Troubleshooting

**apt-get gets killed (OOM) during install**
Add swap before running setup — see step 2 of manual install above. 8 GB RAM with no swap is not enough to install Docker packages.

**`dpkg --configure -a` fails with dependency errors**
Run `apt-get install -y --fix-broken` first, then retry.

**Nginx fails with `map_hash_bucket_size` error**
Ensure `/etc/nginx/conf.d/map-hash.conf` exists: `echo 'map_hash_bucket_size 128;' > /etc/nginx/conf.d/map-hash.conf`

**Open WebUI shows "Backend Required" error**
This happens when Nginx routes `/api/` to Ollama instead of Open WebUI. The current config routes `/ollama/` to Ollama and all other traffic to Open WebUI — this is correct. If you see this error, check that your Nginx config matches `nginx/kbai-hermes.conf.template`.

**Ollama not responding**
Check container logs: `docker logs kbai-ollama`. It may still be initializing — wait 30 seconds and retry.

**AnythingLLM can't connect to Ollama**
Use `http://kbai-ollama:11434` as the base URL inside AnythingLLM settings (not localhost — they communicate over the Docker internal network).

**Model pull fails / runs out of disk**
Check disk space: `df -h`. The Hermes model needs ~6 GB free. The embedding model (`nomic-embed-text`) needs an additional ~270 MB.

**Port 3002 not reachable**
Check nginx is listening: `ss -tlnp | grep 3002`. If not, verify `/etc/nginx/sites-enabled/kbai-anythingllm` exists and reload nginx.
