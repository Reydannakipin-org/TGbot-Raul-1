#!/usr/bin/env bash
set -e

# ждём, пока Postgres будет готов
until pg_isready -h db -p 5432; do
  echo "Waiting for Postgres at db:5432..."
  sleep 1
done

# прогоняем миграции (alembic.ini лежит в /app)
alembic upgrade head

# запускаем ваш бот из папки random_coffee_bot
exec python random_coffee_bot/main.py
