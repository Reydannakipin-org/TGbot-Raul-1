from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta, date
from random import shuffle
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import User, Pair, Setting, Feedback
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import random
from collections import defaultdict
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
import asyncio
from aiogram import Dispatcher
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from apscheduler.triggers.cron import CronTrigger
from apscheduler.job import Job

scheduler = AsyncIOScheduler()

class FeedbackStates(StatesGroup):
    waiting_for_feedback_decision = State()
    waiting_for_comment_decision = State()
    writing_comment = State()

class CommentStates(StatesGroup):
    waiting_for_comment = State()

def meeting_question_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data="meeting_yes")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="meeting_no")]
    ])

async def prompt_user_comment(user_id: int):
    # Установим FSM состояние
    state = FSMContext(bot.storage, bot, user_id)
    await state.set_state(CommentStates.waiting_for_comment)

    await bot.send_message(user_id, "Привет! Пожалуйста, оставь комментарий о последней встрече ☕️")

async def get_users_ready_for_matching(session: AsyncSession) -> list[User]:
    """Выбираем пользователей для участия в формировании пар по правилам."""

    result = await session.execute(select(Setting).filter_by(key='global_interval'))
    setting = result.scalars().first()
    global_interval = setting.value if setting else 2

    result = await session.execute(select(User))
    users = result.scalars().all()
    selected_users = []
    today = datetime.utcnow().date()

    for user in users:
        # Пропускаем, если пользователь в паузе
        if user.pause_until and user.pause_until > today:
            continue

        user_interval = user.pairing_interval or global_interval

        # Пропускаем неактивных, но обновляем future_meeting при необходимости
        if not user.is_active:
            if user_interval > global_interval and user.future_meeting == 0:
                user.future_meeting = 1
            continue  # Не добавляем неактивных в пары вообще

        # Основная логика для активных пользователей
        if global_interval >= user_interval:
            user.future_meeting = 0
            selected_users.append(user)
        elif user.future_meeting == 1:
            user.future_meeting = 0
            selected_users.append(user)
        else:
            user.future_meeting = 1

    await session.commit()
    return selected_users


async def generate_unique_pairs(session, users: list[User]) -> list[Pair]:
    """Формирует пары, минимизируя количество повторений."""

    # Загружаем историю всех пар
    result = await session.execute(select(Pair.user1_id, Pair.user2_id, Pair.user3_id))
    history = defaultdict(int)  # (min_id, max_id) -> count

    for row in result.fetchall():
        ids = [row.user1_id, row.user2_id]
        if row.user3_id:
            ids.append(row.user3_id)
        ids = sorted(ids)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                history[(ids[i], ids[j])] += 1

    # Подготовка
    random.shuffle(users)
    user_ids = [u.id for u in users]
    user_map = {u.id: u for u in users}
    used = set()
    pairs = []

    # Сортируем возможные пары по числу повторений
    possible_pairs = []
    for i in range(len(user_ids)):
        for j in range(i + 1, len(user_ids)):
            u1, u2 = user_ids[i], user_ids[j]
            key = tuple(sorted((u1, u2)))
            if u1 not in used and u2 not in used:
                possible_pairs.append((history[key], u1, u2))

    possible_pairs.sort()  # от самых редких к частым

    for _, u1, u2 in possible_pairs:
        if u1 not in used and u2 not in used:
            used.update([u1, u2])
            pairs.append((u1, u2))

    remaining = [uid for uid in user_ids if uid not in used]
    pair_objs = []

    # Сохраняем пары в БД
    for u1_id, u2_id in pairs:
        u1, u2 = user_map[u1_id], user_map[u2_id]
        pair = Pair(
            user1_id=u1.id, user2_id=u2.id,
            user1_username=u1.username,
            user2_username=u2.username,
            paired_at=datetime.utcnow()
        )
        u1.last_paired_at = datetime.utcnow()
        u2.last_paired_at = datetime.utcnow()
        session.add(pair)
        pair_objs.append(pair)

    if remaining:
        odd = user_map[remaining[0]]
        odd.last_paired_at = datetime.utcnow()
        if pair_objs:
            last_pair = pair_objs[-1]
            last_pair.user3_id = odd.id
            last_pair.user3_username = odd.username
            session.add(last_pair)
        else:
            print(f"⚠️ Один пользователь остался без пары: {odd.username or odd.id}")

    return pair_objs


async def notify_users_about_pairs(session: AsyncSession, pairs: list[Pair], bot: Bot):
    """Отправляет сообщения участникам пар через Telegram, используя HTML-ссылки с tg://user?id."""
    for pair in pairs:
        user_ids = [pair.user1_id, pair.user2_id]
        if pair.user3_id:
            user_ids.append(pair.user3_id)

        # Загружаем данные всех участников пары
        result = await session.execute(
            select(User.id, User.telegram_id, User.first_name, User.last_name).where(User.id.in_(user_ids))
        )
        user_data = {
            row.id: {
                "telegram_id": row.telegram_id,
                "first_name": row.first_name or "Пользователь",
                "last_name": row.last_name,
            }
            for row in result.fetchall()
        }

        for user_id in user_ids:
            user_info = user_data.get(user_id)
            if not user_info or not user_info["telegram_id"]:
                print(f"❗ Не удалось найти telegram_id для user_id={user_id}")
                continue

            # Формируем ссылки на партнёров
            partner_links = []
            for partner_id in user_ids:
                if partner_id == user_id:
                    continue
                partner = user_data.get(partner_id)
                if partner and partner["telegram_id"]:
                    name = f'{partner["first_name"]} {partner["last_name"]}'.strip()
                    link = f'<a href="tg://user?id={partner["telegram_id"]}">{name}</a>'
                    partner_links.append(link)
                else:
                    partner_links.append("неизвестный пользователь")

            partners_str = ", ".join(partner_links)

            message = (
                f"👥 Ваша пара на эту неделю:\n"
                f"{partners_str}\n\n"
                f"Свяжитесь друг с другом и договоритесь о встрече!"
            )

            try:
                await bot.send_message(chat_id=user_info["telegram_id"], text=message, parse_mode="HTML")
            except Exception as e:
                print(f"⚠️ Не удалось отправить сообщение для user_id={user_id}: {e}")



async def auto_pairing(session_maker, bot: Bot):
    async with session_maker() as session:
        users = await get_users_ready_for_matching(session)
        if len(users) < 2:
            print("❗ Недостаточно пользователей для формирования пар.")
            return

        # 💡 Новый способ формирования пар
        pairs = await generate_unique_pairs(session, users)

        await session.commit()
        print(f"✅ Сформировано {len(pairs)} пар.")

        await notify_users_about_pairs(session, pairs, bot)

async def save_comment(telegram_id: int, comment_text: str, session_maker: async_sessionmaker) -> str:
    async with session_maker() as session:
        # Получаем user по telegram_id
        result_user = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result_user.scalar()
        if user is None:
            return f"Пользователь с telegram_id {telegram_id} не найден"

        user_id = user.id

        # Ищем последнюю пару, где он есть
        result_pair = await session.execute(
            select(Pair)
            .where(or_(Pair.user1_id == user_id, Pair.user2_id == user_id, Pair.user3_id == user_id))
            .order_by(Pair.paired_at.desc())
        )
        pair = result_pair.scalars().first()

        if not pair:
            return "Ошибка: вы ещё не участвуете в паре 🤷"

        # Тут сохраняем комментарий
        pair_id = pair.id

        result_feedback = await session.execute(
            select(Feedback).where(Feedback.user_id == user_id, Feedback.pair_id == pair_id)
        )
        feedback = result_feedback.scalar()

        if feedback:
            feedback.comment = comment_text
            feedback.submitted_at = datetime.utcnow()
            feedback.did_meet = True
            status_msg = "Комментарий обновлён ✅"
        else:
            new_feedback = Feedback(
                pair_id=pair_id,
                user_id=user_id,
                comment=comment_text,
                did_meet=True,
                submitted_at=datetime.utcnow()
            )
            session.add(new_feedback)
            status_msg = "Спасибо за ваш комментарий ✅"

        await session.commit()
        return status_msg


async def start_feedback_prompt(bot: Bot, telegram_id: int, dispatcher: Dispatcher):
    fsm_context = dispatcher.fsm.get_context(user_id=telegram_id, chat_id=telegram_id, bot=bot)

    # Получаем текущее состояние
    state = await fsm_context.get_state()

    await bot.send_message(
        telegram_id,
        "Привет! Прошла ли встреча?",
        reply_markup=meeting_question_kb()  # Убедись, что у тебя есть функция meeting_question_kb()
    )

    await fsm_context.set_state(FeedbackStates.waiting_for_feedback_decision)

def show_next_runs(scheduler: AsyncIOScheduler):
    print("🔔 Расписание ближайших запусков задач:")

    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        print(f"🛠 Задача '{job.id}' запустится в: {next_run.strftime('%Y-%m-%d %H:%M:%S') if next_run else 'нет запланированного запуска'}")

async def schedule_feedback_jobs(bot: Bot, session_maker, dispatcher: Dispatcher):
    async def setup_jobs():
        async with session_maker() as session:
            setting_result = await session.execute(
                select(Setting.value).where(Setting.key == "global_interval")
            )
            setting_value = setting_result.scalar()
            interval_weeks = setting_value if setting_value is not None else 2
            interval_day = interval_weeks * 7 -3
            users_result = await session.execute(select(User.telegram_id).where(User.is_active == True))
            telegram_ids = users_result.scalars().all()

            for telegram_id in telegram_ids:
                scheduler.add_job(
                    start_feedback_prompt,
                    trigger=IntervalTrigger(days=interval_day),
                    args=[bot, telegram_id, dispatcher],
                    id=f"feedback_{telegram_id}",
                    replace_existing=True,
                )

        scheduler.add_job(
            auto_pairing,
            trigger=IntervalTrigger(weeks=interval_weeks),
            args=[session_maker, bot],
            id="auto_pairing_weekly"
        )

    # ⬇⬇⬇ Ждем выполнения setup_jobs перед стартом планировщика
    await setup_jobs()

    # Теперь можно запускать планировщик и печатать расписание
    if not scheduler.running:
        scheduler.start()

    show_next_runs(scheduler)


