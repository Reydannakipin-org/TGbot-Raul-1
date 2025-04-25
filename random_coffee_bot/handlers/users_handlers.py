import logging

from aiogram import F, Router, types
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.exc import SQLAlchemyError

from database.db import AsyncSessionLocal
from texts import TEXTS
from services.user_service import (create_user,
                                   delete_user,
                                   get_user_by_telegram_id,
                                   set_user_active,
                                   update_user_field)
from states.user_states import FSMUserForm
from keyboards.user_buttons import (
    create_active_user_keyboard,
    create_inactive_user_keyboard,
    create_confirmation_keyboard
)


logger = logging.getLogger(__name__)

user_router = Router()


@user_router.message(CommandStart(), StateFilter(default_state))
async def process_start_command(message: Message, state: FSMContext):
    '''
    Хэндлер для команды /start. Регистрирует нового пользователя.
    Если поль-ль уже существует, обновляет его статус is_active = True.
    '''
    logger.info('Вошли в хэндлер, обрабатывающий команду /start')
    if message.from_user is None:
        return await message.answer(TEXTS['error_access'])

    user_telegram_id = message.from_user.id

    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_by_telegram_id(session, user_telegram_id)

            if user is None:
                logger.info('Пользователя нет в БД. Приступаем к добавлению.')
                user = await create_user(session,
                                         user_telegram_id,
                                         message.from_user.username,
                                         message.from_user.first_name,
                                         message.from_user.last_name)
                logger.info(f'Пользователь добавлен в БД. '
                            f'Имя {user.first_name}. Фамилия {user.last_name}')
                await message.answer(TEXTS['start'])
                await message.answer(TEXTS['ask_first_name'])
                await state.set_state(FSMUserForm.waiting_for_first_name)
            else:
                if not user.is_active:
                    await set_user_active(session, user_telegram_id, True)
                    logger.info('Статус пользователя изменен на Активный.')
                await message.answer(TEXTS['re_start'])
    except SQLAlchemyError as e:
        logger.exception('Ошибка при работе с базой данных: %s', str(e))
        await message.answer(TEXTS['db_error'])


@user_router.message(StateFilter(FSMUserForm.waiting_for_first_name),
                     F.text.isalpha())
async def process_first_name_sending(message: Message, state: FSMContext):
    '''
    Хэндлер срабатывает в состоянии, когда мы ждем от пользователя его имя,
    и оно введено верно. Обновляет имя в БД.
    '''
    if message.from_user is None:
        return await message.answer(TEXTS['error_access'])
    user_telegram_id = message.from_user.id

    first_name = message.text.strip()  # type: ignore
    logger.info(f'Получено сообщение в качестве имени: {first_name}')

    try:
        async with AsyncSessionLocal() as session:
            ok = await update_user_field(session,
                                         user_telegram_id,
                                         'first_name',
                                         first_name)
            if not ok:
                await message.answer(TEXTS['error_find_user'])
                return await state.clear()

            logger.info('Имя сохранено.')

        await message.answer(TEXTS['ask_last_name'])
        await state.set_state(FSMUserForm.waiting_for_last_name)
    except SQLAlchemyError:
        logger.exception('Ошибка при сохранении имени')
        await message.answer(TEXTS['db_error'])


@user_router.message(StateFilter(FSMUserForm.waiting_for_first_name))
async def warning_not_first_name(message: Message, state: FSMContext):
    '''
    Хэндлер срабатывает в состоянии, когда мы ждем от пользователя его имя,
    и оно введено неверно. Просим пользователя ввести заново.
    '''
    logger.info(f'Отказ. Получено сообщение в качестве имени: {message.text}')
    await message.answer(TEXTS['not_first_name'])


@user_router.message(StateFilter(FSMUserForm.waiting_for_last_name),
                     F.text.isalpha())
async def process_last_name_sending(message: Message, state: FSMContext):
    '''
    Хэндлер срабатывает в состоянии, когда мы ждем от пользователя
    его фамилию, и она введена верно. Обновляет фамилию в БД.
    '''
    if message.from_user is None:
        return await message.answer(TEXTS['error_access'])
    user_telegram_id = message.from_user.id

    last_name = message.text.strip()  # type: ignore
    logger.info(f'Получено сообщение в качестве фамилии: {last_name}')

    try:
        async with AsyncSessionLocal() as session:
            ok = await update_user_field(session,
                                         user_telegram_id,
                                         'last_name',
                                         last_name)
            if not ok:
                await message.answer(TEXTS['error_find_user'])
                return await state.clear()

            logger.info('Фамилия сохранена')

        keyboard = create_active_user_keyboard()

        await message.answer(
            TEXTS['thanks_for_answers'], reply_markup=keyboard
        )
        await state.clear()
    except SQLAlchemyError:
        logger.exception('Ошибка при сохранении фамилии')
        await message.answer(TEXTS['db_error'])


@user_router.message(StateFilter(FSMUserForm.waiting_for_last_name))
async def warning_not_last_name(message: Message, state: FSMContext):
    '''
    Хэндлер срабатывает в состоянии, когда мы ждем от пользователя его фамилию,
    и она введена неверно. Просим пользователя ввести заново.
    '''
    logger.info(f'Отказ. Получено сообщение в качестве фамилии: {message.text}')
    await message.answer(TEXTS['not_last_name'])


@user_router.message(Command(commands='help'), StateFilter(default_state))
async def process_help_command(message: Message):
    '''Хэндлер срабатывает на команду /help и отправляет инфо.'''
    await message.answer(TEXTS['help'])


# Служебная команда только на время разработки! Удаляет вас из БД.
@user_router.message(Command(commands='delete_me'), StateFilter(default_state))
async def process_delete_me_command(message: Message):
    if message.from_user is None:
        return await message.answer(TEXTS['error_access'])
    user_telegram_id = message.from_user.id

    try:
        async with AsyncSessionLocal() as session:
            deleted = await delete_user(session, user_telegram_id)
            if deleted:
                await message.answer('Ваш аккаунт успешно удалён.')
                logger.info('Пользователь удален')
            else:
                await message.answer('Вы не зарегистрированы, нечего удалять.')
    except SQLAlchemyError:
        logger.exception('Ошибка при удалении пользователя')
        await message.answer(TEXTS['db_error'])


@user_router.message(Command(commands='profile'), StateFilter(default_state))
async def process_send_profile_data(message: Message):
    '''
    Хэндлер срабатывает на команду /profile и отправляет инфо
    о пользователе.
    '''
    if message.from_user is None:
        return await message.answer(TEXTS['error_access'])
    user_telegram_id = message.from_user.id

    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_by_telegram_id(session, user_telegram_id)

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
    except SQLAlchemyError:
        logger.exception('Ошибка при получении данных профиля.')
        await message.answer(TEXTS['db_error'])


@user_router.message(Command(commands='change_name'),
                     StateFilter(default_state))
async def process_change_name(message: Message, state: FSMContext):
    '''
    Хэндлер срабатывает на команду /change_name и переводит состояние
    в ожидание отправки пользователем его имени.
    '''
    await message.answer(TEXTS['ask_first_name'])
    await state.set_state(FSMUserForm.waiting_for_first_name)


users_data = {
    751138564: {'active': True},  # Пример пользователя с активным статусом
    269444415: {'active': True}, # Пример пользователя с неактивным статусом
}

@user_router.message(Command(commands='user'), StateFilter(default_state))
async def process_user(message: Message):
    telegram_id = message.from_user.id  # Получаем telegram_id пользователя

    # Получаем данные пользователя из хранилища
    user_data = users_data.get(telegram_id)

    if user_data is not None:
        if user_data['active']:  # Проверяем значение поля active
            keyboard = create_active_user_keyboard()  # Создаем клавиатуру для активных пользователей
            await message.answer("Добро пожаловать обратно! Вы активный пользователь.", reply_markup=keyboard)
        else:
            keyboard = create_inactive_user_keyboard()  # Создаем клавиатуру для неактивных пользователей
            await message.answer("Вы неактивны. Пожалуйста, свяжитесь с администратором.", reply_markup=keyboard)
    else:
        keyboard = create_inactive_user_keyboard()  # Можно также показать неактивную клавиатуру для незарегистрированных пользователей
        await message.answer("Привет! Вы не зарегистрированы в системе.", reply_markup=keyboard)


@user_router.message(lambda message: message.text == "⏸️ Приостановить участие")
async def pause_participation(message: types.Message):
    telegram_id = message.from_user.id  # Получаем telegram_id пользователя
    user_data = users_data.get(telegram_id)

    if user_data and user_data['active']:
        await message.answer("Вы точно хотите приостановить участие?", reply_markup=create_confirmation_keyboard())
    else:
        await message.answer("Вы уже неактивны.")


@user_router.message(lambda message: message.text == "▶️ Возобновить участие")
async def resume_participation(message: types.Message):
    telegram_id = message.from_user.id  # Получаем telegram_id пользователя
    user_data = users_data.get(telegram_id)

    if user_data and not user_data['active']:
        await message.answer("Вы точно хотите возобновить участие?", reply_markup=create_confirmation_keyboard())
    else:
        await message.answer("Вы уже активны.")


# Обработчик callback-запросов для обработки нажатий на кнопки "Да" и "Нет"
@user_router.callback_query(lambda c: c.data.startswith("confirm_"))
async def process_confirmation(callback_query: types.CallbackQuery):
    telegram_id = callback_query.from_user.id  # Получаем telegram_id пользователя

    if telegram_id not in users_data:
        await callback_query.answer("Пользователь не найден.", show_alert=True)
        return

    await callback_query.message.delete()

    if callback_query.data == "confirm_yes":
        if users_data[telegram_id]['active']:  # Если пользователь активен, приостанавливаем его участие
            users_data[telegram_id]['active'] = False
            await callback_query.message.answer('Вы приостановили участие', reply_markup=create_inactive_user_keyboard())
        else:  # Если пользователь неактивен, возобновляем его участие
            users_data[telegram_id]['active'] = True
            await callback_query.message.answer('Вы возобновили участие', reply_markup=create_active_user_keyboard())

    elif callback_query.data == "confirm_no":
        await callback_query.answer('Вы решили не изменять статус участия', show_alert=True)

    # Уведомляем Telegram о том, что запрос обработан
    await callback_query.answer()