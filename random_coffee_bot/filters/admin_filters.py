from aiogram.filters import BaseFilter
from aiogram import types
from database.models import User
from sqlalchemy import select
from database.db import AsyncSessionLocal


class AdminFilter(BaseFilter):
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
