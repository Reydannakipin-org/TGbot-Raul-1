from aiogram import types
import sheets


async def start_handler(message: types.Message):
    await message.answer("Привет! Я бот для генерации пар. Используй команду /generate для генерации пар.")


async def generate_pairs_handler(message: types.Message):
    # Подключаемся к таблицам
    sheet, sheet_pair = sheets.connect_to_sheets()

    # Генерация пар
    new_pairs = sheets.generate_pairs(sheet, sheet_pair)

    # Сохраняем новые пары
    sheets.save_new_pairs(sheet_pair, new_pairs)

    # Отправляем сообщение пользователю
    if new_pairs:
        await message.answer(f"Генерация пар завершена! Добавлено {len(new_pairs)} новых уникальных пар.")
    else:
        await message.answer("Не удалось создать новых уникальных пар.")