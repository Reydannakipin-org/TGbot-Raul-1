import logging

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (InlineKeyboardButton,
                           InlineKeyboardMarkup,
                           KeyboardButton)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from database.db import AsyncSessionLocal
from database.models import User
from texts import (INLINE_BUTTON_TEXTS,
                   INTERVAL_TEXTS,
                   KEYBOARD_BUTTON_TEXTS)


logger = logging.getLogger(__name__)


button_info = KeyboardButton(
    text=KEYBOARD_BUTTON_TEXTS['button_info']
)
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
    button_info,
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
                callback_data=('new_global_interval:2')
            )
        ],
        [
            InlineKeyboardButton(
                text=INTERVAL_TEXTS['3'],
                callback_data=('new_global_interval:3')
            )
        ],
        [
            InlineKeyboardButton(
                text=INTERVAL_TEXTS['4'],
                callback_data=('new_global_interval:4')
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


class UsersCallbackFactory(CallbackData, prefix='get_user'):
    telegram_id: int


class PageCallbackFactory(CallbackData, prefix='page'):
    page: int


ITEMS_PER_PAGE = 2


async def generate_inline_user_list(page: int = 1) -> InlineKeyboardBuilder:
    try:
        async with AsyncSessionLocal() as session:
            total_res = await session.execute(
                select(func.count()).select_from(User)
            )
            total = total_res.scalar_one()

            stmt = (
                select(User)
                .order_by(User.last_name)
                .offset((page - 1) * ITEMS_PER_PAGE)
                .limit(ITEMS_PER_PAGE)
            )
            result = await session.execute(stmt)
            users = result.scalars().all()
    except SQLAlchemyError as e:
        logger.exception('Не удалось получить список пользователей из БД.')
        raise e

    kb = InlineKeyboardBuilder()

    for u in users:
        text = f"{u.last_name or ''} {u.first_name or ''}".strip() or f"#{u.telegram_id}"
        kb.button(
            text=text,
            callback_data=UsersCallbackFactory(telegram_id=u.telegram_id).pack()
        )

    if page > 1:
        kb.button(
            text="⬅️ Назад",
            callback_data=PageCallbackFactory(page=page - 1).pack()
        )
    if page * ITEMS_PER_PAGE < total:
        kb.button(
            text="Вперёд ➡️",
            callback_data=PageCallbackFactory(page=page + 1).pack()
        )

    kb.adjust(1)
    return kb
