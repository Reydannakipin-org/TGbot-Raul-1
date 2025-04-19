from dataclasses import dataclass
from pathlib import Path
from environs import Env


# Этот класс используется, пока мы работаем с SQLite.
@dataclass
class DatabaseConfig:
    db_url: str


@dataclass
class TgBot:
    token: str
    admin_tg_id: int
    group_tg_id: int


@dataclass
class Config:
    tg_bot: TgBot
    db: DatabaseConfig


def load_config(path: str | None = None) -> Config:
    env: Env = Env()
    # Указываем путь к .env внутри random_coffee_bot
    default_path = Path(__file__).resolve().parent / '.env'
    env.read_env(path or default_path)

    return Config(
        tg_bot=TgBot(
            token=env('BOT_TOKEN'),
            admin_tg_id=env.int('ADMIN_TELEGRAM_ID'),
            group_tg_id=env.int('TELEGRAM_ID_TEST_GROUP')
        ),
        db=DatabaseConfig(
            db_url=env('DATABASE_URL')
        )
    )