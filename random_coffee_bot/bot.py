from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_EXECUTED
from apscheduler.jobstores.base import JobLookupError
from datetime import datetime, timedelta
from random import shuffle
import asyncio
import random
from collections import defaultdict
from keyboards.user_buttons import meeting_question_kb
from sqlalchemy import select, or_, and_, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from globals import job_context
from aiogram import Bot, Dispatcher
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.models import User, Pair, Setting, Feedback

scheduler = AsyncIOScheduler(
        jobstores={'default': SQLAlchemyJobStore(url='sqlite:///jobs.sqlite')},
        timezone='Europe/Moscow'
    )

class FeedbackStates(StatesGroup):
    writing_comment = State()

class CommentStates(StatesGroup):
    waiting_for_comment = State()


async def prompt_user_comment(user_id: int):
    # Установим FSM состояние
    state = FSMContext(bot.storage, bot, user_id)
    await state.set_state(CommentStates.waiting_for_comment)

    await bot.send_message(user_id, "Привет! Пожалуйста, оставь комментарий о последней встрече ☕️")

async def feedback_dispatcher_wrapper():
    bot, dispatcher, session_maker = job_context.get_context()
    await feedback_dispatcher_job(bot, session_maker)

async def auto_pairing_wrapper():
    bot, dispatcher, session_maker = job_context.get_context()
    await auto_pairing(session_maker, bot)

# async def reload_jobs_wrapper():
#     bot, dispatcher, session_maker = job_context.get_context()
#     await reload_scheduled_jobs(bot, session_maker, dispatcher)

# ласт пара
async def get_latest_pair_id_for_user(session: AsyncSession, user_id: int) -> int | None:
    result = await session.execute(
        select(Pair.id)
        .where(
            and_(
                or_(
                    Pair.user1_id == user_id,
                    Pair.user2_id == user_id,
                    Pair.user3_id == user_id
                ),
                Pair.paired_at < datetime.utcnow()  # только прошедшие
            )
        )
        .order_by(Pair.paired_at.desc())
    )
    pair_id = result.scalar_one_or_none()
    return pair_id

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

async def save_comment(
    telegram_id: int,
    comment_text: str,
    session_maker: async_sessionmaker,
    pair_id: int,
    force_update: bool = False
) -> str:
    async with session_maker() as session:
        result_user = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result_user.scalar()
        if user is None:
            return f"Пользователь с telegram_id {telegram_id} не найден"

        user_id = user.id

        result_feedback = await session.execute(
            select(Feedback).where(Feedback.user_id == user_id, Feedback.pair_id == pair_id)
        )
        feedback = result_feedback.scalar()

        if feedback:
            feedback.comment = comment_text
            feedback.submitted_at = datetime.utcnow()
            feedback.did_meet = True
            status_msg = "Комментарий обновлён ✅" if force_update else "Комментарий добавлен ✅"
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


# async def start_feedback_prompt(bot: Bot, telegram_id: int, dispatcher: Dispatcher, session_maker):
#     async with session_maker() as session:
#         # Получаем пользователя по telegram_id
#         result = await session.execute(
#             select(User).where(User.telegram_id == telegram_id)
#         )
#         user: User | None = result.scalar_one_or_none()
#
#         if not user:
#             print(f"⚠️ Пользователь с telegram_id={telegram_id} не найден.")
#             return
#
#         # Получаем pair_id — ID пары, в которой он участвовал сегодня
#         pair_id = await get_latest_pair_id_for_user(session, user.id)
#
#         if not pair_id:
#             print(f"ℹ️ Пользователь {telegram_id} сегодня не участвовал в паре.")
#             return
#
#         fsm_context = dispatcher.fsm.get_context(user_id=telegram_id, chat_id=telegram_id, bot=bot)
#
#         # Отправка сообщения
#         await bot.send_message(
#             telegram_id,
#             "Привет! Прошла ли встреча?",
#             reply_markup=meeting_question_kb(pair_id)
#         )
#
#         # Ставим состояние ожидания ответа
#         await fsm_context.set_state(FeedbackStates.waiting_for_feedback_decision)

# отображение когда сформируются пары и опрос как прошла встреча
def show_next_runs(scheduler: AsyncIOScheduler):
    print("🔔 Расписание ближайших запусков задач:")

    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        print(f"🛠 Задача '{job.id}' запустится в: {next_run.strftime('%Y-%m-%d %H:%M:%S') if next_run else 'нет запланированного запуска'}")

# сам запуск
def job_listener(event):
    show_next_runs(scheduler)

# async def reload_scheduled_jobs(bot: Bot, session_maker, dispatcher: Dispatcher):
#     print("♻️ Проверка и запуск задач...")
#
#     # Получаем настройки
#     async with session_maker() as session:
#         result = await session.execute(select(Setting).where(Setting.key == "global_interval"))
#         setting = result.scalar_one_or_none()
#         interval_weeks = setting.value if setting and setting.value else 2
#
#     # Пытаемся обновить / добавить задачи, только если их нет
#     def ensure_job(job_id: str, func, trigger):
#         try:
#             scheduler.get_job(job_id)
#             print(f"✅ Задача '{job_id}' уже существует.")
#         except JobLookupError:
#             print(f"➕ Добавляем задачу '{job_id}'...")
#             scheduler.add_job(
#                 func,
#                 trigger=trigger,
#                 id=job_id,
#                 replace_existing=False,
#             )
#
#     ensure_job("feedback_dispatcher", feedback_dispatcher_wrapper,
#                IntervalTrigger(minutes=interval_weeks))
#     ensure_job("auto_pairing_weekly", auto_pairing_wrapper,
#                IntervalTrigger(minutes=interval_weeks))
#     ensure_job("reload_jobs_hourly", reload_jobs_wrapper,
#                IntervalTrigger(minutes=interval_weeks))
#
#     if not scheduler.running:
#         scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED)
#         scheduler.start()
#
#     show_next_runs(scheduler)

async def feedback_dispatcher_job(bot: Bot, session_maker):
    async with session_maker() as session:
        # Получаем все пары, которым еще не отправляли опрос
        result_pairs = await session.execute(
            select(Pair).where(Pair.feedback_sent == False)
        )
        pairs = result_pairs.scalars().all()

        if not pairs:
            print("ℹ️ Нет новых пар для отправки опроса.")
            return

        for pair in pairs:
            user_ids = [pair.user1_id, pair.user2_id]
            if pair.user3_id:
                user_ids.append(pair.user3_id)

            result_users = await session.execute(
                select(User).where(User.id.in_(user_ids), User.has_permission  == True)
            )
            users = result_users.scalars().all()

            for user in users:
                try:
                    await bot.send_message(
                        user.telegram_id,
                        "Привет! Прошла ли встреча?",
                        reply_markup=meeting_question_kb(pair.id)
                    )
                    await asyncio.sleep(60)
                except Exception as e:
                    print(f"⚠️ Не удалось отправить опрос для {user.telegram_id}: {e}")

            # Отмечаем, что опрос для этой пары отправлен
            pair.feedback_sent = True

        # Сохраняем изменения
        await session.commit()



async def schedule_feedback_jobs(session_maker):
    async with session_maker() as session:
        result = await session.execute(select(Setting).where(Setting.key == "global_interval"))
        setting = result.scalar_one_or_none()

        interval_minutes = int(setting.value) if setting and setting.value else 2
        start_date = setting.first_matching_date if setting and setting.first_matching_date else datetime.utcnow()

    if not scheduler.running:
        scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED)
        scheduler.start()  # Сначала инициализируем scheduler (загрузит jobstore из БД)

    def schedule_or_reschedule(job_id, func, interval_minutes):
        job = scheduler.get_job(job_id)

        if job:
            current_interval = job.trigger.interval.total_seconds() / 60
            if int(current_interval) == interval_minutes:
                print(f"✅ '{job_id}' уже запланирована с тем же интервалом.")
                return

            print(f"♻️ Интервал '{job_id}' изменился. Перезапускаем...")

            next_time = job.next_run_time or datetime.utcnow()
            scheduler.remove_job(job_id)

            scheduler.add_job(
                func,
                trigger=IntervalTrigger(minutes=interval_minutes, start_date=next_time),
                id=job_id,
                replace_existing=True,
            )
            print(f"🆕 '{job_id}' пересоздана. Старт: {next_time}")
        else:
            print(f"➕ '{job_id}' не существует. Создаём заново.")
            scheduler.add_job(
                func,
                trigger=IntervalTrigger(minutes=interval_minutes, start_date=start_date),
                id=job_id,
                replace_existing=False,
            )

    # Запуск задач — только после старта планировщика!
    schedule_or_reschedule("feedback_dispatcher", feedback_dispatcher_wrapper, interval_minutes)
    schedule_or_reschedule("auto_pairing_weekly", auto_pairing_wrapper, interval_minutes)

    show_next_runs(scheduler)

