from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import Config, load_config


config: Config = load_config()
database_url = config.db.db_url
engine = create_async_engine(database_url)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
