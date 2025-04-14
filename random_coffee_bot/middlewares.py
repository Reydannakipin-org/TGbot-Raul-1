import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Update

from random_coffee_bot.texts import TEXTS


logger = logging.getLogger(__name__)


class GroupMemberMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,  # type: ignore
        data: Dict[str, Any]
    ) -> Any:
        logger.info(f'Вошли в мидлвэер. data = {data['user'].first_name}')
        bot = data['bot']
        user = data['event_from_user']
        group_tg_id = data.get('group_tg_id')
        try:
            member = await bot.get_chat_member(chat_id=group_tg_id,
                                               user_id=user.id)
            if member.status in ['left', 'kicked']:
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
        return await handler(event, data)
