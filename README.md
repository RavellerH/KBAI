# KBAI — Self-hosted Knowledge Base AI

A fully self-hosted, open-source AI stack for your personal knowledge base.
Run powerful language models on your own VPS with a chat interface, a RAG engine
that searches your notes and PDFs, a Telegram bot with multi-model routing, and
a protected REST API — no cloud subscriptions required, no data leaving your server.

---

## What's Included

| Service | Purpose | Access |
|---|---|---|
| **Ollama** | Serves the Hermes LLM locally | Internal only |
| **Open WebUI** | Chat UI for the Hermes model | `http://your-ip/` |
| **AnythingLLM** | RAG — chat with your notes & PDFs | `http://your-ip:3002/` |
| **Telegram Bot** | Private AI assistant with model routing + file upload | Telegram |
| **Nginx** | Reverse proxy + Bearer token API auth | Port 80 / 3002 |
| **systemd** | Auto-start all services on boot | — |

**Default model:** [NousResearch Hermes-3-Llama-3.1-8B](https://huggingface.co/NousResearch/Hermes-3-Llama-3.1-8B) — Q4_K_M quantization (~5.5 GB, runs on CPU)

---

## Architecture

```
                        ┌──────────────────────────────────────┐
                        │              YOUR VPS                 │
                        │                                       │
  Browser / API  ──────▶│  Nginx (port 80)                     │
                        │   ├── /         → Open WebUI         │
                        │   └── /ollama/  → Ollama API         │
                        │                                       │
  Browser        ──────▶│  Nginx (port 3002) → AnythingLLM    │
                        │                                       │
  Telegram       ──────▶│  Telegram Bot                        │
                        │   ├── Local Hermes (Ollama)           │
                        │   └── Cloud models (OpenRouter)       │
                        │                                       │
                        │  Docker Compose                       │
                        │   ├── kbai-ollama        :11434      │
                        │   ├── kbai-open-webui    :3001       │
                        │   ├── kbai-anythingllm   :8081       │
                        │   └── kbai-telegram-bot             │
                        └──────────────────────────────────────┘
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
5. Pull and start all containers
6. Configure Nginx reverse proxy with Bearer token auth
7. Enable auto-start on boot via systemd
8. Download the Hermes-3-Llama-3.1-8B model (~5.5 GB)

**When finished, the script prints your URLs and API key — save them.**

---

## Telegram Bot

A private Telegram bot that connects to your AI stack. Features:

- **Multi-model routing** — switch between local Hermes and 8 cloud models with one tap
- **File-to-knowledge-base** — send any PDF, TXT, DOCX, MD, or CSV and it's automatically embedded into AnythingLLM
- **Conversation memory** — per-chat history with `/reset` to clear
- **Private mode** — locked to your Telegram chat ID only

### Supported Models

| Model | Provider | Cost |
|---|---|---|
| Hermes 8B | Local VPS | Free (already paid) |
| Gemini Flash 1.5 | OpenRouter | ~$0.0001/msg |
| DeepSeek V3 | OpenRouter | ~$0.0003/msg |
| Qwen 2.5 72B | OpenRouter | ~$0.0005/msg |
| Llama 3.3 70B | OpenRouter | ~$0.0003/msg |
| Claude Haiku 4.5 | OpenRouter | ~$0.001/msg |
| GPT-4o mini | OpenRouter | ~$0.001/msg |
| Nemotron 70B | OpenRouter | ~$0.001/msg |
| Mistral Large | OpenRouter | ~$0.002/msg |

### Bot Setup

1. Create a bot with [@BotFather](https://t.me/botfather) on Telegram — get a token
2. Get a free [OpenRouter](https://openrouter.ai) API key (optional, for cloud models)
3. Get an AnythingLLM API key: AnythingLLM → Settings → API Keys → Generate
4. Add to `/opt/kbai/.env` on your VPS:

```env
TELEGRAM_BOT_TOKEN=your-bot-token
OPENROUTER_API_KEY=your-openrouter-key
ANYTHINGLLM_API_KEY=your-anythingllm-key
```

5. Build and start:

```bash
cd /opt/kbai && docker compose up -d --build telegram-bot
```

6. Send `/start` to your bot — it will reply with your chat ID
7. Add `TELEGRAM_ALLOWED_CHAT_ID=<your-id>` to `.env` and restart to lock it down

### Bot Commands

| Command | Action |
|---|---|
| `/start` | Show status and setup info |
| `/model` | Open model switcher (inline tap buttons) |
| `/kb` | Show knowledge base status and document count |
| `/reset` | Clear conversation history |
| `/help` | Show help |
| Send a file | Upload PDF/TXT/DOCX/MD/CSV to knowledge base |

---

## Initial Setup

### Open WebUI (Chat with Hermes)

1. Open `http://your-ip/`
2. Create your admin account on first visit
3. The Hermes model is pre-loaded — start chatting

### AnythingLLM (RAG — Chat with your knowledge base)

1. Open `http://your-ip:3002/`
2. Create your admin account
3. LLM and embedding are pre-configured via environment variables — no manual setup needed
4. Create **Workspaces** for each domain (e.g. `Research`, `Notes`, `Projects`)
5. Upload your PDFs and Markdown notes, or send files via the Telegram bot
6. Chat with your documents — AnythingLLM retrieves relevant context using RAG

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

---

## Pulling Additional Models

```bash
docker exec kbai-ollama ollama pull mistral
docker exec kbai-ollama ollama pull llama3.2
docker exec kbai-ollama ollama list
```

---

## TLS / HTTPS

Requires a domain name (not just an IP) pointing to your VPS.

```bash
apt-get install -y certbot python3-certbot-nginx
certbot --nginx -d your-domain.com
```

---

## Service Management

```bash
# Status
docker ps

# Restart everything
systemctl restart kbai-hermes

# Logs
docker logs kbai-ollama
docker logs kbai-open-webui
docker logs kbai-anythingllm
docker logs kbai-telegram-bot

# Rebuild a single service
cd /opt/kbai && docker compose up -d --build --force-recreate telegram-bot
```

---

## File Structure

```
├── docker-compose.yml                   # All services
├── .env.example                         # Environment template (copy → .env)
├── nginx/
│   ├── kbai-hermes.conf.template        # Proxy: Open WebUI + Ollama API
│   └── kbai-anythingllm.conf.template   # Proxy: AnythingLLM on :3002
├── telegram-bot/
│   ├── bot.py                           # Telegram bot
│   ├── Dockerfile
│   └── requirements.txt
├── systemd/
│   └── kbai-hermes.service              # Auto-start on boot
└── scripts/
    ├── setup.sh                         # Main installer
    ├── install.sh                       # Bootstrap
    └── pull-model.sh                    # Pull Hermes into Ollama
```

---

## Troubleshooting

**apt-get gets killed (OOM) during install**
Add swap before running setup — the Q4_K_M model needs ~5.5 GB RAM and install tools need headroom.

**Open WebUI shows "Backend Required" error**
Nginx is routing `/api/` to Ollama instead of Open WebUI. The correct config routes `/ollama/` to Ollama. Check your nginx site config matches `nginx/kbai-hermes.conf.template`.

**AnythingLLM can't connect to Ollama**
Use `http://kbai-ollama:11434` as the base URL — not `localhost`. Services communicate over the Docker internal network.

**Telegram bot not responding**
Check it's running: `docker ps | grep telegram`. View logs: `docker logs kbai-telegram-bot --tail 30`.

**File upload to knowledge base fails**
Ensure `ANYTHINGLLM_API_KEY` is set in `.env` and at least one workspace exists in AnythingLLM. Check logs: `docker logs kbai-telegram-bot --tail 20`.

**Port 3002 not reachable**
Check UFW: `ufw status`. If active, run: `ufw allow 3002/tcp && ufw reload`.

**Model pull fails / runs out of disk**
Check disk space: `df -h`. Hermes needs ~6 GB, nomic-embed-text needs ~270 MB.
