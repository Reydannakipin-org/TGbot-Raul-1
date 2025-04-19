import logging

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

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

@user_router.message(F.text.lower() == "/join")
async def join_random_coffee(message: Message, session: async_sessionmaker):
    async with session() as s:
        result = await s.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()

        if user:
            if user.is_active:
                await message.answer("Вы уже участвуете в Random Coffee 😊")
            else:
                user.is_active = True
                await s.commit()
                await message.answer("✅ Вы добавлены в список участников Random Coffee!")
        else:
            await message.answer("Вы ещё не зарегистрированы в системе. Обратитесь к администратору.")

@user_router.message(F.text.lower() == "/leave")
async def leave_random_coffee(message: Message, session: async_sessionmaker):
    async with session() as s:
        result = await s.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()

        if user:
            if not user.is_active:
                await message.answer("Вы уже не участвуете в Random Coffee 😴")
            else:
                user.is_active = False
                await s.commit()
                await message.answer("❌ Вы исключены из участия в Random Coffee. Возвращайтесь, когда захотите!")
        else:
            await message.answer("Вы ещё не зарегистрированы в системе. Обратитесь к администратору.")