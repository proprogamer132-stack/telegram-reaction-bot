import re
import logging

import regex as re_lib

from telegram import Update, ReactionTypeEmoji
from telegram.ext import Application, MessageHandler, filters, ContextTypes

from config import BOT_TOKEN, DEFAULT_REACTION, MAX_REACTIONS

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

pending_reactions: dict[int, tuple[int | str, int]] = {}


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


async def auto_react(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not update.effective_chat:
        return

    if msg.from_user and msg.from_user.is_bot:
        return

    try:
        await context.bot.set_message_reaction(
            chat_id=update.effective_chat.id,
            message_id=msg.message_id,
            reaction=[ReactionTypeEmoji(DEFAULT_REACTION)],
        )
    except Exception as e:
        logger.warning("Auto-react failed in %s: %s", update.effective_chat.id, e)


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    user_id = update.effective_user.id

    link_data = parse_message_link(text)
    if link_data:
        chat_id, msg_id = link_data
        pending_reactions[user_id] = (chat_id, msg_id)
        await update.message.reply_text(
            f"Reply with emoji(s) to add as reactions (up to {MAX_REACTIONS})."
        )
    else:
        await update.message.reply_text(
            "Send a Telegram message link like:\n"
            "https://t.me/username/1234\n"
            "or https://t.me/c/1234567890/1234"
        )


async def handle_reaction_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.reply_to_message or not update.message.text:
        return

    user_id = update.effective_user.id
    if user_id not in pending_reactions:
        return

    bot_msg = update.message.reply_to_message
    if not bot_msg.from_user or not bot_msg.from_user.is_bot:
        return

    chat_id, msg_id = pending_reactions[user_id]
    emojis = split_emojis(update.message.text)

    if not emojis:
        await update.message.reply_text("No valid emojis found.")
        return

    reactions = [ReactionTypeEmoji(e) for e in emojis]

    try:
        await context.bot.set_message_reaction(
            chat_id=chat_id,
            message_id=msg_id,
            reaction=reactions,
        )
        await update.message.reply_text(f"Reaction added: {' '.join(emojis)}")
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")
        logger.error("Reaction error: %s", e)
    finally:
        del pending_reactions[user_id]


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(
        (filters.ChatType.GROUPS
         | filters.ChatType.SUPERGROUP
         | filters.ChatType.CHANNEL)
        & ~filters.COMMAND,
        auto_react,
    ))

    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.TEXT & ~filters.REPLY,
        handle_link,
    ))

    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.TEXT & filters.REPLY,
        handle_reaction_reply,
    ))

    logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
