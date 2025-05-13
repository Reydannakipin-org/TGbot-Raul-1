import logging
import os
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from aiogram import F, Router, types
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import CallbackQuery, Message
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select

# Импорт базы данных и сервисов
from database.db import AsyncSessionLocal
from database.models import User, Feedback
from bot import CommentStates, save_comment
from services.user_service import (
    create_user,
    create_text_for_select_an_interval,
    create_text_with_default_interval,
    create_text_random_coffee,
    create_text_status_active,
    get_user_by_telegram_id,
    parse_callback_data,
    set_new_user_interval,
    set_user_active,
    update_user_field,
    upload_to_drive,
    create_text_with_interval,
)

# Импорт фильтров и состояний
from filters.admin_filters import AdminCallbackFilter, AdminMessageFilter
from states.user_states import FSMUserForm

from keyboards.user_buttons import (
    create_active_user_keyboard,
    create_activate_keyboard,
    create_deactivate_keyboard,
    create_inactive_user_keyboard,
    generate_inline_confirm_change_interval,
    generate_inline_interval,
    yes_or_no_keyboard,
    meeting_question_kb,
    comment_question_kb,
    confirm_edit_comment_kb
)

# Импорт текстов
from texts import (
    TEXTS,
    KEYBOARD_BUTTON_TEXTS,
    USER_TEXTS,
    ADMIN_TEXTS,
    NAME_PATTERN,
)
from services.constants import DATE_FORMAT_1


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
    logger.debug('Вошли в хэндлер, обрабатывающий команду /start')
    if message.from_user is None:
        return await message.answer(TEXTS['error_access'])

    user_telegram_id = message.from_user.id

    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_by_telegram_id(session, user_telegram_id)

            if user is None:
                logger.debug('Пользователя нет в БД. Приступаем к добавлению.')
                user = await create_user(session,
                                         user_telegram_id,
                                         message.from_user.username,
                                         message.from_user.first_name,
                                         message.from_user.last_name)
                logger.debug(f'Пользователь добавлен в БД. '
                            f'Имя {user.first_name}. Фамилия {user.last_name}')
                await message.answer(TEXTS['start'])
                await message.answer(TEXTS['ask_first_name'])
                await state.set_state(FSMUserForm.waiting_for_first_name)
            else:
                if not user.is_active:
                    await set_user_active(session, user_telegram_id, True)
                    logger.debug('Статус пользователя изменен на Активный.')
                await message.answer(
                    TEXTS['re_start'],
                    reply_markup=create_active_user_keyboard())
    except SQLAlchemyError as e:
        logger.error('Ошибка при работе с базой данных: %s', str(e))
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

    first_name = message.text.strip()
    logger.debug(f'Получено сообщение в качестве имени: {first_name}')

    try:
        async with AsyncSessionLocal() as session:
            ok = await update_user_field(session,
                                         user_telegram_id,
                                         'first_name',
                                         first_name)
            if not ok:
                await message.answer(TEXTS['error_find_user'])
                return await state.clear()

            logger.debug('Имя сохранено.')

        await message.answer(TEXTS['ask_last_name'])
        await state.set_state(FSMUserForm.waiting_for_last_name)
    except SQLAlchemyError:
        logger.error('Ошибка при сохранении имени')
        await message.answer(TEXTS['db_error'])


@user_router.message(StateFilter(FSMUserForm.waiting_for_first_name))
async def warning_not_first_name(message: Message, state: FSMContext):
    '''
    Хэндлер срабатывает в состоянии, когда мы ждем от пользователя его имя,
    и оно введено неверно. Просим пользователя ввести заново.
    '''
    logger.debug(f'Отказ. Получено сообщение в качестве имени: {message.text}')
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

    last_name = message.text.strip()
    logger.debug(f'Получено сообщение в качестве фамилии: {last_name}')

    try:
        async with AsyncSessionLocal() as session:
            ok = await update_user_field(session,
                                         user_telegram_id,
                                         'last_name',
                                         last_name)
            if not ok:
                await message.answer(TEXTS['error_find_user'])
                return await state.clear()

            logger.debug('Фамилия сохранена')

        keyboard = create_active_user_keyboard()

        await message.answer(
            TEXTS['thanks_for_answers'], reply_markup=keyboard
        )
        await state.clear()
    except SQLAlchemyError:
        logger.error('Ошибка при сохранении фамилии')
        await message.answer(TEXTS['db_error'])


@user_router.message(StateFilter(FSMUserForm.waiting_for_last_name))
async def warning_not_last_name(message: Message, state: FSMContext):
    '''
    Хэндлер срабатывает в состоянии, когда мы ждем от пользователя его фамилию,
    и она введена неверно. Просим пользователя ввести заново.
    '''
    logger.debug(
        f'Отказ. Получено сообщение в качестве фамилии: {message.text}'
    )
    await message.answer(TEXTS['not_last_name'])


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
        logger.error("Ошибка при запросе пользователя для паузы участия.")
        return await message.answer(TEXTS['db_error'])

    if user is None:
        return await message.answer(TEXTS['error_find_user'])

    if user.is_active:
        await message.answer(
            USER_TEXTS['confirm_pause'],
            reply_markup=create_deactivate_keyboard()
        )
    else:
        await message.answer(USER_TEXTS['status_inactive'])


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
            USER_TEXTS['confirm_resume'],
            reply_markup=create_activate_keyboard()
        )
    else:
        await message.answer(USER_TEXTS['status_active'])


@user_router.callback_query(lambda c: c.data.startswith("confirm_deactivate_"),
                            StateFilter(default_state))
async def process_deactivate_confirmation(callback_query: CallbackQuery):
    """
    Хэндлер для обработки подтверждения приостановки участия.
    """
    telegram_id = callback_query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await get_user_by_telegram_id(session, telegram_id)

        if user is None:
            await callback_query.answer(
                USER_TEXTS['user_not_found'], show_alert=True
            )
            return

        try:
            await callback_query.message.delete()

            if callback_query.data == "confirm_deactivate_yes":
                if user.is_active:
                    await set_user_active(session, telegram_id, False)
                    await callback_query.message.answer(
                        USER_TEXTS['participation_paused'],
                        reply_markup=create_inactive_user_keyboard()
                    )
                else:
                    await callback_query.answer(
                        USER_TEXTS['already_paused'],
                        show_alert=True
                    )

            elif callback_query.data == "confirm_deactivate_no":
                await callback_query.answer(
                    USER_TEXTS['status_not_changed'],
                    show_alert=True
                )

            await callback_query.answer()

        except Exception as e:
            logger.error(f"Произошла ошибка: {e}")
            await callback_query.answer(
                USER_TEXTS['error_occurred'],
                show_alert=True
            )



@user_router.callback_query(lambda c: c.data.startswith("confirm_activate_"),
                            StateFilter(default_state))
async def process_activate_confirmation(callback_query: CallbackQuery):
    """
    Хэндлер для обработки подтверждения возобновления участия.
    """
    telegram_id = callback_query.from_user.id

    async with AsyncSessionLocal() as session:
        user = await get_user_by_telegram_id(session, telegram_id)

        if user is None:
            await callback_query.answer(
                USER_TEXTS['user_not_found'],
                show_alert=True
            )
            return

        try:
            await callback_query.message.delete()

            if callback_query.data == "confirm_activate_yes":
                if not user.is_active:
                    await set_user_active(session, telegram_id, True)
                    await callback_query.message.answer(
                        USER_TEXTS['participation_resumed'],
                        reply_markup=create_active_user_keyboard()
                    )
                else:
                    await callback_query.answer(
                        USER_TEXTS['status_active'],
                        show_alert=True
                    )

            elif callback_query.data == "confirm_activate_no":
                await callback_query.answer(
                    USER_TEXTS['status_not_changed'],
                    show_alert=True
                )

            await callback_query.answer()

        except Exception as e:
            logger.error(f"Произошла ошибка: {e}")
            await callback_query.answer(
                USER_TEXTS['error_occurred'],
                show_alert=True
            )


# --- Ответ: Да/Нет встреча ---
@user_router.callback_query(F.data.startswith("meeting_yes") | F.data.startswith("meeting_no"))
async def process_meeting_feedback(callback: types.CallbackQuery, session_maker):
    await callback.answer()
    data = callback.data
    _, pair_id_str = parse_callback_data(callback.data)
    pair_id = int(pair_id_str)

    telegram_user_id = callback.from_user.id

    async with session_maker() as session:
        user = await session.execute(select(User).filter_by(telegram_id=telegram_user_id))
        user = user.scalar_one_or_none()

        if user is None:
            await callback.message.answer("Пользователь не найден.")
            return

        user_id = user.id

        # Проверяем, существует ли уже отзыв для этой пары и пользователя
        existing_feedback = await session.execute(
            select(Feedback).filter_by(pair_id=pair_id, user_id=user_id)
        )
        existing_feedback = existing_feedback.scalar_one_or_none()

        if data.startswith("meeting_no"):
            if existing_feedback:
                # Если отзыв с ответом "нет" уже существует, уведомляем пользователя
                if existing_feedback.did_meet is False:
                    await callback.message.answer("Ты уже оставил отзыв с ответом 'нет' для этой встречи.")
                    return
                if existing_feedback.did_meet is True:
                    await callback.message.answer("Ты уже оставил отзыв с ответом 'да' для этой встречи и не можешь поменять на 'нет'.")
                    return
                else:
                    # Если отзыв с ответом "да" существует, обновляем его
                    existing_feedback.did_meet = False
                    existing_feedback.comment = None  # Очищаем комментарий, если был
                    await session.commit()

            else:
                # Если отзыва нет, создаём новый
                feedback = Feedback(pair_id=pair_id, user_id=user_id, did_meet=False)
                session.add(feedback)
                await session.commit()

            await callback.message.edit_text("Спасибо за информацию!")


        elif data.startswith("meeting_yes"):
            if existing_feedback:
                if existing_feedback.did_meet is not True:
                    existing_feedback.did_meet = True
                    await session.commit()

            else:
                feedback = Feedback(pair_id=pair_id, user_id=user_id, did_meet=True)
                session.add(feedback)
                await session.commit()

            await callback.message.edit_text(
                "Хочешь оставить комментарий?",
                reply_markup=comment_question_kb(pair_id)

            )


# --- Ответ: Комментарий или нет ---
@user_router.callback_query(F.data.startswith("leave_comment") | F.data.startswith("no_comment"))
async def process_comment_choice(callback: types.CallbackQuery, state: FSMContext, session_maker):
    await callback.answer()
    data = callback.data
    action, pair_id = data.split(":")

    telegram_user_id = callback.from_user.id

    async with session_maker() as session:
        user = await session.execute(select(User).filter_by(telegram_id=telegram_user_id))
        user = user.scalar_one_or_none()

        if user is None:
            await callback.message.answer("Пользователь не найден.")
            return

        user_id = user.id
        pair_id = int(pair_id)

        # Проверяем, существует ли уже отзыв без комментария
        existing_feedback = await session.execute(
            select(Feedback).filter_by(pair_id=pair_id, user_id=user_id)
        )
        existing_feedback = existing_feedback.scalar_one_or_none()

        if action == "no_comment":
            if existing_feedback:
                # Если отзыв без комментария уже существует
                await callback.message.answer("Спасибо! Отзыв учтён ✅")
                return

            feedback = Feedback(pair_id=pair_id, user_id=user_id, did_meet=True, comment=None)
            session.add(feedback)
            await session.commit()

            await state.clear()
            await callback.message.answer("Спасибо! Отзыв учтён ✅")

        else:
            # Если выбран вариант с комментарием, запускаем ожидание ввода
            await state.set_state(CommentStates.waiting_for_comment)
            await state.update_data(pair_id=pair_id)
            await callback.message.answer("Введи комментарий (или отправь /cancel, чтобы отменить)")
#11111
@user_router.callback_query(F.data.startswith("confirm_edit") | F.data.startswith("cancel_edit"))
async def handle_edit_decision(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await callback.answer()
    data = callback.data
    action, pair_id_str = data.split(":")
    pair_id = int(pair_id_str)
    session_maker = kwargs["session_maker"]
    user_id = callback.from_user.id

    if action == "cancel_edit":
        await state.clear()
        await callback.message.edit_reply_markup()
        await callback.message.answer("Замена коментария отменена ✅")
        return

    # confirm_edit
    state_data = await state.get_data()
    temp_comment = state_data.get("temp_comment")
    if not temp_comment:
        await callback.message.answer("Ошибка: временный комментарий не найден.")
        await state.clear()
        return

    status_msg = await save_comment(user_id, temp_comment, session_maker, pair_id, force_update=True)

    await state.clear()

    await callback.message.edit_reply_markup()
    await callback.message.answer(status_msg)

#--- Обработка /cancel ---
@user_router.message(CommentStates.waiting_for_comment, F.text == "/cancel")
async def cancel_feedback(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено ❌")


# --- Обработка комментария ---
@user_router.message(CommentStates.waiting_for_comment, F.text)
async def receive_comment(message: types.Message, state: FSMContext, **kwargs):
    session_maker = kwargs["session_maker"]
    user_id = message.from_user.id
    comment_text = message.text.strip()

    button_texts = ['📋 Список участников',
                    '👥 Управление участниками',
                    '📊 Выгрузить в гугл таблицу',
                    '🤝 Изменить интервал',
                    '✏️ Изменить мои данные',
                    '📊 Мой статус участия',
                    '🗓️ Изменить частоту встреч',
                    '⏸️ Приостановить участие',
                    '❓ Как работает Random Coffee?',
                    '▶️ Возобновить участие',
                    ]

    if comment_text in button_texts:
        await message.answer("Пожалуйста, введи комментарий вручную, а не выбирай кнопку.")
        return

    data = await state.get_data()
    pair_id = data.get("pair_id")
    if pair_id is None:
        await message.answer("Извини, произошла ошибка при записи комментария. Сообщи об этом админу.")
        await state.clear()
        return

    async with session_maker() as session:
        result_user = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result_user.scalar()
        if user is None:
            await message.answer("Пользователь не найден.")
            return

        feedback_query = await session.execute(
            select(Feedback).where(Feedback.user_id == user.id, Feedback.pair_id == pair_id)
        )
        existing_feedback = feedback_query.scalar()

    if existing_feedback and existing_feedback.comment:
        # Сохраняем временно комментарий и спрашиваем подтверждение
        await state.update_data(temp_comment=comment_text)
        await message.answer(
            "Ты уже оставлял комментарий для этой встречи.\nХочешь изменить его?",
            reply_markup=confirm_edit_comment_kb(pair_id)
        )
        return

    # Иначе сохраняем
    status_msg = await save_comment(user_id, comment_text, session_maker, pair_id)
    await message.answer(status_msg)
    await state.clear()


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
            user = await get_user_by_telegram_id(session, telegram_id)

            if user is None:
                await message.answer(USER_TEXTS['user_not_found'])
                return

            user_message = (
                f"Твои текущие данные: \n"
                f"Имя: {user.first_name} \n"
                f"Фамилия: {user.last_name} \n\n"
                "Ты уверен, что хочешь изменить их?"
            )

        await message.answer(
            user_message,
            reply_markup=yes_or_no_keyboard()
        )

    except SQLAlchemyError:
        logger.error('Ошибка при работе с базой данных')
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
    await callback.message.answer(USER_TEXTS['enter_new_name'])
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
        await message.answer(USER_TEXTS['status_not_sent'])


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
        logger.error('Ошибка при работе с базой данных')
        await message.answer(ADMIN_TEXTS['db_error'])

    try:
        await message.answer(
                text=data_text,
                reply_markup=generate_inline_confirm_change_interval()
            )
    except Exception as e:
        logger.error(f'Ошибка при отправке сообщения пользователю: {e}')
        await message.answer(USER_TEXTS['status_not_sent'])


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

            reply_markup = generate_inline_interval()

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
                _, new_interval_str = parse_callback_data(callback.data)
                try:
                    new_interval = int(new_interval_str.strip())
                except ValueError:
                    new_interval = None
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
        await callback.answer(USER_TEXTS['data_processing_error'])
        return

    except SQLAlchemyError as e:
        logger.error(f'Ошибка при работе с базой данных: {e}')
        await callback.answer(ADMIN_TEXTS['db_error'])
        return

    try:
        if isinstance(callback.message, Message):
            await callback.message.edit_text(text=data_text)

    except Exception as e:
        logger.error(f'Ошибка при отправке сообщения пользователю: {e}')
        await callback.answer(USER_TEXTS['status_update_failed'])


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


@user_router.message(
    F.text == KEYBOARD_BUTTON_TEXTS['button_send_photo'],
    StateFilter(default_state)
)
async def request_photo_handler(message: Message, state: FSMContext):
    '''
    Проверяет нажал ли пользователь на кнопку отправить фото.
    '''
    await message.answer(USER_TEXTS['send_photo'])
    await state.set_state(FSMUserForm.waiting_for_photo)


@user_router.message(
    Command("cancel"),
    StateFilter(FSMUserForm.waiting_for_photo)
)
async def cancel_handler(message: Message, state: FSMContext):
    '''
    С помощью команды /cancel можно выйти из состояния отправки фото.
    '''
    await state.clear()
    await message.answer(USER_TEXTS['cancellation_send_photo'])


@user_router.message(StateFilter(FSMUserForm.waiting_for_photo))
async def photo_handler(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer(USER_TEXTS['error_send_photo'])
        return

    photo = message.photo[-1]
    file_id = photo.file_id
    file = await message.bot.get_file(file_id)
    destination = f'./{file_id}.jpg'

    await message.bot.download_file(file.file_path, destination=destination)

    user_name = message.from_user.full_name
    current_time = datetime.now().strftime(DATE_FORMAT_1)

    file_name = f"{current_time} - {user_name}.jpg"

    upload_result = upload_to_drive(destination, file_name)

    if upload_result:
        await message.answer(USER_TEXTS['photo_sent_successfully'])
    else:
        await message.answer(USER_TEXTS['photo_upload_error'])

    os.remove(destination)
    await state.clear()


@user_router.message(F.text)
async def fallback_handler(message: Message):
    '''
    Этот хэндлер должен быть самым последним,
    так как он улавливает любую команду которую не смогли уловить
    другие хэндлеры.
    '''
    await message.answer(USER_TEXTS['no_now'])
