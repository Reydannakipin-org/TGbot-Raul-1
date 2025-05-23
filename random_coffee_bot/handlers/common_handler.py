import logging

from aiogram import F, Router
from aiogram.exceptions import (AiogramError,
                                TelegramAPIError,
                                TelegramBadRequest,
                                TelegramForbiddenError,
                                TelegramNetworkError,
                                TelegramRetryAfter)
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import CallbackQuery, ErrorEvent, Message
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import User, Feedback
from keyboards.user_buttons import (comment_question_kb,
                                    confirm_edit_comment_kb)
from services.user_service import parse_callback_data
from states.user_states import CommentStates
from texts import (
    TEXTS,
    KEYBOARD_BUTTON_TEXTS,
    USER_TEXTS,
    ADMIN_TEXTS
)


logger = logging.getLogger(__name__)

common_router = Router()


# --- Ответ: Да/Нет встреча ---
@common_router.callback_query(F.data.startswith("meeting_yes") | F.data.startswith("meeting_no"),
                              StateFilter(default_state))
async def process_meeting_feedback(callback: CallbackQuery):
    await callback.answer()
    data = callback.data
    _, pair_id_str = parse_callback_data(callback.data)
    pair_id = int(pair_id_str)
    current_text = callback.message.text or ''
    telegram_user_id = callback.from_user.id

    async with AsyncSessionLocal() as session:
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

        if existing_feedback:
            await callback.message.answer('Информация об этой встрече уже записана.')
            return

        if data.startswith("meeting_no"):
            feedback = Feedback(pair_id=pair_id, user_id=user_id, did_meet=False)
            session.add(feedback)
            await session.commit()
            await callback.message.edit_text(f'{current_text}\n\n〰️\nТвой ответ: нет')
            await callback.message.answer('✅ Спасибо за информацию!')
            return

        elif data.startswith("meeting_yes"):
            feedback = Feedback(pair_id=pair_id, user_id=user_id, did_meet=True)
            session.add(feedback)
            await session.commit()
            await callback.message.edit_text(f'{current_text}\n\n〰️\nТвой ответ: да')
            await callback.message.answer(
                'Хочешь оставить комментарий об этой встрече?',
                reply_markup=comment_question_kb(feedback.id)
            )


# --- Ответ: Комментарий или нет ---
@common_router.callback_query(F.data.startswith("leave_comment") | F.data.startswith("no_comment"),
                            StateFilter(default_state))
async def process_comment_choice(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    action, feedback_id_str = parse_callback_data(callback.data)
    feedback_id = int(feedback_id_str)

    if action == "no_comment":
        await callback.message.edit_text('✅ Спасибо за информацию!')
        return

    else:
        await state.set_state(CommentStates.waiting_for_comment)
        await state.update_data(feedback_id=feedback_id)
        await callback.message.delete()
        await callback.message.answer(
            'Отправь текст комментария.\n\n'
            'Если ты передумал оставлять комментарий, отправь /cancel.')


@common_router.message(CommentStates.waiting_for_comment, F.text == "/cancel")
async def cancel_feedback(message: Message, state: FSMContext):
    data = await state.get_data()
    feedback_id = data.get("feedback_id")
    try:
        async with AsyncSessionLocal() as session:
            feedback_query = await session.execute(
                select(Feedback).where(Feedback.id == feedback_id)
            )
            existing_feedback = feedback_query.scalar()

            if not existing_feedback:
                await message.answer("Извини, произошла ошибка при записи комментария. Сообщи об этом админу.")
                await state.clear()
                return

            existing_feedback.comment = None
            await session.commit()
    except SQLAlchemyError:
        logger.error('Ошибка при работе с базой данных')
        await message.answer(ADMIN_TEXTS['db_error'])
        return
    await state.clear()
    await message.answer('Встреча оставлена без комментария.')


# --- Обработка комментария ---
@common_router.message(CommentStates.waiting_for_comment, F.text)
async def receive_comment(message: Message, state: FSMContext):
    if message.text in KEYBOARD_BUTTON_TEXTS.values():
        await message.answer(ADMIN_TEXTS['no_kb_buttons'])
        await message.answer(
            'Отправь текст комментария.\n\n'
            'Если ты передумал оставлять комментарий, отправь /cancel.')
        return

    comment_text = message.text.strip()

    data = await state.get_data()
    feedback_id = data.get("feedback_id")
    if feedback_id is None:
        await message.answer("Извини, произошла ошибка при записи комментария. Сообщи об этом админу.")
        await state.clear()
        return

    async with AsyncSessionLocal() as session:

        feedback_query = await session.execute(
            select(Feedback).where(Feedback.id == feedback_id)
        )
        existing_feedback = feedback_query.scalar_one_or_none()

        if not existing_feedback:
            await message.answer("Извини, произошла ошибка при записи комментария. Сообщи об этом админу.")
            await state.clear()
            return

        try:
            existing_feedback.comment = comment_text
            await session.commit()
        except SQLAlchemyError:
            logger.error('Ошибка при работе с базой данных')
            await message.answer(ADMIN_TEXTS['db_error'])
            await state.clear()
            return

        await state.clear()
        await message.answer(f'Ты хочешь оставить комментарий:\n\n{comment_text}',
                             reply_markup=confirm_edit_comment_kb(feedback_id))


@common_router.message(CommentStates.waiting_for_comment, ~F.text)
async def receive_no_comment(message: Message, state: FSMContext):
    await message.answer(USER_TEXTS['reject_no_text_comment'])


@common_router.callback_query(F.data.startswith("confirm_edit") | F.data.startswith("save_comment"),
                            StateFilter(default_state))
async def handle_edit_decision(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    action, feedback_id_str = parse_callback_data(callback.data)
    feedback_id = int(feedback_id_str)

    if action == "save_comment":
        await callback.message.edit_text("Комментарий сохранен ✅")
        return

    await state.set_state(CommentStates.waiting_for_comment)
    await state.update_data(feedback_id=feedback_id)
    await callback.message.delete()
    await callback.message.answer(
        'Отправь текст комментария.\n\n'
        'Если ты передумал оставлять комментарий, отправь /cancel.')


@common_router.callback_query(F.data.startswith('cancel_comment'),
                            StateFilter(default_state))
async def proccess_cancel_comment(callback: CallbackQuery, state: FSMContext):
    _, feedback_id_str = parse_callback_data(callback.data)
    feedback_id = int(feedback_id_str)
    try:
        async with AsyncSessionLocal() as session:
            feedback_query = await session.execute(
                select(Feedback).where(Feedback.id == feedback_id)
            )
            existing_feedback = feedback_query.scalar()

            if not existing_feedback:
                await callback.message.answer("Извини, произошла ошибка при записи комментария. Сообщи об этом админу.")
                await state.clear()
                return

            existing_feedback.comment = None
            await session.commit()
    except SQLAlchemyError:
        logger.error('Ошибка при работе с базой данных')
        await callback.message.answer(ADMIN_TEXTS['db_error'])
        return
    await state.clear()
    await callback.message.edit_text('Встреча оставлена без комментария.')


@common_router.callback_query()
async def missed_callback(callback: CallbackQuery):
    """
    Хэндлер будет обрабатывать коллбеки, которые устарели или потеряли
    данные из-за перезапуска бота.
    """
    try:
        if isinstance(callback.message, Message):
            await callback.message.delete()
    except Exception:
        pass
    await callback.answer(TEXTS['old_callback'], show_alert=True)



@common_router.error()
async def global_error_handler(event: ErrorEvent) -> bool:
    """
    Глобальный хэндлер ошибок. Возвращает True, чтобы aiogram не прокидывал
    исключение дальше, и бот не падал.
    """
    chat_id = None
    if event.update.message:
        chat_id = event.update.message.chat.id
    elif event.update.callback_query and event.update.callback_query.message:
        chat_id = event.update.callback_query.message.chat.id

    if isinstance(event.exception, TelegramRetryAfter):
        logger.warning('Превышен лимит запросов')

    elif isinstance(event.exception, TelegramForbiddenError):
        logger.error(f'Сообщение не доставлено. '
                     f'Юзер {chat_id or "неизвестный"} заблокировал бота.')

    elif isinstance(event.exception, TelegramBadRequest):
        text = str(event.exception).lower()
        if ('message is not modified' in text
                or 'message to edit not found' in text):
            return True
        logger.error(f'BadRequest при работе с Telegram API: {event.exception}')

    elif isinstance(event.exception, TelegramNetworkError):
        logger.warning(f'Проблемы с интернет-соединением при запросе '
                       f'к Telegram API: {event.exception}')

    elif isinstance(event.exception, TelegramAPIError):
        logger.exception(f'TelegramAPIError: {event.exception}')

    elif isinstance(event.exception, AiogramError):
        logger.exception(f'Aiogram ошибка: {event.exception}')

    else:
        logger.exception(f'Необработанное исключение: {event.exception}')

    return True
