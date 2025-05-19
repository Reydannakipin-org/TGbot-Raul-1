import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_EXECUTED
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
from aiogram import Bot
from aiogram.fsm.state import State, StatesGroup

from config import MOSCOW_TZ
from database.models import User, Pair, Setting, Feedback
from dotenv import load_dotenv
from services.admin_service import notify_users_about_pairs


logger = logging.getLogger(__name__)

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL").replace("+asyncpg", "+psycopg")

# подлкючение для постгресса
scheduler = AsyncIOScheduler(
    jobstores={
        'default': SQLAlchemyJobStore(url=DATABASE_URL)
    },
    timezone='UTC'
)
# пусть пока тут будет когда будет постгрес тогда будет видно где лучше быть
# scheduler = AsyncIOScheduler(
#         jobstores={'default': SQLAlchemyJobStore(url='sqlite:///jobs.sqlite')},
#         timezone='Europe/Moscow'
#     )

current_interval = None


class CommentStates(StatesGroup):
    waiting_for_comment = State()


async def feedback_dispatcher_wrapper():
    bot, dispatcher, session_maker = job_context.get_context()
    await feedback_dispatcher_job(bot, session_maker)

async def auto_pairing_wrapper():
    bot, dispatcher, session_maker = job_context.get_context()
    await auto_pairing(session_maker, bot)

async def reload_scheduled_wrapper():
    _, _, session_maker = job_context.get_context()
    await reload_scheduled_jobs(session_maker)

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
            session.add(last_pair)
        else:
            logger.info(f"⚠️ Один пользователь остался без пары: {odd.id}")

    return pair_objs


async def auto_pairing(session_maker, bot: Bot):
    async with session_maker() as session:
        users = await get_users_ready_for_matching(session)
        if len(users) < 2:
            logger.info("❗ Недостаточно пользователей для формирования пар.")
            return

        # 💡 Новый способ формирования пар
        pairs = await generate_unique_pairs(session, users)

        await session.commit()
        logger.info(f"✅ Сформировано {len(pairs)} пар.")

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
            status_msg = "Спасибо за комментарий ✅"

        await session.commit()
        return status_msg


# отображение для консоли его в проде не будет
def show_next_runs(scheduler: AsyncIOScheduler):
    logger.debug("🔔 Расписание ближайших запусков задач:")

    for job in scheduler.get_jobs():
        next_run_utc = job.next_run_time
        next_run_msk = next_run_utc.astimezone(MOSCOW_TZ)
        logger.debug(f"🛠 Задача '{job.id}' запустится в: {next_run_msk.strftime('%Y-%m-%d %H:%M по МСК') if next_run_msk else 'нет запланированного запуска'}")


def get_next_pairing_date() -> str | None:
    """
    Возвращает дату, когда состоится следующее формирование пар
    согласно планировщику задач.
    """
    job = next((job for job in scheduler.get_jobs() if job.id == 'auto_pairing_weekly'), None)

    if job:
        next_run_utc = job.next_run_time
        next_run_msk = next_run_utc.astimezone(MOSCOW_TZ)
        next_run_str = next_run_msk.strftime('%Y-%m-%d %H:%M по МСК')
        logger.debug(f"🛠 Задача '{job.id}' запустится: {next_run_str}")
        return next_run_str
    return None


# отображение для консоли его в проде не будет
def job_listener(event):
    show_next_runs(scheduler)


async def feedback_dispatcher_job(bot: Bot, session_maker):
    async with session_maker() as session:
        result_pairs = await session.execute(
            select(Pair).where(Pair.feedback_sent.is_(False))
        )
        pairs = result_pairs.scalars().all()

        if not pairs:
            logger.info("ℹ️ Нет новых пар для отправки опроса.")
            return

        for pair in pairs:
            user_ids = [pair.user1_id, pair.user2_id]
            if pair.user3_id:
                user_ids.append(pair.user3_id)

            result_users = await session.execute(
                select(User).where(User.id.in_(user_ids),
                                   User.has_permission.is_(True))
            )
            users = result_users.scalars().all()

            kb = meeting_question_kb(pair.id)
            success = True
            for user in users:
                try:
                    await bot.send_message(
                        user.telegram_id,
                        "Привет! Прошла ли встреча?",
                        reply_markup=kb
                    )
                    await asyncio.sleep(0.05)
                except Exception as e:
                    logger.info(f"⚠️ Не удалось отправить опрос для {user.telegram_id}: {e}")
                    success = False  # хотя бы одному не отправили

            # Отмечаем только если всем отправлено успешно
            if success:
                pair.feedback_sent = True

        await session.commit()

async def schedule_feedback_dispatcher_for_auto_pairing(start_date_for_auto_pairing):
    start_date_for_feedback_dispatcher = start_date_for_auto_pairing - timedelta(days=3)
    return start_date_for_feedback_dispatcher

async def schedule_feedback_jobs(session_maker):
    global current_interval

    async with session_maker() as session:
        result = await session.execute(select(Setting).where(Setting.key == "global_interval"))
        setting = result.scalar_one_or_none()

        interval_minutes = int(setting.value) if setting and setting.value else 2
        start_date = setting.first_matching_date if setting and setting.first_matching_date else datetime.utcnow()

        pairing_day = interval_minutes * 7


    if not scheduler.running:
        scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED)
        scheduler.start()

    if current_interval != interval_minutes:
        logger.info(f"🔁 Интервал изменился: {current_interval} ➡️ {interval_minutes}")
        current_interval = interval_minutes

    def schedule_or_reschedule(job_id, func, interval_days, start_date=None):
        job = scheduler.get_job(job_id)
        now = datetime.utcnow()

        if job:
            current_interval_from_job = job.trigger.interval.total_seconds() // 86400
            if int(current_interval_from_job) == interval_days:
                logger.debug(f"✅ '{job_id}' уже запланирована с тем же интервалом.")
                return
            else:
                logger.info(
                    f"♻️ Интервал '{job_id}' изменился с {current_interval_from_job} на {interval_days}. Перезапускаем...")
                scheduler.remove_job(job_id)

        effective_start = start_date or now

        scheduler.add_job(
            func,
            trigger=IntervalTrigger(days=interval_days, start_date=effective_start),
            id=job_id,
            replace_existing=True,
            misfire_grace_time=172800,  # 2 дня
        )
        logger.debug(f"🆕 '{job_id}' пересоздана. Старт: {effective_start}")

        # # 👉 Ручной запуск, если задача должна была уже отработать
        # time_since_start = (now - effective_start).total_seconds()
        # # interval_sec = interval_days * 86400  # секунды в дне
        # interval_sec = interval_days * 60 # Таня - убрать строку, вернуть ту, что выше

        # if 0 < time_since_start < 172800 and time_since_start % interval_sec < 60:
        #     scheduler._create_executor("default").submit_job(
        #         scheduler.get_job(job_id),
        #         run_times=[now]
        #     )

    start_date_for_auto_pairing = start_date
    schedule_or_reschedule("auto_pairing_weekly", auto_pairing_wrapper, pairing_day, start_date=start_date_for_auto_pairing)

    start_date_for_feedback_dispatcher = await schedule_feedback_dispatcher_for_auto_pairing(start_date_for_auto_pairing)
    schedule_or_reschedule("feedback_dispatcher", feedback_dispatcher_wrapper, pairing_day, start_date=start_date_for_feedback_dispatcher)

    schedule_or_reschedule("reload_jobs_checker", reload_scheduled_wrapper, 1, start_date=start_date_for_auto_pairing)

    show_next_runs(scheduler)


async def reload_scheduled_jobs(session_maker):
    async with session_maker() as session:
        result = await session.execute(select(Setting).where(Setting.key == "global_interval"))
        setting = result.scalar_one_or_none()
        new_interval_minutes = int(setting.value) if setting and setting.value else 2

    global current_interval
    # Если интервал изменился, обновляем задачи
    if current_interval != new_interval_minutes:
        logger.info(f"🔁 Интервал изменился: {current_interval} ➡️ {new_interval_minutes}")
        current_interval = new_interval_minutes

        # Перезапускаем задачи с новым интервалом
        await schedule_feedback_jobs(session_maker)
    else:
        logger.debug("✅ Интервал не изменился. Задачи остаются с прежним интервалом.")
