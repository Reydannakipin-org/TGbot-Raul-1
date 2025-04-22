from datetime import datetime, timedelta, date
from sqlalchemy import select
from database.models import User, Setting


async def get_users_ready_for_matching(session):
    today = datetime.utcnow().date()

    # Получаем глобальный интервал в неделях
    result = await session.execute(select(Setting).where(Setting.key == 'global_interval'))
    setting = result.scalar_one_or_none()
    global_interval_weeks = int(setting.value) if setting else 3
    global_interval_days = global_interval_weeks * 7

    # Жестко задаём дату первого матчмейкинга (или можно доставать из базы)
    first_matching_date = datetime.strptime("2025-04-01", "%Y-%m-%d").date()

    # Проверяем: сегодня ли глобальный день
    delta_days = (today - first_matching_date).days
    if delta_days < 0 or delta_days % global_interval_days != 0:
        return []  # сегодня не день для создания пар

    # Сегодня — глобальный день. Загружаем всех пользователей
    result = await session.execute(select(User))
    users = result.scalars().all()

    ready_users = []
    for user in users:
        # Пропускаем, если пользователь на паузе
        if user.pause_until and user.pause_until.date() > today:
            continue

        # Интервал пользователя, если нет — используем глобальный
        user_interval_days = user.pairing_interval if user.pairing_interval else global_interval_days

        # Проверка даты последнего участия
        if not user.last_paired_at:
            # Никогда не участвовал — можно
            ready_users.append(user)
            continue

        # Преобразуем дату
        last_paired_date = (
            user.last_paired_at.date() if isinstance(user.last_paired_at, datetime)
            else datetime.strptime(user.last_paired_at, "%Y-%m-%d").date()
            if isinstance(user.last_paired_at, str)
            else user.last_paired_at
        )

        # Может ли участвовать снова?
        next_allowed_date = last_paired_date + timedelta(days=user_interval_days)
        if next_allowed_date <= today:
            ready_users.append(user)

    return ready_users