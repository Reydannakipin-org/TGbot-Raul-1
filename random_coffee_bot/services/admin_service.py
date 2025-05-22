import html
import logging
from datetime import date, datetime
from typing import Optional, Sequence

import asyncio
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from config import MOSCOW_TZ
from database.db import AsyncSessionLocal
from database.models import Feedback, Notification, Pair, Setting, User
from keyboards.user_buttons import meeting_question_kb
from services.constants import DATE_FORMAT, DATE_TIME_FORMAT
from services.user_service import set_user_active
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
                               input_date: Optional[date]
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


async def get_users_count(session: AsyncSession) -> tuple[int, int]:
    """
    Возвращает общее количество юзеров и количество активных.
    """
    result1 = await session.execute(
        select(func.count(User.id))
    )
    number_of_users = result1.scalar_one()
    result2 = await session.execute(
        select(func.count(User.id))
        .where(User.is_active.is_(True))
    )
    number_of_active_users = result2.scalar_one()
    return number_of_users, number_of_active_users


def create_text_with_interval(template: str,
                              current_interval: Optional[int],
                              next_pairing_date: str,
                              extra_fields: Optional[dict[str, str]] = None
                              ) -> str:
    """
    Подставляет значения для переменных interval и next_pairing_date
    в полученном тексте.
    """
    if current_interval is None:
        interval_text = ADMIN_TEXTS['no_data']
    else:
        interval_text = INTERVAL_TEXTS.get(str(current_interval),
                                           INTERVAL_TEXTS['default'])

    if next_pairing_date:
        date_text = next_pairing_date
    else:
        date_text = ADMIN_TEXTS['unknown']

    data = {
        'interval': interval_text,
        'next_pairing_date': date_text
    }

    if extra_fields:
        data.update(extra_fields)
    return template.format(**data)


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


async def get_global_interval(session: AsyncSession) -> Optional[int]:
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
        logger.info(f'Установленный интервал {current_interval.value}')
        return current_interval.value
    except SQLAlchemyError as e:
        await session.rollback()
        logger.exception('Ошибка при установке нового интервала')
        raise e


async def fetch_all_users(session: AsyncSession) -> Sequence[User]:
    """
    Извлекает из БД всех пользователей, предварительно удалив устаревшие
    даты в pause_until, сортирует по дате присоединения.
    """
    today = date.today()
    try:
        async with session.begin():
            await session.execute(
                update(User)
                .where(
                    User.pause_until.is_not(None),
                    User.pause_until <= today
                )
                .values(pause_until=None)
            )
            result = await session.execute(
                select(User).order_by(User.joined_at)
            )
            users = result.scalars().all()

        return users
    except SQLAlchemyError as e:
        logger.exception(f'Не удалось получить юзеров из БД: {e}')
        raise e


async def export_users_to_gsheet(
    users: Sequence[User]
) -> None:
    """
    Записывает данные о пользователях в Гугл Таблицу.
    """
    logger.info('Начниаем экспорт юзеров.')
    worksheet = users_sheet
    loop = asyncio.get_running_loop()

    rows: list[list[str]] = []
    headers = ['telegram_id', 'Имя', 'Фамилия', 'Активен?', 'Есть разрешение?',
               'Интервал', 'На паузе до', 'Дата присоединения',
               'Дата и время принятия политики обработки ПД']
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
        accept_policy = (u.joined_at.astimezone(MOSCOW_TZ)
                         .strftime(DATE_TIME_FORMAT))

        rows.append([telegram_id, first_name, last_name, is_active,
                     has_permission, pairing_interval, pause_until, joined_at,
                     accept_policy])
    logger.info(f'Сформировано строк {len(rows)-1}')

    await loop.run_in_executor(None, worksheet.clear)
    await loop.run_in_executor(None, worksheet.append_rows, rows)
    logger.info('Таблица юзеров экспортирована.')


async def fetch_all_pairs(session: AsyncSession) -> Sequence[Pair]:
    """
    Извлекает из БД все пары, сортирует по дате их формирования.
    """
    try:
        result = await session.execute(
            select(Pair)
            .options(
                selectinload(Pair.user1),
                selectinload(Pair.user2),
                selectinload(Pair.user3),
                selectinload(Pair.feedbacks).selectinload(Feedback.user)
            ).order_by(Pair.paired_at.desc())
        )
        pairs = result.scalars().all()
        return pairs
    except SQLAlchemyError as e:
        logger.exception(f'Не удалось получить пары из БД: {e}')
        raise e


async def export_pairs_to_gsheet(
    pairs: Sequence[Pair]
) -> None:
    """
    Записывает данные о парах в Гугл Таблицу.
    """
    logger.info('Начинаем экспорт пар и отзывов.')
    worksheet = pairs_sheet
    loop = asyncio.get_running_loop()

    rows: list[list[str]] = []
    headers = ['Дата',
               'Коллега 1', 'Была встреча?', 'Коммент',
               'Коллега 2', 'Была встреча?', 'Коммент',
               'Коллега 3', 'Была встреча?', 'Коммент']
    rows.append(headers)

    def get_feedback_data(fb: Feedback | None) -> tuple[str, str]:
        if fb is None:
            return ('', '')
        met = 'да' if fb.did_meet else 'нет'
        comment = fb.comment or '-'
        return (met, comment)

    for p in pairs:
        # на время тестирования
        pairing_date_utc = p.paired_at
        pairing_date_msk = pairing_date_utc.astimezone(MOSCOW_TZ)
        pairing_date = pairing_date_msk.strftime('%Y-%m-%d %H:%M')
        # на время тестирования
        # pairing_date = p.paired_at.strftime(DATE_FORMAT)
        fb_by_user = {fb.user_id: fb for fb in p.feedbacks}
        u1_full_name = (f'{p.user1.first_name or ""} {p.user1.last_name or ""}'
                        ).strip()
        fb1 = fb_by_user.get(p.user1_id)
        u1_did_met, u1_comment = get_feedback_data(fb1)
        u2_full_name = (f'{p.user2.first_name or ""} {p.user2.last_name or ""}'
                        ).strip()
        fb2 = fb_by_user.get(p.user2_id)
        u2_did_met, u2_comment = get_feedback_data(fb2)
        if p.user3_id:
            u3_full_name = (f'{p.user3.first_name or ""} {p.user3.last_name or ""}'
                            ).strip()
            fb3 = fb_by_user.get(p.user3_id)
            u3_did_met, u3_comment = get_feedback_data(fb3)
        else:
            u3_full_name = ''
            u3_did_met = ''
            u3_comment = ''
        rows.append([pairing_date,
                    u1_full_name, u1_did_met, u1_comment,
                    u2_full_name, u2_did_met, u2_comment,
                    u3_full_name, u3_did_met, u3_comment])

    logger.info(f'Сформировано строк {len(rows)-1}')

    await loop.run_in_executor(None, worksheet.clear)
    await loop.run_in_executor(None, worksheet.append_rows, rows)
    logger.info('Таблица пар с отзывами экспортирована.')


async def create_notif(session: AsyncSession, received_text: str
                       ) -> Notification:
    """Создает объект расслыки в БД."""
    notif = Notification(
        text=received_text
    )
    session.add(notif)
    try:
        await session.commit()
        return notif
    except SQLAlchemyError as e:
        await session.rollback()
        raise e


async def get_notif(notif_id: int) -> Notification | None:
    """Возвращает экземпляр уведомления."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Notification)
            .where(Notification.id == notif_id)
        )
        notif = result.scalar_one_or_none()
        return notif


async def mark_notif_as_sent(notif_id: int) -> None:
    """Устанавливает дату и время, когда была отправлена рассылка."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Notification)
            .where(Notification.id == notif_id)
            .values(sent_at=datetime.utcnow())
        )
        await session.commit()


async def get_active_user_ids() -> Sequence[int]:
    """Возвращает список telegram ID активных пользователей."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User.telegram_id).where(User.is_active.is_(True))
        )
        user_telegram_ids = result.scalars().all()
        return user_telegram_ids


async def broadcast_notif_to_active_users(
        bot: Bot, notif: Notification) -> tuple[int, Optional[str]]:
    """
    Отправляет рассылку активным пльзователям.
    Вовзращает количество доставленных писем.
    """
    delivered_count = 0

    try:
        user_telegram_ids = await get_active_user_ids()
    except SQLAlchemyError as e:
        logger.error(f'Ошибка при получении ID активных юзеров из БД: {e}')
        raise e
    if not user_telegram_ids:
        return 0, 'Нет активных пользователей для отправки уведомления.'

    for telegram_id in user_telegram_ids:
        try:
            await bot.send_message(telegram_id, notif.text)
            await asyncio.sleep(0.05)
            delivered_count += 1
        except TelegramForbiddenError:
            logger.warning(f'Юзер {telegram_id} заблокировал бота.')
            try:
                async with AsyncSessionLocal() as session:
                    await set_user_active(session, telegram_id, False)
                    logger.info(f'Статус юзера {telegram_id} изменен '
                                'на неактивный.')
            except SQLAlchemyError as e:
                logger.error('Не удалось изменить статус юзера '
                             f'{telegram_id} на неактивный: {e}')
        except Exception as e:
            logger.warning(f'Не получилось отправить для {telegram_id}: {e}')
    if delivered_count > 0:
        try:
            await mark_notif_as_sent(notif.id)
        except SQLAlchemyError as e:
            logger.error(f'Ошибка при работе с БД: {e}')
        return delivered_count, None
    return delivered_count, (f'Не удалось отправить уведомление ни одному '
                             f'из {len(user_telegram_ids)} пользователей.\n'
                             'Попробуйте снова немного позже. При '
                             'повторной неудаче обратитесь к разработчикам.')


async def reset_user_pause_until(session: AsyncSession, user: User) -> None:
    """Если pause_until сегодня или раньше — обнуляем это поле."""
    today = date.today()
    if user.pause_until is not None and user.pause_until <= today:
        user.pause_until = None
        try:
            await session.commit()
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error('Ошибка при очистке pause_until '
                         f'для user_id={user.id}: {e}')


async def set_first_pairing_date(recieved_date: datetime):
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Setting).where(Setting.key == 'global_interval')
            )
            current_interval = result.scalars().first()

            if not current_interval:
                current_interval = Setting(
                    key='global_interval',
                    value=2,
                    first_matching_date=recieved_date)
                session.add(current_interval)
                await session.commit()
            elif (current_interval.first_matching_date and
                  current_interval.first_matching_date < recieved_date):
                current_interval.first_matching_date = recieved_date
                await session.commit()

            logger.info(f'Установленный интервал: {current_interval.value}\n'
                        f'Записанная дата в БД: {current_interval.first_matching_date} (МСК-3)')
    except SQLAlchemyError as e:
        await session.rollback()
        logger.error(f'Ошибка при установке интервала и даты: {e}')


async def notify_users_about_pairs(session: AsyncSession,
                                   pairs: list[Pair],
                                   bot: Bot) -> None:
    """
    Отправляет сообщения участникам пар через Telegram,
    используя HTML-ссылки с tg://user?id.
    """
    await refresh_all_usernames(session, bot)

    all_ids = {
        *(p.user1_id for p in pairs),
        *(p.user2_id for p in pairs),
        *(p.user3_id for p in pairs if p.user3_id is not None)
    }
    result = await session.execute(
        select(User).where(User.id.in_(all_ids))
    )
    users = {u.id: u for u in result.scalars().all()}

    def make_link(u: User) -> str:
        name = html.escape(
            f'{u.first_name or "Пользователь"} {u.last_name or ""}'.strip())
        if u.username:
            return (
                f'👥 <a href="tg://user?id={u.telegram_id}">{name}</a> '
                f'(если имя некликабельно, попробуй так: @{u.username})'
            )
        return (
            f'👥 <a href="tg://user?id={u.telegram_id}">{name}</a> '
            '(если имя некликабельно, это означает, что пользователь '
            'запретил его упоминать, но ты можешь найти его в нашей группе)'
        )

    for pair in pairs:
        user_ids = [pair.user1_id, pair.user2_id]
        if pair.user3_id:
            user_ids.append(pair.user3_id)

        for user_id in user_ids:
            user = users.get(user_id)
            if not user or not user.telegram_id:
                logger.info(f'❗ Не удалось найти telegram_id={user_id}')
                continue

            partner_links = [
                make_link(users[p]) if (p in users and users[p].telegram_id)
                else "неизвестный пользователь"
                for p in user_ids if p != user_id
            ]

            partners_str = ",\n".join(partner_links)

            message = (
                'Привет! 🤗\n'
                'На этот раз тебе выпала возможность пообщаться с:\n'
                f'{partners_str}\n\n'
                'Пожалуйста, свяжитесь друг с другом и договорись о встрече '
                'в любом удобном формате.\n\n'
                'Прекрасной рабочей недели!'
            )

            try:
                logger.debug(f'Отправляем сообщение: {message}')
                await bot.send_message(chat_id=user.telegram_id, text=message,
                                       parse_mode="HTML")
                await asyncio.sleep(0.05)
            except TelegramForbiddenError:
                logger.warning(f'Юзер {user.telegram_id} заблокировал бота.')
                try:
                    await set_user_active(session, user.telegram_id, False)
                    logger.info(f'Статус юзера {user.telegram_id} изменен '
                                'на неактивный.')
                except SQLAlchemyError:
                    logger.exception('Не удалось изменить статус юзера '
                                     f'{user.telegram_id} на неактивный.')
            except TelegramBadRequest as e:
                if 'chat not found' in str(e).lower():
                    logger.warning(f'Юзер {user.telegram_id} удалил чат с ботом.')
                    try:
                        await set_user_active(session, user.telegram_id, False)
                        logger.info(f'Статус юзера {user.telegram_id} изменен '
                                    'на неактивный.')
                    except SQLAlchemyError:
                        logger.exception('Не удалось изменить статус юзера '
                                         f'{user.telegram_id} на неактивный.')
                else:
                    logger.exception('⚠️ Не удалось отправить сообщение для '
                                     f'telegram_id={user.telegram_id}.')
            except Exception:
                logger.exception('⚠️ Не удалось отправить сообщение для '
                                 f'telegram_id={user.telegram_id}.')


async def feedback_dispatcher_job(bot: Bot, session_maker):
    async with session_maker() as session:
        result_pairs = await session.execute(
            select(Pair).where(Pair.feedback_sent.is_(False))
        )
        pairs = result_pairs.scalars().all()

        if not pairs:
            logger.info("ℹ️ Нет новых пар для отправки опроса.")
            return

        for pair in pairs:
            user_ids = [pair.user1_id, pair.user2_id]
            if pair.user3_id:
                user_ids.append(pair.user3_id)

            result_users = await session.execute(
                select(User).where(User.id.in_(user_ids),
                                   User.has_permission.is_(True))
            )
            users = result_users.scalars().all()

            if not users:
                logger.info(f'Пара {pair.id}: нет участников, '
                            'которым разрешено пользоваться ботом.')
                continue

            kb = meeting_question_kb(pair.id)
            for user in users:
                partner_names = []
                for p in users:
                    if p.id == user.id:
                        continue
                    name = ' '.join(filter(None, (p.first_name, p.last_name)))
                    if not name:
                        name = 'коллега'
                    partner_names.append(name)
                if partner_names:
                    if len(partner_names) == 1:
                        partners_text = f'с коллегой {partner_names[0]}'
                    else:
                        partners_text = 'с коллегами ' + ', '.join(partner_names)
                    text = f'Привет! Прошла ли встреча {partners_text}?'
                else:
                    text = 'Привет! Прошла ли встреча?'

                try:
                    await bot.send_message(
                        user.telegram_id,
                        text,
                        reply_markup=kb
                    )
                    await asyncio.sleep(0.05)
                except TelegramForbiddenError:
                    logger.warning(f'Юзер {user.telegram_id} заблокировал бота.')
                    try:
                        await set_user_active(session, user.telegram_id, False)
                        logger.info(f'Статус юзера {user.telegram_id} изменен '
                                    'на неактивный.')
                    except SQLAlchemyError:
                        logger.exception('Не удалось изменить статус юзера '
                                         f'{user.telegram_id} на неактивный.')
                except TelegramBadRequest as e:
                    if 'chat not found' in str(e).lower():
                        logger.warning(f'Юзер {user.telegram_id} удалил чат с ботом.')
                        try:
                            await set_user_active(session, user.telegram_id, False)
                            logger.info(f'Статус юзера {user.telegram_id} изменен '
                                        'на неактивный.')
                        except SQLAlchemyError:
                            logger.exception('Не удалось изменить статус юзера '
                                             f'{user.telegram_id} на неактивный.')
                    else:
                        logger.exception('⚠️ Не удалось отправить сообщение для '
                                         f'telegram_id={user.telegram_id}.')
                except Exception:
                    logger.exception(f'Не удалось отправить опрос для {user.telegram_id}.')

            pair.feedback_sent = True
            try:
                await session.flush()
                logger.debug(f'✅ Пара {pair.id} помечена во flush()')
            except SQLAlchemyError:
                logger.exception(f'Неудачный flush() для пары {pair.id}')

        try:
            await session.commit()
            logger.info('Все отметки об отправке опроса парам закоммичены.')
        except SQLAlchemyError:
            logger.exception("Не удалось закоммитить отметки об отправке опроса.")


async def refresh_all_usernames(session: AsyncSession, bot: Bot) -> None:
    """Фоновая задача: пробегаем по всем users и обновляем username через get_chat."""
    result = await session.execute(select(User)
                                   .where(User.is_active.is_(True)))
    users = result.scalars().all()
    for user in users:
        try:
            chat = await bot.get_chat(user.telegram_id)
            if user.username != chat.username:
                user.username = chat.username
                session.add(user)
        except TelegramForbiddenError:
            logger.warning(f'Юзер {user.telegram_id} заблокировал бота.')
            try:
                await set_user_active(session, user.telegram_id, False)
                logger.info(f'Статус юзера {user.telegram_id} изменен '
                            'на неактивный.')
            except SQLAlchemyError:
                logger.exception('Не удалось изменить статус юзера '
                                 f'{user.telegram_id} на неактивный.')
        except TelegramBadRequest as e:
            if 'chat not found' in str(e).lower():
                logger.warning(f'Юзер {user.telegram_id} удалил чат с ботом.')
                try:
                    await set_user_active(session, user.telegram_id, False)
                    logger.info(f'Статус юзера {user.telegram_id} изменен '
                                'на неактивный.')
                except SQLAlchemyError:
                    logger.exception('Не удалось изменить статус юзера '
                                     f'{user.telegram_id} на неактивный.')
            else:
                logger.exception('⚠️ Не удалось отправить сообщение для '
                                 f'telegram_id={user.telegram_id}.')
        except Exception:
            logger.exception(f'Не удалось обновить юзернейм для {user.telegram_id}.')
    await session.commit()
