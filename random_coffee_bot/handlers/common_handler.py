import logging

from aiogram import Router
from aiogram.exceptions import (AiogramError,
                                TelegramAPIError,
                                TelegramBadRequest,
                                TelegramForbiddenError,
                                TelegramNetworkError,
                                TelegramRetryAfter)
from aiogram.types import CallbackQuery, ErrorEvent, Message

from texts import TEXTS


logger = logging.getLogger(__name__)

common_router = Router()


@common_router.callback_query()
async def missed_callback(callback: CallbackQuery):
    """
    Хэндлер будет обрабатывать коллбеки, которые устарели или потеряли
    данные из-за перезапуска бота.
    """
    try:
        if isinstance(callback.message, Message):
            await callback.message.delete()
    except Exception:
        pass
    await callback.answer(TEXTS['old_callback'], show_alert=True)



@common_router.error()
async def global_error_handler(event: ErrorEvent) -> bool:
    """
    Глобальный хэндлер ошибок. Возвращает True, чтобы aiogram не прокидывал
    исключение дальше, и бот не падал.
    """
    chat_id = None
    if event.update.message:
        chat_id = event.update.message.chat.id
    elif event.update.callback_query and event.update.callback_query.message:
        chat_id = event.update.callback_query.message.chat.id

    if isinstance(event.exception, TelegramRetryAfter):
        logger.warning('Превышен лимит запросов')

    elif isinstance(event.exception, TelegramForbiddenError):
        logger.error(f'Сообщение не доставлено. '
                     f'Юзер {chat_id or "неизвестный"} заблокировал бота.')

    elif isinstance(event.exception, TelegramBadRequest):
        text = str(event.exception).lower()
        if ('message is not modified' in text
                or 'message to edit not found' in text):
            return True
        logger.error(f'BadRequest при работе с Telegram API: {event.exception}')

    elif isinstance(event.exception, TelegramNetworkError):
        logger.warning(f'Проблемы с интернет-соединением при запросе '
                       f'к Telegram API: {event.exception}')

    elif isinstance(event.exception, TelegramAPIError):
        logger.exception(f'TelegramAPIError: {event.exception}')

    elif isinstance(event.exception, AiogramError):
        logger.exception(f'Aiogram ошибка: {event.exception}')

    else:
        logger.exception(f'Необработанное исключение: {event.exception}')

    return True
