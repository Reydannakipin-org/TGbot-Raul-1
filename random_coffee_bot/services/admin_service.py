import logging
from datetime import date, datetime
from typing import Optional, Sequence

import asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from database.models import Feedback, Pair, Setting, User
from services.constants import DATE_FORMAT
from services.user_service import get_user_by_telegram_id
from texts import ADMIN_TEXTS, INTERVAL_TEXTS
from utils.google_sheets import pairs_sheet, users_sheet


logger = logging.getLogger(__name__)


async def set_user_permission(session: AsyncSession,
                              user: User,
                              has_permission: bool
                              ) -> bool:
    """
    Изменяет значение флага has_permission.
    Возвращает True, если пользователь найден и обновлен.
    """
    try:
        user.has_permission = has_permission
        if not has_permission:
            user.is_active = False
        await session.commit()
        return True
    except SQLAlchemyError as e:
        await session.rollback()
        logger.exception(f'Ошибка при обновлении пользователя '
                         f'{user.telegram_id}')
        raise e


async def set_user_pause_until(session: AsyncSession,
                               user: User,
                               input_date: date
                               ) -> bool:
    """
    Изменяет значение флага has_permission.
    Возвращает True, если пользователь найден и обновлен.
    """
    try:
        user.pause_until = input_date
        await session.commit()
        return True
    except SQLAlchemyError as e:
        await session.rollback()
        logger.exception(f'Ошибка при обновлении пользователя '
                         f'{user.telegram_id}')
        raise e


def format_text_about_user(template: str,   user: User,
                           extra_fields: Optional[dict[str, str]] = None
                           ) -> str:
    """
    Форматирует текст на основе шаблона и атрибутов пользователя.
    """
    data = {
        'first_name': user.first_name or ADMIN_TEXTS['no_data'],
        'last_name': user.last_name or '',
        'status': (ADMIN_TEXTS['status_active_true'] if user.is_active
                   else ADMIN_TEXTS['status_active_false']),
        'permission': (ADMIN_TEXTS['has_permission_true']
                       if user.has_permission
                       else ADMIN_TEXTS['has_permission_false']),
        'interval': (INTERVAL_TEXTS[str(user.pairing_interval)]
                     if user.pairing_interval
                     else INTERVAL_TEXTS['default']),
        'pause_until': (user.pause_until.strftime(DATE_FORMAT)
                        if user.pause_until else ADMIN_TEXTS['no_settings']),
    }
    if extra_fields:
        data.update(extra_fields)
    return template.format(**data)


def create_text_with_interval(text: str,
                              current_interval: Optional[str],
                              next_pairing_date: Optional[date]) -> str:
    """
    Подставляет значения для переменных interval и next_pairing_date
    в полученном тексте.
    """
    if current_interval is None:
        interval_text = ADMIN_TEXTS['no_data']
    else:
        interval_text = INTERVAL_TEXTS.get(current_interval,
                                           INTERVAL_TEXTS['default'])

    if next_pairing_date:
        date_text = next_pairing_date.strftime(DATE_FORMAT)
    else:
        date_text = ADMIN_TEXTS['unknown']

    data_text = text.format(
        interval=interval_text,
        next_pairing_date=date_text)
    return data_text


def is_valid_date(txt: str) -> bool:
    """
    Проверяет, являются ли данные из строки датой в нужном формате.
    """
    try:
        datetime.strptime(txt, DATE_FORMAT)
        return True
    except ValueError:
        return False


def parse_callback_data(data: str) -> tuple[str, str]:
    """
    Разбирает callback.data в формате 'action:param' и возвращает
    кортеж (action, param).
    """
    try:
        action, param = data.split(':', 1)
        return action, param
    except ValueError:
        logger.error(f'Неверные данные у коллбека: {data}')
        raise


async def get_global_interval(session: AsyncSession) -> Optional[str]:
    """
    Возвращает из базы данных значение глобального интервала.
    """
    result = await session.execute(
        select(Setting.value).where(Setting.key == 'global_interval')
    )
    return result.scalar()


async def set_new_global_interval(session: AsyncSession, new_value: int
                                  ) -> str:
    """
    Изменяет значение глобального интервала в таблице settings.
    Возвращает True, если интервал обновлен.
    """
    try:
        result = await session.execute(
            select(Setting).where(Setting.key == 'global_interval')
        )
        current_interval = result.scalars().first()

        if current_interval:
            current_interval.value = new_value
        else:
            current_interval = Setting(key='global_interval', value=new_value)
            session.add(current_interval)

        await session.commit()
        logger.info(f'Установленный интервал {current_interval}')
        return current_interval.value
    except SQLAlchemyError as e:
        await session.rollback()
        logger.exception('Ошибка при установке нового интервала')
        raise e


def get_next_pairing_date() -> Optional[date]:
    """
    Возвращает дату, когда состоится следующее формирование пар
    согласно планировщику задач.
    """
    # TODO
    return None


async def get_all_users(session: AsyncSession) -> Sequence[User]:
    """
    Извлекает из БД всех пользователей, сортирует по дате присоединения.
    """
    try:
        result = await session.execute(
            select(User).order_by(User.joined_at)
        )
        users = result.scalars().all()
        return users

    except SQLAlchemyError as e:
        await session.rollback()
        logger.exception('Ошибка при получении из БД всех пользователей.')
        raise e


async def export_users_to_gsheet(
    session: AsyncSession
) -> int:
    """
    Берёт всех пользователей из БД и записывает их в Гугл Таблицу.
    Возвращает число отправленных строк.
    """
    logger.info('Начниаем экспорт юзеров.')
    users = await get_all_users(session)
    worksheet = users_sheet
    loop = asyncio.get_running_loop()

    rows: list[list[str]] = []
    headers = ['telegram_id', 'Имя', 'Фамилия', 'Активен?', 'Есть разрешение?',
               'Интервал', 'На паузе до', 'Дата присоединения']
    rows.append(headers)

    for u in users:
        telegram_id = u.telegram_id
        first_name = u.first_name
        last_name = u.last_name if u.last_name else '-'
        is_active = 'да' if u.is_active else 'нет'
        has_permission = 'да' if u.has_permission else 'нет'
        pairing_interval = (INTERVAL_TEXTS['default'] if not u.pairing_interval
                            else INTERVAL_TEXTS[str(u.pairing_interval)])
        pause_until = (u.pause_until.strftime(DATE_FORMAT) if u.pause_until
                       else '')
        joined_at = u.joined_at.strftime(DATE_FORMAT)

        rows.append([telegram_id, first_name, last_name, is_active,
                     has_permission, pairing_interval, pause_until, joined_at])
    logger.info(f'Сформировано строк {len(rows)-1}')

    await loop.run_in_executor(None, worksheet.clear)
    await loop.run_in_executor(None, worksheet.append_rows, rows)
    logger.info('Таблица юзеров экспортирована.')

    return len(users)


async def get_all_pairs(session: AsyncSession) -> Sequence[Pair]:
    """
    Извлекает из БД всех пользователей, сортирует по дате присоединения.
    """
    try:
        result = await session.execute(
            select(Pair)
            .options(
                selectinload(Pair.user1),
                selectinload(Pair.user2),
                selectinload(Pair.feedbacks).selectinload(Feedback.user)
            ).order_by(Pair.paired_at.desc())
        )
        pairs = result.scalars().all()
        return pairs

    except SQLAlchemyError as e:
        await session.rollback()
        logger.exception('Ошибка при получении из БД всех пар.')
        raise e


async def export_pairs_to_gsheet(
    session: AsyncSession
) -> int:
    """
    Берёт всех пользователей из БД и записывает их в Гугл Таблицу.
    Возвращает число отправленных строк.
    """
    logger.info('Начинаем экспорт пар и отзывов.')
    pairs = await get_all_pairs(session)
    worksheet = pairs_sheet
    loop = asyncio.get_running_loop()

    rows: list[list[str]] = []
    headers = ['Дата', 'Коллега 1', 'Была встреча?', 'Коммент',
               'Коллега 2', 'Была встреча?', 'Коммент']
    rows.append(headers)

    def get_feedback_data(fb: Feedback | None) -> tuple[str, str]:
        if fb is None:
            return ('', '')
        met = 'да' if fb.did_meet else 'нет'
        comment = fb.comment or '-'
        return (met, comment)

    for p in pairs:
        pairing_date = p.paired_at.strftime(DATE_FORMAT)
        fb_by_user = {fb.user_id: fb for fb in p.feedbacks}
        u1_full_name = (f'{p.user1.first_name or ""} {p.user1.last_name or ""}'
                        ).strip()
        fb1 = fb_by_user.get(p.user1_id)
        u1_did_met, u1_comment = get_feedback_data(fb1)
        u2_full_name = (f'{p.user2.first_name or ""} {p.user2.last_name or ""}'
                        ).strip()
        fb2 = fb_by_user.get(p.user2_id)
        u2_did_met, u2_comment = get_feedback_data(fb2)
        rows.append([pairing_date, u1_full_name, u1_did_met, u1_comment,
                     u2_full_name, u2_did_met, u2_comment])
    logger.info(f'Сформировано строк {len(rows)-1}')

    await loop.run_in_executor(None, worksheet.clear)
    await loop.run_in_executor(None, worksheet.append_rows, rows)
    logger.info('Таблица пар с отзывами экспортирована.')
    return len(pairs)


# Служебная на время разработки
async def create_pair(session: AsyncSession,
                      user1_id: int,
                      user2_id: int) -> Pair:
    """Создает пару. Возвращает экземпляр пары."""
    pair = Pair(
                user1_id=user1_id,
                user2_id=user2_id
            )
    session.add(pair)
    try:
        await session.commit()
        await session.refresh(pair)
        return pair
    except SQLAlchemyError as e:
        await session.rollback()
        logger.exception(f'Ошибка при создании пары для {user1_id} и {user2_id}')
        raise e
