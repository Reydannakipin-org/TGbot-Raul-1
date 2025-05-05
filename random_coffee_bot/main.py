import asyncio
import logging
from bot import schedule_feedback_jobs
from aiogram import Bot, Dispatcher
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from config import Config, load_config
from handlers.admin_handlers import admin_router
from handlers.users_handlers import user_router
from middlewares import AccessMiddleware
from globals import job_context

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
    admin_id = config.tg_bot.admin_tg_id
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
        'session_maker': session_maker,
        'admin_id': admin_id,
        'google_sheet_id': google_sheet_id
    })

    dp.update.middleware(AccessMiddleware())
    dp.include_router(admin_router)
    dp.include_router(user_router)

    await schedule_feedback_jobs(session_maker)
    #await reload_scheduled_jobs(bot, session_maker, dp)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())


