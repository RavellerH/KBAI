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

TOKEN              = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_ID         = os.getenv("TELEGRAM_ALLOWED_CHAT_ID", "").strip()
OLLAMA_URL         = os.getenv("OLLAMA_BASE_URL", "http://kbai-ollama:11434")
LOCAL_MODEL        = os.getenv("OLLAMA_MODEL", "hf.co/NousResearch/Hermes-3-Llama-3.1-8B-GGUF:Q4_K_M")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
SYSTEM             = os.getenv("SYSTEM_PROMPT", (
    "You are a knowledgeable and direct AI assistant. "
    "Answer concisely. Use markdown formatting when helpful."
))

# (openrouter_model_id, display_name, est_cost)
CLOUD_MODELS: dict[str, tuple[str, str, str]] = {
    "gemini":    ("google/gemini-flash-1.5",                 "Gemini Flash 1.5",   "~$0.0001/msg"),
    "deepseek":  ("deepseek/deepseek-chat",                  "DeepSeek V3",        "~$0.0003/msg"),
    "qwen":      ("qwen/qwen-2.5-72b-instruct",              "Qwen 2.5 72B",       "~$0.0005/msg"),
    "claude":    ("anthropic/claude-haiku-4-5",              "Claude Haiku 4.5",   "~$0.001/msg"),
    "gpt4o":     ("openai/gpt-4o-mini",                      "GPT-4o mini",        "~$0.001/msg"),
    "nemotron":  ("nvidia/llama-3.1-nemotron-70b-instruct",  "Nemotron 70B",       "~$0.001/msg"),
    "llama":     ("meta-llama/llama-3.3-70b-instruct",       "Llama 3.3 70B",      "~$0.0003/msg"),
    "mistral":   ("mistralai/mistral-large",                 "Mistral Large",      "~$0.002/msg"),
}

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

    await update.message.reply_text(
        "🤖 *Hermes is ready.*\n\n"
        f"Current model: `local` (Hermes on VPS)\n"
        f"{cloud_status}\n\n"
        "Send me anything to chat.\n\n"
        "/model — Switch AI model\n"
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

async def callback_model(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    if not allowed(chat_id):
        return

    model_key = query.data.split(":")[1]
    active_model[chat_id] = model_key
    histories[chat_id] = []

    if model_key == "local":
        name = "Local Hermes (private)"
    else:
        name = CLOUD_MODELS[model_key][1]

    await query.edit_message_text(
        f"✅ Switched to *{name}*. Conversation cleared.\n\n"
        "_(tap /model to change again)_",
        parse_mode="Markdown",
        reply_markup=model_keyboard(model_key)
    )

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
    logger.info(f"Access: {'chat_id=' + ALLOWED_ID if ALLOWED_ID else 'OPEN'}")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CallbackQueryHandler(callback_model, pattern="^model:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
