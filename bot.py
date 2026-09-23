import logging
from pathlib import Path

from telegram import Update
from telegram.error import Conflict
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import settings
from database import db
from handlers import (
    PREVIEW,
    WAITING_EMAILS,
    WAITING_MANAGER_ID,
    WAITING_MESSAGE,
    cancel_command,
    handle_callback_query,
    handle_manager_callback,
    handle_manager_id,
    handle_message_text,
    history_command,
    help_command,
    notify_command,
    managers_command,
    start_command,
    status_command,
)
from parser import extract_email_from_chat

Path(settings.log_path).parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(settings.log_path, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


async def handle_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None:
        return

    chat_info = await context.bot.get_chat(chat.id)
    title = chat_info.title or chat.title or ""
    email = extract_email_from_chat(title, chat_info.description or "")
    if not email:
        return

    db.upsert_partner_chat(email, chat.id, title, 1)
    logger.info("Registered chat %s for email %s", chat.id, email)


async def handle_chat_title_change(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None:
        return

    chat_info = await context.bot.get_chat(chat.id)
    title = chat_info.title or chat.title or ""
    email = extract_email_from_chat(title, chat_info.description or "")
    if not email:
        return

    db.upsert_partner_chat(email, chat.id, title, 1)
    logger.info("Registered or updated chat %s for email %s", chat.id, email)


async def register_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    message = update.effective_message
    if user is None or chat is None or message is None:
        return

    if user.id not in settings.manager_ids:
        await message.reply_text("У вас нет доступа к регистрации чатов.")
        return

    chat_info = await context.bot.get_chat(chat.id)
    title = chat_info.title or chat.title or ""
    email = extract_email_from_chat(title, chat_info.description or "")
    if not email:
        await message.reply_text(
            "Не найден email в названии или описании чата. "
            "Укажите его, например: partner@example.com"
        )
        return

    db.upsert_partner_chat(email, chat.id, title, 1)
    logger.info("Registered chat %s manually for email %s", chat.id, email)
    await message.reply_text(f"Чат зарегистрирован для {email}.")


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(context.error, Conflict):
        logger.error("Polling conflict: another bot process is using this token.")
        return

    logger.error("Unhandled Telegram update error", exc_info=context.error)


def build_application() -> Application:
    application = Application.builder().token(settings.bot_token).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("notify", notify_command),
            MessageHandler(filters.Regex(r"^Рассылка$"), notify_command),
        ],
        states={
            WAITING_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message_text)],
            WAITING_EMAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message_text)],
            PREVIEW: [
                CallbackQueryHandler(handle_callback_query, pattern=r"^(confirm_send|cancel_send)$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
    )
    manager_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_manager_callback, pattern=r"^(manager_add|manager_remove:-?\d+)$")],
        states={
            WAITING_MANAGER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_manager_id)],
        },
        fallbacks=[],
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("managers", managers_command))
    application.add_handler(MessageHandler(filters.Regex(r"^Чаты$"), status_command))
    application.add_handler(MessageHandler(filters.Regex(r"^История$"), history_command))
    application.add_handler(MessageHandler(filters.Regex(r"^Помощь$"), help_command))
    application.add_handler(MessageHandler(filters.Regex(r"^Менеджеры$"), managers_command))
    application.add_handler(CommandHandler("register", register_chat_command))
    application.add_handler(conv)
    application.add_handler(manager_conv)
    application.add_handler(ChatMemberHandler(handle_chat_member, chat_member_types=ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_TITLE, handle_chat_title_change))
    application.add_error_handler(handle_error)
    return application


def main() -> None:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is missing. Set it in .env")

    logger.info("Bot started")
    application = build_application()
    logger.info("Bot is running")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
