from aiogram.types import KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

button_change_my_details = KeyboardButton(text="✏️ Изменить мои данные")
button_my_status = KeyboardButton(text="📊 Мой статус участия")
button_edit_meetings = KeyboardButton(text="🗓️ Изменить частоту встреч")
button_stop_participation = KeyboardButton(text="⏸️ Приостановить участие")
# button_start_participation = KeyboardButton(text="▶️ Возобновить участие")
button_how_it_works = KeyboardButton(text="❓ Как работает Random Coffee?")

# Кнопки для неактивных пользователей
button_resume_participation = KeyboardButton(text="▶️ Возобновить участие")
button_how_it_works_inactive = KeyboardButton(text="❓ Как работает Random Coffee?")


def create_confirmation_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да", callback_data="confirm_yes"),
         InlineKeyboardButton(text="Нет", callback_data="confirm_no")]
    ])
    return keyboard


# Функция для создания клавиатуры для активных пользователей
def create_active_user_keyboard():
    buttons_kb_builder_user = ReplyKeyboardBuilder()
    buttons_kb_builder_user.row(
        button_change_my_details,
        button_my_status,
        button_edit_meetings,
        # button_start_participation,
        button_stop_participation,
        button_how_it_works,
        width=1
    )
    return buttons_kb_builder_user.as_markup(resize_keyboard=True)


# Функция для создания клавиатуры для неактивных пользователей
def create_inactive_user_keyboard():
    buttons_kb_builder_user = ReplyKeyboardBuilder()
    buttons_kb_builder_user.row(
        button_resume_participation,
        button_how_it_works_inactive,
        width=1
    )
    return buttons_kb_builder_user.as_markup(resize_keyboard=True)
