import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from random_coffee_bot.texts import TEXTS


logger = logging.getLogger(__name__)

user_router = Router()


@user_router.message(CommandStart())
async def process_start_command(message: Message):
    logger.info('Вошли в хэндлер, обрабатывающий команду /start')
    await message.answer(TEXTS['start'])
