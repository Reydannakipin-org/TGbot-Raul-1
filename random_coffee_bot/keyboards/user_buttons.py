from aiogram.types import KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from services.user_service import get_global_interval
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from texts import (KEYBOARD_BUTTON_TEXTS,
                   INLINE_BUTTON_TEXTS,
                   INTERVAL_TEXTS,
                   )

button_change_my_details = KeyboardButton(
    text=KEYBOARD_BUTTON_TEXTS['button_change_my_details']
)
button_my_status = KeyboardButton(
    text=KEYBOARD_BUTTON_TEXTS['button_my_status']
)
button_edit_meetings = KeyboardButton(
    text=KEYBOARD_BUTTON_TEXTS['button_edit_meetings']
)
button_stop_participation = KeyboardButton(
    text=KEYBOARD_BUTTON_TEXTS['button_stop_participation']
)
button_how_it_works = KeyboardButton(
    text=KEYBOARD_BUTTON_TEXTS['button_how_it_works']
)

# Кнопки для неактивных пользователей
button_resume_participation = KeyboardButton(
    text=KEYBOARD_BUTTON_TEXTS['button_resume_participation']
)
button_how_it_works_inactive = KeyboardButton(
    text=KEYBOARD_BUTTON_TEXTS['button_how_it_works']
)


def create_deactivate_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=INLINE_BUTTON_TEXTS['yes'],
                              callback_data="confirm_deactivate_yes"
                              ),
         InlineKeyboardButton(text=INLINE_BUTTON_TEXTS['no'],
                              callback_data="confirm_deactivate_no"
                              )]
    ])
    return keyboard


def create_activate_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=INLINE_BUTTON_TEXTS['yes'],
                              callback_data="confirm_activate_yes"
                              ),
         InlineKeyboardButton(text=INLINE_BUTTON_TEXTS['no'],
                              callback_data="confirm_activate_no"
                              )]
    ])
    return keyboard


def generate_inline_confirm_change_interval():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=INLINE_BUTTON_TEXTS['yes'],
                callback_data=('confirm_changing_interval')
            ),
            InlineKeyboardButton(
                text=INLINE_BUTTON_TEXTS['no'],
                callback_data=('cancel_changing_interval')
            )
        ]
    ])


# Функция для создания клавиатуры для активных пользователей
def create_active_user_keyboard():
    buttons_kb_builder_user = ReplyKeyboardBuilder()
    buttons_kb_builder_user.row(
        button_change_my_details,
        button_my_status,
        button_edit_meetings,
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


async def generate_inline_interval(session: AsyncSession):
    # admin_interval = await get_global_interval(session)
    # text = f'По умолчанию: 1 раз в {admin_interval} недели'
    text = 'По умолчанию'
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=text,
                callback_data='change_interval'
            )
        ],
        [
            InlineKeyboardButton(
                text=INTERVAL_TEXTS['2'],
                callback_data=('new_interval:2')
            )
        ],
        [
            InlineKeyboardButton(
                text=INTERVAL_TEXTS['3'],
                callback_data=('new_interval:3')
            )
        ],
        [
            InlineKeyboardButton(
                text=INTERVAL_TEXTS['4'],
                callback_data=('new_interval:4')
            )
        ]
    ])
    return keyboard


def yes_or_no_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=INLINE_BUTTON_TEXTS['yes'],
                              callback_data="change_my_details_yes"
                              ),
         InlineKeyboardButton(text=INLINE_BUTTON_TEXTS['no'],
                              callback_data="change_my_details_no"
                              )]
    ])
    return keyboard
