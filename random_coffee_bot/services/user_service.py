from typing import Optional
import logging
import os

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Setting, User
from texts import ADMIN_TEXTS, INTERVAL_TEXTS, USER_TEXTS

logger = logging.getLogger(__name__)

folder_id = os.getenv('GOOGLE_DRIVE_FOLDER_ID')

load_dotenv()


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int
                                  ) -> Optional[User]:
    '''Получает из БД экземпляр пользователя по его telegram_id.
    Если пользователь найден, возвращает его экземпляр. В ином случае - None'''
    query = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()
    return user


async def create_user(session: AsyncSession,
                      telegram_id: int,
                      username: str | None,
                      first_name: str,
                      last_name: str | None) -> User:
    '''Создает пользователя. Возвращает экземпляр пользователя.'''
    user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
    session.add(user)
    try:
        await session.commit()
        return user
    except SQLAlchemyError as e:
        await session.rollback()
        raise e


async def update_user_field(session: AsyncSession,
                            telegram_id: int,
                            field: str,
                            value: str) -> bool:
    '''Обновляет заданное поле пользователя.
    Возвращает True, если пользователь найден и обновлен.'''
    try:
        user = await get_user_by_telegram_id(session, telegram_id)
        if not user:
            return False
        setattr(user, field, value)
        await session.commit()
        return True
    except SQLAlchemyError as e:
        await session.rollback()
        raise e


async def set_user_active(session: AsyncSession,
                          telegram_id: int,
                          is_active: bool
                          ) -> bool:
    '''Изменяет значение флага is_active.
    Возвращает True, если пользователь найден и обновлен.'''
    try:
        user = await get_user_by_telegram_id(session, telegram_id)
        if not user:
            return False
        user.is_active = is_active
        await session.commit()
        return True
    except SQLAlchemyError as e:
        await session.rollback()
        raise e


async def delete_user(session: AsyncSession, telegram_id: int) -> bool:
    '''Служебная функция на время разработки.
    Удаляет пользователя из БД.'''
    try:
        user = await get_user_by_telegram_id(session, telegram_id)
        if not user:
            return False
        await session.delete(user)
        await session.commit()
        return True
    except SQLAlchemyError as e:
        await session.rollback()
        raise e


async def create_text_random_coffee(session: AsyncSession):
    '''
    Создает текст для описание проекта Random_coffee.
    '''
    interval = await get_global_interval(session)

    message = USER_TEXTS['random_coffee_bot'].format(
        admin_interval=interval
    )
    return message


async def create_text_status_active(
    session: AsyncSession, user_id: int
) -> str:
    '''
    Создает текст с информацией для кнопки "Мой статус участия".
    '''
    user = await get_user_by_telegram_id(session, user_id)

    if user is None:
        return "Пользователь не найден."

    first_name = user.first_name or "Не указано"
    last_name = user.last_name or "Не указано"
    meetings = user.pairing_interval
    status = user.is_active

    status_text = "Активен" if status else "Неактивен"
    interval_text = (
        INTERVAL_TEXTS.get(str(meetings),
                           INTERVAL_TEXTS['default'])
    )

    if interval_text == INTERVAL_TEXTS['default']:
        admin_interval = await get_global_interval(session)
        interval_text = (
            INTERVAL_TEXTS.get(str(admin_interval),
                               INTERVAL_TEXTS['default'])
            )

    message = USER_TEXTS['participation_status'].format(
        first_name=first_name,
        last_name=last_name,
        interval=interval_text,
        status=status_text
    )

    return message


async def create_text_with_default_interval(
    session: AsyncSession, text: str, user_id: int
) -> str:
    '''
    Создает текст для ответа, когда пользователь
    передумал менять интервал встреч.
    '''
    admin_current_interval = await get_global_interval(session)
    user_current_interval = await get_user_interval(session, user_id)

    if user_current_interval is not None:
        user_key = str(user_current_interval)
        user_interval_text = (
            INTERVAL_TEXTS.get(user_key)
            if user_key
            else ADMIN_TEXTS['no_data']
        )
    else:
        user_current_interval = admin_current_interval
        user_key = str(user_current_interval)
        user_interval_text = (
            INTERVAL_TEXTS.get(user_key)
            if user_key
            else ADMIN_TEXTS['no_data']
        )

    data_text = text.format(
        current_interval=user_interval_text
    )
    return data_text


async def create_text_for_select_an_interval(session: AsyncSession, text: str) -> str:
    '''
    Создает текст для выбора интервала встреч.
    '''
    admin_current_interval = await get_global_interval(session)

    data_text = text.format(
        their_interval=admin_current_interval
    )
    return data_text


async def create_text_with_interval(
    session: AsyncSession, text: str, user_id: int
) -> str:
    '''
    Создает текст для ответа когда пользоватеь
    решил изменить интервал встреч.
    '''
    admin_current_interval = await get_global_interval(session)
    user_current_interval = await get_user_interval(session, user_id)

    admin_interval_text = (
        INTERVAL_TEXTS.get(str(admin_current_interval))
        if admin_current_interval
        else ADMIN_TEXTS['no_data']
    )

    if user_current_interval is not None:
        user_key = str(user_current_interval)
        user_interval_text = (
            INTERVAL_TEXTS.get(user_key) if user_key else ADMIN_TEXTS[
                'no_data'
            ]
        )
    else:
        user_current_interval = admin_current_interval
        user_key = str(user_current_interval)
        user_interval_text = (
            INTERVAL_TEXTS.get(user_key) if user_key else ADMIN_TEXTS[
                'no_data'
            ]
        )

    data_text = text.format(
        your_interval=user_interval_text,
        their_interval=admin_interval_text
    )
    return data_text


async def get_global_interval(session: AsyncSession) -> Optional[int]:
    '''
    Возвращает из базы данных значение глобального интервала.
    '''
    result = await session.execute(
        select(Setting.value).where(Setting.key == "global_interval")
    )
    return result.scalar()


async def get_user_interval(
    session: AsyncSession, user_id: int
) -> Optional[str]:
    '''
    Возвращает из базы данных значение интервала которое поставил пользователь.
    '''
    result = await session.execute(
        select(User.pairing_interval).where(User.telegram_id == user_id)
    )

    return result.scalar()


async def set_new_user_interval(
    session: AsyncSession, user_id: int, new_value: int | None
) -> None:
    '''
    Изменяет значение интервала для конкретного пользователя в таблице users.
    '''
    logger.info(
        f"Попытка установить новый pairing_interval: "
        f"{new_value} для пользователя с id {user_id}"
    )

    try:
        updated_user_result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        updated_user = updated_user_result.scalars().first()

        if updated_user is None:
            logger.warning(f'Пользователь с id {user_id} не найден')
            raise ValueError(f'Пользователь с id {user_id} не найден')

        logger.info(
            f"Обновлённое значение pairing_interval для пользователя до "
            f"изменения: {updated_user.pairing_interval}"
        )

        updated_user.pairing_interval = new_value
        await session.commit()

        logger.info(
            f"pairing_interval для пользователя с id "
            f"{user_id} обновлён на {new_value}"
        )

    except SQLAlchemyError as e:
        await session.rollback()
        logger.exception(
            'Ошибка при установке нового интервала для пользователя'
        )
        raise e


def upload_to_drive(file_path, file_name):
    '''
    Функция для работы с отправкой фото на гугл диск.
    '''
    SCOPES = ['https://www.googleapis.com/auth/drive']
    SERVICE_ACCOUNT_FILE = 'random_coffee_bot/credentials.json'

    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)

    service = build('drive', 'v3', credentials=credentials)

    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }

    media = MediaFileUpload(file_path, mimetype='image/jpeg')

    try:
        file = service.files().create(
            body=file_metadata, media_body=media, fields='id'
        ).execute()
        return file.get('id')
    except Exception as e:
        print(f"Ошибка при загрузке файла: {e}")
        return None


# #Временно нужно будет удалить
# async def set_new_global_interval(session: AsyncSession, new_value: int
#                                   ) -> None:
#     '''
#     Изменяет значение глобального интервала в таблице settings.
#     Возвращает True, если интервал обновлен.
#     '''
#     try:
#         result = await session.execute(
#             select(Setting).where(Setting.key == 'global_interval')
#         )
#         setting = result.scalars().first()

#         if setting:
#             setting.value = new_value
#         else:
#             setting = Setting(key='global_interval', value=new_value)
#             session.add(setting)

#         await session.commit()
#     except SQLAlchemyError as e:
#         await session.rollback()
#         logger.exception('Ошибка при установке нового интервала')
#         raise e


def parse_callback_data(data: str) -> tuple[str, str]:
    """
    Разбирает callback.data в формате 'action:us' и возвращает
    кортеж (action, param).
    """
    try:
        action, param = data.split(':', 1)
        return action, param
    except ValueError:
        logger.error(f'Неверные данные у коллбека: {data}')
        raise
