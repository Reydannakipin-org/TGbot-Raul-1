import logging

from aiogram import Router, F, types
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from sqlalchemy import select, or_, desc, update
from sqlalchemy.ext.asyncio import async_sessionmaker
from aiogram.enums.parse_mode import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db import AsyncSessionLocal
from database.models import User, Pair, Feedback
from texts import TEXTS
from bot import save_comment

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