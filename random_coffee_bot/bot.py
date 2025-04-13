import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
# aiogram.types import ParseMode
#from aiogram.contrib.middlewares.logging import LoggingMiddleware
from handlers import start_handler, generate_pairs_handler
import sheets  # Импортируем модуль для работы с Google Sheets

API_TOKEN = '7620831052:AAFOts0bw_geXbk3P7i0_1buETFLnDg4VxY'  # Замените на ваш токен

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Регистрируем хэндлеры
dp.message.register(start_handler, Command("start"))
dp.message.register(generate_pairs_handler, Command("generate"))

async def main():
    # Инициализация базы данных
    # database.init_db()  # Если нужно, подключите базу данных
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())