from aiogram.filters import BaseFilter
from aiogram import types

from config import load_config


config = load_config()
admin_id = config.tg_bot.admin_tg_id
admins_list = config.tg_bot.admins_list


class AdminMessageFilter(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        user_id = message.from_user.id  # type: ignore
        is_access = user_id == admin_id or user_id in admins_list
        return is_access


class AdminCallbackFilter(BaseFilter):
    async def __call__(self, callback_query: types.CallbackQuery) -> bool:
        user_id = callback_query.from_user.id
        is_access = user_id == admin_id or user_id in admins_list
        return is_access
