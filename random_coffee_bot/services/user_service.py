from typing import Optional
import logging

from sqlalchemy import select
from database.models import Setting
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from datetime import date

from database.models import User
from texts import ADMIN_TEXTS, INTERVAL_TEXTS

logger = logging.getLogger(__name__)


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int
                                  ) -> Optional[User]:
    '''Получает из БД экземпляр пользователя по его telegram_id.
    Если пользователь найден, возвращает его экземпляр. В ином случае - None'''
    query = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()
    return user


async def create_user(session: AsyncSession,
                      telegram_id: int,
                      username: str | None,
                      first_name: str,
                      last_name: str | None) -> User:
    '''Создает пользователя. Возвращает экземпляр пользователя.'''
    user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
    session.add(user)
    try:
        await session.commit()
        return user
    except SQLAlchemyError as e:
        await session.rollback()
        raise e


async def update_user_field(session: AsyncSession,
                            telegram_id: int,
                            field: str,
                            value: str) -> bool:
    '''Обновляет заданное поле пользователя.
    Возвращает True, если пользователь найден и обновлен.'''
    try:
        user = await get_user_by_telegram_id(session, telegram_id)
        if not user:
            return False
        setattr(user, field, value)
        await session.commit()
        return True
    except SQLAlchemyError as e:
        await session.rollback()
        raise e


async def set_user_active(session: AsyncSession,
                          telegram_id: int,
                          is_active: bool
                          ) -> bool:
    '''Изменяет значение флага is_active.
    Возвращает True, если пользователь найден и обновлен.'''
    try:
        user = await get_user_by_telegram_id(session, telegram_id)
        if not user:
            return False
        user.is_active = is_active
        await session.commit()
        return True
    except SQLAlchemyError as e:
        await session.rollback()
        raise e


async def set_user_pairing_interval(
    session: AsyncSession,
    telegram_id: int,
    pairing_interval: int
) -> bool:
    '''Изменяет значение поля pairing_interval для пользователя.
    Возвращает True, если пользователь найден и обновлен.'''
    try:
        user = await get_user_by_telegram_id(session, telegram_id)
        if not user:
            return False

        # Убедитесь, что pairing_interval - это допустимое значение
        if pairing_interval not in [2, 3, 4]:  # или другие допустимые значения
            raise ValueError(
                "Недопустимое значение интервала. Допустимые значения: 2, 3 или 4."
            )

        user.pairing_interval = pairing_interval
        await session.commit()
        return True
    except SQLAlchemyError as e:
        await session.rollback()
        raise e
    except ValueError as ve:
        # Обработка недопустимого значения интервала
        logging.error(f"Ошибка при установке интервала: {ve}")
        return False


async def set_user_permission(session: AsyncSession,
                              telegram_id: int,
                              has_permission: bool
                              ) -> bool:
    '''Изменяет значение флага has_permission.
    Возвращает True, если пользователь найден и обновлен.'''
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


async def delete_user(session: AsyncSession, telegram_id: int) -> bool:
    '''Служебная функция на время разработки.
    Удаляет пользователя из БД.'''
    try:
        user = await get_user_by_telegram_id(session, telegram_id)
        if not user:
            return False
        await session.delete(user)
        await session.commit()
        return True
    except SQLAlchemyError as e:
        await session.rollback()
        raise e


async def create_text_with_interval(
    session: AsyncSession, text: str, user_id: int
) -> str:
    admin_current_interval = await get_global_interval(session)
    user_current_interval = await get_user_interval(session, user_id)

    logger.info(f"Администратор - {admin_current_interval}, Пользователь - {user_current_interval}")

    # Получаем текст для интервала администратора
    admin_interval_text = INTERVAL_TEXTS.get(admin_current_interval) if admin_current_interval else ADMIN_TEXTS['no_data']

    # Если у пользователя установлен свой интервал, используем его
    if user_current_interval is not None:
        user_interval_text = INTERVAL_TEXTS.get(user_current_interval) if user_current_interval else ADMIN_TEXTS['no_data']
    else:
        # Если у пользователя нет установленного интервала, используем интервал администратора
        user_current_interval = admin_current_interval
        user_interval_text = admin_interval_text

    data_text = text.format(
        your_interval=user_interval_text,
        their_interval=admin_interval_text
    )

    logger.info(f"Formatted text: {data_text}")

    return data_text


async def get_global_interval(session: AsyncSession) -> Optional[str]:
    '''
    Возвращает из базы данных значение глобального интервала.
    '''
    result = await session.execute(
        select(Setting.value).where(Setting.key == "global_interval")
    )
    return result.scalar()


async def get_user_interval(
    session: AsyncSession, user_id: int
) -> Optional[str]:  # Изменено на Optional[str]
    '''
    Возвращает из базы данных значение интервала которое поставил пользователь.
    '''
    result = await session.execute(
        select(User.pairing_interval).where(User.telegram_id == user_id)
    )

    return result.scalar()


#Временно нужно будет удалить
async def set_new_global_interval(session: AsyncSession, new_value: int
                                  ) -> None:
    '''
    Изменяет значение глобального интервала в таблице settings.
    Возвращает True, если интервал обновлен.
    '''
    try:
        result = await session.execute(
            select(Setting).where(Setting.key == 'global_interval')
        )
        setting = result.scalars().first()

        if setting:
            setting.value = new_value
        else:
            setting = Setting(key='global_interval', value=new_value)
            session.add(setting)

        await session.commit()
    except SQLAlchemyError as e:
        await session.rollback()
        logger.exception('Ошибка при установке нового интервала')
        raise e


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
