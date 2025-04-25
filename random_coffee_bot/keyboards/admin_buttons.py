from aiogram.types import KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder

button_list_employee = KeyboardButton(text="📋 Список сотрудников")
button_participant_management = KeyboardButton(text="👥 Управление участниками")
button_google_sheets = KeyboardButton(text="📊 Выгрузка в Google Sheets")
button_create_pair = KeyboardButton(text="🤝 Настройка создания пар")


buttons_kb_builder_admin = ReplyKeyboardBuilder()

buttons_kb_builder_admin.row(
    button_list_employee,
    button_participant_management,
    button_google_sheets,
    button_create_pair,

    width=1
)

buttons_kb_admin = buttons_kb_builder_admin.as_markup(
    # one_time_keyboard=True,
    resize_keyboard=True
)