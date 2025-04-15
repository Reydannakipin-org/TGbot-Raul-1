from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import Config, load_config
# from database.models import Base


config: Config = load_config()
database_url = config.db.db_url
engine = create_async_engine(database_url)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# Эта функция не нужна, т.к. БД создается и имзеняется через Alembic.
# async def create_database():
#     async with engine.begin() as conn:
#         await conn.run_sync(Base.metadata.drop_all)
#         await conn.run_sync(Base.metadata.create_all)
