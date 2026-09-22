from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def main_menu(include_manager_controls: bool) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton("Рассылка"), KeyboardButton("Чаты")],
        [KeyboardButton("История")],
        [KeyboardButton("Помощь")],
    ]
    if include_manager_controls:
        rows.insert(1, [KeyboardButton("Менеджеры")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def manager_keyboard(manager_ids: list[int]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("Выдать доступ", callback_data="manager_add")]]
    rows.extend(
        [InlineKeyboardButton(f"Отозвать доступ: {user_id}", callback_data=f"manager_remove:{user_id}")]
        for user_id in manager_ids
    )
    return InlineKeyboardMarkup(rows)


def confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("✅ Отправить", callback_data="confirm_send"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel_send"),
        ]]
    )
