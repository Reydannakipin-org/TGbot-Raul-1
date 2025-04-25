from aiogram.filters import BaseFilter
from aiogram import types

from config import load_config


config = load_config()
admin_id = config.tg_bot.admin_tg_id


class AdminMessageFilter(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        return message.from_user.id == admin_id  # type: ignore


class AdminCallbackFilter(BaseFilter):
    async def __call__(self, callback_query: types.CallbackQuery) -> bool:
        return callback_query.from_user.id == admin_id
