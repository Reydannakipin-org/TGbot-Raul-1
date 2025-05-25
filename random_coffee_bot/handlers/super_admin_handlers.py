import logging
from aiogram import Router
from aiogram.filters import Command, StateFilter
from aiogram.types import Message
from aiogram.fsm.state import default_state
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.context import FSMContext

from filters.super_admin_filters import (
    SuperAdminMessageFilter,
    SuperAdminCallbackFilter
)
from states.admin_states import FSMAdminPanel
from services.admin_service import (
    set_user_as_admin,
    set_admin_as_user,
    is_user_admin,
    is_admin_user,
    get_admin_list
)
from keyboards.admin_buttons import buttons_kb_admin
from keyboards.user_buttons import create_active_user_keyboard
from texts import ADMIN_TEXTS, KEYBOARD_BUTTON_TEXTS

logger = logging.getLogger(__name__)

super_admin_router = Router()

super_admin_router.message.filter(SuperAdminMessageFilter())
super_admin_router.callback_query.filter(SuperAdminCallbackFilter())


@super_admin_router.message(Command('add_admin'), StateFilter(default_state))
async def cmd_add_admin(message: Message, state: FSMContext):
    '''
    Хэндлер для команды добаления админа командой /add_admin.
    '''
    await message.answer(ADMIN_TEXTS['prompt_for_user_id'])
    await state.set_state(FSMAdminPanel.waiting_for_user_id)


@super_admin_router.message(
    Command("cancel"),
    StateFilter(FSMAdminPanel.waiting_for_user_id)
)
async def cancel_admin_handler(message: Message, state: FSMContext):
    '''
    Хэндлер для остановки добавления админа командой /cancel.
    '''
    await state.clear()
    await message.answer(ADMIN_TEXTS['creation_cancelled'])


@super_admin_router.message(StateFilter(FSMAdminPanel.waiting_for_user_id))
async def process_user_id(message: Message, state: FSMContext):
    '''
    Хэндлер для ввода ID пользователя, которого хотим сделать админом.
    '''
    if message.text in KEYBOARD_BUTTON_TEXTS.values():
        await message.answer(ADMIN_TEXTS['no_kb_buttons'])
        await message.answer(ADMIN_TEXTS['prompt_for_user_id'])
        return

    user_id_str = message.text

    if isinstance(user_id_str, str) and user_id_str.isdigit():
        user_id = int(user_id_str)

        if await is_user_admin(user_id):
            await message.answer(ADMIN_TEXTS['user_already_admin'])
            await state.clear()
            return

        success = await set_user_as_admin(user_id)

        if success:
            await message.answer(
                f"Пользователь с ID {user_id} теперь админ."
            )

            key = StorageKey(
                user_id=user_id,
                chat_id=user_id,
                bot_id=message.bot.id
            )
            user_ctx = FSMContext(storage=state.storage, key=key)
            await user_ctx.clear()

            await message.bot.send_message(
                user_id,
                ADMIN_TEXTS['now_admin_message'],
                reply_markup=buttons_kb_admin
            )
            await state.clear()
        else:
            await message.answer(f"Пользователь с ID {user_id} не найден.  Проверьте и отправьте новый ID.\n\nЧтобы отменить действие, отправьте /cancel.")
    else:
        logger.debug("Было введено не ID пользователя.")
        await message.answer(ADMIN_TEXTS['invalid_user_id_input'])


@super_admin_router.message(
    Command('remove_admin'),
    StateFilter(default_state)
)
async def cmd_remove_admin(message: Message, state: FSMAdminPanel):
    '''
    Хэндлер для удаления не главного админа командой /remove_admin.
    '''
    await message.answer(ADMIN_TEXTS['prompt_for_admin_id'])
    await state.set_state(FSMAdminPanel.waiting_for_admin_id)


@super_admin_router.message(
    Command("cancel"),
    StateFilter(FSMAdminPanel.waiting_for_admin_id)
)
async def cancel_user_handler(message: Message, state: FSMContext):
    '''
    Остановка удаления не главного админа командой /cancel.
    '''
    await state.clear()
    await message.answer(ADMIN_TEXTS['deletion_cancelled'])


@super_admin_router.message(StateFilter(FSMAdminPanel.waiting_for_admin_id))
async def process_admin_id(message: Message, state: FSMContext):
    '''
    Ввод ID не главного админа которого хочешь удалить.
    '''
    if message.text in KEYBOARD_BUTTON_TEXTS.values():
        await message.answer(ADMIN_TEXTS['no_kb_buttons'])
        await message.answer(ADMIN_TEXTS['prompt_for_admin_id'])
        return

    user_id_str = message.text
    if isinstance(user_id_str, str) and user_id_str.isdigit():
        user_id = int(user_id_str)

        if await is_admin_user(user_id):
            await message.answer(
                ADMIN_TEXTS['invalid_admin_user']
            )
            await state.clear()
            return

        success = await set_admin_as_user(user_id)

        if success:
            keyboard = create_active_user_keyboard()
            await message.answer(
                f"Пользователь с ID {user_id} теперь обычный пользователь в активном статусе и снова сможет принимать участие во встречах."
            )

            key = StorageKey(
                user_id=user_id,
                chat_id=user_id,
                bot_id=message.bot.id
            )
            user_ctx = FSMContext(storage=state.storage, key=key)
            await user_ctx.clear()

            await message.bot.send_message(
                user_id,
                "Ты больше не являешься админом и снова можешь участвовать во встречах Random Coffee.",
                reply_markup=keyboard)
            await state.clear()

        else:
            await message.answer(f"Админ с ID {user_id} не найден. Проверьте и отправьте новый ID.\n\nЧтобы отменить действие, отправьте /cancel.")

    else:
        logger.debug("Было введено не ID администратора.")
        await message.answer(
            ADMIN_TEXTS['invalid_admin_id']
        )


@super_admin_router.message(Command("admin_list"), StateFilter(default_state))
async def admin_list_handler(message: Message):
    '''
    Хэндлер для команды /admin_list, выводит список всех администраторов.
    '''
    admins = await get_admin_list()

    if not admins:
        await message.answer("Список админов пуст.")
        return

    admin_ids = [
        f"ID: {admin.telegram_id} - {admin.first_name} {admin.last_name or ''}"
        for admin in admins
    ]
    admin_list_message = "\n".join(admin_ids)

    await message.answer(f"Список админов:\n{admin_list_message}")
