import logging

from aiogram import F, Router
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardRemove
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy import select, or_, desc, update

from database.db import AsyncSessionLocal
from database.models import User, Pair, Feedback
from filters.admin_filters import AdminCallbackFilter, AdminMessageFilter
from services.user_service import (create_user,
                                   delete_user,
                                   get_user_by_telegram_id,
                                   set_user_active,
                                   update_user_field)
from texts import TEXTS
from bot import save_comment
from keyboards.user_buttons import (
    create_active_user_keyboard,
    create_activate_keyboard,
    create_deactivate_keyboard,
    create_inactive_user_keyboard
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
    lambda message: message.text == "⏸️ Приостановить участие",
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


@user_router.message(lambda message: message.text == "▶️ Возобновить участие",
                     StateFilter(default_state)
                     )
async def resume_participation(message: Message, state: FSMContext):
    """Хэндлер для возобновления участия пользователя."""
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


@user_router.message(F.text)
async def fallback_handler(message: Message):
    await message.answer('Я не знаю такой команды. '
                         'Пожалуйста, используй клавиатуру.')


class FeedbackStates(StatesGroup):
    waiting_for_feedback_decision = State()
    waiting_for_comment_decision = State()
    writing_comment = State()

# --- Инлайн-кнопки ---
def meeting_question_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data="meeting_yes")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="meeting_no")]
    ])

def comment_question_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Оставить комментарий", callback_data="leave_comment")],
        [InlineKeyboardButton(text="⏭️ Без комментария", callback_data="no_comment")]
    ])


# --- Ответ: Да/Нет встреча ---
@user_router.callback_query(F.data.in_(["meeting_yes", "meeting_no"]))
async def process_meeting_feedback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data == "meeting_no":
        await callback.message.answer("Спасибо за информацию!")
        await state.clear()
    else:
        await callback.message.answer("Хотите оставить комментарий?", reply_markup=comment_question_kb())
        await state.set_state(FeedbackStates.waiting_for_comment_decision)

# --- Ответ: Комментарий или нет ---
@user_router.callback_query(F.data.in_(["leave_comment", "no_comment"]))
async def process_comment_choice(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data == "no_comment":
        await callback.message.answer("Спасибо! Отзыв учтён ✅")
        await state.clear()
    else:
        await callback.message.answer("Введите комментарий.")
        await state.set_state(FeedbackStates.writing_comment)

# --- Обработка комментария ---
@user_router.message(FeedbackStates.writing_comment, F.text)
async def receive_comment(message: types.Message, state: FSMContext, **kwargs):
    session_maker = kwargs['session']  # <- получаем из workflow_data
    user_id = message.from_user.id
    comment_text = message.text

    status_msg = await save_comment(user_id, comment_text, session_maker)
    await message.answer(status_msg)
    await state.clear()

# --- Обработка /cancel ---
# @user_router.message(F.text == "/cancel")
# async def cancel_feedback(message: types.Message, state: FSMContext):
#     await state.clear()
#     await message.answer("Действие отменено ❌")