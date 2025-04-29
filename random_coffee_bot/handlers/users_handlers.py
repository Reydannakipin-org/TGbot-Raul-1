import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import Message, ReplyKeyboardRemove, CallbackQuery
from sqlalchemy.exc import SQLAlchemyError

from database.db import AsyncSessionLocal
from filters.admin_filters import AdminCallbackFilter, AdminMessageFilter
from texts import TEXTS, KEYBOARD_BUTTON_TEXTS, USER_TEXTS, ADMIN_TEXTS
from services.user_service import (create_user,
                                   delete_user,
                                   get_user_by_telegram_id,
                                   set_user_active,
                                   update_user_field,
                                   create_text_with_interval,
                                   set_new_global_interval,
                                   parse_callback_data,)
from states.user_states import FSMUserForm
from keyboards.user_buttons import (
    create_active_user_keyboard,
    create_activate_keyboard,
    create_deactivate_keyboard,
    create_inactive_user_keyboard,
    generate_inline_confirm_change_interval,
    generate_inline_interval,
)


logger = logging.getLogger(__name__)

user_router = Router()
user_router.message.filter(~AdminMessageFilter())
user_router.callback_query.filter(~AdminCallbackFilter())


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
    logger.info(
        f'Отказ. Получено сообщение в качестве фамилии: {message.text}'
    )
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
                await message.answer('Ваш аккаунт успешно удалён.',
                                     reply_markup=ReplyKeyboardRemove())
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


# Служебная команда только на время разработки!
@user_router.message(Command(commands='user'), StateFilter(default_state))
async def process_user(message: Message):
    """Хэндлер для команды /user. Получает информацию о пользователе."""
    if message.from_user is None:
        return await message.answer(TEXTS['error_access'])
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        user = await get_user_by_telegram_id(session, telegram_id)

    if user is not None:
        if user.is_active:
            keyboard = create_active_user_keyboard()
            await message.answer(
                "Добро пожаловать обратно! Вы активный пользователь.",
                reply_markup=keyboard
            )
        else:
            keyboard = create_inactive_user_keyboard()
            await message.answer(
                "Вы неактивны. Пожалуйста, свяжитесь с администратором.",
                reply_markup=keyboard
            )
    else:
        keyboard = create_inactive_user_keyboard()
        await message.answer(
            "Привет! Вы не зарегистрированы в системе.",
            reply_markup=keyboard
        )


@user_router.message(
    F.text == KEYBOARD_BUTTON_TEXTS[
        'button_stop_participation'
    ],
    StateFilter(default_state)
)
async def pause_participation(message: Message, state: FSMContext):
    """Хэндлер для приостановки участия пользователя."""
    if message.from_user is None:
        return await message.answer(TEXTS['error_access'])
    telegram_id = message.from_user.id

    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_by_telegram_id(session, telegram_id)
    except SQLAlchemyError:
        logger.exception("Ошибка при запросе пользователя для паузы участия.")
        return await message.answer(TEXTS['db_error'])

    if user is None:
        return await message.answer(TEXTS['error_find_user'])

    if user.is_active:
        await message.answer(
            "Вы точно хотите приостановить участие?",
            reply_markup=create_deactivate_keyboard()
        )
    else:
        await message.answer("Вы уже неактивны.")


@user_router.message(F.text == KEYBOARD_BUTTON_TEXTS[
    'button_resume_participation'
    ],
    StateFilter(default_state)
)
async def resume_participation(message: Message, state: FSMContext):
    """
    Хэндлер для возобновления участия пользователя.
    """
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        user = await get_user_by_telegram_id(session, telegram_id)

    if user and not user.is_active:
        await message.answer(
            "Вы точно хотите возобновить участие?",
            reply_markup=create_activate_keyboard()
        )
    else:
        await message.answer("Вы уже активны.")


@user_router.callback_query(lambda c: c.data.startswith("confirm_deactivate_"),
                            StateFilter(default_state))
async def process_deactivate_confirmation(callback_query: CallbackQuery):
    """Хэндлер для обработки подтверждения приостановки участия."""
    telegram_id = callback_query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await get_user_by_telegram_id(session, telegram_id)

        if user is None:
            await callback_query.answer(
                "Пользователь не найден.", show_alert=True
            )
            return

        try:
            await callback_query.message.delete()

            if callback_query.data == "confirm_deactivate_yes":
                if user.is_active:
                    await set_user_active(session, telegram_id, False)
                    await callback_query.message.answer(
                        'Вы приостановили участие',
                        reply_markup=create_inactive_user_keyboard()
                    )
                else:
                    await callback_query.answer(
                        "Вы уже приостановили участие.",
                        show_alert=True
                    )

            elif callback_query.data == "confirm_deactivate_no":
                await callback_query.answer(
                    'Вы решили не изменять статус участия',
                    show_alert=True
                )

            await callback_query.answer()

        except Exception as e:
            print(f"Произошла ошибка: {e}")
            await callback_query.answer(
                "Произошла ошибка. Пожалуйста, попробуйте еще раз.",
                show_alert=True
            )


@user_router.callback_query(lambda c: c.data.startswith("confirm_activate_"),
                            StateFilter(default_state))
async def process_activate_confirmation(callback_query: CallbackQuery):
    """Хэндлер для обработки подтверждения возобновления участия."""
    telegram_id = callback_query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await get_user_by_telegram_id(session, telegram_id)

        if user is None:
            await callback_query.answer(
                "Пользователь не найден.",
                show_alert=True
            )
            return

        try:
            await callback_query.message.delete()

            if callback_query.data == "confirm_activate_yes":
                if not user.is_active:
                    await set_user_active(session, telegram_id, True)
                    await callback_query.message.answer(
                        'Вы возобновили участие',
                        reply_markup=create_active_user_keyboard()
                    )
                else:
                    await callback_query.answer(
                        "Вы уже активны.",
                        show_alert=True
                    )

            elif callback_query.data == "confirm_activate_no":
                await callback_query.answer(
                    'Вы решили не изменять статус участия',
                    show_alert=True
                )

            await callback_query.answer()

        except Exception as e:
            print(f"Произошла ошибка: {e}")
            await callback_query.answer(
                "Произошла ошибка. Пожалуйста, попробуйте еще раз.",
                show_alert=True
            )


@user_router.message(Command(commands='clean'),
                     StateFilter(default_state))
async def process_clean_keyboards(message: Message, state: FSMContext):
    '''
    Служебный хэндлер для удаления клавиатуры на этапе тестирования.
    '''
    await message.answer('Убираем клаву',
                         reply_markup=ReplyKeyboardRemove())


@user_router.message(F.text == KEYBOARD_BUTTON_TEXTS['button_edit_meetings'],
                     StateFilter(default_state))
async def process_frequency(message: Message):
    try:
        async with AsyncSessionLocal() as session:
            user_id = message.from_user.id  # Получаем ID пользователя
            data_text = await create_text_with_interval(
                session, USER_TEXTS['user_confirm_changing_interval'], user_id
            )

            await message.answer(
                text=data_text,
                reply_markup=generate_inline_confirm_change_interval()
            )

    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        await message.answer(ADMIN_TEXTS['db_error'])


@user_router.callback_query(
    lambda c: c.data.startswith('confirm_changing_interval'),
    StateFilter(default_state)
)
async def handle_callback_query_yes(callback_query: CallbackQuery):
    await callback_query.message.delete()
    await callback_query.message.answer(
        USER_TEXTS['update_frequency'],
        reply_markup=generate_inline_interval()
    )


@user_router.callback_query(
    lambda c: c.data.startswith('new_interval:'),
    StateFilter(default_state)
)
async def process_set_new_interval_user(callback: CallbackQuery):
    '''
    Хэндлер срабатывает на нажатии пользователем инлайн-кнопки
    с выбором частоты встреч.
    '''
    _, new_interval = parse_callback_data(callback.data)

    try:
        async with AsyncSessionLocal() as session:
            user_id = callback.from_user.id
            await set_new_global_interval(session, new_interval)

            data_text = await create_text_with_interval(
                session, USER_TEXTS['success_new_interval'], user_id
            )

            if isinstance(callback.message, Message):
                await callback.message.edit_text(text=data_text)

    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных ')
        await callback.answer(ADMIN_TEXTS['db_error'])


@user_router.callback_query(
    lambda c: c.data.startswith('cancel_changing_interval')
)
async def handle_callback_query_no(callback_query: CallbackQuery):
    await callback_query.message.delete()
    await callback_query.message.answer(
        text=USER_TEXTS['user_default_interval']
    )


#Хэндлер для тестов нужно будет удалить
@user_router.message(Command(commands='interval'))
async def set_interval_command(message: Message):
    try:
        # Устанавливаем новый интервал (например, 2)
        new_interval = 4  # Замените на нужный вам интервал

        async with AsyncSessionLocal() as session:
            await set_new_global_interval(session, new_interval)

        await message.answer(
            f"Глобальный интервал успешно изменен на {new_interval}."
        )

    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        await message.answer(ADMIN_TEXTS['db_error'])
    except Exception as e:
        logger.exception('Произошла ошибка при изменении интервала')
        await message.answer(f"Произошла ошибка: {str(e)}")


@user_router.message(F.text)
async def fallback_handler(message: Message):
    '''
    Этот хэндлер должен быть самым последним,
    так как он улавливает любую команду которую не смогли уловить
    другие хэндлеры.
    '''
    await message.answer('Я не знаю такой команды. '
                         'Пожалуйста, используй клавиатуру.')
