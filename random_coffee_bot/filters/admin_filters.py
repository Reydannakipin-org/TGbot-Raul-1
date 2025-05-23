from aiogram.filters import BaseFilter
from aiogram import types
from database.db import AsyncSessionLocal
from config import load_config
from services.user_service import get_user_by_telegram_id


config = load_config()
admins_list = config.tg_bot.admins_list


class AdminMessageFilter(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        '''
        Фильтр для НЕ ГЛАВНОГО админа.
        '''
        user_id = message.from_user.id

        if user_id in admins_list:
            return True

        async with AsyncSessionLocal() as session:
            user = await get_user_by_telegram_id(session, user_id)
            return user.is_admin if user else False


class AdminCallbackFilter(BaseFilter):
    async def __call__(self, callback_query: types.CallbackQuery) -> bool:
        user_id = callback_query.from_user.id

        if user_id in admins_list:
            return True

        async with AsyncSessionLocal() as session:
            user = await get_user_by_telegram_id(session, user_id)
            return user is not None and user.is_admin
