#!/usr/bin/env bash
set -e

export PGPASSWORD="$POSTGRES_PASSWORD"

until pg_isready \
  -h db \
  -p 5432 \
  -U "$POSTGRES_USER" \
  > /dev/null 2>&1
do
  echo "Waiting for Postgres at db:5432 (user=$POSTGRES_USER)…"
  sleep 1
done

alembic upgrade head
exec python random_coffee_bot/main.py