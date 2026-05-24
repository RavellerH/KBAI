import os, logging, httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN       = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_ID  = os.getenv("TELEGRAM_ALLOWED_CHAT_ID", "").strip()
OLLAMA_URL  = os.getenv("OLLAMA_BASE_URL", "http://kbai-ollama:11434")
MODEL       = os.getenv("OLLAMA_MODEL", "hf.co/NousResearch/Hermes-3-Llama-3.1-8B-GGUF:Q4_K_M")
SYSTEM      = os.getenv("SYSTEM_PROMPT", (
    "You are Hermes, a knowledgeable and direct AI assistant. "
    "Answer concisely. Use markdown formatting when helpful."
))

histories: dict[int, list[dict]] = {}

def allowed(chat_id: int) -> bool:
    return not ALLOWED_ID or str(chat_id) == ALLOWED_ID

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
    await update.message.reply_text(
        "🤖 *Hermes is ready.*\n\n"
        "Send me anything — I'll respond using the Hermes-3-Llama-3.1-8B model "
        "running on your VPS.\n\n"
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

    messages = [{"role": "system", "content": SYSTEM}] + histories[chat_id]

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={"model": MODEL, "messages": messages, "stream": False}
            )
            resp.raise_for_status()
            reply = resp.json()["message"]["content"]
    except httpx.TimeoutException:
        reply = "⚠️ Hermes is taking too long to respond. The model may be busy — try again."
    except Exception as e:
        logger.error(f"Ollama error: {e}")
        reply = f"⚠️ Error connecting to Hermes: {e}"

    histories[chat_id].append({"role": "assistant", "content": reply})

    for chunk in [reply[i:i+4096] for i in range(0, len(reply), 4096)]:
        await update.message.reply_text(chunk)

def main():
    logger.info(f"Starting Hermes Telegram bot (model: {MODEL})")
    logger.info(f"Access: {'chat_id=' + ALLOWED_ID if ALLOWED_ID else 'OPEN'}")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
