from aiogram.filters import BaseFilter
from aiogram import types
from database.models import User
from sqlalchemy import select
from database.db import AsyncSessionLocal
from config import load_config


config = load_config()
admin_id = config.tg_bot.admin_tg_id
admins_list = config.tg_bot.admins_list


class AdminMessageFilter(BaseFilter):
    '''
    Фильтр для НЕ ГЛАВНОГО админа.
    '''
    def __init__(self):
        pass

    async def __call__(self, message: types.Message) -> bool:
        user_id = message.from_user.id

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User).filter_by(telegram_id=user_id)
            )
            user = result.scalars().first()

            return user.is_admin if user else False


class AdminCallbackFilter(BaseFilter):
    async def __call__(self, callback_query: types.CallbackQuery) -> bool:
        user_id = callback_query.from_user.id

        if user_id in admins_list:
            return True
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.telegram_id == user_id))
            user = result.scalars().first()

            return user is not None and user.is_admin
