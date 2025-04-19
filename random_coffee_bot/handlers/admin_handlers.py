from aiogram import Router, F
from sqlalchemy.ext.asyncio import async_sessionmaker
from aiogram.types import Message
from sqlalchemy import select
from database.models import User

admin_router = Router()


@admin_router.message(F.text.lower() == "/all")
async def list_participants(message: Message, session: async_sessionmaker):
    # Получаем информацию о пользователе из базы данных
    async with session() as s:
        result = await s.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()

        # Проверка на админский статус
        if not user or not user.is_admin:
            await message.answer("⛔ У вас нет доступа к этой команде.")
            return

        # Получаем список активных участников
        result = await s.execute(select(User).where(User.is_active == True))
        participants = result.scalars().all()

        if not participants:
            await message.answer("Список участников пуст.")
            return

        # Формируем список участников
        text = "👥 Участники Random Coffee:\n\n"
        for i, user in enumerate(participants, start=1):
            username = f"@{user.username}"
            text += f"{i}. {username} (ID: {user.telegram_id})\n"

        await message.answer(text)