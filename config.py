# config.py
import os
from dataclasses import dataclass
#from dotenv import load_dotenv

# Подтягиваем переменные из .env при запуске любого процесса
#load_dotenv()

def _parse_admin_ids(s):
    return [int(x.strip()) for x in (s or "").split(",") if x.strip()]

@dataclass(frozen=True)
class Settings:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    SELLER_CHAT_ID: int = int(os.getenv("SELLER_CHAT_ID", "0"))
    WEBAPP_URL: str = os.getenv("WEBAPP_URL", "")
    PORT: int = int(os.getenv("PORT", "8000"))

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./shop.db")
    MEDIA_ROOT: str = os.getenv("MEDIA_ROOT", "media")

    ADMIN_BOT_TOKEN: str = os.getenv("ADMIN_BOT_TOKEN", "")
    ADMIN_IDS: list = tuple(_parse_admin_ids(os.getenv("ADMIN_IDS", "")))

settings = Settings()
