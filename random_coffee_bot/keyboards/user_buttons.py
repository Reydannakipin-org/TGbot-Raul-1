from aiogram.types import KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from texts import (
    KEYBOARD_BUTTON_TEXTS,
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
button_send_photo = KeyboardButton(
    text=KEYBOARD_BUTTON_TEXTS['button_send_photo']
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


def create_active_user_keyboard():
    '''
    Функция для создания клавиатуры для активных пользователей.
    '''
    buttons_kb_builder_user = ReplyKeyboardBuilder()
    buttons_kb_builder_user.row(
        button_change_my_details,
        button_my_status,
        button_edit_meetings,
        button_send_photo,
        button_stop_participation,
        button_how_it_works,
        width=1
    )
    return buttons_kb_builder_user.as_markup(resize_keyboard=True)


def create_inactive_user_keyboard():
    '''
    Функция для создания клавиатуры для неактивных пользователей.
    '''
    buttons_kb_builder_user = ReplyKeyboardBuilder()
    buttons_kb_builder_user.row(
        button_resume_participation,
        button_how_it_works_inactive,
        width=1
    )
    return buttons_kb_builder_user.as_markup(resize_keyboard=True)


def generate_inline_interval():
    '''
    Инлайн-клавиатура для выбора интервала встреч.
    '''
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

  def meeting_question_kb(pair_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data=f"meeting_yes:{pair_id}")],
        [InlineKeyboardButton(text="❌ Нет", callback_data=f"meeting_no:{pair_id}")]
    ])

def comment_question_kb(pair_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Комментарий (оставить/изменить)", callback_data=f"leave_comment:{pair_id}")],
        [InlineKeyboardButton(text="⏭️ Без комментария", callback_data=f"no_comment:{pair_id}")]
    ])

def confirm_edit_comment_kb(pair_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Да, изменить", callback_data=f"confirm_edit:{pair_id}"),
            InlineKeyboardButton(text="❌ Нет, оставить", callback_data=f"cancel_edit:{pair_id}")
        ]
    ])