import logging

from aiogram import F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.state import default_state
from aiogram.types import Message

from filters.admin_filters import AdminCallbackFilter, AdminMessageFilter
from keyboards.admin_buttons import buttons_kb_admin
from texts import ADMIN_TEXTS


logger = logging.getLogger(__name__)

admin_router = Router()
admin_router.message.filter(AdminMessageFilter())
admin_router.callback_query.filter(AdminCallbackFilter())


@admin_router.message(CommandStart(), StateFilter(default_state))
async def process_start_command(message: Message):
    '''
    Хэндлер для команды /start админа.
    '''
    logger.info('Вошли в хэндлер, обрабатывающий команду /start')
    await message.answer(ADMIN_TEXTS['admin_welcome'],
                         reply_markup=buttons_kb_admin)


@admin_router.message(F.text, StateFilter(default_state))
async def fallback_handler(message: Message):
    await message.answer(ADMIN_TEXTS['admin_unknown_command'])
