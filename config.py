import os
from dataclasses import dataclass
from pathlib import Path

from typing import Optional

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))


def _parse_manager_ids(raw_value: Optional[str]) -> list[int]:
    if not raw_value:
        return []
    ids: list[int] = []
    for value in raw_value.split(","):
        item = value.strip()
        if not item:
            continue
        try:
            ids.append(int(item))
        except ValueError:
            continue
    return ids


@dataclass(frozen=True)
class Settings:
    bot_token: str
    manager_ids: list[int]
    db_path: Path = DATA_DIR / "bot.db"
    log_path: Path = BASE_DIR / "logs" / "bot.log"


settings = Settings(
    bot_token=os.getenv("BOT_TOKEN", "").strip(),
    manager_ids=_parse_manager_ids(os.getenv("MANAGER_IDS")),
    db_path=DATA_DIR / "bot.db",
    log_path=BASE_DIR / "logs" / "bot.log",
)
