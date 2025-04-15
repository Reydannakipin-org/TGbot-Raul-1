import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import User
from texts import TEXTS


logger = logging.getLogger(__name__)

user_router = Router()


@user_router.message(CommandStart())
async def process_start_command(message: Message):
    logger.info('Вошли в хэндлер, обрабатывающий команду /start')
    if message.from_user is None:
        await message.answer(TEXTS['error_access'])
        return

    async with AsyncSessionLocal() as session:
        query = select(User).where(User.telegram_id == message.from_user.id)
        result = await session.execute(query)
        user = result.scalar_one_or_none()

        if user is None:
            logger.info('Пользователя нет в БД. Приступаем к добавлению.')
            user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username
            )
            session.add(user)
            await session.commit()
            logger.info('Пользователь добавлен в БД.')
            await message.answer(TEXTS['start'])
        else:
            if not user.is_active:
                user.is_active = True
                await session.commit()
                logger.info('Статус пользователя изменен на Активный.')
            await message.answer(TEXTS['re_start'])
