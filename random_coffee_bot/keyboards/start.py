from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, BotCommand
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import Message, BotCommand, KeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from admin_buttons import buttons_kb_admin
from user_buttons import create_active_user_keyboard, create_inactive_user_keyboard
# from random_coffee_bot.services.user_service import get_user_by_telegram_id

import os
from dotenv import load_dotenv

load_dotenv()


bot = Bot(token=os.getenv("BOT_TOKEN"))
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


users_data = {
    751138564: {'active': True},  # Пример пользователя с активным статусом
    269444415: {'active': True}, # Пример пользователя с неактивным статусом
}


@dp.message(Command("user"))
async def process_user(message: Message):
    telegram_id = message.from_user.id  # Получаем telegram_id пользователя

    # Получаем данные пользователя из хранилища
    user_data = users_data.get(telegram_id)

    if user_data is not None:
        if user_data['active']:  # Проверяем значение поля active
            keyboard = create_active_user_keyboard()  # Создаем клавиатуру для активных пользователей
            await message.answer("Добро пожаловать обратно! Вы активный пользователь.", reply_markup=keyboard)
        else:
            keyboard = create_inactive_user_keyboard()  # Создаем клавиатуру для неактивных пользователей
            await message.answer("Вы неактивны. Пожалуйста, свяжитесь с администратором.", reply_markup=keyboard)
    else:
        keyboard = create_inactive_user_keyboard()  # Можно также показать неактивную клавиатуру для незарегистрированных пользователей
        await message.answer("Привет! Вы не зарегистрированы в системе.", reply_markup=keyboard)


@dp.message(F.text.in_(["⏸️ Приостановить участие", "▶️ Возобновить участие"]))
async def toggle_participation(message: Message):
    if message.text == "⏸️ Приостановить участие":
        keyboard = create_inactive_user_keyboard()
        await message.answer("Вы приостановили участие", reply_markup=keyboard)
    elif message.text == "▶️ Возобновить участие":
        keyboard = create_active_user_keyboard()
        await message.answer("Вы возобновили участие", reply_markup=keyboard)


# @dp.message(Command("user"))
# async def process_user(message: Message):
#     await message.answer(
#         text='Панель для пользователя',
#         reply_markup=buttons_kb_user
#     )


# @dp.message(Command("user"))
# async def cmd_start(message: Message):
#     telegram_id = message.from_user.id  # Получаем telegram_id пользователя
#     async with AsyncSession() as session:  # Создаем асинхронную сессию
#         user = await get_user_by_telegram_id(session, telegram_id)  # Получаем пользователя

#         if user:
#             # Проверяем статус пользователя (предполагаем, что у вас есть поле status)
#             if user.is_active:
#                 keyboard = create_active_user_keyboard()  # Создаем клавиатуру для активных пользователей
#                 await message.answer("Добро пожаловать обратно! Вы активный пользователь.", reply_markup=keyboard)
#             else:
#                 keyboard = create_inactive_user_keyboard()  # Создаем клавиатуру для неактивных пользователей
#                 await message.answer("Вы неактивны. Пожалуйста, свяжитесь с администратором.", reply_markup=keyboard)
#         else:
#             keyboard = create_inactive_user_keyboard()  # Можно также показать неактивную клавиатуру для незарегистрированных пользователей
#             await message.answer("Привет! Вы не зарегистрированы в системе.", reply_markup=keyboard)


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
