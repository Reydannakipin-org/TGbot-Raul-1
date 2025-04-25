from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta, date
from random import shuffle
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import User, Pair, Setting
from aiogram import Bot
import random
from collections import defaultdict

scheduler = AsyncIOScheduler()

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


def setup_scheduler(session_maker, bot: Bot):
    @scheduler.scheduled_job("cron", minute="*")   #каждую минуту для тестов
    #@scheduler.scheduled_job("cron", day_of_week="tue", hour=10)  # каждый вторник в 10 часов потом обновлю до нужного интервала
    async def auto_pairing():
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

    scheduler.start()
