#!/usr/bin/env bash
set -e

export PGPASSWORD="$POSTGRES_PASSWORD"
export PGHOST="db"
export PGPORT="5432"
export PGUSER="$POSTGRES_USER"
export PGDATABASE="$POSTGRES_DB"

until pg_isready > /dev/null 2>&1; do
  echo "Waiting for Postgres at $PGHOST:$PGPORT (db=$PGDATABASE)…"
  sleep 1
done

alembic upgrade head
exec python random_coffee_bot/main.py