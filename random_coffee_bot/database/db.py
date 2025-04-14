from sqlalchemy import Column, Integer
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, declared_attr

from config import Config, load_config
from database.models import Base


config: Config = load_config()
database_url = config.db.db_url
engine = create_async_engine(database_url)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def create_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)  # Пока нет Alembic, будем удалять таблицы и создавать заново каждый запуск
        await conn.run_sync(Base.metadata.create_all)  # Создание всех таблиц
