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


participation_active = False

# Определение кнопок
button_change_my_details = KeyboardButton(text="✏️ Изменить мои данные")
button_my_status = KeyboardButton(text="📊 Мой статус участия")
button_edit_meetings = KeyboardButton(text="🗓️ Изменить частоту встреч")
button_stop_participation = KeyboardButton(text="⏸️ Приостановить участие")
button_how_it_works = KeyboardButton(text="❓ Как работает Random Coffee?")


def get_buttons_kb_user():
    global participation_active

    # Динамическое изменение текста кнопки "Приостановить участие"
    if participation_active:
        button_stop_participation.text = "▶️ Возобновить участие"
    else:
        button_stop_participation.text = "⏸️ Приостановить участие"

    buttons_kb_builder_user = ReplyKeyboardBuilder()
    buttons_kb_builder_user.row(
        button_change_my_details,
        button_my_status,
        button_edit_meetings,
        button_stop_participation,
        button_how_it_works,
        width=1
    )
    return buttons_kb_builder_user.as_markup(resize_keyboard=True)


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


@dp.message(F.text.in_(["⏸️ Приостановить участие", "▶️ Возобновить участие"]))
async def toggle_participation(message: Message):
    global participation_active

    # Меняем состояние участия
    participation_active = not participation_active

    # Обновляем клавиатуру с новым состоянием кнопки
    keyboard = get_buttons_kb_user()

    if participation_active:
        await message.answer("Вы возобновили участие!", reply_markup=keyboard)
    else:
        await message.answer("Вы приостановили участие!", reply_markup=keyboard)

dp.startup.register(set_main_menu)

if __name__ == "__main__":
    dp.run_polling(bot)
