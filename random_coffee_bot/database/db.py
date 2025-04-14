from sqlalchemy import Column, Integer
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalhemy.orm import DeclarativeBase, declared_attr

from random_coffee_bot.config import Config, load_config


class Base(DeclarativeBase):
    pass


class CommonMixin:

    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    id = Column(Integer, primary_key=True)


config: Config = load_config()
database_url = config.db.db_url
engine = create_async_engine(database_url)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def create_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # Создание всех таблиц


if __name__ == "__db__":
    import asyncio
    asyncio.run(create_database())
