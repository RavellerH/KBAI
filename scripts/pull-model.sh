#!/usr/bin/env bash
set -euo pipefail

# Q4_K_M: ~5.5 GB download, ~6 GB RAM at runtime — good balance for CPU-only VPS
MODEL="hf.co/NousResearch/Hermes-3-Llama-3.1-8B-GGUF:Q4_K_M"

echo "[kbai] Pulling ${MODEL} into Ollama..."
echo "[kbai] This may take several minutes depending on your VPS bandwidth."
docker exec kbai-ollama ollama pull "$MODEL"
echo "[kbai] Model ready. Verify with: docker exec kbai-ollama ollama list"
