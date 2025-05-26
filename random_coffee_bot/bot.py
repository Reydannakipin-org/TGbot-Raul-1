import logging
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_EXECUTED
from datetime import datetime, timedelta, timezone
import random
from collections import defaultdict
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from globals import job_context
from aiogram import Bot

from config import MOSCOW_TZ
from database.db import AsyncSessionLocal
from database.models import User, Pair, Setting
from dotenv import load_dotenv
from services.admin_service import (feedback_dispatcher_job,
                                    notify_users_about_pairs)
from services.constants import DATE_TIME_FORMAT

logger = logging.getLogger(__name__)

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL").replace("+asyncpg", "+psycopg")

scheduler = AsyncIOScheduler(
    jobstores={
        'default': SQLAlchemyJobStore(url=DATABASE_URL)
    },
    timezone='UTC'
)

current_interval = None


async def feedback_dispatcher_wrapper():
    bot, dispatcher, session_maker = job_context.get_context()
    await feedback_dispatcher_job(bot, session_maker)

async def auto_pairing_wrapper():
    bot, dispatcher, session_maker = job_context.get_context()

    async with session_maker() as session:
        result = await session.execute(select(Setting))
        setting_obj = result.scalar_one_or_none()

        if setting_obj and setting_obj.auto_pairing_paused == 1:
            logger.info("🛑 Задача auto_pairing_weekly приостановлена (флаг в настройках).")
            return

    await auto_pairing(session_maker, bot)

async def reload_scheduled_wrapper():
    _, _, session_maker = job_context.get_context()
    await reload_scheduled_jobs(session_maker)


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
                Pair.paired_at < datetime.utcnow()
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
        if user.pause_until and user.pause_until > today:
            continue

        user_interval = user.pairing_interval or global_interval

        if not user.is_active:
            if user_interval > global_interval and user.future_meeting == 0:
                user.future_meeting = 1
            continue

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

    random.shuffle(users)
    user_ids = [u.id for u in users]
    user_map = {u.id: u for u in users}
    used = set()
    pairs = []

    possible_pairs = []
    for i in range(len(user_ids)):
        for j in range(i + 1, len(user_ids)):
            u1, u2 = user_ids[i], user_ids[j]
            key = tuple(sorted((u1, u2)))
            if u1 not in used and u2 not in used:
                possible_pairs.append((history[key], u1, u2))

    possible_pairs.sort()

    for _, u1, u2 in possible_pairs:
        if u1 not in used and u2 not in used:
            used.update([u1, u2])
            pairs.append((u1, u2))

    remaining = [uid for uid in user_ids if uid not in used]
    pair_objs = []

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

        pairs = await generate_unique_pairs(session, users)

        await session.commit()
        logger.info(f"✅ Сформировано {len(pairs)} пар.")

        await notify_users_about_pairs(session, pairs, bot)


# отображение для консоли
def show_next_runs(scheduler: AsyncIOScheduler):
    logger.debug("🔔 Расписание ближайших запусков задач:")

    for job in scheduler.get_jobs():
        next_run_utc = job.next_run_time
        next_run_msk = next_run_utc.astimezone(MOSCOW_TZ)
        logger.debug(f"🛠 Задача '{job.id}' запустится в: {next_run_msk.strftime(DATE_TIME_FORMAT) if next_run_msk else 'нет запланированного запуска'}")


async def get_next_pairing_date() -> str | None:
    """
    Возвращает дату, когда состоится следующее формирование пар
    согласно планировщику задач.
    """
    job = next((job for job in scheduler.get_jobs() if job.id == 'auto_pairing_weekly'), None)

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Setting))
        setting_obj = result.scalar_one_or_none()

    if job:
        next_run_utc = job.next_run_time
        next_run_msk = next_run_utc.astimezone(MOSCOW_TZ)
        next_run_str = next_run_msk.strftime(DATE_TIME_FORMAT)

        if setting_obj and setting_obj.auto_pairing_paused == 1:
            logger.info(f"🛠 Паринг остановлен. Но задача '{job.id}' запланирована на: {next_run_str}")
            return f'формирование пар приостановлено (если возобновить: {next_run_str})'
        else:
            logger.debug(f"🛠 Задача '{job.id}' запустится: {next_run_str}")
            return next_run_str
    return None


# отображение для консоли
def job_listener(event):
    show_next_runs(scheduler)


async def schedule_feedback_dispatcher_for_auto_pairing(start_date_for_auto_pairing):
    start_date_for_feedback_dispatcher = start_date_for_auto_pairing - timedelta(days=3)  # Для прода должно стоять days
    return start_date_for_feedback_dispatcher


def schedule_or_reschedule(job_id, func, recieved_interval, session_maker,
                           start_date=None,
                           misfire_grace_time: int | None = None):
    job = scheduler.get_job(job_id)
    now = datetime.now(timezone.utc)
    effective_start = start_date or now

    if job:
        # Для прода:
        current_job_interval = job.trigger.interval.days()
        # current_job_interval = job.trigger.interval.total_seconds() // 3600  # Для тестирования часы
        if (int(current_job_interval) != recieved_interval or
                job.misfire_grace_time != misfire_grace_time):
            next_run_time = getattr(job, "next_run_time", None)
            if next_run_time:
                new_start_date = next_run_time + timedelta(days=int(recieved_interval))  # Для прода должно стоять days
            else:
                new_start_date = effective_start

            scheduler.modify_job(
                job_id,
                trigger=IntervalTrigger(days=recieved_interval, start_date=new_start_date),  # Для прода должно стоять days
                misfire_grace_time=misfire_grace_time
            )
            logger.info(
                f"🕒 '{job_id}' будет перезапущена с новым интервалом {recieved_interval} начиная с {new_start_date}, grace_time={misfire_grace_time}")
        else:
            logger.info(f"✅ '{job_id}' уже запланирована с интервалом {recieved_interval} и grace_time={misfire_grace_time}")
    else:
        scheduler.add_job(
            func,
            trigger=IntervalTrigger(days=recieved_interval, start_date=effective_start),  # Для прода должно стоять days
            id=job_id,
            replace_existing=True,
            misfire_grace_time=misfire_grace_time,
        )
        print(f"🆕 '{job_id}' создана. Старт: {effective_start}")


async def schedule_feedback_jobs(session_maker):
    global current_interval

    async with session_maker() as session:
        result = await session.execute(select(Setting).where(Setting.key == "global_interval"))
        setting = result.scalar_one_or_none()

        setting_interval = int(setting.value) if setting and setting.value else 2
        start_date = (
            setting.first_matching_date
            if setting and setting.first_matching_date
            else datetime.utcnow()
        )

        interval_for_job = setting_interval * 7

    if not scheduler.running:
        scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED)
        scheduler.start()

    if current_interval != setting_interval:
        print(f"🔁 Интервал изменился: {current_interval} ➡️ {setting_interval}")
        current_interval = setting_interval

    start_date_for_auto_pairing = start_date
    schedule_or_reschedule("auto_pairing_weekly", auto_pairing_wrapper, interval_for_job, session_maker,
                           start_date=start_date_for_auto_pairing, misfire_grace_time=172800)  # Для прода: misfire_grace_time=172800 (для теста 7200 - 2 часа)

    start_date_for_feedback_dispatcher = await schedule_feedback_dispatcher_for_auto_pairing(
        start_date_for_auto_pairing)
    schedule_or_reschedule("feedback_dispatcher", feedback_dispatcher_wrapper, interval_for_job, session_maker,
                           start_date=start_date_for_feedback_dispatcher, misfire_grace_time=None)

    schedule_or_reschedule("reload_jobs_checker", reload_scheduled_wrapper, 1, session_maker,
                           start_date=start_date_for_auto_pairing, misfire_grace_time=86400)  # Для прода: misfire_grace_time=86400 (для теста 3600 - 1 час)

    show_next_runs(scheduler)


async def reload_scheduled_jobs(session_maker):
    async with session_maker() as session:
        result = await session.execute(select(Setting).where(Setting.key == "global_interval"))
        setting = result.scalar_one_or_none()
        new_interval = int(setting.value) if setting and setting.value else 2

    global current_interval
    if current_interval != new_interval:
        logger.info(f"🔁 Интервал изменился: {current_interval} ➡️ {new_interval}")
        current_interval = new_interval

        await schedule_feedback_jobs(session_maker)
    else:
        logger.debug("✅ Интервал не изменился. Задачи остаются с прежним интервалом.")
