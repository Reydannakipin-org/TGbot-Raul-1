from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, BotCommand
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import Message, BotCommand, KeyboardButton

from admin_buttons import buttons_kb_admin
from user_buttons import buttons_kb_user

BOT_TOKEN = '7652547374:AAEvVbIl-EkXvzwzdYCdywl2yV1T22JsecM'

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


async def set_main_menu(dispatcher: Dispatcher):
    main_menu_commands = [
        BotCommand(command="/start", description="Начало работы бота"),
        BotCommand(command="/info", description="Справка о работе бота"),
        BotCommand(command="/help", description="СТут будет что-нибудь"),
    ]
    await bot.set_my_commands(main_menu_commands)

dp.startup.register(set_main_menu)


@dp.message(Command("admin"))
async def process_admin(message: Message):
    await message.answer(
        text='Панель для администратора',
        reply_markup=buttons_kb_admin
    )


@dp.message(Command("user"))
async def process_user(message: Message):
    await message.answer(
        text='Панель для пользователя',
        reply_markup=buttons_kb_user
    )


@dp.message(Command("info"))
async def process_info(message: Message):
    await message.answer(
        text='Информация о боте',
        reply_markup=buttons_kb_admin
    )


@dp.message(F.text == "❓ Как работает Random Coffee?")
async def how_answer(message: Message):
    await message.answer(
        text="Тут будет описание того как должен работать этот бот"
    )

dp.startup.register(set_main_menu)

if __name__ == "__main__":
    dp.run_polling(bot)
