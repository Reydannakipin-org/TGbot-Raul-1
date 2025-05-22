import logging
from datetime import date, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state, StatesGroup, State
from aiogram.types import CallbackQuery, Message
from gspread.exceptions import (
    APIError,
    SpreadsheetNotFound,
    WorksheetNotFound
)
from oauth2client.client import HttpAccessTokenRefreshError
from sqlalchemy.exc import SQLAlchemyError

from bot import get_next_pairing_date, auto_pairing_wrapper, force_reschedule_job
from database.db import AsyncSessionLocal
from filters.admin_filters import AdminCallbackFilter, AdminMessageFilter
from keyboards.admin_buttons import (buttons_kb_admin,
                                     generate_inline_manage,
                                     generate_inline_confirm_change_interval,
                                     generate_inline_confirm_permission_false,
                                     generate_inline_confirm_permission_true,
                                     generate_inline_interval_options,
                                     generate_inline_notification_options,
                                     generate_inline_user_list,
                                     PageCallbackFactory,
                                     UsersCallbackFactory)
from services import admin_service as adm
from services.constants import DATE_FORMAT
from services.user_service import get_user_by_telegram_id
from states.admin_states import FSMAdminPanel
from texts import ADMIN_TEXTS, KEYBOARD_BUTTON_TEXTS

from zoneinfo import ZoneInfo
from sqlalchemy import select
from database.models import Setting


logger = logging.getLogger(__name__)


admin_router = Router()
admin_router.message.filter(AdminMessageFilter())
admin_router.callback_query.filter(AdminCallbackFilter())


@admin_router.message(CommandStart(), StateFilter(default_state))
async def process_start_command(message: Message):
    """
    Хэндлер для команды /start админа. Отправляет клавиатуру.
    """
    logger.info('Админ отправил /start')
    await message.answer(ADMIN_TEXTS['admin_welcome'],
                         reply_markup=buttons_kb_admin)


@admin_router.message(
        F.text == KEYBOARD_BUTTON_TEXTS['button_participant_management'],
        StateFilter(default_state))
async def process_participant_management(message: Message, state: FSMContext):
    """
    Хэндлер срабатывает при нажатии на кнопку клавиатуры "Управление
    участниками". Запрашивает у админа Telegram ID юзера, для которого
    хочет внести изменения. Переводит в состояние ожидания ввода ID.
    """
    logger.info('Админ нажал "Управление участниками"')
    await message.answer(ADMIN_TEXTS['ask_user_telegram_id'])
    await state.set_state(FSMAdminPanel.waiting_for_telegram_id)


@admin_router.message(StateFilter(FSMAdminPanel.waiting_for_telegram_id),
                      F.text.regexp(r'^\d+$'))
async def process_find_user_by_telegram_id(message: Message,
                                           state: FSMContext):
    """
    Хэндлер срабатывает в состоянии, когда мы получаем от админа цифры в
    качестве telegram ID. Если в БД есть юзер с таким ID, отправляем инфо
    о нем админу вместе с инлайн-клавиатурой для управления юзером.
    Если такого юзера нет, просим отправить новый ID.
    """
    user_telegram_id = int(message.text)  # type: ignore
    logger.info(f'Админ прислал ID юзера {user_telegram_id}')

    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_by_telegram_id(session, user_telegram_id)
            if user is None:
                logger.info('Пользователя с полученным ID нет в БД.')
                await message.answer(ADMIN_TEXTS['finding_user_fail'])
                return
            await adm.reset_user_pause_until(session, user)
    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        await message.answer(ADMIN_TEXTS['db_error'])

    logger.info(f'Пользователь {user_telegram_id} найден.')
    data_text = adm.format_text_about_user(
        ADMIN_TEXTS['finding_user_success'], user)
    ikb_participant_management = generate_inline_manage(
        user_telegram_id, user.has_permission)
    await message.answer(data_text,
                        reply_markup=ikb_participant_management)
    await state.clear()


@admin_router.message(StateFilter(FSMAdminPanel.waiting_for_telegram_id),
                      Command(commands='cancel'))
async def process_cancel(message: Message, state: FSMContext):
    """
    Хэндлер срабатывает в состоянии, когда мы ждем от админа цифры в качестве
    telegram ID, но он отправляет команду /cancel.
    """
    logger.info('Админ отменил поиск юзера.')
    await state.clear()
    await message.answer(ADMIN_TEXTS['cancel_finding_user'])


@admin_router.message(StateFilter(FSMAdminPanel.waiting_for_telegram_id),
                      Command(commands='list'))
async def process_get_all_users_list(message: Message, state: FSMContext):
    """
    Хэндлер срабатывает в состоянии, когда мы ждем от админа цифры в качестве
    telegram ID, но он отправляет команду /list. Отправляем ему сообщение
    со списком юзеров в виде инлайн-кнопок.
    """
    try:
        kb_bilder = await generate_inline_user_list()
    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        await message.answer(ADMIN_TEXTS['db_error'])
    await message.answer(
        text="Выберите нужного пользователя из списка:",
        reply_markup=kb_bilder.as_markup()
    )
    await state.clear()


@admin_router.message(StateFilter(FSMAdminPanel.waiting_for_telegram_id),
                      ~F.text.regexp(r'^\d+$'))
async def process_warning_not_numbers(message: Message, state: FSMContext):
    """
    Хэндлер срабатывает в состоянии, когда мы ждем от админа цифры в качестве
    telegram ID, но получаем не цифры. Просим админа ввести заново.
    """
    logger.info('Админ прислал в качестве телеграм ID не цифры.')
    await message.answer(ADMIN_TEXTS['warning_not_numbers'])


@admin_router.callback_query(PageCallbackFactory.filter(),
                             StateFilter(default_state))
async def paginate_users(callback: CallbackQuery,
                         callback_data: PageCallbackFactory):
    """
    Хэндлер срабатывает, когда админ нажимает на инлайн-кнопки навигации
    по списку пользователей.
    """
    page = callback_data.page
    try:
        kb = await generate_inline_user_list(page=page)
    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        if isinstance(callback.message, Message):
            await callback.message.answer(ADMIN_TEXTS['db_error'])
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            text="Выберите нужного пользователя из списка:",
            reply_markup=kb.as_markup()
        )
    await callback.answer()


@admin_router.callback_query(UsersCallbackFactory.filter(),
                             StateFilter(default_state))
async def show_user_details(callback: CallbackQuery,
                            callback_data: UsersCallbackFactory):
    """
    Хэндлре срабатывает, когда админ нажимает на инлайн-кнопку с
    именем пользователя в списке пользователей.
    """
    user_telegram_id = callback_data.telegram_id
    logger.info(f'Админ выбрал юзера {user_telegram_id}')
    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_by_telegram_id(session, user_telegram_id)
            if user is None:
                logger.info('Пользователя с полученным ID нет в БД.')
                if isinstance(callback.message, Message):
                    await callback.message.answer(ADMIN_TEXTS['finding_user_fail'])
                return
            await adm.reset_user_pause_until(session, user)
    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        if isinstance(callback.message, Message):
            await callback.message.answer(ADMIN_TEXTS['db_error'])
        return

    logger.info(f'Пользователь {user_telegram_id} найден.')
    data_text = adm.format_text_about_user(
        ADMIN_TEXTS['finding_user_success'], user)
    ikb_participant_management = generate_inline_manage(
        user_telegram_id, user.has_permission)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            data_text, reply_markup=ikb_participant_management)
    await callback.answer()


@admin_router.callback_query(lambda c: c.data.startswith('cancel:'),
                             StateFilter(default_state))
async def process_inline_cancel(callback: CallbackQuery):
    """
    Хэндлер срабатывает на нажатие админом инлайн-кнопки "Отменить"
    изменения конкретного юзера.
    """
    _, user_telegram_id = adm.parse_callback_data(callback.data)
    logger.info(f'Админ отменил работу с юзером {user_telegram_id}')

    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_by_telegram_id(session, int(user_telegram_id))
    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        await callback.answer(ADMIN_TEXTS['db_error'])
        return

    if user is None:
        logger.info('Пользователя с полученным ID нет в БД.')
        await callback.answer(ADMIN_TEXTS['finding_user_fail'])
        return
    else:
        data_text = adm.format_text_about_user(
            ADMIN_TEXTS['cancel_user_managing'], user
        )
        if isinstance(callback.message, Message):
            await callback.message.edit_text(text=data_text)
    await callback.answer()


@admin_router.callback_query(
        lambda c: c.data.startswith('set_has_permission_false:'),
        StateFilter(default_state))
async def process_set_has_permission_false(callback: CallbackQuery):
    """
    Хэндлер срабатывает на нажатие админом инлайн-кнопки "Запретить
    пользоваться ботом" конкретному юзеру и заменяет предыдущее сообщение
    на новое с инлайн-кнопками для подтверждения действия.
    """
    _, user_telegram_id = adm.parse_callback_data(callback.data)
    logger.info(f'Админ нажал "Запретить пользоваться ботом" '
                f'для юзера {user_telegram_id}')

    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_by_telegram_id(session, user_telegram_id)
    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        await callback.answer(ADMIN_TEXTS['db_error'])

    if user is None:
        logger.info('Пользователя с полученным ID нет в БД.')
        await callback.answer(ADMIN_TEXTS['finding_user_fail'])
        return
    else:
        data_text = adm.format_text_about_user(
            ADMIN_TEXTS['confirm_set_has_permission_false'], user
        )
        if isinstance(callback.message, Message):
            await callback.message.edit_text(
                text=data_text,
                reply_markup=generate_inline_confirm_permission_false(
                    user_telegram_id)
            )
    await callback.answer()


@admin_router.callback_query(
        lambda c: c.data.startswith('confirm_set_has_permission_false:'),
        StateFilter(default_state))
async def process_confirm_set_has_permission_false(callback: CallbackQuery):
    """
    Хэндлер срабатывает, если админ нажимает инлайн-кнопку "да" для
    подтверждения запретить юзеру пользоваться ботом. Отправляет
    сообщение с подтверждением действия.
    """
    _, user_telegram_id = adm.parse_callback_data(callback.data)
    logger.info(f'Админ подтвердил, что хочет запретить юзеру '
                f'{user_telegram_id} пользоваться ботом.')

    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_by_telegram_id(session, user_telegram_id)

            if user is None:
                logger.info('Пользователя с полученным ID нет в БД.')
                await callback.answer(ADMIN_TEXTS['finding_user_fail'])
                return
            else:
                await adm.set_user_permission(session, user, False)

    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        await callback.answer(ADMIN_TEXTS['db_error'])

    logger.info('У юзера больше нет разрешения использовать бота.')
    data_text = adm.format_text_about_user(
        ADMIN_TEXTS['success_set_has_permission_false'], user
    )
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text=data_text)
    await callback.answer()


@admin_router.callback_query(
        lambda c: c.data.startswith('return_to_find_user_by_telegram_id:'),
        StateFilter(default_state))
async def process_find_user_by_telegram_id_cb(callback: CallbackQuery):
    """
    Хэндлер срабатывает, если админ на просьбу подтвердить какие-то изменения
    для юзера нажимает "нет". Возвращает админа к сообщению с
    данными юзера и инлайн-кнопками для управления им.
    """
    _, user_telegram_id = adm.parse_callback_data(callback.data)
    logger.info(f'Админ отменил изменение юзера {user_telegram_id}')

    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_by_telegram_id(session, user_telegram_id)
    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        await callback.answer(ADMIN_TEXTS['db_error'])

    if user is None:
        logger.info('Пользователя с полученным ID нет в БД.')
        await callback.answer(ADMIN_TEXTS['finding_user_fail'])
        return
    else:
        logger.info('Возвращаем админа к сообщению с инфо о юзере.')
        data_text = adm.format_text_about_user(
            ADMIN_TEXTS['finding_user_success'], user)
        ikb_participant_management = generate_inline_manage(
            user_telegram_id, user.has_permission)
        if isinstance(callback.message, Message):
            await callback.message.edit_text(
                text=data_text,
                reply_markup=ikb_participant_management)
    await callback.answer()


@admin_router.callback_query(
        lambda c: c.data.startswith('set_has_permission_true:'),
        StateFilter(default_state))
async def process_set_has_permission_true(callback: CallbackQuery):
    """
    Хэндлер срабатывает на нажатие админом инлайн-кнопки "Разрешить
    пользоваться ботом" конкретному юзеру и заменяет предыдущее сообщение
    на новое с инлайн-кнопками для подтверждения действия.
    """
    _, user_telegram_id = adm.parse_callback_data(callback.data)
    logger.info(f'Админ нажал "Разрешить пользоваться ботом" для '
                f'юзера {user_telegram_id}')

    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_by_telegram_id(session, user_telegram_id)
    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        await callback.answer(ADMIN_TEXTS['db_error'])

    if user is None:
        logger.info('Пользователя с полученным ID нет в БД.')
        await callback.answer(ADMIN_TEXTS['finding_user_fail'])
        return
    else:
        data_text = adm.format_text_about_user(
            ADMIN_TEXTS['confirm_set_has_permission_true'], user
        )
        if isinstance(callback.message, Message):
            await callback.message.edit_text(
                text=data_text,
                reply_markup=generate_inline_confirm_permission_true(
                    user_telegram_id)
            )
    await callback.answer()


@admin_router.callback_query(
        lambda c: c.data.startswith('confirm_set_has_permission_true:'),
        StateFilter(default_state))
async def process_confirm_set_has_permission_true(callback: CallbackQuery):
    """
    Хэндлер срабатывает, если админ нажимает инлайн-кнопку "да" для
    подтверждения разрешить юзеру пользоваться ботом. Отправляет
    сообщение с подтверждением действия.
    """
    _, user_telegram_id = adm.parse_callback_data(callback.data)
    logger.info(f'Админ потвердил, что хочет разрешить юзеру '
                f'{user_telegram_id} пользоваться ботом.')

    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_by_telegram_id(session, user_telegram_id)

            if user is None:
                logger.info('Пользователя с полученным ID нет в БД.')
                await callback.answer(ADMIN_TEXTS['finding_user_fail'])
                return
            await adm.set_user_permission(session, user, True)
    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        await callback.answer(ADMIN_TEXTS['db_error'])

    logger.info('У юзера снова есть разрешение использовать бота.')
    data_text = adm.format_text_about_user(
        ADMIN_TEXTS['success_set_has_permission_true'], user
    )
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text=data_text)
    await callback.answer()


@admin_router.callback_query(
        lambda c: c.data.startswith('set_pause:'),
        StateFilter(default_state))
async def process_set_pause(callback: CallbackQuery, state: FSMContext):
    """
    Хэндлер срабатывает на нажатие админом инлайн-кнопки "Поставить на паузу"
    конкретного юзера и заменяет предыдущее сообщение
    на новое с просьюой отправить дату.
    Устанавливает состояние: ожидание ввода даты.
    """
    _, user_telegram_id = adm.parse_callback_data(callback.data)
    logger.info(f'Админ нажал "Поставить на паузу" юзера {user_telegram_id}')

    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_by_telegram_id(session, user_telegram_id)
    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        await callback.answer(ADMIN_TEXTS['db_error'])

    if user is None:
        logger.info('Пользователя с полученным ID нет в БД.')
        await callback.answer(ADMIN_TEXTS['finding_user_fail'])
        return
    else:
        data_text = adm.format_text_about_user(
            ADMIN_TEXTS['ask_date_for_pause'], user
        )
        if isinstance(callback.message, Message):
            await callback.message.edit_text(
                text=data_text)
        await state.set_state(FSMAdminPanel.waiting_for_end_pause_date)
        await state.update_data(user_telegram_id=user_telegram_id)
    await callback.answer()


@admin_router.message(StateFilter(FSMAdminPanel.waiting_for_end_pause_date),
                      Command(commands='cancel'))
async def process_cancel_setting_pause(message: Message, state: FSMContext):
    """
    Хэндлер срабатывает в состоянии, когда мы ждем от админа цифры в качестве
    telegram ID, но он отправляет команду /cancel.
    """
    logger.info('Админ отменил установку паузы для юзера.')
    await state.clear()
    await message.answer(ADMIN_TEXTS['cancel_setting_user_pause'])


@admin_router.message(StateFilter(FSMAdminPanel.waiting_for_end_pause_date),
                      F.text.func(lambda t: bool(t and adm.is_valid_date(t))))
async def process_check_date_for_pause(message: Message, state: FSMContext):
    """
    Хэндлер срабатывает в состоянии, когда мы ждем от админа дату , до
    которой юзера нужно поставить на паузу,
    и админ присылает дату в верном формате.
    """
    parsed_date = datetime.strptime(message.text, DATE_FORMAT).date()  # type: ignore

    today = date.today()
    if parsed_date < today:
        logger.info('Админ указал дату окончания паузы в прошлом.')
        await message.answer(ADMIN_TEXTS['past_date_for_pause'])
        return

    max_allowed = today + timedelta(days=365)
    if parsed_date > max_allowed:
        logger.info('Админ указал дату окончания паузы, до которой '
                    'больше года.')
        await message.answer(ADMIN_TEXTS['more_than_year_pause'])
        return

    user_telegram_id = await state.get_value('user_telegram_id')
    logger.info(f'Получен id {user_telegram_id} из данных состояния.')
    await state.clear()

    try:
        async with AsyncSessionLocal() as session:
            user = await get_user_by_telegram_id(session, user_telegram_id)

            if user is None:
                logger.info('Пользователя с полученным ID нет в БД.')
                await message.answer(ADMIN_TEXTS['finding_user_fail'])
                return

            if parsed_date == today:
                await adm.set_user_pause_until(session, user, None)
                logger.info('Пользователю убрана дата окончания паузы.')
                data_text = adm.format_text_about_user(
                    ADMIN_TEXTS['no_pause_until'], user)
            else:
                await adm.set_user_pause_until(session, user, parsed_date)
                logger.info('Пользователю установлена дата окончания паузы.')
                data_text = adm.format_text_about_user(
                    ADMIN_TEXTS['success_set_pause_untill'], user)
    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        await message.answer(ADMIN_TEXTS['db_error'])
        return

    await message.answer(data_text)


@admin_router.message(StateFilter(FSMAdminPanel.waiting_for_end_pause_date))
async def process_wrong_date_for_pause(message: Message, state: FSMContext):
    """
    Хэндлер срабатывает в состоянии, когда мы ждем от админа дату , до
    которой юзера нужно поставить на паузу, но получаем некорректные данные.
    """
    logger.info('Получены неверные данные в качестве даты.')
    await message.answer(ADMIN_TEXTS['wrong_date_for_pause'])


@admin_router.message(
        F.text == KEYBOARD_BUTTON_TEXTS['button_change_interval'],
        StateFilter(default_state))
async def process_button_change_interval(message: Message):
    """
    Хэндлер срабатывает при нажатии на кнопку клавиатуры "Изменить интервал".
    Отправляет сообщение с инлайн-кнопками для подтверждения действия.
    """
    logger.info('Админ нажал кнопку "Изменить интервал".')
    try:
        async with AsyncSessionLocal() as session:
            current_interval = await adm.get_global_interval(session)
    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        await message.answer(ADMIN_TEXTS['db_error'])

    next_pairing_date = get_next_pairing_date()

    data_text = adm.create_text_with_interval(
        ADMIN_TEXTS['confirm_changing_interval'],
        current_interval, next_pairing_date)

    await message.answer(
        text=data_text,
        reply_markup=generate_inline_confirm_change_interval())


@admin_router.callback_query(F.data == 'confirm_changing_interval',
                             StateFilter(default_state))
async def process_choose_new_interval(callback: CallbackQuery):
    """
    Хэндлер срабатывает, когда админ подтверждает, что хочет задать
    новый глобальный интервал. Отправляет сообщение с инлайн-кнопка
    возможных вариантов для нового интервала.
    """
    logger.info('Админ подтвердил, что хочет изменить интервал.')
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            text=ADMIN_TEXTS['choose_interval'],
            reply_markup=generate_inline_interval_options()
        )
    await callback.answer()


@admin_router.callback_query(
        lambda c: c.data.startswith('new_global_interval:'),
        StateFilter(default_state))
async def process_set_new_interval(callback: CallbackQuery):
    """
    Хэндлер срабатывает на нажатие админом инлайн-кнопки с одним из
    вариантов интервала. Устанавливает выбранный вариант как новый
    глобальный интервал в базе данных.
    """
    _, new_interval_str = adm.parse_callback_data(callback.data)
    try:
        new_interval = int(new_interval_str.strip())
    except ValueError:
        logger.error('Невозможно привести интервал из коллбэка к int.')
        return
    try:
        async with AsyncSessionLocal() as session:
            current_interval = await adm.set_new_global_interval(
                session, new_interval)
    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        await callback.answer(ADMIN_TEXTS['db_error'])

    next_pairing_date = get_next_pairing_date()
    data_text = adm.create_text_with_interval(
        ADMIN_TEXTS['success_new_interval'],
        current_interval, next_pairing_date)
    logger.info('Админ установил новый интервал.')

    if isinstance(callback.message, Message):
        await callback.message.edit_text(text=data_text)
    await callback.answer()


@admin_router.callback_query(F.data == 'cancel_changing_interval',
                             StateFilter(default_state))
async def process_cancel_changing_interval(callback: CallbackQuery):
    """
    Срабатывает, если админ передумал менять глобальный интервал.
    """
    logger.info('Админ отменил изменение интервала.')
    try:
        async with AsyncSessionLocal() as session:
            current_interval = await adm.get_global_interval(session)
    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        await callback.answer(ADMIN_TEXTS['db_error'])

    next_pairing_date = get_next_pairing_date()
    data_text = adm.create_text_with_interval(
        ADMIN_TEXTS['cancel_changing_interval'],
        current_interval, next_pairing_date)

    if isinstance(callback.message, Message):
        await callback.message.edit_text(text=data_text)
    await callback.answer()


@admin_router.message(F.text == KEYBOARD_BUTTON_TEXTS['button_google_sheets'],
                      StateFilter(default_state))
async def process_export_to_gsheet(message: Message, google_sheet_id):
    """
    Хэндлер срабатывает при нажатии на кнопку клавиатуры "Выгрузить в
    гугл таблицу". Делает экспорт данных и отправляет админу ссылку на таблицу.
    Параметр google_sheet_id приходит из workflow_data диспетчера, куда должен
    быть передан при инициализации из конфига.
    """
    logger.info('Админ нажал "выгрузить в гугл-таблицу".')
    await message.answer(ADMIN_TEXTS['start_export_data'])

    try:
        async with AsyncSessionLocal() as session:
            users = await adm.fetch_all_users(session)
            pairs = await adm.fetch_all_pairs(session)
        await adm.export_users_to_gsheet(users)
        await adm.export_pairs_to_gsheet(pairs)

    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        await message.answer(ADMIN_TEXTS['db_error'])
    except SpreadsheetNotFound:
        logger.exception('❌ Не нашёл таблицу по этому ID. '
                         'Проверьте SPREADSHEET_ID и доступы.')
        await message.answer(ADMIN_TEXTS['error_google_sheets_settings'])
    except WorksheetNotFound:
        logger.exception('❌ Лист с нужным именем не найден. '
                         'Проверьте, чтобы имена листов соответсвовали '
                         'инструкции разработчиков.')
        await message.answer(ADMIN_TEXTS['error_google_sheets_wrong_name'])
    except APIError as e:
        logger.exception(f'❌ Ошибка API Google Sheets: '
                         f'{e.response.status_code} — {e.response.reason}')
        await message.answer(ADMIN_TEXTS['error_google_sheets_unknown'])
    except HttpAccessTokenRefreshError:
        logger.exception('❌ Не удалось обновить токен доступа. Проверьте '
                         'credentials.json и права сервис-аккаунта.')
        await message.answer(ADMIN_TEXTS['error_google_sheets_settings'])
    except Exception as e:
        logger.exception(f'❌ Неожиданная ошибка при записи в Google '
                         f'Sheets:\n{e}')
        await message.answer(ADMIN_TEXTS['error_google_sheets_unknown'])
    else:
        logger.info('Экспорт в гугл-таблицу завершен успешно.')
        text = ADMIN_TEXTS['success_export_data'].format(
            google_sheet_id=google_sheet_id)
        await message.answer(
            text=text, parse_mode='HTML'
        )


@admin_router.message(
        F.text == KEYBOARD_BUTTON_TEXTS['button_send_notification'],
        StateFilter(default_state))
async def process_create_notification(message: Message, state: FSMContext):
    await message.answer(ADMIN_TEXTS['ask_text_for_notif'])
    await state.set_state(FSMAdminPanel.waiting_for_text_of_notification)


@admin_router.message(
        F.text == KEYBOARD_BUTTON_TEXTS['button_info'],
        StateFilter(default_state))
async def process_get_info(message: Message):
    try:
        async with AsyncSessionLocal() as session:
            current_interval = await adm.get_global_interval(session)
            number_of_users, number_of_active_users = (
                await adm.get_users_count(session))
    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        await message.answer(ADMIN_TEXTS['db_error'])

    next_pairing_date = get_next_pairing_date()

    extra_data = {
        'all_users': number_of_users,
        'active_users': number_of_active_users
    }

    data_text = adm.create_text_with_interval(
        ADMIN_TEXTS['info'],
        current_interval, next_pairing_date, extra_data)

    await message.answer(data_text)


@admin_router.message(Command(commands='cancel'),
                      FSMAdminPanel.waiting_for_text_of_notification)
async def process_cancel_creating_notif(message: Message, state: FSMContext):
    await message.answer(ADMIN_TEXTS['cancel_creating_notif'])
    await state.clear()


@admin_router.message(FSMAdminPanel.waiting_for_text_of_notification)
async def process_get_text_of_notification(message: Message,
                                           state: FSMContext):
    if not message.text:
        await message.answer(ADMIN_TEXTS['reject_no_text'])
        return
    else:
        received_text = message.text.strip()
    try:
        async with AsyncSessionLocal() as session:
            notif = await adm.create_notif(session, received_text)
    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        await message.answer(ADMIN_TEXTS['db_error'])
        return
    confirm_text = (ADMIN_TEXTS['ask_confirm_sending_notif']
                    .format(notif_text=notif.text))
    inline_kb = generate_inline_notification_options(notif.id)
    await state.clear()
    await message.answer(confirm_text, reply_markup=inline_kb)


@admin_router.callback_query(lambda c: c.data.startswith('confirm_notif:'),
                             StateFilter(default_state))
async def process_send_notif(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    _, notif_id_str = adm.parse_callback_data(callback.data)
    try:
        notif_id = int(notif_id_str)
        notif = await adm.get_notif(notif_id)
    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        if isinstance(callback.message, Message):
            await callback.message.answer(ADMIN_TEXTS['db_error'])
        return
    except ValueError:
        logger.error('Не передан id нотификации в коллбэке.')
        if isinstance(callback.message, Message):
            await callback.message.answer(ADMIN_TEXTS['code_error'])
        return
    if isinstance(callback.message, Message):
        await callback.message.edit_text(ADMIN_TEXTS['start_sending_notif']
                                         .format(notif_text=notif.text))
    try:
        delivered_notif, reason = await adm.broadcast_notif_to_active_users(
            bot, notif)
    except SQLAlchemyError:
        logger.exception('Ошибка при работе с базой данных')
        if isinstance(callback.message, Message):
            await callback.message.answer(ADMIN_TEXTS['db_error'])
        return

    if not delivered_notif:
        if isinstance(callback.message, Message):
            await callback.message.answer(reason)
        return
    if isinstance(callback.message, Message):
        await callback.message.answer(ADMIN_TEXTS['success_broadcast']
                                      .format(n=delivered_notif))


@admin_router.callback_query(F.data == 'edit_notif',
                             StateFilter(default_state))
async def process_create_other_notification(callback: CallbackQuery,
                                            state: FSMContext):
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(ADMIN_TEXTS['ask_text_for_notif'])
    await state.set_state(FSMAdminPanel.waiting_for_text_of_notification)


@admin_router.callback_query(F.data == 'cancel_notif',
                             StateFilter(default_state))
async def process_cancel_notif(callback: CallbackQuery):
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(ADMIN_TEXTS['notif_is_canceled'])


# Приостановить создание пар
@admin_router.message(Command("pause_pairing"), StateFilter(default_state))
async def pause_pairing_handler(message: Message, session_maker):
    async with session_maker() as session:
        setting = await session.execute(select(Setting))
        setting_obj = setting.scalar_one_or_none()

        if setting_obj:
            setting_obj.auto_pairing_paused = True
        else:
            setting_obj = Setting(auto_pairing_paused=True)
            session.add(setting_obj)

        await session.commit()
    await message.answer("🛑 Формирование пар временно приостановлено.")

# Возобновить создание пар лучше использовать это, тут нельзя указать когда запустить бота но он продолжит в том интеравале какой был
# @user_router.message(Command("resume_pairing"))
# async def resume_pairing_handler(message: Message, session_maker):
#     async with session_maker() as session:
#         setting = await session.execute(select(Setting))
#         setting_obj = setting.scalar_one_or_none()
#
#         if setting_obj and setting_obj.auto_pairing_paused:
#             setting_obj.auto_pairing_paused = False
#             await session.commit()
#             await message.reply("✅ Формирование пар возобновлено.")
#         else:
#             await message.reply("ℹ️ Формирование пар и так активно.")


class ResumePairingStates(StatesGroup):
    waiting_for_days_input = State()


@admin_router.message(Command("resume_pairing"), StateFilter(default_state))
async def resume_pairing_start(message: Message, state: FSMContext):
    await message.answer("📆 Через сколько дней возобновить формирование пар? Введи число от 0 до 30:")
    await state.set_state(ResumePairingStates.waiting_for_days_input)

# Возобновить создание пар, feedback_dispatcher не будет запушен за 3 дня до формирования пар если не попасть в тайминг
@admin_router.message(ResumePairingStates.waiting_for_days_input)
async def process_days_input(message: Message, state: FSMContext, session_maker):
    try:
        days = int(message.text.strip())
        if days < 0 or days > 30:
            await message.answer("⛔ Введи число от 0 до 30.")
            return
    except ValueError:
        await message.answer("⛔ Пожалуйста, введи целое число.")
        return

    async with session_maker() as session:
        result = await session.execute(select(Setting).where(Setting.key == "global_interval"))
        setting = result.scalar_one_or_none()


        if not setting.auto_pairing_paused:
            await message.answer("ℹ️ Формирование пар уже активно.")
            await state.clear()
            return

        setting.auto_pairing_paused = False
        setting.first_matching_date = datetime.now(ZoneInfo("Europe/Moscow")) + timedelta(days=days)
        await session.commit()

        start_date = setting.first_matching_date
        interval_minutes = int(setting.value)
        pairing_day = interval_minutes * 7

        force_reschedule_job(
            job_id="auto_pairing_weekly",
            func=auto_pairing_wrapper,
            interval_minutes=pairing_day,
            session_maker=session_maker,
            start_date=start_date
        )

        await message.answer(
            f"✅ Формирование пар возобновлено. Следующий запуск через {days} дней: {start_date.strftime('%Y-%m-%d %H:%M:%S')}"
        )

    await state.clear()

@admin_router.message()
async def other_type_handler(message: Message):
    """
    Хэндлер срабатывает, когда админ отправляет что-то кроме текста,
    что бот не может обработать.
    """
    logger.info('Админ отправил что-то кроме текста.')
    await message.answer(ADMIN_TEXTS['admin_unknown_type_data'],
                         reply_markup=buttons_kb_admin)


@admin_router.message(F.text)
async def fallback_handler(message: Message):
    """
    Хэндлер срабатывает, когда админ отправляет неизвестную команду или текст.
    """
    logger.info('Админ отправил неизвестную команду.')
    await message.answer(ADMIN_TEXTS['admin_unknown_command'],
                         reply_markup=buttons_kb_admin)