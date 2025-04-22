import logging

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from sqlalchemy import select, or_, desc
from sqlalchemy.ext.asyncio import async_sessionmaker

from database.db import AsyncSessionLocal
from database.models import User, Pair
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

# изменить статус is_active на 1
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

# изменить статус is_active на 0
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

# информация пользователя о себе
@user_router.message(F.text.lower() == "/me")
async def user_profile(message: Message, session: async_sessionmaker):
    async with session() as s:
        result = await s.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()

        if not user:
            await message.answer("Вы ещё не зарегистрированы в системе.")
            return

        # Статус участия
        status = "✅ Активен" if user.is_active else "❌ Не участвует"

        # Интервал
        interval = f"{user.pairing_interval} дней" if user.pairing_interval else "не задан"

        # Поиск последней пары
        pair_result = await s.execute(
            select(Pair)
            .where(or_(Pair.user1_id == user.id, Pair.user2_id == user.id))
            .order_by(desc(Pair.paired_at))
            .limit(1)
        )
        last_pair = pair_result.scalar_one_or_none()

        if last_pair:
            if last_pair.user1_id == user.id:
                partner_username = last_pair.user2_username
            else:
                partner_username = last_pair.user1_username
            pair_info = f"@{partner_username}"
        else:
            pair_info = "нет данных"

        await message.answer(
            f"👤 Ваш профиль:\n"
            f"🔹 Username: @{user.username if user.username else 'не указан'}\n"
            f"🔹 Статус: {status}\n"
            f"🔹 Интервал участия: {interval}\n"
            f"\n"
            f"👥 Последняя пара: {pair_info}"
        )

# кнопки для выбор интервала
def get_interval_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 раз в 2 недели", callback_data="interval_2"),
            InlineKeyboardButton(text="1 раз в 3 недели", callback_data="interval_3"),
            InlineKeyboardButton(text="1 раз в 4 недели", callback_data="interval_4"),
        ]
    ])
    return keyboard

# команда для выбора интервала
@user_router.message(F.text.lower() == "/interval")
async def change_interval_prompt(message: Message):
    await message.answer(
        "Выбери, как часто ты хочешь участвовать в Random Coffee:",
        reply_markup=get_interval_keyboard()
    )

# функция для изменения интервала в базе
@user_router.callback_query(F.data.startswith("interval_"))
async def set_pairing_interval(callback: CallbackQuery, session: async_sessionmaker):
    interval_weeks = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    async with session() as s:
        result = await s.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            await callback.answer("Вы ещё не зарегистрированы.")
            return

        user.pairing_interval = interval_weeks
        await s.commit()

        await callback.answer(f"Теперь ты участвуешь раз в {interval_weeks} недели.", show_alert=True)