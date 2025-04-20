from aiogram import Router, F
from sqlalchemy.ext.asyncio import async_sessionmaker
from aiogram.types import Message
from sqlalchemy import select
from database.models import User, Setting, Pair
from datetime import datetime
from bot import get_users_ready_for_matching
from random import shuffle
admin_router = Router()

# список всех пользователей
@admin_router.message(F.text.lower() == "/all")
async def list_participants(message: Message, session: async_sessionmaker):
    async with session() as s:
        result = await s.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()

        if not user or not user.is_admin:
            await message.answer("⛔ У вас нет доступа к этой команде.")
            return

        result = await s.execute(select(User).where(User.is_active == True))
        participants = result.scalars().all()

        if not participants:
            await message.answer("Список участников пуст.")
            return

        # вместо username можно ставить first_name and last_name когда появится функционал
        text = "👥 Участники Random Coffee:\n\n"
        for i, user in enumerate(participants, start=1):
            username = f"@{user.username}"
            interval = F'{user.pairing_interval}'
            text += f"{i}. {username}, (ID: {user.telegram_id}), Интервал встреч раз в {interval} недели\n"

        await message.answer(text)

# Удаление поьзователя
@admin_router.message(F.text.lower().startswith("/delete_user"))
async def delete_user(message: Message, session: async_sessionmaker):
    async with session() as s:
        result = await s.execute(select(User).where(User.telegram_id == message.from_user.id))
        admin = result.scalar_one_or_none()

        if not admin or not admin.is_admin:
            await message.answer("⛔ У вас нет доступа к этой команде.")
            return

        user_id_to_delete = message.text.split(" ")[1]

        if not user_id_to_delete.isdigit():
            await message.answer("Пожалуйста, укажите корректный ID пользователя. Пример: /delete_user 123456789")
            return

        user_id_to_delete = int(user_id_to_delete)

        result = await s.execute(select(User).where(User.telegram_id == user_id_to_delete))
        user_to_delete = result.scalar_one_or_none()

        if not user_to_delete:
            await message.answer(f"Пользователь с ID {user_id_to_delete} не найден.")
            return

        # Удаляем пользователя
        await s.delete(user_to_delete)
        await s.commit()

        await message.answer(f"Пользователь с ID {user_id_to_delete} был удалён.")

# Добавление поьзователя
@admin_router.message(F.text.lower().startswith("/add_user"))
async def add_user(message: Message, session: async_sessionmaker):
    async with session() as s:
        result = await s.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        admin = result.scalar_one_or_none()

        if not admin or not admin.is_admin:
            await message.answer("⛔ У вас нет доступа к этой команде.")
            return

        parts = message.text.strip().split()

        if len(parts) < 2:
            await message.answer("Пожалуйста, укажите telegram_id пользователя. Пример: /add_user 123456789")
            return

        user_id_to_add = parts[1]

        if not user_id_to_add.isdigit():
            await message.answer("⚠️ ID должен быть числом.")
            return

        user_id_to_add = int(user_id_to_add)

        result = await s.execute(select(User).where(User.telegram_id == user_id_to_add))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            await message.answer(f"Пользователь с ID {user_id_to_add} уже существует в системе.")
            return

        # Создаём нового пользователя
        new_user = User(
            telegram_id=user_id_to_add,
            is_active=True,
            is_in_group=True,
            is_blocked=False,
            is_admin=False,
            joined_at=datetime.utcnow()
        )

        s.add(new_user)
        await s.commit()

        await message.answer(f"✅ Пользователь с ID {user_id_to_add} успешно добавлен.")

# изменение интервала админом
@admin_router.message(F.text.lower().startswith("/set_interval"))
async def set_global_interval(message: Message, session: async_sessionmaker):
    async with session() as s:
        # Проверка прав
        result = await s.execute(select(User).where(User.telegram_id == message.from_user.id))
        admin = result.scalar_one_or_none()
        if not admin or not admin.is_admin:
            await message.answer("⛔ У вас нет прав использовать эту команду.")
            return

        parts = message.text.strip().split()
        if len(parts) != 2 or not parts[1].isdigit():
            await message.answer("⚠️ Укажите интервал в неделях. Пример: /set_interval 3")
            return

        interval = parts[1]

        # Сохраняем или обновляем значение
        result = await s.execute(select(Setting).where(Setting.key == "global_interval"))
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = interval
        else:
            s.add(Setting(key="global_interval", value=interval))

        await s.commit()
        await message.answer(f"✅ Глобальный интервал установлен: раз в {interval} недель.")

#формирование пар
@admin_router.message(F.text.lower().startswith("/form_pairs"))
async def form_pairs_cmd(message: Message, session: async_sessionmaker):
    async with session() as s:
        # Проверяем, админ ли отправитель
        result = await s.execute(select(User).where(User.telegram_id == message.from_user.id))
        admin = result.scalar_one_or_none()
        if not admin or not admin.is_admin:
            await message.answer("⛔ У вас нет прав использовать эту команду.")
            return

        # Получаем пользователей, готовых к подбору
        candidates = await get_users_ready_for_matching(s)

        if len(candidates) < 2:
            await message.answer("⚠️ Недостаточно пользователей для формирования пар.")
            return

        # Перемешиваем кандидатов для случайных пар
        shuffle(candidates)

        # Формируем пары
        pairs = []
        for i in range(0, len(candidates) - 1, 2):
            user1 = candidates[i]
            user2 = candidates[i + 1]
            pair = Pair(user1_id=user1.id, user2_id=user2.id)
            pairs.append(pair)

            # Обновляем дату последней пары у обоих
            user1.last_paired_at = datetime.utcnow()
            user2.last_paired_at = datetime.utcnow()

            s.add(pair)

        await s.commit()

        await message.answer(f"✅ Успешно сформировано {len(pairs)} пар.")