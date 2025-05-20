# from filters.admin_filters import AdminFilter
from filters.super_admin_filters import AdminMessageFilter
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
import logging
from aiogram.fsm.context import FSMContext
from states.admin_states import FSMAdminPanel
from services.admin_service import set_user_as_admin, set_admin_as_user
from aiogram.filters import StateFilter
from keyboards.admin_buttons import buttons_kb_admin
from keyboards.user_buttons import create_active_user_keyboard

logger = logging.getLogger(__name__)

super_admin_router = Router()

super_admin_router.message.filter(AdminMessageFilter())


@super_admin_router.message(Command('add_admin'), )
async def cmd_add_admin(message: Message, state: FSMContext):
    await message.answer(
        "Введи ID пользователя, которого хочешь сделать "
        "администратором. \n\nЕсли передумал(-а) создавать "
        "админестратора то нужно нажать на /cancel."
    )
    await state.set_state(FSMAdminPanel.waiting_for_user_id)


@super_admin_router.message(
    Command("cancel"),
    StateFilter(FSMAdminPanel.waiting_for_user_id)
)
async def cancel_admin_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Создание админестратора отменено.")


@super_admin_router.message(StateFilter(FSMAdminPanel.waiting_for_user_id))
async def process_user_id(message: Message, state: FSMContext):
    user_id = message.text

    if user_id.isdigit():
        user_id = int(user_id)

        success = await set_user_as_admin(user_id)

        if success:
            await message.answer(
                f"Пользователь с ID {user_id} теперь администратор."
            )
            await message.bot.send_message(
                user_id,
                "Теперь ты стал администратором",
                reply_markup=buttons_kb_admin
            )

        else:
            await message.answer(f"Пользователь с ID {user_id} не найден.")

    else:
        await message.answer(
           "Пожалуйста введи корректный числовой ID  пользователя."
        )

    await state.clear()


@super_admin_router.message(Command('remove_admin'))
async def cmd_remove_admin(message: Message, state: FSMAdminPanel):
    await message.answer(
        "Введи ID админа, которого хочешь сделать "
        "пользователем. \n\nЕсли передумал(-а) удалять "
        "админестратора то нажми на /cancel."
    )
    await state.set_state(FSMAdminPanel.waiting_for_admin_id)


@super_admin_router.message(
    Command("cancel"),
    StateFilter(FSMAdminPanel.waiting_for_admin_id)
)
async def cancel_user_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Удаление админестратора отменено.")


@super_admin_router.message(StateFilter(FSMAdminPanel.waiting_for_admin_id))
async def process_admin_id(message: Message, state: FSMAdminPanel):
    user_id = message.text

    if user_id.isdigit():
        user_id = int(user_id)

        success = await set_admin_as_user(user_id)

        if success:
            keyboard = create_active_user_keyboard()
            await message.answer(
                f"Пользователь с ID {user_id} теперь обычный пользователь."
            )
            await message.bot.send_message(
                user_id,
                "Теперь ты обычный пользователь",
                reply_markup=keyboard)

        else:
            await message.answer(f"Админестратор с ID {user_id} не найден.")

    else:
        await message.answer(
            "Пожалуйста введи корректный числовой  ID админестратора."
        )

    await state.clear()
