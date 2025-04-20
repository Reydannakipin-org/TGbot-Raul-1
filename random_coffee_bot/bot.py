from datetime import datetime, timedelta, date
from sqlalchemy import select
from database.models import User, Setting


async def get_users_ready_for_matching(session):
    now = datetime.utcnow()

    # Получаем глобальный интервал
    result = await session.execute(select(Setting).where(Setting.key == 'global_interval'))
    setting = result.scalar_one_or_none()
    global_interval_weeks = int(setting.value) if setting else 2
    cutoff = now - timedelta(weeks=global_interval_weeks)

    # Получаем пользователей, которые прошли свой интервал
    result = await session.execute(select(User))
    users = result.scalars().all()

    ready_users = []
    for user in users:
        user_interval_days = user.pairing_interval if user.pairing_interval else global_interval_weeks * 7
        user_cutoff = now - timedelta(days=user_interval_days)

        if user.pause_until and user.pause_until > now:
            continue

        # Преобразуем строку даты в объект datetime с проверкой на пустое значение
        if user.last_paired_at == '' or not user.last_paired_at:
            last_paired_at = None
        else:
            # Приводим дату к datetime (добавляем время 00:00:00)
            last_paired_at = datetime.combine(user.last_paired_at, datetime.min.time())

        # Теперь сравниваем last_paired_at с datetime (user_cutoff)
        if not last_paired_at or last_paired_at <= user_cutoff:
            ready_users.append(user)

    return ready_users