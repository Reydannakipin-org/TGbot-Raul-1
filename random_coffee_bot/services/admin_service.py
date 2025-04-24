import logging
from datetime import datetime, date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from database.models import Setting, User
from texts import ADMIN_TEXTS, INTERVAL_TEXTS
from services.user_service import get_user_by_telegram_id


logger = logging.getLogger(__name__)


async def set_user_permission(session: AsyncSession,
                              telegram_id: int,
                              has_permission: bool
                              ) -> bool:
    '''
    Изменяет значение флага has_permission.
    Возвращает True, если пользователь найден и обновлен.
    '''
    try:
        user = await get_user_by_telegram_id(session, telegram_id)
        if not user:
            return False
        user.has_permission = has_permission
        if not has_permission:
            user.is_active = False
        await session.commit()
        return True
    except SQLAlchemyError as e:
        await session.rollback()
        raise e


async def set_user_puase_until(session: AsyncSession,
                               telegram_id: int,
                               input_date: date
                               ) -> bool:
    '''Изменяет значение флага has_permission.
    Возвращает True, если пользователь найден и обновлен.'''
    try:
        user = await get_user_by_telegram_id(session, telegram_id)
        if not user:
            return False
        user.pause_until = input_date
        await session.commit()
        return True
    except SQLAlchemyError as e:
        await session.rollback()
        raise e


def create_text_about_user(user: User):
    data_text = ADMIN_TEXTS['finding_user_success'].format(
        first_name=user.first_name or ADMIN_TEXTS['no_data'],
        last_name=user.last_name or ADMIN_TEXTS['no_data'],
        status=(ADMIN_TEXTS['status_active_true'] if user.is_active
                else ADMIN_TEXTS['status_active_false']),
        permission=(ADMIN_TEXTS['has_permission_true'] if user.has_permission
                    else ADMIN_TEXTS['has_permission_false']),
        interval=(INTERVAL_TEXTS['default'] if not user.pairing_interval
                  else INTERVAL_TEXTS[str(user.pairing_interval)]),
        pause=(user.pause_until.strftime("%d.%m.%Y") if user.pause_until
               else ADMIN_TEXTS['no_settings'])
    )
    return data_text


def create_text_with_full_name(text: str, user: User):
    data_text = text.format(
        first_name=user.first_name or ADMIN_TEXTS['no_data'],
        last_name=user.last_name or '')
    return data_text


def create_text_with_full_name_date(text: str, user: User):
    data_text = text.format(
        first_name=user.first_name or ADMIN_TEXTS['no_data'],
        last_name=user.last_name or '',
        date=user.pause_until.strftime("%d.%m.%Y") or ADMIN_TEXTS['no_data'])
    return data_text


async def create_text_with_interval(session: AsyncSession, text: str):
    '''
    Подставляет значения для переменных interval и next_pairing_date
    в полученном тексте.
    '''
    current_interval: Optional[str] = await get_global_interval(session)
    next_pairing_date = get_next_pairing_date()

    if current_interval is None:
        interval_text = ADMIN_TEXTS['no_data']
    else:
        interval_text = INTERVAL_TEXTS.get(current_interval,
                                           INTERVAL_TEXTS['default'])

    if next_pairing_date:
        date_text = next_pairing_date.strftime("%d.%m.%Y")
    else:
        date_text = ADMIN_TEXTS['unknown']

    data_text = text.format(
        interval=interval_text,
        next_pairing_date=date_text)
    return data_text


def is_valid_date(txt: str) -> bool:
    try:
        datetime.strptime(txt, "%d.%m.%Y")
        return True
    except ValueError:
        return False


def parse_callback_data(data: str) -> tuple[str, str]:
    """
    Разбирает callback.data в формате 'action:us' и возвращает
    кортеж (action, param).
    """
    try:
        action, param = data.split(':', 1)
        return action, param
    except ValueError:
        logger.error(f'Неверные данные у коллбека: {data}')
        raise


async def get_global_interval(session: AsyncSession) -> Optional[str]:
    '''
    Возвращает из базы данных значение глобального интервала.
    '''
    result = await session.execute(
        select(Setting.value).where(Setting.key == "global_interval")
    )
    return result.scalar()


async def set_new_global_interval(session: AsyncSession, new_value: int
                                  ) -> None:
    '''
    Изменяет значение глобального интервала в таблице settings.
    Возвращает True, если интервал обновлен.
    '''
    try:
        result = await session.execute(
            select(Setting).where(Setting.key == "global_interval")
        )
        setting = result.scalars().first()

        if setting:
            setting.value = new_value
        else:
            setting = Setting(key="global_interval", value=new_value)
            session.add(setting)

        await session.commit()
    except SQLAlchemyError as e:
        await session.rollback()
        raise e


def get_next_pairing_date() -> Optional[date]:
    return None
