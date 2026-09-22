import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from broadcaster import ControlledBroadcaster
from config import settings
from database import db
from keyboards import confirmation_keyboard, main_menu, manager_keyboard
from parser import normalize_email_list

logger = logging.getLogger(__name__)

WAITING_MESSAGE = 1
WAITING_EMAILS = 2
PREVIEW = 3
WAITING_MANAGER_ID = 4


@dataclass
class DraftNotification:
    message_text: str = ""
    recipients: list[str] = field(default_factory=list)
    found: list[dict[str, Any]] = field(default_factory=list)
    not_found: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    pending: list[tuple[str, int]] = field(default_factory=list)


class NotificationStateManager:
    def __init__(self):
        self.sessions: dict[int, DraftNotification] = {}

    def start(self, manager_id: int) -> DraftNotification:
        session = DraftNotification()
        self.sessions[manager_id] = session
        return session

    def get(self, manager_id: int):
        return self.sessions.get(manager_id)

    def clear(self, manager_id: int) -> None:
        self.sessions.pop(manager_id, None)


state_manager = NotificationStateManager()


def is_manager(user_id: int) -> bool:
    return user_id in settings.manager_ids or db.is_manager(user_id)


def is_owner(user_id: int) -> bool:
    return user_id in settings.manager_ids


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return

    if not is_manager(user.id):
        await update.message.reply_text("У вас нет доступа к этому боту.")
        return

    await update.message.reply_text(
        "Панель управления рассылками.",
        reply_markup=main_menu(is_owner(user.id)),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_manager(update.effective_user.id):
        await update.message.reply_text("У вас нет доступа к этому боту.")
        return

    await update.message.reply_text(
        "Для рассылки выберите «Рассылка», затем отправьте текст и email получателей.\n\n"
        "Чаты регистрируются по email в названии, например:\n"
        "Partner | partner@example.com",
    )


async def managers_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or not is_owner(user.id):
        await update.message.reply_text("Управлять доступом может только владелец бота.")
        return

    manager_ids = [row["user_id"] for row in db.get_managers()]
    text = "Дополнительные менеджеры:\n" + ("\n".join(str(user_id) for user_id in manager_ids) if manager_ids else "—")
    await update.message.reply_text(text, reply_markup=manager_keyboard(manager_ids))


async def handle_manager_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return ConversationHandler.END

    await query.answer()
    if not is_owner(user.id):
        await query.answer("Недостаточно прав.", show_alert=True)
        return ConversationHandler.END

    if query.data == "manager_add":
        await query.edit_message_text("Отправьте числовой Telegram ID нового менеджера.")
        return WAITING_MANAGER_ID

    if query.data and query.data.startswith("manager_remove:"):
        manager_id = int(query.data.split(":", 1)[1])
        db.remove_manager(manager_id)
        manager_ids = [row["user_id"] for row in db.get_managers()]
        text = "Дополнительные менеджеры:\n" + ("\n".join(str(user_id) for user_id in manager_ids) if manager_ids else "—")
        await query.edit_message_text(text, reply_markup=manager_keyboard(manager_ids))
    return ConversationHandler.END


async def handle_manager_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if user is None or not is_owner(user.id):
        return ConversationHandler.END

    try:
        manager_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Нужен числовой Telegram ID. Попробуйте ещё раз.")
        return WAITING_MANAGER_ID

    if is_owner(manager_id):
        await update.message.reply_text("Этот пользователь уже является владельцем бота.")
        return ConversationHandler.END

    db.add_manager(manager_id, user.id)
    await update.message.reply_text("Доступ выдан. Новый менеджер должен отправить боту /start.")
    return ConversationHandler.END


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_manager(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет доступа к этому боту.")
        return

    stats = db.get_statistics()
    last_updated = stats["last_updated"] or "—"
    await update.message.reply_text(
        f"Чаты\n\n"
        f"Зарегистрировано чатов: {stats['total']}\n"
        f"Активных чатов: {stats['active']}\n"
        f"Неактивных: {stats['inactive']}\n\n"
        f"Последнее обновление: {last_updated}",
    )


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or not is_manager(user.id):
        await update.message.reply_text("У вас нет доступа к этому боту.")
        return

    notifications = db.get_recent_notifications()
    if not notifications:
        await update.message.reply_text("История уведомлений пока пуста.")
        return

    entries: list[str] = []
    for notification in notifications:
        message_text = " ".join(notification["message_text"].split())
        if len(message_text) > 180:
            message_text = message_text[:177] + "..."
        entries.append(
            f"#{notification['id']} | {notification['created_at']}\n"
            f"{message_text}\n"
            f"Получателей: {notification['total_recipients']} | "
            f"Отправлено: {notification['sent_count']} | "
            f"Ошибок: {notification['failed_count']}\n"
            f"Менеджер: {notification['manager_id']}"
        )

    await update.message.reply_text("Последние уведомления:\n\n" + "\n\n".join(entries))


async def notify_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_manager(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет доступа к этому боту.")
        return ConversationHandler.END

    context.user_data.clear()
    state_manager.start(update.effective_user.id)
    context.user_data["stage"] = "WAITING_MESSAGE"
    await update.message.reply_text(
        "📝 О чем уведомляем?\n\n"
        "Отправьте готовый текст сообщения, который необходимо отправить партнерам.",
    )
    return WAITING_MESSAGE


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    manager_id = update.effective_user.id
    context.user_data.clear()
    state_manager.clear(manager_id)
    await update.message.reply_text("❌ Процесс отменён.\n\nТекущая сессия рассылки очищена.")
    return ConversationHandler.END


async def handle_message_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    manager_id = update.effective_user.id
    session = state_manager.get(manager_id)
    if session is None:
        return ConversationHandler.END

    stage = context.user_data.get("stage")

    if stage == "WAITING_MESSAGE":
        session.message_text = update.message.text
        context.user_data["stage"] = "WAITING_EMAILS"
        await update.message.reply_text(
            "✅ Сообщение получено.\n\n"
            "Теперь отправьте список email партнеров.\n\n"
            "Можно указать каждый email с новой строки.",
        )
        return WAITING_EMAILS

    if stage == "WAITING_EMAILS":
        recipients = normalize_email_list(update.message.text)
        session.recipients = recipients
        found: list[dict[str, Any]] = []
        not_found: list[str] = []
        conflicts: list[str] = []
        pending: list[tuple[str, int]] = []

        for email in recipients:
            rows = db.get_active_chats_for_email(email)
            if not rows:
                not_found.append(email)
                continue
            if len(rows) > 1:
                conflicts.append(email)
                logger.warning("Conflict detected for email=%s: %s chats", email, len(rows))
                continue
            row = rows[0]
            found.append({"email": email, "chat_id": int(row["chat_id"])})
            pending.append((email, int(row["chat_id"])))

        session.found = found
        session.not_found = not_found
        session.conflicts = conflicts
        session.pending = pending
        context.user_data["stage"] = "PREVIEW"

        preview_text = (
            "📨 ПРЕДПРОСМОТР РАССЫЛКИ\n\n"
            "Сообщение:\n\n"
            f"{session.message_text}\n\n"
            "────────────────\n\n"
            f"Получателей в списке: {len(recipients)}\n"
            f"Найдено Telegram-чатов: {len(found)}\n"
            f"Не найдено: {len(not_found)}\n"
            + (f"⚠️ Конфликтов: {len(conflicts)}\n" if conflicts else "")
            + "\n"
            + "Найденные:\n"
            + ("\n".join(f"✅ {item['email']}" for item in found) if found else "—")
            + "\n\nНе найдены:\n"
            + ("\n".join(f"❌ {email}" for email in not_found) if not_found else "—")
            + ("\n\nКонфликты:\n" + "\n".join(f"⚠️ {email}" for email in conflicts) if conflicts else "")
            + "\n\nОтправить сообщение "
            + str(len(found))
            + " партнерам?"
        )
        await update.message.reply_text(preview_text, reply_markup=confirmation_keyboard())
        return PREVIEW

    return ConversationHandler.END


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None:
        return ConversationHandler.END

    await query.answer()
    manager_id = update.effective_user.id
    session = state_manager.get(manager_id)

    if query.data == "cancel_send":
        context.user_data.clear()
        state_manager.clear(manager_id)
        await query.edit_message_text("❌ Рассылка отменена.\n\nСообщение не отправлялось.")
        return ConversationHandler.END

    if query.data == "confirm_send":
        if not session:
            await query.edit_message_text("❌ Сессия рассылки не найдена.")
            return ConversationHandler.END

        context.user_data["stage"] = "SENDING"
        await query.edit_message_text("⏳ Начинаю отправку...\n\nОтправлено: 0/" + str(len(session.pending)))
        return await perform_broadcast(update, context, session)

    return ConversationHandler.END


async def perform_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, session: DraftNotification) -> int:
    broadcaster = ControlledBroadcaster(context.bot)
    sent_count = 0
    failed_emails: list[str] = []
    successful_emails: list[str] = []
    notification_id = db.save_notification(update.effective_user.id, session.message_text)
    recipient_rows: list[dict[str, Any]] = []

    for email, chat_id in session.pending:
        ok, error = await broadcaster.send_with_retry(chat_id, session.message_text)
        if ok:
            sent_count += 1
            successful_emails.append(email)
            status = "sent"
            sent_at = datetime.utcnow().isoformat(timespec="seconds")
            error_text = None
        else:
            failed_emails.append(email)
            status = "failed"
            sent_at = None
            error_text = error

        recipient_rows.append(
            {
                "email": email,
                "chat_id": chat_id,
                "status": status,
                "error": error_text,
                "sent_at": sent_at,
            }
        )
        logger.info("Notification sent to %s with status=%s", email, status)

    if recipient_rows:
        db.save_recipients(notification_id, recipient_rows)

    context.user_data.clear()
    state_manager.clear(update.effective_user.id)

    final_text = (
        "✅ Рассылка завершена.\n\n"
        f"📨 Всего в списке: {len(session.recipients)}\n"
        f"✅ Успешно отправлено: {sent_count}\n"
        f"❌ Ошибка отправки: {len(failed_emails)}\n"
        f"⚠️ Не найдено: {len(session.not_found)}\n"
        + (f"⚠️ Конфликтов: {len(session.conflicts)}\n" if session.conflicts else "")
        + "\nУспешно:\n"
        + ("\n".join(f"• {email}" for email in successful_emails) if successful_emails else "—")
        + "\n\nОшибка:\n"
        + ("\n".join(f"• {email}" for email in failed_emails) if failed_emails else "—")
        + "\n\nНе найдены:\n"
        + ("\n".join(f"• {email}" for email in session.not_found) if session.not_found else "—")
        + ("\n\nКонфликты:\n" + "\n".join(f"• {email}" for email in session.conflicts) if session.conflicts else "")
    )
    await update.callback_query.message.reply_text(final_text)
    return ConversationHandler.END
