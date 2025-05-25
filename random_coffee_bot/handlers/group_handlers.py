import logging

from aiogram import Router
from aiogram.filters import IS_MEMBER, IS_NOT_MEMBER
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter
from aiogram.types import ChatMemberUpdated
from sqlalchemy.exc import SQLAlchemyError


from database.db import AsyncSessionLocal
from services.user_service import get_user_by_telegram_id


logger = logging.getLogger(__name__)

group_router = Router()


@group_router.chat_member(ChatMemberUpdatedFilter(IS_MEMBER >> IS_NOT_MEMBER))
async def on_user_leave(update: ChatMemberUpdated):
    logger.debug('Хэндлер выхода из группы')
    user_id = update.from_user.id
    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_by_telegram_id(session, user_id)
            if user is None:
                return
            user.is_active = False
            user.has_permission = False
            user.is_blocked = True
            await session.commit()
            logger.info(f'Юзер {user_id} больше не участник группы. Статусы изменены.')
    except SQLAlchemyError:
        await session.rollback()
        logger.exception(f'Не удалось изменить статусы юзера {user_id}, '
                         'который больше не является участником группы.')


@group_router.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def on_user_join(update: ChatMemberUpdated):
    logger.debug('Хэндлер вступления в группу')
    user_id = update.from_user.id
    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_by_telegram_id(session, user_id)
            if user is None:
                return
            user.has_permission = True
            user.is_blocked = False
            await session.commit()
            logger.info(f'Юзер {user_id} снова участник группы. Статусы изменены.')
    except SQLAlchemyError:
        await session.rollback()
        logger.exception(f'Не удалось изменить статусы юзера {user_id}, '
                         'который вернулся в группу.')
