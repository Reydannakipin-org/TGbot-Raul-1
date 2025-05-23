from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat, MenuButtonCommands

from config import load_config


config = load_config()
admins_list = config.tg_bot.admins_list


async def set_super_admin_main_menu(bot: Bot):

    super_admin_commands = [
        BotCommand(command='/add_admin',
                   description='Дать роль админа'),
        BotCommand(command='/remove_admin',
                   description='Забрать роль админа'),
        BotCommand(command='/admin_list',
                   description='Список админов')
    ]

    await bot.set_my_commands(commands=[], scope=BotCommandScopeDefault())

    for admin_id in admins_list:
        try:
            await bot.set_my_commands(
                commands=super_admin_commands,
                scope=BotCommandScopeChat(chat_id=admin_id))

            await bot.set_chat_menu_button(
                chat_id=admin_id,
                menu_button=MenuButtonCommands()
            )
        except Exception:
            pass
