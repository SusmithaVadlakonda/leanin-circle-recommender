"""Runtime settings, read from environment variables. See .env.example."""
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.seed import DEFAULT_DB_PATH
from app.timestamps import parse_timestamp


@dataclass(frozen=True)
class Settings:
    db_path: Path = DEFAULT_DB_PATH
    as_of: datetime | None = None  # None means the latest timestamp in the data

    @classmethod
    def from_env(cls) -> "Settings":
        db_path = os.environ.get("CIRCLES_DB_PATH", "").strip()
        as_of = os.environ.get("RECOMMENDER_AS_OF", "").strip()
        return cls(
            db_path=Path(db_path) if db_path else DEFAULT_DB_PATH,
            as_of=parse_timestamp(as_of) if as_of else None,
        )
