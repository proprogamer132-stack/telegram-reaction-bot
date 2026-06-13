import re
import logging

import httpx
import regex as re_lib

from telegram import Update, ReactionTypeEmoji
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

from config import (
    BOT_TOKEN, DEFAULT_REACTION, MAX_REACTIONS,
    WEBHOOK, PORT, RENDER_URL,
    OWNER_ID, OWNER_USERNAME, BOT_PASSWORD, BIG_REACTION,
    GEMINI_API_KEY,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

pending_reactions: dict[int, tuple[int | str, int]] = {}
authorized_users: set[int] = set()

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1/models/{GEMINI_MODEL}:generateContent"


def parse_message_link(text: str):
    match = re.search(r"t\.me/(?:c/)?([^/\s?]+)/(\d+)", text)
    if not match:
        return None

    chat_part = match.group(1)
    msg_id = int(match.group(2))
    is_private = "/c/" in match.group(0)

    if is_private:
        try:
            chat_id = int(f"-100{chat_part}")
        except ValueError:
            return None
    else:
        chat_id = chat_part

    return chat_id, msg_id


def split_emojis(text: str):
    text = text.strip()
    if not text:
        return []

    parts = text.split()
    if len(parts) > 1:
        return parts[:MAX_REACTIONS]

    clusters = re_lib.findall(r"\X", text)
    result = [c.strip() for c in clusters if c.strip()]
    return result[:MAX_REACTIONS]


async def get_ai_emojis(text: str) -> list[str]:
    prompt = (
        "What 1-3 Telegram reaction emojis best fit this message?\n"
        "Reply with ONLY the emojis separated by spaces, nothing else.\n"
        "Message: " + text[:500]
    )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
            )
            data = resp.json()
            result = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            parts = result.split()
            if len(parts) > 1:
                return parts[:MAX_REACTIONS]
            clusters = re_lib.findall(r"\X", result)
            emojis = [c.strip() for c in clusters if c.strip()]
            return emojis[:MAX_REACTIONS] if emojis else [DEFAULT_REACTION]
    except Exception as e:
        logger.warning("AI error: %s", e)
        return [DEFAULT_REACTION]


async def auto_react(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not update.effective_chat:
        return
    if msg.from_user and msg.from_user.is_bot:
        return
    if not msg.text:
        return

    emojis = [DEFAULT_REACTION]
    if GEMINI_API_KEY and msg.text:
        emojis = await get_ai_emojis(msg.text)

    try:
        await context.bot.set_message_reaction(
            chat_id=update.effective_chat.id,
            message_id=msg.message_id,
            reaction=[ReactionTypeEmoji(e) for e in emojis],
            is_big=BIG_REACTION,
        )
    except Exception as e:
        logger.warning("Auto-react failed in %s: %s", update.effective_chat.id, e)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user_id = update.effective_user.id
    if user_id == OWNER_ID:
        await update.message.reply_text(
            "Welcome back! Fully automated mode active.\n"
            "Send a message link and I'll react automatically with AI."
        )
    elif user_id in authorized_users:
        await update.message.reply_text(
            "Welcome! Send a message link for AI-powered reactions."
        )
    else:
        await update.message.reply_text(
            f"Sorry, you are not Atheer to use me.\n"
            f"If you want to use me, contact @{OWNER_USERNAME} and get the password."
        )


async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    uid = update.effective_user.id
    await update.message.reply_text(f"Your Telegram ID: `{uid}`")


async def auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not context.args:
        await update.message.reply_text("Usage: /auth PASSWORD")
        return
    user_id = update.effective_user.id
    if user_id == OWNER_ID:
        await update.message.reply_text("You are the owner, already authorized.")
        return
    if user_id in authorized_users:
        await update.message.reply_text("Already authorized!")
        return
    if context.args[0] == BOT_PASSWORD:
        authorized_users.add(user_id)
        await update.message.reply_text(
            "Correct! You can now use the bot.\n"
            "Send a message link for AI-powered reactions."
        )
    else:
        await update.message.reply_text(f"Wrong password. Contact @{OWNER_USERNAME}.")


async def handle_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    text = update.message.text.strip()

    logger.info("Private msg from %s: %s", user_id, text[:80])

    if user_id != OWNER_ID and user_id not in authorized_users:
        await update.message.reply_text(
            f"Sorry, you are not Atheer to use me.\n"
            f"If you want to use me, contact @{OWNER_USERNAME} and get the password."
        )
        return

    link_data = parse_message_link(text)
    if not link_data:
        await update.message.reply_text(
            "Send a Telegram message link like:\n"
            "https://t.me/username/1234\n"
            "or https://t.me/c/1234567890/1234"
        )
        return

    chat_id, msg_id = link_data
    await update.message.reply_text("Analyzing message with AI...")

    message_text = None
    try:
        copied = await context.bot.copy_message(
            chat_id=update.effective_chat.id,
            from_chat_id=chat_id,
            message_id=msg_id,
        )
        message_text = copied.text or copied.caption or ""
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=copied.message_id,
        )
    except Exception:
        pass

    emojis = [DEFAULT_REACTION]
    if message_text and GEMINI_API_KEY:
        emojis = await get_ai_emojis(message_text)

    try:
        await context.bot.set_message_reaction(
            chat_id=chat_id,
            message_id=msg_id,
            reaction=[ReactionTypeEmoji(e) for e in emojis],
            is_big=BIG_REACTION,
        )
        await update.message.reply_text(f"Reacted with: {' '.join(emojis)}")
    except Exception as e:
        msg = str(e)
        if "chat not found" in msg.lower():
            hint = "Bot is not in that chat. Add @AAAATHEErBOT as admin to the channel or add it to the group."
        else:
            hint = msg
        await update.message.reply_text(f"Failed: {hint}")
        logger.error("Reaction error: %s", e)


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", show_id))
    app.add_handler(CommandHandler("auth", auth))

    app.add_handler(MessageHandler(
        (filters.ChatType.GROUPS
         | filters.ChatType.SUPERGROUP
         | filters.ChatType.CHANNEL)
        & ~filters.COMMAND,
        auto_react,
    ))

    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.TEXT,
        handle_private,
    ))

    logger.info("Bot started with AI mode: %s", bool(GEMINI_API_KEY))

    if WEBHOOK and RENDER_URL:
        webhook_url = f"{RENDER_URL}/{BOT_TOKEN}"
        logger.info("Webhook mode: %s", webhook_url)
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=webhook_url,
            allowed_updates=Update.ALL_TYPES,
        )
    else:
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
