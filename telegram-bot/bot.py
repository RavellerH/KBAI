import os, logging, httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN               = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_ID          = os.getenv("TELEGRAM_ALLOWED_CHAT_ID", "").strip()
OLLAMA_URL          = os.getenv("OLLAMA_BASE_URL", "http://kbai-ollama:11434")
LOCAL_MODEL         = os.getenv("OLLAMA_MODEL", "hf.co/NousResearch/Hermes-3-Llama-3.1-8B-GGUF:Q4_K_M")
OPENROUTER_API_KEY  = os.getenv("OPENROUTER_API_KEY", "")
ANYTHINGLLM_URL     = os.getenv("ANYTHINGLLM_URL", "http://kbai-anythingllm:3001")
ANYTHINGLLM_API_KEY = os.getenv("ANYTHINGLLM_API_KEY", "")
SYSTEM              = os.getenv("SYSTEM_PROMPT", (
    "You are a knowledgeable and direct AI assistant. "
    "Answer concisely. Use markdown formatting when helpful."
))

CLOUD_MODELS: dict[str, tuple[str, str]] = {
    "gemini":   ("google/gemini-flash-1.5",                "Gemini Flash 1.5"),
    "deepseek": ("deepseek/deepseek-chat",                 "DeepSeek V3"),
    "qwen":     ("qwen/qwen-2.5-72b-instruct",             "Qwen 2.5 72B"),
    "llama":    ("meta-llama/llama-3.3-70b-instruct",      "Llama 3.3 70B"),
    "claude":   ("anthropic/claude-haiku-4-5",             "Claude Haiku 4.5"),
    "gpt4o":    ("openai/gpt-4o-mini",                     "GPT-4o mini"),
    "nemotron": ("nvidia/llama-3.1-nemotron-70b-instruct", "Nemotron 70B"),
    "mistral":  ("mistralai/mistral-large",                "Mistral Large"),
}

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx", ".csv", ".json"}

histories:    dict[int, list[dict]] = {}
active_model: dict[int, str]        = {}

def allowed(chat_id: int) -> bool:
    return not ALLOWED_ID or str(chat_id) == ALLOWED_ID

def model_keyboard(current: str) -> InlineKeyboardMarkup:
    def btn(key: str, label: str) -> InlineKeyboardButton:
        text = f"✅ {label}" if key == current else label
        return InlineKeyboardButton(text, callback_data=f"model:{key}")

    return InlineKeyboardMarkup([
        [btn("gemini",   "Gemini Flash"),  btn("deepseek", "DeepSeek V3")],
        [btn("qwen",     "Qwen 2.5 72B"),  btn("llama",    "Llama 3.3 70B")],
        [btn("claude",   "Claude Haiku"),  btn("gpt4o",    "GPT-4o mini")],
        [btn("nemotron", "Nemotron 70B"),  btn("mistral",  "Mistral Large")],
        [btn("local",    "🏠 Local Hermes (private, slow)")],
    ])

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    logger.info(f"/start from chat_id={chat_id}")

    if not ALLOWED_ID:
        await update.message.reply_text(
            f"⚙️ *Setup mode — bot is open*\n\n"
            f"Your Telegram chat ID is:\n`{chat_id}`\n\n"
            f"To restrict the bot to only you, add this to `/opt/kbai/.env`:\n"
            f"`TELEGRAM_ALLOWED_CHAT_ID={chat_id}`\n\n"
            f"Then restart: `docker compose up -d --force-recreate telegram-bot`",
            parse_mode="Markdown"
        )
    elif not allowed(chat_id):
        await update.message.reply_text("⛔ Access denied.")
        return

    histories[chat_id] = []
    active_model[chat_id] = "local"
    cloud_status = "✅ Cloud models available" if OPENROUTER_API_KEY else "❌ No OpenRouter key — local only"
    kb_status    = "✅ Knowledge base connected" if ANYTHINGLLM_API_KEY else "❌ No AnythingLLM key — file upload disabled"

    await update.message.reply_text(
        "🤖 *Hermes is ready.*\n\n"
        f"Model: `local` (Hermes on VPS)\n"
        f"{cloud_status}\n"
        f"{kb_status}\n\n"
        "Send me anything to chat, or send a file to add it to your knowledge base.\n\n"
        "/model — Switch AI model\n"
        "/kb — Knowledge base status\n"
        "/reset — Clear conversation history\n"
        "/help — Show this message",
        parse_mode="Markdown"
    )

async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not allowed(chat_id):
        return
    histories[chat_id] = []
    await update.message.reply_text("🔄 Conversation cleared.")

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, ctx)

async def cmd_model(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not allowed(chat_id):
        return

    if not OPENROUTER_API_KEY:
        await update.message.reply_text(
            "⚠️ No OpenRouter key configured. Only local Hermes available.\n\n"
            "Add OPENROUTER_API_KEY to /opt/kbai/.env and restart the bot."
        )
        return

    current = active_model.get(chat_id, "local")
    await update.message.reply_text(
        "Choose a model — tap to switch:\n_(✅ = currently active)_",
        parse_mode="Markdown",
        reply_markup=model_keyboard(current)
    )

async def cmd_kb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not allowed(chat_id):
        return

    if not ANYTHINGLLM_API_KEY:
        await update.message.reply_text(
            "⚠️ Knowledge base not configured.\n\n"
            "1. Go to AnythingLLM → Settings → API Keys → Generate\n"
            "2. Add to your VPS:\n"
            "`echo 'ANYTHINGLLM_API_KEY=<key>' >> /opt/kbai/.env`\n"
            "3. Restart: `docker compose up -d --force-recreate telegram-bot`",
            parse_mode="Markdown"
        )
        return

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            headers = {"Authorization": f"Bearer {ANYTHINGLLM_API_KEY}"}
            ws_resp = await client.get(f"{ANYTHINGLLM_URL}/api/v1/workspaces", headers=headers)
            ws_resp.raise_for_status()
            workspaces = ws_resp.json().get("workspaces", [])

        if not workspaces:
            await update.message.reply_text(
                "📚 Knowledge base connected but no workspaces found.\n\n"
                "Create a workspace in AnythingLLM first, then send files here."
            )
            return

        lines = ["📚 *Knowledge Base*\n"]
        for ws in workspaces:
            doc_count = len(ws.get("documents", []))
            lines.append(f"• *{ws['name']}* — {doc_count} document(s)")
        lines.append("\nSend any PDF, TXT, DOCX, MD, or CSV file to add it.")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    except Exception as e:
        logger.error(f"KB status error: {e}")
        await update.message.reply_text(f"⚠️ Could not reach AnythingLLM: {e}")

async def callback_model(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    if not allowed(chat_id):
        return

    model_key = query.data.split(":")[1]
    active_model[chat_id] = model_key
    histories[chat_id] = []

    name = "Local Hermes (private)" if model_key == "local" else CLOUD_MODELS[model_key][1]

    await query.edit_message_text(
        f"✅ Switched to *{name}*. Conversation cleared.\n\n"
        "_(tap /model to change again)_",
        parse_mode="Markdown",
        reply_markup=model_keyboard(model_key)
    )

async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not allowed(chat_id):
        return

    if not ANYTHINGLLM_API_KEY:
        await update.message.reply_text(
            "⚠️ Knowledge base not configured. See /kb for setup instructions."
        )
        return

    doc = update.message.document
    file_name = doc.file_name or "document"
    ext = os.path.splitext(file_name)[1].lower()

    if ext not in SUPPORTED_EXTENSIONS:
        await update.message.reply_text(
            f"⚠️ Unsupported file type `{ext}`.\n"
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
            parse_mode="Markdown"
        )
        return

    msg = await update.message.reply_text(f"📥 Uploading *{file_name}* to knowledge base...", parse_mode="Markdown")

    try:
        tg_file   = await ctx.bot.get_file(doc.file_id)
        file_bytes = await tg_file.download_as_bytearray()

        async with httpx.AsyncClient(timeout=120.0) as client:
            headers = {"Authorization": f"Bearer {ANYTHINGLLM_API_KEY}"}

            upload_resp = await client.post(
                f"{ANYTHINGLLM_URL}/api/v1/document/upload",
                headers=headers,
                files={"file": (file_name, bytes(file_bytes), "application/octet-stream")}
            )
            upload_resp.raise_for_status()
            upload_data = upload_resp.json()

            if not upload_data.get("success"):
                raise Exception(upload_data.get("error", "Upload failed"))

            doc_location = upload_data["documents"][0]["location"]

            ws_resp = await client.get(f"{ANYTHINGLLM_URL}/api/v1/workspaces", headers=headers)
            ws_resp.raise_for_status()
            workspaces = ws_resp.json().get("workspaces", [])

            if not workspaces:
                await msg.edit_text(
                    f"✅ *{file_name}* uploaded.\n\n"
                    "⚠️ No workspace found — create one in AnythingLLM to start querying it.",
                    parse_mode="Markdown"
                )
                return

            slug    = workspaces[0]["slug"]
            ws_name = workspaces[0]["name"]

            embed_resp = await client.post(
                f"{ANYTHINGLLM_URL}/api/v1/workspace/{slug}/update-embeddings",
                headers=headers,
                json={"adds": [doc_location], "deletes": []}
            )
            embed_resp.raise_for_status()

        await msg.edit_text(
            f"✅ *{file_name}* added to knowledge base\n"
            f"Workspace: _{ws_name}_\n\n"
            "You can now query it in AnythingLLM.",
            parse_mode="Markdown"
        )
        logger.info(f"KB upload: {file_name} → {ws_name} ({slug})")

    except Exception as e:
        logger.error(f"KB upload error: {e}")
        await msg.edit_text(f"⚠️ Upload failed: {e}")

async def call_ollama(messages: list[dict]) -> str:
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": LOCAL_MODEL, "messages": messages, "stream": False}
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

async def call_openrouter(messages: list[dict], model: str) -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://github.com/ravellerh/kbai",
                "X-Title": "KBAI Hermes Bot",
            },
            json={"model": model, "messages": messages}
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not allowed(chat_id):
        await update.message.reply_text("⛔ Access denied.")
        return

    user_text = update.message.text
    if chat_id not in histories:
        histories[chat_id] = []

    histories[chat_id].append({"role": "user", "content": user_text})
    await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")

    model_key = active_model.get(chat_id, "local")
    messages  = [{"role": "system", "content": SYSTEM}] + histories[chat_id]

    try:
        if model_key == "local":
            reply = await call_ollama(messages)
        else:
            reply = await call_openrouter(messages, CLOUD_MODELS[model_key][0])
    except httpx.TimeoutException:
        reply = "⚠️ Request timed out. Try again or switch model with /model."
    except Exception as e:
        logger.error(f"LLM error ({model_key}): {e}")
        reply = f"⚠️ Error: {e}"

    histories[chat_id].append({"role": "assistant", "content": reply})

    for chunk in [reply[i:i+4096] for i in range(0, len(reply), 4096)]:
        await update.message.reply_text(chunk)

def main():
    logger.info(f"Starting Hermes Telegram bot (local: {LOCAL_MODEL})")
    logger.info(f"OpenRouter: {'configured' if OPENROUTER_API_KEY else 'not configured'}")
    logger.info(f"AnythingLLM KB: {'configured' if ANYTHINGLLM_API_KEY else 'not configured'}")
    logger.info(f"Access: {'chat_id=' + ALLOWED_ID if ALLOWED_ID else 'OPEN'}")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CommandHandler("kb",    cmd_kb))
    app.add_handler(CallbackQueryHandler(callback_model, pattern="^model:"))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
