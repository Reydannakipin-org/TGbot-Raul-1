from aiogram.types import (InlineKeyboardButton,
                           InlineKeyboardMarkup,
                           KeyboardButton)
from aiogram.utils.keyboard import ReplyKeyboardBuilder


from texts import INLINE_BUTTON_TEXTS, KEYBOARD_BUTTON_TEXTS


button_list_participants = KeyboardButton(
    text=KEYBOARD_BUTTON_TEXTS['button_list_participants'])
button_participant_management = KeyboardButton(
    text=KEYBOARD_BUTTON_TEXTS['button_participant_management'])
button_google_sheets = KeyboardButton(
    text=KEYBOARD_BUTTON_TEXTS['button_google_sheets'])
button_change_interval = KeyboardButton(
    text=KEYBOARD_BUTTON_TEXTS['button_change_interval'])


buttons_kb_builder_admin = ReplyKeyboardBuilder()

buttons_kb_builder_admin.row(
    button_list_participants,
    button_participant_management,
    button_google_sheets,
    button_change_interval,
    width=1
)

buttons_kb_admin = buttons_kb_builder_admin.as_markup(
    resize_keyboard=True
)


def generate_ikb_participant_management(user_telegram_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=INLINE_BUTTON_TEXTS['set_has_permission_false'],
                callback_data=f'set_has_permission_false:{user_telegram_id}'
            )
        ]
    ])


def generate_ikb_confirm_set_has_permission_false(user_telegram_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=INLINE_BUTTON_TEXTS['yes'],
                callback_data=(
                    f'confirm_set_has_permission_false:{user_telegram_id}')
            ),
            InlineKeyboardButton(
                text=INLINE_BUTTON_TEXTS['no'],
                callback_data=(
                    f'return_to_find_user_by_telegram_id:{user_telegram_id}')
            )
        ]
    ])
