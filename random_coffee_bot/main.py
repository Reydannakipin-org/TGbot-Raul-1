import asyncio
import logging

from aiogram import Bot, Dispatcher

from config import Config, load_config
# from database.db import create_database
from handlers.admin_handlers import admin_router
from handlers.users_handlers import user_router
from middlewares import GroupMemberMiddleware


logger = logging.getLogger(__name__)


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(filename)s:%(lineno)d #%(levelname)-8s '
               '[%(asctime)s] - %(name)s - %(message)s')

    logger.info('Старт бота')

    # Из переменной config можно получить переменные окружения в текущем файле.
    config: Config = load_config()
    group_tg_id = config.tg_bot.group_tg_id

    bot = Bot(
        token=config.tg_bot.token
    )
    dp = Dispatcher()
    dp.workflow_data.update({'group_tg_id': group_tg_id})

    dp.update.middleware(GroupMemberMiddleware())
    dp.include_router(admin_router)
    dp.include_router(user_router)


    # Так как БД сейчас настроена через Alembic, эта строчка не нужна.
    # Но оставим, если понадобиться вручную дропнуть БД и создать новую.
    # await create_database()

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
