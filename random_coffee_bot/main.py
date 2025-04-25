import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bot import setup_scheduler, schedule_feedback_jobs
from aiogram import Bot, Dispatcher
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from config import Config, load_config
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

    engine = create_async_engine(config.db.db_url, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    bot = Bot(
        token=config.tg_bot.token
    )
    dp = Dispatcher()
    dp.workflow_data.update({
        'group_tg_id': group_tg_id,
        'session': session_maker
    })

    dp.update.middleware(GroupMemberMiddleware())
    dp.include_router(admin_router)
    dp.include_router(user_router)
    setup_scheduler(session_maker, bot)
    schedule_feedback_jobs(bot, session_maker, dp)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
