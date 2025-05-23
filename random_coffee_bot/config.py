from dataclasses import dataclass
from environs import Env
from pathlib import Path
from zoneinfo import ZoneInfo


MOSCOW_TZ = ZoneInfo("Europe/Moscow")


@dataclass
class DatabaseConfig:
    db_url: str


@dataclass
class TgBot:
    token: str
    group_tg_id: int
    admins_list: list


@dataclass
class GoogleSheetConfig:
    sheet_id: str


@dataclass
class Config:
    tg_bot: TgBot
    db: DatabaseConfig
    g_sheet: GoogleSheetConfig


def load_config(path: str | None = None) -> Config:
    env: Env = Env()
    default_path = Path(__file__).resolve().parent / '.env'
    env.read_env(path or default_path)

    return Config(
        tg_bot=TgBot(
            token=env('BOT_TOKEN'),
            group_tg_id=env.int('TELEGRAM_ID_PROJECT_GROUP'),
            admins_list=env.list('ADMIN_ID_LIST', subcast=int)
        ),
        db=DatabaseConfig(
            db_url=env('DATABASE_URL')
        ),
        g_sheet=GoogleSheetConfig(
            sheet_id=env('GOOGLE_SHEET_ID')
        )
    )
