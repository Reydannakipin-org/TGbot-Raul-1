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


async def create_text_with_default_interval(
    session: AsyncSession, text: str, user_id: int
) -> str:
    '''
    Создает текст для ответа, когда пользователь
    передумал менять интервал встреч.
    '''
    admin_current_interval = await get_global_interval(session)
    user_current_interval = await get_user_interval(session, user_id)

    if user_current_interval is not None:
        user_key = str(user_current_interval)
        user_interval_text = INTERVAL_TEXTS.get(user_key) if user_key else ADMIN_TEXTS['no_data']
    else:
        user_current_interval = admin_current_interval
        user_key = str(user_current_interval)
        user_interval_text = INTERVAL_TEXTS.get(user_key) if user_key else ADMIN_TEXTS['no_data']

    data_text = text.format(
        current_interval=user_interval_text
    )
    return data_text


async def create_text_with_interval(
    session: AsyncSession, text: str, user_id: int
) -> str:
    '''
    Создает текст для ответа когда пользоватеь
    решил изменить интервал встчер.
    '''
    admin_current_interval = await get_global_interval(session)
    user_current_interval = await get_user_interval(session, user_id)


    # Получаем текст для интервала администратора
    admin_interval_text = (
        INTERVAL_TEXTS.get(str(admin_current_interval)) if admin_current_interval else ADMIN_TEXTS['no_data']
    )

    if user_current_interval is not None:
        user_key = str(user_current_interval)
        user_interval_text = (
            INTERVAL_TEXTS.get(user_key) if user_key else ADMIN_TEXTS[
                'no_data'
            ]
        )
    else:
        user_current_interval = admin_current_interval
        user_key = str(user_current_interval)
        user_interval_text = (
            INTERVAL_TEXTS.get(user_key) if user_key else ADMIN_TEXTS[
                'no_data'
            ]
        )

    data_text = text.format(
        your_interval=user_interval_text,
        their_interval=admin_interval_text
    )
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


async def set_new_user_interval(
    session: AsyncSession, user_id: int, new_value: int
) -> None:
    '''
    Изменяет значение интервала для конкретного пользователя в таблице users.
    '''
    logger.info(
        f"Попытка установить новый pairing_interval: {new_value} для пользователя с id {user_id}"
    )

    try:
        updated_user_result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        updated_user = updated_user_result.scalars().first()

        if updated_user is None:
            logger.warning(f'Пользователь с id {user_id} не найден')
            raise ValueError(f'Пользователь с id {user_id} не найден')

        logger.info(
            f"Обновлённое значение pairing_interval для пользователя до изменения: {updated_user.pairing_interval}"
        )

        updated_user.pairing_interval = new_value  # Обновляем значение
        await session.commit()  # Коммит изменений

        logger.info(
            f'pairing_interval для пользователя с id {user_id} обновлён на {new_value}'
        )

    except SQLAlchemyError as e:
        await session.rollback()  # Откат в случае ошибки
        logger.exception(
            'Ошибка при установке нового интервала для пользователя'
        )
        raise e


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
