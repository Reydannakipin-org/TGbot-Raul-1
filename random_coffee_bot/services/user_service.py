from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from database.models import User


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
