from aiogram import types
#from aiogram.types import ParseMode
import sheets
import gspread
from oauth2client.service_account import ServiceAccountCredentials

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



async def set_schedule_handler(message: types.Message):
    # Перемещаем импорт сюда, чтобы избежать циклической зависимости
    import bot

    # Проверяем, что сообщение содержит хотя бы два слова
    parts = message.text.split()

    # Если нет второго слова (интервала), отправляем сообщение о неправильном формате
    if len(parts) < 2:
        await message.answer("Пожалуйста, укажите интервал в неделях. Пример: /active 2")
        return

    # Попытка преобразования второго слова в целое число
    try:
        new_interval = int(parts[1])
        if new_interval < 1:
            await message.answer("Интервал должен быть больше или равен 1 неделе.")
            return
    except ValueError:
        await message.answer("Интервал должен быть числом. Пример: /active 2")
        return

    # Теперь изменяем интервал и обновляем задачу
    bot.interval_weeks = new_interval  # Прямое изменение атрибута объекта bot

    # Проверяем, существует ли задача с id 'generate_pairs'
    job = bot.scheduler.get_job('generate_pairs')
    if job:
        # Удаляем задачу, если она существует
        bot.scheduler.remove_job('generate_pairs')

    # Добавляем новую задачу с обновленным интервалом
    bot.scheduler.add_job(bot.run_generation_task, 'interval', minutes=bot.interval_weeks, id='generate_pairs',
                          replace_existing=True)

    await message.answer(f"Интервал генерации пар изменен на {bot.interval_weeks} недели.")