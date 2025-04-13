import logging
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
#from aiogram.contrib.middlewares.logging import LoggingMiddleware
from handlers import start_handler, generate_pairs_handler, set_schedule_handler
import sheets  # Импортируем модуль для работы с Google Sheets

API_TOKEN = '7620831052:AAFOts0bw_geXbk3P7i0_1buETFLnDg4VxY'  # Замените на ваш токен

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Создаем планировщик задач
scheduler = AsyncIOScheduler()

# Хранение интервала генерации пар в неделях
interval_weeks = 2  # По умолчанию раз в 2 недели

# Регистрируем хэндлеры
dp.message.register(start_handler, Command("start"))
dp.message.register(generate_pairs_handler, Command("generate"))
dp.message.register(set_schedule_handler, Command("set_schedule"))

# Функция для старта бота
async def main():
    # Инициализация базы данных
    # database.init_db()  # Если нужно, подключите базу данных

    # Запускаем APScheduler
    scheduler.start()

    # Планируем регулярную задачу на основе интервала
    scheduler.add_job(run_generation_task, 'interval', minutes=interval_weeks, id='generate_pairs', replace_existing=True)

    await dp.start_polling(bot)

async def run_generation_task():
    # Подключаемся к таблицам
    sheet, sheet_pair = sheets.connect_to_sheets()

    # Генерация пар
    new_pairs = sheets.generate_pairs(sheet, sheet_pair)

    # Сохраняем новые пары
    sheets.save_new_pairs(sheet_pair, new_pairs)

    print(f"Задача по генерации пар выполнена. {len(new_pairs)} новых пар добавлено.")

if __name__ == "__main__":
    asyncio.run(main())