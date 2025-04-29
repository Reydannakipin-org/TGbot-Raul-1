import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove, Update
from sqlalchemy.exc import SQLAlchemyError

from database.db import AsyncSessionLocal
from services.user_service import get_user_by_telegram_id
from texts import TEXTS


logger = logging.getLogger(__name__)


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,  # type: ignore
        data: Dict[str, Any]
    ) -> Any:
        logger.info('Старт мидлвэер диспетчера. Получен апдейт.')
        chat = None
        if event.message:
            chat = event.message.chat
        elif event.callback_query:
            chat = event.callback_query.message.chat  # type: ignore
        if not chat or chat.type != ChatType.PRIVATE:
            logger.info('Апдейт не из приватного чата. Игнорируем')
            return

        logger.info('Апдейт из приватного чата. Проверяем админ ли это.')
        user = data['event_from_user']
        admin_id = data.get('admin_id', 0)
        if user.id == admin_id:
            logger.info('Это админ. Апдейт передан в хэндлеры.')
            return await handler(event, data)

        logger.info('Проверяем состоит ли юзер в группе.')
        bot = data['bot']
        group_tg_id = data.get('group_tg_id')
        try:
            member = await bot.get_chat_member(chat_id=group_tg_id,
                                               user_id=user.id)
            if member.status in ['left', 'kicked']:
                logger.info('Юзера нет в группе. Отказ в доступе.')
                if event.message:
                    await event.message.answer(TEXTS['deny_access'])
                elif event.callback_query:
                    await event.callback_query.answer(TEXTS['deny_access'],
                                                      show_alert=True)
                return
        except Exception as e:
            logging.exception('Ошибка при проверке членства: %s', e)
            if event.message:
                await event.message.answer(TEXTS['error_access'])
            elif event.callback_query:
                await event.callback_query.answer(TEXTS['error_access'],
                                                  show_alert=True)
            return

        logger.info('Юзер есть в группе. Проверяем, есть ли он в БД.')
        try:
            async with AsyncSessionLocal() as session:
                user_from_db = await get_user_by_telegram_id(session, user.id)

                if user_from_db is None:
                    logger.info(f'Юзера нет в БД. Апдейт передан в хэндлеры. '
                                f'Юзер: {data['event_from_user']}')
                    return await handler(event, data)
                else:
                    logger.info('Юзер есть в БД. Проверяем разрешение.')
                    if not user_from_db.has_permission:
                        logger.info('У юзера нет разрешения. Отказ в доступе.')
                        if event.message:
                            await event.message.answer(
                                TEXTS['no_permission'],
                                reply_markup=ReplyKeyboardRemove())
                        elif event.callback_query:
                            await event.callback_query.answer(
                                TEXTS['no_permission'], show_alert=True)
                        return
        except SQLAlchemyError:
            logger.exception('Ошибка при работе с базой данных')
            if event.message:
                await event.message.answer(TEXTS['db_error'])
            elif event.callback_query:
                await event.callback_query.answer(TEXTS['db_error'],
                                                  show_alert=True)
            return
        logger.info(f'У юзера есть разрешение. Апдейт передан в хэндлеры. '
                    f'Юзер: {data['event_from_user']}')
        return await handler(event, data)
