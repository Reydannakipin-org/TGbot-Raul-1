from datetime import datetime, timedelta
from sqlalchemy import select
from app.models import User, Setting

async def get_users_ready_for_matching(session):
    now = datetime.utcnow()

    # Получаем глобальный интервал
    result = await session.execute(select(Setting).where(Setting.key == 'global_interval'))
    setting = result.scalar_one_or_none()
    global_interval_weeks = int(setting.value) if setting else 3
    cutoff = now - timedelta(weeks=global_interval_weeks)

    # Получаем пользователей, которые прошли свой интервал
    result = await session.execute(select(User))
    users = result.scalars().all()

    ready_users = []
    for user in users:
        user_interval = timedelta(weeks=user.interval or 2)
        if not user.last_paired_at or user.last_paired_at <= now - user_interval:
            ready_users.append(user)

    return ready_users