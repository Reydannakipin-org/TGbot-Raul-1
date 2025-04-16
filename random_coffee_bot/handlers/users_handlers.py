import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state, State, StatesGroup
from aiogram.types import Message
from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import User
from texts import TEXTS


logger = logging.getLogger(__name__)

user_router = Router()


class FSMUserForm(StatesGroup):
    waiting_for_first_name = State()
    waiting_for_last_name = State()


@user_router.message(CommandStart(), StateFilter(default_state))
async def process_start_command(message: Message, state: FSMContext):
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
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name
            )
            session.add(user)
            await session.commit()
            logger.info(f'Пользователь добавлен в БД. Имя {user.first_name}. '
                        f'Фамилия {user.last_name}')
            await message.answer(TEXTS['start'])
            await message.answer(TEXTS['ask_first_name'])
            await state.set_state(FSMUserForm.waiting_for_first_name)
        else:
            if not user.is_active:
                user.is_active = True
                await session.commit()
                logger.info('Статус пользователя изменен на Активный.')
            await message.answer(TEXTS['re_start'])


@user_router.message(StateFilter(FSMUserForm.waiting_for_first_name),
                     F.text.isalpha())
async def process_first_name_sending(message: Message, state: FSMContext):
    first_name = message.text.strip()  # type: ignore
    logger.info(f'Получено сообщение в качестве имени: {first_name}')
    async with AsyncSessionLocal() as session:
        query = select(User).where(User.telegram_id == message.from_user.id)  # type: ignore
        result = await session.execute(query)
        user = result.scalar_one_or_none()
        if user is None:
            await message.answer(TEXTS['error_find_user'])
            await state.clear()
            return
        user.first_name = first_name
        await session.commit()
        logger.info(f'Имя сохранено {user.first_name}')

    await message.answer(TEXTS['ask_last_name'])
    await state.set_state(FSMUserForm.waiting_for_last_name)


@user_router.message(StateFilter(FSMUserForm.waiting_for_first_name))
async def warning_not_first_name(message: Message, state: FSMContext):
    logger.info(f'Отказ. Получено сообщение в качестве имени: {message.text}')
    await message.answer(TEXTS['not_first_name'])


@user_router.message(StateFilter(FSMUserForm.waiting_for_last_name),
                     F.text.isalpha())
async def process_last_name_sending(message: Message, state: FSMContext):
    last_name = message.text.strip()  # type: ignore
    logger.info(f'Получено сообщение в качестве фамилии: {last_name}')
    async with AsyncSessionLocal() as session:
        query = select(User).where(User.telegram_id == message.from_user.id)  # type: ignore
        result = await session.execute(query)
        user = result.scalar_one_or_none()
        if user is None:
            await message.answer(TEXTS['error_find_user'])
            await state.clear()
            return
        user.last_name = last_name
        await session.commit()
        logger.info(f'Фамилия сохранена {user.last_name}')

    await message.answer(TEXTS['thanks_for_answers'])
    await state.clear()


@user_router.message(StateFilter(FSMUserForm.waiting_for_last_name))
async def warning_not_last_name(message: Message, state: FSMContext):
    logger.info(f'Отказ. Получено сообщение в качестве фамилии: {message.text}')
    await message.answer(TEXTS['not_last_name'])


@user_router.message(Command(commands='help'), StateFilter(default_state))
async def process_help_command(message: Message):
    await message.answer(TEXTS['help'])


# Служебная команда только на время разработки! Удаляет вас из БД.
@user_router.message(Command(commands='delete_me'), StateFilter(default_state))
async def process_delete_me_command(message: Message):
    if message.from_user is None:
        await message.answer('Ошибка: не удалось определить пользователя.')
        return

    async with AsyncSessionLocal() as session:
        query = select(User).where(User.telegram_id == message.from_user.id)
        result = await session.execute(query)
        user = result.scalar_one_or_none()

        if user is not None:
            await session.delete(user)
            await session.commit()
            await message.answer('Ваш аккаунт успешно удалён. Все данные сброшены.')
            logger.info('Пользователь удален')
        else:
            await message.answer('Вы не зарегистрированы, нечего удалять.')


@user_router.message(Command(commands='profile'), StateFilter(default_state))
async def process_send_profile_data(message: Message):
    if message.from_user is None:
        await message.answer(TEXTS['error_find_user'])
        return

    async with AsyncSessionLocal() as session:
        query = select(User).where(User.telegram_id == message.from_user.id)
        result = await session.execute(query)
        user = result.scalar_one_or_none()

        if user is None:
            await message.answer(TEXTS['error_find_user'])
            return

        data_text = TEXTS['my_data'].format(
            first_name=user.first_name or TEXTS['no_data'],
            last_name=user.last_name or TEXTS['no_data'],
            status=(TEXTS['status_active_true'] if user.is_active else
                    TEXTS['status_active_false'])
        )
        await message.answer(data_text)


@user_router.message(Command(commands='change_name'),
                     StateFilter(default_state))
async def process_change_name(message: Message, state: FSMContext):
    if message.from_user is None:
        await message.answer(TEXTS['error_find_user'])
        return

    async with AsyncSessionLocal() as session:
        query = select(User).where(User.telegram_id == message.from_user.id)
        result = await session.execute(query)
        user = result.scalar_one_or_none()

        if user is None:
            await message.answer(TEXTS['error_find_user'])
            return

        await message.answer(TEXTS['ask_first_name'])
        await state.set_state(FSMUserForm.waiting_for_first_name)
