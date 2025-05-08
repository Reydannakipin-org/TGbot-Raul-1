from aiogram.types import (InlineKeyboardButton,
                           InlineKeyboardMarkup,
                           KeyboardButton)
from aiogram.utils.keyboard import ReplyKeyboardBuilder


from texts import (INLINE_BUTTON_TEXTS,
                   INTERVAL_TEXTS,
                   KEYBOARD_BUTTON_TEXTS)


button_list_participants = KeyboardButton(
    text=KEYBOARD_BUTTON_TEXTS['button_list_participants'])
button_participant_management = KeyboardButton(
    text=KEYBOARD_BUTTON_TEXTS['button_participant_management'])
button_google_sheets = KeyboardButton(
    text=KEYBOARD_BUTTON_TEXTS['button_google_sheets'])
button_change_interval = KeyboardButton(
    text=KEYBOARD_BUTTON_TEXTS['button_change_interval'])
button_send_notification = KeyboardButton(
    text=KEYBOARD_BUTTON_TEXTS['button_send_notification']
)


buttons_kb_builder_admin = ReplyKeyboardBuilder()

buttons_kb_builder_admin.row(
    button_participant_management,
    button_google_sheets,
    button_change_interval,
    button_send_notification,
    width=1
)

buttons_kb_admin = buttons_kb_builder_admin.as_markup(
    resize_keyboard=True
)


def generate_inline_manage(user_telegram_id: int,
                           has_permission: bool):
    if has_permission:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                    text=INLINE_BUTTON_TEXTS['set_has_permission_false'],
                    callback_data=f'set_has_permission_false:{user_telegram_id}')],
            [InlineKeyboardButton(
                text=INLINE_BUTTON_TEXTS['set_pause'],
                callback_data=f'set_pause:{user_telegram_id}')],
            [InlineKeyboardButton(
                text=INLINE_BUTTON_TEXTS['cancel'],
                callback_data=f'cancel:{user_telegram_id}')]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=INLINE_BUTTON_TEXTS['set_has_permission_true'],
                callback_data=f'set_has_permission_true:{user_telegram_id}'
                )],
            [InlineKeyboardButton(
                text=INLINE_BUTTON_TEXTS['cancel'],
                callback_data=f'cancel:{user_telegram_id}'
                )]
        ])


def generate_inline_confirm_permission_false(user_telegram_id: int):
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


def generate_inline_confirm_permission_true(user_telegram_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=INLINE_BUTTON_TEXTS['yes'],
                callback_data=(
                    f'confirm_set_has_permission_true:{user_telegram_id}')
            ),
            InlineKeyboardButton(
                text=INLINE_BUTTON_TEXTS['no'],
                callback_data=(
                    f'return_to_find_user_by_telegram_id:{user_telegram_id}')
            )
        ]
    ])


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


def generate_inline_interval_options():
    return InlineKeyboardMarkup(inline_keyboard=[
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


def generate_inline_notification_options(notif_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=INLINE_BUTTON_TEXTS['confirm_notif'],
                callback_data=(f'confirm_notif:{notif_id}')
            )
        ],
        [
            InlineKeyboardButton(
                text=INLINE_BUTTON_TEXTS['edit_notif'],
                callback_data=('edit_notif')
            )
        ],
        [
            InlineKeyboardButton(
                text=INLINE_BUTTON_TEXTS['cancel_notif'],
                callback_data=('cancel_notif')
            )
        ]
    ])


# def generate_inline_notification_options(notif_id):
#     return InlineKeyboardMarkup(inline_keyboard=[
#         [
#             InlineKeyboardButton(
#                 text=INLINE_BUTTON_TEXTS['confirm_notif'],
#                 callback_data=(f'confirm_notif:{notif_id}')
#             )
#         ],
#         [
#             InlineKeyboardButton(
#                 text=INLINE_BUTTON_TEXTS['edit_notif'],
#                 callback_data=(f'edit_notif:{notif_id}')
#             )
#         ],
#         [
#             InlineKeyboardButton(
#                 text=INLINE_BUTTON_TEXTS['cancel_notif'],
#                 callback_data=(f'cancel_notif:{notif_id}')
#             )
#         ]
#     ])