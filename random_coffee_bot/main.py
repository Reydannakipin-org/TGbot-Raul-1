import logging_config
logging_config.setup_logging()

import logging
logger = logging.getLogger(__name__)


import asyncio
from datetime import datetime

from bot import scheduler, schedule_feedback_jobs
from aiogram import Bot, Dispatcher
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from config import Config, load_config
from handlers.super_admin_handlers import super_admin_router
from handlers.admin_handlers import admin_router
from handlers.group_handlers import group_router
from handlers.common_handler import common_router
from handlers.users_handlers import user_router
from main_menu.super_admin_menu import set_super_admin_main_menu
from middlewares import AccessMiddleware
from globals import job_context
from services.admin_service import set_first_pairing_date


async def main():
    logger.info('Старт бота')

    # Из переменной config можно получить переменные окружения
    config: Config = load_config()
    group_tg_id = config.tg_bot.group_tg_id
    admins_list = config.tg_bot.admins_list
    google_sheet_id = config.g_sheet.sheet_id

    engine = create_async_engine(config.db.db_url, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    bot = Bot(
        token=config.tg_bot.token
    )
    dp = Dispatcher()
    job_context.set_context(bot, dp, session_maker)
    dp.workflow_data.update({
        'group_tg_id': group_tg_id,
        'admins_list': admins_list,
        'session_maker': session_maker,
        'google_sheet_id': google_sheet_id
    })

    dp.update.middleware(AccessMiddleware())
    dp.include_router(group_router)
    dp.include_router(super_admin_router)
    dp.include_router(admin_router)
    dp.include_router(user_router)
    dp.include_router(common_router)

    dp.startup.register(set_super_admin_main_menu)

    #  На случай, если нужно будет запланировать все задачи с чистого листа на новую дату:
    # scheduler.start()  # Для прода закоментировать
    # scheduler.remove_all_jobs()  # Для прода закоментировать

    # При первом запуске бота установить нужную дату и время первого
    # формирования пар (время UTC):
    await set_first_pairing_date(datetime(2025, 5, 27, 7, 00))

    await schedule_feedback_jobs(session_maker)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
