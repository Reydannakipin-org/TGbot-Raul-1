import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select
from database.models import User

# Импорт базы данных и сервисов
from database.db import AsyncSessionLocal
from services.user_service import (
    create_user,
    delete_user,
    get_user_by_telegram_id,
    set_user_active,
    update_user_field,
    create_text_with_interval,
    set_new_global_interval,
    parse_callback_data,
    set_new_user_interval,
    create_text_with_default_interval,
    create_text_status_active,
    create_text_random_coffee,
    create_text_for_select_an_interval,
)

# Импорт фильтров и состояний
from filters.admin_filters import AdminCallbackFilter, AdminMessageFilter
from states.user_states import FSMUserForm

# Импорт текстов и клавиатур
from texts import TEXTS, KEYBOARD_BUTTON_TEXTS, USER_TEXTS, ADMIN_TEXTS
from keyboards.user_buttons import (
    create_active_user_keyboard,
    create_activate_keyboard,
    create_deactivate_keyboard,
    create_inactive_user_keyboard,
    generate_inline_confirm_change_interval,
    generate_inline_interval,
    yes_or_no_keyboard,
)

NAME_PATTERN = r'^[A-Za-zА-Яа-яЁё]+(?:[-\s][A-Za-zА-Яа-яЁё]+)*$'


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
                     F.text.regexp(NAME_PATTERN))
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
                     F.text.regexp(NAME_PATTERN))
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
    """
    Хэндлер для приостановки участия пользователя.
    """
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


@user_router.message(
    F.text == KEYBOARD_BUTTON_TEXTS['button_change_my_details'],
    StateFilter(default_state)
)
async def update_full_name(message: Message):
    '''
    Хэндлер для обновления имени и фамилии пользователя.
    '''
    telegram_id = message.from_user.id

    try:
        async with AsyncSessionLocal() as session:
            # Получаем текущее имя и фамилию пользователя
            user = await get_user_by_telegram_id(session, telegram_id)

            if user is None:
                await message.answer("Пользователь не найден.")
                return

            # Форматируем сообщение с текущими данными
            user_message = (
                f"Твои текущие данные: \n"
                f"Имя: {user.first_name} \n"
                f"Фамилия: {user.last_name} \n\n"
                "Ты уверен, что хочешь изменить их?"
            )

        # Отправляем сообщение пользователю
        await message.answer(
            user_message,
            reply_markup=yes_or_no_keyboard()
        )

    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        await message.answer(ADMIN_TEXTS['db_error'])


@user_router.callback_query(
    lambda c: c.data.startswith('change_my_details_yes'),
    StateFilter(default_state)
)
async def update_full_name_yes(callback: CallbackQuery, state: FSMContext):
    '''
    Хэндлер для подтверждения изменения имени и фамилии.
    '''
    await callback.message.delete()
    await callback.message.answer("Введи новое имя:")
    await state.set_state(FSMUserForm.waiting_for_first_name)


@user_router.callback_query(
    lambda c: c.data.startswith('change_my_details_no'),
    StateFilter(default_state)
)
async def no_update(callback: CallbackQuery):
    '''
    Хэндлер для обработки отказа от обновления данных.
    '''
    await callback.message.delete()
    await callback.message.answer(USER_TEXTS['no_update'])


@user_router.message(
    F.text == KEYBOARD_BUTTON_TEXTS['button_my_status'],
    StateFilter(default_state))
async def status_active(message: Message):
    '''
    Хэндлер для кнопки "Мой статус участия".
    '''
    user_id = message.from_user.id

    try:
        async with AsyncSessionLocal() as session:
            status_message = await create_text_status_active(session, user_id)

    except Exception as e:
        logger.error(f'Ошибка при получении статуса пользователя: {e}')
        await message.answer(ADMIN_TEXTS['db_error'])
        return

    try:
        await message.answer(status_message)

    except Exception as e:
        logger.error(f'Ошибка при отправке сообщения пользователю: {e}')
        await message.answer("Не удалось отправить статус. Попробуйте позже.")


@user_router.message(F.text == KEYBOARD_BUTTON_TEXTS['button_edit_meetings'],
                     StateFilter(default_state))
async def process_frequency(message: Message):
    try:
        async with AsyncSessionLocal() as session:
            user_id = message.from_user.id
            result = await session.execute(
                select(User.pairing_interval).where(
                    User.telegram_id == user_id
                )
            )

            pairing_interval = result.scalars().first()

            if pairing_interval is None:
                data_text = await create_text_with_interval(
                    session, USER_TEXTS['no_interval'], user_id
                )
            else:
                data_text = await create_text_with_interval(
                    session, USER_TEXTS['user_confirm_changing_interval'],
                    user_id
                )

    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        await message.answer(ADMIN_TEXTS['db_error'])

    try:
        await message.answer(
                text=data_text,
                reply_markup=generate_inline_confirm_change_interval()
            )
    except Exception as e:
        logger.error(f'Ошибка при отправке сообщения пользователю: {e}')
        await message.answer("Не удалось отправить статус. Попробуйте позже.")


@user_router.callback_query(
    lambda c: c.data.startswith('confirm_changing_interval'),
    StateFilter(default_state)
)
async def handle_callback_query_yes(callback: CallbackQuery):
    await callback.message.delete()
    try:
        async with AsyncSessionLocal() as session:
            formatted_text = await create_text_for_select_an_interval(
                session, USER_TEXTS['update_frequency']
            )

            reply_markup = await generate_inline_interval(session)

            await callback.message.answer(
                formatted_text,
                reply_markup=reply_markup
            )

    except SQLAlchemyError as e:
        logger.error(f'Ошибка при работе с базой данных: {e}')
        await callback.answer(ADMIN_TEXTS['db_error'])


@user_router.callback_query(
    lambda c: c.data.startswith('new_interval:') or c.data.startswith(
        'change_interval'
    ),
    StateFilter(default_state)
)
async def process_set_or_change_interval(callback: CallbackQuery):
    '''
    Хэндлер срабатывает на нажатие пользователем инлайн-кнопки
    с выбором частоты встреч или установкой частоты встреч по умолчанию.
    '''
    user_id = callback.from_user.id

    try:
        async with AsyncSessionLocal() as session:
            if callback.data.startswith('new_interval:'):
                _, new_interval = parse_callback_data(callback.data)
            else:
                new_interval = None

            await set_new_user_interval(session, user_id, new_interval)

            data_text = await create_text_with_interval(
                session,
                USER_TEXTS['success_new_interval'],
                user_id
            )

    except ValueError as ve:
        logger.error(f'Ошибка значения: {ve}')
        await callback.answer(
            "Произошла ошибка при обработке данных. "
            "Пожалуйста, попробуйте еще раз."
        )
        return

    except SQLAlchemyError as e:
        logger.error(f'Ошибка при работе с базой данных: {e}')
        await callback.answer(ADMIN_TEXTS['db_error'])
        return  # Завершаем выполнение функции после обработки ошибки

    try:
        # Отправляем сообщение пользователю
        if isinstance(callback.message, Message):
            await callback.message.edit_text(text=data_text)

    except Exception as e:
        logger.error(f'Ошибка при отправке сообщения пользователю: {e}')
        await callback.answer("Не удалось обновить статус. Попробуйте позже.")


@user_router.callback_query(
    lambda c: c.data.startswith('cancel_changing_interval')
)
async def handle_callback_query_no(callback: CallbackQuery):
    '''
    Обрабатывает нажатие на инлайн кнопку 'нет'
    во время изминения интервала встреч.
    '''
    try:
        async with AsyncSessionLocal() as session:
            user_id = callback.from_user.id
            data_text = await create_text_with_default_interval(
                session, USER_TEXTS['user_default_interval'], user_id
            )
        if isinstance(callback.message, Message):
            await callback.message.edit_text(text=data_text)

    except SQLAlchemyError as e:
        logger.error(f'Ошибка при работе с базой данных: {e}')
        await callback.answer(ADMIN_TEXTS['db_error'])


@user_router.message(F.text == KEYBOARD_BUTTON_TEXTS['button_how_it_works'])
async def text_random_coffee(message: Message):
    '''
    Выводит текст о том как работает Random_coffee
    '''
    async with AsyncSessionLocal() as session:
        text = await create_text_random_coffee(session)
        await message.answer(text)


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
    await message.answer('Я не знаю такой командыrandom_coffee_bot. '
                         'Пожалуйста, используй клавиатуру.')
