from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Config:
    token: str
    timezone: str
    db_path: Path


def load_config() -> Config:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Missing DISCORD_TOKEN in environment (.env).")

    timezone = os.getenv("BOT_TIMEZONE", "America/Chicago").strip() or "America/Chicago"

    # Store DB in ./data/bot.db (relative to repo root)
    db_path = Path("data") / "bot.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return Config(token=token, timezone=timezone, db_path=db_path)
